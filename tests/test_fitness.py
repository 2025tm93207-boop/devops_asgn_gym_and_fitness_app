"""Unit tests for the pure business logic in aceest.fitness."""
import random
from datetime import date

import pytest

from aceest import fitness


class TestCalories:
    @pytest.mark.parametrize(
        "program, expected",
        [
            ("Fat Loss (FL) – 3 day", 80 * 22),
            ("Fat Loss (FL) – 5 day", 80 * 24),
            ("Muscle Gain (MG) – PPL", 80 * 35),
            ("Beginner (BG)", 80 * 26),
        ],
    )
    def test_uses_program_factor(self, program, expected):
        assert fitness.calculate_calories(80, program) == expected

    def test_unknown_program_uses_default_factor(self):
        assert fitness.calculate_calories(80, "Unknown") == 80 * fitness.DEFAULT_CALORIE_FACTOR

    def test_result_is_truncated_to_int(self):
        assert fitness.calculate_calories(70.5, "Beginner (BG)") == int(70.5 * 26)

    @pytest.mark.parametrize("weight", [None, 0, -5])
    def test_missing_or_invalid_weight_returns_none(self, weight):
        assert fitness.calculate_calories(weight, "Beginner (BG)") is None


class TestBmi:
    def test_calculation(self):
        assert fitness.calculate_bmi(175, 80) == 26.1

    def test_rounded_to_one_decimal(self):
        assert fitness.calculate_bmi(180, 75) == 23.1

    @pytest.mark.parametrize("height, weight", [(0, 80), (175, 0), (None, 80), (175, None), (-1, 80)])
    def test_invalid_input_raises(self, height, weight):
        with pytest.raises(ValueError):
            fitness.calculate_bmi(height, weight)

    @pytest.mark.parametrize(
        "bmi, category",
        [
            (17.0, "Underweight"),
            (18.4, "Underweight"),
            (18.5, "Normal"),
            (24.9, "Normal"),
            (25.0, "Overweight"),
            (29.9, "Overweight"),
            (30.0, "Obese"),
            (40.0, "Obese"),
        ],
    )
    def test_category_boundaries(self, bmi, category):
        assert fitness.bmi_category(bmi)[0] == category

    def test_category_includes_risk_note(self):
        _, risk = fitness.bmi_category(22)
        assert risk


class TestMembershipStatus:
    TODAY = date(2026, 6, 15)

    def test_future_expiry_is_active(self):
        assert fitness.membership_status("2026-12-31", self.TODAY) == "active"

    def test_expiry_today_is_still_active(self):
        assert fitness.membership_status("2026-06-15", self.TODAY) == "active"

    def test_past_expiry_is_expired(self):
        assert fitness.membership_status("2026-01-01", self.TODAY) == "expired"

    @pytest.mark.parametrize("value", [None, "", "not-a-date", "2026/01/01"])
    def test_missing_or_malformed_is_unknown(self, value):
        assert fitness.membership_status(value, self.TODAY) == "unknown"


class TestGenerateProgram:
    @pytest.mark.parametrize(
        "experience, days, per_day",
        [("beginner", 3, 3), ("intermediate", 4, 4), ("advanced", 5, 4)],
    )
    def test_plan_shape_matches_experience(self, experience, days, per_day):
        plan = fitness.generate_program("Beginner (BG)", experience)
        assert len(plan) == days * per_day
        assert [p["day"] for p in plan[::per_day]] == fitness.WEEK_DAYS[:days]

    @pytest.mark.parametrize("experience", list(fitness.EXPERIENCE_LEVELS))
    def test_sets_and_reps_within_level_ranges(self, experience):
        level = fitness.EXPERIENCE_LEVELS[experience]
        for item in fitness.generate_program("Beginner (BG)", experience):
            assert level["sets"][0] <= item["sets"] <= level["sets"][1]
            assert level["reps"][0] <= item["reps"] <= level["reps"][1]

    @pytest.mark.parametrize(
        "program, focus",
        [
            ("Fat Loss (FL) – 3 day", "Conditioning"),
            ("Fat Loss (FL) – 5 day", "Conditioning"),
            ("Muscle Gain (MG) – PPL", "Hypertrophy"),
            ("Beginner (BG)", "Full Body"),
            ("Unknown Program", "Full Body"),
        ],
    )
    def test_exercises_come_from_program_focus(self, program, focus):
        plan = fitness.generate_program(program, "advanced")
        assert {p["exercise"] for p in plan} <= set(fitness.EXERCISE_POOL[focus])

    def test_no_duplicate_exercises_within_a_day(self):
        plan = fitness.generate_program("Beginner (BG)", "advanced")
        for day in fitness.WEEK_DAYS[:5]:
            names = [p["exercise"] for p in plan if p["day"] == day]
            assert len(names) == len(set(names))

    def test_experience_is_case_insensitive(self):
        assert len(fitness.generate_program("Beginner (BG)", "BeGiNnEr")) == 9

    def test_seeded_rng_is_reproducible(self):
        first = fitness.generate_program("Beginner (BG)", "advanced", random.Random(42))
        second = fitness.generate_program("Beginner (BG)", "advanced", random.Random(42))
        assert first == second

    @pytest.mark.parametrize("experience", [None, "", "expert"])
    def test_invalid_experience_raises(self, experience):
        with pytest.raises(ValueError):
            fitness.generate_program("Beginner (BG)", experience)
