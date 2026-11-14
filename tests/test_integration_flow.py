"""
tests/test_integration_flow.py
───────────────────────────────
Phase 15: End-to-End System Integration Flow Test.

Tests the complete student-admin lifecycle in one unbroken flow:
  1. Student registration
  2. Manual skill addition
  3. Resume upload and text parsing
  4. Review and confirmation of extracted skills
  5. Admin creates Job Role + Job Description + weighted Job Skills
  6. Student selects target job
  7. Initial Skill-Gap analysis (unweighted 60.0%, weighted 60.0%)
  8. Job matching via TF-IDF cosine similarity
  9. Course recommendations for missing skills
 10. Learning path generation
 11. Completion of a learning path step (Machine Learning)
 12. Re-running Skill-Gap analysis (coverage increases to 80.0% unweighted, 85.0% weighted)
 13. Recording employment outcome (Placed, 16.5 LPA)
 14. Admin dashboard stats verification reflecting the new student
 15. ML placement prediction endpoint execution (demo mode)
"""

import io
import pytest
from extensions import db
from models.user import User
from models.student import Student
from models.skill import Skill, StudentSkill, SkillAlias
from models.job import JobRole, JobDescription, JobSkill
from models.gap import SkillGapAnalysis
from models.course import Course, CourseSkill, LearningPathItem
from models.outcome import EmploymentOutcome
from ml.skill_extractor import refresh_skills_cache


