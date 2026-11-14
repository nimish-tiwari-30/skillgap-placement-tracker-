"""
tests/test_analytics.py
────────────────────────
Comprehensive test suite for Phase 13: Analytics Dashboard & Personal Analytics.
Covers:
1. Empty database behavior (safe values, no NaN, no division by zero)
2. Hand-calculated 10-student dataset with exact expected values for KPIs,
   placement %, salary stats, salary bins, branch-wise placement,
   most demanded skills, and deduplicated most missing skills
3. Branch and graduation year filter mechanics
4. Admin Dashboard API (/api/dashboard/stats) permissions, validation & structure
5. Student Personal Analytics (/student/analytics and /api/student/<id>/analytics)
   ownership enforcement
6. Admin Dashboard web view rendering, canvas elements, demo banner,
   and formula-injection-safe CSV export
"""

from datetime import date, datetime, timedelta
import io
import pytest
from flask import json
from extensions import db as _db
from models.user import User
from models.student import Student, SkillProgress
from models.skill import Skill, StudentSkill
from models.job import JobRole, JobDescription, JobSkill
from models.gap import SkillGapAnalysis, GapSkill
from models.course import LearningPathItem
from models.outcome import EmploymentOutcome
from services import analytics_service


# ════════════════════════════════════════════════════════════════════════════════
#  FIXTURES & HELPERS
# ════════════════════════════════════════════════════════════════════════════════

def create_user_student(email, roll, name, branch, year=2025, cgpa=8.0):
    """Helper to create and commit user + student records."""
    user = User(email=email.strip().lower(), role='student', is_active=True)
    user.set_password('Pass1234')
    _db.session.add(user)
    _db.session.flush()

    student = Student(
        user_id=user.id,
        full_name=name,
        roll_number=roll,
        branch=branch,
        graduation_year=year,
        cgpa=cgpa,
    )
    _db.session.add(student)
    _db.session.commit()
    return user, student


def create_admin_user(email='admin_p13@test.com'):
    """Helper to create and commit an admin user."""
    user = User(email=email.strip().lower(), role='admin', is_active=True)
    user.set_password('AdminPass123')
    _db.session.add(user)
    _db.session.commit()
    return user


def login_client(client, email, password):
    """Log in client session."""
    client.get('/logout')
    return client.post('/login', data={'email': email.strip().lower(), 'password': password}, follow_redirects=True)


# ════════════════════════════════════════════════════════════════════════════════
#  1. EMPTY DATABASE TESTS
# ════════════════════════════════════════════════════════════════════════════════

def test_analytics_empty_database_safe():
    """All analytics functions must return safe non-crashing values on an empty database."""
    # 1. Placement summary
    ps = analytics_service.placement_summary()
    assert ps['total_students'] == 0
    assert ps['placed_count'] == 0
    assert ps['placement_pct'] == 0.0
    assert ps['chart_data']['values'] == [0, 0, 0, 0]

    # 2. Salary stats
    ss = analytics_service.salary_stats()
    assert ss['average'] is None
    assert ss['median'] is None
    assert ss['average_display'] == 'N/A'
    assert ss['median_display'] == 'N/A'
    assert len(ss['bins']) == 5
    for b in ss['bins']:
        assert b['count'] == 0

    # 3. Roles and branches
    assert analytics_service.average_salary_by_role() == []
    assert analytics_service.job_role_distribution() == []
    assert analytics_service.branch_wise_placement() == []
    assert analytics_service.most_demanded_skills() == []
    assert analytics_service.most_missing_skills() == []

    # 4. Match score and improvement
    ms = analytics_service.average_match_score()
    assert ms['average_match'] is None
    assert ms['average_match_display'] == 'N/A'

    imp = analytics_service.skill_improvement_over_time()
    assert imp['timeline'] == []
    assert imp['chart_labels'] == []

    # 5. Full dashboard aggregator
    dash = analytics_service.get_dashboard_analytics()
    assert dash['kpis']['total_students'] == 0
    assert dash['kpis']['placed_count'] == 0
    assert dash['kpis']['placement_pct'] == 0.0
    assert dash['kpis']['avg_salary_display'] == 'N/A'
    assert dash['kpis']['median_salary_display'] == 'N/A'
    assert dash['kpis']['avg_match_score_display'] == 'N/A'

    # 6. Student personal analytics on non-existent student
    assert analytics_service.get_student_personal_analytics(99999) is None

    # 7. CSV Export
    csv_text = analytics_service.export_dashboard_csv()
    assert "SECTION 1: KEY PERFORMANCE INDICATORS" in csv_text
    assert "Total Students,0" in csv_text


