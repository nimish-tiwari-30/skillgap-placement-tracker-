"""
forms/job_forms.py
──────────────────
WTForms form classes for Job Roles and Job Descriptions.

Phase 7:
- JobRoleForm: Create and edit high-level career job roles (title, department, description).
- JobDescriptionForm: Create and edit company job postings (title, company, role, location, min_experience, description_text).
"""

from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, BooleanField
from wtforms.validators import DataRequired, Optional, Length

# Importance scale choices for job skills (1 to 5)
# Documented scale:
# 1 = Nice-to-have
# 2 = Desirable
# 3 = Required (Default)
# 4 = Highly Important
# 5 = Critical
# Note: Phase 8 (Skill-gap analysis) uses these weights for weighted match % computation.
IMPORTANCE_CHOICES = [
    (1, '1 — Nice-to-have'),
    (2, '2 — Desirable'),
    (3, '3 — Required (Default)'),
    (4, '4 — Highly Important'),
    (5, '5 — Critical'),
]


class JobRoleForm(FlaskForm):
    """Form for adding and editing job roles."""
    title = StringField(
        'Role Name',
        validators=[DataRequired(message='Role name is required.'), Length(max=150)]
    )
    department = StringField(
        'Department',
        validators=[Optional(), Length(max=100)]
    )
    description = TextAreaField(
        'Description',
        validators=[Optional()]
    )


class JobDescriptionForm(FlaskForm):
    """Form for adding and editing job descriptions."""
    job_role_id = SelectField(
        'Job Role',
        coerce=int,
        validators=[DataRequired(message='Please select a job role.')]
    )
    title = StringField(
        'Job Title',
        validators=[DataRequired(message='Job title is required.'), Length(max=255)]
    )
    company_name = StringField(
        'Company Name',
        validators=[DataRequired(message='Company name is required.'), Length(max=255)]
    )
    location = StringField(
        'Location',
        validators=[Optional(), Length(max=150)],
        default='Remote'
    )
    min_experience = StringField(
        'Minimum Experience',
        validators=[Optional(), Length(max=50)],
        default='0-1 years'
    )
    description_text = TextAreaField(
        'Job Description Text',
        validators=[
            DataRequired(message='Job description text is required.'),
            Length(min=10, message='Please provide a detailed job description (at least 10 characters).')
        ]
    )
    is_active = BooleanField(
        'Active Listing',
        default=True
    )
