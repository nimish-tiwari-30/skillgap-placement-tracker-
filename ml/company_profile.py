"""
ml/company_profile.py
─────────────────────
Pure functions for Company-Wise Skill Profile aggregation and Skill Gap calculation.

No database, Flask, or web dependencies inside this module.
Modular, deterministic, transparent, and easy to unit-test.

Formulas & Rules:
  - Demand Share:
      demand_share = jobs_requiring_skill / total_company_jobs
  - Company Importance:
      importance_avg = round(sum(importance_weights) / count, 1)
      importance     = round(importance_avg) clamped to [1, 5] (integer for weighting)
  - Classification:
      * Core:       required in 50% or more of the company's jobs (demand_share >= 0.50)
      * Common:     required in 25% to 49% of the company's jobs (0.25 <= demand_share < 0.50)
      * Occasional: required in less than 25% of the company's jobs (demand_share < 0.25)
"""

from typing import Any, Dict, List, Optional, Set, Tuple, Union
import math
from ml.skill_gap import calculate_skill_gap
from ml.job_matcher import compute_single_job_match


def classify_demand_share(demand_share: float) -> str:
    """
    Classify a skill's frequency across a company's job descriptions:
      - Core:       demand_share >= 0.50 (required in >= 50% of jobs)
      - Common:     0.25 <= demand_share < 0.50 (required in 25-49% of jobs)
      - Occasional: demand_share < 0.25 (required in < 25% of jobs)
    """
    if demand_share >= 0.50:
        return 'Core'
    elif demand_share >= 0.25:
        return 'Common'
    else:
        return 'Occasional'


def build_company_skill_profile(
    job_skill_rows: List[Any],
    total_company_jobs: Optional[int] = None,
    total_jobs: Optional[int] = None,
    **kwargs: Any
) -> List[Dict[str, Any]]:
    """
    Aggregate individual job requirements across a company into a unified skill profile.

    Parameters:
      job_skill_rows: list of dicts or tuples representing job requirements:
          - Dict: {'job_id': int, 'skill_id': int, 'skill_name': str, 'importance': int}
          - Tuple: (job_id, skill_id, skill_name, importance)
      total_company_jobs: Total number of active jobs at the company (alias: total_jobs).

    Returns:
      List of dicts, one per distinct skill:
        - skill_id: int
        - skill_name: str
        - job_count: int (number of jobs requiring this skill)
        - total_jobs: int (total company jobs)
        - demand_share: float (rounded to 3 decimals, e.g. 0.667)
        - demand_share_pct: float (rounded to 1 decimal, e.g. 66.7)
        - demand_pct: alias for demand_share_pct
        - importance_avg: float (rounded to 1 decimal, e.g. 4.3)
        - avg_importance: alias for importance_avg
        - importance: int (integer 1-5 for skill-gap weighting)
        - company_importance: alias for importance
        - classification: str ('Core', 'Common', 'Occasional')
    """
    # 1. Determine total jobs
    observed_job_ids: Set[Any] = set()
    for row in job_skill_rows:
        if isinstance(row, dict):
            jid = row.get('job_id')
        elif isinstance(row, (list, tuple)) and len(row) >= 1:
            jid = row[0]
        else:
            jid = None
        if jid is not None:
            observed_job_ids.add(jid)

    target_jobs = total_company_jobs if total_company_jobs is not None else total_jobs
    if target_jobs is not None:
        effective_total_jobs = max(0, int(target_jobs))
    else:
        effective_total_jobs = len(observed_job_ids)

    # Edge Case: Company has zero jobs or zero skill rows
    if effective_total_jobs == 0 or not job_skill_rows:
        return []

    # 2. Group skill occurrences by skill_id
    # mapping: skill_id -> {'name': str, 'job_ids': set(), 'importances': list()}
    skill_map: Dict[int, Dict[str, Any]] = {}

    for row in job_skill_rows:
        if isinstance(row, dict):
            jid = row.get('job_id')
            sid = row.get('skill_id')
            name = str(row.get('skill_name') or row.get('name') or f"Skill #{sid}").strip()
            imp = row.get('importance', 3)
        elif isinstance(row, (list, tuple)) and len(row) >= 4:
            jid = row[0]
            sid = row[1]
            name = str(row[2]).strip()
            imp = row[3]
        else:
            continue

        if sid is None:
            continue

        try:
            sid_int = int(sid)
        except (ValueError, TypeError):
            continue

        try:
            imp_int = max(1, min(5, int(imp)))
        except (ValueError, TypeError):
            imp_int = 3

        if sid_int not in skill_map:
            skill_map[sid_int] = {
                'skill_id': sid_int,
                'name': name,
                'job_ids': set(),
                'importances': [],
            }

        if jid is not None:
            skill_map[sid_int]['job_ids'].add(jid)
        skill_map[sid_int]['importances'].append(imp_int)

    # 3. Compute metrics for each skill
    profile: List[Dict[str, Any]] = []

    for sid_int, data in skill_map.items():
        job_count = len(data['job_ids'])
        # Guard against demand share > 1.0 if total_jobs was misreported
        total_for_skill = max(effective_total_jobs, job_count)

        if total_for_skill > 0:
            share = job_count / total_for_skill
        else:
            share = 0.0

        share_rounded = round(share, 3)
        share_pct = round(share * 100.0, 1)

        importances = data['importances']
        if importances:
            avg_imp = round(sum(importances) / len(importances), 1)
            # Nearest integer in 1-5
            int_imp = max(1, min(5, int(round(avg_imp))))
        else:
            avg_imp = 3.0
            int_imp = 3

        classification = classify_demand_share(share)

        profile.append({
            'skill_id': sid_int,
            'skill_name': data['name'],
            'job_count': job_count,
            'total_jobs': total_for_skill,
            'demand_share': share_rounded,
            'demand_share_pct': share_pct,
            'demand_pct': share_pct,
            'importance_avg': avg_imp,
            'avg_importance': avg_imp,
            'importance': int_imp,
            'company_importance': int_imp,
            'classification': classification,
        })

    # 4. Sort: demand_share desc, importance_avg desc, skill_name asc
    profile.sort(key=lambda s: (-s['demand_share'], -s['importance_avg'], s['skill_name'].lower()))
    return profile


