"""
tests/test_skill_gap.py
───────────────────────
Comprehensive test suite for Phase 8: Skill-Gap Analysis.

Covers:
  1. Pure ML core logic worked examples and mathematical correctness
     - 50.0% worked example (Python, SQL, Excel vs 6 required skills)
     - Hand-calculated weighted percentage example
     - Edge cases: zero required skills, zero student skills, 100% full match, 0% no overlap
     - Missing skills ordering by importance descending
  2. Service layer (services/gap_service.py)
     - Atomic saving of SkillGapAnalysis + GapSkill rows
     - History creation upon re-running analysis
     - Target job setting and profile completion update
     - Ownership enforcement
  3. Student web routes (routes/student.py)
     - Guest redirect on unauthenticated access
     - Admin access restriction on student-only routes
     - Skill gap page rendering with summary cards, table, charts, and history
     - Dashboard displaying target job and latest match %
  4. JSON API (routes/api.py)
     - POST /api/skill-gap format and validation
     - GET /api/student/<id>/skill-gap/latest ownership and admin access
"""

import pytest
from app import create_app
from extensions import db as _db
from models.user import User
from models.student import Student, SkillProgress
from models.skill import Skill, StudentSkill
from models.job import JobRole, JobDescription, JobSkill
from models.gap import SkillGapAnalysis, GapSkill
from ml.skill_gap import calculate_skill_gap
from services import gap_service, profile_service


# ════════════════════════════════════════════════════════════════════════════════
#  1. PURE LOGIC TESTS (ml/skill_gap.py)
# ════════════════════════════════════════════════════════════════════════════════

def test_ml_worked_example_50_percent():
    """
    Worked example from prompt:
      Student has {Python, SQL, Excel}
      Job requires {Python, SQL, Excel, Power BI, Statistics, Tableau}
      Expected: Coverage = 50.0%, Matched = 3, Missing = exactly {Power BI, Statistics, Tableau}
    """
    student_skills = {'Python', 'SQL', 'Excel'}
    required_skills = {'Python', 'SQL', 'Excel', 'Power BI', 'Statistics', 'Tableau'}

    res = calculate_skill_gap(student_skills, required_skills)

    assert res['coverage_pct'] == 50.0
    assert res['matched_count'] == 3
    assert set(res['matched']) == {'Python', 'SQL', 'Excel'}
    assert res['missing_count'] == 3
    assert set(res['missing']) == {'Power BI', 'Statistics', 'Tableau'}
    assert res['extra_count'] == 0
    assert res['zero_required'] is False


def test_ml_weighted_example_hand_calculated():
    """
    Importance-weighted test with known values:
      Required skills:
        Python: 5
        SQL: 4
        Excel: 3
        Power BI: 4
        Statistics: 3
        Tableau: 2
      Sum of all required importance = 5 + 4 + 3 + 4 + 3 + 2 = 21

      Student has {Python, SQL, Excel}:
        Sum of matched importance = 5 + 4 + 3 = 12

      Hand calculation:
        Weighted % = (12 / 21) * 100 = 57.142857...
        Rounded to 1 decimal place = 57.1%
    """
    student_skills = {'Python', 'SQL', 'Excel'}
    required_skills = {
        'Python': 5,
        'SQL': 4,
        'Excel': 3,
        'Power BI': 4,
        'Statistics': 3,
        'Tableau': 2,
    }

    res = calculate_skill_gap(student_skills, required_skills)

    assert res['coverage_pct'] == 50.0
    assert res['weighted_pct'] == 57.1
    assert res['matched_count'] == 3
    assert res['missing_count'] == 3


