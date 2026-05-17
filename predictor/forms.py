"""
predictor/forms.py
==================
Django form for collecting flight-booking parameters from the user.
Choices are loaded dynamically from the normalised lookup tables so
there is a single source of truth — no hard-coded list duplication.
"""

import logging
from django import forms
from .models import Airline, City, TimeSlot, StopType, FlightClass

logger = logging.getLogger("predictor")


def _qs_to_choices(qs, value_field="pk", label_field="__str__"):
    """Turn a queryset into (value, label) tuples for <select>."""
    choices = [("", "— Select —")]
    for obj in qs:
        label = str(obj)
        choices.append((getattr(obj, value_field), label))
    return choices


class FlightPredictionForm(forms.Form):
    # ── Categorical fields ────────────────────────────────────────────────────
    airline = forms.ModelChoiceField(
        queryset=Airline.objects.all(),
        empty_label="— Select Airline —",
        widget=forms.Select(attrs={"class": "form-select", "id": "airline"}),
        label="Airline",
    )
    source_city = forms.ModelChoiceField(
        queryset=City.objects.all(),
        empty_label="— Departure City —",
        widget=forms.Select(attrs={"class": "form-select", "id": "source_city"}),
        label="Source City",
    )
    destination_city = forms.ModelChoiceField(
        queryset=City.objects.all(),
        empty_label="— Arrival City —",
        widget=forms.Select(attrs={"class": "form-select", "id": "destination_city"}),
        label="Destination City",
    )
    departure_time = forms.ModelChoiceField(
        queryset=TimeSlot.objects.all(),
        empty_label="— Departure Time —",
        widget=forms.Select(attrs={"class": "form-select", "id": "departure_time"}),
        label="Departure Time",
    )
    arrival_time = forms.ModelChoiceField(
        queryset=TimeSlot.objects.all(),
        empty_label="— Arrival Time —",
        widget=forms.Select(attrs={"class": "form-select", "id": "arrival_time"}),
        label="Arrival Time",
    )
    stops = forms.ModelChoiceField(
        queryset=StopType.objects.all(),
        empty_label="— Number of Stops —",
        widget=forms.Select(attrs={"class": "form-select", "id": "stops"}),
        label="Stops",
    )
    flight_class = forms.ModelChoiceField(
        queryset=FlightClass.objects.all(),
        empty_label="— Travel Class —",
        widget=forms.Select(attrs={"class": "form-select", "id": "flight_class"}),
        label="Class",
    )

    # ── Numeric fields ────────────────────────────────────────────────────────
    duration = forms.FloatField(
        min_value=0.5,
        max_value=50.0,
        initial=2.5,
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "step": "0.5",
            "placeholder": "e.g. 2.5",
            "id": "duration",
        }),
        label="Duration (hours)",
        help_text="Total flight duration in hours (0.5 – 50)",
    )
    days_left = forms.IntegerField(
        min_value=1,
        max_value=49,
        initial=15,
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "placeholder": "e.g. 15",
            "id": "days_left",
        }),
        label="Days Left to Departure",
        help_text="How many days until the flight (1 – 49)",
    )

    def clean(self):
        cleaned = super().clean()
        src = cleaned.get("source_city")
        dst = cleaned.get("destination_city")
        if src and dst and src == dst:
            raise forms.ValidationError(
                "Source city and destination city must be different."
            )
        logger.debug("Form cleaned successfully: %s → %s", src, dst)
        return cleaned
