"""Karte der Spielwelt mit eigener Seite im Menü."""
from flask import Blueprint

from ...core import Module

bp = Blueprint("karte", __name__, template_folder="templates")

from . import routes  # noqa: E402,F401  (registriert die Routen am Blueprint)

module = Module(name="karte", label="Karte", icon="fa-map", order=30, blueprint=bp,
                description="Spielstand hochladen und die Welt ansehen.")
