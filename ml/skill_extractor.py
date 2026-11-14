"""
ml/skill_extractor.py
─────────────────────
NLP skill extraction engine using dictionary and alias phrase matching.

Pipeline:
1. Normalization: clean whitespace, lowercase comparison, preserve special symbols (+, #, ., -).
2. Word-boundary & Symbol-aware Regex:
   Uses negative lookbehind/lookahead `(?<![a-zA-Z0-9#+])PATTERN(?![a-zA-Z0-9#+])`
   to ensure exact token boundaries so "Java" does not match within "JavaScript",
   while properly matching technical tokens like C++, C#, .NET, Node.js, and scikit-learn.
3. Overlap Span Protection:
   Matches longer phrases first (e.g., "Python Programming" before "Python", "MS Excel"
   before "Excel") so substring tokens do not duplicate count the same text segment.
4. Ambiguity Guard:
   Short tokens like "C" and "R" require explicit aliases ("C Programming") or technical
   context (e.g. "C/C++", "Languages: C") to avoid false positives on random letters.
5. In-Memory Caching:
   Caches the canonical dictionary and alias mapping from the database, with a
   refresh_cache() method to reload when skills are added by admin.

LIMITATION:
This is a rule-based dictionary & alias matching extractor. It can only detect skills
and aliases recorded in the database skills catalog. It will not identify unlisted
frameworks or domain jargon unless added to the master dictionary.
"""

import re
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class SkillExtractor:
    """
    Extracts canonical skills from document text using a database-backed
    dictionary and alias catalog with boundary and span overlap protection.
    """

    def __init__(self):
        self._targets = None       # List of (pattern, canonical_name, category, skill_id, is_short)
        self._skill_map = {}       # skill_id -> Skill
        self._loaded = False

    def load_dictionary(self, force_refresh: bool = False):
        """
        Load canonical skills and aliases from the database into in-memory cache.
        Safe to call repeatedly; only queries the DB if not yet loaded or forced.
        """
        if self._loaded and not force_refresh:
            return

        from models.skill import Skill, SkillAlias

        try:
            skills = Skill.query.all()
            aliases = SkillAlias.query.all()
        except Exception as e:
            logger.warning(f"Could not load skills from DB: {e}")
            return

        self._skill_map = {s.id: s for s in skills}

        targets = []
        # Add canonical skill names
        for skill in skills:
            name = skill.name.strip()
            if name:
                is_short = len(name) <= 2
                targets.append((name, skill.name, skill.category or 'General', skill.id, is_short))

        # Add aliases
        for alias in aliases:
            alias_name = alias.alias_name.strip()
            if alias_name and alias.skill_id in self._skill_map:
                canonical = self._skill_map[alias.skill_id]
                is_short = len(alias_name) <= 2
                targets.append((alias_name, canonical.name, canonical.category or 'General', canonical.id, is_short))

        # Sort descending by pattern length so longer phrases claim spans first
        targets.sort(key=lambda t: len(t[0]), reverse=True)

        self._targets = targets
        self._loaded = True

    def refresh_cache(self):
        """Force reload the skills dictionary from the database."""
        self.load_dictionary(force_refresh=True)

    def extract_skills(self, text: str) -> List[Dict[str, Any]]:
        """
        Extract canonical skills from text.
        Returns a list of dicts:
        [
            {
                'canonical_name': 'Python',
                'name': 'Python',
                'matched_text': 'Python Programming',
                'count': 2,
                'category': 'Programming',
                'skill_id': 1
            },
            ...
        ]
        Ordered by occurrence count descending, then by name.
        """
        if not text or not text.strip():
            return []

        self.load_dictionary()
        if not self._targets:
            return []

        clean_content = text
        lower_content = text.lower()

        # Track spans (start, end) already claimed by longer matches
        claimed_spans = []
        # Store results keyed by canonical skill name
        found_skills: Dict[str, Dict[str, Any]] = {}

        for pattern, canonical_name, category, skill_id, is_short in self._targets:
            token = pattern.strip()
            if not token:
                continue

            # ── Ambiguous single-letter safeguards ───────────────────────────
            if token.upper() == 'C':
                # Check for explicit programming context (e.g. C/C++, C and Python, Languages: C)
                c_pattern = r'(?<![a-zA-Z0-9#+])C(?![a-zA-Z0-9#+])\s*(?:/|,|and)\s*(?:C\+\+|Java|Python|C#|SQL)'
                lang_context = r'(?:programming\s+languages?|languages?|skills?|technologies?)\s*:[^\n]*\bC\b'
                if not (re.search(c_pattern, clean_content) or re.search(lang_context, clean_content, re.IGNORECASE)):
                    continue

            elif token.upper() == 'R':
                # Check for explicit analytics context
                r_pattern = r'(?<![a-zA-Z0-9#+])R(?![a-zA-Z0-9#+])\s*(?:/|,|and)\s*(?:Python|SQL|Statistics|SAS|SPSS|Tableau)'
                lang_context = r'(?:programming\s+languages?|languages?|skills?|technologies?)\s*:[^\n]*\bR\b'
                if not (re.search(r_pattern, clean_content) or re.search(lang_context, clean_content, re.IGNORECASE)):
                    continue

            elif token.lower() == 'go':
                # Word "go" is very common in English; match only in technical list context or if 'Golang' present
                go_pattern = r'(?:languages?|skills?|technologies?)\s*:[^\n]*\bGo\b'
                if not (re.search(go_pattern, clean_content) or 'golang' in lower_content):
                    continue

            # ── Regex with exact boundaries preserving +, #, ., - ────────────
            escaped = re.escape(token)
            # Boundary allows special characters like C++, C#, .NET, Node.js, scikit-learn
            regex = re.compile(
                r'(?<![a-zA-Z0-9#+])' + escaped + r'(?![a-zA-Z0-9#+])',
                re.IGNORECASE
            )

            matches = list(regex.finditer(clean_content))
            valid_occurrences = 0
            first_match_text = token

            for m in matches:
                span = (m.start(), m.end())
                # Check for span overlap with an already matched longer phrase
                overlaps = any(s <= span[0] < e or s < span[1] <= e for s, e in claimed_spans)
                if not overlaps:
                    claimed_spans.append(span)
                    valid_occurrences += 1
                    if valid_occurrences == 1:
                        first_match_text = m.group(0)

            if valid_occurrences > 0:
                if canonical_name in found_skills:
                    found_skills[canonical_name]['count'] += valid_occurrences
                else:
                    found_skills[canonical_name] = {
                        'canonical_name': canonical_name,
                        'name': canonical_name,
                        'matched_text': first_match_text,
                        'count': valid_occurrences,
                        'category': category,
                        'skill_id': skill_id
                    }

        # Convert to list and sort by occurrence count descending, then name
        results = list(found_skills.values())
        results.sort(key=lambda x: (-x['count'], x['canonical_name']))
        return results


# Module-level singleton
extractor = SkillExtractor()


def extract_skills_from_text(text: str) -> List[Dict[str, Any]]:
    """Helper function to extract skills from text using the default extractor."""
    return extractor.extract_skills(text)


def refresh_skills_cache():
    """Helper function to refresh the in-memory skills dictionary."""
    extractor.refresh_cache()
