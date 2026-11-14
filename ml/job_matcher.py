"""
ml/job_matcher.py
─────────────────
Pure functions for TF-IDF vectorization and Cosine Similarity calculation
between student skill profiles and job requirement descriptions.

Mathematical & Conceptual Notes:
  - Cosine Similarity measures the cosine of the angle between two multi-dimensional
    vectors:
        cos(θ) = (A · B) / (||A|| * ||B||)
    It evaluates the orientation (direction) rather than the magnitude (size).
    A score of 1.0 (100%) indicates identical directional alignment of skills,
    while 0.0 indicates orthogonal vectors (zero shared skills).
  - TF-IDF (Term Frequency - Inverse Document Frequency) reflects how important
    a skill is to a document relative to the whole corpus:
      - Term Frequency (TF): Boosted by repeating tokens proportionally to proficiency
        and importance weights (1 to 5).
      - Inverse Document Frequency (IDF): Automatically down-weights ubiquitous skills
        that appear across nearly all jobs (e.g., general communication or basic tools),
        while accentuating specialized, distinctive skills (e.g., PyTorch, Snowflake).
  - Note on Corpus Size: With a small corpus of job descriptions, IDF weights
    can be relatively coarse; as the job database scales, IDF distinctions become
    progressively sharper.
  - Multi-Word Skill Token Preservation:
    We supply a custom identity analyzer (`_identity_analyzer`) to TfidfVectorizer.
    Because the document is already a pre-tokenized list of canonical skill strings,
    scikit-learn does not apply regex/whitespace token splitting. Multi-word skills
    like "Power BI", "Machine Learning", or "Node.js" remain intact as single tokens.
"""

from typing import Any, Dict, Iterable, List, Optional, Tuple, Union
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


# Numeric mapping for student proficiency level (1 to 5 repeat factor)
PROFICIENCY_WEIGHT_MAP: Dict[str, int] = {
    'Beginner': 1,
    'Intermediate': 3,
    'Advanced': 5,
}


def _identity_analyzer(doc: List[str]) -> List[str]:
    """
    Identity analyzer for TfidfVectorizer.

    By returning the document unchanged (which is already a list of canonical
    skill tokens), scikit-learn skips its default regex/whitespace tokenizer.
    This prevents multi-word skill names such as 'Power BI', 'Machine Learning',
    or 'Spring Boot' from being split into separate words ('Power' and 'BI').
    """
    return doc


def build_student_document(student_skills: Any) -> List[str]:
    """
    Convert a student's skills into a list of skill tokens.
    Skills are repeated according to proficiency weight (1-5), so that higher
    mastery contributes greater term frequency.

    Supported input formats:
      - dict: {skill_name: proficiency_str_or_int, ...}
      - list of dicts: [{'name': 'Python', 'proficiency': 'Advanced'}, ...]
      - set / list of str: ['Python', 'SQL', ...]
    """
    tokens: List[str] = []
    if not student_skills:
        return tokens

    if isinstance(student_skills, dict):
        for skill_name, prof_val in student_skills.items():
            name = str(skill_name).strip()
            if not name:
                continue
            if isinstance(prof_val, dict):
                p_raw = prof_val.get('proficiency') or prof_val.get('proficiency_level')
            else:
                p_raw = prof_val

            weight = 3
            if isinstance(p_raw, (int, float)):
                weight = max(1, min(5, int(p_raw)))
            elif isinstance(p_raw, str) and p_raw in PROFICIENCY_WEIGHT_MAP:
                weight = PROFICIENCY_WEIGHT_MAP[p_raw]

            tokens.extend([name] * weight)

    elif isinstance(student_skills, (list, tuple, set)):
        for item in student_skills:
            if isinstance(item, dict):
                name = item.get('name') or item.get('skill') or ''
                name = str(name).strip()
                if not name:
                    continue
                p_raw = item.get('proficiency') or item.get('proficiency_level')
                weight = 3
                if isinstance(p_raw, (int, float)):
                    weight = max(1, min(5, int(p_raw)))
                elif isinstance(p_raw, str) and p_raw in PROFICIENCY_WEIGHT_MAP:
                    weight = PROFICIENCY_WEIGHT_MAP[p_raw]
                tokens.extend([name] * weight)
            else:
                name = str(item).strip()
                if name:
                    tokens.extend([name] * 3)

    return tokens


