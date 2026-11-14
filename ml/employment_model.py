"""
ml/employment_model.py
───────────────────────
Prediction service for Phase 14: Employment Outcome ML Model.

RESPONSIBILITIES:
  - Load the trained model bundle from ml/saved_models/employment_model.pkl.
  - Expose predict_student(student) → dict with probability, label, confidence tier.
  - Expose get_model_info() → dict with metrics + metadata for the admin page.
  - Auto-train if no model file exists yet (first run).
  - All results carry a disclaimer if mode = 'demo'.

LEAKAGE GUARD:
  Only features known BEFORE the placement outcome are used:
    cgpa, skill_count, skill_match_pct, aptitude_score,
    communication_score, has_internship, profile_completion.
  Never use: company_name, salary, placement_date.
"""

import os
import logging
import numpy as np
import joblib

logger = logging.getLogger(__name__)

THIS_DIR   = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(THIS_DIR, 'saved_models', 'employment_model.pkl')

# Feature order must exactly match ml/train_model.py FEATURE_COLUMNS
FEATURE_COLUMNS = [
    'cgpa',
    'skill_count',
    'skill_match_pct',
    'aptitude_score',
    'communication_score',
    'has_internship',
    'profile_completion',
]


def _load_bundle() -> dict | None:
    """
    Load the persisted model bundle (.pkl or .joblib).
    Returns None if no model file exists (model not yet trained).
    """
    target_path = None
    if os.path.exists(MODEL_PATH):
        target_path = MODEL_PATH
    else:
        alt_path = os.path.join(THIS_DIR, 'saved_models', 'employment_model.joblib')
        if os.path.exists(alt_path):
            target_path = alt_path

    if not target_path:
        return None
    try:
        return joblib.load(target_path)
    except Exception as exc:
        logger.error(f"[employment_model] Failed to load model: {exc}")
        return None


def ensure_model_trained() -> dict | None:
    """
    Called at app startup or on first prediction request.
    If model file is missing, triggers training automatically.
    Returns the bundle dict or None on failure.
    """
    bundle = _load_bundle()
    if bundle is not None:
        return bundle

    logger.info("[employment_model] No model found. Auto-training now…")
    try:
        import sys, os as _os
        # Ensure project root is on path
        root = _os.path.dirname(THIS_DIR)
        if root not in sys.path:
            sys.path.insert(0, root)
        from ml.train_model import train_and_save
        return train_and_save()
    except Exception as exc:
        logger.error(f"[employment_model] Auto-training failed: {exc}")
        return None


def _extract_features(student) -> np.ndarray | None:
    """
    Build a 1-row feature matrix from a Student ORM object.
    Returns None if the student object is invalid or essential fields are missing.
    """
    if student is None:
        return None

    # cgpa: default 0.0 if not set
    cgpa = float(student.cgpa) if student.cgpa else 0.0

    # skill_count: number of StudentSkill rows linked to this student
    skill_count = len(student.skills) if student.skills else 0

    # skill_match_pct: from latest gap analysis (if any)
    skill_match_pct = 0.0
    if student.gap_analyses:
        from datetime import datetime as _dt
        latest = sorted(student.gap_analyses, key=lambda g: getattr(g, 'analyzed_at', _dt.min), reverse=True)[0]
        cov = getattr(latest, 'weighted_coverage_pct', None) or getattr(latest, 'unweighted_coverage_pct', None)
        if cov is not None:
            skill_match_pct = float(cov)

    # Aptitude / communication — default 50 (median) if not yet filled
    aptitude_score      = student.aptitude_score      if student.aptitude_score      is not None else 50
    communication_score = student.communication_score if student.communication_score is not None else 50

    # has_internship: 1 if at least one internship record exists
    has_internship = 1 if student.internships else 0

    # profile_completion
    profile_completion = student.profile_completion_pct or 0

    features = np.array([[
        cgpa,
        skill_count,
        skill_match_pct,
        aptitude_score,
        communication_score,
        has_internship,
        profile_completion,
    ]], dtype=float)

    return features


