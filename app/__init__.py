import os
from flask import Flask
from flask_login import LoginManager
from dotenv import load_dotenv

load_dotenv()


def create_app():
    import os as _os

    _base = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
    app = Flask(
        __name__,
        template_folder=_os.path.join(_base, "templates"),
        static_folder=_os.path.join(_base, "static"),
    )
    app.secret_key = os.getenv("NEXTAUTH_SECRET", os.urandom(24).hex())

    import json as _json

    @app.template_filter("from_json")
    def from_json_filter(value):
        if value is None:
            return []
        if isinstance(value, list):
            return value
        try:
            return _json.loads(value)
        except (_json.JSONDecodeError, TypeError):
            return []

    @app.template_filter("thumb_url")
    def thumb_url_filter(value):
        if not value:
            return value
        base, ext = _os.path.splitext(value)
        return f"{base}_thumb{ext}"

    @app.template_filter("thumb_url")
    def thumb_url_filter(value):
        if not value:
            return ""
        if isinstance(value, list):
            return [thumb_url_filter(v) for v in value]
        base, ext = _os.path.splitext(value)
        return f"{base}_thumb{ext}"

    from app.models import SessionLocal, users

    login_manager = LoginManager()
    login_manager.login_view = "routes.login_page"
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        db = SessionLocal()
        try:
            from sqlalchemy import select

            row = db.execute(select(users).where(users.c.id == user_id)).first()
            if row:
                from flask_login import UserMixin

                class UserProxy(UserMixin):
                    def __init__(self, row):
                        self.id = row.id
                        self.email = row.email
                        self.name = row.name
                        self.role = row.role

                return UserProxy(row)
            return None
        finally:
            db.close()

    @app.teardown_appcontext
    def shutdown_session(exception=None):
        SessionLocal.remove()

    from app.routes import routes_bp

    app.register_blueprint(routes_bp)

    # Serve generated PDFs
    @app.route("/contracts/<path:filename>")
    def serve_contract_pdf(filename):
        from flask import send_from_directory
        import os as _os

        pdf_dir = _os.path.join(app.root_path, "..", "public", "contracts")
        return send_from_directory(pdf_dir, filename)

    # Serve uploaded property files
    @app.route("/uploads/properties/<path:filename>")
    def serve_upload(filename):
        from flask import send_from_directory
        import os as _os

        upload_dir = _os.path.join(app.root_path, "..", "public", "uploads", "properties")
        return send_from_directory(upload_dir, filename)

    return app
