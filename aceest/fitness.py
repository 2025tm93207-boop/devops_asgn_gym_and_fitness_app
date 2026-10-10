"""Pure business logic for ACEest Fitness & Gym.

Ported from the original Tkinter desktop scripts (Aceestver-1.0 .. 3.1.2).
Nothing in this module touches Flask or the database, so it can be unit
tested in isolation.
"""
import random
from datetime import date

PROGRAMS = {
    "Fat Loss (FL) – 3 day": {
        "factor": 22,
        "desc": "3-day full-body fat loss",
        "focus": "Conditioning",
    },
    "Fat Loss (FL) – 5 day": {
        "factor": 24,
        "desc": "5-day split, higher volume fat loss",
        "focus": "Conditioning",
    },
    "Muscle Gain (MG) – PPL": {
        "factor": 35,
        "desc": "Push/Pull/Legs hypertrophy",
        "focus": "Hypertrophy",
    },
    "Beginner (BG)": {
        "factor": 26,
        "desc": "3-day simple beginner full-body",
        "focus": "Full Body",
    },
}

DEFAULT_CALORIE_FACTOR = 25

EXERCISE_POOL = {
    "Strength": ["Squat", "Deadlift", "Bench Press", "Overhead Press", "Pull-Up", "Barbell Row"],
    "Hypertrophy": [
        "Leg Press",
        "Incline Dumbbell Press",
        "Lat Pulldown",
        "Lateral Raise",
        "Bicep Curl",
        "Tricep Extension",
    ],
    "Conditioning": ["Running", "Cycling", "Rowing", "Burpees", "Jump Rope", "Kettlebell Swings"],
    "Full Body": ["Push-Up", "Pull-Up", "Lunge", "Plank", "Dumbbell Row", "Dumbbell Press"],
}

EXPERIENCE_LEVELS = {
    "beginner": {"sets": (2, 3), "reps": (8, 12), "days": 3},
    "intermediate": {"sets": (3, 4), "reps": (8, 15), "days": 4},
    "advanced": {"sets": (4, 5), "reps": (6, 15), "days": 5},
}

WEEK_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]

WORKOUT_TYPES = ["Strength", "Hypertrophy", "Conditioning", "Mixed", "Mobility"]


def calculate_calories(weight_kg, program):
    """Daily calorie target = body weight (kg) x program factor."""
    if weight_kg is None or weight_kg <= 0:
        return None
    factor = PROGRAMS.get(program, {}).get("factor", DEFAULT_CALORIE_FACTOR)
    return int(weight_kg * factor)


def calculate_bmi(height_cm, weight_kg):
    """Return BMI rounded to 1 decimal place."""
    if not height_cm or not weight_kg or height_cm <= 0 or weight_kg <= 0:
        raise ValueError("Height and weight must be positive numbers")
    height_m = height_cm / 100.0
    return round(weight_kg / (height_m * height_m), 1)


def bmi_category(bmi):
    """Return (category, risk note) for a BMI value."""
    if bmi < 18.5:
        return "Underweight", "Potential nutrient deficiency, low energy."
    if bmi < 25:
        return "Normal", "Low risk if active and strong."
    if bmi < 30:
        return "Overweight", "Moderate risk; focus on adherence and progressive activity."
    return "Obese", "Higher risk; prioritize fat loss, consistency, and supervision."


def membership_status(expiry, today=None):
    """Classify a YYYY-MM-DD membership expiry as active / expired / unknown."""
    if not expiry:
        return "unknown"
    today = today or date.today()
    try:
        expiry_date = date.fromisoformat(expiry)
    except ValueError:
        return "unknown"
    return "active" if expiry_date >= today else "expired"


def generate_program(program_name, experience, rng=None):
    """Generate a weekly workout plan for a client.

    Returns a list of {"day", "exercise", "sets", "reps"} dicts.
    Pass a seeded ``random.Random`` as ``rng`` for reproducible output.
    """
    level = EXPERIENCE_LEVELS.get((experience or "").lower())
    if level is None:
        raise ValueError(
            f"Invalid experience level; expected one of {', '.join(EXPERIENCE_LEVELS)}"
        )
    rng = rng or random.Random()

    focus = PROGRAMS.get(program_name, {}).get("focus", "Full Body")
    days = level["days"]
    per_day = 3 if days < 4 else 4

    plan = []
    for day in WEEK_DAYS[:days]:
        for exercise in rng.sample(EXERCISE_POOL[focus], k=per_day):
            plan.append(
                {
                    "day": day,
                    "exercise": exercise,
                    "sets": rng.randint(*level["sets"]),
                    "reps": rng.randint(*level["reps"]),
                }
            )
    return plan
