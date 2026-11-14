"""
tests/test_database.py
───────────────────────
Phase 15: Database Integrity & Schema Synchronization Suite.

Covers:
  1. CRUD operations on core models (User, Student, Skill, JobRole, Course, EmploymentOutcome)
  2. Foreign Key constraint enforcement (invalid user_id on Student, invalid skill_id on StudentSkill)
  3. ON DELETE cascade behavior (users -> students deletion cascade)
  4. Unique constraint enforcement (email, roll_number, (student_id, skill_id), (job_description_id, skill_id), (course_id, skill_id))
  5. Schema-vs-Model synchronization test: Verifies that every table and column
     defined in database/schema.sql matches the SQLAlchemy model definitions.
"""

import os
import re
import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import Engine
import sqlite3

from extensions import db
from models.user import User
from models.student import Student, Project, Certification, Internship, SkillProgress
from models.skill import Skill, SkillAlias, StudentSkill, Resume
from models.job import JobRole, JobDescription, JobSkill
from models.gap import SkillGapAnalysis, GapSkill
from models.course import Course, CourseSkill, CourseProgress, LearningPathItem
from models.outcome import EmploymentOutcome, EmploymentOutcomeSkill


@pytest.fixture(autouse=True)
def enable_sqlite_foreign_keys(app):
    """Ensure SQLite enforces foreign key constraints during tests."""
    with app.app_context():
        db.session.execute(text("PRAGMA foreign_keys = ON;"))
        db.session.commit()
    yield


# ── 1. Model CRUD Operations ──────────────────────────────────────────────────

def test_crud_operations(app):
    """Test Create, Read, Update, Delete for representative models."""
    with app.app_context():
        # Create User & Student
        user = User(email='crud_user@test.com', role='student', is_active=True)
        user.set_password('Pass1234!')
        db.session.add(user)
        db.session.flush()

        student = Student(
            user_id=user.id,
            full_name='CRUD Student',
            roll_number='CRUD01',
            branch='CS',
            cgpa=8.5,
            profile_completion_pct=40
        )
        db.session.add(student)

        # Create Skill
        skill = Skill(name='Rust Programming', category='Programming', description='Systems language')
        db.session.add(skill)

        # Create Job Role
        role = JobRole(title='Systems Engineer', department='Infrastructure', description='Low level systems')
        db.session.add(role)

        # Create Course
        course = Course(title='Learn Rust', provider='Coursera', difficulty_level='Beginner', duration_hours=20.0)
        db.session.add(course)

        db.session.commit()

        # READ
        saved_student = Student.query.filter_by(roll_number='CRUD01').first()
        assert saved_student is not None
        assert saved_student.full_name == 'CRUD Student'
        assert float(saved_student.cgpa) == 8.5

        saved_skill = Skill.query.filter_by(name='Rust Programming').first()
        assert saved_skill is not None
        assert saved_skill.category == 'Programming'

        # UPDATE
        saved_student.full_name = 'CRUD Student Updated'
        saved_student.cgpa = 9.1
        saved_skill.description = 'Modern memory-safe systems programming'
        db.session.commit()

        refreshed_student = Student.query.filter_by(roll_number='CRUD01').first()
        assert refreshed_student.full_name == 'CRUD Student Updated'
        assert float(refreshed_student.cgpa) == 9.1

        # Outcome CRUD
        outcome = EmploymentOutcome(
            student_id=student.id,
            status='Placed',
            company_name='RustCorp',
            role_title='Junior Systems Engineer',
            salary_package_lpa=14.5
        )
        db.session.add(outcome)
        db.session.commit()

        saved_outcome = EmploymentOutcome.query.filter_by(student_id=student.id).first()
        assert saved_outcome is not None
        assert saved_outcome.company_name == 'RustCorp'

        # DELETE
        db.session.delete(saved_outcome)
        db.session.delete(saved_student)
        db.session.delete(user)
        db.session.delete(saved_skill)
        db.session.delete(role)
        db.session.delete(course)
        db.session.commit()

        assert Student.query.filter_by(roll_number='CRUD01').first() is None
        assert Skill.query.filter_by(name='Rust Programming').first() is None


# ── 2. Foreign Key Constraint Enforcement ─────────────────────────────────────

def test_fk_constraint_violations(app):
    """Assert invalid foreign key references are rejected with IntegrityError."""
    with app.app_context():
        # 1. Student referencing non-existent user_id
        invalid_student = Student(
            user_id=999999,  # Non-existent
            full_name='Ghost Student',
            roll_number='GHOST01',
            branch='CS'
        )
        db.session.add(invalid_student)
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()

        # 2. StudentSkill referencing non-existent skill_id
        valid_user = User(email='fk_user@test.com', role='student')
        valid_user.set_password('Pass1234!')
        db.session.add(valid_user)
        db.session.flush()

        valid_student = Student(user_id=valid_user.id, full_name='Valid St', roll_number='VALID01', branch='CS')
        db.session.add(valid_student)
        db.session.commit()

        invalid_student_skill = StudentSkill(
            student_id=valid_student.id,
            skill_id=888888,  # Non-existent
            proficiency_level='Beginner'
        )
        db.session.add(invalid_student_skill)
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


# ── 3. ON DELETE Cascade Behavior ─────────────────────────────────────────────

def test_user_to_student_cascade_delete(app):
    """
    Verify ON DELETE CASCADE behavior:
    Deleting a User automatically deletes associated Student profile.
    """
    with app.app_context():
        u = User(email='cascade_test@test.com', role='student')
        u.set_password('Pass1234!')
        db.session.add(u)
        db.session.flush()

        st = Student(user_id=u.id, full_name='Cascade Student', roll_number='CASC01', branch='IT')
        db.session.add(st)
        db.session.commit()

        st_id = st.id
        u_id = u.id

        assert db.session.get(Student, st_id) is not None

        # Delete User
        db.session.delete(u)
        db.session.commit()

        # Student should be removed
        assert db.session.get(User, u_id) is None
        assert db.session.get(Student, st_id) is None


