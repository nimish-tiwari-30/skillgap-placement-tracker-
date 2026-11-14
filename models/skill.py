"""
models/skill.py
───────────────
SQLAlchemy ORM models for the skills subsystem:
skills, skill_aliases, student_skills, resumes
"""

from datetime import datetime
from extensions import db


class Skill(db.Model):
    """Master canonical skills dictionary. All skill references point here."""
    __tablename__ = 'skills'

    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(100), nullable=False, unique=True)
    category    = db.Column(db.String(100), nullable=True, index=True)
    description = db.Column(db.Text, nullable=True)
    created_at  = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    aliases         = db.relationship('SkillAlias', back_populates='skill', cascade='all, delete-orphan')
    student_skills  = db.relationship('StudentSkill', back_populates='skill', cascade='all, delete-orphan')
    job_skills      = db.relationship('JobSkill', back_populates='skill', cascade='all, delete-orphan')
    course_skills   = db.relationship('CourseSkill', back_populates='skill', cascade='all, delete-orphan')
    gap_skills      = db.relationship('GapSkill', back_populates='skill', cascade='all, delete-orphan')

    def __repr__(self) -> str:
        return f'<Skill id={self.id} name={self.name} category={self.category}>'


class SkillAlias(db.Model):
    """
    Maps raw/alternate skill strings to canonical skills.
    e.g. "ms excel" -> Skill(name="Excel")
         "power-bi" -> Skill(name="Power BI")
    Stored in DB (not scattered in code) for easy admin management.
    """
    __tablename__ = 'skill_aliases'

    id          = db.Column(db.Integer, primary_key=True)
    skill_id    = db.Column(db.Integer, db.ForeignKey('skills.id', ondelete='CASCADE'), nullable=False)
    alias_name  = db.Column(db.String(150), nullable=False, unique=True)

    skill = db.relationship('Skill', back_populates='aliases')

    def __repr__(self) -> str:
        return f'<SkillAlias alias={self.alias_name} -> skill_id={self.skill_id}>'


class StudentSkill(db.Model):
    """
    Links a student to a canonical skill with proficiency.
    Source indicates whether manually added or extracted from resume.
    """
    __tablename__ = 'student_skills'

    id                  = db.Column(db.Integer, primary_key=True)
    student_id          = db.Column(db.Integer, db.ForeignKey('students.id', ondelete='CASCADE'), nullable=False)
    skill_id            = db.Column(db.Integer, db.ForeignKey('skills.id', ondelete='CASCADE'), nullable=False)
    proficiency_level   = db.Column(
        db.Enum('Beginner', 'Intermediate', 'Advanced', name='proficiency_enum2'),
        nullable=False, default='Beginner'
    )
    source              = db.Column(
        db.Enum('manual', 'resume', 'course', name='skill_source_enum'),
        nullable=False, default='manual'
    )
    created_at          = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # Unique constraint — student can't have same skill twice
    __table_args__ = (
        db.UniqueConstraint('student_id', 'skill_id', name='uq_student_skill'),
    )

    student = db.relationship('Student', back_populates='skills')
    skill   = db.relationship('Skill', back_populates='student_skills')

    def __repr__(self) -> str:
        return f'<StudentSkill student={self.student_id} skill={self.skill_id} level={self.proficiency_level}>'


class Resume(db.Model):
    """
    Stores metadata about uploaded resume files.
    File contents are NOT stored in DB — only file path is stored.
    Binary data in DB is an anti-pattern for large files.
    """
    __tablename__ = 'resumes'

    id              = db.Column(db.Integer, primary_key=True)
    student_id      = db.Column(db.Integer, db.ForeignKey('students.id', ondelete='CASCADE'), nullable=False)
    original_name   = db.Column(db.String(255), nullable=False)
    stored_filename = db.Column(db.String(255), nullable=False)
    file_path       = db.Column(db.String(500), nullable=False)
    file_type       = db.Column(db.Enum('pdf', 'docx', name='resume_type_enum'), nullable=False)
    file_size_kb    = db.Column(db.Integer, nullable=True)
    extracted_text  = db.Column(db.Text, nullable=True)
    is_active       = db.Column(db.Boolean, nullable=False, default=True)
    uploaded_at     = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    student = db.relationship('Student', back_populates='resumes')

    def __repr__(self) -> str:
        return f'<Resume id={self.id} student={self.student_id} file={self.original_name}>'
