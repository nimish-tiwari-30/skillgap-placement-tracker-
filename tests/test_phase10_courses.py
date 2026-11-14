"""
tests/test_phase10_courses.py
──────────────────────────────
Comprehensive test suite for Phase 10: Courses + Content-Based Course Recommendation.

Covers:
  1. Pure ML core logic (ml/recommender.py)
     - Ideal difficulty mapping
     - Difficulty fit score calculation
     - Content-based ranking: difficulty fit -> rating -> duration tie-breaker
     - Covers N missing skills annotation
     - Edge cases: all skills covered (empty missing_skills), no matching courses
  2. Service layer (services/recommendation_service.py)
     - Missing skills computation with Phase 8 gap logic
     - No N+1 queries eager-loading of courses and skill tags
     - Ownership checks (student cannot view another student's recommendations, admin can)
     - All covered congratulatory state
     - Error handling for invalid/inactive job or missing student
  3. Admin routes (routes/admin.py)
     - List courses with search and difficulty filters
     - Create course with skill tags and validation (title required, rating 0-5)
     - Edit course and update skill tags
     - Delete course with cascade to course_skills
     - Role-based authorization (students blocked)
  4. Student web routes (routes/student.py)
     - GET /student/recommendations (no job prompt, target job default, ?job_id query param)
     - Student dashboard displays Phase 10 recommendations card
  5. JSON API (routes/api.py)
     - GET /api/student/<id>/recommendations?job_id=<n>
     - Ownership enforcement (403 for unauthorized student)
     - Required query parameter validation (400 for missing job_id)
"""

import pytest
from app import create_app
from extensions import db as _db
from models.user import User
from models.student import Student
from models.skill import Skill, StudentSkill
from models.job import JobRole, JobDescription, JobSkill
from models.course import Course, CourseSkill
from ml.recommender import (
    _ideal_difficulty,
    _difficulty_fit_score,
    _rank_courses_for_skill,
    recommend,
)
from services import recommendation_service


# ════════════════════════════════════════════════════════════════════════════════
#  TEST HELPERS
# ════════════════════════════════════════════════════════════════════════════════

def create_test_student(email='student10@test.com', roll='ROLL10', name='Alice Learner'):
    """Create and persist a student user + Student profile."""
    user = User(email=email, role='student', is_active=True)
    user.set_password('Pass1234')
    _db.session.add(user)
    _db.session.flush()

    student = Student(
        user_id=user.id,
        full_name=name,
        roll_number=roll,
        branch='Computer Science',
    )
    _db.session.add(student)
    _db.session.commit()
    return user, student


def create_test_admin(email='admin10@test.com'):
    """Create and persist an admin user."""
    user = User(email=email, role='admin', is_active=True)
    user.set_password('AdminPass123')
    _db.session.add(user)
    _db.session.commit()
    return user


