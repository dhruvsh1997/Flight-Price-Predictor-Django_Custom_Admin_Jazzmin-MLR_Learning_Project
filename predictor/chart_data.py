"""
predictor/chart_data.py
=======================
Functions that query FlightRecord to produce Chart.js-ready JSON payloads.
All heavy aggregation is done at the DB layer (Django ORM annotate/aggregate),
keeping Python loops minimal.
"""

import json
import logging
from django.db.models import Avg, Count, Min, Max

from .models import FlightRecord, PredictionLog

logger = logging.getLogger("predictor")


def _labels_values(qs, label_key: str, value_key: str):
    labels = [r[label_key] for r in qs]
    values = [round(r[value_key] or 0, 2) for r in qs]
    return labels, values


# ─── Global / overview charts ─────────────────────────────────────────────────

def avg_price_by_airline() -> str:
    """Bar chart: average price per airline."""
    qs = (
        FlightRecord.objects
        .values(label=models_label("airline__name"))
        .annotate(avg=Avg("price"))
        .order_by("-avg")
    )
    labels, values = _labels_values(qs, "label", "avg")
    logger.debug("avg_price_by_airline: %d airlines", len(labels))
    return json.dumps({"labels": labels, "values": values})


def avg_price_by_class() -> str:
    """Doughnut chart: average price by travel class."""
    qs = (
        FlightRecord.objects
        .values(label=models_label("flight_class__name"))
        .annotate(avg=Avg("price"))
        .order_by("label")
    )
    labels, values = _labels_values(qs, "label", "avg")
    return json.dumps({"labels": labels, "values": values})


def avg_price_by_stops() -> str:
    """Bar chart: average price by number of stops."""
    qs = (
        FlightRecord.objects
        .values(label=models_label("stops__code"))
        .annotate(avg=Avg("price"))
        .order_by("stops__display_order")
    )
    labels, values = _labels_values(qs, "label", "avg")
    return json.dumps({"labels": labels, "values": values})


def price_vs_duration_sample(n: int = 300) -> str:
    """Scatter chart: price vs duration (sampled)."""
    qs = FlightRecord.objects.values("duration", "price").order_by("?")[:n]
    points = [{"x": round(r["duration"], 2), "y": r["price"]} for r in qs]
    logger.debug("price_vs_duration_sample: %d points", len(points))
    return json.dumps(points)


def avg_price_by_days_left() -> str:
    """Line chart: avg price grouped by days_left."""
    qs = (
        FlightRecord.objects
        .values("days_left")
        .annotate(avg=Avg("price"))
        .order_by("days_left")
    )
    labels = [r["days_left"] for r in qs]
    values = [round(r["avg"] or 0, 2) for r in qs]
    return json.dumps({"labels": labels, "values": values})


def top_routes(n: int = 8) -> str:
    """Horizontal bar: top N routes by avg price."""
    qs = (
        FlightRecord.objects
        .values(src=models_label("source_city__name"), dst=models_label("destination_city__name"))
        .annotate(avg=Avg("price"), cnt=Count("id"))
        .order_by("-avg")[:n]
    )
    labels = [f"{r['src']} → {r['dst']}" for r in qs]
    values = [round(r["avg"] or 0, 2) for r in qs]
    return json.dumps({"labels": labels, "values": values})


# ─── Contextual charts (shown after a prediction) ────────────────────────────

def similar_flights_price_distribution(
    airline_name: str,
    source_city_name: str,
    destination_city_name: str,
    flight_class_name: str,
    predicted_price: float,
) -> str:
    """
    Histogram-style bar chart: price distribution for the same
    airline + route + class as the prediction.
    """
    qs = (
        FlightRecord.objects
        .filter(
            airline__name=airline_name,
            source_city__name=source_city_name,
            destination_city__name=destination_city_name,
            flight_class__name=flight_class_name,
        )
        .values_list("price", flat=True)
    )
    prices = list(qs[:2000])   # cap for performance

    if not prices:
        logger.warning(
            "No historical records for %s %s→%s [%s]",
            airline_name, source_city_name, destination_city_name, flight_class_name,
        )
        return json.dumps({"buckets": [], "counts": [], "predicted": predicted_price})

    # Build 10-bucket histogram manually (avoids numpy dependency in views)
    min_p, max_p = min(prices), max(prices)
    bucket_size = max(1, (max_p - min_p) // 10)
    buckets = {}
    for p in prices:
        bucket = int((p - min_p) // bucket_size) * bucket_size + min_p
        buckets[bucket] = buckets.get(bucket, 0) + 1

    sorted_buckets = sorted(buckets.items())
    labels = [f"₹{k:,}" for k, _ in sorted_buckets]
    counts = [v for _, v in sorted_buckets]

    return json.dumps({
        "labels": labels,
        "counts": counts,
        "predicted": round(predicted_price, 2),
        "min": min_p,
        "max": max_p,
        "avg": round(sum(prices) / len(prices), 2),
    })


def airline_avg_prices_for_route(
    source_city_name: str,
    destination_city_name: str,
    flight_class_name: str,
) -> str:
    """Bar chart: average price by airline for the selected route + class."""
    qs = (
        FlightRecord.objects
        .filter(
            source_city__name=source_city_name,
            destination_city__name=destination_city_name,
            flight_class__name=flight_class_name,
        )
        .values(label=models_label("airline__name"))
        .annotate(avg=Avg("price"))
        .order_by("-avg")
    )
    labels, values = _labels_values(qs, "label", "avg")
    return json.dumps({"labels": labels, "values": values})


def prediction_history_chart() -> str:
    """Line chart: last 20 predictions over time."""
    qs = (
        PredictionLog.objects
        .order_by("-predicted_at")[:20]
        .values("predicted_at", "predicted_price")
    )
    records = list(qs)[::-1]   # chronological
    labels = [r["predicted_at"].strftime("%d %b %H:%M") for r in records]
    values = [round(r["predicted_price"], 2) for r in records]
    return json.dumps({"labels": labels, "values": values})


# ─── Dashboard summary stats ──────────────────────────────────────────────────

def dashboard_summary() -> dict:
    agg = FlightRecord.objects.aggregate(
        total=Count("id"),
        avg_price=Avg("price"),
        min_price=Min("price"),
        max_price=Max("price"),
    )
    pred_count = PredictionLog.objects.count()
    return {
        "total_records": agg["total"] or 0,
        "avg_price": round(agg["avg_price"] or 0, 2),
        "min_price": agg["min_price"] or 0,
        "max_price": agg["max_price"] or 0,
        "total_predictions": pred_count,
    }


# ─── Small helper (avoids F() import hell for .values() aliasing) ─────────────

def models_label(field_path: str):
    """Return a Django F() expression for use in .values(label=…)."""
    from django.db.models import F
    return F(field_path)
