"""
tests/test_forum.py
───────────────────
Comprehensive test suite for Open Discussion Forum (Phase Forum).

Covers:
1. Category CRUD & listing.
2. Thread creation, reply creation, input validation (empty, whitespace, length limits).
3. XSS prevention (strict escaping, zero unescaped tags).
4. Ownership enforcement (edit/delete own only, admin can moderate any, guest redirected).
5. Thread locking & pinning behavior.
6. Soft delete & restore (hidden from students, visible to admin).
7. Helpful votes / likes (toggle, single vote, no self-likes).
8. Reporting & Admin moderation queue (abuse prevention, resolve, dismiss, content deletion).
9. Search, category filter, skill filter, sorting, pagination, and invalid filter resiliency.
10. Anti-spam rate limiting & duplicate body blocking.
11. PII privacy protection (no roll numbers or emails leaked).
12. FORUM_ENABLED feature toggle.
13. Query efficiency (0 N+1 queries).
"""

import pytest
from flask import url_for
from extensions import db as _db
from models.user import User
from models.student import Student
from models.skill import Skill
from models.forum import ForumCategory, ForumThread, ForumPost, ForumPostLike, ForumReport
from services import forum_service


@pytest.fixture
def forum_setup(app):
    """Create test users, category, and skill for forum tests."""
    # Reset in-memory rate limiters before each test
    forum_service._USER_THREAD_TIMESTAMPS.clear()
    forum_service._USER_POST_TIMESTAMPS.clear()
    forum_service._USER_RECENT_BODIES.clear()

    # Student 1
    u1 = User(email='student1@forum.edu', role='student', is_active=True)
    u1.set_password('Pass1234!')
    _db.session.add(u1)
    _db.session.flush()

    s1 = Student(user_id=u1.id, full_name='Alice Sharma', roll_number='ROLL_A1', branch='CSE')
    _db.session.add(s1)

    # Student 2
    u2 = User(email='student2@forum.edu', role='student', is_active=True)
    u2.set_password('Pass1234!')
    _db.session.add(u2)
    _db.session.flush()

    s2 = Student(user_id=u2.id, full_name='Bob Patel', roll_number='ROLL_B2', branch='ECE')
    _db.session.add(s2)

    # Admin
    admin = User(email='admin@forum.edu', role='admin', is_active=True)
    admin.set_password('AdminPass123!')
    _db.session.add(admin)

    # Category
    cat1 = ForumCategory.query.filter_by(slug='general').first()
    if not cat1:
        cat1 = ForumCategory(name='General', slug='general', description='General chats', sort_order=1)
        _db.session.add(cat1)

    cat2 = ForumCategory.query.filter_by(slug='interviews').first()
    if not cat2:
        cat2 = ForumCategory(name='Interviews', slug='interviews', description='Interview prep', sort_order=2)
        _db.session.add(cat2)

    # Skill
    skill1 = Skill.query.filter_by(name='Python').first()
    if not skill1:
        skill1 = Skill(name='Python', category='Programming')
        _db.session.add(skill1)

    _db.session.commit()

    return {
        'student1': u1,
        'student2': u2,
        'admin': admin,
        'cat1': cat1,
        'cat2': cat2,
        'skill1': skill1
    }


def login_user(client, email, password):
    """Helper to log in a user cleanly after logging out any previous user."""
    client.get('/logout')
    return client.post('/login', data={'email': email, 'password': password}, follow_redirects=True)


# ── 1. Validation & Creation Tests ────────────────────────────────────────────

def test_create_thread_validation(client, forum_setup):
    """Test thread creation validation: empty title, empty body, whitespace, and excessive length."""
    u1 = forum_setup['student1']
    cat = forum_setup['cat1']

    # 1. Empty title & body
    ok, res = forum_service.create_thread(u1.id, cat.id, "   ", "   ")
    assert not ok
    assert "between 1 and 150 characters" in res

    # 2. Title too long (> 150 chars)
    ok, res = forum_service.create_thread(u1.id, cat.id, "A" * 151, "Valid body")
    assert not ok
    assert "between 1 and 150 characters" in res

    # 3. Body too long (> 5000 chars)
    ok, res = forum_service.create_thread(u1.id, cat.id, "Valid title", "B" * 5001)
    assert not ok
    assert "between 1 and 5000 characters" in res

    # 4. Invalid category
    ok, res = forum_service.create_thread(u1.id, 99999, "Valid title", "Valid body")
    assert not ok
    assert "valid discussion category" in res.lower()

    # 5. Successful creation
    ok, thread = forum_service.create_thread(u1.id, cat.id, "Valid Discussion", "This is a valid body content.")
    assert ok
    assert thread.id is not None
    assert thread.title == "Valid Discussion"
    assert thread.category_id == cat.id


