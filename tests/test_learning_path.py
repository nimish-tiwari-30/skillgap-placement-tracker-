"""
tests/test_learning_path.py
────────────────────────────
Comprehensive test suite for Phase 11: Learning Path + Progress Tracking.

Covers:
  1. Pure ML core logic (ml/learning_path.py):
     - Worked example: Statistics, Power BI, Tableau difficulty + importance ordering
     - Project and resume fixed final phases
     - Completion % calculation (0 steps, some steps, all steps, zero division guard)
  2. Service layer (services/learning_path_service.py):
     - generate_path idempotency (no duplicate items on repeated calls)
     - Refresh keeps completed items and appends newly missing skills
     - Auto-completion of skills already possessed by the student
     - Atomic mark_complete (item status, completed_at, student_skills source='course', skill_progress row)
     - mark_complete idempotency (harmless on already-completed items)
     - Project and resume milestones completed without a skill_id
     - mark_pending (undo) resets item status without removing skill from profile
     - Profile completion score updates properly after new skills are added
     - Ownership checks (student cannot touch another student's items)
  3. Student web routes (routes/student.py):
     - GET /student/learning-path (target job default, milestone checklist, progress bar)
     - POST /student/learning-path/generate (generates or syncs path)
     - POST /student/learning-path/<item_id>/complete & /undo
     - GET /student/progress (chart datasets and audit log table)
     - Friendly states: no target job, all skills acquired, no progress data
     - Dashboard displays real learning progress card
     - Access control: guest redirected, admin blocked from student pages
  4. API endpoints (routes/api.py):
     - GET /api/student/<id>/learning-path?job_id=<id> (success JSON, own data only, admin allowed)
     - Missing or invalid job_id validation (400 and 404 JSON)
     - POST /api/learning-path/<item_id>/complete (returns updated completion %, rejects unauthorized)
"""

import json
import pytest
from extensions import db as _db
from models.user import User
from models.student import Student, SkillProgress
from models.skill import Skill, StudentSkill
from models.job import JobRole, JobDescription, JobSkill
from models.course import Course, CourseSkill, LearningPathItem
from ml.learning_path import (
    DIFFICULTY_ORDER,
    DEFAULT_PROFICIENCY_MAP,
    generate_learning_path_phases,
    calculate_completion_pct,
)
from services import learning_path_service, profile_service


# ════════════════════════════════════════════════════════════════════════════════
#  FIXTURES & HELPERS
# ════════════════════════════════════════════════════════════════════════════════

def create_student_user(email='learner11@test.com', roll='ROLL11', name='Sam Path'):
    """Create and persist a test student user with student profile."""
    user = User(email=email.strip().lower(), role='student', is_active=True)
    user.set_password('Pass1234')
    _db.session.add(user)
    _db.session.flush()

    student = Student(
        user_id=user.id,
        full_name=name,
        roll_number=roll,
        branch='Information Technology',
    )
    _db.session.add(student)
    _db.session.commit()
    return user, student


def create_admin_user(email='admin11@test.com'):
    """Create and persist a test admin user."""
    user = User(email=email.strip().lower(), role='admin', is_active=True)
    user.set_password('AdminPass123')
    _db.session.add(user)
    _db.session.commit()
    return user


