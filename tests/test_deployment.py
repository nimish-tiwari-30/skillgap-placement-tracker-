"""
tests/test_deployment.py
─────────────────────────
Tests for deployment readiness and production configurations:
1. ProductionConfig refuses to start without SECRET_KEY or with placeholder.
2. DATABASE_URL overrides DB_* variables and handles special characters in credentials.
3. DB_SSL flag configures SQLALCHEMY_ENGINE_OPTIONS.
4. BEHIND_PROXY flag applies Werkzeug ProxyFix.
5. /health and /health/db endpoints return 200.
6. Missing model file returns friendly error message without crashing.
7. deploy/setup_db.py runs twice idempotently and creates admin only from env vars.
"""

import os
import pytest
from unittest.mock import patch
from werkzeug.middleware.proxy_fix import ProxyFix
from sqlalchemy.engine import make_url

from config import Config, ProductionConfig
from app import create_app
from extensions import db
from models.user import User
from models.student import Student
from ml import employment_model
from deploy.setup_db import setup_database, create_admin_user


def test_production_config_refuses_without_secret_key(monkeypatch):
    """Test that ProductionConfig strictly rejects missing or placeholder SECRET_KEY."""
    monkeypatch.delenv('SECRET_KEY', raising=False)
    with pytest.raises(ValueError) as excinfo:
        create_app('production')
    assert "SECRET_KEY" in str(excinfo.value)

    # Test with known placeholder secrets
    for placeholder in ['change_me', 'secret', 'dev_secret_key', 'default_fallback_secret_key_12345']:
        monkeypatch.setenv('SECRET_KEY', placeholder)
        with pytest.raises(ValueError) as exc:
            create_app('production')
        assert "SECRET_KEY" in str(exc.value)


def test_production_config_starts_with_valid_secret(monkeypatch):
    """Test that ProductionConfig succeeds with secure SECRET_KEY and sets secure flags."""
    monkeypatch.setenv('SECRET_KEY', 'secure_production_secret_key_random_string_987654')
    prod_app = create_app('production')
    assert prod_app.debug is False
    assert prod_app.config['SESSION_COOKIE_SECURE'] is True
    assert prod_app.config['SESSION_COOKIE_HTTPONLY'] is True
    assert prod_app.config['SESSION_COOKIE_SAMESITE'] == 'Lax'


def test_database_url_overrides_db_vars_and_handles_special_characters(monkeypatch):
    """Test that DATABASE_URL takes priority over DB_* and correctly percent-encodes passwords with special chars."""
    monkeypatch.setenv('DB_USER', 'fallback_user')
    monkeypatch.setenv('DB_HOST', 'fallback_host')
    
    # URL with special characters: '@', '#', '!'
    raw_url = "mysql://cloud_user:p@ss#word!@db.cloud.internal:3306/production_db"
    monkeypatch.setenv('DATABASE_URL', raw_url)

    uri = Config.build_db_uri('ignored_db')
    assert uri.startswith('mysql+pymysql://')

    parsed = make_url(uri)
    assert parsed.drivername == 'mysql+pymysql'
    assert parsed.username == 'cloud_user'
    assert parsed.password == 'p@ss#word!'
    assert parsed.host == 'db.cloud.internal'
    assert parsed.database == 'production_db'


def test_db_ssl_engine_options(monkeypatch):
    """Test that DB_SSL=true configures connect_args['ssl'] in Config."""
    monkeypatch.setenv('DB_SSL', 'true')
    cfg = Config()
    opts = cfg.SQLALCHEMY_ENGINE_OPTIONS
    assert 'connect_args' in opts
    assert 'ssl' in opts['connect_args']
    assert opts['connect_args']['ssl']['check_hostname'] is False

    # Also test with DB_SSL_CA
    monkeypatch.setenv('DB_SSL_CA', '/path/to/ca.pem')
    opts_ca = Config().SQLALCHEMY_ENGINE_OPTIONS
    assert opts_ca['connect_args']['ssl']['ca'] == '/path/to/ca.pem'


def test_behind_proxy_applies_proxy_fix(monkeypatch):
    """Test that BEHIND_PROXY=true wraps wsgi_app with ProxyFix."""
    monkeypatch.setenv('BEHIND_PROXY', 'true')
    monkeypatch.setenv('SECRET_KEY', 'valid-test-key-abcdef-123456')
    prod_app = create_app('production')
    assert isinstance(prod_app.wsgi_app, ProxyFix)


def test_health_endpoints(client):
    """Test /health and /health/db endpoints return 200 with proper payload."""
    res_health = client.get('/health')
    assert res_health.status_code == 200
    assert res_health.json['status'] == 'ok'

    res_db = client.get('/health/db')
    assert res_db.status_code == 200
    assert res_db.json['status'] == 'ok'
    assert res_db.json['database'] == 'connected'


def test_missing_model_file_gives_friendly_message(app, monkeypatch):
    """Test that a missing ML model file does not crash and returns a user-friendly error message."""
    with app.app_context():
        # Mock bundle loading to simulate missing model
        monkeypatch.setattr(employment_model, '_load_bundle', lambda: None)
        monkeypatch.setattr(employment_model, 'ensure_model_trained', lambda: None)

        test_student = Student(user_id=999, full_name="Test Student", roll_number="TEST001", branch="CSE")
        pred = employment_model.predict_student(test_student)

        assert pred['success'] is False
        assert pred['label'] is None
        assert "Model not available" in pred['error']


def test_setup_db_idempotency_and_admin_creation(app, monkeypatch):
    """Test that deploy/setup_db.py runs twice idempotently and handles admin creation from environment variables."""
    # 1. Admin creation when env vars provided
    monkeypatch.setenv('ADMIN_EMAIL', 'prod_admin_test@skillgap.edu')
    monkeypatch.setenv('ADMIN_PASSWORD', 'SuperAdminSecret#2026')
    monkeypatch.setenv('SEED_DEMO_USERS', 'false')

    # Run pass 1
    setup_database(app)
    with app.app_context():
        admin = User.query.filter_by(email='prod_admin_test@skillgap.edu').first()
        assert admin is not None
        assert admin.role == 'admin'
        assert admin.check_password('SuperAdminSecret#2026')

    # Run pass 2 (must be idempotent — no DuplicateEntry or crash)
    setup_database(app)
    with app.app_context():
        admins = User.query.filter_by(email='prod_admin_test@skillgap.edu').all()
        assert len(admins) == 1

    # 2. When env vars missing, admin creation skips gracefully without creating users
    monkeypatch.delenv('ADMIN_EMAIL', raising=False)
    monkeypatch.delenv('ADMIN_PASSWORD', raising=False)
    with app.app_context():
        created = create_admin_user()
        assert created is False
