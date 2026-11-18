"""
deploy/setup_db.py — Production Database Initialization & Idempotent Seeding
─────────────────────────────────────────────────────────────────────────────
Sets up a fresh database on a production or staging server:
1. Creates all tables from SQLAlchemy models if they do not exist.
2. Seeds master skills (seed_skills.py).
3. Seeds job roles and descriptions (seed_jobs.py).
4. Seeds courses catalog (seed_courses.py).
5. Seeds real companies if seed_real_companies.py exists.
6. Seeds demo students (seed_demo_students.py), unless SEED_DEMO_USERS=false.
7. Creates the production admin from ADMIN_EMAIL and ADMIN_PASSWORD env vars (if set).

Safe to run multiple times without creating duplicate rows or erroring out.
"""

import os
import sys

# Ensure project root is in sys.path
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(THIS_DIR, '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv()

from app import create_app
from extensions import db
from models.user import User


def create_admin_user() -> bool:
    """
    Creates an admin account reading credentials from ADMIN_EMAIL and ADMIN_PASSWORD.
    Never hardcodes passwords in code. If either variable is missing, skips creation gracefully.
    Idempotent: skips if user already exists.
    """
    admin_email = os.environ.get('ADMIN_EMAIL')
    admin_password = os.environ.get('ADMIN_PASSWORD')

    if not admin_email or not admin_password:
        print("[setup_db] ADMIN_EMAIL or ADMIN_PASSWORD not set in environment. Skipping admin creation.")
        return False

    admin_email = admin_email.strip()
    existing = User.query.filter_by(email=admin_email).first()
    if existing:
        print(f"[setup_db] Admin account '{admin_email}' already exists. Skipping creation.")
        return False

    admin = User(email=admin_email, role='admin', is_active=True)
    admin.set_password(admin_password)
    db.session.add(admin)
    db.session.commit()
    print(f"[setup_db] Created production admin user: {admin_email}")
    return True


def setup_database(app=None):
    """
    Executes full database schema creation and idempotent seed pipeline.
    """
    if app is None:
        env_mode = os.environ.get('FLASK_ENV', 'production')
        # If in production and SECRET_KEY is missing, provide temporary fallback for CLI init
        if env_mode == 'production' and not os.environ.get('SECRET_KEY'):
            os.environ['SECRET_KEY'] = 'setup-db-init-secret-temporary-key-123456789'
        app = create_app(env_mode)

    with app.app_context():
        print("==================================================")
        print("  Starting Database Setup & Idempotent Seeding    ")
        print("==================================================")

        # 1. Create tables
        print("[1/6] Creating database tables if not exist...")
        db.create_all()
        print("      [OK] Database schema verified.")

        # 2. Seed Skills
        print("[2/6] Running seed_skills...")
        import seed_skills
        seed_skills.seed(app)

        # 3. Seed Jobs
        print("[3/6] Running seed_jobs...")
        import seed_jobs
        seed_jobs.seed_jobs(app)

        # 4. Seed Courses
        print("[4/6] Running seed_courses...")
        import seed_courses
        seed_courses.seed_courses(app)

        # 5. Seed Real Companies (if script exists)
        print("[5/6] Checking for seed_real_companies...")
        try:
            import seed_real_companies
            if hasattr(seed_real_companies, 'seed'):
                seed_real_companies.seed()
            elif hasattr(seed_real_companies, 'seed_companies'):
                seed_real_companies.seed_companies()
            print("      [OK] seed_real_companies executed.")
        except ImportError:
            print("      [SKIP] seed_real_companies.py not present in codebase.")

        # 6. Seed Demo Students (optional via SEED_DEMO_USERS=false)
        seed_demo_flag = os.environ.get('SEED_DEMO_USERS', 'true').lower()
        if seed_demo_flag not in ('false', '0', 'no'):
            print("[6/6] Seeding demo students (SEED_DEMO_USERS != false)...")
            import seed_demo_students
            seed_demo_students.seed_demo_students()
        else:
            print("[6/6] Skipping demo students seeding (SEED_DEMO_USERS=false).")

        # 7. Admin account from environment variables
        print("[+] Checking production admin credentials...")
        create_admin_user()

        # 8. Discussion Forum seed (Categories & Demo discussions)
        print("[+] Seeding Discussion Forum (seed_forum)...")
        try:
            import seed_forum
            seed_forum.seed_forum(app)
            print("      [OK] seed_forum executed.")
        except Exception as e:
            print(f"      [SKIP] seed_forum error/skipped: {e}")

        print("==================================================")
        print("  Database Setup Completed Successfully!          ")
        print("==================================================")


if __name__ == '__main__':
    setup_database()

