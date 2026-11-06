from flask import Blueprint

from ...core import Module

bp = Blueprint("admin", __name__, template_folder="templates")

from . import routes  # noqa: E402,F401

module = Module(
    name="admin",
    label="Nutzer",
    icon="fa-users-cog",
    order=900,
    admin_only=True,
    blueprint=bp,
    description="Nutzer mit Name und E-Mail anlegen, Rollen vergeben.",
)