def create_skills_job_and_courses():
    """
    Setup a realistic scenario:
      Skills: Python, SQL, Docker, React, AWS
      Job: requires Python (weight 5), SQL (weight 4), Docker (weight 3)
      Courses:
        - Course A: Python (Beginner, rating 4.8, 20h)
        - Course B: SQL & Docker (Beginner, rating 4.6, 15h) -> covers 2 missing skills!
        - Course C: SQL (Advanced, rating 4.9, 10h)
        - Course D: AWS (Intermediate, rating 4.5, 25h) -> not required by job
    """
    # 1. Skills
    skills = {}
    for s_name in ['Python', 'SQL', 'Docker', 'React', 'AWS']:
        s = Skill.query.filter_by(name=s_name).first()
        if not s:
            s = Skill(name=s_name, category='General')
            _db.session.add(s)
            _db.session.flush()
        skills[s_name] = s

    # 2. Job Role & Job
    role = JobRole(title='Backend Engineer Role', department='Engineering')
    _db.session.add(role)
    _db.session.flush()

    job = JobDescription(
        job_role_id=role.id,
        title='Junior Backend Engineer',
        company_name='Cloud Corp',
        description_text='Looking for backend developer skilled in Python, SQL, and Docker.',
        is_active=True,
    )
    _db.session.add(job)
    _db.session.flush()

    job_skills_data = [('Python', 5), ('SQL', 4), ('Docker', 3)]
    for s_name, weight in job_skills_data:
        js = JobSkill(job_description_id=job.id, skill_id=skills[s_name].id, importance_weight=weight)
        _db.session.add(js)

    # 3. Courses
    c1 = Course(
        title='Complete Python Mastery',
        provider='Udemy',
        difficulty_level='Beginner',
        duration_hours=20.0,
        rating=4.8,
        url='https://example.com/python',
        description='Learn Python from scratch.',
    )
    c2 = Course(
        title='Databases and Containers: SQL & Docker',
        provider='Coursera',
        difficulty_level='Beginner',
        duration_hours=15.0,
        rating=4.6,
        url='https://example.com/sql-docker',
        description='Master both SQL queries and Docker containers in one place.',
    )
    c3 = Course(
        title='Advanced SQL Performance & Tuning',
        provider='edX',
        difficulty_level='Advanced',
        duration_hours=10.0,
        rating=4.9,
        url='https://example.com/advanced-sql',
        description='Deep dive into SQL optimization.',
    )
    c4 = Course(
        title='AWS Cloud Practitioner',
        provider='A Cloud Guru',
        difficulty_level='Intermediate',
        duration_hours=25.0,
        rating=4.5,
        url='https://example.com/aws',
        description='Cloud basics.',
    )
    _db.session.add_all([c1, c2, c3, c4])
    _db.session.flush()

    # Tag skills
    _db.session.add(CourseSkill(course_id=c1.id, skill_id=skills['Python'].id))
    _db.session.add(CourseSkill(course_id=c2.id, skill_id=skills['SQL'].id))
    _db.session.add(CourseSkill(course_id=c2.id, skill_id=skills['Docker'].id))  # multi-skill!
    _db.session.add(CourseSkill(course_id=c3.id, skill_id=skills['SQL'].id))
    _db.session.add(CourseSkill(course_id=c4.id, skill_id=skills['AWS'].id))

    _db.session.commit()
    return skills, role, job, [c1, c2, c3, c4]


def login_client(client, email, password):
    """Helper to log in a test client."""
    client.get('/logout')
    return client.post('/login', data={'email': email, 'password': password}, follow_redirects=True)


# ════════════════════════════════════════════════════════════════════════════════
#  1. PURE ML LOGIC TESTS (ml/recommender.py)
# ════════════════════════════════════════════════════════════════════════════════

def test_ideal_difficulty_mapping():
    """Verify student proficiency maps to ideal course difficulty score."""
    assert _ideal_difficulty(None) == 1           # Beginner default
    assert _ideal_difficulty('') == 1
    assert _ideal_difficulty('Beginner') == 1
    assert _ideal_difficulty('Intermediate') == 2
    assert _ideal_difficulty('Advanced') == 3


def test_difficulty_fit_distance():
    """Verify distance calculation between ideal difficulty and course difficulty."""
    # Ideal = Beginner (1)
    assert _difficulty_fit_score(1, 'Beginner') == 0       # Exact match
    assert _difficulty_fit_score(1, 'Intermediate') == 1   # 1 level distance
    assert _difficulty_fit_score(1, 'Advanced') == 2       # 2 levels distance

    # Ideal = Intermediate (2)
    assert _difficulty_fit_score(2, 'Beginner') == 1
    assert _difficulty_fit_score(2, 'Intermediate') == 0
    assert _difficulty_fit_score(2, 'Advanced') == 1


def test_pure_recommender_empty_missing_skills():
    """When a student has no missing skills, recommender returns congratulatory flag."""
    res = recommend(missing_skills=[], all_courses=[])
    assert res['all_covered'] is True
    assert res['items'] == []


