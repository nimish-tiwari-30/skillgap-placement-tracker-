"""
routes/student.py
──────────────────
Student Blueprint — all student-facing pages.
Phase 5: Full profile + skill management.
"""

from flask import (
    Blueprint, render_template, redirect, url_for, flash, request, jsonify, abort, send_from_directory, session
)
from flask_login import current_user
from extensions import db
from utils.decorators import student_required
from services import profile_service, resume_service, job_service, gap_service, match_service
from forms.profile_forms import (
    ProfileForm, AddSkillForm, CertificationForm, ProjectForm, InternshipForm
)
from forms.resume_forms import ResumeUploadForm
from models.skill import Skill, StudentSkill, Resume

student_bp = Blueprint('student', __name__)


# ── Helper: get current student, 404 if missing ───────────────────────────────
def _get_student():
    student = current_user.student
    if not student:
        abort(404)
    return student


# ════════════════════════════════════════════════════════════════════════════════
#  DASHBOARD
# ════════════════════════════════════════════════════════════════════════════════

@student_bp.route('/dashboard')
@student_required
def dashboard():
    """Student home dashboard — shows real profile completion %, target job match, and closest job matches."""
    student    = _get_student()
    completion = profile_service.calculate_profile_completion(student)

    # Group skills by category for display
    skills_by_cat = {}
    for ss in student.skills:
        cat = ss.skill.category or 'Other'
        skills_by_cat.setdefault(cat, []).append(ss)

    # Phase 8: Fetch target job & latest gap analysis
    target_job = getattr(student, 'target_job', None)
    latest_analysis = None
    latest_details = None

    if target_job:
        latest_analysis = gap_service.get_latest_analysis(student.id, target_job.id, current_user=current_user)
    else:
        latest_analysis = gap_service.get_latest_analysis(student.id, current_user=current_user)

    if latest_analysis:
        latest_details = gap_service.format_analysis_details(latest_analysis)

    # Phase 9: Top 3 jobs by overall match (neutral wording: closest matches by skill similarity)
    top_matches = []
    ok, all_matches = match_service.match_student_to_all_jobs(student.id, current_user=current_user, sort_by='overall_match')
    if ok and isinstance(all_matches, list):
        top_matches = all_matches[:3]

    # Phase 10: Top 3 missing skills for target job (for "Recommended Skills" dashboard card)
    top_missing_skills = []
    if target_job:
        from services.recommendation_service import _get_missing_skills_for_job
        from models.job import JobSkill
        from models.skill import StudentSkill
        from sqlalchemy.orm import joinedload, selectinload
        from models.student import Student as StudentModel
        from models.job import JobDescription
        # Reload job with eager skills for the pure function
        job_with_skills = JobDescription.query.options(
            selectinload(JobDescription.job_skills).joinedload(JobSkill.skill)
        ).filter_by(id=target_job.id).first()
        student_with_skills = StudentModel.query.options(
            selectinload(StudentModel.skills).joinedload(StudentSkill.skill)
        ).filter_by(id=student.id).first()
        if job_with_skills and student_with_skills:
            top_missing_skills = _get_missing_skills_for_job(student_with_skills, job_with_skills)[:3]

    # Phase 11: Learning Path completion % and real skill progress for dashboard
    path_completion_pct = 0.0
    has_learning_path = False
    if target_job:
        from services import learning_path_service
        path_res = learning_path_service.get_path(student.id, target_job.id, current_user=current_user)
        path_completion_pct = path_res.get('completion_pct', 0.0)
        has_learning_path = path_res.get('total_items', 0) > 0

    top_student_skills = []
    PROF_NUM = {'Beginner': 33, 'Intermediate': 66, 'Advanced': 100}
    for ss in student.skills[:3]:
        top_student_skills.append({
            'name': ss.skill.name if ss.skill else f'Skill #{ss.skill_id}',
            'level': ss.proficiency_level,
            'pct': PROF_NUM.get(ss.proficiency_level, 33),
        })

    # Phase 12: Employment Outcome for dashboard
    from services import employment_service
    employment_outcome = employment_service.get_outcome(student.id, current_user=current_user)

    return render_template(
        'student/dashboard.html',
        title         = 'My Dashboard',
        student       = student,
        completion    = completion,
        skill_count   = len(student.skills),
        skills_by_cat = skills_by_cat,
        target_job    = target_job,
        latest_analysis = latest_analysis,
        latest_details  = latest_details,
        top_matches     = top_matches,
        top_missing_skills = top_missing_skills,
        path_completion_pct = path_completion_pct,
        has_learning_path   = has_learning_path,
        top_student_skills  = top_student_skills,
        employment_outcome  = employment_outcome,
    )


