"""
models/job.py
─────────────
SQLAlchemy ORM models for job roles and job descriptions:
job_roles, job_descriptions, job_skills
"""

from datetime import datetime
from extensions import db


class JobRole(db.Model):
    """
    High-level career target category.
    e.g. "Data Analyst", "Backend Developer", "DevOps Engineer"
    Students pick a target JobRole to analyze their gap against.
    """
    __tablename__ = 'job_roles'

    id          = db.Column(db.Integer, primary_key=True)
    title       = db.Column(db.String(150), nullable=False, unique=True)
    department  = db.Column(db.String(100), nullable=True, index=True)
    description = db.Column(db.Text, nullable=True)
    created_at  = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # One job role can have many job descriptions (different companies/JDs)
    job_descriptions    = db.relationship('JobDescription', back_populates='job_role', cascade='all, delete-orphan')
    gap_analyses        = db.relationship('SkillGapAnalysis', back_populates='job_role', cascade='all, delete-orphan')

    def __repr__(self) -> str:
        return f'<JobRole id={self.id} title={self.title}>'


class JobDescription(db.Model):
    """
    Detailed job posting linked to a JobRole.
    Contains the full description text used for TF-IDF cosine similarity.
    """
    __tablename__ = 'job_descriptions'

    id              = db.Column(db.Integer, primary_key=True)
    job_role_id     = db.Column(db.Integer, db.ForeignKey('job_roles.id', ondelete='CASCADE'), nullable=False)
    title           = db.Column(db.String(255), nullable=False)
    company_name    = db.Column(db.String(255), nullable=True)
    description_text = db.Column(db.Text, nullable=False)
    min_experience  = db.Column(db.String(50), nullable=True, default='0 years')
    location        = db.Column(db.String(150), nullable=True)
    is_active       = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at      = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    job_role    = db.relationship('JobRole', back_populates='job_descriptions')
    job_skills  = db.relationship('JobSkill', back_populates='job_description', cascade='all, delete-orphan')
    gap_analyses = db.relationship('SkillGapAnalysis', back_populates='job_description')

    def __repr__(self) -> str:
        return f'<JobDescription id={self.id} title={self.title} role_id={self.job_role_id}>'


class JobSkill(db.Model):
    """
    Maps a required skill to a job description with an importance weight.
    importance_weight: 1 = Nice to have, 5 = Absolutely required.
    Used in weighted coverage % calculation.
    """
    __tablename__ = 'job_skills'

    id                  = db.Column(db.Integer, primary_key=True)
    job_description_id  = db.Column(db.Integer, db.ForeignKey('job_descriptions.id', ondelete='CASCADE'), nullable=False)
    skill_id            = db.Column(db.Integer, db.ForeignKey('skills.id', ondelete='CASCADE'), nullable=False)
    importance_weight   = db.Column(db.SmallInteger, nullable=False, default=3)

    __table_args__ = (
        db.UniqueConstraint('job_description_id', 'skill_id', name='uq_job_skill'),
    )

    job_description = db.relationship('JobDescription', back_populates='job_skills')
    skill           = db.relationship('Skill', back_populates='job_skills')

    def __repr__(self) -> str:
        return f'<JobSkill jd={self.job_description_id} skill={self.skill_id} weight={self.importance_weight}>'