# ── 4. Unique Constraints Enforcement ─────────────────────────────────────────

def test_unique_constraints(app):
    """
    Assert unique constraints prevent duplicate data:
    - User.email
    - Student.roll_number
    - StudentSkill (student_id, skill_id)
    - JobSkill (job_description_id, skill_id)
    - CourseSkill (course_id, skill_id)
    """
    with app.app_context():
        # Duplicate user email
        u1 = User(email='unique_email@test.com', role='student')
        u1.set_password('Pass1234!')
        db.session.add(u1)
        db.session.commit()

        u2 = User(email='unique_email@test.com', role='student')
        u2.set_password('Pass1234!')
        db.session.add(u2)
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()

        # Duplicate student roll number
        u_a = User(email='roll_a@test.com', role='student')
        u_a.set_password('Pass1234!')
        u_b = User(email='roll_b@test.com', role='student')
        u_b.set_password('Pass1234!')
        db.session.add_all([u_a, u_b])
        db.session.flush()

        s_a = Student(user_id=u_a.id, full_name='A', roll_number='DUP_ROLL', branch='CS')
        db.session.add(s_a)
        db.session.commit()

        s_b = Student(user_id=u_b.id, full_name='B', roll_number='DUP_ROLL', branch='IT')
        db.session.add(s_b)
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()

        # Duplicate StudentSkill (student_id, skill_id)
        skill = Skill(name='Kotlin', category='Programming')
        db.session.add(skill)
        db.session.commit()

        ss1 = StudentSkill(student_id=s_a.id, skill_id=skill.id, proficiency_level='Beginner')
        db.session.add(ss1)
        db.session.commit()

        ss2 = StudentSkill(student_id=s_a.id, skill_id=skill.id, proficiency_level='Advanced')
        db.session.add(ss2)
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()

        # Duplicate JobSkill (job_description_id, skill_id)
        role = JobRole(title='Mobile Dev', department='Tech')
        db.session.add(role)
        db.session.flush()
        jd = JobDescription(job_role_id=role.id, title='Android Dev', description_text='Android with Kotlin')
        db.session.add(jd)
        db.session.flush()

        js1 = JobSkill(job_description_id=jd.id, skill_id=skill.id, importance_weight=4)
        db.session.add(js1)
        db.session.commit()

        js2 = JobSkill(job_description_id=jd.id, skill_id=skill.id, importance_weight=5)
        db.session.add(js2)
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()

        # Duplicate CourseSkill (course_id, skill_id)
        c = Course(title='Kotlin for Android', provider='Google')
        db.session.add(c)
        db.session.flush()

        cs1 = CourseSkill(course_id=c.id, skill_id=skill.id)
        db.session.add(cs1)
        db.session.commit()

        cs2 = CourseSkill(course_id=c.id, skill_id=skill.id)
        db.session.add(cs2)
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


# ── 5. Schema-vs-Model Synchronization Test ───────────────────────────────────

def _parse_schema_sql_tables(schema_path: str) -> dict[str, set[str]]:
    """
    Parse CREATE TABLE blocks in schema.sql to extract table names
    and their set of column names.
    """
    with open(schema_path, 'r', encoding='utf-8') as f:
        sql = f.read()

    # Regex to extract CREATE TABLE statements
    table_pattern = re.compile(
        r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s*\((.*?)\)\s*ENGINE',
        re.DOTALL | re.IGNORECASE
    )

    schema_tables = {}
    for match in table_pattern.finditer(sql):
        table_name = match.group(1).lower()
        body = match.group(2)

        columns = set()
        for line in body.splitlines():
            line = line.strip()
            # Ignore comments, keys, constraints
            if not line or line.startswith('--'):
                continue
            first_word = line.split()[0].upper()
            if first_word in ('PRIMARY', 'KEY', 'UNIQUE', 'INDEX', 'CONSTRAINT', 'FOREIGN', 'CHECK', 'ON', 'REFERENCES'):
                continue

            # First token is the column name
            col_name = line.split()[0].strip('`",')
            if col_name:
                columns.add(col_name.lower())

        schema_tables[table_name] = columns

    return schema_tables


def test_schema_sql_vs_model_synchronization(app):
    """
    Assert that every table and column in SQLAlchemy models exactly matches
    database/schema.sql.
    """
    base_dir = os.path.dirname(os.path.dirname(__file__))
    schema_path = os.path.join(base_dir, 'database', 'schema.sql')
    assert os.path.exists(schema_path), f"schema.sql not found at {schema_path}"

    schema_tables = _parse_schema_sql_tables(schema_path)
    assert len(schema_tables) >= 20, f"Expected at least 20 tables in schema.sql, found {len(schema_tables)}"

    model_tables = db.metadata.tables

    # Check each schema table has a matching model table and column set
    for tbl_name, expected_cols in schema_tables.items():
        assert tbl_name in model_tables, f"Table '{tbl_name}' in schema.sql is missing from SQLAlchemy models"

        model_col_names = {col.name.lower() for col in model_tables[tbl_name].columns}

        # Check column differences
        missing_in_model = expected_cols - model_col_names
        extra_in_model = model_col_names - expected_cols

        assert not missing_in_model, (
            f"Table '{tbl_name}' in schema.sql has columns missing from model: {missing_in_model}"
        )
        assert not extra_in_model, (
            f"Model table '{tbl_name}' has extra columns not declared in schema.sql: {extra_in_model}"
        )