# ════════════════════════════════════════════════════════════════════════════════
#  PROFILE (tabs: Academic, Skills, Certs, Projects, Internships)
# ════════════════════════════════════════════════════════════════════════════════

@student_bp.route('/profile', methods=['GET', 'POST'])
@student_required
def profile():
    """
    Single page with 5 tab sections.
    Each section POSTs to its own action URL (action parameter selects the handler).
    """
    student     = _get_student()
    active_tab  = request.args.get('tab', 'academic')

    # Initialise all forms
    profile_form = ProfileForm(obj=student)
    add_skill_form  = AddSkillForm()
    cert_form    = CertificationForm()
    project_form = ProjectForm()
    intern_form  = InternshipForm()

    # All skills (for autocomplete) — sent to template as JSON
    all_skills = Skill.query.order_by(Skill.name).all()
    skill_options = [{'id': s.id, 'name': s.name, 'category': s.category or ''} for s in all_skills]

    # Profile completion
    completion = profile_service.calculate_profile_completion(student)

    return render_template(
        'student/profile.html',
        title        = 'My Profile',
        student      = student,
        active_tab   = active_tab,
        profile_form = profile_form,
        add_skill_form  = add_skill_form,
        cert_form    = cert_form,
        project_form = project_form,
        intern_form  = intern_form,
        skill_options = skill_options,
        completion   = completion,
    )


# ════════════════════════════════════════════════════════════════════════════════
#  ACADEMIC PROFILE UPDATE
# ════════════════════════════════════════════════════════════════════════════════

@student_bp.route('/profile/update', methods=['POST'])
@student_required
def update_profile():
    """Handle academic profile form POST."""
    student = _get_student()
    ok, err = profile_service.update_profile(student, request.form)
    if ok:
        flash('Profile updated successfully!', 'success')
    else:
        flash(f'Update failed: {err}', 'danger')
    return redirect(url_for('student.profile', tab='academic'))


# ════════════════════════════════════════════════════════════════════════════════
#  SKILLS
# ════════════════════════════════════════════════════════════════════════════════

@student_bp.route('/profile/skills/add', methods=['POST'])
@student_required
def add_skill():
    """Add a skill from the master list to the student's profile."""
    student = _get_student()
    skill_id    = request.form.get('skill_id', '')
    proficiency = request.form.get('proficiency', 'Beginner')

    if not skill_id:
        flash('Please select a skill from the list.', 'warning')
        return redirect(url_for('student.profile', tab='skills'))

    try:
        sid = int(skill_id)
    except ValueError:
        flash('Invalid skill selected.', 'danger')
        return redirect(url_for('student.profile', tab='skills'))

    ok, err = profile_service.add_student_skill(student, sid, proficiency)
    if ok:
        flash('Skill added!', 'success')
    else:
        flash(err, 'warning')
    return redirect(url_for('student.profile', tab='skills'))


@student_bp.route('/profile/skills/update', methods=['POST'])
@student_required
def update_skill():
    """Update proficiency for an existing skill."""
    student     = _get_student()
    skill_id    = request.form.get('skill_id', '')
    proficiency = request.form.get('proficiency', 'Beginner')

    try:
        sid = int(skill_id)
    except (ValueError, TypeError):
        flash('Invalid request.', 'danger')
        return redirect(url_for('student.profile', tab='skills'))

    ok, err = profile_service.update_student_skill(student, sid, proficiency)
    if ok:
        flash('Proficiency updated!', 'success')
    else:
        flash(err, 'warning')
    return redirect(url_for('student.profile', tab='skills'))


@student_bp.route('/profile/skills/remove', methods=['POST'])
@student_required
def remove_skill():
    """Remove a skill from the student's profile."""
    student  = _get_student()
    skill_id = request.form.get('skill_id', '')

    try:
        sid = int(skill_id)
    except (ValueError, TypeError):
        flash('Invalid request.', 'danger')
        return redirect(url_for('student.profile', tab='skills'))

    ok, err = profile_service.remove_student_skill(student, sid)
    if ok:
        flash('Skill removed.', 'info')
    else:
        flash(err, 'warning')
    return redirect(url_for('student.profile', tab='skills'))


# ── Skill autocomplete API (JSON) ─────────────────────────────────────────────
@student_bp.route('/api/skills/search')
@student_required
def skill_search():
    """AJAX endpoint: returns JSON list of skills matching query."""
    q = request.args.get('q', '').strip()
    results = profile_service.search_skills(q)
    return jsonify(results)


# ════════════════════════════════════════════════════════════════════════════════
#  CERTIFICATIONS
# ════════════════════════════════════════════════════════════════════════════════

