"""
services/company_service.py
───────────────────────────
Service layer for Company-Wise Skill Gap Analysis ("Target Companies").

Features:
  - list_companies(): Distinct companies derived from active job descriptions.
  - get_company_profile(company_name): Aggregated skills categorized as Core / Common / Occasional.
  - analyze_company(student_id, company_name): Matched, missing, coverage, weighted, overall match,
    and course recommendations for missing skills.
  - compare_companies(student_id, company_names): Side-by-side comparison for up to 5 companies.
  - Session-based target company preference (no schema changes).
  - Strict ownership enforcement: Students can only view their own skill gap.
"""

from typing import Any, Dict, List, Optional, Set, Tuple
from sqlalchemy import func
from sqlalchemy.orm import joinedload, selectinload
from flask import session, has_request_context

from extensions import db
from models.student import Student
from models.skill import Skill, StudentSkill
from models.job import JobDescription, JobSkill, JobRole
from ml.company_profile import build_company_skill_profile, compute_company_skill_gap
from services.gap_service import check_student_access
from services.recommendation_service import _load_all_courses_with_skills
from ml.recommender import recommend


def _normalize_company_name(name: Optional[str]) -> str:
    """Normalize company name: trimmed string, empty string if None."""
    return str(name or '').strip()


def list_companies() -> List[Dict[str, Any]]:
    """
    Retrieve all distinct companies with active job postings.
    Loads data in exactly 2 DB queries (no N+1 queries):
      Query 1: Active job descriptions joined with job roles
      Query 2: Job skills eager-loaded via selectinload

    Returns list of dicts:
      - company_name: str (canonical display name)
      - job_count: int
      - skills_count: int (distinct required skills across all jobs at this company)
      - roles: list of str (distinct role titles)
    """
    # 1. Fetch all active jobs with roles and skills in 2 queries
    jobs = JobDescription.query.options(
        joinedload(JobDescription.job_role),
        selectinload(JobDescription.job_skills)
    ).filter(
        JobDescription.is_active == True,
        JobDescription.company_name.isnot(None),
        func.trim(JobDescription.company_name) != ''
    ).all()

    # 2. Group by lower-case trimmed company name
    grouped: Dict[str, Dict[str, Any]] = {}

    for j in jobs:
        raw_name = _normalize_company_name(j.company_name)
        if not raw_name:
            continue
        key = raw_name.lower()

        if key not in grouped:
            grouped[key] = {
                'canonical_name': raw_name,
                'name_counts': {},
                'jobs': [],
                'roles_set': set(),
                'skill_ids_set': set(),
            }

        group = grouped[key]
        group['jobs'].append(j)
        group['name_counts'][raw_name] = group['name_counts'].get(raw_name, 0) + 1

        if j.job_role and j.job_role.title:
            group['roles_set'].add(j.job_role.title)

        for js in j.job_skills:
            if js.skill_id:
                group['skill_ids_set'].add(js.skill_id)

    # 3. Format results with canonical display name
    results: List[Dict[str, Any]] = []
    for key, data in grouped.items():
        # Pick the most frequent original casing as canonical
        canonical = max(data['name_counts'].items(), key=lambda x: x[1])[0]
        results.append({
            'company_name': canonical,
            'name': canonical,
            'job_count': len(data['jobs']),
            'skills_count': len(data['skill_ids_set']),
            'skill_count': len(data['skill_ids_set']),
            'roles': sorted(data['roles_set']),
        })

    # Sort alphabetically by company name
    results.sort(key=lambda c: c['company_name'].lower())
    return results


def get_company_jobs(company_name: str) -> List[JobDescription]:
    """
    Fetch all active JobDescriptions matching the company name (case-insensitive trimmed).
    Eager-loads job skills and role.
    """
    norm = _normalize_company_name(company_name).lower()
    if not norm:
        return []

    return JobDescription.query.options(
        joinedload(JobDescription.job_role),
        selectinload(JobDescription.job_skills).joinedload(JobSkill.skill)
    ).filter(
        JobDescription.is_active == True,
        func.lower(func.trim(JobDescription.company_name)) == norm
    ).all()


