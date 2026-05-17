"""
test.py — Flight Price Prediction: Model Training & Evaluation
==============================================================
Run this script BEFORE starting the Django server.

What it does
------------
1. Loads Clean_Dataset.xlsx from the dataset/ folder
2. Loads (or seeds) lookup data into the normalised SQLite tables
3. Bulk-inserts FlightRecord rows into the DB
4. Encodes categorical columns with LabelEncoder
5. Scales numeric features with StandardScaler
6. Trains a Multiple Linear Regression model
7. Evaluates and prints: MAE, MSE, RMSE, R², Adjusted R²
8. Saves the full sklearn Pipeline (encoder + scaler + model) as ml_models/flight_price_model.pkl

Usage
-----
    # From the project root (with venv active)
    python test.py

Logging
-------
All steps are logged to BOTH:
  • Console  (stdout)
  • logs/predictor.log  (rotating, max 5 MB × 3 files)
"""

import sys
import os
import io
import logging
import logging.handlers
from pathlib import Path

# Force UTF-8 on stdout/stderr BEFORE anything writes to them.
# Windows console is cp1252 and crashes on ╔═║─₹✓ box-drawing chars.
for _stream_name in ("stdout", "stderr"):
    _stream = getattr(sys, _stream_name, None)
    if _stream is None:
        continue
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        try:
            setattr(sys, _stream_name, io.TextIOWrapper(
                _stream.buffer, encoding="utf-8", errors="replace", line_buffering=True,
            ))
        except Exception:
            pass

# ─── Bootstrap Django settings so we can use ORM ─────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "MLR_Flight_Price.settings")

import django
django.setup()

# ─── Standard imports (after Django setup) ────────────────────────────────────
import numpy as np
import pandas as pd
import joblib

from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.pipeline import Pipeline
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    r2_score,
)
from sklearn.base import BaseEstimator, TransformerMixin

from django.conf import settings
from django.db import transaction

from predictor.models import (
    Airline, City, TimeSlot, StopType, FlightClass, FlightRecord,
)

# ─── Logging setup ────────────────────────────────────────────────────────────
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

logger = logging.getLogger("ml_training")
logger.setLevel(logging.DEBUG)

