"""
tests/conftest.py
──────────────────
Pytest configuration and shared fixtures for all test suites.
"""

import pytest
from app import create_app
from extensions import db as _db
from models.user import User
from models.student import Student, Certification, Project, Internship, SkillProgress
from models.skill import Skill, SkillAlias, StudentSkill, Resume
from models.job import JobRole, JobDescription, JobSkill
from models.gap import SkillGapAnalysis, GapSkill
from models.course import Course, CourseSkill, CourseProgress, LearningPathItem
from models.outcome import EmploymentOutcome, EmploymentOutcomeSkill
from models.forum import ForumCategory, ForumThread, ForumPost, ForumPostLike, ForumReport


@pytest.fixture(scope='session')
def app():
    """Create Flask app wired to an in-memory SQLite database for tests."""
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
    with test_app.app_context():
        _db.drop_all()


@pytest.fixture(autouse=True)
def app_context(app):
    """Provide a fresh Flask app context per test, clearing g automatically."""
    ctx = app.app_context()
    ctx.push()
    yield ctx
    ctx.pop()


@pytest.fixture
def client(app):
    """Flask test client with fresh session per test."""
    with app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def clean_db(app, app_context):
    """Wipe tables before each test for clean isolation."""
    _db.session.rollback()
    _db.session.close()
    _db.session.remove()
    _db.session.expunge_all()
    _db.session.query(ForumReport).delete()
    _db.session.query(ForumPostLike).delete()
    _db.session.query(ForumPost).delete()
    _db.session.query(ForumThread).delete()
    _db.session.query(ForumCategory).delete()
    _db.session.query(EmploymentOutcomeSkill).delete()
    _db.session.query(EmploymentOutcome).delete()
    _db.session.query(Resume).delete()
    _db.session.query(LearningPathItem).delete()
    _db.session.query(CourseProgress).delete()
    _db.session.query(CourseSkill).delete()
    _db.session.query(Course).delete()
    _db.session.query(GapSkill).delete()
    _db.session.query(SkillGapAnalysis).delete()
    _db.session.query(SkillProgress).delete()
    _db.session.query(StudentSkill).delete()
    _db.session.query(Certification).delete()
    _db.session.query(Project).delete()
    _db.session.query(Internship).delete()
    _db.session.query(Student).delete()
    _db.session.query(User).delete()
    _db.session.query(JobSkill).delete()
    _db.session.query(JobDescription).delete()
    _db.session.query(JobRole).delete()
    _db.session.commit()
    _db.session.expunge_all()
    _db.session.remove()
    yield
    _db.session.rollback()
    _db.session.expunge_all()
    _db.session.remove()
