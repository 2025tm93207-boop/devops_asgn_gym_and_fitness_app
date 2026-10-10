"""Integration tests for the Flask HTTP endpoints."""
from datetime import date

import pytest

from aceest import fitness

from .conftest import SAMPLE_CLIENT


# ---------- public endpoints ----------


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


def test_index_page_lists_programs(client):
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    for name in fitness.PROGRAMS:
        assert name in body


def test_programs_endpoint(client):
    resp = client.get("/api/programs")
    assert resp.status_code == 200
    data = resp.get_json()
    assert [p["name"] for p in data] == list(fitness.PROGRAMS)
    assert all({"factor", "desc", "focus"} <= p.keys() for p in data)


# ---------- authentication ----------


class TestAuth:
    def test_login_success(self, client):
        resp = client.post("/api/login", json={"username": "admin", "password": "admin"})
        assert resp.status_code == 200
        assert resp.get_json() == {"username": "admin", "role": "Admin"}

    @pytest.mark.parametrize(
        "payload",
        [
            {"username": "admin", "password": "wrong"},
            {"username": "nobody", "password": "admin"},
            {"username": "", "password": ""},
        ],
    )
    def test_login_rejects_bad_credentials(self, client, payload):
        resp = client.post("/api/login", json=payload)
        assert resp.status_code == 401
        assert resp.get_json()["error"] == "Invalid credentials"

    def test_login_requires_json_body(self, client):
        resp = client.post("/api/login", data="username=admin")
        assert resp.status_code == 400

    def test_password_is_stored_hashed(self, app):
        from aceest.db import get_db

        with app.app_context():
            stored = get_db().execute(
                "SELECT password_hash FROM users WHERE username='admin'"
            ).fetchone()[0]
        assert stored != "admin"

    def test_admin_credentials_configurable(self, tmp_path):
        from aceest import create_app

        app = create_app(
            {
                "TESTING": True,
                "DATABASE": str(tmp_path / "custom.db"),
                "ADMIN_USERNAME": "coach",
                "ADMIN_PASSWORD": "s3cret",
            }
        )
        c = app.test_client()
        resp = c.post("/api/login", json={"username": "coach", "password": "s3cret"})
        assert resp.status_code == 200

    @pytest.mark.parametrize(
        "method, url",
        [
            ("get", "/api/clients"),
            ("post", "/api/clients"),
            ("get", "/api/clients/Prerna"),
            ("put", "/api/clients/Prerna"),
            ("delete", "/api/clients/Prerna"),
            ("get", "/api/clients/Prerna/progress"),
            ("post", "/api/clients/Prerna/progress"),
            ("get", "/api/clients/Prerna/workouts"),
            ("post", "/api/clients/Prerna/workouts"),
            ("get", "/api/clients/Prerna/metrics"),
            ("post", "/api/clients/Prerna/metrics"),
            ("get", "/api/clients/Prerna/bmi"),
            ("get", "/api/clients/Prerna/summary"),
            ("post", "/api/clients/Prerna/generate-program"),
        ],
    )
    def test_protected_endpoints_require_login(self, client, method, url):
        resp = getattr(client, method)(url, json={})
        assert resp.status_code == 401
        assert resp.get_json()["error"] == "Authentication required"

    def test_logout_ends_session(self, auth_client):
        assert auth_client.get("/api/clients").status_code == 200
        assert auth_client.post("/api/logout").status_code == 200
        assert auth_client.get("/api/clients").status_code == 401


# ---------- clients CRUD ----------