fmt = logging.Formatter(
    "[{asctime}] [{levelname}] [{name}:{lineno}] — {message}",
    style="{",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# Console handler
_ch = logging.StreamHandler(sys.stdout)
_ch.setFormatter(fmt)
_ch.setLevel(logging.DEBUG)
logger.addHandler(_ch)

# Rotating file handler (utf-8 so unicode survives in predictor.log)
_fh = logging.handlers.RotatingFileHandler(
    LOG_DIR / "predictor.log", maxBytes=5 * 1024 * 1024, backupCount=3,
    encoding="utf-8",
)
_fh.setFormatter(fmt)
_fh.setLevel(logging.DEBUG)
logger.addHandler(_fh)


# ─── Constants ────────────────────────────────────────────────────────────────
DATASET_PATH: Path = settings.DATASET_PATH
MODEL_PATH: Path = settings.ML_MODEL_PATH
MODEL_PATH.parent.mkdir(exist_ok=True)

CATEGORICAL_COLS = [
    "airline", "source_city", "destination_city",
    "departure_time", "arrival_time", "stops", "class",
]
NUMERIC_COLS = ["duration", "days_left"]
TARGET_COL = "price"
TEST_SIZE = 0.2
RANDOM_STATE = 42


# ─── Custom transformer: multi-column LabelEncoder ────────────────────────────

class MultiColumnLabelEncoder(BaseEstimator, TransformerMixin):
    """
    Apply sklearn LabelEncoder to each categorical column independently.
    Stores one encoder per column so inverse_transform is possible later.

    Why not OrdinalEncoder?
    -----------------------
    LabelEncoder is more transparent for a learning project; it lets us
    inspect encoder.classes_ per column and understand the exact integer
    mapping (which is what AIRLINE_MAP / CITY_MAP in ml_engine.py mirrors).
    """

    def __init__(self, columns):
        self.columns = columns
        self.encoders_ = {}

    def fit(self, X, y=None):
        df = pd.DataFrame(X, columns=self.columns + ["duration", "days_left"]) \
            if not isinstance(X, pd.DataFrame) else X
        for col in self.columns:
            le = LabelEncoder()
            le.fit(df[col].astype(str))
            self.encoders_[col] = le
            logger.debug(
                "LabelEncoder fitted for '%s': classes = %s",
                col, list(le.classes_),
            )
        return self

    def transform(self, X, y=None):
        df = X.copy() if isinstance(X, pd.DataFrame) else pd.DataFrame(
            X, columns=self.columns + NUMERIC_COLS
        )
        for col in self.columns:
            df[col] = self.encoders_[col].transform(df[col].astype(str))
        return df.values.astype(float)


# ─── Step 1: Load dataset ─────────────────────────────────────────────────────

def load_dataset() -> pd.DataFrame:
    logger.info("=" * 60)
    logger.info("STEP 1 — Loading dataset from: %s", DATASET_PATH)

    if not DATASET_PATH.exists():
        logger.error(
            "Dataset not found at %s\n"
            "Please download Clean_Dataset.xlsx from Kaggle and place it in dataset/",
            DATASET_PATH,
        )
        raise FileNotFoundError(f"Dataset not found: {DATASET_PATH}")

    df = pd.read_excel(DATASET_PATH, engine="openpyxl")
    logger.info("Dataset loaded: %d rows × %d columns", *df.shape)
    logger.debug("Columns: %s", list(df.columns))
    logger.debug("Data types:\n%s", df.dtypes.to_string())
    return df


# ─── Step 2: Clean & preprocess ───────────────────────────────────────────────

def preprocess(df: pd.DataFrame) -> pd.DataFrame:
    logger.info("=" * 60)
    logger.info("STEP 2 — Preprocessing")

    # Standardise column names to lowercase, strip whitespace
    df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")
    logger.debug("Normalised column names: %s", list(df.columns))

    # Drop unnecessary columns
    drop_cols = [c for c in ["unnamed:_0", "flight", "unnamed:_0_level_0"] if c in df.columns]
    if drop_cols:
        df.drop(columns=drop_cols, inplace=True)
        logger.info("Dropped columns: %s", drop_cols)

    # Rename 'class' if needed (Python keyword conflict)
    if "class" not in df.columns and "flight_class" in df.columns:
        df.rename(columns={"flight_class": "class"}, inplace=True)

    # Missing value report
    null_counts = df.isnull().sum()
    if null_counts.any():
        logger.warning("Missing values detected:\n%s", null_counts[null_counts > 0].to_string())
        df.dropna(inplace=True)
        logger.info("Rows after dropping NaN: %d", len(df))
    else:
        logger.info("No missing values found ✓")

    # Strip whitespace from string columns
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].str.strip()

    # Descriptive stats for numeric columns
    logger.info("Numeric summary:\n%s", df[NUMERIC_COLS + [TARGET_COL]].describe().to_string())

    # Outlier report (IQR method on price)
    q1, q3 = df[TARGET_COL].quantile(0.25), df[TARGET_COL].quantile(0.75)
    iqr = q3 - q1
    outliers = df[(df[TARGET_COL] < q1 - 1.5 * iqr) | (df[TARGET_COL] > q3 + 1.5 * iqr)]
    logger.info(
        "Outliers in price (IQR method): %d rows (%.2f%% of data)",
        len(outliers), 100 * len(outliers) / len(df),
    )

    logger.info("Preprocessing complete. Final shape: %d × %d", *df.shape)
    return df


# ─── Step 3: Seed DB lookup tables + bulk-insert FlightRecord ─────────────────