def compute_company_skill_gap(
    arg1: Any,
    arg2: Any
) -> Dict[str, Any]:
    """
    Calculate the transparent skill-gap between a student's skills and a company's required skills.
    Reuses ml/skill_gap.py for exact mathematical consistency with earlier phases.

    Accepts arguments in either order:
      - compute_company_skill_gap(student_skills, company_profile)
      - compute_company_skill_gap(company_profile, student_skills)

    Parameters:
      student_skills: dict, list, or set of student skills.
          e.g. {skill_id: {'proficiency': 'Advanced', 'name': 'Python'}}
               or list of skill_ids or names.
      company_profile: List of skill dicts produced by build_company_skill_profile().

    Returns:
      Comprehensive gap analysis dict containing:
        - coverage_pct: float
        - weighted_pct: float
        - overall_match_pct: float (TF-IDF cosine similarity)
        - matched_skills: list of matched skill dicts
        - missing_skills: list of missing skill dicts
        - extra_skills: list of extra skill dicts
        - core_skills: list of Core company skills
        - common_skills: list of Common company skills
        - occasional_skills: list of Occasional company skills
        - matched_count: int
        - missing_count: int
        - extra_count: int
        - total_required: int
        - zero_required: bool
    """
    # Detect argument order
    if isinstance(arg1, list) and (not arg1 or (isinstance(arg1[0], dict) and ('company_importance' in arg1[0] or 'demand_share' in arg1[0] or 'classification' in arg1[0]))):
        company_profile: List[Dict[str, Any]] = arg1
        student_skills: Any = arg2
    else:
        student_skills: Any = arg1
        company_profile: List[Dict[str, Any]] = arg2 if isinstance(arg2, list) else []

    if not company_profile:
        return {
            'coverage_pct': 0.0,
            'weighted_pct': 0.0,
            'overall_match_pct': 0.0,
            'matched_skills': [],
            'missing_skills': [],
            'extra_skills': [],
            'matched_count': 0,
            'missing_count': 0,
            'extra_count': 0,
            'total_required': 0,
            'total_student': 0,
            'zero_required': True,
            'core_skills': [],
            'common_skills': [],
            'occasional_skills': [],
        }

    # Normalize student skills to inspect key type (strings vs IDs)
    from ml.skill_gap import _normalize_student_skills
    norm_s = _normalize_student_skills(student_skills)
    uses_string_keys = any(isinstance(k, str) and not k.isdigit() for k in norm_s.keys()) if norm_s else False

    # Build required_skills map for calculate_skill_gap
    required_map: Dict[Any, Dict[str, Any]] = {}
    profile_by_key: Dict[Any, Dict[str, Any]] = {}

    for item in company_profile:
        key = item['skill_name'] if uses_string_keys else item['skill_id']
        required_map[key] = {
            'importance': item['importance'],
            'name': item['skill_name'],
        }
        profile_by_key[key] = item

    # 1. Call existing pure function ml/skill_gap.py
    gap_result = calculate_skill_gap(student_skills, required_map)

    # 2. Enrich matched and missing skills with company profile metadata
    matched_skills: List[Dict[str, Any]] = []
    for detail in gap_result.get('matched_details', []):
        k = detail.get('skill')
        meta = profile_by_key.get(k, {})
        matched_skills.append({
            'skill_id': meta.get('skill_id', k if isinstance(k, int) else None),
            'skill_name': meta.get('skill_name', str(k)),
            'importance': detail.get('importance', meta.get('importance', 3)),
            'importance_avg': meta.get('importance_avg', 3.0),
            'demand_share': meta.get('demand_share', 0.0),
            'demand_share_pct': meta.get('demand_share_pct', 0.0),
            'classification': meta.get('classification', 'Occasional'),
            'proficiency': detail.get('proficiency'),
        })

    # Missing skills sorted by company importance desc, then demand_share desc
    missing_skills: List[Dict[str, Any]] = []
    for detail in gap_result.get('missing_details', []):
        k = detail.get('skill')
        meta = profile_by_key.get(k, {})
        missing_skills.append({
            'skill_id': meta.get('skill_id', k if isinstance(k, int) else None),
            'skill_name': meta.get('skill_name', str(k)),
            'importance': detail.get('importance', meta.get('importance', 3)),
            'importance_avg': meta.get('importance_avg', 3.0),
            'demand_share': meta.get('demand_share', 0.0),
            'demand_share_pct': meta.get('demand_share_pct', 0.0),
            'classification': meta.get('classification', 'Occasional'),
            'proficiency': None,
        })
    missing_skills.sort(key=lambda s: (-s['importance'], -s['demand_share'], s['skill_name'].lower()))

    # Extra skills
    extra_skills = gap_result.get('extra_details', [])

    # Groupings by classification for template rendering
    core_skills = [p for p in company_profile if p.get('classification') == 'Core']
    common_skills = [p for p in company_profile if p.get('classification') == 'Common']
    occasional_skills = [p for p in company_profile if p.get('classification') == 'Occasional']

    # 3. Overall match % (TF-IDF Cosine Similarity) using ml/job_matcher.py
    # Reuses existing compute_single_job_match pure function
    company_doc_skills = {
        p['skill_name']: p['importance']
        for p in company_profile
    }
    overall_match = compute_single_job_match(student_skills, company_doc_skills)

    # Edge Case: check for NaN / Inf
    if math.isnan(overall_match) or math.isinf(overall_match):
        overall_match = 0.0

    return {
        'coverage_pct': gap_result.get('coverage_pct', 0.0),
        'weighted_pct': gap_result.get('weighted_pct', 0.0),
        'overall_match_pct': round(overall_match, 1),
        'matched_skills': matched_skills,
        'missing_skills': missing_skills,
        'extra_skills': extra_skills,
        'matched_count': gap_result.get('matched_count', 0),
        'missing_count': gap_result.get('missing_count', 0),
        'extra_count': gap_result.get('extra_count', 0),
        'total_required': gap_result.get('total_required', 0),
        'total_student': gap_result.get('total_student', 0),
        'zero_required': gap_result.get('zero_required', False),
        'core_skills': core_skills,
        'common_skills': common_skills,
        'occasional_skills': occasional_skills,
    }
