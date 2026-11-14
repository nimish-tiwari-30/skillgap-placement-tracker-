"""
services/employment_service.py
───────────────────────────────
Service layer for Phase 12: Employment Outcome Tracking.

Handles:
  - Validating employment outcome data (status ENUM, positive salary bounds, non-future dates, skill IDs)
  - Recording, updating, and deleting employment outcomes with associated skills in ONE transaction
  - Ownership enforcement (students manage own outcome; admins manage any)
  - Admin multi-filter search, pagination, summary cards via Pandas, and sanitized CSV export
"""

import csv
import io
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple, Union

import pandas as pd
from sqlalchemy import or_, func
from sqlalchemy.orm import joinedload

from extensions import db
from models.outcome import EmploymentOutcome, EmploymentOutcomeSkill
from models.skill import Skill
from models.student import Student
from services.analytics_service import compute_employment_summary


# Valid Enum definitions from schema
VALID_STATUSES = ('Placed', 'Not Placed', 'In Progress')
VALID_PLACEMENT_TYPES = ('Campus', 'Off-Campus', 'Internship-Converted', 'Unknown')

# Salary Bounds in Lakhs Per Annum (LPA) in INR
# Realistic range: 0.1 LPA (Rs 10,000/yr) up to 150.0 LPA (Rs 1.5 Crore/yr)
MIN_SALARY_LPA = 0.1
MAX_SALARY_LPA = 150.0


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


def validate_outcome_data(data: Dict[str, Any]) -> Tuple[bool, Optional[str], Dict[str, Any]]:
    """
    Validate employment outcome form/API data.

    Rules:
      1. status must be one of: 'Placed', 'Not Placed', 'In Progress'.
      2. If status is 'Placed':
         - company_name is required.
         - role_title is required.
         - placement_date is required and cannot be in the future (> today).
         - salary_package_lpa is required, positive, and <= MAX_SALARY_LPA (150 LPA).
      3. If status is NOT 'Placed':
         - company_name, role_title, placement_date are optional.
         - salary_package_lpa MUST NOT be set.
         - placement_date (if given) cannot be in the future.
      4. skills_used (if given) must be a list of valid skill IDs existing in DB.

    Returns:
      (True, None, cleaned_data) or (False, error_message, {})
    """
    cleaned: Dict[str, Any] = {}

    # 1. Validate Status
    status = (data.get('status') or '').strip()
    # Normalize casing if needed
    status_map = {s.lower(): s for s in VALID_STATUSES}
    if status.lower() not in status_map:
        return False, f"Invalid status '{status}'. Must be one of: {', '.join(VALID_STATUSES)}", {}
    cleaned_status = status_map[status.lower()]
    cleaned['status'] = cleaned_status

    # 2. Extract common text fields
    company = (data.get('company_name') or '').strip()
    role = (data.get('role_title') or '').strip()
    notes = (data.get('notes') or '').strip()
    p_type = (data.get('placement_type') or 'Unknown').strip()

    # Placement type validation
    p_type_map = {t.lower(): t for t in VALID_PLACEMENT_TYPES}
    cleaned['placement_type'] = p_type_map.get(p_type.lower(), 'Unknown')
    cleaned['notes'] = notes if notes else None

    # 3. Parse Placement Date
    raw_date = data.get('placement_date')
    parsed_date: Optional[date] = None
    if raw_date:
        if isinstance(raw_date, (datetime, date)):
            parsed_date = raw_date.date() if isinstance(raw_date, datetime) else raw_date
        elif isinstance(raw_date, str) and raw_date.strip():
            try:
                parsed_date = datetime.strptime(raw_date.strip(), '%Y-%m-%d').date()
            except ValueError:
                return False, "Invalid placement date format. Use YYYY-MM-DD.", {}

    today = date.today()
    if parsed_date and parsed_date > today:
        return False, f"Placement date ({parsed_date}) cannot be in the future.", {}

    # 4. Parse Salary
    raw_salary = data.get('salary_package_lpa')
    parsed_salary: Optional[Decimal] = None
    if raw_salary is not None and str(raw_salary).strip() != '':
        try:
            val_float = float(raw_salary)
            # If input is in whole INR (e.g. 600000), convert to LPA (6.0)
            if val_float > 1000.0:
                val_float = val_float / 100000.0
            parsed_salary = Decimal(str(round(val_float, 2)))
        except (ValueError, TypeError):
            return False, "Salary package must be a valid numeric value.", {}

    # 5. Conditional rules based on status
    if cleaned_status == 'Placed':
        if not company:
            return False, "Company name is required when status is Placed.", {}
        if not role:
            return False, "Job role is required when status is Placed.", {}
        if not parsed_date:
            return False, "Placement date is required when status is Placed.", {}
        if parsed_salary is None or parsed_salary <= Decimal('0.0'):
            return False, "Salary package is required and must be greater than 0 LPA when status is Placed.", {}
        if parsed_salary > Decimal(str(MAX_SALARY_LPA)):
            return False, f"Salary package exceeds realistic maximum of {MAX_SALARY_LPA} LPA.", {}

        cleaned['company_name'] = company
        cleaned['role_title'] = role
        cleaned['placement_date'] = parsed_date
        cleaned['salary_package_lpa'] = parsed_salary
    else:
        # Non-placed: salary MUST NOT be set
        if parsed_salary is not None and parsed_salary > Decimal('0.0'):
            return False, f"Salary cannot be set when status is '{cleaned_status}'.", {}

        cleaned['company_name'] = company if company else None
        cleaned['role_title'] = role if role else None
        cleaned['placement_date'] = parsed_date
        cleaned['salary_package_lpa'] = None

    # 6. Validate Skills Used
    raw_skills = data.get('skills_used') or data.get('skill_ids') or []
    skill_ids: List[int] = []
    if isinstance(raw_skills, list):
        for s in raw_skills:
            try:
                if isinstance(s, dict) and 'id' in s:
                    skill_ids.append(int(s['id']))
                else:
                    skill_ids.append(int(s))
            except (ValueError, TypeError):
                continue
    elif isinstance(raw_skills, (str, int)):
        try:
            skill_ids = [int(raw_skills)]
        except ValueError:
            pass

    # Verify skill IDs exist in database
    if skill_ids:
        existing_skills = Skill.query.filter(Skill.id.in_(skill_ids)).all()
        found_ids = {s.id for s in existing_skills}
        for sid in skill_ids:
            if sid not in found_ids:
                return False, f"Skill ID {sid} does not exist in master skills catalog.", {}
        cleaned['skill_ids'] = list(set(skill_ids))
    else:
        cleaned['skill_ids'] = []

    return True, None, cleaned


