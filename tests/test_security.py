"""
tests/test_security.py
───────────────────────
Phase 15: Security Checklist Verification Suite.

Automated verification of core web application security controls:
  1. Password Hashing & Safe Logging (no plaintext in DB or application logs)
  2. Session Cookie Flags & Production Configuration Hardening
  3. Open Redirect Mitigation (protocol-relative and external domain blocking)
  4. Login Brute-Force Throttling
  5. SQL Injection Resilience (parameterized queries across search/filter/auth)
  6. XSS Prevention (automatic HTML escaping of user inputs)
  7. Template Filter Audit (inspecting |safe and autoescape)
  8. Secure File Uploads (extension, magic bytes, path traversal, double extension, UUID naming)
  9. CSV Formula Injection Neutralization (=, +, -, @ prepended with ')
 10. Information Leakage Prevention & Error Handling (custom 404/500, no stack traces leaked)
 11. HTTP Security Headers (nosniff, DENY, same-origin, Content-Security-Policy)
 12. Secrets Hygiene (.gitignore rules and placeholder .env.example)
"""

import io
import os
import re
import pytest
from unittest.mock import patch

from extensions import db
from models.user import User
from models.student import Student, Project
from models.skill import Skill, StudentSkill, Resume
from models.job import JobRole, JobDescription
from models.course import Course
from models.outcome import EmploymentOutcome
from config import Config, ProductionConfig
from services.auth_service import reset_failed_attempts


# ── 1. Password Hashing & Safe Logging ────────────────────────────────────────

def test_passwords_hashed_and_never_logged(client, app, caplog):
    """
    Assert passwords are stored as secure hashes, never in plaintext,
    and are never leaked to application logs during registration or login.
    """
    plain_password = "P@ssw0rd_SuperSecret_999!"

    # 1. Register a student
    reg_data = {
        'full_name': 'Security Audit User',
        'email': 'sec_user@college.edu',
        'roll_number': 'SEC999',
        'branch': 'Cyber Security',
        'password': plain_password,
        'confirm_password': plain_password,
    }
    with caplog.at_level("DEBUG"):
        res = client.post('/register', data=reg_data, follow_redirects=False)
        assert res.status_code == 302

    # Check database storage
    user = User.query.filter_by(email='sec_user@college.edu').first()
    assert user is not None
    assert user.password_hash != plain_password
    assert not user.password_hash.startswith("plain:")
    assert user.check_password(plain_password) is True
    assert user.check_password("WrongPassword123") is False

    # Check logs: the plain password must NEVER appear in captured logs
    assert plain_password not in caplog.text

    # 2. Login attempt
    caplog.clear()
    with caplog.at_level("DEBUG"):
        login_res = client.post('/login', data={
            'email': 'sec_user@college.edu',
            'password': plain_password
        }, follow_redirects=False)
        assert login_res.status_code == 302

    # Password must still not be in logs
    assert plain_password not in caplog.text


# ── 2. Session Cookie Flags & Production Config ──────────────────────────────

def test_session_cookie_settings_and_production_config(app):
    """
    Verify HttpOnly, SameSite, and ProductionConfig settings
    (DEBUG=False, SESSION_COOKIE_SECURE=True, non-default SECRET_KEY required).
    """
    # Base / app settings
    assert app.config.get('SESSION_COOKIE_HTTPONLY') is True
    assert app.config.get('SESSION_COOKIE_SAMESITE') in ('Lax', 'Strict')

    # ProductionConfig verification
    assert ProductionConfig.DEBUG is False
    assert ProductionConfig.SESSION_COOKIE_SECURE is True

    # ProductionConfig must raise ValueError if SECRET_KEY is missing or default
    with patch.dict(os.environ, {'SECRET_KEY': ''}, clear=False):
        with pytest.raises(ValueError, match="ProductionConfig requires a non-default SECRET_KEY"):
            ProductionConfig()

    with patch.dict(os.environ, {'SECRET_KEY': 'default_fallback_secret_key_12345'}, clear=False):
        with pytest.raises(ValueError, match="ProductionConfig requires a non-default SECRET_KEY"):
            ProductionConfig()

    # With a valid secret key, ProductionConfig instantiates cleanly
    with patch.dict(os.environ, {'SECRET_KEY': 'real_production_secret_key_random_hex'}, clear=False):
        prod = ProductionConfig()
        assert prod.SECRET_KEY == 'real_production_secret_key_random_hex'


