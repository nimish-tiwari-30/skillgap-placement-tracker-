"""
seed_courses.py
───────────────
Starter courses catalog seed script for Phase 10 (Course Recommendation).

Run:  python seed_courses.py
Safe to run multiple times — idempotent (skips or updates existing courses).

Coverage:
  38+ real-world courses across all skill categories (Programming, Data & Analytics,
  Web, Database, Cloud/DevOps, AI/ML, Tools), tagged with canonical skill names
  from seed_skills.py.
"""

import os
import sys

# Allow running directly from project root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from extensions import db
from models.course import Course, CourseSkill
from models.skill import Skill


# Format:
# (title, provider, difficulty, duration_hours, rating, is_free, url, description, [skill_canonical_names])
COURSES = [
    # ── Programming ─────────────────────────────────────────────────────────────
    (
        "Python for Everybody Specialization",
        "Coursera / Univ. of Michigan",
        "Beginner",
        36.0,
        4.8,
        False,
        "https://www.coursera.org/specializations/python",
        "Learn to program and analyze data with Python. Covers data structures, networked APIs, and databases.",
        ["Python", "SQL", "SQLite"]
    ),
    (
        "Complete Python Developer in 2026: Zero to Mastery",
        "Udemy",
        "Beginner",
        30.5,
        4.7,
        False,
        "https://www.udemy.com/course/complete-python-developer-zero-to-mastery/",
        "Master modern Python 3 fundamentals, OOP, functional programming, testing, and script automation.",
        ["Python", "Git", "VS Code"]
    ),
    (
        "Advanced Python: Clean Code & Design Patterns",
        "Pluralsight",
        "Advanced",
        18.0,
        4.6,
        False,
        "https://www.pluralsight.com/courses/python-clean-coding",
        "Deep dive into decorators, generators, metaclasses, context managers, and architectural design patterns.",
        ["Python"]
    ),
    (
        "Java Programming Masterclass 2026",
        "Udemy",
        "Beginner",
        45.0,
        4.7,
        False,
        "https://www.udemy.com/course/java-the-complete-java-developer-course/",
        "Comprehensive guide to core Java, OOP concepts, lambdas, streams, multi-threading, and unit testing.",
        ["Java", "Git"]
    ),
    (
        "Advanced Java Development & Spring Microservices",
        "edX",
        "Advanced",
        28.0,
        4.6,
        False,
        "https://www.edx.org/course/advanced-java-spring",
        "Enterprise-grade distributed systems with Spring Boot, JPA, microservices architecture, and caching.",
        ["Java", "PostgreSQL", "Redis"]
    ),
    (
        "C++ Programming: From Beginner to Beyond",
        "Udemy",
        "Intermediate",
        35.0,
        4.6,
        False,
        "https://www.udemy.com/course/beginning-c-plus-plus-programming/",
        "Modern C++ (C++11/14/17/20), pointers, memory management, STL containers, and algorithm design.",
        ["C++", "C"]
    ),
    (
        "The Complete JavaScript Course 2026: From Zero to Expert!",
        "Udemy",
        "Beginner",
        52.0,
        4.8,
        False,
        "https://www.udemy.com/course/the-complete-javascript-course/",
        "The modern JavaScript course for everyone. Master modern ES6+, async/await, DOM manipulation, and architecture.",
        ["JavaScript", "HTML", "CSS"]
    ),
    (
        "Understanding TypeScript & Modern Tooling",
        "Udemy",
        "Intermediate",
        15.0,
        4.7,
        False,
        "https://www.udemy.com/course/understanding-typescript/",
        "Boost JavaScript with types, generics, decorators, compiler options, and TypeScript with React/Node.",
        ["TypeScript", "JavaScript"]
    ),
    (
        "Go: The Complete Developer's Guide (Golang)",
        "Udemy",
        "Beginner",
        12.0,
        4.7,
        False,
        "https://www.udemy.com/course/go-the-complete-developers-guide/",
        "Master the fundamentals and advanced features of the Go programming language including goroutines and channels.",
        ["Go"]
    ),
    (
        "Android App Development with Kotlin",
        "Google Developers / Coursera",
        "Intermediate",
        24.0,
        4.6,
        True,
        "https://developer.android.com/courses",
        "Build robust modern Android applications using Kotlin, Android Studio, Jetpack Compose, and Coroutines.",
        ["Kotlin"]
    ),

    # ── Data & Analytics ────────────────────────────────────────────────────────
    (
        "The Complete SQL Bootcamp: Go from Zero to Hero",
        "Udemy",
        "Beginner",
        16.0,
        4.7,
        False,
        "https://www.udemy.com/course/the-complete-sql-bootcamp/",
        "Learn how to read and write complex queries to a database using PostgreSQL, aggregation, and window functions.",
        ["SQL", "PostgreSQL"]
    ),
    (
        "Advanced SQL for Data Analysts & Scientists",
        "DataCamp",
        "Advanced",
        14.0,
        4.8,
        False,
        "https://www.datacamp.com/courses/advanced-sql",
        "CTEs, window functions, query performance optimization, indexing, and complex data transformations.",
        ["SQL", "PostgreSQL", "MySQL"]
    ),
    (
        "Data Analysis with Python and Pandas",
        "Coursera / IBM",
        "Intermediate",
        20.0,
        4.6,
        False,
        "https://www.coursera.org/learn/data-analysis-with-python",
        "Import, clean, manipulate, and visualize real-world datasets with Pandas, NumPy, and Matplotlib.",
        ["Python", "Pandas", "NumPy", "Jupyter Notebook"]
    ),
    (
        "Microsoft Excel: Advanced Excel Formulas & Functions",
        "Udemy",
        "Intermediate",
        11.5,
        4.7,
        False,
        "https://www.udemy.com/course/advanced-excel-formulas-functions/",
        "Master 75+ Excel formulas, dynamic arrays, XLOOKUP, INDEX/MATCH, and automated spreadsheet reporting.",
        ["Excel"]
    ),
    (
        "Microsoft Power BI Desktop for Business Intelligence",
        "Udemy",
        "Beginner",
        18.0,
        4.7,
        False,
        "https://www.udemy.com/course/microsoft-power-bi-up-running-with-power-bi-desktop/",
        "Transform raw data into interactive dashboards. Master data modeling, DAX measures, and report publishing.",
        ["Power BI", "Excel", "SQL"]
    ),
    (
        "Tableau 2026 A-Z: Hands-On Tableau Training for Data Science",
        "Udemy",
        "Beginner",
        10.5,
        4.6,
        False,
        "https://www.udemy.com/course/tableau10/",
        "Create high-impact visualizations and stories in Tableau. Covers calculated fields, parameters, and dashboards.",
        ["Tableau"]
    ),
    (
        "Statistics and Probability for Data Science",
        "Khan Academy",
        "Beginner",
        15.0,
        4.8,
        True,
        "https://www.khanacademy.org/math/statistics-probability",
        "Foundational statistics: descriptive stats, normal distributions, confidence intervals, and hypothesis testing.",
        ["Statistics", "R"]
    ),

    # ── Web Development ─────────────────────────────────────────────────────────
    (
        "Responsive Web Design Fundamentals",
        "freeCodeCamp",
        "Beginner",
        30.0,
        4.8,
        True,
        "https://www.freecodecamp.org/learn/2022/responsive-web-design/",
        "HTML5 semantic layout, CSS3 Flexbox and CSS Grid, responsive design principles, and accessibility standards.",
        ["HTML", "CSS", "Bootstrap"]
    ),
    (
        "React - The Complete Guide (incl. React Router & Redux)",
        "Udemy",
        "Intermediate",
        42.0,
        4.7,
        False,
        "https://www.udemy.com/course/react-the-complete-guide-incl-redux/",
        "Dive in and learn React.js from scratch! Hooks, Redux Toolkit, React Router, Next.js, and best practices.",
        ["React", "JavaScript", "HTML", "CSS"]
    ),
    (
        "Node.js, Express, MongoDB & More: The Complete Bootcamp",
        "Udemy",
        "Intermediate",
        38.0,
        4.7,
        False,
        "https://www.udemy.com/course/nodejs-express-mongodb-bootcamp/",
        "Master Node by building a fast, scalable RESTful API with authentication, security, and MongoDB integration.",
        ["Node.js", "JavaScript", "MongoDB", "Postman"]
    ),
    (
        "Python Flask: Build Web Applications from Scratch",
        "edX",
        "Intermediate",
        16.0,
        4.5,
        False,
        "https://www.edx.org/course/flask-web-development",
        "Build secure, modular Flask web applications with SQLAlchemy ORM, authentication, WTForms, and Jinja2.",
        ["Flask", "Python", "SQL", "Bootstrap"]
    ),
    (
        "Python and Django Full Stack Web Developer Bootcamp",
        "Udemy",
        "Intermediate",
        32.0,
        4.6,
        False,
        "https://www.udemy.com/course/python-and-django-full-stack-web-developer-bootcamp/",
        "Full stack development with Django ORM, authentication, class-based views, REST frameworks, and frontend.",
        ["Django", "Python", "HTML", "CSS"]
    ),
    (
        "Advanced React & Next.js Architecture",
        "Frontend Masters",
        "Advanced",
        14.0,
        4.9,
        False,
        "https://frontendmasters.com/courses/next-js/",
        "Production grade SSR, server components, edge rendering, advanced caching, and enterprise design patterns.",
        ["React", "TypeScript", "JavaScript"]
    ),

    # ── Database ────────────────────────────────────────────────────────────────
    (
        "MySQL Database Administration & Performance Tuning",
        "Udemy",
        "Intermediate",
        20.0,
        4.5,
        False,
        "https://www.udemy.com/course/mysql-database-administration/",
        "Master MySQL indexing, replication, query explain plans, transaction isolation, and backup strategies.",
        ["MySQL", "SQL"]
    ),
    (
        "MongoDB - The Complete Developer's Guide",
        "Udemy",
        "Intermediate",
        17.0,
        4.7,
        False,
        "https://www.udemy.com/course/mongodb-the-complete-developers-guide/",
        "Master MongoDB development. CRUD operations, aggregation pipelines, schema design, and indexing.",
        ["MongoDB", "Node.js"]
    ),
    (
        "Redis: High Performance In-Memory Data Store",
        "Redis University",
        "Intermediate",
        10.0,
        4.8,
        True,
        "https://university.redis.com/",
        "Understand Redis data structures, caching patterns, pub/sub messaging, and high availability clusters.",
        ["Redis"]
    ),

    # ── Cloud & DevOps ──────────────────────────────────────────────────────────
    (
        "Git & GitHub: Complete Guide to Version Control",
        "Coursera",
        "Beginner",
        12.0,
        4.8,
        True,
        "https://www.coursera.org/learn/introduction-git-github",
        "Learn branching, merging, rebasing, pull requests, resolving merge conflicts, and team collaboration workflows.",
        ["Git", "GitHub"]
    ),
    (
        "Docker & Kubernetes: The Practical Guide",
        "Udemy",
        "Intermediate",
        23.5,
        4.8,
        False,
        "https://www.udemy.com/course/docker-kubernetes-the-practical-guide/",
        "Build, test, and deploy Docker images and multi-container apps. Master Dockerfiles, compose, and K8s pods.",
        ["Docker", "Linux"]
    ),
    (
        "Linux Command Line and Shell Scripting Bootcamp",
        "Udemy",
        "Beginner",
        14.0,
        4.6,
        False,
        "https://www.udemy.com/course/linux-command-line-and-shell-scripting-bootcamp/",
        "Bash scripting, permissions, process management, SSH, package managers, and server administration.",
        ["Linux"]
    ),
    (
        "AWS Certified Solutions Architect Associate (SAA-C03)",
        "A Cloud Guru / Udemy",
        "Intermediate",
        30.0,
        4.8,
        False,
        "https://www.udemy.com/course/aws-certified-solutions-architect-associate-saa-c03/",
        "Master core AWS cloud services: EC2, S3, RDS, Lambda, VPC, IAM, CloudFront, and high-availability design.",
        ["AWS", "Docker", "Linux"]
    ),

    # ── AI & Machine Learning ───────────────────────────────────────────────────
    (
        "Machine Learning Specialization",
        "Coursera / Stanford & DeepLearning.AI",
        "Beginner",
        40.0,
        4.9,
        False,
        "https://www.coursera.org/specializations/machine-learning-introduction",
        "Andrew Ng's world-famous ML course. Supervised learning, linear regression, logistic regression, trees, and neural nets.",
        ["Machine Learning", "scikit-learn", "Python", "NumPy"]
    ),
    (
        "Deep Learning Specialization",
        "Coursera / DeepLearning.AI",
        "Intermediate",
        45.0,
        4.9,
        False,
        "https://www.coursera.org/specializations/deep-learning",
        "Build neural networks, CNNs for computer vision, RNNs/Transformers for sequences, and optimize hyper-parameters.",
        ["Deep Learning", "TensorFlow", "Python"]
    ),
    (
        "Applied Machine Learning with scikit-learn",
        "edX",
        "Intermediate",
        18.0,
        4.7,
        False,
        "https://www.edx.org/course/applied-machine-learning-scikit-learn",
        "Feature engineering, cross-validation, ensemble methods, pipeline construction, and evaluation metrics.",
        ["scikit-learn", "Machine Learning", "Pandas", "NumPy"]
    ),
    (
        "Natural Language Processing (NLP) with Python",
        "Udemy",
        "Intermediate",
        22.0,
        4.6,
        False,
        "https://www.udemy.com/course/nlp-natural-language-processing-with-python/",
        "Text preprocessing, TF-IDF vectorization, sentiment analysis, spaCy, NLTK, and BERT embeddings.",
        ["NLP", "Machine Learning", "Python"]
    ),
    (
        "TensorFlow Developer Certificate Bootcamp",
        "Udemy",
        "Intermediate",
        35.0,
        4.7,
        False,
        "https://www.udemy.com/course/tensorflow-developer-certificate-machine-learning-zero-to-mastery/",
        "Hands-on deep learning: building CNNs, transfer learning, NLP sequence models, and time series forecasting.",
        ["TensorFlow", "Deep Learning", "Python"]
    ),

    # ── Tools & Quality ─────────────────────────────────────────────────────────
    (
        "Postman: The Complete Guide to API Testing",
        "Udemy",
        "Beginner",
        10.0,
        4.7,
        False,
        "https://www.udemy.com/course/postman-the-complete-guide/",
        "Automated API testing, environment variables, collection runners, pre-request scripts, and CI/CD integration.",
        ["Postman"]
    ),
    (
        "Figma UI/UX Design Essentials",
        "Udemy",
        "Beginner",
        12.0,
        4.8,
        False,
        "https://www.udemy.com/course/figma-ux-ui-design-user-experience-tutorial-course/",
        "Create responsive UI mockups, interactive prototypes, design systems, auto-layout components, and wireframes.",
        ["Figma"]
    ),
    (
        "Automated Testing with Selenium & Python",
        "Udemy",
        "Intermediate",
        16.0,
        4.5,
        False,
        "https://www.udemy.com/course/selenium-webdriver-with-python/",
        "End-to-end browser automation, test runners, Page Object Model (POM), assertions, and reporting.",
        ["Selenium", "Python", "VS Code"]
    ),
]