def test_full_system_end_to_end_flow(client, app):
    """
    Execute the entire product workflow end-to-end and assert key numbers at each phase.
    """
    # ── Setup Canonical Skills & Courses ─────────────────────────────────────
    with app.app_context():
        skills_def = [
            ("Python", "Programming"),
            ("SQL", "Data & Analytics"),
            ("Docker", "Cloud/DevOps"),
            ("Machine Learning", "Data & Analytics"),
            ("FastAPI", "Programming"),
        ]
        skill_map = {}
        for s_name, s_cat in skills_def:
            sk = Skill.query.filter_by(name=s_name).first()
            if not sk:
                sk = Skill(name=s_name, category=s_cat)
                db.session.add(sk)
                db.session.flush()
            skill_map[s_name] = sk

            alias_name = s_name.lower()
            if not SkillAlias.query.filter_by(alias_name=alias_name).first():
                db.session.add(SkillAlias(skill_id=sk.id, alias_name=alias_name))

        # Add course for Machine Learning & FastAPI idempotently
        c_ml = Course.query.filter_by(title="Complete Machine Learning Bootcamp").first()
        if not c_ml:
            c_ml = Course(title="Complete Machine Learning Bootcamp", provider="Coursera", difficulty_level="Intermediate")
            db.session.add(c_ml)
            db.session.flush()

        c_api = Course.query.filter_by(title="FastAPI Microservices Guide").first()
        if not c_api:
            c_api = Course(title="FastAPI Microservices Guide", provider="Udemy", difficulty_level="Beginner")
            db.session.add(c_api)
            db.session.flush()

        if not CourseSkill.query.filter_by(course_id=c_ml.id, skill_id=skill_map["Machine Learning"].id).first():
            db.session.add(CourseSkill(course_id=c_ml.id, skill_id=skill_map["Machine Learning"].id))

        if not CourseSkill.query.filter_by(course_id=c_api.id, skill_id=skill_map["FastAPI"].id).first():
            db.session.add(CourseSkill(course_id=c_api.id, skill_id=skill_map["FastAPI"].id))

        # Admin user
        admin = User.query.filter_by(email="admin_flow@college.edu").first()
        if not admin:
            admin = User(email="admin_flow@college.edu", role="admin", is_active=True)
            admin.set_password("AdminPass123!")
            db.session.add(admin)

        db.session.commit()
        refresh_skills_cache()

    # ── STEP 1: Student Registration ──────────────────────────────────────────
    reg_data = {
        'full_name': 'E2E Flow Student',
        'email': 'e2e_student@college.edu',
        'roll_number': 'E2E_ROLL_01',
        'branch': 'Computer Science',
        'password': 'StudentPass123!',
        'confirm_password': 'StudentPass123!',
    }
    res_reg = client.post('/register', data=reg_data, follow_redirects=False)
    assert res_reg.status_code == 302
    assert '/login' in res_reg.headers['Location']

    with app.app_context():
        st_user = User.query.filter_by(email='e2e_student@college.edu').first()
        assert st_user is not None
        student = Student.query.filter_by(roll_number='E2E_ROLL_01').first()
        assert student is not None
        assert student.user_id == st_user.id
        student_id = student.id

    # ── STEP 2: Manual Skill Addition ─────────────────────────────────────────
    # Log in as the student
    res_login = client.post('/login', data={'email': 'e2e_student@college.edu', 'password': 'StudentPass123!'}, follow_redirects=True)
    assert res_login.status_code == 200

    # Add 'Python' manually
    py_id = skill_map["Python"].id
    res_add_skill = client.post('/student/profile/skills/add', data={
        'skill_id': py_id,
        'proficiency': 'Intermediate'
    }, follow_redirects=True)
    assert res_add_skill.status_code == 200

    with app.app_context():
        ss = StudentSkill.query.filter_by(student_id=student_id, skill_id=py_id).first()
        assert ss is not None
        assert ss.proficiency_level == 'Intermediate'
        assert ss.source == 'manual'

    # ── STEP 3: Upload Sample Resume ──────────────────────────────────────────
    # Minimal PDF mentioning SQL and Docker
    pdf_bytes = (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n"
        b"3 0 obj<</Type/Page/MediaBox[0 0 300 144]/Parent 2 0 R/Resources<<>>/Contents 4 0 R>>endobj\n"
        b"4 0 obj<</Length 45>>stream\n"
        b"BT /F1 12 Tf 50 100 Td (Proficient in SQL and Docker containers) Tj ET\n"
        b"endstream\n"
        b"endobj\n"
        b"xref\n0 5\n0000000000 65535 f\n0000000009 00000 n\n0000000058 00000 n\n0000000115 00000 n\n0000000214 00000 n\n"
        b"trailer<</Size 5/Root 1 0 R>>\nstartxref\n310\n%%EOF\n"
    )

    res_upload = client.post('/student/resume/upload', data={
        'resume': (io.BytesIO(pdf_bytes), 'resume_e2e.pdf')
    }, content_type='multipart/form-data', follow_redirects=True)
    assert res_upload.status_code == 200
    assert b'Resume parsed successfully' in res_upload.data or b'technical skill' in res_upload.data

    # ── STEP 4: Confirm Extracted Skills ──────────────────────────────────────
    sql_id = skill_map["SQL"].id
    docker_id = skill_map["Docker"].id

    res_confirm = client.post('/student/resume/confirm', data={
        'skill_ids': [str(sql_id), str(docker_id)],
        f'proficiency_{sql_id}': 'Intermediate',
        f'proficiency_{docker_id}': 'Beginner',
    }, follow_redirects=True)
    assert res_confirm.status_code == 200

    with app.app_context():
        # Student should now possess 3 skills: Python (manual), SQL (resume), Docker (resume)
        curr_skills = StudentSkill.query.filter_by(student_id=student_id).all()
        assert len(curr_skills) == 3
        skills_owned = {cs.skill_id for cs in curr_skills}
        assert skills_owned == {py_id, sql_id, docker_id}

    # ── STEP 5: Admin Creates Job Role + Job Description + Skills ─────────────
    client.get('/logout')
    client.post('/login', data={'email': 'admin_flow@college.edu', 'password': 'AdminPass123!'}, follow_redirects=False)

    with app.app_context():
        role = JobRole(title='Full Stack AI Engineer', department='Engineering', description='Build AI-powered services')
        db.session.add(role)
        db.session.flush()

        jd = JobDescription(
            job_role_id=role.id,
            title='Junior AI Engineer',
            company_name='Neural Systems Inc',
            description_text='Looking for AI Engineer with Python SQL Docker Machine Learning and FastAPI expertise',
            min_experience='0-1 years'
        )
        db.session.add(jd)
        db.session.flush()

        # Weights: Python:5, SQL:4, Docker:3, Machine Learning:5, FastAPI:3 (Total weight = 20)
        weights = {
            skill_map["Python"].id: 5,
            skill_map["SQL"].id: 4,
            skill_map["Docker"].id: 3,
            skill_map["Machine Learning"].id: 5,
            skill_map["FastAPI"].id: 3,
        }
        for s_id, w in weights.items():
            db.session.add(JobSkill(job_description_id=jd.id, skill_id=s_id, importance_weight=w))

        db.session.commit()
        role_id = role.id
        jd_id = jd.id

    # ── STEP 6: Student Sets Target Job ───────────────────────────────────────
    client.get('/logout')
    client.post('/login', data={'email': 'e2e_student@college.edu', 'password': 'StudentPass123!'}, follow_redirects=True)

    res_target = client.post(f'/student/skill-gap/set-target/{jd_id}', follow_redirects=True)
    assert res_target.status_code == 200

    with app.app_context():
        st_ref = db.session.get(Student, student_id)
        assert st_ref.target_job_id == jd_id

    # ── STEP 7: Skill-Gap Analysis (Coverage & Weighted) ──────────────────────
    res_gap = client.post('/student/skill-gap', data={'job_id': jd_id}, follow_redirects=True)
    assert res_gap.status_code == 200

    with app.app_context():
        latest_gap = SkillGapAnalysis.query.filter_by(student_id=student_id, job_description_id=jd_id).order_by(SkillGapAnalysis.id.desc()).first()
        assert latest_gap is not None
        # Student has 3 of 5 required skills -> 60.0% unweighted coverage
        assert float(latest_gap.unweighted_coverage_pct) == 60.0
        # Matched weights: 5 (Python) + 4 (SQL) + 3 (Docker) = 12. Total = 20. -> 12/20 = 60.0%
        assert float(latest_gap.weighted_coverage_pct) == 60.0

    # ── STEP 8: Job Match (Cosine Similarity) ─────────────────────────────────
    res_match = client.get(f'/student/job-match/{jd_id}')
    assert res_match.status_code == 200
    assert b'Neural Systems Inc' in res_match.data or b'Junior AI Engineer' in res_match.data

    # ── STEP 9: Course Recommendations ────────────────────────────────────────
    res_recom = client.get('/student/recommendations')
    assert res_recom.status_code == 200
    # Must recommend courses for missing skills (Machine Learning or FastAPI)
    assert b'Machine Learning' in res_recom.data or b'FastAPI' in res_recom.data

    # ── STEP 10: Generate Learning Path ───────────────────────────────────────
    res_lpath_gen = client.post('/student/learning-path/generate', data={'job_id': jd_id}, follow_redirects=True)
    assert res_lpath_gen.status_code == 200

    with app.app_context():
        items = LearningPathItem.query.filter_by(student_id=student_id).order_by(LearningPathItem.display_order).all()
        assert len(items) >= 2
        # Find item for Machine Learning
        ml_item = next(it for it in items if it.skill_id == skill_map["Machine Learning"].id)
        assert ml_item.is_completed is False
        ml_item_id = ml_item.id

    # ── STEP 11: Mark a Step Complete ─────────────────────────────────────────
    res_complete = client.post(f'/student/learning-path/{ml_item_id}/complete', follow_redirects=True)
    assert res_complete.status_code == 200

    with app.app_context():
        # Item marked complete
        upd_item = db.session.get(LearningPathItem, ml_item_id)
        assert upd_item.is_completed is True
        # Machine Learning skill automatically acquired
        ml_skill = StudentSkill.query.filter_by(student_id=student_id, skill_id=skill_map["Machine Learning"].id).first()
        assert ml_skill is not None
        assert ml_skill.source == 'course'

    # ── STEP 12: Re-run Skill-Gap (Assert Coverage Increased) ─────────────────
    res_gap2 = client.post('/student/skill-gap', data={'job_id': jd_id}, follow_redirects=True)
    assert res_gap2.status_code == 200

    with app.app_context():
        new_gap = SkillGapAnalysis.query.filter_by(student_id=student_id, job_description_id=jd_id).order_by(SkillGapAnalysis.id.desc()).first()
        # Student now has 4 of 5 skills -> 80.0% unweighted coverage
        assert float(new_gap.unweighted_coverage_pct) == 80.0
        # Matched weights: 12 + 5 (ML) = 17 / 20 = 85.0%
        assert float(new_gap.weighted_coverage_pct) == 85.0
        # Verify coverage increased
        assert new_gap.unweighted_coverage_pct > latest_gap.unweighted_coverage_pct
        assert new_gap.weighted_coverage_pct > latest_gap.weighted_coverage_pct

    # ── STEP 13: Record Employment Outcome ────────────────────────────────────
    outcome_data = {
        'status': 'Placed',
        'company_name': 'Neural Systems Inc',
        'role_title': 'Junior AI Engineer',
        'salary_package_lpa': '16.5',
        'placement_date': '2026-05-15',
        'placement_type': 'Campus',
        'notes': 'Placed through automated campus referral',
    }
    res_outcome = client.post('/student/employment', data=outcome_data, follow_redirects=True)
    assert res_outcome.status_code == 200

    with app.app_context():
        saved_out = EmploymentOutcome.query.filter_by(student_id=student_id).first()
        assert saved_out is not None
        assert saved_out.status == 'Placed'
        assert float(saved_out.salary_package_lpa) == 16.5

    # ── STEP 14: Admin Dashboard Reflects the New Student ────────────────────
    client.get('/logout')
    client.post('/login', data={'email': 'admin_flow@college.edu', 'password': 'AdminPass123!'}, follow_redirects=False)

    res_stats = client.get('/api/dashboard/stats')
    assert res_stats.status_code == 200
    stats_json = res_stats.get_json()
    assert stats_json['success'] is True
    data = stats_json['data']
    # Dashboard stats contain the placed student
    kpis = data['kpis']
    assert kpis['total_students'] >= 1
    assert kpis['placed_count'] >= 1
    assert kpis['placement_pct'] > 0.0

    # ── STEP 15: Prediction Endpoint Responds (Demo Mode) ─────────────────────
    client.get('/logout')
    client.post('/login', data={'email': 'e2e_student@college.edu', 'password': 'StudentPass123!'}, follow_redirects=True)

    res_pred = client.get('/student/prediction')
    assert res_pred.status_code == 200
    pred_html = res_pred.data.decode('utf-8')
    assert 'Predicted outcome' in pred_html or 'Placement' in pred_html
    # Demo notice is rendered
    assert 'historical data' in pred_html.lower() or 'demo' in pred_html.lower() or 'not enough' in pred_html.lower()