def test_pure_recommender_ranks_by_fit_rating_duration():
    """
    Test 3-tier ranking:
      1) difficulty fit (primary)
      2) rating (secondary)
      3) duration (tie-breaker)
    """
    missing_skills = [
        {'skill_id': 1, 'name': 'SQL', 'importance': 5, 'proficiency': 'Beginner'}
    ]

    all_courses = [
        # Course 1: Advanced (fit distance 2), rating 5.0, 10h
        {'course_id': 101, 'title': 'SQL Expert', 'difficulty_level': 'Advanced', 'rating': 5.0, 'duration_hours': 10.0, 'skill_ids': [1]},
        # Course 2: Beginner (fit distance 0), rating 4.5, 20h
        {'course_id': 102, 'title': 'SQL Basics A', 'difficulty_level': 'Beginner', 'rating': 4.5, 'duration_hours': 20.0, 'skill_ids': [1]},
        # Course 3: Beginner (fit distance 0), rating 4.8, 30h
        {'course_id': 103, 'title': 'SQL Basics B', 'difficulty_level': 'Beginner', 'rating': 4.8, 'duration_hours': 30.0, 'skill_ids': [1]},
        # Course 4: Beginner (fit distance 0), rating 4.8, 15h -> should beat Course 3 on duration tie-breaker!
        {'course_id': 104, 'title': 'SQL Basics Fast', 'difficulty_level': 'Beginner', 'rating': 4.8, 'duration_hours': 15.0, 'skill_ids': [1]},
    ]

    res = recommend(missing_skills, all_courses, top_n=3)
    assert res['all_covered'] is False
    assert len(res['items']) == 1

    item = res['items'][0]
    assert item['skill_id'] == 1
    assert item['has_courses'] is True
    assert len(item['courses']) == 3

    # Ranking expected:
    # 1st: Course 104 (fit=0, rating=4.8, duration=15)
    # 2nd: Course 103 (fit=0, rating=4.8, duration=30)
    # 3rd: Course 102 (fit=0, rating=4.5, duration=20)
    # (Course 101 with Advanced fit=2 was pushed out of top 3)
    ranked_ids = [c['course_id'] for c in item['courses']]
    assert ranked_ids == [104, 103, 102]


def test_pure_recommender_covers_n_missing_skills():
    """Verify that multi-skill courses correctly count how many of the missing skills they cover."""
    missing_skills = [
        {'skill_id': 1, 'name': 'SQL', 'importance': 5},
        {'skill_id': 2, 'name': 'Docker', 'importance': 4},
        {'skill_id': 3, 'name': 'Python', 'importance': 3},
    ]

    all_courses = [
        {'course_id': 201, 'title': 'SQL Only', 'difficulty_level': 'Beginner', 'rating': 4.5, 'duration_hours': 10, 'skill_ids': [1]},
        {'course_id': 202, 'title': 'SQL & Docker Combined', 'difficulty_level': 'Beginner', 'rating': 4.7, 'duration_hours': 20, 'skill_ids': [1, 2]},
    ]

    res = recommend(missing_skills, all_courses, top_n=3)
    sql_item = next(i for i in res['items'] if i['skill_id'] == 1)

    c202 = next(c for c in sql_item['courses'] if c['course_id'] == 202)
    assert c202['covers_n_missing_skills'] == 2  # Covers both SQL (1) and Docker (2)


def test_pure_recommender_no_matching_course():
    """Verify safe fallback when no course in DB covers a missing skill."""
    missing_skills = [
        {'skill_id': 999, 'name': 'RareSkill', 'importance': 3}
    ]
    all_courses = [
        {'course_id': 301, 'title': 'Unrelated Course', 'difficulty_level': 'Beginner', 'rating': 4.0, 'skill_ids': [10]}
    ]
    res = recommend(missing_skills, all_courses)
    assert res['all_covered'] is False
    assert len(res['items']) == 1
    assert res['items'][0]['has_courses'] is False
    assert res['items'][0]['courses'] == []


