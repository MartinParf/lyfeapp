from django import forms

from .models import (
    Exercise,
    ExercisePool,
    ExercisePoolItem,
    WorkoutSession,
    WorkoutSessionExercise,
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
    class Meta:
        model = WorkoutSession
        fields = ["focus", "source_pool", "status", "scheduled_date", "started_at", "ended_at", "notes"]
        widgets = {
            "scheduled_date": forms.DateInput(attrs={"type": "date"}),
            "started_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "ended_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
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
        self.fields["scheduled_date"].required = False
        self.fields["started_at"].required = False
        self.fields["ended_at"].required = False


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