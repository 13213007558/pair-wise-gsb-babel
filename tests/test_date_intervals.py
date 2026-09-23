import datetime

import pytest

from babel import dates
from babel.util import UTC

TEST_DT = datetime.datetime(2016, 1, 8, 11, 46, 15)
TEST_TIME = TEST_DT.time()
TEST_DATE = TEST_DT.date()


def test_format_interval_same_instant_1():
    assert (
        dates.format_interval(TEST_DT, TEST_DT, "yMMMd", fuzzy=False, locale="fi")
        == "8.1.2016"
    )


def test_format_interval_same_instant_2():
    assert (
        dates.format_interval(TEST_DT, TEST_DT, "xxx", fuzzy=False, locale="fi")
        == "8.1.2016 11.46.15"
    )


def test_format_interval_same_instant_3():
    assert (
        dates.format_interval(TEST_TIME, TEST_TIME, "xxx", fuzzy=False, locale="fi")
        == "11.46.15"
    )


def test_format_interval_same_instant_4():
    assert (
        dates.format_interval(TEST_DATE, TEST_DATE, "xxx", fuzzy=False, locale="fi")
        == "8.1.2016"
    )


def test_format_interval_no_difference():
    t1 = TEST_DT
    t2 = t1 + datetime.timedelta(minutes=8)
    assert dates.format_interval(t1, t2, "yMd", fuzzy=False, locale="fi") == "8.1.2016"


def test_format_interval_in_tz(timezone_getter):
    t1 = TEST_DT.replace(tzinfo=UTC)
    t2 = t1 + datetime.timedelta(minutes=18)
    hki_tz = timezone_getter("Europe/Helsinki")
    assert (
        dates.format_interval(t1, t2, "Hmv", tzinfo=hki_tz, locale="fi")
        == "13.46\u201314.04 aikavyöhyke: Suomi"
    )


def test_format_interval_12_hour():
    t2 = TEST_DT
    t1 = t2 - datetime.timedelta(hours=1)
    assert (
        dates.format_interval(t1, t2, "hm", locale="en")
        == "10:46\u2009\u2013\u200911:46\u202fAM"
    )


def test_format_interval_invalid_skeleton():
    t1 = TEST_DATE
    t2 = TEST_DATE + datetime.timedelta(days=1)
    assert (
        dates.format_interval(t1, t2, "mumumu", fuzzy=False, locale="fi")
        == "8.1.2016\u20139.1.2016"
    )
    assert dates.format_interval(t1, t2, fuzzy=False, locale="fi") == "8.1.2016\u20139.1.2016"


def test_issue_825():
    assert (
        dates.format_timedelta(
            datetime.timedelta(hours=1),
            granularity='hour',
            threshold=100,
            format='short',
            locale='pt',
        )
        == '1 h'
    )


# ---------------------------------------------------------------------------
# format_interval_skeleton
# ---------------------------------------------------------------------------

SAME_MONTH = (datetime.date(2026, 3, 4), datetime.date(2026, 3, 6))
CROSS_MONTH = (datetime.date(2026, 3, 28), datetime.date(2026, 4, 3))
CROSS_YEAR = (datetime.date(2025, 12, 30), datetime.date(2026, 1, 2))


def test_format_interval_skeleton_zh_same_month():
    assert (
        dates.format_interval_skeleton("yMMMd", *SAME_MONTH, locale="zh")
        == "2026年3月4日至6日"
    )


def test_format_interval_skeleton_zh_cross_month():
    assert (
        dates.format_interval_skeleton("yMMMd", *CROSS_MONTH, locale="zh")
        == "2026年3月28日至4月3日"
    )


def test_format_interval_skeleton_zh_cross_year():
    assert (
        dates.format_interval_skeleton("yMMMd", *CROSS_YEAR, locale="zh")
        == "2025年12月30日至2026年1月2日"
    )


def test_format_interval_skeleton_en_same_month():
    assert (
        dates.format_interval_skeleton("yMMMd", *SAME_MONTH, locale="en")
        == "Mar 4\u2009–\u20096, 2026"
    )


def test_format_interval_skeleton_en_cross_month():
    assert (
        dates.format_interval_skeleton("yMMMd", *CROSS_MONTH, locale="en")
        == "Mar 28\u2009–\u2009Apr 3, 2026"
    )


