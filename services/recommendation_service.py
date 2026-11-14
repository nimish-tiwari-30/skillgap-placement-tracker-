"""
services/recommendation_service.py
────────────────────────────────────
Service layer for Phase 10: Course Recommendation.

Reuses Phase 8 gap logic (gap_service.analyze) to find missing skills,
then calls ml/recommender.py (pure functions) to get ranked courses.

No N+1 queries: courses and their skill tags are loaded in 2 DB queries.
Ownership enforced: a student can only get their own recommendations.
"""

from typing import Any, Dict, List, Optional, Tuple

from extensions import db
from models.student import Student
from models.job import JobDescription, JobSkill
from models.skill import Skill, StudentSkill
from models.course import Course, CourseSkill
from sqlalchemy.orm import joinedload, selectinload

from ml.recommender import recommend
from services.gap_service import check_student_access


def _get_missing_skills_for_job(student: Student, job: JobDescription) -> List[Dict[str, Any]]:
    """
    Compute missing skills for a student vs job WITHOUT saving to DB.
    Reuses Phase 8 ml/skill_gap.py logic.

    Returns list of dicts: {skill_id, name, importance, proficiency or None}
    ordered by importance descending.
    """
    from ml.skill_gap import calculate_skill_gap

    # Build student skills mapping: skill_id -> {proficiency, name}
    student_skills_map: Dict[int, Any] = {}
    for ss in student.skills:
        student_skills_map[ss.skill_id] = {
            'proficiency': ss.proficiency_level,
            'name': ss.skill.name if ss.skill else f"Skill #{ss.skill_id}",
        }

    # Build job required skills mapping: skill_id -> {importance, name}
    job_skills_map: Dict[int, Any] = {}
    for js in job.job_skills:
        job_skills_map[js.skill_id] = {
            'importance': js.importance_weight,
            'name': js.skill.name if js.skill else f"Skill #{js.skill_id}",
        }

    # Calculate gap using the same pure function as Phase 8
    gap_result = calculate_skill_gap(student_skills_map, job_skills_map)

    # Build structured missing skill list (with importance and optional proficiency)
    missing_details = []
    for detail in gap_result['missing_details']:
        sid = detail['skill']  # skill_id (int key from the map)
        name = job_skills_map.get(sid, {}).get('name', f"Skill #{sid}")
        missing_details.append({
            'skill_id':   sid,
            'name':       name,
            'importance': detail['importance'],
            'proficiency': None,   # Student doesn't have this skill at all
        })

    # Already sorted by importance desc from ml/skill_gap.py, but ensure it here
    missing_details.sort(key=lambda x: (-x['importance'], x['name'].lower()))
    return missing_details


def _load_all_courses_with_skills() -> List[Dict[str, Any]]:
    """
    Load ALL courses and their skill tags in exactly 2 DB queries (no N+1):
      Query 1: SELECT * FROM courses
      Query 2: SELECT * FROM course_skills (via selectinload)

    Returns list of plain dicts (not ORM objects) ready for ml/recommender.py.
    """
    # Eager-load course_skills in one round trip
    courses_orm = Course.query.options(
        selectinload(Course.course_skills)
    ).all()

    course_dicts = []
    for c in courses_orm:
        skill_ids = [cs.skill_id for cs in c.course_skills]
        course_dicts.append({
            'course_id':       c.id,
            'title':           c.title,
            'provider':        c.provider or '',
            'difficulty_level': c.difficulty_level,
            'duration_hours':  float(c.duration_hours) if c.duration_hours else None,
            'rating':          float(c.rating) if c.rating else None,
            'url':             c.url or '#',
            'description':     c.description or '',
            'skill_ids':       skill_ids,
        })

    return course_dicts


def recommend_for_job(
    student_id: int,
    job_id: int,
    current_user: Any = None,
    top_n: int = 3,
) -> Tuple[bool, Any]:
    """
    Get course recommendations for a student's missing skills for a target job.

    Steps:
      1. Ownership check
      2. Fetch student + job (with eager loading for skills)
      3. Compute missing skills using Phase 8 gap logic
      4. Load ALL courses with skill tags (2 queries, no N+1)
      5. Call ml/recommender.py pure function
      6. Return structured result

    Returns:
      (True, result_dict)  on success
      (False, error_str)   on failure
    """
    # --- Ownership check ---
    if current_user and not check_student_access(student_id, current_user):
        return False, "Access denied. You can only view your own recommendations."

    # --- Load student with skills (eager) ---
    student = Student.query.options(
        selectinload(Student.skills).joinedload(StudentSkill.skill)
    ).filter_by(id=student_id).first()

    if not student:
        return False, "Student not found."

    # --- Load job with skills (eager) ---
    job = JobDescription.query.options(
        selectinload(JobDescription.job_skills).joinedload(JobSkill.skill)
    ).filter_by(id=job_id, is_active=True).first()

    if not job:
        return False, "Job not found or inactive."

    # --- Get missing skills using Phase 8 logic ---
    missing_skills = _get_missing_skills_for_job(student, job)

    # --- Load all courses + their skill tags (no N+1) ---
    all_courses = _load_all_courses_with_skills()

    # --- Call pure recommendation engine ---
    result = recommend(missing_skills, all_courses, top_n=top_n)

    # Attach job meta for the template
    result['job_id'] = job_id
    result['job_title'] = job.title
    result['company_name'] = job.company_name or ''
    result['missing_count'] = len(missing_skills)
    result['student_has_skills'] = len(student.skills) > 0

    return True, result
