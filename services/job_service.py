"""
services/job_service.py
───────────────────────
Service layer for Job Roles, Job Descriptions, and Job Skill Extraction.

Phase 7:
- CRUD for Job Roles (safe deletion check preventing orphan references)
- CRUD for Job Descriptions
- NLP Skill extraction wrapper (ml/skill_extractor.py)
- Atomic transaction saving of job skills with importance weights
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from extensions import db
from models.job import JobRole, JobDescription, JobSkill
from models.skill import Skill
from ml.skill_extractor import extract_skills_from_text

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════════
#  JOB ROLE SERVICES
# ════════════════════════════════════════════════════════════════════════════════

def get_all_roles(search: Optional[str] = None) -> List[JobRole]:
    """Retrieve all job roles, optionally filtered by title or department."""
    query = JobRole.query
    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(
            db.or_(
                JobRole.title.ilike(term),
                JobRole.department.ilike(term)
            )
        )
    return query.order_by(JobRole.title.asc()).all()


def get_role_by_id(role_id: int) -> Optional[JobRole]:
    """Retrieve a single job role by ID."""
    return db.session.get(JobRole, role_id)


def create_role(title: str, department: Optional[str] = None, description: Optional[str] = None) -> Tuple[bool, str, Optional[JobRole]]:
    """
    Create a new job role with unique name check.
    Returns (success, message, role_object).
    """
    clean_title = (title or '').strip()
    if not clean_title:
        return False, "Job role name cannot be empty.", None

    # Check for existing role with same name (case-insensitive)
    existing = JobRole.query.filter(db.func.lower(JobRole.title) == clean_title.lower()).first()
    if existing:
        return False, f"A job role named '{clean_title}' already exists.", None

    try:
        role = JobRole(
            title=clean_title,
            department=(department or '').strip() or None,
            description=(description or '').strip() or None
        )
        db.session.add(role)
        db.session.commit()
        return True, f"Job role '{clean_title}' created successfully.", role
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating job role: {e}")
        return False, f"Failed to create job role: {str(e)}", None


def update_role(role_id: int, title: str, department: Optional[str] = None, description: Optional[str] = None) -> Tuple[bool, str, Optional[JobRole]]:
    """
    Update an existing job role with unique name validation.
    Returns (success, message, role_object).
    """
    role = get_role_by_id(role_id)
    if not role:
        return False, "Job role not found.", None

    clean_title = (title or '').strip()
    if not clean_title:
        return False, "Job role name cannot be empty.", None

    # Check unique constraint against other roles
    conflict = JobRole.query.filter(
        db.func.lower(JobRole.title) == clean_title.lower(),
        JobRole.id != role_id
    ).first()
    if conflict:
        return False, f"Another job role named '{clean_title}' already exists.", None

    try:
        role.title = clean_title
        role.department = (department or '').strip() or None
        role.description = (description or '').strip() or None
        db.session.commit()
        return True, f"Job role '{clean_title}' updated successfully.", role
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating job role: {e}")
        return False, f"Failed to update job role: {str(e)}", None


def delete_role(role_id: int) -> Tuple[bool, str]:
    """
    Delete a job role safely.
    If the role is referenced by existing job descriptions, blocks deletion with a friendly message.
    """
    role = get_role_by_id(role_id)
    if not role:
        return False, "Job role not found."

    # Check if role is in use
    in_use_count = JobDescription.query.filter_by(job_role_id=role_id).count()
    if in_use_count > 0:
        return False, f"Cannot delete '{role.title}' because it is assigned to {in_use_count} job description(s). Please delete or reassign those jobs first."

    try:
        title = role.title
        db.session.delete(role)
        db.session.commit()
        return True, f"Job role '{title}' deleted successfully."
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting job role: {e}")
        return False, f"Failed to delete job role: {str(e)}"


# ════════════════════════════════════════════════════════════════════════════════
#  JOB DESCRIPTION SERVICES
# ════════════════════════════════════════════════════════════════════════════════

def get_all_jobs(search: Optional[str] = None, role_id: Optional[int] = None, active_only: bool = False) -> List[JobDescription]:
    """Retrieve job descriptions with optional search, role filter, and active status."""
    query = JobDescription.query
    if active_only:
        query = query.filter_by(is_active=True)

    if role_id:
        query = query.filter_by(job_role_id=role_id)

    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(
            db.or_(
                JobDescription.title.ilike(term),
                JobDescription.company_name.ilike(term),
                JobDescription.description_text.ilike(term),
                JobDescription.location.ilike(term)
            )
        )

    return query.order_by(JobDescription.created_at.desc()).all()


def get_job_by_id(job_id: int) -> Optional[JobDescription]:
    """Retrieve a single job description by ID."""
    return db.session.get(JobDescription, job_id)


def create_job(data: Dict[str, Any]) -> Tuple[bool, str, Optional[JobDescription]]:
    """Create a new job description."""
    role_id = data.get('job_role_id')
    role = get_role_by_id(role_id)
    if not role:
        return False, "Selected Job Role does not exist.", None

    title = (data.get('title') or '').strip()
    company = (data.get('company_name') or '').strip()
    desc_text = (data.get('description_text') or '').strip()

    if not title:
        return False, "Job title is required.", None
    if not company:
        return False, "Company name is required.", None
    if not desc_text:
        return False, "Job description text is required.", None

    try:
        job = JobDescription(
            job_role_id=role_id,
            title=title,
            company_name=company,
            description_text=desc_text,
            location=(data.get('location') or 'Remote').strip(),
            min_experience=(data.get('min_experience') or '0-1 years').strip(),
            is_active=bool(data.get('is_active', True))
        )
        db.session.add(job)
        db.session.commit()
        return True, "Job description created successfully.", job
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating job description: {e}")
        return False, f"Failed to create job: {str(e)}", None


def update_job(job_id: int, data: Dict[str, Any]) -> Tuple[bool, str, Optional[JobDescription]]:
    """Update an existing job description."""
    job = get_job_by_id(job_id)
    if not job:
        return False, "Job description not found.", None

    role_id = data.get('job_role_id')
    if role_id:
        role = get_role_by_id(role_id)
        if not role:
            return False, "Selected Job Role does not exist.", None
        job.job_role_id = role_id

    title = (data.get('title') or '').strip()
    company = (data.get('company_name') or '').strip()
    desc_text = (data.get('description_text') or '').strip()

    if not title:
        return False, "Job title cannot be empty.", None
    if not company:
        return False, "Company name cannot be empty.", None
    if not desc_text:
        return False, "Job description text cannot be empty.", None

    try:
        job.title = title
        job.company_name = company
        job.description_text = desc_text
        job.location = (data.get('location') or 'Remote').strip()
        job.min_experience = (data.get('min_experience') or '0-1 years').strip()
        if 'is_active' in data:
            job.is_active = bool(data.get('is_active'))
        db.session.commit()
        return True, "Job description updated successfully.", job
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating job description: {e}")
        return False, f"Failed to update job: {str(e)}", None


def delete_job(job_id: int) -> Tuple[bool, str]:
    """Delete a job description and its associated job_skills rows."""
    job = get_job_by_id(job_id)
    if not job:
        return False, "Job description not found."

    try:
        title = job.title
        db.session.delete(job)
        db.session.commit()
        return True, f"Job '{title}' deleted successfully."
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting job description: {e}")
        return False, f"Failed to delete job: {str(e)}"


# ════════════════════════════════════════════════════════════════════════════════
#  SKILL EXTRACTION & JOB_SKILLS PERSISTENCE
# ════════════════════════════════════════════════════════════════════════════════

def extract_job_skills(text: str) -> List[Dict[str, Any]]:
    """
    Extract skills from job description text using Phase 6 NLP extractor.
    Returns list of dicts with skill_id, canonical_name, count, category.
    """
    return extract_skills_from_text(text)


def save_job_skills(job_id: int, selections: List[Dict[str, Any]]) -> Tuple[bool, str, int]:
    """
    Save confirmed required skills for a job description in a single atomic transaction.
    - selections: list of dicts: [{'skill_id': int, 'importance_weight': int}]
    - De-duplicates skill IDs (avoids uq_job_skill violation).
    - Overwrites or refreshes job_skills for this job cleanly without duplicates.
    - Validates importance_weight is an integer between 1 and 5 (default 3).
    Returns (success, message, saved_count).
    """
    job = get_job_by_id(job_id)
    if not job:
        return False, "Job description not found.", 0

    # Deduplicate selections by skill_id
    deduped = {}
    for item in selections:
        try:
            sid = int(item.get('skill_id'))
            weight = int(item.get('importance_weight', 3))
            # Clamp weight between 1 and 5
            weight = max(1, min(5, weight))
            deduped[sid] = weight
        except (ValueError, TypeError):
            continue

    try:
        # Atomic replacement: delete existing skills for this job
        JobSkill.query.filter_by(job_description_id=job_id).delete()

        # Insert new selections
        saved_count = 0
        for sid, weight in deduped.items():
            # Verify skill exists in catalog
            skill = db.session.get(Skill, sid)
            if skill:
                js = JobSkill(
                    job_description_id=job_id,
                    skill_id=sid,
                    importance_weight=weight
                )
                db.session.add(js)
                saved_count += 1

        db.session.commit()
        return True, f"Successfully saved {saved_count} required skill(s).", saved_count
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error saving job skills: {e}")
        return False, f"Failed to save job skills: {str(e)}", 0


def get_job_with_skills(job_id: int) -> Optional[JobDescription]:
    """
    Retrieve job description with skills eager loaded and sorted by importance descending.
    """
    job = get_job_by_id(job_id)
    return job
