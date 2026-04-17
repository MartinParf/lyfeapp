from datetime import datetime, time, timedelta

from django import forms
from django.utils import timezone

from .models import (
    Exercise,
    ExercisePool,
    ExercisePoolItem,
    WorkoutSession,
    WorkoutSessionExercise,
    WorkoutSessionStatus,
    WorkoutSet,
)


class ExerciseForm(forms.ModelForm):
    class Meta:
        model = Exercise
        fields = ["name", "primary_pattern", "is_active"]

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if not name:
            raise forms.ValidationError("Name is required.")
        return name


class ExercisePoolForm(forms.ModelForm):
    class Meta:
        model = ExercisePool
        fields = ["name", "focus", "description", "is_active"]


class ExercisePoolItemForm(forms.ModelForm):
    class Meta:
        model = ExercisePoolItem
        fields = ["exercise", "sequence", "is_active", "notes"]

    def __init__(self, *args, **kwargs):
        pool = kwargs.pop("pool", None)
        super().__init__(*args, **kwargs)

        self.fields["exercise"].queryset = Exercise.objects.filter(is_active=True).order_by("name")

        if pool is not None and not self.instance.pk:
            next_sequence = (
                pool.items.order_by("-sequence").values_list("sequence", flat=True).first() or 0
            ) + 1
            self.fields["sequence"].initial = next_sequence


class WorkoutSessionForm(forms.ModelForm):
    planned = forms.BooleanField(required=False, label="Planned")
    session_date = forms.DateField(
        label="Date",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    duration_minutes = forms.IntegerField(
        required=False,
        min_value=5,
        max_value=480,
        label="Duration (min)",
        widget=forms.NumberInput(attrs={"step": "5", "placeholder": "90"}),
    )

    class Meta:
        model = WorkoutSession
        fields = ["focus", "source_pool", "notes"]
        widgets = {
            "notes": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Optional session notes",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        if user is not None:
            self.fields["source_pool"].queryset = ExercisePool.objects.filter(
                user=user,
                is_active=True,
            ).order_by("name")
        else:
            self.fields["source_pool"].queryset = ExercisePool.objects.none()

        self.fields["source_pool"].required = False
        self.fields["notes"].required = False
        self.fields["source_pool"].empty_label = "No pool"

        instance = self.instance if self.instance and self.instance.pk else None
        today = timezone.localdate()

        if instance:
            self.fields["planned"].initial = not (
                instance.status == WorkoutSessionStatus.COMPLETED
                or (
                    instance.started_at
                    and instance.ended_at
                    and instance.ended_at >= instance.started_at
                )
            )
            self.fields["session_date"].initial = (
                instance.scheduled_date
                or (instance.started_at.date() if instance.started_at else None)
                or (instance.ended_at.date() if instance.ended_at else None)
                or today
            )

            if instance.started_at and instance.ended_at and instance.ended_at > instance.started_at:
                self.fields["duration_minutes"].initial = int(
                    (instance.ended_at - instance.started_at).total_seconds() // 60
                )
        else:
            self.fields["planned"].initial = True
            self.fields["session_date"].initial = today

    def clean(self):
        cleaned = super().clean()

        planned = cleaned.get("planned")
        session_date = cleaned.get("session_date")
        duration_minutes = cleaned.get("duration_minutes")

        if not session_date:
            self.add_error("session_date", "Date is required.")

        if not planned and not duration_minutes:
            self.add_error("duration_minutes", "Duration is required for a completed session.")

        return cleaned

    def _build_anchor_datetime(self, session_date):
        base_time = time(hour=18, minute=0)

        if self.instance and self.instance.pk and self.instance.started_at:
            local_started = timezone.localtime(self.instance.started_at)
            base_time = local_started.time().replace(tzinfo=None)

        naive = datetime.combine(session_date, base_time)
        return timezone.make_aware(naive, timezone.get_current_timezone())

    def save(self, commit=True):
        session = super().save(commit=False)

        planned = self.cleaned_data["planned"]
        session_date = self.cleaned_data["session_date"]
        duration_minutes = self.cleaned_data.get("duration_minutes")

        session.scheduled_date = session_date

        if planned:
            session.status = WorkoutSessionStatus.PLANNED
            session.started_at = None
            session.ended_at = None
        else:
            anchor = self._build_anchor_datetime(session_date)
            session.started_at = anchor
            session.ended_at = anchor + timedelta(minutes=duration_minutes)
            session.status = WorkoutSessionStatus.COMPLETED

        if commit:
            session.save()

        return session


class WorkoutSessionExerciseForm(forms.ModelForm):
    class Meta:
        model = WorkoutSessionExercise
        fields = ["exercise", "notes"]

    def __init__(self, *args, **kwargs):
        kwargs.pop("session", None)
        super().__init__(*args, **kwargs)
        self.fields["exercise"].queryset = Exercise.objects.filter(is_active=True).order_by("name")


class WorkoutSetForm(forms.ModelForm):
    class Meta:
        model = WorkoutSet
        fields = ["set_type", "weight_kg", "reps", "rpe", "notes"]

    def __init__(self, *args, **kwargs):
        kwargs.pop("session_exercise", None)
        super().__init__(*args, **kwargs)