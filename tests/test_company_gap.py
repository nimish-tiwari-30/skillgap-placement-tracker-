"""
tests/test_company_gap.py
─────────────────────────
Comprehensive test suite for Company-Wise Skill Gap ("Target Companies").

Covers:
1. Pure function aggregation in ml/company_profile.py (job counts, demand share, avg importance, Core/Common/Occasional).
2. Hand-calculated skill gap verification matching ml/skill_gap.py.
3. Edge cases: zero jobs, zero skills, zero student skills, NaN/ZeroDivision guards.
4. Database case-insensitive company grouping ("Demo Sky Systems" vs "demo sky systems ").
5. Company comparison (up to 5, validation, unknown handling).
6. Web routes and API access control (guest 302, student 200, admin 403, cross-tenant isolation, 404 for unknown company).
7. Required disclaimer text on rendered pages.
"""

import pytest
from extensions import db as _db
from models.user import User
from models.student import Student
from models.skill import Skill, StudentSkill
from models.job import JobRole, JobDescription, JobSkill
from ml.company_profile import (
    build_company_skill_profile,
    compute_company_skill_gap,
    classify_demand_share,
)
from services.company_service import (
    list_companies,
    get_company_profile,
    analyze_company,
    compare_companies,
)


# ─────────────────────────────────────────────────────────────────────────────
# 1. PURE FUNCTION TESTS: Aggregation & Classification
# ─────────────────────────────────────────────────────────────────────────────

def test_demand_share_classification():
    """Verify classification thresholds: Core >= 50%, Common 25-49%, Occasional < 25%."""
    assert classify_demand_share(0.50) == "Core"
    assert classify_demand_share(0.75) == "Core"
    assert classify_demand_share(1.00) == "Core"
    assert classify_demand_share(0.49) == "Common"
    assert classify_demand_share(0.25) == "Common"
    assert classify_demand_share(0.249) == "Occasional"
    assert classify_demand_share(0.10) == "Occasional"
    assert classify_demand_share(0.0) == "Occasional"


def test_company_skill_profile_aggregation_three_jobs():
    """
    Aggregation test with 3 hand-built jobs:
      Job 1: Skill A (imp 5), Skill B (imp 3)
      Job 2: Skill A (imp 4), Skill C (imp 2)
      Job 3: Skill A (imp 3), Skill B (imp 4)
    Total jobs = 3.
      Skill A: 3 jobs -> 100% -> demand share 1.0 -> 'Core', avg importance = (5+4+3)/3 = 4.0, company_importance = 4
      Skill B: 2 jobs -> 66.7% -> demand share 0.67 -> 'Core', avg importance = (3+4)/2 = 3.5, company_importance = 4
      Skill C: 1 job  -> 33.3% -> demand share 0.33 -> 'Common', avg importance = 2.0, company_importance = 2
    """
    job_skills_rows = [
        {"job_id": 1, "skill_id": 101, "skill_name": "Skill A", "importance": 5},
        {"job_id": 1, "skill_id": 102, "skill_name": "Skill B", "importance": 3},
        {"job_id": 2, "skill_id": 101, "skill_name": "Skill A", "importance": 4},
        {"job_id": 2, "skill_id": 103, "skill_name": "Skill C", "importance": 2},
        {"job_id": 3, "skill_id": 101, "skill_name": "Skill A", "importance": 3},
        {"job_id": 3, "skill_id": 102, "skill_name": "Skill B", "importance": 4},
    ]

    profile = build_company_skill_profile(job_skills_rows, total_company_jobs=3)

    assert len(profile) == 3
    # Check Skill A
    a_row = next(r for r in profile if r["skill_name"] == "Skill A")
    assert a_row["job_count"] == 3
    assert a_row["demand_share"] == 1.0
    assert a_row["demand_share_pct"] == 100.0
    assert a_row["importance_avg"] == 4.0
    assert a_row["importance"] == 4
    assert a_row["classification"] == "Core"

    # Check Skill B
    b_row = next(r for r in profile if r["skill_name"] == "Skill B")
    assert b_row["job_count"] == 2
    assert round(b_row["demand_share"], 2) == 0.67
    assert round(b_row["demand_share_pct"], 1) == 66.7
    assert b_row["importance_avg"] == 3.5
    assert b_row["importance"] == 4
    assert b_row["classification"] == "Core"

    # Check Skill C
    c_row = next(r for r in profile if r["skill_name"] == "Skill C")
    assert c_row["job_count"] == 1
    assert round(c_row["demand_share"], 2) == 0.33
    assert round(c_row["demand_share_pct"], 1) == 33.3
    assert c_row["importance_avg"] == 2.0
    assert c_row["importance"] == 2
    assert c_row["classification"] == "Common"