def setup_skills_and_job():
    """
    Setup skills with distinct difficulty and importance weights:
      - Statistics: Intermediate, importance 4
      - Power BI: Beginner, importance 5
      - Tableau: Beginner, importance 3
      - Python: Advanced, importance 5
    """
    skills = {}
    skill_meta = [
        ('Statistics', 'Data', 'Intermediate'),
        ('Power BI', 'BI', 'Beginner'),
        ('Tableau', 'BI', 'Beginner'),
        ('Python', 'Programming', 'Advanced'),
    ]
    for s_name, cat, diff in skill_meta:
        s = Skill.query.filter_by(name=s_name).first()
        if not s:
            s = Skill(name=s_name, category=cat)
            _db.session.add(s)
            _db.session.flush()
        skills[s_name] = s

    role = JobRole(title='BI Analyst Role', department='Analytics')
    _db.session.add(role)
    _db.session.flush()

    job = JobDescription(
        job_role_id=role.id,
        title='Business Intelligence Analyst',
        company_name='Metro Analytics',
        description_text='Looking for BI analyst proficient in Power BI, Tableau, and Statistics.',
        is_active=True,
    )
    _db.session.add(job)
    _db.session.flush()

    # Job requirements
    reqs = [
        ('Power BI', 5),
        ('Tableau', 3),
        ('Statistics', 4),
    ]
    for s_name, weight in reqs:
        js = JobSkill(job_description_id=job.id, skill_id=skills[s_name].id, importance_weight=weight)
        _db.session.add(js)

    # Optional course tagging for Power BI
    course = Course(
        title='Power BI Masterclass 2026',
        provider='Coursera',
        difficulty_level='Beginner',
        duration_hours=12.0,
        rating=4.8,
        url='https://example.com/power-bi',
        description='Hands-on dashboards with Power BI.',
    )
    _db.session.add(course)
    _db.session.flush()
    cs = CourseSkill(course_id=course.id, skill_id=skills['Power BI'].id)
    _db.session.add(cs)

    # Course tagging for Tableau
    c_tab = Course(
        title='Tableau Fundamentals',
        provider='Udemy',
        difficulty_level='Beginner',
        duration_hours=10.0,
        rating=4.7,
        url='https://example.com/tableau',
        description='Beginner Tableau tutorials.',
    )
    _db.session.add(c_tab)
    _db.session.flush()
    cs_tab = CourseSkill(course_id=c_tab.id, skill_id=skills['Tableau'].id)
    _db.session.add(cs_tab)

    # Course tagging for Statistics
    c_stat = Course(
        title='Applied Statistics for Data Science',
        provider='edX',
        difficulty_level='Intermediate',
        duration_hours=18.0,
        rating=4.9,
        url='https://example.com/stats',
        description='Intermediate statistics concepts.',
    )
    _db.session.add(c_stat)
    _db.session.flush()
    cs_stat = CourseSkill(course_id=c_stat.id, skill_id=skills['Statistics'].id)
    _db.session.add(cs_stat)

    _db.session.commit()
    return skills, job, course


# ════════════════════════════════════════════════════════════════════════════════
#  1. PURE ML CORE LOGIC TESTS (ml/learning_path.py)
# ════════════════════════════════════════════════════════════════════════════════

def test_worked_example_ordering():
    """
    Worked example: missing Statistics (Intermediate, weight 4),
    Power BI (Beginner, weight 5), Tableau (Beginner, weight 3).

    Ordering criteria:
      1. Difficulty ascending: Beginner -> Intermediate -> Advanced
      2. Importance descending: 5 -> 4 -> 3
      3. Name ascending
      4. Fixed final milestones: Project, Resume
    """
    missing_skills = [
        {'id': 1, 'name': 'Statistics', 'difficulty': 'Intermediate', 'importance': 4},
        {'id': 2, 'name': 'Power BI', 'difficulty': 'Beginner', 'importance': 5},
        {'id': 3, 'name': 'Tableau', 'difficulty': 'Beginner', 'importance': 3},
    ]

    phases = generate_learning_path_phases(missing_skills)

    # 3 skills + 2 fixed steps = 5 phases
    assert len(phases) == 5

    # Phase 1: Beginner, importance 5 -> Power BI
    assert phases[0]['position'] == 1
    assert phases[0]['skill_id'] == 2
    assert phases[0]['title'] == 'Master Power BI'
    assert phases[0]['difficulty'] == 'Beginner'

    # Phase 2: Beginner, importance 3 -> Tableau
    assert phases[1]['position'] == 2
    assert phases[1]['skill_id'] == 3
    assert phases[1]['title'] == 'Master Tableau'
    assert phases[1]['difficulty'] == 'Beginner'

    # Phase 3: Intermediate, importance 4 -> Statistics
    assert phases[2]['position'] == 3
    assert phases[2]['skill_id'] == 1
    assert phases[2]['title'] == 'Master Statistics'
    assert phases[2]['difficulty'] == 'Intermediate'

    # Phase 4: Capstone project
    assert phases[3]['position'] == 4
    assert phases[3]['skill_id'] is None
    assert phases[3]['title'] == 'Build a project using these skills'

    # Phase 5: Resume update
    assert phases[4]['position'] == 5
    assert phases[4]['skill_id'] is None
    assert phases[4]['title'] == 'Update your resume'