def predict_student(student) -> dict:
    """
    Generate a placement prediction for a student.

    Returns a dict:
      {
        'success':       bool,
        'label':         'Placed' | 'Not Placed',
        'probability':   float 0.0–1.0 (probability of Placed),
        'confidence':    'High' | 'Medium' | 'Low',
        'mode':          'real' | 'demo',
        'is_demo':       bool,
        'disclaimer':    str (non-empty only when mode == 'demo'),
        'feature_values': dict of raw feature values used,
        'error':         str (non-empty only on failure),
      }
    """
    bundle = _load_bundle()
    if bundle is None:
        # Try to train on-demand
        bundle = ensure_model_trained()

    if bundle is None:
        return {
            'success':       False,
            'label':         None,
            'probability':   None,
            'confidence':    None,
            'mode':          None,
            'is_demo':       True,
            'disclaimer':    '',
            'feature_values': {},
            'error':         'Model not available. Please ask admin to train the model first.',
        }

    features = _extract_features(student)
    if features is None:
        return {
            'success':  False,
            'label':    None,
            'error':    'Could not extract features from student profile.',
        }

    # Scale and predict
    scaler = bundle['scaler']
    model  = bundle['model']
    X_sc   = scaler.transform(features)

    prob_array   = model.predict_proba(X_sc)[0]   # [prob_not_placed, prob_placed]
    prob_placed  = float(prob_array[1])
    pred_label   = 'Placed' if prob_placed >= 0.50 else 'Not Placed'

    # Confidence tier based on probability distance from 0.5
    margin = abs(prob_placed - 0.5)
    if margin >= 0.30:
        confidence = 'High'
    elif margin >= 0.15:
        confidence = 'Medium'
    else:
        confidence = 'Low'

    mode    = bundle.get('mode', 'demo')
    is_demo = (mode == 'demo')
    disclaimer = (
        'Not enough real historical data yet: this prediction is based on synthetic/demo training data, '
        'not real historical placements. It is a statistical estimate only — not a guarantee.'
        if is_demo else
        'This is a statistical model estimate based on real historical data. '
        'It is not a guarantee of placement outcome.'
    )

    # Expose raw feature values for transparency on the UI
    fv = dict(zip(FEATURE_COLUMNS, features[0].tolist()))
    fv_labeled = {
        'CGPA':                  fv['cgpa'],
        'Skills Count':          int(fv['skill_count']),
        'Skill Match %':         round(fv['skill_match_pct'], 1),
        'Aptitude Score':        int(fv['aptitude_score']),
        'Communication Score':   int(fv['communication_score']),
        'Has Internship':        bool(fv['has_internship']),
        'Profile Completion %':  int(fv['profile_completion']),
    }

    return {
        'success':             True,
        'label':               pred_label,
        'probability':         round(prob_placed, 4),
        'probability_pct':     round(prob_placed * 100, 1),
        'confidence':          confidence,
        'mode':                mode,
        'is_demo':             is_demo,
        'disclaimer':          disclaimer,
        'feature_values':      fv_labeled,
        'feature_importances': bundle.get('feature_importances', {}),
        'error':               '',
    }


def get_model_info() -> dict:
    """
    Return model metadata + metrics for the admin model page.
    Returns a dict with 'available': False if model is not yet trained.
    """
    bundle = _load_bundle()
    if bundle is None:
        return {'available': False, 'error': 'Model not trained yet. Run python ml/train_model.py'}

    return {
        'available':           True,
        'mode':                bundle.get('mode', 'demo'),
        'is_demo':             bundle.get('mode', 'demo') == 'demo',
        'real_data_count':     bundle.get('real_data_count', 0),
        'trained_at':          bundle.get('trained_at', 'unknown'),
        'n_training_samples':  bundle.get('n_training_samples', 0),
        'metrics':             bundle.get('metrics', {}),
        'confusion_matrix':    bundle.get('confusion_matrix', []),
        'feature_importances': bundle.get('feature_importances', {}),
        'feature_columns':     bundle.get('feature_columns', FEATURE_COLUMNS),
    }