# ─────────────────────────────────────────────────────────────────────────────
# 2. GAP COMPUTATION & CONSISTENCY WITH ml/skill_gap.py
# ─────────────────────────────────────────────────────────────────────────────

def test_company_skill_gap_hand_calculated_numbers():
    """
    Company required skills:
      Skill A (imp 4)
      Skill B (imp 4)
      Skill C (imp 2)
    Total importance = 4 + 4 + 2 = 10.

    Student has only: Skill A.
    Matched: [Skill A]
    Missing: [Skill B, Skill C]

    Expected metrics:
      Coverage % = (1 / 3) * 100 = 33.3%
      Weighted % = (4 / 10) * 100 = 40.0%
      Extra count = 0
    """
    company_profile = [
        {"skill_id": 1, "skill_name": "Skill A", "importance": 4, "company_importance": 4, "demand_share": 1.0, "classification": "Core"},
        {"skill_id": 2, "skill_name": "Skill B", "importance": 4, "company_importance": 4, "demand_share": 0.67, "classification": "Core"},
        {"skill_id": 3, "skill_name": "Skill C", "importance": 2, "company_importance": 2, "demand_share": 0.33, "classification": "Common"},
    ]
    student_skills = ["Skill A"]

    gap = compute_company_skill_gap(company_profile, student_skills)

    assert gap["total_required"] == 3
    assert gap["matched_count"] == 1
    assert gap["missing_count"] == 2
    assert [s["skill_name"] for s in gap["matched_skills"]] == ["Skill A"]
    assert [s["skill_name"] for s in gap["missing_skills"]] == ["Skill B", "Skill C"]
    assert gap["coverage_pct"] == 33.3
    assert gap["weighted_pct"] == 40.0
    assert gap["overall_match_pct"] >= 0.0


# ─────────────────────────────────────────────────────────────────────────────
# 3. EDGE CASES: Zero jobs, Zero skills, Student with 0 skills, No Crash / No NaN
# ─────────────────────────────────────────────────────────────────────────────

def test_edge_cases_zero_jobs_and_zero_skills():
    """Verify company with 0 jobs or 0 skills returns safe zero defaults with no crash or NaN."""
    # Zero jobs
    profile_empty = build_company_skill_profile([], total_company_jobs=0)
    assert profile_empty == []

    gap_empty = compute_company_skill_gap([], ["Python", "SQL"])
    assert gap_empty["coverage_pct"] == 0.0
    assert gap_empty["weighted_pct"] == 0.0
    assert gap_empty["overall_match_pct"] == 0.0
    assert gap_empty["total_required"] == 0
    assert gap_empty["matched_skills"] == []
    assert gap_empty["missing_skills"] == []

    # Student with 0 skills
    company_profile = [
        {"skill_id": 1, "skill_name": "Python", "importance": 5, "company_importance": 5, "demand_share": 1.0, "classification": "Core"}
    ]
    gap_no_student_skills = compute_company_skill_gap(company_profile, [])
    assert gap_no_student_skills["coverage_pct"] == 0.0
    assert gap_no_student_skills["weighted_pct"] == 0.0
    assert gap_no_student_skills["matched_count"] == 0
    assert gap_no_student_skills["missing_count"] == 1
    assert [s["skill_name"] for s in gap_no_student_skills["missing_skills"]] == ["Python"]