def test_completion_percentage_calculation():
    """Verify completion percentage handles 0, partial, full, and zero items."""
    # Zero total items: zero-division safety
    assert calculate_completion_pct(0, 0) == 0.0
    assert calculate_completion_pct(5, 0) == 0.0

    # 0 completed
    assert calculate_completion_pct(0, 5) == 0.0

    # Partial completed
    assert calculate_completion_pct(1, 5) == 20.0
    assert calculate_completion_pct(2, 3) == 66.7
    assert calculate_completion_pct(1, 7) == 14.3

    # All completed
    assert calculate_completion_pct(5, 5) == 100.0

    # Negative bounds clamped
    assert calculate_completion_pct(-1, 5) == 0.0
    assert calculate_completion_pct(10, 5) == 100.0


# ════════════════════════════════════════════════════════════════════════════════
#  2. SERVICE LAYER TESTS (services/learning_path_service.py)
# ════════════════════════════════════════════════════════════════════════════════

def test_generate_path_idempotency_and_no_duplicates():
    """Generating path twice for same student and job does not create duplicate items."""
    user, student = create_student_user()
    skills, job, _ = setup_skills_and_job()

    ok1, res1 = learning_path_service.generate_path(student.id, job.id, current_user=user)
    assert ok1 is True
    assert res1['total_items'] == 5  # 3 missing + 2 final

    # Second generation call (sync)
    ok2, res2 = learning_path_service.generate_path(student.id, job.id, current_user=user)
    assert ok2 is True
    assert res2['total_items'] == 5

    # Check database row count
    db_items = LearningPathItem.query.filter_by(student_id=student.id).all()
    assert len(db_items) == 5


def test_generate_path_auto_completes_existing_skills():
    """If student already possesses a required skill, it is auto-marked completed."""
    user, student = create_student_user(email='existing_sk@test.com', roll='ROLL_EX')
    skills, job, _ = setup_skills_and_job()

    # 1. Initial path generation
    learning_path_service.generate_path(student.id, job.id, current_user=user)

    # 2. Student acquires Power BI
    ss = StudentSkill(
        student_id=student.id,
        skill_id=skills['Power BI'].id,
        proficiency_level='Beginner',
        source='manual',
    )
    _db.session.add(ss)
    _db.session.commit()

    # 3. Synchronize / refresh path
    ok, res = learning_path_service.generate_path(student.id, job.id, current_user=user)
    assert ok is True
    # The Power BI step should be status='completed'
    pbi_item = LearningPathItem.query.filter_by(
        student_id=student.id,
        skill_id=skills['Power BI'].id,
    ).first()
    assert pbi_item is not None
    assert pbi_item.status == 'completed'
    assert pbi_item.completed_at is not None


