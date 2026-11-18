"""
app.py — Application Factory
──────────────────────────────
Full create_app() with:
  - Config loading
  - Extensions init (db, login_manager, csrf, migrate)
  - Blueprint registration (auth, student, admin, api)
  - Error handlers (404, 500, 413, 429)
  - Context processors (current_year, app_name)
  - Logging setup
  - /health endpoint
"""

import os
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, jsonify, render_template
from dotenv import load_dotenv

load_dotenv()

from config import config
from extensions import db, login_manager, csrf, migrate


def create_app(config_name: str = None) -> Flask:
    """
    Application Factory.
    Creates a new Flask app instance with the given config.
    """
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')

    app = Flask(__name__)

    # ── Load Config ─────────────────────────────────────────────
    config_obj = config.get(config_name, config['default'])()
    app.config.from_object(config_obj)
    if hasattr(config_obj, 'SQLALCHEMY_DATABASE_URI'):
        app.config['SQLALCHEMY_DATABASE_URI'] = config_obj.SQLALCHEMY_DATABASE_URI
    if hasattr(config_obj, 'SQLALCHEMY_ENGINE_OPTIONS') and config_obj.SQLALCHEMY_ENGINE_OPTIONS:
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = config_obj.SQLALCHEMY_ENGINE_OPTIONS

    # ── ProxyFix Support (behind reverse proxy with HTTPS) ────────
    behind_proxy = os.environ.get('BEHIND_PROXY', '').lower() in ('true', '1', 'yes')
    if behind_proxy:
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    # ── Init Extensions ──────────────────────────────────────────
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    migrate.init_app(app, db)

    # ── Upload Folder ────────────────────────────────────────────
    upload_folder = app.config.get('UPLOAD_FOLDER')
    if upload_folder:
        try:
            os.makedirs(upload_folder, exist_ok=True)
        except (OSError, PermissionError) as e:
            app.logger.warning(f"Could not create upload folder {upload_folder}: {e}")

    # ── Flask-Login User Loader ──────────────────────────────────
    from models.user import User

    @login_manager.user_loader
    def load_user(user_id: str):
        try:
            user = db.session.get(User, int(user_id))
            if user:
                _ = user.is_active
            return user
        except Exception:
            return None

    # ── Register Blueprints ──────────────────────────────────────
    from routes.auth import auth_bp
    from routes.student import student_bp
    from routes.admin import admin_bp
    from routes.api import api_bp
    from routes.forum import forum_bp

    app.register_blueprint(auth_bp)                       # /login, /register, /logout
    app.register_blueprint(student_bp, url_prefix='/student')  # /student/dashboard, etc.
    app.register_blueprint(admin_bp,   url_prefix='/admin')    # /admin/dashboard, etc.
    app.register_blueprint(api_bp,     url_prefix='/api')      # /api/...
    app.register_blueprint(forum_bp,   url_prefix='/forum')    # /forum/...

    # ── Download Project ZIP Route ───────────────────────────────
    from flask import send_file

    @app.route('/download-zip')
    def download_zip():
        for fname in ['skill_gap_system_complete.zip', 'skill_gap_system_phase16.zip', 'skill_gap_system_phase15.zip', 'skill_gap_system_phase14.zip', 'skill_gap_system_phase11.zip', 'skill_gap_system_phase9.zip', 'skill_gap_system_phase8.zip', 'skill_gap_system_phase3.zip']:
            zip_path = os.path.join(app.root_path, fname)
            if os.path.exists(zip_path):
                return send_file(zip_path, as_attachment=True, download_name=fname)
        return "Zip file not found", 404

    # ── Context Processors ───────────────────────────────────────
    # Variables automatically available in ALL templates
    from datetime import datetime

    @app.context_processor
    def inject_globals():
        return {
            'current_year': datetime.utcnow().year,
            'app_name': 'Skill Gap System',
            'forum_enabled': app.config.get('FORUM_ENABLED', True),
        }

    # ── Security Headers ─────────────────────────────────────────
    @app.after_request
    def set_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
            "font-src 'self' https://cdn.jsdelivr.net https://fonts.gstatic.com; "
            "img-src 'self' data:; "
            "connect-src 'self';"
        )
        return response

    # ── Error Handlers ────────────────────────────────────────────
    @app.errorhandler(404)
    def not_found(e):
        # Return JSON for API requests, HTML for browser requests
        from flask import request
        if request.path.startswith('/api/'):
            return jsonify({"success": False, "error": "Resource not found"}), 404
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def server_error(e):
        from flask import request
        db.session.rollback()
        app.logger.error(f"Server error: {e}", exc_info=True)
        if request.path.startswith('/api/'):
            return jsonify({"success": False, "error": "Internal server error"}), 500
        return render_template('errors/500.html'), 500

    @app.errorhandler(413)
    def file_too_large(e):
        from flask import request
        max_mb = app.config.get('MAX_UPLOAD_MB', 16)
        if request.path.startswith('/api/'):
            return jsonify({"success": False, "error": f"File too large. Max {max_mb}MB allowed."}), 413
        return render_template('errors/413.html', max_mb=max_mb), 413

    @app.errorhandler(403)
    def forbidden(e):
        from flask import request
        if request.path.startswith('/api/'):
            return jsonify({"success": False, "error": "Access forbidden"}), 403
        return render_template('errors/403.html'), 403

    # ── Health Checks ─────────────────────────────────────────────
    @app.route('/health')
    def health_check():
        return jsonify({
            "status": "ok",
            "app": "Skill Gap & Employment Outcome Tracking System"
        }), 200

    @app.route('/health/db')
    def health_db_check():
        try:
            from sqlalchemy import text
            db.session.execute(text('SELECT 1'))
            return jsonify({
                "status": "ok",
                "database": "connected"
            }), 200
        except Exception as e:
            app.logger.error(f"Health DB check failed: {e}")
            return jsonify({
                "status": "error",
                "database": "disconnected",
                "error": str(e)
            }), 503

    # ── CLI Commands ─────────────────────────────────────────────
    @app.cli.command('create-admin')
    def cli_create_admin():
        """Create admin from ADMIN_EMAIL and ADMIN_PASSWORD environment variables."""
        admin_email = os.environ.get('ADMIN_EMAIL')
        admin_password = os.environ.get('ADMIN_PASSWORD')
        if not admin_email or not admin_password:
            print("Error: ADMIN_EMAIL and ADMIN_PASSWORD environment variables must be set.")
            return
        from models.user import User
        if User.query.filter_by(email=admin_email).first():
            print(f"Admin '{admin_email}' already exists.")
            return
        admin_user = User(email=admin_email, role='admin', is_active=True)
        admin_user.set_password(admin_password)
        db.session.add(admin_user)
        db.session.commit()
        print(f"Admin '{admin_email}' created.")

    # ── Logging Setup ─────────────────────────────────────────────
    _setup_logging(app)

    return app


def _setup_logging(app: Flask) -> None:
    """
    Configure application logging.
    Rotates logs to logs/skill_gap.log if directory is writable;
    falls back cleanly to console StreamHandler on read-only environments.
    """
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG if app.debug else logging.INFO)
    console_handler.setFormatter(logging.Formatter(
        '[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
    ))
    app.logger.addHandler(console_handler)

    try:
        if not os.path.exists('logs'):
            os.makedirs('logs', exist_ok=True)

        file_handler = RotatingFileHandler(
            'logs/skill_gap.log',
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding='utf-8'
        )
        file_handler.setFormatter(logging.Formatter(
            '[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
        ))
        file_handler.setLevel(logging.WARNING)
        app.logger.addHandler(file_handler)
    except (OSError, PermissionError) as e:
        app.logger.warning(f"Could not initialize file logging ({e}); falling back to console logging.")

    app.logger.setLevel(logging.DEBUG if app.debug else logging.INFO)


# ── Module-level app instance (for `flask --app app run`) ────────────
app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='127.0.0.1', port=port, debug=True)
