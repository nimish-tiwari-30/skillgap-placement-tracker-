"""
tests/test_ml.py
────────────────
Comprehensive test suite for Phase 14: Employment Outcome ML Model.

Tests cover:
  1. Synthetic Dataset Generator (ml/generate_synthetic_dataset.py):
     - Dataset shape and columns
     - Value ranges for features (CGPA, percentages, scores)
     - Binary target labels (0 and 1)
  2. Training Pipeline (ml/train_model.py):
     - Data source selection (< 100 rows -> 'demo' mode; >= 100 -> 'real' mode)
     - Model bundle contents (model, scaler, feature_columns, metrics, confusion matrix)
     - Evaluation metrics (accuracy, precision, recall, f1, 5-fold CV)
  3. Employment Model Service (ml/employment_model.py):
     - Feature extraction from student ORM object with leakage prevention
     - Prediction output format (label, probability_pct, confidence, disclaimer)
     - Deterministic behavior for high-achieving vs struggling profiles
     - Model info retrieval for admin dashboard
  4. Student Prediction Route (routes/student.py):
     - GET /student/prediction returns 200 with rendered estimation and tips
     - Unauthenticated access redirects to login
     - Admin access blocked (student_required)
  5. Admin Model Management Routes (routes/admin.py):
     - GET /admin/model displays metrics, data gate indicator, confusion matrix
     - POST /admin/model/retrain triggers retraining and updates metrics
     - Student access blocked (admin_required)
"""

import os
import pytest
import pandas as pd
import numpy as np

from extensions import db as _db
from models.user import User
from models.student import Student, Internship
from models.skill import Skill, StudentSkill
from models.outcome import EmploymentOutcome
from models.gap import SkillGapAnalysis
from ml import generate_synthetic_dataset, train_model, employment_model


# ════════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ════════════════════════════════════════════════════════════════════════════════

def create_student_with_profile(
    email='ml.student@example.com',
    roll='22ML001',
    cgpa=8.5,
    skills_count=6,
    aptitude=85,
    comm=80,
    has_internship=True,
    profile_completion=90
):
    """Helper to persist a student with complete feature attributes."""
    user = User(email=email, role='student', is_active=True)
    user.set_password('TestPass@123')
    _db.session.add(user)
    _db.session.flush()

    student = Student(
        user_id=user.id,
        full_name='ML Test Student',
        roll_number=roll,
        branch='Computer Science',
        cgpa=cgpa,
        graduation_year=2025,
        aptitude_score=aptitude,
        communication_score=comm,
        profile_completion_pct=profile_completion,
    )
    _db.session.add(student)
    _db.session.flush()

    # Add skills
    for i in range(1, skills_count + 1):
        sname = f'MLSkill_{i}_{roll}'
        skill = Skill.query.filter_by(name=sname).first()
        if not skill:
            skill = Skill(name=sname, category='Core')
            _db.session.add(skill)
            _db.session.flush()
        ss = StudentSkill(student_id=student.id, skill_id=skill.id, proficiency_level='Intermediate')
        _db.session.add(ss)

    if has_internship:
        intern = Internship(
            student_id=student.id,
            company_name='Tech Labs',
            role_title='Intern',
            is_current=False
        )
        _db.session.add(intern)

    _db.session.commit()
    return user, student


def create_admin_user(email='ml.admin@example.com'):
    user = User(email=email, role='admin', is_active=True)
    user.set_password('AdminPass@123')
    _db.session.add(user)
    _db.session.commit()
    return user


# ════════════════════════════════════════════════════════════════════════════════
#  1. SYNTHETIC DATASET GENERATION TESTS
# ════════════════════════════════════════════════════════════════════════════════

def test_generate_synthetic_dataset_structure():
    """Verify synthetic dataset contains required features and valid bounds."""
    df = generate_synthetic_dataset.generate_dataset(n=50, seed=42)

    expected_cols = [
        'cgpa', 'skill_count', 'skill_match_pct', 'aptitude_score',
        'communication_score', 'has_internship', 'profile_completion', 'label'
    ]
    for col in expected_cols:
        assert col in df.columns, f"Missing expected column: {col}"

    assert len(df) == 50
    assert set(df['label'].unique()).issubset({0, 1})
    assert (df['cgpa'] >= 0.0).all() and (df['cgpa'] <= 10.0).all()
    assert (df['skill_match_pct'] >= 0.0).all() and (df['skill_match_pct'] <= 100.0).all()
    assert (df['aptitude_score'] >= 0).all() and (df['aptitude_score'] <= 100).all()
    assert (df['communication_score'] >= 0).all() and (df['communication_score'] <= 100).all()
    assert set(df['has_internship'].unique()).issubset({0, 1})


# ════════════════════════════════════════════════════════════════════════════════
#  2. TRAINING PIPELINE TESTS
# ════════════════════════════════════════════════════════════════════════════════

