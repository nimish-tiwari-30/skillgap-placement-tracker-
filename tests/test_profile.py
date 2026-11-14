"""
tests/test_profile.py
──────────────────────
Phase 5 pytest tests for student profile and skill management.

Run:  .\\venv\\Scripts\\python.exe -m pytest tests/test_profile.py -v
"""

import pytest
from app import create_app
from extensions import db as _db
from models.user import User
from models.student import Student, SkillProgress, Certification
from models.skill import Skill, StudentSkill, SkillAlias


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope='module')
def app():
    test_app = create_app('testing')
    test_app.config.update({
        'TESTING': True,
        'WTF_CSRF_ENABLED': False,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'SERVER_NAME': 'localhost',
    })
    with test_app.app_context():
        _db.create_all()
        yield test_app
        _db.drop_all()


@pytest.fixture
def client(app):
    """Fresh client with clean DB for each test."""
    with app.app_context():
        # Clean up before each test
        _db.session.query(SkillProgress).delete()
        _db.session.query(StudentSkill).delete()
        _db.session.query(Certification).delete()
        _db.session.query(SkillAlias).delete()
        _db.session.query(Skill).delete()
        _db.session.query(Student).delete()
        _db.session.query(User).delete()
        _db.session.commit()

    with app.test_client() as c:
        yield c


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_student(app, email='student@test.com', roll='22CS001'):
    """Create a student user in the DB directly."""
    with app.app_context():
        user = User(email=email, role='student', is_active=True)
        user.set_password('TestPass123')
        _db.session.add(user)
        _db.session.flush()
        student = Student(user_id=user.id, full_name='Test Student',
                          roll_number=roll, branch='Computer Science')
        _db.session.add(student)
        _db.session.commit()
        return user.id, student.id


def make_skill(app, name='Python', category='Programming'):
    """Insert a skill into DB and return its id."""
    with app.app_context():
        skill = Skill(name=name, category=category)
        _db.session.add(skill)
        _db.session.commit()
        return skill.id


def login(client, email='student@test.com', password='TestPass123'):
    return client.post('/login', data={'email': email, 'password': password})


def make_admin(app, email='admin@test.com'):
    """Create admin user."""
    with app.app_context():
        admin = User(email=email, role='admin', is_active=True)
        admin.set_password('AdminPass123')
        _db.session.add(admin)
        _db.session.commit()


# ════════════════════════════════════════════════════════════════════════════════
#  SKILL TESTS
# ════════════════════════════════════════════════════════════════════════════════

def test_add_skill(client, app):
    """Student can add a skill."""
    uid, sid = make_student(app)
    skill_id = make_skill(app)
    login(client)

    res = client.post('/student/profile/skills/add', data={
        'skill_id': skill_id, 'proficiency': 'Beginner'
    })
    assert res.status_code == 302

    with app.app_context():
        ss = StudentSkill.query.filter_by(student_id=sid, skill_id=skill_id).first()
        assert ss is not None
        assert ss.proficiency_level == 'Beginner'


def test_add_duplicate_skill_blocked(client, app):
    """Adding the same skill twice is blocked with a friendly message."""
    uid, sid = make_student(app)
    skill_id = make_skill(app)
    login(client)

    client.post('/student/profile/skills/add', data={'skill_id': skill_id, 'proficiency': 'Beginner'})
    client.post('/student/profile/skills/add', data={'skill_id': skill_id, 'proficiency': 'Advanced'})

    with app.app_context():
        count = StudentSkill.query.filter_by(student_id=sid, skill_id=skill_id).count()
        assert count == 1  # still only one row, no duplicate


def test_update_proficiency(client, app):
    """Student can update skill proficiency."""
    uid, sid = make_student(app)
    skill_id = make_skill(app)
    login(client)

    client.post('/student/profile/skills/add', data={'skill_id': skill_id, 'proficiency': 'Beginner'})
    client.post('/student/profile/skills/update', data={'skill_id': skill_id, 'proficiency': 'Advanced'})

    with app.app_context():
        ss = StudentSkill.query.filter_by(student_id=sid, skill_id=skill_id).first()
        assert ss.proficiency_level == 'Advanced'


def test_remove_skill(client, app):
    """Student can remove a skill."""
    uid, sid = make_student(app)
    skill_id = make_skill(app)
    login(client)

    client.post('/student/profile/skills/add', data={'skill_id': skill_id, 'proficiency': 'Beginner'})
    client.post('/student/profile/skills/remove', data={'skill_id': skill_id})

    with app.app_context():
        ss = StudentSkill.query.filter_by(student_id=sid, skill_id=skill_id).first()
        assert ss is None


