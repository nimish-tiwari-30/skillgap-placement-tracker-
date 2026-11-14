"""
routes/api.py
─────────────
JSON API Blueprint — all /api/* endpoints.
Phase 3: stubs returning consistent {"success": true/false} format.
Real logic added in Phases 10–19.

ALL endpoints:
  - Require authentication (enforced via @login_required)
  - Return consistent JSON: {"success": bool, "data": ..., "error": ...}
  - Students can only access their own data (ownership check added per phase)
"""

from flask import Blueprint, request
from flask_login import login_required, current_user
from extensions import db
from utils.helpers import api_success, api_error
from services import resume_service, gap_service, match_service
from models.student import Student
from models.skill import StudentSkill
from models.job import JobDescription

api_bp = Blueprint('api', __name__)


# ── Resume & Skill Extraction ─────────────────────────────────
@api_bp.route('/analyze-resume', methods=['POST'])
@login_required
def analyze_resume():
    """Extract skills from uploaded resume file or JSON text payload."""
    if current_user.is_student() and not current_user.student:
        return api_error("Student profile not found.", 404)

    file_obj = request.files.get('resume') or request.files.get('file')
    if file_obj:
        if not resume_service.allowed_file(file_obj.filename):
            return api_error("Unsupported file format. Please upload PDF or DOCX.", 400)
        ext = file_obj.filename.rsplit('.', 1)[1].lower()
        try:
            import io
            from ml.resume_parser import validate_resume_bytes, extract_text
            file_bytes = file_obj.read()
            valid, err = validate_resume_bytes(file_bytes, ext)
            if not valid:
                return api_error(err, 400)
            text = extract_text(io.BytesIO(file_bytes), ext)
        except Exception as e:
            return api_error(f"Failed to extract text: {str(e)}", 400)
    else:
        data = request.get_json(silent=True) or {}
        text = data.get('text', '')

    if not text or not text.strip():
        return api_error("No readable resume text or file provided.", 400)

    from ml.skill_extractor import extract_skills_from_text
    extracted = extract_skills_from_text(text)

    return api_success({
        'skills': [
            {'name': s.get('canonical_name') or s.get('name'), 'count': s.get('count', 1)}
            for s in extracted
        ],
        'text_length': len(text)
    })


@api_bp.route('/analyze-job', methods=['POST'])
@login_required
def analyze_job():
    """
    Phase 7: Extract skills from a job description text payload.
    Accepts JSON: {"description": "..."}
    Returns JSON: {"success": true, "data": {"skills": [{"name": "...", "count": N}]}}
    """
    payload = request.get_json(silent=True) or {}
    description = payload.get('description') or payload.get('text', '')

    if not description or not str(description).strip():
        return api_error("Job description text is required.", 400)

    from ml.skill_extractor import extract_skills_from_text
    extracted = extract_skills_from_text(str(description))

    skills_data = [
        {
            'name': s.get('canonical_name') or s.get('name'),
            'count': s.get('count', 1)
        }
        for s in extracted
    ]

    return api_success({'skills': skills_data})


# ── Skill Gap (Phase 8) ───────────────────────────────────────
@api_bp.route('/skill-gap', methods=['POST'])
@login_required
def skill_gap():
    """
    Phase 8: Compute skill gap analysis for the logged-in student against a target job.
    Accepts JSON: {"job_id": <int>}
    Returns JSON: {"success": true, "data": {"coverage": float, "weighted": float, "matched": [...], "missing": [...], "extra": [...]}}
    """
    if not current_user.is_student():
        return api_error("Only students can perform skill gap analysis.", 403)
    if not current_user.student:
        return api_error("Student profile not found.", 404)

    payload = request.get_json(silent=True) or {}
    job_id = payload.get('job_id')
    if not job_id:
        return api_error("job_id is required.", 400)

    try:
        job_id = int(job_id)
    except (ValueError, TypeError):
        return api_error("Invalid job_id. Must be an integer.", 400)

    job = db.session.get(JobDescription, job_id)
    if not job or not job.is_active:
        return api_error("Job description not found or is inactive.", 404)

    ok, res_or_err, details = gap_service.analyze(
        student_id=current_user.student.id,
        job_id=job.id,
        current_user=current_user
    )

    if not ok:
        return api_error(str(res_or_err), 400)

    return api_success({
        'analysis_id': res_or_err.id,
        'job_id': job.id,
        'job_title': job.title,
        'coverage': float(res_or_err.unweighted_coverage_pct or 0.0),
        'weighted': float(res_or_err.weighted_coverage_pct or 0.0),
        'matched': details.get('matched', []),
        'missing': details.get('missing', []),
        'extra': details.get('extra', []),
        'matched_count': details.get('matched_count', 0),
        'missing_count': details.get('missing_count', 0),
        'extra_count': details.get('extra_count', 0),
    })