@student_bp.route('/profile/certs/add', methods=['POST'])
@student_required
def add_cert():
    student = _get_student()
    form_data = {
        'title':          request.form.get('title', '').strip(),
        'issuing_org':    request.form.get('issuing_org', '').strip(),
        'issue_date':     _parse_date(request.form.get('issue_date')),
        'expiry_date':    _parse_date(request.form.get('expiry_date')),
        'credential_url': request.form.get('credential_url', '').strip(),
    }
    if not form_data['title']:
        flash('Certification title is required.', 'warning')
    else:
        ok, err = profile_service.add_certification(student, form_data)
        flash('Certification added!' if ok else err, 'success' if ok else 'danger')
    return redirect(url_for('student.profile', tab='certs'))


@student_bp.route('/profile/certs/delete/<int:cert_id>', methods=['POST'])
@student_required
def delete_cert(cert_id):
    student = _get_student()
    ok, err = profile_service.delete_certification(student, cert_id)
    flash('Certification removed.' if ok else err, 'info' if ok else 'danger')
    return redirect(url_for('student.profile', tab='certs'))


# ════════════════════════════════════════════════════════════════════════════════
#  PROJECTS
# ════════════════════════════════════════════════════════════════════════════════

@student_bp.route('/profile/projects/add', methods=['POST'])
@student_required
def add_project():
    student = _get_student()
    form_data = {
        'title':       request.form.get('title', '').strip(),
        'description': request.form.get('description', '').strip(),
        'tech_stack':  request.form.get('tech_stack', '').strip(),
        'project_url': request.form.get('project_url', '').strip(),
        'start_date':  _parse_date(request.form.get('start_date')),
        'end_date':    _parse_date(request.form.get('end_date')),
    }
    if not form_data['title']:
        flash('Project title is required.', 'warning')
    else:
        ok, err = profile_service.add_project(student, form_data)
        flash('Project added!' if ok else err, 'success' if ok else 'danger')
    return redirect(url_for('student.profile', tab='projects'))


@student_bp.route('/profile/projects/delete/<int:project_id>', methods=['POST'])
@student_required
def delete_project(project_id):
    student = _get_student()
    ok, err = profile_service.delete_project(student, project_id)
    flash('Project removed.' if ok else err, 'info' if ok else 'danger')
    return redirect(url_for('student.profile', tab='projects'))


# ════════════════════════════════════════════════════════════════════════════════
#  INTERNSHIPS
# ════════════════════════════════════════════════════════════════════════════════

@student_bp.route('/profile/internships/add', methods=['POST'])
@student_required
def add_internship():
    student = _get_student()
    form_data = {
        'company_name': request.form.get('company_name', '').strip(),
        'role_title':   request.form.get('role_title', '').strip(),
        'description':  request.form.get('description', '').strip(),
        'start_date':   _parse_date(request.form.get('start_date')),
        'end_date':     _parse_date(request.form.get('end_date')),
    }
    if not form_data['company_name'] or not form_data['role_title']:
        flash('Company name and role title are required.', 'warning')
    else:
        ok, err = profile_service.add_internship(student, form_data)
        flash('Internship added!' if ok else err, 'success' if ok else 'danger')
    return redirect(url_for('student.profile', tab='internships'))


@student_bp.route('/profile/internships/delete/<int:intern_id>', methods=['POST'])
@student_required
def delete_internship(intern_id):
    student = _get_student()
    ok, err = profile_service.delete_internship(student, intern_id)
    flash('Internship removed.' if ok else err, 'info' if ok else 'danger')
    return redirect(url_for('student.profile', tab='internships'))


# ════════════════════════════════════════════════════════════════════════════════
#  RESUME UPLOAD & PARSING (Phase 6)
# ════════════════════════════════════════════════════════════════════════════════

@student_bp.route('/resume', methods=['GET'])
@student_required
def resume_upload():
    """Resume management, upload form, review screen, and history."""
    student = _get_student()
    form = ResumeUploadForm()
    active_resume = resume_service.get_active_resume(student)
    resume_history = resume_service.get_student_resumes(student)

    # Active review session data from most recent upload
    review_data = session.get('resume_review')

    # Resume-extracted skills already on profile
    resume_skills = [ss for ss in student.skills if ss.source == 'resume']

    return render_template(
        'student/resume_upload.html',
        title='Resume & Skill Extraction',
        student=student,
        form=form,
        active_resume=active_resume,
        resume_history=resume_history,
        review_data=review_data,
        resume_skills=resume_skills
    )


@student_bp.route('/resume/upload', methods=['POST'])
@student_required
def upload_resume_file():
    """Handle resume file upload, text extraction, and skill detection."""
    student = _get_student()
    form = ResumeUploadForm()

    if form.validate_on_submit():
        file_obj = form.resume.data
        ok, msg, data = resume_service.process_resume_upload(student, file_obj)
        if ok:
            detected = data.get('detected_skills', [])
            session['resume_review'] = {
                'resume_id': data['resume_id'],
                'detected_skills': detected,
                'text_length': data['text_length'],
                'preview': data['preview']
            }
            if detected:
                flash(
                    f"Resume parsed successfully! Found {len(detected)} technical skill(s). Please review and confirm below.",
                    'success'
                )
            else:
                flash(
                    "Resume text extracted successfully, but no matching skills were found in our canonical dictionary.",
                    'warning'
                )
        else:
            flash(msg, 'danger')
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(error, 'danger')

    return redirect(url_for('student.resume_upload'))


