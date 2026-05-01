from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from bio.models import Profile
from fitness.models import (
    Exercise,
    ExercisePool,
    ExercisePoolItem,
    WorkoutSession,
)


@override_settings(ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"])
class ApiWorkoutSessionCreateTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.password = "LocalTestPassword123!"
        self.user = User.objects.create_user(
            username="api_session_user",
            email="api_session_user@example.com",
            password=self.password,
        )
        Profile.objects.get_or_create(user=self.user)

        self.exercise = Exercise.objects.create(
            name="API Test Bench Press",
            slug="api-test-bench-press",
            primary_pattern="PUSH",
            is_custom=False,
            is_active=True,
        )
        self.pool = ExercisePool.objects.create(
            user=self.user,
            name="API Test Pool",
            focus="CUSTOM",
            description="Pool for API session create tests",
            is_active=True,
        )
        ExercisePoolItem.objects.create(
            pool=self.pool,
            exercise=self.exercise,
            sequence=1,
        )

    def _login(self):
        response = self.client.post(
            "/api/v1/auth/login/",
            data={
                "identity": self.user.username,
                "password": self.password,
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["data"]["tokens"]["access"]

    def test_create_workout_session_returns_201(self):
        access = self._login()
        client_uuid = str(uuid4())

        response = self.client.post(
            "/api/v1/workout-sessions/",
            data={
                "client_uuid": client_uuid,
                "focus": "CUSTOM",
                "source_pool_id": self.pool.id,
                "scheduled_date": "2026-05-02",
                "notes": "API session create test",
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {access}",
        )
        self.assertEqual(response.status_code, 201)

        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["created"])
        self.assertEqual(payload["data"]["client_uuid"], client_uuid)
        self.assertEqual(payload["data"]["imported_exercise_count"], 1)
        self.assertEqual(WorkoutSession.objects.count(), 1)
        self.assertEqual(WorkoutSession.objects.first().session_exercises.count(), 1)

    def test_create_workout_session_is_idempotent_by_client_uuid(self):
        access = self._login()
        client_uuid = str(uuid4())

        first = self.client.post(
            "/api/v1/workout-sessions/",
            data={
                "client_uuid": client_uuid,
                "focus": "CUSTOM",
                "source_pool_id": self.pool.id,
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {access}",
        )
        self.assertEqual(first.status_code, 201)

        second = self.client.post(
            "/api/v1/workout-sessions/",
            data={
                "client_uuid": client_uuid,
                "focus": "CUSTOM",
                "source_pool_id": self.pool.id,
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {access}",
        )
        self.assertEqual(second.status_code, 200)

        payload = second.json()
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["created"])
        self.assertEqual(WorkoutSession.objects.count(), 1)