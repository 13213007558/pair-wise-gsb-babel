#
# Copyright test_plural_check.py
#
# Tests for the safe Plural-Forms parser and checker.

import pytest

from babel.messages import plural_check
from babel.messages.catalog import Catalog
from babel.messages.plural_check import (
    DIVISION_BY_ZERO,
    NEGATIVE_RESULT,
    RESULT_OUT_OF_RANGE,
    SYNTAX,
    UNKNOWN,
    UNREACHABLE_FORM,
    PluralSyntaxError,
    check_plural_expression,
    check_plural_forms,
    evaluate,
    parse_plural_expression,
)


def test_parse_simple_expression():
    tree = parse_plural_expression('(n != 1)')
    assert evaluate(tree, 1) == 0
    assert evaluate(tree, 2) == 1


def test_parse_ternary_and_logic():
    tree = parse_plural_expression('n == 1 ? 0 : n >= 2 && n <= 4 ? 1 : 2')
    assert [evaluate(tree, n) for n in range(7)] == [2, 0, 1, 1, 1, 2, 2]


def test_c_semantics_division_and_modulo():
    # C truncates toward zero and the remainder takes the dividend's sign.
    assert evaluate(parse_plural_expression('(0 - 7) / 2'), 0) == -3
    assert evaluate(parse_plural_expression('(0 - 7) % 3'), 0) == -1


def test_short_circuit_avoids_division_by_zero():
    tree = parse_plural_expression('n == 0 ? 0 : 10 / n')
    assert evaluate(tree, 0) == 0
    assert evaluate(parse_plural_expression('n != 0 && 10 / n > 1'), 0) == 0


@pytest.mark.parametrize('source', [
    '(n !',
    'n ? 1',
    'n +',
    'm != 1',
    'n != 1 garbage',
    "__import__('os')",
    'n; plural=0',
])
def test_syntax_errors(source):
    report = check_plural_expression(source, 2)
    assert report.status == 'syntax_error'
    assert report.issues_of(SYNTAX)
    with pytest.raises(PluralSyntaxError):
        parse_plural_expression(source)


def test_safe_formula_is_ok():
    report = check_plural_expression('(n != 1)', 2)
    assert report.ok
    assert report.status == 'ok'
    assert report.values == frozenset({0, 1})


def test_russian_formula_is_ok():
    report = check_plural_expression(
        'n % 10 == 1 && n % 100 != 11 ? 0 : '
        'n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 12 || n % 100 > 14) ? 1 : 2',
        3,
    )
    assert report.ok
    assert report.values == frozenset({0, 1, 2})


def test_division_by_zero_only_at_1000():
    # The error is only reachable for n == 1000 (mod 1001); sampling
    # n in 0..100 would declare this formula safe.
    report = check_plural_expression(
        'n % 1001 == 1000 ? 10 / (n % 1001 - 1000) : (n != 1)',
        2,
    )
    assert report.status == 'error'
    (issue,) = report.issues
    assert issue.kind == DIVISION_BY_ZERO
    assert issue.n == 1000
    assert 'n=1000' in issue.message


def test_out_of_range_only_at_1000():
    report = check_plural_expression('n % 1001 == 1000 ? 5 : (n != 1)', 2)
    assert report.status == 'error'
    (issue,) = report.issues
    assert issue.kind == RESULT_OUT_OF_RANGE
    assert issue.n == 1000


def test_dead_branch_is_reported():
    report = check_plural_expression('(n == 1 ? 0 : 1)', 3)
    assert report.status == 'error'
    (issue,) = report.issues
    assert issue.kind == UNREACHABLE_FORM
    assert 'plural form 2' in issue.message


def test_negative_result_is_reported():
    report = check_plural_expression('n % 3 - 1', 2)
    assert report.status == 'error'
    issue = report.issues_of(NEGATIVE_RESULT)[0]
    assert issue.n == 0


def test_out_of_range_result_is_reported():
    report = check_plural_expression('n % 5', 2)
    assert report.status == 'error'
    issue = report.issues_of(RESULT_OUT_OF_RANGE)[0]
    assert issue.n == 2


def test_unprovable_formula_is_unknown_not_safe():
    report = check_plural_expression('n * n % 2', 2)
    assert report.status == 'unknown'
    assert report.issues_of(UNKNOWN)
    assert not report.ok


def test_oversized_period_is_unknown():
    report = check_plural_expression('n % 1000000 == 999999 ? 1 : 0', 2, max_period=1000)
    assert report.status == 'unknown'


def test_affine_root_is_exact():
    # n itself grows past nplurals; the witness is computed analytically.
    report = check_plural_expression('n', 2)
    assert report.status == 'error'
    issue = report.issues_of(RESULT_OUT_OF_RANGE)[0]
    assert issue.n == 2


def test_affine_divisor_zero_is_found():
    report = check_plural_expression('n == 5 ? 10 / (n - 5) : 0', 1)
    assert report.status == 'error'
    issue = report.issues_of(DIVISION_BY_ZERO)[0]
    assert issue.n == 5


def test_check_plural_forms_header():
    report = check_plural_forms('nplurals=2; plural=(n != 1);')
    assert report.ok
    assert report.expression == '(n != 1)'
    assert report.nplurals == 2


def test_check_plural_forms_header_problems():
    assert check_plural_forms('nplurals=2; plural=(n == 1 ? 0 : 1);').ok
    report = check_plural_forms('nplurals=3; plural=(n == 1 ? 0 : 1);')
    assert report.issues_of(UNREACHABLE_FORM)
    assert check_plural_forms('plural=(n != 1);').status == 'syntax_error'
    assert check_plural_forms('nplurals=2;').status == 'syntax_error'


@pytest.mark.parametrize('locale', ['en', 'ru', 'ar', 'ja', 'cs', 'fr'])
def test_builtin_locale_formulas_are_safe(locale):
    catalog = Catalog(locale=locale)
    report = catalog.check_plural_forms()
    assert report.ok, str(report)


def test_catalog_check_keeps_original_expression():
    catalog = Catalog()
    catalog.mime_headers = [
        ('Plural-Forms', 'nplurals=3; plural=(n == 1 ? 0 : 1);'),
    ]
    report = catalog.check_plural_forms()
    # The original formula text is preserved verbatim on the catalog
    # and echoed back in the report.
    assert catalog.plural_expr == '(n == 1 ? 0 : 1)'
    assert catalog.num_plurals == 3
    assert report.expression == '(n == 1 ? 0 : 1)'
    assert report.issues_of(UNREACHABLE_FORM)


def test_catalog_check_plural_forms_does_not_mutate_catalog():
    catalog = Catalog(locale='en')
    before = catalog.plural_forms
    catalog.check_plural_forms()
    assert catalog.plural_forms == before


def test_no_python_eval_is_used():
    # The checker must never evaluate the formula with Python's eval/exec.
    import inspect

    source = inspect.getsource(plural_check)
    assert 'eval(' not in source.replace('evaluate(', '').replace('_eval', '')
    assert 'exec(' not in source
