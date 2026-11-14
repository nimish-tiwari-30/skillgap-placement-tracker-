"""
fk_demo.py
──────────
Demonstrates that Foreign Key constraints work correctly.

Test A: Insert student with non-existent user_id → must FAIL (Error 1452)
Test B: Delete a user → linked student row is CASCADE DELETED automatically

Run: python fk_demo.py
"""

import os
import pymysql
from dotenv import load_dotenv

load_dotenv()

conn = pymysql.connect(
    host=os.environ['DB_HOST'],
    user=os.environ['DB_USER'],
    password=os.environ['DB_PASSWORD'],
    port=int(os.environ['DB_PORT']),
    database=os.environ['DB_NAME'],
    charset='utf8mb4',
    autocommit=False
)

cursor = conn.cursor()

print("=" * 55)
print("  FK BEHAVIOR DEMO — Phase 2")
print("=" * 55)

# ─────────────────────────────────────────────────────────
# TEST A: Orphan insert — student with non-existent user_id
# Expected: MySQL raises Error 1452 (FK violation)
# ─────────────────────────────────────────────────────────
print("\n[TEST A] Insert student with user_id=999999 (does not exist in users)")
try:
    cursor.execute(
        "INSERT INTO students (user_id, full_name, roll_number, branch) "
        "VALUES (%s, %s, %s, %s)",
        (999999, 'Ghost Student', 'GHOST-001', 'CS')
    )
    conn.rollback()
    print("  [FAIL] Row was inserted — FK enforcement is NOT active!")
    print("         Fix: Ensure table uses InnoDB engine, not MyISAM.")
except pymysql.err.IntegrityError as e:
    conn.rollback()
    if e.args[0] == 1452:
        print(f"  [PASS] Correctly rejected with Error 1452:")
        print(f"         {e.args[1]}")
        print("         Explanation: users.id=999999 doesn't exist, so students.user_id FK fails.")
    else:
        print(f"  [FAIL] Unexpected IntegrityError: {e}")


# ─────────────────────────────────────────────────────────
# TEST B: CASCADE DELETE — delete user → student disappears
# Setup:  insert a real user + linked student, then delete user
# Expected: student row is automatically deleted (ON DELETE CASCADE)
# ─────────────────────────────────────────────────────────
print("\n[TEST B] ON DELETE CASCADE — deleting user cascades to student")

try:
    # Insert a test user
    cursor.execute(
        "INSERT INTO users (email, password_hash, role) VALUES (%s, %s, %s)",
        ('cascade_test@demo.com', 'fakehash', 'student')
    )
    user_id = cursor.lastrowid
    print(f"  → Inserted user id={user_id} (cascade_test@demo.com)")

    # Insert a linked student
    cursor.execute(
        "INSERT INTO students (user_id, full_name, roll_number, branch) "
        "VALUES (%s, %s, %s, %s)",
        (user_id, 'Cascade Test Student', 'CASCADE-001', 'CS')
    )
    student_id = cursor.lastrowid
    print(f"  → Inserted student id={student_id} linked to user id={user_id}")

    # Verify student exists
    cursor.execute("SELECT id FROM students WHERE id = %s", (student_id,))
    exists_before = cursor.fetchone()
    print(f"  → Student exists before delete: {exists_before is not None}")

    # DELETE the user (should cascade to student)
    cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
    print(f"  → Deleted user id={user_id}")

    # Check if student was automatically deleted
    cursor.execute("SELECT id FROM students WHERE id = %s", (student_id,))
    exists_after = cursor.fetchone()

    if exists_after is None:
        print(f"  [PASS] Student id={student_id} was AUTOMATICALLY DELETED via CASCADE.")
        print("         Explanation: students.user_id has ON DELETE CASCADE,")
        print("         so when user is deleted, all linked students are deleted too.")
    else:
        print(f"  [FAIL] Student still exists after user delete — CASCADE not working.")

    conn.commit()

except Exception as e:
    conn.rollback()
    print(f"  [ERROR] Test B failed: {e}")

cursor.close()
conn.close()

print("\n" + "=" * 55)
print("  FK DEMO COMPLETE")
print("=" * 55)