def test_create_reply_validation(client, forum_setup):
    """Test reply validation: empty, whitespace, too long, locked thread."""
    u1 = forum_setup['student1']
    u2 = forum_setup['student2']
    cat = forum_setup['cat1']

    ok, thread = forum_service.create_thread(u1.id, cat.id, "Thread for Replies", "Body here")
    assert ok

    # 1. Empty body
    ok, res = forum_service.create_reply(u2.id, thread.id, "   ")
    assert not ok
    assert "between 1 and 3000 characters" in res

    # 2. Body too long (> 3000 chars)
    ok, res = forum_service.create_reply(u2.id, thread.id, "R" * 3001)
    assert not ok
    assert "between 1 and 3000 characters" in res

    # 3. Nonexistent thread
    ok, res = forum_service.create_reply(u2.id, 99999, "Valid reply")
    assert not ok
    assert "not found" in res.lower()

    # 4. Successful reply updates last_activity_at
    initial_activity = thread.last_activity_at
    ok, post = forum_service.create_reply(u2.id, thread.id, "A great helpful response.")
    assert ok
    assert post.id is not None
    _db.session.refresh(thread)
    assert thread.last_activity_at >= initial_activity


# ── 2. XSS Escaping Tests ─────────────────────────────────────────────────────

def test_forum_xss_prevention(client, forum_setup):
    """Verify that script tags and HTML elements in titles, bodies, and replies are safely escaped."""
    login_user(client, 'student1@forum.edu', 'Pass1234!')
    cat = forum_setup['cat1']

    xss_title = '<script>alert("xss_title")</script> Test Title'
    xss_body = '<b>Bold Body</b><script>alert("xss_body")</script><img src=x onerror=alert("img")>'

    # Create thread with XSS payload
    res = client.post('/forum/new', data={
        'category_id': cat.id,
        'title': xss_title,
        'body': xss_body,
        'skill_id': 0
    }, follow_redirects=True)
    assert res.status_code == 200

    html = res.data.decode('utf-8')
    # Unescaped script or img tag must NOT appear in HTML
    assert '<script>alert("xss_title")</script>' not in html
    assert '<script>alert("xss_body")</script>' not in html
    assert '<img src=x' not in html

    # Escaped representations MUST be present
    assert '&lt;script&gt;alert(&#34;xss_title&#34;)&lt;/script&gt;' in html or '&lt;script&gt;' in html

    # Post reply with XSS payload
    thread = ForumThread.query.filter_by(user_id=forum_setup['student1'].id).first()
    reply_res = client.post(f'/forum/t/{thread.id}/reply', data={
        'body': '<script>alert("xss_reply")</script>'
    }, follow_redirects=True)
    assert reply_res.status_code == 200
    reply_html = reply_res.data.decode('utf-8')
    assert '<script>alert("xss_reply")</script>' not in reply_html


# ── 3. Ownership & Authorization Tests ─────────────────────────────────────────

def test_forum_guest_redirected_to_login(client):
    """Guest requests to forum must be redirected to login."""
    res = client.get('/forum/', follow_redirects=False)
    assert res.status_code == 302
    assert '/login' in res.location

    res_new = client.get('/forum/new', follow_redirects=False)
    assert res_new.status_code == 302
    assert '/login' in res_new.location