def build_job_document(job_skills: Any) -> List[str]:
    """
    Convert a job's required skills into a list of skill tokens.
    Skills are repeated according to their importance weight (1-5),
    reflecting higher employer priority in term frequency.

    Supported input formats:
      - dict: {skill_name: importance_int, ...}
      - list of dicts: [{'name': 'Python', 'importance': 5}, ...]
      - set / list of str: ['Python', 'SQL', ...]
    """
    tokens: List[str] = []
    if not job_skills:
        return tokens

    if isinstance(job_skills, dict):
        for skill_name, imp_val in job_skills.items():
            name = str(skill_name).strip()
            if not name:
                continue
            if isinstance(imp_val, dict):
                raw = imp_val.get('importance') or imp_val.get('importance_weight')
            else:
                raw = imp_val
            try:
                weight = max(1, min(5, int(raw)))
            except (ValueError, TypeError):
                weight = 3
            tokens.extend([name] * weight)

    elif isinstance(job_skills, (list, tuple, set)):
        for item in job_skills:
            if isinstance(item, dict):
                name = item.get('name') or item.get('skill') or ''
                name = str(name).strip()
                if not name:
                    continue
                raw = item.get('importance') or item.get('importance_weight')
                try:
                    weight = max(1, min(5, int(raw)))
                except (ValueError, TypeError):
                    weight = 3
                tokens.extend([name] * weight)
            elif isinstance(item, (tuple, list)) and len(item) >= 2:
                name = str(item[0]).strip()
                if not name:
                    continue
                try:
                    weight = max(1, min(5, int(item[1])))
                except (ValueError, TypeError):
                    weight = 3
                tokens.extend([name] * weight)
            else:
                name = str(item).strip()
                if name:
                    tokens.extend([name] * 3)

    return tokens


def compute_job_matches(
    student_skills: Any,
    job_skills_list: List[Any]
) -> List[float]:
    """
    Compute TF-IDF vectorization and cosine similarity between a student profile
    and a list of jobs in a unified corpus.

    Parameters:
      student_skills: skills of the student (dict, list, or set)
      job_skills_list: list of job skills representations for all jobs

    Returns:
      List of similarity scores as percentages rounded to 1 decimal place (0.0 to 100.0).
    """
    if not job_skills_list:
        return []

    # 1. Build documents
    student_doc = build_student_document(student_skills)
    job_docs = [build_job_document(js) for js in job_skills_list]

    # Edge Case: Student has zero skills
    if not student_doc:
        return [0.0] * len(job_skills_list)

    # Edge Case: Check total tokens in entire corpus
    total_tokens = len(student_doc) + sum(len(jd) for jd in job_docs)
    if total_tokens == 0:
        return [0.0] * len(job_skills_list)

    # 2. Assemble corpus: [student_doc, job_doc_0, job_doc_1, ...]
    corpus = [student_doc] + job_docs

    # Check if corpus vocabulary has any non-empty tokens
    all_tokens = set(student_doc)
    for jd in job_docs:
        all_tokens.update(jd)
    if not all_tokens:
        return [0.0] * len(job_skills_list)

    # 3. Fit TF-IDF Vectorizer with identity analyzer
    try:
        vectorizer = TfidfVectorizer(
            analyzer=_identity_analyzer,
            lowercase=False,
            norm='l2'
        )
        tfidf_matrix = vectorizer.fit_transform(corpus)
    except Exception:
        # Fallback guard against any vectorizer fitting exceptions
        return [0.0] * len(job_skills_list)

    # student_vector is index 0; job_vectors are indices 1 to end
    student_vector = tfidf_matrix[0:1]
    job_vectors = tfidf_matrix[1:]

    # 4. Compute cosine similarity
    raw_sims = cosine_similarity(student_vector, job_vectors)[0]

    # 5. Clean, clamp, and format as percentage rounded to 1 decimal
    cleaned_scores: List[float] = []
    for val in raw_sims:
        if np.isnan(val) or np.isinf(val):
            score = 0.0
        else:
            score = float(np.clip(val, 0.0, 1.0)) * 100.0
            score = round(score, 1)
        cleaned_scores.append(score)

    return cleaned_scores


def compute_single_job_match(
    student_skills: Any,
    job_skills: Any
) -> float:
    """
    Calculate cosine similarity percentage between a student and a single job description.
    """
    scores = compute_job_matches(student_skills, [job_skills])
    return scores[0] if scores else 0.0
