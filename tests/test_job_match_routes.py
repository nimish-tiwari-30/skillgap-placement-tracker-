"""
tests/test_job_match_routes.py
───────────────────────────────
Integration tests for Phase 9: Job Matching service, web routes, and API endpoints.

Tests:
  - Service match_student_to_all_jobs returns accurate Coverage % and Overall Match %
  - Web route /student/job-match loads for student with transparent dual progress bars
  - Mandatory transparency info note is present and visible
  - UI wording is neutral (never claims "recommended" or hiring probability)
  - Search, career role filter, and neutral sorting work as expected
  - Web route /student/job-match/<id> loads detail breakdown and links
  - Guest redirect to /login and admin RBAC 403 protection
  - API GET /api/job/<id>/match returns structured JSON
  - API GET /api/job/<id>/match returns 404 on invalid job_id
  - API GET /api/student/<id>/job-matches enforces data ownership
"""

import pytest
from app import create_app
from extensions import db as _db
from models.user import User
from models.student import Student
from models.skill import Skill, StudentSkill
from models.job import JobRole, JobDescription, JobSkill
from services import match_service, gap_service


def login_client(client, email, password):
    client.get('/logout')
    return client.post('/login', data={'email': email, 'password': password})


def setup_matching_fixtures():
    """Create test student, job roles, skills, and 3 distinct jobs."""
    user = User(email='matcher_student@test.com', role='student', is_active=True)
    user.set_password('Student@123')
    _db.session.add(user)
    _db.session.flush()

    student = Student(
        user_id=user.id,
        full_name='Matching Candidate',
        roll_number='MATCH101',
        branch='Computer Science',
    )
    _db.session.add(student)
    _db.session.flush()

    role1 = JobRole(title='Data Science & Analytics', department='Engineering')
    role2 = JobRole(title='Web & Backend Development', department='Engineering')
    _db.session.add_all([role1, role2])
    _db.session.flush()

    # Skills: Python, SQL, Excel, Django, React
    skill_names = ['Python', 'SQL', 'Excel', 'Django', 'React']
    skills = {}
    for name in skill_names:
        s = Skill.query.filter_by(name=name).first()
        if not s:
            s = Skill(name=name, category='Tech')
            _db.session.add(s)
            _db.session.flush()
        skills[name] = s

    # Give student {Python (Advanced), SQL (Intermediate)}
    ss1 = StudentSkill(student_id=student.id, skill_id=skills['Python'].id, proficiency_level='Advanced')
    ss2 = StudentSkill(student_id=student.id, skill_id=skills['SQL'].id, proficiency_level='Intermediate')
    _db.session.add_all([ss1, ss2])

    # Job 1: Data Analyst (requires Python, SQL, Excel) -> High Match
    job1 = JobDescription(
        job_role_id=role1.id,
        title='Data Analyst Lead',
        company_name='Alpha Data Corp',
        description_text='Looking for analyst proficient in Python and SQL.',
        is_active=True,
    )
    _db.session.add(job1)
    _db.session.flush()
    _db.session.add(JobSkill(job_description_id=job1.id, skill_id=skills['Python'].id, importance_weight=5))
    _db.session.add(JobSkill(job_description_id=job1.id, skill_id=skills['SQL'].id, importance_weight=4))
    _db.session.add(JobSkill(job_description_id=job1.id, skill_id=skills['Excel'].id, importance_weight=3))

    # Job 2: Web Developer (requires Django, React) -> Zero Match
    job2 = JobDescription(
        job_role_id=role2.id,
        title='Frontend React Developer',
        company_name='Beta Web Studios',
        description_text='Build frontend apps in React and Django backend.',
        is_active=True,
    )
    _db.session.add(job2)
    _db.session.flush()
    _db.session.add(JobSkill(job_description_id=job2.id, skill_id=skills['Django'].id, importance_weight=4))
    _db.session.add(JobSkill(job_description_id=job2.id, skill_id=skills['React'].id, importance_weight=5))

    _db.session.commit()
    return student, user, job1, job2, role1, role2


# ════════════════════════════════════════════════════════════════════════════════
#  1. SERVICE LAYER TESTS
# ════════════════════════════════════════════════════════════════════════════════

