from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings

from bio.models import Profile


@override_settings(ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"])
class ApiAuthTests(TestCase):
    def setUp(self):
        cache.clear()

        User = get_user_model()
        self.password = "LocalTestPassword123!"
        self.user = User.objects.create_user(
            username="api_auth_user",
            email="api_auth_user@example.com",
            password=self.password,
        )
        Profile.objects.get_or_create(user=self.user)

    def tearDown(self):
        cache.clear()

    def _login(self, password=None):
        return self.client.post(
            "/api/v1/auth/login/",
            data={
                "identity": self.user.username,
                "password": password or self.password,
            },
            content_type="application/json",
        )

    def test_login_returns_access_and_refresh_tokens(self):
        response = self._login()
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertIn("access", payload["data"]["tokens"])
        self.assertIn("refresh", payload["data"]["tokens"])
        self.assertEqual(payload["data"]["user"]["username"], self.user.username)

    def test_login_rejects_invalid_credentials(self):
        response = self._login(password="wrong-password")
        self.assertEqual(response.status_code, 401)

        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "invalid_credentials")

    def test_me_requires_authentication(self):
        response = self.client.get("/api/v1/auth/me/")
        self.assertEqual(response.status_code, 401)

        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "authentication_required")

    def test_me_returns_authenticated_user(self):
        login_response = self._login()
        access = login_response.json()["data"]["tokens"]["access"]

        response = self.client.get(
            "/api/v1/auth/me/",
            HTTP_AUTHORIZATION=f"Bearer {access}",
        )
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["username"], self.user.username)

    def test_refresh_returns_new_access_token(self):
        login_response = self._login()
        refresh = login_response.json()["data"]["tokens"]["refresh"]

        response = self.client.post(
            "/api/v1/auth/refresh/",
            data={"refresh": refresh},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertIn("access", payload["data"])

    def test_logout_blacklists_refresh_token(self):
        login_response = self._login()
        refresh = login_response.json()["data"]["tokens"]["refresh"]

        logout_response = self.client.post(
            "/api/v1/auth/logout/",
            data={"refresh": refresh},
            content_type="application/json",
        )
        self.assertEqual(logout_response.status_code, 200)

        refresh_response = self.client.post(
            "/api/v1/auth/refresh/",
            data={"refresh": refresh},
            content_type="application/json",
        )
        self.assertEqual(refresh_response.status_code, 401)

        payload = refresh_response.json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "invalid_refresh_token")


@override_settings(
    ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"],
    API_AUTH_WINDOW_SECONDS=900,
    API_LOGIN_IP_LIMIT=50,
    API_LOGIN_IDENTITY_IP_LIMIT=3,
)
class ApiAuthRateLimitTests(TestCase):
    def setUp(self):
        cache.clear()

        User = get_user_model()
        self.user = User.objects.create_user(
            username="rate_limit_user",
            email="rate_limit_user@example.com",
            password="CorrectPassword123!",
        )
        Profile.objects.get_or_create(user=self.user)

    def tearDown(self):
        cache.clear()

    def test_login_rate_limit_returns_429(self):
        for _ in range(3):
            response = self.client.post(
                "/api/v1/auth/login/",
                data={
                    "identity": self.user.username,
                    "password": "wrong-password",
                },
                content_type="application/json",
            )
            self.assertEqual(response.status_code, 401)

        response = self.client.post(
            "/api/v1/auth/login/",
            data={
                "identity": self.user.username,
                "password": "wrong-password",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 429)

        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "rate_limited")