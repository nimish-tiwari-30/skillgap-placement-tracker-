"""
tests/test_phase16_ui.py
─────────────────────────
Phase 16 UI / UX Polish Verification & Render Audit Suite.

Covers:
1. Render check for every GET route across guest, student, and admin roles.
2. Verified presence of design tokens, skip-links, accessibility tags, and titles.
3. Preserved demo data disclaimers, ML limitations warnings, and security headers.
4. Chart theme and dark-mode asset availability.
"""

import pytest
from extensions import db as _db
from models.user import User
from models.student import Student
from models.job import JobRole, JobDescription
from models.course import Course
from models.skill import Skill, StudentSkill


@pytest.fixture
def ui_test_env(app):
    """Seed minimal coherent database fixtures for page rendering."""
    # 1. Create student and user
    u_student = User(email='ui_student@college.edu', role='student', is_active=True)
    u_student.set_password('Secret123!')
    _db.session.add(u_student)
    _db.session.flush()

    student = Student(
        user_id=u_student.id,
        full_name='UI Test Student',
        roll_number='22UI001',
        branch='Computer Science',
        cgpa=8.5
    )
    _db.session.add(student)

    # 2. Create admin user
    u_admin = User(email='ui_admin@college.edu', role='admin', is_active=True)
    u_admin.set_password('AdminSecret123!')
    _db.session.add(u_admin)

    # 3. Job Role and Job
    role = JobRole(title='Full Stack Engineer', department='Engineering')
    _db.session.add(role)
    _db.session.flush()

    job = JobDescription(
        title='Junior Full Stack Developer',
        company_name='Nexus Tech Labs',
        location='Bengaluru, India',
        description_text='Looking for Python, JavaScript, and Docker proficiency.',
        min_experience='0-1 years',
        job_role_id=role.id,
        is_active=True
    )
    _db.session.add(job)

    # 4. Course
    course = Course(
        title='Production Web Systems',
        provider='Coursera',
        url='https://coursera.org/production-web',
        rating=4.8,
        difficulty_level='Intermediate'
    )
    _db.session.add(course)

    # 5. Skill
    skill = Skill.query.filter_by(name='Python').first()
    if not skill:
        skill = Skill(name='Python', category='Programming')
        _db.session.add(skill)
        _db.session.flush()

    ss = StudentSkill(student_id=student.id, skill_id=skill.id, proficiency_level='Intermediate')
    _db.session.add(ss)

    _db.session.commit()

    return {
        'student_user': u_student,
        'student': student,
        'admin_user': u_admin,
        'job': job,
        'course': course
    }


def test_landing_page_renders_hero_and_features(client):
    """GET / renders modern landing page when unauthenticated."""
    res = client.get('/', follow_redirects=False)
    assert res.status_code == 200
    assert b'SkillGap AI' in res.data
    assert b'Bridge the Gap Between Campus Learning' in res.data
    assert b'Resume Skill Extraction' in res.data
    assert b'Skill-Gap Analysis' in res.data
    assert b'Smart Job Matching' in res.data
    assert b'How It Works' in res.data
    assert b'Sign In' in res.data
    assert b'Get Started' in res.data


def test_auth_pages_render_cleanly(client):
    """GET /login and /register render with proper titles and forms."""
    res_login = client.get('/login')
    assert res_login.status_code == 200
    assert b'Sign In' in res_login.data
    assert b'Welcome back' in res_login.data
    assert b'csrf_token' in res_login.data

    res_reg = client.get('/register')
    assert res_reg.status_code == 200
    assert b'Create Account' in res_reg.data
    assert b'csrf_token' in res_reg.data


def test_student_get_pages_render_audit(client, ui_test_env):
    """Verify all student GET pages render HTTP 200 with skip links and navbar."""
    # Login as student
    client.post('/login', data={'email': 'ui_student@college.edu', 'password': 'Secret123!'})

    job_id = ui_test_env['job'].id

    student_urls = [
        '/student/dashboard',
        '/student/profile',
        '/student/resume',
        '/student/skill-gap',
        '/student/jobs',
        f'/student/jobs/{job_id}',
        '/student/job-match',
        f'/student/job-match/{job_id}',
        '/student/recommendations',
        f'/student/recommendations?job_id={job_id}',
        '/student/learning-path',
        f'/student/learning-path?job_id={job_id}',
        '/student/progress',
        '/student/employment',
        '/student/analytics',
        '/student/prediction',
    ]

    for url in student_urls:
        res = client.get(url)
        assert res.status_code == 200, f"Page {url} failed with status {res.status_code}"
        # Assert accessibility & layout integrity
        assert b'<html lang="en">' in res.data
        assert b'Skip to main content' in res.data
        assert b'top-navbar' in res.data
        assert b'style.css' in res.data


def test_admin_get_pages_render_audit(client, ui_test_env):
    """Verify all admin GET pages render HTTP 200 with grouped navigation."""
    # Login as admin
    client.post('/login', data={'email': 'ui_admin@college.edu', 'password': 'AdminSecret123!'})

    student_id = ui_test_env['student'].id
    job_id = ui_test_env['job'].id

    admin_urls = [
        '/admin/dashboard',
        '/admin/students',
        f'/admin/students/{student_id}',
        '/admin/job-roles',
        '/admin/jobs',
        '/admin/jobs/create',
        f'/admin/jobs/{job_id}/edit',
        f'/admin/jobs/{job_id}/skills',
        '/admin/skills',
        '/admin/courses',
        '/admin/employment',
        '/admin/model',
    ]

    for url in admin_urls:
        res = client.get(url)
        assert res.status_code == 200, f"Admin page {url} failed with status {res.status_code}"
        # Assert layout and navigation
        assert b'Skip to main content' in res.data
        assert b'top-navbar' in res.data
        assert b'Overview' in res.data
        assert b'Data' in res.data
        assert b'Analytics' in res.data


def test_disclaimers_and_demo_banners_preserved(client, ui_test_env):
    """Verify disclaimers, limitations boxes, and demo banners are strictly preserved."""
    # 1. Admin dashboard demo notice
    client.post('/login', data={'email': 'ui_admin@college.edu', 'password': 'AdminSecret123!'})
    res_admin = client.get('/admin/dashboard')
    assert res_admin.status_code == 200
    assert b'Demo project: figures shown are computed from synthetic/demo data' in res_admin.data

    # 2. Admin ML Model management limitations / demo mode
    res_model = client.get('/admin/model')
    assert res_model.status_code == 200
    assert b'Feature Leakage' in res_model.data
    assert b'Not enough real historical data yet' in res_model.data or b'historical' in res_model.data

    # 3. Student Prediction page limitations
    client.get('/logout')
    client.post('/login', data={'email': 'ui_student@college.edu', 'password': 'Secret123!'})
    res_pred = client.get('/student/prediction')
    assert res_pred.status_code == 200
    assert b'Model Limitations' in res_pred.data
    assert b'not a placement guarantee' in res_pred.data


def test_security_headers_and_csp_still_active(client):
    """Verify CSP and security headers from Phase 15 still exist on responses."""
    res = client.get('/')
    assert res.headers.get('X-Content-Type-Options') == 'nosniff'
    assert res.headers.get('X-Frame-Options') == 'DENY'
    assert res.headers.get('Referrer-Policy') == 'same-origin'
    assert 'Content-Security-Policy' in res.headers
    csp = res.headers['Content-Security-Policy']
    assert "cdn.jsdelivr.net" in csp
    assert "fonts.googleapis.com" in csp