def test_skill_progress_row_created(client, app):
    """Adding a skill creates a SkillProgress record."""
    uid, sid = make_student(app)
    skill_id = make_skill(app)
    login(client)

    client.post('/student/profile/skills/add', data={'skill_id': skill_id, 'proficiency': 'Intermediate'})

    with app.app_context():
        prog = SkillProgress.query.filter_by(student_id=sid, skill_id=skill_id).first()
        assert prog is not None
        assert prog.new_proficiency == 'Intermediate'
        assert prog.old_proficiency is None


# ════════════════════════════════════════════════════════════════════════════════
#  OWNERSHIP / SECURITY
# ════════════════════════════════════════════════════════════════════════════════

def test_student_cannot_reach_admin_skills(client, app):
    """Student gets 403 on /admin/skills."""
    make_student(app)
    login(client)
    res = client.get('/admin/skills', follow_redirects=False)
    assert res.status_code == 403


def test_student_cannot_delete_other_students_cert(client, app):
    """Student B cannot delete Student A's cert (service ownership check)."""
    from services.profile_service import add_certification, delete_certification

    uid_a, sid_a = make_student(app, email='a@test.com', roll='22A001')
    uid_b, sid_b = make_student(app, email='b@test.com', roll='22B002')

    # Add cert for student A directly via service
    with app.app_context():
        student_a = _db.session.get(Student, sid_a)
        add_certification(student_a, {'title': 'Cert A'})
        cert_id = Certification.query.filter_by(student_id=sid_a).first().id

    # Now try to delete student A's cert as student B (via service)
    with app.app_context():
        student_b = _db.session.get(Student, sid_b)
        ok, err = delete_certification(student_b, cert_id)
        assert ok is False           # Must be blocked
        assert 'not found' in err.lower() or 'denied' in err.lower()


def test_non_admin_blocked_from_admin_skills(client, app):
    """Student is forbidden from /admin/skills."""
    make_student(app)
    login(client)
    res = client.get('/admin/skills', follow_redirects=False)
    assert res.status_code == 403


# ════════════════════════════════════════════════════════════════════════════════
#  PROFILE COMPLETION
# ════════════════════════════════════════════════════════════════════════════════

def test_profile_completion_calculation(client, app):
    """Known scenario: 5 skills + basic details + cgpa + grad year + phone + links = 80%."""
    from services.profile_service import calculate_profile_completion, update_profile

    uid, sid = make_student(app)

    with app.app_context():
        student = _db.session.get(Student, sid)

        # Update academic details directly via service
        update_profile(student, {
            'full_name': 'Test Student',
            'branch': 'Computer Science',
            'cgpa': '8.5',
            'graduation_year': '2025',
            'phone': '9876543210',
            'linkedin_url': 'https://linkedin.com/in/test',
            'github_url': 'https://github.com/test',
        })

        # Add 5 different skills
        for i in range(5):
            skill = Skill(name=f'Skill{i}', category='Programming')
            _db.session.add(skill)
        _db.session.commit()

        skills = Skill.query.all()
        for skill in skills[:5]:
            ss = StudentSkill(student_id=sid, skill_id=skill.id, proficiency_level='Beginner')
            _db.session.add(ss)
        _db.session.commit()

        student = _db.session.get(Student, sid)
        result = calculate_profile_completion(student)

        # Expected: basic(20)+phone(10)+cgpa(10)+grad(10)+5skills(20)+linkedin(5)+github(5) = 80
        assert result['percentage'] == 80
        assert isinstance(result['missing'], list)


# ════════════════════════════════════════════════════════════════════════════════
#  ADMIN SKILL MANAGEMENT
# ════════════════════════════════════════════════════════════════════════════════

def test_admin_can_add_skill(client, app):
    """Admin can add a new skill via service."""
    from services.profile_service import admin_add_skill
    with app.app_context():
        ok, err = admin_add_skill('AdminTestSkill', 'Tools', 'A test skill')
        assert ok is True
        assert err is None
        skill = Skill.query.filter_by(name='AdminTestSkill').first()
        assert skill is not None
        assert skill.category == 'Tools'


def test_admin_duplicate_skill_blocked(client, app):
    """Admin cannot add duplicate skill name — service returns error."""
    from services.profile_service import admin_add_skill
    with app.app_context():
        ok1, _ = admin_add_skill('UniqueSkill', 'Tools')
        ok2, err2 = admin_add_skill('UniqueSkill', 'Tools')   # duplicate
        assert ok1 is True
        assert ok2 is False
        assert 'already exists' in err2
        count = Skill.query.filter_by(name='UniqueSkill').count()
        assert count == 1
