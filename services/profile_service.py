"""
services/profile_service.py
────────────────────────────
Business logic for student profile and skill management.

All DB writes are here — routes only receive/return HTTP.
Ownership checks ensure students can only touch their own data.
"""

from extensions import db
from models.student import Student, Certification, Project, Internship, SkillProgress
from models.skill import Skill, SkillAlias, StudentSkill
from sqlalchemy.exc import IntegrityError


# ════════════════════════════════════════════════════════════════════════════════
#  PROFILE COMPLETION CALCULATOR
# ════════════════════════════════════════════════════════════════════════════════

def calculate_profile_completion(student: Student) -> dict:
    """
    Calculate profile completion % and return what's still missing.

    Scoring weights (total = 100 points):
      - Basic details (full_name, branch, roll_number)  → 20 pts
      - Phone filled                                    → 10 pts
      - CGPA filled                                     → 10 pts
      - Graduation year filled                          → 10 pts
      - At least 5 skills added                         → 20 pts
      - At least 1 project                              → 10 pts
      - At least 1 certification                        → 10 pts
      - Resume uploaded (Phase 6)                       →  0 pts (placeholder)
      - LinkedIn URL                                    →  5 pts
      - GitHub URL                                      →  5 pts
      TOTAL                                             → 100 pts

    Returns dict: {percentage: int, missing: [str]}
    """
    score    = 0
    missing  = []

    # Basic details (20 pts)
    if student.full_name and student.branch and student.roll_number:
        score += 20
    else:
        missing.append("Complete basic details (name, branch, roll number)")

    # Phone (10 pts)
    if student.phone:
        score += 10
    else:
        missing.append("Add your phone number")

    # CGPA (10 pts)
    if student.cgpa:
        score += 10
    else:
        missing.append("Enter your CGPA")

    # Graduation year (10 pts)
    if student.graduation_year:
        score += 10
    else:
        missing.append("Set your graduation year")

    # Skills: at least 5 (20 pts)
    # Use direct query if student is persisted so newly added skills (e.g. from learning path) reflect immediately
    if student.id:
        skill_count = StudentSkill.query.filter_by(student_id=student.id).count()
    else:
        skill_count = len(student.skills)

    if skill_count >= 5:
        score += 20
    elif skill_count > 0:
        score += skill_count * 4   # Partial credit: 4 pts per skill up to 20
        missing.append(f"Add {5 - skill_count} more skill(s) (you have {skill_count}/5)")
    else:
        missing.append("Add at least 5 skills to your profile")

    # Projects (10 pts)
    if student.projects:
        score += 10
    else:
        missing.append("Add at least 1 project")

    # Certifications (10 pts)
    if student.certifications:
        score += 10
    else:
        missing.append("Add at least 1 certification")

    # Resume (10 pts — Phase 6)
    has_active_resume = False
    try:
        has_active_resume = any(r.is_active for r in getattr(student, 'resumes', []))
    except Exception:
        pass
    if has_active_resume:
        score += 10
    else:
        missing.append("Upload your resume for skill extraction")

    # LinkedIn (5 pts)
    if student.linkedin_url:
        score += 5
    else:
        missing.append("Add your LinkedIn URL")

    # GitHub (5 pts)
    if student.github_url:
        score += 5
    else:
        missing.append("Add your GitHub URL")

    # Target Job / Role (10 pts — Phase 8)
    if getattr(student, 'target_job_id', None):
        score += 10
    else:
        missing.append("Set your target job / career role")

    # Clamp to 100
    score = min(score, 100)

    # Also persist the % back to the student row
    student.profile_completion_pct = score
    db.session.commit()

    return {"percentage": score, "missing": missing}


# ════════════════════════════════════════════════════════════════════════════════
#  PROFILE UPDATE
# ════════════════════════════════════════════════════════════════════════════════

