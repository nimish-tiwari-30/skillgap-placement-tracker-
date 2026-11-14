"""
ml/skill_gap.py
───────────────
Pure functions for skill-gap calculation.

No database, Flask, or external web dependencies inside this module.
Designed to be modular, fast, transparent, and easy to unit-test.

Formulas:
  - Matched Skills = R ∩ S
  - Missing Skills = R − S
  - Extra Skills   = S − R
  - Coverage %     = (|Matched| / |Required|) * 100
  - Weighted %     = (Σ importance of Matched / Σ importance of all Required) * 100
"""

from typing import Any, Dict, Iterable, List, Optional, Set, Tuple, Union


def _normalize_student_skills(skills: Any) -> Dict[Any, Dict[str, Any]]:
    """
    Normalize student skills into a consistent dictionary:
    { skill_key: {'proficiency': Optional[str], 'original': Any} }
    """
    norm: Dict[Any, Dict[str, Any]] = {}
    if not skills:
        return norm

    if isinstance(skills, dict):
        for k, v in skills.items():
            if isinstance(v, dict):
                prof = v.get('proficiency') or v.get('proficiency_level')
            else:
                prof = str(v) if v is not None else None
            norm[k] = {'proficiency': prof, 'original': k}
    elif isinstance(skills, (list, tuple, set)):
        for item in skills:
            if isinstance(item, dict):
                key = item.get('id') if 'id' in item else (item.get('name') or item.get('skill'))
                prof = item.get('proficiency') or item.get('proficiency_level')
                if key is not None:
                    norm[key] = {'proficiency': prof, 'original': item}
            else:
                norm[item] = {'proficiency': None, 'original': item}
    return norm


def _normalize_required_skills(skills: Any) -> Dict[Any, Dict[str, Any]]:
    """
    Normalize required skills into a consistent dictionary:
    { skill_key: {'importance': int (1-5), 'original': Any} }
    """
    norm: Dict[Any, Dict[str, Any]] = {}
    if not skills:
        return norm

    if isinstance(skills, dict):
        for k, v in skills.items():
            if isinstance(v, dict):
                imp = v.get('importance') or v.get('importance_weight') or 3
            else:
                try:
                    imp = int(v)
                except (ValueError, TypeError):
                    imp = 3
            imp = max(1, min(5, imp))
            norm[k] = {'importance': imp, 'original': k}
    elif isinstance(skills, (list, tuple, set)):
        for item in skills:
            if isinstance(item, dict):
                key = item.get('id') if 'id' in item else (item.get('name') or item.get('skill'))
                imp = item.get('importance') or item.get('importance_weight') or 3
                try:
                    imp = int(imp)
                except (ValueError, TypeError):
                    imp = 3
                imp = max(1, min(5, imp))
                if key is not None:
                    norm[key] = {'importance': imp, 'original': item}
            elif isinstance(item, (tuple, list)) and len(item) >= 2:
                key = item[0]
                try:
                    imp = int(item[1])
                except (ValueError, TypeError):
                    imp = 3
                imp = max(1, min(5, imp))
                norm[key] = {'importance': imp, 'original': item}
            else:
                norm[item] = {'importance': 3, 'original': item}
    return norm


def calculate_skill_gap(
    student_skills: Any,
    required_skills: Any
) -> Dict[str, Any]:
    """
    Compute transparent skill-gap analysis comparing student skills against job required skills.

    Parameters:
      student_skills:
        Set, list, or dict of skills possessed by the student.
        Optionally includes proficiency levels ('Beginner', 'Intermediate', 'Advanced').
      required_skills:
        Set, list, or dict of skills required by the job.
        Optionally includes importance weight (1-5, defaults to 3).

    Returns:
      dict with:
        coverage_pct: float (rounded to 1 decimal place, e.g. 50.0)
        weighted_pct: float (rounded to 1 decimal place, e.g. 57.1)
        matched: list of matched skill identifiers
        missing: list of missing skill identifiers (ordered by importance descending)
        extra: list of extra skill identifiers
        matched_details: list of dicts with skill, importance, proficiency
        missing_details: list of dicts with skill, importance (ordered by importance desc)
        extra_details: list of dicts with skill, proficiency
        matched_count: int
        missing_count: int
        extra_count: int
        total_required: int
        total_student: int
        zero_required: bool
    """
    s_norm = _normalize_student_skills(student_skills)
    r_norm = _normalize_required_skills(required_skills)

    s_set: Set[Any] = set(s_norm.keys())
    r_set: Set[Any] = set(r_norm.keys())

    # Pure set operations
    matched_keys = r_set.intersection(s_set)
    missing_keys = r_set.difference(s_set)
    extra_keys = s_set.difference(r_set)

    total_required = len(r_set)
    total_student = len(s_set)

    # Edge Case: Job has 0 required skills
    if total_required == 0:
        extra_details = [
            {
                'skill': k,
                'proficiency': s_norm[k].get('proficiency'),
                'meta': s_norm[k].get('original'),
            }
            for k in sorted(extra_keys, key=lambda x: str(x).lower())
        ]
        return {
            'coverage_pct': 0.0,
            'weighted_pct': 0.0,
            'matched': [],
            'missing': [],
            'extra': [d['skill'] for d in extra_details],
            'matched_details': [],
            'missing_details': [],
            'extra_details': extra_details,
            'matched_count': 0,
            'missing_count': 0,
            'extra_count': len(extra_keys),
            'total_required': 0,
            'total_student': total_student,
            'zero_required': True,
        }

    # Coverage percentage = (matched required / total required) * 100
    matched_count = len(matched_keys)
    coverage_pct = round((matched_count / total_required) * 100.0, 1)

    # Weighted percentage = sum(importance of matched) / sum(importance of all required) * 100
    total_importance = sum(r_norm[k]['importance'] for k in r_set)
    matched_importance = sum(r_norm[k]['importance'] for k in matched_keys)

    if total_importance > 0:
        weighted_pct = round((matched_importance / total_importance) * 100.0, 1)
    else:
        weighted_pct = 0.0

    # Build missing skills details sorted by importance descending (tie-break alphabetically)
    missing_details = [
        {
            'skill': k,
            'importance': r_norm[k]['importance'],
            'meta': r_norm[k].get('original'),
        }
        for k in missing_keys
    ]
    missing_details.sort(key=lambda item: (-item['importance'], str(item['skill']).lower()))

    # Build matched skills details sorted by importance descending
    matched_details = [
        {
            'skill': k,
            'importance': r_norm[k]['importance'],
            'proficiency': s_norm[k].get('proficiency'),
            'meta': r_norm[k].get('original'),
        }
        for k in matched_keys
    ]
    matched_details.sort(key=lambda item: (-item['importance'], str(item['skill']).lower()))

    # Build extra skills details sorted alphabetically
    extra_details = [
        {
            'skill': k,
            'proficiency': s_norm[k].get('proficiency'),
            'meta': s_norm[k].get('original'),
        }
        for k in extra_keys
    ]
    extra_details.sort(key=lambda item: str(item['skill']).lower())

    return {
        'coverage_pct': coverage_pct,
        'weighted_pct': weighted_pct,
        'matched': [m['skill'] for m in matched_details],
        'missing': [m['skill'] for m in missing_details],
        'extra': [e['skill'] for e in extra_details],
        'matched_details': matched_details,
        'missing_details': missing_details,
        'extra_details': extra_details,
        'matched_count': matched_count,
        'missing_count': len(missing_keys),
        'extra_count': len(extra_keys),
        'total_required': total_required,
        'total_student': total_student,
        'zero_required': False,
    }
