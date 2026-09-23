import decimal
import re

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


@pytest.mark.parametrize(('numerator_value', 'numerator_unit', 'denominator_value', 'denominator_unit', 'length', 'locale', 'expected'), [
    # Speed units, all three widths, in English, Chinese and Arabic
    (30, 'kilometer', 1, 'hour', 'long', 'en', '30 kilometers per hour'),
    (30, 'kilometer', 1, 'hour', 'short', 'en', '30 km/h'),
    (30, 'kilometer', 1, 'hour', 'narrow', 'en', '30km/h'),
    (30, 'kilometer', 1, 'hour', 'long', 'zh_CN', '每小时30公里'),
    (30, 'kilometer', 1, 'hour', 'narrow', 'zh_CN', '30km/h'),
    (30, 'kilometer', 1, 'hour', 'long', 'ar', '30 كيلومتر في الساعة'),
    (30, 'kilometer', 1, 'hour', 'short', 'ar', '30 كم/س'),
    # Decimal values keep the regular number formatting
    (decimal.Decimal('30.5'), 'kilometer', 1, 'hour', 'long', 'en', '30.5 kilometers per hour'),
    # Negative values keep their sign
    (-5, 'kilometer', 1, 'hour', 'long', 'en', '-5 kilometers per hour'),
    # "per" semantics with a non-1 denominator; each value pluralized independently
    (32.5, 'ton', 15, 'hour', 'long', 'en', '32.5 tons per 15 hours'),
    (1, 'ton', 1, 'hour', 'long', 'en', '1 ton per hour'),
    # Temperature over duration, resolved through the locale's per pattern
    (2, 'celsius', 1, 'hour', 'long', 'en', '2 degrees Celsius per hour'),
    (2, 'celsius', 1, 'hour', 'long', 'ar', '2 درجة مئوية في الساعة'),
    # Unitless values fall back to the locale's generic "x/y" pattern
    (7, None, 11, None, 'short', 'en', '7/11'),
])
def test_format_compound_unit(numerator_value, numerator_unit, denominator_value, denominator_unit, length, locale, expected):
    assert format_compound_unit(
        numerator_value,
        numerator_unit,
        denominator_value,
        denominator_unit=denominator_unit,
        length=length,
        locale=locale,
    ) == expected


def test_format_compound_unit_unknown_numerator_unit():
    with pytest.raises(UnknownUnitError):
        format_compound_unit(1, 'horse', denominator_unit='hour', locale='en')


def test_format_compound_unit_unknown_denominator_unit():
    with pytest.raises(UnknownUnitError):
        format_compound_unit(1, 'kilometer', denominator_unit='fortnight', locale='en')


def test_format_compound_unit_does_not_shadow_static_units():
    # "kilometer-per-hour" is resolved dynamically, not stored as a static
    # unit key; the regular format_unit entry points keep working as before.
    assert format_unit(30, 'speed-kilometer-per-hour', locale='en') == '30 kilometers per hour'
    assert format_unit(30, 'kilometer', locale='en') == '30 kilometers'


@pytest.mark.parametrize(('values', 'length', 'locale', 'expected'), [
    # Empty and single-item lists
    ([], 'long', 'en', ''),
    ([(20, 'temperature-celsius')], 'long', 'en', '20 degrees Celsius'),
    ([(20, 'temperature-celsius')], 'long', 'zh_CN', '20摄氏度'),
    ([(20, 'temperature-celsius')], 'long', 'ar', '20 درجة مئوية'),
    # Two items use the locale's "two" pattern; plural forms are chosen per item
    ([(1, 'length-foot'), (2, 'length-inch')], 'long', 'en', '1 foot, 2 inches'),
    ([(3, 'length-foot'), (2, 'length-inch')], 'short', 'zh_CN', '3英尺2英寸'),
    ([(3, 'length-foot'), (2, 'length-inch')], 'short', 'ar', '3 قدم و2 بوصة'),
    # Three or more items use the "start"/"middle"/"end" patterns
    ([(1, 'length-foot'), (2, 'length-inch'), (3, 'length-mile')], 'long', 'en',
     '1 foot, 2 inches, 3 miles'),
    ([(1, 'length-foot'), (2, 'length-inch'), (0, 'temperature-celsius')], 'long', 'en',
     '1 foot, 2 inches, 0 degrees Celsius'),
    ([(3, 'length-foot'), (2, 'length-inch'), (20, 'temperature-celsius')], 'short', 'ar',
     '3 قدم، و2 بوصة، و20°م'),
    # Widths select both unit names and list styles
    ([(3, 'length-foot'), (2, 'length-inch')], 'short', 'en', '3 ft, 2 in'),
    ([(3, 'length-foot'), (2, 'length-inch')], 'narrow', 'en', '3′ 2″'),
    ([(3, 'length-foot'), (2, 'length-inch')], 'narrow', 'zh_CN', '3′2″'),
    # Speed units can be listed alongside length units
    ([(30, 'speed-kilometer-per-hour'), (3, 'length-foot')], 'long', 'en',
     '30 kilometers per hour, 3 feet'),
    # Negative, zero and Decimal values keep the regular number formatting
    ([(decimal.Decimal('-2.5'), 'temperature-celsius')], 'long', 'en', '-2.5 degrees Celsius'),
    ([(0, 'length-foot')], 'long', 'en', '0 feet'),
    ([(decimal.Decimal('0.5'), 'length-inch'), (2, 'length-foot')], 'long', 'en',
     '0.5 inches, 2 feet'),
])
def test_format_unit_list(values, length, locale, expected):
    assert format_unit_list(values, length=length, locale=locale) == expected


def test_format_unit_list_unknown_unit():
    with pytest.raises(UnknownUnitError):
        format_unit_list([(1, 'length-foot'), (2, 'length-horse')], locale='en')


def _parse_en_unit_list(formatted):
    # Test helper: parse an English formatted unit list back into
    # (value, unit) structure. The API itself only returns localized text.
    if not formatted:
        return []
    return [
        (match.group(1), match.group(2))
        for match in map(re.compile(r'(-?[\d.]+)\s+(.+)').fullmatch, formatted.split(', '))
    ]


def test_format_unit_list_output_can_be_parsed_back():
    formatted = format_unit_list(
        [(1, 'length-foot'), (2, 'length-inch'), (30, 'speed-kilometer-per-hour')],
        locale='en',
    )
    assert _parse_en_unit_list(formatted) == [
        ('1', 'foot'),
        ('2', 'inches'),
        ('30', 'kilometers per hour'),
    ]
