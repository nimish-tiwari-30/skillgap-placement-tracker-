"""
tests/test_job_matcher.py
─────────────────────────
Unit tests for Phase 9 core matching logic: ml/job_matcher.py.

Tests:
  - Identical skill profile vs job gives 100.0% (and explanation why)
  - No shared skills gives 0.0%
  - Relative match ordering: student closer to Job A than Job B scores higher for A
  - Multi-word skill tokens stay intact (custom identity analyzer)
  - Proficiency and importance repeats change scores in expected direction
  - Edge cases: zero student skills, zero job skills, empty corpus (no crashes, no NaNs)
  - Score bounds: scores are always strictly between 0.0 and 100.0
"""

import pytest
import numpy as np
from ml.job_matcher import (
    build_student_document,
    build_job_document,
    compute_job_matches,
    compute_single_job_match,
    _identity_analyzer,
)


def test_identical_skill_profile_yields_100_percent():
    """
    Test: An identical skill profile between student and job yields 100.0%.

    Why:
      Cosine similarity computes cos(θ) = (u · v) / (||u|| * ||v||).
      When the student document has the exact same skill tokens and repeat frequencies
      as the job document, the two TF-IDF vectors are collinear (angle θ = 0 degrees).
      Since cos(0) = 1.0, multiplying by 100 gives exactly 100.0%.
    """
    student_skills = {'Python': 'Intermediate', 'SQL': 'Intermediate', 'Excel': 'Beginner'}
    job_skills = {'Python': 3, 'SQL': 3, 'Excel': 1}

    score = compute_single_job_match(student_skills, job_skills)
    assert score == 100.0, f"Expected 100.0 for collinear skill vectors, got {score}"


def test_no_shared_skills_yields_zero():
    """
    Test: Orthogonal vectors (zero shared skills) produce exactly 0.0%.
    """
    student_skills = {'Python': 'Advanced', 'Django': 'Intermediate'}
    job_skills = {'Rust': 5, 'Solidity': 4}

    score = compute_single_job_match(student_skills, job_skills)
    assert score == 0.0


def test_relative_matching_closer_to_a_than_b():
    """
    Test: A student whose skills align closely with Job A but barely with Job B
    receives a higher similarity score for Job A.
    """
    student_skills = {'Python': 'Advanced', 'SQL': 'Intermediate', 'Pandas': 'Intermediate'}

    job_a_data_analyst = {
        'Python': 5,
        'SQL': 4,
        'Pandas': 4,
        'Tableau': 3,
    }
    job_b_embedded_systems = {
        'C': 5,
        'Assembly': 5,
        'RTOS': 4,
        'Python': 1,
    }

    scores = compute_job_matches(student_skills, [job_a_data_analyst, job_b_embedded_systems])
    assert len(scores) == 2
    score_a, score_b = scores[0], scores[1]

    assert score_a > score_b, f"Expected Job A ({score_a}) to score higher than Job B ({score_b})"
    assert score_a > 50.0
    assert score_b < 20.0


def test_multi_word_skills_stay_intact():
    """
    Test: Multi-word skill tokens (e.g. 'Power BI', 'Machine Learning', 'Spring Boot')
    must NOT be split into individual words ('Power', 'BI').
    """
    student = {'Power BI': 'Intermediate', 'Machine Learning': 'Advanced'}
    job = {'Power BI': 4, 'Machine Learning': 5}

    s_doc = build_student_document(student)
    j_doc = build_job_document(job)

    # Verify document tokens are intact
    assert 'Power BI' in s_doc
    assert 'Machine Learning' in s_doc
    assert 'Power' not in s_doc
    assert 'BI' not in s_doc

    # When weights are proportional (e.g. Intermediate=3 and Advanced=5 vs Job 3 and 5),
    # cosine similarity is 100.0%
    job_aligned = {'Power BI': 3, 'Machine Learning': 5}
    score = compute_single_job_match(student, job_aligned)
    assert score == 100.0

    # With slightly different weighting (3, 5 vs 4, 5), angle difference yields ~99.1%
    score_slight_diff = compute_single_job_match(student, job)
    assert score_slight_diff >= 99.0


def test_proficiency_and_importance_weighting_direction():
    """
    Test: When a student has higher proficiency in a job's most important skill,
    the cosine similarity score increases compared to when their proficiency is low.
    """
    # Job heavily prioritizes Python (weight 5) over Git (weight 1)
    job = {'Python': 5, 'Git': 1}

    # Student 1: Expert in Python (5), Beginner in Git (1) -> Aligns with job priority
    student_high_python = {'Python': 'Advanced', 'Git': 'Beginner'}

    # Student 2: Beginner in Python (1), Expert in Git (5) -> Misaligned with job priority
    student_low_python = {'Python': 'Beginner', 'Git': 'Advanced'}

    scores = compute_job_matches(
        student_high_python,
        [job]
    )
    score_high = scores[0]

    scores_low = compute_job_matches(
        student_low_python,
        [job]
    )
    score_low = scores_low[0]

    assert score_high > score_low, (
        f"Expected student with high Python to score higher ({score_high} vs {score_low})"
    )


def test_edge_cases_no_crash_or_nan():
    """
    Test edge cases:
      - Student has 0 skills
      - Job has 0 skills
      - Empty corpus
      - Neither student nor job has skills
    All must return 0.0 without divide-by-zero or NaN.
    """
    # 1. Student with 0 skills
    scores_empty_student = compute_job_matches({}, [{'Python': 3, 'SQL': 4}])
    assert scores_empty_student == [0.0]
    assert not np.isnan(scores_empty_student[0])

    # 2. Job with 0 skills
    scores_empty_job = compute_job_matches({'Python': 'Intermediate'}, [{}])
    assert scores_empty_job == [0.0]
    assert not np.isnan(scores_empty_job[0])

    # 3. Empty corpus (0 student skills, 0 job skills)
    scores_empty_corpus = compute_job_matches({}, [{}])
    assert scores_empty_corpus == [0.0]

    # 4. Empty job list
    assert compute_job_matches({'Python': 3}, []) == []


def test_score_bounds():
    """
    Test: Computed match scores are always bounded within [0.0, 100.0].
    """
    students = [
        {'Python': 'Advanced', 'SQL': 'Intermediate'},
        {'Java': 'Beginner'},
        {},
        {'Python': 'Beginner', 'Rust': 'Advanced', 'Docker': 'Intermediate'},
    ]

    jobs = [
        {'Python': 5, 'SQL': 4, 'Tableau': 3},
        {'Java': 4, 'Spring': 4},
        {'AWS': 5, 'Kubernetes': 4},
        {},
    ]

    for s in students:
        scores = compute_job_matches(s, jobs)
        for val in scores:
            assert 0.0 <= val <= 100.0
            assert not np.isnan(val)
            assert isinstance(val, float)