def update_profile(student: Student, form_data: dict) -> tuple[bool, str | None]:
    """
    Update academic profile fields on the students table.
    Returns (True, None) on success or (False, error_message).
    """
    try:
        student.full_name       = form_data.get('full_name', student.full_name).strip()
        student.phone           = (form_data.get('phone') or '').strip() or None
        student.linkedin_url    = (form_data.get('linkedin_url') or '').strip() or None
        student.github_url      = (form_data.get('github_url') or '').strip() or None

        # CGPA: convert to float, allow blank
        cgpa_raw = form_data.get('cgpa', '')
        if cgpa_raw and str(cgpa_raw).strip():
            try:
                student.cgpa = float(cgpa_raw)
            except ValueError:
                return False, "CGPA must be a valid number (e.g. 8.5)"
        else:
            student.cgpa = None

        # Graduation year
        grad_raw = form_data.get('graduation_year', '')
        student.graduation_year = int(grad_raw) if grad_raw else None

        # Branch
        branch = form_data.get('branch', '').strip()
        if branch:
            student.branch = branch

        # Phase 14: Aptitude and Communication scores (0–100)
        apt_raw = form_data.get('aptitude_score', '')
        if apt_raw is not None and str(apt_raw).strip() != '':
            try:
                apt = int(apt_raw)
                student.aptitude_score = max(0, min(100, apt))
            except ValueError:
                pass
        elif 'aptitude_score' in form_data:
            student.aptitude_score = None

        comm_raw = form_data.get('communication_score', '')
        if comm_raw is not None and str(comm_raw).strip() != '':
            try:
                comm = int(comm_raw)
                student.communication_score = max(0, min(100, comm))
            except ValueError:
                pass
        elif 'communication_score' in form_data:
            student.communication_score = None

        db.session.commit()
        return True, None
    except Exception as exc:
        db.session.rollback()
        return False, str(exc)


# ════════════════════════════════════════════════════════════════════════════════
#  SKILLS
# ════════════════════════════════════════════════════════════════════════════════

def add_student_skill(student: Student, skill_id: int, proficiency: str) -> tuple[bool, str | None]:
    """
    Link a skill to a student. If already exists, show friendly message.
    Also writes a SkillProgress row (old=None, new=proficiency).
    """
    # Check if student already has this skill
    existing = StudentSkill.query.filter_by(
        student_id=student.id, skill_id=skill_id
    ).first()

    if existing:
        return False, "You already have this skill. Use 'Update' to change proficiency."

    skill = db.session.get(Skill, skill_id)
    if not skill:
        return False, "Skill not found."

    try:
        ss = StudentSkill(
            student_id=student.id,
            skill_id=skill_id,
            proficiency_level=proficiency,
            source='manual',
        )
        db.session.add(ss)

        # Record skill progress (first time — old proficiency is None)
        progress = SkillProgress(
            student_id=student.id,
            skill_id=skill_id,
            old_proficiency=None,
            new_proficiency=proficiency,
        )
        db.session.add(progress)
        db.session.commit()
        return True, None
    except IntegrityError:
        db.session.rollback()
        return False, "You already have this skill in your profile."
    except Exception as exc:
        db.session.rollback()
        return False, str(exc)


def update_student_skill(student: Student, skill_id: int, new_proficiency: str) -> tuple[bool, str | None]:
    """
    Update proficiency for an existing student skill.
    Writes a SkillProgress row if proficiency actually changed.
    """
    ss = StudentSkill.query.filter_by(
        student_id=student.id, skill_id=skill_id
    ).first()

    if not ss:
        return False, "Skill not found in your profile."

    try:
        old_prof = ss.proficiency_level

        if old_prof != new_proficiency:
            # Write a progress record only if something actually changed
            progress = SkillProgress(
                student_id=student.id,
                skill_id=skill_id,
                old_proficiency=old_prof,
                new_proficiency=new_proficiency,
            )
            db.session.add(progress)
            ss.proficiency_level = new_proficiency

        db.session.commit()
        return True, None
    except Exception as exc:
        db.session.rollback()
        return False, str(exc)