# ─────────────────────────────────────────────────────────────────────────────
# 4. DATABASE INTEGRATION & CASE-INSENSITIVE GROUPING
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def seeded_company_db(app_context):
    """Seed test database with jobs across case-varying company names and students."""
    role = JobRole.query.filter_by(title="Software Engineer").first()
    if not role:
        role = JobRole(title="Software Engineer", department="Tech", description="Dev role")
        _db.session.add(role)
        _db.session.flush()

    def get_or_create_s(name, cat):
        s = Skill.query.filter_by(name=name).first()
        if not s:
            s = Skill(name=name, category=cat)
            _db.session.add(s)
            _db.session.flush()
        return s

    s_py = get_or_create_s("Python", "Backend")
    s_sql = get_or_create_s("SQL", "Database")
    s_dock = get_or_create_s("Docker", "DevOps")

    # Create 2 jobs under "Demo Sky Systems" and 1 job under "demo sky systems " (differing case and trailing whitespace)
    j1 = JobDescription(
        job_role_id=role.id,
        title="Backend Engineer",
        company_name="Demo Sky Systems",
        location="Remote",
        min_experience="0 years",
        description_text="Build services in Python and SQL"
    )
    j2 = JobDescription(
        job_role_id=role.id,
        title="Fullstack Engineer",
        company_name="Demo Sky Systems",
        location="Remote",
        min_experience="2 years",
        description_text="Python and Docker"
    )
    j3 = JobDescription(
        job_role_id=role.id,
        title="Platform Engineer",
        company_name="demo sky systems ",
        location="Remote",
        min_experience="1 year",
        description_text="SQL and Docker"
    )
    _db.session.add_all([j1, j2, j3])
    _db.session.flush()

    # Job Skills
    js_list = [
        JobSkill(job_description_id=j1.id, skill_id=s_py.id, importance_weight=5),
        JobSkill(job_description_id=j1.id, skill_id=s_sql.id, importance_weight=4),
        JobSkill(job_description_id=j2.id, skill_id=s_py.id, importance_weight=4),
        JobSkill(job_description_id=j2.id, skill_id=s_dock.id, importance_weight=3),
        JobSkill(job_description_id=j3.id, skill_id=s_sql.id, importance_weight=5),
        JobSkill(job_description_id=j3.id, skill_id=s_dock.id, importance_weight=4),
    ]
    _db.session.add_all(js_list)

    # Student with Python
    u = User(email="student_test@example.com", role="student", is_active=True)
    u.set_password("StudentPass123!")
    _db.session.add(u)
    _db.session.flush()

    st = Student(user_id=u.id, full_name="Sky Student", roll_number="SKY01", branch="CS")
    _db.session.add(st)
    _db.session.flush()

    _db.session.add(StudentSkill(student_id=st.id, skill_id=s_py.id, proficiency_level="Intermediate"))
    _db.session.commit()

    return {
        "user": u,
        "student": st,
        "company_name": "Demo Sky Systems",
    }


def test_case_insensitive_company_grouping(seeded_company_db):
    """Verify list_companies groups 'Demo Sky Systems' and 'demo sky systems ' into one canonical company."""
    companies = list_companies()
    matching = [c for c in companies if c["company_name"].lower() == "demo sky systems"]
    assert len(matching) == 1, "Case variants of Demo Sky Systems should be grouped into exactly 1 company"
    comp = matching[0]
    assert comp["job_count"] == 3
    assert comp["skill_count"] == 3  # Python, SQL, Docker


def test_company_service_analyze_and_compare(seeded_company_db):
    """Verify analyze_company and compare_companies work with real DB entities."""
    st = seeded_company_db["student"]
    comp_name = seeded_company_db["company_name"]

    ok, res, code = analyze_company(st.id, comp_name)
    assert ok is True
    assert code == 200
    assert res["company_name"].lower() == "demo sky systems"
    assert "Python" in [s["skill_name"] for s in res["matched_skills"]]
    assert any(s["skill_name"] in ("SQL", "Docker") for s in res["missing_skills"])
    assert res["total_jobs"] == 3

    # Compare up to 5 companies
    ok_c, comp_data, code_c = compare_companies(st.id, [comp_name])
    assert ok_c is True
    comp_list = comp_data["companies"]
    assert len(comp_list) == 1
    assert comp_list[0]["company_name"].lower() == "demo sky systems"


def test_compare_limit_and_unknown_handling(seeded_company_db):
    """Verify comparison rejects more than 5 companies and handles unknown companies gracefully."""
    st = seeded_company_db["student"]
    six_names = ["Comp1", "Comp2", "Comp3", "Comp4", "Comp5", "Comp6"]
    # compare_companies should reject more than 5 companies
    ok_limit, res_limit, code_limit = compare_companies(st.id, six_names)
    assert ok_limit is False
    assert code_limit == 400
    assert "up to 5" in res_limit

    # Unknown company (<= 5) returns 404 friendly error
    ok_unk, res_unk, code_unk = compare_companies(st.id, ["UnknownCorpX"])
    assert ok_unk is False
    assert code_unk == 404

    # Unknown company returns None in get_company_profile
    unk = get_company_profile("NonExistentCorp12345")
    assert unk is None


# ─────────────────────────────────────────────────────────────────────────────
# 5. ROUTE ACCESS CONTROL & API ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def auth_fixtures(seeded_company_db):
    u = seeded_company_db["user"]
    st = seeded_company_db["student"]

    # Admin user
    adm = User(email="admin_co@example.com", role="admin", is_active=True)
    adm.set_password("AdminPass123!")
    _db.session.add(adm)

    # Other student
    u2 = User(email="other_student@example.com", role="student", is_active=True)
    u2.set_password("OtherPass123!")
    _db.session.add(u2)
    _db.session.flush()
    st2 = Student(user_id=u2.id, full_name="Other Student", roll_number="OTHER01", branch="IT")
    _db.session.add(st2)
    _db.session.commit()

    return {
        "student_user": u,
        "student": st,
        "admin_user": adm,
        "other_user": u2,
        "other_student": st2,
    }


