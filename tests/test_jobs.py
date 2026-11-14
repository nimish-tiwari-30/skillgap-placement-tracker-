"""
tests/test_jobs.py
──────────────────
Phase 7 pytest suite for:
- NLP skill extraction from job description text (Data Analyst benchmark)
- Admin Job Roles CRUD: unique name enforcement, graceful deletion block when in use
- Admin Job Descriptions CRUD: creation, NLP review flow, atomic job_skills saving,
  and re-edit duplicate prevention
- Student read-only browsing (/student/jobs, /student/jobs/<id>) and RBAC enforcement
- JSON API endpoints (/api/analyze-job, /api/jobs)
"""

import json
import pytest
from extensions import db as _db
from models.user import User
from models.student import Student
from models.skill import Skill, SkillAlias
from models.job import JobRole, JobDescription, JobSkill
from ml.skill_extractor import refresh_skills_cache, extract_skills_from_text
from services import job_service


# ── Helpers ──────────────────────────────────────────────────────────────────

def seed_test_skills():
    """Ensure required skills and aliases exist for tests."""
    skills_data = [
        ("Python", "Programming", ["Python3", "Py"]),
        ("SQL", "Data & Analytics", ["Structured Query Language"]),
        ("Power BI", "Data & Analytics", ["Power-BI", "PowerBI"]),
        ("Excel", "Data & Analytics", ["MS Excel", "Microsoft Excel"]),
        ("Statistics", "Data & Analytics", []),
        ("Java", "Programming", []),
        ("Docker", "Cloud/DevOps", []),
        ("AWS", "Cloud/DevOps", []),
    ]

    for name, cat, aliases in skills_data:
        skill = Skill.query.filter_by(name=name).first()
        if not skill:
            skill = Skill(name=name, category=cat)
            _db.session.add(skill)
            _db.session.flush()

        for alias in aliases:
            if not SkillAlias.query.filter_by(alias_name=alias).first():
                _db.session.add(SkillAlias(skill_id=skill.id, alias_name=alias))

    _db.session.commit()
    refresh_skills_cache()


def make_admin(app, email='admin_test@test.com'):
    """Create an admin user."""
    with app.app_context():
        user = User(email=email, role='admin')
        user.set_password('AdminPass123!')
        _db.session.add(user)
        _db.session.commit()
        return user.id


def make_student(app, email='student_test@test.com', roll='22TEST01'):
    """Create a student user."""
    with app.app_context():
        user = User(email=email, role='student')
        user.set_password('StudentPass123!')
        _db.session.add(user)
        _db.session.flush()

        student = Student(
            user_id=user.id,
            full_name='Test Student',
            roll_number=roll,
            branch='Computer Science',
            graduation_year=2026
        )
        _db.session.add(student)
        _db.session.commit()
        return user.id


def login(client, email, password):
    """Log in via the auth route."""
    return client.post('/login', data={'email': email, 'password': password}, follow_redirects=True)


def logout(client):
    """Log out current session."""
    return client.get('/logout', follow_redirects=True)


# ════════════════════════════════════════════════════════════════════════════
#  1. NLP SKILL EXTRACTION TEST
# ════════════════════════════════════════════════════════════════════════════

def test_job_skill_extraction_data_analyst(app):
    """
    Test extraction:
    'We are looking for a Data Analyst with experience in Python, SQL, Power BI, Excel and Statistics.'
    returns those five skills.
    """
    with app.app_context():
        seed_test_skills()

        text = "We are looking for a Data Analyst with experience in Python, SQL, Power BI, Excel and Statistics."
        extracted = extract_skills_from_text(text)
        extracted_names = {s['canonical_name'] for s in extracted}

        expected = {"Python", "SQL", "Power BI", "Excel", "Statistics"}
        assert expected.issubset(extracted_names), f"Missing skills: {expected - extracted_names}"
        assert len(extracted_names.intersection(expected)) == 5