# ════════════════════════════════════════════════════════════════════════════════
#  2. HAND-CALCULATED DATASET TEST (10 STUDENTS)
# ════════════════════════════════════════════════════════════════════════════════

def test_hand_calculated_analytics():
    """
    Construct an exact 10-student cohort with known figures:
    - 6 CSE (4 in 2025, 2 in 2024), 4 ECE (2 in 2025, 2 in 2024)
    - 5 Placed:
        Student 1: CSE, 2025, "Software Engineer", 10.0 LPA
        Student 2: CSE, 2025, "Software Engineer", 6.0 LPA
        Student 3: CSE, 2024, "Data Analyst", 8.0 LPA
        Student 4: ECE, 2025, "Embedded Engineer", 12.0 LPA
        Student 5: ECE, 2024, "Data Analyst", 4.0 LPA
    - 3 In Progress: Students 6, 7 (CSE), Student 8 (ECE)
    - 2 Not Placed: Student 9 (CSE), Student 10 (ECE)

    Hand calculations:
    - Total students = 10, Placed = 5 -> Placement % = 50.0%
    - Salaries: [4.0, 6.0, 8.0, 10.0, 12.0]
      Mean = 40.0 / 5 = 8.00 LPA
      Median = 8.00 LPA
      Min = 4.00 LPA, Max = 12.00 LPA
    - Bins:
      0-3 LPA: 0
      3-5 LPA: 1 (4.0)
      5-8 LPA: 1 (6.0)
      8-12 LPA: 2 (8.0, 10.0)
      12+ LPA: 1 (12.0)
    - Branch-wise:
      CSE: 6 total, 3 placed -> 50.0%
      ECE: 4 total, 2 placed -> 50.0%
    - Salary by Role:
      "Software Engineer": count=2, avg=8.00 LPA
      "Data Analyst": count=2, avg=6.00 LPA
      "Embedded Engineer": count=1, avg=12.00 LPA
    - Role Distribution:
      "Software Engineer": 2 (40.0%)
      "Data Analyst": 2 (40.0%)
      "Embedded Engineer": 1 (20.0%)
    """
    # 1. Create Skills
    skills = {}
    for s_name in ['Python', 'SQL', 'Docker', 'React']:
        s = Skill.query.filter_by(name=s_name).first()
        if not s:
            s = Skill(name=s_name, category='Tech')
            _db.session.add(s)
            _db.session.flush()
        skills[s_name] = s

    # 2. Create Job Descriptions & JobSkills
    role_se = JobRole.query.filter_by(title='Software Engineer').first()
    if not role_se:
        role_se = JobRole(title='Software Engineer', department='Engineering')
        _db.session.add(role_se)
        _db.session.flush()

    role_da = JobRole.query.filter_by(title='Data Analyst').first()
    if not role_da:
        role_da = JobRole(title='Data Analyst', department='Analytics')
        _db.session.add(role_da)
        _db.session.flush()

    jd1 = JobDescription(job_role_id=role_se.id, title='Backend Dev', company_name='A', description_text='desc1', is_active=True)
    jd2 = JobDescription(job_role_id=role_se.id, title='Fullstack Dev', company_name='B', description_text='desc2', is_active=True)
    jd3 = JobDescription(job_role_id=role_da.id, title='BI Analyst', company_name='C', description_text='desc3', is_active=True)
    _db.session.add_all([jd1, jd2, jd3])
    _db.session.flush()

    # JD1: Python(5), SQL(4)
    # JD2: Python(4), Docker(3)
    # JD3: Python(5), React(2)
    # Demand: Python (3 jobs, weight=14), SQL (1 job, 4), Docker (1 job, 3), React (1 job, 2)
    _db.session.add_all([
        JobSkill(job_description_id=jd1.id, skill_id=skills['Python'].id, importance_weight=5),
        JobSkill(job_description_id=jd1.id, skill_id=skills['SQL'].id, importance_weight=4),
        JobSkill(job_description_id=jd2.id, skill_id=skills['Python'].id, importance_weight=4),
        JobSkill(job_description_id=jd2.id, skill_id=skills['Docker'].id, importance_weight=3),
        JobSkill(job_description_id=jd3.id, skill_id=skills['Python'].id, importance_weight=5),
        JobSkill(job_description_id=jd3.id, skill_id=skills['React'].id, importance_weight=2),
    ])

    # 3. Create 10 Students & Outcomes
    students = []
    # (email, roll, name, branch, year, status, role, salary)
    student_specs = [
        ('s1@test.com', 'R01', 'Student 1', 'Computer Science', 2025, 'Placed', 'Software Engineer', 10.0),
        ('s2@test.com', 'R02', 'Student 2', 'Computer Science', 2025, 'Placed', 'Software Engineer', 6.0),
        ('s3@test.com', 'R03', 'Student 3', 'Computer Science', 2024, 'Placed', 'Data Analyst', 8.0),
        ('s4@test.com', 'R04', 'Student 4', 'Electronics', 2025, 'Placed', 'Embedded Engineer', 12.0),
        ('s5@test.com', 'R05', 'Student 5', 'Electronics', 2024, 'Placed', 'Data Analyst', 4.0),
        ('s6@test.com', 'R06', 'Student 6', 'Computer Science', 2025, 'In Progress', None, None),
        ('s7@test.com', 'R07', 'Student 7', 'Computer Science', 2025, 'In Progress', None, None),
        ('s8@test.com', 'R08', 'Student 8', 'Electronics', 2025, 'In Progress', None, None),
        ('s9@test.com', 'R09', 'Student 9', 'Computer Science', 2024, 'Not Placed', None, None),
        ('s10@test.com', 'R10', 'Student 10', 'Electronics', 2024, 'Not Placed', None, None),
    ]

    for email, roll, name, branch, year, status, role, sal in student_specs:
        _, st = create_user_student(email, roll, name, branch, year)
        students.append(st)
        outcome = EmploymentOutcome(
            student_id=st.id,
            status=status,
            company_name='Company X' if status == 'Placed' else None,
            role_title=role,
            salary_package_lpa=sal,
            placement_date=date(2025, 1, 15) if status == 'Placed' else None,
            placement_type='Campus' if status == 'Placed' else 'Unknown',
        )
        _db.session.add(outcome)

    _db.session.commit()

    # 4. Test Placement Summary
    ps = analytics_service.placement_summary()
    assert ps['total_students'] == 10
    assert ps['placed_count'] == 5
    assert ps['in_progress_count'] == 3
    assert ps['not_placed_count'] == 2
    assert ps['placement_pct'] == 50.0

    # 5. Test Salary Stats
    ss = analytics_service.salary_stats()
    assert ss['average'] == 8.0
    assert ss['median'] == 8.0
    assert ss['min'] == 4.0
    assert ss['max'] == 12.0
    assert ss['average_display'] == '8.00 LPA'
    assert ss['median_display'] == '8.00 LPA'

    bin_counts = {b['label']: b['count'] for b in ss['bins']}
    assert bin_counts['0-3 LPA'] == 0
    assert bin_counts['3-5 LPA'] == 1
    assert bin_counts['5-8 LPA'] == 1
    assert bin_counts['8-12 LPA'] == 2
    assert bin_counts['12+ LPA'] == 1

    # 6. Test Branch-wise Placement
    b_data = analytics_service.branch_wise_placement()
    b_map = {b['branch']: b for b in b_data}
    assert b_map['Computer Science']['total'] == 6
    assert b_map['Computer Science']['placed'] == 3
    assert b_map['Computer Science']['placement_pct'] == 50.0

    assert b_map['Electronics']['total'] == 4
    assert b_map['Electronics']['placed'] == 2
    assert b_map['Electronics']['placement_pct'] == 50.0

    # 7. Test Average Salary by Role
    sr = analytics_service.average_salary_by_role()
    sr_map = {r['role']: r for r in sr}
    assert sr_map['Software Engineer']['count'] == 2
    assert sr_map['Software Engineer']['average_salary'] == 8.0

    assert sr_map['Data Analyst']['count'] == 2
    assert sr_map['Data Analyst']['average_salary'] == 6.0

    assert sr_map['Embedded Engineer']['count'] == 1
    assert sr_map['Embedded Engineer']['average_salary'] == 12.0

    # 8. Test Role Distribution
    rd = analytics_service.job_role_distribution()
    rd_map = {r['role']: r for r in rd}
    assert rd_map['Software Engineer']['count'] == 2
    assert rd_map['Software Engineer']['percentage'] == 40.0
    assert rd_map['Data Analyst']['count'] == 2
    assert rd_map['Data Analyst']['percentage'] == 40.0
    assert rd_map['Embedded Engineer']['count'] == 1
    assert rd_map['Embedded Engineer']['percentage'] == 20.0

    # 9. Test Most Demanded Skills
    demanded = analytics_service.most_demanded_skills(limit=5)
    assert demanded[0]['skill_name'] == 'Python'
    assert demanded[0]['job_count'] == 3
    assert demanded[0]['weighted_demand'] == 14

    # 10. Gap Analyses & Deduplication of Most Missing Skills:
    # Student 1 runs analysis for role_se twice:
    # - Run 1 (older, id=1): missing SQL
    # - Run 2 (latest, id=2): missing Docker
    # Only Run 2 must be counted (Docker, not SQL)!
    an1 = SkillGapAnalysis(student_id=students[0].id, job_role_id=role_se.id, weighted_coverage_pct=50.0, analyzed_at=datetime(2025, 1, 1, 10, 0))
    _db.session.add(an1)
    _db.session.flush()
    _db.session.add(GapSkill(analysis_id=an1.id, skill_id=skills['SQL'].id, status='Missing'))

    an2 = SkillGapAnalysis(student_id=students[0].id, job_role_id=role_se.id, weighted_coverage_pct=75.0, analyzed_at=datetime(2025, 1, 2, 10, 0))
    _db.session.add(an2)
    _db.session.flush()
    _db.session.add(GapSkill(analysis_id=an2.id, skill_id=skills['Docker'].id, status='Missing'))

    # Student 2 runs analysis for role_se (id=3): missing Docker, Python
    an3 = SkillGapAnalysis(student_id=students[1].id, job_role_id=role_se.id, weighted_coverage_pct=60.0, analyzed_at=datetime(2025, 1, 2, 11, 0))
    _db.session.add(an3)
    _db.session.flush()
    _db.session.add_all([
        GapSkill(analysis_id=an3.id, skill_id=skills['Docker'].id, status='Missing'),
        GapSkill(analysis_id=an3.id, skill_id=skills['Python'].id, status='Missing'),
    ])
    _db.session.commit()

    missing = analytics_service.most_missing_skills(limit=5)
    missing_map = {m['skill_name']: m['missing_count'] for m in missing}
    # Docker is missing in latest of Student 1 and Student 2 -> count = 2
    assert missing_map.get('Docker') == 2
    # Python is missing in Student 2 -> count = 1
    assert missing_map.get('Python') == 1
    # SQL was only in older analysis of Student 1 -> MUST NOT BE COUNTED (0 or not in missing)
    assert 'SQL' not in missing_map

    # 11. Average Match Score:
    # Latest for Student 1 = 75.0, Student 2 = 60.0 -> Mean = (75 + 60) / 2 = 67.5%
    avg_match = analytics_service.average_match_score()
    assert avg_match['average_match'] == 67.5
    assert avg_match['average_match_display'] == '67.5%'


