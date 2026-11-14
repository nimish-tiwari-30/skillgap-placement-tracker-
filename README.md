# Skill Gap & Employment Outcome Tracking System

> **Note**: This system uses synthetic/demo data for initial seed loading and machine learning dataset training. All statistics presented on initial setup reflect demo benchmarks.

## 📌 Overview
The **Skill Gap & Employment Outcome Tracking System** is a full-stack Flask application designed to compare student skills against target job roles, quantify skill gaps, provide course recommendations, track learning progress, and predict placement outcomes using machine learning.

---

## 🛠 Tech Stack
- **Frontend**: HTML5, CSS3, JavaScript, Bootstrap 5, Chart.js
- **Backend**: Python 3.10+, Flask, Flask-SQLAlchemy, Flask-Login, Flask-WTF, Werkzeug
- **Database**: MySQL 8.0, PyMySQL driver
- **Data & ML**: Pandas, NumPy, scikit-learn, joblib, spaCy (`en_core_web_sm`), pdfplumber, python-docx
- **Testing**: pytest

---

## 🚀 Setup Instructions (Windows)

### 1. Clone & Navigate to Project Directory
```powershell
cd "C:\Users\Nimish Tiwari\.gemini\antigravity-ide\scratch\major_one\skill_gap_system"
```

### 2. Create & Activate Virtual Environment
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### 3. Install Dependencies & spaCy NLP Model
```powershell
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

### 4. Configure Environment Variables
Copy `.env.example` to `.env` and fill in your MySQL credentials:
```env
SECRET_KEY=your_secure_secret_key
FLASK_ENV=development
FLASK_DEBUG=1
DB_USER=root
DB_PASSWORD=your_mysql_password
DB_HOST=localhost
DB_PORT=3306
DB_NAME=skill_gap_system
MAX_UPLOAD_MB=16
UPLOAD_FOLDER=static/uploads
```

### 5. Verify Environment Setup
```powershell
python verify_setup.py
```

### 6. Run Minimal Health Server
```powershell
python app.py
```
Visit `http://127.0.0.1:5000/health` in your browser.

---

## 📁 Project Structure
```text
skill_gap_system/
├── app.py              # Flask app factory
├── config.py           # Multi-environment configuration
├── verify_setup.py     # Environment check script
├── requirements.txt    # Pinned dependency manifest
├── .env                # Local secrets (git-ignored)
├── models/             # SQLAlchemy ORM Models
├── routes/             # Flask Blueprints & Controllers
├── services/           # Business logic & services
├── utils/              # Helper utilities & decorators
├── ml/                 # Resume parsing, skill extraction, ML models
├── templates/          # Jinja2 HTML templates
└── static/             # Static CSS, JS, and uploads
```