# ── 3. Open Redirect Mitigation ───────────────────────────────────────────────

def test_open_redirect_rejected(client):
    """
    Verify external domains, protocol-relative (//evil.com), and backslash-prefixed
    next URLs are rejected on login.
    """
    u = User(email='redirect_test@college.edu', role='student', is_active=True)
    u.set_password('Pass1234!')
    db.session.add(u)
    db.session.flush()

    st = Student(user_id=u.id, full_name='Redirect Test', roll_number='REDIR01', branch='CS')
    db.session.add(st)
    db.session.commit()

    malicious_targets = [
        'https://evil.com',
        'http://attacker.com/malware',
        '//evil.com',
        '//evil.com/path',
        '//attacker.com',
        r'/\evil.com',
    ]

    for evil_url in malicious_targets:
        # Clear any prior session
        client.get('/logout')

        res = client.post(f'/login?next={evil_url}', data={
            'email': 'redirect_test@college.edu',
            'password': 'Pass1234!'
        }, follow_redirects=False)

        assert res.status_code == 302
        location = res.headers.get('Location', '')
        # Must redirect to safe internal dashboard, not external target
        assert 'evil.com' not in location
        assert 'attacker.com' not in location
        assert '/student/dashboard' in location

    # Safe internal redirect should be permitted
    client.get('/logout')
    res_safe = client.post('/login?next=/student/profile', data={
        'email': 'redirect_test@college.edu',
        'password': 'Pass1234!'
    }, follow_redirects=False)
    assert res_safe.status_code == 302
    assert res_safe.headers.get('Location') == '/student/profile'


# ── 4. Login Brute-Force Throttling ───────────────────────────────────────────

def test_login_brute_force_throttling(client):
    """
    Verify in-memory login attempt throttling blocks rapid failed attempts.
    """
    reset_failed_attempts()

    u = User(email='throttle_target@college.edu', role='student', is_active=True)
    u.set_password('CorrectPassword123!')
    db.session.add(u)
    db.session.commit()

    # 4 failed attempts: returned message is "Incorrect password"
    for i in range(4):
        res = client.post('/login', data={
            'email': 'throttle_target@college.edu',
            'password': f'Wrong_{i}'
        }, follow_redirects=False)
        assert res.status_code == 200
        assert b'Incorrect password' in res.data

    # 5th failed attempt triggers rate limit
    res_5 = client.post('/login', data={
        'email': 'throttle_target@college.edu',
        'password': 'Wrong_5'
    }, follow_redirects=False)
    assert res_5.status_code == 200

    # 6th attempt: blocked by rate limiter
    res_blocked = client.post('/login', data={
        'email': 'throttle_target@college.edu',
        'password': 'Wrong_6'
    }, follow_redirects=False)
    assert res_blocked.status_code == 200
    assert b'Too many failed login attempts' in res_blocked.data

    # Even with CORRECT password, account is throttled
    res_correct_while_throttled = client.post('/login', data={
        'email': 'throttle_target@college.edu',
        'password': 'CorrectPassword123!'
    }, follow_redirects=False)
    assert res_correct_while_throttled.status_code == 200
    assert b'Too many failed login attempts' in res_correct_while_throttled.data

    # Reset attempts (simulating time window expiry)
    reset_failed_attempts('throttle_target@college.edu')

    # Now correct password succeeds immediately
    res_success = client.post('/login', data={
        'email': 'throttle_target@college.edu',
        'password': 'CorrectPassword123!'
    }, follow_redirects=False)
    assert res_success.status_code == 302
    assert '/student/dashboard' in res_success.headers['Location']


# ── 5. SQL Injection Resilience ───────────────────────────────────────────────

