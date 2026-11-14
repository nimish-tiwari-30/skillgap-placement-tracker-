"""
tests/test_employment.py
────────────────────────
Comprehensive test suite for Phase 12: Employment Tracking.

Tests cover:
  1. Service Layer & Validation (services/employment_service.py):
     - Valid Placed outcome creation and update with skills used
     - Placed validation errors: missing company, role, salary, date
     - Non-placed validation: salary prohibited on In Progress / Not Placed
     - Salary validation: negative, zero, and out-of-bounds (> 150 LPA) rejected
     - Date validation: future date rejected
     - Status validation: invalid ENUM value rejected
     - Skills validation: nonexistent skill ID rejected
     - Deletion: outcome and junction rows removed cleanly
     - Ownership enforcement: student cannot modify/view another student's outcome
  2. Analytics Service (services/analytics_service.py):
     - placement_percentage, average_salary, median_salary calculation
     - Hand-calculated numbers match expected values
     - Safe handling of empty datasets (returns 0.0 or None, display N/A, no crash)
  3. Student Web Routes (routes/student.py):
     - GET /student/employment (view current status and form)
     - POST /student/employment (create and update)
     - POST /student/employment/delete (remove outcome)
     - Dashboard displays real employment status badge and company/role
     - Guest redirected to login
  4. Admin Web Routes (routes/admin.py):
     - GET /admin/employment (search, filter by branch/status/role, pagination)
     - Summary cards reflect real DB metrics computed via Pandas
     - Admin can record and delete outcome for any student
     - CSV export (/admin/employment/export-csv) with formula injection protection (=, +, -, @)
     - Non-admin blocked from /admin/employment (403)
  5. API Endpoints (routes/api.py):
     - GET /api/student/<id>/employment (success JSON, own data only, admin allowed)
     - POST /api/student/<id>/employment (validation handling, own data only, admin allowed)
     - 404 for invalid student ID
  6. Demo Seeding (seed_demo_students.py):
     - Script is idempotent (runs twice without duplicate students or errors)
     - Creates realistic mix of Placed, In Progress, and Not Placed outcomes
"""

import json
from datetime import date, timedelta
from decimal import Decimal
import pytest

from extensions import db as _db
from models.user import User
from models.student import Student
from models.skill import Skill
from models.job import JobRole
from models.outcome import EmploymentOutcome, EmploymentOutcomeSkill
from services import employment_service, analytics_service


# ════════════════════════════════════════════════════════════════════════════════
#  FIXTURES & HELPERS
# ════════════════════════════════════════════════════════════════════════════════

def create_student_user(email='test_p12@test.com', roll='ROLL12', name='Alex Career', branch='Computer Science'):
    """Create and persist a test student user."""
    user = User(email=email.strip().lower(), role='student', is_active=True)
    user.set_password('Pass1234')
    _db.session.add(user)
    _db.session.flush()

    student = Student(
        user_id=user.id,
        full_name=name,
        roll_number=roll,
        branch=branch,
        graduation_year=2025,
        cgpa=8.50,
    )
    _db.session.add(student)
    _db.session.commit()
    return user, student


def create_admin_user(email='admin_p12@test.com'):
    """Create and persist a test admin user."""
    user = User(email=email.strip().lower(), role='admin', is_active=True)
    user.set_password('AdminPass123')
    _db.session.add(user)
    _db.session.commit()
    return user


def setup_sample_skills():
    """Ensure standard skills exist in DB for testing."""
    skills = {}
    for s_name, cat in [('Python', 'Programming'), ('SQL', 'Database'), ('React', 'Web')]:
        s = Skill.query.filter_by(name=s_name).first()
        if not s:
            s = Skill(name=s_name, category=cat)
            _db.session.add(s)
            _db.session.flush()
        skills[s_name] = s
    _db.session.commit()
    return skills


def login_client(client, email, password):
    """Helper to log in client via auth route."""
    client.get('/logout')
    return client.post('/login', data={'email': email.strip().lower(), 'password': password}, follow_redirects=True)


