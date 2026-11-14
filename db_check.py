"""
db_check.py
───────────
Phase 2 verification script.
Checks:
  1. SQLAlchemy connects via app config
  2. All 20 expected tables exist in the database
  3. Model-vs-schema column match for each model
  4. Insert → Read → Update → Delete (rolled-back transaction)
  5. Foreign key enforcement is active (InnoDB strict mode)

Run: python db_check.py
Expected: All PASS
"""

import sys
import os
import io
from dotenv import load_dotenv

# Fix Windows terminal encoding (cp1252 can't handle unicode box chars)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

load_dotenv()

# ── Helpers ──────────────────────────────────────────────────────────
def ok(msg: str) -> None:
    print(f"\033[92m[PASS]\033[0m {msg}")

def fail(msg: str) -> None:
    print(f"\033[91m[FAIL]\033[0m {msg}")
    # Don't exit — show all results

def section(title: str) -> None:
    print(f"\n{'--'*25}")
    print(f"  {title}")
    print(f"{'--'*25}")


# ── Expected Tables ───────────────────────────────────────────────────
EXPECTED_TABLES = [
    'users', 'students', 'skills', 'skill_aliases', 'student_skills',
    'resumes', 'certifications', 'projects', 'internships',
    'job_roles', 'job_descriptions', 'job_skills',
    'skill_gap_analysis', 'gap_skills',
    'courses', 'course_skills', 'course_progress', 'learning_path_items',
    'employment_outcomes', 'skill_progress',
]

# ── Expected columns per model (subset check) ─────────────────────────
EXPECTED_COLUMNS = {
    'users':                ['id', 'email', 'password_hash', 'role', 'is_active', 'created_at'],
    'students':             ['id', 'user_id', 'full_name', 'roll_number', 'branch', 'cgpa', 'graduation_year', 'profile_completion_pct'],
    'skills':               ['id', 'name', 'category'],
    'skill_aliases':        ['id', 'skill_id', 'alias_name'],
    'student_skills':       ['id', 'student_id', 'skill_id', 'proficiency_level', 'source'],
    'resumes':              ['id', 'student_id', 'original_name', 'stored_filename', 'file_path', 'file_type'],
    'job_roles':            ['id', 'title', 'department'],
    'job_descriptions':     ['id', 'job_role_id', 'title', 'description_text', 'is_active'],
    'job_skills':           ['id', 'job_description_id', 'skill_id', 'importance_weight'],
    'skill_gap_analysis':   ['id', 'student_id', 'job_role_id', 'unweighted_coverage_pct', 'weighted_coverage_pct', 'cosine_similarity_score'],
    'gap_skills':           ['id', 'analysis_id', 'skill_id', 'status'],
    'courses':              ['id', 'title', 'provider', 'difficulty_level', 'duration_hours', 'rating'],
    'course_skills':        ['id', 'course_id', 'skill_id'],
    'course_progress':      ['id', 'student_id', 'course_id', 'status'],
    'learning_path_items':  ['id', 'student_id', 'analysis_id', 'skill_id', 'phase_number', 'is_completed'],
    'employment_outcomes':  ['id', 'student_id', 'status', 'company_name', 'salary_package_lpa'],
    'certifications':       ['id', 'student_id', 'title', 'issuing_org'],
    'projects':             ['id', 'student_id', 'title', 'tech_stack'],
    'internships':          ['id', 'student_id', 'company_name', 'role_title'],
    'skill_progress':       ['id', 'student_id', 'skill_id', 'old_proficiency', 'new_proficiency', 'recorded_at'],
}