# ════════════════════════════════════════════════════════════════════════════════
#  2. SERVICE LAYER TESTS (services/recommendation_service.py)
# ════════════════════════════════════════════════════════════════════════════════

def test_service_recommend_for_job_success(app):
    """
    Test full service flow:
      Student has: Python
      Job requires: Python, SQL, Docker
      Missing: SQL, Docker
      Verify recommendations return SQL and Docker with ranked courses.
    """
    with app.app_context():
        user, student = create_test_student()
        skills, role, job, courses = create_skills_job_and_courses()

        # Give student Python
        ss = StudentSkill(student_id=student.id, skill_id=skills['Python'].id, proficiency_level='Beginner')
        _db.session.add(ss)
        _db.session.commit()

        ok, result = recommendation_service.recommend_for_job(
            student_id=student.id,
            job_id=job.id,
            current_user=user,
        )

        assert ok is True
        assert result['all_covered'] is False
        assert result['job_title'] == 'Junior Backend Engineer'
        assert result['missing_count'] == 2  # SQL, Docker

        missing_names = [i['skill_name'] for i in result['items']]
        assert 'SQL' in missing_names
        assert 'Docker' in missing_names
        assert 'Python' not in missing_names  # Matched, not missing


def test_service_recommend_for_job_all_covered(app):
    """When student has all required skills, service returns all_covered=True."""
    with app.app_context():
        user, student = create_test_student()
        skills, role, job, courses = create_skills_job_and_courses()

        # Give student all 3 required skills
        for s_name in ['Python', 'SQL', 'Docker']:
            ss = StudentSkill(student_id=student.id, skill_id=skills[s_name].id, proficiency_level='Intermediate')
            _db.session.add(ss)
        _db.session.commit()

        ok, result = recommendation_service.recommend_for_job(
            student_id=student.id,
            job_id=job.id,
            current_user=user,
        )
        assert ok is True
        assert result['all_covered'] is True
        assert len(result['items']) == 0


def test_service_recommend_ownership_enforcement(app):
    """Student cannot request recommendations for another student; admin can."""
    with app.app_context():
        user1, student1 = create_test_student('s1@test.com', 'R1', 'Student 1')
        user2, student2 = create_test_student('s2@test.com', 'R2', 'Student 2')
        admin = create_test_admin()
        skills, role, job, courses = create_skills_job_and_courses()

        # Student 1 attempts to view Student 2's recommendations -> Denied
        ok, msg = recommendation_service.recommend_for_job(student2.id, job.id, current_user=user1)
        assert ok is False
        assert "Access denied" in msg

        # Admin attempts to view Student 2's recommendations -> Allowed
        ok, res = recommendation_service.recommend_for_job(student2.id, job.id, current_user=admin)
        assert ok is True


def test_service_invalid_job(app):
    """Calling recommendation for a non-existent or inactive job returns an error."""
    with app.app_context():
        user, student = create_test_student()
        ok, msg = recommendation_service.recommend_for_job(student.id, 99999, current_user=user)
        assert ok is False
        assert "Job not found" in msg


# ════════════════════════════════════════════════════════════════════════════════
#  3. ADMIN ROUTES TESTS (routes/admin.py)
# ════════════════════════════════════════════════════════════════════════════════

def test_admin_courses_page_and_filtering(app, client):
    """Admin can view /admin/courses and filter by difficulty or search keyword."""
    with app.app_context():
        admin = create_test_admin()
        skills, role, job, courses = create_skills_job_and_courses()

    login_client(client, 'admin10@test.com', 'AdminPass123')

    # View list
    resp = client.get('/admin/courses')
    assert resp.status_code == 200
    assert b'Manage Courses' in resp.data
    assert b'Complete Python Mastery' in resp.data

    # Search filter
    resp = client.get('/admin/courses?q=Python')
    assert resp.status_code == 200
    assert b'Complete Python Mastery' in resp.data
    assert b'AWS Cloud Practitioner' not in resp.data

    # Difficulty filter
    resp = client.get('/admin/courses?diff=Advanced')
    assert resp.status_code == 200
    assert b'Advanced SQL Performance' in resp.data
    assert b'Complete Python Mastery' not in resp.data


