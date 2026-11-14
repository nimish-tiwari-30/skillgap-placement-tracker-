"""
models/__init__.py
──────────────────
Exports all models from a single import point.
Usage: from models import User, Student, Skill, ...
"""

from models.user import User
from models.student import Student, Certification, Project, Internship, SkillProgress
from models.skill import Skill, SkillAlias, StudentSkill, Resume
from models.job import JobRole, JobDescription, JobSkill
from models.gap import SkillGapAnalysis, GapSkill
from models.course import Course, CourseSkill, CourseProgress, LearningPathItem
from models.outcome import EmploymentOutcome

__all__ = [
    'User',
    'Student', 'Certification', 'Project', 'Internship', 'SkillProgress',
    'Skill', 'SkillAlias', 'StudentSkill', 'Resume',
    'JobRole', 'JobDescription', 'JobSkill',
    'SkillGapAnalysis', 'GapSkill',
    'Course', 'CourseSkill', 'CourseProgress', 'LearningPathItem',
    'EmploymentOutcome',
]
