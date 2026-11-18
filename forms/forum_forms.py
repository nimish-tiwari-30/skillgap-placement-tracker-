"""
forms/forum_forms.py
────────────────────
Flask-WTF Form definitions for the Open Discussion Forum:
- CreateThreadForm: New thread title, category, body, and optional skill tag.
- ReplyForm: Flat reply to a thread.
- EditThreadForm: Edit existing thread.
- EditPostForm: Edit existing reply.
- ReportForm: Report inappropriate content to moderators.
- CategoryForm: Admin category creation and management.
"""

from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, HiddenField, IntegerField
from wtforms.validators import DataRequired, Optional, Length, NumberRange


class CreateThreadForm(FlaskForm):
    """Form for starting a new discussion thread."""
    category_id = SelectField(
        'Category',
        coerce=int,
        validators=[DataRequired(message='Please choose a category.')]
    )
    title = StringField(
        'Discussion Title',
        validators=[
            DataRequired(message='Title is required.'),
            Length(min=3, max=150, message='Title must be between 3 and 150 characters.')
        ]
    )
    body = TextAreaField(
        'Discussion Content',
        validators=[
            DataRequired(message='Content is required.'),
            Length(min=5, max=5000, message='Content must be between 5 and 5000 characters.')
        ]
    )
    skill_id = SelectField(
        'Tag a Skill (Optional)',
        coerce=int,
        validators=[Optional()]
    )


class ReplyForm(FlaskForm):
    """Form for adding a reply to an active thread."""
    body = TextAreaField(
        'Write your reply',
        validators=[
            DataRequired(message='Reply content is required.'),
            Length(min=1, max=3000, message='Reply must be between 1 and 3000 characters.')
        ]
    )


class EditThreadForm(FlaskForm):
    """Form for modifying an existing discussion thread."""
    title = StringField(
        'Discussion Title',
        validators=[
            DataRequired(message='Title is required.'),
            Length(min=3, max=150, message='Title must be between 3 and 150 characters.')
        ]
    )
    body = TextAreaField(
        'Discussion Content',
        validators=[
            DataRequired(message='Content is required.'),
            Length(min=5, max=5000, message='Content must be between 5 and 5000 characters.')
        ]
    )
    skill_id = SelectField(
        'Tag a Skill (Optional)',
        coerce=int,
        validators=[Optional()]
    )


class EditPostForm(FlaskForm):
    """Form for editing an existing reply post."""
    body = TextAreaField(
        'Edit Reply',
        validators=[
            DataRequired(message='Reply content is required.'),
            Length(min=1, max=3000, message='Reply must be between 1 and 3000 characters.')
        ]
    )


class ReportForm(FlaskForm):
    """Form for reporting a thread or reply for moderation."""
    target_type = HiddenField('Target Type', validators=[DataRequired()])
    target_id = HiddenField('Target ID', validators=[DataRequired()])
    reason = TextAreaField(
        'Reason for Report',
        validators=[
            DataRequired(message='Please explain why this content violates community guidelines.'),
            Length(min=5, max=300, message='Reason must be between 5 and 300 characters.')
        ]
    )


class CategoryForm(FlaskForm):
    """Admin form to add or edit forum categories."""
    name = StringField(
        'Category Name',
        validators=[
            DataRequired(message='Name is required.'),
            Length(max=100, message='Name must be under 100 characters.')
        ]
    )
    slug = StringField(
        'URL Slug',
        validators=[
            DataRequired(message='Slug is required.'),
            Length(max=100, message='Slug must be under 100 characters.')
        ]
    )
    description = StringField(
        'Short Description',
        validators=[Optional(), Length(max=255, message='Description must be under 255 characters.')]
    )
    sort_order = IntegerField(
        'Sort Order',
        default=0,
        validators=[Optional(), NumberRange(min=0, max=1000)]
    )
