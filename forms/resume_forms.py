"""
forms/resume_forms.py
──────────────────────
WTForms form for student resume uploads.
Validates file extension (PDF, DOCX) and presence.
"""

from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired, FileAllowed


class ResumeUploadForm(FlaskForm):
    """Form for student resume file upload."""
    resume = FileField(
        'Resume Document',
        validators=[
            FileRequired(message='Please select a resume file (PDF or DOCX).'),
            FileAllowed(['pdf', 'docx'], message='Invalid file type. Only PDF (.pdf) and Word (.docx) files are supported.')
        ]
    )
