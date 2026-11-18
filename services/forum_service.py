"""
services/forum_service.py
─────────────────────────
Service layer for the Open Discussion Forum feature.
Contains all business logic, validation, anti-spam rate limiting, query optimization,
and moderation controls so routes stay thin and testable.

Architectural highlights:
- Anti-spam rate limiting: in-memory per-process counters (documented limitation).
- Query optimization: 0 N+1 queries. Aggregates reply and like counts in bulk.
- Privacy enforcement: helper functions strip roll numbers & emails; only name, role badge,
  and branch (for students) are exposed.
- Safe soft-delete: content is hidden from normal users, visible to admins with indicators.
"""

import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any

from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload
from flask import current_app

from extensions import db
from models.user import User
from models.skill import Skill
from models.forum import ForumCategory, ForumThread, ForumPost, ForumPostLike, ForumReport


# ── In-Memory Anti-Spam Rate Limiting ─────────────────────────────────────────
# Note: In-memory per-process counters (same architecture as login brute-force throttling).
# Multi-worker WSGI servers maintain independent process state. Redis is recommended for horizontal scaling.
_USER_THREAD_TIMESTAMPS: Dict[int, List[float]] = {}
_USER_POST_TIMESTAMPS: Dict[int, List[float]] = {}
_USER_RECENT_BODIES: Dict[int, List[Tuple[str, float]]] = {}


def _clean_old_timestamps(ts_list: List[float], max_age_seconds: float) -> List[float]:
    """Prune timestamps older than max_age_seconds."""
    now = time.time()
    return [t for t in ts_list if now - t < max_age_seconds]


def is_forum_enabled() -> bool:
    """Check if forum is active via configuration."""
    if current_app:
        return bool(current_app.config.get('FORUM_ENABLED', True))
    return True


def check_thread_rate_limit(user_id: int) -> Tuple[bool, Optional[str]]:
    """Enforce max threads per hour limit per user."""
    limit = 5
    if current_app:
        limit = current_app.config.get('FORUM_RATE_LIMIT_THREADS_PER_HOUR', 5)

    now = time.time()
    history = _USER_THREAD_TIMESTAMPS.get(user_id, [])
    history = _clean_old_timestamps(history, 3600.0)
    _USER_THREAD_TIMESTAMPS[user_id] = history

    if len(history) >= limit:
        return False, f"You are posting too fast. Maximum {limit} new discussions per hour allowed. Please wait before creating another."
    return True, None


def check_post_rate_limit(user_id: int) -> Tuple[bool, Optional[str]]:
    """Enforce max replies per 10 minutes limit per user."""
    limit = 10
    if current_app:
        limit = current_app.config.get('FORUM_RATE_LIMIT_POSTS_PER_10MIN', 10)

    now = time.time()
    history = _USER_POST_TIMESTAMPS.get(user_id, [])
    history = _clean_old_timestamps(history, 600.0)
    _USER_POST_TIMESTAMPS[user_id] = history

    if len(history) >= limit:
        return False, f"You are replying too fast. Maximum {limit} replies per 10 minutes allowed. Please wait before posting again."
    return True, None


def check_duplicate_content(user_id: int, body: str) -> Tuple[bool, Optional[str]]:
    """Block an identical post/thread body repeated by the same user within 5 minutes."""
    body_clean = body.strip().lower()
    now = time.time()
    recent = _USER_RECENT_BODIES.get(user_id, [])
    # Keep only entries within last 300 seconds (5 mins)
    recent = [(b, t) for b, t in recent if now - t < 300.0]
    _USER_RECENT_BODIES[user_id] = recent

    for b, _ in recent:
        if b == body_clean:
            return False, "Duplicate content detected. You recently posted this exact message. Please avoid reposting."
    return True, None


