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

from babel import Locale, UnknownLocaleError, localedata, plural

EPSILON = decimal.Decimal("0.0001")


def test_plural_rule():
    rule = plural.PluralRule({'one': 'n is 1'})
    assert rule(1) == 'one'
    assert rule(2) == 'other'

    rule = plural.PluralRule({'one': 'n is 1'})
    assert rule.rules == {'one': 'n is 1'}


def test_plural_rule_operands_i():
    rule = plural.PluralRule({'one': 'i is 1'})
    assert rule(1.2) == 'one'
    assert rule(2) == 'other'


def test_plural_rule_operands_v():
    rule = plural.PluralRule({'one': 'v is 2'})
    assert rule(decimal.Decimal('1.20')) == 'one'
    assert rule(decimal.Decimal('1.2')) == 'other'
    assert rule(2) == 'other'


def test_plural_rule_operands_w():
    rule = plural.PluralRule({'one': 'w is 2'})
    assert rule(decimal.Decimal('1.23')) == 'one'
    assert rule(decimal.Decimal('1.20')) == 'other'
    assert rule(1.2) == 'other'


def test_plural_rule_operands_f():
    rule = plural.PluralRule({'one': 'f is 20'})
    assert rule(decimal.Decimal('1.23')) == 'other'
    assert rule(decimal.Decimal('1.20')) == 'one'
    assert rule(1.2) == 'other'


def test_plural_rule_operands_t():
    rule = plural.PluralRule({'one': 't = 5'})
    assert rule(decimal.Decimal('1.53')) == 'other'
    assert rule(decimal.Decimal('1.50')) == 'one'
    assert rule(1.5) == 'one'


def test_plural_other_is_ignored():
    rule = plural.PluralRule({'one': 'n is 1', 'other': '@integer 2'})
    assert rule(1) == 'one'


def test_to_javascript():
    src = plural.to_javascript({'one': 'n is 1'})
    assert src == "(function(n) { return (n == 1) ? 'one' : 'other'; })"


def test_to_python():
    func = plural.to_python({'one': 'n is 1', 'few': 'n in 2..4'})
    assert func(1) == 'one'
    assert func(3) == 'few'

    func = plural.to_python({'one': 'n in 1,11', 'few': 'n in 3..10,13..19'})
    assert func(11) == 'one'
    assert func(15) == 'few'


def test_to_gettext():
    src = plural.to_gettext({'one': 'n is 1', 'two': 'n is 2'})
    assert src == 'nplurals=3; plural=((n == 1) ? 0 : (n == 2) ? 1 : 2);'


def test_in_range_list():
    assert plural.in_range_list(1, [(1, 3)])
    assert plural.in_range_list(3, [(1, 3)])
    assert plural.in_range_list(3, [(1, 3), (5, 8)])
    assert not plural.in_range_list(1.2, [(1, 4)])
    assert not plural.in_range_list(10, [(1, 4)])
    assert not plural.in_range_list(10, [(1, 4), (6, 8)])


def test_within_range_list():
    assert plural.within_range_list(1, [(1, 3)])
    assert plural.within_range_list(1.0, [(1, 3)])
    assert plural.within_range_list(1.2, [(1, 4)])
    assert plural.within_range_list(8.8, [(1, 4), (7, 15)])
    assert not plural.within_range_list(10, [(1, 4)])
    assert not plural.within_range_list(10.5, [(1, 4), (20, 30)])


def test_cldr_modulo():
    assert plural.cldr_modulo(-3, 5) == -3
    assert plural.cldr_modulo(-3, -5) == -3
    assert plural.cldr_modulo(3, 5) == 3


def test_plural_within_rules():
    p = plural.PluralRule({'one': 'n is 1', 'few': 'n within 2,4,7..9'})
    assert repr(p) == "<PluralRule 'one: n is 1, few: n within 2,4,7..9'>"
    assert plural.to_javascript(p) == (
        "(function(n) { "
        "return ((n == 2) || (n == 4) || (n >= 7 && n <= 9))"
        " ? 'few' : (n == 1) ? 'one' : 'other'; })"
    )
    assert plural.to_gettext(p) == (
        'nplurals=3; plural=(((n == 2) || (n == 4) || (n >= 7 && n <= 9))'
        ' ? 1 : (n == 1) ? 0 : 2);'
    )
    assert p(0) == 'other'
    assert p(1) == 'one'
    assert p(2) == 'few'
    assert p(3) == 'other'
    assert p(4) == 'few'
    assert p(5) == 'other'
    assert p(6) == 'other'
    assert p(7) == 'few'
    assert p(8) == 'few'
    assert p(9) == 'few'


def test_locales_with_no_plural_rules_have_default():
    pf = Locale.parse('ii').plural_form
    assert pf(1) == 'other'
    assert pf(2) == 'other'
    assert pf(15) == 'other'


def test_plural_range_rule_wildcards_and_default():
    rule = plural.PluralRangeRule({'one': {None: 'other'}, None: {'one': 'one'}})
    assert rule('one', 'few') == 'other'
    assert rule('many', 'one') == 'one'
    assert rule('many', 'few') == 'other'


def test_locale_plural_range_uses_both_endpoints():
    assert Locale.parse('ka').plural_range_category(2, 1) == 'other'
    assert Locale.parse('ka').plural_range_category(1, 2) == 'one'
    assert Locale.parse('sl').plural_range_category(1, 1) == 'few'
    assert Locale.parse('ru').plural_range_category(1, 5) == 'many'