def seed_database(df: pd.DataFrame):
    logger.info("=" * 60)
    logger.info("STEP 3 — Seeding normalised database tables")

    # ── Lookup tables ──────────────────────────────────────────────────────────
    def upsert(model, name_field, values):
        created = 0
        for v in values:
            obj, was_created = model.objects.get_or_create(**{name_field: v})
            if was_created:
                created += 1
        logger.info("%s: %d new records inserted (total unique: %d)",
                    model.__name__, created, model.objects.count())

    upsert(Airline, "name", df["airline"].unique())
    upsert(City, "name", list(df["source_city"].unique()) + list(df["destination_city"].unique()))

    # TimeSlots with ordering
    time_order = ["Early_Morning", "Morning", "Afternoon", "Evening", "Night", "Late_Night"]
    for i, label in enumerate(time_order):
        TimeSlot.objects.get_or_create(label=label, defaults={"display_order": i})
    # catch any labels in data not in our list
    for label in set(df["departure_time"].unique()) | set(df["arrival_time"].unique()):
        TimeSlot.objects.get_or_create(label=label, defaults={"display_order": 99})
    logger.info("TimeSlot: %d records", TimeSlot.objects.count())

    stop_order = {"zero": 0, "one": 1, "two_or_more": 2}
    for code, order in stop_order.items():
        StopType.objects.get_or_create(code=code, defaults={"display_order": order})
    logger.info("StopType: %d records", StopType.objects.count())

    for class_name in df["class"].unique():
        FlightClass.objects.get_or_create(name=class_name)
    logger.info("FlightClass: %d records", FlightClass.objects.count())

    # ── Bulk-insert FlightRecord (skip if already populated) ──────────────────
    existing = FlightRecord.objects.count()
    if existing > 0:
        logger.info(
            "FlightRecord table already has %d rows — skipping bulk insert. "
            "(Delete the DB to re-seed.)", existing,
        )
        return

    logger.info("Bulk-inserting %d FlightRecord rows …", len(df))

    # Pre-cache all lookups as name→obj dicts
    airlines    = {a.name: a for a in Airline.objects.all()}
    cities      = {c.name: c for c in City.objects.all()}
    time_slots  = {t.label: t for t in TimeSlot.objects.all()}
    stop_types  = {s.code: s for s in StopType.objects.all()}
    f_classes   = {f.name: f for f in FlightClass.objects.all()}

    records = []
    errors = 0
    for _, row in df.iterrows():
        try:
            records.append(FlightRecord(
                airline=airlines[row["airline"]],
                source_city=cities[row["source_city"]],
                destination_city=cities[row["destination_city"]],
                departure_time=time_slots[row["departure_time"]],
                arrival_time=time_slots[row["arrival_time"]],
                stops=stop_types[row["stops"]],
                flight_class=f_classes[row["class"]],
                duration=float(row["duration"]),
                days_left=int(row["days_left"]),
                price=int(row["price"]),
            ))
        except (KeyError, ValueError) as exc:
            errors += 1
            if errors <= 5:
                logger.warning("Skipping row (error: %s): %s", exc, dict(row))

    with transaction.atomic():
        FlightRecord.objects.bulk_create(records, batch_size=5000)

    logger.info(
        "FlightRecord bulk insert complete: %d inserted, %d skipped",
        len(records), errors,
    )


# ─── Step 4: Build feature matrix ─────────────────────────────────────────────

def build_features(df: pd.DataFrame):
    logger.info("=" * 60)
    logger.info("STEP 4 — Building feature matrix")

    feature_cols = CATEGORICAL_COLS + NUMERIC_COLS
    X = df[feature_cols].copy()
    y = df[TARGET_COL].values

    logger.info("Feature columns: %s", feature_cols)
    logger.info("X shape: %s | y shape: %s", X.shape, y.shape)
    logger.info("Target (price) — min: %d  max: %d  mean: %.2f  std: %.2f",
                y.min(), y.max(), y.mean(), y.std())

    return X, y


# ─── Step 5: Train / test split ───────────────────────────────────────────────

def split_data(X, y):
    logger.info("=" * 60)
    logger.info("STEP 5 — Train/Test Split (%.0f%% train / %.0f%% test)",
                (1 - TEST_SIZE) * 100, TEST_SIZE * 100)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=TEST_SIZE, random_state=RANDOM_STATE
    )
    logger.info("Train size: %d  Test size: %d", len(X_train), len(X_test))
    return X_train, X_test, y_train, y_test


# ─── Step 6: Build Pipeline and train ─────────────────────────────────────────

def train_model(X_train, y_train):
    logger.info("=" * 60)
    logger.info("STEP 6 — Training Multiple Linear Regression Pipeline")
    logger.info(
        "Pipeline: MultiColumnLabelEncoder → StandardScaler → LinearRegression"
    )

    feature_cols = CATEGORICAL_COLS + NUMERIC_COLS

    pipeline = Pipeline([
        ("encoder", MultiColumnLabelEncoder(columns=CATEGORICAL_COLS)),
        ("scaler", StandardScaler()),
        ("model",  LinearRegression()),
    ])

    pipeline.fit(X_train, y_train)

    # Inspect learned coefficients
    model: LinearRegression = pipeline.named_steps["model"]
    logger.info("Intercept: %.4f", model.intercept_)
    for feat, coef in zip(feature_cols, model.coef_):
        logger.info("  Coefficient %-25s : %+.4f", feat, coef)

    return pipeline