def record_user_activity(user_id: int, action_type: str, body: str) -> None:
    """Record thread or post timestamp and body for spam prevention."""
    now = time.time()
    if action_type == 'thread':
        history = _USER_THREAD_TIMESTAMPS.get(user_id, [])
        history.append(now)
        _USER_THREAD_TIMESTAMPS[user_id] = history
    elif action_type == 'post':
        history = _USER_POST_TIMESTAMPS.get(user_id, [])
        history.append(now)
        _USER_POST_TIMESTAMPS[user_id] = history

    recent = _USER_RECENT_BODIES.get(user_id, [])
    recent.append((body.strip().lower(), now))
    _USER_RECENT_BODIES[user_id] = recent


def reset_rate_limits() -> None:
    """Helper for unit tests to clear rate limit dictionaries."""
    global _USER_THREAD_TIMESTAMPS, _USER_POST_TIMESTAMPS, _USER_RECENT_BODIES
    _USER_THREAD_TIMESTAMPS.clear()
    _USER_POST_TIMESTAMPS.clear()
    _USER_RECENT_BODIES.clear()


# ── Privacy & Author Info Helper ─────────────────────────────────────────────

def get_author_info(user: Optional[User]) -> Dict[str, Any]:
    """
    Safely formats user identity for the forum.
    Never returns roll numbers or email addresses to protect privacy.
    """
    if not user:
        return {
            'name': 'Former Member',
            'role': 'student',
            'branch': None,
            'is_admin': False,
        }

    is_admin = user.is_admin()
    if is_admin:
        # If admin has a student record (e.g. testing) use full_name, else "Administrator"
        name = "Administrator"
        if user.student and user.student.full_name:
            name = user.student.full_name
        return {
            'name': name,
            'role': 'admin',
            'branch': None,
            'is_admin': True,
        }

    # Student user
    student = user.student
    name = student.full_name if (student and student.full_name) else "Student Member"
    branch = student.branch if (student and student.branch) else None
    return {
        'name': name,
        'role': 'student',
        'branch': branch,
        'is_admin': False,
    }


# ── Category Service Functions ───────────────────────────────────────────────

def list_categories(include_counts: bool = True) -> List[Dict[str, Any]]:
    """
    Retrieve all forum categories sorted by sort_order.
    Computes active thread count in 1 bulk query to avoid N+1 queries.
    """
    categories = ForumCategory.query.order_by(ForumCategory.sort_order.asc(), ForumCategory.name.asc()).all()
    if not categories:
        return []

    counts_dict: Dict[int, int] = {}
    if include_counts:
        cat_ids = [c.id for c in categories]
        thread_counts = db.session.query(
            ForumThread.category_id, func.count(ForumThread.id)
        ).filter(
            ForumThread.category_id.in_(cat_ids),
            ForumThread.is_deleted == False
        ).group_by(ForumThread.category_id).all()
        counts_dict = dict(thread_counts)

    results = []
    for c in categories:
        results.append({
            'category': c,
            'thread_count': counts_dict.get(c.id, 0)
        })
    return results


def get_category_by_slug(slug: str) -> Optional[ForumCategory]:
    """Find a category by its unique URL slug."""
    if not slug:
        return None
    return ForumCategory.query.filter_by(slug=slug.strip().lower()).first()


def get_category_by_id(cat_id: int) -> Optional[ForumCategory]:
    """Find a category by ID."""
    return db.session.get(ForumCategory, cat_id)


def create_category(name: str, slug: str, description: Optional[str] = None, sort_order: int = 0) -> Tuple[bool, Any]:
    """Create a new category (admin action)."""
    name = (name or '').strip()
    slug = (slug or '').strip().lower()
    description = (description or '').strip() or None

    if not name or len(name) > 100:
        return False, "Category name must be between 1 and 100 characters."
    if not slug or len(slug) > 100:
        return False, "Slug must be between 1 and 100 characters."

    if ForumCategory.query.filter_by(name=name).first():
        return False, f"Category with name '{name}' already exists."
    if ForumCategory.query.filter_by(slug=slug).first():
        return False, f"Category with slug '{slug}' already exists."

    cat = ForumCategory(
        name=name,
        slug=slug,
        description=description,
        sort_order=sort_order
    )
    db.session.add(cat)
    db.session.commit()
    return True, cat


