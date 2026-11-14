"""
tests/test_resume.py
────────────────────
Phase 6 pytest suite for secure resume upload, MIME/magic byte checks,
text extraction (PDF/DOCX), review & confirm flow, duplicate handling,
and ownership enforcement.

Run:  .\\venv\\Scripts\\python.exe -m pytest tests/test_resume.py -v
"""

import io
import os
import pytest
from extensions import db as _db
from models.user import User
from models.student import Student, SkillProgress
from models.skill import Skill, SkillAlias, StudentSkill, Resume
from ml.skill_extractor import refresh_skills_cache


# ── Fixture & test setup helpers ─────────────────────────────────────────────

def seed_test_skills():
    """Ensure baseline canonical skills and aliases exist for tests."""
    skills_data = [
        ("Python", "Programming", ["Python3", "Py"]),
        ("Java", "Programming", ["Core Java"]),
        ("C++", "Programming", ["CPP"]),
        ("C#", "Programming", ["CSharp"]),
        ("JavaScript", "Programming", ["JS", "ES6"]),
        ("React", "Web", ["ReactJS", "React.js"]),
        ("SQL", "Data & Analytics", []),
        ("Excel", "Data & Analytics", ["MS Excel"]),
        ("Power BI", "Data & Analytics", ["Power-BI"]),
        ("PostgreSQL", "Database", ["Postgres"]),
        ("Docker", "Cloud/DevOps", []),
        ("Machine Learning", "AI/ML", ["ML"]),
        ("scikit-learn", "AI/ML", ["sklearn"]),
        ("Node.js", "Web", ["NodeJS"]),
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


def make_student(app, email='student@test.com', roll='22CS001'):
    """Create a student user directly in DB."""
    with app.app_context():
        user = User(email=email, role='student')
        user.set_password('Password123')
        _db.session.add(user)
        _db.session.flush()

        student = Student(
            user_id=user.id,
            full_name='Test Student',
            roll_number=roll,
            branch='Computer Science',
            cgpa=8.0,
            graduation_year=2025
        )
        _db.session.add(student)
        _db.session.commit()
        return user.id, student.id


def login(client, email='student@test.com', password='Password123'):
    """Helper to log in via HTTP session."""
    client.get('/logout')
    return client.post('/login', data={'email': email, 'password': password}, follow_redirects=True)


# ════════════════════════════════════════════════════════════════════════════════
#  UPLOAD & MAGIC BYTE VALIDATION TESTS
# ════════════════════════════════════════════════════════════════════════════════

def test_resume_upload_pdf_success(client, app):
    """Student uploads a valid PDF resume; text is extracted and review screen is staged."""
    uid, sid = make_student(app)
    login(client)

    with app.app_context():
        seed_test_skills()

    fixture_path = os.path.join(app.root_path, 'tests', 'fixtures', 'sample_resume.pdf')
    with open(fixture_path, 'rb') as f:
        pdf_bytes = f.read()

    res = client.post(
        '/student/resume/upload',
        data={'resume': (io.BytesIO(pdf_bytes), 'sample_resume.pdf')},
        content_type='multipart/form-data',
        follow_redirects=True
    )
    assert res.status_code == 200
    assert b"Resume parsed successfully" in res.data
    assert b"Review Detected Skills" in res.data

    with app.app_context():
        student = _db.session.get(Student, sid)
        assert len(student.resumes) == 1
        active_res = student.resumes[0]
        assert active_res.is_active is True
        assert active_res.original_name == 'sample_resume.pdf'
        assert active_res.file_type == 'pdf'
        assert active_res.extracted_text is not None
        assert "Python" in active_res.extracted_text


def test_resume_upload_docx_success(client, app):
    """Student uploads a valid DOCX resume; paragraphs and tables are extracted."""
    uid, sid = make_student(app)
    login(client)

    with app.app_context():
        seed_test_skills()

    fixture_path = os.path.join(app.root_path, 'tests', 'fixtures', 'sample_resume.docx')
    with open(fixture_path, 'rb') as f:
        docx_bytes = f.read()

    res = client.post(
        '/student/resume/upload',
        data={'resume': (io.BytesIO(docx_bytes), 'sample_resume.docx')},
        content_type='multipart/form-data',
        follow_redirects=True
    )
    assert res.status_code == 200
    assert b"Resume parsed successfully" in res.data

    with app.app_context():
        student = _db.session.get(Student, sid)
        active_res = student.resumes[0]
        assert active_res.file_type == 'docx'
        assert "Java" in active_res.extracted_text
        assert "PostgreSQL" in active_res.extracted_text


def test_fake_extension_file_rejected(client, app):
    """A non-PDF file renamed as .pdf is rejected by magic byte checking."""
    make_student(app)
    login(client)

    fixture_path = os.path.join(app.root_path, 'tests', 'fixtures', 'fake_resume.pdf')
    with open(fixture_path, 'rb') as f:
        fake_bytes = f.read()

    res = client.post(
        '/student/resume/upload',
        data={'resume': (io.BytesIO(fake_bytes), 'fake_resume.pdf')},
        content_type='multipart/form-data',
        follow_redirects=True
    )
    assert res.status_code == 200
    assert b"missing %PDF signature" in res.data or b"corrupted" in res.data

    with app.app_context():
        assert Resume.query.count() == 0


def test_empty_file_rejected(client, app):
    """0-byte file is rejected with a friendly error."""
    make_student(app)
    login(client)

    res = client.post(
        '/student/resume/upload',
        data={'resume': (io.BytesIO(b""), 'empty.pdf')},
        content_type='multipart/form-data',
        follow_redirects=True
    )
    assert res.status_code == 200
    assert b"empty" in res.data.lower() or b"select a resume" in res.data.lower()


def test_invalid_extension_rejected(client, app):
    """Files with non-whitelisted extensions (.txt, .exe) are blocked."""
    make_student(app)
    login(client)

    res = client.post(
        '/student/resume/upload',
        data={'resume': (io.BytesIO(b"dummy code"), 'program.exe')},
        content_type='multipart/form-data',
        follow_redirects=True
    )
    assert res.status_code == 200
    assert b"Only PDF" in res.data or b"Invalid file type" in res.data


def test_oversized_file_rejected(client, app):
    """Files exceeding MAX_UPLOAD_MB limit are rejected."""
    make_student(app)
    login(client)

    # 17 MB dummy PDF
    large_bytes = b"%PDF-1.4\n" + b"A" * (17 * 1024 * 1024)
    res = client.post(
        '/student/resume/upload',
        data={'resume': (io.BytesIO(large_bytes), 'huge.pdf')},
        content_type='multipart/form-data',
        follow_redirects=True
    )
    assert res.status_code in (200, 413)
    if res.status_code == 200:
        assert b"exceeds" in res.data.lower() or b"limit" in res.data.lower()


# ════════════════════════════════════════════════════════════════════════════════
#  CONFIRM FLOW & PROFILE INTEGRATION TESTS
# ════════════════════════════════════════════════════════════════════════════════

def test_confirm_flow_adds_skills_and_skips_duplicates(client, app):
    """Confirm action persists selected skills with source='resume', skips existing, logs progress."""
    uid, sid = make_student(app)
    login(client)

    with app.app_context():
        seed_test_skills()
        py_skill = Skill.query.filter_by(name='Python').first()
        # Student already has Python
        ss_existing = StudentSkill(
            student_id=sid,
            skill_id=py_skill.id,
            proficiency_level='Advanced',
            source='manual'
        )
        _db.session.add(ss_existing)
        _db.session.commit()

        sql_skill = Skill.query.filter_by(name='SQL').first()
        docker_skill = Skill.query.filter_by(name='Docker').first()
        py_id = py_skill.id
        sql_id = sql_skill.id
        docker_id = docker_skill.id

    # Confirm adding Python, SQL, and Docker
    res = client.post(
        '/student/resume/confirm',
        data={
            'skill_ids': [py_id, sql_id, docker_id],
            f'proficiency_{sql_id}': 'Intermediate',
            f'proficiency_{docker_id}': 'Beginner',
        },
        follow_redirects=True
    )
    assert res.status_code == 200
    assert b"Added 2, skipped 1 already in profile" in res.data

    with app.app_context():
        student = _db.session.get(Student, sid)
        assert len(student.skills) == 3

        # Existing Python kept
        py_entry = [s for s in student.skills if s.skill_id == py_id][0]
        assert py_entry.source == 'manual'
        assert py_entry.proficiency_level == 'Advanced'

        # New SQL added with source='resume'
        sql_entry = [s for s in student.skills if s.skill_id == sql_id][0]
        assert sql_entry.source == 'resume'
        assert sql_entry.proficiency_level == 'Intermediate'

        # Verify SkillProgress logged for new skills
        progs = SkillProgress.query.filter_by(student_id=sid).all()
        assert len(progs) == 2


def test_profile_completion_reflects_resume_upload(client, app):
    """Uploading a resume increases profile completion %."""
    uid, sid = make_student(app)
    login(client)

    with app.app_context():
        student = _db.session.get(Student, sid)
        initial_pct = student.calculate_profile_completion()

    fixture_path = os.path.join(app.root_path, 'tests', 'fixtures', 'sample_resume.pdf')
    with open(fixture_path, 'rb') as f:
        pdf_bytes = f.read()

    client.post(
        '/student/resume/upload',
        data={'resume': (io.BytesIO(pdf_bytes), 'my_resume.pdf')},
        content_type='multipart/form-data',
        follow_redirects=True
    )

    with app.app_context():
        student = _db.session.get(Student, sid)
        new_pct = student.calculate_profile_completion()
        assert new_pct > initial_pct


# ════════════════════════════════════════════════════════════════════════════════
#  OWNERSHIP & SECURITY TESTS
# ════════════════════════════════════════════════════════════════════════════════

def test_student_cannot_download_other_student_resume(client, app):
    """Student B cannot download Student A's resume (404/denied)."""
    uid_a, sid_a = make_student(app, email='a@test.com', roll='22A001')
    uid_b, sid_b = make_student(app, email='b@test.com', roll='22B002')

    # Upload as Student A
    login(client, email='a@test.com')
    fixture_path = os.path.join(app.root_path, 'tests', 'fixtures', 'sample_resume.pdf')
    with open(fixture_path, 'rb') as f:
        pdf_bytes = f.read()

    client.post(
        '/student/resume/upload',
        data={'resume': (io.BytesIO(pdf_bytes), 'a_resume.pdf')},
        content_type='multipart/form-data',
        follow_redirects=True
    )

    with app.app_context():
        res_a = Resume.query.filter_by(student_id=sid_a).first()
        res_a_id = res_a.id

    # Switch session to Student B
    client.get('/logout')
    login(client, email='b@test.com')

    # Student B attempts to download Student A's resume -> 404
    res = client.get(f'/student/resume/download/{res_a_id}')
    assert res.status_code == 404


def test_student_cannot_delete_other_student_resume(client, app):
    """Student B cannot delete Student A's resume."""
    uid_a, sid_a = make_student(app, email='a@test.com', roll='22A001')
    uid_b, sid_b = make_student(app, email='b@test.com', roll='22B002')

    login(client, email='a@test.com')
    fixture_path = os.path.join(app.root_path, 'tests', 'fixtures', 'sample_resume.pdf')
    with open(fixture_path, 'rb') as f:
        pdf_bytes = f.read()

    client.post(
        '/student/resume/upload',
        data={'resume': (io.BytesIO(pdf_bytes), 'a_resume.pdf')},
        content_type='multipart/form-data',
        follow_redirects=True
    )

    with app.app_context():
        res_a_id = Resume.query.filter_by(student_id=sid_a).first().id

    client.get('/logout')
    login(client, email='b@test.com')

    # Student B tries to delete Student A's resume
    res = client.post(f'/student/resume/delete/{res_a_id}', follow_redirects=True)
    assert res.status_code == 200
    assert b"denied" in res.data.lower() or b"not found" in res.data.lower()

    with app.app_context():
        # Ensure resume A was NOT deleted
        assert Resume.query.filter_by(id=res_a_id).first() is not None


# ════════════════════════════════════════════════════════════════════════════════
#  API ENDPOINT TESTS
# ════════════════════════════════════════════════════════════════════════════════

def test_api_analyze_resume(client, app):
    """POST /api/analyze-resume accepts file upload and returns JSON with skills and text_length."""
    make_student(app)
    login(client)

    with app.app_context():
        seed_test_skills()

    fixture_path = os.path.join(app.root_path, 'tests', 'fixtures', 'sample_resume.pdf')
    with open(fixture_path, 'rb') as f:
        pdf_bytes = f.read()

    res = client.post(
        '/api/analyze-resume',
        data={'resume': (io.BytesIO(pdf_bytes), 'sample_resume.pdf')},
        content_type='multipart/form-data'
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data['success'] is True
    assert 'data' in data
    assert 'skills' in data['data']
    assert 'text_length' in data['data']
    assert data['data']['text_length'] > 0

    skill_names = {s['name'] for s in data['data']['skills']}
    assert "Python" in skill_names
    assert "SQL" in skill_names