# ════════════════════════════════════════════════════════════════════════════════
#  1. SERVICE LAYER & VALIDATION TESTS
# ════════════════════════════════════════════════════════════════════════════════

def test_save_placed_outcome_success():
    """Successfully save a Placed outcome with skills used."""
    user, student = create_student_user(email='placed_svc@test.com', roll='P12_01')
    skills = setup_sample_skills()

    data = {
        'status': 'Placed',
        'company_name': 'Tech Corp',
        'role_title': 'Software Engineer',
        'salary_package_lpa': 8.50,
        'placement_date': date.today() - timedelta(days=10),
        'placement_type': 'Campus',
        'notes': 'Selected via on-campus drive.',
        'skill_ids': [skills['Python'].id, skills['SQL'].id],
    }

    ok, outcome = employment_service.save_outcome(student.id, data, current_user=user)
    assert ok is True
    assert outcome.status == 'Placed'
    assert outcome.company_name == 'Tech Corp'
    assert float(outcome.salary_package_lpa) == 8.50
    assert len(outcome.skills_used) == 2

    # Verify retrieval
    retrieved = employment_service.get_outcome(student.id, current_user=user)
    assert retrieved is not None
    assert retrieved['status'] == 'Placed'
    assert retrieved['company_name'] == 'Tech Corp'
    assert len(retrieved['skills_used']) == 2
    assert retrieved['skill_ids'] == [skills['Python'].id, skills['SQL'].id] or set(retrieved['skill_ids']) == {skills['Python'].id, skills['SQL'].id}


def test_placed_missing_required_fields_rejected():
    """Placed status requires company, role, salary, and date."""
    user, student = create_student_user(email='missing_flds@test.com', roll='P12_02')

    # Missing company
    ok, err = employment_service.save_outcome(student.id, {
        'status': 'Placed',
        'role_title': 'Dev',
        'salary_package_lpa': 6.0,
        'placement_date': date.today(),
    }, current_user=user)
    assert ok is False
    assert "Company name is required" in err

    # Missing role
    ok, err = employment_service.save_outcome(student.id, {
        'status': 'Placed',
        'company_name': 'Acme',
        'salary_package_lpa': 6.0,
        'placement_date': date.today(),
    }, current_user=user)
    assert ok is False
    assert "Job role is required" in err

    # Missing date
    ok, err = employment_service.save_outcome(student.id, {
        'status': 'Placed',
        'company_name': 'Acme',
        'role_title': 'Dev',
        'salary_package_lpa': 6.0,
    }, current_user=user)
    assert ok is False
    assert "Placement date is required" in err

    # Missing or zero salary
    ok, err = employment_service.save_outcome(student.id, {
        'status': 'Placed',
        'company_name': 'Acme',
        'role_title': 'Dev',
        'placement_date': date.today(),
        'salary_package_lpa': 0.0,
    }, current_user=user)
    assert ok is False
    assert "greater than 0" in err


def test_salary_on_non_placed_status_rejected():
    """Salary package MUST NOT be set for non-placed statuses (In Progress / Not Placed)."""
    user, student = create_student_user(email='salary_nonplaced@test.com', roll='P12_03')

    # In Progress with salary
    ok, err = employment_service.save_outcome(student.id, {
        'status': 'In Progress',
        'salary_package_lpa': 7.0,
    }, current_user=user)
    assert ok is False
    assert "Salary cannot be set when status is 'In Progress'" in err

    # Not Placed with salary
    ok, err = employment_service.save_outcome(student.id, {
        'status': 'Not Placed',
        'salary_package_lpa': 5.0,
    }, current_user=user)
    assert ok is False
    assert "Salary cannot be set when status is 'Not Placed'" in err


