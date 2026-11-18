-- ============================================================
-- schema.sql — Skill Gap & Employment Outcome Tracking System
-- Database: skill_gap_system
-- Engine: MySQL 8.0 | Charset: utf8mb4
-- ============================================================

-- Create and select database
CREATE DATABASE IF NOT EXISTS skill_gap_system
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE skill_gap_system;

-- ────────────────────────────────────────────────
-- TABLE 1: users
-- Base authentication table for all system users
-- ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id              INT             NOT NULL AUTO_INCREMENT,
    email           VARCHAR(255)    NOT NULL,
    password_hash   VARCHAR(255)    NOT NULL,
    role            ENUM('student','admin') NOT NULL DEFAULT 'student',
    is_active       TINYINT(1)      NOT NULL DEFAULT 1,
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_users_email (email),
    INDEX idx_users_role (role)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ────────────────────────────────────────────────
-- TABLE 2: students
-- Extended profile for student role users
-- ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS students (
    id                      INT             NOT NULL AUTO_INCREMENT,
    user_id                 INT             NOT NULL,
    full_name               VARCHAR(150)    NOT NULL,
    roll_number             VARCHAR(50)     NOT NULL,
    branch                  VARCHAR(100)    NOT NULL,
    cgpa                    DECIMAL(4,2)    DEFAULT NULL CHECK (cgpa >= 0.0 AND cgpa <= 10.0),
    graduation_year         YEAR            DEFAULT NULL,
    phone                   VARCHAR(20)     DEFAULT NULL,
    linkedin_url            VARCHAR(255)    DEFAULT NULL,
    github_url              VARCHAR(255)    DEFAULT NULL,
    profile_completion_pct  TINYINT         NOT NULL DEFAULT 0 CHECK (profile_completion_pct >= 0 AND profile_completion_pct <= 100),
    target_job_id           INT             DEFAULT NULL,
    -- Phase 14: ML features — scores known BEFORE placement outcome
    aptitude_score          TINYINT         DEFAULT NULL CHECK (aptitude_score >= 0 AND aptitude_score <= 100),
    communication_score     TINYINT         DEFAULT NULL CHECK (communication_score >= 0 AND communication_score <= 100),
    created_at              DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at              DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_students_user_id (user_id),
    UNIQUE KEY uq_students_roll_number (roll_number),
    INDEX idx_students_branch (branch),
    INDEX idx_students_graduation_year (graduation_year),
    INDEX idx_students_target_job_id (target_job_id),
    CONSTRAINT fk_students_user_id
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_students_target_job_id
        FOREIGN KEY (target_job_id) REFERENCES job_descriptions(id)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ────────────────────────────────────────────────
-- TABLE 3: skills
-- Master canonical skills dictionary
-- ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS skills (
    id          INT             NOT NULL AUTO_INCREMENT,
    name        VARCHAR(100)    NOT NULL,
    category    VARCHAR(100)    DEFAULT NULL,
    description TEXT            DEFAULT NULL,
    created_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_skills_name (name),
    INDEX idx_skills_category (category)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ────────────────────────────────────────────────
-- TABLE 4: skill_aliases
-- Maps raw/alternate skill names to canonical skill
-- e.g. "ms excel" -> "Excel", "python programming" -> "Python"
-- ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS skill_aliases (
    id          INT             NOT NULL AUTO_INCREMENT,
    skill_id    INT             NOT NULL,
    alias_name  VARCHAR(150)    NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_skill_aliases_alias (alias_name),
    INDEX idx_skill_aliases_skill_id (skill_id),
    CONSTRAINT fk_skill_aliases_skill_id
        FOREIGN KEY (skill_id) REFERENCES skills(id)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ────────────────────────────────────────────────
-- TABLE 5: student_skills
-- Student's self-declared or resume-extracted skills
-- ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS student_skills (
    id                  INT             NOT NULL AUTO_INCREMENT,
    student_id          INT             NOT NULL,
    skill_id            INT             NOT NULL,
    proficiency_level   ENUM('Beginner','Intermediate','Advanced') NOT NULL DEFAULT 'Beginner',
    source              ENUM('manual','resume','course') NOT NULL DEFAULT 'manual',
    created_at          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_student_skill (student_id, skill_id),
    INDEX idx_student_skills_student_id (student_id),
    INDEX idx_student_skills_skill_id (skill_id),
    CONSTRAINT fk_student_skills_student_id
        FOREIGN KEY (student_id) REFERENCES students(id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_student_skills_skill_id
        FOREIGN KEY (skill_id) REFERENCES skills(id)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ────────────────────────────────────────────────
-- TABLE 6: resumes
-- Uploaded resume file metadata (not binary content)
-- ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS resumes (
    id              INT             NOT NULL AUTO_INCREMENT,
    student_id      INT             NOT NULL,
    original_name   VARCHAR(255)    NOT NULL,
    stored_filename VARCHAR(255)    NOT NULL,
    file_path       VARCHAR(500)    NOT NULL,
    file_type       ENUM('pdf','docx') NOT NULL,
    file_size_kb    INT             DEFAULT NULL,
    extracted_text  MEDIUMTEXT      DEFAULT NULL,
    is_active       TINYINT(1)      NOT NULL DEFAULT 1,
    uploaded_at     DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_resumes_student_id (student_id),
    CONSTRAINT fk_resumes_student_id
        FOREIGN KEY (student_id) REFERENCES students(id)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ────────────────────────────────────────────────
-- TABLE 7: certifications
-- Student certifications and credentials
-- ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS certifications (
    id              INT             NOT NULL AUTO_INCREMENT,
    student_id      INT             NOT NULL,
    title           VARCHAR(255)    NOT NULL,
    issuing_org     VARCHAR(255)    DEFAULT NULL,
    issue_date      DATE            DEFAULT NULL,
    expiry_date     DATE            DEFAULT NULL,
    credential_url  VARCHAR(500)    DEFAULT NULL,
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_certifications_student_id (student_id),
    CONSTRAINT fk_certifications_student_id
        FOREIGN KEY (student_id) REFERENCES students(id)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ────────────────────────────────────────────────
-- TABLE 8: projects
-- Student academic/personal projects
-- ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS projects (
    id              INT             NOT NULL AUTO_INCREMENT,
    student_id      INT             NOT NULL,
    title           VARCHAR(255)    NOT NULL,
    description     TEXT            DEFAULT NULL,
    tech_stack      VARCHAR(500)    DEFAULT NULL,
    project_url     VARCHAR(500)    DEFAULT NULL,
    start_date      DATE            DEFAULT NULL,
    end_date        DATE            DEFAULT NULL,
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_projects_student_id (student_id),
    CONSTRAINT fk_projects_student_id
        FOREIGN KEY (student_id) REFERENCES students(id)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ────────────────────────────────────────────────
-- TABLE 9: internships
-- Student internship experience records
-- ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS internships (
    id              INT             NOT NULL AUTO_INCREMENT,
    student_id      INT             NOT NULL,
    company_name    VARCHAR(255)    NOT NULL,
    role_title      VARCHAR(255)    NOT NULL,
    description     TEXT            DEFAULT NULL,
    start_date      DATE            DEFAULT NULL,
    end_date        DATE            DEFAULT NULL,
    is_current      TINYINT(1)      NOT NULL DEFAULT 0,
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_internships_student_id (student_id),
    CONSTRAINT fk_internships_student_id
        FOREIGN KEY (student_id) REFERENCES students(id)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ────────────────────────────────────────────────
-- TABLE 10: job_roles
-- High-level career target categories
-- e.g. "Data Analyst", "Backend Developer"
-- ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS job_roles (
    id          INT             NOT NULL AUTO_INCREMENT,
    title       VARCHAR(150)    NOT NULL,
    department  VARCHAR(100)    DEFAULT NULL,
    description TEXT            DEFAULT NULL,
    created_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_job_roles_title (title),
    INDEX idx_job_roles_department (department)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ────────────────────────────────────────────────
-- TABLE 11: job_descriptions
-- Detailed job postings linked to a job role
-- ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS job_descriptions (
    id              INT             NOT NULL AUTO_INCREMENT,
    job_role_id     INT             NOT NULL,
    title           VARCHAR(255)    NOT NULL,
    company_name    VARCHAR(255)    DEFAULT NULL,
    description_text TEXT           NOT NULL,
    min_experience  VARCHAR(50)     DEFAULT '0 years',
    location        VARCHAR(150)    DEFAULT NULL,
    is_active       TINYINT(1)      NOT NULL DEFAULT 1,
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_job_descriptions_job_role_id (job_role_id),
    INDEX idx_job_descriptions_is_active (is_active),
    CONSTRAINT fk_job_descriptions_job_role_id
        FOREIGN KEY (job_role_id) REFERENCES job_roles(id)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ────────────────────────────────────────────────
-- TABLE 12: job_skills
-- Skills required by a job description (with importance weight)
-- importance_weight: 1=Nice to have, 5=Must have
-- ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS job_skills (
    id                  INT             NOT NULL AUTO_INCREMENT,
    job_description_id  INT             NOT NULL,
    skill_id            INT             NOT NULL,
    importance_weight   TINYINT         NOT NULL DEFAULT 3 CHECK (importance_weight >= 1 AND importance_weight <= 5),
    PRIMARY KEY (id),
    UNIQUE KEY uq_job_skill (job_description_id, skill_id),
    INDEX idx_job_skills_jd_id (job_description_id),
    INDEX idx_job_skills_skill_id (skill_id),
    CONSTRAINT fk_job_skills_jd_id
        FOREIGN KEY (job_description_id) REFERENCES job_descriptions(id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_job_skills_skill_id
        FOREIGN KEY (skill_id) REFERENCES skills(id)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ────────────────────────────────────────────────
-- TABLE 13: skill_gap_analysis
-- Snapshot of a student's gap analysis for a job role
-- ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS skill_gap_analysis (
    id                      INT             NOT NULL AUTO_INCREMENT,
    student_id              INT             NOT NULL,
    job_role_id             INT             NOT NULL,
    job_description_id      INT             DEFAULT NULL,
    unweighted_coverage_pct DECIMAL(5,2)    DEFAULT NULL,
    weighted_coverage_pct   DECIMAL(5,2)    DEFAULT NULL,
    cosine_similarity_score DECIMAL(5,4)    DEFAULT NULL,
    analyzed_at             DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_sga_student_id (student_id),
    INDEX idx_sga_job_role_id (job_role_id),
    INDEX idx_sga_analyzed_at (analyzed_at),
    CONSTRAINT fk_sga_student_id
        FOREIGN KEY (student_id) REFERENCES students(id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_sga_job_role_id
        FOREIGN KEY (job_role_id) REFERENCES job_roles(id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_sga_job_description_id
        FOREIGN KEY (job_description_id) REFERENCES job_descriptions(id)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ────────────────────────────────────────────────
-- TABLE 14: gap_skills
-- Per-skill result from a gap analysis (Matched/Missing/Extra)
-- ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS gap_skills (
    id          INT             NOT NULL AUTO_INCREMENT,
    analysis_id INT             NOT NULL,
    skill_id    INT             NOT NULL,
    status      ENUM('Matched','Missing','Extra') NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_gap_skill (analysis_id, skill_id),
    INDEX idx_gap_skills_analysis_id (analysis_id),
    INDEX idx_gap_skills_skill_id (skill_id),
    CONSTRAINT fk_gap_skills_analysis_id
        FOREIGN KEY (analysis_id) REFERENCES skill_gap_analysis(id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_gap_skills_skill_id
        FOREIGN KEY (skill_id) REFERENCES skills(id)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ────────────────────────────────────────────────
-- TABLE 15: courses
-- Course catalog for recommendations
-- ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS courses (
    id              INT             NOT NULL AUTO_INCREMENT,
    title           VARCHAR(255)    NOT NULL,
    provider        VARCHAR(150)    DEFAULT NULL,
    difficulty_level ENUM('Beginner','Intermediate','Advanced') NOT NULL DEFAULT 'Beginner',
    duration_hours  DECIMAL(6,1)    DEFAULT NULL,
    rating          DECIMAL(3,2)    DEFAULT NULL CHECK (rating >= 0 AND rating <= 5),
    url             VARCHAR(500)    DEFAULT NULL,
    description     TEXT            DEFAULT NULL,
    is_free         TINYINT(1)      NOT NULL DEFAULT 0,
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_courses_difficulty (difficulty_level),
    INDEX idx_courses_rating (rating)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ────────────────────────────────────────────────
-- TABLE 16: course_skills
-- Maps courses to the skills they teach
-- ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS course_skills (
    id          INT NOT NULL AUTO_INCREMENT,
    course_id   INT NOT NULL,
    skill_id    INT NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_course_skill (course_id, skill_id),
    INDEX idx_course_skills_course_id (course_id),
    INDEX idx_course_skills_skill_id (skill_id),
    CONSTRAINT fk_course_skills_course_id
        FOREIGN KEY (course_id) REFERENCES courses(id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_course_skills_skill_id
        FOREIGN KEY (skill_id) REFERENCES skills(id)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ────────────────────────────────────────────────
-- TABLE 17: learning_path_items
-- Ordered, per-student learning steps (skill + phase)
-- ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS learning_path_items (
    id              INT             NOT NULL AUTO_INCREMENT,
    student_id      INT             NOT NULL,
    analysis_id     INT             DEFAULT NULL,
    skill_id        INT             DEFAULT NULL,
    phase_number    TINYINT         NOT NULL DEFAULT 1,
    phase_label     VARCHAR(100)    DEFAULT NULL,
    item_type       ENUM('skill','project','resume_update') NOT NULL DEFAULT 'skill',
    description     TEXT            DEFAULT NULL,
    is_completed    TINYINT(1)      NOT NULL DEFAULT 0,
    completed_at    DATETIME        DEFAULT NULL,
    display_order   INT             NOT NULL DEFAULT 0,
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_lpi_student_id (student_id),
    INDEX idx_lpi_analysis_id (analysis_id),
    INDEX idx_lpi_skill_id (skill_id),
    CONSTRAINT fk_lpi_student_id
        FOREIGN KEY (student_id) REFERENCES students(id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_lpi_analysis_id
        FOREIGN KEY (analysis_id) REFERENCES skill_gap_analysis(id)
        ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT fk_lpi_skill_id
        FOREIGN KEY (skill_id) REFERENCES skills(id)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ────────────────────────────────────────────────
-- TABLE 18: course_progress
-- Tracks which student is enrolled in / completed which course
-- ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS course_progress (
    id              INT             NOT NULL AUTO_INCREMENT,
    student_id      INT             NOT NULL,
    course_id       INT             NOT NULL,
    status          ENUM('not_started','in_progress','completed') NOT NULL DEFAULT 'not_started',
    started_at      DATETIME        DEFAULT NULL,
    completed_at    DATETIME        DEFAULT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_course_progress (student_id, course_id),
    INDEX idx_course_progress_student_id (student_id),
    INDEX idx_course_progress_course_id (course_id),
    CONSTRAINT fk_course_progress_student_id
        FOREIGN KEY (student_id) REFERENCES students(id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_course_progress_course_id
        FOREIGN KEY (course_id) REFERENCES courses(id)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ────────────────────────────────────────────────
-- TABLE 19: employment_outcomes
-- Placement results per student (used for ML training)
-- ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS employment_outcomes (
    id                  INT             NOT NULL AUTO_INCREMENT,
    student_id          INT             NOT NULL,
    status              ENUM('Placed','Not Placed','In Progress') NOT NULL DEFAULT 'In Progress',
    company_name        VARCHAR(255)    DEFAULT NULL,
    role_title          VARCHAR(255)    DEFAULT NULL,
    salary_package_lpa  DECIMAL(8,2)    DEFAULT NULL,
    placement_date      DATE            DEFAULT NULL,
    placement_type      ENUM('Campus','Off-Campus','Internship-Converted','Unknown') DEFAULT 'Unknown',
    notes               TEXT            DEFAULT NULL,
    updated_at          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_employment_student (student_id),
    INDEX idx_employment_status (status),
    INDEX idx_employment_placement_date (placement_date),
    CONSTRAINT fk_employment_student_id
        FOREIGN KEY (student_id) REFERENCES students(id)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ────────────────────────────────────────────────
-- TABLE 20: skill_progress
-- Tracks improvement in a student's proficiency for a skill over time
-- ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS skill_progress (
    id                  INT             NOT NULL AUTO_INCREMENT,
    student_id          INT             NOT NULL,
    skill_id            INT             NOT NULL,
    old_proficiency     ENUM('Beginner','Intermediate','Advanced') DEFAULT NULL,
    new_proficiency     ENUM('Beginner','Intermediate','Advanced') NOT NULL,
    recorded_at         DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_skill_progress_student_id (student_id),
    INDEX idx_skill_progress_skill_id (skill_id),
    INDEX idx_skill_progress_recorded_at (recorded_at),
    CONSTRAINT fk_skill_progress_student_id
        FOREIGN KEY (student_id) REFERENCES students(id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_skill_progress_skill_id
        FOREIGN KEY (skill_id) REFERENCES skills(id)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ────────────────────────────────────────────────
-- TABLE 21: employment_outcome_skills
-- Junction table linking employment outcomes with the skills utilized in the job
-- ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS employment_outcome_skills (
    id                  INT             NOT NULL AUTO_INCREMENT,
    outcome_id          INT             NOT NULL,
    skill_id            INT             NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_outcome_skill (outcome_id, skill_id),
    INDEX idx_outcome_skills_outcome (outcome_id),
    INDEX idx_outcome_skills_skill (skill_id),
    CONSTRAINT fk_eos_outcome_id
        FOREIGN KEY (outcome_id) REFERENCES employment_outcomes(id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_eos_skill_id
        FOREIGN KEY (skill_id) REFERENCES skills(id)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ────────────────────────────────────────────────
-- TABLE 22: forum_categories
-- Discussion categories for open student & admin forum
-- ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS forum_categories (
    id                  INT             NOT NULL AUTO_INCREMENT,
    name                VARCHAR(100)    NOT NULL,
    slug                VARCHAR(100)    NOT NULL,
    description         VARCHAR(255)    DEFAULT NULL,
    sort_order          INT             NOT NULL DEFAULT 0,
    created_at          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_forum_categories_name (name),
    UNIQUE KEY uq_forum_categories_slug (slug),
    INDEX idx_forum_categories_sort_order (sort_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ────────────────────────────────────────────────
-- TABLE 23: forum_threads
-- Discussion threads created by authenticated users
-- ON DELETE category: RESTRICT (cannot delete category with active threads)
-- ON DELETE user: CASCADE (removing user cleans up their threads)
-- ON DELETE skill: SET NULL (deleting a skill preserves the thread)
-- ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS forum_threads (
    id                  INT             NOT NULL AUTO_INCREMENT,
    category_id         INT             NOT NULL,
    user_id             INT             NOT NULL,
    title               VARCHAR(150)    NOT NULL,
    body                TEXT            NOT NULL,
    skill_id            INT             DEFAULT NULL,
    is_pinned           TINYINT(1)      NOT NULL DEFAULT 0,
    is_locked           TINYINT(1)      NOT NULL DEFAULT 0,
    is_deleted          TINYINT(1)      NOT NULL DEFAULT 0,
    created_at          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    last_activity_at    DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_forum_threads_category (category_id),
    INDEX idx_forum_threads_user (user_id),
    INDEX idx_forum_threads_last_activity (last_activity_at),
    INDEX idx_forum_threads_is_deleted (is_deleted),
    INDEX idx_forum_threads_skill (skill_id),
    CONSTRAINT fk_forum_threads_category
        FOREIGN KEY (category_id) REFERENCES forum_categories(id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_forum_threads_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_forum_threads_skill
        FOREIGN KEY (skill_id) REFERENCES skills(id)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ────────────────────────────────────────────────
-- TABLE 24: forum_posts
-- Flat discussion replies to a thread
-- ON DELETE thread: CASCADE (deleting thread removes replies)
-- ON DELETE user: CASCADE (removing user removes replies)
-- ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS forum_posts (
    id                  INT             NOT NULL AUTO_INCREMENT,
    thread_id           INT             NOT NULL,
    user_id             INT             NOT NULL,
    body                TEXT            NOT NULL,
    is_deleted          TINYINT(1)      NOT NULL DEFAULT 0,
    created_at          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    edited_at           DATETIME        DEFAULT NULL,
    PRIMARY KEY (id),
    INDEX idx_forum_posts_thread (thread_id),
    INDEX idx_forum_posts_user (user_id),
    INDEX idx_forum_posts_created (created_at),
    CONSTRAINT fk_forum_posts_thread
        FOREIGN KEY (thread_id) REFERENCES forum_threads(id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_forum_posts_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ────────────────────────────────────────────────
-- TABLE 25: forum_post_likes
-- Helpful / Upvote marks on threads and posts
-- Target type: 'thread' or 'post'
-- Unique constraint enforces one vote per user per target
-- ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS forum_post_likes (
    id                  INT             NOT NULL AUTO_INCREMENT,
    user_id             INT             NOT NULL,
    target_type         ENUM('thread','post') NOT NULL,
    target_id           INT             NOT NULL,
    created_at          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_forum_likes_user_target (user_id, target_type, target_id),
    INDEX idx_forum_likes_target (target_type, target_id),
    INDEX idx_forum_likes_user (user_id),
    CONSTRAINT fk_forum_likes_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ────────────────────────────────────────────────
-- TABLE 26: forum_reports
-- User reports for inappropriate / abusive discussion content
-- Target type: 'thread' or 'post'
-- Unique constraint prevents reporting the same item multiple times
-- ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS forum_reports (
    id                  INT             NOT NULL AUTO_INCREMENT,
    reporter_id         INT             NOT NULL,
    target_type         ENUM('thread','post') NOT NULL,
    target_id           INT             NOT NULL,
    reason              VARCHAR(300)    NOT NULL,
    status              ENUM('open','resolved','dismissed') NOT NULL DEFAULT 'open',
    created_at          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_by         INT             DEFAULT NULL,
    resolved_at         DATETIME        DEFAULT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_forum_reports_user_target (reporter_id, target_type, target_id),
    INDEX idx_forum_reports_status (status),
    INDEX idx_forum_reports_target (target_type, target_id),
    INDEX idx_forum_reports_reporter (reporter_id),
    CONSTRAINT fk_forum_reports_reporter
        FOREIGN KEY (reporter_id) REFERENCES users(id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_forum_reports_resolver
        FOREIGN KEY (resolved_by) REFERENCES users(id)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

