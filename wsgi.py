"""
wsgi.py — Production WSGI Entrypoint
────────────────────────────────────
Exposes the WSGI application callable `app` for production servers
such as Gunicorn, uWSGI, PythonAnywhere, Render, or Railway.

Usage (Linux/Production):
    gunicorn --workers=2 --bind=0.0.0.0:$PORT --timeout=120 wsgi:app
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file if present
load_dotenv()

from app import create_app

# Default to 'production' if FLASK_ENV is not explicitly set
env_name = os.environ.get('FLASK_ENV', 'production')
app = create_app(env_name)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