@student_bp.route('/resume/confirm', methods=['POST'])
@student_required
def confirm_resume_skills():
    """Confirm and persist detected skills to student's profile."""
    student = _get_student()

    selected_ids = request.form.getlist('skill_ids', type=int)
    if not selected_ids:
        flash("No skills were selected to add.", "warning")
        session.pop('resume_review', None)
        return redirect(url_for('student.resume_upload'))

    proficiencies = {}
    for sid in selected_ids:
        prof = request.form.get(f'proficiency_{sid}', 'Intermediate')
        proficiencies[sid] = prof

    added, skipped = resume_service.confirm_resume_skills(student, selected_ids, proficiencies)
    session.pop('resume_review', None)

    flash(f"Skills updated! Added {added}, skipped {skipped} already in profile.", 'success')
    return redirect(url_for('student.resume_upload'))


@student_bp.route('/resume/discard', methods=['POST'])
@student_required
def discard_resume_review():
    """Dismiss the pending skill review panel."""
    session.pop('resume_review', None)
    flash("Skill import dismissed.", 'info')
    return redirect(url_for('student.resume_upload'))


@student_bp.route('/resume/download/<int:resume_id>', methods=['GET'])
@student_required
def download_resume(resume_id: int):
    """Download uploaded resume with ownership verification."""
    student = _get_student()
    resume = resume_service.get_resume_by_id(resume_id)

    if not resume or resume.student_id != student.id:
        abort(404)

    upload_dir = resume_service.get_upload_dir()
    return send_from_directory(
        upload_dir,
        resume.stored_filename,
        as_attachment=True,
        download_name=resume.original_name
    )


@student_bp.route('/resume/delete/<int:resume_id>', methods=['POST'])
@student_required
def delete_resume_file(resume_id: int):
    """Remove a resume document and its metadata."""
    student = _get_student()
    ok, msg = resume_service.delete_resume(student, resume_id)
    # If this resume was in review session, clear review
    review = session.get('resume_review')
    if review and review.get('resume_id') == resume_id:
        session.pop('resume_review', None)

    flash(msg, 'info' if ok else 'danger')
    return redirect(url_for('student.resume_upload'))


# ════════════════════════════════════════════════════════════════════════════════
#  SKILL GAP ANALYSIS (Phase 8)
# ════════════════════════════════════════════════════════════════════════════════

@student_bp.route('/skill-gap', methods=['GET', 'POST'])
@student_required
def skill_gap():
    """
    Skill gap analysis — Phase 8.
    Allows a student to choose a target job, runs transparent gap analysis,
    saves the snapshot, displays coverage %, weighted %, comparisons, and Chart.js visuals.
    """
    student = _get_student()
    active_jobs = job_service.get_all_jobs(active_only=True)

    if request.method == 'POST':
        job_id = request.form.get('job_id', type=int)
        set_target = request.form.get('set_target') == '1'

        if not job_id:
            flash("Please select a target job from the list.", "warning")
            return redirect(url_for('student.skill_gap'))

        ok, res_or_err, details = gap_service.analyze(student.id, job_id, current_user=current_user)
        if not ok:
            flash(f"Analysis could not be completed: {res_or_err}", "danger")
            return redirect(url_for('student.skill_gap', job_id=job_id))

        if set_target:
            gap_service.set_target_job(student.id, job_id, current_user=current_user)
            flash("Skill gap analysis calculated and set as your target job!", "success")
        else:
            flash("Skill gap analysis completed successfully!", "success")

        return redirect(url_for('student.skill_gap', job_id=job_id))

    # GET handling
    job_id = request.args.get('job_id', type=int)
    # If no job query param, fallback to student's saved target job if any
    if not job_id and getattr(student, 'target_job_id', None):
        job_id = student.target_job_id

    selected_job = None
    analysis = None
    details = None
    history = []

    if job_id:
        selected_job = job_service.get_job_by_id(job_id)
        if selected_job:
            analysis = gap_service.get_latest_analysis(student.id, job_id=job_id, current_user=current_user)
            if analysis:
                details = gap_service.format_analysis_details(analysis)
            history = gap_service.get_history(student.id, job_id=job_id, limit=10, current_user=current_user)

    return render_template(
        'student/skill_gap.html',
        title='Skill Gap Analysis',
        student=student,
        jobs=active_jobs,
        selected_job=selected_job,
        job_id=job_id,
        analysis=analysis,
        details=details,
        history=history,
        has_skills=len(student.skills) > 0,
    )