# ════════════════════════════════════════════════════════════════════════════════
#  3. FILTERS TESTS (BRANCH & GRADUATION YEAR)
# ════════════════════════════════════════════════════════════════════════════════

def test_analytics_filters():
    """Branch and graduation year filters correctly filter dataset calculations."""
    # 4 CSE (2025), 2 CSE (2024), 2 IT (2025), 2 IT (2024)
    # CSE 2025: 4 students, 2 placed
    for i in range(4):
        _, st = create_user_student(f'cse25_{i}@test.com', f'CSE25_{i}', f'CSE 25 {i}', 'Computer Science', 2025)
        status = 'Placed' if i < 2 else 'In Progress'
        sal = 8.0 if status == 'Placed' else None
        _db.session.add(EmploymentOutcome(student_id=st.id, status=status, salary_package_lpa=sal, role_title='Dev'))

    for i in range(2):
        _, st = create_user_student(f'cse24_{i}@test.com', f'CSE24_{i}', f'CSE 24 {i}', 'Computer Science', 2024)
        _db.session.add(EmploymentOutcome(student_id=st.id, status='Not Placed'))

    for i in range(2):
        _, st = create_user_student(f'it25_{i}@test.com', f'IT25_{i}', f'IT 25 {i}', 'Information Technology', 2025)
        _db.session.add(EmploymentOutcome(student_id=st.id, status='Placed', salary_package_lpa=12.0, role_title='Analyst'))

    _db.session.commit()

    # Filter by Branch='Computer Science'
    dash_cse = analytics_service.get_dashboard_analytics({'branch': 'Computer Science'})
    assert dash_cse['kpis']['total_students'] == 6
    assert dash_cse['kpis']['placed_count'] == 2
    assert dash_cse['kpis']['placement_pct'] == 33.3

    # Filter by Year=2025
    dash_2025 = analytics_service.get_dashboard_analytics({'year': 2025})
    assert dash_2025['kpis']['total_students'] == 6  # 4 CSE + 2 IT
    assert dash_2025['kpis']['placed_count'] == 4    # 2 CSE + 2 IT
    assert dash_2025['kpis']['placement_pct'] == 66.7

    # Filter by Branch='Information Technology' AND Year=2025
    dash_it_25 = analytics_service.get_dashboard_analytics({'branch': 'Information Technology', 'year': 2025})
    assert dash_it_25['kpis']['total_students'] == 2
    assert dash_it_25['kpis']['placed_count'] == 2
    assert dash_it_25['kpis']['placement_pct'] == 100.0
    assert dash_it_25['kpis']['avg_salary_display'] == '12.00 LPA'

    # Filter by non-existent branch
    dash_empty = analytics_service.get_dashboard_analytics({'branch': 'Mechanical Engineering'})
    assert dash_empty['kpis']['total_students'] == 0
    assert dash_empty['kpis']['placed_count'] == 0
    assert dash_empty['kpis']['placement_pct'] == 0.0
    assert dash_empty['kpis']['avg_salary_display'] == 'N/A'


