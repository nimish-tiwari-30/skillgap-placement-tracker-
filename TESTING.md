# Testing Guide — Skill Gap System

## 1. Running Tests

### Run all tests
```bash
.\venv\Scripts\pytest.exe -v
```

### Run a specific test file
```bash
.\venv\Scripts\pytest.exe tests/test_security.py -v
```

### Run tests in reverse order (order-independence check)
```bash
.\venv\Scripts\pytest.exe tests/test_skill_gap.py tests/test_security.py tests/test_integration_flow.py tests/test_auth.py -v
```

## 2. Test Database Setup
- Tests run against an isolated **in-memory SQLite database** (`sqlite:///:memory:`).
- Configured via `TestingConfig` in `config.py`.
- No live MySQL development or production data is ever touched or modified.
- Tables are created per session and cleaned between tests via `clean_db` fixture in `tests/conftest.py`.

## 3. Test File Coverage
- `tests/test_auth.py`: Authentication lifecycle, login, registration, and logout.
- `tests/test_profile.py`: Profile CRUD, academic details, and portfolio items.
- `tests/test_resume.py`: Resume uploads, magic byte validation, and storage.
- `tests/test_skill_extractor.py`: NLP skill extraction and alias matching.
- `tests/test_jobs.py`: Admin job roles, job descriptions, and skill requirements.
- `tests/test_skill_gap.py`: Unweighted and weighted skill gap analysis computation.
- `tests/test_job_matcher.py`: TF-IDF vectorization and cosine similarity calculation.
- `tests/test_job_match_routes.py`: Job match browsing and student job matching views.
- `tests/test_phase10_courses.py`: Course catalog management and recommendation engine.
- `tests/test_learning_path.py`: Dynamic learning path generation and progress tracking.
- `tests/test_employment.py`: Employment outcome recording and student/admin views.
- `tests/test_analytics.py`: Pandas dashboard KPI calculations and branch/role summaries.
- `tests/test_ml.py`: Random Forest model training, evaluation metrics, and prediction.
- `tests/test_route_access.py`: Full URL route authorization audit across 4 caller types & CSRF.
- `tests/test_security.py`: Security checklist automated tests (SQLi, XSS, uploads, cookies, CSP).
- `tests/test_database.py`: CRUD, FK constraints, ON DELETE cascades, and schema-vs-model sync.
- `tests/test_integration_flow.py`: Full end-to-end 15-step student-to-admin lifecycle test.