def test_ml_edge_cases():
    """
    Test zero required skills, zero student skills, 100% full match, and 0% no overlap.
    """
    # 1. Zero required skills (Edge case: must not divide by zero)
    res_zero_req = calculate_skill_gap({'Python', 'SQL'}, {})
    assert res_zero_req['coverage_pct'] == 0.0
    assert res_zero_req['weighted_pct'] == 0.0
    assert res_zero_req['zero_required'] is True
    assert res_zero_req['matched_count'] == 0
    assert res_zero_req['missing_count'] == 0
    assert res_zero_req['extra_count'] == 2

    # 2. Zero student skills
    res_zero_student = calculate_skill_gap(set(), {'Python': 5, 'Java': 4})
    assert res_zero_student['coverage_pct'] == 0.0
    assert res_zero_student['weighted_pct'] == 0.0
    assert res_zero_student['matched_count'] == 0
    assert res_zero_student['missing_count'] == 2
    assert res_zero_student['extra_count'] == 0

    # 3. 100% Full match
    full_skills = {'Python': 5, 'Docker': 4, 'AWS': 3}
    res_full = calculate_skill_gap(full_skills, full_skills)
    assert res_full['coverage_pct'] == 100.0
    assert res_full['weighted_pct'] == 100.0
    assert res_full['matched_count'] == 3
    assert res_full['missing_count'] == 0
    assert res_full['extra_count'] == 0

    # 4. No overlap (0%)
    res_no_overlap = calculate_skill_gap({'C++', 'Rust'}, {'Python': 5, 'Java': 4})
    assert res_no_overlap['coverage_pct'] == 0.0
    assert res_no_overlap['weighted_pct'] == 0.0
    assert res_no_overlap['matched_count'] == 0
    assert res_no_overlap['missing_count'] == 2
    assert res_no_overlap['extra_count'] == 2


def test_ml_missing_sorted_by_importance_descending():
    """
    Ensure missing skills are returned strictly ordered by importance descending.
    """
    student_skills = {'Git'}
    required_skills = {
        'LowPriority': 1,
        'CriticalMustHave': 5,
        'MediumSkill': 3,
        'HighSkill': 4,
    }

    res = calculate_skill_gap(student_skills, required_skills)

    assert res['missing'] == ['CriticalMustHave', 'HighSkill', 'MediumSkill', 'LowPriority']
    assert res['missing_details'][0]['importance'] == 5
    assert res['missing_details'][1]['importance'] == 4
    assert res['missing_details'][2]['importance'] == 3
    assert res['missing_details'][3]['importance'] == 1


# ════════════════════════════════════════════════════════════════════════════════
#  FIXTURES & HELPERS FOR INTEGRATION TESTS
# ════════════════════════════════════════════════════════════════════════════════

def create_test_student(email='student1@test.com', roll='22CS101', name='Alice Student'):
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


def create_test_admin(email='admin@test.com'):
    user = User(email=email, role='admin', is_active=True)
    user.set_password('AdminPass123')
    _db.session.add(user)
    _db.session.commit()
    return user


def create_skills_and_job():
    """Create master skills and an active job description with job_skills."""
    role = JobRole(title='Data Analyst Specialist', department='Analytics')
    _db.session.add(role)
    _db.session.flush()

    job = JobDescription(
        job_role_id=role.id,
        title='Junior Data Analyst',
        company_name='Acme Analytics Corp',
        description_text='Looking for junior data analyst skilled in Python, SQL, and Excel.',
        min_experience='0-1 years',
        location='Remote',
        is_active=True,
    )
    _db.session.add(job)
    _db.session.flush()

    skill_names = ['Python', 'SQL', 'Excel', 'Power BI', 'Statistics', 'Tableau', 'Docker']
    skills_map = {}
    for name in skill_names:
        s = Skill.query.filter_by(name=name).first()
        if not s:
            s = Skill(name=name, category='Analytics')
            _db.session.add(s)
            _db.session.flush()
        skills_map[name] = s

    # Assign 6 required skills to job with varying importance
    importances = {
        'Python': 5,
        'SQL': 4,
        'Excel': 3,
        'Power BI': 4,
        'Statistics': 3,
        'Tableau': 2,
    }
    for s_name, imp in importances.items():
        js = JobSkill(job_description_id=job.id, skill_id=skills_map[s_name].id, importance_weight=imp)
        _db.session.add(js)

    _db.session.commit()
    return role, job, skills_map


def login_client(client, email, password):
    client.get('/logout')
    return client.post('/login', data={'email': email, 'password': password})