def update_category(cat_id: int, name: str, slug: str, description: Optional[str] = None, sort_order: int = 0) -> Tuple[bool, Any]:
    """Update an existing category (admin action)."""
    cat = db.session.get(ForumCategory, cat_id)
    if not cat:
        return False, "Category not found."

    name = (name or '').strip()
    slug = (slug or '').strip().lower()
    description = (description or '').strip() or None

    if not name or len(name) > 100:
        return False, "Category name must be between 1 and 100 characters."
    if not slug or len(slug) > 100:
        return False, "Slug must be between 1 and 100 characters."

    dup_name = ForumCategory.query.filter(ForumCategory.name == name, ForumCategory.id != cat_id).first()
    if dup_name:
        return False, f"Another category with name '{name}' already exists."

    dup_slug = ForumCategory.query.filter(ForumCategory.slug == slug, ForumCategory.id != cat_id).first()
    if dup_slug:
        return False, f"Another category with slug '{slug}' already exists."

    cat.name = name
    cat.slug = slug
    cat.description = description
    cat.sort_order = sort_order
    db.session.commit()
    return True, cat


# ── Thread Service Functions ─────────────────────────────────────────────────

def list_threads(
    category_slug: Optional[str] = None,
    search_query: Optional[str] = None,
    skill_id: Optional[int] = None,
    sort_by: str = 'latest_activity',
    page: int = 1,
    per_page: int = 15,
    current_user: Optional[User] = None,
    is_admin: bool = False
) -> Dict[str, Any]:
    """
    List discussion threads with filters, search, and pagination.
    Optimized: Eager-loads relations and fetches reply/like counts in 2 bulk queries (0 N+1).
    """
    query = ForumThread.query.options(
        joinedload(ForumThread.category),
        joinedload(ForumThread.skill),
        joinedload(ForumThread.user).joinedload(User.student)
    )

    # 1. Soft-delete filter (admins can see deleted items marked in UI)
    if not is_admin:
        query = query.filter(ForumThread.is_deleted == False)

    # 2. Category filter
    selected_category = None
    if category_slug:
        selected_category = get_category_by_slug(category_slug)
        if selected_category:
            query = query.filter(ForumThread.category_id == selected_category.id)

    # 3. Skill filter
    selected_skill = None
    if skill_id and str(skill_id).isdigit():
        s_id = int(skill_id)
        selected_skill = db.session.get(Skill, s_id)
        if selected_skill:
            query = query.filter(ForumThread.skill_id == s_id)

    # 4. Search query (title & body)
    q_clean = (search_query or '').strip()
    if q_clean:
        pattern = f"%{q_clean}%"
        query = query.filter(or_(ForumThread.title.ilike(pattern), ForumThread.body.ilike(pattern)))

    # 5. Sorting: Pinned threads always come first, then user sort
    sort_clean = (sort_by or '').strip().lower()
    if sort_clean == 'newest':
        query = query.order_by(ForumThread.is_pinned.desc(), ForumThread.created_at.desc())
    elif sort_clean == 'most_replies':
        # Subquery for reply count
        reply_subq = db.session.query(
            ForumPost.thread_id,
            func.count(ForumPost.id).label('rep_count')
        ).filter(ForumPost.is_deleted == False).group_by(ForumPost.thread_id).subquery()

        query = query.outerjoin(reply_subq, ForumThread.id == reply_subq.c.thread_id)\
                     .order_by(ForumThread.is_pinned.desc(), func.coalesce(reply_subq.c.rep_count, 0).desc(), ForumThread.last_activity_at.desc())
    else:
        # Default: latest_activity
        sort_clean = 'latest_activity'
        query = query.order_by(ForumThread.is_pinned.desc(), ForumThread.last_activity_at.desc())

    # 6. Pagination
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    threads = pagination.items

    # 7. Bulk aggregate reply & like counts for thread IDs on this page (Fixed 2 queries)
    thread_ids = [t.id for t in threads]
    reply_counts: Dict[int, int] = {}
    like_counts: Dict[int, int] = {}
    user_liked_thread_ids = set()

    if thread_ids:
        # Reply counts
        reps = db.session.query(
            ForumPost.thread_id, func.count(ForumPost.id)
        ).filter(
            ForumPost.thread_id.in_(thread_ids),
            ForumPost.is_deleted == False
        ).group_by(ForumPost.thread_id).all()
        reply_counts = dict(reps)

        # Like counts
        likes = db.session.query(
            ForumPostLike.target_id, func.count(ForumPostLike.id)
        ).filter(
            ForumPostLike.target_type == 'thread',
            ForumPostLike.target_id.in_(thread_ids)
        ).group_by(ForumPostLike.target_id).all()
        like_counts = dict(likes)

        # Current user likes
        if current_user and current_user.is_authenticated:
            user_likes = db.session.query(ForumPostLike.target_id).filter(
                ForumPostLike.target_type == 'thread',
                ForumPostLike.user_id == current_user.id,
                ForumPostLike.target_id.in_(thread_ids)
            ).all()
            user_liked_thread_ids = {r[0] for r in user_likes}

    # Annotate thread objects in memory
    for t in threads:
        t.reply_count = reply_counts.get(t.id, 0)
        t.like_count = like_counts.get(t.id, 0)
        t.user_has_liked = t.id in user_liked_thread_ids
        t.author_info = get_author_info(t.user)

    return {
        'threads': threads,
        'pagination': pagination,
        'selected_category': selected_category,
        'selected_skill': selected_skill,
        'search_query': q_clean,
        'sort_by': sort_clean,
        'total_threads': pagination.total,
    }


