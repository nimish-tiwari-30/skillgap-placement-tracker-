"""
seed_jobs.py
────────────
Seed script for Job Roles and Job Descriptions (Phase 7).

Run:
    python seed_jobs.py

Idempotent:
    - Safe to run multiple times without duplicate errors or duplicate rows.
    - Checks existing JobRoles by unique title.
    - Checks existing JobDescriptions by (title, company_name).
    - Checks existing JobSkills by (job_description_id, skill_id).

Scope:
    - 11 Job Roles across Data, Software, AI, DevOps, and QA.
    - 22 Realistic Job Descriptions with synthetic company naming ("Demo Corp Alpha", etc.).
    - Automated skill extraction using ml.skill_extractor and weighted importance assignment.
"""

import os
import sys

# Allow running from project root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from extensions import db
from models.job import JobRole, JobDescription, JobSkill
from models.skill import Skill
from ml.skill_extractor import extract_skills_from_text

# ── 1. Job Roles Definition ──────────────────────────────────────────────────
# Format: (title, department, description)
ROLES_DATA = [
    ("Data Analyst", "Data & Analytics", "Extracts insights from large data sets, builds interactive dashboards, and communicates findings to stakeholders."),
    ("Python Developer", "Software Engineering", "Develops backend applications, automated scripts, data processing workflows, and web services using Python."),
    ("Web Developer", "Frontend & Web", "Builds dynamic, mobile-friendly websites and web applications using modern HTML, CSS, JavaScript, and frameworks."),
    ("Business Analyst", "Operations & Strategy", "Analyzes business requirements, models processes, and builds data reports to support executive decision-making."),
    ("ML Engineer", "Artificial Intelligence", "Develops, trains, and deploys scalable machine learning models and end-to-end data pipelines in production."),
    ("Data Scientist", "Data Science", "Applies advanced statistics, predictive modeling, machine learning, and data analytics to solve complex business problems."),
    ("DevOps Engineer", "Cloud & Infrastructure", "Manages automated CI/CD deployment pipelines, containerization, cloud infrastructure, and operational reliability."),
    ("Backend Developer", "Software Engineering", "Architects scalable server-side systems, relational databases, REST APIs, and microservices."),
    ("Frontend Developer", "Frontend & Web", "Creates interactive, accessible user interfaces and high-performance frontend components using modern JS frameworks."),
    ("Software Tester", "Quality Assurance", "Executes manual and automated testing suites, writes test plans, reports bugs, and ensures software quality."),
    ("Cloud Engineer", "Cloud & Infrastructure", "Designs, provisions, and maintains enterprise cloud infrastructure on AWS, ensuring security and uptime.")
]

