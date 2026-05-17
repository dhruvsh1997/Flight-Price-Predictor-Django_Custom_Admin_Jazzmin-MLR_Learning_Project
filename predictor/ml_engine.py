"""
predictor/ml_engine.py
======================
Handles loading the trained Multiple Linear Regression model (pkl) and
transforming form inputs into the feature vector the model expects.

The preprocessing pipeline (encoders + scaler) is saved inside the same pkl
alongside the model — so this module only needs to call pipeline.predict().
"""

import sys
import logging
import joblib
import pandas as pd
from pathlib import Path
from django.conf import settings

from .transformers import MultiColumnLabelEncoder

CATEGORICAL_COLS = [
    "airline", "source_city", "destination_city",
    "departure_time", "arrival_time", "stops", "class",
]
NUMERIC_COLS = ["duration", "days_left"]

logger = logging.getLogger("predictor")

_pipeline = None   # module-level cache — load once per process


def _load_pipeline():
    """Load the ML pipeline from disk (lazy, cached)."""
    global _pipeline
    if _pipeline is None:
        model_path: Path = settings.ML_MODEL_PATH
        if not model_path.exists():
            logger.error(
                "Model file not found at %s. "
                "Run `python test.py` first to train and save the model.",
                model_path,
            )
            raise FileNotFoundError(
                f"Model not found: {model_path}\n"
                "Please run `python test.py` to train and save the model."
            )

        # Pipeline was pickled while test.py ran as __main__, so the class
        # path stored in the pkl is `__main__.MultiColumnLabelEncoder`.
        # Inject the class into the current __main__ so unpickling resolves it.
        sys.modules["__main__"].MultiColumnLabelEncoder = MultiColumnLabelEncoder

        logger.info("Loading ML pipeline from %s", model_path)
        _pipeline = joblib.load(model_path)
        logger.info("ML pipeline loaded successfully.")
    return _pipeline


def predict_price(
    airline_name: str,
    source_city_name: str,
    destination_city_name: str,
    departure_time_label: str,
    arrival_time_label: str,
    stops_code: str,
    flight_class_name: str,
    duration: float,
    days_left: int,
) -> float:
    """
    Transform raw string inputs → predicted price.

    The saved pipeline performs label-encoding + scaling internally, so we
    must pass the raw string values exactly as they appeared during training.

    Returns
    -------
    float  Predicted price in INR.
    """
    logger.debug(
        "predict_price called: airline=%s src=%s dst=%s dep=%s arr=%s "
        "stops=%s class=%s dur=%.1f days=%d",
        airline_name, source_city_name, destination_city_name,
        departure_time_label, arrival_time_label,
        stops_code, flight_class_name, duration, days_left,
    )

    features = pd.DataFrame([{
        "airline": airline_name,
        "source_city": source_city_name,
        "destination_city": destination_city_name,
        "departure_time": departure_time_label,
        "arrival_time": arrival_time_label,
        "stops": stops_code,
        "class": flight_class_name,
        "duration": float(duration),
        "days_left": int(days_left),
    }], columns=CATEGORICAL_COLS + NUMERIC_COLS)

    pipeline = _load_pipeline()
    try:
        prediction = pipeline.predict(features)[0]
    except ValueError as exc:
        logger.error("Unknown category passed to pipeline: %s", exc)
        raise ValueError(f"Unknown category: {exc}") from exc
    prediction = max(0.0, float(prediction))   # prices can't be negative

    logger.info(
        "Prediction result: ₹%.2f  (airline=%s, %s→%s, class=%s, dur=%.1fh, days=%d)",
        prediction, airline_name, source_city_name, destination_city_name,
        flight_class_name, duration, days_left,
    )
    return prediction