def remove_student_skill(student: Student, skill_id: int) -> tuple[bool, str | None]:
    """Remove a skill from the student's profile."""
    ss = StudentSkill.query.filter_by(
        student_id=student.id, skill_id=skill_id
    ).first()

    if not ss:
        return False, "Skill not found in your profile."

    try:
        db.session.delete(ss)
        db.session.commit()
        return True, None
    except Exception as exc:
        db.session.rollback()
        return False, str(exc)


# ════════════════════════════════════════════════════════════════════════════════
#  CERTIFICATIONS
# ════════════════════════════════════════════════════════════════════════════════

def add_certification(student: Student, form_data: dict) -> tuple[bool, str | None]:
    """Add a certification entry for a student."""
    try:
        cert = Certification(
            student_id     = student.id,
            title          = form_data['title'].strip(),
            issuing_org    = (form_data.get('issuing_org') or '').strip() or None,
            issue_date     = form_data.get('issue_date') or None,
            expiry_date    = form_data.get('expiry_date') or None,
            credential_url = (form_data.get('credential_url') or '').strip() or None,
        )
        db.session.add(cert)
        db.session.commit()
        return True, None
    except Exception as exc:
        db.session.rollback()
        return False, str(exc)


def delete_certification(student: Student, cert_id: int) -> tuple[bool, str | None]:
    """Delete certification — ownership check included."""
    cert = Certification.query.filter_by(id=cert_id, student_id=student.id).first()
    if not cert:
        return False, "Certification not found or access denied."
    try:
        db.session.delete(cert)
        db.session.commit()
        return True, None
    except Exception as exc:
        db.session.rollback()
        return False, str(exc)


# ════════════════════════════════════════════════════════════════════════════════
#  PROJECTS
# ════════════════════════════════════════════════════════════════════════════════

def add_project(student: Student, form_data: dict) -> tuple[bool, str | None]:
    """Add a project to student's profile."""
    try:
        proj = Project(
            student_id  = student.id,
            title       = form_data['title'].strip(),
            description = (form_data.get('description') or '').strip() or None,
            tech_stack  = (form_data.get('tech_stack') or '').strip() or None,
            project_url = (form_data.get('project_url') or '').strip() or None,
            start_date  = form_data.get('start_date') or None,
            end_date    = form_data.get('end_date') or None,
        )
        db.session.add(proj)
        db.session.commit()
        return True, None
    except Exception as exc:
        db.session.rollback()
        return False, str(exc)


def delete_project(student: Student, project_id: int) -> tuple[bool, str | None]:
    """Delete project — ownership check included."""
    proj = Project.query.filter_by(id=project_id, student_id=student.id).first()
    if not proj:
        return False, "Project not found or access denied."
    try:
        db.session.delete(proj)
        db.session.commit()
        return True, None
    except Exception as exc:
        db.session.rollback()
        return False, str(exc)


# ════════════════════════════════════════════════════════════════════════════════
#  INTERNSHIPS
# ════════════════════════════════════════════════════════════════════════════════

def add_internship(student: Student, form_data: dict) -> tuple[bool, str | None]:
    """Add an internship to student's profile."""
    try:
        intern = Internship(
            student_id   = student.id,
            company_name = form_data['company_name'].strip(),
            role_title   = form_data['role_title'].strip(),
            description  = (form_data.get('description') or '').strip() or None,
            start_date   = form_data.get('start_date') or None,
            end_date     = form_data.get('end_date') or None,
        )
        db.session.add(intern)
        db.session.commit()
        return True, None
    except Exception as exc:
        db.session.rollback()
        return False, str(exc)


def delete_internship(student: Student, internship_id: int) -> tuple[bool, str | None]:
    """Delete internship — ownership check included."""
    intern = Internship.query.filter_by(id=internship_id, student_id=student.id).first()
    if not intern:
        return False, "Internship not found or access denied."
    try:
        db.session.delete(intern)
        db.session.commit()
        return True, None
    except Exception as exc:
        db.session.rollback()
        return False, str(exc)