class TestClients:
    def test_create_client(self, auth_client):
        resp = auth_client.post("/api/clients", json=SAMPLE_CLIENT)
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["name"] == "Prerna"
        assert data["calories"] == 80 * 35
        assert data["membership_status"] == "active"
        assert "id" not in data

    def test_create_minimal_client(self, auth_client):
        resp = auth_client.post("/api/clients", json={"name": "Asha", "program": "Beginner (BG)"})
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["weight"] is None
        assert data["calories"] is None
        assert data["membership_status"] == "unknown"

    def test_name_is_trimmed(self, auth_client):
        resp = auth_client.post(
            "/api/clients", json={"name": "  Asha  ", "program": "Beginner (BG)"}
        )
        assert resp.get_json()["name"] == "Asha"

    def test_duplicate_name_conflicts(self, sample_client):
        resp = sample_client.post("/api/clients", json=SAMPLE_CLIENT)
        assert resp.status_code == 409

    @pytest.mark.parametrize(
        "overrides, message",
        [
            ({"name": ""}, "'name' is required"),
            ({"program": "Yoga"}, "'program' must be one of"),
            ({"age": "abc"}, "'age' must be a number"),
            ({"age": 0}, "'age' must be >= 1"),
            ({"height": 500}, "'height' must be <= 300"),
            ({"weight": 5}, "'weight' must be >= 20"),
            ({"target_adherence": 150}, "'target_adherence' must be <= 100"),
            ({"membership_expiry": "31-12-2026"}, "YYYY-MM-DD"),
        ],
    )
    def test_create_validation(self, auth_client, overrides, message):
        resp = auth_client.post("/api/clients", json={**SAMPLE_CLIENT, **overrides})
        assert resp.status_code == 400
        assert message in resp.get_json()["error"]

    def test_create_rejects_non_object_body(self, auth_client):
        assert auth_client.post("/api/clients", json=["Prerna"]).status_code == 400

    def test_list_clients_sorted_by_name(self, auth_client):
        for name in ["Zara", "Arun", "Meena"]:
            auth_client.post("/api/clients", json={"name": name, "program": "Beginner (BG)"})
        names = [c["name"] for c in auth_client.get("/api/clients").get_json()]
        assert names == ["Arun", "Meena", "Zara"]

    def test_get_client(self, sample_client):
        resp = sample_client.get("/api/clients/Prerna")
        assert resp.status_code == 200
        assert resp.get_json()["program"] == SAMPLE_CLIENT["program"]

    def test_get_missing_client(self, auth_client):
        resp = auth_client.get("/api/clients/Ghost")
        assert resp.status_code == 404
        assert "not found" in resp.get_json()["error"]

    def test_update_recalculates_calories_on_weight_change(self, sample_client):
        resp = sample_client.put("/api/clients/Prerna", json={"weight": 90})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["weight"] == 90
        assert data["calories"] == 90 * 35
        assert data["age"] == SAMPLE_CLIENT["age"]  # untouched fields are kept

    def test_update_recalculates_calories_on_program_change(self, sample_client):
        resp = sample_client.put("/api/clients/Prerna", json={"program": "Fat Loss (FL) – 3 day"})
        assert resp.get_json()["calories"] == 80 * 22

    def test_update_validation(self, sample_client):
        assert sample_client.put("/api/clients/Prerna", json={"age": -1}).status_code == 400
        assert sample_client.put("/api/clients/Prerna", json={}).status_code == 400

    def test_update_missing_client(self, auth_client):
        assert auth_client.put("/api/clients/Ghost", json={"age": 20}).status_code == 404

    def test_expired_membership(self, auth_client):
        resp = auth_client.post(
            "/api/clients",
            json={"name": "Old", "program": "Beginner (BG)", "membership_expiry": "2000-01-01"},
        )
        assert resp.get_json()["membership_status"] == "expired"

    def test_delete_client_cascades(self, sample_client):
        sample_client.post("/api/clients/Prerna/progress", json={"adherence": 80})
        assert sample_client.delete("/api/clients/Prerna").status_code == 204
        assert sample_client.get("/api/clients/Prerna").status_code == 404

        # Re-creating the same name must not resurrect old history.
        sample_client.post("/api/clients", json=SAMPLE_CLIENT)
        assert sample_client.get("/api/clients/Prerna/progress").get_json() == []

    def test_delete_missing_client(self, auth_client):
        assert auth_client.delete("/api/clients/Ghost").status_code == 404


# ---------- progress ----------


