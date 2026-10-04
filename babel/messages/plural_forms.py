"""Safe parsing and validation of gettext ``Plural-Forms`` expressions."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, ClassVar, NamedTuple

__all__ = [
    "PluralFormsCheckResult",
    "PluralFormsIssue",
    "PluralFormsSyntaxError",
    "check_plural_forms",
    "evaluate_plural_expression",
    "parse_plural_expression",
    "parse_plural_forms",
]


class PluralFormsSyntaxError(ValueError):
    """Raised when a gettext plural expression cannot be parsed."""


class _Token(NamedTuple):
    kind: str
    value: str
    pos: int


class _Node(NamedTuple):
    kind: str
    pos: int
    left: object = None
    right: object = None
    third: object = None
    value: int = 0


_TOKEN_RE = re.compile(
    r"(?P<number>[0-9]+)|"
    r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)|"
    r"(?P<op>==|!=|<=|>=|&&|\|\||[-+*/%<>!?:()])",
)


def _tokenize(source: str) -> list[_Token]:
    tokens: list[_Token] = []
    pos = 0
    while pos < len(source):
        if source[pos].isspace():
            pos += 1
            continue
        match = _TOKEN_RE.match(source, pos)
        if match is None or match.start() != pos:
            raise PluralFormsSyntaxError(f"unexpected character at position {pos}")
        kind = match.lastgroup or "op"
        value = match.group()
        if kind == "name" and value != "n":
            raise PluralFormsSyntaxError(f"unknown variable {value!r} at position {pos}")
        tokens.append(_Token(kind, value, pos))
        pos = match.end()
    return tokens


class _Parser:
    def __init__(self, source: str) -> None:
        self.source = source
        self.tokens = _tokenize(source)
        self.pos = 0

    def parse(self) -> _Node:
        node = self.conditional()
        if self.pos < len(self.tokens):
            token = self.tokens[self.pos]
            raise PluralFormsSyntaxError(
                f"unexpected token {token.value!r} at position {token.pos}",
            )
        return node

    def peek(self) -> _Token | None:
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return None

    def take(self, value: str | None = None) -> _Token:
        token = self.peek()
        if token is None:
            raise PluralFormsSyntaxError(f"expected {value or 'expression'}, got end of expression")
        if value is not None and token.value != value:
            raise PluralFormsSyntaxError(
                f"expected {value!r}, got {token.value!r} at position {token.pos}",
            )
        self.pos += 1
        return token

    def conditional(self) -> _Node:
        condition = self.logical_or()
        if self.peek() is not None and self.peek().value == "?":
            pos = self.take("?").pos
            then = self.conditional()
            self.take(":")
            otherwise = self.conditional()
            return _Node("if", pos, condition, then, otherwise)
        return condition

    def logical_or(self) -> _Node:
        node = self.logical_and()
        while self.peek() is not None and self.peek().value == "||":
            pos = self.take().pos
            node = _Node("or", pos, node, self.logical_and())
        return node

    def logical_and(self) -> _Node:
        node = self.equality()
        while self.peek() is not None and self.peek().value == "&&":
            pos = self.take().pos
            node = _Node("and", pos, node, self.equality())
        return node

    def equality(self) -> _Node:
        node = self.relational()
        while self.peek() is not None and self.peek().value in ("==", "!="):
            token = self.take()
            node = _Node(token.value, token.pos, node, self.relational())
        return node

    def relational(self) -> _Node:
        node = self.additive()
        while self.peek() is not None and self.peek().value in ("<", ">", "<=", ">="):
            token = self.take()
            node = _Node(token.value, token.pos, node, self.additive())
        return node

    def additive(self) -> _Node:
        node = self.multiplicative()
        while self.peek() is not None and self.peek().value in ("+", "-"):
            token = self.take()
            node = _Node(token.value, token.pos, node, self.multiplicative())
        return node

    def multiplicative(self) -> _Node:
        node = self.unary()
        while self.peek() is not None and self.peek().value in ("*", "/", "%"):
            token = self.take()
            node = _Node(token.value, token.pos, node, self.unary())
        return node

    def unary(self) -> _Node:
        token = self.peek()
        if token is not None and token.value in ("-", "!", "+"):
            self.pos += 1
            return _Node(token.value, token.pos, self.unary())
        return self.primary()

    def primary(self) -> _Node:
        token = self.take()
        if token.kind == "number":
            return _Node("const", token.pos, value=int(token.value))
        if token.kind == "name":
            return _Node("n", token.pos)
        if token.value == "(":
            node = self.conditional()
            self.take(")")
            return node
        raise PluralFormsSyntaxError(
            f"expected expression, got {token.value!r} at position {token.pos}",
        )


def parse_plural_expression(source: str) -> object:
    """Parse a gettext plural expression without using Python's parser or eval."""
    if not source or not source.strip():
        raise PluralFormsSyntaxError("empty plural expression")
    return _Parser(source).parse()


