"""
routes/forum.py
───────────────
Routes and controller actions for the Open Discussion Forum.
Handles thread browsing, creation, replies, editing, soft-deletion,
likes, content reporting, and inline admin moderation actions.

All routes require authentication (@login_required / before_request).
Open to both students and admins.
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, jsonify
from flask_login import current_user, login_required
from utils.decorators import admin_required

from models.forum import ForumCategory, ForumThread, ForumPost
from models.skill import Skill
from forms.forum_forms import (
    CreateThreadForm, ReplyForm, EditThreadForm, EditPostForm, ReportForm
)
from services import forum_service

forum_bp = Blueprint('forum', __name__)


@forum_bp.before_request
def check_forum_access():
    """Ensure user is logged in and forum feature is active."""
    if not current_user.is_authenticated:
        flash("Please sign in to access the discussion forum.", "warning")
        return redirect(url_for('auth.login'))

    if not forum_service.is_forum_enabled():
        return render_template('forum/disabled.html', title="Forum Offline"), 200


# ── Forum Home & Category Views ───────────────────────────────────────────────

@forum_bp.route('/')
def index():
    """
    Forum home page:
    Displays discussion categories, active filters, search, and paginated threads.
    """
    category_slug = request.args.get('c', '').strip() or None
    search_query = request.args.get('q', '').strip() or None
    skill_id_str = request.args.get('skill', '').strip() or None
    sort_by = request.args.get('sort', 'latest_activity').strip()
    page = request.args.get('page', 1, type=int)

    # Validate skill ID gracefully
    skill_id = None
    if skill_id_str and skill_id_str.isdigit():
        skill_id = int(skill_id_str)

    # Fetch data through optimized service layer
    categories_data = forum_service.list_categories(include_counts=True)
    threads_data = forum_service.list_threads(
        category_slug=category_slug,
        search_query=search_query,
        skill_id=skill_id,
        sort_by=sort_by,
        page=page,
        per_page=15,
        current_user=current_user,
        is_admin=current_user.is_admin()
    )

    all_skills = Skill.query.order_by(Skill.name.asc()).all()

    return render_template(
        'forum/index.html',
        title="Discussion Forum",
        categories_data=categories_data,
        threads=threads_data['threads'],
        pagination=threads_data['pagination'],
        selected_category=threads_data['selected_category'],
        selected_skill=threads_data['selected_skill'],
        search_query=threads_data['search_query'],
        sort_by=threads_data['sort_by'],
        total_threads=threads_data['total_threads'],
        all_skills=all_skills
    )


@forum_bp.route('/c/<slug>')
def category_view(slug: str):
    """Direct category filter URL (e.g. /forum/c/placement-preparation)."""
    return redirect(url_for('forum.index', c=slug))


# ── Create Thread ─────────────────────────────────────────────────────────────

@forum_bp.route('/new', methods=['GET', 'POST'])
def new_thread():
    """Create a new discussion thread."""
    form = CreateThreadForm()

    # Populate category choices
    categories = ForumCategory.query.order_by(ForumCategory.sort_order.asc(), ForumCategory.name.asc()).all()
    form.category_id.choices = [(c.id, c.name) for c in categories]

    # Populate optional skill tag choices
    skills = Skill.query.order_by(Skill.name.asc()).all()
    form.skill_id.choices = [(0, 'None / General')] + [(s.id, s.name) for s in skills]

    # Pre-select category if passed in query param
    cat_param = request.args.get('c', '').strip()
    if request.method == 'GET' and cat_param:
        cat_match = ForumCategory.query.filter_by(slug=cat_param).first()
        if cat_match:
            form.category_id.data = cat_match.id

    if form.validate_on_submit():
        category_id = form.category_id.data
        title = form.title.data
        body = form.body.data
        skill_id = form.skill_id.data if form.skill_id.data and form.skill_id.data > 0 else None

        ok, res = forum_service.create_thread(
            user_id=current_user.id,
            category_id=category_id,
            title=title,
            body=body,
            skill_id=skill_id
        )

        if ok:
            flash("Your discussion thread has been posted!", "success")
            return redirect(url_for('forum.thread_view', thread_id=res.id))
        else:
            flash(res, "danger")

    return render_template(
        'forum/new_thread.html',
        title="Start a Discussion",
        form=form
    )


# ── Thread View & Replies ─────────────────────────────────────────────────────

@forum_bp.route('/t/<int:thread_id>')
def thread_view(thread_id: int):
    """
    Thread detail page with original post, helpful button,
    paginated replies, and reply submission form.
    """
    page = request.args.get('page', 1, type=int)

    thread, replies_pagination = forum_service.get_thread(
        thread_id=thread_id,
        page=page,
        per_page=20,
        current_user=current_user,
        is_admin=current_user.is_admin()
    )

    if not thread:
        abort(404)

    reply_form = ReplyForm()
    report_form = ReportForm()

    return render_template(
        'forum/thread.html',
        title=thread.title,
        thread=thread,
        replies_pagination=replies_pagination,
        replies=replies_pagination.items,
        reply_form=reply_form,
        report_form=report_form
    )


@forum_bp.route('/t/<int:thread_id>/reply', methods=['POST'])
def post_reply(thread_id: int):
    """Submit a flat reply to an active thread."""
    form = ReplyForm()
    if form.validate_on_submit():
        body = form.body.data
        ok, res = forum_service.create_reply(
            user_id=current_user.id,
            thread_id=thread_id,
            body=body
        )
        if ok:
            flash("Your reply has been posted!", "success")
        else:
            flash(res, "danger")
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"{error}", "danger")

    return redirect(url_for('forum.thread_view', thread_id=thread_id))


# ── Edit & Delete Content ─────────────────────────────────────────────────────

@forum_bp.route('/t/<int:thread_id>/edit', methods=['GET', 'POST'])
def edit_thread(thread_id: int):
    """Edit own thread (or admin)."""
    thread = ForumThread.query.get(thread_id)
    if not thread or (thread.is_deleted and not current_user.is_admin()):
        abort(404)

    if thread.user_id != current_user.id and not current_user.is_admin():
        abort(403)

    form = EditThreadForm()
    skills = Skill.query.order_by(Skill.name.asc()).all()
    form.skill_id.choices = [(0, 'None / General')] + [(s.id, s.name) for s in skills]

    if request.method == 'GET':
        form.title.data = thread.title
        form.body.data = thread.body
        form.skill_id.data = thread.skill_id or 0

    if form.validate_on_submit():
        skill_id = form.skill_id.data if form.skill_id.data and form.skill_id.data > 0 else None
        ok, res = forum_service.edit_own_thread(
            user=current_user,
            thread_id=thread_id,
            title=form.title.data,
            body=form.body.data,
            skill_id=skill_id
        )
        if ok:
            flash("Discussion updated successfully.", "success")
            return redirect(url_for('forum.thread_view', thread_id=thread_id))
        else:
            flash(res, "danger")

    return render_template(
        'forum/edit_thread.html',
        title="Edit Discussion",
        form=form,
        thread=thread
    )


@forum_bp.route('/t/<int:thread_id>/delete', methods=['POST'])
def delete_thread(thread_id: int):
    """Soft delete thread (author or admin)."""
    ok, msg = forum_service.delete_own_thread(user=current_user, thread_id=thread_id)
    if ok:
        flash("Discussion deleted.", "info")
        return redirect(url_for('forum.index'))
    else:
        flash(msg, "danger")
        return redirect(url_for('forum.thread_view', thread_id=thread_id))


@forum_bp.route('/p/<int:post_id>/edit', methods=['GET', 'POST'])
def edit_post(post_id: int):
    """Edit own reply (or admin)."""
    post = ForumPost.query.get(post_id)
    if not post or (post.is_deleted and not current_user.is_admin()):
        abort(404)

    if post.user_id != current_user.id and not current_user.is_admin():
        abort(403)

    form = EditPostForm()
    if request.method == 'GET':
        form.body.data = post.body

    if form.validate_on_submit():
        ok, res = forum_service.edit_own_post(
            user=current_user,
            post_id=post_id,
            body=form.body.data
        )
        if ok:
            flash("Reply updated.", "success")
            return redirect(url_for('forum.thread_view', thread_id=post.thread_id))
        else:
            flash(res, "danger")

    return render_template(
        'forum/edit_post.html',
        title="Edit Reply",
        form=form,
        post=post
    )


@forum_bp.route('/p/<int:post_id>/delete', methods=['POST'])
def delete_post(post_id: int):
    """Soft delete reply (author or admin)."""
    post = ForumPost.query.get(post_id)
    thread_id = post.thread_id if post else None

    ok, msg = forum_service.delete_own_post(user=current_user, post_id=post_id)
    if ok:
        flash("Reply deleted.", "info")
    else:
        flash(msg, "danger")

    if thread_id:
        return redirect(url_for('forum.thread_view', thread_id=thread_id))
    return redirect(url_for('forum.index'))


# ── Helpful / Like Votes ──────────────────────────────────────────────────────

@forum_bp.route('/like', methods=['POST'])
def like_content():
    """Toggle helpful mark on a thread or reply."""
    target_type = request.form.get('target_type', '').strip().lower()
    target_id_str = request.form.get('target_id', '').strip()

    if not target_id_str.isdigit():
        flash("Invalid target.", "danger")
        return redirect(url_for('forum.index'))

    target_id = int(target_id_str)
    ok, msg, new_count, liked = forum_service.toggle_like(
        user_id=current_user.id,
        target_type=target_type,
        target_id=target_id
    )

    # Support JSON requests for smooth vanilla JS upvoting
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
        return jsonify({
            'success': ok,
            'message': msg,
            'like_count': new_count,
            'liked': liked
        })

    flash(msg, "success" if ok else "warning")
    thread_id = target_id if target_type == 'thread' else getattr(ForumPost.query.get(target_id), 'thread_id', None)
    if thread_id:
        return redirect(url_for('forum.thread_view', thread_id=thread_id))
    return redirect(url_for('forum.index'))


# ── Report Inappropriate Content ─────────────────────────────────────────────

@forum_bp.route('/report', methods=['POST'])
def report_content():
    """Submit a moderation report for inappropriate content."""
    form = ReportForm()
    if form.validate_on_submit():
        target_type = form.target_type.data
        target_id = int(form.target_id.data)
        reason = form.reason.data

        ok, msg = forum_service.report_content(
            reporter_id=current_user.id,
            target_type=target_type,
            target_id=target_id,
            reason=reason
        )
        flash(msg, "info" if ok else "warning")

        thread_id = target_id if target_type == 'thread' else getattr(ForumPost.query.get(target_id), 'thread_id', None)
        if thread_id:
            return redirect(url_for('forum.thread_view', thread_id=thread_id))
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"{error}", "danger")

    return redirect(url_for('forum.index'))


# ── Admin Moderation Actions (Inline) ─────────────────────────────────────────

@forum_bp.route('/t/<int:thread_id>/pin', methods=['POST'])
@admin_required
def pin_thread(thread_id: int):
    """Pin or unpin discussion thread (admin only)."""
    thread = ForumThread.query.get(thread_id)
    if not thread:
        abort(404)
    new_state = not thread.is_pinned
    ok, msg = forum_service.pin_thread(thread_id, is_pinned=new_state)
    flash(msg, "success" if ok else "danger")
    return redirect(url_for('forum.thread_view', thread_id=thread_id))


@forum_bp.route('/t/<int:thread_id>/lock', methods=['POST'])
@admin_required
def lock_thread(thread_id: int):
    """Lock or unlock discussion thread (admin only)."""
    thread = ForumThread.query.get(thread_id)
    if not thread:
        abort(404)
    new_state = not thread.is_locked
    ok, msg = forum_service.lock_thread(thread_id, is_locked=new_state)
    flash(msg, "success" if ok else "danger")
    return redirect(url_for('forum.thread_view', thread_id=thread_id))


@forum_bp.route('/t/<int:thread_id>/restore', methods=['POST'])
@admin_required
def restore_thread(thread_id: int):
    """Restore a soft-deleted discussion thread (admin only)."""
    ok, msg = forum_service.restore_thread(thread_id)
    flash(msg, "success" if ok else "danger")
    return redirect(url_for('forum.thread_view', thread_id=thread_id))


@forum_bp.route('/p/<int:post_id>/restore', methods=['POST'])
@admin_required
def restore_post(post_id: int):
    """Restore a soft-deleted reply post (admin only)."""
    post = ForumPost.query.get(post_id)
    thread_id = post.thread_id if post else None
    ok, msg = forum_service.restore_post(post_id)
    flash(msg, "success" if ok else "danger")
    if thread_id:
        return redirect(url_for('forum.thread_view', thread_id=thread_id))
    return redirect(url_for('forum.index'))
