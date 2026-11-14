"""
utils/helpers.py
─────────────────
Shared utility functions used across routes and services.
"""

from flask import jsonify


def api_success(data=None, message: str = "Success", status_code: int = 200):
    """Standard JSON success response for all API endpoints."""
    response = {"success": True, "message": message}
    if data is not None:
        response["data"] = data
    return jsonify(response), status_code


def api_error(message: str = "An error occurred", status_code: int = 400):
    """Standard JSON error response for all API endpoints."""
    return jsonify({"success": False, "error": message}), status_code
