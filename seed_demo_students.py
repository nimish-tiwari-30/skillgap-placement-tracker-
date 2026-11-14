"""
seed_demo_students.py
─────────────────────
Idempotent script to seed 30 synthetic demo students for Phase 12 & Phase 13.
Safe to execute multiple times without duplicating data or altering real users.

Credentials for Demo Accounts:
  Demo Students:
    Email:    demo.student01@example.com to demo.student30@example.com
    Password: DemoStudent@123
  Demo Admin:
    Email:    admin@skillgap.edu
    Password: Admin@123

Usage:
  python seed_demo_students.py
"""

import os
import random
import sys
from datetime import date, datetime, timedelta

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from extensions import db
from models.user import User
from models.student import Student, Certification, Project, Internship
from models.skill import Skill, StudentSkill
from models.job import JobRole
from models.outcome import EmploymentOutcome, EmploymentOutcomeSkill


# Fixed random seed for deterministic, reproducible dataset
RANDOM_SEED = 42

BRANCHES = ['CSE', 'IT', 'ECE', 'EE', 'ME', 'CE']
GRADUATION_YEARS = [2024, 2025, 2026]

DEMO_FIRST_NAMES = [
    'Aarav', 'Ananya', 'Rohan', 'Priya', 'Kabir', 'Sneha', 'Vikram', 'Neha',
    'Aditya', 'Pooja', 'Rahul', 'Divya', 'Arjun', 'Isha', 'Karan', 'Tanvi',
    'Varun', 'Riya', 'Sameer', 'Shreya', 'Amit', 'Meera', 'Nikhil', 'Simran',
    'Akash', 'Kavita', 'Manish', 'Sonal', 'Gaurav', 'Anjali'
]

DEMO_LAST_NAMES = [
    'Sharma', 'Verma', 'Patel', 'Reddy', 'Mehta', 'Nair', 'Gupta', 'Singh',
    'Joshi', 'Chopra', 'Rao', 'Bhat', 'Deshmukh', 'Mishra', 'Iyer', 'Kapoor'
]

DEMO_COMPANIES = [
    'Demo Tech Corp', 'Apex Cloud Solutions', 'Nexus Analytics',
    'Cognitive Data Systems', 'Quantum Softworks', 'Zenith Infotech',
    'Matrix Digital Labs', 'Horizon FinTech'
]

CERT_PROVIDERS = [
    ('AWS Certified Cloud Practitioner', 'Amazon Web Services'),
    ('Google Associate Cloud Engineer', 'Google Cloud'),
    ('Microsoft Certified: Azure Fundamentals', 'Microsoft'),
    ('Meta Front-End Developer', 'Coursera / Meta'),
    ('Python for Everybody', 'University of Michigan'),
    ('Deep Learning Specialization', 'DeepLearning.AI'),
]


def seed_demo_admin():
    """Ensure at least one admin exists."""
    admin_email = 'admin@skillgap.edu'
    existing = User.query.filter_by(email=admin_email).first()
    if not existing:
        admin_user = User(email=admin_email, role='admin', is_active=True)
        admin_user.set_password('Admin@123')
        db.session.add(admin_user)
        db.session.flush()
        print(f"[OK] Seeded demo admin: {admin_email} / Admin@123")
    else:
        print(f"[SKIP] Demo admin already exists: {admin_email}")


