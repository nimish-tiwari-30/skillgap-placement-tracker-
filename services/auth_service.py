"""
services/auth_service.py
─────────────────────────
Business logic for authentication.

WHY A SERVICE LAYER? (viva answer)
  Routes should only handle HTTP — receive request, call service, return response.
  Business logic (DB queries, validation, hashing) lives here so it can be
  tested independently without a running Flask server.

Functions:
  register_student(form_data) → (success: bool, error_msg: str | None)
  authenticate_user(email, password) → (User | None, error_msg: str | None)
  email_exists(email) → bool
  rollno_exists(roll_number) → bool
"""

from extensions import db
from models.user import User
from models.student import Student


# ── Registration ─────────────────────────────────────────────────────────────

def email_exists(email: str) -> bool:
    """Return True if email is already registered."""
    return db.session.query(
        User.query.filter_by(email=email.strip().lower()).exists()
    ).scalar()


def rollno_exists(roll_number: str) -> bool:
    """Return True if roll number is already in students table."""
    return db.session.query(
        Student.query.filter_by(roll_number=roll_number.strip().upper()).exists()
    ).scalar()


def register_student(form_data: dict) -> tuple[bool, str | None]:
    """
    Create a new student user account.

    Steps:
      1. Validate all required fields are present.
      2. Check for duplicate email / roll number.
      3. Create User record with hashed password.
      4. Create Student profile linked to that User.
      5. Commit to DB — both records saved atomically.

    Returns:
      (True, None)          — success
      (False, error_msg)    — validation or DB error
    """
    # ── 1. Required field check ───────────────────────────────────
    required = ['full_name', 'email', 'roll_number', 'branch', 'password', 'confirm_password']
    for field in required:
        if not form_data.get(field, '').strip():
            return False, f"'{field.replace('_', ' ').title()}' is required."

    full_name        = form_data['full_name'].strip()
    email            = form_data['email'].strip().lower()
    roll_number      = form_data['roll_number'].strip().upper()
    branch           = form_data['branch'].strip()
    password         = form_data['password']
    confirm_password = form_data['confirm_password']

    # ── 2. Password match ─────────────────────────────────────────
    if password != confirm_password:
        return False, "Passwords do not match."

    if len(password) < 8:
        return False, "Password must be at least 8 characters."

    # ── 3. Duplicate checks ────────────────────────────────────────
    if User.query.filter_by(email=email).first():
        return False, "An account with this email already exists."

    if Student.query.filter_by(roll_number=roll_number).first():
        return False, "This roll number is already registered."

    # ── 4. Create User + Student (atomic) ─────────────────────────
    try:
        user = User(
            email=email,
            role='student',
            is_active=True,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.flush()          # Get user.id without committing yet

        student = Student(
            user_id=user.id,
            full_name=full_name,
            roll_number=roll_number,
            branch=branch,
            profile_completion_pct=30,  # name + roll + branch already filled
        )
        db.session.add(student)
        db.session.commit()

        return True, None

    except Exception as exc:
        db.session.rollback()
        return False, f"Registration failed: {str(exc)}"


import time

# ── In-Memory Login Throttling (Brute-Force Mitigation) ──────────────────────
# Note: In production with multiple workers/nodes, use Redis or DB rate limiting.
_FAILED_LOGINS: dict[str, list[float]] = {}
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_WINDOW_SECONDS = 300  # 5 minutes


def _is_rate_limited(email: str) -> bool:
    """Return True if email has exceeded maximum allowed failed login attempts."""
    now = time.time()
    clean = email.strip().lower()
    timestamps = _FAILED_LOGINS.get(clean, [])
    recent = [t for t in timestamps if now - t < LOCKOUT_WINDOW_SECONDS]
    _FAILED_LOGINS[clean] = recent
    return len(recent) >= MAX_FAILED_ATTEMPTS


def _record_failed_attempt(email: str) -> None:
    """Record a failed login timestamp for rate limiting."""
    now = time.time()
    clean = email.strip().lower()
    timestamps = _FAILED_LOGINS.get(clean, [])
    recent = [t for t in timestamps if now - t < LOCKOUT_WINDOW_SECONDS]
    recent.append(now)
    _FAILED_LOGINS[clean] = recent


def reset_failed_attempts(email: str | None = None) -> None:
    """Clear failed login attempts (for testing or successful login)."""
    if email:
        _FAILED_LOGINS.pop(email.strip().lower(), None)
    else:
        _FAILED_LOGINS.clear()


# ── Authentication ────────────────────────────────────────────────────────────

def authenticate_user(email: str, password: str) -> tuple:
    """
    Verify email + password and return the User object if valid.

    Returns:
      (User, None)          — credentials correct, account active
      (None, error_msg)     — wrong credentials, account disabled, or throttled
    """
    if not email or not password:
        return None, "Email and password are required."

    clean_email = email.strip().lower()

    if _is_rate_limited(clean_email):
        return None, "Too many failed login attempts. Please wait 5 minutes before trying again."

    user = User.query.filter_by(email=clean_email).first()

    if user is None:
        _record_failed_attempt(clean_email)
        return None, "No account found with that email."

    if not user.check_password(password):
        _record_failed_attempt(clean_email)
        return None, "Incorrect password. Please try again."

    if not user.is_active:
        return None, "Your account has been deactivated. Contact admin."

    # Successful authentication resets failed attempts
    reset_failed_attempts(clean_email)
    return user, None
