"""
train_model.py (root wrapper)
─────────────────────────────
Convenience CLI entry point for training the Employment Outcome model.
Delegates directly to ml/train_model.py.

Usage:
  python train_model.py
"""

import sys
import os

# Ensure project root is in python path
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from ml.train_model import train_and_save

if __name__ == '__main__':
    train_and_save()
