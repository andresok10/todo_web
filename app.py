import os
import secrets
from typing import Callable, Protocol, cast

from calendario import app1
from descargador import app2
from flask import Blueprint, Flask
from flask_wtf.csrf import CSRFProtect

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"


# Flask-WTF no anota exempt; al recibir un Blueprint devuelve ese Blueprint.
class _CSRFBlueprintExemption(Protocol):
    exempt: Callable[[Blueprint], Blueprint]


csrf = CSRFProtect(app)
cast(_CSRFBlueprintExemption, csrf).exempt(app2)
app.register_blueprint(app1)
app.register_blueprint(app2)

if __name__ == "__main__":
    app.run(host=os.environ.get("HOST", "0.0.0.0"), port=int(os.environ.get("PORT", "5003")), debug=os.environ.get("FLASK_DEBUG") == "1")