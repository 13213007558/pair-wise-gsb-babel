#
# Copyright (C) 2007-2011 Edgewall Software, 2013-2025 the Babel team
# All rights reserved.
#
# This software is licensed as described in the file LICENSE, which
# you should have received as part of this distribution. The terms
# are also available at https://github.com/python-babel/babel/blob/master/LICENSE.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://github.com/python-babel/babel/commits/master/.

import decimal

import pytest

from babel import numbers


def test_can_parse_decimals():
    assert decimal.Decimal('1099.98') == numbers.parse_decimal('1,099.98', locale='en_US')
    assert decimal.Decimal('1099.98') == numbers.parse_decimal('1.099,98', locale='de')
    assert decimal.Decimal('1099.98') == numbers.parse_decimal('1,099.98', locale='ar', numbering_system="default")
    assert decimal.Decimal('1099.98') == numbers.parse_decimal('1٬099٫98', locale='ar_EG', numbering_system="default")
    with pytest.raises(numbers.NumberFormatError):
        numbers.parse_decimal('2,109,998', locale='de')
    with pytest.raises(numbers.UnsupportedNumberingSystemError):
        numbers.parse_decimal('2,109,998', locale='de', numbering_system="unknown")


def test_parse_decimal_strict_mode():
    # Numbers with a misplaced grouping symbol should be rejected
    with pytest.raises(numbers.NumberFormatError) as info:
        numbers.parse_decimal('11.11', locale='de', strict=True)
    assert info.value.suggestions == ['1.111', '11,11']
    # Numbers with two misplaced grouping symbols should be rejected
    with pytest.raises(numbers.NumberFormatError) as info:
        numbers.parse_decimal('80.00.00', locale='de', strict=True)
    assert info.value.suggestions == ['800.000']
    # Partially grouped numbers should be rejected
    with pytest.raises(numbers.NumberFormatError) as info:
        numbers.parse_decimal('2000,000', locale='en_US', strict=True)
    assert info.value.suggestions == ['2,000,000', '2,000']
    # Numbers with duplicate grouping symbols should be rejected
    with pytest.raises(numbers.NumberFormatError) as info:
        numbers.parse_decimal('0,,000', locale='en_US', strict=True)
    assert info.value.suggestions == ['0']
    # Return only suggestion for 0 on strict
    with pytest.raises(numbers.NumberFormatError) as info:
        numbers.parse_decimal('0.00', locale='de', strict=True)
    assert info.value.suggestions == ['0']
    # Properly formatted numbers should be accepted
    assert str(numbers.parse_decimal('1.001', locale='de', strict=True)) == '1001'
    # Trailing zeroes should be accepted
    assert str(numbers.parse_decimal('3.00', locale='en_US', strict=True)) == '3.00'
    # Numbers with a grouping symbol and no trailing zeroes should be accepted
    assert str(numbers.parse_decimal('3,400.6', locale='en_US', strict=True)) == '3400.6'
    # Numbers with a grouping symbol and trailing zeroes (not all zeroes after decimal) should be accepted
    assert str(numbers.parse_decimal('3,400.60', locale='en_US', strict=True)) == '3400.60'
    # Numbers with a grouping symbol and trailing zeroes (all zeroes after decimal) should be accepted
    assert str(numbers.parse_decimal('3,400.00', locale='en_US', strict=True)) == '3400.00'
    assert str(numbers.parse_decimal('3,400.0000', locale='en_US', strict=True)) == '3400.0000'
    # Numbers with a grouping symbol and no decimal part should be accepted
    assert str(numbers.parse_decimal('3,800', locale='en_US', strict=True)) == '3800'
    # Numbers without any grouping symbol should be accepted
    assert str(numbers.parse_decimal('2000.1', locale='en_US', strict=True)) == '2000.1'
    # Numbers without any grouping symbol and no decimal should be accepted
    assert str(numbers.parse_decimal('2580', locale='en_US', strict=True)) == '2580'
    # High precision numbers should be accepted
    assert str(numbers.parse_decimal('5,000001', locale='fr', strict=True)) == '5.000001'


def test_parse_decimal_strict_indian_grouping():
    # Indian locales group as 3,2,2,... (e.g. 12,34,567)
    assert numbers.parse_decimal('12,34,567', locale='hi_IN', strict=True) == decimal.Decimal(
        '1234567',
    )
    assert numbers.parse_decimal(
        '1,23,456.789', locale='hi_IN', strict=True,
    ) == decimal.Decimal('123456.789')
    # Western-style grouping is not valid for hi_IN
    with pytest.raises(numbers.NumberFormatError) as info:
        numbers.parse_decimal('1,234,567', locale='hi_IN', strict=True)
    assert info.value.suggestions == ['12,34,567']
    # ... and Indian-style grouping is not valid for en_US
    with pytest.raises(numbers.NumberFormatError):
        numbers.parse_decimal('12,34,567', locale='en_US', strict=True)


