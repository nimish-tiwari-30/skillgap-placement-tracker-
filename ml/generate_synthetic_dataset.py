"""
ml/generate_synthetic_dataset.py
─────────────────────────────────
Generates a synthetic training dataset for the employment outcome classifier.

WHY SYNTHETIC DATA?
  Real student data is limited (< 100 labeled outcomes in early stages).
  We generate 500 rows with realistic correlations so the model can still
  learn patterns. The app displays a clear DEMO/SYNTHETIC disclaimer.

FEATURES (all known BEFORE placement outcome — no leakage):
  - cgpa               : float 0.0–10.0
  - skill_count        : int   1–12
  - skill_match_pct    : float 0–100 (% of target-job skills the student has)
  - aptitude_score     : int   0–100
  - communication_score: int   0–100
  - has_internship     : int   0 or 1
  - profile_completion : int   0–100

TARGET:
  - label  : 0 = Not Placed, 1 = Placed
  (We collapse 'In Progress' → 0 since outcome not yet known)

Usage:
  python ml/generate_synthetic_dataset.py
  → writes ml/data/synthetic_training.csv
"""

import os
import random
import pandas as pd
import numpy as np

RANDOM_SEED = 42
N_ROWS = 500

OUTPUT_DIR  = os.path.join(os.path.dirname(__file__), 'data')
OUTPUT_FILE = os.path.join(OUTPUT_DIR, 'synthetic_training.csv')


def generate_dataset(n: int = N_ROWS, seed: int = RANDOM_SEED) -> pd.DataFrame:
    """Return a DataFrame of synthetic student feature rows with a binary label."""
    rng = np.random.default_rng(seed)
    random.seed(seed)

    rows = []
    for _ in range(n):
        # --- Generate base features ---
        cgpa                = round(float(rng.uniform(4.0, 10.0)), 2)
        skill_count         = int(rng.integers(1, 13))          # 1–12
        skill_match_pct     = round(float(rng.uniform(0, 100)), 1)
        aptitude_score      = int(rng.integers(20, 101))        # 20–100
        communication_score = int(rng.integers(20, 101))
        has_internship      = int(rng.random() < 0.45)          # 45% have internship
        profile_completion  = int(rng.integers(20, 101))

        # --- Compute placement probability (deterministic, not random) ---
        # Higher weights for cgpa, skill match, aptitude → more placement likely
        score = (
            (cgpa / 10.0)               * 30   # max 30 pts
            + (skill_match_pct / 100.0) * 25   # max 25 pts
            + (aptitude_score  / 100.0) * 20   # max 20 pts
            + (communication_score / 100.0) * 15  # max 15 pts
            + has_internship             * 7   # 7 pts bonus
            + (profile_completion / 100.0) * 3  # max 3 pts
        )  # total max: 100

        # Add realistic real-world variance so accuracy lands in realistic ~75-82% range
        score += float(rng.normal(0, 8.5))
        label = 1 if score >= 50 else 0

        rows.append({
            'cgpa':                 cgpa,
            'skill_count':          skill_count,
            'skill_match_pct':      skill_match_pct,
            'aptitude_score':       aptitude_score,
            'communication_score':  communication_score,
            'has_internship':       has_internship,
            'profile_completion':   profile_completion,
            'label':                label,
        })

    df = pd.DataFrame(rows)
    return df


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    df = generate_dataset()
    df.to_csv(OUTPUT_FILE, index=False)

    placed_count = df['label'].sum()
    print(f"[OK] Generated {len(df)} rows -> {OUTPUT_FILE}")
    print(f"     Placed={placed_count} ({placed_count/len(df)*100:.1f}%)  Not Placed={len(df)-placed_count}")


if __name__ == '__main__':
    main()
