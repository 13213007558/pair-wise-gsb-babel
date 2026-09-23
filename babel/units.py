from __future__ import annotations

import decimal
from collections.abc import Sequence
from typing import Literal

from babel.core import Locale
from babel.lists import format_list
from babel.numbers import LC_NUMERIC, format_decimal


class UnknownUnitError(ValueError):
    def __init__(self, unit: str, locale: Locale) -> None:
        ValueError.__init__(self, f"{unit} is not a known unit in {locale}")


def get_unit_name(
    measurement_unit: str,
    length: Literal['short', 'long', 'narrow'] = 'long',
    locale: Locale | str | None = None,
) -> str | None:
    """
    Get the display name for a measurement unit in the given locale.

    >>> get_unit_name("radian", locale="en")
    'radians'

    Unknown units will raise exceptions:

    >>> get_unit_name("battery", locale="fi")
    Traceback (most recent call last):
        ...
    UnknownUnitError: battery/long is not a known unit/length in fi

    :param measurement_unit: the code of a measurement unit.
                             Known units can be found in the CLDR Unit Validity XML file:
                             https://unicode.org/repos/cldr/tags/latest/common/validity/unit.xml

    :param length: "short", "long" or "narrow"
    :param locale: the `Locale` object or locale identifier. Defaults to the system numeric locale.
    :return: The unit display name, or None.
    """
    locale = Locale.parse(locale or LC_NUMERIC)
    unit = _find_unit_pattern(measurement_unit, locale=locale)
    if not unit:
        raise UnknownUnitError(unit=measurement_unit, locale=locale)
    return locale.unit_display_names.get(unit, {}).get(length)


def _find_unit_pattern(unit_id: str, locale: Locale | str | None = None) -> str | None:
    """
    Expand a unit into a qualified form.

    Known units can be found in the CLDR Unit Validity XML file:
    https://unicode.org/repos/cldr/tags/latest/common/validity/unit.xml

    >>> _find_unit_pattern("radian", locale="en")
    'angle-radian'

    Unknown values will return None.

    >>> _find_unit_pattern("horse", locale="en")

    :param unit_id: the code of a measurement unit.
    :return: A key to the `unit_patterns` mapping, or None.
    """
    locale = Locale.parse(locale or LC_NUMERIC)
    unit_patterns: dict[str, str] = locale._data["unit_patterns"]
    if unit_id in unit_patterns:
        return unit_id
    for unit_pattern in sorted(unit_patterns, key=len):
        if unit_pattern.endswith(unit_id):
            return unit_pattern
    return None


def format_unit(
    value: str | float | decimal.Decimal,
    measurement_unit: str,
    length: Literal['short', 'long', 'narrow'] = 'long',
    format: str | None = None,
    locale: Locale | str | None = None,
    *,
    numbering_system: Literal["default"] | str = "latn",
) -> str:
    """Format a value of a given unit.

    Values are formatted according to the locale's usual pluralization rules
    and number formats.

    >>> format_unit(12, 'length-meter', locale='ro_RO')
    '12 metri'
    >>> format_unit(15.5, 'length-mile', locale='fi_FI')
    '15,5 mailia'
    >>> format_unit(1200, 'pressure-millimeter-ofhg', locale='nb')
    '1\\xa0200 millimeter kvikks\\xf8lv'
    >>> format_unit(270, 'ton', locale='en')
    '270 tons'
    >>> format_unit(1234.5, 'kilogram', locale='ar_EG', numbering_system='default')
    '1٬234٫5 كيلوغرام'

    Number formats may be overridden with the ``format`` parameter.

    >>> import decimal
    >>> format_unit(decimal.Decimal("-42.774"), 'temperature-celsius', 'short', format='#.0', locale='fr')
    '-42,8\\u202f\\xb0C'

    The locale's usual pluralization rules are respected.

    >>> format_unit(1, 'length-meter', locale='ro_RO')
    '1 metru'
    >>> format_unit(0, 'length-mile', locale='cy')
    '0 mi'
    >>> format_unit(1, 'length-mile', locale='cy')
    '1 filltir'
    >>> format_unit(3, 'length-mile', locale='cy')
    '3 milltir'

    >>> format_unit(15, 'length-horse', locale='fi')
    Traceback (most recent call last):
        ...
    UnknownUnitError: length-horse is not a known unit in fi

    .. versionadded:: 2.2.0

    :param value: the value to format. If this is a string, no number formatting will be attempted.
    :param measurement_unit: the code of a measurement unit.
                             Known units can be found in the CLDR Unit Validity XML file:
                             https://unicode.org/repos/cldr/tags/latest/common/validity/unit.xml
    :param length: "short", "long" or "narrow"
    :param format: An optional format, as accepted by `format_decimal`.
    :param locale: the `Locale` object or locale identifier. Defaults to the system numeric locale.
    :param numbering_system: The numbering system used for formatting number symbols. Defaults to "latn".
                             The special value "default" will use the default numbering system of the locale.
    :raise `UnsupportedNumberingSystemError`: If the numbering system is not supported by the locale.
    """
    locale = Locale.parse(locale or LC_NUMERIC)

    q_unit = _find_unit_pattern(measurement_unit, locale=locale)
    if not q_unit:
        raise UnknownUnitError(unit=measurement_unit, locale=locale)
    unit_patterns = locale._data["unit_patterns"][q_unit].get(length, {})

    if isinstance(value, str):  # Assume the value is a preformatted singular.
        formatted_value = value
        plural_form = "one"
    else:
        formatted_value = format_decimal(
            value,
            format,
            locale,
            numbering_system=numbering_system,
        )
        plural_form = locale.plural_form(value)

    if plural_form in unit_patterns:
        return unit_patterns[plural_form].format(formatted_value)

    # Fall back to a somewhat bad representation.
    # nb: This is marked as no-cover, as the current CLDR seemingly has no way for this to happen.
    fallback_name = get_unit_name(  # pragma: no cover
        measurement_unit,
        length=length,
        locale=locale,
    )
    return f"{formatted_value} {fallback_name or measurement_unit}"  # pragma: no cover


