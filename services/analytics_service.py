"""
services/analytics_service.py
───────────────────────────────
Helper analytics functions powered by Pandas for employment summary metrics and dashboards.
Phase 12: Basic summary cards for admin employment view.
Phase 13: Full Analytics Suite for Admin Dashboard and Student Personal Analytics.
All functions use Pandas, return JSON-serializable Python data structures,
and gracefully handle edge cases (empty tables, NaN safety, divide-by-zero).
"""

import io
import csv
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional, Union
import numpy as np
import pandas as pd
from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload

from extensions import db
from models.user import User
from models.student import Student, SkillProgress
from models.skill import Skill, StudentSkill
from models.job import JobRole, JobDescription, JobSkill
from models.gap import SkillGapAnalysis, GapSkill
from models.course import LearningPathItem
from models.outcome import EmploymentOutcome


# ════════════════════════════════════════════════════════════════════════════════
#  1. DATA NORMALIZATION & BASE DATAFRAME HELPERS
# ════════════════════════════════════════════════════════════════════════════════

def _to_dataframe(data: Union[pd.DataFrame, List[Dict[str, Any]], Any]) -> pd.DataFrame:
    """Normalize input into a pandas DataFrame, supporting dicts, DataFrames, and ORM objects."""
    if isinstance(data, pd.DataFrame):
        return data.copy()
    if isinstance(data, list):
        if not data:
            return pd.DataFrame()
        first = data[0]
        if isinstance(first, dict):
            return pd.DataFrame(data)
        # If items are SQLAlchemy ORM objects
        rows = []
        for obj in data:
            if hasattr(obj, '__table__'):
                row = {c.name: getattr(obj, c.name) for c in obj.__table__.columns}
                rows.append(row)
            elif hasattr(obj, '__dict__'):
                row = {k: v for k, v in obj.__dict__.items() if not k.startswith('_')}
                rows.append(row)
        return pd.DataFrame(rows)
    return pd.DataFrame()


def _sanitize_csv_cell(value: Any) -> str:
    """
    Prevent CSV Formula Injection (DDE attacks) by prepending a single quote
    if the text begins with dangerous characters (=, +, -, @, \t, \r).
    """
    if value is None:
        return ""
    val_str = str(value).strip()
    if val_str and val_str[0] in ('=', '+', '-', '@', '\t', '\r'):
        return f"'{val_str}"
    return val_str


def _get_student_outcome_df(filters: Optional[Dict[str, Any]] = None) -> pd.DataFrame:
    """
    Batch query students outer joined with employment outcomes into a single Pandas DataFrame.
    Applies branch and graduation year filters server-side.
    Guarantees that dashboard statistics match the Phase 12 employment summary.
    """
    filters = filters or {}
    branch = (filters.get('branch') or '').strip()
    year = filters.get('year') or filters.get('graduation_year')

    query = db.session.query(
        Student.id.label('student_id'),
        Student.full_name,
        Student.roll_number,
        Student.branch,
        Student.graduation_year,
        Student.cgpa,
        EmploymentOutcome.status,
        EmploymentOutcome.company_name,
        EmploymentOutcome.role_title,
        EmploymentOutcome.salary_package_lpa,
        EmploymentOutcome.placement_date,
        EmploymentOutcome.placement_type,
    ).outerjoin(
        EmploymentOutcome, Student.id == EmploymentOutcome.student_id
    )

    if branch and branch.lower() != 'all':
        query = query.filter(Student.branch == branch)
    if year and str(year).strip().lower() != 'all':
        try:
            query = query.filter(Student.graduation_year == int(year))
        except (ValueError, TypeError):
            pass

    records = [r._asdict() for r in query.all()]
    if not records:
        return pd.DataFrame(columns=[
            'student_id', 'full_name', 'roll_number', 'branch', 'graduation_year', 'cgpa',
            'status', 'company_name', 'role_title', 'salary_package_lpa', 'placement_date', 'placement_type'
        ])

    df = pd.DataFrame(records)
    df['status'] = df['status'].fillna('Unrecorded')
    df['salary_package_lpa'] = pd.to_numeric(df['salary_package_lpa'], errors='coerce')
    return df


