"""
ml/train_model.py
──────────────────
Training pipeline for the Employment Outcome Random Forest Classifier.

HOW IT WORKS:
  1. Count REAL labeled outcomes from the DB.
  2. If real data >= 100 rows: train on real data (mode = 'real').
  3. Else: fall back to synthetic data (mode = 'demo') and show disclaimer.
  4. Train a RandomForestClassifier, evaluate on a held-out test split,
     then persist the model + metadata as a .pkl file in ml/saved_models/.

Usage (from project root):
  python ml/train_model.py

Output:
  ml/saved_models/employment_model.pkl  — serialised model bundle
"""

import os
import sys
import json
import joblib
import numpy as np
import pandas as pd
from datetime import datetime

from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    confusion_matrix, classification_report
)
from sklearn.preprocessing import StandardScaler

# ── Paths ────────────────────────────────────────────────────────────────────
THIS_DIR   = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR   = os.path.dirname(THIS_DIR)
MODEL_DIR  = os.path.join(THIS_DIR, 'saved_models')
MODEL_PATH = os.path.join(MODEL_DIR, 'employment_model.pkl')
SYNTH_CSV  = os.path.join(THIS_DIR, 'data', 'synthetic_training.csv')

# Features used for training — must match ml/employment_model.py exactly
FEATURE_COLUMNS = [
    'cgpa',
    'skill_count',
    'skill_match_pct',
    'aptitude_score',
    'communication_score',
    'has_internship',
    'profile_completion',
]
TARGET_COLUMN = 'label'
REAL_DATA_THRESHOLD = 100   # below this, fall back to synthetic


def _load_real_data() -> tuple[pd.DataFrame | None, int]:
    """
    Query the DB for students with a resolved placement outcome.
    Returns (DataFrame or None, count_of_labeled_rows).

    Joins: students → employment_outcomes → student_skills (aggregated)
    Label: 1 = Placed, 0 = Not Placed  (skips 'In Progress')
    Leakage check: only features known BEFORE outcome are included.
    """
    sys.path.insert(0, ROOT_DIR)
    from app import create_app
    from extensions import db
    from models.student import Student
    from models.outcome import EmploymentOutcome
    from models.gap import SkillGapAnalysis
    from sqlalchemy import func

    app = create_app()
    with app.app_context():
        # Count how many student-outcomes are labeled (Placed / Not Placed)
        labeled_outcomes = (
            EmploymentOutcome.query
            .filter(EmploymentOutcome.status.in_(['Placed', 'Not Placed']))
            .all()
        )
        count = len(labeled_outcomes)
        if count < REAL_DATA_THRESHOLD:
            return None, count

        rows = []
        for outcome in labeled_outcomes:
            st: Student = outcome.student
            if not st:
                continue

            # Count student skills
            skill_count = len(st.skills) if st.skills else 0

            # Latest gap analysis for skill_match_pct
            latest_gap = (
                SkillGapAnalysis.query
                .filter_by(student_id=st.id)
                .order_by(SkillGapAnalysis.analyzed_at.desc())
                .first()
            )
            cov = getattr(latest_gap, 'weighted_coverage_pct', None) or getattr(latest_gap, 'unweighted_coverage_pct', None) if latest_gap else None
            skill_match_pct = float(cov) if cov is not None else 0.0

            rows.append({
                'cgpa':                 float(st.cgpa) if st.cgpa else 0.0,
                'skill_count':          skill_count,
                'skill_match_pct':      skill_match_pct,
                'aptitude_score':       st.aptitude_score if st.aptitude_score is not None else 50,
                'communication_score':  st.communication_score if st.communication_score is not None else 50,
                'has_internship':       1 if st.internships else 0,
                'profile_completion':   st.profile_completion_pct or 0,
                'label':                1 if outcome.status == 'Placed' else 0,
            })

        return pd.DataFrame(rows), count


def _load_synthetic_data() -> pd.DataFrame:
    """Generate synthetic dataset if CSV not already present."""
    if not os.path.exists(SYNTH_CSV):
        print("[INFO] Synthetic CSV not found. Generating...")
        from ml.generate_synthetic_dataset import generate_dataset
        df = generate_dataset()
        os.makedirs(os.path.dirname(SYNTH_CSV), exist_ok=True)
        df.to_csv(SYNTH_CSV, index=False)
    else:
        df = pd.read_csv(SYNTH_CSV)
    return df