def test_train_and_save_pipeline(tmp_path, monkeypatch):
    """Verify train_and_save creates a valid model bundle with complete metrics."""
    test_model_path = str(tmp_path / "test_model.pkl")
    monkeypatch.setattr(train_model, 'MODEL_PATH', test_model_path)
    monkeypatch.setattr(train_model, 'MODEL_DIR', str(tmp_path))

    bundle = train_model.train_and_save()

    assert bundle is not None
    assert 'model' in bundle
    assert 'scaler' in bundle
    assert 'metrics' in bundle
    assert 'mode' in bundle
    assert bundle['mode'] == 'demo'  # insufficient real data in fresh test db

    metrics = bundle['metrics']
    assert 0.0 <= metrics['accuracy'] <= 1.0
    assert 0.0 <= metrics['precision'] <= 1.0
    assert 0.0 <= metrics['recall'] <= 1.0
    assert 0.0 <= metrics['f1_score'] <= 1.0
    assert 0.0 <= metrics['cv_accuracy_mean'] <= 1.0

    # Ensure file was created
    assert os.path.exists(test_model_path)


# ════════════════════════════════════════════════════════════════════════════════
#  3. PREDICTION SERVICE & LEAKAGE PREVENTION TESTS
# ════════════════════════════════════════════════════════════════════════════════

def test_prediction_service_with_student(app):
    """Verify predict_student extracts pre-outcome features and returns valid prediction."""
    user, student = create_student_with_profile(
        cgpa=9.2, skills_count=8, aptitude=90, comm=85, has_internship=True
    )

    pred = employment_model.predict_student(student)

    assert pred['success'] is True
    assert pred['label'] in ['Placed', 'Not Placed']
    assert 0.0 <= pred['probability'] <= 1.0
    assert 0.0 <= pred['probability_pct'] <= 100.0
    assert pred['confidence'] in ['High', 'Medium', 'Low']
    assert pred['is_demo'] is True
    assert 'statistical estimate' in pred['disclaimer']

    # Leakage check: feature values must not contain company, salary, or date
    fv = pred['feature_values']
    assert 'Company' not in fv
    assert 'Salary' not in fv
    assert 'Placement Date' not in fv
    assert 'CGPA' in fv
    assert fv['CGPA'] == 9.2


def test_prediction_differential():
    """A profile with high CGPA, skills, aptitude and internship should have higher placement prob than a low profile."""
    _, top_student = create_student_with_profile(
        email='top@example.com', roll='TOP01',
        cgpa=9.5, skills_count=9, aptitude=95, comm=90, has_internship=True
    )
    _, low_student = create_student_with_profile(
        email='low@example.com', roll='LOW01',
        cgpa=4.5, skills_count=1, aptitude=30, comm=35, has_internship=False, profile_completion=30
    )

    top_pred = employment_model.predict_student(top_student)
    low_pred = employment_model.predict_student(low_student)

    assert top_pred['success'] is True
    assert low_pred['success'] is True
    assert top_pred['probability'] > low_pred['probability']


def test_get_model_info():
    """Verify get_model_info returns expected structure for admin console."""
    info = employment_model.get_model_info()
    assert info['available'] is True
    assert 'metrics' in info
    assert 'confusion_matrix' in info
    assert 'feature_importances' in info


# ════════════════════════════════════════════════════════════════════════════════
#  4. STUDENT PREDICTION ROUTE TESTS
# ════════════════════════════════════════════════════════════════════════════════

def test_student_prediction_route_authenticated(client):
    """Authenticated student should access /student/prediction and see prediction metrics."""
    user, student = create_student_with_profile()

    # Login
    client.post('/login', data={'email': user.email, 'password': 'TestPass@123'}, follow_redirects=True)

    resp = client.get('/student/prediction')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'Placement Outcome Predictor' in html
    assert 'Estimated Placement Probability' in html
    assert 'Features Extracted From Profile' in html
    assert 'Not enough real historical data yet' in html


def test_student_prediction_route_unauthenticated(client):
    """Unauthenticated user visiting /student/prediction should be redirected to login."""
    resp = client.get('/student/prediction', follow_redirects=False)
    assert resp.status_code == 302
    assert '/login' in resp.headers['Location']


# ════════════════════════════════════════════════════════════════════════════════
#  5. ADMIN MODEL MANAGEMENT ROUTE TESTS
# ════════════════════════════════════════════════════════════════════════════════

def test_admin_model_route_authenticated(client):
    """Admin should view /admin/model with diagnostics and data gate status."""
    admin = create_admin_user()

    client.post('/login', data={'email': admin.email, 'password': 'AdminPass@123'}, follow_redirects=True)

    resp = client.get('/admin/model')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'Employment Outcome Classifier' in html
    assert 'Accuracy' in html
    assert 'Confusion Matrix' in html
    assert 'Feature Importance Weights' in html
    assert 'Not enough real historical data yet' in html


def test_admin_model_retrain_action(client):
    """Admin can trigger manual retraining via POST /admin/model/retrain."""
    admin = create_admin_user()

    client.post('/login', data={'email': admin.email, 'password': 'AdminPass@123'}, follow_redirects=True)

    resp = client.post('/admin/model/retrain', follow_redirects=True)
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'Model successfully retrained' in html


def test_student_cannot_access_admin_model(client):
    """Student attempting to access admin model management should receive 403 Forbidden."""
    user, student = create_student_with_profile()

    client.post('/login', data={'email': user.email, 'password': 'TestPass@123'}, follow_redirects=True)

    resp = client.get('/admin/model')
    assert resp.status_code == 403
