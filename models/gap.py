"""
models/gap.py
─────────────
SQLAlchemy ORM models for skill gap analysis results:
skill_gap_analysis, gap_skills
"""

from datetime import datetime
from extensions import db


class SkillGapAnalysis(db.Model):
    """
    Stores a snapshot of a student's skill gap analysis result.
    One student can run analysis multiple times; each run saved separately.
    Scores stored: unweighted %, weighted %, cosine similarity.
    """
    __tablename__ = 'skill_gap_analysis'

    id                      = db.Column(db.Integer, primary_key=True)
    student_id              = db.Column(db.Integer, db.ForeignKey('students.id', ondelete='CASCADE'), nullable=False)
    job_role_id             = db.Column(db.Integer, db.ForeignKey('job_roles.id', ondelete='CASCADE'), nullable=False)
    job_description_id      = db.Column(db.Integer, db.ForeignKey('job_descriptions.id', ondelete='SET NULL'), nullable=True)
    unweighted_coverage_pct = db.Column(db.Numeric(5, 2), nullable=True)
    weighted_coverage_pct   = db.Column(db.Numeric(5, 2), nullable=True)
    cosine_similarity_score = db.Column(db.Numeric(5, 4), nullable=True)
    analyzed_at             = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    student         = db.relationship('Student', back_populates='gap_analyses')
    job_role        = db.relationship('JobRole', back_populates='gap_analyses')
    job_description = db.relationship('JobDescription', back_populates='gap_analyses')
    gap_skills      = db.relationship('GapSkill', back_populates='analysis', cascade='all, delete-orphan')
    learning_path   = db.relationship('LearningPathItem', back_populates='analysis', cascade='all, delete-orphan')

    def __repr__(self) -> str:
        return (f'<SkillGapAnalysis id={self.id} student={self.student_id} '
                f'job_role={self.job_role_id} coverage={self.unweighted_coverage_pct}%>')


class GapSkill(db.Model):
    """
    Per-skill status result from a gap analysis.
    Status:
      Matched = skill is in both student profile AND job required (R ∩ S)
      Missing = skill required by job but student doesn't have it (R - S)
      Extra   = student has skill but job doesn't require it (S - R)
    """
    __tablename__ = 'gap_skills'

    id          = db.Column(db.Integer, primary_key=True)
    analysis_id = db.Column(db.Integer, db.ForeignKey('skill_gap_analysis.id', ondelete='CASCADE'), nullable=False)
    skill_id    = db.Column(db.Integer, db.ForeignKey('skills.id', ondelete='CASCADE'), nullable=False)
    status      = db.Column(db.Enum('Matched', 'Missing', 'Extra', name='gap_status_enum'), nullable=False)

    __table_args__ = (
        db.UniqueConstraint('analysis_id', 'skill_id', name='uq_gap_skill'),
    )

    analysis    = db.relationship('SkillGapAnalysis', back_populates='gap_skills')
    skill       = db.relationship('Skill', back_populates='gap_skills')

    def __repr__(self) -> str:
        return f'<GapSkill analysis={self.analysis_id} skill={self.skill_id} status={self.status}>'