def train_and_save():
    """Main training function. Called from CLI or app startup."""
    os.makedirs(MODEL_DIR, exist_ok=True)

    # ── 1. Decide data source ────────────────────────────────────────────────
    print("[PHASE 14] Loading data...")
    real_df, real_count = _load_real_data()

    if real_df is not None and len(real_df) >= REAL_DATA_THRESHOLD:
        df   = real_df
        mode = 'real'
        print(f"[OK] Using REAL data: {len(df)} rows (labeled outcomes)")
    else:
        df   = _load_synthetic_data()
        mode = 'demo'
        print(f"[DEMO] Real data insufficient ({real_count} rows < {REAL_DATA_THRESHOLD}). Using synthetic data.")

    # ── 2. Prepare features + target ────────────────────────────────────────
    X = df[FEATURE_COLUMNS].values.astype(float)
    y = df[TARGET_COLUMN].values.astype(int)

    # ── 3. Train / test split ────────────────────────────────────────────────
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=42, stratify=y
    )

    # ── 4. Scale features (helps some estimators; RF is invariant but nice for API) ──
    scaler = StandardScaler()
    X_train_sc = scaler.fit_transform(X_train)
    X_test_sc  = scaler.transform(X_test)

    # ── 5. Train RandomForestClassifier ──────────────────────────────────────
    clf = RandomForestClassifier(
        n_estimators=200,
        max_depth=8,
        min_samples_leaf=4,
        class_weight='balanced',   # handles class imbalance automatically
        random_state=42,
        n_jobs=-1,
    )
    clf.fit(X_train_sc, y_train)

    # ── 6. Evaluate ──────────────────────────────────────────────────────────
    y_pred = clf.predict(X_test_sc)
    accuracy  = accuracy_score(y_test, y_pred)
    precision = precision_score(y_test, y_pred, zero_division=0)
    recall    = recall_score(y_test, y_pred, zero_division=0)
    f1        = f1_score(y_test, y_pred, zero_division=0)
    cm        = confusion_matrix(y_test, y_pred).tolist()

    # Cross-validation accuracy (5-fold, on full dataset)
    cv_scores = cross_val_score(clf, scaler.transform(X), y, cv=5, scoring='accuracy')

    # Feature importances as a dict for the admin model page
    feature_importances = {
        col: round(float(imp), 4)
        for col, imp in zip(FEATURE_COLUMNS, clf.feature_importances_)
    }

    print(f"\n-- Evaluation Results ----------------------------------")
    print(f"  Accuracy  : {accuracy:.3f}")
    print(f"  Precision : {precision:.3f}")
    print(f"  Recall    : {recall:.3f}")
    print(f"  F1 Score  : {f1:.3f}")
    print(f"  CV Acc.   : {cv_scores.mean():.3f} +/- {cv_scores.std():.3f}")
    print(f"  Confusion Matrix: {cm}")
    print(f"  Feature Importances: {feature_importances}")

    # ── 7. Persist model bundle ──────────────────────────────────────────────
    bundle = {
        'model':              clf,
        'scaler':             scaler,
        'feature_columns':    FEATURE_COLUMNS,
        'mode':               mode,           # 'real' or 'demo'
        'real_data_count':    real_count,
        'trained_at':         datetime.utcnow().isoformat(),
        'n_training_samples': len(X_train),
        'metrics': {
            'accuracy':   round(accuracy, 4),
            'precision':  round(precision, 4),
            'recall':     round(recall, 4),
            'f1_score':   round(f1, 4),
            'cv_accuracy_mean': round(float(cv_scores.mean()), 4),
            'cv_accuracy_std':  round(float(cv_scores.std()), 4),
        },
        'confusion_matrix':    cm,
        'feature_importances': feature_importances,
    }
    joblib.dump(bundle, MODEL_PATH)
    # Also save .joblib and JSON metrics for server / deployment compatibility
    joblib_path = os.path.join(MODEL_DIR, 'employment_model.joblib')
    joblib.dump(bundle, joblib_path)
    metrics_path = os.path.join(MODEL_DIR, 'employment_metrics.json')
    try:
        with open(metrics_path, 'w', encoding='utf-8') as mf:
            json.dump(bundle.get('metrics', {}), mf, indent=2)
    except Exception as e:
        print(f"Warning: Could not write metrics json: {e}")

    print(f"\n[OK] Model saved -> {MODEL_PATH} and {joblib_path}")
    return bundle


if __name__ == '__main__':
    train_and_save()