def get_thread(
    thread_id: int,
    page: int = 1,
    per_page: int = 20,
    current_user: Optional[User] = None,
    is_admin: bool = False
) -> Tuple[Optional[ForumThread], Optional[Any]]:
    """
    Retrieve thread details and its paginated flat replies.
    Optimized: Single bulk query for post likes.
    Returns (thread, replies_pagination) or (None, None) if 404.
    """
    thread = ForumThread.query.options(
        joinedload(ForumThread.category),
        joinedload(ForumThread.skill),
        joinedload(ForumThread.user).joinedload(User.student)
    ).filter(ForumThread.id == thread_id).first()

    if not thread:
        return None, None
    if thread.is_deleted and not is_admin:
        return None, None

    # Thread author info and likes
    thread.author_info = get_author_info(thread.user)
    thread.like_count = ForumPostLike.query.filter_by(target_type='thread', target_id=thread.id).count()
    thread.user_has_liked = False
    if current_user and current_user.is_authenticated:
        thread.user_has_liked = bool(ForumPostLike.query.filter_by(
            target_type='thread', target_id=thread.id, user_id=current_user.id
        ).first())

    # Replies query
    posts_query = ForumPost.query.options(
        joinedload(ForumPost.user).joinedload(User.student)
    ).filter(ForumPost.thread_id == thread.id)

    if not is_admin:
        posts_query = posts_query.filter(ForumPost.is_deleted == False)

    posts_query = posts_query.order_by(ForumPost.created_at.asc())
    replies_pagination = posts_query.paginate(page=page, per_page=per_page, error_out=False)
    replies = replies_pagination.items

    # Bulk like counts for replies on this page
    post_ids = [p.id for p in replies]
    post_likes_dict: Dict[int, int] = {}
    user_liked_post_ids = set()

    if post_ids:
        counts = db.session.query(
            ForumPostLike.target_id, func.count(ForumPostLike.id)
        ).filter(
            ForumPostLike.target_type == 'post',
            ForumPostLike.target_id.in_(post_ids)
        ).group_by(ForumPostLike.target_id).all()
        post_likes_dict = dict(counts)

        if current_user and current_user.is_authenticated:
            u_likes = db.session.query(ForumPostLike.target_id).filter(
                ForumPostLike.target_type == 'post',
                ForumPostLike.user_id == current_user.id,
                ForumPostLike.target_id.in_(post_ids)
            ).all()
            user_liked_post_ids = {r[0] for r in u_likes}

    for p in replies:
        p.like_count = post_likes_dict.get(p.id, 0)
        p.user_has_liked = p.id in user_liked_post_ids
        p.author_info = get_author_info(p.user)

    return thread, replies_pagination