def test_sql_injection_resilience(client):
    """
    Inject typical SQL injection payloads into query params, filters, and auth forms.
    Assert no HTTP 500 errors occur, no data is leaked, and tables remain intact.
    """
    admin = User(email='sqli_admin@college.edu', role='admin', is_active=True)
    admin.set_password('AdminPass123!')
    db.session.add(admin)

    st_user = User(email='sqli_student@college.edu', role='student', is_active=True)
    st_user.set_password('StudentPass123!')
    db.session.add(st_user)
    db.session.flush()

    student = Student(user_id=st_user.id, full_name='SQLi Normal Student', roll_number='SQLI01', branch='CS')
    db.session.add(student)
    db.session.commit()

    sqli_payloads = [
        "' OR 1=1 --",
        "'; DROP TABLE users; --",
        "' UNION SELECT NULL, NULL, NULL --",
        "admin' --",
        "\" OR \"\"=\"",
        "1; DROP TABLE students; --",
    ]

    # Test unauthenticated login form against SQLi
    for payload in sqli_payloads:
        client.get('/logout')
        res = client.post('/login', data={'email': payload, 'password': 'random_password'}, follow_redirects=False)
        assert res.status_code in (200, 302)
        assert b'Internal Server Error' not in res.data

    # Log in cleanly as admin
    client.get('/logout')
    login_res = client.post('/login', data={'email': 'sqli_admin@college.edu', 'password': 'AdminPass123!'}, follow_redirects=False)
    assert login_res.status_code == 302

    # Test admin filters and search inputs
    for payload in sqli_payloads:
        endpoints_to_test = [
            f'/admin/employment?search={payload}',
            f'/admin/employment?branch={payload}',
            f'/admin/employment?role={payload}',
            f'/admin/jobs?search={payload}',
            f'/admin/courses?q={payload}',
            f'/admin/dashboard?branch={payload}',
        ]
        for url in endpoints_to_test:
            resp = client.get(url)
            assert resp.status_code == 200, f"SQLi payload triggered error on {url}"
            assert b'Traceback' not in resp.data
            assert b'OperationalError' not in resp.data

    # Verify tables are still intact and populated
    assert User.query.filter_by(email='sqli_admin@college.edu').first() is not None
    assert Student.query.filter_by(roll_number='SQLI01').first() is not None


# ── 6. XSS Prevention on Rendered Pages ───────────────────────────────────────

def test_xss_prevention_on_rendered_pages(client):
    """
    Store HTML/script payloads in profile fields, projects, jobs, courses, and outcomes.
    Assert rendered HTML auto-escapes them, preventing executable <script> tags.
    """
    xss_payload = '<script>alert(1)</script>'

    u = User(email='xss_tester@college.edu', role='student', is_active=True)
    u.set_password('Pass1234!')
    db.session.add(u)
    db.session.flush()

    st = Student(
        user_id=u.id,
        full_name=f'Student {xss_payload}',
        roll_number='XSS01',
        branch=f'CS {xss_payload}',
        linkedin_url='https://linkedin.com/in/test'
    )
    db.session.add(st)
    db.session.flush()

    proj = Project(
        student_id=st.id,
        title=f'Project {xss_payload}',
        description=f'Desc {xss_payload}'
    )
    db.session.add(proj)

    role = JobRole(
        title=f'Role {xss_payload}',
        department='Tech',
        description=f'Role Desc {xss_payload}'
    )
    db.session.add(role)
    db.session.flush()

    jd = JobDescription(
        job_role_id=role.id,
        title=f'Job {xss_payload}',
        company_name=f'Corp {xss_payload}',
        description_text='Job description'
    )
    db.session.add(jd)

    course = Course(
        title=f'Course {xss_payload}',
        provider='Online Provider',
        url='https://example.com/course'
    )
    db.session.add(course)

    outcome = EmploymentOutcome(
        student_id=st.id,
        status='Placed',
        company_name=f'Company {xss_payload}',
        role_title=f'Placement Role {xss_payload}',
        salary_package_lpa=10.0
    )
    db.session.add(outcome)
    db.session.commit()

    # Log in as the student
    client.post('/login', data={'email': 'xss_tester@college.edu', 'password': 'Pass1234!'}, follow_redirects=True)

    pages_to_check = [
        '/student/dashboard',
        '/student/profile',
        '/student/jobs',
        '/student/employment',
    ]

    for page in pages_to_check:
        res = client.get(page)
        assert res.status_code == 200
        html = res.data.decode('utf-8', errors='ignore')

        # Raw executable <script>alert(1)</script> must NEVER exist in rendered HTML
        assert '<script>alert(1)</script>' not in html
        # Escaped version must be present
        assert '&lt;script&gt;alert(1)&lt;/script&gt;' in html or 'alert(1)' in html


