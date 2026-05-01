from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from bio.models import Profile
from fitness.models import Exercise, ExercisePool, ExercisePoolItem


@override_settings(ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"])
class ApiBootstrapTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.password = "LocalTestPassword123!"
        self.user = User.objects.create_user(
            username="api_bootstrap_user",
            email="api_bootstrap_user@example.com",
            password=self.password,
        )
        Profile.objects.get_or_create(user=self.user)

        self.exercise = Exercise.objects.create(
            name="Test Bench Press",
            slug="test-bench-press",
            primary_pattern="PUSH",
            is_custom=False,
            is_active=True,
        )

        self.pool = ExercisePool.objects.create(
            user=self.user,
            name="Test Pool",
            focus="CUSTOM",
            description="Bootstrap test pool",
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

    def test_bootstrap_returns_expected_sections(self):
        access = self._login()

        response = self.client.get(
            "/api/v1/bootstrap/",
            HTTP_AUTHORIZATION=f"Bearer {access}",
        )
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertTrue(payload["ok"])

        data = payload["data"]
        self.assertIn("profile", data)
        self.assertIn("server", data)
        self.assertIn("config", data)
        self.assertIn("feature_flags", data)
        self.assertIn("fitness", data)

        self.assertEqual(data["server"]["api_version"], "v1")
        self.assertIn("bootstrap_version", data["config"])
        self.assertIn("profile_version", data["profile"])

        self.assertGreaterEqual(len(data["fitness"]["exercises"]), 1)
        self.assertGreaterEqual(len(data["fitness"]["pool_summaries"]), 1)

        self.assertEqual(data["fitness"]["pool_summaries"][0]["name"], "Test Pool")