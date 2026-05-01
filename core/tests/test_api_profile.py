from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from bio.models import Profile


@override_settings(ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"])
class ApiProfileTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.password = "LocalTestPassword123!"
        self.user = User.objects.create_user(
            username="api_profile_user",
            email="api_profile_user@example.com",
            password=self.password,
        )
        self.profile, _ = Profile.objects.get_or_create(user=self.user)
        self.profile.display_name = "Profile User"
        self.profile.bio = "Initial bio"
        self.profile.goal_mode = "maintain"
        self.profile.height_cm = 180
        self.profile.target_weight_kg = "82.5"
        self.profile.save()

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

    def test_get_profile_returns_profile_version(self):
        access = self._login()

        response = self.client.get(
            "/api/v1/profile/me/",
            HTTP_AUTHORIZATION=f"Bearer {access}",
        )
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["display_name"], "Profile User")
        self.assertEqual(
            payload["data"]["profile_version"],
            payload["data"]["updated_at"],
        )

    def test_patch_profile_updates_fields(self):
        access = self._login()

        response = self.client.patch(
            "/api/v1/profile/me/",
            data={
                "display_name": "Updated User",
                "bio": "Updated bio",
                "goal_mode": "maintain",
                "height_cm": 181,
                "target_weight_kg": "83.0",
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {access}",
        )
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertEqual(payload["data"]["display_name"], "Updated User")
        self.assertEqual(payload["data"]["bio"], "Updated bio")
        self.assertEqual(payload["data"]["height_cm"], 181)
        self.assertEqual(payload["data"]["target_weight_kg"], "83.0")

    def test_patch_profile_invalid_height_returns_400(self):
        access = self._login()

        response = self.client.patch(
            "/api/v1/profile/me/",
            data={
                "height_cm": 50,
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {access}",
        )
        self.assertEqual(response.status_code, 400)

        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "validation_error")
        self.assertIn("height_cm", payload["error"]["details"])