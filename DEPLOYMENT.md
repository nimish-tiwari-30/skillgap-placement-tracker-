# Deployment Guide: Skill Gap & Employment Outcome Tracking System

## 1. Environment Variables Reference

| Variable | Example Value | Required? | Description / Security Note |
|---|---|---|---|
| `FLASK_ENV` | `production` | Required | Set to `production` (enforces strict security, disables debug). |
| `SECRET_KEY` | `rand-hex-64-char-string` | Required | Cryptographic secret for cookies/CSRF. **Never commit to repo.** |
| `DATABASE_URL` | `mysql+pymysql://u:p@host:3306/db` | Recommended | Single MySQL connection string. Overrides individual `DB_*` vars. |
| `DB_USER` / `DB_HOST` | `admin` / `mysql.provider.com` | Optional | Used if `DATABASE_URL` is omitted. |
| `DB_PASSWORD` / `DB_NAME` | `SecretPass123` / `skillgap_prod` | Optional | Passwords with special characters are automatically URL-encoded. |
| `DB_SSL` | `true` | Optional | Set `true` to enable TLS encryption for cloud MySQL (Aiven, Render, RDS). |
| `BEHIND_PROXY` | `true` | Optional | Set `true` if hosted behind HTTPS reverse proxy (Render, Nginx, Cloudflare). |
| `ADMIN_EMAIL` | `admin@yourdomain.edu` | Optional | Initial production administrator email for `setup_db.py`. |
| `ADMIN_PASSWORD` | `StrongAdminPass#2026` | Optional | Initial admin password. Never commit. |
| `SEED_DEMO_USERS` | `false` | Optional | Defaults to `true`. Set `false` in production to omit demo student data. |
| `UPLOAD_FOLDER` | `static/uploads` | Optional | Base folder for uploaded resumes. Note: Ephemeral disks lose files on restart. |

---

## 2. Deploy to PythonAnywhere (Step-by-Step)

1. **Create Account & MySQL Database**:
   - In PythonAnywhere Dashboard -> **Databases**, create a MySQL database (e.g. `yourusername$skillgap`). Note password and host.
2. **Open Bash Console & Clone Repository**:
   ```bash
   git clone <your-repository-url> skillgap
   cd skillgap
   ```
3. **Setup Virtualenv & Dependencies**:
   ```bash
   mkvirtualenv --python=/usr/bin/python3.11 skillgap-env
   pip install --upgrade pip
   pip install -r requirements.txt
   ```
4. **Configure Environment & Initialize Database**:
   - Create `.env` in project root:
     ```bash
     FLASK_ENV=production
     SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
     DATABASE_URL=mysql+pymysql://yourusername:yourdbpass@yourusername.mysql.pythonanywhere-services.com/yourusername$skillgap
     ADMIN_EMAIL=admin@yourdomain.edu
     ADMIN_PASSWORD=YourSecurePassword123
     SEED_DEMO_USERS=false
     ```
   - Run database setup:
     ```bash
     python deploy/setup_db.py
     ```
5. **Configure Web Tab**:
   - Go to **Web** tab -> **Add a new web app** -> **Manual configuration** -> **Python 3.11**.
   - Set **Source code**: `/home/yourusername/skillgap`
   - Set **Working directory**: `/home/yourusername/skillgap`
   - Set **Virtualenv**: `/home/yourusername/.virtualenvs/skillgap-env`
   - In **WSGI configuration file**, replace everything with:
     ```python
     import os, sys
     from dotenv import load_dotenv
     project_home = '/home/yourusername/skillgap'
     if project_home not in sys.path:
         sys.path.insert(0, project_home)
     load_dotenv(os.path.join(project_home, '.env'))
     from wsgi import app as application
     ```
6. **Reload Web App**: Click the green **Reload** button at top of Web tab.

---

## 3. Deploy to Render (Web Service + External MySQL)

1. **Create External MySQL**: Provision MySQL on Aiven, PlanetScale, Supabase, or Render MySQL.
2. **New Web Service**: Connect your GitHub repository to Render.
3. **Service Settings**:
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt && python deploy/setup_db.py`
   - **Start Command**: `gunicorn --workers=2 --bind=0.0.0.0:$PORT --timeout=120 wsgi:app`
   - **Health Check Path**: `/health`
4. **Environment Variables**:
   - `FLASK_ENV`: `production`
   - `SECRET_KEY`: Generate a random 64-character hex string.
   - `DATABASE_URL`: `mysql+pymysql://user:pass@host:port/dbname`
   - `DB_SSL`: `true`
   - `BEHIND_PROXY`: `true`
   - `ADMIN_EMAIL` & `ADMIN_PASSWORD`: Your admin credentials.
   - `SEED_DEMO_USERS`: `false` (or `true` if demo showcase).

---

## 4. Post-Deployment Checklist & Troubleshooting

- [ ] Verify `/health` returns `200` (`{"status":"ok"}`).
- [ ] Verify `/health/db` returns `200` (`{"database":"connected"}`).
- [ ] Test admin login with `$ADMIN_EMAIL` and `$ADMIN_PASSWORD`.
- [ ] Test student registration, skill gap analysis, and course recommendation.

### Common Errors & Fixes
- **MySQL Connection Refused / 1045**: Check credentials, DB hostname, and ensure external IP access is allowed in cloud DB firewall.
- **SSL Handshake Error**: If connecting to AWS RDS / Aiven, set `DB_SSL=true`. If cloud provider requires specific CA cert, provide `DB_SSL_CA=/path/to/ca.pem`.
- **502 Bad Gateway / Timeout**: Gunicorn worker timed out. The `--timeout 120` in `Procfile` allows cold start and model evaluation.
- **CSRF / Session Lost over HTTPS**: Ensure `BEHIND_PROXY=true` is set so Werkzeug recognizes HTTPS and allows secure session cookies.
- **Static Files 404**: In PythonAnywhere, map `/static/` to `/home/yourusername/skillgap/static/` in the Web tab Static Files section.
- **spaCy Model Missing**: Runtime skill extraction uses the built-in dictionary/regex engine and does not depend on spaCy.