class TestProgress:
    def test_add_and_list(self, sample_client):
        resp = sample_client.post(
            "/api/clients/Prerna/progress", json={"adherence": 75, "week": "Week 1"}
        )
        assert resp.status_code == 201
        sample_client.post("/api/clients/Prerna/progress", json={"adherence": 85, "week": "Week 2"})
        data = sample_client.get("/api/clients/Prerna/progress").get_json()
        assert data == [{"week": "Week 1", "adherence": 75}, {"week": "Week 2", "adherence": 85}]

    def test_default_week_label(self, sample_client):
        resp = sample_client.post("/api/clients/Prerna/progress", json={"adherence": 50})
        assert resp.get_json()["week"].startswith("Week ")

    @pytest.mark.parametrize(
        "payload", [{}, {"adherence": -1}, {"adherence": 101}, {"adherence": "x"}]
    )
    def test_validation(self, sample_client, payload):
        assert sample_client.post("/api/clients/Prerna/progress", json=payload).status_code == 400

    def test_unknown_client(self, auth_client):
        resp = auth_client.post("/api/clients/Ghost/progress", json={"adherence": 50})
        assert resp.status_code == 404


# ---------- workouts ----------


class TestWorkouts:
    WORKOUT = {
        "date": "2026-10-01",
        "workout_type": "Strength",
        "duration_min": 60,
        "notes": "  Felt strong  ",
        "exercises": [
            {"name": "Squat", "sets": 5, "reps": 5, "weight": 100},
            {"name": "Bench Press", "sets": 3, "reps": 8, "weight": 70},
        ],
    }

    def test_add_workout_with_exercises(self, sample_client):
        resp = sample_client.post("/api/clients/Prerna/workouts", json=self.WORKOUT)
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["notes"] == "Felt strong"
        assert [e["name"] for e in data["exercises"]] == ["Squat", "Bench Press"]

    def test_list_newest_first_with_exercises(self, sample_client):
        sample_client.post("/api/clients/Prerna/workouts", json=self.WORKOUT)
        sample_client.post(
            "/api/clients/Prerna/workouts",
            json={"date": "2026-10-05", "workout_type": "Mobility"},
        )
        data = sample_client.get("/api/clients/Prerna/workouts").get_json()
        assert [w["date"] for w in data] == ["2026-10-05", "2026-10-01"]
        assert data[0]["exercises"] == []
        assert data[1]["exercises"][0] == {"name": "Squat", "sets": 5, "reps": 5, "weight": 100.0}

    def test_date_defaults_to_today(self, sample_client):
        resp = sample_client.post("/api/clients/Prerna/workouts", json={"workout_type": "Mixed"})
        assert resp.get_json()["date"] == date.today().isoformat()

    @pytest.mark.parametrize(
        "payload",
        [
            {"workout_type": "Dancing"},
            {},
            {"workout_type": "Strength", "date": "yesterday"},
            {"workout_type": "Strength", "duration_min": 0},
            {"workout_type": "Strength", "exercises": "Squat"},
            {"workout_type": "Strength", "exercises": [{"sets": 3}]},
            {"workout_type": "Strength", "exercises": [{"name": "Squat", "sets": 0}]},
        ],
    )
    def test_validation(self, sample_client, payload):
        assert sample_client.post("/api/clients/Prerna/workouts", json=payload).status_code == 400

    def test_invalid_workout_is_not_partially_saved(self, sample_client):
        bad = {"workout_type": "Strength", "exercises": [{"name": "Squat"}, {"name": ""}]}
        sample_client.post("/api/clients/Prerna/workouts", json=bad)
        assert sample_client.get("/api/clients/Prerna/workouts").get_json() == []


# ---------- body metrics ----------


