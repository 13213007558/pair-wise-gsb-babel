# Tests for babel.dates.format_relative_time

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from freezegun import freeze_time

from babel import dates
from babel.dates import format_relative_time


def test_frozen_clock_future_and_past_en():
    with freeze_time("2024-01-01 12:00:00"):
        now = datetime.now()
        assert format_relative_time(
            datetime(2024, 1, 1, 13, 30) - now, locale='en',
        ) == 'in 2 hours'
        assert format_relative_time(
            datetime(2024, 1, 1, 10, 30) - now, locale='en',
        ) == '2 hours ago'


def test_frozen_clock_boundary_matrix():
    """The same boundary set in en, fr and ar under a frozen clock."""
    with freeze_time("2024-01-01 12:00:00"):
        now = datetime.now()

        def at(**kwargs):
            return datetime(2024, 1, 1, 12, 0, 0) + timedelta(**kwargs) - now

        # Rounding: 1.5 hours rounds half-even to 2 in all three locales.
        assert format_relative_time(at(hours=1.5), locale='en') == 'in 2 hours'
        assert format_relative_time(at(hours=1.5), locale='fr') == 'dans 2 heures'
        assert format_relative_time(at(hours=1.5), locale='ar') == '\u062e\u0644\u0627\u0644 \u0633\u0627\u0639\u062a\u064a\u0646'

        # Unit switching: 23 hours crosses the 0.85 day threshold.
        assert format_relative_time(at(hours=23), locale='en') == 'in 1 day'
        assert format_relative_time(at(hours=23), locale='fr') == 'dans 1 jour'
        assert format_relative_time(at(hours=23), locale='ar') == '\u062e\u0644\u0627\u0644 \u064a\u0648\u0645 \u0648\u0627\u062d\u062f'

        # Direction: past uses the locale's own past syntax.
        assert format_relative_time(at(hours=-2), locale='en') == '2 hours ago'
        assert format_relative_time(at(hours=-2), locale='fr') == 'il y a 2 heures'
        assert format_relative_time(at(hours=-2), locale='ar') == '\u0642\u0628\u0644 \u0633\u0627\u0639\u062a\u064a\u0646'


def test_exact_threshold_crossing():
    # 0.85 days == 73440 seconds exactly: switches to days.
    assert format_relative_time(timedelta(seconds=73440), locale='en') == 'in 1 day'
    assert format_relative_time(timedelta(seconds=-73440), locale='en') == '1 day ago'
    # One second below the threshold stays in hours.
    assert format_relative_time(timedelta(seconds=73439), locale='en') == 'in 20 hours'
    assert format_relative_time(timedelta(seconds=-73439), locale='en') == '20 hours ago'


def test_custom_thresholds():
    delta = timedelta(hours=23)
    assert format_relative_time(delta, thresholds={'day': 1.1}, locale='en') == 'in 23 hours'
    assert format_relative_time(delta, thresholds={'day': Decimal('0.5')}, locale='en') == 'in 1 day'
    with pytest.raises(ValueError, match='Invalid threshold unit'):
        format_relative_time(delta, thresholds={'fortnight': 0.5}, locale='en')


def test_rounding_modes():
    delta = timedelta(minutes=90)
    assert format_relative_time(delta, locale='en') == 'in 2 hours'
    assert format_relative_time(delta, rounding_mode='ROUND_HALF_DOWN', locale='en') == 'in 1 hour'
    assert format_relative_time(delta, rounding_mode='ROUND_DOWN', locale='en') == 'in 1 hour'
    assert format_relative_time(delta, rounding_mode='ROUND_UP', locale='en') == 'in 2 hours'
    # 2.5 rounds to 2 with the default ROUND_HALF_EVEN.
    assert format_relative_time(timedelta(minutes=150), locale='en') == 'in 2 hours'
    with pytest.raises(ValueError, match='Invalid rounding mode'):
        format_relative_time(delta, rounding_mode='ROUND_SIDEWAYS', locale='en')


