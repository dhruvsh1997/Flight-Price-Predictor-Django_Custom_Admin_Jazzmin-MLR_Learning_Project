"""
predictor/models.py
===================
Normalised relational schema for the Flight Price dataset.

Tables
------
  Airline        – lookup: airline names  (Air_India, Vistara …)
  City           – lookup: Indian metro cities  (Delhi, Mumbai …)
  TimeSlot       – lookup: time-of-day bins  (Early_Morning, Morning …)
  StopType       – lookup: zero / one / two_or_more
  FlightClass    – lookup: Economy / Business
  FlightRecord   – fact table (one row per booking option in the dataset)
  PredictionLog  – every price prediction made through the web UI

Why normalise?
--------------
  * Eliminates string duplication across 300 k rows
  * Enables fast GROUP-BY analytics (avg price per airline, city …)
  * Keeps the admin panel clean — edit a city name once, not everywhere
"""

import logging
from django.db import models
from django.core.validators import MinValueValidator

logger = logging.getLogger("predictor")


# ─── Lookup / Dimension Tables ────────────────────────────────────────────────

class Airline(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Airline"
        verbose_name_plural = "Airlines"

    def __str__(self):
        return self.name


class City(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "City"
        verbose_name_plural = "Cities"

    def __str__(self):
        return self.name


class TimeSlot(models.Model):
    """
    Departure / arrival time bins used in the dataset.
    E.g.  Early_Morning | Morning | Afternoon | Evening | Night | Late_Night
    """
    label = models.CharField(max_length=50, unique=True)
    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "label"]
        verbose_name = "Time Slot"
        verbose_name_plural = "Time Slots"

    def __str__(self):
        return self.label


class StopType(models.Model):
    """
    Number-of-stops category: zero | one | two_or_more
    """
    STOP_CHOICES = [
        ("zero", "Non-stop"),
        ("one", "1 Stop"),
        ("two_or_more", "2+ Stops"),
    ]
    code = models.CharField(max_length=20, unique=True, choices=STOP_CHOICES)
    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["display_order"]
        verbose_name = "Stop Type"
        verbose_name_plural = "Stop Types"

    def __str__(self):
        return dict(self.STOP_CHOICES).get(self.code, self.code)


class FlightClass(models.Model):
    name = models.CharField(max_length=20, unique=True)   # Economy | Business

    class Meta:
        ordering = ["name"]
        verbose_name = "Flight Class"
        verbose_name_plural = "Flight Classes"

    def __str__(self):
        return self.name


# ─── Fact Table ───────────────────────────────────────────────────────────────

class FlightRecord(models.Model):
    """
    One row = one booking option scraped from EaseMyTrip (Feb–Mar 2022).
    All categorical attributes are FK-linked to normalised lookup tables.
    """
    airline        = models.ForeignKey(Airline,     on_delete=models.PROTECT, related_name="records")
    source_city    = models.ForeignKey(City,         on_delete=models.PROTECT, related_name="departures")
    destination_city = models.ForeignKey(City,       on_delete=models.PROTECT, related_name="arrivals")
    departure_time = models.ForeignKey(TimeSlot,     on_delete=models.PROTECT, related_name="departures")
    arrival_time   = models.ForeignKey(TimeSlot,     on_delete=models.PROTECT, related_name="arrivals")
    stops          = models.ForeignKey(StopType,     on_delete=models.PROTECT, related_name="records")
    flight_class   = models.ForeignKey(FlightClass,  on_delete=models.PROTECT, related_name="records")

    # Numeric features
    duration       = models.FloatField(validators=[MinValueValidator(0)])   # hours
    days_left      = models.PositiveIntegerField()                          # days to departure

    # Target
    price          = models.PositiveIntegerField()                          # INR

    # Housekeeping
    created_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Flight Record"
        verbose_name_plural = "Flight Records"
        indexes = [
            models.Index(fields=["airline"]),
            models.Index(fields=["source_city", "destination_city"]),
            models.Index(fields=["flight_class"]),
            models.Index(fields=["price"]),
        ]

    def __str__(self):
        return (
            f"{self.airline} | {self.source_city} → {self.destination_city} "
            f"| {self.flight_class} | ₹{self.price}"
        )


# ─── Prediction Audit Log ─────────────────────────────────────────────────────

class PredictionLog(models.Model):
    """
    Stores every price prediction made through the UI for audit / analytics.
    FK fields mirror FlightRecord but are nullable so a log entry can survive
    even if lookup data is deleted.
    """
    # Input snapshot (FK for relational integrity, allow NULL for resilience)
    airline          = models.ForeignKey(Airline,    on_delete=models.SET_NULL, null=True)
    source_city      = models.ForeignKey(City,        on_delete=models.SET_NULL, null=True, related_name="pred_departures")
    destination_city = models.ForeignKey(City,        on_delete=models.SET_NULL, null=True, related_name="pred_arrivals")
    departure_time   = models.ForeignKey(TimeSlot,    on_delete=models.SET_NULL, null=True, related_name="pred_departures")
    arrival_time     = models.ForeignKey(TimeSlot,    on_delete=models.SET_NULL, null=True, related_name="pred_arrivals")
    stops            = models.ForeignKey(StopType,    on_delete=models.SET_NULL, null=True)
    flight_class     = models.ForeignKey(FlightClass, on_delete=models.SET_NULL, null=True)
    duration         = models.FloatField()
    days_left        = models.PositiveIntegerField()

    # Output
    predicted_price  = models.FloatField()

    # Metadata
    predicted_at     = models.DateTimeField(auto_now_add=True)
    session_key      = models.CharField(max_length=40, blank=True)

    class Meta:
        verbose_name = "Prediction Log"
        verbose_name_plural = "Prediction Logs"
        ordering = ["-predicted_at"]

    def __str__(self):
        return (
            f"[{self.predicted_at:%Y-%m-%d %H:%M}] "
            f"{self.airline} {self.source_city}→{self.destination_city} "
            f"₹{self.predicted_price:,.0f}"
        )
