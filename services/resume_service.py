"""
services/resume_service.py
───────────────────────────
Resume management, file validation, text extraction, and skill persistence.

Responsibilities:
1. Validates file extension AND magic bytes/archive integrity via ml.resume_parser.
2. Stores files in static/uploads/resumes/ with randomized UUID filenames.
3. Extracts plain text via ml.resume_parser (pdfplumber & python-docx) and stores
   it in the resumes.extracted_text database column.
4. Identifies skills via ml.skill_extractor against the canonical skills catalog
   and alias directory.
5. Supports review-before-confirm workflow: detected skills can be reviewed
   by the student before being persisted with source='resume'.
6. Enforces student ownership on resume download, viewing, and deletion.
"""

import os
import time
import uuid
import logging
from typing import Tuple, Dict, Any, List, Optional
from werkzeug.utils import secure_filename
from flask import current_app

from extensions import db
from models.student import Student, SkillProgress
from models.skill import Skill, StudentSkill, Resume
from ml.resume_parser import validate_resume_bytes, extract_text
from ml.skill_extractor import extract_skills_from_text, refresh_skills_cache

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {'pdf', 'docx'}


def allowed_file(filename: str) -> bool:
    """Check if filename has a permitted extension."""
    if not filename or '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    return ext in ALLOWED_EXTENSIONS


def get_upload_dir() -> str:
    """Return the absolute path to static/uploads/resumes/, creating it if needed."""
    base_upload = current_app.config.get('UPLOAD_FOLDER', os.path.join(current_app.root_path, 'static', 'uploads'))
    resume_dir = os.path.join(base_upload, 'resumes')
    os.makedirs(resume_dir, exist_ok=True)
    return resume_dir