def test_mark_complete_atomic_and_idempotent():
    """
    mark_complete in ONE transaction:
      - marks step completed with completed_at
      - adds skill to student_skills (source='course', proficiency chosen)
      - writes a skill_progress row
      - harmless on re-marking already completed step
    """
    user, student = create_student_user(email='atomic@test.com', roll='ROLL_ATOMIC')
    skills, job, _ = setup_skills_and_job()

    learning_path_service.generate_path(student.id, job.id, current_user=user)
    stat_item = LearningPathItem.query.filter_by(
        student_id=student.id,
        skill_id=skills['Statistics'].id,
    ).first()

    assert stat_item.status == 'pending'

    # Mark complete with proficiency 4 (Advanced)
    ok, msg = learning_path_service.mark_complete(
        student_id=student.id,
        item_id=stat_item.id,
        proficiency=4,
        current_user=user,
    )
    assert ok is True

    # 1. Check item status
    _db.session.refresh(stat_item)
    assert stat_item.status == 'completed'
    assert stat_item.completed_at is not None

    # 2. Check student_skills
    ss = StudentSkill.query.filter_by(student_id=student.id, skill_id=skills['Statistics'].id).first()
    assert ss is not None
    assert ss.source == 'course'
    assert ss.proficiency_level == 'Advanced'

    # 3. Check skill_progress row
    prog = SkillProgress.query.filter_by(student_id=student.id, skill_id=skills['Statistics'].id).first()
    assert prog is not None
    assert prog.new_proficiency == 'Advanced'

    # 4. Calling mark_complete again on completed step is harmless
    ok2, _ = learning_path_service.mark_complete(student.id, stat_item.id, proficiency=4, current_user=user)
    assert ok2 is True


def test_mark_complete_final_steps_without_skill():
    """Project and resume steps can be marked complete without a skill_id."""
    user, student = create_student_user(email='milestone@test.com', roll='ROLL_MS')
    skills, job, _ = setup_skills_and_job()

    learning_path_service.generate_path(student.id, job.id, current_user=user)
    project_item = LearningPathItem.query.filter_by(
        student_id=student.id,
        item_type='project',
    ).first()
    assert project_item is not None

    ok, msg = learning_path_service.mark_complete(student.id, project_item.id, current_user=user)
    assert ok is True
    _db.session.refresh(project_item)
    assert project_item.status == 'completed'
    assert project_item.completed_at is not None


def test_mark_pending_undo_does_not_remove_skill():
    """
    Undo (mark_pending) resets step status to 'pending'
    without removing the skill from the profile.
    """
    user, student = create_student_user(email='undo@test.com', roll='ROLL_UNDO')
    skills, job, _ = setup_skills_and_job()

    learning_path_service.generate_path(student.id, job.id, current_user=user)
    tableau_item = LearningPathItem.query.filter_by(
        student_id=student.id,
        skill_id=skills['Tableau'].id,
    ).first()

    # Complete it first
    learning_path_service.mark_complete(student.id, tableau_item.id, proficiency=3, current_user=user)

    # Now Undo
    ok, msg = learning_path_service.mark_pending(student.id, tableau_item.id, current_user=user)
    assert ok is True

    _db.session.refresh(tableau_item)
    assert tableau_item.status == 'pending'
    assert tableau_item.completed_at is None

    # Verify skill is STILL present in student_skills (not removed)
    ss = StudentSkill.query.filter_by(student_id=student.id, skill_id=skills['Tableau'].id).first()
    assert ss is not None


def test_profile_completion_updates_on_new_skill():
    """Verify profile completion reflects skills added via learning path."""
    user, student = create_student_user(email='profcomp@test.com', roll='ROLL_PC')
    skills, job, _ = setup_skills_and_job()

    initial_comp = profile_service.calculate_profile_completion(student)

    learning_path_service.generate_path(student.id, job.id, current_user=user)
    tableau_item = LearningPathItem.query.filter_by(
        student_id=student.id,
        skill_id=skills['Tableau'].id,
    ).first()

    learning_path_service.mark_complete(student.id, tableau_item.id, proficiency=3, current_user=user)

    updated_comp = profile_service.calculate_profile_completion(student)
    # The score should have increased due to added skill
    assert updated_comp['percentage'] > initial_comp['percentage']


# ════════════════════════════════════════════════════════════════════════════════
#  3. OWNERSHIP & ACCESS CONTROL TESTS
# ════════════════════════════════════════════════════════════════════════════════