# ── 2. Job Descriptions Data (Realistic Synthetic Demo Postings) ─────────────
# All companies clearly marked with "Demo" prefix.
JOBS_DATA = [
    # ── Role: Data Analyst (3 postings) ──────────────────────────────────────
    {
        "role": "Data Analyst",
        "title": "Junior Data Analyst",
        "company": "Demo Analytics Alpha",
        "location": "Bangalore",
        "min_experience": "0-1 years",
        "text": """We are looking for a motivated Data Analyst with strong hands-on experience in Python, SQL, Power BI, Excel, and Statistics.
The analyst will query relational databases, perform exploratory data analysis, clean raw tabular data, and prepare weekly KPI reports for leadership."""
    },
    {
        "role": "Data Analyst",
        "title": "BI & Data Analyst",
        "company": "Demo Insights Corp",
        "location": "Remote",
        "min_experience": "1-2 years",
        "text": """Demo Insights Corp is hiring a Data Analyst to lead business reporting.
Required qualifications include proficiency in SQL, Tableau, Excel, and Pandas. You should have practical experience in data visualization, writing complex MySQL queries, and strong Communication skills to present insights."""
    },
    {
        "role": "Data Analyst",
        "title": "Commercial Data Analyst",
        "company": "Demo Retail Labs",
        "location": "Mumbai",
        "min_experience": "1-3 years",
        "text": """Looking for an energetic Data Analyst proficient in SQL, Python, Excel, Power BI, and Statistics.
Responsibilities include tracking customer retention metrics, developing dashboards in Power BI, and collaborating closely with our sales teams."""
    },

    # ── Role: Python Developer (2 postings) ──────────────────────────────────
    {
        "role": "Python Developer",
        "title": "Python Backend Engineer",
        "company": "Demo Software Beta",
        "location": "Pune",
        "min_experience": "0-2 years",
        "text": """Demo Software Beta seeks a Python Developer. Must have experience building server applications with Python, Flask, MySQL, and REST API design.
Version control with Git and familiarity with Linux and Postman for API testing are required."""
    },
    {
        "role": "Python Developer",
        "title": "Django Software Developer",
        "company": "Demo Systems Gamma",
        "location": "Hyderabad",
        "min_experience": "1-3 years",
        "text": """We are seeking a Python Developer with in-depth knowledge of Python, Django, PostgreSQL, and Redis.
The candidate will build scalable backend services, integrate REST APIs, and use Git and Docker for local development workflows."""
    },

    # ── Role: Web Developer (2 postings) ────────────────────────────────────
    {
        "role": "Web Developer",
        "title": "Full Stack Web Developer",
        "company": "Demo Web Matrix",
        "location": "Delhi NCR",
        "min_experience": "0-2 years",
        "text": """Demo Web Matrix is hiring a Web Developer skilled in HTML, CSS, JavaScript, Bootstrap, Node.js, and MongoDB.
You will be responsible for creating modern responsive web pages, developing backend REST APIs, and collaborating in Git workflows."""
    },
    {
        "role": "Web Developer",
        "title": "Junior Web Developer",
        "company": "Demo Interactive Delta",
        "location": "Remote",
        "min_experience": "0-1 years",
        "text": """Entry level Web Developer position. We require solid foundational knowledge in HTML, CSS, JavaScript, Bootstrap, and GitHub.
You will assist in converting Figma mockups into responsive browser interfaces with clean semantic code."""
    },

    # ── Role: Business Analyst (2 postings) ──────────────────────────────────
    {
        "role": "Business Analyst",
        "title": "Business Analyst - Operations",
        "company": "Demo Global Consulting",
        "location": "Gurugram",
        "min_experience": "1-2 years",
        "text": """Demo Global Consulting is hiring a Business Analyst. Candidates must possess practical proficiency in Excel, SQL, Power BI, and Communication.
You will gather business requirements, document project specifications, and build executive dashboards."""
    },
    {
        "role": "Business Analyst",
        "title": "Associate Business Analyst",
        "company": "Demo Fintech Solutions",
        "location": "Bangalore",
        "min_experience": "0-1 years",
        "text": """Demo Fintech Solutions seeks an Associate Business Analyst. Requirements include strong analytical Problem Solving, Excel, Tableau, and SQL.
The role involves analyzing transaction funnels and preparing reports for product management."""
    },

    # ── Role: ML Engineer (2 postings) ──────────────────────────────────────
    {
        "role": "ML Engineer",
        "title": "Associate Machine Learning Engineer",
        "company": "Demo AI Innovations",
        "location": "Bengaluru",
        "min_experience": "1-2 years",
        "text": """Join Demo AI Innovations as an ML Engineer. The candidate must have hands-on experience with Python, Machine Learning, scikit-learn, Pandas, and NumPy.
Experience with TensorFlow or Deep Learning and tracking experiments using Jupyter Notebook is highly desirable."""
    },
    {
        "role": "ML Engineer",
        "title": "NLP & ML Systems Engineer",
        "company": "Demo Cognitive Tech",
        "location": "Remote",
        "min_experience": "1-3 years",
        "text": """Demo Cognitive Tech is seeking an ML Engineer. Primary requirements: Python, Machine Learning, NLP, scikit-learn, and Docker.
You will train text classification models, deploy inference endpoints via Flask, and manage versioning with Git."""
    },

    # ── Role: Data Scientist (2 postings) ────────────────────────────────────
    {
        "role": "Data Scientist",
        "title": "Junior Data Scientist",
        "company": "Demo Data Ventures",
        "location": "Hyderabad",
        "min_experience": "0-2 years",
        "text": """Demo Data Ventures is seeking a Junior Data Scientist. We require solid capabilities in Python, Statistics, Machine Learning, Pandas, and SQL.
You will analyze customer datasets, build predictive regression and classification models, and communicate insights to leaders."""
    },
    {
        "role": "Data Scientist",
        "title": "Data Scientist - Analytics",
        "company": "Demo Health Analytics",
        "location": "Chennai",
        "min_experience": "1-3 years",
        "text": """We are hiring a Data Scientist. Essential skill set includes Python, R, Statistics, Machine Learning, and Tableau.
Responsibilities include hypothesis testing, building statistical models, and visualizing complex biomedical data."""
    },

    # ── Role: DevOps Engineer (2 postings) ──────────────────────────────────
    {
        "role": "DevOps Engineer",
        "title": "Cloud DevOps Engineer",
        "company": "Demo Cloud Dynamics",
        "location": "Pune",
        "min_experience": "1-3 years",
        "text": """Demo Cloud Dynamics is hiring a DevOps Engineer. Requirements include Linux, Docker, Kubernetes, AWS, CI/CD, and Git.
You will automate application deployments, maintain cloud infrastructure, and ensure high availability of services."""
    },
    {
        "role": "DevOps Engineer",
        "title": "Junior DevOps & Systems Engineer",
        "company": "Demo Ops Platform",
        "location": "Remote",
        "min_experience": "0-2 years",
        "text": """Looking for a Junior DevOps Engineer with strong Linux, Docker, Git, CI/CD, and AWS skills.
You will manage container images, write automation scripts, and assist in monitoring application logs and metrics."""
    },

    # ── Role: Backend Developer (2 postings) ────────────────────────────────
    {
        "role": "Backend Developer",
        "title": "Backend Software Engineer",
        "company": "Demo CloudStack Systems",
        "location": "Bangalore",
        "min_experience": "1-3 years",
        "text": """Demo CloudStack Systems is looking for a Backend Developer. Required technical skills: Java, MySQL, REST API, Git, and Docker.
Familiarity with building scalable microservices and implementing authentication and database indexing is expected."""
    },
    {
        "role": "Backend Developer",
        "title": "Node.js Backend Developer",
        "company": "Demo NextGen Tech",
        "location": "Remote",
        "min_experience": "0-2 years",
        "text": """We are looking for a Backend Developer specializing in Node.js, JavaScript, MongoDB, Redis, and REST API.
You will design high-throughput APIs, manage database schemas, and write unit tests for backend modules."""
    },

    # ── Role: Frontend Developer (2 postings) ───────────────────────────────
    {
        "role": "Frontend Developer",
        "title": "Frontend React Developer",
        "company": "Demo Pixel Studios",
        "location": "Noida",
        "min_experience": "1-2 years",
        "text": """Demo Pixel Studios seeks a Frontend Developer proficient in React, JavaScript, HTML, CSS, and Figma.
The developer will create responsive user interfaces, integrate REST API endpoints, and maintain UI component libraries."""
    },
    {
        "role": "Frontend Developer",
        "title": "UI / Frontend Developer",
        "company": "Demo Digital UI",
        "location": "Remote",
        "min_experience": "0-2 years",
        "text": """We are looking for a passionate Frontend Developer with strong skills in TypeScript, React, HTML, CSS, and Bootstrap.
You will translate design wireframes into clean, interactive web experiences with attention to cross-browser performance."""
    },

    # ── Role: Software Tester (2 postings) ──────────────────────────────────
    {
        "role": "Software Tester",
        "title": "QA & Automation Test Engineer",
        "company": "Demo Enterprise QA",
        "location": "Bangalore",
        "min_experience": "1-2 years",
        "text": """Demo Enterprise QA seeks a Software Tester. Must have practical experience with Selenium, Automated Testing, Manual Testing, JIRA, and Postman.
You will design automated test scripts, perform regression testing, and log defect reports."""
    },
    {
        "role": "Software Tester",
        "title": "Junior Software Test Engineer",
        "company": "Demo Quality Labs",
        "location": "Hyderabad",
        "min_experience": "0-1 years",
        "text": """Entry level Software Tester role. Requirements: Manual Testing, JIRA, Unit Testing, Python, and Communication.
You will write test cases, perform functional testing across web applications, and collaborate with developers to verify fixes."""
    },

    # ── Role: Cloud Engineer (1 posting) ────────────────────────────────────
    {
        "role": "Cloud Engineer",
        "title": "AWS Cloud Solutions Engineer",
        "company": "Demo Sky Systems",
        "location": "Bangalore",
        "min_experience": "1-3 years",
        "text": """Demo Sky Systems is hiring a Cloud Engineer with deep expertise in AWS, Linux, Docker, Kubernetes, and Git.
You will architect serverless services, configure security policies, and manage cloud migration projects."""
    },

    # ── Additional Synthetic Postings for Multi-Job Company Skill Gap ─────────
    # Ensures at least 8 companies have 2-3 jobs each in diverse roles.
    # Clearly synthetic demo data marked with 'Demo' prefix.

    # 1. Demo Analytics Alpha (adds Python Developer & Data Scientist)
    {
        "role": "Python Developer",
        "title": "Analytics Backend Engineer",
        "company": "Demo Analytics Alpha",
        "location": "Bangalore",
        "min_experience": "1-2 years",
        "text": """Demo Analytics Alpha is seeking a Python Backend Engineer to build analytics data APIs.
Requires hands-on experience in Python, SQL, Flask, Git, and Linux. Familiarity with relational data modeling is required."""
    },
    {
        "role": "Data Scientist",
        "title": "Data Science Specialist",
        "company": "Demo Analytics Alpha",
        "location": "Bangalore",
        "min_experience": "1-3 years",
        "text": """Join Demo Analytics Alpha as a Data Scientist.
Must have strong expertise in Python, Machine Learning, Statistics, Pandas, and SQL to create predictive models for business analytics."""
    },

    # 2. Demo Software Beta (adds Frontend Developer & DevOps Engineer)
    {
        "role": "Frontend Developer",
        "title": "Frontend React Developer",
        "company": "Demo Software Beta",
        "location": "Pune",
        "min_experience": "0-2 years",
        "text": """Demo Software Beta seeks a Frontend Developer proficient in React, JavaScript, HTML, CSS, and Git.
You will build modern, accessible web client interfaces and integrate RESTful APIs."""
    },
    {
        "role": "DevOps Engineer",
        "title": "DevOps CI/CD Engineer",
        "company": "Demo Software Beta",
        "location": "Pune",
        "min_experience": "1-3 years",
        "text": """Demo Software Beta is hiring a DevOps Engineer.
Key requirements include Docker, Git, Linux, AWS, and Postman. Experience automating integration and deployment pipelines is required."""
    },

    # 3. Demo Systems Gamma (adds Backend Developer & Cloud Engineer)
    {
        "role": "Backend Developer",
        "title": "Full Stack Backend Engineer",
        "company": "Demo Systems Gamma",
        "location": "Hyderabad",
        "min_experience": "1-2 years",
        "text": """Demo Systems Gamma is expanding our server engineering team.
Requires Python, PostgreSQL, Docker, Redis, and Git. You will design database schemas and build resilient backend web services."""
    },
    {
        "role": "Cloud Engineer",
        "title": "Cloud Infrastructure Specialist",
        "company": "Demo Systems Gamma",
        "location": "Hyderabad",
        "min_experience": "2-3 years",
        "text": """Looking for a Cloud Engineer at Demo Systems Gamma.
Must have solid experience with AWS, Docker, Kubernetes, Linux, and Git to maintain cloud deployments and container clusters."""
    },

    # 4. Demo AI Innovations (adds Data Scientist & Python Developer)
    {
        "role": "Data Scientist",
        "title": "Applied Data Scientist",
        "company": "Demo AI Innovations",
        "location": "Bengaluru",
        "min_experience": "1-3 years",
        "text": """Demo AI Innovations seeks a Data Scientist.
Requirements: Python, Machine Learning, Deep Learning, Statistics, Pandas, and SQL. Focus on training neural models and data analysis."""
    },
    {
        "role": "Python Developer",
        "title": "AI Platform Python Developer",
        "company": "Demo AI Innovations",
        "location": "Bengaluru",
        "min_experience": "1-2 years",
        "text": """Develop AI service backends at Demo AI Innovations.
Requires Python, Flask, Docker, Git, and MySQL. Experience deploying REST APIs for machine learning inference is a plus."""
    },

    # 5. Demo Cloud Dynamics (adds Cloud Engineer & Backend Developer)
    {
        "role": "Cloud Engineer",
        "title": "Cloud Solutions Architect",
        "company": "Demo Cloud Dynamics",
        "location": "Noida",
        "min_experience": "1-3 years",
        "text": """Demo Cloud Dynamics is hiring a Cloud Solutions Engineer.
Must have practical knowledge of AWS, Docker, Kubernetes, Linux, and Git to automate scalable cloud systems."""
    },
    {
        "role": "Backend Developer",
        "title": "Infrastructure Backend Engineer",
        "company": "Demo Cloud Dynamics",
        "location": "Noida",
        "min_experience": "1-2 years",
        "text": """Demo Cloud Dynamics seeks a Backend Developer.
Requirements include Python, REST API, Docker, MySQL, and Linux for building scalable infrastructure management APIs."""
    },

    # 6. Demo NextGen Tech (adds Frontend Developer & Software Tester)
    {
        "role": "Frontend Developer",
        "title": "Modern Frontend UI Engineer",
        "company": "Demo NextGen Tech",
        "location": "Remote",
        "min_experience": "1-2 years",
        "text": """Demo NextGen Tech seeks a Frontend UI Engineer.
Requires HTML, CSS, JavaScript, React, and Figma. Build responsive components and interactive dashboards."""
    },
    {
        "role": "Software Tester",
        "title": "Web Quality Assurance Engineer",
        "company": "Demo NextGen Tech",
        "location": "Remote",
        "min_experience": "0-2 years",
        "text": """Demo NextGen Tech is looking for a QA Engineer.
Key skills: Selenium, Unit Testing, Python, JIRA, and Postman for automated and regression web testing."""
    },

    # 7. Demo Quality Labs (adds Software Tester & Web Developer)
    {
        "role": "Software Tester",
        "title": "Automation Test Specialist",
        "company": "Demo Quality Labs",
        "location": "Hyderabad",
        "min_experience": "1-2 years",
        "text": """Demo Quality Labs is looking for an Automation Test Specialist.
Hands-on experience in Selenium, Python, Unit Testing, Git, and JIRA is required to develop robust test automation suites."""
    },
    {
        "role": "Web Developer",
        "title": "QA Web Tooling Developer",
        "company": "Demo Quality Labs",
        "location": "Hyderabad",
        "min_experience": "1-2 years",
        "text": """Build internal test verification tools at Demo Quality Labs.
Requires JavaScript, HTML, CSS, Git, and Postman. You will build dashboards for test reports."""
    },

    # 8. Demo Sky Systems (adds DevOps Engineer & Data Analyst)
    {
        "role": "DevOps Engineer",
        "title": "Cloud DevOps Engineer",
        "company": "Demo Sky Systems",
        "location": "Bangalore",
        "min_experience": "1-3 years",
        "text": """Demo Sky Systems seeks a DevOps Engineer.
Key qualifications: Docker, Kubernetes, AWS, Linux, and Git. Automate cloud deployments and monitoring."""
    },
    {
        "role": "Data Analyst",
        "title": "Cloud Cost & Data Analyst",
        "company": "Demo Sky Systems",
        "location": "Bangalore",
        "min_experience": "1-2 years",
        "text": """Demo Sky Systems is hiring a Data Analyst for cloud usage reporting.
Proficiency in SQL, Python, Power BI, Excel, and AWS. Analyze resource consumption patterns and create visual summaries."""
    }
]


