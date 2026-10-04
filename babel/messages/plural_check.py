"""
babel.messages.plural_check
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Safe parsing and validation of the ``plural`` expression of a gettext
``Plural-Forms`` header.  The expression is parsed into an AST (Python's
:func:`eval` is never used) and then checked for reachable errors.

The supported language is the C-like subset used by gettext plural
formulas:

- integer constants and the variable ``n``;
- ``+``, unary ``+``/``-``/``!``, ``*``, ``/`` and ``%``;
- the comparison operators ``==``, ``!=``, ``<``, ``<=``, ``>``, ``>=``;
- the logical operators ``&&`` and ``||`` (short-circuiting);
- the conditional operator ``? :`` and parentheses.

Division and modulo use C semantics (truncation toward zero).

For formulas in the common provable subset -- conditions made of constant
comparisons and constant-modulo terms -- every sub-expression is proven to
be *eventually periodic*:  there exist a threshold ``T`` and a period ``P``
such that the value at ``n`` equals the value at ``n + P`` for every
``n >= T``.  Bounds of the sub-expression plus the thresholds of constant
comparisons (for example ``n >= 2`` becomes constant past ``n == 2``) give
``T`` and ``P``; exhaustive evaluation on ``range(T + P)`` therefore yields
complete conclusions (with a concrete witness ``n`` for every problem).
This is *not* a bounded try of ``0`` .. ``100``.

Formulas outside the provable subset (for example ones involving ``n * n``
or division by an expression in ``n``) produce an ``unknown`` result
instead of a possibly false safety claim.

:copyright: (c) 2026 by the Babel Team.
:license: BSD, see LICENSE for more details.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from math import gcd
from typing import ClassVar, Union


class PluralSyntaxError(ValueError):
    """Raised when a plural expression cannot be parsed."""


# AST nodes are plain tuples:
#   ('num', value)
#   ('var',)
#   ('un', op, operand)
#   ('bin', op, left, right)
#   ('cond', condition, when_true, when_false)

_MULTI_CHAR_OPS = ('==', '!=', '<=', '>=', '&&', '||')
_SINGLE_CHAR_OPS = set('+-*/%<>!?:()')


def _tokenize(source: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    pos = 0
    length = len(source)
    while pos < length:
        char = source[pos]
        if char.isspace():
            pos += 1
            continue
        if char.isdigit():
            end = pos + 1
            while end < length and source[end].isdigit():
                end += 1
            tokens.append(('num', source[pos:end]))
            pos = end
            continue
        if char.isalpha() or char == '_':
            end = pos + 1
            while end < length and (source[end].isalnum() or source[end] == '_'):
                end += 1
            tokens.append(('ident', source[pos:end]))
            pos = end
            continue
        if source[pos:pos + 2] in _MULTI_CHAR_OPS:
            tokens.append(('op', source[pos:pos + 2]))
            pos += 2
            continue
        if char in _SINGLE_CHAR_OPS:
            tokens.append(('op', char))
            pos += 1
            continue
        raise PluralSyntaxError(f"unexpected character {char!r} at position {pos}")
    tokens.append(('eof', ''))
    return tokens


class _Parser:
    """Recursive-descent parser for C-precedence gettext expressions."""

    def __init__(self, source: str) -> None:
        self.tokens = _tokenize(source)
        self.index = 0

    @property
    def _current(self) -> tuple[str, str]:
        return self.tokens[self.index]

    def _advance(self) -> tuple[str, str]:
        token = self.tokens[self.index]
        self.index += 1
        return token

    def _accept(self, value: str) -> bool:
        if self._current == ('op', value):
            self._advance()
            return True
        return False

    def _expect(self, value: str) -> None:
        if not self._accept(value):
            kind, actual = self._current
            if kind == 'eof':
                raise PluralSyntaxError(f"unexpected end of expression, expected {value!r}")
            raise PluralSyntaxError(f"expected {value!r} but got {actual!r}")

    def parse(self) -> tuple:
        node = self._conditional()
        if self._current[0] != 'eof':
            raise PluralSyntaxError(f"unexpected trailing token {self._current[1]!r}")
        return node

    def _conditional(self) -> tuple:
        condition = self._logical_or()
        if self._accept('?'):
            when_true = self._conditional()
            self._expect(':')
            when_false = self._conditional()
            return ('cond', condition, when_true, when_false)
        return condition

    def _logical_or(self) -> tuple:
        node = self._logical_and()
        while self._accept('||'):
            node = ('bin', '||', node, self._logical_and())
        return node

    def _logical_and(self) -> tuple:
        node = self._equality()
        while self._accept('&&'):
            node = ('bin', '&&', node, self._equality())
        return node

    def _equality(self) -> tuple:
        node = self._relational()
        while self._current[1] in ('==', '!='):
            op = self._advance()[1]
            node = ('bin', op, node, self._relational())
        return node

    def _relational(self) -> tuple:
        node = self._additive()
        while self._current[1] in ('<', '<=', '>', '>='):
            op = self._advance()[1]
            node = ('bin', op, node, self._additive())
        return node

    def _additive(self) -> tuple:
        node = self._multiplicative()
        while self._current[1] in ('+', '-'):
            op = self._advance()[1]
            node = ('bin', op, node, self._multiplicative())
        return node

    def _multiplicative(self) -> tuple:
        node = self._unary()
        while self._current[1] in ('*', '/', '%'):
            op = self._advance()[1]
            node = ('bin', op, node, self._unary())
        return node

    def _unary(self) -> tuple:
        if self._current[1] in ('!', '-', '+'):
            op = self._advance()[1]
            return ('un', op, self._unary())
        return self._primary()

    def _primary(self) -> tuple:
        kind, value = self._current
        if kind == 'num':
            self._advance()
            return ('num', int(value))
        if kind == 'ident':
            self._advance()
            if value != 'n':
                raise PluralSyntaxError(f"unknown identifier {value!r}; only 'n' is allowed")
            return ('var',)
        if self._accept('('):
            node = self._conditional()
            self._expect(')')
            return node
        if kind == 'eof':
            raise PluralSyntaxError("unexpected end of expression")
        raise PluralSyntaxError(f"unexpected token {value!r}")


def parse_plural_expression(source: str) -> tuple:
    """Parse a gettext plural formula into an AST.

    :raises PluralSyntaxError: if the expression is not in the supported subset.
    """
    return _Parser(source).parse()


class _DivisionByZero(Exception):
    """Raised during concrete evaluation on a reachable division by zero."""


def _trunc_div(left: int, right: int) -> int:
    """C-style division (truncation toward zero)."""
    if right == 0:
        raise _DivisionByZero
    quotient = abs(left) // abs(right)
    return -quotient if (left < 0) != (right < 0) else quotient


def _trunc_mod(left: int, right: int) -> int:
    """C-style remainder (sign follows the dividend)."""
    return left - _trunc_div(left, right) * right


def evaluate(node: tuple, n: int) -> int:
    """Evaluate the AST for a single non-negative integer ``n``.

    Logical operators and the conditional short-circuit like in C.

    :raises _DivisionByZero: if a reachable division/modulo by zero occurs.
    """
    kind = node[0]
    if kind == 'num':
        return node[1]
    if kind == 'var':
        return n
    if kind == 'un':
        op, operand = node[1], node[2]
        value = evaluate(operand, n)
        if op == '-':
            return -value
        if op == '+':
            return value
        return 1 if value == 0 else 0
    if kind == 'bin':
        op, left_node, right_node = node[1], node[2], node[3]
        if op == '&&':
            return 1 if evaluate(left_node, n) != 0 and evaluate(right_node, n) != 0 else 0
        if op == '||':
            return 1 if evaluate(left_node, n) != 0 or evaluate(right_node, n) != 0 else 0
        left = evaluate(left_node, n)
        right = evaluate(right_node, n)
        if op == '+':
            return left + right
        if op == '-':
            return left - right
        if op == '*':
            return left * right
        if op == '/':
            return _trunc_div(left, right)
        if op == '%':
            return _trunc_mod(left, right)
        return 1 if _compare(op, left, right) else 0
    _, condition, when_true, when_false = node
    branch = when_true if evaluate(condition, n) != 0 else when_false
    return evaluate(branch, n)


def _compare(op: str, left: int, right: int) -> bool:
    if op == '==':
        return left == right
    if op == '!=':
        return left != right
    if op == '<':
        return left < right
    if op == '<=':
        return left <= right
    if op == '>':
        return left > right
    return left >= right


def compile_formula(tree: tuple):
    """Compile the AST into a callable ``f(n) -> int`` without using eval.

    The compiled function uses ordinary Python closures and short-circuiting
    operators; it raises `_DivisionByZero` on a reachable division by zero.
    """
    kind = tree[0]
    if kind == 'num':
        value = tree[1]
        return lambda n: value
    if kind == 'var':
        return lambda n: n
    if kind == 'un':
        operand = compile_formula(tree[2])
        op = tree[1]
        if op == '-':
            return lambda n: -operand(n)
        if op == '+':
            return operand
        return lambda n: 1 if operand(n) == 0 else 0
    if kind == 'cond':
        condition = compile_formula(tree[1])
        when_true = compile_formula(tree[2])
        when_false = compile_formula(tree[3])
        return lambda n: when_true(n) if condition(n) != 0 else when_false(n)
    op = tree[1]
    if op == '&&':
        left = compile_formula(tree[2])
        right = compile_formula(tree[3])
        return lambda n: 1 if left(n) != 0 and right(n) != 0 else 0
    if op == '||':
        left = compile_formula(tree[2])
        right = compile_formula(tree[3])
        return lambda n: 1 if left(n) != 0 or right(n) != 0 else 0
    left = compile_formula(tree[2])
    right = compile_formula(tree[3])
    if op == '+':
        return lambda n: left(n) + right(n)
    if op == '-':
        return lambda n: left(n) - right(n)
    if op == '*':
        return lambda n: left(n) * right(n)
    if op == '/':
        return lambda n: _trunc_div(left(n), right(n))
    if op == '%':
        return lambda n: _trunc_mod(left(n), right(n))
    return lambda n: 1 if _compare(op, left(n), right(n)) else 0


def _compare_ranges(op: str, left_low: int, left_high: int, right_low: int, right_high: int) -> int | None:
    """Constant result of comparing two ranges, or ``None`` if it varies."""
    if op == '==':
        if left_high < right_low or right_high < left_low:
            return 0
        if left_low == left_high == right_low == right_high:
            return 1
        return None
    if op == '!=':
        if left_high < right_low or right_high < left_low:
            return 1
        if left_low == left_high == right_low == right_high:
            return 0
        return None
    if op == '<':
        if left_high < right_low:
            return 1
        if left_low >= right_high:
            return 0
        return None
    if op == '<=':
        if left_high <= right_low:
            return 1
        if left_low > right_high:
            return 0
        return None
    if op == '>':
        if left_low > right_high:
            return 1
        if left_high <= right_low:
            return 0
        return None
    # '>='
    if left_low >= right_high:
        return 1
    if left_high < right_low:
        return 0
    return None


def _order_affine(left: _Summary, right: _Summary) -> tuple[_Affine, _Bounded, bool]:
    """Split an affine/bounded pair; ``reverse`` means affine is on the right."""
    if isinstance(left, _Affine):
        return left, right, False
    return right, left, True


@dataclass(frozen=True)
class _Bounded:
    """A value bounded by ``low``/``high`` and eventually periodic.

    For every ``n >= threshold`` the value at ``n + period`` equals the
    value at ``n``; the bounds hold for every ``n >= 0``.
    """

    low: int
    high: int
    threshold: int
    period: int


@dataclass(frozen=True)
class _Affine:
    """The exact value ``coef * n + const`` with a positive coefficient."""

    coef: int
    const: int


_Summary = Union[_Bounded, _Affine, None]


def _lcm(a: int, b: int) -> int:
    return a // gcd(a, b) * b


def _ceil_div(value: int, divisor: int) -> int:
    """Smallest integer ``q`` with ``q * divisor >= value`` (divisor > 0)."""
    return -((-value) // divisor)


_COMPARISON_OPS = frozenset(('==', '!=', '<', '<=', '>', '>='))


class _Summarizer:
    """Computes an abstract summary, or ``None`` outside the provable subset."""

    max_period: ClassVar[int] = 2_000_000

    def summarize(self, node: tuple) -> _Summary:
        kind = node[0]
        if kind == 'num':
            return _Bounded(node[1], node[1], 0, 1)
        if kind == 'var':
            return _Affine(1, 0)
        if kind == 'un':
            return self._unary(node[1], node[2])
        if kind == 'cond':
            return self._conditional(node[1], node[2], node[3])
        return self._binary(node[1], node[2], node[3])

    def _envelope(self, *summaries: _Bounded) -> tuple[int, int] | None:
        threshold = 0
        period = 1
        for summary in summaries:
            threshold = max(threshold, summary.threshold)
            period = _lcm(period, summary.period)
            if period > self.max_period:
                return None
        return threshold, period

    def _unary(self, op: str, operand_node: tuple) -> _Summary:
        operand = self.summarize(operand_node)
        if operand is None:
            return None
        if op == '+':
            return operand
        if op == '-':
            if isinstance(operand, _Bounded):
                return _Bounded(-operand.high, -operand.low, operand.threshold, operand.period)
            return None
        return self._truth(operand)

    def _truth(self, value: _Summary) -> _Summary:
        """Summary of the truth test ``value != 0``."""
        if isinstance(value, _Bounded):
            if value.low > 0 or value.high < 0:
                return _Bounded(1, 1, 0, 1)
            if value.low == 0 and value.high == 0:
                return _Bounded(0, 0, 0, 1)
            envelope = self._envelope(value)
            if envelope is None:
                return None
            threshold, period = envelope
            return _Bounded(0, 1, threshold, period)
        if isinstance(value, _Affine):
            # coef * n + const is guaranteed non-zero past -const/coef.
            threshold = max(0, _ceil_div(-value.const + 1, value.coef))
            return _Bounded(0, 1, threshold, 1)
        return None

    def _conditional(self, condition_node: tuple, true_node: tuple, false_node: tuple) -> _Summary:
        condition = self._truth(self.summarize(condition_node))
        if condition is None:
            return None
        # Constant condition: only the taken branch matters.
        if condition.low == condition.high:
            branch = true_node if condition.low == 1 else false_node
            return self.summarize(branch)
        true_value = self.summarize(true_node)
        false_value = self.summarize(false_node)
        if not isinstance(true_value, _Bounded) or not isinstance(false_value, _Bounded):
            return None
        envelope = self._envelope(condition, true_value, false_value)
        if envelope is None:
            return None
        threshold, period = envelope
        return _Bounded(
            min(true_value.low, false_value.low),
            max(true_value.high, false_value.high),
            threshold,
            period,
        )

    def _binary(self, op: str, left_node: tuple, right_node: tuple) -> _Summary:
        if op in ('&&', '||'):
            left = self._truth(self.summarize(left_node))
            right = self._truth(self.summarize(right_node))
            if not isinstance(left, _Bounded) or not isinstance(right, _Bounded):
                return None
            envelope = self._envelope(left, right)
            if envelope is None:
                return None
            threshold, period = envelope
            # && can be 0 even if a side is constant 1, || can be 1 even
            # if a side is constant 0; only all-constant operands fold.
            if op == '&&' and left.low == left.high == right.low == right.high:
                return _Bounded(left.low and right.low, left.low and right.low, 0, 1)
            if op == '||' and left.low == left.high == right.low == right.high:
                result = 1 if left.low or right.low else 0
                return _Bounded(result, result, 0, 1)
            return _Bounded(0, 1, threshold, period)
        if op in _COMPARISON_OPS:
            return self._comparison(op, left_node, right_node)
        return self._arithmetic(op, left_node, right_node)

    def _comparison(self, op: str, left_node: tuple, right_node: tuple) -> _Summary:
        left = self.summarize(left_node)
        right = self.summarize(right_node)
        if left is None or right is None:
            return None
        if isinstance(left, _Bounded) and isinstance(right, _Bounded):
            envelope = self._envelope(left, right)
            if envelope is None:
                return None
            threshold, period = envelope
            constant = _compare_ranges(op, left.low, left.high, right.low, right.high)
            if constant is not None:
                return _Bounded(constant, constant, 0, 1)
            return _Bounded(0, 1, threshold, period)
        if isinstance(left, _Affine) and isinstance(right, _Affine):
            # (a1*n+b1) op (a2*n+b2) becomes constant once the difference
            # d*n + c has a fixed sign.
            dcoef = left.coef - right.coef
            cconst = left.const - right.const
            if dcoef == 0:
                truth = 1 if _compare(op, cconst, 0) else 0
                return _Bounded(truth, truth, 0, 1)
            step = abs(dcoef)
            # First n for which d*n + c has the sign of d (and never leaves).
            threshold = max(0, _ceil_div(-cconst + 1, step)) if dcoef > 0 else max(
                0, _ceil_div(cconst + 1, step),
            )
            if dcoef > 0:
                truth = 1 if _compare(op, 1, 0) else 0
            else:
                truth = 1 if _compare(op, -1, 0) else 0
            if threshold == 0:
                return _Bounded(truth, truth, 0, 1)
            # Constant only past the threshold; before it, either outcome.
            return _Bounded(0, 1, threshold, 1)
        # One affine side, one bounded side.
        affine, bounded, reverse = _order_affine(left, right)
        # affine op bounded: past T, coef*n+const > bounded.high, so the
        # comparison result is constant.
        threshold = max(0, _ceil_div(bounded.high - affine.const + 1, affine.coef))
        if reverse:
            truth = 1 if _compare(op, bounded.high, bounded.high + 1) else 0
        else:
            truth = 1 if _compare(op, bounded.high + 1, bounded.high) else 0
        if threshold == 0:
            return _Bounded(truth, truth, 0, 1)
        # Constant only past the threshold; before it, either outcome.
        return _Bounded(0, 1, threshold, 1)

    def _arithmetic(self, op: str, left_node: tuple, right_node: tuple) -> _Summary:
        left = self.summarize(left_node)
        right = self.summarize(right_node)
        if left is None or right is None:
            return None
        if isinstance(left, _Bounded) and isinstance(right, _Bounded):
            return self._bounded_arithmetic(op, left, right)
        return self._affine_arithmetic(op, left, right)

    def _bounded_arithmetic(self, op: str, left: _Bounded, right: _Bounded) -> _Summary:
        envelope = self._envelope(left, right)
        if envelope is None:
            return None
        threshold, period = envelope
        if op == '+':
            return _Bounded(left.low + right.low, left.high + right.high, threshold, period)
        if op == '-':
            return _Bounded(left.low - right.high, left.high - right.low, threshold, period)
        if op == '*':
            corners = [
                left.low * right.low, left.low * right.high,
                left.high * right.low, left.high * right.high,
            ]
            return _Bounded(min(corners), max(corners), threshold, period)
        if op == '/':
            if right.low <= 0 <= right.high:
                # Possibly a division by zero; the concrete scan decides.
                # For any non-zero divisor, |a / b| <= |a|.
                magnitude = max(abs(left.low), abs(left.high))
                return _Bounded(-magnitude, magnitude, threshold, period)
            corners = [
                _trunc_div(left.low, right.low), _trunc_div(left.low, right.high),
                _trunc_div(left.high, right.low), _trunc_div(left.high, right.high),
            ]
            return _Bounded(min(corners), max(corners), threshold, period)
        # '%': the result takes the sign of the dividend and is strictly
        # smaller than the divisor in magnitude.
        magnitude = max(abs(right.low), abs(right.high))
        if magnitude == 0:
            # Divisor is the constant zero; the concrete scan will raise.
            return _Bounded(0, 0, 0, 1)
        low = 0 if left.low >= 0 else -(magnitude - 1)
        high = 0 if left.high <= 0 else magnitude - 1
        return _Bounded(low, high, threshold, period)

    def _affine_arithmetic(self, op: str, left: _Summary, right: _Summary) -> _Summary:
        affine = left if isinstance(left, _Affine) else right
        other = right if isinstance(left, _Affine) else left
        on_left = isinstance(left, _Affine)
        if not isinstance(affine, _Affine):
            return None
        if isinstance(other, _Affine):
            if op == '+':
                return _Affine(affine.coef + other.coef, affine.const + other.const)
            if op == '-':
                coef = affine.coef - other.coef if on_left else other.coef - affine.coef
                const = affine.const - other.const if on_left else other.const - affine.const
                if coef > 0:
                    return _Affine(coef, const)
                if coef == 0:
                    return _Bounded(const, const, 0, 1)
            return None
        # other is _Bounded.
        if not on_left and op in ('/', '%'):
            # bounded / affine: once the divisor exceeds the numerator in
            # magnitude the (truncated) result is constantly 0.
            # bounded % affine: ... and the remainder is the numerator itself.
            magnitude = max(abs(other.low), abs(other.high))
            threshold = max(0, _ceil_div(magnitude - affine.const + 1, affine.coef))
            if op == '/':
                return _Bounded(-magnitude, magnitude, threshold, 1)
            return _Bounded(
                other.low, other.high,
                max(other.threshold, threshold), other.period,
            )
        if other.low != other.high:
            return None
        const = other.low
        if op == '+':
            return _Affine(affine.coef, affine.const + const)
        if op == '-':
            if on_left:
                return _Affine(affine.coef, affine.const - const)
            return None
        if op == '*':
            if const == 0:
                return _Bounded(0, 0, 0, 1)
            if const > 0:
                return _Affine(affine.coef * const, affine.const * const)
            return None
        if op == '/':
            if const == 1 and on_left:
                return affine
            return None
        # '%' by a constant: bounded, with a period of |const|.
        if not on_left:
            return None
        if const == 0:
            # Modulo by zero; the concrete scan will raise.
            return _Bounded(0, 0, 0, 1)
        magnitude = abs(const)
        threshold = max(0, _ceil_div(-affine.const, affine.coef))
        return _Bounded(-(magnitude - 1), magnitude - 1, threshold, magnitude)


# ---------------------------------------------------------------------------
# Check report
# ---------------------------------------------------------------------------

#: The expression contains a syntax error.
SYNTAX = 'syntax'
#: A division or modulo by zero is performed for some n (with a witness).
DIVISION_BY_ZERO = 'division_by_zero'
#: The formula yields a negative value for some n (with a witness).
NEGATIVE_RESULT = 'negative_result'
#: The formula yields a value >= nplurals for some n (with a witness).
RESULT_OUT_OF_RANGE = 'result_out_of_range'
#: A declared plural form index is never produced.
UNREACHABLE_FORM = 'unreachable_form'
#: The formula is outside the provable subset; no claim is made.
UNKNOWN = 'unknown'


@dataclass(frozen=True)
class PluralIssue:
    """A single problem found in a plural formula."""

    kind: str
    message: str
    #: Smallest witnessing ``n`` (``None`` for unreachable branches/unknown).
    n: int | None = None


@dataclass
class PluralCheckReport:
    """Result of checking a ``Plural-Forms`` formula.

    ``status`` is one of ``'ok'``, ``'error'``, ``'syntax_error'`` or
    ``'unknown'``.  When the formula lies in the provable subset,
    ``threshold``/``period`` describe the exhaustive analysis and
    ``values`` is the exact set of results produced for every ``n >= 0``.
    """

    expression: str | None
    nplurals: int | None
    issues: list[PluralIssue] = field(default_factory=list)
    threshold: int | None = None
    period: int | None = None
    values: frozenset[int] | None = None

    @property
    def ok(self) -> bool:
        return not self.issues

    @property
    def status(self) -> str:
        kinds = {issue.kind for issue in self.issues}
        if SYNTAX in kinds:
            return 'syntax_error'
        if UNKNOWN in kinds:
            return 'unknown'
        if kinds:
            return 'error'
        return 'ok'

    def issues_of(self, kind: str) -> list[PluralIssue]:
        return [issue for issue in self.issues if issue.kind == kind]

    def __str__(self) -> str:
        if self.ok:
            return f"plural formula is safe (nplurals={self.nplurals})"
        return '; '.join(issue.message for issue in self.issues)


def check_plural_expression(
    expression: str,
    nplurals: int,
    max_period: int = _Summarizer.max_period,
) -> PluralCheckReport:
    """Safely parse and check a gettext plural ``expression``.

    :param expression: the formula text (the ``plural=`` value)
    :param nplurals: declared number of plural forms
    :param max_period: formulas with an analysis period larger than this
                       are reported as ``unknown`` rather than exhaustively
                       explored
    """
    report = PluralCheckReport(expression=expression, nplurals=nplurals)
    try:
        tree = parse_plural_expression(expression)
    except PluralSyntaxError as error:
        report.issues.append(PluralIssue(SYNTAX, f"syntax error in plural formula: {error}"))
        return report

    summarizer = _Summarizer()
    summarizer.max_period = max_period
    summary = summarizer.summarize(tree)

    if isinstance(summary, _Bounded):
        _check_bounded(tree, summary, nplurals, max_period, report)
    elif isinstance(summary, _Affine):
        _check_affine(tree, summary, nplurals, summarizer, max_period, report)
    else:
        report.issues.append(PluralIssue(
            UNKNOWN,
            "plural formula is outside the subset that can be proven safe "
            "(constant comparisons and constant modulo); not claiming safety",
        ))
    return report


def _check_bounded(
    tree: tuple,
    summary: _Bounded,
    nplurals: int,
    max_period: int,
    report: PluralCheckReport,
) -> None:
    scan_size = summary.threshold + summary.period
    if scan_size > max_period:
        report.issues.append(PluralIssue(
            UNKNOWN,
            f"plural formula needs an analysis period of {scan_size} "
            f"(limit {max_period}); not claiming safety",
        ))
        return
    report.threshold = summary.threshold
    report.period = summary.period

    first_witness: dict[int, int] = {}
    div_zero_witness: int | None = None
    # Every n >= 0 is represented by a member of range(scan_size): n < T
    # directly, and n >= T through eventual periodicity (value(n) == value(n%P)
    # inside the periodic region).
    func = compile_formula(tree)
    for n in range(scan_size):
        try:
            value = func(n)
        except _DivisionByZero:
            if div_zero_witness is None:
                div_zero_witness = n
            continue
        if value not in first_witness:
            first_witness[value] = n

    report.values = frozenset(first_witness)

    if div_zero_witness is not None:
        report.issues.append(PluralIssue(
            DIVISION_BY_ZERO,
            f"division or modulo by zero is reached (first at n={div_zero_witness})",
            div_zero_witness,
        ))
    for value in sorted(first_witness):
        witness = first_witness[value]
        if value < 0:
            report.issues.append(PluralIssue(
                NEGATIVE_RESULT,
                f"plural formula returns {value} at n={witness}, which is negative",
                witness,
            ))
        elif value >= nplurals:
            report.issues.append(PluralIssue(
                RESULT_OUT_OF_RANGE,
                f"plural formula returns {value} at n={witness}, "
                f"but nplurals={nplurals} only allows 0..{nplurals - 1}",
                witness,
            ))
    for form in range(nplurals):
        if form not in first_witness:
            report.issues.append(PluralIssue(
                UNREACHABLE_FORM,
                f"plural form {form} is declared but never produced by the formula",
            ))


def _check_affine(
    tree: tuple,
    summary: _Affine,
    nplurals: int,
    summarizer: _Summarizer,
    max_period: int,
    report: PluralCheckReport,
) -> None:
    a, b = summary.coef, summary.const
    # The exact value is a*n + b with a > 0.
    if b < 0:
        report.issues.append(PluralIssue(
            NEGATIVE_RESULT,
            f"plural formula returns {b} at n=0, which is negative",
            0,
        ))
    overflow_witness = max(0, _ceil_div(nplurals - b, a))
    report.issues.append(PluralIssue(
        RESULT_OUT_OF_RANGE,
        f"plural formula returns {a * overflow_witness + b} at n={overflow_witness}, "
        f"but nplurals={nplurals} only allows 0..{nplurals - 1}",
        overflow_witness,
    ))
    # Reachable values in the valid range are those with 0 <= a*n + b < nplurals.
    first_n = max(0, _ceil_div(-b, a))
    last_n = _ceil_div(nplurals - b, a)
    reachable = {a * n + b for n in range(first_n, last_n) if 0 <= a * n + b < nplurals}
    report.values = frozenset(reachable)
    for form in range(nplurals):
        if form not in reachable:
            report.issues.append(PluralIssue(
                UNREACHABLE_FORM,
                f"plural form {form} is declared but never produced by the formula",
            ))

    # Division by zero: analyze each divisor sub-expression exactly.
    cache: dict[tuple, _Summary] = {}

    def cached(node: tuple) -> _Summary:
        if node not in cache:
            cache[node] = summarizer.summarize(node)
        return cache[node]

    def walk(node: tuple) -> None:
        kind = node[0]
        if kind == 'num' or kind == 'var':
            return
        if kind == 'un':
            walk(node[2])
            return
        if kind == 'cond':
            walk(node[1])
            walk(node[2])
            walk(node[3])
            return
        if node[1] in ('/', '%'):
            check_divisor(node[3])
        walk(node[2])
        walk(node[3])

    unknown_divisor = False
    candidates: list[int] = []

    def check_divisor(denom_node: tuple) -> None:
        nonlocal unknown_divisor
        denom = cached(denom_node)
        if isinstance(denom, _Affine):
            if denom.const % denom.coef == 0:
                zero_n = -denom.const // denom.coef
                if zero_n >= 0:
                    candidates.append(zero_n)
        elif isinstance(denom, _Bounded):
            scan_size = denom.threshold + denom.period
            if scan_size > max_period:
                unknown_divisor = True
                return
            for n in range(scan_size):
                try:
                    if evaluate(denom_node, n) == 0:
                        candidates.append(n)
                except _DivisionByZero:
                    candidates.append(n)
        else:
            unknown_divisor = True

    walk(tree)
    if unknown_divisor:
        report.issues.append(PluralIssue(
            UNKNOWN,
            "could not prove absence of division by zero: a divisor is outside "
            "the subset built from constant comparisons and constant modulo",
        ))
    for n in sorted(set(candidates)):
        try:
            evaluate(tree, n)
        except _DivisionByZero:
            report.issues.append(PluralIssue(
                DIVISION_BY_ZERO,
                f"division or modulo by zero is reached (first at n={n})",
                n,
            ))
            break


def check_plural_forms(
    forms: str,
    max_period: int = _Summarizer.max_period,
) -> PluralCheckReport:
    """Check a whole ``Plural-Forms`` header value such as
    ``"nplurals=2; plural=(n != 1);"``.
    """
    nplurals_match = re.search(r'nplurals\s*=\s*(\d+)', forms)
    plural_match = re.search(r'plural\s*=', forms)
    if nplurals_match is None or plural_match is None:
        return PluralCheckReport(
            expression=None,
            nplurals=int(nplurals_match.group(1)) if nplurals_match else None,
            issues=[PluralIssue(SYNTAX,
                                "Plural-Forms must contain both nplurals=<int> and plural=<expr>")],
        )
    nplurals = int(nplurals_match.group(1))
    expression = forms[plural_match.end():].strip()
    if expression.endswith(';'):
        expression = expression[:-1].rstrip()
    if nplurals < 1:
        report = PluralCheckReport(expression=expression, nplurals=nplurals)
        report.issues.append(PluralIssue(SYNTAX, "nplurals must be a positive integer"))
        return report
    return check_plural_expression(expression, nplurals, max_period=max_period)
