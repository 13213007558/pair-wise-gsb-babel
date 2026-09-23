import datetime
import re

import pytest

from babel import dates
from babel.dates import format_interval_skeleton
from babel.util import UTC

EN_MONTHS = {
    name: number
    for number, name in enumerate(
        ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
        start=1,
    )
}


def parse_zh_date_interval(text):
    """
    Parse a zh "y年M月d日至..." interval back into a (start, end) date pair.

    Fields collapsed into the other end (year, month) are inherited, mirroring
    how a reader resolves the shared fields; a single value parses to two
    equal dates.
    """
    parts = text.split("至")
    if len(parts) == 1:
        parts *= 2
    fields = []
    for part in parts:
        match = re.fullmatch(r"(?:(\d+)年)?(?:(\d+)月)?(\d+)日", part)
        assert match, f"unparseable zh date part: {part!r}"
        fields.append(tuple(int(group) if group else None for group in match.groups()))
    (start_y, start_m, start_d), (end_y, end_m, end_d) = fields
    year_start = start_y if start_y is not None else end_y
    year_end = end_y if end_y is not None else start_y
    month_start = start_m if start_m is not None else end_m
    month_end = end_m if end_m is not None else start_m
    return (
        datetime.date(year_start, month_start, start_d),
        datetime.date(year_end, month_end, end_d),
    )


def parse_en_date_interval(text):
    """
    Parse an en "MMM d – d, y" style interval back into a (start, end) date
    pair, inheriting collapsed fields like a reader would.
    """
    parts = text.split("\u2009\u2013\u2009")
    if len(parts) == 1:
        parts *= 2
    fields = []
    for part in parts:
        match = re.fullmatch(r"(?:(\w+) )?(\d+)(?:, (\d+))?", part)
        assert match, f"unparseable en date part: {part!r}"
        month_name, day, year = match.groups()
        fields.append(
            (
                EN_MONTHS[month_name] if month_name else None,
                int(day),
                int(year) if year else None,
            ),
        )
    (start_m, start_d, start_y), (end_m, end_d, end_y) = fields
    year_start = start_y if start_y is not None else end_y
    year_end = end_y if end_y is not None else start_y
    month_start = start_m if start_m is not None else end_m
    month_end = end_m if end_m is not None else start_m
    return (
        datetime.date(year_start, month_start, start_d),
        datetime.date(year_end, month_end, end_d),
    )


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        (
            datetime.date(2026, 3, 4),
            datetime.date(2026, 3, 6),
            "2026年3月4日至6日",
        ),
        (
            datetime.date(2026, 3, 30),
            datetime.date(2026, 4, 2),
            "2026年3月30日至4月2日",
        ),
        (
            datetime.date(2025, 12, 31),
            datetime.date(2026, 1, 2),
            "2025年12月31日至2026年1月2日",
        ),
    ],
    ids=["same-month", "cross-month", "cross-year"],
)
def test_zh_date_intervals(start, end, expected):
    formatted = format_interval_skeleton(start, end, "yMMMd", locale="zh")
    assert formatted == expected
    # Both ends of the collapsed interval must parse back to the input dates.
    assert parse_zh_date_interval(formatted) == (start, end)


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        (
            datetime.date(2026, 3, 4),
            datetime.date(2026, 3, 6),
            "Mar 4\u2009\u2013\u20096, 2026",
        ),
        (
            datetime.date(2026, 3, 30),
            datetime.date(2026, 4, 2),
            "Mar 30\u2009\u2013\u2009Apr 2, 2026",
        ),
        (
            datetime.date(2025, 12, 31),
            datetime.date(2026, 1, 2),
            "Dec 31, 2025\u2009\u2013\u2009Jan 2, 2026",
        ),
    ],
    ids=["same-month", "cross-month", "cross-year"],
)
def test_en_date_intervals(start, end, expected):
    formatted = format_interval_skeleton(start, end, "yMMMd", locale="en")
    assert formatted == expected
    assert parse_en_date_interval(formatted) == (start, end)


