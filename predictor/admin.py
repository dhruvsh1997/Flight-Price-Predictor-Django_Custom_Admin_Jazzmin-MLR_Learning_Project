"""
predictor/admin.py
==================
Django Admin registration with Jazzmin-compatible customisations.

Key features demonstrated:
  * list_display, list_filter, search_fields on every model
  * readonly_fields for computed / audit data
  * fieldsets for grouped form layout
  * Custom actions (export CSV)
  * Inline admin (FlightRecord inside Airline detail)
  * Short descriptions for computed columns
"""

import csv
import logging
from django.contrib import admin
from django.http import HttpResponse
from django.utils.html import format_html

from .models import Airline, City, TimeSlot, StopType, FlightClass, FlightRecord, PredictionLog

logger = logging.getLogger("predictor")


# ─── CSV export action (reusable) ─────────────────────────────────────────────

def export_as_csv(modeladmin, request, queryset):
    """Generic action: download selected rows as CSV."""
    meta = modeladmin.model._meta
    field_names = [f.name for f in meta.fields]

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f"attachment; filename={meta.verbose_name_plural}.csv"

    writer = csv.writer(response)
    writer.writerow(field_names)
    for obj in queryset:
        writer.writerow([getattr(obj, f) for f in field_names])

    logger.info("CSV export: %d %s rows by %s", queryset.count(), meta.verbose_name, request.user)
    return response

export_as_csv.short_description = "📥 Export selected as CSV"


# ─── Inline: show flight records inside Airline admin ─────────────────────────

class FlightRecordInline(admin.TabularInline):
    model = FlightRecord
    extra = 0
    max_num = 15
    fields = ("source_city", "destination_city", "flight_class", "duration", "days_left", "price")
    readonly_fields = fields
    can_delete = False
    show_change_link = True
    verbose_name = "Sample Flight Record"
    verbose_name_plural = "Sample Flight Records (first 15)"


# ─── Lookup table admins ───────────────────────────────────────────────────────

@admin.register(Airline)
class AirlineAdmin(admin.ModelAdmin):
    list_display  = ("name", "record_count", "avg_price_display")
    search_fields = ("name",)
    inlines       = [FlightRecordInline]

    def get_queryset(self, request):
        from django.db.models import Count, Avg
        qs = super().get_queryset(request)
        return qs.annotate(_count=Count("records"), _avg=Avg("records__price"))

    @admin.display(description="# Records", ordering="_count")
    def record_count(self, obj):
        return obj._count

    @admin.display(description="Avg Price (₹)", ordering="_avg")
    def avg_price_display(self, obj):
        val = getattr(obj, "_avg", None)
        if val:
            return f"₹{val:,.0f}"
        return "—"


@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    list_display  = ("name", "departure_count", "arrival_count")
    search_fields = ("name",)

    def get_queryset(self, request):
        from django.db.models import Count
        qs = super().get_queryset(request)
        return qs.annotate(
            _dep=Count("departures", distinct=True),
            _arr=Count("arrivals", distinct=True),
        )

    @admin.display(description="Departures", ordering="_dep")
    def departure_count(self, obj):
        return obj._dep

    @admin.display(description="Arrivals", ordering="_arr")
    def arrival_count(self, obj):
        return obj._arr


@admin.register(TimeSlot)
class TimeSlotAdmin(admin.ModelAdmin):
    list_display  = ("label", "display_order")
    list_editable = ("display_order",)
    ordering      = ("display_order",)


@admin.register(StopType)
class StopTypeAdmin(admin.ModelAdmin):
    list_display  = ("code", "display_order")
    list_editable = ("display_order",)
    ordering      = ("display_order",)


@admin.register(FlightClass)
class FlightClassAdmin(admin.ModelAdmin):
    list_display = ("name",)


# ─── FlightRecord admin ────────────────────────────────────────────────────────

@admin.register(FlightRecord)
class FlightRecordAdmin(admin.ModelAdmin):
    list_display = (
        "airline", "route_display", "departure_time", "arrival_time",
        "stops", "flight_class", "duration_display", "days_left", "price_display",
    )
    list_filter  = ("airline", "flight_class", "stops", "source_city", "destination_city")
    search_fields = (
        "airline__name", "source_city__name", "destination_city__name",
    )
    list_per_page = 50
    readonly_fields = ("created_at",)
    actions = [export_as_csv]

    fieldsets = (
        ("Route Information", {
            "fields": ("airline", "source_city", "destination_city"),
        }),
        ("Schedule", {
            "fields": ("departure_time", "arrival_time", "stops"),
        }),
        ("Booking Details", {
            "fields": ("flight_class", "duration", "days_left"),
        }),
        ("Pricing", {
            "fields": ("price",),
            "classes": ("wide",),
        }),
        ("Audit", {
            "fields": ("created_at",),
            "classes": ("collapse",),
        }),
    )

    @admin.display(description="Route")
    def route_display(self, obj):
        return format_html(
            '<span style="color:#0d6efd;font-weight:600">{} → {}</span>',
            obj.source_city, obj.destination_city,
        )

    @admin.display(description="Duration", ordering="duration")
    def duration_display(self, obj):
        return f"{obj.duration:.1f} h"

    @admin.display(description="Price (₹)", ordering="price")
    def price_display(self, obj):
        color = "#198754" if obj.price < 10000 else "#dc3545" if obj.price > 50000 else "#fd7e14"
        return format_html('<strong style="color:{}">{}</strong>', color, f"₹{obj.price:,}")


# ─── PredictionLog admin ───────────────────────────────────────────────────────

@admin.register(PredictionLog)
class PredictionLogAdmin(admin.ModelAdmin):
    list_display  = (
        "predicted_at", "airline", "route_display",
        "flight_class", "duration", "days_left", "predicted_price_display",
    )
    list_filter   = ("airline", "flight_class", "source_city", "destination_city")
    search_fields = ("airline__name", "source_city__name", "destination_city__name")
    readonly_fields = (
        "airline", "source_city", "destination_city",
        "departure_time", "arrival_time", "stops", "flight_class",
        "duration", "days_left", "predicted_price", "predicted_at", "session_key",
    )
    list_per_page = 30
    date_hierarchy = "predicted_at"
    actions = [export_as_csv]

    fieldsets = (
        ("Input Features", {
            "fields": (
                "airline", ("source_city", "destination_city"),
                ("departure_time", "arrival_time"),
                ("stops", "flight_class"),
                ("duration", "days_left"),
            ),
        }),
        ("Prediction Output", {
            "fields": ("predicted_price", "predicted_at", "session_key"),
        }),
    )

    @admin.display(description="Route")
    def route_display(self, obj):
        if obj.source_city and obj.destination_city:
            return format_html(
                "{} → {}",
                obj.source_city.name, obj.destination_city.name,
            )
        return "—"

    @admin.display(description="Predicted Price (₹)", ordering="predicted_price")
    def predicted_price_display(self, obj):
        return format_html(
            '<strong style="color:#0d6efd">₹{:,.0f}</strong>',
            obj.predicted_price,
        )

    def has_add_permission(self, request):
        return False   # Logs are created only by the app, not manually
