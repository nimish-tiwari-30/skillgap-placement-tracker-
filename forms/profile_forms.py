"""
forms/profile_forms.py
───────────────────────
WTForms form classes for student profile management.

Why forms? (viva answer)
  Forms handle validation and CSRF in one place.
  Instead of writing manual `if not request.form.get('field')` checks
  in every route, WTForms gives us validators + HTML generation.
"""

from flask_wtf import FlaskForm
from wtforms import (
    StringField, SelectField, FloatField, IntegerField,
    TextAreaField, URLField, DateField, HiddenField
)
from wtforms.validators import (
    DataRequired, Optional, NumberRange, Length, URL, ValidationError
)

# ── Proficiency choices (1-5 mapped to labels) ────────────────────────────────
PROFICIENCY_CHOICES = [
    ('Beginner',     '1 — Beginner'),
    ('Intermediate', '2 — Intermediate'),
    ('Advanced',     '3 — Advanced'),
]

# ── Branch choices ─────────────────────────────────────────────────────────────
BRANCH_CHOICES = [
    ('', 'Select Branch'),
    ('Computer Science',      'Computer Science'),
    ('Information Technology','Information Technology'),
    ('Electronics',           'Electronics'),
    ('Mechanical',            'Mechanical'),
    ('Civil',                 'Civil'),
    ('Electrical',            'Electrical'),
]

GRAD_YEAR_CHOICES = [(str(y), str(y)) for y in range(2020, 2031)]
GRAD_YEAR_CHOICES.insert(0, ('', 'Select Year'))


class ProfileForm(FlaskForm):
    """
    Academic profile — updates the students table.
    branch, cgpa, graduation_year, phone, linkedin_url, github_url
    are the fields a student can self-edit.
    full_name and roll_number are immutable after registration.
    """
    full_name       = StringField('Full Name',
                        validators=[DataRequired(), Length(max=150)])
    phone           = StringField('Phone',
                        validators=[Optional(), Length(max=20)])
    cgpa            = FloatField('CGPA',
                        validators=[Optional(), NumberRange(min=0.0, max=10.0,
                        message='CGPA must be between 0.0 and 10.0')])
    graduation_year = SelectField('Graduation Year',
                        choices=GRAD_YEAR_CHOICES, validators=[Optional()])
    branch          = SelectField('Branch',
                        choices=BRANCH_CHOICES, validators=[DataRequired()])
    linkedin_url    = URLField('LinkedIn URL',
                        validators=[Optional(), URL(message='Enter a valid URL'),
                        Length(max=255)])
    github_url      = URLField('GitHub URL',
                        validators=[Optional(), URL(message='Enter a valid URL'),
                        Length(max=255)])
    # Phase 14: ML test scores (optional, 0–100)
    aptitude_score      = IntegerField('Aptitude Score (0–100)',
                            validators=[Optional(), NumberRange(min=0, max=100,
                            message='Score must be between 0 and 100')])
    communication_score = IntegerField('Communication Score (0–100)',
                            validators=[Optional(), NumberRange(min=0, max=100,
                            message='Score must be between 0 and 100')])


class AddSkillForm(FlaskForm):
    """
    Add a skill to the student's profile.
    skill_id comes from the master skills table (searchable dropdown).
    """
    skill_id    = HiddenField('Skill ID', validators=[DataRequired()])
    skill_name  = StringField('Skill', validators=[DataRequired()])   # for display
    proficiency = SelectField('Proficiency', choices=PROFICIENCY_CHOICES,
                              validators=[DataRequired()])


class CertificationForm(FlaskForm):
    """Form for adding/editing a student certification."""
    title          = StringField('Certification Title',
                        validators=[DataRequired(), Length(max=255)])
    issuing_org    = StringField('Issuing Organization',
                        validators=[Optional(), Length(max=255)])
    issue_date     = DateField('Issue Date', validators=[Optional()])
    expiry_date    = DateField('Expiry Date', validators=[Optional()])
    credential_url = URLField('Credential URL',
                        validators=[Optional(), URL(), Length(max=500)])

    def validate_expiry_date(self, field):
        """Expiry must be after issue date."""
        if field.data and self.issue_date.data:
            if field.data < self.issue_date.data:
                raise ValidationError('Expiry date must be after issue date.')


class ProjectForm(FlaskForm):
    """Form for adding/editing a student project."""
    title       = StringField('Project Title',
                    validators=[DataRequired(), Length(max=255)])
    description = TextAreaField('Description',
                    validators=[Optional(), Length(max=2000)])
    tech_stack  = StringField('Tech Stack (comma separated)',
                    validators=[Optional(), Length(max=500)])
    project_url = URLField('Project URL',
                    validators=[Optional(), URL(), Length(max=500)])
    start_date  = DateField('Start Date', validators=[Optional()])
    end_date    = DateField('End Date', validators=[Optional()])


class InternshipForm(FlaskForm):
    """Form for adding/editing a student internship."""
    company_name = StringField('Company Name',
                    validators=[DataRequired(), Length(max=255)])
    role_title   = StringField('Role / Designation',
                    validators=[DataRequired(), Length(max=255)])
    description  = TextAreaField('Description',
                    validators=[Optional(), Length(max=2000)])
    start_date   = DateField('Start Date', validators=[Optional()])
    end_date     = DateField('End Date', validators=[Optional()])


# ── Admin forms ───────────────────────────────────────────────────────────────

class SkillForm(FlaskForm):
    """Admin form: add or edit a master skill."""
    name        = StringField('Skill Name',
                    validators=[DataRequired(), Length(max=100)])
    category    = SelectField('Category', choices=[
        ('', 'Select Category'),
        ('Programming',  'Programming'),
        ('Data & Analytics', 'Data & Analytics'),
        ('Web',          'Web'),
        ('Database',     'Database'),
        ('Cloud/DevOps', 'Cloud/DevOps'),
        ('AI/ML',        'AI/ML'),
        ('Tools',        'Tools'),
        ('Soft Skills',  'Soft Skills'),
    ], validators=[DataRequired()])
    description = TextAreaField('Description', validators=[Optional(), Length(max=500)])


class AliasForm(FlaskForm):
    """Admin form: add an alias for a skill."""
    alias_name = StringField('Alias', validators=[DataRequired(), Length(max=150)])
    skill_id   = HiddenField('Skill ID', validators=[DataRequired()])
