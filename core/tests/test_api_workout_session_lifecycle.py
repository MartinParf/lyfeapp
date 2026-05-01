from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from bio.models import Profile
from fitness.models import WorkoutSession, WorkoutSessionStatus


@override_settings(ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"])
class ApiWorkoutSessionLifecycleTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.password = "LocalTestPassword123!"
        self.user = User.objects.create_user(
            username="api_session_lifecycle_user",
            email="api_session_lifecycle_user@example.com",
            password=self.password,
        )
        Profile.objects.get_or_create(user=self.user)

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

    def test_start_session_transitions_planned_to_in_progress(self):
        session = WorkoutSession.objects.create(
            user=self.user,
            focus="CUSTOM",
            status=WorkoutSessionStatus.PLANNED,
        )
        access = self._login()

        response = self.client.post(
            f"/api/v1/workout-sessions/{session.id}/start/",
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {access}",
        )
        self.assertEqual(response.status_code, 200)

        session.refresh_from_db()
        self.assertEqual(session.status, WorkoutSessionStatus.IN_PROGRESS)
        self.assertIsNotNone(session.started_at)

    def test_complete_session_transitions_in_progress_to_completed(self):
        from django.utils import timezone

        # 1. Přímé vytvoření tréninku ve stavu IN_PROGRESS
        session = WorkoutSession.objects.create(
            user=self.user,
            focus="CUSTOM",
            status=WorkoutSessionStatus.IN_PROGRESS,
            started_at=timezone.now(),
        )
        access = self._login()

        # 2. Zavolání API pro dokončení tréninku
        response = self.client.post(
            f"/api/v1/workout-sessions/{session.id}/complete/",
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {access}",
        )
        
        # 3. Striktní ověření výsledku
        self.assertEqual(response.status_code, 200)

        session.refresh_from_db()
        self.assertEqual(session.status, WorkoutSessionStatus.COMPLETED)
        self.assertIsNotNone(session.ended_at)

    def test_cancel_session_transitions_planned_to_cancelled(self):
        session = WorkoutSession.objects.create(
            user=self.user,
            focus="CUSTOM",
            status=WorkoutSessionStatus.PLANNED,
        )
        access = self._login()

        response = self.client.post(
            f"/api/v1/workout-sessions/{session.id}/cancel/",
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {access}",
        )
        self.assertEqual(response.status_code, 200)

        session.refresh_from_db()
        self.assertEqual(session.status, WorkoutSessionStatus.CANCELLED)

    def test_complete_planned_session_returns_409(self):
        session = WorkoutSession.objects.create(
            user=self.user,
            focus="CUSTOM",
            status=WorkoutSessionStatus.PLANNED,
        )
        access = self._login()

        response = self.client.post(
            f"/api/v1/workout-sessions/{session.id}/complete/",
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {access}",
        )
        self.assertEqual(response.status_code, 409)

        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "invalid_state_transition")