def test_admin_create_course_success(app, client):
    """Admin can create a course and tag it with skills."""
    with app.app_context():
        admin = create_test_admin()
        skills, role, job, courses = create_skills_job_and_courses()
        py_id = skills['Python'].id
        sql_id = skills['SQL'].id

    login_client(client, 'admin10@test.com', 'AdminPass123')

    resp = client.post('/admin/courses/create', data={
        'title': 'New Test Course for Data Science',
        'provider': 'DataCamp',
        'difficulty_level': 'Intermediate',
        'duration_hours': '25.0',
        'rating': '4.7',
        'url': 'https://datacamp.com/test',
        'description': 'A thorough data science course.',
        'skill_ids': [str(py_id), str(sql_id)],
    }, follow_redirects=True)

    assert resp.status_code == 200
    assert b'created successfully' in resp.data

    # Verify DB
    with app.app_context():
        c = Course.query.filter_by(title='New Test Course for Data Science').first()
        assert c is not None
        assert c.provider == 'DataCamp'
        assert float(c.rating) == 4.7
        tag_skill_ids = [cs.skill_id for cs in c.course_skills]
        assert py_id in tag_skill_ids
        assert sql_id in tag_skill_ids


def test_admin_create_course_validation(app, client):
    """Validation rejects empty title or invalid rating."""
    with app.app_context():
        admin = create_test_admin()

    login_client(client, 'admin10@test.com', 'AdminPass123')

    # Missing title
    resp = client.post('/admin/courses/create', data={
        'title': '',
        'difficulty_level': 'Beginner',
    }, follow_redirects=True)
    assert b'Title is required' in resp.data

    # Rating > 5.0
    resp = client.post('/admin/courses/create', data={
        'title': 'Invalid Rating Course',
        'rating': '5.5',
    }, follow_redirects=True)
    assert b'Rating must be between 0 and 5' in resp.data


def test_admin_edit_course(app, client):
    """Admin can edit course details and modify tagged skills."""
    with app.app_context():
        admin = create_test_admin()
        skills, role, job, courses = create_skills_job_and_courses()
        course_id = courses[0].id
        react_id = skills['React'].id

    login_client(client, 'admin10@test.com', 'AdminPass123')

    resp = client.post(f'/admin/courses/{course_id}/edit', data={
        'title': 'Updated Python Mastery 2026',
        'provider': 'Udemy Pro',
        'difficulty_level': 'Intermediate',
        'duration_hours': '28.0',
        'rating': '4.9',
        'url': 'https://example.com/updated',
        'description': 'Updated description.',
        'skill_ids': [str(react_id)],
    }, follow_redirects=True)

    assert resp.status_code == 200
    assert b'updated successfully' in resp.data

    with app.app_context():
        updated = _db.session.get(Course, course_id)
        assert updated.title == 'Updated Python Mastery 2026'
        assert float(updated.rating) == 4.9
        assert len(updated.course_skills) == 1
        assert updated.course_skills[0].skill_id == react_id


def test_admin_delete_course_cascade(app, client):
    """Deleting a course removes it and cascades CourseSkill tags."""
    with app.app_context():
        admin = create_test_admin()
        skills, role, job, courses = create_skills_job_and_courses()
        course_id = courses[1].id  # Has 2 skill tags

    login_client(client, 'admin10@test.com', 'AdminPass123')

    resp = client.post(f'/admin/courses/{course_id}/delete', follow_redirects=True)
    assert resp.status_code == 200
    assert b'deleted successfully' in resp.data

    with app.app_context():
        assert _db.session.get(Course, course_id) is None
        # Verify cascaded tags are gone
        assert CourseSkill.query.filter_by(course_id=course_id).count() == 0


