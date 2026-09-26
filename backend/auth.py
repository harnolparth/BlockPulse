"""
AgriTrace — Auth
Password hashing (PBKDF2, stdlib only — no external deps needed) and
JWT session tokens (PyJWT) with simple role-based guards.
"""

import hashlib
import hmac
import os
import secrets
import functools
import datetime

import jwt
from flask import request, jsonify, session, redirect, url_for

SECRET_KEY = os.environ.get("AGRITRACE_SECRET", "dev-secret-change-me-in-production")
JWT_ALGO = "HS256"
TOKEN_TTL_HOURS = 12


def hash_password(password: str, salt: str = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000)
    return f"{salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, digest_hex = stored.split("$")
    except ValueError:
        return False
    check = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000)
    return hmac.compare_digest(check.hex(), digest_hex)


def issue_token(user_row) -> str:
    payload = {
        "uid": user_row["id"],
        "role": user_row["role"],
        "name": user_row["full_name"],
        "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=TOKEN_TTL_HOURS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALGO)


def decode_token(token: str):
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGO])
    except jwt.PyJWTError:
        return None


def current_user():
    """Reads the JWT from either the session cookie (page views) or the
    Authorization header (API calls) so the same routes serve both."""
    token = session.get("token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1]
    if not token:
        return None
    return decode_token(token)


def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if not user:
            if request.path.startswith("/api/"):
                return jsonify({"error": "authentication required"}), 401
            return redirect(url_for("login_page", next=request.path))
        return view(*args, user=user, **kwargs)
    return wrapped


def roles_required(*allowed_roles):
    def decorator(view):
        @functools.wraps(view)
        def wrapped(*args, **kwargs):
            user = current_user()
            if not user:
                if request.path.startswith("/api/"):
                    return jsonify({"error": "authentication required"}), 401
                return redirect(url_for("login_page", next=request.path))
            if user["role"] not in allowed_roles and user["role"] != "admin":
                return jsonify({"error": f"requires role in {allowed_roles}"}), 403
            return view(*args, user=user, **kwargs)
        return wrapped
    return decorator


def device_key_valid(conn, device_key: str):
    row = conn.execute("SELECT * FROM nodes WHERE device_key = ?", (device_key,)).fetchone()
    return row