def get_outcome(student_id: int, current_user: Any = None) -> Optional[Dict[str, Any]]:
    """
    Retrieve current employment outcome for a student with skills used.
    Enforces ownership permissions.
    """
    if current_user and not check_student_access(student_id, current_user):
        return None

    outcome = EmploymentOutcome.query.options(
        joinedload(EmploymentOutcome.skills_used).joinedload(EmploymentOutcomeSkill.skill),
        joinedload(EmploymentOutcome.student)
    ).filter_by(student_id=student_id).first()

    if not outcome:
        return None

    skills_list = []
    skill_ids = []
    for eos in outcome.skills_used:
        if eos.skill:
            skills_list.append({
                'id': eos.skill.id,
                'name': eos.skill.name,
                'category': eos.skill.category,
            })
            skill_ids.append(eos.skill.id)

    return {
        'id': outcome.id,
        'student_id': outcome.student_id,
        'status': outcome.status,
        'company_name': outcome.company_name,
        'role_title': outcome.role_title,
        'salary_package_lpa': float(outcome.salary_package_lpa) if outcome.salary_package_lpa is not None else None,
        'placement_date': outcome.placement_date.strftime('%Y-%m-%d') if outcome.placement_date else None,
        'placement_date_formatted': outcome.placement_date.strftime('%b %d, %Y') if outcome.placement_date else None,
        'placement_type': outcome.placement_type,
        'notes': outcome.notes,
        'skills_used': skills_list,
        'skill_ids': skill_ids,
        'is_placed': outcome.is_placed(),
        'updated_at': outcome.updated_at.strftime('%Y-%m-%d %H:%M') if outcome.updated_at else None,
    }