def get_company_profile(company_name: str) -> Optional[Dict[str, Any]]:
    """
    Build the aggregated skill profile for a target company.

    Returns:
      Dict with company_name, total_jobs, roles, skills, core_skills, common_skills,
      occasional_skills, jobs, and most_relevant_job_id, or None if company not found.
    """
    jobs = get_company_jobs(company_name)
    if not jobs:
        return None

    # Canonical name from existing jobs
    canonical_name = jobs[0].company_name.strip()

    # Flatten job skills into rows: (job_id, skill_id, skill_name, importance)
    skill_rows: List[Dict[str, Any]] = []
    distinct_roles: Set[str] = set()

    for j in jobs:
        if j.job_role and j.job_role.title:
            distinct_roles.add(j.job_role.title)
        for js in j.job_skills:
            sname = js.skill.name if js.skill else f"Skill #{js.skill_id}"
            skill_rows.append({
                'job_id': j.id,
                'skill_id': js.skill_id,
                'skill_name': sname,
                'importance': js.importance_weight,
            })

    # Call pure function in ml/company_profile.py
    skills_profile = build_company_skill_profile(
        skill_rows,
        total_company_jobs=len(jobs)
    )

    core_skills = [s for s in skills_profile if s['classification'] == 'Core']
    common_skills = [s for s in skills_profile if s['classification'] == 'Common']
    occasional_skills = [s for s in skills_profile if s['classification'] == 'Occasional']

    # Most relevant job: job with the highest number of skills
    jobs_sorted = sorted(jobs, key=lambda j: len(j.job_skills), reverse=True)
    most_relevant_job_id = jobs_sorted[0].id if jobs_sorted else None

    return {
        'company_name': canonical_name,
        'total_jobs': len(jobs),
        'roles': sorted(distinct_roles),
        'skills': skills_profile,
        'core_skills': core_skills,
        'common_skills': common_skills,
        'occasional_skills': occasional_skills,
        'jobs': jobs,
        'most_relevant_job_id': most_relevant_job_id,
    }


def analyze_company(
    student_id: int,
    company_name: str,
    current_user: Any = None
) -> Tuple[bool, Any, int]:
    """
    Analyze skill gap for a student against a company's aggregated skill requirements.

    Enforces ownership:
      - Students can only view their own data.
      - Admins can view any student's data.

    Returns:
      (True, analysis_dict, 200) on success
      (False, error_message, status_code) on failure
    """
    # 1. Ownership check
    if current_user and not check_student_access(student_id, current_user):
        return False, "Access denied. You can only view your own skill gap analysis.", 403

    # 2. Fetch student with skills
    student = Student.query.options(
        selectinload(Student.skills).joinedload(StudentSkill.skill)
    ).filter_by(id=student_id).first()

    if not student:
        return False, "Student not found.", 404

    # 3. Fetch company profile
    company_profile = get_company_profile(company_name)
    if not company_profile:
        return False, f"Company '{company_name}' was not found or has no active job postings.", 404

    # 4. Build student skills mapping
    student_skills_map: Dict[int, Dict[str, Any]] = {}
    for ss in student.skills:
        student_skills_map[ss.skill_id] = {
            'proficiency': ss.proficiency_level,
            'name': ss.skill.name if ss.skill else f"Skill #{ss.skill_id}",
        }

    # 5. Compute gap using pure functions
    gap_result = compute_company_skill_gap(
        student_skills_map,
        company_profile['skills']
    )

    # 6. Fetch recommended courses for missing skills
    missing_for_rec: List[Dict[str, Any]] = [
        {
            'skill_id': s['skill_id'],
            'name': s['skill_name'],
            'importance': s['importance'],
            'proficiency': None,
        }
        for s in gap_result['missing_skills']
    ]

    all_courses = _load_all_courses_with_skills()
    rec_result = recommend(missing_for_rec, all_courses, top_n=3)

    # Attach courses to each missing skill item in gap_result
    courses_by_skill_id: Dict[int, List[Dict[str, Any]]] = {}
    for item in rec_result.get('items', []):
        courses_by_skill_id[item['skill_id']] = item.get('courses', [])

    for s in gap_result['missing_skills']:
        s['courses'] = courses_by_skill_id.get(s['skill_id'], [])
        s['has_courses'] = len(s['courses']) > 0

    # 7. Assemble final response
    analysis = {
        'company_name': company_profile['company_name'],
        'total_jobs': company_profile['total_jobs'],
        'roles': company_profile['roles'],
        'coverage_pct': gap_result['coverage_pct'],
        'weighted_pct': gap_result['weighted_pct'],
        'overall_match_pct': gap_result['overall_match_pct'],
        'matched_skills': gap_result['matched_skills'],
        'missing_skills': gap_result['missing_skills'],
        'extra_skills': gap_result['extra_skills'],
        'matched_count': gap_result['matched_count'],
        'missing_count': gap_result['missing_count'],
        'extra_count': gap_result['extra_count'],
        'total_required': gap_result['total_required'],
        'total_student': gap_result['total_student'],
        'core_skills': gap_result['core_skills'],
        'common_skills': gap_result['common_skills'],
        'occasional_skills': gap_result['occasional_skills'],
        'all_skills': company_profile['skills'],
        'most_relevant_job_id': company_profile['most_relevant_job_id'],
        'has_skills': len(student.skills) > 0,
    }

    return True, analysis, 200


