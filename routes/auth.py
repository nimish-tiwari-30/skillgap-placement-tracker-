"""
routes/auth.py
──────────────
Authentication Blueprint — Login, Register, Logout.
Phase 4: Full form handling with AuthService.
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import current_user, logout_user, login_user
from services.auth_service import register_student, authenticate_user

from urllib.parse import urlsplit

auth_bp = Blueprint('auth', __name__)


def _is_safe_url(target: str | None) -> bool:
    """Verify target URL is a safe local relative path (rejects open redirects and protocol-relative URLs)."""
    if not target:
        return False
    # Reject external URLs, protocol-relative (//), and backslash-prefixed paths (/\\)
    if not target.startswith('/') or target.startswith('//') or target.startswith('/\\') or '\\' in target:
        return False
    parsed = urlsplit(target)
    return not parsed.scheme and not parsed.netloc


# ── Root Redirect ─────────────────────────────────────────────────────────────

@auth_bp.route('/')
def index():
    """Root route: logged-in users go to their dashboard, others see the landing page."""
    if current_user.is_authenticated:
        if current_user.is_admin():
            return redirect(url_for('admin.dashboard'))
        return redirect(url_for('student.dashboard'))
    return render_template('index.html')


# ── Login ─────────────────────────────────────────────────────────────────────

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """
    GET  — Render login form.
    POST — Validate credentials, create session, redirect to dashboard.

    Flow: form → authenticate_user() → login_user() → redirect
    """
    try:
        if current_user.is_authenticated:
            return redirect(url_for('auth.index'))
    except Exception:
        logout_user()

    error = None

    if request.method == 'POST':
        email    = request.form.get('email', '').strip()
        password = request.form.get('password', '')

        user, error = authenticate_user(email, password)

        if user:
            login_user(user, remember=request.form.get('remember_me') == 'on')
            flash(f'Welcome back! Logged in as {user.email}', 'success')

            # Safe redirect: reject open redirects and protocol-relative URLs
            next_page = request.args.get('next')
            if _is_safe_url(next_page):
                return redirect(next_page)

            if user.is_admin():
                return redirect(url_for('admin.dashboard'))
            return redirect(url_for('student.dashboard'))

    return render_template('login.html', title='Login', error=error)


# ── Register ──────────────────────────────────────────────────────────────────

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """
    GET  — Render registration form.
    POST — Validate, create User + Student records, redirect to login.

    Flow: form → register_student() → flash success → redirect login
    """
    if current_user.is_authenticated:
        return redirect(url_for('auth.index'))

    error      = None
    form_data  = {}   # Preserve form values on validation failure

    if request.method == 'POST':
        form_data = {
            'full_name':        request.form.get('full_name', ''),
            'email':            request.form.get('email', ''),
            'roll_number':      request.form.get('roll_number', ''),
            'branch':           request.form.get('branch', ''),
            'password':         request.form.get('password', ''),
            'confirm_password': request.form.get('confirm_password', ''),
        }

        success, error = register_student(form_data)

        if success:
            flash('Account created successfully! Please log in.', 'success')
            return redirect(url_for('auth.login'))

    return render_template('register.html', title='Register',
                           error=error, form_data=form_data)


# ── Logout ────────────────────────────────────────────────────────────────────

@auth_bp.route('/logout')
def logout():
    """Log out the current user and clear session."""
    logout_user()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('auth.login'))