# ════════════════════════════════════════════════════════════════════════════════
#  2. SERVICE LAYER TESTS (services/gap_service.py)
# ════════════════════════════════════════════════════════════════════════════════

def test_service_analyze_and_atomic_save(app):
    """
    Test that analyze() performs gap calculation and saves SkillGapAnalysis + GapSkill rows
    atomically in the database.
    """
    with app.app_context():
        user, student = create_test_student()
        role, job, skills_map = create_skills_and_job()

        # Give student {Python, SQL, Excel, Docker} (Docker is extra)
        for s_name in ['Python', 'SQL', 'Excel', 'Docker']:
            ss = StudentSkill(student_id=student.id, skill_id=skills_map[s_name].id, proficiency_level='Intermediate')
            _db.session.add(ss)
        _db.session.commit()

        ok, analysis, details = gap_service.analyze(student.id, job.id, current_user=user)

        assert ok is True
        assert analysis.id is not None
        assert float(analysis.unweighted_coverage_pct) == 50.0
        assert float(analysis.weighted_coverage_pct) == 57.1
        assert analysis.job_description_id == job.id
        assert analysis.job_role_id == role.id

        # Verify gap_skills rows saved in DB
        gap_rows = GapSkill.query.filter_by(analysis_id=analysis.id).all()
        matched_rows = [g for g in gap_rows if g.status == 'Matched']
        missing_rows = [g for g in gap_rows if g.status == 'Missing']
        extra_rows = [g for g in gap_rows if g.status == 'Extra']

        assert len(matched_rows) == 3
        assert len(missing_rows) == 3
        assert len(extra_rows) == 1

        matched_skill_ids = {g.skill_id for g in matched_rows}
        assert matched_skill_ids == {skills_map['Python'].id, skills_map['SQL'].id, skills_map['Excel'].id}

        extra_skill_ids = {g.skill_id for g in extra_rows}
        assert extra_skill_ids == {skills_map['Docker'].id}


def test_service_rerun_creates_new_history_row(app):
    """
    Re-running gap analysis creates a new snapshot row in skill_gap_analysis
    so history is preserved over time.
    """
    with app.app_context():
        user, student = create_test_student()
        role, job, skills_map = create_skills_and_job()

        # Run 1: Student has 0 skills
        ok1, a1, _ = gap_service.analyze(student.id, job.id, current_user=user)
        assert ok1 is True
        assert float(a1.unweighted_coverage_pct) == 0.0

        # Student learns Python & SQL
        ss1 = StudentSkill(student_id=student.id, skill_id=skills_map['Python'].id, proficiency_level='Beginner')
        ss2 = StudentSkill(student_id=student.id, skill_id=skills_map['SQL'].id, proficiency_level='Beginner')
        _db.session.add_all([ss1, ss2])
        _db.session.commit()

        # Run 2: Re-run analysis
        ok2, a2, _ = gap_service.analyze(student.id, job.id, current_user=user)
        assert ok2 is True
        assert a2.id != a1.id
        assert float(a2.unweighted_coverage_pct) > 0.0

        # Verify history
        history = gap_service.get_history(student.id, job.id, current_user=user)
        assert len(history) == 2
        assert history[0].id == a2.id  # Latest first
        assert history[1].id == a1.id


def test_service_set_target_job_and_profile_completion(app):
    """
    Student can set a target job; this updates profile completion % to count target role.
    """
    with app.app_context():
        user, student = create_test_student()
        role, job, skills_map = create_skills_and_job()

        # Initial profile completion
        init_comp = profile_service.calculate_profile_completion(student)
        init_pct = init_comp['percentage']

        # Set target job
        ok, err = gap_service.set_target_job(student.id, job.id, current_user=user)
        assert ok is True
        assert err is None

        # Reload student and check target_job_id
        student_reloaded = _db.session.get(Student, student.id)
        assert student_reloaded.target_job_id == job.id

        # Profile completion should now include target role bonus (10 pts)
        new_comp = profile_service.calculate_profile_completion(student_reloaded)
        assert new_comp['percentage'] == init_pct + 10


