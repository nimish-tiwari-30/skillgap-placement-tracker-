# Security Checklist & Audit Report

## 1. Security Controls Verification Matrix

| Security Control | Implementation (File / Function) | Test Verification (Test Name) | Status |
| :--- | :--- | :--- | :--- |
| **Password Hashing** | `models/user.py` (`User.set_password`, `User.check_password` via PBKDF2:SHA256) | `tests/test_security.py::test_passwords_hashed_and_never_logged` | **PASS** |
| **CSRF Protection** | `extensions.py` (`CSRFProtect(app)`), templates include `csrf_token()` | `tests/test_route_access.py::test_csrf_protection_on_all_post_routes` | **PASS** |
| **Role-Based Access (RBAC)** | `utils/decorators.py` (`@student_required`, `@admin_required`) | `tests/test_route_access.py::test_student_blocked_from_admin_routes`, `test_admin_blocked_from_student_routes` | **PASS** |
| **Ownership Checks** | `services/employment_service.py` (`check_student_access`), `routes/student.py` (`_get_student`) | `tests/test_route_access.py::test_student_cross_tenant_isolation`, `tests/test_employment.py::test_ownership_enforcement` | **PASS** |
| **Input Validation** | `forms/profile_forms.py`, `services/employment_service.py` (`validate_outcome_data`) | `tests/test_employment.py::test_outcome_validation_logic`, `tests/test_auth.py::test_register_password_mismatch` | **PASS** |
| **File Upload Validation** | `services/resume_service.py` (`process_resume_upload`, `validate_resume_bytes`, UUID storage) | `tests/test_security.py::test_upload_validation_security`, `tests/test_resume.py` | **PASS** |
| **SQL Injection Protection** | SQLAlchemy ORM parameterized queries across all repositories and service layers | `tests/test_security.py::test_sql_injection_resilience` | **PASS** |
| **XSS Escaping** | Jinja2 auto-escaping on all templates, strict audit of `\|safe` filters | `tests/test_security.py::test_xss_prevention_on_rendered_pages`, `test_template_safe_filter_audit` | **PASS** |
| **Session Cookie Flags** | `config.py` (`SESSION_COOKIE_HTTPONLY=True`, `SESSION_COOKIE_SAMESITE='Lax'`, `ProductionConfig.SESSION_COOKIE_SECURE=True`) | `tests/test_security.py::test_session_cookie_settings_and_production_config` | **PASS** |
| **HTTP Security Headers** | `app.py` (`set_security_headers`: `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, CSP) | `tests/test_security.py::test_http_security_headers_present` | **PASS** |
| **Error Handling Leakage** | `app.py` (`@app.errorhandler(404)` JSON for API, `@app.errorhandler(500)` with `db.session.rollback()`) | `tests/test_security.py::test_error_handling_and_no_information_leakage` | **PASS** |
| **Secrets Hygiene** | `config.py` (env-based config), `.gitignore` excludes `.env`, placeholder `.env.example` | `tests/test_security.py::test_secrets_hygiene`, `test_session_cookie_settings_and_production_config` | **PASS** |
| **CSV Formula Injection** | `services/employment_service.py` (`_sanitize_csv_cell`), `services/analytics_service.py` (`_sanitize_csv_cell`) | `tests/test_security.py::test_csv_injection_neutralization` | **PASS** |
| **Login Throttling** | `services/auth_service.py` (`_is_rate_limited`, `_record_failed_attempt`, 5-failure 5-minute lockout) | `tests/test_security.py::test_login_brute_force_throttling` | **PASS** |

---

## 2. Open Redirect Mitigation
- **Implementation**: `routes/auth.py` (`_is_safe_url` using `urllib.parse.urlsplit`).
- **Rejected Targets**: Protocol-relative URLs (`//evil.com`), external URLs (`https://evil.com`), backslash bypass attempts (`/\evil.com`).
- **Verified in**: `tests/test_security.py::test_open_redirect_rejected`.

---

## 3. Known Limitations (Honest Assessment)
1. **Local Demo HTTPS**: In local development (`FLASK_ENV=development`), HTTP is used (`http://127.0.0.1:5000`). `SESSION_COOKIE_SECURE` is enforced only when running under `ProductionConfig`.
2. **In-Memory Login Throttling (Multi-Worker Note)**: The failed login tracking (`_FAILED_LOGINS` in `auth_service.py`) is held in-process memory. Under multi-worker WSGI servers (such as Gunicorn with 2+ workers) or distributed cloud containers, each process maintains its own independent failure counters. For large-scale production deployments with high traffic, a shared Redis instance or Flask-Limiter with Redis backend is recommended.
3. **Email Verification**: User registration does not require clicking an email verification link before login.
4. **Password Reset Flow**: There is no self-service "Forgot Password" or tokenized email reset mechanism.
5. **Malware Scanning**: File uploads are verified for extension, size, and document magic bytes (PDF/DOCX structure), but binary contents are not scanned with an anti-virus or sandboxing engine (e.g., ClamAV).
