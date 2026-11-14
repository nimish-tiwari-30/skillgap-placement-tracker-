import os
import re
from urllib.parse import quote_plus, unquote

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    """Base Configuration Class"""
    SECRET_KEY = os.environ.get('SECRET_KEY', 'default_fallback_secret_key_12345')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Upload Configurations
    MAX_UPLOAD_MB = int(os.environ.get('MAX_UPLOAD_MB', 16))
    MAX_CONTENT_LENGTH = MAX_UPLOAD_MB * 1024 * 1024  # Enforces maximum upload payload in bytes
    _upload_folder_env = os.environ.get('UPLOAD_FOLDER', 'static/uploads')
    UPLOAD_FOLDER = _upload_folder_env if os.path.isabs(_upload_folder_env) else os.path.abspath(os.path.join(BASE_DIR, _upload_folder_env))
    ALLOWED_EXTENSIONS = {'pdf', 'docx'}
    
    # Security Cookie Settings
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

    @staticmethod
    def normalize_database_url(url: str) -> str:
        """
        Normalizes database URL to ensure mysql+pymysql driver and safely percent-encoded password.
        Supports standard mysql:// and mariadb:// prefixes and handles special characters in credentials.
        """
        if not url:
            return url
        url = url.strip()
        if url.startswith('mysql://'):
            url = 'mysql+pymysql://' + url[len('mysql://'):]
        elif url.startswith('mariadb://'):
            url = 'mysql+pymysql://' + url[len('mariadb://'):]

        # Handle passwords with special characters (e.g. '@', '#', ':', '?', '$')
        match = re.match(r'^([a-zA-Z0-9\+]+)://([^:]+):(.*)@([^/@]+)(/.*)?$', url)
        if match:
            scheme, user, raw_pass, host_part, rest = match.groups()
            decoded_pass = unquote(raw_pass)
            encoded_pass = quote_plus(decoded_pass)
            rest = rest or ''
            return f"{scheme}://{user}:{encoded_pass}@{host_part}{rest}"
        return url

    @staticmethod
    def build_db_uri(db_name: str) -> str:
        """
        Constructs safe SQLAlchemy URI.
        Prioritizes DATABASE_URL if set; otherwise builds from DB_* variables with URL-encoded password.
        """
        db_url = os.environ.get('DATABASE_URL')
        if db_url:
            return Config.normalize_database_url(db_url)
        user = os.environ.get('DB_USER', 'root')
        password = quote_plus(os.environ.get('DB_PASSWORD', ''))
        host = os.environ.get('DB_HOST', 'localhost')
        port = os.environ.get('DB_PORT', '3306')
        return f"mysql+pymysql://{user}:{password}@{host}:{port}/{db_name}"

    @property
    def SQLALCHEMY_ENGINE_OPTIONS(self):
        """Database engine options, including optional SSL support for cloud MySQL."""
        opts = {}
        if os.environ.get('DB_SSL', '').lower() in ('true', '1', 'yes'):
            ssl_args = {'check_hostname': False}
            ca_cert = os.environ.get('DB_SSL_CA')
            if ca_cert:
                ssl_args['ca'] = ca_cert
            opts['connect_args'] = {'ssl': ssl_args}
        return opts



class DevelopmentConfig(Config):
    """Development Environment Configuration"""
    DEBUG = True
    ENV = 'development'
    
    @property
    def SQLALCHEMY_DATABASE_URI(self):
        db_name = os.environ.get('DB_NAME', 'skill_gap_system')
        return Config.build_db_uri(db_name)


class TestingConfig(Config):
    """Testing Environment Configuration — uses SQLite in-memory, no MySQL needed."""
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SQLALCHEMY_ENGINE_OPTIONS = {}


class ProductionConfig(Config):
    """Production Environment Configuration"""
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SECRET_KEY = os.environ.get('SECRET_KEY', None)

    PLACEHOLDER_SECRETS = (
        'default_fallback_secret_key_12345',
        'dev_secret_key_change_in_production_12345',
        'dev_secret_key',
        'change_me',
        'secret',
        'your_secure_secret_key',
    )

    def __init__(self):
        super().__init__()
        secret = os.environ.get('SECRET_KEY')
        if not secret or secret.strip() in self.PLACEHOLDER_SECRETS:
            raise ValueError(
                "ProductionConfig requires a non-default SECRET_KEY environment variable. "
                "Set SECRET_KEY in your production environment before starting the application."
            )
        self.SECRET_KEY = secret
    
    @property
    def SQLALCHEMY_DATABASE_URI(self):
        db_name = os.environ.get('DB_NAME', 'skill_gap_system')
        return Config.build_db_uri(db_name)


config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