def save_outcome(
    student_id: int,
    data: Dict[str, Any],
    current_user: Any = None
) -> Tuple[bool, Union[EmploymentOutcome, str]]:
    """
    Create or update student's employment outcome and associated skills in ONE transaction.
    """
    # 1. Ownership enforcement
    if current_user and not check_student_access(student_id, current_user):
        return False, "Access denied. You can only update your own employment outcome."

    student = db.session.get(Student, student_id)
    if not student:
        return False, "Student profile not found."

    # 2. Validation
    valid, err_msg, cleaned = validate_outcome_data(data)
    if not valid:
        return False, err_msg or "Validation error."

    # 3. Save outcome and junction rows in single transaction
    try:
        outcome = EmploymentOutcome.query.filter_by(student_id=student_id).first()
        if not outcome:
            outcome = EmploymentOutcome(student_id=student_id)
            db.session.add(outcome)

        outcome.status = cleaned['status']
        outcome.company_name = cleaned['company_name']
        outcome.role_title = cleaned['role_title']
        outcome.salary_package_lpa = cleaned['salary_package_lpa']
        outcome.placement_date = cleaned['placement_date']
        outcome.placement_type = cleaned['placement_type']
        outcome.notes = cleaned['notes']
        outcome.updated_at = datetime.utcnow()

        db.session.flush()

        # Synchronize skills used junction table
        desired_skill_ids = set(cleaned.get('skill_ids', []))
        existing_skills = EmploymentOutcomeSkill.query.filter_by(outcome_id=outcome.id).all()
        existing_skill_ids = {eos.skill_id for eos in existing_skills}

        # Delete removed skills
        for eos in existing_skills:
            if eos.skill_id not in desired_skill_ids:
                db.session.delete(eos)

        # Add newly added skills
        for sid in desired_skill_ids:
            if sid not in existing_skill_ids:
                db.session.add(EmploymentOutcomeSkill(outcome_id=outcome.id, skill_id=sid))

        db.session.commit()
        return True, outcome

    except Exception as e:
        db.session.rollback()
        return False, f"Failed to save employment outcome: {str(e)}"


def delete_outcome(student_id: int, current_user: Any = None) -> Tuple[bool, Optional[str]]:
    """
    Delete employment outcome and its skill junction rows.
    """
    if current_user and not check_student_access(student_id, current_user):
        return False, "Access denied. You can only delete your own employment outcome."

    outcome = EmploymentOutcome.query.filter_by(student_id=student_id).first()
    if not outcome:
        return False, "Employment outcome record not found."

    try:
        db.session.delete(outcome)
        db.session.commit()
        return True, None
    except Exception as e:
        db.session.rollback()
        return False, f"Failed to delete outcome: {str(e)}"


