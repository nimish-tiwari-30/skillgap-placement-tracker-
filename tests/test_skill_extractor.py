"""
tests/test_skill_extractor.py
─────────────────────────────
Pytest tests for NLP skill extraction pipeline, boundary checking,
alias resolution, and occurrence counting.

Run:  .\\venv\\Scripts\\python.exe -m pytest tests/test_skill_extractor.py -v
"""

import pytest
from extensions import db as _db
from models.skill import Skill, SkillAlias
from ml.skill_extractor import SkillExtractor, extract_skills_from_text, refresh_skills_cache


def seed_test_skills():
    """Seed canonical skills and aliases needed for tests."""
    skills_data = [
        ("Python", "Programming", ["Python Programming", "Python3", "Py"]),
        ("Java", "Programming", ["Core Java", "Java SE"]),
        ("JavaScript", "Programming", ["JS", "ES6"]),
        ("C", "Programming", ["C Programming", "C Language"]),
        ("C++", "Programming", ["CPP", "C Plus Plus"]),
        ("C#", "Programming", ["CSharp"]),
        ("SQL", "Data & Analytics", ["Structured Query Language"]),
        ("Excel", "Data & Analytics", ["MS Excel", "Microsoft Excel"]),
        ("Power BI", "Data & Analytics", ["Power-BI", "PowerBI"]),
        ("Node.js", "Web", ["NodeJS", "Node js"]),
        ("scikit-learn", "AI/ML", ["sklearn", "Scikit Learn"]),
        ("R", "Programming", ["R Programming", "R Language"]),
    ]

    for name, cat, aliases in skills_data:
        skill = Skill.query.filter_by(name=name).first()
        if not skill:
            skill = Skill(name=name, category=cat)
            _db.session.add(skill)
            _db.session.flush()

        for alias in aliases:
            if not SkillAlias.query.filter_by(alias_name=alias).first():
                _db.session.add(SkillAlias(skill_id=skill.id, alias_name=alias))

    _db.session.commit()
    refresh_skills_cache()


def test_exact_canonical_skills_extraction(app):
    """Text: 'Worked with Python, SQL, Power BI and Excel.' returns exactly those 4 skills."""
    with app.app_context():
        seed_test_skills()
        text = "Worked with Python, SQL, Power BI and Excel."
        results = extract_skills_from_text(text)
        names = {s['canonical_name'] for s in results}
        assert names == {"Python", "SQL", "Power BI", "Excel"}
        assert len(results) == 4


def test_alias_mapping_cases(app):
    """Aliases resolve to canonical skill names: MS Excel->Excel, Power-BI->Power BI, Python Programming->Python, JS->JavaScript."""
    with app.app_context():
        seed_test_skills()
        text = "Proficient in MS Excel, Power-BI, Python Programming, and JS development."
        results = extract_skills_from_text(text)
        name_map = {s['canonical_name']: s for s in results}

        assert "Excel" in name_map
        assert name_map["Excel"]["matched_text"].lower() == "ms excel"

        assert "Power BI" in name_map
        assert name_map["Power BI"]["matched_text"].lower() == "power-bi"

        assert "Python" in name_map
        assert name_map["Python"]["matched_text"].lower() == "python programming"

        assert "JavaScript" in name_map
        assert name_map["JavaScript"]["matched_text"].lower() == "js"


def test_word_boundary_java_vs_javascript(app):
    """'JavaScript' does NOT trigger 'Java'. When both are present, both match cleanly."""
    with app.app_context():
        seed_test_skills()

        # Text with ONLY JavaScript
        text_only_js = "Frontend developed exclusively using JavaScript."
        res1 = extract_skills_from_text(text_only_js)
        names1 = {s['canonical_name'] for s in res1}
        assert "JavaScript" in names1
        assert "Java" not in names1

        # Text with BOTH Java and JavaScript
        text_both = "Backend built with Java, client-side coded in JavaScript."
        res2 = extract_skills_from_text(text_both)
        names2 = {s['canonical_name'] for s in res2}
        assert "Java" in names2
        assert "JavaScript" in names2


def test_special_symbols_handling(app):
    """Special characters in skill names (C++, C#, Node.js, scikit-learn) match correctly."""
    with app.app_context():
        seed_test_skills()
        text = "Experience with C++, C#, Node.js, and scikit-learn algorithms."
        results = extract_skills_from_text(text)
        names = {s['canonical_name'] for s in results}
        assert "C++" in names
        assert "C#" in names
        assert "Node.js" in names
        assert "scikit-learn" in names


def test_ambiguous_short_skills_guard(app):
    """Random isolated letters 'C' or 'R' in non-technical context do NOT trigger false positives."""
    with app.app_context():
        seed_test_skills()
        # Random non-programming sentence with C and R
        text_innocent = "Contact Dr. C. Johnson at apartment 4R on Main Street."
        results = extract_skills_from_text(text_innocent)
        names = {s['canonical_name'] for s in results}
        assert "C" not in names
        assert "R" not in names

        # Technical context where C is adjacent to C++
        text_tech = "Programming in C/C++ and Python."
        res_tech = extract_skills_from_text(text_tech)
        names_tech = {s['canonical_name'] for s in res_tech}
        assert "C" in names_tech
        assert "C++" in names_tech


def test_no_skills_returns_empty_list(app):
    """Text with no matching skills returns an empty list without error."""
    with app.app_context():
        seed_test_skills()
        text = "Attended morning lectures on European history and creative writing."
        results = extract_skills_from_text(text)
        assert results == []


def test_occurrence_count_confidence(app):
    """Repeated skill mentions increment occurrence count accurately."""
    with app.app_context():
        seed_test_skills()
        text = "Used Python for backend services. Python scripts automated data ingestion. Also deployed Python APIs."
        results = extract_skills_from_text(text)
        py_result = [s for s in results if s['canonical_name'] == 'Python'][0]
        assert py_result['count'] == 3


def test_cache_refresh(app):
    """New skill added to DB becomes detectable after refresh_skills_cache()."""
    with app.app_context():
        seed_test_skills()
        # Ensure 'Rust' is not present
        assert not any(s['canonical_name'] == 'Rust' for s in extract_skills_from_text("Coded in Rust."))

        # Admin adds Rust
        rust = Skill(name='Rust', category='Programming')
        _db.session.add(rust)
        _db.session.commit()

        # Cache refreshed
        refresh_skills_cache()
        results = extract_skills_from_text("Coded in Rust.")
        assert any(s['canonical_name'] == 'Rust' for s in results)