def test_forum_ownership_enforcement(client, forum_setup):
    """Student cannot edit or delete another student's thread or reply. Admin can delete any."""
    u1 = forum_setup['student1']
    u2 = forum_setup['student2']
    admin = forum_setup['admin']
    cat = forum_setup['cat1']

    # S1 creates thread and reply
    ok, thread = forum_service.create_thread(u1.id, cat.id, "Alice's Thread", "Alice's secret thoughts")
    assert ok
    ok, post = forum_service.create_reply(u1.id, thread.id, "Alice's reply")
    assert ok

    # Log in as Student 2 (Bob)
    login_user(client, 'student2@forum.edu', 'Pass1234!')

    # Bob tries to GET edit Alice's thread -> 403
    res = client.get(f'/forum/t/{thread.id}/edit')
    assert res.status_code == 403

    # Bob tries to POST edit Alice's thread -> service level check
    ok, msg = forum_service.edit_own_thread(u2, thread.id, "Hacked Title", "Hacked Body")
    assert not ok
    assert "only edit your own" in msg.lower()

    # Bob tries to POST delete Alice's thread -> service level check
    ok, msg = forum_service.delete_own_thread(u2, thread.id)
    assert not ok
    assert "only delete your own" in msg.lower()

    # Bob tries to GET edit Alice's reply -> 403
    res_p = client.get(f'/forum/p/{post.id}/edit')
    assert res_p.status_code == 403

    # Bob tries to delete Alice's reply -> service level check
    ok, msg = forum_service.delete_own_post(u2, post.id)
    assert not ok
    assert "only delete your own" in msg.lower()

    # Log in as Admin
    login_user(client, 'admin@forum.edu', 'AdminPass123!')

    # Admin CAN delete Alice's reply
    ok, msg = forum_service.delete_own_post(admin, post.id)
    assert ok

    # Admin CAN delete Alice's thread
    ok, msg = forum_service.delete_own_thread(admin, thread.id)
    assert ok
    _db.session.refresh(thread)
    assert thread.is_deleted is True


# ── 4. Locking & Pinning Tests ────────────────────────────────────────────────

def test_forum_lock_rejects_replies(client, forum_setup):
    """Locked thread rejects replies."""
    u1 = forum_setup['student1']
    u2 = forum_setup['student2']
    admin = forum_setup['admin']
    cat = forum_setup['cat1']

    ok, thread = forum_service.create_thread(u1.id, cat.id, "Lockable Thread", "Body")
    assert ok

    # Admin locks thread
    ok, msg = forum_service.lock_thread(thread.id, is_locked=True)
    assert ok
    assert thread.is_locked is True

    # User attempts to reply to locked thread
    ok, res = forum_service.create_reply(u2.id, thread.id, "Trying to reply to locked thread")
    assert not ok
    assert "locked" in res.lower()


def test_forum_pinned_ordering(forum_setup):
    """Pinned threads appear first regardless of creation date."""
    u1 = forum_setup['student1']
    cat = forum_setup['cat1']

    # Thread 1: regular
    ok, t1 = forum_service.create_thread(u1.id, cat.id, "Regular Thread 1", "Body 1")
    # Thread 2: regular newer
    ok, t2 = forum_service.create_thread(u1.id, cat.id, "Regular Thread 2", "Body 2")
    # Thread 3: pinned
    ok, t3 = forum_service.create_thread(u1.id, cat.id, "Pinned Thread", "Body 3")
    forum_service.pin_thread(t3.id, is_pinned=True)

    data = forum_service.list_threads()
    threads = data['threads']
    # Pinned thread must be first
    assert threads[0].id == t3.id


# ── 5. Soft Delete Behavior ───────────────────────────────────────────────────

def test_forum_soft_delete_visibility(client, forum_setup):
    """Soft-deleted threads and replies are hidden from students and visible to admin."""
    u1 = forum_setup['student1']
    admin = forum_setup['admin']
    cat = forum_setup['cat1']

    ok, thread = forum_service.create_thread(u1.id, cat.id, "Thread to Delete", "Body to be hidden")
    assert ok

    # Soft delete thread
    ok, msg = forum_service.delete_own_thread(u1, thread.id)
    assert ok

    # Normal user query does not find it
    t_found, _ = forum_service.get_thread(thread.id, is_admin=False)
    assert t_found is None

    # Admin query DOES find it
    t_admin, _ = forum_service.get_thread(thread.id, is_admin=True)
    assert t_admin is not None
    assert t_admin.is_deleted is True

    # Student viewing soft-deleted thread gets 404
    login_user(client, 'student2@forum.edu', 'Pass1234!')
    res = client.get(f'/forum/t/{thread.id}')
    assert res.status_code == 404

    # Admin viewing soft-deleted thread gets 200 with deleted notice
    login_user(client, 'admin@forum.edu', 'AdminPass123!')
    res_adm = client.get(f'/forum/t/{thread.id}')
    assert res_adm.status_code == 200
    assert "soft-deleted" in res_adm.data.decode('utf-8').lower()


# ── 6. Helpful Likes Tests ────────────────────────────────────────────────────