# ════════════════════════════════════════════════════════════════════════════
#  2. ADMIN JOB ROLES CRUD & SAFETY TESTS
# ════════════════════════════════════════════════════════════════════════════

def test_admin_job_role_crud_and_duplicate_blocked(app, client):
    """Admin can create, edit, and duplicate role name is blocked."""
    seed_test_skills()
    make_admin(app)

    login(client, 'admin_test@test.com', 'AdminPass123!')

    # 1. Create role
    resp = client.post('/admin/job-roles/create', data={
        'title': 'Data Analyst',
        'department': 'Analytics',
        'description': 'Analyzes business data.'
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert b"created successfully" in resp.data

    with app.app_context():
        role = JobRole.query.filter_by(title='Data Analyst').first()
        assert role is not None
        assert role.department == 'Analytics'

    # 2. Duplicate role name blocked
    resp_dup = client.post('/admin/job-roles/create', data={
        'title': 'Data Analyst',
        'department': 'Other Dept',
        'description': 'Duplicate attempt'
    }, follow_redirects=True)
    assert resp_dup.status_code == 200
    assert b"already exists" in resp_dup.data

    with app.app_context():
        count = JobRole.query.filter_by(title='Data Analyst').count()
        assert count == 1

    # 3. Edit role
    with app.app_context():
        role = JobRole.query.filter_by(title='Data Analyst').first()
        role_id = role.id

    resp_edit = client.post(f'/admin/job-roles/{role_id}/edit', data={
        'title': 'Lead Data Analyst',
        'department': 'Advanced Analytics',
        'description': 'Leads analytics team.'
    }, follow_redirects=True)
    assert resp_edit.status_code == 200
    assert b"updated successfully" in resp_edit.data

    with app.app_context():
        updated = JobRole.query.get(role_id)
        assert updated.title == 'Lead Data Analyst'
        assert updated.department == 'Advanced Analytics'


def test_in_use_role_delete_blocked_gracefully(app, client):
    """Deleting a job role assigned to existing job descriptions must be blocked gracefully."""
    seed_test_skills()
    make_admin(app)

    with app.app_context():
        role = JobRole(title='Backend Developer', department='Engineering')
        _db.session.add(role)
        _db.session.flush()

        job = JobDescription(
            job_role_id=role.id,
            title='Python Developer',
            company_name='Demo Company A',
            description_text='We need Python and SQL experience.',
            is_active=True
        )
        _db.session.add(job)
        _db.session.commit()
        role_id = role.id

    login(client, 'admin_test@test.com', 'AdminPass123!')

    # Attempt to delete role in use
    resp = client.post(f'/admin/job-roles/{role_id}/delete', follow_redirects=True)
    assert resp.status_code == 200
    assert b"Cannot delete" in resp.data

    with app.app_context():
        role_still_exists = JobRole.query.get(role_id)
        assert role_still_exists is not None

    # Delete the job first, then role deletion should succeed
    with app.app_context():
        job_to_del = JobDescription.query.filter_by(job_role_id=role_id).first()
        _db.session.delete(job_to_del)
        _db.session.commit()

    resp_del_ok = client.post(f'/admin/job-roles/{role_id}/delete', follow_redirects=True)
    assert resp_del_ok.status_code == 200
    assert b"deleted successfully" in resp_del_ok.data

    with app.app_context():
        assert JobRole.query.get(role_id) is None


# ════════════════════════════════════════════════════════════════════════════
#  3. ADMIN JOB DESCRIPTIONS & JOB_SKILLS PERSISTENCE TESTS
# ════════════════════════════════════════════════════════════════════════════

def test_admin_job_descriptions_and_skills_persistence(app, client):
    """
    Test job creation, skill review screen, atomic job_skills saving,
    and verifying re-edit does not create duplicate rows.
    """
    seed_test_skills()
    make_admin(app)

    with app.app_context():
        role = JobRole(title='Data Scientist', department='AI')
        _db.session.add(role)
        _db.session.commit()
        role_id = role.id

    login(client, 'admin_test@test.com', 'AdminPass123!')

    # 1. Create job description
    resp_create = client.post('/admin/jobs/create', data={
        'job_role_id': role_id,
        'title': 'Junior Data Scientist',
        'company_name': 'Demo AI Labs',
        'location': 'Bangalore',
        'min_experience': '0-1 years',
        'description_text': 'We are looking for someone with Python, SQL, Statistics, and Excel knowledge.',
        'is_active': 'y'
    }, follow_redirects=True)

    assert resp_create.status_code == 200
    # Must redirect to the skill review screen
    assert b"Review Required Skills" in resp_create.data

    with app.app_context():
        job = JobDescription.query.filter_by(title='Junior Data Scientist').first()
        assert job is not None
        job_id = job.id

        py_skill = Skill.query.filter_by(name='Python').first()
        sql_skill = Skill.query.filter_by(name='SQL').first()
        stat_skill = Skill.query.filter_by(name='Statistics').first()

    # 2. Confirm skills on review screen with weights
    review_post_data = {
        'skill_ids': [py_skill.id, sql_skill.id, stat_skill.id],
        f'importance_{py_skill.id}': 5,     # Critical
        f'importance_{sql_skill.id}': 4,    # High
        f'importance_{stat_skill.id}': 3,   # Required
    }

    resp_confirm = client.post(f'/admin/jobs/{job_id}/skills', data=review_post_data, follow_redirects=True)
    assert resp_confirm.status_code == 200
    assert b"Successfully configured" in resp_confirm.data

    with app.app_context():
        js_rows = JobSkill.query.filter_by(job_description_id=job_id).all()
        assert len(js_rows) == 3
        weights = {js.skill.name: js.importance_weight for js in js_rows}
        assert weights['Python'] == 5
        assert weights['SQL'] == 4
        assert weights['Statistics'] == 3

    # 3. Re-edit job and re-confirm skills without creating duplicates
    re_review_data = {
        'skill_ids': [py_skill.id, sql_skill.id],
        f'importance_{py_skill.id}': 5,
        f'importance_{sql_skill.id}': 5,
    }
    resp_reconfirm = client.post(f'/admin/jobs/{job_id}/skills', data=re_review_data, follow_redirects=True)
    assert resp_reconfirm.status_code == 200

    with app.app_context():
        js_rows_after = JobSkill.query.filter_by(job_description_id=job_id).all()
        # Should now be 2 rows (no duplicates, clean update)
        assert len(js_rows_after) == 2
        for js in js_rows_after:
            assert js.importance_weight == 5


# ════════════════════════════════════════════════════════════════════════════
#  4. STUDENT READ-ONLY & RBAC PERMISSIONS TESTS
# ════════════════════════════════════════════════════════════════════════════

def test_student_can_browse_jobs_read_only(app, client):
    """Student can view /student/jobs and /student/jobs/<id>."""
    seed_test_skills()
    make_student(app)

    with app.app_context():
        role = JobRole(title='Web Developer', department='Frontend')
        _db.session.add(role)
        _db.session.flush()

        job = JobDescription(
            job_role_id=role.id,
            title='Frontend Engineer',
            company_name='Demo Web Corp',
            description_text='Looking for someone skilled in Python and SQL.',
            is_active=True
        )
        _db.session.add(job)
        _db.session.flush()

        py_skill = Skill.query.filter_by(name='Python').first()
        js = JobSkill(job_description_id=job.id, skill_id=py_skill.id, importance_weight=5)
        _db.session.add(js)
        _db.session.commit()
        job_id = job.id

    login(client, 'student_test@test.com', 'StudentPass123!')

    # Student views jobs list
    resp_list = client.get('/student/jobs')
    assert resp_list.status_code == 200
    assert b"Frontend Engineer" in resp_list.data
    assert b"Demo Web Corp" in resp_list.data

    # Student views job detail
    resp_detail = client.get(f'/student/jobs/{job_id}')
    assert resp_detail.status_code == 200
    assert b"Required Skills" in resp_detail.data
    assert b"Python" in resp_detail.data
    assert b"Critical" in resp_detail.data


def test_student_blocked_from_admin_jobs_pages(app, client):
    """Student cannot access admin job management pages (403 Forbidden)."""
    make_student(app)
    login(client, 'student_test@test.com', 'StudentPass123!')

    # Student tries to reach admin job roles
    resp_roles = client.get('/admin/job-roles')
    assert resp_roles.status_code == 403

    # Student tries to reach admin jobs
    resp_jobs = client.get('/admin/jobs')
    assert resp_jobs.status_code == 403

    # Student tries to reach create job
    resp_create = client.get('/admin/jobs/create')
    assert resp_create.status_code == 403


def test_guest_redirected_to_login(app, client):
    """Unauthenticated guest is redirected to login page."""
    logout(client)

    resp_student_jobs = client.get('/student/jobs')
    assert resp_student_jobs.status_code == 302
    assert '/login' in resp_student_jobs.headers['Location']

    resp_admin_jobs = client.get('/admin/jobs')
    assert resp_admin_jobs.status_code == 302
    assert '/login' in resp_admin_jobs.headers['Location']


# ════════════════════════════════════════════════════════════════════════════
#  5. API ENDPOINTS TESTS (/api/analyze-job, /api/jobs)
# ════════════════════════════════════════════════════════════════════════════

def test_api_analyze_job(app, client):
    """POST /api/analyze-job accepts {description} and returns {success, data:{skills:[{name, count}]}}."""
    seed_test_skills()
    make_student(app)
    login(client, 'student_test@test.com', 'StudentPass123!')

    # Valid payload
    payload = {
        'description': 'We need a developer with Python and SQL experience. Python is required.'
    }
    resp = client.post('/api/analyze-job', json=payload)
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data['success'] is True
    assert 'data' in data
    assert 'skills' in data['data']

    skills = data['data']['skills']
    names = {s['name'] for s in skills}
    assert 'Python' in names
    assert 'SQL' in names

    # Empty payload should return 400
    resp_empty = client.post('/api/analyze-job', json={'description': ''})
    assert resp_empty.status_code == 400
    empty_data = json.loads(resp_empty.data)
    assert empty_data['success'] is False


def test_api_get_jobs(app, client):
    """GET /api/jobs returns active jobs list with required skills."""
    seed_test_skills()
    make_student(app)

    with app.app_context():
        role = JobRole(title='DevOps Engineer', department='Cloud')
        _db.session.add(role)
        _db.session.flush()

        job = JobDescription(
            job_role_id=role.id,
            title='Cloud DevOps Specialist',
            company_name='Demo Cloud A',
            description_text='Looking for someone with Docker and AWS experience.',
            location='Remote',
            min_experience='1-2 years',
            is_active=True
        )
        _db.session.add(job)
        _db.session.flush()

        docker_skill = Skill.query.filter_by(name='Docker').first()
        aws_skill = Skill.query.filter_by(name='AWS').first()
        _db.session.add(JobSkill(job_description_id=job.id, skill_id=docker_skill.id, importance_weight=5))
        _db.session.add(JobSkill(job_description_id=job.id, skill_id=aws_skill.id, importance_weight=4))
        _db.session.commit()

    login(client, 'student_test@test.com', 'StudentPass123!')

    resp = client.get('/api/jobs')
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data['success'] is True
    assert isinstance(data['data'], list)
    assert len(data['data']) >= 1

    found_job = next((j for j in data['data'] if j['title'] == 'Cloud DevOps Specialist'), None)
    assert found_job is not None
    assert found_job['company_name'] == 'Demo Cloud A'
    assert found_job['role'] == 'DevOps Engineer'

    skill_names = {s['name'] for s in found_job['skills']}
    assert 'Docker' in skill_names
    assert 'AWS' in skill_names