def test_service_ownership_enforcement(app):
    """
    Student cannot analyze or view another student's gap analysis.
    """
    with app.app_context():
        user1, student1 = create_test_student('s1@test.com', 'ROLL1', 'Student One')
        user2, student2 = create_test_student('s2@test.com', 'ROLL2', 'Student Two')
        role, job, skills_map = create_skills_and_job()

        # Student 1 attempts to analyze Student 2's profile -> Blocked
        ok, msg, _ = gap_service.analyze(student2.id, job.id, current_user=user1)
        assert ok is False
        assert "Access denied" in msg

        # Student 1 attempts to view Student 2's history -> Returns empty
        hist = gap_service.get_history(student2.id, current_user=user1)
        assert hist == []


# ════════════════════════════════════════════════════════════════════════════════
#  3. WEB ROUTE TESTS (routes/student.py)
# ════════════════════════════════════════════════════════════════════════════════

def test_web_guest_redirected(client, app):
    """Unauthenticated guest attempting to access /student/skill-gap is redirected to login."""
    client.get('/logout')
    res = client.get('/student/skill-gap')
    assert res.status_code == 302
    assert '/login' in res.headers.get('Location', '')


def test_web_admin_blocked_from_student_skill_gap(client, app):
    """Admin cannot access student-only skill-gap page (gets 403 Forbidden)."""
    with app.app_context():
        admin = create_test_admin()
    login_client(client, 'admin@test.com', 'AdminPass123')

    res = client.get('/student/skill-gap')
    assert res.status_code == 403


def test_web_student_skill_gap_page_and_flow(client, app):
    """
    Student can access /student/skill-gap, run analysis via POST,
    and see coverage %, weighted %, comparison table, progress bar, and charts.
    """
    with app.app_context():
        user, student = create_test_student()
        role, job, skills_map = create_skills_and_job()

        # Student has {Python, SQL, Excel}
        for s_name in ['Python', 'SQL', 'Excel']:
            ss = StudentSkill(student_id=student.id, skill_id=skills_map[s_name].id, proficiency_level='Intermediate')
            _db.session.add(ss)
        _db.session.commit()
        job_id = job.id

    # Login student
    login_client(client, 'student1@test.com', 'Pass1234')

    # 1. GET page without job selected
    get_res = client.get('/student/skill-gap')
    assert get_res.status_code == 200
    assert b"Skill Gap Analysis" in get_res.data
    assert b"Junior Data Analyst" in get_res.data

    # 2. POST analyze job
    post_res = client.post('/student/skill-gap', data={
        'job_id': job_id,
        'set_target': '1'
    }, follow_redirects=True)

    assert post_res.status_code == 200
    html = post_res.data.decode('utf-8')

    # Coverage % (50.0%) and Weighted % (57.1%) displayed
    assert "50.0%" in html
    assert "57.1%" in html

    # Matched & Missing counts
    assert "Matched Skills" in html
    assert "Missing Skills" in html

    # Explanation line under cards
    assert "Coverage %" in html
    assert "Weighted %" in html

    # Comparison matrix table
    assert "Python" in html
    assert "Power BI" in html
    assert "Tableau" in html
    assert "Matched" in html
    assert "Missing" in html

    # Charts present
    assert "gapDoughnutChart" in html
    assert "competencyBarChart" in html


def test_web_dashboard_displays_target_job_and_match(client, app):
    """
    Student dashboard renders target job, match percentage, and matched/missing counts.
    """
    with app.app_context():
        user, student = create_test_student('dash@test.com', 'ROLLDASH', 'Dash Student')
        role, job, skills_map = create_skills_and_job()

        # Add Python and set as target job
        ss = StudentSkill(student_id=student.id, skill_id=skills_map['Python'].id, proficiency_level='Beginner')
        _db.session.add(ss)
        student.target_job_id = job.id
        _db.session.commit()

        # Run analysis once
        gap_service.analyze(student.id, job.id, current_user=user)

    login_client(client, 'dash@test.com', 'Pass1234')
    res = client.get('/student/dashboard')
    assert res.status_code == 200

    html = res.data.decode('utf-8')
    assert "Junior Data Analyst" in html
    assert "Acme Analytics Corp" in html
    assert "Skill Match Coverage" in html
    assert "Matched Skills" in html
    assert "Missing Skills" in html


