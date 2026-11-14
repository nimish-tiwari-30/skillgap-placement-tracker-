import sys
import os
import importlib
import importlib.metadata
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def print_result(label, success, details=""):
    status_str = "[PASS]" if success else "[FAIL]"
    color = "\033[92m" if success else "\033[91m"
    reset = "\033[0m"
    print(f"{color}{status_str}{reset} {label} {details}")

def verify_all():
    print("==================================================")
    print(" SYSTEM ENVIRONMENT CHECK - PHASE 1 VERIFICATION")
    print("==================================================\n")

    overall_pass = True

    # 1. Python Version Check
    py_ver = sys.version_info
    py_pass = py_ver.major == 3 and py_ver.minor >= 10
    print_result(
        "Python Version:", 
        py_pass, 
        f"({py_ver.major}.{py_ver.minor}.{py_ver.micro})" + (" - Minimum 3.10 required" if not py_pass else "")
    )
    if not py_pass: overall_pass = False

    # 2. Package Import Checks
    # tuple format: (module_import_name, pip_distribution_name)
    packages = [
        ("flask", "Flask"),
        ("flask_sqlalchemy", "Flask-SQLAlchemy"),
        ("flask_login", "Flask-Login"),
        ("flask_wtf", "Flask-WTF"),
        ("flask_migrate", "Flask-Migrate"),
        ("sqlalchemy", "SQLAlchemy"),
        ("pymysql", "PyMySQL"),
        ("cryptography", "cryptography"),
        ("dotenv", "python-dotenv"),
        ("werkzeug", "Werkzeug"),
        ("pandas", "pandas"),
        ("numpy", "numpy"),
        ("sklearn", "scikit-learn"),
        ("joblib", "joblib"),
        ("spacy", "spacy"),
        ("pdfplumber", "pdfplumber"),
        ("docx", "python-docx"),
        ("pytest", "pytest")
    ]
    
    print("\n--- Package Dependencies Check ---")
    for mod_name, dist_name in packages:
        try:
            importlib.import_module(mod_name)
            try:
                ver = importlib.metadata.version(dist_name)
            except Exception:
                ver = "Installed"
            print_result(f"Package '{dist_name}':", True, f"({ver})")
        except ImportError as e:
            print_result(f"Package '{dist_name}':", False, f"Missing. Install via: pip install -r requirements.txt")
            overall_pass = False

    # 3. spaCy Model Check (Optional: SkillExtractor uses built-in dictionary regex engine)
    print("\n--- spaCy NLP Model Check ---")
    try:
        import spacy
        try:
            nlp = spacy.load("en_core_web_sm")
            print_result("spaCy 'en_core_web_sm':", True, f"Model loaded successfully ({nlp.meta['name']})")
        except Exception:
            print_result("spaCy 'en_core_web_sm':", True, "Not installed (Optional — SkillExtractor uses fast regex dictionary matcher)")
    except ImportError:
        print_result("spaCy package:", True, "Not installed (Optional — SkillExtractor uses fast regex dictionary matcher)")

    # 4. Environment Variables Check
    print("\n--- Environment Configuration Check (.env) ---")
    required_env_vars = ['SECRET_KEY', 'FLASK_ENV', 'DB_USER', 'DB_HOST', 'DB_PORT', 'DB_NAME', 'UPLOAD_FOLDER']
    missing_vars = [var for var in required_env_vars if not os.environ.get(var)]
    
    if not missing_vars:
        print_result(".env Configuration:", True, f"All required keys present ({', '.join(required_env_vars)})")
    else:
        print_result(".env Configuration:", False, f"Missing keys: {', '.join(missing_vars)}. Fix: Check your .env file")
        overall_pass = False

    # 5. MySQL Connection Check
    print("\n--- MySQL Connection Check ---")
    try:
        import pymysql
        db_user = os.environ.get('DB_USER', 'root')
        db_pass = os.environ.get('DB_PASSWORD', '')
        db_host = os.environ.get('DB_HOST', 'localhost')
        db_port = int(os.environ.get('DB_PORT', 3306))
        target_db = os.environ.get('DB_NAME', 'skill_gap_system')

        # Connect to MySQL Server directly (without selecting specific DB yet)
        conn = pymysql.connect(
            host=db_host,
            user=db_user,
            password=db_pass,
            port=db_port,
            connect_timeout=5
        )
        with conn.cursor() as cursor:
            cursor.execute("SHOW DATABASES;")
            databases = [row[0] for row in cursor.fetchall()]
            
        conn.close()

        db_exists = target_db in databases
        if db_exists:
            print_result("MySQL Server Connection:", True, f"Connected to server. Database '{target_db}' EXISTS.")
        else:
            print_result("MySQL Server Connection:", True, f"Connected to server. Database '{target_db}' NOT CREATED YET (Will be created in Phase 2).")

    except Exception as e:
        print_result("MySQL Server Connection:", False, f"Connection Notice: {e}. (Update DB_PASSWORD in .env if needed)")
        overall_pass = False

    # 6. Upload Directory Permissions Check
    print("\n--- Directory Permissions Check ---")
    upload_dir = os.path.abspath(os.environ.get('UPLOAD_FOLDER', 'static/uploads'))
    try:
        os.makedirs(upload_dir, exist_ok=True)
        test_file = os.path.join(upload_dir, '.write_test')
        with open(test_file, 'w') as f:
            f.write('test')
        os.remove(test_file)
        print_result("Upload Directory Writable:", True, f"({upload_dir})")
    except Exception as e:
        print_result("Upload Directory Writable:", False, f"Failed write test at {upload_dir}: {e}")
        overall_pass = False

    print("\n==================================================")
    if overall_pass:
        print(" VERIFICATION RESULT: ALL CHECKS PASSED SUCCESSFULLY! ")
    else:
        print(" VERIFICATION RESULT: SOME CHECKS NEED ATTENTION (SEE ABOVE). ")
    print("==================================================\n")

if __name__ == '__main__':
    verify_all()
