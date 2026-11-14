"""
models/course.py
────────────────
SQLAlchemy ORM models for the course recommendation subsystem:
courses, course_skills, course_progress, learning_path_items
"""

from datetime import datetime
from extensions import db


class Course(db.Model):
    """
    Course catalog for recommendations.
    Courses are recommended based on missing skills from gap analysis.
    """
    __tablename__ = 'courses'

    id              = db.Column(db.Integer, primary_key=True)
    title           = db.Column(db.String(255), nullable=False)
    provider        = db.Column(db.String(150), nullable=True)
    difficulty_level = db.Column(
        db.Enum('Beginner', 'Intermediate', 'Advanced', name='course_difficulty_enum'),
        nullable=False, default='Beginner'
    )
    duration_hours  = db.Column(db.Numeric(6, 1), nullable=True)
    rating          = db.Column(db.Numeric(3, 2), nullable=True, index=True)
    url             = db.Column(db.String(500), nullable=True)
    description     = db.Column(db.Text, nullable=True)
    is_free         = db.Column(db.Boolean, nullable=False, default=False)
    created_at      = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    course_skills   = db.relationship('CourseSkill', back_populates='course', cascade='all, delete-orphan')
    progress        = db.relationship('CourseProgress', back_populates='course', cascade='all, delete-orphan')

    def __repr__(self) -> str:
        return f'<Course id={self.id} title={self.title} difficulty={self.difficulty_level}>'


class CourseSkill(db.Model):
    """Maps courses to the skills they teach (many-to-many bridge)."""
    __tablename__ = 'course_skills'

    id          = db.Column(db.Integer, primary_key=True)
    course_id   = db.Column(db.Integer, db.ForeignKey('courses.id', ondelete='CASCADE'), nullable=False)
    skill_id    = db.Column(db.Integer, db.ForeignKey('skills.id', ondelete='CASCADE'), nullable=False)

    __table_args__ = (
        db.UniqueConstraint('course_id', 'skill_id', name='uq_course_skill'),
    )

    course  = db.relationship('Course', back_populates='course_skills')
    skill   = db.relationship('Skill', back_populates='course_skills')

    def __repr__(self) -> str:
        return f'<CourseSkill course={self.course_id} skill={self.skill_id}>'


class CourseProgress(db.Model):
    """Tracks a student's enrollment and completion status for a course."""
    __tablename__ = 'course_progress'

    id              = db.Column(db.Integer, primary_key=True)
    student_id      = db.Column(db.Integer, db.ForeignKey('students.id', ondelete='CASCADE'), nullable=False)
    course_id       = db.Column(db.Integer, db.ForeignKey('courses.id', ondelete='CASCADE'), nullable=False)
    status          = db.Column(
        db.Enum('not_started', 'in_progress', 'completed', name='course_status_enum'),
        nullable=False, default='not_started'
    )
    started_at      = db.Column(db.DateTime, nullable=True)
    completed_at    = db.Column(db.DateTime, nullable=True)

    __table_args__ = (
        db.UniqueConstraint('student_id', 'course_id', name='uq_course_progress'),
    )

    student = db.relationship('Student', back_populates='course_progress')
    course  = db.relationship('Course', back_populates='progress')

    def __repr__(self) -> str:
        return f'<CourseProgress student={self.student_id} course={self.course_id} status={self.status}>'


class LearningPathItem(db.Model):
    """
    Ordered learning steps for a student, generated from gap analysis.
    Items are grouped into phases:
      Phase 1–N: Learn missing skills (ordered by difficulty/importance)
      Phase N+1: Build a capstone project
      Phase N+2: Resume update
    """
    __tablename__ = 'learning_path_items'

    id              = db.Column(db.Integer, primary_key=True)
    student_id      = db.Column(db.Integer, db.ForeignKey('students.id', ondelete='CASCADE'), nullable=False)
    analysis_id     = db.Column(db.Integer, db.ForeignKey('skill_gap_analysis.id', ondelete='SET NULL'), nullable=True)
    skill_id        = db.Column(db.Integer, db.ForeignKey('skills.id', ondelete='SET NULL'), nullable=True)
    phase_number    = db.Column(db.SmallInteger, nullable=False, default=1)
    phase_label     = db.Column(db.String(100), nullable=True)
    item_type       = db.Column(
        db.Enum('skill', 'project', 'resume_update', name='lpi_type_enum'),
        nullable=False, default='skill'
    )
    description     = db.Column(db.Text, nullable=True)
    is_completed    = db.Column(db.Boolean, nullable=False, default=False)
    completed_at    = db.Column(db.DateTime, nullable=True)
    display_order   = db.Column(db.Integer, nullable=False, default=0)
    created_at      = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    student     = db.relationship('Student', back_populates='learning_path')
    analysis    = db.relationship('SkillGapAnalysis', back_populates='learning_path')
    skill       = db.relationship('Skill')

    @property
    def status(self) -> str:
        return 'completed' if self.is_completed else 'pending'

    @status.setter
    def status(self, value: str) -> None:
        self.is_completed = (str(value).strip().lower() == 'completed')

    @property
    def position(self) -> int:
        return self.display_order or self.phase_number

    @position.setter
    def position(self, val: int) -> None:
        self.display_order = val
        self.phase_number = val

    def __repr__(self) -> str:
        return f'<LearningPathItem id={self.id} student={self.student_id} phase={self.phase_number} completed={self.is_completed}>'