def test_locale_plural_range_parent_fallback_and_missing_rule_default():
    assert Locale.parse('en_US').plural_range_category(2, 1) == 'other'
    assert Locale.parse('en_US').plural_range_category(1, 1) == 'other'
    assert Locale.parse('ii').plural_range_category(1, 2) == 'other'


def test_locale_plural_range_keeps_endpoint_order_and_decimal_precision():
    locale = Locale.parse('lv')
    assert Locale.parse('cs').plural_range_category(decimal.Decimal('1'), 2) == 'few'
    assert Locale.parse('cs').plural_range_category(decimal.Decimal('1.0'), 2) == 'few'
    assert locale.plural_range_category(
        decimal.Decimal('0.10'),
        decimal.Decimal('0.1'),
    ) == 'one'
    assert Locale.parse('ka').plural_range_category(2, 1) == 'other'
    assert Locale.parse('ka').plural_range_category(1, 2) == 'one'


def test_format_plural_range():
    messages = {'other': '{0}–{1} days'}
    assert plural.format_plural_range(2, 1, messages, locale='ka') == '2–1 days'


def test_format_plural_range_keeps_decimal_precision():
    messages = {'one': '{0}–{1} days'}
    assert plural.format_plural_range(
        decimal.Decimal('0.10'),
        decimal.Decimal('0.1'),
        messages,
        locale='lv',
    ) == '0.10–0.1 days'


def test_format_plural_range_missing_message():
    with pytest.raises(KeyError, match="'one'"):
        plural.format_plural_range(1, 2, {'other': '{0}–{1}'}, locale='ka')


def test_format_plural_range_unknown_locale():
    with pytest.raises(UnknownLocaleError):
        plural.format_plural_range(1, 2, {}, locale='xx_YY')


WELL_FORMED_TOKEN_TESTS = (
    ("", []),
    (
        "n = 1",
        [
            ("value", "1"),
            ("symbol", "="),
            ("word", "n"),
        ],
    ),
    (
        "n = 1 @integer 1",
        [
            ("value", "1"),
            ("symbol", "="),
            ("word", "n"),
        ],
    ),
    (
        "n is 1",
        [
            ("value", "1"),
            ("word", "is"),
            ("word", "n"),
        ],
    ),
    (
        "n % 100 = 3..10",
        [
            ("value", "10"),
            ("ellipsis", ".."),
            ("value", "3"),
            ("symbol", "="),
            ("value", "100"),
            ("symbol", "%"),
            ("word", "n"),
        ],
    ),
)


@pytest.mark.parametrize(("rule_text", "tokens"), WELL_FORMED_TOKEN_TESTS)
def test_tokenize_well_formed(rule_text, tokens):
    assert plural.tokenize_rule(rule_text) == tokens


@pytest.mark.parametrize('rule_text', ['a = 1', 'n ! 2'])
def test_tokenize_malformed(rule_text):
    with pytest.raises(plural.RuleError):
        plural.tokenize_rule(rule_text)


def test_next_token_empty():
    assert not plural.test_next_token([], '')


def test_next_token_type_ok_and_no_value():
    assert plural.test_next_token([('word', 'and')], 'word')


def test_next_token_type_ok_and_not_value():
    assert not plural.test_next_token([('word', 'and')], 'word', 'or')


def test_next_token_type_ok_and_value_ok():
    assert plural.test_next_token([('word', 'and')], 'word', 'and')


def test_next_token_type_not_ok_and_value_ok():
    assert not plural.test_next_token([('abc', 'and')], 'word', 'and')


EXTRACT_OPERANDS_TESTS = (
    (1, 1, 1, 0, 0, 0, 0),
    (decimal.Decimal('1.0'), '1.0', 1, 1, 0, 0, 0),
    (decimal.Decimal('1.00'), '1.00', 1, 2, 0, 0, 0),
    (decimal.Decimal('1.3'), '1.3', 1, 1, 1, 3, 3),
    (decimal.Decimal('1.30'), '1.30', 1, 2, 1, 30, 3),
    (decimal.Decimal('1.03'), '1.03', 1, 2, 2, 3, 3),
    (decimal.Decimal('1.230'), '1.230', 1, 3, 2, 230, 23),
    (-1, 1, 1, 0, 0, 0, 0),
    (1.3, '1.3', 1, 1, 1, 3, 3),
)


@pytest.mark.parametrize(("source", "n", "i", "v", "w", "f", "t"), EXTRACT_OPERANDS_TESTS)
def test_extract_operands(source, n, i, v, w, f, t):
    e_n, e_i, e_v, e_w, e_f, e_t, e_c, e_e = plural.extract_operands(source)
    assert abs(e_n - decimal.Decimal(n)) <= EPSILON  # float-decimal conversion inaccuracy
    assert e_i == i
    assert e_v == v
    assert e_w == w
    assert e_f == f
    assert e_t == t
    assert not e_c  # Not supported at present
    assert not e_e  # Not supported at present


@pytest.mark.parametrize('locale', ['ru', 'pl'])
def test_gettext_compilation(locale):
    # Test that new plural form elements introduced in recent CLDR versions
    # are compiled "down" to `n` when emitting Gettext rules.
    ru_rules = localedata.load(locale)['plural_form'].rules
    chars = 'ivwft'
    # Test that these rules are valid for this test; i.e. that they contain at least one
    # of the gettext-unsupported characters.
    assert any(f" {ch} " in rule for ch in chars for rule in ru_rules.values())
    # Then test that the generated value indeed does not contain these.
    ru_rules_gettext = plural.to_gettext(ru_rules)
    assert not any(ch in ru_rules_gettext for ch in chars)
