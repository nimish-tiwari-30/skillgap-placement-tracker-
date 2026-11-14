"""
models/student.py
─────────────────
SQLAlchemy ORM models for student profile and all portfolio tables:
students, certifications, projects, internships, skill_progress
"""

from datetime import datetime
from extensions import db


class Student(db.Model):
    """Extended profile data for users with role='student'."""
    __tablename__ = 'students'

    id                      = db.Column(db.Integer, primary_key=True)
    user_id                 = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, unique=True)
    full_name               = db.Column(db.String(150), nullable=False)
    roll_number             = db.Column(db.String(50), nullable=False, unique=True)
    branch                  = db.Column(db.String(100), nullable=False)
    cgpa                    = db.Column(db.Numeric(4, 2), nullable=True)
    graduation_year         = db.Column(db.SmallInteger, nullable=True)
    phone                   = db.Column(db.String(20), nullable=True)
    linkedin_url            = db.Column(db.String(255), nullable=True)
    github_url              = db.Column(db.String(255), nullable=True)
    profile_completion_pct  = db.Column(db.SmallInteger, nullable=False, default=0)
    target_job_id           = db.Column(db.Integer, db.ForeignKey('job_descriptions.id', ondelete='SET NULL'), nullable=True)
    # Phase 14: ML features — aptitude & communication scores (0–100), known before outcome
    aptitude_score          = db.Column(db.SmallInteger, nullable=True)
    communication_score     = db.Column(db.SmallInteger, nullable=True)
    created_at              = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at              = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user                = db.relationship('User', back_populates='student')
    target_job          = db.relationship('JobDescription', foreign_keys=[target_job_id])
    skills              = db.relationship('StudentSkill', back_populates='student', cascade='all, delete-orphan')
    resumes             = db.relationship('Resume', back_populates='student', cascade='all, delete-orphan')
    certifications      = db.relationship('Certification', back_populates='student', cascade='all, delete-orphan')
    projects            = db.relationship('Project', back_populates='student', cascade='all, delete-orphan')
    internships         = db.relationship('Internship', back_populates='student', cascade='all, delete-orphan')
    gap_analyses        = db.relationship('SkillGapAnalysis', back_populates='student', cascade='all, delete-orphan')
    employment_outcome  = db.relationship('EmploymentOutcome', back_populates='student', uselist=False, cascade='all, delete-orphan')
    learning_path       = db.relationship('LearningPathItem', back_populates='student', cascade='all, delete-orphan')
    course_progress     = db.relationship('CourseProgress', back_populates='student', cascade='all, delete-orphan')
    skill_progress      = db.relationship('SkillProgress', back_populates='student', cascade='all, delete-orphan')

    def calculate_profile_completion(self) -> int:
        """
        Compute profile completion % based on documented system weights.
        Called after profile, skill, or resume updates to keep completion % fresh.
        """
        from services.profile_service import calculate_profile_completion
        return calculate_profile_completion(self)['percentage']

    def __repr__(self) -> str:
        return f'<Student id={self.id} name={self.full_name} branch={self.branch}>'


class Certification(db.Model):
    """Student certifications from external providers."""
    __tablename__ = 'certifications'

    id              = db.Column(db.Integer, primary_key=True)
    student_id      = db.Column(db.Integer, db.ForeignKey('students.id', ondelete='CASCADE'), nullable=False)
    title           = db.Column(db.String(255), nullable=False)
    issuing_org     = db.Column(db.String(255), nullable=True)
    issue_date      = db.Column(db.Date, nullable=True)
    expiry_date     = db.Column(db.Date, nullable=True)
    credential_url  = db.Column(db.String(500), nullable=True)
    created_at      = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    student = db.relationship('Student', back_populates='certifications')

    def __repr__(self) -> str:
        return f'<Certification id={self.id} title={self.title}>'


class Project(db.Model):
    """Student academic or personal project records."""
    __tablename__ = 'projects'

    id          = db.Column(db.Integer, primary_key=True)
    student_id  = db.Column(db.Integer, db.ForeignKey('students.id', ondelete='CASCADE'), nullable=False)
    title       = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    tech_stack  = db.Column(db.String(500), nullable=True)
    project_url = db.Column(db.String(500), nullable=True)
    start_date  = db.Column(db.Date, nullable=True)
    end_date    = db.Column(db.Date, nullable=True)
    created_at  = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    student = db.relationship('Student', back_populates='projects')

    def __repr__(self) -> str:
        return f'<Project id={self.id} title={self.title}>'


class Internship(db.Model):
    """Student internship experience records."""
    __tablename__ = 'internships'

    id              = db.Column(db.Integer, primary_key=True)
    student_id      = db.Column(db.Integer, db.ForeignKey('students.id', ondelete='CASCADE'), nullable=False)
    company_name    = db.Column(db.String(255), nullable=False)
    role_title      = db.Column(db.String(255), nullable=False)
    description     = db.Column(db.Text, nullable=True)
    start_date      = db.Column(db.Date, nullable=True)
    end_date        = db.Column(db.Date, nullable=True)
    is_current      = db.Column(db.Boolean, nullable=False, default=False)
    created_at      = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    student = db.relationship('Student', back_populates='internships')

    def __repr__(self) -> str:
        return f'<Internship id={self.id} company={self.company_name}>'


class SkillProgress(db.Model):
    """Tracks improvement of a student's skill proficiency over time."""
    __tablename__ = 'skill_progress'

    id              = db.Column(db.Integer, primary_key=True)
    student_id      = db.Column(db.Integer, db.ForeignKey('students.id', ondelete='CASCADE'), nullable=False)
    skill_id        = db.Column(db.Integer, db.ForeignKey('skills.id', ondelete='CASCADE'), nullable=False)
    old_proficiency = db.Column(db.Enum('Beginner', 'Intermediate', 'Advanced', name='proficiency_enum'), nullable=True)
    new_proficiency = db.Column(db.Enum('Beginner', 'Intermediate', 'Advanced', name='proficiency_enum'), nullable=False)
    recorded_at     = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    student = db.relationship('Student', back_populates='skill_progress')
    skill   = db.relationship('Skill')

    def __repr__(self) -> str:
        return f'<SkillProgress student={self.student_id} skill={self.skill_id} {self.old_proficiency}->{self.new_proficiency}>'