@api_bp.route('/student/<int:student_id>/skill-gap/latest', methods=['GET'])
@login_required
def student_latest_skill_gap(student_id: int):
    """
    Phase 8: Get the latest skill gap analysis for a student.
    Enforces ownership: students can only access their own analysis; admins can view any.
    """
    if current_user.is_student():
        if not current_user.student or current_user.student.id != student_id:
            return api_error("Access denied. You can only view your own skill gap analysis.", 403)

    student = db.session.get(Student, student_id)
    if not student:
        return api_error("Student not found.", 404)

    job_id = request.args.get('job_id', type=int)
    latest = gap_service.get_latest_analysis(student_id, job_id=job_id, current_user=current_user)
    if not latest:
        return api_success(None, message="No skill gap analysis found for this student.")

    details = gap_service.format_analysis_details(latest)
    return api_success({
        'analysis_id': latest.id,
        'job_id': latest.job_description_id,
        'job_title': details['job_title'],
        'role_title': details['role_title'],
        'coverage': details['coverage_pct'],
        'weighted': details['weighted_pct'],
        'matched': details['matched'],
        'missing': details['missing'],
        'extra': details['extra'],
        'matched_count': details['matched_count'],
        'missing_count': details['missing_count'],
        'extra_count': details['extra_count'],
        'analyzed_at': details['analyzed_at'],
    })


# ── Student Skills ────────────────────────────────────────────
@api_bp.route('/student/<int:student_id>/skills', methods=['GET'])
@login_required
def student_skills(student_id: int):
    """Phase 6: Get a student's skills list."""
    if current_user.is_student():
        if not current_user.student or current_user.student.id != student_id:
            return api_error("Access denied. You can only view your own skills.", 403)

    student = db.session.get(Student, student_id)
    if not student:
        return api_error("Student not found.", 404)

    skills_data = [
        {
            'id': ss.id,
            'skill_id': ss.skill_id,
            'name': ss.skill.name,
            'category': ss.skill.category,
            'proficiency_level': ss.proficiency_level,
            'source': ss.source
        }
        for ss in student.skills
    ]
    return api_success(skills_data)



# ── Job Endpoints ─────────────────────────────────────────────
@api_bp.route('/jobs', methods=['GET'])
@login_required
def get_jobs():
    """
    Phase 7: List all active jobs with their required skills.
    Returns JSON list of jobs with title, company, role, and skills list with importance_weight.
    """
    from models.job import JobDescription

    jobs_list = JobDescription.query.filter_by(is_active=True).order_by(JobDescription.created_at.desc()).all()
    jobs_data = []

    for job in jobs_list:
        jobs_data.append({
            'id': job.id,
            'title': job.title,
            'company_name': job.company_name,
            'role': job.job_role.title if job.job_role else None,
            'location': job.location,
            'min_experience': job.min_experience,
            'skills': [
                {
                    'skill_id': js.skill_id,
                    'name': js.skill.name,
                    'importance_weight': js.importance_weight
                }
                for js in sorted(job.job_skills, key=lambda x: x.importance_weight, reverse=True)
            ]
        })

    return api_success(jobs_data)


# ── Job Matching (Phase 9) ────────────────────────────────────
@api_bp.route('/job/<int:job_id>/match', methods=['GET'])
@login_required
def job_match(job_id: int):
    """
    Phase 9: Compute TF-IDF Cosine Similarity match score and Skill Coverage
    for the logged-in student against a job description.
    Returns JSON: {"success": true, "data": {"job_id", "coverage", "weighted", "overall_match", "matched":[], "missing":[], "extra":[]}}
    """
    if not current_user.is_student():
        return api_error("Only students can view job match scores.", 403)
    if not current_user.student:
        return api_error("Student profile not found.", 404)

    ok, res_or_err = match_service.match_student_to_job(
        student_id=current_user.student.id,
        job_id=job_id,
        current_user=current_user
    )

    if not ok:
        # Check if job not found
        if "not found" in str(res_or_err).lower():
            return api_error(str(res_or_err), 404)
        return api_error(str(res_or_err), 400)

    data = res_or_err
    return api_success({
        'job_id': data['job_id'],
        'job_title': data['title'],
        'company_name': data['company_name'],
        'role_title': data['role_title'],
        'coverage': data['coverage_pct'],
        'weighted': data['weighted_pct'],
        'overall_match': data['overall_match_pct'],
        'matched': data['matched'],
        'missing': data['missing'],
        'extra': data['extra'],
        'matched_count': data['matched_count'],
        'missing_count': data['missing_count'],
        'extra_count': data['extra_count'],
    })


