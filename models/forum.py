"""
models/forum.py
───────────────
SQLAlchemy ORM models for the Open Discussion Forum feature:
- ForumCategory: Discussion categories (e.g. Placement Prep, Interview Experiences)
- ForumThread: Main discussion threads created by users (supports soft-delete)
- ForumPost: Flat replies to threads (supports soft-delete)
- ForumPostLike: Helpful / Upvote marks on threads and posts (one per user/target)
- ForumReport: User reports for content moderation (one per user/target)

ON DELETE Rules:
- forum_threads -> forum_categories: RESTRICT (cannot delete category with active threads)
- forum_threads -> users: CASCADE (removing user deletes their threads)
- forum_threads -> skills: SET NULL (deleting a skill keeps the thread)
- forum_posts -> forum_threads: CASCADE (deleting thread deletes replies)
- forum_posts -> users: CASCADE (removing user deletes their posts)
- forum_post_likes -> users: CASCADE
- forum_reports -> users (reporter): CASCADE
- forum_reports -> users (resolved_by): SET NULL
"""

from datetime import datetime
from extensions import db


class ForumCategory(db.Model):
    """Categories grouping discussion threads."""
    __tablename__ = 'forum_categories'

    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(100), nullable=False, unique=True)
    slug        = db.Column(db.String(100), nullable=False, unique=True, index=True)
    description = db.Column(db.String(255), nullable=True)
    sort_order  = db.Column(db.Integer, nullable=False, default=0, index=True)
    created_at  = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    threads = db.relationship('ForumThread', back_populates='category', cascade='all, delete-orphan', passive_deletes=True)

    def __repr__(self) -> str:
        return f'<ForumCategory id={self.id} slug={self.slug}>'


class ForumThread(db.Model):
    """Discussion thread posted by a student or admin."""
    __tablename__ = 'forum_threads'

    id               = db.Column(db.Integer, primary_key=True)
    category_id      = db.Column(db.Integer, db.ForeignKey('forum_categories.id', ondelete='RESTRICT'), nullable=False, index=True)
    user_id          = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    title            = db.Column(db.String(150), nullable=False)
    body             = db.Column(db.Text, nullable=False)
    skill_id         = db.Column(db.Integer, db.ForeignKey('skills.id', ondelete='SET NULL'), nullable=True, index=True)
    is_pinned        = db.Column(db.Boolean, nullable=False, default=False)
    is_locked        = db.Column(db.Boolean, nullable=False, default=False)
    is_deleted       = db.Column(db.Boolean, nullable=False, default=False, index=True)
    created_at       = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at       = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_activity_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    # Relationships
    category = db.relationship('ForumCategory', back_populates='threads')
    user     = db.relationship('User', foreign_keys=[user_id])
    skill    = db.relationship('Skill', foreign_keys=[skill_id])
    posts    = db.relationship('ForumPost', back_populates='thread', cascade='all, delete-orphan', passive_deletes=True, order_by='ForumPost.created_at.asc()')

    def __repr__(self) -> str:
        return f'<ForumThread id={self.id} title={self.title[:30]}>'


class ForumPost(db.Model):
    """Flat reply to a discussion thread."""
    __tablename__ = 'forum_posts'

    id         = db.Column(db.Integer, primary_key=True)
    thread_id  = db.Column(db.Integer, db.ForeignKey('forum_threads.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    body       = db.Column(db.Text, nullable=False)
    is_deleted = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    edited_at  = db.Column(db.DateTime, nullable=True)

    # Relationships
    thread = db.relationship('ForumThread', back_populates='posts')
    user   = db.relationship('User', foreign_keys=[user_id])

    def __repr__(self) -> str:
        return f'<ForumPost id={self.id} thread_id={self.thread_id}>'


class ForumPostLike(db.Model):
    """Helpful / Upvote vote on a thread or reply."""
    __tablename__ = 'forum_post_likes'

    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    target_type = db.Column(db.Enum('thread', 'post', name='forum_like_target_enum'), nullable=False)
    target_id   = db.Column(db.Integer, nullable=False)
    created_at  = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'target_type', 'target_id', name='uq_forum_likes_user_target'),
        db.Index('idx_forum_likes_target', 'target_type', 'target_id'),
    )

    user = db.relationship('User', foreign_keys=[user_id])

    def __repr__(self) -> str:
        return f'<ForumPostLike id={self.id} user_id={self.user_id} {self.target_type}:{self.target_id}>'


class ForumReport(db.Model):
    """Flagged inappropriate content report submitted by a user for moderation."""
    __tablename__ = 'forum_reports'

    id          = db.Column(db.Integer, primary_key=True)
    reporter_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    target_type = db.Column(db.Enum('thread', 'post', name='forum_report_target_enum'), nullable=False)
    target_id   = db.Column(db.Integer, nullable=False)
    reason      = db.Column(db.String(300), nullable=False)
    status      = db.Column(db.Enum('open', 'resolved', 'dismissed', name='forum_report_status_enum'), nullable=False, default='open', index=True)
    created_at  = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    resolved_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    resolved_at = db.Column(db.DateTime, nullable=True)

    __table_args__ = (
        db.UniqueConstraint('reporter_id', 'target_type', 'target_id', name='uq_forum_reports_user_target'),
        db.Index('idx_forum_reports_target', 'target_type', 'target_id'),
    )

    reporter = db.relationship('User', foreign_keys=[reporter_id])
    resolver = db.relationship('User', foreign_keys=[resolved_by])

    def __repr__(self) -> str:
        return f'<ForumReport id={self.id} {self.target_type}:{self.target_id} status={self.status}>'
