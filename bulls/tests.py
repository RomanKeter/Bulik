"""Basic tests for key business rules.

Tests are intentionally small and readable to support learning.
"""

from datetime import date

from django.test import TestCase

from .models import Bull, Section, WeightRecord
from .services import calculate_bull_days


class BullModelTests(TestCase):
    """Checks strict number format behavior."""

    def setUp(self):
        self.section = Section.objects.create(number=99, side=Section.Side.LEFT, position_in_row=1)

    def test_full_code_is_built_automatically(self):
        """Save must concatenate bivayka and bull number."""
        bull = Bull.objects.create(
            bivayka="ABCDEFGH",
            bull_number="123456",
            full_code="",
            current_section=self.section,
        )
        self.assertEqual(bull.full_code, "ABCDEFGH123456")


class BullDaysTests(TestCase):
    """Verifies bull-day formula for simple scenario."""

    def setUp(self):
        section = Section.objects.create(number=100, side=Section.Side.RIGHT, position_in_row=1)
        self.bull = Bull.objects.create(
            bivayka="ZXCVBNMA",
            bull_number="654321",
            full_code="",
            current_section=section,
            arrival_date=date(2026, 1, 1),
        )
        WeightRecord.objects.create(bull=self.bull, weighing_date=date(2026, 1, 1), weight_kg=300)

    def test_bull_days_full_presence(self):
        """Bull present all 10 days should contribute 10."""
        result = calculate_bull_days(date(2026, 1, 1), date(2026, 1, 10))
        self.assertEqual(result, 10)

# Create your tests here.