def test_granularity_limits():
    delta = timedelta(days=3)
    assert format_relative_time(delta, max_granularity='hour', locale='en') == 'in 72 hours'
    assert format_relative_time(timedelta(seconds=30), min_granularity='minute', locale='en') == 'in 1 minute'
    with pytest.raises(ValueError, match='Invalid min_granularity'):
        format_relative_time(delta, min_granularity='fortnight', locale='en')
    with pytest.raises(ValueError, match='Invalid max_granularity'):
        format_relative_time(delta, max_granularity='fortnight', locale='en')
    with pytest.raises(ValueError, match='smaller than'):
        format_relative_time(delta, min_granularity='day', max_granularity='hour', locale='en')


def test_negative_zero_and_zero():
    assert format_relative_time(Decimal('-0'), locale='en') == 'in 0 seconds'
    assert format_relative_time(Decimal('0'), locale='en') == 'in 0 seconds'
    assert format_relative_time(timedelta(0), locale='en') == 'in 0 seconds'
    assert format_relative_time(0, locale='en') == 'in 0 seconds'


def test_numeric_input_types():
    assert format_relative_time(5400, locale='en') == 'in 2 hours'
    assert format_relative_time(Decimal('5400'), locale='en') == 'in 2 hours'
    assert format_relative_time(5400.0, locale='en') == 'in 2 hours'
    assert format_relative_time(Decimal('-5400'), locale='en') == '2 hours ago'
    # Fractional seconds are preserved exactly, never routed through float.
    assert format_relative_time(Decimal('0.4'), locale='en') == 'in 1 second'
    assert format_relative_time(timedelta(microseconds=1), locale='en') == 'in 1 second'


def test_very_large_intervals():
    # 100_000 years in seconds, exactly representable as a Decimal.
    assert format_relative_time(Decimal('3153600000000'), locale='en') == 'in 100,000 years'
    assert format_relative_time(Decimal('-3153600000000'), locale='en') == '100,000 years ago'
    with pytest.raises(ValueError, match='finite'):
        format_relative_time(Decimal('Infinity'), locale='en')


def test_plural_uses_displayed_value_ar():
    # Arabic has dedicated zero/one/two/few/many plural categories; the
    # category must be derived from the final displayed (rounded) value.
    assert format_relative_time(timedelta(hours=1), locale='ar') == '\u062e\u0644\u0627\u0644 \u0633\u0627\u0639\u0629 \u0648\u0627\u062d\u062f\u0629'
    assert format_relative_time(timedelta(hours=2), locale='ar') == '\u062e\u0644\u0627\u0644 \u0633\u0627\u0639\u062a\u064a\u0646'
    assert format_relative_time(timedelta(hours=3), locale='ar') == '\u062e\u0644\u0627\u0644 3 \u0633\u0627\u0639\u0627\u062a'
    assert format_relative_time(timedelta(hours=11), locale='ar') == '\u062e\u0644\u0627\u0644 11 \u0633\u0627\u0639\u0629'
    # 1.5 hours rounds to the displayed value 2, i.e. the "two" category.
    assert format_relative_time(timedelta(minutes=90), locale='ar') == '\u062e\u0644\u0627\u0644 \u0633\u0627\u0639\u062a\u064a\u0646'
    assert format_relative_time(timedelta(minutes=-90), locale='ar') == '\u0642\u0628\u0644 \u0633\u0627\u0639\u062a\u064a\u0646'


def test_format_variants():
    delta = timedelta(hours=3)
    assert format_relative_time(delta, format='long', locale='en') == 'in 3 hours'
    assert format_relative_time(delta, format='short', locale='en') == 'in 3 hr.'
    assert format_relative_time(delta, format='narrow', locale='en') == 'in 3h'
    assert format_relative_time(delta, format='short', locale='fr') == 'dans 3\xa0h'
    with pytest.raises(TypeError, match='Format must be one of'):
        format_relative_time(delta, format='medium', locale='en')


def test_missing_data_falls_back_to_root():
    # The root locale provides generic patterns for every unit.
    assert format_relative_time(timedelta(hours=2), locale='root') == '+2 h'
    assert format_relative_time(timedelta(hours=-2), locale='root') == '-2 h'


def test_format_timedelta_unchanged():
    # The existing API keeps its exact behavior.
    assert dates.format_timedelta(timedelta(weeks=12), locale='en_US') == '3 months'
    assert dates.format_timedelta(timedelta(hours=1), add_direction=True, locale='en') == 'in 1 hour'
    assert dates.format_timedelta(timedelta(hours=-1), add_direction=True, locale='en') == '1 hour ago'