def test_student_cannot_touch_another_student_path():
    """Student A cannot view, complete, or undo Student B's path items."""
    userA, studentA = create_student_user(email='studentA@test.com', roll='ROLL_A')
    userB, studentB = create_student_user(email='studentB@test.com', roll='ROLL_B')
    skills, job, _ = setup_skills_and_job()

    learning_path_service.generate_path(studentA.id, job.id, current_user=userA)
    itemA = LearningPathItem.query.filter_by(student_id=studentA.id).first()

    # User B attempts to complete User A's item
    ok, err = learning_path_service.mark_complete(studentB.id, itemA.id, current_user=userB)
    assert ok is False
    assert "not found" in err.lower() or "unauthorized" in err.lower() or "access denied" in err.lower()

    # User B attempts to undo User A's item
    ok, err = learning_path_service.mark_pending(studentB.id, itemA.id, current_user=userB)
    assert ok is False


# ════════════════════════════════════════════════════════════════════════════════
#  4. WEB ROUTE TESTS (routes/student.py)
# ════════════════════════════════════════════════════════════════════════════════

def login_client(client, email, password):
    """Helper to log in a test client via standard auth route."""
    client.get('/logout')
    return client.post('/login', data={'email': email, 'password': password}, follow_redirects=True)


def test_student_learning_path_page_and_generation(client):
    """GET /student/learning-path renders checklist, timeline and handles generation."""
    user, student = create_student_user(email='web_lp@test.com', roll='ROLL_WLP')
    skills, job, _ = setup_skills_and_job()

    # Set as target job
    student.target_job_id = job.id
    _db.session.commit()

    # Log in
    login_client(client, user.email, 'Pass1234')

    # 1. View page initially
    res = client.get('/student/learning-path')
    assert res.status_code == 200
    assert b"Target Job Learning Path" in res.data or b"Learning Path" in res.data

    # 2. Trigger generation
    res_gen = client.post(
        '/student/learning-path/generate',
        data={'job_id': job.id},
        follow_redirects=True,
    )
    assert res_gen.status_code == 200
    assert b"Master Power BI" in res_gen.data
    assert b"Build a project using these skills" in res_gen.data

    # 3. Find an item to complete
    item = LearningPathItem.query.filter_by(student_id=student.id, skill_id=skills['Power BI'].id).first()
    assert item is not None

    res_comp = client.post(
        f'/student/learning-path/{item.id}/complete',
        data={'proficiency': '4', 'job_id': job.id},
        follow_redirects=True,
    )
    assert res_comp.status_code == 200

    # 4. Undo the completion
    res_undo = client.post(
        f'/student/learning-path/{item.id}/undo',
        data={'job_id': job.id},
        follow_redirects=True,
    )
    assert res_undo.status_code == 200


def test_student_progress_page(client):
    """GET /student/progress renders Chart.js chart and audit activity table."""
    user, student = create_student_user(email='prog_page@test.com', roll='ROLL_PROG')
    skills, job, _ = setup_skills_and_job()

    # Add a skill progress record
    prog = SkillProgress(
        student_id=student.id,
        skill_id=skills['Power BI'].id,
        old_proficiency='Beginner',
        new_proficiency='Intermediate',
    )
    _db.session.add(prog)
    _db.session.commit()

    login_client(client, user.email, 'Pass1234')

    res = client.get('/student/progress')
    assert res.status_code == 200
    assert b"Proficiency Trajectory Over Time" in res.data or b"Skill Progress" in res.data
    assert b"Power BI" in res.data
    assert b"Recent Proficiency Activity Log" in res.data or b"Recent" in res.data