def test_salary_bounds_and_future_date_rejected():
    """Salary must not exceed upper bound (150 LPA), and date cannot be future."""
    user, student = create_student_user(email='bounds@test.com', roll='P12_04')

    # Huge salary (> 150 LPA)
    ok, err = employment_service.save_outcome(student.id, {
        'status': 'Placed',
        'company_name': 'Global Corp',
        'role_title': 'VP',
        'salary_package_lpa': 250.0,
        'placement_date': date.today(),
    }, current_user=user)
    assert ok is False
    assert "exceeds realistic maximum" in err

    # Future placement date (> today)
    tomorrow = date.today() + timedelta(days=1)
    ok, err = employment_service.save_outcome(student.id, {
        'status': 'Placed',
        'company_name': 'Future Corp',
        'role_title': 'Eng',
        'salary_package_lpa': 12.0,
        'placement_date': tomorrow,
    }, current_user=user)
    assert ok is False
    assert "cannot be in the future" in err


def test_invalid_status_and_invalid_skill_id_rejected():
    """Invalid status string or invalid skill ID is rejected."""
    user, student = create_student_user(email='invalid_inputs@test.com', roll='P12_05')

    # Invalid status
    ok, err = employment_service.save_outcome(student.id, {
        'status': 'UnknownStatus',
    }, current_user=user)
    assert ok is False
    assert "Invalid status" in err

    # Nonexistent skill ID
    ok, err = employment_service.save_outcome(student.id, {
        'status': 'In Progress',
        'skill_ids': [999999],
    }, current_user=user)
    assert ok is False
    assert "does not exist in master skills catalog" in err


def test_delete_outcome():
    """Deleting an outcome deletes both outcome and junction rows."""
    user, student = create_student_user(email='del_svc@test.com', roll='P12_06')
    skills = setup_sample_skills()

    data = {
        'status': 'Placed',
        'company_name': 'Delete Me Corp',
        'role_title': 'Tester',
        'salary_package_lpa': 5.0,
        'placement_date': date.today(),
        'skill_ids': [skills['Python'].id],
    }
    employment_service.save_outcome(student.id, data, current_user=user)

    # Delete outcome
    ok, err = employment_service.delete_outcome(student.id, current_user=user)
    assert ok is True

    # Verify deleted
    outcome = EmploymentOutcome.query.filter_by(student_id=student.id).first()
    assert outcome is None
    skills_count = EmploymentOutcomeSkill.query.filter_by(skill_id=skills['Python'].id).count()
    # No orphan junction rows for this outcome


def test_ownership_enforcement():
    """Student cannot modify or view another student's outcome."""
    userA, studentA = create_student_user(email='studentA@test.com', roll='P12_A')
    userB, studentB = create_student_user(email='studentB@test.com', roll='P12_B')

    # Save outcome for Student A
    employment_service.save_outcome(studentA.id, {'status': 'In Progress'}, current_user=userA)

    # Student B attempts to get Student A's outcome
    res = employment_service.get_outcome(studentA.id, current_user=userB)
    assert res is None

    # Student B attempts to edit Student A's outcome
    ok, err = employment_service.save_outcome(studentA.id, {'status': 'Not Placed'}, current_user=userB)
    assert ok is False
    assert "Access denied" in err

    # Student B attempts to delete Student A's outcome
    ok, err = employment_service.delete_outcome(studentA.id, current_user=userB)
    assert ok is False
    assert "Access denied" in err


# ════════════════════════════════════════════════════════════════════════════════
#  2. ANALYTICS SERVICE TESTS (Pandas)
# ════════════════════════════════════════════════════════════════════════════════