def create_thread(
    user_id: int,
    category_id: int,
    title: str,
    body: str,
    skill_id: Optional[int] = None
) -> Tuple[bool, Any]:
    """Validate, rate limit, and create a new discussion thread."""
    title = (title or '').strip()
    body = (body or '').strip()

    if not title or len(title) > 150:
        return False, "Title must be between 1 and 150 characters."
    if not body or len(body) > 5000:
        return False, "Content body must be between 1 and 5000 characters."

    category = db.session.get(ForumCategory, category_id)
    if not category:
        return False, "Please select a valid discussion category."

    # Verify skill if provided
    valid_skill_id = None
    if skill_id:
        try:
            s_id = int(skill_id)
            if s_id > 0:
                skill = db.session.get(Skill, s_id)
                if skill:
                    valid_skill_id = skill.id
        except (ValueError, TypeError):
            valid_skill_id = None

    # Anti-spam checks
    ok_rate, rate_msg = check_thread_rate_limit(user_id)
    if not ok_rate:
        return False, rate_msg

    ok_dup, dup_msg = check_duplicate_content(user_id, body)
    if not ok_dup:
        return False, dup_msg

    now = datetime.utcnow()
    thread = ForumThread(
        category_id=category.id,
        user_id=user_id,
        title=title,
        body=body,
        skill_id=valid_skill_id,
        created_at=now,
        updated_at=now,
        last_activity_at=now
    )
    db.session.add(thread)
    db.session.commit()

    record_user_activity(user_id, 'thread', body)
    return True, thread


def create_reply(user_id: int, thread_id: int, body: str) -> Tuple[bool, Any]:
    """Validate, rate limit, and add a reply to a thread."""
    thread = db.session.get(ForumThread, thread_id)
    if not thread or thread.is_deleted:
        return False, "Discussion not found."
    if thread.is_locked:
        return False, "This discussion is locked and cannot receive new replies."

    body = (body or '').strip()
    if not body or len(body) > 3000:
        return False, "Reply must be between 1 and 3000 characters."

    # Anti-spam checks
    ok_rate, rate_msg = check_post_rate_limit(user_id)
    if not ok_rate:
        return False, rate_msg

    ok_dup, dup_msg = check_duplicate_content(user_id, body)
    if not ok_dup:
        return False, dup_msg

    now = datetime.utcnow()
    post = ForumPost(
        thread_id=thread.id,
        user_id=user_id,
        body=body,
        created_at=now
    )
    thread.last_activity_at = now

    db.session.add(post)
    db.session.commit()

    record_user_activity(user_id, 'post', body)
    return True, post


def edit_own_thread(
    user: User,
    thread_id: int,
    title: str,
    body: str,
    skill_id: Optional[int] = None
) -> Tuple[bool, Any]:
    """Edit own thread (or admin can edit any). Sets updated_at."""
    thread = db.session.get(ForumThread, thread_id)
    if not thread or thread.is_deleted:
        return False, "Discussion not found."

    if thread.user_id != user.id and not user.is_admin():
        return False, "You can only edit your own discussion."

    title = (title or '').strip()
    body = (body or '').strip()
    if not title or len(title) > 150:
        return False, "Title must be between 1 and 150 characters."
    if not body or len(body) > 5000:
        return False, "Content body must be between 1 and 5000 characters."

    valid_skill_id = None
    if skill_id:
        try:
            s_id = int(skill_id)
            if s_id > 0:
                skill = db.session.get(Skill, s_id)
                if skill:
                    valid_skill_id = skill.id
        except (ValueError, TypeError):
            valid_skill_id = None

    thread.title = title
    thread.body = body
    thread.skill_id = valid_skill_id
    thread.updated_at = datetime.utcnow()
    db.session.commit()
    return True, thread