def process_resume_upload(student: Student, file_storage) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Handles secure resume upload, validation, extraction, and staging for review:
    1. Checks file extension and max payload size
    2. Validates magic bytes/zip integrity to reject renamed/fake files
    3. Extracts text via pdfplumber or python-docx
    4. Saves file with randomized UUID in static/uploads/resumes/
    5. Saves new Resume row in DB with extracted_text
    6. Identifies skills using ml.skill_extractor
    7. Computes which skills student already owns
    8. Updates student profile completion
    """
    if not file_storage or not file_storage.filename:
        return False, "Please select a resume file to upload.", {}

    student = db.session.get(Student, student.id)
    if not student:
        return False, "Student record not found.", {}

    original_filename = file_storage.filename
    if not allowed_file(original_filename):
        return False, "Invalid file format. Only PDF (.pdf) and Word (.docx) files are supported.", {}

    ext = original_filename.rsplit('.', 1)[1].lower()

    # Read binary content
    try:
        file_bytes = file_storage.read()
    except Exception as e:
        return False, f"Could not read upload payload: {str(e)}", {}

    if not file_bytes or len(file_bytes) == 0:
        return False, "The uploaded file is empty (0 bytes).", {}

    # File size validation
    max_mb = current_app.config.get('MAX_UPLOAD_MB', 16)
    if len(file_bytes) > max_mb * 1024 * 1024:
        return False, f"File size exceeds the {max_mb} MB limit.", {}

    # Deep magic bytes / format validation
    is_valid_format, format_err = validate_resume_bytes(file_bytes, ext)
    if not is_valid_format:
        return False, format_err, {}

    # Text extraction
    import io
    stream = io.BytesIO(file_bytes)
    try:
        raw_text = extract_text(stream, ext)
    except ValueError as e:
        # Friendly parser error (e.g. scanned/image-only PDF or empty doc)
        return False, str(e), {}
    except Exception as e:
        logger.error(f"Text extraction failed for {original_filename}: {e}")
        return False, f"Failed to extract text from document: {str(e)}", {}

    if not raw_text or not raw_text.strip():
        return False, "No readable text found in document. Please ensure the document is not an image-only scan.", {}

    # Generate secure randomized filename
    upload_dir = get_upload_dir()
    clean_base = secure_filename(original_filename.rsplit('.', 1)[0]) or 'resume'
    unique_id = uuid.uuid4().hex[:12]
    stored_filename = f"resume_{student.id}_{int(time.time())}_{unique_id}_{clean_base}.{ext}"
    dest_path = os.path.join(upload_dir, stored_filename)

    try:
        with open(dest_path, 'wb') as f:
            f.write(file_bytes)
    except IOError as e:
        logger.error(f"Failed to write file to {dest_path}: {e}")
        return False, "Failed to write file to server storage.", {}

    # Deactivate existing active resumes for this student
    Resume.query.filter_by(student_id=student.id, is_active=True).update({'is_active': False})

    file_size_kb = max(1, len(file_bytes) // 1024)
    rel_path = os.path.join('uploads', 'resumes', stored_filename).replace('\\', '/')

    resume_entry = Resume(
        student_id=student.id,
        original_name=original_filename,
        stored_filename=stored_filename,
        file_path=rel_path,
        file_type=ext,
        file_size_kb=file_size_kb,
        extracted_text=raw_text,
        is_active=True
    )
    db.session.add(resume_entry)

    # Detect skills using NLP skill extractor
    detected_skills = extract_skills_from_text(raw_text)

    # Check which skills student already has
    existing_skill_ids = set(
        sid for (sid,) in db.session.query(StudentSkill.skill_id).filter_by(student_id=student.id).all()
    )

    enriched_skills = []
    for item in detected_skills:
        skill_id = item.get('skill_id')
        already_owned = skill_id in existing_skill_ids
        enriched_skills.append({
            'skill_id': skill_id,
            'name': item.get('name') or item.get('canonical_name'),
            'category': item.get('category'),
            'matched_text': item.get('matched_text'),
            'count': item.get('count', 1),
            'already_owned': already_owned,
            'selected': not already_owned  # Default select new skills
        })

    # Update profile completion since active resume is now recorded
    student.profile_completion_pct = student.calculate_profile_completion()

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"DB commit error during resume save: {e}")
        if os.path.exists(dest_path):
            try:
                os.remove(dest_path)
            except OSError:
                pass
        return False, "Database error saving resume details.", {}

    return True, "Resume parsed successfully.", {
        'resume': resume_entry,
        'resume_id': resume_entry.id,
        'detected_skills': enriched_skills,
        'text_length': len(raw_text),
        'preview': raw_text[:350]
    }


def confirm_resume_skills(
    student: Student,
    selected_skill_ids: List[int],
    proficiencies: Optional[Dict[int, str]] = None
) -> Tuple[int, int]:
    """
    Persists selected skills into student_skills with source='resume'.
    Skips skills already owned by student.
    Writes skill_progress rows for each newly added skill.
    Updates student.profile_completion_pct.

    Returns: (added_count, skipped_count)
    """
    if proficiencies is None:
        proficiencies = {}

    student = db.session.get(Student, student.id)
    if not student:
        return 0, 0

    existing_skill_ids = set(
        sid for (sid,) in db.session.query(StudentSkill.skill_id).filter_by(student_id=student.id).all()
    )

    added_count = 0
    skipped_count = 0

    valid_proficiencies = {'Beginner', 'Intermediate', 'Advanced'}

    for sid in selected_skill_ids:
        if sid in existing_skill_ids:
            skipped_count += 1
            continue

        skill = db.session.get(Skill, sid)
        if not skill:
            continue

        # Default proficiency is Intermediate ('2') as specified in prompt
        prof = proficiencies.get(sid, 'Intermediate')
        if prof not in valid_proficiencies:
            prof = 'Intermediate'

        ss = StudentSkill(
            student_id=student.id,
            skill_id=sid,
            proficiency_level=prof,
            source='resume'
        )
        db.session.add(ss)
        existing_skill_ids.add(sid)

        # Log to skill_progress
        prog = SkillProgress(
            student_id=student.id,
            skill_id=sid,
            old_proficiency=None,
            new_proficiency=prof
        )
        db.session.add(prog)
        added_count += 1

    # Recalculate profile completion
    db.session.flush()
    student.profile_completion_pct = student.calculate_profile_completion()
    db.session.commit()

    return added_count, skipped_count


def delete_resume(student: Student, resume_id: int) -> Tuple[bool, str]:
    """
    Deletes a student's resume from storage and database.
    Enforces student ownership check.
    """
    resume = Resume.query.filter_by(id=resume_id, student_id=student.id).first()
    if not resume:
        return False, "Resume not found or access denied."

    upload_dir = get_upload_dir()
    file_path = os.path.join(upload_dir, resume.stored_filename)
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
        except OSError as e:
            logger.warning(f"Could not remove physical file {file_path}: {e}")

    db.session.delete(resume)

    # Recalculate completion
    db.session.flush()
    student.profile_completion_pct = student.calculate_profile_completion()
    db.session.commit()

    return True, "Resume deleted successfully."


def get_active_resume(student: Student) -> Optional[Resume]:
    """Return the active resume record for student."""
    return Resume.query.filter_by(student_id=student.id, is_active=True).first()


def get_student_resumes(student: Student) -> List[Resume]:
    """Return all resumes uploaded by this student (for resume history)."""
    return Resume.query.filter_by(student_id=student.id).order_by(Resume.uploaded_at.desc()).all()


def get_resume_by_id(resume_id: int) -> Optional[Resume]:
    """Retrieve resume by primary key."""
    return db.session.get(Resume, resume_id)