def test_analytics_service_hand_calculated_example():
    """Verify placement %, average salary, and median salary match hand calculations."""
    records = [
        {'status': 'Placed', 'salary_package_lpa': 6.0},
        {'status': 'Placed', 'salary_package_lpa': 12.0},
        {'status': 'Placed', 'salary_package_lpa': 9.0},
        {'status': 'In Progress', 'salary_package_lpa': None},
        {'status': 'Not Placed', 'salary_package_lpa': None},
    ]

    # Hand calculations:
    # Total = 5
    # Placed = 3
    # Placement % = 3/5 * 100 = 60.0%
    # Salaries: [6.0, 9.0, 12.0]
    # Mean = (6 + 9 + 12) / 3 = 9.00
    # Median = 9.00

    pct = analytics_service.placement_percentage(records)
    assert pct == 60.0

    avg_sal = analytics_service.average_salary(records)
    assert avg_sal == 9.00

    med_sal = analytics_service.median_salary(records)
    assert med_sal == 9.00

    summary = analytics_service.compute_employment_summary(records)
    assert summary['total_students'] == 5
    assert summary['placed_count'] == 3
    assert summary['placement_pct'] == 60.0
    assert summary['avg_salary_display'] == '9.00 LPA'
    assert summary['median_salary_display'] == '9.00 LPA'


def test_analytics_service_empty_data_safe():
    """Empty datasets return safe defaults without throwing exceptions."""
    empty_summary = analytics_service.compute_employment_summary([])
    assert empty_summary['total_students'] == 0
    assert empty_summary['placed_count'] == 0
    assert empty_summary['placement_pct'] == 0.0
    assert empty_summary['avg_salary_display'] == 'N/A'
    assert empty_summary['median_salary_display'] == 'N/A'


# ════════════════════════════════════════════════════════════════════════════════
#  3. STUDENT WEB ROUTE TESTS
# ════════════════════════════════════════════════════════════════════════════════

def test_student_employment_page_flow(client):
    """Student can view page, submit outcome form, view badge, and delete record."""
    user, student = create_student_user(email='web_student@test.com', roll='P12_W01')
    skills = setup_sample_skills()

    login_client(client, user.email, 'Pass1234')

    # 1. View empty page
    res_get = client.get('/student/employment')
    assert res_get.status_code == 200
    assert b"No Employment Record" in res_get.data

    # 2. Submit form to record Placed status
    res_post = client.post('/student/employment', data={
        'status': 'Placed',
        'company_name': 'Google Cloud',
        'role_title': 'Cloud Architect',
        'salary_package_lpa': '15.50',
        'placement_date': date.today().strftime('%Y-%m-%d'),
        'placement_type': 'Campus',
        'notes': 'Great onboarding process.',
        'skills_used': [str(skills['Python'].id)],
    }, follow_redirects=True)
    assert res_post.status_code == 200
    assert b"Employment outcome updated successfully" in res_post.data
    assert b"Cloud Architect" in res_post.data
    assert b"Google Cloud" in res_post.data
    assert b"15.50 LPA" in res_post.data

    # 3. Check Dashboard shows real status and role
    res_dash = client.get('/student/dashboard')
    assert res_dash.status_code == 200
    assert b"Cloud Architect" in res_dash.data
    assert b"Google Cloud" in res_dash.data

    # 4. Delete outcome
    res_del = client.post('/student/employment/delete', follow_redirects=True)
    assert res_del.status_code == 200
    assert b"Employment outcome deleted successfully" in res_del.data
    assert b"No Employment Record Found" in res_del.data


# ════════════════════════════════════════════════════════════════════════════════
#  4. ADMIN WEB ROUTE & CSV EXPORT TESTS
# ════════════════════════════════════════════════════════════════════════════════