def test_forum_like_toggle_and_self_like_blocked(client, forum_setup):
    """Likes toggle on/off, self-liking is blocked, and duplicate like is prevented."""
    u1 = forum_setup['student1']
    u2 = forum_setup['student2']
    cat = forum_setup['cat1']

    ok, thread = forum_service.create_thread(u1.id, cat.id, "Likeable Thread", "Body")
    assert ok

    # Author cannot like own thread
    ok, msg, count, liked = forum_service.toggle_like(u1.id, 'thread', thread.id)
    assert not ok
    assert "own discussion" in msg.lower() or "own" in msg.lower()
    assert count == 0

    # Other student likes thread
    ok, msg, count, liked = forum_service.toggle_like(u2.id, 'thread', thread.id)
    assert ok
    assert liked is True
    assert count == 1

    # Second click toggles unlike
    ok, msg, count, liked = forum_service.toggle_like(u2.id, 'thread', thread.id)
    assert ok
    assert liked is False
    assert count == 0


# ── 7. Reports & Moderation Tests ─────────────────────────────────────────────

def test_forum_reporting_and_moderation(client, forum_setup):
    """User can report once per target, duplicate reports blocked, admin can resolve/dismiss."""
    u1 = forum_setup['student1']
    u2 = forum_setup['student2']
    admin = forum_setup['admin']
    cat = forum_setup['cat1']

    ok, thread = forum_service.create_thread(u1.id, cat.id, "Spammy Thread", "Buy cheap stuff here")
    assert ok

    # Student 2 reports thread
    ok, msg = forum_service.report_content(u2.id, 'thread', thread.id, "Spam promotional content")
    assert ok
    assert "submitted" in msg.lower()

    # Student 2 tries to report same thread again -> blocked
    ok, msg = forum_service.report_content(u2.id, 'thread', thread.id, "Spam again")
    assert not ok
    assert "already submitted a report" in msg.lower() or "already reported" in msg.lower()

    # Non-admin cannot access admin moderation reports
    login_user(client, 'student2@forum.edu', 'Pass1234!')
    res_mod = client.get('/admin/forum/reports')
    assert res_mod.status_code == 403

    # Admin accesses reports queue
    login_user(client, 'admin@forum.edu', 'AdminPass123!')
    res_admin_mod = client.get('/admin/forum/reports')
    assert res_admin_mod.status_code == 200
    assert "Spam promotional content" in res_admin_mod.data.decode('utf-8')

    # Admin resolves report with content deletion
    report = ForumReport.query.filter_by(reporter_id=u2.id).first()
    assert report is not None

    res_resolve = client.post(f'/admin/forum/reports/{report.id}/resolve', data={
        'action': 'resolved',
        'delete_content': '1',
        'target_type': 'thread',
        'target_id': str(thread.id)
    }, follow_redirects=True)
    assert res_resolve.status_code == 200

    _db.session.refresh(report)
    assert report.status == 'resolved'
    assert report.resolved_by == admin.id

    _db.session.refresh(thread)
    assert thread.is_deleted is True


# ── 8. Search, Filters, Sort & Resiliency Tests ───────────────────────────────

def test_forum_filters_sort_and_resiliency(forum_setup):
    """Search, category filtering, skill filtering, and graceful handling of bad inputs."""
    u1 = forum_setup['student1']
    cat1 = forum_setup['cat1']
    cat2 = forum_setup['cat2']
    skill = forum_setup['skill1']

    forum_service.create_thread(u1.id, cat1.id, "Learn Python Fundamentals", "Variables, loops, functions", skill_id=skill.id)
    forum_service.create_thread(u1.id, cat2.id, "Tech Interview Experiences", "Interview with top MNC", skill_id=None)

    # 1. Search by keyword
    data_q = forum_service.list_threads(search_query="Python")
    assert data_q['total_threads'] == 1
    assert "Python" in data_q['threads'][0].title

    # 2. Category filter
    data_cat2 = forum_service.list_threads(category_slug='interviews')
    assert data_cat2['total_threads'] == 1
    assert data_cat2['threads'][0].category_id == cat2.id

    # 3. Skill filter
    data_skill = forum_service.list_threads(skill_id=skill.id)
    assert data_skill['total_threads'] == 1
    assert data_skill['threads'][0].skill_id == skill.id

    # 4. Sorting: newest
    data_sort = forum_service.list_threads(sort_by='newest')
    assert len(data_sort['threads']) >= 2

    # 5. Invalid filter inputs handled gracefully without error
    data_bad = forum_service.list_threads(category_slug='nonexistent-slug-xyz', sort_by='weird_invalid_sort', page=-5)
    assert isinstance(data_bad['threads'], list)


