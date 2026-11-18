"""
seed_forum.py
─────────────
Idempotent seed script to initialize forum categories and synthetic demo discussions.
Safe to run multiple times without duplicating data or altering existing threads.

Includes:
- 6 standard placement & community categories
- 9 realistic demo threads with replies written by demo student & admin users
- Clear [Demo] prefix on all seeded discussions

Usage:
    python seed_forum.py
"""

import os
import sys
from datetime import datetime, timedelta

# Allow running from project root
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if THIS_DIR not in sys.path:
    sys.path.insert(0, THIS_DIR)

from app import create_app
from extensions import db
from models.user import User
from models.skill import Skill
from models.forum import ForumCategory, ForumThread, ForumPost, ForumPostLike


FORUM_CATEGORIES = [
    {
        'name': 'General Discussion',
        'slug': 'general-discussion',
        'description': 'Open campus discussions, announcements, and general career advice.',
        'sort_order': 1
    },
    {
        'name': 'Placement Preparation',
        'slug': 'placement-preparation',
        'description': 'Aptitude, DSA roadmaps, mock tests, and placement strategy tips.',
        'sort_order': 2
    },
    {
        'name': 'Skills & Learning',
        'slug': 'skills-learning',
        'description': 'Deep dives into programming languages, cloud, web frameworks, and data tools.',
        'sort_order': 3
    },
    {
        'name': 'Companies & Interviews',
        'slug': 'companies-interviews',
        'description': 'Interview rounds, HR questions, STAR technique, and recruitment trends.',
        'sort_order': 4
    },
    {
        'name': 'Projects & Resumes',
        'slug': 'projects-resumes',
        'description': 'Resume reviews, portfolio architectures, and capstone project feedback.',
        'sort_order': 5
    },
    {
        'name': 'Help & Feedback',
        'slug': 'help-feedback',
        'description': 'Platform suggestions, bug reports, and navigation support.',
        'sort_order': 6
    }
]


