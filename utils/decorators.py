"""
utils/decorators.py
────────────────────
RBAC (Role-Based Access Control) decorators.

Usage:
  @admin_required   — only logged-in admins can access
  @student_required — only logged-in students can access

How it works (viva explanation):
  Flask-Login's @login_required only checks if user is logged in.
  Our decorators add a second check: is the user the RIGHT ROLE?
  If not, they get a 403 Forbidden response.
"""

from functools import wraps
from flask import abort, flash, redirect, url_for
from flask_login import current_user


def admin_required(f):
    """
    Decorator: allows access only to logged-in admin users.
    Apply AFTER @login_required (Flask-Login handles auth, we handle role).
    """
    @wraps(f)        # Preserves original function name (important for Flask routing)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        if not current_user.is_admin():
            abort(403)   # Forbidden — user is logged in but wrong role
        return f(*args, **kwargs)
    return decorated_function


def student_required(f):
    """
    Decorator: allows access only to logged-in student users.
    Also prevents admins from accidentally accessing student pages.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        if not current_user.is_student():
            abort(403)
        return f(*args, **kwargs)
    return decorated_function
