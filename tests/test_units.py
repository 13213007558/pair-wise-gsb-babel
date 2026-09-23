import decimal

import pytest

from babel.units import (
    UnknownUnitError,
    format_compound_unit,
    format_unit,
    format_unit_list,
)


# New units in CLDR 46
@pytest.mark.parametrize(('unit', 'count', 'expected'), [
    ('speed-light-speed', 1, '1 světlo'),
    ('speed-light-speed', 2, '2 světla'),
    ('speed-light-speed', 5, '5 světel'),
    ('concentr-portion-per-1e9', 1, '1 částice na miliardu'),
    ('concentr-portion-per-1e9', 2, '2 částice na miliardu'),
    ('concentr-portion-per-1e9', 5, '5 částic na miliardu'),
    ('duration-night', 1, '1 noc'),
    ('duration-night', 2, '2 noci'),
    ('duration-night', 5, '5 nocí'),
])
def test_new_cldr46_units(unit, count, expected):
    assert format_unit(count, unit, locale='cs_CZ') == expected


@pytest.mark.parametrize(('value', 'unit', 'locale', 'expected'), [
    (30, 'kilometer-per-hour', 'en', '30 kilometers per hour'),
    (30, 'kilometer-per-hour', 'zh', '每小时30公里'),
    (30, 'kilometer-per-hour', 'ar', '30 كيلومتر في الساعة'),
    (20, 'celsius', 'en', '20 degrees Celsius'),
    (20, 'celsius', 'zh', '20摄氏度'),
    (3, 'foot', 'en', '3 feet'),
    (decimal.Decimal('-3.5'), 'celsius', 'en', '-3.5 degrees Celsius'),
    (0, 'fahrenheit', 'en', '0 degrees Fahrenheit'),
])
def test_format_unit_basics(value, unit, locale, expected):
    assert format_unit(value, unit, locale=locale) == expected


def test_format_unit_unknown():
    with pytest.raises(UnknownUnitError):
        format_unit(1, 'horse', locale='en')


@pytest.mark.parametrize(('locale', 'expected'), [
    ('en', '30 kilometers per hour'),
    ('zh', '每小时30公里'),
    ('ar', '30 كيلومتر في الساعة'),
])
def test_format_compound_unit_per_semantics(locale, expected):
    # "kilometer per hour" is resolved to the predefined compound unit
    # "speed-kilometer-per-hour", not treated as a new static unit key.
    assert format_compound_unit(30, 'kilometer', denominator_unit='hour', locale=locale) == expected


def test_format_compound_unit_independent_plural_forms():
    # The numerator and denominator pick their plural forms independently.
    assert format_compound_unit(1, 'kilometer', 2, 'hour', locale='en') == '1 kilometer per 2 hours'
    assert format_compound_unit(2, 'kilometer', 1, 'hour', locale='en') == '2 kilometers per hour'


def test_format_compound_unit_decimal_value():
    assert format_compound_unit(
        decimal.Decimal('-0.5'), 'meter', denominator_unit='second', locale='en',
    ) == '-0.5 meters per second'


def test_format_compound_unit_unknown_unit():
    with pytest.raises(UnknownUnitError):
        format_compound_unit(1, 'horse', denominator_unit='hour', locale='en')
    with pytest.raises(UnknownUnitError):
        format_compound_unit(5, 'meter', 3, 'purple', locale='en')


@pytest.mark.parametrize(('values', 'length', 'locale', 'expected'), [
    # Single items are not list-formatted.
    ([(30, 'kilometer-per-hour')], 'long', 'en', '30 kilometers per hour'),
    ([(30, 'kilometer-per-hour')], 'long', 'zh', '每小时30公里'),
    ([(30, 'kilometer-per-hour')], 'long', 'ar', '30 كيلومتر في الساعة'),
    # Two items use the locale's "two"/"start" list pattern.
    ([(3, 'foot'), (2, 'inch')], 'long', 'en', '3 feet, 2 inches'),
    ([(3, 'foot'), (2, 'inch')], 'short', 'zh', '3英尺2英寸'),
    ([(3, 'meter'), (2, 'kilometer')], 'long', 'ar', '3 أمتار، و2 كيلومتر'),
    # Three or more items use the "start"/"middle"/"end" list patterns.
    (
        [(30, 'kilometer-per-hour'), (3, 'foot'), (20, 'celsius')],
        'long', 'en',
        '30 kilometers per hour, 3 feet, 20 degrees Celsius',
    ),
    (
        [(1, 'kilometer'), (200, 'meter'), (30, 'centimeter')],
        'short', 'zh',
        '1公里200米30厘米',
    ),
    (
        [(1, 'kilometer'), (200, 'meter'), (30, 'centimeter')],
        'long', 'ar',
        '1 كيلومتر، و200 متر، و30 سنتيمتر',
    ),
    # Widths select both the unit display width and the list style.
    ([(3, 'foot'), (2, 'inch')], 'narrow', 'en', '3′ 2″'),
    ([(3, 'foot'), (2, 'inch')], 'short', 'en', '3 ft, 2 in'),
    # Decimal, negative and zero values keep the usual number formatting.
    (
        [(decimal.Decimal('-3.5'), 'celsius'), (0, 'fahrenheit')],
        'long', 'en',
        '-3.5 degrees Celsius, 0 degrees Fahrenheit',
    ),
])
def test_format_unit_list(values, length, locale, expected):
    assert format_unit_list(values, length=length, locale=locale) == expected


def test_format_unit_list_empty():
    assert format_unit_list([], locale='en') == ''


def test_format_unit_list_preformatted_strings():
    # Preformatted strings (e.g. compound units) can be mixed with (value, unit) tuples.
    speed = format_compound_unit(30, 'kilometer', denominator_unit='hour', locale='en')
    assert format_unit_list([speed, (20, 'celsius')], locale='en') == \
        '30 kilometers per hour, 20 degrees Celsius'


def test_format_unit_list_number_format_and_numbering_system():
    assert format_unit_list([(1234.5, 'meter')], format='#.0', locale='en') == '1234.5 meters'
    assert format_unit_list(
        [(1234.5, 'kilometer')], locale='ar', numbering_system='arab',
    ) == '1٬234٫5 كيلومتر'


def test_format_unit_list_unknown_unit():
    with pytest.raises(UnknownUnitError):
        format_unit_list([(1, 'horse')], locale='en')
    with pytest.raises(UnknownUnitError):
        format_unit_list([(1, 'meter'), (2, 'horse')], locale='en')
