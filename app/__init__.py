import importlib
import os
import pkgutil
import secrets

from flask import Flask, abort, g, render_template, request

from . import core, modules as modules_pkg


def _secret_key() -> str:
    env = os.environ.get("SECRET_KEY")
    if env:
        return env
    f = core.data_dir() / ".secret"
    if not f.exists():
        f.write_text(secrets.token_hex(32))
        f.chmod(0o600)
    return f.read_text().strip()


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=_secret_key(),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("INSECURE_COOKIES") != "1",
    )

    # Module automatisch finden: app/modules/<name>/__init__.py mit `module = Module(...)`
    core.MODULES.clear()
    for info in pkgutil.iter_modules(modules_pkg.__path__):
        mod = importlib.import_module(f"{modules_pkg.__name__}.{info.name}")
        if hasattr(mod, "module"):
            core.MODULES.append(mod.module)
    core.MODULES.sort(key=lambda m: (m.order, m.name))
    core.init_db()
    for m in core.MODULES:
        app.register_blueprint(m.blueprint, url_prefix=f"/{m.name}")

    app.teardown_appcontext(core.close_db)

    @app.get("/healthz")
    def healthz():
        return "ok"

    @app.before_request
    def authenticate():
        if request.endpoint in ("healthz", "static"):
            return None
        user, state = core.resolve_user()
        if state != "ok":
            return render_template("denied.html", state=state, email=core.identity_email()), 403
        g.user = user
        mod = next((m for m in core.MODULES if m.name == request.blueprint), None)
        if mod and mod.admin_only and user["role"] != "admin":
            abort(403)
        core.check_csrf()

    @app.context_processor
    def inject():
        user = g.get("user")
        nav = [m for m in core.MODULES
               if m.show_in_nav and (not m.admin_only or (user and user["role"] == "admin"))]
        return {"nav_modules": nav, "me": user, "csrf_token": core.csrf_token}

    @app.get("/")
    def home():
        mods = [m for m in core.MODULES if not m.admin_only or g.user["role"] == "admin"]
        return render_template("home.html", cards=mods)

    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(400)
    def error(e):
        return render_template("error.html", e=e), e.code

    return app