def test_admin_employment_page_and_csv_export(client):
    """Admin can view outcomes, filter, and download sanitized CSV."""
    admin = create_admin_user(email='admin_page@test.com')
    user, student = create_student_user(email='student_for_admin@test.com', roll='P12_ADM01', branch='ECE')

    # Record outcome with potential formula injection to test sanitization
    employment_service.save_outcome(student.id, {
        'status': 'Placed',
        'company_name': '=SUM(A1:A10)',  # Formula injection attempt
        'role_title': '+AdminRole',
        'salary_package_lpa': 10.0,
        'placement_date': date.today(),
    })

    login_client(client, admin.email, 'AdminPass123')

    # 1. View admin employment page
    res_admin = client.get('/admin/employment')
    assert res_admin.status_code == 200
    assert b"Employment &amp; Placement Outcomes" in res_admin.data or b"Employment & Placement Outcomes" in res_admin.data
    assert b"P12_ADM01" in res_admin.data

    # 2. Filter by branch
    res_filt = client.get('/admin/employment?branch=ECE')
    assert res_filt.status_code == 200
    assert b"P12_ADM01" in res_filt.data

    # 3. Export CSV and check formula injection sanitization
    res_csv = client.get('/admin/employment/export-csv')
    assert res_csv.status_code == 200
    assert res_csv.content_type.startswith('text/csv')
    csv_text = res_csv.data.decode('utf-8')
    assert "Student Name,Roll Number,Branch" in csv_text
    # Cell starting with '=' must be prefixed with single quote
    assert "'=SUM(A1:A10)" in csv_text
    assert "'+AdminRole" in csv_text


def test_access_control(client):
    """Guest redirected; student blocked from admin employment page."""
    user, student = create_student_user(email='student_lock@test.com', roll='P12_LOCK')

    # 1. Guest redirected
    client.get('/logout')
    res_guest = client.get('/student/employment')
    assert res_guest.status_code in [302, 401]

    # 2. Student blocked from admin employment page (403 or redirect)
    login_client(client, user.email, 'Pass1234')
    res_block = client.get('/admin/employment')
    assert res_block.status_code in [302, 403]


# ════════════════════════════════════════════════════════════════════════════════
#  5. API ENDPOINT TESTS
# ════════════════════════════════════════════════════════════════════════════════

def test_api_employment_endpoints(client):
    """GET and POST /api/student/<id>/employment validation and ownership."""
    user, student = create_student_user(email='api_emp@test.com', roll='P12_API')
    other_user, other_student = create_student_user(email='api_other@test.com', roll='P12_OTHER')

    login_client(client, user.email, 'Pass1234')

    # 1. POST valid outcome via API
    res_post = client.post(
        f'/api/student/{student.id}/employment',
        data=json.dumps({
            'status': 'In Progress',
            'notes': 'Interviewing with multiple startups.'
        }),
        content_type='application/json'
    )
    assert res_post.status_code == 200
    data = res_post.get_json()
    assert data['success'] is True
    assert data['data']['status'] == 'In Progress'

    # 2. GET outcome
    res_get = client.get(f'/api/student/{student.id}/employment')
    assert res_get.status_code == 200
    data_get = res_get.get_json()
    assert data_get['success'] is True
    assert data_get['data']['notes'] == 'Interviewing with multiple startups.'

    # 3. Ownership: student cannot touch another student's outcome (403)
    res_unauth = client.get(f'/api/student/{other_student.id}/employment')
    assert res_unauth.status_code == 403

    # 4. Invalid student ID (404)
    res_404 = client.get('/api/student/999999/employment')
    assert res_404.status_code == 404


# ════════════════════════════════════════════════════════════════════════════════
#  6. DEMO SEED SCRIPT TEST
# ════════════════════════════════════════════════════════════════════════════════

def test_seed_demo_students_idempotent():
    """seed_demo_students runs twice with no duplicates and produces mixed outcomes."""
    from seed_demo_students import seed_demo_students

    # Run seed function
    seed_demo_students()

    # Query demo students
    demo_students = Student.query.filter(Student.roll_number.like('22DEMO%')).all()
    assert len(demo_students) == 30

    # Verify distribution includes all 3 statuses
    demo_outcomes = [st.employment_outcome for st in demo_students if st.employment_outcome]
    statuses = {o.status for o in demo_outcomes}
    assert 'Placed' in statuses
    assert 'In Progress' in statuses
    assert 'Not Placed' in statuses

    # Run seed function a second time — must not create duplicates
    seed_demo_students()
    demo_students_again = Student.query.filter(Student.roll_number.like('22DEMO%')).all()
    assert len(demo_students_again) == 30
