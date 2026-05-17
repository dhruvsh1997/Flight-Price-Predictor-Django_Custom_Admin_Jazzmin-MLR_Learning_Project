"""
predictor/management/commands/seed_lookups.py
=============================================
Management command to seed the normalised lookup tables WITHOUT
needing the full dataset (useful when running test.py separately).

Usage:
    python manage.py seed_lookups
"""

import logging
from django.core.management.base import BaseCommand
from predictor.models import Airline, City, TimeSlot, StopType, FlightClass

logger = logging.getLogger("predictor")

AIRLINES = ["Air_India", "AirAsia", "GO_FIRST", "Indigo", "SpiceJet", "Vistara"]
CITIES   = ["Bangalore", "Chennai", "Delhi", "Hyderabad", "Kolkata", "Mumbai"]
TIMES    = [
    ("Early_Morning", 0), ("Morning", 1), ("Afternoon", 2),
    ("Evening", 3), ("Night", 4), ("Late_Night", 5),
]
STOPS    = [("zero", 0), ("one", 1), ("two_or_more", 2)]
CLASSES  = ["Economy", "Business"]


class Command(BaseCommand):
    help = "Seed lookup tables: Airline, City, TimeSlot, StopType, FlightClass"

    def handle(self, *args, **options):
        self.stdout.write("Seeding lookup tables …")

        for name in AIRLINES:
            obj, created = Airline.objects.get_or_create(name=name)
            if created:
                logger.debug("Created Airline: %s", name)

        for name in CITIES:
            obj, created = City.objects.get_or_create(name=name)
            if created:
                logger.debug("Created City: %s", name)

        for label, order in TIMES:
            obj, created = TimeSlot.objects.get_or_create(label=label, defaults={"display_order": order})
            if created:
                logger.debug("Created TimeSlot: %s", label)

        for code, order in STOPS:
            obj, created = StopType.objects.get_or_create(code=code, defaults={"display_order": order})
            if created:
                logger.debug("Created StopType: %s", code)

        for name in CLASSES:
            obj, created = FlightClass.objects.get_or_create(name=name)
            if created:
                logger.debug("Created FlightClass: %s", name)

        self.stdout.write(self.style.SUCCESS(
            "✓ Lookup tables seeded successfully.\n"
            f"  Airlines: {Airline.objects.count()}  |  Cities: {City.objects.count()}  |  "
            f"TimeSlots: {TimeSlot.objects.count()}  |  StopTypes: {StopType.objects.count()}  |  "
            f"Classes: {FlightClass.objects.count()}"
        ))
        logger.info("seed_lookups management command completed.")