class TestMetrics:
    def test_add_and_list_sorted_by_date(self, sample_client):
        sample_client.post("/api/clients/Prerna/metrics", json={"date": "2026-10-08", "weight": 79})
        sample_client.post("/api/clients/Prerna/metrics", json={"date": "2026-10-01", "weight": 81})
        data = sample_client.get("/api/clients/Prerna/metrics").get_json()
        assert [m["date"] for m in data] == ["2026-10-01", "2026-10-08"]

    def test_weigh_in_updates_client_weight_and_calories(self, sample_client):
        sample_client.post(
            "/api/clients/Prerna/metrics",
            json={"date": "2026-10-01", "weight": 82, "waist": 85, "bodyfat": 18},
        )
        client = sample_client.get("/api/clients/Prerna").get_json()
        assert client["weight"] == 82
        assert client["calories"] == 82 * 35

    def test_metrics_without_weight_keep_client_weight(self, sample_client):
        sample_client.post("/api/clients/Prerna/metrics", json={"waist": 84})
        assert sample_client.get("/api/clients/Prerna").get_json()["weight"] == 80

    @pytest.mark.parametrize(
        "payload",
        [{"date": "bad"}, {"weight": 5}, {"waist": 1000}, {"bodyfat": 90}, {"weight": "heavy"}],
    )
    def test_validation(self, sample_client, payload):
        assert sample_client.post("/api/clients/Prerna/metrics", json=payload).status_code == 400


# ---------- analytics ----------


class TestAnalytics:
    def test_bmi(self, sample_client):
        resp = sample_client.get("/api/clients/Prerna/bmi")
        assert resp.status_code == 200
        assert resp.get_json()["bmi"] == 26.1
        assert resp.get_json()["category"] == "Overweight"

    def test_bmi_requires_height_and_weight(self, auth_client):
        auth_client.post("/api/clients", json={"name": "Asha", "program": "Beginner (BG)"})
        assert auth_client.get("/api/clients/Asha/bmi").status_code == 400

    def test_summary_empty_history(self, sample_client):
        data = sample_client.get("/api/clients/Prerna/summary").get_json()
        assert data["client"]["name"] == "Prerna"
        assert data["program_notes"] == "Push/Pull/Legs hypertrophy"
        assert data["weeks_logged"] == 0
        assert data["average_adherence"] == 0
        assert data["workouts_logged"] == 0
        assert data["last_metrics"] is None

    def test_summary_aggregates_history(self, sample_client):
        for adherence in (70, 80, 95):
            sample_client.post("/api/clients/Prerna/progress", json={"adherence": adherence})
        sample_client.post("/api/clients/Prerna/workouts", json={"workout_type": "Strength"})
        sample_client.post("/api/clients/Prerna/metrics", json={"date": "2026-09-01", "weight": 81})
        sample_client.post("/api/clients/Prerna/metrics", json={"date": "2026-10-01", "weight": 79})

        data = sample_client.get("/api/clients/Prerna/summary").get_json()
        assert data["weeks_logged"] == 3
        assert data["average_adherence"] == 81.7
        assert data["workouts_logged"] == 1
        assert data["last_metrics"]["date"] == "2026-10-01"

    def test_summary_missing_client(self, auth_client):
        assert auth_client.get("/api/clients/Ghost/summary").status_code == 404

    def test_generate_program(self, sample_client):
        resp = sample_client.post(
            "/api/clients/Prerna/generate-program", json={"experience": "Intermediate"}
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["experience"] == "intermediate"
        assert len(data["plan"]) == 4 * 4
        assert {p["exercise"] for p in data["plan"]} <= set(fitness.EXERCISE_POOL["Hypertrophy"])

    def test_generate_program_seed_is_reproducible(self, sample_client):
        payload = {"experience": "advanced", "seed": 7}
        first = sample_client.post("/api/clients/Prerna/generate-program", json=payload).get_json()
        second = sample_client.post("/api/clients/Prerna/generate-program", json=payload).get_json()
        assert first == second

    @pytest.mark.parametrize("payload", [{}, {"experience": "expert"}, None])
    def test_generate_program_invalid_experience(self, sample_client, payload):
        resp = sample_client.post("/api/clients/Prerna/generate-program", json=payload)
        assert resp.status_code == 400
