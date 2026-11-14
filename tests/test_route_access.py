"""
tests/test_route_access.py
──────────────────────────
Phase 15: Route Authorization Audit.

Programmatically iterates app.url_map and audits access control across 4 callers:
  1. Unauthenticated Guest
  2. Authenticated Student
  3. Authenticated Other Student (cross-tenant access to /api/student/<id>/*)
  4. Authenticated Admin

Also verifies that all POST routes enforce CSRF protection when CSRF is enabled.
"""

import pytest
from flask import url_for
from extensions import db as _db
from models.user import User
from models.student import Student

PUBLIC_ALLOWLIST = {
    'auth.index',
    'auth.login',
    'auth.register',
    'health_check',
    'health_db_check',
    'download_zip',
    'static',
}


def _build_test_url(app, rule, student_id=1):
    """Generate a valid test URL for a given rule with dummy route parameters."""
    args = {}
    for var in rule.arguments:
        if 'student_id' in var:
            args[var] = student_id
        elif 'filename' in var:
            args[var] = 'css/style.css'
        else:
            args[var] = 1
    with app.test_request_context():
        return url_for(rule.endpoint, **args)


@pytest.fixture
def auth_users(app):
    """Provide student 1, student 2, and admin users."""
    u1 = User(email='audit_s1@test.com', role='student', is_active=True)
    u1.set_password('Pass1234!')
    _db.session.add(u1)
    _db.session.flush()

    s1 = Student(user_id=u1.id, full_name='Audit Student 1', roll_number='AUDIT01', branch='CS')
    _db.session.add(s1)

    u2 = User(email='audit_s2@test.com', role='student', is_active=True)
    u2.set_password('Pass1234!')
    _db.session.add(u2)
    _db.session.flush()

    s2 = Student(user_id=u2.id, full_name='Audit Student 2', roll_number='AUDIT02', branch='IT')
    _db.session.add(s2)

    adm = User(email='audit_admin@test.com', role='admin', is_active=True)
    adm.set_password('Pass1234!')
    _db.session.add(adm)
    _db.session.commit()

    return {
        's1_user': u1,
        's1': s1,
        's2_user': u2,
        's2': s2,
        'admin_user': adm,
    }


def test_guest_access_audit(app, client):
    """Verify unauthenticated guests can only access the explicit public allowlist."""
    unprotected = []

    for rule in app.url_map.iter_rules():
        if rule.endpoint in PUBLIC_ALLOWLIST:
            continue
        url = _build_test_url(app, rule)
        methods = [m for m in rule.methods if m in ('GET', 'POST')]

        for m in methods:
            func = client.get if m == 'GET' else client.post
            resp = func(url, follow_redirects=False)

            # Protected routes must redirect guests to login (302) or return 401/403
            if resp.status_code not in (302, 401, 403):
                unprotected.append({
                    'endpoint': rule.endpoint,
                    'method': m,
                    'url': url,
                    'status': resp.status_code
                })

    if unprotected:
        print("\nUNPROTECTED GUEST ROUTES FOUND:")
        print(f"{'Endpoint':35} {'Method':6} {'URL':35} {'Status'}")
        print("-" * 85)
        for u in unprotected:
            print(f"{u['endpoint']:35} {u['method']:6} {u['url']:35} {u['status']}")

    assert len(unprotected) == 0, f"Found {len(unprotected)} unprotected routes for guests"


def test_student_blocked_from_admin_routes(app, client, auth_users):
    """Verify authenticated students receive 403 Forbidden on all /admin/* endpoints."""
    u1 = auth_users['s1_user']
    with client.session_transaction() as sess:
        sess['_user_id'] = str(u1.id)
        sess['_fresh'] = True

    leaks = []
    for rule in app.url_map.iter_rules():
        if rule.endpoint.startswith('admin.'):
            url = _build_test_url(app, rule)
            methods = [m for m in rule.methods if m in ('GET', 'POST')]

            for m in methods:
                func = client.get if m == 'GET' else client.post
                resp = func(url, follow_redirects=False)
                if resp.status_code != 403:
                    leaks.append((rule.endpoint, m, url, resp.status_code))

    assert len(leaks) == 0, f"Student accessed admin routes without 403: {leaks}"


def test_admin_blocked_from_student_routes(app, client, auth_users):
    """Verify authenticated admins receive 403 Forbidden on student-only routes."""
    adm = auth_users['admin_user']
    with client.session_transaction() as sess:
        sess['_user_id'] = str(adm.id)
        sess['_fresh'] = True

    leaks = []
    for rule in app.url_map.iter_rules():
        if rule.endpoint.startswith('student.'):
            url = _build_test_url(app, rule)
            methods = [m for m in rule.methods if m in ('GET', 'POST')]

            for m in methods:
                func = client.get if m == 'GET' else client.post
                resp = func(url, follow_redirects=False)
                if resp.status_code != 403:
                    leaks.append((rule.endpoint, m, url, resp.status_code))

    assert len(leaks) == 0, f"Admin accessed student-only routes without 403: {leaks}"


def test_student_cross_tenant_isolation(app, client, auth_users):
    """Verify student 1 cannot access student 2's private API endpoints."""
    u1 = auth_users['s1_user']
    s2 = auth_users['s2']

    with client.session_transaction() as sess:
        sess['_user_id'] = str(u1.id)
        sess['_fresh'] = True

    leaks = []
    for rule in app.url_map.iter_rules():
        if '<int:student_id>' in rule.rule and rule.endpoint.startswith('api.'):
            url = _build_test_url(app, rule, student_id=s2.id)
            methods = [m for m in rule.methods if m in ('GET', 'POST')]

            for m in methods:
                func = client.get if m == 'GET' else client.post
                resp = func(url, follow_redirects=False)
                if resp.status_code != 403:
                    leaks.append((rule.endpoint, m, url, resp.status_code))

    assert len(leaks) == 0, f"Cross-tenant isolation failure: {leaks}"


def test_csrf_protection_on_all_post_routes(app):
    """Verify that every POST route rejects requests missing a CSRF token when CSRF is enabled."""
    csrf_app = app
    # Enable CSRF in test client
    csrf_app.config['WTF_CSRF_ENABLED'] = True

    unprotected_post = []
    with csrf_app.test_client() as csrf_client:
        for rule in csrf_app.url_map.iter_rules():
            if 'POST' in rule.methods:
                url = _build_test_url(csrf_app, rule)
                resp = csrf_client.post(url, data={'dummy': '1'}, follow_redirects=False)
                # Without CSRF token, request must be rejected with 400 Bad Request
                if resp.status_code != 400:
                    unprotected_post.append((rule.endpoint, url, resp.status_code))

    # Reset config for other tests
    csrf_app.config['WTF_CSRF_ENABLED'] = False

    assert len(unprotected_post) == 0, f"POST routes without CSRF enforcement: {unprotected_post}"
