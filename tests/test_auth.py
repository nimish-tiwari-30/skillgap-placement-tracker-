"""
tests/test_auth.py
───────────────────
Phase 4 pytest tests for authentication.

Tests:
  - GET /login        returns 200
  - GET /register     returns 200
  - POST /register    creates user + student and redirects
  - POST /login       valid credentials → 302 to dashboard
  - POST /login       wrong password → 200 with error
  - POST /login       unknown email  → 200 with error
  - GET /logout       clears session and redirects to login
  - Duplicate email   → register returns error

Run:
  .\\venv\\Scripts\\python.exe -m pytest tests/test_auth.py -v
"""

import pytest
from app import create_app
from extensions import db as _db
from models.user import User
from models.student import Student


# ── Shared fixtures inherited from conftest.py (app, client, clean_db) ─────────


# ── Helper ────────────────────────────────────────────────────────────────────

VALID_REG = {
    'full_name':        'Test Student',
    'email':            'test@college.edu',
    'roll_number':      '22CS001',
    'branch':           'Computer Science',
    'password':         'Password123',
    'confirm_password': 'Password123',
}


def register(client, data=None):
    """POST to /register with given (or default valid) data."""
    return client.post('/register', data=data or VALID_REG, follow_redirects=False)


def login(client, email='test@college.edu', password='Password123'):
    """POST to /login."""
    return client.post('/login', data={'email': email, 'password': password},
                       follow_redirects=False)


# ── Page Load Tests ───────────────────────────────────────────────────────────

def test_login_page_loads(client):
    """GET /login returns 200."""
    res = client.get('/login')
    assert res.status_code == 200
    assert b'Sign In' in res.data


def test_register_page_loads(client):
    """GET /register returns 200."""
    res = client.get('/register')
    assert res.status_code == 200
    assert b'Create Account' in res.data


# ── Registration Tests ────────────────────────────────────────────────────────

def test_register_creates_user_and_student(client, app):
    """Successful registration creates a User and Student row."""
    res = register(client)
    assert res.status_code == 302                   # Redirect to /login
    assert '/login' in res.headers['Location']

    with app.app_context():
        user = User.query.filter_by(email='test@college.edu').first()
        assert user is not None
        assert user.role == 'student'

        student = Student.query.filter_by(roll_number='22CS001').first()
        assert student is not None
        assert student.full_name == 'Test Student'


def test_register_password_hashed(client, app):
    """Stored password must NOT be plaintext."""
    register(client)
    with app.app_context():
        user = User.query.filter_by(email='test@college.edu').first()
        assert user.password_hash != 'Password123'
        assert user.check_password('Password123') is True


def test_register_duplicate_email(client, app):
    """Second registration with same email returns error page (200)."""
    register(client)
    res = register(client)    # Same data again
    assert res.status_code == 200
    assert b'already exists' in res.data


def test_register_password_mismatch(client):
    """Passwords don't match → stays on register page with error."""
    data = {**VALID_REG, 'confirm_password': 'WrongPass'}
    res = client.post('/register', data=data, follow_redirects=False)
    assert res.status_code == 200
    assert b'do not match' in res.data


def test_register_short_password(client):
    """Password < 8 chars → error."""
    data = {**VALID_REG, 'password': 'abc', 'confirm_password': 'abc'}
    res = client.post('/register', data=data, follow_redirects=False)
    assert res.status_code == 200
    assert b'8 characters' in res.data


# ── Login Tests ───────────────────────────────────────────────────────────────

def test_login_valid_credentials(client, app):
    """Valid login → redirect to student dashboard."""
    register(client)
    res = login(client)
    assert res.status_code == 302
    assert 'dashboard' in res.headers['Location']


def test_login_wrong_password(client):
    """Wrong password → 200 with error message on the login page."""
    register(client)
    client.get('/logout')    # Ensure no active session
    # Now try logging in with wrong password — user still exists in DB
    res = client.post('/login', data={
        'email': 'test@college.edu',
        'password': 'totallyWrong!'
    })
    assert res.status_code == 200
    # The error div should be present and contain an error message
    assert b'alert-danger' in res.data


def test_login_unknown_email(client):
    """Unknown email → 200 with error message."""
    client.get('/logout')    # Ensure no active session
    res = login(client, email='nobody@example.com')
    assert res.status_code == 200
    assert b'No account found' in res.data


# ── Logout Test ───────────────────────────────────────────────────────────────

def test_logout_redirects_to_login(client):
    """Logout clears session and goes to /login."""
    register(client)
    login(client)
    res = client.get('/logout', follow_redirects=False)
    assert res.status_code == 302
    assert '/login' in res.headers['Location']