_PLURAL_FORMS_RE = re.compile(
    r"^\s*nplurals\s*=\s*(?P<nplurals>[^;]+?)\s*;"
    r"\s*plural\s*=\s*(?P<plural>.*?)\s*;?\s*$",
    re.DOTALL,
)


def parse_plural_forms(source: str) -> tuple[int | None, str, object]:
    """Parse a complete ``Plural-Forms`` header value."""
    match = _PLURAL_FORMS_RE.match(source)
    if match is None:
        raise PluralFormsSyntaxError("malformed Plural-Forms header")
    nplurals_text = match.group("nplurals").strip()
    plural_text = match.group("plural").strip()
    nplurals = int(nplurals_text) if re.fullmatch(r"[+-]?[0-9]+", nplurals_text) else None
    return nplurals, plural_text, parse_plural_expression(plural_text)


@dataclass(frozen=True)
class _Affine:
    slope: int
    intercept: int


@dataclass(frozen=True)
class _Remainder:
    multiplier: int
    remainder: _Affine
    offset: int

    @property
    def modulus(self) -> int:
        return abs(self.remainder.slope)


_Term = Any


@dataclass(frozen=True)
class _Atom:
    op: str
    term: _Term
    constant: int


_Guard = tuple[_Atom, ...]


@dataclass(frozen=True)
class PluralFormsIssue:
    code: str
    message: str
    witness: int | None = None
    index: int | None = None


@dataclass(frozen=True)
class PluralFormsCheckResult:
    status: str
    nplurals: int | None
    expression: str | None
    issues: tuple[PluralFormsIssue, ...] = field(default_factory=tuple)
    reachable_indices: tuple[int, ...] = ()
    period: int | None = None
    threshold: int | None = None


def _negate(term: _Term) -> _Term | None:
    if isinstance(term, int):
        return -term
    if isinstance(term, _Affine):
        return _Affine(-term.slope, -term.intercept)
    if isinstance(term, _Remainder):
        return _Remainder(-term.multiplier, term.remainder, -term.offset)
    return None


def _add(left: _Term, right: _Term) -> _Term | None:
    if isinstance(left, int) and isinstance(right, int):
        return left + right
    if isinstance(left, int):
        return _add(right, left)
    if isinstance(right, int):
        if isinstance(left, _Affine):
            return _Affine(left.slope, left.intercept + right)
        if isinstance(left, _Remainder):
            return _Remainder(left.multiplier, left.remainder, left.offset + right)
    if isinstance(left, _Affine) and isinstance(right, _Affine):
        return _Affine(left.slope + right.slope, left.intercept + right.intercept)
    return None


def _sub(left: _Term, right: _Term) -> _Term | None:
    if isinstance(left, int) and isinstance(right, int):
        return left - right
    if isinstance(right, int):
        if isinstance(left, _Affine):
            return _Affine(left.slope, left.intercept - right)
        if isinstance(left, _Remainder):
            return _Remainder(left.multiplier, left.remainder, left.offset - right)
    if isinstance(left, _Affine) and isinstance(right, _Affine):
        return _Affine(left.slope - right.slope, left.intercept - right.intercept)
    return None


def _mul(left: _Term, right: _Term) -> _Term | None:
    if isinstance(left, int) and isinstance(right, int):
        return left * right
    if isinstance(left, int):
        return _mul(right, left)
    if isinstance(right, int):
        if isinstance(left, _Affine):
            return _Affine(left.slope * right, left.intercept * right)
        if isinstance(left, _Remainder):
            return _Remainder(left.multiplier * right, left.remainder, left.offset * right)
    return None


def _mod(term: _Term, divisor: int) -> _Term | None:
    divisor = abs(divisor)
    if divisor == 0:
        return 0
    if isinstance(term, int):
        return int(math.fmod(term, divisor))
    if isinstance(term, _Affine) and term.slope in (0, 1):
        if term.slope == 0:
            return _c_mod(term.intercept, divisor)
        return _Remainder(1, _Affine(divisor, term.intercept), 0)
    if isinstance(term, _Remainder) and term.multiplier == 1 and term.offset == 0:
        if term.remainder.slope % divisor == 0:
            return int(math.fmod(term.remainder.intercept, divisor))
        if divisor % term.modulus == 0:
            return term
        if term.modulus % divisor == 0:
            return _Remainder(1, _Affine(divisor, term.remainder.intercept), 0)
    if isinstance(term, _Affine) and term.slope == 0:
        return _c_mod(term.intercept, divisor)
    return None


