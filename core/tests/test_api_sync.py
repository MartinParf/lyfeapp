from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from bio.models import Activity, DailyMetric, Profile
from fitness.models import (
    Exercise,
    WorkoutSession,
    WorkoutSessionExercise,
    WorkoutSessionStatus,
    WorkoutSet,
)
from fitness.services.sync import touch_session_for_sync


@override_settings(ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"])
class ApiSyncTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.password = "LocalTestPassword123!"
        self.user = User.objects.create_user(
            username="api_sync_user",
            email="api_sync_user@example.com",
            password=self.password,
        )
        self.profile, _ = Profile.objects.get_or_create(user=self.user)

        self.exercise = Exercise.objects.create(
            name="Sync Test Bench Press",
            slug="sync-test-bench-press",
            primary_pattern="PUSH",
            is_custom=False,
            is_active=True,
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

    def test_sync_changes_returns_created_and_deleted_buckets(self):
        access = self._login()
        since = timezone.now()

        DailyMetric.objects.create(
            user=self.user,
            date=timezone.localdate(),
            weight_kg=Decimal("82.5"),
            alcohol_units=0,
        )

        Activity.objects.create(
            user=self.user,
            client_uuid=uuid4(),
            date=timezone.localdate(),
            activity_type="WALKING",
            duration_minutes=30,
        )

        deleted_activity = Activity.objects.create(
            user=self.user,
            client_uuid=uuid4(),
            date=timezone.localdate(),
            activity_type="WALKING",
            duration_minutes=10,
        )
        deleted_activity.deleted_at = timezone.now()
        deleted_activity.save()

        session = WorkoutSession.objects.create(
            user=self.user,
            client_uuid=uuid4(),
            focus="CUSTOM",
            status=WorkoutSessionStatus.PLANNED,
            notes="sync session",
        )
        entry = WorkoutSessionExercise.objects.create(
            session=session,
            exercise=self.exercise,
            sequence=1,
        )
        WorkoutSet.objects.create(
            session_exercise=entry,
            set_order=1,
            weight_kg=Decimal("80.0"),
            reps=8,
        )

        deleted_session = WorkoutSession.objects.create(
            user=self.user,
            client_uuid=uuid4(),
            focus="CUSTOM",
            status=WorkoutSessionStatus.PLANNED,
        )
        deleted_session.deleted_at = timezone.now()
        deleted_session.save()

        response = self.client.get(
            "/api/v1/sync/changes/",
            {"since": since.isoformat()},
            HTTP_AUTHORIZATION=f"Bearer {access}",
        )
        self.assertEqual(response.status_code, 200)

        payload = response.json()["data"]
        self.assertGreaterEqual(len(payload["daily_metrics"]["created"]), 1)
        self.assertGreaterEqual(len(payload["activities"]["created"]), 1)
        self.assertGreaterEqual(len(payload["activities"]["deleted"]), 1)
        self.assertGreaterEqual(len(payload["workout_sessions"]["created"]), 1)
        self.assertGreaterEqual(len(payload["workout_sessions"]["deleted"]), 1)
        self.assertEqual(payload["sync_contract_version"], "1")
        self.assertEqual(payload["activities"]["deletion_mode"], "soft_delete")
        self.assertEqual(payload["workout_sessions"]["deletion_mode"], "soft_delete_full_tree")
        self.assertEqual(payload["workout_sessions"]["payload_mode"], "full_tree")

        created_session = payload["workout_sessions"]["created"][0]
        self.assertEqual(len(created_session["exercises"]), 1)
        self.assertEqual(len(created_session["exercises"][0]["sets"]), 1)

    def test_sync_changes_returns_updated_session_when_child_changes_and_parent_touched(self):
        access = self._login()

        session = WorkoutSession.objects.create(
            user=self.user,
            client_uuid=uuid4(),
            focus="CUSTOM",
            status=WorkoutSessionStatus.PLANNED,
            notes="before",
        )
        entry = WorkoutSessionExercise.objects.create(
            session=session,
            exercise=self.exercise,
            sequence=1,
        )
        workout_set = WorkoutSet.objects.create(
            session_exercise=entry,
            set_order=1,
            weight_kg=Decimal("80.0"),
            reps=8,
        )

        old_ts = timezone.now() - timedelta(days=2)
        WorkoutSession.objects.filter(pk=session.pk).update(created_at=old_ts, updated_at=old_ts)
        WorkoutSessionExercise.objects.filter(pk=entry.pk).update(created_at=old_ts, updated_at=old_ts)
        WorkoutSet.objects.filter(pk=workout_set.pk).update(created_at=old_ts, updated_at=old_ts)

        session.refresh_from_db()
        entry.refresh_from_db()
        workout_set.refresh_from_db()

        since = timezone.now()

        workout_set.reps = 9
        workout_set.save()
        touch_session_for_sync(session)

        response = self.client.get(
            "/api/v1/sync/changes/",
            {"since": since.isoformat()},
            HTTP_AUTHORIZATION=f"Bearer {access}",
        )
        self.assertEqual(response.status_code, 200)

        payload = response.json()["data"]
        self.assertEqual(len(payload["workout_sessions"]["updated"]), 1)
        self.assertEqual(payload["sync_contract_version"], "1")
        self.assertEqual(payload["workout_sessions"]["payload_mode"], "full_tree")

        updated_session = payload["workout_sessions"]["updated"][0]
        self.assertEqual(updated_session["exercises"][0]["sets"][0]["reps"], 9)

def test_sync_changes_requires_since(self):
    access = self._login()

    response = self.client.get(
        "/api/v1/sync/changes/",
        HTTP_AUTHORIZATION=f"Bearer {access}",
    )
    self.assertEqual(response.status_code, 400)

    payload = response.json()
    self.assertFalse(payload["ok"])
    self.assertEqual(payload["error"]["code"], "validation_error")


def test_sync_changes_rejects_invalid_since(self):
    access = self._login()

    response = self.client.get(
        "/api/v1/sync/changes/",
        {"since": "not-a-datetime"},
        HTTP_AUTHORIZATION=f"Bearer {access}",
    )
    self.assertEqual(response.status_code, 400)

    payload = response.json()
    self.assertFalse(payload["ok"])
    self.assertEqual(payload["error"]["code"], "validation_error")


def test_sync_changes_empty_delta_returns_contract_metadata(self):
    access = self._login()
    since = timezone.now()

    response = self.client.get(
        "/api/v1/sync/changes/",
        {"since": since.isoformat()},
        HTTP_AUTHORIZATION=f"Bearer {access}",
    )
    self.assertEqual(response.status_code, 200)

    payload = response.json()["data"]
    self.assertEqual(payload["sync_contract_version"], "1")
    self.assertIn("synced_at", payload)
    self.assertEqual(payload["activities"]["deletion_mode"], "soft_delete")
    self.assertEqual(payload["workout_sessions"]["deletion_mode"], "soft_delete_full_tree")
    self.assertEqual(payload["workout_sessions"]["payload_mode"], "full_tree")

    self.assertEqual(payload["daily_metrics"]["created"], [])
    self.assertEqual(payload["daily_metrics"]["updated"], [])
    self.assertEqual(payload["activities"]["created"], [])
    self.assertEqual(payload["activities"]["updated"], [])
    self.assertEqual(payload["activities"]["deleted"], [])
    self.assertEqual(payload["workout_sessions"]["created"], [])
    self.assertEqual(payload["workout_sessions"]["updated"], [])
    self.assertEqual(payload["workout_sessions"]["deleted"], [])