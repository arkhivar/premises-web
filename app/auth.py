import bcrypt
from functools import wraps
from flask import redirect, url_for, flash
from flask_login import current_user


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("routes.login_page"))
            if current_user.role not in roles:
                flash("Доступ запрещён", "error")
                return redirect(url_for("routes.dashboard"))
            return f(*args, **kwargs)

        return decorated

    return decorator
