"""
predictor/views.py
==================
Three public views:
  home        – landing page with overview charts + quick facts
  predict     – GET: form  |  POST: run model, store PredictionLog, redirect
  result      – show prediction + contextual charts
  dashboard   – analytics dashboard (charts overview)
"""

import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse

from .forms import FlightPredictionForm
from .models import PredictionLog, Airline, City, TimeSlot, StopType, FlightClass
from .ml_engine import predict_price
from . import chart_data

logger = logging.getLogger("predictor")


# ─── Home ─────────────────────────────────────────────────────────────────────

def home(request):
    logger.info("Home page requested.")
    summary = chart_data.dashboard_summary()
    ctx = {
        "summary": summary,
        "chart_airline": chart_data.avg_price_by_airline(),
        "chart_class": chart_data.avg_price_by_class(),
        "chart_stops": chart_data.avg_price_by_stops(),
        "chart_days": chart_data.avg_price_by_days_left(),
    }
    return render(request, "predictor/home.html", ctx)


# ─── Prediction form + result ─────────────────────────────────────────────────

@require_http_methods(["GET", "POST"])
def predict(request):
    form = FlightPredictionForm()

    if request.method == "POST":
        form = FlightPredictionForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data

            airline       = cd["airline"]
            source        = cd["source_city"]
            destination   = cd["destination_city"]
            dep_time      = cd["departure_time"]
            arr_time      = cd["arrival_time"]
            stops         = cd["stops"]
            f_class       = cd["flight_class"]
            duration      = cd["duration"]
            days_left     = cd["days_left"]

            logger.info(
                "Prediction request: %s | %s → %s | %s | dur=%.1f | days=%d",
                airline, source, destination, f_class, duration, days_left,
            )

            try:
                price = predict_price(
                    airline_name=airline.name,
                    source_city_name=source.name,
                    destination_city_name=destination.name,
                    departure_time_label=dep_time.label,
                    arrival_time_label=arr_time.label,
                    stops_code=stops.code,
                    flight_class_name=f_class.name,
                    duration=duration,
                    days_left=days_left,
                )
            except FileNotFoundError as exc:
                logger.error("Model not found: %s", exc)
                messages.error(
                    request,
                    "⚠️ Model not found. Please run python test.py first to train the model.",
                )
                return render(request, "predictor/predict.html", {"form": form})
            except Exception as exc:
                logger.exception("Prediction error: %s", exc)
                messages.error(request, f"Prediction failed: {exc}")
                return render(request, "predictor/predict.html", {"form": form})

            # Persist to PredictionLog
            log = PredictionLog.objects.create(
                airline=airline,
                source_city=source,
                destination_city=destination,
                departure_time=dep_time,
                arrival_time=arr_time,
                stops=stops,
                flight_class=f_class,
                duration=duration,
                days_left=days_left,
                predicted_price=price,
                session_key=request.session.session_key or "",
            )
            logger.info("PredictionLog #%d saved: ₹%.2f", log.pk, price)

            # Pass pk so result view can fetch fresh from DB
            return redirect("predictor:result", pk=log.pk)

        else:
            logger.warning("Form validation failed: %s", form.errors)
            messages.warning(request, "Please fix the errors below.")

    ctx = {
        "form": form,
        "steps": [
            {"icon": "📊", "title": "Select Parameters", "desc": "Choose airline, route, class, stops, timing and duration."},
            {"icon": "🤖", "title": "MLR Model Runs", "desc": "A trained Multiple Linear Regression pipeline encodes and scales your input, then predicts."},
            {"icon": "📈", "title": "See Price + Charts", "desc": "Get your predicted fare plus historical distribution and comparison charts."},
        ],
    }
    return render(request, "predictor/predict.html", ctx)


# ─── Result ───────────────────────────────────────────────────────────────────

def result(request, pk: int):
    log = get_object_or_404(PredictionLog, pk=pk)
    logger.info("Result page for PredictionLog #%d", pk)

    ctx = {
        "log": log,
        # Contextual charts
        "chart_distribution": chart_data.similar_flights_price_distribution(
            airline_name=log.airline.name if log.airline else "",
            source_city_name=log.source_city.name if log.source_city else "",
            destination_city_name=log.destination_city.name if log.destination_city else "",
            flight_class_name=log.flight_class.name if log.flight_class else "",
            predicted_price=log.predicted_price,
        ),
        "chart_route_airlines": chart_data.airline_avg_prices_for_route(
            source_city_name=log.source_city.name if log.source_city else "",
            destination_city_name=log.destination_city.name if log.destination_city else "",
            flight_class_name=log.flight_class.name if log.flight_class else "",
        ),
        "chart_history": chart_data.prediction_history_chart(),
    }
    return render(request, "predictor/result.html", ctx)


# ─── Analytics Dashboard ──────────────────────────────────────────────────────

def dashboard(request):
    logger.info("Dashboard requested.")
    summary = chart_data.dashboard_summary()
    ctx = {
        "summary": summary,
        "chart_airline": chart_data.avg_price_by_airline(),
        "chart_class": chart_data.avg_price_by_class(),
        "chart_stops": chart_data.avg_price_by_stops(),
        "chart_scatter": chart_data.price_vs_duration_sample(),
        "chart_days": chart_data.avg_price_by_days_left(),
        "chart_routes": chart_data.top_routes(),
        "chart_history": chart_data.prediction_history_chart(),
        "recent_preds": PredictionLog.objects.select_related(
            "airline", "source_city", "destination_city", "flight_class"
        ).order_by("-predicted_at")[:10],
    }
    return render(request, "predictor/dashboard.html", ctx)


# ─── API endpoint (AJAX): form options ────────────────────────────────────────

def api_options(request):
    """Return all dropdown options as JSON (for future SPA/HTMX use)."""
    return JsonResponse({
        "airlines": list(Airline.objects.values("id", "name")),
        "cities": list(City.objects.values("id", "name")),
        "time_slots": list(TimeSlot.objects.values("id", "label").order_by("display_order")),
        "stop_types": list(StopType.objects.values("id", "code").order_by("display_order")),
        "classes": list(FlightClass.objects.values("id", "name")),
    })