@pytest.mark.parametrize(
    ("start", "end", "expected", "start_fields", "end_fields"),
    [
        # Same month: the month and year are only printed once, on the end.
        (
            datetime.date(2026, 3, 4),
            datetime.date(2026, 3, 6),
            "4\u20136 مارس 2026",
            ("4",),
            ("6", "مارس", "2026"),
        ),
        # Cross month: each end carries its own month, the year is shared.
        (
            datetime.date(2026, 3, 30),
            datetime.date(2026, 4, 2),
            "30 مارس \u2013 2 أبريل 2026",
            ("30", "مارس"),
            ("2", "أبريل", "2026"),
        ),
        # Cross year: both ends are fully spelled out.
        (
            datetime.date(2025, 12, 31),
            datetime.date(2026, 1, 2),
            "31 ديسمبر 2025 \u2013 2 يناير 2026",
            ("31", "ديسمبر", "2025"),
            ("2", "يناير", "2026"),
        ),
    ],
    ids=["same-month", "cross-month", "cross-year"],
)
def test_ar_date_intervals(start, end, expected, start_fields, end_fields):
    formatted = format_interval_skeleton(start, end, "yMMMd", locale="ar")
    assert formatted == expected
    # Manually verify the fields of each end: the shared fields must appear
    # exactly where a reader expects them.
    if start.month == end.month:
        assert formatted.count("مارس") == 1  # the shared month is never duplicated
    for field in start_fields + end_fields:
        assert field in formatted


def test_equal_dates_degrade_to_single_value():
    day = datetime.date(2026, 3, 4)
    assert format_interval_skeleton(day, day, "yMMMd", locale="zh") == "2026年3月4日"
    assert format_interval_skeleton(day, day, "yMMMd", locale="en") == "Mar 4, 2026"
    assert format_interval_skeleton(day, day, "yMMMd", locale="ar") == "4 مارس 2026"


def test_difference_only_in_unexpressed_fields_degrades_to_single_value():
    start = datetime.datetime(2026, 3, 4, 0, 0, 1)
    end = datetime.datetime(2026, 3, 4, 23, 59, 59)
    assert format_interval_skeleton(start, end, "yMMMd", locale="en") == "Mar 4, 2026"


def test_narrow_month_skeleton_fuzzy_matches():
    start = datetime.date(2026, 3, 4)
    end = datetime.date(2026, 3, 6)
    # "yMMMMMd" (narrow month) is not a CLDR interval skeleton; the closest
    # match "yMMMd" is used instead of guessing.
    assert (
        format_interval_skeleton(start, end, "yMMMMMd", locale="en")
        == "Mar 4\u2009\u2013\u20096, 2026"
    )
    assert format_interval_skeleton(start, end, "yMMMMMd", locale="zh") == "2026年3月4日至6日"


def test_day_period_intervals():
    morning = datetime.datetime(2026, 3, 4, 9, 0)
    forenoon = datetime.datetime(2026, 3, 4, 10, 0)
    afternoon = datetime.datetime(2026, 3, 4, 15, 0)
    # Different day periods: the period is printed on both ends.
    assert (
        format_interval_skeleton(morning, afternoon, "Bhm", locale="zh")
        == "上午9:00至下午3:00"
    )
    assert (
        format_interval_skeleton(morning, afternoon, "Bhm", locale="en")
        == "9:00 in the morning\u2009\u2013\u20093:00 in the afternoon"
    )
    # Same day period: the period is collapsed into the first end.
    assert format_interval_skeleton(morning, forenoon, "Bhm", locale="zh") == "上午9:00至10:00"


def test_am_pm_interval():
    morning = datetime.datetime(2026, 3, 4, 9, 0)
    afternoon = datetime.datetime(2026, 3, 4, 15, 0)
    assert (
        format_interval_skeleton(morning, afternoon, "hm", locale="zh") == "上午9:00至下午3:00"
    )


def test_same_timezone_normalization(timezone_getter):
    hki_tz = timezone_getter("Europe/Helsinki")
    # 2026-03-04 22:00 UTC and 23:00 UTC are both 2026-03-05 in Helsinki.
    start = datetime.datetime(2026, 3, 4, 22, 0, tzinfo=UTC)
    end = datetime.datetime(2026, 3, 4, 23, 0, tzinfo=UTC)
    assert (
        format_interval_skeleton(start, end, "yMMMd", tzinfo=hki_tz, locale="en")
        == "Mar 5, 2026"
    )