def test_format_interval_skeleton_en_cross_year():
    assert (
        dates.format_interval_skeleton("yMMMd", *CROSS_YEAR, locale="en")
        == "Dec 30, 2025\u2009–\u2009Jan 2, 2026"
    )


def test_format_interval_skeleton_ar_same_month():
    # Shared year/month rendered once ("مارس 2026"), both day values retained.
    assert dates.format_interval_skeleton("yMMMd", *SAME_MONTH, locale="ar") == "4–6 مارس 2026"


def test_format_interval_skeleton_ar_cross_month():
    assert (
        dates.format_interval_skeleton("yMMMd", *CROSS_MONTH, locale="ar")
        == "28 مارس – 3 أبريل 2026"
    )


def test_format_interval_skeleton_ar_cross_year():
    assert (
        dates.format_interval_skeleton("yMMMd", *CROSS_YEAR, locale="ar")
        == "30 ديسمبر 2025 – 2 يناير 2026"
    )


@pytest.mark.parametrize(
    "locale,single",
    [("zh", "2026年3月4日"), ("en", "Mar 4, 2026"), ("ar", "4 مارس 2026")],
)
def test_format_interval_skeleton_equal_dates_degrade_to_single(locale, single):
    assert (
        dates.format_interval_skeleton("yMMMd", SAME_MONTH[0], SAME_MONTH[0], locale=locale)
        == single
    )


def test_format_interval_skeleton_equal_dates_not_duplicated():
    # Same calendar day, different clock times: a day-only skeleton must not
    # print the date twice (nor join it with a range separator).
    t1 = datetime.datetime(2026, 3, 4, 9, 15)
    t2 = datetime.datetime(2026, 3, 4, 18, 30)
    assert dates.format_interval_skeleton("yMd", t1, t2, locale="zh") == "2026/3/4"
    assert "–" not in dates.format_interval_skeleton("yMd", t1, t2, locale="zh")


def test_format_interval_skeleton_narrow_month_matches_fuzzy():
    assert (
        dates.format_interval_skeleton("yMMMMMd", *SAME_MONTH, locale="en")
        == "Mar 4\u2009–\u20096, 2026"
    )
    assert (
        dates.format_interval_skeleton("yMMMMMd", *SAME_MONTH, locale="zh")
        == "2026年3月4日至6日"
    )


def test_format_interval_skeleton_day_period():
    t1 = datetime.datetime(2026, 3, 4, 7, 30)
    t2 = datetime.datetime(2026, 3, 4, 18, 30)
    assert dates.format_interval_skeleton("Bhm", t1, t2, locale="zh") == "早上7:30至下午6:30"
    assert (
        dates.format_interval_skeleton("Bhm", t1, t2, locale="en")
        == "7:30 in the morning\u2009–\u20096:30 in the evening"
    )


def test_format_interval_skeleton_in_same_timezone(timezone_getter):
    tz = timezone_getter("Asia/Tokyo")
    t1 = datetime.datetime(2026, 3, 4, 0, 30, tzinfo=UTC).astimezone(tz)
    t2 = datetime.datetime(2026, 3, 4, 9, 30, tzinfo=UTC).astimezone(tz)
    assert (
        dates.format_interval_skeleton("Hm", t1, t2, locale="en") == "09:30\u2009–\u200918:30"
    )


def test_format_interval_skeleton_in_different_timezones(timezone_getter):
    # Each end carries its own tzinfo, and each is rendered in its own zone.
    tokyo = timezone_getter("Asia/Tokyo")
    new_york = timezone_getter("America/New_York")
    t1 = datetime.datetime(2026, 3, 4, 23, 0, tzinfo=UTC).astimezone(tokyo)
    t2 = datetime.datetime(2026, 3, 5, 2, 0, tzinfo=UTC).astimezone(new_york)
    assert (
        dates.format_interval_skeleton("Hm", t1, t2, locale="en") == "08:00\u2009–\u200921:00"
    )
    # For a skeleton without an interval pattern, both ends are printed in full,
    # so the two local dates (March 5 in Tokyo, March 4 in New York) cannot be
    # mistaken for a single date or reordered by the reader.
    assert (
        dates.format_interval_skeleton("yMMMdHm", t1, t2, locale="en")
        == "Mar 5, 2026, 8:00:00\u202fAM\u2009–\u2009Mar 4, 2026, 9:00:00\u202fPM"
    )


