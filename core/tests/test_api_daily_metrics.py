from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from bio.models import DailyMetric, Profile


@override_settings(ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"])
class ApiDailyMetricUpsertTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.password = "LocalTestPassword123!"
        self.user = User.objects.create_user(
            username="api_daily_metric_user",
            email="api_daily_metric_user@example.com",
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

    def test_upsert_daily_metric_creates_row(self):
        access = self._login()

        response = self.client.put(
            "/api/v1/daily-metrics/by-date/2026-05-01/",
            data={
                "weight_kg": "82.4",
                "diet_mode": "STANDARD",
                "sleep_quality": 4,
                "alcohol_units": 1,
                "calories_planned": 2400,
                "calories_actual": 2350,
                "notes": "create test",
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {access}",
        )
        self.assertEqual(response.status_code, 201)

        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["created"])
        self.assertEqual(payload["data"]["date"], "2026-05-01")
        self.assertEqual(DailyMetric.objects.count(), 1)

    def test_upsert_daily_metric_updates_existing_row(self):
        access = self._login()

        first = self.client.put(
            "/api/v1/daily-metrics/by-date/2026-05-01/",
            data={
                "weight_kg": "82.4",
                "diet_mode": "STANDARD",
                "sleep_quality": 4,
                "alcohol_units": 1,
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {access}",
        )
        self.assertEqual(first.status_code, 201)

        second = self.client.put(
            "/api/v1/daily-metrics/by-date/2026-05-01/",
            data={
                "weight_kg": "81.9",
                "diet_mode": "LOW_CARB",
                "sleep_quality": 5,
                "alcohol_units": 0,
                "notes": "updated test",
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {access}",
        )
        self.assertEqual(second.status_code, 200)

        payload = second.json()
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["created"])
        self.assertEqual(payload["data"]["weight_kg"], "81.9")
        self.assertEqual(payload["data"]["diet_mode"], "LOW_CARB")
        self.assertEqual(payload["data"]["sleep_quality"], 5)
        self.assertEqual(payload["data"]["notes"], "updated test")
        self.assertEqual(DailyMetric.objects.count(), 1)

    def test_upsert_daily_metric_invalid_sleep_quality_returns_400(self):
        access = self._login()

        response = self.client.put(
            "/api/v1/daily-metrics/by-date/2026-05-01/",
            data={
                "sleep_quality": 9,
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {access}",
        )
        self.assertEqual(response.status_code, 400)

        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "validation_error")