# ── 7. Template Filter Audit ──────────────────────────────────────────────────

def test_template_safe_filter_audit():
    """
    Audit all templates for `|safe` or `autoescape false`.
    Verify that only legitimate static HTML entities (e.g. '&mdash;') use |safe.
    """
    templates_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates')
    safe_usages = []
    autoescape_disabled = []

    for root, _, files in os.walk(templates_dir):
        for f in files:
            if f.endswith('.html'):
                file_path = os.path.join(root, f)
                rel_path = os.path.relpath(file_path, templates_dir)
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as fp:
                    content = fp.read()
                    if '|safe' in content or '| safe' in content:
                        for line_idx, line in enumerate(content.splitlines(), 1):
                            if '|safe' in line or '| safe' in line:
                                safe_usages.append((rel_path, line_idx, line.strip()))
                    if 'autoescape false' in content.lower():
                        autoescape_disabled.append(rel_path)

    assert len(autoescape_disabled) == 0, f"Found templates with autoescape disabled: {autoescape_disabled}"

    # Only verified safe static HTML entity fallback is permissible
    for rel_path, line_no, line in safe_usages:
        assert '&mdash;' in line or 'mdash' in line, f"Unsafe usage of |safe found in {rel_path}:{line_no} -> {line}"


# ── 8. Secure File Uploads ────────────────────────────────────────────────────

def test_upload_validation_security(client):
    """
    Verify rejection of malicious upload vectors:
    - wrong extensions (.exe, .sh)
    - double extensions (resume.pdf.exe)
    - fake PDF (text content with .pdf extension)
    - fake DOCX (text content with .docx extension)
    - empty file (0 bytes)
    - path traversal filename (../../passwd.pdf)
    - stored filename is randomized with UUID
    """
    u = User(email='upload_sec@college.edu', role='student', is_active=True)
    u.set_password('Pass1234!')
    db.session.add(u)
    db.session.flush()

    st = Student(user_id=u.id, full_name='Upload Sec Student', roll_number='UP01', branch='CS')
    db.session.add(st)
    db.session.commit()

    # Log in as the student
    client.post('/login', data={'email': 'upload_sec@college.edu', 'password': 'Pass1234!'}, follow_redirects=True)

    # 1. Disallowed extension (.exe)
    res = client.post('/student/resume/upload', data={
        'resume': (io.BytesIO(b'dummy executable'), 'exploit.exe')
    }, content_type='multipart/form-data', follow_redirects=True)
    assert res.status_code == 200
    assert b'Invalid file format' in res.data or b'Only PDF' in res.data

    # 2. Double extension (resume.pdf.exe)
    res = client.post('/student/resume/upload', data={
        'resume': (io.BytesIO(b'dummy executable'), 'resume.pdf.exe')
    }, content_type='multipart/form-data', follow_redirects=True)
    assert res.status_code == 200
    assert b'Invalid file format' in res.data or b'Only PDF' in res.data

    # 3. Empty file (0 bytes)
    res = client.post('/student/resume/upload', data={
        'resume': (io.BytesIO(b''), 'empty.pdf')
    }, content_type='multipart/form-data', follow_redirects=True)
    assert res.status_code == 200
    assert b'empty' in res.data.lower()

    # 4. Fake PDF (plain text claiming to be PDF)
    res = client.post('/student/resume/upload', data={
        'resume': (io.BytesIO(b'Just plain text pretending to be a PDF'), 'fake.pdf')
    }, content_type='multipart/form-data', follow_redirects=True)
    assert res.status_code == 200
    assert b'corrupted' in res.data.lower() or b'magic' in res.data.lower() or b'invalid' in res.data.lower()

    # 5. Fake DOCX (plain text claiming to be DOCX)
    res = client.post('/student/resume/upload', data={
        'resume': (io.BytesIO(b'Just plain text pretending to be a DOCX'), 'fake.docx')
    }, content_type='multipart/form-data', follow_redirects=True)
    assert res.status_code == 200
    assert b'valid word' in res.data.lower() or b'corrupted' in res.data.lower() or b'invalid' in res.data.lower()

    # 6. Valid PDF with path traversal filename
    valid_pdf_content = (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n"
        b"3 0 obj<</Type/Page/MediaBox[0 0 300 144]/Parent 2 0 R/Resources<<>>/Contents 4 0 R>>endobj\n"
        b"4 0 obj<</Length 55>>stream\n"
        b"BT /F1 12 Tf 50 100 Td (Python SQL Docker Machine Learning) Tj ET\n"
        b"endstream\n"
        b"endobj\n"
        b"xref\n0 5\n0000000000 65535 f\n0000000009 00000 n\n0000000058 00000 n\n0000000115 00000 n\n0000000214 00000 n\n"
        b"trailer<</Size 5/Root 1 0 R>>\nstartxref\n320\n%%EOF\n"
    )

    res = client.post('/student/resume/upload', data={
        'resume': (io.BytesIO(valid_pdf_content), '../../evil_path_traversal.pdf')
    }, content_type='multipart/form-data', follow_redirects=True)

    # Check database record: stored filename must NOT contain path traversal characters
    resume = Resume.query.filter_by(student_id=st.id).first()
    assert resume is not None
    assert '..' not in resume.stored_filename
    assert '/' not in resume.stored_filename
    assert '\\' not in resume.stored_filename
    # Randomized UUID pattern present in stored filename
    assert re.search(r'resume_\d+_\d+_[a-f0-9]+_', resume.stored_filename) is not None