@student_bp.route('/skill-gap/set-target/<int:job_id>', methods=['POST'])
@student_required
def set_target_job(job_id: int):
    """Save the selected job as the student's primary target job."""
    student = _get_student()
    ok, err = gap_service.set_target_job(student.id, job_id, current_user=current_user)
    if ok:
        flash("Target job saved successfully! Profile completion updated.", "success")
    else:
        flash(err or "Failed to set target job.", "danger")
    return redirect(url_for('student.skill_gap', job_id=job_id))


# ════════════════════════════════════════════════════════════════════════════════
#  JOB MATCHING (Phase 9 - TF-IDF & Cosine Similarity)
# ════════════════════════════════════════════════════════════════════════════════

@student_bp.route('/job-match', methods=['GET'])
@student_required
def job_matching():
    """
    Job matching overview — Phase 9.
    Compares student skills against all active jobs, presenting transparent
    Skill Coverage % and Overall Job Match % (TF-IDF Cosine Similarity).
    Allows searching, filtering by career role, and neutral sorting.
    """
    student = _get_student()
    q = request.args.get('q', '').strip()
    role_id = request.args.get('role_id', type=int)
    sort_by = request.args.get('sort_by', 'overall_match')

    ok, match_list = match_service.match_student_to_all_jobs(
        student_id=student.id,
        current_user=current_user,
        search=q,
        role_id=role_id,
        sort_by=sort_by
    )
    if not ok:
        flash(str(match_list), 'danger')
        match_list = []

    roles = job_service.get_all_roles()

    return render_template(
        'student/job_matching.html',
        title='Job Matching Analysis',
        student=student,
        jobs=match_list,
        roles=roles,
        q=q,
        active_role_id=role_id,
        sort_by=sort_by,
        has_skills=len(student.skills) > 0,
    )


@student_bp.route('/job-match/<int:job_id>', methods=['GET'])
@student_required
def job_match_detail(job_id: int):
    """
    Detailed single-job match breakdown — Phase 9.
    Displays Coverage %, Weighted %, and Overall Match %,
    categorized skill badges, and action links to run full skill-gap analysis.
    """
    student = _get_student()
    ok, match_data = match_service.match_student_to_job(
        student_id=student.id,
        job_id=job_id,
        current_user=current_user
    )
    if not ok:
        abort(404)

    return render_template(
        'student/job_match_detail.html',
        title=f"Match Analysis — {match_data['title']}",
        student=student,
        match=match_data,
        has_skills=len(student.skills) > 0,
    )


# ════════════════════════════════════════════════════════════════════════════════
#  LEARNING PATH & PROGRESS TRACKING (Phase 11)
# ════════════════════════════════════════════════════════════════════════════════

@student_bp.route('/learning-path', methods=['GET'])
@student_required
def learning_path():
    """
    Step-by-step learning roadmap derived from target job gaps.
    Shows ordered steps with difficulty, importance, top recommended course,
    status badges, and completion controls.
    """
    from services import learning_path_service
    from models.job import JobDescription

    student = _get_student()

    job_id = request.args.get('job_id', type=int)
    if not job_id and student.target_job_id:
        job_id = student.target_job_id

    all_active_jobs = JobDescription.query.filter_by(is_active=True).order_by(
        JobDescription.title
    ).all()

    target_job = None
    path_data = None
    error_msg = None

    if job_id:
        target_job = db.session.get(JobDescription, job_id)
        if not target_job or not target_job.is_active:
            error_msg = "Selected job was not found or is currently inactive."
        else:
            # Check existing path
            path_data = learning_path_service.get_path(student.id, job_id, current_user=current_user)
            # If path hasn't been generated yet, auto-generate on first visit
            if path_data.get('total_items', 0) == 0:
                ok, gen_res = learning_path_service.generate_path(student.id, job_id, current_user=current_user)
                if ok and isinstance(gen_res, dict):
                    path_data = gen_res

    return render_template(
        'student/learning_path.html',
        title='My Learning Path',
        student=student,
        job_id=job_id,
        target_job=target_job,
        all_active_jobs=all_active_jobs,
        path_data=path_data,
        error_msg=error_msg,
    )


@student_bp.route('/learning-path/generate', methods=['POST'])
@student_required
def generate_learning_path():
    """Generate or synchronize a learning path for the selected job."""
    from services import learning_path_service
    student = _get_student()
    job_id = request.form.get('job_id', type=int)

    if not job_id:
        flash("Please select a target job first.", "warning")
        return redirect(url_for('student.learning_path'))

    ok, res = learning_path_service.generate_path(student.id, job_id, current_user=current_user)
    if ok:
        flash("Learning path synchronized successfully.", "success")
    else:
        flash(f"Could not generate path: {res}", "danger")

    return redirect(url_for('student.learning_path', job_id=job_id))