def seed_courses(app=None):
    """Seed the course catalog and associate skills via CourseSkill bridge."""
    from flask import has_app_context

    def _do_seed():
        print("[+] Seeding course catalog for Phase 10...")

        # Pre-load all skills by canonical name for fast lookup
        skills_by_name = {s.name.lower(): s for s in Skill.query.all()}
        print(f"    Found {len(skills_by_name)} skills in DB.")

        created_courses = 0
        updated_courses = 0
        tagged_skills_count = 0

        for title, provider, diff, duration, rating, is_free, url, desc, skill_names in COURSES:
            course = Course.query.filter_by(title=title).first()
            if not course:
                course = Course(
                    title=title,
                    provider=provider,
                    difficulty_level=diff,
                    duration_hours=duration,
                    rating=rating,
                    is_free=is_free,
                    url=url,
                    description=desc,
                )
                db.session.add(course)
                db.session.flush()  # to obtain course.id
                created_courses += 1
            else:
                # Update attributes
                course.provider = provider
                course.difficulty_level = diff
                course.duration_hours = duration
                course.rating = rating
                course.is_free = is_free
                course.url = url
                course.description = desc
                updated_courses += 1

            # Manage skill tags
            existing_skill_ids = {cs.skill_id for cs in course.course_skills}
            for sname in skill_names:
                sk = skills_by_name.get(sname.lower())
                if not sk:
                    print(f"    [!] Skill '{sname}' not found in DB! Skipping tag for '{title}'.")
                    continue
                if sk.id not in existing_skill_ids:
                    db.session.add(CourseSkill(course_id=course.id, skill_id=sk.id))
                    existing_skill_ids.add(sk.id)
                    tagged_skills_count += 1

        db.session.commit()
        total_courses = Course.query.count()
        total_tags = CourseSkill.query.count()
        print(f"[OK] Seeding complete!")
        print(f"    Created: {created_courses}, Updated: {updated_courses}")
        print(f"    Total courses in DB: {total_courses}")
        print(f"    Total course-skill tags in DB: {total_tags}")

    if has_app_context():
        _do_seed()
    else:
        if app is None:
            app = create_app()
        with app.app_context():
            _do_seed()


if __name__ == '__main__':
    seed_courses()