def seed_jobs(app=None):
    """Seed job roles, descriptions, and auto-extract skills with weights."""
    from flask import has_app_context

    def _do_seed():
        print("-- Seeding Job Roles & Job Descriptions ---------------------")

        # 1. Seed Roles
        role_map = {}
        added_roles = 0
        existing_roles = 0

        for title, dept, desc in ROLES_DATA:
            role = JobRole.query.filter(db.func.lower(JobRole.title) == title.lower()).first()
            if not role:
                role = JobRole(title=title, department=dept, description=desc)
                db.session.add(role)
                db.session.flush()
                added_roles += 1
            else:
                existing_roles += 1
            role_map[title] = role

        db.session.commit()
        print(f"[OK] Roles: {added_roles} added, {existing_roles} already existed. Total: {len(role_map)}")

        # 2. Seed Job Descriptions & Skills
        added_jobs = 0
        existing_jobs = 0
        total_job_skills_created = 0

        for item in JOBS_DATA:
            role = role_map.get(item["role"])
            if not role:
                continue

            # Check if job already exists
            existing_job = JobDescription.query.filter_by(
                title=item["title"],
                company_name=item["company"]
            ).first()

            if existing_job:
                job = existing_job
                existing_jobs += 1
            else:
                job = JobDescription(
                    job_role_id=role.id,
                    title=item["title"],
                    company_name=item["company"],
                    location=item["location"],
                    min_experience=item["min_experience"],
                    description_text=item["text"].strip(),
                    is_active=True
                )
                db.session.add(job)
                db.session.flush()
                added_jobs += 1

            # Extract skills from JD text
            extracted = extract_skills_from_text(job.description_text)
            
            # Map importance weights:
            # Top extracted skills get weight 5 (Critical) or 4 (High), secondary get 3 (Required)
            existing_skills = {js.skill_id for js in JobSkill.query.filter_by(job_description_id=job.id).all()}

            for idx, ext_item in enumerate(extracted):
                sid = ext_item.get("skill_id")
                if not sid:
                    continue

                if sid not in existing_skills:
                    # Assign sensible importance weights:
                    # Primary/top 2 detected skills -> 5 or 4, next skills -> 3
                    if idx == 0:
                        weight = 5  # Critical
                    elif idx == 1:
                        weight = 4  # Highly Important
                    elif idx == 2:
                        weight = 3  # Required
                    elif idx == 3:
                        weight = 3  # Required
                    else:
                        weight = 2  # Desirable

                    js = JobSkill(
                        job_description_id=job.id,
                        skill_id=sid,
                        importance_weight=weight
                    )
                    db.session.add(js)
                    existing_skills.add(sid)
                    total_job_skills_created += 1

        db.session.commit()

        total_roles = JobRole.query.count()
        total_jobs = JobDescription.query.count()
        total_js = JobSkill.query.count()

        print(f"[OK] Jobs: {added_jobs} added, {existing_jobs} already existed. Total: {total_jobs}")
        print(f"[OK] JobSkills: {total_job_skills_created} newly created. Total active job_skills: {total_js}")
        print(f"-- Verification ---------------------------------------------")
        print(f"  Roles >= 10: {total_roles >= 10} ({total_roles} found)")
        print(f"  Jobs  >= 20: {total_jobs >= 20} ({total_jobs} found)")
        assert total_roles >= 10, f"Expected >= 10 roles, got {total_roles}"
        assert total_jobs >= 20, f"Expected >= 20 jobs, got {total_jobs}"
        print("[PASS] Seed jobs completed successfully and verified!")

    if has_app_context():
        _do_seed()
    else:
        if app is None:
            app = create_app()
        with app.app_context():
            _do_seed()


if __name__ == '__main__':
    seed_jobs()
