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
from babel.numbers import CurrencyParseResult


def test_can_parse_decimals():
    v = decimal.Decimal('1099.98')
    assert numbers.parse_decimal('1,099.98', locale='en_US') == v
    assert numbers.parse_decimal('1.099,98', locale='de') == v
    assert numbers.parse_decimal('1,099.98', locale='ar', numbering_system="default") == v  # fmt: skip
    assert numbers.parse_decimal('1٬099٫98', locale='ar_EG', numbering_system="default") == v  # fmt: skip
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


def test_parse_currency_basic():
    # Symbol position follows the locale's currency pattern.
    assert numbers.parse_currency('1.234,50 \u20ac', locale='de', currencies={'EUR'}) == [
        CurrencyParseResult(decimal.Decimal('1234.50'), 'EUR', 0, 10),
    ]
    assert numbers.parse_currency('$1,234.50', locale='en_US', currencies={'USD'}) == [
        CurrencyParseResult(decimal.Decimal('1234.50'), 'USD', 0, 9),
    ]
    # Accounting parentheses denote a negative amount.
    assert numbers.parse_currency('($1,234.50)', locale='en_US', currencies={'USD'}) == [
        CurrencyParseResult(decimal.Decimal('-1234.50'), 'USD', 0, 11),
    ]
    # An explicit minus sign is honored as well.
    assert numbers.parse_currency('-$1,234.50', locale='en_US', currencies={'USD'}) == [
        CurrencyParseResult(decimal.Decimal('-1234.50'), 'USD', 0, 10),
    ]
    # The ISO code marker is supported in both positions.
    assert numbers.parse_currency('USD 1,234.50', locale='en_US', currencies={'USD'}) == [
        CurrencyParseResult(decimal.Decimal('1234.50'), 'USD', 0, 12),
    ]
    assert numbers.parse_currency('1.234,50 EUR', locale='de', currencies={'EUR'}) == [
        CurrencyParseResult(decimal.Decimal('1234.50'), 'EUR', 0, 12),
    ]


def test_parse_currency_no_marker_uses_default_currency():
    # A number without any currency marker requires an explicit default.
    with pytest.raises(numbers.NumberFormatError):
        numbers.parse_currency('1,234.50', locale='en_US')
    # Accounting negatives work with the default currency too.
    assert numbers.parse_currency(
        '(1,234.50)',
        locale='en_US',
        default_currency='USD',
    ) == [CurrencyParseResult(decimal.Decimal('-1234.50'), 'USD', 0, 10)]
    assert numbers.parse_currency(
        '1,234.50',
        locale='en_US',
        default_currency='EUR',
    ) == [CurrencyParseResult(decimal.Decimal('1234.50'), 'EUR', 0, 8)]
    # A marker that belongs to a currency outside the allowed set cannot be
    # overridden by the default currency.
    with pytest.raises(numbers.NumberFormatError):
        numbers.parse_currency(
            '1.234,50 \u20ac',
            locale='de',
            currencies={'USD'},
            default_currency='USD',
        )


def test_parse_currency_ambiguous_symbol():
    # The same symbol yields different results depending on the allowed set.
    assert [
        r.currency for r in numbers.parse_currency('$1.00', locale='en_US', currencies={'USD'})
    ] == ['USD']
    assert [
        r.currency for r in numbers.parse_currency('$1.00', locale='en_US', currencies={'CAD'})
    ] == ['CAD']
    results = numbers.parse_currency(
        '$1.00',
        locale='en_US',
        currencies={'USD', 'CAD', 'AUD'},
    )
    assert [r.currency for r in results] == ['AUD', 'CAD', 'USD']
    assert all(r.amount == decimal.Decimal('1.00') for r in results)
    # Other shared symbols work the same ("\u00a5" is JPY in en, CNY in zh).
    results = numbers.parse_currency('\u00a51,234', locale='en_US', currencies={'JPY', 'CNY'})
    assert [r.currency for r in results] == ['CNY', 'JPY']
    # Disambiguating markers are matched precisely.
    assert [
        r.currency
        for r in numbers.parse_currency('CA$1.00', locale='en_US', currencies={'USD', 'CAD'})
    ] == ['CAD']


