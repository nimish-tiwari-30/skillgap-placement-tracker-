"""
services/learning_path_service.py
───────────────────────────────────
Service layer for Phase 11: Learning Path + Progress Tracking.

Key Responsibilities:
  1. Generate & synchronize step-by-step learning paths for a student vs target job:
     - Reuses Phase 8 gap logic to detect missing skills.
     - Reuses ml/learning_path.py pure functions for difficulty-based sequencing.
     - Preserves existing progress on refresh (no duplicates, no progress loss).
     - Auto-completes steps if the student already possesses the skill.
  2. Complete steps atomically:
     - Updates LearningPathItem (is_completed, completed_at).
     - Inserts/updates student_skills (source='course', student's chosen proficiency).
     - Records audit row in skill_progress for historical proficiency tracking.
  3. Reversible steps (Undo):
     - Resets step to pending without destroying student's profile skills.
  4. Query learning path status and Chart.js historical skill progression.
  5. Enforces ownership: students can only access and update their own items.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from extensions import db
from models.course import Course, CourseSkill, LearningPathItem
from models.gap import SkillGapAnalysis
from models.job import JobDescription
from models.skill import Skill, StudentSkill
from models.student import SkillProgress, Student
from sqlalchemy.orm import joinedload, selectinload

from ml.learning_path import (
    PROJECT_PHASE_LABEL,
    RESUME_PHASE_LABEL,
    calculate_completion_pct,
    generate_learning_path_plan,
)
from services.gap_service import check_student_access
from services.recommendation_service import _get_missing_skills_for_job


# Fallback difficulty mapping for standard skills when not explicitly set
DEFAULT_SKILL_DIFFICULTY: Dict[str, str] = {
    'html': 'Beginner', 'css': 'Beginner', 'sql': 'Beginner', 'excel': 'Beginner',
    'python': 'Beginner', 'git': 'Beginner', 'bootstrap': 'Beginner', 'linux': 'Beginner',
    'vs code': 'Beginner', 'postman': 'Beginner', 'figma': 'Beginner', 'github': 'Beginner',
    'power bi': 'Beginner', 'tableau': 'Beginner',
    'javascript': 'Intermediate', 'react': 'Intermediate', 'node.js': 'Intermediate',
    'flask': 'Intermediate', 'django': 'Intermediate', 'postgresql': 'Intermediate',
    'mysql': 'Intermediate', 'mongodb': 'Intermediate', 'pandas': 'Intermediate',
    'numpy': 'Intermediate', 'docker': 'Intermediate', 'aws': 'Intermediate',
    'java': 'Intermediate', 'c++': 'Intermediate', 'c': 'Intermediate', 'go': 'Intermediate',
    'typescript': 'Intermediate', 'selenium': 'Intermediate', 'redis': 'Intermediate',
    'statistics': 'Intermediate', 'scikit-learn': 'Intermediate', 'kotlin': 'Intermediate',
    'r': 'Intermediate',
    'machine learning': 'Advanced', 'deep learning': 'Advanced', 'tensorflow': 'Advanced',
    'nlp': 'Advanced',
}


def _infer_skill_difficulty(skill_name: str, skill_id: int) -> str:
    """Determine skill difficulty from dictionary or associated courses fallback."""
    # 1. Dictionary lookup for canonical skills
    clean_name = (skill_name or '').strip().lower()
    if clean_name in DEFAULT_SKILL_DIFFICULTY:
        return DEFAULT_SKILL_DIFFICULTY[clean_name]

    # 2. Course tag fallback
    first_cs = CourseSkill.query.filter_by(skill_id=skill_id).first()
    if first_cs and first_cs.course and first_cs.course.difficulty_level:
        return first_cs.course.difficulty_level

    return 'Beginner'


def _map_proficiency(proficiency: Any) -> str:
    """Map numeric (1-5) or string input to 'Beginner', 'Intermediate', 'Advanced'."""
    if isinstance(proficiency, int):
        if proficiency <= 2:
            return 'Beginner'
        elif proficiency == 3:
            return 'Intermediate'
        else:
            return 'Advanced'
    elif isinstance(proficiency, str):
        val = proficiency.strip().title()
        if val in ('Beginner', 'Intermediate', 'Advanced'):
            return val
        if val.isdigit():
            return _map_proficiency(int(val))
    return 'Intermediate'  # Default level 3


def _get_or_create_analysis(student_id: int, job_id: int, current_user: Any = None) -> Optional[SkillGapAnalysis]:
    """Retrieve the latest gap analysis snapshot for this student and job, creating one if needed."""
    from services.gap_service import analyze, get_latest_analysis
    latest = get_latest_analysis(student_id, job_id, current_user=current_user)
    if latest:
        return latest
    ok, analysis, _ = analyze(student_id, job_id, current_user=current_user)
    if ok and isinstance(analysis, SkillGapAnalysis):
        return analysis
    return None


def generate_path(
    student_id: int,
    job_id: int,
    current_user: Any = None,
) -> Tuple[bool, Any]:
    """
    Generate or refresh a structured learning path for a student vs target job.

    Sync Guarantees:
      - Never duplicates path items.
      - Preserves already completed steps and their completion timestamps.
      - Adds newly missing skills in the correct sequence.
      - Auto-completes any skill step if the student already has that skill in their profile.
    """
    # 1. Ownership & access check
    if current_user and not check_student_access(student_id, current_user):
        return False, "Access denied. You can only manage your own learning path."

    student = Student.query.options(
        selectinload(Student.skills).joinedload(StudentSkill.skill)
    ).filter_by(id=student_id).first()
    if not student:
        return False, "Student not found."

    job = JobDescription.query.options(
        selectinload(JobDescription.job_skills)
    ).filter_by(id=job_id, is_active=True).first()
    if not job:
        return False, "Target job not found or inactive."

    # 2. Get or create gap analysis snapshot
    analysis = _get_or_create_analysis(student_id, job_id, current_user=current_user)
    analysis_id = analysis.id if analysis else None

    # 3. Compute missing skills using Phase 8 gap engine
    missing_skills_raw = _get_missing_skills_for_job(student, job)

    # Augment missing skills with difficulty
    missing_skills = []
    for s in missing_skills_raw:
        diff = _infer_skill_difficulty(s['name'], s['skill_id'])
        missing_skills.append({
            'skill_id':   s['skill_id'],
            'name':       s['name'],
            'importance': s['importance'],
            'difficulty': diff,
        })

    # 4. Generate ordered plan using ml/learning_path.py pure functions
    plan = generate_learning_path_plan(missing_skills)

    # 5. Fetch all existing items for this student and this target job
    # Query items linked either to this analysis or to any analysis for this job
    existing_items_query = LearningPathItem.query.filter_by(student_id=student_id)
    if analysis_id:
        existing_items = existing_items_query.filter(
            (LearningPathItem.analysis_id == analysis_id) |
            (LearningPathItem.analysis.has(job_description_id=job_id))
        ).all()
    else:
        existing_items = existing_items_query.all()

    # Index existing items by (item_type, skill_id)
    existing_by_key: Dict[Tuple[str, Optional[int]], LearningPathItem] = {}
    for it in existing_items:
        key = (it.item_type, it.skill_id)
        existing_by_key[key] = it

    # Set of skills the student already possesses (query directly from DB for fresh snapshot)
    student_skill_ids = {ss.skill_id for ss in StudentSkill.query.filter_by(student_id=student_id).all()}

    # Auto-complete any existing items in the student's path if they now possess that skill
    for ex_item in existing_items:
        if ex_item.item_type == 'skill' and ex_item.skill_id in student_skill_ids:
            if not ex_item.is_completed:
                ex_item.is_completed = True
                ex_item.completed_at = datetime.utcnow()

    # 6. Synchronize: update existing or create new items
    synced_items = []
    for step in plan:
        key = (step['item_type'], step['skill_id'])
        item = existing_by_key.get(key)

        if item:
            # Update sequencing labels and display order, keep existing completion state
            item.phase_number = step['phase_number']
            item.phase_label  = step['phase_label']
            item.display_order = step['display_order']
            item.description  = step['description']
            if analysis_id:
                item.analysis_id = analysis_id

            # Auto-complete if student now possesses this skill
            if step['item_type'] == 'skill' and step['skill_id'] in student_skill_ids:
                if not item.is_completed:
                    item.is_completed = True
                    item.completed_at = datetime.utcnow()
            synced_items.append(item)
        else:
            # Create new learning path item
            auto_complete = (step['item_type'] == 'skill' and step['skill_id'] in student_skill_ids)
            new_item = LearningPathItem(
                student_id=student_id,
                analysis_id=analysis_id,
                skill_id=step['skill_id'],
                phase_number=step['phase_number'],
                phase_label=step['phase_label'],
                item_type=step['item_type'],
                description=step['description'],
                is_completed=auto_complete,
                completed_at=datetime.utcnow() if auto_complete else None,
                display_order=step['display_order'],
            )
            db.session.add(new_item)
            synced_items.append(new_item)

    db.session.commit()
    return True, get_path(student_id, job_id, current_user=current_user)


def get_path(
    student_id: int,
    job_id: int,
    current_user: Any = None,
) -> Dict[str, Any]:
    """
    Retrieve the current learning path for a student and job.
    Includes completion %, item statuses, and top course recommendations.
    """
    if current_user and not check_student_access(student_id, current_user):
        return {
            'error': "Access denied.",
            'items': [],
            'total_items': 0,
            'completed_items': 0,
            'completion_pct': 0.0,
        }

    job = db.session.get(JobDescription, job_id)
    job_title = job.title if job else 'Target Job'
    company_name = job.company_name if job else ''

    # Fetch items ordered by display_order
    items = LearningPathItem.query.filter_by(
        student_id=student_id
    ).filter(
        (LearningPathItem.analysis.has(job_description_id=job_id)) |
        (LearningPathItem.analysis_id == None)
    ).options(
        joinedload(LearningPathItem.skill)
    ).order_by(
        LearningPathItem.display_order.asc(),
        LearningPathItem.phase_number.asc()
    ).all()

    # Preload top courses for skill items in one query to avoid N+1
    skill_ids = [it.skill_id for it in items if it.skill_id is not None]
    top_courses_by_skill: Dict[int, Dict[str, Any]] = {}
    if skill_ids:
        # Load course-skills for these skills, prioritizing high rating and shorter duration
        cs_rows = CourseSkill.query.filter(
            CourseSkill.skill_id.in_(skill_ids)
        ).options(
            joinedload(CourseSkill.course)
        ).all()

        for cs in cs_rows:
            sid = cs.skill_id
            c = cs.course
            if not c:
                continue
            rating = float(c.rating) if c.rating else 0.0
            duration = float(c.duration_hours) if c.duration_hours else 999.0

            # Keep best-rated course per skill
            if sid not in top_courses_by_skill:
                top_courses_by_skill[sid] = {
                    'id': c.id,
                    'title': c.title,
                    'provider': c.provider or '',
                    'difficulty_level': c.difficulty_level,
                    'rating': float(c.rating) if c.rating else None,
                    'duration_hours': float(c.duration_hours) if c.duration_hours else None,
                    'url': c.url or '#',
                }
            else:
                existing = top_courses_by_skill[sid]
                ex_rating = existing['rating'] or 0.0
                if rating > ex_rating:
                    top_courses_by_skill[sid] = {
                        'id': c.id,
                        'title': c.title,
                        'provider': c.provider or '',
                        'difficulty_level': c.difficulty_level,
                        'rating': float(c.rating) if c.rating else None,
                        'duration_hours': float(c.duration_hours) if c.duration_hours else None,
                        'url': c.url or '#',
                    }

    total_items = len(items)
    completed_items = sum(1 for it in items if it.is_completed)
    completion_pct = calculate_completion_pct(completed_items, total_items)

    formatted_items = []
    for it in items:
        rec_course = top_courses_by_skill.get(it.skill_id) if it.skill_id else None
        formatted_items.append({
            'id':              it.id,
            'phase_number':    it.phase_number,
            'phase_label':     it.phase_label,
            'item_type':       it.item_type,
            'skill_id':        it.skill_id,
            'skill_name':      it.skill.name if it.skill else None,
            'description':     it.description,
            'is_completed':    it.is_completed,
            'status':          'completed' if it.is_completed else 'pending',
            'completed_at':    it.completed_at.strftime('%b %d, %Y') if it.completed_at else None,
            'display_order':   it.display_order,
            'recommended_course': rec_course,
        })

    return {
        'job_id':          job_id,
        'job_title':       job_title,
        'company_name':    company_name,
        'items':           formatted_items,
        'steps':           formatted_items,
        'total_items':     total_items,
        'completed_items': completed_items,
        'completion_pct':  completion_pct,
        'all_completed':   (completed_items == total_items and total_items > 0),
    }


def mark_complete(
    student_id: int,
    item_id: int,
    proficiency: Any = 3,
    current_user: Any = None,
) -> Tuple[bool, Any]:
    """
    Mark a learning path step completed in ONE atomic transaction.

    Actions:
      1. Verify student ownership.
      2. If already completed, return harmlessly (idempotent, no duplicate progress rows).
      3. Mark item completed with timestamp.
      4. For skill steps:
         - Add skill to student_skills (source='course') or update existing proficiency.
         - Record skill_progress history row.
      5. Project and resume_update steps are completed without modifying student_skills.
    """
    item = db.session.get(LearningPathItem, item_id)
    if not item:
        return False, "Learning path step not found."

    # Ownership check
    if item.student_id != student_id:
        return False, "Access denied. You can only complete your own learning steps."
    if current_user and not check_student_access(student_id, current_user):
        return False, "Access denied. You can only complete your own learning steps."

    # Harmless idempotent check: if already completed, do nothing
    if item.is_completed:
        return True, item

    try:
        # Mark item complete
        item.is_completed = True
        item.completed_at = datetime.utcnow()

        # If this step teaches a skill, update student_skills & record skill_progress
        if item.item_type == 'skill' and item.skill_id:
            prof_level = _map_proficiency(proficiency)

            # Check existing student skill
            st_skill = StudentSkill.query.filter_by(
                student_id=student_id,
                skill_id=item.skill_id
            ).first()

            old_prof = None
            if st_skill:
                old_prof = st_skill.proficiency_level
                st_skill.proficiency_level = prof_level
            else:
                st_skill = StudentSkill(
                    student_id=student_id,
                    skill_id=item.skill_id,
                    proficiency_level=prof_level,
                    source='course'
                )
                db.session.add(st_skill)

            # Write skill_progress audit row
            progress_entry = SkillProgress(
                student_id=student_id,
                skill_id=item.skill_id,
                old_proficiency=old_prof,
                new_proficiency=prof_level,
                recorded_at=datetime.utcnow()
            )
            db.session.add(progress_entry)

        db.session.commit()
        return True, item

    except Exception as e:
        db.session.rollback()
        return False, f"Failed to complete step: {str(e)}"


def mark_pending(
    student_id: int,
    item_id: int,
    current_user: Any = None,
) -> Tuple[bool, Any]:
    """
    Undo a completed learning step.

    IMPORTANT AGENT RULE:
      For skill steps, we do NOT delete the skill from the student's profile!
      Skills once acquired remain part of their technical record.
      We solely reset the step completion flag on the learning path.
    """
    item = db.session.get(LearningPathItem, item_id)
    if not item:
        return False, "Learning path step not found."

    # Ownership check
    if item.student_id != student_id:
        return False, "Access denied. You can only modify your own learning steps."
    if current_user and not check_student_access(student_id, current_user):
        return False, "Access denied. You can only modify your own learning steps."

    try:
        item.is_completed = False
        item.completed_at = None
        db.session.commit()
        return True, item
    except Exception as e:
        db.session.rollback()
        return False, f"Failed to reset step: {str(e)}"


def get_skill_progress_history(student_id: int) -> Dict[str, Any]:
    """
    Fetch proficiency improvement history for a student over time.
    Returns:
      - chart_data: structured for Chart.js line graph
      - history_table: tabular rows (date, skill, old_proficiency, new_proficiency)
      - unique_skills: list of skills with recorded progress
    """
    records = SkillProgress.query.filter_by(
        student_id=student_id
    ).options(
        joinedload(SkillProgress.skill)
    ).order_by(
        SkillProgress.recorded_at.asc()
    ).all()

    PROF_TO_NUM = {'Beginner': 1, 'Intermediate': 2, 'Advanced': 3}

    # Build unique skills and chronological table
    unique_skills_dict = {}
    history_table = []

    for r in records:
        sname = r.skill.name if r.skill else f"Skill #{r.skill_id}"
        unique_skills_dict[r.skill_id] = sname

        history_table.append({
            'id':              r.id,
            'skill_id':        r.skill_id,
            'skill_name':      sname,
            'old_proficiency': r.old_proficiency or 'None',
            'new_proficiency': r.new_proficiency,
            'date':            r.recorded_at.strftime('%Y-%m-%d %H:%M'),
        })

    # Show newest first in table
    history_table.reverse()

    # Build Chart.js structure
    # Colors for distinct skills
    COLORS = [
        '#6366f1', '#06b6d4', '#10b981', '#f59e0b', '#ec4899',
        '#8b5cf6', '#3b82f6', '#14b8a6', '#f97316', '#84cc16'
    ]

    skill_datasets = []
    color_idx = 0
    for sid, sname in unique_skills_dict.items():
        skill_recs = [r for r in records if r.skill_id == sid]
        data_points = []
        for r in skill_recs:
            data_points.append({
                'x': r.recorded_at.strftime('%Y-%m-%d'),
                'y': PROF_TO_NUM.get(r.new_proficiency, 1),
                'prof_label': r.new_proficiency,
            })

        c = COLORS[color_idx % len(COLORS)]
        color_idx += 1

        skill_datasets.append({
            'label':           sname,
            'skill_id':        sid,
            'data':            data_points,
            'borderColor':     c,
            'backgroundColor': c,
            'tension':         0.25,
            'fill':            False,
        })

    return {
        'history_table': history_table,
        'datasets':      skill_datasets,
        'unique_skills': [{'id': sid, 'name': sname} for sid, sname in unique_skills_dict.items()],
        'has_data':      len(records) > 0,
    }
