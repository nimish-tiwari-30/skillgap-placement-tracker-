"""
seed_users.py
─────────────
Idempotent seed script to create default demo Admin and Student accounts.

Run:
    python seed_users.py

Credentials:
    Admin:
        Email:    admin@skillgap.edu
        Password: Admin@123
    Student:
        Email:    student@skillgap.edu
        Password: Student@123
"""

import os
import sys

# Allow running from project root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from extensions import db
from models.user import User
from models.student import Student
from models.skill import Skill, StudentSkill


def seed_demo_users():
    app = create_app()
    with app.app_context():
        print("-- Seeding Demo Users ---------------------------------------")

        # 1. Admin User
        admin_email = "admin@skillgap.edu"
        admin = User.query.filter_by(email=admin_email).first()
        if not admin:
            admin = User(email=admin_email, role='admin')
            admin.set_password('Admin@123')
            db.session.add(admin)
            db.session.flush()
            print(f"[OK] Created Admin user: {admin_email}")
        else:
            print(f"[SKIP] Admin user already exists: {admin_email}")

        # 2. Student User
        student_email = "student@skillgap.edu"
        student_user = User.query.filter_by(email=student_email).first()
        if not student_user:
            student_user = User(email=student_email, role='student')
            student_user.set_password('Student@123')
            db.session.add(student_user)
            db.session.flush()

            student = Student(
                user_id=student_user.id,
                full_name="Aarav Sharma",
                roll_number="22CS101",
                branch="Computer Science",
                graduation_year=2026,
                cgpa=8.75,
                phone="9876543210"
            )
            db.session.add(student)
            db.session.flush()

            # Seed a few initial skills for the student
            sample_skills = ["Python", "SQL", "Excel", "Git"]
            for sname in sample_skills:
                skill = Skill.query.filter(db.func.lower(Skill.name) == sname.lower()).first()
                if skill:
                    ss = StudentSkill(
                        student_id=student.id,
                        skill_id=skill.id,
                        proficiency_level="Intermediate",
                        source="manual"
                    )
                    db.session.add(ss)

            print(f"[OK] Created Student user: {student_email} (Aarav Sharma, Roll: 22CS101)")
        else:
            print(f"[SKIP] Student user already exists: {student_email}")

        db.session.commit()
        print("[PASS] User seeding completed successfully!")


if __name__ == '__main__':
    seed_demo_users()