def main():
    print("=" * 50)
    print("  DB_CHECK.PY — Phase 2 Verification")
    print("=" * 50)

    all_passed = True

    # ── CHECK 1: SQLAlchemy Connection via Flask App ──────────────
    section("CHECK 1: SQLAlchemy Connection via Flask App Config")
    try:
        from app import create_app
        from extensions import db

        app = create_app('development')
        with app.app_context():
            # Test actual DB query via ORM
            result = db.session.execute(db.text("SELECT 1 AS alive")).fetchone()
            if result and result[0] == 1:
                ok("SQLAlchemy connected to MySQL via app config")
            else:
                fail("SQLAlchemy query returned unexpected result")
                all_passed = False
    except Exception as e:
        fail(f"Flask/SQLAlchemy connection failed: {e}")
        fail("Fix: Check SQLALCHEMY_DATABASE_URI in config.py and .env credentials")
        all_passed = False
        return  # Can't continue without DB

    # ── CHECK 2: All Expected Tables Exist ───────────────────────
    section("CHECK 2: Expected Tables Existence (SHOW TABLES)")
    with app.app_context():
        try:
            result = db.session.execute(db.text("SHOW TABLES")).fetchall()
            existing_tables = {row[0].lower() for row in result}

            for table in EXPECTED_TABLES:
                if table in existing_tables:
                    ok(f"Table exists: {table}")
                else:
                    fail(f"Table MISSING: {table}  →  Fix: Re-run database/apply_schema.py")
                    all_passed = False

            extra = existing_tables - set(EXPECTED_TABLES)
            if extra:
                print(f"  [INFO] Extra tables (not in expected list): {extra}")

        except Exception as e:
            fail(f"SHOW TABLES failed: {e}")
            all_passed = False

    # ── CHECK 3: Column Match (Model vs Schema) ───────────────────
    section("CHECK 3: Column Match — Model vs Schema")
    with app.app_context():
        for table, expected_cols in EXPECTED_COLUMNS.items():
            try:
                result = db.session.execute(
                    db.text(f"SHOW COLUMNS FROM `{table}`")
                ).fetchall()
                actual_cols = {row[0].lower() for row in result}
                missing_cols = [c for c in expected_cols if c.lower() not in actual_cols]
                if missing_cols:
                    fail(f"Table '{table}' missing columns: {missing_cols}")
                    all_passed = False
                else:
                    ok(f"Table '{table}' — all {len(expected_cols)} expected columns present")
            except Exception as e:
                fail(f"Could not check columns for '{table}': {e}")
                all_passed = False

    # ── CHECK 4: CRUD Transaction (Insert→Read→Update→Delete) ────
    section("CHECK 4: CRUD Transaction (auto-rolled back)")
    with app.app_context():
        try:
            from models import Skill

            # Begin a nested transaction (SAVEPOINT) so we can rollback safely
            with db.session.begin_nested():
                # INSERT
                test_skill = Skill(name='__TEST_SKILL__', category='test')
                db.session.add(test_skill)
                db.session.flush()  # Push to DB within transaction (no commit)

                inserted_id = test_skill.id
                ok(f"INSERT: Skill '__TEST_SKILL__' inserted (id={inserted_id})")

                # READ
                found = db.session.get(Skill, inserted_id)
                if found and found.name == '__TEST_SKILL__':
                    ok(f"READ: Skill fetched successfully (name={found.name})")
                else:
                    fail("READ: Could not fetch inserted skill")
                    all_passed = False

                # UPDATE
                found.category = 'test_updated'
                db.session.flush()
                refreshed = db.session.get(Skill, inserted_id)
                if refreshed and refreshed.category == 'test_updated':
                    ok(f"UPDATE: Category updated to 'test_updated'")
                else:
                    fail("UPDATE: Category update not reflected")
                    all_passed = False

                # DELETE
                db.session.delete(refreshed)
                db.session.flush()
                deleted = db.session.get(Skill, inserted_id)
                if deleted is None:
                    ok(f"DELETE: Skill removed from session successfully")
                else:
                    fail("DELETE: Skill still present after delete")
                    all_passed = False

            # ROLLBACK — nested transaction automatically rolls back here
            db.session.rollback()
            ok("ROLLBACK: Transaction rolled back — no test data in DB")

        except Exception as e:
            db.session.rollback()
            fail(f"CRUD transaction failed: {e}")
            all_passed = False

    # ── CHECK 5: Foreign Key Enforcement Active ────────────────────
    section("CHECK 5: Foreign Key Enforcement (InnoDB STRICT)")
    with app.app_context():
        try:
            # Try inserting a student with a non-existent user_id — must fail
            db.session.execute(db.text("SET FOREIGN_KEY_CHECKS=1"))
            db.session.execute(db.text(
                "INSERT INTO students (user_id, full_name, roll_number, branch) "
                "VALUES (999999, 'Ghost Student', 'TEST-0000', 'Test')"
            ))
            db.session.rollback()
            fail("FK enforcement FAILED — orphan row was accepted! Check InnoDB engine.")
            all_passed = False
        except Exception as e:
            db.session.rollback()
            if '1452' in str(e) or 'foreign key constraint' in str(e).lower():
                ok("FK enforcement ACTIVE — orphan insert correctly rejected (Error 1452)")
            else:
                fail(f"Unexpected error during FK test: {e}")
                all_passed = False

    # ── FINAL RESULT ──────────────────────────────────────────────
    print()
    print("=" * 50)
    if all_passed:
        print("\033[92m  ALL CHECKS PASSED — Phase 2 DB is ready!\033[0m")
    else:
        print("\033[91m  SOME CHECKS FAILED — See FAIL messages above.\033[0m")
    print("=" * 50)


if __name__ == '__main__':
    main()
