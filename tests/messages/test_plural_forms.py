from io import StringIO

import pytest

from babel.messages import catalog, pofile
from babel.messages.plural_forms import (
    PluralFormsSyntaxError,
    check_plural_forms,
    evaluate_plural_expression,
    parse_plural_expression,
)


def test_safe_formula_has_period_and_threshold():
    result = check_plural_forms(
        "nplurals=3; plural=(n == 0 || n == 1) ? 0 "
        ": n != 0 && n % 1000000 == 0 ? 1 : 2;",
    )
    assert result.status == "safe"
    assert result.reachable_indices == (0, 1, 2)
    assert result.period == 1000000
    assert result.threshold == 2


def test_modulo_formula_reports_out_of_range_witness():
    result = check_plural_forms("nplurals=10; plural=n % 11;")
    assert result.status == "invalid_result"
    issue = next(issue for issue in result.issues if issue.code == "index_out_of_range")
    assert issue.witness == 10


def test_negative_result_witness():
    result = check_plural_forms("nplurals=2; plural=n == 0 ? -1 : 1;")
    assert result.status == "invalid_result"
    issue = next(issue for issue in result.issues if issue.code == "negative_result")
    assert issue.witness == 0


def test_division_by_zero_only_at_declared_witness():
    formula = "nplurals=2; plural=n == 1000 ? 1 / 0 : 0;"
    result = check_plural_forms(formula)
    assert result.status == "division_by_zero"
    assert len(result.issues) == 1
    assert result.issues[0].code == "division_by_zero"
    assert result.issues[0].witness == 1000


def test_guarded_impossible_division_is_not_reported():
    result = check_plural_forms("nplurals=1; plural=n == 1 ? 0 / (n == 2 ? 0 : 1) : 0;")
    assert result.status == "safe"
    assert result.reachable_indices == (0,)


def test_dead_plural_branch_reports_missing_index():
    result = check_plural_forms(
        "nplurals=3; plural=n == 1 ? 0 : n == 2 ? 0 : 2;",
    )
    assert result.status == "unreachable_plural"
    assert result.reachable_indices == (0, 2)
    assert len(result.issues) == 1
    assert result.issues[0].code == "unreachable_plural"
    assert result.issues[0].index == 1


@pytest.mark.parametrize("formula", [
    "n == 1 ? 0",
    "foo",
    "n /",
    "n @ 1",
])
def test_syntax_errors(formula):
    with pytest.raises(PluralFormsSyntaxError):
        parse_plural_expression(formula)
    result = check_plural_forms(f"nplurals=2; plural={formula};")
    assert result.status == "syntax_error"
    assert result.issues[0].code == "syntax_error"


def test_unsupported_nonlinear_formula_is_unknown():
    result = check_plural_forms("nplurals=3; plural=n * n;")
    assert result.status == "unknown"
    assert result.issues == ()


def test_safe_evaluator_does_not_use_python_evaluation():
    ast = parse_plural_expression("n == 1000 ? 1 / 0 : 1 / (n - 1000)")
    assert evaluate_plural_expression(ast, 1001) == 1


def test_catalog_check_reports_real_witnesses():
    cat = catalog.Catalog(plural_forms="nplurals=2; plural=n == 1000 ? 1 / 0 : 0;")
    result = cat.check_plural_forms()
    assert result.issues[0].witness == 1000
    checks = list(cat.check(plural_forms=True))
    assert len(checks) == 1
    assert checks[0][0].id == ""
    assert [str(error) for error in checks[0][1]] == ["division by zero is reachable"]


def test_catalog_retains_exact_formula_text():
    raw = "nplurals=3; plural=n == 1 ? 0 : n == 2 ? 0 : 2;"
    cat = catalog.Catalog(plural_forms=raw)
    assert cat.plural_forms == raw
    assert cat.check_plural_forms().expression == "n == 1 ? 0 : n == 2 ? 0 : 2"


def test_po_header_roundtrip_preserves_formula_text():
    raw = "nplurals=3; plural=n == 1 ? 0 : n == 2 ? 0 : 2;"
    stream = StringIO(
        f'msgid ""\nmsgstr ""\n"Plural-Forms: {raw}\\n"\n\nmsgid "one"\nmsgid_plural "many"\n'
        'msgstr[0] ""\nmsgstr[1] ""\nmsgstr[2] ""\n',
    )
    cat = pofile.read_po(stream)
    assert cat.plural_forms == raw
    result = cat.check_plural_forms()
    assert result.status == "unreachable_plural"
    assert result.issues[0].index == 1


def test_built_in_finite_proof_does_not_guess_from_small_sample():
    result = check_plural_forms(
        "nplurals=2; plural=(n >= 0 && n <= 100) ? 0 : 1;",
    )
    assert result.status == "safe"
    assert result.reachable_indices == (0, 1)
    assert result.threshold >= 100