# ════════════════════════════════════════════════════════════════════════════════
#  4. JSON API TESTS (routes/api.py)
# ════════════════════════════════════════════════════════════════════════════════

def test_api_post_skill_gap_success(client, app):
    """
    POST /api/skill-gap returns structured JSON matching expected schema.
    """
    with app.app_context():
        user, student = create_test_student('api1@test.com', 'ROLLAPI1', 'API Student')
        role, job, skills_map = create_skills_and_job()

        for s_name in ['Python', 'SQL', 'Excel']:
            ss = StudentSkill(student_id=student.id, skill_id=skills_map[s_name].id, proficiency_level='Intermediate')
            _db.session.add(ss)
        _db.session.commit()
        job_id = job.id

    login_client(client, 'api1@test.com', 'Pass1234')

    res = client.post('/api/skill-gap', json={'job_id': job_id})
    assert res.status_code == 200
    json_data = res.get_json()

    assert json_data['success'] is True
    data = json_data['data']
    assert data['coverage'] == 50.0
    assert data['weighted'] == 57.1
    assert set(data['matched']) == {'Python', 'SQL', 'Excel'}
    assert set(data['missing']) == {'Power BI', 'Statistics', 'Tableau'}
    assert data['matched_count'] == 3
    assert data['missing_count'] == 3


def test_api_post_skill_gap_validation_errors(client, app):
    """
    POST /api/skill-gap returns 400 on missing or invalid job_id, and 404 for non-existent job.
    """
    with app.app_context():
        user, student = create_test_student('api_err@test.com', 'ROLLERR', 'API Error Student')

    login_client(client, 'api_err@test.com', 'Pass1234')

    # Missing job_id
    res_missing = client.post('/api/skill-gap', json={})
    assert res_missing.status_code == 400
    assert res_missing.get_json()['success'] is False

    # Invalid job_id
    res_invalid = client.post('/api/skill-gap', json={'job_id': 'abc'})
    assert res_invalid.status_code == 400
    assert res_invalid.get_json()['success'] is False

    # Non-existent job_id
    res_404 = client.post('/api/skill-gap', json={'job_id': 99999})
    assert res_404.status_code == 404
    assert res_404.get_json()['success'] is False


def test_api_latest_skill_gap_ownership_and_admin(client, app):
    """
    GET /api/student/<id>/skill-gap/latest:
      - Student can get their own latest analysis
      - Student cannot view another student's latest analysis (403)
      - Admin can view any student's latest analysis
    """
    with app.app_context():
        user1, student1 = create_test_student('s_owner1@test.com', 'ROLLOWN1', 'Owner 1')
        user2, student2 = create_test_student('s_owner2@test.com', 'ROLLOWN2', 'Owner 2')
        admin = create_test_admin('admin_api@test.com')
        role, job, skills_map = create_skills_and_job()

        # Run analysis for student 1
        gap_service.analyze(student1.id, job.id, current_user=user1)
        s1_id = student1.id
        s2_id = student2.id

    # 1. Student 1 requests own analysis -> 200
    login_client(client, 's_owner1@test.com', 'Pass1234')
    res1 = client.get(f'/api/student/{s1_id}/skill-gap/latest')
    assert res1.status_code == 200
    assert res1.get_json()['success'] is True
    assert res1.get_json()['data']['coverage'] == 0.0  # 0 skills

    # 2. Student 1 attempts to view Student 2's analysis -> 403 Forbidden
    res_forbidden = client.get(f'/api/student/{s2_id}/skill-gap/latest')
    assert res_forbidden.status_code == 403
    assert res_forbidden.get_json()['success'] is False

    # 3. Admin can view Student 1's analysis -> 200
    login_client(client, 'admin_api@test.com', 'AdminPass123')
    res_admin = client.get(f'/api/student/{s1_id}/skill-gap/latest')
    assert res_admin.status_code == 200
    assert res_admin.get_json()['success'] is True
    assert res_admin.get_json()['data']['job_id'] == job.id
