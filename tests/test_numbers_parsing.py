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


def test_parse_currency_suffix_symbol():
    results = numbers.parse_currency('1.234,50\xa0€', locale='de_DE', currencies={'EUR'})
    assert results == [
        numbers.CurrencyParseResult(decimal.Decimal('1234.50'), 'EUR', 0, 10),
    ]
    # A regular space is accepted in place of the no-break space
    results = numbers.parse_currency('1.234,50 €', locale='de_DE', currencies={'EUR'})
    assert results[0].amount == decimal.Decimal('1234.50')


def test_parse_currency_preserves_fractional_digits():
    # Fractional digits are kept exactly as given; no cash rounding is applied
    (result,) = numbers.parse_currency('€1,234.567', locale='en_US', currencies={'EUR'})
    assert result.amount == decimal.Decimal('1234.567')
    assert result.amount.as_tuple().exponent == -3
    (result,) = numbers.parse_currency('1.234,50 €', locale='de_DE', currencies={'EUR'})
    assert result.amount == decimal.Decimal('1234.50')
    assert str(result.amount) == '1234.50'


def test_parse_currency_accounting_parentheses():
    (result,) = numbers.parse_currency('($1,234.50)', locale='en_US', currencies={'USD'})
    assert result.amount == decimal.Decimal('-1234.50')
    assert result.currency == 'USD'
    assert (result.start, result.end) == (0, 11)
    # Parenthesized amount without a symbol, using an explicit default currency
    (result,) = numbers.parse_currency('(1,234.50)', locale='en_US', default_currency='USD')
    assert result.amount == decimal.Decimal('-1234.50')
    assert (result.start, result.end) == (0, 10)


def test_parse_currency_minus_sign():
    (result,) = numbers.parse_currency('-$1,234.50', locale='en_US', currencies={'USD'})
    assert result.amount == decimal.Decimal('-1234.50')
    (result,) = numbers.parse_currency('-1.234,50 €', locale='de_DE', currencies={'EUR'})
    assert result.amount == decimal.Decimal('-1234.50')


def test_parse_currency_ambiguous_symbol_depends_on_allowed_set():
    string = '$1,234.50'
    # The same symbol yields different results depending on the allowed set;
    # USD is never picked arbitrarily when several currencies match.
    assert [r.currency for r in numbers.parse_currency(string, locale='en_US', currencies={'USD'})] == ['USD']  # fmt: skip
    assert [r.currency for r in numbers.parse_currency(string, locale='en_US', currencies={'CAD'})] == ['CAD']  # fmt: skip
    results = numbers.parse_currency(string, locale='en_US', currencies={'USD', 'CAD'})
    assert {r.currency for r in results} == {'USD', 'CAD'}
    assert {r.amount for r in results} == {decimal.Decimal('1234.50')}
    # None of the allowed currencies is denoted by the symbol
    with pytest.raises(numbers.NumberFormatError):
        numbers.parse_currency(string, locale='en_US', currencies={'EUR'})


def test_parse_currency_iso_code_marker():
    (result,) = numbers.parse_currency('USD 1,234.50', locale='en_US', currencies={'USD'})
    assert result.amount == decimal.Decimal('1234.50')
    (result,) = numbers.parse_currency('1,234.50 USD', locale='en_US', currencies={'USD'})
    assert result.amount == decimal.Decimal('1234.50')
    # ISO codes should not match inside words
    with pytest.raises(numbers.NumberFormatError):
        numbers.parse_currency('TOTALLY 5.00', locale='en_US', currencies={'ALL'})


def test_parse_currency_default_currency():
    (result,) = numbers.parse_currency('1,234.50', locale='en_US', default_currency='USD')
    assert result.amount == decimal.Decimal('1234.50')
    assert result.currency == 'USD'
    # Without a marker and without a default currency, parsing fails
    with pytest.raises(numbers.NumberFormatError):
        numbers.parse_currency('1,234.50', locale='en_US')
    # A default currency is only used when no marker is present
    (result,) = numbers.parse_currency('€1,234.50', locale='en_US', currencies={'EUR'}, default_currency='USD')  # fmt: skip
    assert result.currency == 'EUR'


def test_parse_currency_unknown_currency():
    with pytest.raises(numbers.UnknownCurrencyError):
        numbers.parse_currency('$1.00', locale='en_US', currencies={'ZZZ'})
    with pytest.raises(numbers.UnknownCurrencyError):
        numbers.parse_currency('1.00', locale='en_US', default_currency='ZZZ')


def test_parse_currency_strict_mode_rejects_misaligned_grouping():
    with pytest.raises(numbers.NumberFormatError):
        numbers.parse_currency('$1,23,456.00', locale='en_US', currencies={'USD'}, strict=True)
    # Properly grouped amounts are accepted
    (result,) = numbers.parse_currency('$1,234,456.00', locale='en_US', currencies={'USD'}, strict=True)  # fmt: skip
    assert result.amount == decimal.Decimal('1234456.00')


def test_parse_currency_lenient_mode_keeps_both_interpretations():
    # A misplaced grouping symbol allows two different amount readings;
    # lenient mode must not collapse them into a single value.
    results = numbers.parse_currency('$12,34', locale='en_US', currencies={'USD'})
    assert [r.amount for r in results] == [decimal.Decimal('1234'), decimal.Decimal('12.34')]
    # Properly grouped input yields a single candidate
    results = numbers.parse_currency('$1,234.50', locale='en_US', currencies={'USD'})
    assert [r.amount for r in results] == [decimal.Decimal('1234.50')]


def test_parse_currency_consumed_span_leaves_trailing_text():
    string = '1.234,50\xa0€ zzgl. MwSt.'
    (result,) = numbers.parse_currency(string, locale='de_DE', currencies={'EUR'})
    assert string[result.start:result.end] == '1.234,50\xa0€'
    assert string[result.end:] == ' zzgl. MwSt.'
    # Leading text is outside the consumed span as well
    string = 'Preis: 1.234,50\xa0€'
    (result,) = numbers.parse_currency(string, locale='de_DE', currencies={'EUR'})
    assert string[result.start:result.end] == '1.234,50\xa0€'
    assert string[:result.start] == 'Preis: '


def test_parse_currency_numbering_system():
    string = numbers.format_currency(1234.5, 'EGP', locale='ar_EG', numbering_system='default')
    (result,) = numbers.parse_currency(string, locale='ar_EG', currencies={'EGP'}, numbering_system='default')  # fmt: skip
    assert result.amount == decimal.Decimal('1234.50')
    assert result.currency == 'EGP'


@pytest.mark.parametrize(('locale', 'currency', 'amount'), [
    ('en_US', 'USD', '1234.50'),
    ('de_DE', 'EUR', '1234.50'),
    ('fr_FR', 'EUR', '12345.50'),
    ('en_US', 'JPY', '1234'),
    ('sv_SE', 'SEK', '1234.50'),
])
def test_parse_currency_format_roundtrip(locale, currency, amount):
    value = decimal.Decimal(amount)
    string = numbers.format_currency(value, currency, locale=locale)
    results = numbers.parse_currency(string, locale=locale, currencies={currency})
    assert len(results) == 1
    assert results[0].amount == value
    assert results[0].currency == currency
    assert string[results[0].start:results[0].end] == string