def compare_companies(
    student_id: int,
    company_names: List[str],
    current_user: Any = None
) -> Tuple[bool, Any, int]:
    """
    Compare up to 5 target companies for a student side by side.

    Returns:
      (True, comparison_data, 200) on success
      (False, error_message, status_code) on failure
    """
    # Filter empty or duplicate names while preserving order
    unique_names: List[str] = []
    seen: Set[str] = set()
    for name in company_names:
        clean = _normalize_company_name(name)
        if clean and clean.lower() not in seen:
            seen.add(clean.lower())
            unique_names.append(clean)

    if not unique_names:
        return False, "Please select at least one company to compare.", 400

    if len(unique_names) > 5:
        return False, "You can compare up to 5 companies at a time.", 400

    # Ownership check
    if current_user and not check_student_access(student_id, current_user):
        return False, "Access denied. You can only view your own company comparison.", 403

    summaries: List[Dict[str, Any]] = []
    missing_companies: List[str] = []

    for cname in unique_names:
        ok, res_or_err, code = analyze_company(student_id, cname, current_user)
        if ok:
            summaries.append({
                'company_name': res_or_err['company_name'],
                'total_jobs': res_or_err['total_jobs'],
                'roles': res_or_err['roles'],
                'coverage_pct': res_or_err['coverage_pct'],
                'weighted_pct': res_or_err['weighted_pct'],
                'overall_match_pct': res_or_err['overall_match_pct'],
                'matched_count': res_or_err['matched_count'],
                'missing_count': res_or_err['missing_count'],
                'total_required': res_or_err['total_required'],
                'core_count': len(res_or_err['core_skills']),
                'common_count': len(res_or_err['common_skills']),
                'occasional_count': len(res_or_err['occasional_skills']),
                'most_relevant_job_id': res_or_err['most_relevant_job_id'],
            })
        else:
            missing_companies.append(cname)

    if not summaries:
        return False, f"None of the selected companies ({', '.join(unique_names)}) were found.", 404

    # Target company preference in session (no schema change)
    if summaries and has_request_context():
        try:
            session['last_compared_companies'] = [s['company_name'] for s in summaries]
        except Exception:
            pass

    return True, {
        'companies': summaries,
        'missing_companies': missing_companies,
        'count': len(summaries),
    }, 200
