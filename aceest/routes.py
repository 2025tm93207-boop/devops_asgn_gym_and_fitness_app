"""HTTP endpoints for ACEest Fitness & Gym."""
import random
import sqlite3
from datetime import date, datetime
from functools import wraps

from flask import Blueprint, jsonify, render_template, request, session
from werkzeug.security import check_password_hash

from . import fitness
from .db import get_db

bp = Blueprint("aceest", __name__)


class ApiError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


@bp.app_errorhandler(ApiError)
def handle_api_error(err):
    return jsonify({"error": err.message}), err.status


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "username" not in session:
            raise ApiError("Authentication required", 401)
        return view(*args, **kwargs)

    return wrapped


# ---------- input helpers ----------


def _json_body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError("Request body must be a JSON object")
    return data


def _number(data, key, kind=float, required=False, minimum=None, maximum=None):
    value = data.get(key)
    if value is None or value == "":
        if required:
            raise ApiError(f"'{key}' is required")
        return None
    try:
        value = kind(value)
    except (TypeError, ValueError):
        raise ApiError(f"'{key}' must be a number")
    if minimum is not None and value < minimum:
        raise ApiError(f"'{key}' must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise ApiError(f"'{key}' must be <= {maximum}")
    return value


def _iso_date(data, key, default=None):
    value = data.get(key) or default
    if value is None:
        raise ApiError(f"'{key}' is required")
    try:
        date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ApiError(f"'{key}' must be a date in YYYY-MM-DD format")
    return value


def _get_client(name):
    row = get_db().execute("SELECT * FROM clients WHERE name = ?", (name,)).fetchone()
    if row is None:
        raise ApiError(f"Client '{name}' not found", 404)
    return row


def _client_dict(row):
    client = dict(row)
    client.pop("id")
    client["membership_status"] = fitness.membership_status(client["membership_expiry"])
    return client


def _client_fields(data, partial=False):
    """Validate client fields; with partial=True only supplied keys are returned."""
    fields = {}
    if not partial or "program" in data:
        program = data.get("program")
        if program not in fitness.PROGRAMS:
            raise ApiError(f"'program' must be one of: {', '.join(fitness.PROGRAMS)}")
        fields["program"] = program
    numeric = {
        "age": (int, 1, 120),
        "height": (float, 50, 300),
        "weight": (float, 20, 400),
        "target_weight": (float, 20, 400),
        "target_adherence": (int, 0, 100),
    }
    for key, (kind, lo, hi) in numeric.items():
        if not partial or key in data:
            fields[key] = _number(data, key, kind, minimum=lo, maximum=hi)
    if not partial or "membership_expiry" in data:
        fields["membership_expiry"] = (
            _iso_date(data, "membership_expiry") if data.get("membership_expiry") else None
        )
    return fields


# ---------- pages & meta ----------


@bp.get("/")
def index():
    return render_template("index.html", programs=fitness.PROGRAMS)


@bp.get("/health")
def health():
    return jsonify({"status": "ok"})


@bp.get("/api/programs")
def list_programs():
    return jsonify(
        [{"name": name, **details} for name, details in fitness.PROGRAMS.items()]
    )


# ---------- auth ----------


@bp.post("/api/login")
def login():
    data = _json_body()
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    user = get_db().execute(
        "SELECT username, password_hash, role FROM users WHERE username = ?", (username,)
    ).fetchone()
    if user is None or not check_password_hash(user["password_hash"], password):
        raise ApiError("Invalid credentials", 401)
    session.clear()
    session["username"] = user["username"]
    session["role"] = user["role"]
    return jsonify({"username": user["username"], "role": user["role"]})


@bp.post("/api/logout")
def logout():
    session.clear()
    return jsonify({"message": "Logged out"})


# ---------- clients ----------


@bp.get("/api/clients")
@login_required
def list_clients():
    rows = get_db().execute("SELECT * FROM clients ORDER BY name").fetchall()
    return jsonify([_client_dict(r) for r in rows])


@bp.post("/api/clients")
@login_required
def create_client():
    data = _json_body()
    name = (data.get("name") or "").strip()
    if not name:
        raise ApiError("'name' is required")
    fields = _client_fields(data)
    fields["calories"] = fitness.calculate_calories(fields["weight"], fields["program"])
    db = get_db()
    try:
        db.execute(
            "INSERT INTO clients (name, age, height, weight, program, calories, "
            "target_weight, target_adherence, membership_expiry) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                name,
                fields["age"],
                fields["height"],
                fields["weight"],
                fields["program"],
                fields["calories"],
                fields["target_weight"],
                fields["target_adherence"],
                fields["membership_expiry"],
            ),
        )
        db.commit()
    except sqlite3.IntegrityError:
        raise ApiError(f"Client '{name}' already exists", 409)
    return jsonify(_client_dict(_get_client(name))), 201