def _trunc_div(left: int, right: int) -> int:
    quotient = abs(left) // abs(right)
    return -quotient if (left < 0) != (right < 0) else quotient


def _c_mod(left: int, right: int) -> int:
    remainder = abs(left) % abs(right)
    return -remainder if left < 0 and remainder else remainder


def _negate_atom(atom: _Atom) -> _Atom:
    negation = {"=": "!=", "!=": "=", "<": ">=", "<=": ">", ">": "<=", ">=": "<"}
    return _Atom(negation[atom.op], atom.term, atom.constant)


def _lcm(*values: int) -> int:
    result = 1
    for value in values:
        result = result // math.gcd(result, value) * value
    return result


class _Analyzer:
    max_period: ClassVar[int] = 100_000

    def __init__(self, root: _Node) -> None:
        self.root = root
        self.cases: list[tuple[_Guard, _Term]] = []
        self.bool_unknown: list[_Guard] = []
        self.int_unknown: list[_Guard] = []
        self.zero_division_guards: list[_Guard] = []
        self.moduli: set[int] = set()
        self.bounds: set[int] = {0}

    def analyze(self) -> None:
        self.cases = self.analyze_int(self.root, ())

    def extend(self, path: _Guard, atoms: _Guard) -> _Guard:
        return path + atoms

    def note_bound(self, term: _Term, constant: int, op: str) -> None:
        if isinstance(term, _Affine):
            if term.slope != 0:
                target = constant - term.intercept
                value = target // term.slope
                self.bounds.add(max(0, value + (0 if op in ("<=", ">=") else 1)))
        elif isinstance(term, _Remainder):
            modulus = term.modulus
            self.moduli.add(modulus)
            self.bounds.add(max(0, abs(constant), abs(term.offset)))

    def compare(self, left: _Term, op: str, right: _Term) -> tuple[_Guard | None, bool | None]:
        if isinstance(left, int) and isinstance(right, int):
            operations = {
                "==": left == right, "!=": left != right,
                "<": left < right, "<=": left <= right,
                ">": left > right, ">=": left >= right,
            }
            return (), operations[op]
        difference = _sub(left, right)
        if difference is None:
            return None, None
        if op == "==":
            atom_op = "="
        else:
            atom_op = op
        if isinstance(difference, int):
            return (), bool({
                "==": difference == 0,
                "!=": difference != 0,
                "<": difference < 0,
                "<=": difference <= 0,
                ">": difference > 0,
                ">=": difference >= 0,
            }[op])
        atom = _Atom(atom_op, difference, 0)
        self.note_bound(atom.term, atom.constant, op)
        return (atom,), None

    def analyze_bool(
        self,
        node: _Node,
        path: _Guard,
    ) -> list[tuple[_Guard, bool]]:
        if node.kind == "!":
            return [(guard, not value) for guard, value in self.analyze_bool(node.left, path)]

        if node.kind == "and":
            result: list[tuple[_Guard, bool]] = []
            for guard, value in self.analyze_bool(node.left, path):
                combined = self.extend(path, guard)
                if not value:
                    result.append((guard, False))
                else:
                    result.extend(
                        (guard + right_guard, right_value)
                        for right_guard, right_value in self.analyze_bool(node.right, combined)
                    )
            return result

        if node.kind == "or":
            result = []
            for guard, value in self.analyze_bool(node.left, path):
                combined = self.extend(path, guard)
                if value:
                    result.append((guard, True))
                else:
                    result.extend(
                        (guard + right_guard, right_value)
                        for right_guard, right_value in self.analyze_bool(node.right, combined)
                    )
            return result

        if node.kind == "if":
            result = []
            for guard, value in self.analyze_bool(node.left, path):
                selected = node.right if value else node.third
                combined = self.extend(path, guard)
                result.extend(
                    (guard + selected_guard, selected_value)
                    for selected_guard, selected_value in self.analyze_bool(selected, combined)
                )
            return result

        if node.kind in ("==", "!=", "<", "<=", ">", ">="):
            result = []
            left_cases = self.analyze_int(node.left, path)
            right_cases = self.analyze_int(node.right, path)
            for left_guard, left_term in left_cases:
                for right_guard, right_term in right_cases:
                    atoms, value = self.compare(left_term, node.kind, right_term)
                    if atoms is None:
                        self.bool_unknown.append(path + left_guard + right_guard)
                    elif value is None:
                        atom = atoms[0]
                        result.append((left_guard + right_guard + (atom,), True))
                        result.append((left_guard + right_guard + (_negate_atom(atom),), False))
                    else:
                        result.append((left_guard + right_guard + atoms, value))
            return result

        result = []
        for guard, term in self.analyze_int(node, path):
            atoms, value = self.compare(term, "!=", 0)
            if atoms is None:
                self.bool_unknown.append(path + guard)
            elif value is None:
                atom = atoms[0]
                result.append((guard + (atom,), True))
                result.append((guard + (_negate_atom(atom),), False))
            else:
                result.append((guard + atoms, value))
        return result

    def bool_as_int(self, node: _Node, path: _Guard) -> list[tuple[_Guard, _Term]]:
        cases = []
        for guard, value in self.analyze_bool(node, path):
            cases.append((guard, int(value)))
        return cases

    def analyze_int(self, node: _Node, path: _Guard) -> list[tuple[_Guard, _Term]]:
        if node.kind == "const":
            return [((), node.value)]
        if node.kind == "n":
            return [((), _Affine(1, 0))]
        if node.kind == "+" and node.right is None:
            return self.analyze_int(node.left, path)
        if node.kind == "!":
            return self.bool_as_int(node.left, path)
        if node.kind == "-" and node.right is None:
            result = []
            for guard, term in self.analyze_int(node.left, path):
                negated = _negate(term)
                if negated is None:
                    self.int_unknown.append(path + guard)
                else:
                    result.append((guard, negated))
            return result
        if node.kind == "if":
            result = []
            for guard, value in self.analyze_bool(node.left, path):
                selected = node.right if value else node.third
                result.extend(
                    (guard + selected_guard, selected_term)
                    for selected_guard, selected_term in self.analyze_int(
                        selected,
                        self.extend(path, guard),
                    )
                )
            return result
        if node.kind in ("+", "-", "*") and node.right is not None:
            operation = {"+": _add, "-": _sub, "*": _mul}[node.kind]
            return self.combine_terms(node, path, operation)
        if node.kind in ("/", "%"):
            return self.division(node, path)
        return self.bool_as_int(node, path)

    def combine_terms(self, node: _Node, path: _Guard, operation: object) -> list[tuple[_Guard, _Term]]:
        result = []
        left_cases = self.analyze_int(node.left, path)
        right_cases = self.analyze_int(node.right, path)
        for left_guard, left_term in left_cases:
            for right_guard, right_term in right_cases:
                value = operation(left_term, right_term)
                guard = left_guard + right_guard
                if value is None:
                    self.int_unknown.append(path + guard)
                else:
                    result.append((guard, value))
        return result

    def division(self, node: _Node, path: _Guard) -> list[tuple[_Guard, _Term]]:
        result = []
        left_cases = self.analyze_int(node.left, path)
        right_cases = self.analyze_int(node.right, path)
        for divisor_guard, divisor in right_cases:
            zero_guard, zero_value = self.compare(divisor, "==", 0)
            non_zero_guard, non_zero_value = self.compare(divisor, "!=", 0)
            combined_divisor_guard = path + divisor_guard
            if zero_guard is None:
                self.int_unknown.append(combined_divisor_guard)
                continue
            if zero_value is not False:
                zero_guard_path = combined_divisor_guard + zero_guard
                zero_status, _zero_witness = solve_guard(zero_guard_path)
                if zero_status != "unsat":
                    self.zero_division_guards.append(zero_guard_path)
            if zero_value is True:
                continue
            for numerator_guard, numerator in left_cases:
                guard = divisor_guard + numerator_guard
                if isinstance(divisor, int) and divisor != 0:
                    if node.kind == "%":
                        value = _mod(numerator, divisor)
                        if isinstance(value, _Remainder):
                            self.moduli.add(abs(divisor))
                            if value.remainder.intercept < 0:
                                self.int_unknown.append(path + divisor_guard + numerator_guard)
                    elif isinstance(numerator, int):
                        value = _trunc_div(numerator, divisor)
                    else:
                        value = None
                else:
                    value = None
                if value is None:
                    non_zero_path = path + divisor_guard + numerator_guard + non_zero_guard
                    if node.kind != "/":
                        self.int_unknown.append(path + guard)
                    elif non_zero_guard is None:
                        self.int_unknown.append(path + guard)
                    elif non_zero_value is True:
                        self.int_unknown.append(path + guard)
                    else:
                        status, _witness = solve_guard(non_zero_path)
                        if status == "sat":
                            self.int_unknown.append(non_zero_path)
                else:
                    result.append((guard, value))
        return result