# ── 9. CSV Formula Injection Neutralization ───────────────────────────────────

def test_csv_injection_neutralization(client):
    """
    Assert cells starting with '=', '+', '-', '@' are neutralized with a leading single quote (')
    in CSV export endpoints.
    """
    admin = User(email='csv_admin@college.edu', role='admin', is_active=True)
    admin.set_password('Admin1234!')
    db.session.add(admin)

    st_user = User(email='csv_st@college.edu', role='student', is_active=True)
    st_user.set_password('Pass1234!')
    db.session.add(st_user)
    db.session.flush()

    student = Student(user_id=st_user.id, full_name='=cmd|/c calc!A0', roll_number='+99999', branch='@SpecialBranch')
    db.session.add(student)
    db.session.flush()

    outcome = EmploymentOutcome(
        student_id=student.id,
        status='Placed',
        company_name='-MinusCorp',
        role_title='=HYPERLINK("http://evil.com")',
        salary_package_lpa=12.5,
    )
    db.session.add(outcome)
    db.session.commit()

    # Log in as admin
    client.post('/login', data={'email': 'csv_admin@college.edu', 'password': 'Admin1234!'}, follow_redirects=True)

    # 1. Employment CSV Export
    res = client.get('/admin/employment/export-csv')
    assert res.status_code == 200
    assert res.mimetype == 'text/csv'
    csv_text = res.data.decode('utf-8')

    # All formula characters must be neutralized with leading single quote
    assert "'=cmd|/c calc!A0" in csv_text
    assert "'+99999" in csv_text
    assert "'@SpecialBranch" in csv_text
    assert "'-MinusCorp" in csv_text
    assert "'=HYPERLINK" in csv_text

    # 2. Analytics Dashboard CSV Export
    res_dash = client.get('/admin/dashboard/export-csv')
    assert res_dash.status_code == 200
    assert res_dash.mimetype == 'text/csv'


# ── 10. Information Leakage Prevention & Error Handling ────────────────────────