@api_bp.route('/student/<int:student_id>/job-matches', methods=['GET'])
@login_required
def student_job_matches(student_id: int):
    """
    Phase 9: List matches for all active jobs for a student.
    Enforces ownership: students can only access their own matches; admins can view any.
    """
    if current_user.is_student():
        if not current_user.student or current_user.student.id != student_id:
            return api_error("Access denied. You can only view your own job matches.", 403)

    student = db.session.get(Student, student_id)
    if not student:
        return api_error("Student not found.", 404)

    sort_by = request.args.get('sort_by', 'overall_match')
    role_id = request.args.get('role_id', type=int)
    search = request.args.get('q', '').strip()

    ok, res_or_err = match_service.match_student_to_all_jobs(
        student_id=student.id,
        current_user=current_user,
        search=search,
        role_id=role_id,
        sort_by=sort_by
    )

    if not ok:
        return api_error(str(res_or_err), 400)

    return api_success(res_or_err)


# ── Recommendations ───────────────────────────────────────────────────────────
@api_bp.route('/student/<int:student_id>/recommendations', methods=['GET'])
@login_required
def student_recommendations(student_id: int):
    """
    Phase 10: Return content-based course recommendations for a student's missing skills.

    Query param: job_id (required)
    Ownership: students see only own data; admins can see any.

    Response:
      {success: true, data: {job_id, job_title, items: [{skill, importance, courses:[...]}]}}
    """
    from services import recommendation_service

    # Ownership check: student can only access own recommendations
    if current_user.is_student():
        if not current_user.student or current_user.student.id != student_id:
            return api_error("Access denied. You can only view your own recommendations.", 403)

    student = db.session.get(Student, student_id)
    if not student:
        return api_error("Student not found.", 404)

    job_id = request.args.get('job_id', type=int)
    if not job_id:
        return api_error("job_id query parameter is required.", 400)

    # Validate job exists
    job = db.session.get(JobDescription, job_id)
    if not job or not job.is_active:
        return api_error("Job not found or inactive.", 404)

    ok, result = recommendation_service.recommend_for_job(
        student_id=student_id,
        job_id=job_id,
        current_user=current_user,
    )
    if not ok:
        return api_error(str(result), 400)

    # Shape response: only serializable fields
    items_out = []
    for item in result.get('items', []):
        courses_out = []
        for c in item.get('courses', []):
            courses_out.append({
                'course_id':      c['course_id'],
                'title':          c['title'],
                'provider':       c['provider'],
                'difficulty':     c['difficulty_level'],
                'duration_hours': c['duration_hours'],
                'rating':         c['rating'],
                'url':            c['url'],
                'covers_n_missing_skills': c['covers_n_missing_skills'],
            })
        items_out.append({
            'skill_id':   item['skill_id'],
            'skill_name': item['skill_name'],
            'importance': item['importance'],
            'has_courses': item['has_courses'],
            'courses':    courses_out,
        })

    return api_success({
        'job_id':       job_id,
        'job_title':    result.get('job_title', ''),
        'all_covered':  result.get('all_covered', False),
        'items':        items_out,
    })


# ── Learning Path (Phase 11) ──────────────────────────────────────────────────
@api_bp.route('/student/<int:student_id>/learning-path', methods=['GET'])
@login_required
def get_student_learning_path(student_id: int):
    """
    Phase 11: Return structured learning path and completion % for a student and target job.
    Query param: job_id (required).
    Ownership: students can access only their own path; admins can view any.
    """
    from services import learning_path_service
    from models.job import JobDescription

    # Ownership check
    if current_user.is_student():
        if not current_user.student or current_user.student.id != student_id:
            return api_error("Access denied. You can only view your own learning path.", 403)

    student = db.session.get(Student, student_id)
    if not student:
        return api_error("Student not found.", 404)

    job_id = request.args.get('job_id', type=int)
    if not job_id:
        return api_error("job_id query parameter is required.", 400)

    job = db.session.get(JobDescription, job_id)
    if not job or not job.is_active:
        return api_error("Job not found or inactive.", 404)

    # Fetch existing or auto-generate if empty
    path_data = learning_path_service.get_path(student_id, job_id, current_user=current_user)
    if path_data.get('total_items', 0) == 0:
        ok, _ = learning_path_service.generate_path(student_id, job_id, current_user=current_user)
        if ok:
            path_data = learning_path_service.get_path(student_id, job_id, current_user=current_user)

    return api_success({
        'job_id': job_id,
        'completion': path_data.get('completion_pct', 0.0),
        'steps': path_data.get('items', []),
    })