@student_bp.route('/learning-path/<int:item_id>/complete', methods=['POST'])
@student_required
def complete_learning_step(item_id: int):
    """Mark a learning step completed in one transaction."""
    from services import learning_path_service
    student = _get_student()
    job_id = request.form.get('job_id', type=int)
    proficiency = request.form.get('proficiency', default=3, type=int)

    ok, res = learning_path_service.mark_complete(
        student_id=student.id,
        item_id=item_id,
        proficiency=proficiency,
        current_user=current_user,
    )
    if ok:
        flash("Step marked as completed! Your skill profile and progress history have been updated.", "success")
    else:
        flash(f"Error: {res}", "danger")

    return redirect(url_for('student.learning_path', job_id=job_id))


@student_bp.route('/learning-path/<int:item_id>/undo', methods=['POST'])
@student_required
def undo_learning_step(item_id: int):
    """Undo completion for a step (does not remove skill from profile)."""
    from services import learning_path_service
    student = _get_student()
    job_id = request.form.get('job_id', type=int)

    ok, res = learning_path_service.mark_pending(
        student_id=student.id,
        item_id=item_id,
        current_user=current_user,
    )
    if ok:
        flash("Step reset to pending.", "info")
    else:
        flash(f"Error: {res}", "danger")

    return redirect(url_for('student.learning_path', job_id=job_id))


@student_bp.route('/progress', methods=['GET'])
@student_required
def progress():
    """
    Skill Progress & Proficiency History over time.
    Shows line chart of technical skill evolution and chronological audit table.
    """
    from services import learning_path_service
    student = _get_student()

    history_data = learning_path_service.get_skill_progress_history(student.id)

    return render_template(
        'student/progress.html',
        title='My Skill Progress',
        student=student,
        history_data=history_data,
    )


# ════════════════════════════════════════════════════════════════════════════════
#  JOB BROWSING (Phase 7 - Read-only)
# ════════════════════════════════════════════════════════════════════════════════

@student_bp.route('/jobs', methods=['GET'])
@student_required
def jobs():
    """
    Searchable, filterable list of active jobs for students.
    Shows job title, company, role, location, min experience, and required skills count.
    """
    q = request.args.get('q', '').strip()
    role_id = request.args.get('role_id', type=int)

    all_jobs = job_service.get_all_jobs(search=q, role_id=role_id, active_only=True)
    roles = job_service.get_all_roles()

    return render_template(
        'student/jobs.html',
        title='Browse Opportunities',
        jobs=all_jobs,
        roles=roles,
        q=q,
        active_role_id=role_id
    )


@student_bp.route('/jobs/<int:job_id>', methods=['GET'])
@student_required
def job_detail(job_id: int):
    """
    Read-only job detail page:
    Shows job description and required skills as badges with importance level.
    (Matching algorithm will be connected in Phase 8/9).
    """
    job = job_service.get_job_by_id(job_id)
    if not job or not job.is_active:
        abort(404)

    # Sort skills by importance descending
    sorted_skills = sorted(job.job_skills, key=lambda js: js.importance_weight, reverse=True)

    return render_template(
        'student/job_detail.html',
        title=f'{job.title} — {job.company_name}',
        job=job,
        job_skills=sorted_skills
    )


# ── Internal helper ────────────────────────────────────────────────────────────
def _parse_date(val):
    """Parse a date string (YYYY-MM-DD) to a date object, or return None."""
    if not val or not val.strip():
        return None
    from datetime import date
    try:
        return date.fromisoformat(val.strip())
    except ValueError:
        return None


# ════════════════════════════════════════════════════════════════════════════════
#  RECOMMENDATIONS (Phase 10)
# ════════════════════════════════════════════════════════════════════════════════

@student_bp.route('/recommendations')
@student_required
def recommendations():
    """
    Student course recommendation page.
    - Defaults to the student's current target job (set in Phase 8).
    - Student can override by passing ?job_id=<n> in the query string.
    - All recommendations come from DB (never hard-coded).
    - Friendly state: no target job, no skills in profile, no missing skills.
    """
    from services import recommendation_service
    from models.job import JobDescription

    student = _get_student()

    # Determine which job to recommend for
    job_id = request.args.get('job_id', type=int)
    if not job_id and student.target_job_id:
        job_id = student.target_job_id

    # Collect all active jobs for the dropdown (so student can pick a job)
    all_active_jobs = JobDescription.query.filter_by(is_active=True).order_by(
        JobDescription.title
    ).all()

    result = None
    error_msg = None

    if job_id:
        ok, result = recommendation_service.recommend_for_job(
            student_id=student.id,
            job_id=job_id,
            current_user=current_user,
        )
        if not ok:
            error_msg = result
            result = None

    return render_template(
        'student/recommendations.html',
        title='Course Recommendations',
        student=student,
        job_id=job_id,
        all_active_jobs=all_active_jobs,
        result=result,
        error_msg=error_msg,
    )


