"""generate_stubs.py — Creates placeholder page templates for Phase 3."""
import os

pages = [
    ('templates/student/profile.html',      'My Profile',         'person-lines-fill',   'Complete your profile with education, skills, certifications and projects.',     'Phase 5'),
    ('templates/student/resume_upload.html','Upload Resume',       'file-earmark-arrow-up','Upload your PDF or DOCX resume for automatic skill extraction.',              'Phase 8'),
    ('templates/student/skill_gap.html',    'Skill Gap Analysis',  'bar-chart-gaps',      'Compare your skills vs job requirements — see coverage % and cosine match.',   'Phase 13'),
    ('templates/student/job_matching.html', 'Job Matching',        'briefcase',            'Find best-fit job roles with transparent similarity scores.',                  'Phase 14'),
    ('templates/student/learning_path.html','Learning Path',       'map',                  'Your personalized learning roadmap with phase-by-phase skill targets.',        'Phase 16'),
    ('templates/student/outcome.html',      'Employment Status',   'building-check',       'Record and track your placement outcome.',                                     'Phase 17'),
    ('templates/admin/students.html',       'Manage Students',     'people',               'View, search and manage all student profiles and outcomes.',                   'Phase 7'),
    ('templates/admin/jobs.html',           'Manage Jobs',         'briefcase',            'Add, edit and manage job roles and job descriptions.',                         'Phase 11'),
    ('templates/admin/skills.html',         'Manage Skills',       'tags',                 'Manage canonical skill dictionary and alias mappings.',                        'Phase 6'),
    ('templates/admin/courses.html',        'Manage Courses',      'journal-bookmark',     'Add and manage the course catalog for recommendations.',                       'Phase 15'),
]

STUB = """\
{{% extends "base.html" %}}
{{% block content %}}
<div class="animate-in">
    <div class="d-flex justify-content-between align-items-center mb-4">
        <h2 class="fw-700 mb-0" style="font-size:22px;">{title}</h2>
    </div>
    <div class="coming-soon-card">
        <div class="coming-soon-icon"><i class="bi bi-{icon}"></i></div>
        <h3 class="coming-soon-title">{title} &mdash; {phase}</h3>
        <p class="coming-soon-sub">{desc}</p>
    </div>
</div>
{{% endblock %}}
"""

for path, title, icon, desc, phase in pages:
    content = STUB.format(title=title, icon=icon, desc=desc, phase=phase)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f'  [OK] {path}')

print('All stub templates created.')