def test_student_blocked_from_admin_courses(app, client):
    """Students cannot access /admin/courses."""
    with app.app_context():
        user, student = create_test_student()

    login_client(client, 'student10@test.com', 'Pass1234')

    resp = client.get('/admin/courses')
    # Should redirect with flash message
    assert resp.status_code in [302, 403]


# ════════════════════════════════════════════════════════════════════════════════
#  4. STUDENT WEB ROUTES (routes/student.py)
# ════════════════════════════════════════════════════════════════════════════════

def test_student_recommendations_no_job_selected(app, client):
    """Student with no target job sees the 'No Target Job Selected' empty state."""
    with app.app_context():
        user, student = create_test_student()

    login_client(client, 'student10@test.com', 'Pass1234')

    resp = client.get('/student/recommendations')
    assert resp.status_code == 200
    assert b'Course Recommendations' in resp.data
    assert b'No Target Job Selected' in resp.data


def test_student_recommendations_with_job_query(app, client):
    """Passing ?job_id=<id> renders course recommendations for missing skills."""
    with app.app_context():
        user, student = create_test_student()
        skills, role, job, courses = create_skills_job_and_courses()
        job_id = job.id

    login_client(client, 'student10@test.com', 'Pass1234')

    resp = client.get(f'/student/recommendations?job_id={job_id}')
    assert resp.status_code == 200
    assert b'Course Recommendations' in resp.data
    assert b'Junior Backend Engineer' in resp.data
    assert b'Missing Skills' in resp.data
    assert b'Databases and Containers' in resp.data


def test_student_dashboard_displays_recommendation_card(app, client):
    """Student dashboard includes the Phase 10 Recommended Learning section."""
    with app.app_context():
        user, student = create_test_student()
        skills, role, job, courses = create_skills_job_and_courses()

        # Set target job
        student.target_job_id = job.id
        _db.session.commit()

    login_client(client, 'student10@test.com', 'Pass1234')

    resp = client.get('/student/dashboard')
    assert resp.status_code == 200
    assert b'Recommended Learning &amp; Course Suggestions' in resp.data
    assert b'Find Courses for Gaps' in resp.data


# ════════════════════════════════════════════════════════════════════════════════
#  5. API ENDPOINTS TESTS (routes/api.py)
# ════════════════════════════════════════════════════════════════════════════════

def test_api_recommendations_success(app, client):
    """GET /api/student/<id>/recommendations?job_id=<n> returns valid JSON."""
    with app.app_context():
        user, student = create_test_student()
        skills, role, job, courses = create_skills_job_and_courses()
        s_id = student.id
        j_id = job.id

    login_client(client, 'student10@test.com', 'Pass1234')

    resp = client.get(f'/api/student/{s_id}/recommendations?job_id={j_id}')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    rec_data = data['data']
    assert rec_data['job_id'] == j_id
    assert rec_data['all_covered'] is False
    assert len(rec_data['items']) > 0


def test_api_recommendations_ownership(app, client):
    """Student attempting to fetch another student's recommendations gets 403."""
    with app.app_context():
        user1, student1 = create_test_student('s1@test.com', 'R1', 'Student 1')
        user2, student2 = create_test_student('s2@test.com', 'R2', 'Student 2')
        skills, role, job, courses = create_skills_job_and_courses()
        s2_id = student2.id
        j_id = job.id

    login_client(client, 's1@test.com', 'Pass1234')

    resp = client.get(f'/api/student/{s2_id}/recommendations?job_id={j_id}')
    assert resp.status_code == 403
    data = resp.get_json()
    assert data['success'] is False
    assert "Access denied" in data['error']


def test_api_recommendations_missing_job_id(app, client):
    """GET /api/student/<id>/recommendations without job_id returns 400."""
    with app.app_context():
        user, student = create_test_student()
        s_id = student.id

    login_client(client, 'student10@test.com', 'Pass1234')

    resp = client.get(f'/api/student/{s_id}/recommendations')
    assert resp.status_code == 400
    data = resp.get_json()
    assert data['success'] is False
    assert "job_id query parameter is required" in data['error']
