"""ACEest Fitness & Gym - Flask application package."""
import os

from flask import Flask

from . import db
from .routes import bp


def create_app(config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-only-change-me"),
        DATABASE=os.environ.get("DATABASE", os.path.join(app.instance_path, "aceest_fitness.db")),
        ADMIN_USERNAME=os.environ.get("ADMIN_USERNAME", "admin"),
        ADMIN_PASSWORD=os.environ.get("ADMIN_PASSWORD", "admin"),
    )
    if config:
        app.config.update(config)
    app.json.sort_keys = False

    os.makedirs(app.instance_path, exist_ok=True)
    db.init_app(app)
    app.register_blueprint(bp)
    return app
