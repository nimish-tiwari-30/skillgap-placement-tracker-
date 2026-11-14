"""
ml/recommender.py
──────────────────
Pure functions for content-based course recommendation.
NO Flask or DB imports here — easy to unit-test in isolation.

HOW CONTENT-BASED RECOMMENDATION WORKS (in simple terms):
- Each MISSING skill is matched against courses tagged with that skill.
- Courses are ranked by how well they fit the student's current level (difficulty fit),
  then by rating (higher is better), then by shorter duration as a tie-breaker.
- Result: for each missing skill, student gets top N courses that teach THAT skill.
"""

from typing import Any, Dict, List, Optional, Tuple


# ── Proficiency → numeric score (higher = more advanced) ────────────────────
PROFICIENCY_SCORE: Dict[str, int] = {
    'Beginner': 1,
    'Intermediate': 2,
    'Advanced': 3,
}

# ── Difficulty → numeric score ───────────────────────────────────────────────
DIFFICULTY_SCORE: Dict[str, int] = {
    'Beginner': 1,
    'Intermediate': 2,
    'Advanced': 3,
}

# ── Neutral rating used when a course has no rating ─────────────────────────
NEUTRAL_RATING: float = 2.5


def _ideal_difficulty(proficiency: Optional[str]) -> int:
    """
    Given the student's current proficiency for a skill, compute the ideal
    course difficulty level:
      - No proficiency or Beginner (score 1) → Beginner course (1)
      - Intermediate (score 2)               → Intermediate course (2)
      - Advanced (score 3)                   → Advanced course (3)
    This guides the difficulty-fit ranking below.
    """
    score = PROFICIENCY_SCORE.get(proficiency or '', 0)
    if score <= 1:
        return DIFFICULTY_SCORE['Beginner']       # Student needs basics
    elif score == 2:
        return DIFFICULTY_SCORE['Intermediate']   # Student is mid-level
    else:
        return DIFFICULTY_SCORE['Advanced']        # Student wants mastery


def _difficulty_fit_score(ideal: int, course_difficulty: str) -> int:
    """
    How close is the course difficulty to what the student needs?
    Returns 0 (exact match) to 2 (two levels away).
    Lower is better (used to sort ascending later).

    Example:
      Student needs Beginner (ideal=1), course is Intermediate (2) → distance = 1
      Student needs Beginner (ideal=1), course is Advanced (3)     → distance = 2
    """
    course_score = DIFFICULTY_SCORE.get(course_difficulty, 2)
    return abs(ideal - course_score)   # 0 = perfect fit


def _rank_courses_for_skill(
    courses: List[Dict[str, Any]],
    proficiency: Optional[str],
    top_n: int = 3,
) -> List[Dict[str, Any]]:
    """
    Rank courses for ONE skill using three criteria (documented priority order):
      1) Difficulty fit: smaller distance from ideal difficulty scores HIGHER
         (Beginner for no/low proficiency, Intermediate for score 2, Advanced for 4+)
      2) Rating: higher is better; null rating treated as neutral (2.5)
      3) Duration (hours): shorter is better as a tie-breaker

    Returns the top_n courses, each augmented with a 'rank_score' dict for transparency.
    """
    ideal = _ideal_difficulty(proficiency)

    def sort_key(c: Dict[str, Any]) -> Tuple:
        diff_fit   = _difficulty_fit_score(ideal, c.get('difficulty_level', 'Beginner'))
        rating     = -(float(c.get('rating') or NEUTRAL_RATING))   # negate: higher = better
        duration   = float(c.get('duration_hours') or 999)          # null → treated as very long
        return (diff_fit, rating, duration)

    ranked = sorted(courses, key=sort_key)
    return ranked[:top_n]


def recommend(
    missing_skills: List[Dict[str, Any]],
    all_courses: List[Dict[str, Any]],
    top_n: int = 3,
) -> Dict[str, Any]:
    """
    Main entry point for content-based course recommendation.

    Parameters
    ----------
    missing_skills : list of dicts
        Each dict: {skill_id, name, importance (1-5), proficiency (optional str)}
        Sorted externally by importance descending (done in service layer).

    all_courses : list of dicts
        Each dict: {course_id, title, provider, difficulty_level, duration_hours,
                    rating, url, skill_ids (list of int)}
        Loaded from DB in service layer (no N+1 queries).

    top_n : int
        Max courses to return per missing skill (default 3).

    Returns
    -------
    dict with:
        all_covered  : bool   — True when no missing skills exist (congratulatory flag)
        items        : list   — one item per missing skill, ordered by importance desc
            Each item:
                skill_id     : int
                skill_name   : str
                importance   : int (1-5)
                proficiency  : str or None
                has_courses  : bool   — False when no course covers this skill
                courses      : list of course dicts (ranked top_n)
                    Each course also contains:
                        covers_n_missing_skills : int  — how many missing skills this course covers
    """
    # Edge case: no missing skills → congratulatory response
    if not missing_skills:
        return {
            'all_covered': True,
            'items': [],
        }

    # Build a set of all missing skill_ids for the "covers N missing skills" badge
    missing_skill_ids: set = {int(s['skill_id']) for s in missing_skills}

    # Build an index: skill_id → list of matching courses (for O(1) lookup)
    skill_to_courses: Dict[int, List[Dict[str, Any]]] = {}
    for course in all_courses:
        for sid in (course.get('skill_ids') or []):
            skill_to_courses.setdefault(int(sid), []).append(course)

    items = []
    for skill in missing_skills:
        skill_id    = int(skill['skill_id'])
        proficiency = skill.get('proficiency')   # may be None if student has no entry

        # Find all courses that teach this skill
        matching = skill_to_courses.get(skill_id, [])

        if not matching:
            # No course in DB teaches this skill
            items.append({
                'skill_id':   skill_id,
                'skill_name': skill['name'],
                'importance': skill.get('importance', 3),
                'proficiency': proficiency,
                'has_courses': False,
                'courses': [],
            })
            continue

        # Rank and take top N
        ranked = _rank_courses_for_skill(matching, proficiency, top_n=top_n)

        # Annotate each course with how many of the CURRENT missing skills it covers
        enriched = []
        for c in ranked:
            c_skill_ids = set(int(x) for x in (c.get('skill_ids') or []))
            covers = len(c_skill_ids.intersection(missing_skill_ids))
            enriched.append({**c, 'covers_n_missing_skills': covers})

        items.append({
            'skill_id':   skill_id,
            'skill_name': skill['name'],
            'importance': skill.get('importance', 3),
            'proficiency': proficiency,
            'has_courses': True,
            'courses': enriched,
        })

    return {
        'all_covered': False,
        'items': items,
    }
