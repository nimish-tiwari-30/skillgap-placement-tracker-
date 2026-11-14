"""
seed_skills.py
───────────────
Starter skills dictionary seed script.

Run:  python seed_skills.py
Safe to run multiple times — idempotent (skips existing skills/aliases).

NOTE: This is a STARTER dictionary. Full demo data (job descriptions,
      course catalog, student seed data) comes in later phases.

Coverage: 40+ skills across 8 categories.
"""

import os
import sys

# Allow running from project root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from extensions import db
from models.skill import Skill, SkillAlias

# ── Skill seed data ───────────────────────────────────────────────────────────
# Format: (canonical_name, category, description, [alias1, alias2, ...])
SKILLS = [
    # ── Programming ───────────────────────────────────────────────
    ("Python",       "Programming", "General-purpose, high-level language; widely used in data science and backend.",
     ["Python Programming", "Python3", "Py"]),
    ("Java",         "Programming", "Object-oriented, platform-independent language; common in enterprise.",
     ["Java SE", "Java EE", "Core Java"]),
    ("C",            "Programming", "Low-level systems programming language.", ["C Programming"]),
    ("C++",          "Programming", "Extension of C with OOP; used in systems and competitive programming.",
     ["CPP", "C Plus Plus"]),
    ("JavaScript",   "Programming", "Primary language of the web browser; also Node.js on server.",
     ["JS", "ECMAScript", "ES6"]),
    ("TypeScript",   "Programming", "Typed superset of JavaScript.", ["TS"]),
    ("R",            "Programming", "Statistical computing language.",
     ["R Language", "R Programming"]),
    ("Go",           "Programming", "Compiled, concurrent language from Google.", ["Golang"]),
    ("Kotlin",       "Programming", "Modern JVM language; primary for Android.", []),

    # ── Data & Analytics ──────────────────────────────────────────
    ("SQL",          "Data & Analytics", "Structured Query Language for relational databases.",
     ["MySQL Query", "Structured Query Language"]),
    ("Excel",        "Data & Analytics", "Microsoft spreadsheet tool with pivot tables and formulas.",
     ["MS Excel", "Microsoft Excel", "Spreadsheets"]),
    ("Power BI",     "Data & Analytics", "Microsoft business intelligence and data visualization tool.",
     ["Power-BI", "PowerBI", "Microsoft Power BI"]),
    ("Tableau",      "Data & Analytics", "Drag-and-drop data visualization and BI platform.", []),
    ("Pandas",       "Data & Analytics", "Python library for data manipulation and analysis.", []),
    ("NumPy",        "Data & Analytics", "Python library for numerical computing.", []),
    ("Statistics",   "Data & Analytics", "Probability, distributions, hypothesis testing.", []),

    # ── Web ───────────────────────────────────────────────────────
    ("HTML",         "Web", "HyperText Markup Language — structure of web pages.", ["HTML5"]),
    ("CSS",          "Web", "Cascading Style Sheets — styling of web pages.", ["CSS3"]),
    ("React",        "Web", "Facebook's JavaScript UI library.", ["ReactJS", "React.js"]),
    ("Node.js",      "Web", "Server-side JavaScript runtime.",
     ["Node", "NodeJS", "Node JS"]),
    ("Flask",        "Web", "Lightweight Python web framework.", []),
    ("Django",       "Web", "Batteries-included Python web framework.", []),
    ("Bootstrap",    "Web", "CSS framework for responsive design.", ["Bootstrap 5"]),

    # ── Database ──────────────────────────────────────────────────
    ("MySQL",        "Database", "Popular open-source relational database.", []),
    ("PostgreSQL",   "Database", "Advanced open-source relational database.",
     ["Postgres", "PostgreSQL DB", "PSQL"]),
    ("MongoDB",      "Database", "NoSQL document database.", ["Mongo"]),
    ("SQLite",       "Database", "Lightweight embedded relational database.", []),
    ("Redis",        "Database", "In-memory key-value data store.", []),

    # ── Cloud/DevOps ──────────────────────────────────────────────
    ("Git",          "Cloud/DevOps", "Distributed version control system.", ["Git Version Control"]),
    ("GitHub",       "Cloud/DevOps", "Cloud-based Git repository hosting.", []),
    ("Docker",       "Cloud/DevOps", "Container platform for packaging applications.", []),
    ("Linux",        "Cloud/DevOps", "Open-source operating system family.",
     ["Linux CLI", "Unix/Linux"]),
    ("AWS",          "Cloud/DevOps", "Amazon Web Services cloud platform.",
     ["Amazon Web Services", "Amazon AWS"]),

    # ── AI/ML ─────────────────────────────────────────────────────
    ("Machine Learning", "AI/ML", "Building models that learn from data.",
     ["ML", "Machine-Learning", "ML Algorithms"]),
    ("Deep Learning",    "AI/ML", "Neural networks with multiple hidden layers.",
     ["DL", "Deep-Learning"]),
    ("scikit-learn",     "AI/ML", "Python ML library with classical algorithms.",
     ["Sklearn", "Scikit Learn", "sklearn"]),
    ("TensorFlow",       "AI/ML", "Google's deep learning framework.", ["TF"]),
    ("NLP",              "AI/ML", "Natural Language Processing — text analysis.",
     ["Natural Language Processing"]),

    # ── Tools ─────────────────────────────────────────────────────
    ("Jupyter Notebook", "Tools", "Interactive Python coding environment.",
     ["Jupyter", "Jupyter Lab"]),
    ("VS Code",          "Tools", "Microsoft Visual Studio Code editor.", ["VSCode"]),
    ("Postman",          "Tools", "API development and testing tool.", []),
    ("Figma",            "Tools", "Collaborative UI/UX design tool.", []),
    ("Selenium",         "Tools", "Automated browser testing framework.", ["Selenium WebDriver"]),
    ("JIRA",             "Tools", "Issue tracking and project management tool.", ["Jira Software"]),
    ("Manual Testing",   "Tools", "Manual software quality assurance and test execution.", ["QA Testing", "Software Testing"]),
    ("Automated Testing","Tools", "Automated test suites and test automation frameworks.", ["Automation Testing", "Test Automation"]),
    ("Unit Testing",     "Programming", "Unit test design and test runner frameworks.", ["Unit Tests", "PyTest", "JUnit"]),
    ("Kubernetes",       "Cloud/DevOps", "Container orchestration system.", ["K8s", "K8"]),
    ("CI/CD",            "Cloud/DevOps", "Continuous Integration and Continuous Deployment pipelines.", ["Continuous Integration", "CI CD", "Jenkins"]),
    ("REST API",         "Web", "RESTful web services and API architecture.", ["REST APIs", "RESTful APIs", "RESTful API"]),

    # ── Soft Skills ───────────────────────────────────────────────
    ("Communication",    "Soft Skills", "Written and verbal communication ability.", []),
    ("Team Collaboration", "Soft Skills", "Working effectively within teams.",
     ["Teamwork", "Team Work"]),
    ("Problem Solving",  "Soft Skills", "Analytical thinking and logical reasoning.", []),
    ("Time Management",  "Soft Skills", "Planning and prioritizing tasks effectively.", []),
]