def seed_demo_students():
    """Seed 30 synthetic students with portfolios and employment outcomes."""
    random.seed(RANDOM_SEED)

    # 1. Fetch available skills and job roles
    all_skills = Skill.query.all()
    if not all_skills:
        print("[ERROR] No skills found in database. Seed master skills first.")
        return

    all_roles = JobRole.query.all()
    role_titles = [r.title for r in all_roles] if all_roles else ['Software Engineer', 'Data Analyst', 'Web Developer']

    print(f"-- Seeding 30 Demo Students (Random Seed: {RANDOM_SEED}) -------------------")

    created_count = 0
    updated_count = 0

    for i in range(1, 31):
        idx_str = f"{i:02d}"
        email = f"demo.student{idx_str}@example.com"
        roll_no = f"22DEMO{idx_str}"
        first_name = DEMO_FIRST_NAMES[i - 1]
        last_name = DEMO_LAST_NAMES[(i * 3) % len(DEMO_LAST_NAMES)]
        full_name = f"{first_name} {last_name}"
        branch = BRANCHES[(i - 1) % len(BRANCHES)]
        grad_year = GRADUATION_YEARS[(i - 1) % len(GRADUATION_YEARS)]

        # Synthetic CGPA with realistic variation
        cgpa_base = round(6.2 + (random.random() * 3.6), 2)
        cgpa = min(9.9, max(6.0, cgpa_base))

        # Phase 14: Synthetic aptitude and communication scores (0–100)
        # Loosely correlated with CGPA so higher-CGPA students tend to score higher
        aptitude = int(min(100, max(30, round(50 + (cgpa - 7.5) * 8 + random.gauss(0, 10)))))
        comm     = int(min(100, max(30, round(55 + random.gauss(0, 15)))))

        # Check existing user
        user = User.query.filter_by(email=email).first()
        if not user:
            user = User(email=email, role='student', is_active=True)
            user.set_password('DemoStudent@123')
            db.session.add(user)
            db.session.flush()

            student = Student(
                user_id=user.id,
                full_name=full_name,
                roll_number=roll_no,
                branch=branch,
                graduation_year=grad_year,
                cgpa=cgpa,
                phone=f"98765{i:05d}",
                linkedin_url=f"https://linkedin.com/in/demo-student-{idx_str}",
                github_url=f"https://github.com/demo-student-{idx_str}",
                aptitude_score=aptitude,
                communication_score=comm,
            )
            db.session.add(student)
            db.session.flush()
            created_count += 1
        else:
            student = user.student
            # Idempotent update: set scores if missing (Phase 14)
            if student.aptitude_score is None:
                student.aptitude_score = aptitude
            if student.communication_score is None:
                student.communication_score = comm
            updated_count += 1

        # 2. Seed Skills if student has none
        if not student.skills:
            num_skills = random.randint(4, 9)
            chosen_skills = random.sample(all_skills, min(num_skills, len(all_skills)))
            for sk in chosen_skills:
                prof = random.choice(['Beginner', 'Intermediate', 'Intermediate', 'Advanced'])
                ss = StudentSkill(
                    student_id=student.id,
                    skill_id=sk.id,
                    proficiency_level=prof,
                    source='manual'
                )
                db.session.add(ss)

        # 3. Seed Projects if none
        if not student.projects:
            num_proj = random.randint(1, 3)
            for p_idx in range(1, num_proj + 1):
                proj = Project(
                    student_id=student.id,
                    title=f"Synthetic Project {p_idx}: {branch} Solution",
                    description=f"Automated prototype built by {full_name} for semester capstone.",
                    tech_stack="Python, SQL, HTML/CSS",
                    start_date=date(2023, 1 + (p_idx * 2), 1),
                    end_date=date(2023, 3 + (p_idx * 2), 1),
                )
                db.session.add(proj)

        # 4. Seed Certifications if none
        if not student.certifications and random.random() > 0.3:
            cert_title, cert_org = random.choice(CERT_PROVIDERS)
            cert = Certification(
                student_id=student.id,
                title=cert_title,
                issuing_org=cert_org,
                issue_date=date(2024, random.randint(1, 6), 15),
                credential_url=f"https://verify.example.com/cert/{idx_str}",
            )
            db.session.add(cert)

        # 5. Seed Internships if none
        if not student.internships and random.random() > 0.4:
            intern = Internship(
                student_id=student.id,
                company_name=random.choice(DEMO_COMPANIES),
                role_title="Software Engineering Intern",
                description="Contributed to core product features and bug fixes.",
                start_date=date(2024, 1, 10),
                end_date=date(2024, 4, 10),
                is_current=False,
            )
            db.session.add(intern)

        # 6. Seed Employment Outcome
        # Loosely correlate placement status with CGPA + skills + noise for balanced mix
        skill_count = len(student.skills) if student.skills else num_skills
        noise = random.random()
        placement_score = (cgpa / 10.0) * 0.50 + (min(skill_count, 8) / 8.0) * 0.20 + (noise * 0.30)

        # Thresholds to ensure a realistic mix of all 3 statuses
        if placement_score >= 0.72:
            status = 'Placed'
        elif placement_score >= 0.58:
            status = 'In Progress'
        else:
            status = 'Not Placed'

        # Outcome record (one per student)
        outcome = EmploymentOutcome.query.filter_by(student_id=student.id).first()
        if not outcome:
            outcome = EmploymentOutcome(student_id=student.id)
            db.session.add(outcome)

        outcome.status = status
        outcome.updated_at = datetime.utcnow()

        if status == 'Placed':
            outcome.company_name = random.choice(DEMO_COMPANIES)
            outcome.role_title = random.choice(role_titles)
            # Salary in LPA: between 4.0 LPA and 24.0 LPA loosely tied to CGPA
            salary = round(4.5 + (cgpa - 6.0) * 3.5 + (random.random() * 4.0), 2)
            salary = min(35.0, max(3.5, salary))
            outcome.salary_package_lpa = salary
            # Placement date: within past 18 months, not future
            days_ago = random.randint(15, 450)
            outcome.placement_date = date.today() - timedelta(days=days_ago)
            outcome.placement_type = random.choice(['Campus', 'Campus', 'Off-Campus', 'Internship-Converted'])
            outcome.notes = f"Selected via placement drive for {outcome.role_title}."

            db.session.flush()

            # Attach 2-4 skills used from student's skills
            st_skill_ids = [ss.skill_id for ss in student.skills]
            if st_skill_ids:
                skills_to_use = random.sample(st_skill_ids, min(random.randint(2, 4), len(st_skill_ids)))
                # Remove existing junction rows
                EmploymentOutcomeSkill.query.filter_by(outcome_id=outcome.id).delete()
                for sid in skills_to_use:
                    db.session.add(EmploymentOutcomeSkill(outcome_id=outcome.id, skill_id=sid))
        else:
            outcome.company_name = None
            outcome.role_title = None
            outcome.salary_package_lpa = None
            outcome.placement_date = None
            outcome.placement_type = 'Unknown'
            outcome.notes = "Seeking opportunities." if status == 'In Progress' else "Opting for higher studies or off-campus search."
            # Remove any skills used rows for non-placed
            db.session.flush()
            EmploymentOutcomeSkill.query.filter_by(outcome_id=outcome.id).delete()

    db.session.commit()
    print(f"[PASS] Demo student seeding complete! Created: {created_count}, Updated/Existing: {updated_count}")

    # Summary of seeded outcomes
    placed_n = EmploymentOutcome.query.filter_by(status='Placed').count()
    not_placed_n = EmploymentOutcome.query.filter_by(status='Not Placed').count()
    in_prog_n = EmploymentOutcome.query.filter_by(status='In Progress').count()
    print(f"       Outcome Distribution: Placed={placed_n}, In Progress={in_prog_n}, Not Placed={not_placed_n}")


def run_seed():
    app = create_app()
    with app.app_context():
        seed_demo_admin()
        seed_demo_students()


if __name__ == '__main__':
    run_seed()
