from django import forms
from django.utils import timezone

from .models import Activity, DailyMetric


class DailyMetricForm(forms.ModelForm):
    sleep_quality = forms.IntegerField(
        min_value=1,
        max_value=5,
        label="Sleep quality",
        widget=forms.NumberInput(
            attrs={
                "type": "range",
                "min": "1",
                "max": "5",
                "step": "1",
                "class": "metric-range-input",
                "data-display-id": "sleep-quality-display",
            }
        ),
    )

    alcohol_units = forms.IntegerField(
        min_value=0,
        max_value=10,
        label="Alcohol intake",
        widget=forms.NumberInput(
            attrs={
                "type": "range",
                "min": "0",
                "max": "10",
                "step": "1",
                "class": "metric-range-input",
                "data-display-id": "alcohol-units-display",
            }
        ),
    )

    class Meta:
        model = DailyMetric
        fields = [
            "date",
            "weight_kg",
            "sleep_quality",
            "alcohol_units",
            "diet_mode",
            "calories_planned",
            "calories_actual",
            "notes",
        ]
        widgets = {
            "date": forms.DateInput(
                format="%Y-%m-%d",
                attrs={"type": "date"},
            ),
            "notes": forms.Textarea(
                attrs={
                    "rows": 2,
                    "placeholder": "Optional notes for the day...",
                }
            ),
        }
        labels = {
            "date": "Date",
            "weight_kg": "Weight (kg)",
            "sleep_quality": "Sleep quality",
            "alcohol_units": "Alcohol intake",
            "diet_mode": "Diet mode",
            "calories_planned": "Calories planned",
            "calories_actual": "Calories actual",
            "notes": "Notes",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["date"].input_formats = ["%Y-%m-%d"]

        if not self.instance.pk and not self.initial.get("date"):
            self.initial["date"] = timezone.localdate()

        if not self.instance.pk and self.initial.get("sleep_quality") in (None, ""):
            self.initial["sleep_quality"] = 3

        if not self.instance.pk and self.initial.get("alcohol_units") in (None, ""):
            self.initial["alcohol_units"] = 0

        self.fields["weight_kg"].widget.attrs.update(
            {
                "step": "0.1",
                "placeholder": "e.g. 82.4",
                "inputmode": "decimal",
                "autocomplete": "off",
            }
        )
        self.fields["calories_planned"].widget.attrs.update(
            {
                "placeholder": "e.g. 2400",
                "inputmode": "numeric",
                "autocomplete": "off",
            }
        )
        self.fields["calories_actual"].widget.attrs.update(
            {
                "placeholder": "e.g. 2650",
                "inputmode": "numeric",
                "autocomplete": "off",
            }
        )
        self.fields["notes"].widget.attrs.update(
            {
                "placeholder": "Optional notes for the day...",
            }
        )


class ActivityForm(forms.ModelForm):
    class Meta:
        model = Activity
        fields = [
            "date",
            "activity_type",
            "duration_minutes",
            "distance_km",
            "calories_burned_est",
            "notes",
        ]
        widgets = {
            "date": forms.DateInput(
                format="%Y-%m-%d",
                attrs={"type": "date"},
            ),
            "notes": forms.Textarea(
                attrs={
                    "rows": 2,
                    "placeholder": "Optional notes about the activity...",
                }
            ),
        }
        labels = {
            "date": "Date",
            "activity_type": "Activity type",
            "duration_minutes": "Duration (minutes)",
            "distance_km": "Distance (km)",
            "calories_burned_est": "Calories burned (estimate)",
            "notes": "Notes",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["date"].input_formats = ["%Y-%m-%d"]

        if not self.instance.pk and not self.initial.get("date"):
            self.initial["date"] = timezone.localdate()

        self.fields["duration_minutes"].widget.attrs.update(
            {
                "placeholder": "e.g. 45",
                "inputmode": "numeric",
                "autocomplete": "off",
            }
        )
        self.fields["distance_km"].widget.attrs.update(
            {
                "step": "0.1",
                "placeholder": "e.g. 5.2",
                "inputmode": "decimal",
                "autocomplete": "off",
            }
        )
        self.fields["calories_burned_est"].widget.attrs.update(
            {
                "placeholder": "e.g. 380",
                "inputmode": "numeric",
                "autocomplete": "off",
            }
        )