# ════════════════════════════════════════════════════════════════════════════════
#  2. PHASE 12 COMPATIBLE METRICS
# ════════════════════════════════════════════════════════════════════════════════

def placement_percentage(data: Union[pd.DataFrame, List[Dict[str, Any]], Any]) -> float:
    """
    Compute percentage of placed students among total recorded students.
    Returns 0.0 if dataset is empty.
    """
    df = _to_dataframe(data)
    if df.empty or 'status' not in df.columns:
        return 0.0
    
    total = len(df)
    if total == 0:
        return 0.0
    
    placed = (df['status'] == 'Placed').sum()
    pct = (placed / total) * 100.0
    return round(float(pct), 1)


def average_salary(data: Union[pd.DataFrame, List[Dict[str, Any]], Any]) -> Optional[float]:
    """
    Compute average (mean) salary of placed students with valid positive salary.
    Returns None if no placed students have salary data.
    """
    df = _to_dataframe(data)
    if df.empty or 'status' not in df.columns or 'salary_package_lpa' not in df.columns:
        return None

    placed_sal = pd.to_numeric(
        df[df['status'] == 'Placed']['salary_package_lpa'],
        errors='coerce'
    ).dropna()
    placed_sal = placed_sal[placed_sal > 0]

    if placed_sal.empty:
        return None

    return round(float(placed_sal.mean()), 2)


def median_salary(data: Union[pd.DataFrame, List[Dict[str, Any]], Any]) -> Optional[float]:
    """
    Compute median salary of placed students with valid positive salary.
    Returns None if no placed students have salary data.
    """
    df = _to_dataframe(data)
    if df.empty or 'status' not in df.columns or 'salary_package_lpa' not in df.columns:
        return None

    placed_sal = pd.to_numeric(
        df[df['status'] == 'Placed']['salary_package_lpa'],
        errors='coerce'
    ).dropna()
    placed_sal = placed_sal[placed_sal > 0]

    if placed_sal.empty:
        return None

    return round(float(placed_sal.median()), 2)


def compute_employment_summary(data: Union[pd.DataFrame, List[Dict[str, Any]], Any]) -> Dict[str, Any]:
    """
    Calculate summary card statistics for admin dashboard using Pandas.
    Returns dictionary with numeric and formatted display values.
    """
    df = _to_dataframe(data)
    if df.empty:
        return {
            'total_students': 0,
            'placed_count': 0,
            'placement_pct': 0.0,
            'avg_salary': None,
            'median_salary': None,
            'avg_salary_display': 'N/A',
            'median_salary_display': 'N/A',
        }

    total_count = len(df)
    placed_mask = df['status'] == 'Placed' if 'status' in df.columns else pd.Series(False, index=df.index)
    placed_count = int(placed_mask.sum())
    
    pct = round((placed_count / total_count * 100.0), 1) if total_count > 0 else 0.0
    avg_sal = average_salary(df)
    med_sal = median_salary(df)

    return {
        'total_students': total_count,
        'placed_count': placed_count,
        'placement_pct': pct,
        'avg_salary': avg_sal,
        'median_salary': med_sal,
        'avg_salary_display': f"{avg_sal:.2f} LPA" if avg_sal is not None else 'N/A',
        'median_salary_display': f"{med_sal:.2f} LPA" if med_sal is not None else 'N/A',
    }


# ════════════════════════════════════════════════════════════════════════════════
#  3. PHASE 13 ANALYTICS FUNCTIONS
# ════════════════════════════════════════════════════════════════════════════════

