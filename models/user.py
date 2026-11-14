"""
models/user.py
──────────────
SQLAlchemy ORM model for the `users` table.
Implements Flask-Login's UserMixin for session management.
"""

from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db


class User(UserMixin, db.Model):
    """
    Base authentication model for all system users.
    UserMixin provides: is_authenticated, is_active, is_anonymous, get_id()
    """
    __tablename__ = 'users'

    id              = db.Column(db.Integer, primary_key=True)
    email           = db.Column(db.String(255), nullable=False, unique=True, index=True)
    password_hash   = db.Column(db.String(255), nullable=False)
    role            = db.Column(db.Enum('student', 'admin', name='user_role'), nullable=False, default='student')
    is_active       = db.Column(db.Boolean, nullable=False, default=True)
    created_at      = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at      = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # One-to-one relationship: a user has one student profile
    student = db.relationship('Student', back_populates='user', uselist=False, cascade='all, delete-orphan')

    def set_password(self, password: str) -> None:
        """Hash and store the password using Werkzeug's secure pbkdf2:sha256 hashing."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Verify a plaintext password against the stored hash."""
        return check_password_hash(self.password_hash, password)

    def is_admin(self) -> bool:
        """Check if this user has admin role."""
        return self.role == 'admin'

    def is_student(self) -> bool:
        """Check if this user has student role."""
        return self.role == 'student'

    def __repr__(self) -> str:
        return f'<User id={self.id} email={self.email} role={self.role}>'