def _find_compound_unit(
    numerator_unit: str,
    denominator_unit: str,
    locale: Locale | str | None = None,
) -> str | None:
    """
    Find a predefined compound unit pattern.

    Used internally by format_compound_unit.

    >>> _find_compound_unit("kilometer", "hour", locale="en")
    'speed-kilometer-per-hour'

    >>> _find_compound_unit("mile", "gallon", locale="en")
    'consumption-mile-per-gallon'

    If no predefined compound pattern can be found, `None` is returned.

    >>> _find_compound_unit("gallon", "mile", locale="en")

    >>> _find_compound_unit("horse", "purple", locale="en")

    :param numerator_unit: The numerator unit's identifier
    :param denominator_unit: The denominator unit's identifier
    :param locale: the `Locale` object or locale identifier. Defaults to the system numeric locale.
    :return: A key to the `unit_patterns` mapping, or None.
    :rtype: str|None
    """
    locale = Locale.parse(locale or LC_NUMERIC)

    # Qualify the numerator and denominator units.  This will turn possibly partial
    # units like "kilometer" or "hour" into actual units like "length-kilometer" and
    # "duration-hour".

    resolved_numerator_unit = _find_unit_pattern(numerator_unit, locale=locale)
    resolved_denominator_unit = _find_unit_pattern(denominator_unit, locale=locale)

    # If either was not found, we can't possibly build a suitable compound unit either.
    if not (resolved_numerator_unit and resolved_denominator_unit):
        return None

    # Since compound units are named "speed-kilometer-per-hour", we'll have to slice off
    # the quantities (i.e. "length", "duration") from both qualified units.

    bare_numerator_unit = resolved_numerator_unit.split("-", 1)[-1]
    bare_denominator_unit = resolved_denominator_unit.split("-", 1)[-1]

    # Now we can try and rebuild a compound unit specifier, then qualify it:

    return _find_unit_pattern(
        f"{bare_numerator_unit}-per-{bare_denominator_unit}",
        locale=locale,
    )


