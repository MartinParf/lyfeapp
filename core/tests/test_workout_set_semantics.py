from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from bio.models import Profile
from fitness.models import (
    Exercise,
    WorkoutSession,
    WorkoutSessionExercise,
    WorkoutSessionStatus,
    WorkoutSet,
    WorkoutSetType,
)


class WorkoutSetSemanticsTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="set_semantics_user",
            email="set_semantics_user@example.com",
            password="LocalTestPassword123!",
        )
        Profile.objects.get_or_create(user=self.user)

        self.exercise = Exercise.objects.create(
            name="Set Semantics Bench Press",
            slug="set-semantics-bench-press",
            primary_pattern="PUSH",
            is_custom=False,
            is_active=True,
        )

        self.session = WorkoutSession.objects.create(
            user=self.user,
            focus="CUSTOM",
            status=WorkoutSessionStatus.PLANNED,
        )

        self.session_exercise = WorkoutSessionExercise.objects.create(
            session=self.session,
            exercise=self.exercise,
            sequence=1,
        )

    def test_set_requires_weight_or_reps(self):
        workout_set = WorkoutSet(
            session_exercise=self.session_exercise,
            set_order=1,
            notes="note only should not be enough",
        )

        with self.assertRaises(ValidationError) as ctx:
            workout_set.full_clean()

        self.assertIn("__all__", ctx.exception.message_dict)

    def test_set_with_reps_only_is_valid(self):
        workout_set = WorkoutSet(
            session_exercise=self.session_exercise,
            set_order=1,
            reps=12,
        )

        workout_set.full_clean()
        self.assertTrue(workout_set.has_primary_performance_data)
        self.assertTrue(workout_set.is_progression_relevant)

    def test_set_with_weight_only_is_valid(self):
        workout_set = WorkoutSet(
            session_exercise=self.session_exercise,
            set_order=1,
            weight_kg=Decimal("82.5"),
        )

        workout_set.full_clean()
        self.assertTrue(workout_set.has_primary_performance_data)
        self.assertTrue(workout_set.is_progression_relevant)

    def test_rpe_must_be_between_1_and_10(self):
        workout_set = WorkoutSet(
            session_exercise=self.session_exercise,
            set_order=1,
            reps=8,
            rpe=Decimal("10.5"),
        )

        with self.assertRaises(ValidationError) as ctx:
            workout_set.full_clean()

        self.assertIn("rpe", ctx.exception.message_dict)

    def test_amrap_requires_reps(self):
        workout_set = WorkoutSet(
            session_exercise=self.session_exercise,
            set_order=1,
            set_type=WorkoutSetType.AMRAP,
            weight_kg=Decimal("40.0"),
        )

        with self.assertRaises(ValidationError) as ctx:
            workout_set.full_clean()

        self.assertIn("reps", ctx.exception.message_dict)