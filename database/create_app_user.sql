-- ============================================================
-- create_app_user.sql
-- Creates a dedicated MySQL user for the app (NOT root).
-- Run this ONCE in MySQL Workbench or via mysql command line.
-- Security principle: least privilege — app only gets what it needs.
-- ============================================================

-- Step 1: Create the app user with a strong password
-- ⚠️  Change 'AppUser@1234' to your own secure password before running
CREATE USER IF NOT EXISTS 'skill_gap_user'@'localhost'
    IDENTIFIED BY 'AppUser@1234';

-- Step 2: Grant only required privileges on our database
-- (No SUPER, no DROP DATABASE, no access to other databases)
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, REFERENCES
    ON skill_gap_system.*
    TO 'skill_gap_user'@'localhost';

-- Step 3: Apply the privileges immediately
FLUSH PRIVILEGES;

-- Step 4: Verify
SELECT User, Host FROM mysql.user WHERE User = 'skill_gap_user';
SHOW GRANTS FOR 'skill_gap_user'@'localhost';