def format_compound_unit(
    numerator_value: str | float | decimal.Decimal,
    numerator_unit: str | None = None,
    denominator_value: str | float | decimal.Decimal = 1,
    denominator_unit: str | None = None,
    length: Literal["short", "long", "narrow"] = "long",
    format: str | None = None,
    locale: Locale | str | None = None,
    *,
    numbering_system: Literal["default"] | str = "latn",
) -> str | None:
    """
    Format a compound number value, i.e. "kilometers per hour" or similar.

    Both unit specifiers are optional to allow for formatting of arbitrary values still according
    to the locale's general "per" formatting specifier.

    >>> format_compound_unit(7, denominator_value=11, length="short", locale="pt")
    '7/11'

    >>> format_compound_unit(150, "kilometer", denominator_unit="hour", locale="sv")
    '150 kilometer per timme'

    >>> format_compound_unit(150, "kilowatt", denominator_unit="year", locale="fi")
    '150 kilowattia / vuosi'

    >>> format_compound_unit(32.5, "ton", 15, denominator_unit="hour", locale="en")
    '32.5 tons per 15 hours'

    >>> format_compound_unit(1234.5, "ton", 15, denominator_unit="hour", locale="ar_EG", numbering_system="arab")
    '1٬234٫5 طن لكل 15 ساعة'

    >>> format_compound_unit(160, denominator_unit="square-meter", locale="fr")
    '160 par m\\xe8tre carr\\xe9'

    >>> format_compound_unit(4, "meter", "ratakisko", length="short", locale="fi")
    '4 m/ratakisko'

    >>> format_compound_unit(35, "minute", denominator_unit="nautical-mile", locale="sv")
    '35 minuter per nautisk mil'

    >>> from babel.numbers import format_currency
    >>> format_compound_unit(format_currency(35, "JPY", locale="de"), denominator_unit="liter", locale="de")
    '35\\xa0\\xa5 pro Liter'

    See https://www.unicode.org/reports/tr35/tr35-general.html#perUnitPatterns

    :param numerator_value: The numerator value. This may be a string,
                            in which case it is considered preformatted and the unit is ignored.
    :param numerator_unit: The numerator unit. See `format_unit`.
    :param denominator_value: The denominator value. This may be a string,
                              in which case it is considered preformatted and the unit is ignored.
    :param denominator_unit: The denominator unit. See `format_unit`.
    :param length: The formatting length. "short", "long" or "narrow"
    :param format: An optional format, as accepted by `format_decimal`.
    :param locale: the `Locale` object or locale identifier. Defaults to the system numeric locale.
    :param numbering_system: The numbering system used for formatting number symbols. Defaults to "latn".
                             The special value "default" will use the default numbering system of the locale.
    :return: A formatted compound value.
    :raise `UnsupportedNumberingSystemError`: If the numbering system is not supported by the locale.
    """
    locale = Locale.parse(locale or LC_NUMERIC)

    # Look for a specific compound unit first...

    if numerator_unit and denominator_unit and denominator_value == 1:
        compound_unit = _find_compound_unit(numerator_unit, denominator_unit, locale=locale)
        if compound_unit:
            return format_unit(
                numerator_value,
                compound_unit,
                length=length,
                format=format,
                locale=locale,
                numbering_system=numbering_system,
            )

    # ... failing that, construct one "by hand".

    if isinstance(numerator_value, str):  # Numerator is preformatted
        formatted_numerator = numerator_value
    elif numerator_unit:  # Numerator has unit
        formatted_numerator = format_unit(
            numerator_value,
            numerator_unit,
            length=length,
            format=format,
            locale=locale,
            numbering_system=numbering_system,
        )
    else:  # Unitless numerator
        formatted_numerator = format_decimal(
            numerator_value,
            format=format,
            locale=locale,
            numbering_system=numbering_system,
        )

    if isinstance(denominator_value, str):  # Denominator is preformatted
        formatted_denominator = denominator_value
    elif denominator_unit:  # Denominator has unit
        if denominator_value == 1:  # support perUnitPatterns when the denominator is 1
            denominator_unit = _find_unit_pattern(denominator_unit, locale=locale)
            per_pattern = (
                locale._data["unit_patterns"]
                .get(denominator_unit, {})
                .get(length, {})
                .get("per")
            )
            if per_pattern:
                return per_pattern.format(formatted_numerator)
            # See TR-35's per-unit pattern algorithm, point 3.2.
            # For denominator 1, we replace the value to be formatted with the empty string;
            # this will make `format_unit` return " second" instead of "1 second".
            denominator_value = ""

        formatted_denominator = format_unit(
            denominator_value,
            measurement_unit=(denominator_unit or ""),
            length=length,
            format=format,
            locale=locale,
            numbering_system=numbering_system,
        ).strip()
    else:  # Bare denominator
        formatted_denominator = format_decimal(
            denominator_value,
            format=format,
            locale=locale,
            numbering_system=numbering_system,
        )

    # TODO: this doesn't support "compound_variations" (or "prefix"), and will fall back to the "x/y" representation
    per_pattern = (
        locale._data["compound_unit_patterns"]
        .get("per", {})
        .get(length, {})
        .get("compound", "{0}/{1}")
    )

    return per_pattern.format(formatted_numerator, formatted_denominator)