def test_service_match_student_to_all_jobs(app):
    """
    Test match_student_to_all_jobs:
      - Alpha Data Corp has 2/3 skills (Coverage = 66.7%) and high Overall Match
      - Beta Web Studios has 0/2 skills (Coverage = 0.0%) and Overall Match = 0.0%
      - Coverage % matches ml.skill_gap calculation
    """
    with app.app_context():
        student, user, job1, job2, role1, role2 = setup_matching_fixtures()

        ok, matches = match_service.match_student_to_all_jobs(student.id, current_user=user)
        assert ok is True
        assert len(matches) == 2

        # Check job 1 (Alpha Data Corp)
        m1 = next(m for m in matches if m['job_id'] == job1.id)
        assert m1['coverage_pct'] == 66.7
        assert m1['matched_count'] == 2
        assert m1['missing_count'] == 1
        assert m1['overall_match_pct'] > 50.0

        # Check job 2 (Beta Web Studios)
        m2 = next(m for m in matches if m['job_id'] == job2.id)
        assert m2['coverage_pct'] == 0.0
        assert m2['matched_count'] == 0
        assert m2['overall_match_pct'] == 0.0


def test_service_match_single_job_detail(app):
    """
    Test match_student_to_job returns complete breakdown of skills and percentages.
    """
    with app.app_context():
        student, user, job1, job2, role1, role2 = setup_matching_fixtures()

        ok, data = match_service.match_student_to_job(student.id, job1.id, current_user=user)
        assert ok is True
        assert data['job_id'] == job1.id
        assert set(data['matched']) == {'Python', 'SQL'}
        assert set(data['missing']) == {'Excel'}
        assert data['coverage_pct'] == 66.7
        assert data['overall_match_pct'] > 0.0


# ════════════════════════════════════════════════════════════════════════════════
#  2. WEB ROUTE TESTS
# ════════════════════════════════════════════════════════════════════════════════

def test_web_guest_redirected_from_job_match(client, app):
    """Unauthenticated visitor is redirected to /login."""
    client.get('/logout')
    res = client.get('/student/job-match')
    assert res.status_code == 302
    assert '/login' in res.headers.get('Location', '')


def test_web_admin_blocked_from_student_job_match(client, app):
    """Admin is blocked with 403 from student-only job match page."""
    with app.app_context():
        admin = User(email='admin_match@test.com', role='admin', is_active=True)
        admin.set_password('AdminPass123')
        _db.session.add(admin)
        _db.session.commit()

    login_client(client, 'admin_match@test.com', 'AdminPass123')
    res = client.get('/student/job-match')
    assert res.status_code == 403


def test_web_job_match_page_content_and_info_note(client, app):
    """
    Test student /student/job-match page:
      - Displays both percentages per job: Skill Coverage and Overall Job Match
      - Contains mandatory transparency info note
      - Contains neutral sorting label ('Sorted by: Overall Match')
      - Does NOT contain prescriptive 'recommended' claims or hiring probability wording
    """
    with app.app_context():
        student, user, job1, job2, role1, role2 = setup_matching_fixtures()

    login_client(client, 'matcher_student@test.com', 'Student@123')
    res = client.get('/student/job-match')
    assert res.status_code == 200
    html = res.data.decode('utf-8')

    # Both percentages labeled
    assert "Overall Job Match" in html
    assert "Skill Coverage" in html

    # Mandatory info note text
    assert "Skill Coverage = how many required skills you have." in html
    assert "Overall Job Match = how similar your skill profile is to the job, weighted by importance and proficiency." in html
    assert "Neither is a prediction of getting hired. Demo data." in html

    # Neutral sorting label
    assert "Sorted by: Overall Match" in html

    # Neutral wording check: Ensure no prescriptive claims
    assert "you should choose" not in html.lower()
    assert "hiring probability" not in html.lower()

    # Job titles present
    assert "Data Analyst Lead" in html
    assert "Frontend React Developer" in html


