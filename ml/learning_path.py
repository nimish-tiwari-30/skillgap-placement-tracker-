"""
ml/learning_path.py
───────────────────
Pure functions for generating and evaluating structured learning paths.
NO Flask or DB imports here — 100% testable in isolation.

HOW LEARNING PATH SEQUENCING WORKS:
  1. Beginner skills are taught first, establishing foundations before complex topics.
  2. Within the same difficulty tier, higher importance skills are prioritized (critical gaps first).
  3. Ties are broken alphabetically by skill name for deterministic ordering.
  4. Every learning path culminates in two essential career milestones:
     - Phase N+1: Build a project using these skills (hands-on application)
     - Phase N+2: Update your resume (hiring readiness)
"""

from typing import Any, Dict, List, Optional, Tuple


# Difficulty mapping for sorting: lower score = taught earlier
DIFFICULTY_SCORES: Dict[str, int] = {
    'beginner': 1,
    'intermediate': 2,
    'advanced': 3,
}

DIFFICULTY_ORDER: Dict[str, int] = {
    'Beginner': 1,
    'Intermediate': 2,
    'Advanced': 3,
}

DEFAULT_PROFICIENCY_MAP: Dict[str, int] = {
    'Beginner': 1,
    'Intermediate': 2,
    'Advanced': 3,
}

# Standard phase labels for capstone milestones
PROJECT_PHASE_LABEL = "Build a project using these skills"
RESUME_PHASE_LABEL = "Update your resume"


def get_difficulty_rank(difficulty: Any) -> int:
    """
    Convert a difficulty string or integer into a comparable numeric rank:
      Beginner -> 1
      Intermediate -> 2
      Advanced -> 3
    Defaults to 1 (Beginner) if missing or unknown.
    """
    if isinstance(difficulty, int):
        return difficulty
    if isinstance(difficulty, str):
        return DIFFICULTY_SCORES.get(difficulty.strip().lower(), 1)
    return 1


def calculate_completion_pct(completed_count: int, total_count: int) -> float:
    """
    Calculate progress completion percentage:
      (completed_phases / total_phases) * 100
    Rounded to 1 decimal place.

    Guards against divide-by-zero:
      If total_count <= 0, returns 0.0 safely.
    """
    if total_count <= 0:
        return 0.0
    pct = (completed_count / total_count) * 100.0
    pct = max(0.0, min(100.0, pct))
    return round(pct, 1)


def generate_learning_path_plan(missing_skills: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Generate an ordered list of learning path steps from missing skills.

    Parameters
    ----------
    missing_skills : list of dicts
        Each dict contains:
          - id or skill_id: int
          - name or skill_name: str
          - difficulty: str ('Beginner', 'Intermediate', 'Advanced') or int (1-3)
          - importance: int (1 to 5)

    Ordering Logic:
      - Skill difficulty ascending (Beginner -> Intermediate -> Advanced)
      - Ties broken by importance descending (5 -> 1)
      - Ties broken by name alphabetically (A -> Z)

    Returns
    -------
    list of dicts:
      One item per missing skill, followed by:
      - Phase N+1: 'Build a project using these skills'
      - Phase N+2: 'Update your resume'
    """
    # Defensive copy & sorting key
    def sort_key(s: Dict[str, Any]) -> Tuple[int, int, str]:
        diff_rank = get_difficulty_rank(s.get('difficulty', 'Beginner'))
        importance = int(s.get('importance', 3) or 3)
        name = str(s.get('name') or s.get('skill_name') or '').lower()
        # diff_rank ascending, importance descending (negated), name ascending
        return (diff_rank, -importance, name)

    sorted_skills = sorted(missing_skills, key=sort_key)

    phases: List[Dict[str, Any]] = []
    phase_num = 1

    for s in sorted_skills:
        skill_id = s.get('id') if s.get('id') is not None else s.get('skill_id')
        name = s.get('name') or s.get('skill_name') or f"Skill #{skill_id}"
        diff = s.get('difficulty', 'Beginner')
        imp = int(s.get('importance', 3) or 3)

        phases.append({
            'phase_number': phase_num,
            'position': phase_num,
            'phase_label': f"Master {name}",
            'title': f"Master {name}",
            'item_type': 'skill',
            'skill_id': int(skill_id) if skill_id is not None else None,
            'skill_name': name,
            'difficulty': diff if isinstance(diff, str) else ('Beginner' if diff == 1 else ('Intermediate' if diff == 2 else 'Advanced')),
            'importance': imp,
            'description': f"Master {name} to close your skill gap for the target job.",
            'display_order': phase_num,
        })
        phase_num += 1

    # Phase N+1: Capstone project
    phases.append({
        'phase_number': phase_num,
        'position': phase_num,
        'phase_label': PROJECT_PHASE_LABEL,
        'title': PROJECT_PHASE_LABEL,
        'item_type': 'project',
        'skill_id': None,
        'skill_name': None,
        'difficulty': 'Intermediate',
        'importance': 5,
        'description': "Build a hands-on portfolio project applying the skills learned in this path.",
        'display_order': phase_num,
    })
    phase_num += 1

    # Phase N+2: Resume update
    phases.append({
        'phase_number': phase_num,
        'position': phase_num,
        'phase_label': RESUME_PHASE_LABEL,
        'title': RESUME_PHASE_LABEL,
        'item_type': 'resume_update',
        'skill_id': None,
        'skill_name': None,
        'difficulty': 'Beginner',
        'importance': 5,
        'description': "Update your resume and technical profiles with your newly acquired skills and project.",
        'display_order': phase_num,
    })

    return phases


# Alias for compatibility with prompt specification
generate_learning_path_phases = generate_learning_path_plan