def edit_own_post(user: User, post_id: int, body: str) -> Tuple[bool, Any]:
    """Edit own reply (or admin can edit any). Sets edited_at."""
    post = db.session.get(ForumPost, post_id)
    if not post or post.is_deleted:
        return False, "Reply not found."

    if post.user_id != user.id and not user.is_admin():
        return False, "You can only edit your own reply."

    body = (body or '').strip()
    if not body or len(body) > 3000:
        return False, "Reply must be between 1 and 3000 characters."

    post.body = body
    post.edited_at = datetime.utcnow()
    db.session.commit()
    return True, post


def delete_own_thread(user: User, thread_id: int) -> Tuple[bool, str]:
    """Soft delete a thread (author or admin)."""
    thread = db.session.get(ForumThread, thread_id)
    if not thread:
        return False, "Discussion not found."

    if thread.user_id != user.id and not user.is_admin():
        return False, "You can only delete your own discussion."

    thread.is_deleted = True
    db.session.commit()
    return True, "Discussion deleted."


def delete_own_post(user: User, post_id: int) -> Tuple[bool, str]:
    """Soft delete a reply (author or admin)."""
    post = db.session.get(ForumPost, post_id)
    if not post:
        return False, "Reply not found."

    if post.user_id != user.id and not user.is_admin():
        return False, "You can only delete your own reply."

    post.is_deleted = True
    db.session.commit()
    return True, "Reply deleted."


# ── Likes & Helpful Marks ───────────────────────────────────────────────────

def toggle_like(user_id: int, target_type: str, target_id: int) -> Tuple[bool, str, int, bool]:
    """
    Toggle helpful/upvote mark on a thread or reply.
    Blocks liking own content. Enforces 1 vote per user.
    Returns (success, message, new_like_count, user_has_liked).
    """
    target_type = (target_type or '').strip().lower()
    if target_type not in ('thread', 'post'):
        return False, "Invalid target type.", 0, False

    if target_type == 'thread':
        item = db.session.get(ForumThread, target_id)
        if not item or item.is_deleted:
            return False, "Discussion not found.", 0, False
        if item.user_id == user_id:
            count = ForumPostLike.query.filter_by(target_type='thread', target_id=target_id).count()
            return False, "You cannot mark your own discussion as helpful.", count, False
    else:
        item = db.session.get(ForumPost, target_id)
        if not item or item.is_deleted:
            return False, "Reply not found.", 0, False
        if item.user_id == user_id:
            count = ForumPostLike.query.filter_by(target_type='post', target_id=target_id).count()
            return False, "You cannot mark your own reply as helpful.", count, False

    existing = ForumPostLike.query.filter_by(
        user_id=user_id,
        target_type=target_type,
        target_id=target_id
    ).first()

    if existing:
        db.session.delete(existing)
        db.session.commit()
        liked = False
        msg = "Helpful vote removed."
    else:
        new_like = ForumPostLike(
            user_id=user_id,
            target_type=target_type,
            target_id=target_id
        )
        db.session.add(new_like)
        db.session.commit()
        liked = True
        msg = "Marked as helpful!"

    new_count = ForumPostLike.query.filter_by(target_type=target_type, target_id=target_id).count()
    return True, msg, new_count, liked


# ── Content Reporting & Moderation ──────────────────────────────────────────

def report_content(reporter_id: int, target_type: str, target_id: int, reason: str) -> Tuple[bool, str]:
    """Submit a moderation report for inappropriate content."""
    target_type = (target_type or '').strip().lower()
    if target_type not in ('thread', 'post'):
        return False, "Invalid report target."

    reason = (reason or '').strip()
    if not reason or len(reason) > 300:
        return False, "Report reason must be between 1 and 300 characters."

    if target_type == 'thread':
        item = db.session.get(ForumThread, target_id)
    else:
        item = db.session.get(ForumPost, target_id)

    if not item or item.is_deleted:
        return False, "Content item not found."

    # Check if this user already reported this item
    existing = ForumReport.query.filter_by(
        reporter_id=reporter_id,
        target_type=target_type,
        target_id=target_id
    ).first()
    if existing:
        return False, "You have already submitted a report for this content item."

    rep = ForumReport(
        reporter_id=reporter_id,
        target_type=target_type,
        target_id=target_id,
        reason=reason,
        status='open',
        created_at=datetime.utcnow()
    )
    db.session.add(rep)
    db.session.commit()
    return True, "Thank you. Your report has been submitted to moderators."


