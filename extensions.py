"""
extensions.py
─────────────
Central place to instantiate all Flask extensions.
Imported into create_app() in app.py to avoid circular imports.

Why separate file?
If we define db = SQLAlchemy() inside app.py and models also import from app.py,
we get circular import errors. Defining them here breaks that cycle.
"""

from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_migrate import Migrate

# SQLAlchemy ORM instance — all models will use this `db` object
db = SQLAlchemy()

# Flask-Login manager — handles user session tracking
login_manager = LoginManager()
login_manager.login_view = 'auth.login'           # Redirect to login page if not authenticated
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'warning'

# CSRF protection for all WTForms
csrf = CSRFProtect()

# Database migration manager (Alembic wrapper)
migrate = Migrate()
