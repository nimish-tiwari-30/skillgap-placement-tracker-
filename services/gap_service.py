"""
services/gap_service.py
─────────────────────────
Service layer for Skill-Gap Analysis (Phase 8).

Handles:
  - Performing skill gap calculation via ml.skill_gap
  - Saving SkillGapAnalysis and GapSkill records in a single atomic transaction
  - Enforcing student data ownership
  - Setting student's target job and recalculating profile completion
  - Fetching latest analysis and historical runs for progress tracking
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union

from extensions import db
from models.gap import GapSkill, SkillGapAnalysis
from models.job import JobDescription, JobSkill
from models.skill import Skill, StudentSkill
from models.student import Student
from ml.skill_gap import calculate_skill_gap


# Numerical mapping for proficiency levels for visual chart comparison against importance (1-5 scale)
PROFICIENCY_NUMERIC_MAP = {
    'Beginner': 2.0,
    'Intermediate': 3.5,
    'Advanced': 5.0,
}


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


def set_target_job(student_id: int, job_id: int, current_user: Any = None) -> Tuple[bool, Optional[str]]:
    """
    Assign a target job to a student profile and update profile completion %.
    """
    if current_user and not check_student_access(student_id, current_user):
        return False, "Access denied. You can only set your own target job."

    student = db.session.get(Student, student_id)
    if not student:
        return False, "Student not found."

    job = db.session.get(JobDescription, job_id)
    if not job or not job.is_active:
        return False, "Job opportunity not found or is currently inactive."

    try:
        student.target_job_id = job.id
        db.session.commit()

        # Recalculate profile completion (counts target role)
        from services.profile_service import calculate_profile_completion
        calculate_profile_completion(student)
        return True, None
    except Exception as e:
        db.session.rollback()
        return False, f"Failed to set target job: {str(e)}"


def analyze(
    student_id: int,
    job_id: int,
    current_user: Any = None
) -> Tuple[bool, Union[SkillGapAnalysis, str], Dict[str, Any]]:
    """
    Execute skill-gap analysis for student vs job.
    Saves analysis snapshot and gap_skills rows in ONE atomic transaction.

    Returns:
      (True, analysis_record, details_dict) on success
      (False, error_message, {}) on failure
    """
    if current_user and not check_student_access(student_id, current_user):
        return False, "Access denied. You can only run gap analysis on your own profile.", {}

    student = db.session.get(Student, student_id)
    if not student:
        return False, "Student profile not found.", {}

    job = db.session.get(JobDescription, job_id)
    if not job or not job.is_active:
        return False, "Job posting not found or is inactive.", {}

    # 1. Prepare student skills mapping: skill_id -> dict
    s_skills_input: Dict[int, Dict[str, Any]] = {}
    for ss in student.skills:
        s_skills_input[ss.skill_id] = {
            'proficiency': ss.proficiency_level,
            'name': ss.skill.name if ss.skill else f"Skill #{ss.skill_id}",
        }

    # 2. Prepare job required skills mapping: skill_id -> dict
    r_skills_input: Dict[int, Dict[str, Any]] = {}
    for js in job.job_skills:
        r_skills_input[js.skill_id] = {
            'importance': js.importance_weight,
            'name': js.skill.name if js.skill else f"Skill #{js.skill_id}",
        }

    # 3. Pure computation via ML core logic
    gap_result = calculate_skill_gap(s_skills_input, r_skills_input)

    # 4. Atomic Database Transaction: Save SkillGapAnalysis + GapSkills
    try:
        analysis = SkillGapAnalysis(
            student_id=student.id,
            job_role_id=job.job_role_id,
            job_description_id=job.id,
            unweighted_coverage_pct=gap_result['coverage_pct'],
            weighted_coverage_pct=gap_result['weighted_pct'],
            analyzed_at=datetime.utcnow(),
        )
        db.session.add(analysis)
        db.session.flush()  # Generate analysis.id for gap_skills foreign key

        # Save gap_skills rows
        for skill_id in gap_result['matched']:
            db.session.add(GapSkill(
                analysis_id=analysis.id,
                skill_id=skill_id,
                status='Matched'
            ))

        for skill_id in gap_result['missing']:
            db.session.add(GapSkill(
                analysis_id=analysis.id,
                skill_id=skill_id,
                status='Missing'
            ))

        for skill_id in gap_result['extra']:
            db.session.add(GapSkill(
                analysis_id=analysis.id,
                skill_id=skill_id,
                status='Extra'
            ))

        db.session.commit()

        # Format complete details for presentation
        details = format_analysis_details(analysis, raw_gap_result=gap_result)
        return True, analysis, details

    except Exception as e:
        db.session.rollback()
        return False, f"Database error during gap analysis: {str(e)}", {}


def get_latest_analysis(
    student_id: int,
    job_id: Optional[int] = None,
    current_user: Any = None
) -> Optional[SkillGapAnalysis]:
    """
    Get the most recent gap analysis snapshot for a student (optionally filtered by job_id).
    """
    if current_user and not check_student_access(student_id, current_user):
        return None

    query = SkillGapAnalysis.query.filter_by(student_id=student_id)
    if job_id:
        query = query.filter_by(job_description_id=job_id)
    return query.order_by(SkillGapAnalysis.analyzed_at.desc()).first()


def get_history(
    student_id: int,
    job_id: Optional[int] = None,
    limit: int = 15,
    current_user: Any = None
) -> List[SkillGapAnalysis]:
    """
    Get gap analysis history runs for progress tracking over time.
    """
    if current_user and not check_student_access(student_id, current_user):
        return []

    query = SkillGapAnalysis.query.filter_by(student_id=student_id)
    if job_id:
        query = query.filter_by(job_description_id=job_id)
    return query.order_by(SkillGapAnalysis.analyzed_at.desc()).limit(limit).all()


def format_analysis_details(
    analysis: SkillGapAnalysis,
    raw_gap_result: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Format a complete representation of an analysis for templates and API responses:
      - Matched skills list (with importance and proficiency)
      - Missing skills list (ordered by importance descending)
      - Extra skills list
      - Full comparison table rows
      - Chart data structures for Chart.js (doughnut & bar)
    """
    job = analysis.job_description
    student = analysis.student

    # Pre-fetch student's proficiency per skill
    student_prof_map = {}
    if student:
        for ss in student.skills:
            student_prof_map[ss.skill_id] = ss.proficiency_level

    # Pre-fetch job's required importance per skill
    job_imp_map = {}
    if job:
        for js in job.job_skills:
            job_imp_map[js.skill_id] = js.importance_weight

    # Categorize gap skills
    matched_skills = []
    missing_skills = []
    extra_skills = []

    for gs in analysis.gap_skills:
        skill_name = gs.skill.name if gs.skill else f"Skill #{gs.skill_id}"
        category = gs.skill.category if gs.skill else "General"
        importance = job_imp_map.get(gs.skill_id, 3)
        proficiency = student_prof_map.get(gs.skill_id)

        skill_info = {
            'skill_id': gs.skill_id,
            'name': skill_name,
            'category': category,
            'importance': importance,
            'proficiency': proficiency,
            'status': gs.status,
        }

        if gs.status == 'Matched':
            matched_skills.append(skill_info)
        elif gs.status == 'Missing':
            missing_skills.append(skill_info)
        elif gs.status == 'Extra':
            extra_skills.append(skill_info)

    # Sort missing skills by importance descending (tie-break by name)
    missing_skills.sort(key=lambda x: (-x['importance'], x['name'].lower()))

    # Sort matched skills by importance descending
    matched_skills.sort(key=lambda x: (-x['importance'], x['name'].lower()))

    # Sort extra skills alphabetically
    extra_skills.sort(key=lambda x: x['name'].lower())

    # Build comparison table: all required skills (matched + missing) followed by extra skills
    comparison_table = []
    for item in matched_skills:
        comparison_table.append({
            'name': item['name'],
            'category': item['category'],
            'student_has': True,
            'proficiency': item['proficiency'],
            'required': True,
            'importance': item['importance'],
            'status': 'Matched',
        })
    for item in missing_skills:
        comparison_table.append({
            'name': item['name'],
            'category': item['category'],
            'student_has': False,
            'proficiency': None,
            'required': True,
            'importance': item['importance'],
            'status': 'Missing',
        })
    for item in extra_skills:
        comparison_table.append({
            'name': item['name'],
            'category': item['category'],
            'student_has': True,
            'proficiency': item['proficiency'],
            'required': False,
            'importance': None,
            'status': 'Extra',
        })

    # Chart.js data
    chart_data = {
        'doughnut': {
            'labels': ['Matched Skills', 'Missing Skills'],
            'counts': [len(matched_skills), len(missing_skills)],
        },
        'bar': {
            'labels': [m['name'] for m in matched_skills],
            'required_importance': [m['importance'] for m in matched_skills],
            'student_proficiency': [
                PROFICIENCY_NUMERIC_MAP.get(m['proficiency'], 2.0) for m in matched_skills
            ],
            'proficiency_labels': [m['proficiency'] or 'N/A' for m in matched_skills],
        }
    }

    coverage_pct = float(analysis.unweighted_coverage_pct or 0.0)
    weighted_pct = float(analysis.weighted_coverage_pct or 0.0)

    return {
        'analysis_id': analysis.id,
        'job_id': analysis.job_description_id,
        'job_title': job.title if job else 'Unknown Job',
        'company_name': job.company_name if job else 'Unknown Company',
        'role_title': analysis.job_role.title if analysis.job_role else '',
        'analyzed_at': analysis.analyzed_at.strftime('%Y-%m-%d %H:%M') if analysis.analyzed_at else '',
        'coverage_pct': coverage_pct,
        'weighted_pct': weighted_pct,
        'matched_count': len(matched_skills),
        'missing_count': len(missing_skills),
        'extra_count': len(extra_skills),
        'matched': [m['name'] for m in matched_skills],
        'missing': [m['name'] for m in missing_skills],
        'extra': [e['name'] for e in extra_skills],
        'matched_skills': matched_skills,
        'missing_skills': missing_skills,
        'extra_skills': extra_skills,
        'comparison_table': comparison_table,
        'chart_data': chart_data,
        'zero_required': len(matched_skills) + len(missing_skills) == 0,
    }