# ════════════════════════════════════════════════════════════════════════════════
#  4. API ENDPOINT TESTS (/api/dashboard/stats & /api/student/<id>/analytics)
# ════════════════════════════════════════════════════════════════════════════════

def test_api_dashboard_stats(client):
    """Admin only endpoint /api/dashboard/stats with query parameter validation."""
    admin = create_admin_user('admin_api_stats@test.com')
    user, student = create_user_student('st_api@test.com', 'API_01', 'API Student', 'Computer Science', 2025)

    # 1. Guest blocked
    res_guest = client.get('/api/dashboard/stats')
    assert res_guest.status_code in (302, 401)

    # 2. Student blocked (403)
    login_client(client, user.email, 'Pass1234')
    res_student = client.get('/api/dashboard/stats')
    assert res_student.status_code == 403
    json_student = res_student.get_json()
    assert json_student['success'] is False

    # 3. Admin allowed (200)
    login_client(client, admin.email, 'AdminPass123')
    res_admin = client.get('/api/dashboard/stats')
    assert res_admin.status_code == 200
    json_admin = res_admin.get_json()
    assert json_admin['success'] is True
    assert 'kpis' in json_admin['data']
    assert 'placement' in json_admin['data']
    assert 'salary' in json_admin['data']

    # 4. Valid filter
    res_filtered = client.get('/api/dashboard/stats?branch=Computer+Science&year=2025')
    assert res_filtered.status_code == 200
    assert res_filtered.get_json()['success'] is True

    # 5. Invalid year filter (non-numeric) -> 400
    res_invalid_nan = client.get('/api/dashboard/stats?year=notayear')
    assert res_invalid_nan.status_code == 400
    assert res_invalid_nan.get_json()['success'] is False

    # 6. Invalid year filter (out of range) -> 400
    res_invalid_range = client.get('/api/dashboard/stats?year=3500')
    assert res_invalid_range.status_code == 400
    assert res_invalid_range.get_json()['success'] is False