#: Mapping from unit format lengths to the list pattern styles
#: defined by CLDR for lists of units.
_length_to_list_style = {
    "long": "unit",
    "short": "unit-short",
    "narrow": "unit-narrow",
}


def format_unit_list(
    values: Sequence[tuple[str | float | decimal.Decimal, str] | str],
    length: Literal["short", "long", "narrow"] = "long",
    format: str | None = None,
    locale: Locale | str | None = None,
    *,
    numbering_system: Literal["default"] | str = "latn",
) -> str:
    """
    Format a list of unit values, e.g. "3 feet, 2 inches".

    Each item is a `(value, unit)` tuple, which is formatted with
    `format_unit` (and thus honors the locale's pluralization rules and
    number formats), or a preformatted string, which is used as-is.

    The items are joined using the locale's list patterns for units,
    so the conjunctions and separators follow the CLDR "two", "start",
    "middle" and "end" patterns instead of a hard-coded comma.

    >>> format_unit_list([(3, "foot"), (2, "inch")], locale="en")
    '3 feet, 2 inches'

    >>> format_unit_list([(3, "foot"), (2, "inch")], length="narrow", locale="en")
    '3\u2032 2\u2033'

    >>> format_unit_list([(3, "foot"), (2, "inch")], length="short", locale="zh")
    '3\u82f1\u5c3a2\u82f1\u5bf8'

    A single item is returned as-is, without list formatting:

    >>> format_unit_list([(30, "kilometer-per-hour")], locale="zh")
    '\u6bcf\u5c0f\u65f630\u516c\u91cc'

    >>> format_unit_list([(1, "kilometer"), (200, "meter"), (30, "centimeter")], locale="ar")
    '1 \u0643\u064a\u0644\u0648\u0645\u062a\u0631\u060c \u0648200 \u0645\u062a\u0631\u060c \u064830 \u0633\u0646\u062a\u064a\u0645\u062a\u0631'

    Values may be `decimal.Decimal` instances; negative, zero and fractional
    values are formatted like `format_unit` formats them:

    >>> import decimal
    >>> format_unit_list([(decimal.Decimal("-3.5"), "celsius"), (0, "fahrenheit")], locale="en")
    '-3.5 degrees Celsius, 0 degrees Fahrenheit'

    Preformatted strings can be mixed in, which allows compound units
    (see `format_compound_unit`) to take part in a list:

    >>> speed = format_compound_unit(30, "kilometer", denominator_unit="hour", locale="en")
    >>> format_unit_list([speed, (20, "celsius")], locale="en")
    '30 kilometers per hour, 20 degrees Celsius'

    An empty list formats to an empty string:

    >>> format_unit_list([], locale="en")
    ''

    Unknown units raise an exception:

    >>> format_unit_list([(1, "horse")], locale="en")
    Traceback (most recent call last):
        ...
    UnknownUnitError: horse is not a known unit in en

    .. versionadded:: 2.19.0

    :param values: a sequence of `(value, unit)` tuples as accepted by
                   `format_unit`, or preformatted strings.
    :param length: The formatting length. "short", "long" or "narrow"
    :param format: An optional format, as accepted by `format_decimal`.
    :param locale: the `Locale` object or locale identifier. Defaults to the system numeric locale.
    :param numbering_system: The numbering system used for formatting number symbols. Defaults to "latn".
                             The special value "default" will use the default numbering system of the locale.
    :return: A formatted list of unit values.
    :raise `UnknownUnitError`: If a unit is not known in the locale.
    :raise `UnsupportedNumberingSystemError`: If the numbering system is not supported by the locale.
    """
    locale = Locale.parse(locale or LC_NUMERIC)

    formatted_values = []
    for item in values:
        if isinstance(item, str):  # Preformatted, e.g. the result of `format_compound_unit`.
            formatted_values.append(item)
        else:
            value, unit = item
            formatted_values.append(format_unit(
                value,
                unit,
                length=length,
                format=format,
                locale=locale,
                numbering_system=numbering_system,
            ))

    return format_list(
        formatted_values,
        style=_length_to_list_style[length],
        locale=locale,
    )
