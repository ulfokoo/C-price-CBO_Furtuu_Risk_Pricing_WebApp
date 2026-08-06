import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message_category = "info"


def create_app():
    app = Flask(__name__)
    app.config.from_object("config.Config")

    instance_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "instance")
    os.makedirs(instance_dir, exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)

    from app import models  # noqa

    @login_manager.user_loader
    def load_user(user_id):
        return models.User.query.get(int(user_id))

    from app.blueprints.auth import auth_bp
    from app.blueprints.dashboards import dashboards_bp
    from app.blueprints.admin import admin_bp
    from app.blueprints.input_dashboard import input_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboards_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(input_bp)

    with app.app_context():
        db.create_all()
        from app.seed import ensure_default_admin
        ensure_default_admin()

    @app.context_processor
    def inject_globals():
        from app.models import Product
        return dict(all_products=Product.query.order_by(Product.name).all())

    return app