@api_bp.route('/learning-path/<int:item_id>/complete', methods=['POST'])
@login_required
def api_complete_learning_step(item_id: int):
    """
    Phase 11: Mark a learning step completed.
    Body: {"proficiency": 3} (optional, default 3).
    Returns updated completion %.
    """
    from services import learning_path_service
    from models.course import LearningPathItem

    item = db.session.get(LearningPathItem, item_id)
    if not item:
        return api_error("Learning path step not found.", 404)

    # Ownership check
    if current_user.is_student():
        if not current_user.student or current_user.student.id != item.student_id:
            return api_error("Access denied. You can only complete your own learning steps.", 403)

    body = request.get_json(silent=True) or {}
    proficiency = body.get('proficiency', 3)

    ok, res = learning_path_service.mark_complete(
        student_id=item.student_id,
        item_id=item_id,
        proficiency=proficiency,
        current_user=current_user,
    )
    if not ok:
        return api_error(str(res), 400)

    # Calculate updated completion for this job
    job_id = None
    if item.analysis and item.analysis.job_description_id:
        job_id = item.analysis.job_description_id
    elif item.student and item.student.target_job_id:
        job_id = item.student.target_job_id

    updated_completion = 0.0
    if job_id:
        path_data = learning_path_service.get_path(item.student_id, job_id, current_user=current_user)
        updated_completion = path_data.get('completion_pct', 0.0)

    return api_success({
        'item_id': item_id,
        'is_completed': True,
        'completion': updated_completion,
    })


# ── Employment Outcome Tracking (Phase 12) ────────────────────
@api_bp.route('/student/<int:student_id>/employment', methods=['GET'])
@login_required
def get_student_employment(student_id: int):
    """
    GET /api/student/<id>/employment
    Returns employment outcome record for a student.
    Own data only (admins permitted).
    """
    from services import employment_service

    student = db.session.get(Student, student_id)
    if not student:
        return api_error("Student profile not found.", 404)

    if current_user.is_student() and (not current_user.student or current_user.student.id != student_id):
        return api_error("Access denied. You can only view your own employment outcome.", 403)

    outcome = employment_service.get_outcome(student_id, current_user=current_user)
    return api_success(outcome)


@api_bp.route('/student/<int:student_id>/employment', methods=['POST'])
@login_required
def save_student_employment(student_id: int):
    """
    POST /api/student/<id>/employment
    Creates or updates employment outcome for a student.
    Own data only (admins permitted).
    """
    from services import employment_service

    student = db.session.get(Student, student_id)
    if not student:
        return api_error("Student profile not found.", 404)

    if current_user.is_student() and (not current_user.student or current_user.student.id != student_id):
        return api_error("Access denied. You can only update your own employment outcome.", 403)

    payload = request.get_json(silent=True) or request.form.to_dict() or {}
    ok, res = employment_service.save_outcome(student_id, payload, current_user=current_user)
    if not ok:
        return api_error(str(res), 400)

    updated_outcome = employment_service.get_outcome(student_id, current_user=current_user)
    return api_success(updated_outcome)


# ── Dashboard Analytics (Phase 13) ───────────────────────────
@api_bp.route('/dashboard/stats', methods=['GET'])
@login_required
def dashboard_stats():
    """
    GET /api/dashboard/stats?branch=&year=
    Admin only: aggregated placement, salary, skill demand, and trend metrics.
    Validates branch and year query parameters.
    """
    if not current_user.is_admin():
        return api_error("Access denied. Admin privileges required.", 403)

    branch = request.args.get('branch', '').strip()
    year_raw = request.args.get('year', '').strip()
    year = None
    if year_raw and year_raw.lower() != 'all':
        try:
            year = int(year_raw)
            if year < 1900 or year > 2100:
                return api_error("Invalid year parameter. Must be between 1900 and 2100.", 400)
        except (ValueError, TypeError):
            return api_error("Invalid year parameter. Must be a 4-digit integer.", 400)

    filters = {'branch': branch, 'year': year}
    from services import analytics_service
    analytics_data = analytics_service.get_dashboard_analytics(filters)
    return api_success(analytics_data)