def test_web_job_match_filtering_and_sorting(client, app):
    """
    Test search filtering and role filtering on /student/job-match.
    """
    with app.app_context():
        student, user, job1, job2, role1, role2 = setup_matching_fixtures()
        role1_id = role1.id

    login_client(client, 'matcher_student@test.com', 'Student@123')

    # Search filter: 'React'
    res_search = client.get('/student/job-match?q=React')
    assert res_search.status_code == 200
    html_search = res_search.data.decode('utf-8')
    assert "Frontend React Developer" in html_search
    assert "Data Analyst Lead" not in html_search

    # Role filter: role1 (Data Science)
    res_role = client.get(f'/student/job-match?role_id={role1_id}')
    assert res_role.status_code == 200
    html_role = res_role.data.decode('utf-8')
    assert "Data Analyst Lead" in html_role
    assert "Frontend React Developer" not in html_role


def test_web_job_match_detail_page(client, app):
    """
    Test /student/job-match/<job_id>:
      - Shows both percentages
      - Shows matched/missing badges
      - Links to 'Run full skill-gap analysis'
    """
    with app.app_context():
        student, user, job1, job2, role1, role2 = setup_matching_fixtures()
        job1_id = job1.id

    login_client(client, 'matcher_student@test.com', 'Student@123')
    res = client.get(f'/student/job-match/{job1_id}')
    assert res.status_code == 200
    html = res.data.decode('utf-8')

    assert "Data Analyst Lead" in html
    assert "Overall Job Match" in html
    assert "Skill Coverage" in html
    assert "Run Full Skill-Gap Analysis" in html
    assert "Python" in html
    assert "SQL" in html
    assert "Excel" in html


# ════════════════════════════════════════════════════════════════════════════════
#  3. JSON API TESTS
# ════════════════════════════════════════════════════════════════════════════════

def test_api_job_match_endpoint(client, app):
    """
    GET /api/job/<id>/match:
      - Returns success JSON with coverage, weighted, overall_match, matched, missing, extra
      - Returns 404 for invalid job_id
    """
    with app.app_context():
        student, user, job1, job2, role1, role2 = setup_matching_fixtures()
        job1_id = job1.id

    login_client(client, 'matcher_student@test.com', 'Student@123')

    # Valid job
    res = client.get(f'/api/job/{job1_id}/match')
    assert res.status_code == 200
    json_data = res.get_json()

    assert json_data['success'] is True
    data = json_data['data']
    assert data['job_id'] == job1_id
    assert data['coverage'] == 66.7
    assert data['overall_match'] > 0.0
    assert set(data['matched']) == {'Python', 'SQL'}
    assert set(data['missing']) == {'Excel'}

    # Invalid job -> 404
    res_404 = client.get('/api/job/99999/match')
    assert res_404.status_code == 404
    assert res_404.get_json()['success'] is False


def test_api_student_job_matches_ownership(client, app):
    """
    GET /api/student/<id>/job-matches:
      - Student can get own matches
      - Student cannot view another student's matches (403)
      - Admin can view any student's matches
    """
    with app.app_context():
        student1, user1, job1, job2, role1, role2 = setup_matching_fixtures()

        user2 = User(email='other_student@test.com', role='student', is_active=True)
        user2.set_password('Pass1234')
        _db.session.add(user2)
        _db.session.flush()
        student2 = Student(user_id=user2.id, full_name='Other Candidate', roll_number='OTHER99', branch='IT')
        _db.session.add(student2)

        admin = User(email='admin_matches@test.com', role='admin', is_active=True)
        admin.set_password('AdminPass123')
        _db.session.add(admin)
        _db.session.commit()

        s1_id = student1.id
        s2_id = student2.id

    # 1. Student 1 views own matches -> 200
    login_client(client, 'matcher_student@test.com', 'Student@123')
    res1 = client.get(f'/api/student/{s1_id}/job-matches')
    assert res1.status_code == 200
    assert res1.get_json()['success'] is True
    assert len(res1.get_json()['data']) == 2

    # 2. Student 1 attempts to view Student 2's matches -> 403 Forbidden
    res_forbidden = client.get(f'/api/student/{s2_id}/job-matches')
    assert res_forbidden.status_code == 403
    assert res_forbidden.get_json()['success'] is False

    # 3. Admin can view Student 1's matches -> 200
    login_client(client, 'admin_matches@test.com', 'AdminPass123')
    res_admin = client.get(f'/api/student/{s1_id}/job-matches')
    assert res_admin.status_code == 200
    assert res_admin.get_json()['success'] is True