def test_different_timezones_per_instant(timezone_getter):
    hki_tz = timezone_getter("Europe/Helsinki")
    start = datetime.datetime(2026, 3, 4, 22, 0, tzinfo=UTC)
    end = datetime.datetime(2026, 3, 5, 10, 0, tzinfo=hki_tz)
    # Each instant is rendered in its own zone: Mar 4 (UTC) and Mar 5 (EET).
    formatted = format_interval_skeleton(start, end, "yMMMd", locale="en")
    assert formatted == "Mar 4\u2009\u2013\u20095, 2026"
    assert parse_en_date_interval(formatted) == (
        datetime.date(2026, 3, 4),
        datetime.date(2026, 3, 5),
    )
    # Forcing a single zone folds both ends onto the same day.
    assert (
        format_interval_skeleton(start, end, "yMMMd", tzinfo=hki_tz, locale="en")
        == "Mar 5, 2026"
    )


def test_mixed_date_and_datetime():
    start = datetime.date(2026, 3, 4)
    end = datetime.datetime(2026, 3, 6, 12, 0)
    formatted = format_interval_skeleton(start, end, "yMMMd", locale="zh")
    assert formatted == "2026年3月4日至6日"
    assert parse_zh_date_interval(formatted) == (
        datetime.date(2026, 3, 4),
        datetime.date(2026, 3, 6),
    )


def test_fallback_full_formats_both_ends():
    start = datetime.date(2026, 3, 4)
    end = datetime.date(2026, 3, 6)
    assert (
        format_interval_skeleton(start, end, "xyz", fuzzy=False, fallback="full", locale="en")
        == "Mar 4, 2026\u2009\u2013\u2009Mar 6, 2026"
    )
    assert (
        format_interval_skeleton(start, end, "xyz", fuzzy=False, fallback="full", locale="zh")
        == "2026年3月4日 \u2013 2026年3月6日"
    )


def test_fallback_raise_on_unknown_skeleton():
    start = datetime.date(2026, 3, 4)
    end = datetime.date(2026, 3, 6)
    with pytest.raises(ValueError, match="No interval format found"):
        format_interval_skeleton(start, end, "xyz", fuzzy=False, fallback="raise", locale="en")


def test_fallback_raise_on_uncovered_difference():
    # The "Hm" interval pattern cannot express a difference in seconds.
    start = datetime.datetime(2026, 3, 4, 0, 0, 1)
    end = datetime.datetime(2026, 3, 4, 0, 0, 2)
    with pytest.raises(ValueError, match="No interval pattern"):
        format_interval_skeleton(start, end, "Hm", fuzzy=False, fallback="raise", locale="en")
    # ...but the default "full" fallback just shows the single shared value.
    assert format_interval_skeleton(start, end, "Hm", fuzzy=False, locale="en") == "00:00"


def test_invalid_fallback_mode():
    with pytest.raises(ValueError, match="Invalid fallback mode"):
        format_interval_skeleton(
            datetime.date(2026, 3, 4),
            datetime.date(2026, 3, 6),
            "yMMMd",
            fallback="bogus",
            locale="en",
        )


def test_locale_is_required():
    with pytest.raises(TypeError):
        format_interval_skeleton(datetime.date(2026, 3, 4), datetime.date(2026, 3, 6), "yMMMd")
    with pytest.raises(ValueError, match="explicit locale"):
        format_interval_skeleton(
            datetime.date(2026, 3, 4),
            datetime.date(2026, 3, 6),
            "yMMMd",
            locale=None,
        )


def test_format_date_datetime_interfaces_unchanged():
    # The classic entry points keep their signatures and defaults.
    day = datetime.date(2026, 3, 4)
    assert dates.format_date(day, locale="zh") == "2026年3月4日"
    assert dates.format_date(day, format="full", locale="en") == "Wednesday, March 4, 2026"
    moment = datetime.datetime(2026, 3, 4, 15, 30, tzinfo=UTC)
    assert dates.format_datetime(moment, locale="en") == "Mar 4, 2026, 3:30:00\u202fPM"
