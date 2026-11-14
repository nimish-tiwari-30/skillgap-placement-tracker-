"""
routes/admin.py
───────────────
Admin Blueprint — Phase 5: Skills management + Student list.
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, abort
from utils.decorators import admin_required
from services import profile_service, job_service
from forms.job_forms import JobRoleForm, JobDescriptionForm, IMPORTANCE_CHOICES
from extensions import db
from models.skill import Skill, SkillAlias
from models.student import Student
from models.job import JobRole, JobDescription, JobSkill

admin_bp = Blueprint('admin', __name__)


# ════════════════════════════════════════════════════════════════════════════════
#  PHASE 13: ANALYTICS DASHBOARD
# ════════════════════════════════════════════════════════════════════════════════

@admin_bp.route('/dashboard')
@admin_required
def dashboard():
    """
    Admin analytics dashboard:
    Loads KPIs, 4 main charts + 2 extras, summary tables, branch/year filters,
    and demo data notice.
    """
    from services import analytics_service

    branch = request.args.get('branch', '').strip()
    year = request.args.get('year', '').strip()
    filters = {'branch': branch, 'year': year}

    analytics_data = analytics_service.get_dashboard_analytics(filters)

    # Distinct values for filter dropdowns
    branches = [b[0] for b in db.session.query(Student.branch).distinct().order_by(Student.branch).all() if b[0]]
    years = [y[0] for y in db.session.query(Student.graduation_year).distinct().order_by(Student.graduation_year.desc()).all() if y[0]]

    return render_template(
        'admin/dashboard.html',
        title='Analytics Dashboard',
        analytics=analytics_data,
        branches=branches,
        years=years,
        active_branch=branch,
        active_year=year,
        demo_banner=True,
    )


@admin_bp.route('/dashboard/export-csv')
@admin_required
def dashboard_export_csv():
    """Export dashboard KPIs and summary tables as CSV with injection protection."""
    from services import analytics_service
    from flask import Response

    branch = request.args.get('branch', '').strip()
    year = request.args.get('year', '').strip()
    filters = {'branch': branch, 'year': year}

    csv_content = analytics_service.export_dashboard_csv(filters)
    return Response(
        csv_content,
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=analytics_dashboard_export.csv'}
    )


# ════════════════════════════════════════════════════════════════════════════════
#  SKILLS MANAGEMENT
# ════════════════════════════════════════════════════════════════════════════════

CATEGORIES = [
    'Programming', 'Data & Analytics', 'Web', 'Database',
    'Cloud/DevOps', 'AI/ML', 'Tools', 'Soft Skills'
]


@admin_bp.route('/skills', methods=['GET'])
@admin_required
def skills():
    """
    Admin skill management page.
    Supports search by name and filter by category.
    Aliases are managed from the skill_aliases table (same page).
    """
    q        = request.args.get('q', '').strip()
    cat      = request.args.get('cat', '').strip()

    query = Skill.query
    if q:
        query = query.filter(Skill.name.ilike(f'%{q}%'))
    if cat:
        query = query.filter_by(category=cat)

    skills_list = query.order_by(Skill.category, Skill.name).all()

    return render_template(
        'admin/skills.html',
        title       = 'Manage Skills',
        skills      = skills_list,
        categories  = CATEGORIES,
        q           = q,
        active_cat  = cat,
    )


@admin_bp.route('/skills/add', methods=['POST'])
@admin_required
def add_skill():
    """Admin: add a new master skill."""
    name        = request.form.get('name', '').strip()
    category    = request.form.get('category', '').strip()
    description = request.form.get('description', '').strip()

    if not name or not category:
        flash('Skill name and category are required.', 'warning')
    else:
        ok, err = profile_service.admin_add_skill(name, category, description)
        flash(f"Skill '{name}' added!" if ok else err, 'success' if ok else 'danger')
    return redirect(url_for('admin.skills'))


@admin_bp.route('/skills/edit/<int:skill_id>', methods=['POST'])
@admin_required
def edit_skill(skill_id):
    """Admin: edit an existing skill."""
    name        = request.form.get('name', '').strip()
    category    = request.form.get('category', '').strip()
    description = request.form.get('description', '').strip()

    ok, err = profile_service.admin_update_skill(skill_id, name, category, description)
    flash('Skill updated.' if ok else err, 'success' if ok else 'danger')
    return redirect(url_for('admin.skills'))


@admin_bp.route('/skills/delete/<int:skill_id>', methods=['POST'])
@admin_required
def delete_skill(skill_id):
    """
    Admin: delete a skill.
    If in use by students, returns a friendly message instead of crashing.
    """
    ok, err = profile_service.admin_delete_skill(skill_id)
    flash('Skill deleted.' if ok else err, 'info' if ok else 'warning')
    return redirect(url_for('admin.skills'))


# ── Alias management ──────────────────────────────────────────────────────────

@admin_bp.route('/skills/<int:skill_id>/alias/add', methods=['POST'])
@admin_required
def add_alias(skill_id):
    """Admin: add an alias to a skill."""
    alias_name = request.form.get('alias_name', '').strip()
    if not alias_name:
        flash('Alias name cannot be empty.', 'warning')
    else:
        ok, err = profile_service.admin_add_alias(skill_id, alias_name)
        flash('Alias added.' if ok else err, 'success' if ok else 'danger')
    return redirect(url_for('admin.skills') + f'#skill-{skill_id}')


@admin_bp.route('/skills/alias/delete/<int:alias_id>', methods=['POST'])
@admin_required
def delete_alias(alias_id):
    """Admin: delete a skill alias."""
    ok, err = profile_service.admin_delete_alias(alias_id)
    flash('Alias removed.' if ok else err, 'info' if ok else 'danger')
    return redirect(url_for('admin.skills'))


# ════════════════════════════════════════════════════════════════════════════════
#  STUDENT LIST + DETAIL (read-only)
# ════════════════════════════════════════════════════════════════════════════════

@admin_bp.route('/students')
@admin_required
def students():
    """
    Searchable list of all students with profile completion %.
    Filters: name, roll number, branch.
    """
    q      = request.args.get('q', '').strip()
    branch = request.args.get('branch', '').strip()

    query = Student.query
    if q:
        query = query.filter(
            (Student.full_name.ilike(f'%{q}%')) |
            (Student.roll_number.ilike(f'%{q}%'))
        )
    if branch:
        query = query.filter_by(branch=branch)

    students_list = query.order_by(Student.full_name).all()

    # Get unique branches for filter dropdown
    branches = [b[0] for b in Student.query.with_entities(Student.branch).distinct().all() if b[0]]

    return render_template(
        'admin/students.html',
        title         = 'Manage Students',
        students      = students_list,
        branches      = sorted(branches),
        q             = q,
        active_branch = branch,
    )


@admin_bp.route('/students/<int:student_id>')
@admin_required
def student_detail(student_id):
    """Read-only detail view for a single student."""
    from flask import abort as _abort
    student = Student.query.get_or_404(student_id)
    completion = profile_service.calculate_profile_completion(student)
    return render_template(
        'admin/student_detail.html',
        title      = f'Student — {student.full_name}',
        student    = student,
        completion = completion,
    )


# ════════════════════════════════════════════════════════════════════════════════
#  JOB ROLES MANAGEMENT (Phase 7)
# ════════════════════════════════════════════════════════════════════════════════

@admin_bp.route('/job-roles', methods=['GET'])
@admin_required
def job_roles():
    """List job roles with search query and add/edit modal form."""
    q = request.args.get('q', '').strip()
    roles = job_service.get_all_roles(search=q)
    form = JobRoleForm()
    return render_template(
        'admin/job_roles.html',
        title='Job Roles',
        roles=roles,
        form=form,
        q=q
    )


@admin_bp.route('/job-roles/create', methods=['POST'])
@admin_required
def create_job_role():
    """Create a new job role."""
    form = JobRoleForm()
    if form.validate_on_submit():
        ok, msg, _ = job_service.create_role(
            title=form.title.data,
            department=form.department.data,
            description=form.description.data
        )
        flash(msg, 'success' if ok else 'danger')
    else:
        for _, errors in form.errors.items():
            for error in errors:
                flash(error, 'danger')
    return redirect(url_for('admin.job_roles'))


@admin_bp.route('/job-roles/<int:role_id>/edit', methods=['POST'])
@admin_required
def edit_job_role(role_id: int):
    """Edit an existing job role."""
    form = JobRoleForm()
    if form.validate_on_submit():
        ok, msg, _ = job_service.update_role(
            role_id=role_id,
            title=form.title.data,
            department=form.department.data,
            description=form.description.data
        )
        flash(msg, 'success' if ok else 'danger')
    else:
        for _, errors in form.errors.items():
            for error in errors:
                flash(error, 'danger')
    return redirect(url_for('admin.job_roles'))


@admin_bp.route('/job-roles/<int:role_id>/delete', methods=['POST'])
@admin_required
def delete_job_role(role_id: int):
    """Delete a job role safely. If role is in use, block deletion with a warning."""
    ok, msg = job_service.delete_role(role_id)
    flash(msg, 'success' if ok else 'warning')
    return redirect(url_for('admin.job_roles'))


# ════════════════════════════════════════════════════════════════════════════════
#  JOB DESCRIPTIONS MANAGEMENT (Phase 7)
# ════════════════════════════════════════════════════════════════════════════════

@admin_bp.route('/jobs', methods=['GET'])
@admin_required
def jobs():
    """List job postings with search and role filter."""
    q = request.args.get('q', '').strip()
    role_id = request.args.get('role_id', type=int)

    all_jobs = job_service.get_all_jobs(search=q, role_id=role_id)
    roles = job_service.get_all_roles()

    return render_template(
        'admin/jobs.html',
        title='Manage Jobs',
        jobs=all_jobs,
        roles=roles,
        q=q,
        active_role_id=role_id
    )


@admin_bp.route('/jobs/create', methods=['GET', 'POST'])
@admin_required
def create_job():
    """
    Create a new job description.
    On save, auto-extracts skills and redirects to the skill review screen.
    """
    form = JobDescriptionForm()
    roles = job_service.get_all_roles()
    form.job_role_id.choices = [(r.id, r.title) for r in roles]

    if not roles:
        flash("Please create at least one Job Role before adding a job description.", "warning")
        return redirect(url_for('admin.job_roles'))

    if form.validate_on_submit():
        ok, msg, job = job_service.create_job(form.data)
        if ok:
            flash("Job details saved! Please review the auto-extracted required skills below.", "success")
            return redirect(url_for('admin.job_skills_review', job_id=job.id))
        else:
            flash(msg, "danger")

    return render_template(
        'admin/job_form.html',
        title='Post New Job',
        form=form,
        is_edit=False
    )


@admin_bp.route('/jobs/<int:job_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_job(job_id: int):
    """
    Edit an existing job description.
    On save, redirects to the skill review screen so admin can re-review skills without duplicates.
    """
    job = job_service.get_job_by_id(job_id)
    if not job:
        abort(404)

    roles = job_service.get_all_roles()
    form = JobDescriptionForm(obj=job)
    form.job_role_id.choices = [(r.id, r.title) for r in roles]

    if form.validate_on_submit():
        ok, msg, _ = job_service.update_job(job_id, form.data)
        if ok:
            flash("Job details updated! Review required skills below.", "success")
            return redirect(url_for('admin.job_skills_review', job_id=job.id))
        else:
            flash(msg, "danger")

    return render_template(
        'admin/job_form.html',
        title=f'Edit Job — {job.title}',
        form=form,
        job=job,
        is_edit=True
    )


@admin_bp.route('/jobs/<int:job_id>/skills', methods=['GET', 'POST'])
@admin_required
def job_skills_review(job_id: int):
    """
    Skill extraction review screen:
    - Lists auto-detected skills with pre-selected checkboxes
    - Importance dropdown (1 to 5, default 3)
      Scale: 1 Nice-to-have, 2 Desirable, 3 Required, 4 Highly Important, 5 Critical.
      (Phase 8 will use these weights for weighted match % computation.)
    - Dropdown to manually add any skill missed by extraction
    - Atomic save avoiding any duplicate uq_job_skill constraint errors.
    """
    job = job_service.get_job_by_id(job_id)
    if not job:
        abort(404)

    if request.method == 'POST':
        selected_ids = request.form.getlist('skill_ids', type=int)
        selections = []

        # Collect checked skills with importance weights
        for sid in selected_ids:
            weight = request.form.get(f'importance_{sid}', 3, type=int)
            selections.append({'skill_id': sid, 'importance_weight': weight})

        # Check for any manually added skill
        manual_sid = request.form.get('manual_skill_id', type=int)
        manual_weight = request.form.get('manual_importance', 3, type=int)
        if manual_sid:
            selections.append({'skill_id': manual_sid, 'importance_weight': manual_weight})

        if not selections:
            flash("No skills were selected. Please select at least one required skill or add one manually.", "warning")
            return redirect(url_for('admin.job_skills_review', job_id=job.id))

        ok, msg, count = job_service.save_job_skills(job.id, selections)
        if ok:
            flash(f"Successfully configured {count} required skill(s) for '{job.title}'.", "success")
            return redirect(url_for('admin.jobs'))
        else:
            flash(msg, "danger")
            return redirect(url_for('admin.job_skills_review', job_id=job.id))

    # GET request: extract skills from text
    extracted = job_service.extract_job_skills(job.description_text)
    existing_skills_map = {js.skill_id: js.importance_weight for js in job.job_skills}

    # Build review list of skills
    detected_ids = set()
    review_items = []

    for item in extracted:
        sid = item.get('skill_id')
        if sid:
            detected_ids.add(sid)
            review_items.append({
                'skill_id': sid,
                'name': item.get('canonical_name') or item.get('name'),
                'category': item.get('category', 'General'),
                'count': item.get('count', 1),
                'importance': existing_skills_map.get(sid, 3),
                'is_existing': sid in existing_skills_map
            })

    # Also include existing skills that might not have been in the extracted list
    for js in job.job_skills:
        if js.skill_id not in detected_ids:
            review_items.append({
                'skill_id': js.skill_id,
                'name': js.skill.name,
                'category': js.skill.category or 'General',
                'count': 1,
                'importance': js.importance_weight,
                'is_existing': True
            })

    all_master_skills = Skill.query.order_by(Skill.name.asc()).all()

    return render_template(
        'admin/job_skills_review.html',
        title=f'Review Skills — {job.title}',
        job=job,
        review_items=review_items,
        importance_choices=IMPORTANCE_CHOICES,
        master_skills=all_master_skills
    )


@admin_bp.route('/jobs/<int:job_id>/delete', methods=['POST'])
@admin_required
def delete_job(job_id: int):
    """Delete a job posting."""
    ok, msg = job_service.delete_job(job_id)
    flash(msg, 'success' if ok else 'danger')
    return redirect(url_for('admin.jobs'))


# ════════════════════════════════════════════════════════════════════════════════
#  COURSES MANAGEMENT (Phase 10)
# ════════════════════════════════════════════════════════════════════════════════

from extensions import db as _db_ext
from models.course import Course, CourseSkill


def _validate_course_fields(title, url, duration_str, rating_str):
    """Validate course fields. Returns (errors_list, duration_float, rating_float)."""
    errors = []
    duration = None
    rating = None

    if not title or not title.strip():
        errors.append("Title is required.")

    if url and url.strip():
        if not (url.strip().startswith('http://') or url.strip().startswith('https://')):
            errors.append("URL must start with http:// or https://")

    if duration_str and duration_str.strip():
        try:
            duration = float(duration_str)
            if duration <= 0:
                errors.append("Duration must be a positive number.")
        except ValueError:
            errors.append("Duration must be a number (e.g. 12.5 hours).")

    if rating_str and rating_str.strip():
        try:
            rating = float(rating_str)
            if not (0 <= rating <= 5):
                errors.append("Rating must be between 0 and 5.")
        except ValueError:
            errors.append("Rating must be a number between 0 and 5.")

    return errors, duration, rating


@admin_bp.route('/courses')
@admin_required
def courses():
    """
    Admin: list all courses with search + difficulty filter.
    All skills are passed to the template for the multi-select tagging form.
    """
    from extensions import db as _db
    q = request.args.get('q', '').strip()
    diff_filter = request.args.get('diff', '').strip()

    query = Course.query
    if q:
        query = query.filter(Course.title.ilike(f'%{q}%'))
    if diff_filter in ('Beginner', 'Intermediate', 'Advanced'):
        query = query.filter(Course.difficulty_level == diff_filter)

    course_list = query.order_by(Course.title).all()
    all_skills = Skill.query.order_by(Skill.name).all()

    # Pre-load skill tags per course for display (no N+1: use dict built from course_skills)
    course_skill_map = {}
    for cs in CourseSkill.query.all():
        course_skill_map.setdefault(cs.course_id, set()).add(cs.skill_id)

    return render_template(
        'admin/courses.html',
        title='Manage Courses',
        courses=course_list,
        all_skills=all_skills,
        course_skill_map=course_skill_map,
        q=q,
        diff_filter=diff_filter,
    )


@admin_bp.route('/courses/create', methods=['POST'])
@admin_required
def create_course():
    """Create a new course and tag it with selected skills."""
    from extensions import db as _db

    title       = request.form.get('title', '').strip()
    provider    = request.form.get('provider', '').strip()
    difficulty  = request.form.get('difficulty_level', 'Beginner').strip()
    url         = request.form.get('url', '').strip()
    description = request.form.get('description', '').strip()
    duration_str= request.form.get('duration_hours', '').strip()
    rating_str  = request.form.get('rating', '').strip()
    skill_ids   = request.form.getlist('skill_ids')   # multi-select returns list

    errors, duration, rating = _validate_course_fields(title, url, duration_str, rating_str)
    if errors:
        for e in errors:
            flash(e, 'danger')
        return redirect(url_for('admin.courses'))

    try:
        course = Course(
            title=title,
            provider=provider or None,
            difficulty_level=difficulty,
            url=url or None,
            description=description or None,
            duration_hours=duration,
            rating=rating,
        )
        _db.session.add(course)
        _db.session.flush()  # Get course.id

        # Tag with selected skills (unique constraint handles duplicates)
        for sid_str in skill_ids:
            try:
                sid = int(sid_str)
                _db.session.add(CourseSkill(course_id=course.id, skill_id=sid))
            except (ValueError, Exception):
                pass

        _db.session.commit()
        flash(f'Course "{course.title}" created successfully.', 'success')
    except Exception as e:
        _db.session.rollback()
        flash(f'Error creating course: {str(e)}', 'danger')

    return redirect(url_for('admin.courses'))


@admin_bp.route('/courses/<int:course_id>/edit', methods=['POST'])
@admin_required
def edit_course(course_id: int):
    """Edit an existing course and REPLACE its skill tags (no duplicates)."""
    from extensions import db as _db

    course = _db.session.get(Course, course_id)
    if not course:
        flash('Course not found.', 'danger')
        return redirect(url_for('admin.courses'))

    title       = request.form.get('title', '').strip()
    provider    = request.form.get('provider', '').strip()
    difficulty  = request.form.get('difficulty_level', 'Beginner').strip()
    url         = request.form.get('url', '').strip()
    description = request.form.get('description', '').strip()
    duration_str= request.form.get('duration_hours', '').strip()
    rating_str  = request.form.get('rating', '').strip()
    skill_ids   = request.form.getlist('skill_ids')

    errors, duration, rating = _validate_course_fields(title, url, duration_str, rating_str)
    if errors:
        for e in errors:
            flash(e, 'danger')
        return redirect(url_for('admin.courses'))

    try:
        # Update course fields
        course.title           = title
        course.provider        = provider or None
        course.difficulty_level= difficulty
        course.url             = url or None
        course.description     = description or None
        course.duration_hours  = duration
        course.rating          = rating

        # Replace skill tags: delete existing then re-insert
        # Cascade on the relationship handles deletion; we use direct query for efficiency
        CourseSkill.query.filter_by(course_id=course.id).delete()
        _db.session.flush()

        # Re-insert new tags (unique constraint prevents duplicates)
        seen = set()
        for sid_str in skill_ids:
            try:
                sid = int(sid_str)
                if sid not in seen:
                    seen.add(sid)
                    _db.session.add(CourseSkill(course_id=course.id, skill_id=sid))
            except (ValueError, Exception):
                pass

        _db.session.commit()
        flash(f'Course "{course.title}" updated successfully.', 'success')
    except Exception as e:
        _db.session.rollback()
        flash(f'Error updating course: {str(e)}', 'danger')

    return redirect(url_for('admin.courses'))


@admin_bp.route('/courses/<int:course_id>/delete', methods=['POST'])
@admin_required
def delete_course(course_id: int):
    """Delete a course. course_skills rows cascade automatically."""
    from extensions import db as _db

    course = _db.session.get(Course, course_id)
    if not course:
        flash('Course not found.', 'danger')
        return redirect(url_for('admin.courses'))

    try:
        title = course.title
        _db.session.delete(course)
        _db.session.commit()
        flash(f'Course "{title}" deleted successfully.', 'success')
    except Exception as e:
        _db.session.rollback()
        flash(f'Error deleting course: {str(e)}', 'danger')

    return redirect(url_for('admin.courses'))


# ════════════════════════════════════════════════════════════════════════════════
#  PHASE 12: EMPLOYMENT OUTCOMES TRACKING (ADMIN)
# ════════════════════════════════════════════════════════════════════════════════

@admin_bp.route('/employment', methods=['GET'])
@admin_required
def employment():
    """
    Searchable, filterable list of all students' employment outcomes.
    Summary cards computed using Pandas.
    """
    from services import employment_service

    page = request.args.get('page', 1, type=int)
    filters = {
        'status': request.args.get('status', '').strip(),
        'branch': request.args.get('branch', '').strip(),
        'role':   request.args.get('role', '').strip(),
        'search': request.args.get('search', '').strip(),
    }

    admin_data = employment_service.get_all_outcomes_for_admin(
        filters=filters,
        page=page,
        per_page=20
    )

    return render_template(
        'admin/employment.html',
        title='Employment Outcomes Tracking',
        records=admin_data['records'],
        summary=admin_data['summary'],
        pagination=admin_data['pagination'],
        filters=admin_data['filters'],
        available_branches=admin_data['available_branches'],
        available_roles=admin_data['available_roles'],
    )


@admin_bp.route('/employment/<int:student_id>', methods=['POST'])
@admin_required
def save_employment_outcome(student_id: int):
    """Admin record or update employment outcome for any student."""
    from services import employment_service
    from flask_login import current_user

    form_data = {
        'status':             request.form.get('status'),
        'company_name':       request.form.get('company_name'),
        'role_title':         request.form.get('role_title'),
        'salary_package_lpa': request.form.get('salary_package_lpa'),
        'placement_date':     request.form.get('placement_date'),
        'placement_type':     request.form.get('placement_type'),
        'notes':              request.form.get('notes'),
        'skills_used':        request.form.getlist('skills_used'),
    }

    ok, result = employment_service.save_outcome(
        student_id=student_id,
        data=form_data,
        current_user=current_user
    )

    if ok:
        flash("Employment outcome saved successfully.", "success")
    else:
        flash(f"Validation Error: {result}", "danger")

    return redirect(url_for('admin.employment'))


@admin_bp.route('/employment/<int:student_id>/delete', methods=['POST'])
@admin_required
def delete_employment_outcome(student_id: int):
    """Admin delete employment outcome for a student."""
    from services import employment_service
    from flask_login import current_user

    ok, err = employment_service.delete_outcome(
        student_id=student_id,
        current_user=current_user
    )

    if ok:
        flash("Employment outcome record removed.", "info")
    else:
        flash(f"Error: {err}", "danger")

    return redirect(url_for('admin.employment'))


@admin_bp.route('/employment/export-csv', methods=['GET'])
@admin_required
def export_employment_csv():
    """Export filtered table of employment outcomes as sanitized CSV."""
    from flask import Response
    from services import employment_service

    filters = {
        'status': request.args.get('status', '').strip(),
        'branch': request.args.get('branch', '').strip(),
        'role':   request.args.get('role', '').strip(),
        'search': request.args.get('search', '').strip(),
    }

    csv_content = employment_service.export_outcomes_to_csv(filters=filters)

    return Response(
        csv_content,
        mimetype='text/csv',
        headers={
            'Content-Disposition': 'attachment; filename=employment_outcomes.csv',
            'Content-Type': 'text/csv; charset=utf-8'
        }
    )


# ════════════════════════════════════════════════════════════════════════════════
#  PHASE 14: ML MODEL MANAGEMENT & METRICS
# ════════════════════════════════════════════════════════════════════════════════

@admin_bp.route('/model', methods=['GET'])
@admin_required
def model_management():
    """
    Admin model management console:
    Displays model version, mode (Real vs Demo), evaluation metrics (Accuracy,
    Precision, Recall, F1, 5-fold CV), Confusion Matrix, Feature Importances,
    and threshold gate indicator (< 100 real outcomes).
    """
    from ml import employment_model
    from models.outcome import EmploymentOutcome

    model_info = employment_model.get_model_info()
    if not model_info.get('available'):
        # Auto-train if first visit
        employment_model.ensure_model_trained()
        model_info = employment_model.get_model_info()

    # Current database count of labeled outcomes
    current_labeled_count = (
        EmploymentOutcome.query
        .filter(EmploymentOutcome.status.in_(['Placed', 'Not Placed']))
        .count()
    )

    return render_template(
        'admin/model.html',
        title='ML Model Management',
        model_info=model_info,
        current_labeled_count=current_labeled_count,
        real_data_threshold=100,
    )


@admin_bp.route('/model/retrain', methods=['POST'])
@admin_required
def model_retrain():
    """Trigger manual retraining of the employment classifier."""
    from ml.train_model import train_and_save

    try:
        bundle = train_and_save()
        mode = bundle.get('mode', 'demo')
        acc = bundle.get('metrics', {}).get('accuracy', 0.0)
        flash(f"Model successfully retrained! Mode: {mode.upper()} | Accuracy: {acc*100:.1f}%", 'success')
    except Exception as exc:
        flash(f"Retraining failed: {exc}", 'danger')

    return redirect(url_for('admin.model_management'))