def get_all_outcomes_for_admin(
    filters: Optional[Dict[str, Any]] = None,
    page: int = 1,
    per_page: int = 20
) -> Dict[str, Any]:
    """
    Searchable, filterable query of all students' employment outcomes.
    Computes summary cards via Pandas across the filtered dataset.
    """
    filters = filters or {}
    status_filter = (filters.get('status') or '').strip()
    branch_filter = (filters.get('branch') or '').strip()
    role_filter = (filters.get('role') or '').strip()
    search_query = (filters.get('search') or '').strip()

    # Base query: join Student and EmploymentOutcome
    query = db.session.query(
        Student, EmploymentOutcome
    ).outerjoin(
        EmploymentOutcome, Student.id == EmploymentOutcome.student_id
    ).options(
        joinedload(Student.user)
    )

    # 1. Apply Branch Filter
    if branch_filter and branch_filter.lower() != 'all':
        query = query.filter(Student.branch == branch_filter)

    # 2. Apply Status Filter
    if status_filter and status_filter.lower() != 'all':
        if status_filter == 'Unrecorded':
            query = query.filter(EmploymentOutcome.id == None)
        else:
            query = query.filter(EmploymentOutcome.status == status_filter)

    # 3. Apply Role Filter
    if role_filter and role_filter.lower() != 'all':
        query = query.filter(EmploymentOutcome.role_title.ilike(f"%{role_filter}%"))

    # 4. Apply Search Query (Name, Roll, Company)
    if search_query:
        term = f"%{search_query}%"
        query = query.filter(
            or_(
                Student.full_name.ilike(term),
                Student.roll_number.ilike(term),
                EmploymentOutcome.company_name.ilike(term),
                EmploymentOutcome.role_title.ilike(term)
            )
        )

    # Query all matching records for Pandas summary card computation
    all_matched = query.order_by(Student.roll_number.asc()).all()

    records_for_df = []
    for st, out in all_matched:
        records_for_df.append({
            'student_id': st.id,
            'full_name': st.full_name,
            'roll_number': st.roll_number,
            'branch': st.branch,
            'status': out.status if out else 'Unrecorded',
            'company_name': out.company_name if out else None,
            'role_title': out.role_title if out else None,
            'salary_package_lpa': float(out.salary_package_lpa) if out and out.salary_package_lpa is not None else None,
            'placement_date': out.placement_date if out else None,
            'placement_type': out.placement_type if out else None,
        })

    # Summary metrics computed via Pandas
    summary = compute_employment_summary(records_for_df)

    # Pagination
    total_records = len(records_for_df)
    total_pages = max(1, (total_records + per_page - 1) // per_page)
    current_page = max(1, min(page, total_pages))
    start_idx = (current_page - 1) * per_page
    end_idx = start_idx + per_page
    paginated_records = records_for_df[start_idx:end_idx]

    # Distinct values for dropdown filters
    branches = [b[0] for b in db.session.query(Student.branch).distinct().order_by(Student.branch).all() if b[0]]
    roles = [r[0] for r in db.session.query(EmploymentOutcome.role_title).distinct().order_by(EmploymentOutcome.role_title).all() if r[0]]

    return {
        'records': paginated_records,
        'summary': summary,
        'pagination': {
            'page': current_page,
            'per_page': per_page,
            'total': total_records,
            'pages': total_pages,
            'has_prev': current_page > 1,
            'has_next': current_page < total_pages,
            'prev_num': current_page - 1,
            'next_num': current_page + 1,
        },
        'filters': {
            'status': status_filter,
            'branch': branch_filter,
            'role': role_filter,
            'search': search_query,
        },
        'available_branches': branches,
        'available_roles': roles,
    }


def _sanitize_csv_cell(val: Any) -> str:
    """
    Prevent CSV formula injection by prepending a single quote
    if cell content begins with '=', '+', '-', '@'.
    """
    if val is None:
        return ""
    text_val = str(val).strip()
    if text_val and text_val[0] in ('=', '+', '-', '@'):
        return f"'{text_val}"
    return text_val


def export_outcomes_to_csv(filters: Optional[Dict[str, Any]] = None) -> str:
    """
    Export filtered employment outcome records as CSV string.
    Implements CSV formula injection sanitization.
    """
    # Fetch all matching records without pagination
    admin_data = get_all_outcomes_for_admin(filters=filters, page=1, per_page=100000)
    records = admin_data['records']

    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)

    # Header row
    writer.writerow([
        "Student Name",
        "Roll Number",
        "Branch",
        "Status",
        "Company",
        "Job Role",
        "Salary (LPA)",
        "Placement Date",
        "Placement Type",
    ])

    for r in records:
        sal = f"{r['salary_package_lpa']:.2f}" if r['salary_package_lpa'] is not None else ""
        p_date = r['placement_date'].strftime('%Y-%m-%d') if r['placement_date'] else ""
        writer.writerow([
            _sanitize_csv_cell(r['full_name']),
            _sanitize_csv_cell(r['roll_number']),
            _sanitize_csv_cell(r['branch']),
            _sanitize_csv_cell(r['status']),
            _sanitize_csv_cell(r['company_name']),
            _sanitize_csv_cell(r['role_title']),
            _sanitize_csv_cell(sal),
            _sanitize_csv_cell(p_date),
            _sanitize_csv_cell(r['placement_type']),
        ])

    return output.getvalue()