@api_bp.route('/student/<int:student_id>/analytics', methods=['GET'])
@login_required
def get_student_analytics(student_id: int):
    """
    GET /api/student/<id>/analytics
    Returns personal skill analytics for a student.
    Own data only (admins permitted).
    """
    student = db.session.get(Student, student_id)
    if not student:
        return api_error("Student profile not found.", 404)

    if current_user.is_student() and (not current_user.student or current_user.student.id != student_id):
        return api_error("Access denied. You can only view your own analytics.", 403)

    from services import analytics_service
    data = analytics_service.get_student_personal_analytics(student_id)
    if not data:
        return api_error("Analytics data not found.", 404)
    return api_success(data)


# ── ML Prediction ─────────────────────────────────────────────
@api_bp.route('/predict-employment', methods=['POST'])
@login_required
def predict_employment():
    """Phase 19: ML-based placement prediction."""
    return api_error("Not implemented yet. Coming in Phase 19.", 501)


# ── Target Companies & Company Skill Gap ──────────────────────────────
@api_bp.route('/companies', methods=['GET'])
@login_required
def get_companies_list():
    """List distinct companies with active job postings, job counts, and skill counts."""
    from services import company_service
    companies = company_service.list_companies()
    return api_success(companies)


@api_bp.route('/company/<path:company_name>/skills', methods=['GET'])
@login_required
def get_company_skills(company_name: str):
    """Aggregated required skills for a target company."""
    from services import company_service
    import urllib.parse
    clean_name = urllib.parse.unquote_plus(company_name).strip()
    profile = company_service.get_company_profile(clean_name)
    if not profile:
        return api_error(f"Company '{clean_name}' not found.", 404)
    return api_success({
        'company_name': profile['company_name'],
        'total_jobs': profile['total_jobs'],
        'roles': profile['roles'],
        'skills': profile['skills'],
        'core_skills': profile['core_skills'],
        'common_skills': profile['common_skills'],
        'occasional_skills': profile['occasional_skills'],
    })


@api_bp.route('/student/<int:student_id>/company-gap', methods=['GET'])
@login_required
def get_student_company_gap(student_id: int):
    """
    Company-wise skill gap analysis for a student.
    Enforces ownership: students can only access their own analysis; admins can access any.
    Query param: ?company=<name>
    """
    if current_user.is_student():
        if not current_user.student or current_user.student.id != student_id:
            return api_error("Access denied. You can only view your own company skill gap.", 403)

    company_name = request.args.get('company', '').strip()
    if not company_name:
        return api_error("Query parameter 'company' is required.", 400)

    from services import company_service
    ok, res_or_err, status_code = company_service.analyze_company(
        student_id=student_id,
        company_name=company_name,
        current_user=current_user
    )

    if not ok:
        return api_error(res_or_err, status_code)

    return api_success(res_or_err)


# ── Adzuna Live Companies & Job Postings ───────────────────────
@api_bp.route('/adzuna/search-companies', methods=['GET'])
@login_required
def api_adzuna_search_companies():
    """Live search companies via Adzuna API."""
    from services import adzuna_service
    q = request.args.get('q', '').strip()
    country = request.args.get('country', '').strip()
    ok, data = adzuna_service.search_companies_adzuna(query=q, country=country if country else None)
    if not ok:
        return api_error(data.get('error', 'Failed to fetch companies from Adzuna'), 400, data=data)
    return api_success(data)


@api_bp.route('/adzuna/company-jobs', methods=['GET'])
@login_required
def api_adzuna_company_jobs():
    """Fetch active jobs for a company from Adzuna API."""
    from services import adzuna_service
    company = request.args.get('company', '').strip()
    country = request.args.get('country', '').strip()
    if not company:
        return api_error("Query parameter 'company' is required.", 400)
    ok, data = adzuna_service.get_company_posts_adzuna(company_name=company, country=country if country else None)
    if not ok:
        return api_error(data.get('error', 'Failed to fetch jobs from Adzuna'), 400, data=data)
    return api_success(data)


@api_bp.route('/adzuna/analyze-post', methods=['POST'])
@login_required
def api_adzuna_analyze_post():
    """Analyze skills required for a selected Adzuna post."""
    from services import adzuna_service
    if not current_user.student:
        return api_error("Student profile not found.", 404)

    payload = request.get_json(silent=True) or {}
    post_title = payload.get('title', '').strip()
    post_desc = payload.get('description', '').strip()
    company_name = payload.get('company', '').strip()
    job_id = payload.get('job_id', '').strip()

    if not post_title and not post_desc:
        return api_error("Post title or description is required for analysis.", 400)

    ok, analysis, code = adzuna_service.analyze_adzuna_post_skills(
        student_id=current_user.student.id,
        post_title=post_title,
        post_description=post_desc,
        company_name=company_name,
        job_id=job_id,
        current_user=current_user
    )

    if not ok:
        return api_error(analysis, code)

    return api_success(analysis)