def _point(value: int, modulus: int) -> frozenset[tuple[int, int]]:
    value %= modulus
    return frozenset({(value, value)})


def _full_interval(modulus: int) -> frozenset[tuple[int, int]]:
    return frozenset({(0, modulus - 1)})


def _intersect_intervals(
    left: frozenset[tuple[int, int]],
    right: frozenset[tuple[int, int]],
) -> frozenset[tuple[int, int]]:
    result = set()
    for left_lo, left_hi in left:
        for right_lo, right_hi in right:
            lo = max(left_lo, right_lo)
            hi = min(left_hi, right_hi)
            if lo <= hi:
                result.add((lo, hi))
    return frozenset(result)


def _interval_values(intervals: frozenset[tuple[int, int]]) -> list[int]:
    values = []
    for lo, hi in sorted(intervals):
        values.extend(range(lo, hi + 1))
    return values


def _interval_size(intervals: frozenset[tuple[int, int]]) -> int:
    return sum(hi - lo + 1 for lo, hi in intervals)


def _remainder_interval(
    atom: _Atom,
) -> tuple[int, frozenset[tuple[int, int]] | None, int]:
    term = atom.term
    assert isinstance(term, _Remainder)
    modulus = term.modulus
    if term.multiplier not in (1, -1):
        return modulus, None, max(0, -term.remainder.intercept)

    target_value = atom.constant - term.offset
    if term.multiplier == -1:
        target_value = -target_value
        flipped = {"=": "=", "!=": "!=", "<": ">", "<=": ">=", ">": "<", ">=": "<="}
        op = flipped[atom.op]
    else:
        op = atom.op

    target = target_value
    if op == "=":
        intervals = _point(target, modulus)
    elif op == "!=":
        intervals = _full_interval(modulus) - _point(target, modulus)
    elif op == "<":
        intervals = frozenset({(0, min(modulus - 1, target - 1))}) if target > 0 else frozenset()
    elif op == "<=":
        intervals = frozenset({(0, min(modulus - 1, target))}) if target >= 0 else frozenset()
    elif op == ">":
        intervals = (
            frozenset({(max(0, target + 1), modulus - 1)})
            if target < modulus - 1 else frozenset()
        )
    else:
        intervals = (
            frozenset({(max(0, target), modulus - 1)})
            if target < modulus else frozenset()
        )
    tail_start = max(0, -term.remainder.intercept)
    return modulus, intervals, tail_start