def test_api_student_analytics_ownership(client):
    """Student can only access their own analytics; admin can access any."""
    user_a, student_a = create_user_student('user_a@test.com', 'UA01', 'Alice', 'Computer Science')
    user_b, student_b = create_user_student('user_b@test.com', 'UB01', 'Bob', 'Electronics')
    admin = create_admin_user('admin_st_api@test.com')

    # Student A views own
    login_client(client, user_a.email, 'Pass1234')
    res_own = client.get(f'/api/student/{student_a.id}/analytics')
    assert res_own.status_code == 200
    assert res_own.get_json()['success'] is True
    assert res_own.get_json()['data']['student']['name'] == 'Alice'

    # Student A attempts to view Student B -> 403 Forbidden
    res_other = client.get(f'/api/student/{student_b.id}/analytics')
    assert res_other.status_code == 403
    assert res_other.get_json()['success'] is False

    # Admin can view Student A
    login_client(client, admin.email, 'AdminPass123')
    res_admin_view = client.get(f'/api/student/{student_a.id}/analytics')
    assert res_admin_view.status_code == 200
    assert res_admin_view.get_json()['success'] is True


# ════════════════════════════════════════════════════════════════════════════════
#  5. WEB PAGES & UI TESTS (/admin/dashboard & /student/analytics)
# ════════════════════════════════════════════════════════════════════════════════

