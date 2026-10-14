"""Server-rendered view routes for the frontend pages.

These routes serve Jinja2 templates that fetch data from the /api
endpoints via client-side JavaScript.
"""

from flask import Blueprint, render_template

views_bp = Blueprint("views", __name__)


@views_bp.route("/")
def home():
    """Landing page — lists published forms."""
    return render_template("home.html")


@views_bp.route("/create")
def form_builder():
    """Form builder — owners create new questionnaire forms."""
    return render_template("form_builder.html")


@views_bp.route("/form/<form_id>")
def form_filler(form_id: str):
    """Form filler — respondents fill in a published form."""
    return render_template("form_filler.html", form_id=form_id)


@views_bp.route("/dashboard")
def dashboard():
    """Dashboard — aggregate stats, charts, and form list."""
    return render_template("dashboard.html")


@views_bp.route("/leaderboard/<form_id>")
def leaderboard(form_id: str):
    """Leaderboard — per-form ranked list of respondents with rewards."""
    return render_template("leaderboard.html", form_id=form_id)