# ════════════════════════════════════════════════════════════════════════════════
#  PHASE 12: EMPLOYMENT OUTCOME MANAGEMENT
# ════════════════════════════════════════════════════════════════════════════════

@student_bp.route('/employment', methods=['GET', 'POST'])
@student_required
def employment():
    """
    Student employment outcome management:
      GET: Display current outcome and edit form with suggestions.
      POST: Validate and save outcome and skills used in one transaction.
    """
    from services import employment_service
    from models.job import JobRole

    student = _get_student()

    if request.method == 'POST':
        form_data = {
            'status': request.form.get('status'),
            'company_name': request.form.get('company_name'),
            'role_title': request.form.get('role_title'),
            'salary_package_lpa': request.form.get('salary_package_lpa'),
            'placement_date': request.form.get('placement_date'),
            'placement_type': request.form.get('placement_type'),
            'notes': request.form.get('notes'),
            'skills_used': request.form.getlist('skills_used'),
        }

        ok, result = employment_service.save_outcome(student.id, form_data, current_user=current_user)
        if ok:
            flash('Employment outcome updated successfully!', 'success')
            return redirect(url_for('student.employment'))
        else:
            flash(f"Error: {result}", 'danger')

    outcome = employment_service.get_outcome(student.id, current_user=current_user)
    all_skills = Skill.query.order_by(Skill.name.asc()).all()
    job_roles = JobRole.query.order_by(JobRole.title.asc()).all()

    return render_template(
        'student/employment.html',
        title='My Employment Status',
        student=student,
        outcome=outcome,
        all_skills=all_skills,
        job_roles=job_roles,
    )


@student_bp.route('/employment/delete', methods=['POST'])
@student_required
def delete_employment():
    """Delete current student's employment outcome."""
    from services import employment_service

    student = _get_student()
    ok, err = employment_service.delete_outcome(student.id, current_user=current_user)
    if ok:
        flash('Employment outcome deleted successfully.', 'info')
    else:
        flash(f'Failed to delete outcome: {err}', 'danger')
    return redirect(url_for('student.employment'))


# ════════════════════════════════════════════════════════════════════════════════
#  PHASE 13: STUDENT PERSONAL ANALYTICS
# ════════════════════════════════════════════════════════════════════════════════

@student_bp.route('/analytics', methods=['GET'])
@student_required
def analytics():
    """
    Student personal analytics page:
    Shows profile completion, verified skills, latest gap match, learning path progress,
    proficiency radar chart, skill improvement timeline, and industry comparison.
    """
    from services import analytics_service

    student = _get_student()
    analytics_data = analytics_service.get_student_personal_analytics(student.id)

    return render_template(
        'student/analytics.html',
        title='My Skill Analytics',
        student=student,
        analytics=analytics_data
    )


# ════════════════════════════════════════════════════════════════════════════════
#  PHASE 14: EMPLOYMENT OUTCOME PREDICTION (ML)
# ════════════════════════════════════════════════════════════════════════════════

@student_bp.route('/prediction', methods=['GET'])
@student_required
def prediction():
    """
    Student placement outcome prediction page:
    Uses trained Random Forest Classifier on pre-outcome features.
    Provides probability, confidence rating, feature impact, and actionable recommendations.
    """
    from ml import employment_model

    student = _get_student()
    pred_result = employment_model.predict_student(student)

    # Actionable guidance based on feature values
    suggestions = []
    fv = pred_result.get('feature_values', {})
    if fv.get('Skills Count', 0) < 6:
        suggestions.append({
            'icon': 'bi-tools',
            'title': 'Expand Your Skill Portfolio',
            'desc': f"You currently have {fv.get('Skills Count', 0)} skills recorded. Aim for at least 6–8 relevant technical skills to boost placement likelihood."
        })
    if fv.get('Skill Match %', 0) < 60:
        suggestions.append({
            'icon': 'bi-bullseye',
            'title': 'Target Role Alignment',
            'desc': f"Your target job match is {fv.get('Skill Match %', 0)}%. Review your Skill Gap Analysis and complete recommended courses."
        })
    if not fv.get('Has Internship', False):
        suggestions.append({
            'icon': 'bi-briefcase',
            'title': 'Gain Industry Experience',
            'desc': 'Students with at least one practical internship show significantly higher placement rates in our model.'
        })
    if fv.get('Aptitude Score', 50) < 65:
        suggestions.append({
            'icon': 'bi-cpu',
            'title': 'Practice Aptitude Tests',
            'desc': 'Aptitude screening is often the first round in campus placements. Focus on quantitative and logical reasoning.'
        })
    if fv.get('Communication Score', 50) < 65:
        suggestions.append({
            'icon': 'bi-chat-dots',
            'title': 'Enhance Communication & Soft Skills',
            'desc': 'Interview rounds heavily evaluate verbal clarity and technical communication.'
        })

    return render_template(
        'student/prediction.html',
        title='Placement Outcome Predictor',
        student=student,
        prediction=pred_result,
        suggestions=suggestions,
    )