# ════════════════════════════════════════════════════════════════════════════════
#  ADMIN — SKILL MANAGEMENT
# ════════════════════════════════════════════════════════════════════════════════

def admin_add_skill(name: str, category: str, description: str = '') -> tuple[bool, str | None]:
    """Admin: add a new master skill. Checks for duplicate name."""
    existing = Skill.query.filter(
        db.func.lower(Skill.name) == name.strip().lower()
    ).first()
    if existing:
        return False, f"Skill '{name}' already exists."
    try:
        skill = Skill(
            name        = name.strip(),
            category    = category.strip(),
            description = description.strip() or None,
        )
        db.session.add(skill)
        db.session.commit()
        return True, None
    except Exception as exc:
        db.session.rollback()
        return False, str(exc)


def admin_update_skill(skill_id: int, name: str, category: str, description: str = '') -> tuple[bool, str | None]:
    """Admin: update a master skill."""
    skill = db.session.get(Skill, skill_id)
    if not skill:
        return False, "Skill not found."

    # Check duplicate name (exclude self)
    dup = Skill.query.filter(
        db.func.lower(Skill.name) == name.strip().lower(),
        Skill.id != skill_id
    ).first()
    if dup:
        return False, f"Another skill named '{name}' already exists."

    try:
        skill.name        = name.strip()
        skill.category    = category.strip()
        skill.description = description.strip() or None
        db.session.commit()
        return True, None
    except Exception as exc:
        db.session.rollback()
        return False, str(exc)


def admin_delete_skill(skill_id: int) -> tuple[bool, str | None]:
    """
    Admin: delete a master skill.
    If skill is in use (student_skills, job_skills), show friendly message
    instead of crashing with a FK constraint error.
    """
    skill = db.session.get(Skill, skill_id)
    if not skill:
        return False, "Skill not found."

    # Check if any student is using this skill
    in_use = StudentSkill.query.filter_by(skill_id=skill_id).count()
    if in_use > 0:
        return False, (
            f"Cannot delete '{skill.name}' — it is used by {in_use} student(s). "
            "Remove it from all student profiles first."
        )

    try:
        db.session.delete(skill)
        db.session.commit()
        return True, None
    except Exception as exc:
        db.session.rollback()
        return False, str(exc)


def admin_add_alias(skill_id: int, alias_name: str) -> tuple[bool, str | None]:
    """Admin: add an alias for a skill."""
    existing = SkillAlias.query.filter(
        db.func.lower(SkillAlias.alias_name) == alias_name.strip().lower()
    ).first()
    if existing:
        return False, f"Alias '{alias_name}' already exists."
    try:
        alias = SkillAlias(skill_id=skill_id, alias_name=alias_name.strip())
        db.session.add(alias)
        db.session.commit()
        return True, None
    except Exception as exc:
        db.session.rollback()
        return False, str(exc)


def admin_delete_alias(alias_id: int) -> tuple[bool, str | None]:
    """Admin: delete a skill alias."""
    alias = db.session.get(SkillAlias, alias_id)
    if not alias:
        return False, "Alias not found."
    try:
        db.session.delete(alias)
        db.session.commit()
        return True, None
    except Exception as exc:
        db.session.rollback()
        return False, str(exc)


# ════════════════════════════════════════════════════════════════════════════════
#  HELPER — SKILL SEARCH FOR AUTOCOMPLETE
# ════════════════════════════════════════════════════════════════════════════════

def search_skills(query: str, limit: int = 15) -> list[dict]:
    """
    Search master skills by name (partial match).
    Used for the searchable dropdown on the profile page.
    Returns list of {id, name, category} dicts.
    """
    skills = Skill.query.filter(
        Skill.name.ilike(f'%{query}%')
    ).order_by(Skill.name).limit(limit).all()

    return [{'id': s.id, 'name': s.name, 'category': s.category or ''} for s in skills]