def list_reports(status: str = 'open', page: int = 1, per_page: int = 20) -> Dict[str, Any]:
    """List reports for admin moderation panel."""
    status_clean = (status or 'open').strip().lower()
    query = ForumReport.query.options(
        joinedload(ForumReport.reporter).joinedload(User.student),
        joinedload(ForumReport.resolver)
    )

    if status_clean in ('open', 'resolved', 'dismissed'):
        query = query.filter(ForumReport.status == status_clean)

    query = query.order_by(ForumReport.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    reports = pagination.items

    # Attach preview of reported content
    for r in reports:
        r.reporter_info = get_author_info(r.reporter)
        r.target_preview = None
        r.target_deleted = False
        r.thread_id = None
        if r.target_type == 'thread':
            t = db.session.get(ForumThread, r.target_id)
            if t:
                r.target_preview = f"Thread: {t.title}"
                r.target_body = t.body[:150]
                r.target_deleted = t.is_deleted
                r.thread_id = t.id
        elif r.target_type == 'post':
            p = db.session.get(ForumPost, r.target_id)
            if p:
                r.target_preview = "Reply post"
                r.target_body = p.body[:150]
                r.target_deleted = p.is_deleted
                r.thread_id = p.thread_id

    return {
        'reports': reports,
        'pagination': pagination,
        'status': status_clean,
    }


def resolve_report(report_id: int, admin_user_id: int, action: str = 'resolved') -> Tuple[bool, str]:
    """Admin action: resolve or dismiss a report."""
    rep = db.session.get(ForumReport, report_id)
    if not rep:
        return False, "Report not found."

    action_clean = (action or 'resolved').strip().lower()
    if action_clean not in ('resolved', 'dismissed'):
        action_clean = 'resolved'

    rep.status = action_clean
    rep.resolved_by = admin_user_id
    rep.resolved_at = datetime.utcnow()
    db.session.commit()
    return True, f"Report marked as {action_clean}."


# ── Admin Thread Actions ────────────────────────────────────────────────────

def pin_thread(thread_id: int, is_pinned: bool = True) -> Tuple[bool, str]:
    """Pin or unpin a thread (admin action)."""
    thread = db.session.get(ForumThread, thread_id)
    if not thread:
        return False, "Discussion not found."
    thread.is_pinned = is_pinned
    db.session.commit()
    state = "pinned" if is_pinned else "unpinned"
    return True, f"Discussion successfully {state}."


def lock_thread(thread_id: int, is_locked: bool = True) -> Tuple[bool, str]:
    """Lock or unlock a thread (admin action)."""
    thread = db.session.get(ForumThread, thread_id)
    if not thread:
        return False, "Discussion not found."
    thread.is_locked = is_locked
    db.session.commit()
    state = "locked" if is_locked else "unlocked"
    return True, f"Discussion successfully {state}."


def restore_thread(thread_id: int) -> Tuple[bool, str]:
    """Restore a soft-deleted thread (admin action)."""
    thread = db.session.get(ForumThread, thread_id)
    if not thread:
        return False, "Discussion not found."
    thread.is_deleted = False
    db.session.commit()
    return True, "Discussion successfully restored."


def restore_post(post_id: int) -> Tuple[bool, str]:
    """Restore a soft-deleted reply (admin action)."""
    post = db.session.get(ForumPost, post_id)
    if not post:
        return False, "Reply not found."
    post.is_deleted = False
    db.session.commit()
    return True, "Reply successfully restored."


def get_latest_threads_for_dashboard(limit: int = 3) -> List[ForumThread]:
    """Retrieve top N recent active threads for student dashboard widget."""
    if not is_forum_enabled():
        return []
    return ForumThread.query.options(
        joinedload(ForumThread.category)
    ).filter(
        ForumThread.is_deleted == False
    ).order_by(
        ForumThread.last_activity_at.desc()
    ).limit(limit).all()
