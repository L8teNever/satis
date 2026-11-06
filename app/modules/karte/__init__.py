"""Karte der Spielwelt. Sie läuft als Tab im Rechner, darum gibt es keinen eigenen Menüpunkt."""
from flask import Blueprint

from ...core import Module

bp = Blueprint("karte", __name__, template_folder="templates")

from . import routes  # noqa: E402,F401  (registriert die Routen am Blueprint)

module = Module(name="karte", label="Karte", icon="fa-map", order=30, blueprint=bp, show_in_nav=False,
                description="Spielstand hochladen und die Welt ansehen.")
