"""
Django settings for MLR_Flight_Price project.
Configured with Jazzmin admin theme, file + console logging, SQLite DB.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ─── Base Paths ──────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "django-insecure-change-me-in-production-123456")
DEBUG = os.getenv("DEBUG", "True") == "True"
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")

# ─── Applications ─────────────────────────────────────────────────────────────
INSTALLED_APPS = [
    # Jazzmin must be FIRST to override default admin templates
    "jazzmin",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Project app
    "predictor",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "MLR_Flight_Price.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "MLR_Flight_Price.wsgi.application"

# ─── Database ─────────────────────────────────────────────────────────────────
# Normalized SQLite DB — tables: Airline, City, TimeSlot, Stop, FlightClass, FlightRecord
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# ─── Password Validation ──────────────────────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ─── Internationalisation ─────────────────────────────────────────────────────
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

# ─── Static / Media Files ─────────────────────────────────────────────────────
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ─── ML Model & Dataset Paths ─────────────────────────────────────────────────
ML_MODEL_PATH = BASE_DIR / "ml_models" / "flight_price_model.pkl"
DATASET_PATH = BASE_DIR / "dataset" / "Clean_Dataset.xlsx"

# ─── Logging Configuration ────────────────────────────────────────────────────
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] [{levelname}] [{name}] [{module}:{lineno}] — {message}",
            "style": "{",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
        "simple": {
            "format": "[{levelname}] {message}",
            "style": "{",
        },
    },
    "handlers": {
        # ── Console handler ──────────────────────────────────────────────────
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
            "level": "DEBUG",
        },
        # ── Rotating file handler (Django app logs) ──────────────────────────
        "file_django": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOG_DIR / "django.log",
            "maxBytes": 5 * 1024 * 1024,  # 5 MB
            "backupCount": 3,
            "formatter": "verbose",
            "level": "INFO",
            "encoding": "utf-8",
        },
        # ── Rotating file handler (ML / predictor logs) ──────────────────────
        "file_predictor": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOG_DIR / "predictor.log",
            "maxBytes": 5 * 1024 * 1024,
            "backupCount": 3,
            "formatter": "verbose",
            "level": "DEBUG",
            "encoding": "utf-8",
        },
    },
    "loggers": {
        # Root logger
        "": {
            "handlers": ["console", "file_django"],
            "level": "WARNING",
            "propagate": True,
        },
        # Django internals
        "django": {
            "handlers": ["console", "file_django"],
            "level": "INFO",
            "propagate": False,
        },
        # Our predictor app
        "predictor": {
            "handlers": ["console", "file_predictor"],
            "level": "DEBUG",
            "propagate": False,
        },
        # ML training script (test.py uses this logger)
        "ml_training": {
            "handlers": ["console", "file_predictor"],
            "level": "DEBUG",
            "propagate": False,
        },
    },
}

# ─── Jazzmin Admin UI Configuration ──────────────────────────────────────────
JAZZMIN_SETTINGS = {
    # ── Branding ────────────────────────────────────────────────────────────
    "site_title": "Flight Price Predictor",
    "site_header": "✈ Flight Price Predictor",
    "site_brand": "FlightML Admin",
    "site_logo": None,
    "login_logo": None,
    "site_icon": None,
    "welcome_sign": "Welcome to the Flight Price Prediction Admin Panel",
    "copyright": "Flight Price Predictor — MLR Demo Project",
    "search_model": ["predictor.FlightRecord"],

    # ── Top Menu ─────────────────────────────────────────────────────────────
    "topmenu_links": [
        {"name": "🏠 Home", "url": "home", "permissions": ["auth.view_user"]},
        {"name": "📊 Predictor", "url": "predictor:predict", "permissions": ["auth.view_user"]},
        {"name": "📈 Dashboard", "url": "predictor:dashboard", "permissions": ["auth.view_user"]},
        {"model": "auth.User"},
    ],

    # ── User Menu ─────────────────────────────────────────────────────────────
    "usermenu_links": [
        {"name": "Flight Predictor", "url": "predictor:predict", "icon": "fas fa-plane"},
        {"model": "auth.user"},
    ],

    # ── Sidebar ──────────────────────────────────────────────────────────────
    "show_sidebar": True,
    "navigation_expanded": True,
    "hide_apps": [],
    "hide_models": [],

    "order_with_respect_to": [
        "predictor",
        "predictor.FlightRecord",
        "predictor.Airline",
        "predictor.City",
        "predictor.TimeSlot",
        "predictor.StopType",
        "predictor.FlightClass",
        "predictor.PredictionLog",
        "auth",
    ],

    "icons": {
        "auth": "fas fa-users-cog",
        "auth.user": "fas fa-user",
        "auth.Group": "fas fa-users",
        "predictor.FlightRecord": "fas fa-plane-departure",
        "predictor.Airline": "fas fa-building",
        "predictor.City": "fas fa-city",
        "predictor.TimeSlot": "fas fa-clock",
        "predictor.StopType": "fas fa-map-marker-alt",
        "predictor.FlightClass": "fas fa-chair",
        "predictor.PredictionLog": "fas fa-chart-line",
    },

    "default_icon_parents": "fas fa-chevron-circle-right",
    "default_icon_children": "fas fa-circle",

    # ── UI Tweaks ────────────────────────────────────────────────────────────
    "related_modal_active": True,
    "custom_css": None,
    "custom_js": None,
    "use_google_fonts_cdn": True,
    "show_ui_builder": True,   # ← Enables the live UI builder in admin!
    "changeform_format": "horizontal_tabs",
    "changeform_format_overrides": {
        "auth.user": "collapsible",
        "auth.group": "vertical_tabs",
    },
    "language_chooser": False,
}

# ── Jazzmin UI Tweaks (fine-grained styling) ──────────────────────────────────
JAZZMIN_UI_TWEAKS = {
    "navbar_small_text": False,
    "footer_small_text": False,
    "body_small_text": True,
    "brand_small_text": False,
    "brand_colour": "navbar-primary",
    "accent": "accent-primary",
    "navbar": "navbar-dark",
    "no_navbar_border": False,
    "navbar_fixed": True,
    "layout_boxed": False,
    "footer_fixed": False,
    "sidebar_fixed": True,
    "sidebar": "sidebar-dark-primary",
    "sidebar_nav_small_text": False,
    "sidebar_disable_expand": False,
    "sidebar_nav_child_indent": True,
    "sidebar_nav_compact_style": False,
    "sidebar_nav_legacy_style": False,
    "sidebar_nav_flat_style": False,
    "theme": "flatly",           # Options: default, darkly, flatly, cosmo, cyborg …
    "dark_mode_theme": "darkly",
    "button_classes": {
        "primary": "btn-primary",
        "secondary": "btn-secondary",
        "info": "btn-info",
        "warning": "btn-warning",
        "danger": "btn-danger",
        "success": "btn-success",
    },
}