def test_parse_currency_preserves_decimal_fraction():
    # No cash rounding or quantization happens; the fraction is kept as written.
    result = numbers.parse_currency('$1.005', locale='en_US', currencies={'USD'})[0]
    assert result.amount == decimal.Decimal('1.005')
    assert str(result.amount) == '1.005'
    result = numbers.parse_currency('$3,400.0000', locale='en_US', currencies={'USD'})[0]
    assert str(result.amount) == '3400.0000'
    # Trailing zeroes of the amount are preserved.
    result = numbers.parse_currency('1.234,50 \u20ac', locale='de', currencies={'EUR'})[0]
    assert str(result.amount) == '1234.50'


def test_parse_currency_consumed_span():
    text = '1.234,50 \u20ac und weiter'
    result = numbers.parse_currency(text, locale='de', currencies={'EUR'})[0]
    assert (result.start, result.end) == (0, 10)
    # Unrelated trailing text is left for the caller.
    assert text[result.start : result.end] == '1.234,50 \u20ac'
    assert text[result.end :] == ' und weiter'
    # Leading whitespace is skipped; the span starts at the amount.
    result = numbers.parse_currency('  $1.00', locale='en_US', currencies={'USD'})[0]
    assert (result.start, result.end) == (2, 7)


def test_parse_currency_nbsp_and_spaces():
    # The German pattern separates the number from the symbol with NBSP,
    # but a regular space is accepted as well.
    expected = [CurrencyParseResult(decimal.Decimal('1234.50'), 'EUR', 0, 10)]
    assert (
        numbers.parse_currency('1.234,50\u00a0\u20ac', locale='de', currencies={'EUR'})
        == expected
    )
    assert (
        numbers.parse_currency('1.234,50 \u20ac', locale='de', currencies={'EUR'}) == expected
    )
    # In French, the narrow NBSP is the grouping symbol; a regular space works.
    result = numbers.parse_currency('1 234,56\u00a0\u20ac', locale='fr', currencies={'EUR'})
    assert result == [CurrencyParseResult(decimal.Decimal('1234.56'), 'EUR', 0, 10)]


def test_parse_currency_numbering_system():
    # Arabic-Indic digits with the locale's default numbering system.
    result = numbers.parse_currency(
        '\u200f1\u066c099\u066b98\u00a0\u062c.\u0645.\u200f',
        locale='ar_EG',
        currencies={'EGP'},
        numbering_system='default',
    )
    assert result == [CurrencyParseResult(decimal.Decimal('1099.98'), 'EGP', 0, 15)]


def test_parse_currency_strict_mode():
    # Strict mode rejects misplaced grouping symbols.
    with pytest.raises(numbers.NumberFormatError) as info:
        numbers.parse_currency('$12,34', locale='en_US', currencies={'USD'}, strict=True)
    assert info.value.suggestions == ['1,234', '12.34']
    # Lenient mode must not collapse the two plausible amounts into one.
    results = numbers.parse_currency('$12,34', locale='en_US', currencies={'USD'})
    assert [r.amount for r in results] == [decimal.Decimal('1234'), decimal.Decimal('12.34')]
    assert all(r.currency == 'USD' for r in results)
    # Properly grouped numbers stay unambiguous.
    results = numbers.parse_currency('$1,234.50', locale='en_US', currencies={'USD'})
    assert [r.amount for r in results] == [decimal.Decimal('1234.50')]


def test_parse_currency_rejects_unknown_currency_and_garbage():
    with pytest.raises(numbers.UnknownCurrencyError):
        numbers.parse_currency('$1.00', locale='en_US', currencies={'ZZZ'})
    with pytest.raises(numbers.UnknownCurrencyError):
        numbers.parse_currency('1.00', locale='en_US', default_currency='ZZZ')
    with pytest.raises(numbers.NumberFormatError):
        numbers.parse_currency('no number here', locale='en_US', currencies={'USD'})
