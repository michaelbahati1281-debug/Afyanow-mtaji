import os
from flask import Flask, redirect, url_for
from flask_wtf.csrf import CSRFProtect

from config import Config
from models import db
from helpers import login_manager


csrf = CSRFProtect()


def create_app(config_class=Config):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    os.makedirs(app.instance_path, exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    from routes.auth_routes import auth_bp
    from routes.main_routes import main_bp
    from routes.patient_routes import patient_bp
    from routes.provider_routes import provider_bp
    from routes.admin_routes import admin_bp
    from routes.api_routes import api_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(patient_bp)
    app.register_blueprint(provider_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)

    @app.route("/")
    def index():
        return redirect(url_for("main.landing"))

    from helpers import dashboard_redirect

    with app.app_context():
        db.create_all()

    @app.context_processor
    def inject_globals():
        from flask_login import current_user
        from models import Notification
        from datetime import datetime as _dt
        unread = 0
        if current_user.is_authenticated:
            unread = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
        return {"unread_count": unread, "current_year": _dt.now().year}

    return app


if __name__ == "__main__":
    app = create_app()
    from models import Speciality

    with app.app_context():
        has_started = Speciality.query.first() is not None
    if not has_started:
        print("No data found. Please run: python seed.py")
    app.run(debug=True, host="0.0.0.0", port=5500)