def test_parse_decimal_strict_error_position_and_expected():
    with pytest.raises(numbers.NumberFormatError) as info:
        #'1,234,567' has a western grouping, invalid for hi_IN
        numbers.parse_decimal('1,234,567', locale='hi_IN', strict=True)
    assert info.value.position == 2
    assert info.value.expected == '#,##,##0.###'
    with pytest.raises(numbers.NumberFormatError) as info:
        numbers.parse_decimal('1,234abc', locale='en_US', strict=True)
    assert info.value.position == 5
    assert info.value.expected == '#,##0.###'


def test_parse_decimal_strict_rejects_superfluous_groups():
    for string in ('1,2,3,4', '1,23,456', ',123', '123,', '1,,234', '01,234'):
        with pytest.raises(numbers.NumberFormatError):
            numbers.parse_decimal(string, locale='en_US', strict=True)


def test_parse_decimal_strict_rejects_mixed_symbols():
    # ASCII decimal point in a locale that uses the comma
    with pytest.raises(numbers.NumberFormatError):
        numbers.parse_decimal('1,234.5', locale='de', strict=True)
    # ASCII grouping comma in a locale that uses the Arabic-Indic separator
    with pytest.raises(numbers.NumberFormatError):
        numbers.parse_decimal(
            '1,234.5', locale='ar_EG', numbering_system='default', strict=True,
        )
    # Arabic-Indic separators in a Latin locale
    with pytest.raises(numbers.NumberFormatError):
        numbers.parse_decimal('1٬234', locale='en_US', strict=True)
    # A plain space is not the French grouping character (U+202F)
    with pytest.raises(numbers.NumberFormatError):
        numbers.parse_decimal('1 234,5', locale='fr', strict=True)


def test_parse_decimal_strict_rejects_bidi_and_trailing_chars():
    # Arabic-Indic minus sign carries U+061C; U+200E is the wrong bidi mark
    with pytest.raises(numbers.NumberFormatError) as info:
        numbers.parse_decimal(
            '\u200e-1,234', locale='ar_EG', numbering_system='default', strict=True,
        )
    assert info.value.position == 0
    # ... while the correct bidi mark is accepted
    assert numbers.parse_decimal(
        '\u061c-1٬234',
        locale='ar_EG',
        numbering_system='default',
        strict=True,
    ) == decimal.Decimal('-1234')
    # Trailing characters and whitespace are rejected
    for string in ('1,234abc', '1,234 ', ' 1,234'):
        with pytest.raises(numbers.NumberFormatError):
            numbers.parse_decimal(string, locale='en_US', strict=True)


def test_parse_decimal_strict_native_digits():
    # Arabic-Indic digits are mapped before grouping is validated
    assert numbers.parse_decimal(
        '١٬٢٣٤٫٥',
        locale='ar_EG',
        numbering_system='default',
        strict=True,
    ) == decimal.Decimal('1234.5')
    # Devanagari digits with Indian grouping
    assert numbers.parse_decimal(
        '१२,३४,५६७',
        locale='hi_IN',
        numbering_system='deva',
        strict=True,
    ) == decimal.Decimal('1234567')
    # Digits of another numbering system are rejected
    with pytest.raises(numbers.NumberFormatError):
        numbers.parse_decimal('١٢٣', locale='hi_IN', numbering_system='deva', strict=True)
    # Mixing digit systems within one number is rejected
    with pytest.raises(numbers.NumberFormatError):
        numbers.parse_decimal('1٢3', locale='ar_EG', numbering_system='default', strict=True)


def test_parse_decimal_strict_rejects_non_finite_and_currency():
    for string in ('NaN', 'nan', 'Infinity', '-Infinity', '∞', '$1,234.56', '€1.234,56'):
        with pytest.raises(numbers.NumberFormatError):
            numbers.parse_decimal(string, locale='en_US', strict=True)
    # Lenient mode keeps its existing behavior for non-finite values
    assert numbers.parse_decimal('NaN', locale='en_US').is_nan()
    assert numbers.parse_decimal('Infinity', locale='en_US').is_infinite()


def test_parse_decimal_strict_roundtrip():
    values = [
        '0',
        '-1',
        '1234567.89',
        '-1234567.890123456789',
        '0.000001',
        '1000000',
    ]
    for locale in ('en_US', 'de', 'fr', 'ru', 'hi_IN', 'ar_EG', 'ja_JP'):
        for value in values:
            formatted = numbers.format_decimal(
                decimal.Decimal(value),
                locale=locale,
                decimal_quantization=False,
            )
            parsed = numbers.parse_decimal(formatted, locale=locale, strict=True)
            assert parsed == decimal.Decimal(value), (locale, value, formatted)
    # Also round-trip through the locale's default numbering system
    formatted = numbers.format_decimal(
        decimal.Decimal('-1234.5'),
        locale='ar_EG',
        numbering_system='default',
        decimal_quantization=False,
    )
    assert numbers.parse_decimal(
        formatted,
        locale='ar_EG',
        numbering_system='default',
        strict=True,
    ) == decimal.Decimal('-1234.5')