# ════════════════════════════════════════════════════════════════════════════════
#  TARGET COMPANIES & COMPANY SKILL GAP
# ════════════════════════════════════════════════════════════════════════════════

@student_bp.route('/companies')
@student_required
def companies():
    """Directory of target companies fetched via Adzuna Jobs API."""
    student = _get_student()
    from services import adzuna_service

    q = request.args.get('q', '').strip()
    country = request.args.get('country', '').strip() or adzuna_service.get_adzuna_config().get('country', 'in')
    is_configured = adzuna_service.is_adzuna_configured()

    companies_data = []
    error_msg = None

    ok, res = adzuna_service.search_companies_adzuna(
        query=q,
        country=country,
        page=1
    )
    if ok:
        companies_data = res.get('companies', [])
    else:
        error_msg = res.get('error')

    return render_template(
        'student/companies.html',
        title='Target Companies (Adzuna Live Jobs)',
        student=student,
        companies=companies_data,
        q=q,
        country=country,
        is_configured=is_configured,
        error_msg=error_msg,
        total_count=len(companies_data),
        has_skills=len(student.skills) > 0,
    )


@student_bp.route('/companies/compare')
@student_required
def compare_companies():
    """Side-by-side comparison for up to 5 target companies."""
    student = _get_student()
    from services import company_service

    company_names = request.args.getlist('c')
    if not company_names:
        c_param = request.args.get('company', '').strip()
        if c_param:
            company_names = [c_param]

    sort_by = request.args.get('sort_by', 'overall_match').strip()

    ok, comp_data, code = company_service.compare_companies(student.id, company_names, current_user=current_user)
    if not ok:
        flash(comp_data, "warning" if code == 404 else "danger")
        return redirect(url_for('student.companies'))

    companies_list = comp_data.get('companies', [])
    missing_companies = comp_data.get('missing_companies', [])

    if sort_by == 'coverage':
        companies_list.sort(key=lambda x: x.get('coverage_pct', 0), reverse=True)
    elif sort_by == 'weighted':
        companies_list.sort(key=lambda x: x.get('weighted_pct', 0), reverse=True)
    elif sort_by == 'name':
        companies_list.sort(key=lambda x: x.get('company_name', '').lower())
    else:
        companies_list.sort(key=lambda x: x.get('overall_match_pct', 0), reverse=True)

    return render_template(
        'student/company_compare.html',
        title="Side-by-Side Company Comparison",
        student=student,
        companies=companies_list,
        missing_companies=missing_companies,
        has_skills=len(student.skills) > 0,
        sort_by=sort_by,
    )


@student_bp.route('/companies/<path:company_name>')
@student_required
def company_detail(company_name: str):
    """View active job posts for a selected target company via Adzuna and analyze selected post."""
    student = _get_student()
    from services import adzuna_service
    from flask import abort
    import urllib.parse

    clean_name = urllib.parse.unquote_plus(company_name).strip()
    country = request.args.get('country', '').strip() or adzuna_service.get_adzuna_config().get('country', 'in')
    selected_job_id = request.args.get('job_id', '').strip()

    ok, res = adzuna_service.get_company_posts_adzuna(
        company_name=clean_name,
        country=country
    )

    if not ok or not res.get('jobs'):
        abort(404)

    jobs = res.get('jobs', [])
    selected_job = None
    post_analysis = None

    if jobs:
        if selected_job_id:
            for j in jobs:
                if str(j.get('id')) == str(selected_job_id):
                    selected_job = j
                    break
        if not selected_job:
            selected_job = jobs[0]

        if selected_job:
            _, post_analysis, _ = adzuna_service.analyze_adzuna_post_skills(
                student_id=student.id,
                post_title=selected_job.get('title', ''),
                post_description=selected_job.get('description', ''),
                company_name=clean_name,
                job_id=str(selected_job.get('id', '')),
                current_user=current_user
            )

    return render_template(
        'student/company_detail.html',
        title=f"{clean_name} — Job Posts & Required Skills",
        student=student,
        company_name=clean_name,
        country=country,
        jobs=jobs,
        selected_job=selected_job,
        analysis=post_analysis,
        has_skills=len(student.skills) > 0,
    )