def placement_summary(filters: Optional[Dict[str, Any]] = None, df: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
    """
    Returns breakdown of placement status: total students, count per status, and placement %.
    Safe against empty datasets.
    """
    if df is None:
        df = _get_student_outcome_df(filters)

    total_students = len(df)
    if total_students == 0:
        return {
            'total_students': 0,
            'placed_count': 0,
            'in_progress_count': 0,
            'not_placed_count': 0,
            'unrecorded_count': 0,
            'placement_pct': 0.0,
            'chart_data': {
                'labels': ['Placed', 'In Progress', 'Not Placed', 'Unrecorded'],
                'values': [0, 0, 0, 0],
            }
        }

    placed = int((df['status'] == 'Placed').sum())
    in_prog = int((df['status'] == 'In Progress').sum())
    not_pl = int((df['status'] == 'Not Placed').sum())
    unrec = int((df['status'] == 'Unrecorded').sum())
    pct = round((placed / total_students * 100.0), 1) if total_students > 0 else 0.0

    return {
        'total_students': total_students,
        'placed_count': placed,
        'in_progress_count': in_prog,
        'not_placed_count': not_pl,
        'unrecorded_count': unrec,
        'placement_pct': pct,
        'chart_data': {
            'labels': ['Placed', 'In Progress', 'Not Placed', 'Unrecorded'],
            'values': [placed, in_prog, not_pl, unrec],
        }
    }


def salary_stats(filters: Optional[Dict[str, Any]] = None, df: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
    """
    Compute average, median, min, max of placed students with valid positive salary.
    Also creates salary distribution histogram bins (0-3, 3-5, 5-8, 8-12, 12+ LPA).
    Unit documented: INR Lakhs Per Annum (LPA).
    """
    if df is None:
        df = _get_student_outcome_df(filters)

    empty_bins = [
        {'label': '0-3 LPA', 'count': 0},
        {'label': '3-5 LPA', 'count': 0},
        {'label': '5-8 LPA', 'count': 0},
        {'label': '8-12 LPA', 'count': 0},
        {'label': '12+ LPA', 'count': 0},
    ]

    if df.empty or 'status' not in df.columns or 'salary_package_lpa' not in df.columns:
        return {
            'average': None,
            'median': None,
            'min': None,
            'max': None,
            'average_display': 'N/A',
            'median_display': 'N/A',
            'min_display': 'N/A',
            'max_display': 'N/A',
            'bins': empty_bins,
            'unit': 'INR LPA',
        }

    placed_sal = df[(df['status'] == 'Placed') & (df['salary_package_lpa'] > 0)]['salary_package_lpa']
    if placed_sal.empty:
        return {
            'average': None,
            'median': None,
            'min': None,
            'max': None,
            'average_display': 'N/A',
            'median_display': 'N/A',
            'min_display': 'N/A',
            'max_display': 'N/A',
            'bins': empty_bins,
            'unit': 'INR LPA',
        }

    avg_val = round(float(placed_sal.mean()), 2)
    med_val = round(float(placed_sal.median()), 2)
    min_val = round(float(placed_sal.min()), 2)
    max_val = round(float(placed_sal.max()), 2)

    # Bin counts
    b0_3 = int(((placed_sal >= 0.0) & (placed_sal < 3.0)).sum())
    b3_5 = int(((placed_sal >= 3.0) & (placed_sal < 5.0)).sum())
    b5_8 = int(((placed_sal >= 5.0) & (placed_sal < 8.0)).sum())
    b8_12 = int(((placed_sal >= 8.0) & (placed_sal < 12.0)).sum())
    b12_plus = int((placed_sal >= 12.0).sum())

    bins = [
        {'label': '0-3 LPA', 'count': b0_3},
        {'label': '3-5 LPA', 'count': b3_5},
        {'label': '5-8 LPA', 'count': b5_8},
        {'label': '8-12 LPA', 'count': b8_12},
        {'label': '12+ LPA', 'count': b12_plus},
    ]

    return {
        'average': avg_val,
        'median': med_val,
        'min': min_val,
        'max': max_val,
        'average_display': f"{avg_val:.2f} LPA",
        'median_display': f"{med_val:.2f} LPA",
        'min_display': f"{min_val:.2f} LPA",
        'max_display': f"{max_val:.2f} LPA",
        'bins': bins,
        'unit': 'INR LPA',
    }


def average_salary_by_role(filters: Optional[Dict[str, Any]] = None, df: Optional[pd.DataFrame] = None) -> List[Dict[str, Any]]:
    """
    Computes average salary and student count by job role for placed students.
    Only includes roles with recorded positive salary.
    """
    if df is None:
        df = _get_student_outcome_df(filters)

    if df.empty or 'role_title' not in df.columns:
        return []

    valid = df[(df['status'] == 'Placed') & (df['role_title'].notna()) & (df['salary_package_lpa'] > 0)].copy()
    valid['role_title'] = valid['role_title'].str.strip()
    valid = valid[valid['role_title'] != '']

    if valid.empty:
        return []

    grouped = valid.groupby('role_title')['salary_package_lpa'].agg(['mean', 'count']).reset_index()
    grouped = grouped.sort_values(by=['count', 'mean'], ascending=[False, False])

    results = []
    for _, row in grouped.iterrows():
        avg_s = round(float(row['mean']), 2)
        results.append({
            'role': str(row['role_title']),
            'average_salary': avg_s,
            'count': int(row['count']),
            'average_salary_display': f"{avg_s:.2f} LPA",
        })
    return results


def job_role_distribution(filters: Optional[Dict[str, Any]] = None, df: Optional[pd.DataFrame] = None) -> List[Dict[str, Any]]:
    """
    Count of placed students per job role, including percentage of total placed.
    """
    if df is None:
        df = _get_student_outcome_df(filters)

    if df.empty or 'role_title' not in df.columns:
        return []

    placed_df = df[(df['status'] == 'Placed') & (df['role_title'].notna())].copy()
    placed_df['role_title'] = placed_df['role_title'].str.strip()
    placed_df = placed_df[placed_df['role_title'] != '']

    if placed_df.empty:
        return []

    total_placed = len(placed_df)
    counts = placed_df['role_title'].value_counts().reset_index()
    counts.columns = ['role', 'count']

    results = []
    for _, row in counts.iterrows():
        c = int(row['count'])
        pct = round((c / total_placed * 100.0), 1) if total_placed > 0 else 0.0
        results.append({
            'role': str(row['role']),
            'count': c,
            'percentage': pct,
        })
    return results


def branch_wise_placement(filters: Optional[Dict[str, Any]] = None, df: Optional[pd.DataFrame] = None) -> List[Dict[str, Any]]:
    """
    Per branch metrics: total students, placed students, and placement rate %.
    Sorted alphabetically by branch name.
    """
    if df is None:
        df = _get_student_outcome_df(filters)

    if df.empty or 'branch' not in df.columns:
        return []

    branches = df['branch'].dropna().unique()
    if len(branches) == 0:
        return []

    results = []
    for b in sorted(branches):
        b_df = df[df['branch'] == b]
        tot = len(b_df)
        placed = int((b_df['status'] == 'Placed').sum())
        pct = round((placed / tot * 100.0), 1) if tot > 0 else 0.0
        results.append({
            'branch': str(b),
            'total': tot,
            'placed': placed,
            'placement_pct': pct,
        })
    return results


def most_demanded_skills(limit: int = 10) -> List[Dict[str, Any]]:
    """
    Top skills required across all active job postings.
    Returns count of jobs requiring each skill, plus importance-weighted demand.
    """
    query = db.session.query(
        Skill.id.label('skill_id'),
        Skill.name.label('skill_name'),
        Skill.category.label('category'),
        JobSkill.importance_weight
    ).join(
        JobSkill, Skill.id == JobSkill.skill_id
    ).join(
        JobDescription, JobDescription.id == JobSkill.job_description_id
    ).filter(
        JobDescription.is_active == True
    )

    records = [r._asdict() for r in query.all()]
    if not records:
        return []

    df = pd.DataFrame(records)
    grouped = df.groupby(['skill_id', 'skill_name', 'category']).agg(
        job_count=('importance_weight', 'count'),
        weighted_demand=('importance_weight', 'sum')
    ).reset_index()

    grouped = grouped.sort_values(by=['job_count', 'weighted_demand'], ascending=[False, False]).head(limit)

    results = []
    for _, row in grouped.iterrows():
        results.append({
            'skill_id': int(row['skill_id']),
            'skill_name': str(row['skill_name']),
            'category': str(row['category'] or 'General'),
            'job_count': int(row['job_count']),
            'weighted_demand': int(row['weighted_demand']),
        })
    return results


def most_missing_skills(limit: int = 10, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """
    Across students, how often each skill is missing in their latest analysis.
    DEDUPLICATION LOGIC:
    Uses only each student's latest analysis per target job to avoid double counting
    when students run gap analysis repeatedly.
    """
    filters = filters or {}
    branch = (filters.get('branch') or '').strip()
    year = filters.get('year') or filters.get('graduation_year')

    # Subquery: get max analysis ID per (student_id, job_role_id)
    subq = db.session.query(
        SkillGapAnalysis.student_id,
        SkillGapAnalysis.job_role_id,
        func.max(SkillGapAnalysis.id).label('max_analysis_id')
    ).join(
        Student, Student.id == SkillGapAnalysis.student_id
    )

    if branch and branch.lower() != 'all':
        subq = subq.filter(Student.branch == branch)
    if year and str(year).strip().lower() != 'all':
        try:
            subq = subq.filter(Student.graduation_year == int(year))
        except (ValueError, TypeError):
            pass

    subq = subq.group_by(SkillGapAnalysis.student_id, SkillGapAnalysis.job_role_id).subquery()

    # Query missing skills from those latest analyses
    query = db.session.query(
        Skill.id.label('skill_id'),
        Skill.name.label('skill_name'),
        Skill.category.label('category')
    ).join(
        GapSkill, Skill.id == GapSkill.skill_id
    ).join(
        subq, GapSkill.analysis_id == subq.c.max_analysis_id
    ).filter(
        GapSkill.status == 'Missing'
    )

    records = [r._asdict() for r in query.all()]
    if not records:
        return []

    df = pd.DataFrame(records)
    counts = df.groupby(['skill_id', 'skill_name', 'category']).size().reset_index(name='missing_count')
    counts = counts.sort_values(by='missing_count', ascending=False).head(limit)

    results = []
    for _, row in counts.iterrows():
        results.append({
            'skill_id': int(row['skill_id']),
            'skill_name': str(row['skill_name']),
            'category': str(row['category'] or 'General'),
            'missing_count': int(row['missing_count']),
        })
    return results


def average_match_score(filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Average of latest match_percentage across students.
    Returns None and 'N/A' display if no analyses exist.
    """
    filters = filters or {}
    branch = (filters.get('branch') or '').strip()
    year = filters.get('year') or filters.get('graduation_year')

    # Subquery for each student's latest analysis
    subq = db.session.query(
        SkillGapAnalysis.student_id,
        func.max(SkillGapAnalysis.id).label('max_id')
    ).join(
        Student, Student.id == SkillGapAnalysis.student_id
    )

    if branch and branch.lower() != 'all':
        subq = subq.filter(Student.branch == branch)
    if year and str(year).strip().lower() != 'all':
        try:
            subq = subq.filter(Student.graduation_year == int(year))
        except (ValueError, TypeError):
            pass

    subq = subq.group_by(SkillGapAnalysis.student_id).subquery()

    query = db.session.query(
        SkillGapAnalysis.weighted_coverage_pct,
        SkillGapAnalysis.unweighted_coverage_pct
    ).join(
        subq, SkillGapAnalysis.id == subq.c.max_id
    )

    records = [r._asdict() for r in query.all()]
    if not records:
        return {'average_match': None, 'average_match_display': 'N/A'}

    df = pd.DataFrame(records)
    # Prefer weighted_coverage_pct, fallback to unweighted
    scores = pd.to_numeric(df['weighted_coverage_pct'].fillna(df['unweighted_coverage_pct']), errors='coerce').dropna()
    if scores.empty:
        return {'average_match': None, 'average_match_display': 'N/A'}

    avg_match = round(float(scores.mean()), 1)
    return {
        'average_match': avg_match,
        'average_match_display': f"{avg_match}%",
    }


def skill_improvement_over_time(
    skill_id: Optional[int] = None,
    student_id: Optional[int] = None,
    filters: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    From skill_progress, calculates average proficiency over time.
    Proficiency levels mapped: Beginner = 1.0, Intermediate = 2.0, Advanced = 3.0.
    Dynamically groups by week if data span < 90 days, else by month.
    """
    query = db.session.query(
        SkillProgress.id,
        SkillProgress.student_id,
        SkillProgress.skill_id,
        SkillProgress.new_proficiency,
        SkillProgress.recorded_at
    ).join(
        Student, Student.id == SkillProgress.student_id
    )

    if student_id:
        query = query.filter(SkillProgress.student_id == student_id)
    if skill_id:
        query = query.filter(SkillProgress.skill_id == skill_id)

    filters = filters or {}
    branch = (filters.get('branch') or '').strip()
    year = filters.get('year') or filters.get('graduation_year')

    if branch and branch.lower() != 'all':
        query = query.filter(Student.branch == branch)
    if year and str(year).strip().lower() != 'all':
        try:
            query = query.filter(Student.graduation_year == int(year))
        except (ValueError, TypeError):
            pass

    records = [r._asdict() for r in query.all()]
    if not records:
        return {
            'timeline': [],
            'granularity': 'month',
            'chart_labels': [],
            'chart_values': [],
        }

    df = pd.DataFrame(records)
    df['recorded_at'] = pd.to_datetime(df['recorded_at'], errors='coerce')
    df = df.dropna(subset=['recorded_at'])

    if df.empty:
        return {'timeline': [], 'granularity': 'month', 'chart_labels': [], 'chart_values': []}

    # Map proficiency
    prof_map = {'Beginner': 1.0, 'Intermediate': 2.0, 'Advanced': 3.0}
    df['score'] = df['new_proficiency'].map(prof_map).fillna(1.0)

    # Determine granularity
    span_days = (df['recorded_at'].max() - df['recorded_at'].min()).days
    if span_days < 90:
        granularity = 'week'
        df['period'] = df['recorded_at'].dt.strftime('%Y-W%U')
    else:
        granularity = 'month'
        df['period'] = df['recorded_at'].dt.strftime('%Y-%m')

    grouped = df.groupby('period').agg(
        avg_score=('score', 'mean'),
        count=('score', 'count')
    ).reset_index().sort_values(by='period')

    timeline = []
    labels = []
    values = []
    for _, row in grouped.iterrows():
        p = str(row['period'])
        val = round(float(row['avg_score']), 2)
        timeline.append({
            'period': p,
            'avg_proficiency': val,
            'count': int(row['count']),
        })
        labels.append(p)
        values.append(val)

    return {
        'timeline': timeline,
        'granularity': granularity,
        'chart_labels': labels,
        'chart_values': values,
    }


# ════════════════════════════════════════════════════════════════════════════════
#  4. COMPREHENSIVE ADMIN DASHBOARD AGGREGATOR
# ════════════════════════════════════════════════════════════════════════════════

def get_dashboard_analytics(filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Central analytics aggregator for Admin Dashboard.
    Single-pass data loading via Pandas guarantees zero divide-by-zero, zero NaN,
    and 100% numerical consistency with Phase 12 employment summary.
    """
    filters = filters or {}
    df = _get_student_outcome_df(filters)

    placement = placement_summary(filters=filters, df=df)
    salaries = salary_stats(filters=filters, df=df)
    match_score = average_match_score(filters=filters)
    demanded = most_demanded_skills(limit=10)
    missing = most_missing_skills(limit=10, filters=filters)
    branches = branch_wise_placement(filters=filters, df=df)
    roles = job_role_distribution(filters=filters, df=df)
    salary_roles = average_salary_by_role(filters=filters, df=df)
    improvement = skill_improvement_over_time(filters=filters)

    kpis = {
        'total_students': placement['total_students'],
        'placed_count': placement['placed_count'],
        'placement_pct': placement['placement_pct'],
        'placement_pct_display': f"{placement['placement_pct']}%",
        'avg_salary': salaries['average'],
        'avg_salary_display': salaries['average_display'],
        'median_salary': salaries['median'],
        'median_salary_display': salaries['median_display'],
        'avg_match_score': match_score['average_match'],
        'avg_match_score_display': match_score['average_match_display'],
    }

    return {
        'kpis': kpis,
        'placement': placement,
        'salary': salaries,
        'skills_demanded': demanded,
        'skills_missing': missing,
        'branch_wise': branches,
        'role_distribution': roles,
        'salary_by_role': salary_roles,
        'improvement': improvement,
        'filters': filters,
    }


# ════════════════════════════════════════════════════════════════════════════════
#  5. STUDENT PERSONAL ANALYTICS
# ════════════════════════════════════════════════════════════════════════════════

def get_student_personal_analytics(student_id: int) -> Optional[Dict[str, Any]]:
    """
    Personal analytics computation for /student/analytics.
    Gathers student skill counts, target job gap coverage, learning progress,
    radar proficiency data, and top in-demand skill comparison with neutral wording.
    """
    student = Student.query.options(
        joinedload(Student.skills).joinedload(StudentSkill.skill),
        joinedload(Student.target_job),
        joinedload(Student.learning_path)
    ).filter_by(id=student_id).first()

    if not student:
        return None

    # 1. Profile Completion %
    profile_pct = int(student.profile_completion_pct or 0)

    # 2. Number of Skills
    skill_count = len(student.skills)

    # 3. Latest Target Job Match & Coverage %
    latest_analysis = SkillGapAnalysis.query.filter_by(student_id=student.id).order_by(
        SkillGapAnalysis.id.desc()
    ).first()

    latest_coverage = None
    target_job_title = None
    if latest_analysis:
        latest_coverage = float(latest_analysis.weighted_coverage_pct or latest_analysis.unweighted_coverage_pct or 0.0)
        target_job_title = latest_analysis.job_role.title if latest_analysis.job_role else 'Target Role'
    elif student.target_job:
        target_job_title = student.target_job.title

    # 4. Learning Path Completion %
    total_lp = len(student.learning_path)
    completed_lp = sum(1 for item in student.learning_path if item.is_completed)
    lp_pct = round((completed_lp / total_lp * 100.0), 1) if total_lp > 0 else 0.0

    # 5. Top Skills by Proficiency for Radar / Bar Chart
    prof_weights = {'Beginner': 1, 'Intermediate': 2, 'Advanced': 3}
    student_skills_data = []
    student_skill_ids = set()
    student_skill_map = {}

    for ss in student.skills:
        student_skill_ids.add(ss.skill_id)
        p_lvl = getattr(ss, 'proficiency_level', getattr(ss, 'proficiency', 'Beginner'))
        p_val = prof_weights.get(p_lvl, 1)
        student_skill_map[ss.skill_id] = p_lvl
        student_skills_data.append({
            'name': ss.skill.name,
            'category': ss.skill.category,
            'proficiency': p_lvl,
            'score': p_val,
        })

    # Sort student skills by score descending
    student_skills_data.sort(key=lambda x: x['score'], reverse=True)
    top_skills_chart = {
        'labels': [s['name'] for s in student_skills_data[:8]],
        'scores': [s['score'] for s in student_skills_data[:8]],
        'proficiencies': [s['proficiency'] for s in student_skills_data[:8]],
    }

    # 6. Own Skill Progress Timeline
    progress_data = skill_improvement_over_time(student_id=student.id)

    # 7. Skills vs Most Demanded Skills Comparison (Neutral wording, non-predictive)
    top_demanded = most_demanded_skills(limit=8)
    comparison_skills = []
    for d in top_demanded:
        has = d['skill_id'] in student_skill_ids
        prof = student_skill_map.get(d['skill_id'])
        comparison_skills.append({
            'skill_name': d['skill_name'],
            'category': d['category'],
            'job_count': d['job_count'],
            'is_acquired': has,
            'status_label': 'Present in your profile' if has else 'Not yet acquired',
            'status_badge': 'success' if has else 'secondary',
            'proficiency': prof if has else None,
        })

    return {
        'student': {
            'id': student.id,
            'name': student.full_name,
            'roll_number': student.roll_number,
            'branch': student.branch,
            'graduation_year': student.graduation_year,
            'target_job_title': target_job_title,
        },
        'cards': {
            'profile_completion_pct': profile_pct,
            'skill_count': skill_count,
            'latest_coverage_pct': round(latest_coverage, 1) if latest_coverage is not None else None,
            'latest_coverage_display': f"{latest_coverage:.1f}%" if latest_coverage is not None else 'N/A',
            'learning_path_pct': lp_pct,
            'learning_path_completed': completed_lp,
            'learning_path_total': total_lp,
        },
        'top_skills_chart': top_skills_chart,
        'progress_timeline': progress_data,
        'comparison_skills': comparison_skills,
    }


# ════════════════════════════════════════════════════════════════════════════════
#  6. CSV EXPORT FOR ADMIN DASHBOARD
# ════════════════════════════════════════════════════════════════════════════════

def export_dashboard_csv(filters: Optional[Dict[str, Any]] = None) -> str:
    """
    Exports dashboard KPIs and aggregated summary tables into a clean CSV format.
    Guards against CSV formula injection by prepending single quotes to dangerous characters.
    """
    data = get_dashboard_analytics(filters)
    output = io.StringIO()
    writer = csv.writer(output)

    # 1. Header & Metadata
    writer.writerow([_sanitize_csv_cell("Skill Gap & Employment Outcome Tracking System - Analytics Export")])
    writer.writerow([_sanitize_csv_cell(f"Generated at: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")])
    branch_val = (filters or {}).get('branch') or 'All'
    year_val = (filters or {}).get('year') or 'All'
    writer.writerow([_sanitize_csv_cell(f"Filter Applied: Branch={branch_val}, Year={year_val}")])
    writer.writerow([])

    # 2. Key Performance Indicators
    writer.writerow([_sanitize_csv_cell("SECTION 1: KEY PERFORMANCE INDICATORS")])
    writer.writerow([_sanitize_csv_cell("Metric"), _sanitize_csv_cell("Value")])
    k = data['kpis']
    writer.writerow([_sanitize_csv_cell("Total Students"), _sanitize_csv_cell(k['total_students'])])
    writer.writerow([_sanitize_csv_cell("Total Placed"), _sanitize_csv_cell(k['placed_count'])])
    writer.writerow([_sanitize_csv_cell("Placement Percentage"), _sanitize_csv_cell(k['placement_pct_display'])])
    writer.writerow([_sanitize_csv_cell("Average Salary"), _sanitize_csv_cell(k['avg_salary_display'])])
    writer.writerow([_sanitize_csv_cell("Median Salary"), _sanitize_csv_cell(k['median_salary_display'])])
    writer.writerow([_sanitize_csv_cell("Average Skill-Match Score"), _sanitize_csv_cell(k['avg_match_score_display'])])
    writer.writerow([])

    # 3. Branch-wise Placement Summary
    writer.writerow([_sanitize_csv_cell("SECTION 2: BRANCH-WISE PLACEMENT SUMMARY")])
    writer.writerow([
        _sanitize_csv_cell("Branch"),
        _sanitize_csv_cell("Total Students"),
        _sanitize_csv_cell("Placed Students"),
        _sanitize_csv_cell("Placement Rate (%)")
    ])
    for b in data['branch_wise']:
        writer.writerow([
            _sanitize_csv_cell(b['branch']),
            _sanitize_csv_cell(b['total']),
            _sanitize_csv_cell(b['placed']),
            _sanitize_csv_cell(f"{b['placement_pct']}%")
        ])
    writer.writerow([])

    # 4. Average Salary by Job Role
    writer.writerow([_sanitize_csv_cell("SECTION 3: AVERAGE SALARY BY JOB ROLE")])
    writer.writerow([
        _sanitize_csv_cell("Job Role"),
        _sanitize_csv_cell("Placed Students Count"),
        _sanitize_csv_cell("Average Package (LPA)")
    ])
    for r in data['salary_by_role']:
        writer.writerow([
            _sanitize_csv_cell(r['role']),
            _sanitize_csv_cell(r['count']),
            _sanitize_csv_cell(r['average_salary_display'])
        ])
    writer.writerow([])

    # 5. Job Role Placement Distribution
    writer.writerow([_sanitize_csv_cell("SECTION 4: JOB ROLE PLACEMENT DISTRIBUTION")])
    writer.writerow([
        _sanitize_csv_cell("Job Role"),
        _sanitize_csv_cell("Count"),
        _sanitize_csv_cell("Percentage of Placed (%)")
    ])
    for j in data['role_distribution']:
        writer.writerow([
            _sanitize_csv_cell(j['role']),
            _sanitize_csv_cell(j['count']),
            _sanitize_csv_cell(f"{j['percentage']}%")
        ])

    return output.getvalue()