def test_format_interval_skeleton_mixed_date_and_datetime():
    end = datetime.datetime(2026, 3, 6, 9, 0)
    assert (
        dates.format_interval_skeleton("yMMMd", SAME_MONTH[0], end, locale="zh")
        == "2026年3月4日至6日"
    )
    assert (
        dates.format_interval_skeleton("yMMMd", SAME_MONTH[0], end, locale="en")
        == "Mar 4\u2009–\u20096, 2026"
    )


def test_format_interval_skeleton_fallback_full_joins_complete_ends():
    assert (
        dates.format_interval_skeleton(
            "xxx", *SAME_MONTH, fuzzy=False, fallback="full", locale="zh"
        )
        == "2026年3月4日 – 2026年3月6日"
    )
    assert (
        dates.format_interval_skeleton(
            "xxx", *SAME_MONTH, fuzzy=False, fallback="full", locale="en"
        )
        == "Mar 4, 2026\u2009–\u2009Mar 6, 2026"
    )
    # Arabic keeps the locale's RTL marks and digit/punctuation conventions.
    assert (
        dates.format_interval_skeleton(
            "xxx", *SAME_MONTH, fuzzy=False, fallback="full", locale="ar"
        )
        == "04\u200f/03\u200f/2026 – 06\u200f/03\u200f/2026"
    )


def test_format_interval_skeleton_fallback_full_uses_requested_datetime_skeleton():
    # "yQQQ" is a single-value skeleton but not an interval skeleton.
    assert (
        dates.format_interval_skeleton(
            "yQQQ",
            datetime.date(2026, 3, 4),
            datetime.date(2026, 6, 6),
            fallback="full",
            locale="zh",
        )
        == "2026年第1季度 – 2026年第2季度"
    )
    # Equal rendered ends collapse to a single value even on the fallback path.
    assert (
        dates.format_interval_skeleton(
            "yQQQ",
            datetime.date(2026, 3, 4),
            datetime.date(2026, 3, 5),
            fallback="full",
            locale="zh",
        )
        == "2026年第1季度"
    )


def test_format_interval_skeleton_fallback_raise():
    with pytest.raises(KeyError):
        dates.format_interval_skeleton(
            "xxx", *SAME_MONTH, fuzzy=False, fallback="raise", locale="zh"
        )


def test_format_interval_skeleton_invalid_fallback_value():
    with pytest.raises(ValueError):
        dates.format_interval_skeleton("yMd", *SAME_MONTH, fallback="guess", locale="zh")


def test_format_interval_skeleton_locale_is_required():
    with pytest.raises(TypeError):
        dates.format_interval_skeleton("yMd", *SAME_MONTH)


def test_format_interval_skeleton_end_fields_verified_by_parsing():
    # Split the English output at the range dash and parse each end back,
    # ensuring shared fields never make the ends ambiguous.
    text = dates.format_interval_skeleton("yMd", *SAME_MONTH, locale="en")
    first, second = (part.strip() for part in text.split("\u2013"))
    assert dates.parse_date(first, locale="en") == SAME_MONTH[0]
    assert dates.parse_date(second, locale="en") == SAME_MONTH[1]

    text = dates.format_interval_skeleton("yMd", *CROSS_YEAR, locale="en")
    first, second = (part.strip() for part in text.split("\u2013"))
    assert dates.parse_date(first, locale="en") == CROSS_YEAR[0]
    assert dates.parse_date(second, locale="en") == CROSS_YEAR[1]


def test_format_interval_skeleton_returns_plain_text():
    assert isinstance(dates.format_interval_skeleton("yMMMd", *SAME_MONTH, locale="zh"), str)


def test_format_interval_still_supports_day_period():
    # The extract() fix also repairs format_interval for B/b skeletons,
    # which previously raised NotImplementedError.
    t1 = datetime.datetime(2026, 3, 4, 7, 30)
    t2 = datetime.datetime(2026, 3, 4, 18, 30)
    assert (
        dates.format_interval(t1, t2, "Bhm", locale="en")
        == "7:30 in the morning\u2009–\u20096:30 in the evening"
    )
