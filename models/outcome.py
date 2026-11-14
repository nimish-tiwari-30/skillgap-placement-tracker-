"""
models/outcome.py
─────────────────
SQLAlchemy ORM model for employment outcome tracking.
Used as the target label (Placed / Not Placed) for ML model training.
"""

from datetime import datetime
from extensions import db


class EmploymentOutcome(db.Model):
    """
    Records the placement result for a student.
    One-to-one with Student (each student has at most one outcome record).

    DATA LEAKAGE NOTE (Important for viva):
    Only fields known BEFORE placement decision should be used as ML features.
    company_name, salary_package_lpa, placement_date are outcomes — never features.
    """
    __tablename__ = 'employment_outcomes'

    id                  = db.Column(db.Integer, primary_key=True)
    student_id          = db.Column(db.Integer, db.ForeignKey('students.id', ondelete='CASCADE'), nullable=False, unique=True)
    status              = db.Column(
        db.Enum('Placed', 'Not Placed', 'In Progress', name='placement_status_enum'),
        nullable=False, default='In Progress'
    )
    company_name        = db.Column(db.String(255), nullable=True)
    role_title          = db.Column(db.String(255), nullable=True)
    salary_package_lpa  = db.Column(db.Numeric(8, 2), nullable=True)
    placement_date      = db.Column(db.Date, nullable=True, index=True)
    placement_type      = db.Column(
        db.Enum('Campus', 'Off-Campus', 'Internship-Converted', 'Unknown', name='placement_type_enum'),
        nullable=True, default='Unknown'
    )
    notes               = db.Column(db.Text, nullable=True)
    updated_at          = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    student = db.relationship('Student', back_populates='employment_outcome')
    skills_used = db.relationship('EmploymentOutcomeSkill', back_populates='outcome', cascade='all, delete-orphan', passive_deletes=True)

    def is_placed(self) -> bool:
        return self.status == 'Placed'

    def __repr__(self) -> str:
        return f'<EmploymentOutcome student={self.student_id} status={self.status}>'


class EmploymentOutcomeSkill(db.Model):
    """
    Junction table linking employment outcomes with the skills utilized in the job.
    One outcome can have multiple skills used.
    """
    __tablename__ = 'employment_outcome_skills'

    id          = db.Column(db.Integer, primary_key=True)
    outcome_id  = db.Column(db.Integer, db.ForeignKey('employment_outcomes.id', ondelete='CASCADE'), nullable=False)
    skill_id    = db.Column(db.Integer, db.ForeignKey('skills.id', ondelete='CASCADE'), nullable=False)

    __table_args__ = (
        db.UniqueConstraint('outcome_id', 'skill_id', name='uq_outcome_skill'),
    )

    skill = db.relationship('Skill')
    outcome = db.relationship('EmploymentOutcome', back_populates='skills_used')

    def __repr__(self) -> str:
        return f'<EmploymentOutcomeSkill outcome_id={self.outcome_id} skill_id={self.skill_id}>'