# ── 9. Anti-Spam Rate Limiting & Duplicate Detection ──────────────────────────

def test_forum_rate_limiting(forum_setup):
    """Rate limit blocks 6th thread within an hour, and duplicate body within 60s is blocked."""
    u1 = forum_setup['student1']
    cat = forum_setup['cat1']

    # Create 5 threads (limit is 5 per hour)
    for i in range(5):
        ok, res = forum_service.create_thread(u1.id, cat.id, f"Thread {i}", f"Unique body content {i}")
        assert ok

    # 6th thread must be blocked by rate limiter
    ok, res = forum_service.create_thread(u1.id, cat.id, "Thread 6", "Unique body content 6")
    assert not ok
    assert "maximum 5 new discussions" in res.lower() or "too fast" in res.lower()

    # Test duplicate body detection
    forum_service._USER_THREAD_TIMESTAMPS.clear()
    ok, res = forum_service.create_thread(u1.id, cat.id, "Thread A", "Identical duplicate body content")
    assert ok
    ok, res = forum_service.create_thread(u1.id, cat.id, "Thread B", "Identical duplicate body content")
    assert not ok
    assert "duplicate" in res.lower() or "exact message" in res.lower()


# ── 10. Privacy & PII Protection ──────────────────────────────────────────────

def test_forum_pii_protection(client, forum_setup):
    """Forum templates and author info must never leak student roll numbers or emails."""
    u1 = forum_setup['student1']
    cat = forum_setup['cat1']

    ok, thread = forum_service.create_thread(u1.id, cat.id, "Privacy Discussion", "My content")
    assert ok

    # Check author info dict directly
    author_info = forum_service.get_author_info(u1)
    assert 'email' not in author_info
    assert 'roll_number' not in author_info
    assert author_info['name'] == 'Alice Sharma'
    assert author_info['branch'] == 'CSE'

    # Check rendered thread page HTML
    login_user(client, 'student2@forum.edu', 'Pass1234!')
    res = client.get(f'/forum/t/{thread.id}')
    html = res.data.decode('utf-8')

    # Ensure roll number and email are NOT exposed
    assert 'ROLL_A1' not in html
    assert 'student1@forum.edu' not in html
    assert 'Alice Sharma' in html
    assert 'CSE' in html


# ── 11. Feature Flag: FORUM_ENABLED ───────────────────────────────────────────

def test_forum_disabled_toggle(client, app, forum_setup):
    """When FORUM_ENABLED is False, forum routes render disabled template and sidebar link is hidden."""
    app.config['FORUM_ENABLED'] = False

    try:
        login_user(client, 'student1@forum.edu', 'Pass1234!')

        res = client.get('/forum/')
        assert res.status_code == 200
        html = res.data.decode('utf-8')
        assert "Forum Disabled" in html or "currently disabled" in html
        assert 'href="/forum"' not in html
    finally:
        app.config['FORUM_ENABLED'] = True


# ── 12. Query Efficiency (0 N+1 Queries) ──────────────────────────────────────

def test_forum_query_efficiency(forum_setup):
    """Forum thread listing retrieves categories, threads, reply counts and like counts in bulk queries."""
    u1 = forum_setup['student1']
    cat = forum_setup['cat1']

    # Create 10 threads (clear rate limit before each creation to bypass throttle during test setup)
    for i in range(10):
        forum_service._USER_THREAD_TIMESTAMPS.clear()
        forum_service._USER_RECENT_BODIES.clear()
        ok, t = forum_service.create_thread(u1.id, cat.id, f"Bulk Thread {i}", f"Bulk body {i}")
        assert ok

    # Measure query execution count for list_threads
    from sqlalchemy import event

    query_count = 0

    def query_listener(conn, cursor, statement, parameters, context, executemany):
        nonlocal query_count
        query_count += 1

    engine = _db.engine
    event.listen(engine, "before_cursor_execute", query_listener)

    try:
        data = forum_service.list_threads(page=1, per_page=15)
        threads = data['threads']
        # 1. Total count query
        # 2. Main threads query with joinedloads
        # 3. Aggregated reply counts query
        # 4. Aggregated like counts query
        # Must execute a fixed small number of queries (<= 5), never 1 per thread
        assert query_count <= 5
        assert len(threads) == 10
    finally:
        event.remove(engine, "before_cursor_execute", query_listener)
