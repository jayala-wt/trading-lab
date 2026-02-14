from __future__ import annotations

from flask import Flask

from app.web.routes import trading_lab_bp


def create_app() -> Flask:
    app = Flask(__name__)
    app.register_blueprint(trading_lab_bp)
    return app


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=5050, debug=False)