def seed_forum(app=None):
    """
    Idempotent seeding of forum categories and demo threads/replies.
    Safe to run repeatedly.
    """
    if app is None:
        app = create_app()

    with app.app_context():
        print("-- Seeding Forum Categories & Demo Discussions --------------")

        # ── 0. Create Tables If Missing ───────────────────────────────────────
        db.create_all()

        # ── 1. Seed Categories ────────────────────────────────────────────────
        cat_map = {}
        for c_data in FORUM_CATEGORIES:
            cat = ForumCategory.query.filter_by(slug=c_data['slug']).first()
            if not cat:
                cat = ForumCategory(
                    name=c_data['name'],
                    slug=c_data['slug'],
                    description=c_data['description'],
                    sort_order=c_data['sort_order']
                )
                db.session.add(cat)
                db.session.flush()
                print(f"[OK] Created category: {cat.name}")
            else:
                # Keep sort_order & description updated
                cat.description = c_data['description']
                cat.sort_order = c_data['sort_order']
            cat_map[c_data['slug']] = cat

        db.session.commit()

        # ── 2. Identify Demo Users ───────────────────────────────────────────
        admin_user = User.query.filter_by(role='admin').first()
        demo_students = User.query.filter_by(role='student').order_by(User.id.asc()).limit(6).all()

        if not admin_user and not demo_students:
            print("[SKIP] No users found in database. Seed users first before seeding forum demo posts.")
            return

        u_admin = admin_user
        u_s1 = demo_students[0] if len(demo_students) > 0 else admin_user
        u_s2 = demo_students[1] if len(demo_students) > 1 else u_s1
        u_s3 = demo_students[2] if len(demo_students) > 2 else u_s1
        u_s4 = demo_students[3] if len(demo_students) > 3 else u_s2
        u_s5 = demo_students[4] if len(demo_students) > 4 else u_s3

        # Optional skill tags lookup
        python_skill = Skill.query.filter(db.func.lower(Skill.name) == 'python').first()
        sql_skill = Skill.query.filter(db.func.lower(Skill.name) == 'sql').first()

        now = datetime.utcnow()

        demo_threads_spec = [
            {
                'category_slug': 'general-discussion',
                'author': u_admin,
                'title': '[Demo] Welcome to the SkillGap Open Discussion Forum!',
                'body': (
                    "Welcome to our campus open discussion forum!\n\n"
                    "Here students can exchange interview preparation strategies, ask questions about skills and courses, "
                    "share tips for hiring drives, and collaborate with peers and faculty.\n\n"
                    "Please remember to keep all discussions constructive and follow our Community Guidelines:\n"
                    "• Be respectful and supportive of your fellow peers.\n"
                    "• Do not share confidential exam/interview questions or personal contact details.\n"
                    "• Use clear titles and categorize your threads correctly."
                ),
                'is_pinned': True,
                'skill_id': None,
                'time_offset_hours': 48,
                'replies': [
                    (u_s1, "Thank you! Looking forward to learning from seniors and sharing prep resources.", 46),
                    (u_s2, "Great initiative! Having a centralized campus forum for placement discussions is super helpful.", 44)
                ]
            },
            {
                'category_slug': 'placement-preparation',
                'author': u_s1,
                'title': '[Demo] Core Data Structures and Algorithms Roadmap for Campus Placements',
                'body': (
                    "What is the most effective roadmap to prepare for DSA technical rounds within 3 to 4 months?\n\n"
                    "Should one focus primarily on LeetCode patterns (Sliding Window, Two Pointers, Graphs, Dynamic Programming) "
                    "or dive deep into competitive programming? Any guidance from seniors and mentors would be immensely appreciated!"
                ),
                'is_pinned': False,
                'skill_id': python_skill.id if python_skill else None,
                'time_offset_hours': 36,
                'replies': [
                    (u_admin, "Focus on mastering core patterns: Two Pointers, Sliding Window, BFS/DFS, and Dynamic Programming. Solving 150-200 curated problems with deep understanding is far better than rushing through 500 without pattern recognition.", 32),
                    (u_s3, "NeetCode 150 and Striver SDE Sheet helped me tremendously. Don't skip time and space complexity analysis on whiteboards!", 28)
                ]
            },
            {
                'category_slug': 'skills-learning',
                'author': u_s2,
                'title': '[Demo] Recommended resources for mastering SQL and Database Design',
                'body': (
                    "Many software engineering and data analyst roles emphasize practical SQL knowledge beyond basic SELECT queries.\n\n"
                    "What platforms or project tutorials do you recommend for practicing Window Functions (ROW_NUMBER, RANK, LEAD/LAG), "
                    "indexing strategies, and query plan optimization?"
                ),
                'is_pinned': False,
                'skill_id': sql_skill.id if sql_skill else None,
                'time_offset_hours': 30,
                'replies': [
                    (u_s4, "Mode Analytics SQL tutorials and SQLZoo are great. Also, designing a normalized schema for an e-commerce or booking system will teach you indexing better than toy problems.", 26)
                ]
            },
            {
                'category_slug': 'companies-interviews',
                'author': u_admin,
                'title': '[Demo] Structuring behavioral and HR interview answers using the STAR method',
                'body': (
                    "A reminder for all students appearing for campus interviews:\n\n"
                    "When answering behavioral questions ('Tell me about a time you handled a project setback', 'Describe a conflict with a team member'), "
                    "structure your responses using the STAR method:\n"
                    "• Situation: Set the scene briefly\n"
                    "• Task: Describe what your responsibility was\n"
                    "• Action: Explain the specific steps YOU took\n"
                    "• Result: Share the measurable outcome and key learning\n\n"
                    "Keep answers concise (under 2 minutes) and always speak positively about teamwork."
                ),
                'is_pinned': False,
                'skill_id': None,
                'time_offset_hours': 24,
                'replies': [
                    (u_s1, "Practicing STAR stories with a mock partner really helped me avoid rambling during HR rounds.", 20)
                ]
            },
            {
                'category_slug': 'projects-resumes',
                'author': u_s3,
                'title': '[Demo] What makes an engineering resume stand out to technical recruiters?',
                'body': (
                    "Should student resumes prioritize coursework, hackathon achievements, or personal full-stack projects?\n\n"
                    "What format works best for campus placements, and how many bullet points should we dedicate to each project?"
                ),
                'is_pinned': False,
                'skill_id': None,
                'time_offset_hours': 18,
                'replies': [
                    (u_s5, "Keep it strictly to 1 page. Use clean LaTeX templates (like Jake's Resume). Put your best 2 full-stack projects with live GitHub links at the top.", 15),
                    (u_admin, "Make sure every project bullet uses strong action verbs and quantifies impact: 'Built REST API serving 500+ requests with JWT auth and 95% test coverage'.", 12)
                ]
            },
            {
                'category_slug': 'placement-preparation',
                'author': u_s4,
                'title': '[Demo] Preparing for System Design rounds as an entry-level candidate',
                'body': (
                    "For junior backend developer roles, system design questions are increasingly common.\n\n"
                    "How should beginners start without feeling overwhelmed by distributed systems concepts?"
                ),
                'is_pinned': False,
                'skill_id': None,
                'time_offset_hours': 14,
                'replies': [
                    (u_s2, "Start with Alex Xu's System Design Interview Volume 1. Understand caching (Redis), load balancing, and SQL vs NoSQL trade-offs.", 10)
                ]
            },
            {
                'category_slug': 'projects-resumes',
                'author': u_s5,
                'title': '[Demo] Production-ready capstone project ideas to showcase full-stack skills',
                'body': (
                    "Moving beyond simple todo list apps and weather dashboards:\n"
                    "What kind of capstone projects demonstrate genuine engineering depth to recruiters?"
                ),
                'is_pinned': False,
                'skill_id': python_skill.id if python_skill else None,
                'time_offset_hours': 10,
                'replies': [
                    (u_s1, "Build something with background workers, role-based authorization, rate limiting, and CI/CD pipelines. This demonstrates real-world software engineering practice.", 7)
                ]
            },
            {
                'category_slug': 'help-feedback',
                'author': u_admin,
                'title': '[Demo] How to effectively utilize the Skill Gap AI recommendation engine',
                'body': (
                    "Tip: Once you complete your student profile and list your current technical skills, "
                    "visit the Gap Analysis and Course Recommendations sections to identify missing prerequisites "
                    "for your target job roles."
                ),
                'is_pinned': False,
                'skill_id': None,
                'time_offset_hours': 6,
                'replies': [
                    (u_s3, "The gap analysis matched the prerequisites listed in recent job postings accurately. Thank you!", 4)
                ]
            },
            {
                'category_slug': 'skills-learning',
                'author': u_s1,
                'title': '[Demo] Transitioning from Python to Golang/Java for backend engineering',
                'body': (
                    "Many enterprise backend roles ask for Java/Spring Boot or Golang.\n\n"
                    "How steep is the transition for someone who is already comfortable with Python/Flask?"
                ),
                'is_pinned': False,
                'skill_id': None,
                'time_offset_hours': 3,
                'replies': [
                    (u_s4, "The biggest change is strict typing and concurrency models. REST architecture, ORMs, and database principles translate immediately.", 1)
                ]
            }
        ]

        # ── 3. Seed Threads and Replies ───────────────────────────────────────
        threads_created = 0
        posts_created = 0

        for t_spec in demo_threads_spec:
            cat = cat_map.get(t_spec['category_slug'])
            if not cat:
                continue

            author = t_spec['author']
            title = t_spec['title']

            existing_thread = ForumThread.query.filter_by(title=title).first()
            if existing_thread:
                continue

            t_created = now - timedelta(hours=t_spec['time_offset_hours'])
            thread = ForumThread(
                category_id=cat.id,
                user_id=author.id,
                title=title,
                body=t_spec['body'],
                skill_id=t_spec.get('skill_id'),
                is_pinned=t_spec.get('is_pinned', False),
                is_locked=False,
                is_deleted=False,
                created_at=t_created,
                updated_at=t_created,
                last_activity_at=t_created
            )
            db.session.add(thread)
            db.session.flush()
            threads_created += 1

            # Seed replies
            last_activity = t_created
            for replier, r_body, r_offset in t_spec.get('replies', []):
                r_created = now - timedelta(hours=r_offset)
                post = ForumPost(
                    thread_id=thread.id,
                    user_id=replier.id,
                    body=r_body,
                    is_deleted=False,
                    created_at=r_created,
                    edited_at=None
                )
                db.session.add(post)
                posts_created += 1
                if r_created > last_activity:
                    last_activity = r_created

            thread.last_activity_at = last_activity

        db.session.commit()
        print(f"[PASS] Forum seeding complete: {threads_created} threads, {posts_created} replies added.")


if __name__ == '__main__':
    seed_forum()