def seed(app=None):
    from flask import has_app_context

    def _do_seed():
        added_skills   = 0
        added_aliases  = 0
        skipped_skills = 0

        for name, category, description, aliases in SKILLS:
            # Check if skill already exists (case-insensitive)
            existing = Skill.query.filter(
                db.func.lower(Skill.name) == name.lower()
            ).first()

            if existing:
                skill = existing
                skipped_skills += 1
            else:
                skill = Skill(name=name, category=category, description=description)
                db.session.add(skill)
                db.session.flush()   # Get skill.id without committing yet
                added_skills += 1

            # Add aliases — skip if already exists
            for alias in aliases:
                existing_alias = SkillAlias.query.filter(
                    db.func.lower(SkillAlias.alias_name) == alias.lower()
                ).first()
                if not existing_alias:
                    db.session.add(SkillAlias(skill_id=skill.id, alias_name=alias))
                    added_aliases += 1

        db.session.commit()

        total = Skill.query.count()
        print("[OK] Seed complete!")
        print(f"  Added:   {added_skills} skills, {added_aliases} aliases")
        print(f"  Skipped: {skipped_skills} existing skills")
        print(f"  Total skills in DB: {total}")
        assert total >= 40, f"Expected >=40 skills, got {total}"
        print(f"  [PASS] {total} >= 40 skills")

    if has_app_context():
        _do_seed()
    else:
        if app is None:
            app = create_app()
        with app.app_context():
            _do_seed()


if __name__ == '__main__':
    seed()
