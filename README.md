# ACEest Fitness & Gym

A Flask web application for gym and fitness management, built as part of the **Introduction to DevOps (CSIZG514/SEZG514)** assignment. It is a web-based rewrite of the ACEest Tkinter desktop scripts (v1.0 – v3.1.2), covering client management, workout and body-metric logging, BMI analysis and workout plan generation.

This README covers environment setup and execution for every stage implemented so far:

1. [Application (Flask)](#1-application-setup-and-execution)
2. [Version control workflow](#2-version-control-workflow)
3. [Unit tests (Pytest)](#3-running-the-tests)
4. [Containerisation (Docker)](#4-docker)

---

## Repository layout

```
├── app.py                  # Entry point (creates the Flask app)
├── aceest/
│   ├── __init__.py         # create_app() factory and configuration
│   ├── fitness.py          # Business logic: calories, BMI, membership, plan generator
│   ├── db.py               # SQLite schema, per-request connection, admin seeding
│   ├── routes.py           # HTTP / REST endpoints
│   └── templates/index.html
├── tests/
│   ├── conftest.py         # Fixtures (isolated temp database per test)
│   ├── test_fitness.py     # Unit tests for business logic
│   └── test_routes.py      # API / integration tests
├── requirements.txt        # Runtime dependencies (Flask, gunicorn)
├── requirements-dev.txt    # Test dependencies (pytest, pytest-cov)
├── pytest.ini
├── Dockerfile              # Multi-stage build: test and runtime targets
└── .dockerignore
```

## Prerequisites

| Tool   | Version          | Needed for          |
|--------|------------------|---------------------|
| Python | 3.9 or newer     | Steps 1 and 3       |
| Git    | any recent       | Step 2              |
| Docker | 20.10 or newer   | Step 4              |

Tested on **Rocky Linux 9.5** (Python 3.9) and **Windows 11** (Python 3.12+).

---

## 1. Application setup and execution

### 1.1 Clone the repository

```bash
git clone https://github.com/2025tm93207-boop/devops_asgn_gym_and_fitness_app.git
cd devops_asgn_gym_and_fitness_app
```

### 1.2 Create a virtual environment and install dependencies

**Rocky Linux / any Linux**

```bash
sudo dnf install -y python3 python3-pip      # only if Python is missing
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

**Windows (PowerShell)**

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 1.3 Run the application

```bash
python app.py
```

The app starts on <http://127.0.0.1:5000>. The SQLite database is created automatically at `instance/aceest_fitness.db` on first start, with a default `admin` / `admin` account.

To make the app reachable from other machines (e.g. browsing to a lab VM from your laptop), bind to all interfaces and open the port:

```bash
HOST=0.0.0.0 python app.py

# Rocky Linux firewall (one-time)
sudo firewall-cmd --permanent --add-port=5000/tcp
sudo firewall-cmd --reload
```

Then open `http://<VM-IP>:5000` (find the IP with `hostname -I`). If the lab network blocks the port, use an SSH tunnel instead: `ssh -L 5000:localhost:5000 <user>@<VM-IP>` and browse to <http://localhost:5000>.

### 1.4 Configuration

All settings are read from environment variables:

| Variable         | Default                         | Purpose                                   |
|------------------|---------------------------------|-------------------------------------------|
| `HOST`           | `127.0.0.1`                     | Bind address for `python app.py`          |
| `PORT`           | `5000`                          | Port for `python app.py`                  |
| `FLASK_DEBUG`    | unset                           | Set to `1` to enable debug mode           |
| `SECRET_KEY`     | `dev-only-change-me`            | Session signing key — **set in production** |
| `DATABASE`       | `instance/aceest_fitness.db`    | SQLite database file path                 |
| `ADMIN_USERNAME` | `admin`                         | Default admin account created at startup  |
| `ADMIN_PASSWORD` | `admin`                         | Password for the default admin account    |

Example: `SECRET_KEY=$(openssl rand -hex 32) ADMIN_PASSWORD=MyPass123 HOST=0.0.0.0 python app.py`

### 1.5 API reference

| Method           | Endpoint                                   | Auth | Purpose                               |
|------------------|--------------------------------------------|------|---------------------------------------|
| GET              | `/`                                        | –    | Landing page (programs + API list)    |
| GET              | `/health`                                  | –    | Health check                          |
| GET              | `/api/programs`                            | –    | List training programs                |
| POST             | `/api/login`, `/api/logout`                | –    | Start / end a session                 |
| GET, POST        | `/api/clients`                             | ✔    | List / create clients                 |
| GET, PUT, DELETE | `/api/clients/<name>`                      | ✔    | Read / update / delete a client       |
| GET, POST        | `/api/clients/<name>/progress`             | ✔    | Weekly adherence (0–100 %)            |
| GET, POST        | `/api/clients/<name>/workouts`             | ✔    | Workout sessions with exercises       |
| GET, POST        | `/api/clients/<name>/metrics`              | ✔    | Body metrics (weight, waist, bodyfat) |
| GET              | `/api/clients/<name>/bmi`                  | ✔    | BMI with category and risk note       |
| GET              | `/api/clients/<name>/summary`              | ✔    | Dashboard summary                     |
| POST             | `/api/clients/<name>/generate-program`     | ✔    | Generate a weekly workout plan        |

Valid programs: `Fat Loss (FL) – 3 day`, `Fat Loss (FL) – 5 day`, `Muscle Gain (MG) – PPL`, `Beginner (BG)`.
Valid workout types: `Strength`, `Hypertrophy`, `Conditioning`, `Mixed`, `Mobility`.
Valid experience levels: `beginner`, `intermediate`, `advanced`.

### 1.6 Quick API walkthrough (curl)

Run these in a second terminal while the app is running. `-c` / `-b` store and send the session cookie.

```bash
# Health check
curl http://127.0.0.1:5000/health

# Log in
curl -c cookies.txt -H "Content-Type: application/json" \
     -d '{"username":"admin","password":"admin"}' \
     http://127.0.0.1:5000/api/login

# Create a client
curl -b cookies.txt -H "Content-Type: application/json" \
     -d '{"name":"Prerna","age":30,"height":165,"weight":60,"program":"Beginner (BG)","membership_expiry":"2027-12-31"}' \
     http://127.0.0.1:5000/api/clients

# Log weekly adherence, a workout and body metrics
curl -b cookies.txt -H "Content-Type: application/json" -d '{"adherence":85}' \
     http://127.0.0.1:5000/api/clients/Prerna/progress
curl -b cookies.txt -H "Content-Type: application/json" \
     -d '{"workout_type":"Strength","duration_min":60,"exercises":[{"name":"Squat","sets":5,"reps":5,"weight":40}]}' \
     http://127.0.0.1:5000/api/clients/Prerna/workouts
curl -b cookies.txt -H "Content-Type: application/json" -d '{"weight":59.5,"waist":72,"bodyfat":24}' \
     http://127.0.0.1:5000/api/clients/Prerna/metrics

# Analytics
curl -b cookies.txt http://127.0.0.1:5000/api/clients/Prerna/bmi
curl -b cookies.txt http://127.0.0.1:5000/api/clients/Prerna/summary
curl -b cookies.txt -H "Content-Type: application/json" -d '{"experience":"beginner"}' \
     http://127.0.0.1:5000/api/clients/Prerna/generate-program
```

> **Windows PowerShell:** use `curl.exe` (not the `curl` alias) and escape inner quotes, e.g.
> `-d '{\"username\":\"admin\",\"password\":\"admin\"}'`.

Errors are returned as JSON (`{"error": "..."}`) with status `400` (validation), `401` (not logged in / bad credentials), `404` (client not found) or `409` (duplicate client).

To reset all data, stop the app and delete `instance/aceest_fitness.db`.

---

## 2. Version control workflow

The repository follows a feature-branch workflow: `main` always holds reviewed, working code, and every change is developed on its own branch and merged through a GitHub pull request.

| Branch                  | Purpose                                  |
|-------------------------|------------------------------------------|
| `main`                  | Stable, merged code                      |
| `feature/pytest-suite`  | Pytest unit and API test suite           |
| `feature/docker`        | Dockerfile and container setup           |

Typical flow for a new change:

```bash
git checkout main
git pull                                   # start from the latest main
git checkout -b feature/<short-name>       # e.g. feature/github-actions

# ... make changes, run tests ...

git add <files>
git commit -m "Add <what> for <why>"       # descriptive, imperative messages
git push -u origin feature/<short-name>
```

Then open a pull request into `main` on GitHub, review it and merge. After merging, update your local copy:

```bash
git checkout main
git pull
git branch -d feature/<short-name>
```

Local-only files (virtual environments, `instance/`, `*.db`, caches, `cookies.txt`) are excluded via `.gitignore`.

---

## 3. Running the tests

The suite has two parts:

- `tests/test_fitness.py` — unit tests for the business logic in `aceest/fitness.py` (calorie targets, BMI and category boundaries, membership status, workout plan generation).
- `tests/test_routes.py` — API tests for every endpoint, covering authentication, CRUD, validation errors and analytics.

Each test runs against its own temporary SQLite database, so tests never touch `instance/aceest_fitness.db` and do not affect each other.

### 3.1 Install test dependencies

With the virtual environment from step 1.2 activated:

```bash
pip install -r requirements-dev.txt
```

### 3.2 Run

```bash
pytest                                            # run the whole suite
pytest -v                                         # verbose: one line per test
pytest tests/test_fitness.py                      # a single file
pytest tests/test_routes.py::TestClients          # a single test class
pytest -k bmi                                     # tests whose name matches "bmi"
pytest --cov=aceest --cov-report=term-missing     # with a coverage report
pytest --cov=aceest --cov-report=html             # HTML report in htmlcov/index.html
```

Expected result: **133 passed**, with ~99 % coverage of the `aceest` package. A full run takes under a minute (most of the time is password hashing, which is deliberately slow).

---

## 4. Docker

The [Dockerfile](Dockerfile) is a multi-stage build:

| Stage     | Contents                                                       | Use                                   |
|-----------|----------------------------------------------------------------|---------------------------------------|
| `builder` | Installs `requirements.txt` into a virtualenv                  | Internal; not shipped                 |
| `test`    | App + pytest + tests; default command runs `pytest`            | `docker build --target test`          |
| `runtime` | App + gunicorn only; **default target**                        | `docker build` (production image)     |

Image characteristics:

- Based on `python:3.12-slim-bookworm`; the final image is ~54 MB compressed and contains no build tools or test dependencies.
- Runs as an unprivileged `app` user, not root.
- Served by **gunicorn** (2 workers) instead of the Flask development server.
- Built-in `HEALTHCHECK` against `/health`.
- SQLite data lives in the `/app/instance` volume, so it survives container restarts.

### 4.1 Install Docker on Rocky Linux 9.5

Rocky ships Podman by default; remove the conflicting packages and install Docker CE:

```bash
sudo dnf remove -y podman buildah runc
sudo dnf install -y dnf-plugins-core
sudo dnf config-manager --add-repo https://download.docker.com/linux/rhel/docker-ce.repo
sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker $USER      # log out and back in for this to take effect
docker version                     # verify
```

On Windows, install and start **Docker Desktop**.

### 4.2 Run the tests inside a container

```bash
docker build --target test -t aceest-fitness:test .
docker run --rm aceest-fitness:test
```

The container exits with status `0` when all tests pass and non-zero otherwise.

### 4.3 Build and run the application image

```bash
docker build -t aceest-fitness:latest .

docker run -d --name aceest \
  -p 5000:5000 \
  -e SECRET_KEY="$(openssl rand -hex 32)" \
  -e ADMIN_PASSWORD="ChangeMe123" \
  -v aceest-data:/app/instance \
  aceest-fitness:latest
```

> On Windows PowerShell, put the command on one line (or use `` ` `` for line continuation) and replace `$(openssl rand -hex 32)` with any long random string.

The app is then available at <http://localhost:5000> (or `http://<VM-IP>:5000`; see step 1.3 for the firewall rule).

### 4.4 Manage the container

```bash
docker ps                          # STATUS shows "(healthy)" ~10 s after start
docker logs -f aceest              # gunicorn and request logs
docker exec -it aceest sh          # shell inside the container
docker stop aceest                 # stop
docker start aceest                # start again (data is kept)
docker rm -f aceest                # remove the container (volume is kept)
docker volume rm aceest-data       # delete all stored data
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `python: command not found` (Rocky) | Use `python3`, or activate the venv first (`source venv/bin/activate`). |
| `Python was not found` (Windows) | Use the `py` launcher: `py -m venv .venv`. |
| Browser cannot reach `http://<VM-IP>:5000` | Start with `HOST=0.0.0.0`, open port 5000 in `firewalld`, or use an SSH tunnel. |
| `Address already in use` | Another process (or container) is on port 5000; stop it or run with `PORT=5001` / `-p 5001:5000`. |
| `{"error": "Authentication required"}` | Log in first and pass the cookie file with `-b cookies.txt`. |
| `permission denied ... docker.sock` | Add your user to the `docker` group and log in again, or prefix with `sudo`. |
| `dnf install docker-ce` reports conflicts | Remove `podman buildah runc` first (step 4.1). |
| Container stays `unhealthy` | Check `docker logs aceest` for startup errors. |
