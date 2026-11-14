"""
apply_schema.py
───────────────
Script to create the MySQL database and apply schema.sql.
Run once: python apply_schema.py
"""

import pymysql
import os
import re
from dotenv import load_dotenv

load_dotenv()

DB_HOST     = os.environ.get('DB_HOST', 'localhost')
DB_USER     = os.environ.get('DB_USER', 'root')
DB_PASSWORD = os.environ.get('DB_PASSWORD', '')
DB_PORT     = int(os.environ.get('DB_PORT', 3306))
DB_NAME     = os.environ.get('DB_NAME', 'skill_gap_system')


def apply_schema():
    print("=" * 50)
    print("  DATABASE SETUP — PHASE 2")
    print("=" * 50)

    # Step 1: Connect to MySQL server (no DB selected)
    try:
        conn = pymysql.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            port=DB_PORT,
            autocommit=True,
            charset='utf8mb4'
        )
        print(f"[OK] Connected to MySQL at {DB_HOST}:{DB_PORT}")
    except Exception as e:
        print(f"[FAIL] MySQL connection failed: {e}")
        print("  Fix: Check DB_HOST, DB_USER, DB_PASSWORD in .env")
        return

    cursor = conn.cursor()

    # Step 2: Create database
    try:
        cursor.execute(
            f"CREATE DATABASE IF NOT EXISTS {DB_NAME} "
            f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
        cursor.execute(f"USE {DB_NAME}")
        print(f"[OK] Database '{DB_NAME}' created/verified and selected.")
    except Exception as e:
        print(f"[FAIL] Could not create database: {e}")
        cursor.close()
        conn.close()
        return

    # Step 3: Read schema.sql
    schema_path = os.path.join(os.path.dirname(__file__), 'database', 'schema.sql')
    try:
        with open(schema_path, 'r', encoding='utf-8') as f:
            raw_sql = f.read()
    except FileNotFoundError:
        print(f"[FAIL] schema.sql not found at {schema_path}")
        cursor.close()
        conn.close()
        return

    # Step 4: Remove comment lines, split into statements
    lines = [line for line in raw_sql.splitlines() if not line.strip().startswith('--')]
    clean_sql = '\n'.join(lines)
    statements = [s.strip() for s in clean_sql.split(';') if s.strip()]

    # Step 5: Execute each statement
    created_tables = []
    errors = []

    for stmt in statements:
        upper_stmt = stmt.upper().strip()
        # Skip CREATE DATABASE and USE — already handled above
        if upper_stmt.startswith('CREATE DATABASE') or upper_stmt.startswith('USE '):
            continue
        try:
            cursor.execute(stmt)
            # Track table creation
            if 'CREATE TABLE' in upper_stmt:
                match = re.search(r'CREATE TABLE IF NOT EXISTS (\w+)', stmt, re.IGNORECASE)
                if match:
                    created_tables.append(match.group(1))
        except Exception as e:
            errors.append(f"{str(e)}")

    cursor.close()
    conn.close()

    # Step 6: Report results
    print()
    print("=== TABLES CREATED / VERIFIED ===")
    for table in created_tables:
        print(f"  [OK] {table}")

    if errors:
        print()
        print("=== WARNINGS / ERRORS ===")
        for err in errors:
            print(f"  [!] {err}")

    print()
    print(f"Total tables: {len(created_tables)}")
    if not errors:
        print("Schema applied SUCCESSFULLY! Ready for Phase 3.")
    else:
        print(f"Schema applied with {len(errors)} warnings (check above).")


if __name__ == '__main__':
    apply_schema()