def login_user(client, email, password):
    return client.post('/login', data={'email': email, 'password': password}, follow_redirects=True)


def test_company_pages_guest_redirected(client):
    """Verify unauthenticated guests are redirected to login for student company pages."""
    resp1 = client.get("/student/companies")
    assert resp1.status_code == 302
    assert "/login" in resp1.headers.get("Location", "")

    resp2 = client.get("/student/companies/Demo%20Sky%20Systems")
    assert resp2.status_code == 302

    resp3 = client.get("/student/companies/compare?c=Demo%20Sky%20Systems")
    assert resp3.status_code == 302


def test_company_pages_admin_blocked(client, auth_fixtures):
    """Verify admins are blocked (403) from student company pages."""
    login_user(client, "admin_co@example.com", "AdminPass123!")

    resp1 = client.get("/student/companies")
    assert resp1.status_code == 403

    resp2 = client.get("/student/companies/Demo%20Sky%20Systems")
    assert resp2.status_code == 403

    resp3 = client.get("/student/companies/compare?c=Demo%20Sky%20Systems")
    assert resp3.status_code == 403


def test_student_company_detail_and_disclaimer(client, auth_fixtures):
    """Verify student can view company detail and the mandatory disclaimer text is present."""
    login_user(client, auth_fixtures["student_user"].email, "StudentPass123!")

    resp = client.get("/student/companies/Demo%20Sky%20Systems")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    # Mandatory disclaimer verification
    disclaimer = "Company requirements are combined from the job descriptions stored in this system. They show which skills this company's listed jobs ask for, not the company's actual hiring criteria. Demo data."
    assert disclaimer in html

    # Unknown company returns 404
    resp_404 = client.get("/student/companies/NoSuchCompanyExistent999")
    assert resp_404.status_code == 404


def test_student_company_compare_page_and_disclaimer(client, auth_fixtures):
    """Verify student can view compare page and neutral wording is maintained."""
    login_user(client, auth_fixtures["student_user"].email, "StudentPass123!")

    resp = client.get("/student/companies/compare?c=Demo%20Sky%20Systems")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    disclaimer = "Company requirements are combined from the job descriptions stored in this system. They show which skills this company's listed jobs ask for, not the company's actual hiring criteria. Demo data."
    assert disclaimer in html


def test_api_company_endpoints_and_isolation(client, auth_fixtures):
    """Verify API endpoints enforce authentication, student isolation, and handle unknown companies."""
    # Guest access blocked
    r_guest = client.get("/api/companies")
    assert r_guest.status_code in (302, 401, 403)

    # Authenticated student can get company list
    login_user(client, auth_fixtures["student_user"].email, "StudentPass123!")

    r_comp = client.get("/api/companies")
    assert r_comp.status_code == 200
    data = r_comp.get_json()
    assert data["success"] is True
    assert any(c["company_name"].lower() == "demo sky systems" for c in data["data"])

    # Skill profile for company
    r_skills = client.get("/api/company/Demo%20Sky%20Systems/skills")
    assert r_skills.status_code == 200
    sdata = r_skills.get_json()
    assert sdata["success"] is True
    assert len(sdata["data"]["skills"]) > 0

    # Skill profile for unknown company -> 404 JSON
    r_skills_404 = client.get("/api/company/UnknownEntityX/skills")
    assert r_skills_404.status_code == 404
    assert r_skills_404.get_json()["success"] is False

    # Own student company gap analysis
    s1_id = auth_fixtures["student"].id
    r_gap = client.get(f"/api/student/{s1_id}/company-gap?company=Demo%20Sky%20Systems")
    assert r_gap.status_code == 200
    gdata = r_gap.get_json()
    assert gdata["success"] is True
    assert "company_name" in gdata["data"]

    # Unknown company for student gap -> 404 JSON
    r_gap_404 = client.get(f"/api/student/{s1_id}/company-gap?company=NoSuchCompany")
    assert r_gap_404.status_code == 404
    assert r_gap_404.get_json()["success"] is False

    # Cross-tenant isolation: student 1 cannot read student 2's company gap
    s2_id = auth_fixtures["other_student"].id
    r_cross = client.get(f"/api/student/{s2_id}/company-gap?company=Demo%20Sky%20Systems")
    assert r_cross.status_code == 403
    assert r_cross.get_json()["success"] is False