def test_admin_dashboard_web_view(client):
    """Admin dashboard renders demo banner, 6 KPI cards, 6 charts and CSV export."""
    admin = create_admin_user('admin_web@test.com')
    user, student = create_user_student('web_st@test.com', 'WST01', 'Web Student', 'Computer Science')

    # Student blocked from admin dashboard
    login_client(client, user.email, 'Pass1234')
    res_denied = client.get('/admin/dashboard')
    assert res_denied.status_code == 403

    # Admin views dashboard
    login_client(client, admin.email, 'AdminPass123')
    res_dash = client.get('/admin/dashboard')
    assert res_dash.status_code == 200
    content = res_dash.data.decode('utf-8')

    # Check Demo Banner
    assert "Demo project: figures shown are computed from synthetic/demo data unless real records are entered." in content

    # Check 6 Charts Canvas Elements
    assert 'id="chartPlacementStatus"' in content
    assert 'id="chartTopSkills"' in content
    assert 'id="chartSkillGaps"' in content
    assert 'id="chartBranchPlacement"' in content
    assert 'id="chartSkillImprovement"' in content
    assert 'id="chartSalaryDistribution"' in content

    # Check 2 Tables
    assert "Average Salary by Job Role" in content
    assert "Job Role Placement Distribution" in content

    # Test CSV Export button route
    res_csv = client.get('/admin/dashboard/export-csv')
    assert res_csv.status_code == 200
    assert res_csv.mimetype == 'text/csv'
    csv_text = res_csv.data.decode('utf-8')
    assert "SECTION 1: KEY PERFORMANCE INDICATORS" in csv_text
    assert "SECTION 2: BRANCH-WISE PLACEMENT SUMMARY" in csv_text
    assert "SECTION 3: AVERAGE SALARY BY JOB ROLE" in csv_text
    assert "SECTION 4: JOB ROLE PLACEMENT DISTRIBUTION" in csv_text


def test_student_analytics_web_view(client):
    """Student analytics renders personal metrics, neutral wording, and radar/line charts."""
    user, student = create_user_student('st_view@test.com', 'SV01', 'Sara View', 'Computer Science')

    login_client(client, user.email, 'Pass1234')
    res = client.get('/student/analytics')
    assert res.status_code == 200
    content = res.data.decode('utf-8')

    assert "My Skill &amp; Career Analytics" in content or "My Skill & Career Analytics" in content
    assert "Profile Strength" in content
    assert "Skills Recorded" in content
    assert "Target Match" in content
    assert "Learning Path" in content
    assert "studentSkillRadar" in content
    assert "studentProgressLine" in content
    assert "Your Skills vs Most Demanded Industry Skills" in content


def test_csv_formula_injection_guard():
    """Verify formula injection characters are neutralized in exported CSVs."""
    from services.analytics_service import _sanitize_csv_cell
    assert _sanitize_csv_cell("=1+1") == "'=1+1"
    assert _sanitize_csv_cell("+cmd|'/c calc'!A0") == "'+cmd|'/c calc'!A0"
    assert _sanitize_csv_cell("-500") == "'-500"
    assert _sanitize_csv_cell("@SUM(1,2)") == "'@SUM(1,2)"
    assert _sanitize_csv_cell("Google Cloud") == "Google Cloud"
    assert _sanitize_csv_cell(None) == ""
