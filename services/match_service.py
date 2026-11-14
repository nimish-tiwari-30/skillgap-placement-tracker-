"""
services/match_service.py
─────────────────────────
Service layer for Job Matching via TF-IDF & Cosine Similarity (Phase 9).

Key Design Principles:
  - High Efficiency (No N+1 queries):
    Eagerly loads student skills, active jobs, roles, and job skills using
    SQLAlchemy joinedload and selectinload in 3 optimized queries total.
  - Reuses ml/skill_gap.py for Coverage % and Weighted % (no code duplication).
  - Uses ml/job_matcher.py for TF-IDF Cosine Similarity across the complete job corpus.
  - Enforces student data ownership.
  - Neutral terminology throughout: no claims of "recommendation" or hiring prediction.
"""

from typing import Any, Dict, List, Optional, Tuple, Union
from sqlalchemy.orm import joinedload, selectinload

from extensions import db
from models.job import JobDescription, JobSkill
from models.skill import Skill, StudentSkill
from models.student import Student
from ml.skill_gap import calculate_skill_gap
from ml.job_matcher import compute_job_matches, compute_single_job_match


def check_student_access(student_id: int, user: Any) -> bool:
    """
    Enforce ownership rule:
      - Admin users have full access.
      - Student users can only access their own student records.
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if user.is_admin():
        return True
    if user.is_student() and user.student and user.student.id == student_id:
        return True
    return False


def match_student_to_all_jobs(
    student_id: int,
    current_user: Any = None,
    search: Optional[str] = None,
    role_id: Optional[int] = None,
    sort_by: str = 'overall_match'
) -> Tuple[bool, Union[List[Dict[str, Any]], str]]:
    """
    Match a student's skills against all active jobs in the system.

    Efficiency Check:
      Executes only 3 SQL queries regardless of job count:
        1. Student + StudentSkill + Skill (selectinload / joinedload)
        2. JobDescription + JobRole (joinedload)
        3. JobSkill + Skill (selectinload / joinedload)
      No N+1 query per job!

    Returns:
      (True, jobs_match_list) on success
      (False, error_message) on failure
    """
    if current_user and not check_student_access(student_id, current_user):
        return False, "Access denied. You can only view your own job match calculations."

    # Query 1: Eager load student and their skills
    student = (
        Student.query
        .options(selectinload(Student.skills).joinedload(StudentSkill.skill))
        .filter_by(id=student_id)
        .first()
    )
    if not student:
        return False, "Student not found."

    # Query 2 & 3: Eager load all active jobs and all their job_skills
    jobs_query = (
        JobDescription.query
        .filter_by(is_active=True)
        .options(
            joinedload(JobDescription.job_role),
            selectinload(JobDescription.job_skills).joinedload(JobSkill.skill)
        )
    )

    if role_id:
        jobs_query = jobs_query.filter(JobDescription.job_role_id == role_id)
    if search:
        term = f"%{search.strip()}%"
        jobs_query = jobs_query.filter(
            (JobDescription.title.ilike(term)) |
            (JobDescription.company_name.ilike(term)) |
            (JobDescription.description_text.ilike(term))
        )

    all_jobs: List[JobDescription] = jobs_query.all()
    if not all_jobs:
        return True, []

    # Map student skills by canonical name and proficiency
    student_skills_by_name = {
        ss.skill.name: ss.proficiency_level
        for ss in student.skills if ss.skill
    }
    # Map student skills by ID for calculate_skill_gap
    student_skills_by_id = {
        ss.skill_id: {'proficiency': ss.proficiency_level, 'name': ss.skill.name if ss.skill else ''}
        for ss in student.skills
    }

    # Prepare job skills list for TF-IDF corpus
    job_skills_corpus: List[Dict[str, int]] = []
    gap_results: List[Dict[str, Any]] = []

    for job in all_jobs:
        # Skills by name for TF-IDF
        j_skills_name = {
            js.skill.name: js.importance_weight
            for js in job.job_skills if js.skill
        }
        job_skills_corpus.append(j_skills_name)

        # Skills by ID for calculate_skill_gap
        j_skills_id = {
            js.skill_id: {'importance': js.importance_weight, 'name': js.skill.name if js.skill else ''}
            for js in job.job_skills
        }
        gap = calculate_skill_gap(student_skills_by_id, j_skills_id)
        gap_results.append(gap)

    # Compute TF-IDF Cosine Similarity for all jobs simultaneously
    cosine_scores = compute_job_matches(student_skills_by_name, job_skills_corpus)

    # Assemble structured results
    results: List[Dict[str, Any]] = []
    target_job_id = getattr(student, 'target_job_id', None)

    for i, job in enumerate(all_jobs):
        gap = gap_results[i]
        sim_score = cosine_scores[i] if i < len(cosine_scores) else 0.0

        results.append({
            'job_id': job.id,
            'title': job.title,
            'company_name': job.company_name,
            'role_title': job.job_role.title if job.job_role else '',
            'location': job.location or 'Remote',
            'min_experience': job.min_experience or '0-1 years',
            'coverage_pct': gap['coverage_pct'],
            'weighted_pct': gap['weighted_pct'],
            'overall_match_pct': sim_score,
            'matched_count': gap['matched_count'],
            'missing_count': gap['missing_count'],
            'total_required': gap['total_required'],
            'is_target_job': (target_job_id == job.id),
        })

    # Sort results
    if sort_by == 'coverage':
        results.sort(key=lambda x: (-x['coverage_pct'], -x['overall_match_pct'], x['title'].lower()))
    elif sort_by == 'title':
        results.sort(key=lambda x: x['title'].lower())
    else:  # default: 'overall_match' descending
        results.sort(key=lambda x: (-x['overall_match_pct'], -x['coverage_pct'], x['title'].lower()))

    return True, results


def match_student_to_job(
    student_id: int,
    job_id: int,
    current_user: Any = None
) -> Tuple[bool, Union[Dict[str, Any], str]]:
    """
    Detailed match analysis for a single job against a student's profile.
    Includes Coverage %, Weighted %, Overall Match %, matched skills,
    missing skills ordered by importance, and extra skills.
    """
    if current_user and not check_student_access(student_id, current_user):
        return False, "Access denied. You can only view your own match details."

    student = (
        Student.query
        .options(selectinload(Student.skills).joinedload(StudentSkill.skill))
        .filter_by(id=student_id)
        .first()
    )
    if not student:
        return False, "Student not found."

    job = (
        JobDescription.query
        .options(
            joinedload(JobDescription.job_role),
            selectinload(JobDescription.job_skills).joinedload(JobSkill.skill)
        )
        .filter_by(id=job_id, is_active=True)
        .first()
    )
    if not job:
        return False, "Job opportunity not found or is inactive."

    # Build inputs for skill_gap
    student_skills_by_id = {
        ss.skill_id: {'proficiency': ss.proficiency_level, 'name': ss.skill.name if ss.skill else ''}
        for ss in student.skills
    }
    job_skills_by_id = {
        js.skill_id: {'importance': js.importance_weight, 'name': js.skill.name if js.skill else ''}
        for js in job.job_skills
    }

    gap = calculate_skill_gap(student_skills_by_id, job_skills_by_id)

    # Build inputs for TF-IDF
    student_skills_by_name = {
        ss.skill.name: ss.proficiency_level
        for ss in student.skills if ss.skill
    }
    job_skills_by_name = {
        js.skill.name: js.importance_weight
        for js in job.job_skills if js.skill
    }

    overall_match_pct = compute_single_job_match(student_skills_by_name, job_skills_by_name)

    skill_name_map = {js.skill_id: js.skill.name for js in job.job_skills if js.skill}
    skill_name_map.update({ss.skill_id: ss.skill.name for ss in student.skills if ss.skill})

    # Format detailed skill items
    matched_skills = []
    for m in gap['matched_details']:
        s_id = m['skill']
        matched_skills.append({
            'skill_id': s_id,
            'name': skill_name_map.get(s_id, f"Skill #{s_id}"),
            'importance': m['importance'],
            'proficiency': m.get('proficiency'),
        })

    missing_skills = []
    for m in gap['missing_details']:
        s_id = m['skill']
        missing_skills.append({
            'skill_id': s_id,
            'name': skill_name_map.get(s_id, f"Skill #{s_id}"),
            'importance': m['importance'],
        })

    extra_skills = []
    for e in gap['extra_details']:
        s_id = e['skill']
        extra_skills.append({
            'skill_id': s_id,
            'name': skill_name_map.get(s_id, f"Skill #{s_id}"),
            'proficiency': e.get('proficiency'),
        })

    target_job_id = getattr(student, 'target_job_id', None)

    return True, {
        'job_id': job.id,
        'title': job.title,
        'company_name': job.company_name,
        'role_title': job.job_role.title if job.job_role else '',
        'location': job.location or 'Remote',
        'min_experience': job.min_experience or '0-1 years',
        'description_text': job.description_text,
        'coverage_pct': gap['coverage_pct'],
        'weighted_pct': gap['weighted_pct'],
        'overall_match_pct': overall_match_pct,
        'matched_count': gap['matched_count'],
        'missing_count': gap['missing_count'],
        'extra_count': gap['extra_count'],
        'matched': [item['name'] for item in matched_skills],
        'missing': [item['name'] for item in missing_skills],
        'extra': [item['name'] for item in extra_skills],
        'matched_skills': matched_skills,
        'missing_skills': missing_skills,
        'extra_skills': extra_skills,
        'is_target_job': (target_job_id == job.id),
    }