# ─── Step 7: Evaluate ─────────────────────────────────────────────────────────

def evaluate_model(pipeline, X_train, X_test, y_train, y_test):
    logger.info("=" * 60)
    logger.info("STEP 7 — Model Evaluation")

    y_pred_train = pipeline.predict(X_train)
    y_pred_test  = pipeline.predict(X_test)

    n    = len(y_test)
    p    = X_test.shape[1]   # number of features

    mae  = mean_absolute_error(y_test, y_pred_test)
    mse  = mean_squared_error(y_test, y_pred_test)
    rmse = np.sqrt(mse)
    r2   = r2_score(y_test, y_pred_test)
    adj_r2 = 1 - (1 - r2) * (n - 1) / (n - p - 1)

    # Train metrics for overfitting check
    r2_train = r2_score(y_train, y_pred_train)

    # 5-fold CV on full dataset (sample for speed if large)
    logger.info("Running 5-fold cross-validation on training set …")
    cv_scores = cross_val_score(
        pipeline, X_train, y_train,
        cv=5, scoring="r2", n_jobs=-1,
    )

    separator = "─" * 52
    logger.info(separator)
    logger.info("  EVALUATION METRICS (Test Set)")
    logger.info(separator)
    logger.info("  MAE       : ₹%s", f"{mae:,.2f}")
    logger.info("  MSE       : %s", f"{mse:,.2f}")
    logger.info("  RMSE      : ₹%s", f"{rmse:,.2f}")
    logger.info("  R²        :  %.6f  (train: %.6f)", r2, r2_train)
    logger.info("  Adj. R²   :  %.6f", adj_r2)
    logger.info(separator)
    logger.info("  5-Fold CV R² scores: %s", [f"{s:.4f}" for s in cv_scores])
    logger.info("  CV Mean R²: %.6f  ±  %.6f", cv_scores.mean(), cv_scores.std())
    logger.info(separator)

    # Overfitting check
    r2_gap = r2_train - r2
    if r2_gap > 0.05:
        logger.warning(
            "Possible overfitting detected: train R²=%.4f vs test R²=%.4f (gap=%.4f)",
            r2_train, r2, r2_gap,
        )
    else:
        logger.info("No significant overfitting detected ✓ (gap=%.4f)", r2_gap)

    # Sample predictions
    logger.info("Sample predictions (first 5 test rows):")
    for i in range(min(5, n)):
        logger.info(
            "  Actual: ₹%-8.0f  Predicted: ₹%-8.0f  Error: ₹%+.0f",
            y_test[i], y_pred_test[i], y_pred_test[i] - y_test[i],
        )

    return {
        "mae": mae, "mse": mse, "rmse": rmse,
        "r2": r2, "adj_r2": adj_r2,
        "cv_mean": cv_scores.mean(), "cv_std": cv_scores.std(),
    }


# ─── Step 8: Save model ───────────────────────────────────────────────────────

def save_model(pipeline):
    logger.info("=" * 60)
    logger.info("STEP 8 — Saving Pipeline to %s", MODEL_PATH)
    joblib.dump(pipeline, MODEL_PATH)
    size_kb = MODEL_PATH.stat().st_size / 1024
    logger.info("Model saved successfully (%.1f KB) ✓", size_kb)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    logger.info("╔══════════════════════════════════════════════════════╗")
    logger.info("║  Flight Price Prediction — MLR Training Script       ║")
    logger.info("╚══════════════════════════════════════════════════════╝")

    df = load_dataset()
    df = preprocess(df)
    seed_database(df)
    X, y = build_features(df)
    X_train, X_test, y_train, y_test = split_data(X, y)
    pipeline = train_model(X_train, y_train)
    metrics  = evaluate_model(pipeline, X_train, X_test, y_train, y_test)
    save_model(pipeline)

    logger.info("╔══════════════════════════════════════════════════════╗")
    logger.info("║  Training complete!                                  ║")
    logger.info("║  R² = %-6.4f  |  RMSE = ₹%-10s             ║",
                metrics["r2"], f"{metrics['rmse']:,.2f}")
    logger.info("║  Model saved → ml_models/flight_price_model.pkl     ║")
    logger.info("║  Next: python manage.py runserver                    ║")
    logger.info("╚══════════════════════════════════════════════════════╝")


if __name__ == "__main__":
    main()