@bp.get("/api/clients/<name>")
@login_required
def get_client(name):
    return jsonify(_client_dict(_get_client(name)))


@bp.put("/api/clients/<name>")
@login_required
def update_client(name):
    current = _get_client(name)
    fields = _client_fields(_json_body(), partial=True)
    if not fields:
        raise ApiError("No updatable fields supplied")
    weight = fields.get("weight", current["weight"])
    program = fields.get("program", current["program"])
    fields["calories"] = fitness.calculate_calories(weight, program)

    assignments = ", ".join(f"{key} = ?" for key in fields)
    db = get_db()
    db.execute(
        f"UPDATE clients SET {assignments} WHERE id = ?", (*fields.values(), current["id"])
    )
    db.commit()
    return jsonify(_client_dict(_get_client(name)))


@bp.delete("/api/clients/<name>")
@login_required
def delete_client(name):
    client = _get_client(name)
    db = get_db()
    db.execute("DELETE FROM clients WHERE id = ?", (client["id"],))
    db.commit()
    return "", 204


# ---------- progress ----------


@bp.get("/api/clients/<name>/progress")
@login_required
def list_progress(name):
    client = _get_client(name)
    rows = get_db().execute(
        "SELECT week, adherence FROM progress WHERE client_id = ? ORDER BY id",
        (client["id"],),
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@bp.post("/api/clients/<name>/progress")
@login_required
def add_progress(name):
    client = _get_client(name)
    data = _json_body()
    adherence = _number(data, "adherence", int, required=True, minimum=0, maximum=100)
    week = data.get("week") or datetime.now().strftime("Week %U - %Y")
    db = get_db()
    db.execute(
        "INSERT INTO progress (client_id, week, adherence) VALUES (?, ?, ?)",
        (client["id"], week, adherence),
    )
    db.commit()
    return jsonify({"week": week, "adherence": adherence}), 201


# ---------- workouts ----------


@bp.get("/api/clients/<name>/workouts")
@login_required
def list_workouts(name):
    client = _get_client(name)
    db = get_db()
    workouts = db.execute(
        "SELECT id, date, workout_type, duration_min, notes FROM workouts "
        "WHERE client_id = ? ORDER BY date DESC, id DESC",
        (client["id"],),
    ).fetchall()
    result = []
    for w in workouts:
        workout = dict(w)
        workout["exercises"] = [
            dict(e)
            for e in db.execute(
                "SELECT name, sets, reps, weight FROM exercises WHERE workout_id = ? ORDER BY id",
                (w["id"],),
            ).fetchall()
        ]
        workout.pop("id")
        result.append(workout)
    return jsonify(result)


@bp.post("/api/clients/<name>/workouts")
@login_required
def add_workout(name):
    client = _get_client(name)
    data = _json_body()
    workout_date = _iso_date(data, "date", default=date.today().isoformat())
    workout_type = data.get("workout_type")
    if workout_type not in fitness.WORKOUT_TYPES:
        raise ApiError(f"'workout_type' must be one of: {', '.join(fitness.WORKOUT_TYPES)}")
    duration = _number(data, "duration_min", int, minimum=1, maximum=600)
    notes = (data.get("notes") or "").strip()

    exercises = data.get("exercises") or []
    if not isinstance(exercises, list):
        raise ApiError("'exercises' must be a list")
    clean_exercises = []
    for ex in exercises:
        if not isinstance(ex, dict) or not (ex.get("name") or "").strip():
            raise ApiError("Each exercise needs a 'name'")
        clean_exercises.append(
            (
                ex["name"].strip(),
                _number(ex, "sets", int, minimum=1),
                _number(ex, "reps", int, minimum=1),
                _number(ex, "weight", float, minimum=0),
            )
        )

    db = get_db()
    cur = db.execute(
        "INSERT INTO workouts (client_id, date, workout_type, duration_min, notes) "
        "VALUES (?, ?, ?, ?, ?)",
        (client["id"], workout_date, workout_type, duration, notes),
    )
    db.executemany(
        "INSERT INTO exercises (workout_id, name, sets, reps, weight) VALUES (?, ?, ?, ?, ?)",
        [(cur.lastrowid, *ex) for ex in clean_exercises],
    )
    db.commit()
    return (
        jsonify(
            {
                "date": workout_date,
                "workout_type": workout_type,
                "duration_min": duration,
                "notes": notes,
                "exercises": [
                    dict(zip(("name", "sets", "reps", "weight"), ex)) for ex in clean_exercises
                ],
            }
        ),
        201,
    )


# ---------- body metrics ----------


@bp.get("/api/clients/<name>/metrics")
@login_required
def list_metrics(name):
    client = _get_client(name)
    rows = get_db().execute(
        "SELECT date, weight, waist, bodyfat FROM metrics WHERE client_id = ? ORDER BY date",
        (client["id"],),
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@bp.post("/api/clients/<name>/metrics")
@login_required
def add_metrics(name):
    client = _get_client(name)
    data = _json_body()
    metric = {
        "date": _iso_date(data, "date", default=date.today().isoformat()),
        "weight": _number(data, "weight", float, minimum=20, maximum=400),
        "waist": _number(data, "waist", float, minimum=20, maximum=300),
        "bodyfat": _number(data, "bodyfat", float, minimum=1, maximum=75),
    }
    db = get_db()
    db.execute(
        "INSERT INTO metrics (client_id, date, weight, waist, bodyfat) VALUES (?, ?, ?, ?, ?)",
        (client["id"], metric["date"], metric["weight"], metric["waist"], metric["bodyfat"]),
    )
    # A new weigh-in becomes the client's current weight (as in the desktop app).
    if metric["weight"] is not None:
        db.execute(
            "UPDATE clients SET weight = ?, calories = ? WHERE id = ?",
            (
                metric["weight"],
                fitness.calculate_calories(metric["weight"], client["program"]),
                client["id"],
            ),
        )
    db.commit()
    return jsonify(metric), 201


# ---------- analytics ----------


@bp.get("/api/clients/<name>/bmi")
@login_required
def client_bmi(name):
    client = _get_client(name)
    try:
        bmi = fitness.calculate_bmi(client["height"], client["weight"])
    except ValueError as err:
        raise ApiError(str(err))
    category, risk = fitness.bmi_category(bmi)
    return jsonify({"bmi": bmi, "category": category, "risk": risk})


@bp.get("/api/clients/<name>/summary")
@login_required
def client_summary(name):
    client = _get_client(name)
    db = get_db()
    weeks, avg = db.execute(
        "SELECT COUNT(*), AVG(adherence) FROM progress WHERE client_id = ?", (client["id"],)
    ).fetchone()
    last_metric = db.execute(
        "SELECT date, weight, waist, bodyfat FROM metrics WHERE client_id = ? "
        "ORDER BY date DESC, id DESC LIMIT 1",
        (client["id"],),
    ).fetchone()
    workouts = db.execute(
        "SELECT COUNT(*) FROM workouts WHERE client_id = ?", (client["id"],)
    ).fetchone()[0]
    return jsonify(
        {
            "client": _client_dict(client),
            "program_notes": fitness.PROGRAMS.get(client["program"], {}).get("desc", ""),
            "weeks_logged": weeks,
            "average_adherence": round(avg, 1) if avg is not None else 0,
            "workouts_logged": workouts,
            "last_metrics": dict(last_metric) if last_metric else None,
        }
    )


@bp.post("/api/clients/<name>/generate-program")
@login_required
def generate_program(name):
    client = _get_client(name)
    data = request.get_json(silent=True) or {}
    seed = data.get("seed")
    rng = random.Random(seed) if seed is not None else None
    try:
        plan = fitness.generate_program(client["program"], data.get("experience"), rng)
    except ValueError as err:
        raise ApiError(str(err))
    return jsonify({"client": name, "experience": data["experience"].lower(), "plan": plan})