def _extended_gcd(left: int, right: int) -> tuple[int, int, int]:
    if right == 0:
        return left, 1, 0
    divisor, x, y = _extended_gcd(right, left % right)
    return divisor, y, x - (left // right) * y


def _combine_residue(
    residue_a: int,
    modulus_a: int,
    residue_b: int,
    modulus_b: int,
) -> tuple[int, int] | None:
    divisor, coefficient_a, _coefficient_b = _extended_gcd(modulus_a, modulus_b)
    difference = residue_b - residue_a
    if difference % divisor:
        return None
    modulus = modulus_a // divisor * modulus_b
    residue = (residue_a + modulus_a * (difference // divisor * coefficient_a % (modulus_b // divisor))) % modulus
    return residue, modulus


def _expand_residues(
    residues: frozenset[int],
    modulus: int,
    new_modulus: int,
    new_intervals: frozenset[tuple[int, int]],
) -> frozenset[int]:
    result = set()
    estimated_size = len(residues) * _interval_size(new_intervals)
    if estimated_size > _Analyzer.max_period:
        raise OverflowError
    for value in _interval_values(new_intervals):
        for old in residues:
            combined = _combine_residue(old, modulus, value, new_modulus)
            if combined is not None:
                result.add(combined[0])
    return frozenset(result)


def _affine_constraint(atom: _Atom) -> tuple[str, int, int]:
    term = atom.term
    assert isinstance(term, _Affine)
    return atom.op, term.slope, -term.intercept


def _satisfies_affine_atom(n: int, atom: _Atom) -> bool:
    op, slope, target = _affine_constraint(atom)
    value = slope * n
    return {
        "=": value == target,
        "!=": value != target,
        "<": value < target,
        "<=": value <= target,
        ">": value > target,
        ">=": value >= target,
    }[op]


def solve_guard(guard: _Guard, *, lower: int = 0) -> tuple[str, int | None]:
    groups: dict[int, frozenset[tuple[int, int]]] = {}
    affine_atoms = []
    minimum = lower

    for atom in guard:
        if isinstance(atom.term, _Remainder):
            modulus, intervals, tail_start = _remainder_interval(atom)
            if intervals is None:
                return "unknown", None
            if not intervals:
                return "unsat", None
            minimum = max(minimum, tail_start)
            groups[modulus] = _intersect_intervals(groups.get(modulus, _full_interval(modulus)), intervals)
            if not groups[modulus]:
                return "unsat", None
        elif isinstance(atom.term, _Affine):
            affine_atoms.append(atom)
        else:
            return "unknown", None

    low = minimum
    high: int | None = None
    exact: set[int] = set()
    forbidden: set[int] = set()

    for atom in affine_atoms:
        op, slope, target = _affine_constraint(atom)
        if slope == 0:
            value = atom.term.intercept if isinstance(atom.term, _Affine) else 0
            truth = {
                "=": value == atom.constant,
                "!=": value != atom.constant,
                "<": value < atom.constant,
                "<=": value <= atom.constant,
                ">": value > atom.constant,
                ">=": value >= atom.constant,
            }[op]
            return ("unsat", None) if not truth else ("proved", None)
        if op == "=":
            if target % slope:
                return "unsat", None
            point = -(-target // slope) if slope < 0 else target // slope
            exact.add(point)
        elif op == "!=":
            if target % slope == 0:
                point = target // slope
                forbidden.add(point)
        if op in ("<", "<=", ">", ">="):
            # Solve slope*n compared with target. Python floor division keeps
            # these bounds exact for both positive and negative slopes.
            if slope > 0:
                if op == "<":
                    high_n = (target - 1) // slope
                    high = high_n if high is None else min(high, high_n)
                elif op == "<=":
                    high_n = target // slope
                    high = high_n if high is None else min(high, high_n)
                elif op == ">":
                    low = max(low, target // slope + 1)
                else:
                    low = max(low, (target + slope - 1) // slope)
            elif op == "<":
                low = max(low, target // slope)
            elif op == "<=":
                low = max(low, (target + 1) // slope)
            elif op == ">":
                high_n = (target + 1) // slope
                high = high_n if high is None else max(high, high_n)
            else:
                high_n = target // slope
                high = high_n if high is None else max(high, high_n)

    if high is not None and low > high:
        return "unsat", None
    candidates = sorted(exact) if exact else [low, low + 1, high if high is not None else low]

    residue_groups = sorted(groups.items())
    exact_residues: set[int] = {0}
    exact_modulus = 1
    interval_groups: list[tuple[int, frozenset[tuple[int, int]]]] = []
    incomplete = False
    for modulus, intervals in residue_groups:
        values = frozenset(_interval_values(intervals))
        if len(values) == 1:
            residue = next(iter(values))
            next_residues = set()
            for old in exact_residues:
                combined = _combine_residue(old, exact_modulus, residue, modulus)
                if combined is not None:
                    next_residues.add(combined[0])
            if not next_residues:
                return "unsat", None
            exact_residues = next_residues
            exact_modulus = _lcm(exact_modulus, modulus)
        else:
            interval_groups.append((modulus, intervals))

    small_groups: list[tuple[int, frozenset[tuple[int, int]]]] = []
    large_negations: list[tuple[int, int]] = []
    for modulus, intervals in interval_groups:
        values = _interval_values(intervals)
        full_size = _interval_size(_full_interval(modulus))
        if len(values) == full_size - 1:
            missing = set(range(modulus)) - set(values)
            large_negations.append((modulus, next(iter(missing))))
        else:
            small_groups.append((modulus, intervals))

    small_modulus = 1
    small_intervals: dict[int, frozenset[tuple[int, int]]] = {}
    for modulus, intervals in small_groups:
        interval_size = _interval_size(intervals)
        if (
            _lcm(small_modulus, modulus) <= _Analyzer.max_period
            and len(exact_residues) * interval_size <= _Analyzer.max_period
        ):  # fmt: skip
            small_intervals[modulus] = intervals
            small_modulus = _lcm(small_modulus, modulus)
        else:
            incomplete = True

    residues: frozenset[int] = exact_residues
    residue_modulus = exact_modulus
    for modulus, intervals in sorted(small_intervals.items()):
        try:
            new_residues = _expand_residues(residues, residue_modulus, modulus, intervals)
        except OverflowError:
            incomplete = True
            continue
        if not new_residues:
            return "unsat", None
        residues = new_residues
        residue_modulus = _lcm(residue_modulus, modulus)

    skipped_groups = [
        (modulus, intervals)
        for modulus, intervals in small_groups
        if modulus not in small_intervals
    ] + [
        (modulus, _full_interval(modulus) - _point(residue, modulus))
        for modulus, residue in large_negations
    ]

    def valid(n: int) -> bool:
        if n < low or (high is not None and n > high) or n in forbidden:
            return False
        if any(not _satisfies_affine_atom(n, atom) for atom in affine_atoms):
            return False
        return all(
            any(lo <= n % modulus <= hi for lo, hi in intervals)
            for modulus, intervals in skipped_groups
        )

    if exact:
        for candidate in candidates:
            if candidate < low or (high is not None and candidate > high):
                continue
            if candidate in forbidden or any(
                not _satisfies_affine_atom(candidate, atom) for atom in affine_atoms
            ):  # fmt: skip
                continue
            if any(not any(lo <= candidate % modulus <= hi for lo, hi in intervals)
                   for modulus, intervals in residue_groups):  # fmt: skip
                continue
            if candidate % residue_modulus not in residues:
                continue
            if any(not any(lo <= candidate % modulus <= hi for lo, hi in intervals)
                   for modulus, intervals in skipped_groups):  # fmt: skip
                continue
            return "sat", candidate
        return "unsat", None

    candidate_numbers = []
    for candidate in candidates:
        if candidate is None or candidate < low or (high is not None and candidate > high):
            continue
        aligned = candidate
        if residue_modulus > 1:
            aligned = low + ((candidate - low) % residue_modulus)
            for residue in sorted(residues):
                candidate_numbers.append(low + (residue - low) % residue_modulus + (
                    max(0, candidate - (low + (residue - low) % residue_modulus) + residue_modulus - 1)
                    // residue_modulus * residue_modulus
                ))
        range_end = min(
            (high if high is not None else aligned + residue_modulus),
            aligned + residue_modulus,
            aligned + _Analyzer.max_period,
        )
        candidate_numbers.extend(range(aligned, range_end + 1))
    candidate_numbers.extend(range(low, min(high if high is not None else low + 8, low + 8) + 1))
    for residue in sorted(residues)[:100]:
        candidate_numbers.append(low + (residue - low) % residue_modulus)

    for candidate in dict.fromkeys(candidate_numbers):
        if valid(candidate):
            return "sat", candidate

    if incomplete and high is None and not forbidden and not (
        exact and all(point in forbidden for point in exact)
    ):
        candidate = low + (min(residues) - low) % residue_modulus
        for _ in range(_Analyzer.max_period):
            if candidate >= low and valid(candidate):
                return "sat", candidate
            candidate += residue_modulus if residue_modulus > 1 else 1

    if not incomplete:
        for residue in sorted(residues):
            candidate = low + (residue - low) % residue_modulus
            if high is None or candidate <= high:
                return "sat", candidate
        return "unsat", None

    if not incomplete and high is not None:
        for candidate in range(low, high + 1):
            if valid(candidate):
                return "sat", candidate

    return ("unknown", None) if incomplete else ("unsat", None)


def evaluate_plural_expression(ast: object, n: int) -> int:
    """Evaluate a parsed gettext expression for a non-negative integer ``n``."""
    if n < 0:
        raise ValueError("gettext plural count must be non-negative")

    def evaluate(node: _Node) -> int:
        kind = node.kind
        if kind == "const":
            return node.value
        if kind == "n":
            return n
        if kind == "+" and node.right is None:
            return evaluate(node.left)
        if kind == "-" and node.right is None:
            return -evaluate(node.left)
        if kind == "!":
            return int(not evaluate(node.left))
        if kind == "if":
            condition = evaluate(node.left)
            return evaluate(node.right if condition else node.third)
        left = evaluate(node.left)
        if kind in ("and", "or"):
            if kind == "and":
                if not left:
                    return 0
                return int(bool(evaluate(node.right)))
            if left:
                return 1
            return int(bool(evaluate(node.right)))
        if kind == "?":
            raise AssertionError(kind)
        right = evaluate(node.right)
        if kind in ("==", "!=", "<", "<=", ">", ">="):
            return int({
                "==": left == right, "!=": left != right,
                "<": left < right, "<=": left <= right,
                ">": left > right, ">=": left >= right,
            }[kind])
        if kind == "+" and node.right is not None:
            return left + right
        if kind == "-" and node.right is not None:
            return left - right
        if kind == "*":
            return left * right
        if kind == "/":
            return _trunc_div(left, right)
        if kind == "%":
            return _c_mod(left, right)
        raise PluralFormsSyntaxError(f"unsupported expression node {kind}")

    if not isinstance(ast, _Node):
        raise PluralFormsSyntaxError("invalid parsed expression")
    return evaluate(ast)


def _term_condition_witness(term: _Term, op: str, value: int) -> tuple[str, int | None]:
    if isinstance(term, int):
        truth = {
            "=": term == value,
            "<": term < value,
            ">=": term >= value,
        }[op]
        return ("sat", 0) if truth else ("unsat", None)
    return solve_guard((_Atom(op, term, value),))


def check_plural_forms(source: str) -> PluralFormsCheckResult:
    """Check a complete ``Plural-Forms`` declaration without evaluating untrusted code."""
    try:
        nplurals, expression, ast = parse_plural_forms(source)
    except PluralFormsSyntaxError as error:
        issue = PluralFormsIssue("syntax_error", str(error))
        return PluralFormsCheckResult("syntax_error", None, None, (issue,))

    assert isinstance(ast, _Node)
    analyzer = _Analyzer(ast)
    analyzer.analyze()
    fatal_division = False

    issues: list[PluralFormsIssue] = []
    if nplurals is None or nplurals <= 0:
        issues.append(PluralFormsIssue("invalid_nplurals", "nplurals must be a positive integer"))

    division_issues = []
    for guard in {tuple(guard): None for guard in analyzer.zero_division_guards}:
        status, witness = solve_guard(guard)
        if status == "sat" and witness is not None:
            division_issues.append(PluralFormsIssue(
                "division_by_zero",
                "division by zero is reachable",
                witness=witness,
            ))
            fatal_division = True
        elif status == "unknown":
            division_issues.append(PluralFormsIssue(
                "division_by_zero",
                "division by zero cannot be ruled out",
            ))
    issues.extend(division_issues)

    reachable: set[int] = set()
    unknown_reachable = False
    if nplurals is not None and nplurals > 0 and not fatal_division:
        for guard, term in analyzer.cases:
            for op, bound, code, message in (
                ("<", 0, "negative_result", "plural result can be negative"),
                (
                    ">=", nplurals, "index_out_of_range",
                    "plural result can be greater than or equal to nplurals",
                ),
            ):
                status, witness = _term_condition_witness(term, op, bound)
                if status == "sat" and witness is not None:
                    issues.append(PluralFormsIssue(code, message, witness=witness))
                elif status == "unknown":
                    unknown_reachable = True

            if isinstance(term, int) and 0 <= term < nplurals:
                status, witness = solve_guard(guard)
                if status == "sat" and witness is not None:
                    reachable.add(term)
                elif status == "unknown":
                    unknown_reachable = True
            elif not isinstance(term, int):
                for index in range(nplurals):
                    status, witness = _term_condition_witness(term, "=", index)
                    if status == "sat" and witness is not None:
                        reachable.add(index)
                    elif status == "unknown":
                        unknown_reachable = True

    for guard in analyzer.int_unknown + analyzer.bool_unknown:
        status, _witness = solve_guard(guard)
        if status != "unsat":
            unknown_reachable = True

    if nplurals is not None and nplurals > 0 and not fatal_division:
        if not unknown_reachable:
            for index in range(min(nplurals, analyzer.max_period)):
                if index not in reachable:
                    issues.append(PluralFormsIssue(
                        "unreachable_plural",
                        f"plural index {index} is declared but unreachable",
                        index=index,
                    ))
            if nplurals > analyzer.max_period and len(reachable) < nplurals:
                unknown_reachable = True

    if fatal_division:
        status = "division_by_zero"
    elif any(issue.code == "invalid_nplurals" for issue in issues):
        status = "syntax_error"
    elif any(issue.code in ("negative_result", "index_out_of_range") for issue in issues):
        status = "invalid_result"
    elif unknown_reachable:
        status = "unknown"
    elif any(issue.code == "unreachable_plural" for issue in issues):
        status = "unreachable_plural"
    else:
        status = "safe"

    period = _lcm(*analyzer.moduli) if analyzer.moduli else 1
    threshold = max(analyzer.bounds)
    return PluralFormsCheckResult(
        status=status,
        nplurals=nplurals,
        expression=expression,
        issues=tuple(issues),
        reachable_indices=tuple(sorted(reachable)),
        period=period,
        threshold=threshold,
    )