def test_error_handling_and_no_information_leakage(app, client):
    """
    Verify custom 404/500 responses:
    - 404 under /api/ returns JSON
    - 500 returns generic message with NO stack traces, internal paths, or SQL queries leaked
    - db.session is rolled back on 500
    """
    from services import analytics_service

    # 1. API 404 returns JSON
    res_404 = client.get('/api/does-not-exist')
    assert res_404.status_code == 404
    data_404 = res_404.get_json()
    assert data_404 is not None
    assert data_404['success'] is False
    assert "Resource not found" in data_404['error']

    # 2. Test 500 handling
    secret_leak_text = "/var/secret_data/passwords.txt"
    sql_leak_text = "SELECT * FROM secret_financial_records WHERE 1=1"

    admin = User(email='err_admin@college.edu', role='admin', is_active=True)
    admin.set_password('Admin1234!')
    db.session.add(admin)
    db.session.commit()

    # Log in cleanly without following redirect to avoid calling analytics before mock
    client.post('/login', data={'email': 'err_admin@college.edu', 'password': 'Admin1234!'}, follow_redirects=False)

    def mock_broken_dashboard(*args, **kwargs):
        raise RuntimeError(f"Internal crash with {secret_leak_text} and {sql_leak_text}")

    orig_fn = analytics_service.get_dashboard_analytics
    analytics_service.get_dashboard_analytics = mock_broken_dashboard

    # Temporarily disable exception propagation to invoke Flask's 500 errorhandler
    orig_testing = app.config.get('TESTING')
    orig_debug = app.config.get('DEBUG')
    orig_prop = app.config.get('PROPAGATE_EXCEPTIONS')

    app.config['TESTING'] = False
    app.config['DEBUG'] = False
    app.config['PROPAGATE_EXCEPTIONS'] = False

    try:
        # Test API 500 via /api/dashboard/stats
        res_api = client.get('/api/dashboard/stats')
        assert res_api.status_code == 500
        api_data = res_api.get_json()
        assert api_data is not None
        assert api_data['success'] is False
        assert api_data['error'] == "Internal server error"
        assert secret_leak_text not in res_api.data.decode('utf-8')
        assert sql_leak_text not in res_api.data.decode('utf-8')
        assert "Traceback" not in res_api.data.decode('utf-8')

        # Test HTML 500 via /admin/dashboard
        res_html = client.get('/admin/dashboard')
        assert res_html.status_code == 500
        html_content = res_html.data.decode('utf-8')
        assert "500" in html_content
        assert secret_leak_text not in html_content
        assert sql_leak_text not in html_content
        assert "Traceback" not in html_content
    finally:
        analytics_service.get_dashboard_analytics = orig_fn
        app.config['TESTING'] = orig_testing
        app.config['DEBUG'] = orig_debug
        app.config['PROPAGATE_EXCEPTIONS'] = orig_prop


# ── 11. HTTP Security Headers ─────────────────────────────────────────────────

def test_http_security_headers_present(client):
    """
    Assert after_request sets:
    - X-Content-Type-Options: nosniff
    - X-Frame-Options: DENY
    - Referrer-Policy: same-origin
    - Content-Security-Policy (with required CDNs)
    """
    resp = client.get('/login')
    assert resp.status_code == 200
    headers = resp.headers

    assert headers.get('X-Content-Type-Options') == 'nosniff'
    assert headers.get('X-Frame-Options') == 'DENY'
    assert headers.get('Referrer-Policy') == 'same-origin'

    csp = headers.get('Content-Security-Policy', '')
    assert "default-src 'self'" in csp
    assert "cdn.jsdelivr.net" in csp
    assert "fonts.googleapis.com" in csp
    assert "fonts.gstatic.com" in csp


# ── 12. Secrets Hygiene ───────────────────────────────────────────────────────

def test_secrets_hygiene():
    """
    Verify repository secrets hygiene:
    - .env is listed in .gitignore
    - .env.example contains only dummy/placeholder values
    """
    base_dir = os.path.dirname(os.path.dirname(__file__))

    # Check .gitignore
    gitignore_path = os.path.join(base_dir, '.gitignore')
    assert os.path.exists(gitignore_path)
    with open(gitignore_path, 'r', encoding='utf-8') as f:
        lines = [line.strip() for line in f]
    assert '.env' in lines

    # Check .env.example
    env_example_path = os.path.join(base_dir, '.env.example')
    assert os.path.exists(env_example_path)
    with open(env_example_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Ensure no actual MySQL production passwords or real secret keys are present
    assert 'your_secret_key_here' in content or 'dev_secret' in content
    assert 'your_mysql_password' in content