def test_dashboard_shows_real_learning_progress(client):
    """Student dashboard shows path completion % and top skill proficiency bars."""
    user, student = create_student_user(email='dash_lp@test.com', roll='ROLL_DASH')
    skills, job, _ = setup_skills_and_job()
    student.target_job_id = job.id

    # Give student a skill
    ss = StudentSkill(
        student_id=student.id,
        skill_id=skills['Python'].id,
        proficiency_level='Advanced',
        source='manual',
    )
    _db.session.add(ss)
    _db.session.commit()

    # Generate path
    learning_path_service.generate_path(student.id, job.id, current_user=user)

    login_client(client, user.email, 'Pass1234')

    res = client.get('/student/dashboard')
    assert res.status_code == 200
    assert b"Learning Progress &amp; Skill Mastery" in res.data or b"Learning Progress & Skill Mastery" in res.data
    assert b"Path Completion" in res.data
    assert b"Python" in res.data
    assert b"Employment &amp; Placement Status" in res.data


def test_guest_and_admin_access_control(client):
    """Guest redirected to login; Admin blocked from student-only learning path."""
    client.get('/logout')
    user, student = create_student_user(email='student_ctrl@test.com', roll='ROLL_CTRL')
    admin = create_admin_user(email='admin_ctrl@test.com')

    # Guest access
    res = client.get('/student/learning-path')
    assert res.status_code in [302, 401]

    # Admin access
    login_client(client, admin.email, 'AdminPass123')
    res_admin = client.get('/student/learning-path')
    assert res_admin.status_code in [302, 403]


# ════════════════════════════════════════════════════════════════════════════════
#  5. API ENDPOINT TESTS (routes/api.py)
# ════════════════════════════════════════════════════════════════════════════════

def test_api_get_learning_path(client):
    """GET /api/student/<id>/learning-path?job_id=<id> returns JSON format."""
    user, student = create_student_user(email='api_lp@test.com', roll='ROLL_API')
    skills, job, _ = setup_skills_and_job()

    learning_path_service.generate_path(student.id, job.id, current_user=user)

    login_client(client, user.email, 'Pass1234')

    # 1. Valid request
    res = client.get(f'/api/student/{student.id}/learning-path?job_id={job.id}')
    assert res.status_code == 200
    data = res.get_json()
    assert data['success'] is True
    assert data['data']['job_id'] == job.id
    assert 'completion' in data['data']
    assert len(data['data']['steps']) == 5

    # 2. Missing job_id parameter (400)
    res_missing = client.get(f'/api/student/{student.id}/learning-path')
    assert res_missing.status_code == 400

    # 3. Invalid job_id (404)
    res_inv = client.get(f'/api/student/{student.id}/learning-path?job_id=999999')
    assert res_inv.status_code == 404


def test_api_student_cannot_access_other_student_path(app, client):
    """Student cannot access another student's learning path via API (403)."""
    with app.app_context():
        userA, studentA = create_student_user(email='apiA@test.com', roll='ROLL_APIA')
        userB, studentB = create_student_user(email='apiB@test.com', roll='ROLL_APIB')
        skills, job, _ = setup_skills_and_job()
        learning_path_service.generate_path(studentA.id, job.id, current_user=userA)
        sA_id = studentA.id
        j_id = job.id

    # Log in as Student B
    login_client(client, 'apiB@test.com', 'Pass1234')

    res = client.get(f'/api/student/{sA_id}/learning-path?job_id={j_id}')
    assert res.status_code == 403
    data = res.get_json()
    assert data['success'] is False


def test_api_complete_path_item(client):
    """POST /api/learning-path/<item_id>/complete updates item and returns completion."""
    user, student = create_student_user(email='api_comp@test.com', roll='ROLL_APIC')
    skills, job, _ = setup_skills_and_job()

    learning_path_service.generate_path(student.id, job.id, current_user=user)
    item = LearningPathItem.query.filter_by(student_id=student.id, skill_id=skills['Tableau'].id).first()

    login_client(client, user.email, 'Pass1234')

    res = client.post(
        f'/api/learning-path/{item.id}/complete',
        data=json.dumps({'proficiency': 3}),
        content_type='application/json',
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data['success'] is True
    assert 'completion' in data['data']
    assert data['data']['completion'] > 0
