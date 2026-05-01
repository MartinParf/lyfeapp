from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from bio.models import Activity, Profile


@override_settings(ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"])
class ApiActivityCreateTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.password = "LocalTestPassword123!"
        self.user = User.objects.create_user(
            username="api_activity_user",
            email="api_activity_user@example.com",
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

    def test_create_activity_returns_201(self):
        access = self._login()
        client_uuid = str(uuid4())

        response = self.client.post(
            "/api/v1/activities/",
            data={
                "client_uuid": client_uuid,
                "date": "2026-05-01",
                "activity_type": "WALKING",
                "duration_minutes": 45,
                "calories_burned_est": 250,
                "distance_km": "3.5",
                "notes": "API create test",
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {access}",
        )
        self.assertEqual(response.status_code, 201)

        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["created"])
        self.assertEqual(payload["data"]["client_uuid"], client_uuid)
        self.assertEqual(Activity.objects.count(), 1)

    def test_create_activity_is_idempotent_by_client_uuid(self):
        access = self._login()
        client_uuid = str(uuid4())

        first = self.client.post(
            "/api/v1/activities/",
            data={
                "client_uuid": client_uuid,
                "date": "2026-05-01",
                "activity_type": "WALKING",
                "duration_minutes": 45,
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {access}",
        )
        self.assertEqual(first.status_code, 201)

        second = self.client.post(
            "/api/v1/activities/",
            data={
                "client_uuid": client_uuid,
                "date": "2026-05-01",
                "activity_type": "WALKING",
                "duration_minutes": 45,
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {access}",
        )
        self.assertEqual(second.status_code, 200)

        payload = second.json()
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["created"])
        self.assertEqual(Activity.objects.count(), 1)