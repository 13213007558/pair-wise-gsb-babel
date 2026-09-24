"""
babel.messageformat
~~~~~~~~~~~~~~~~~~~

ICU MessageFormat compilation and formatting.

This module provides an entry point to compile ICU MessageFormat patterns
into reusable objects and to format them with parameters, independent of
the gettext-based APIs in :mod:`babel.messages`.

Supported syntax:

 * simple arguments: ``{name}`` or ``{0}``
 * ``select``: ``{gender, select, female{...} male{...} other{...}}``
 * ``plural``: ``{count, plural, offset:1 =0{...} one{...} other{...}}``
 * ``selectordinal``: ``{pos, selectordinal, one{#st} two{#nd} few{#rd} other{#th}}``
 * ``#`` inside a plural/selectordinal branch, bound to the nearest
   enclosing plural
 * apostrophe quoting: ``''`` for a literal apostrophe, ``'{'`` etc. for
   literal syntax characters

:copyright: (c) 2013-2026 by the Babel Team.
:license: BSD, see LICENSE for more details.
"""

from __future__ import annotations

import decimal
import re
from collections.abc import Mapping
from typing import Any

from babel.core import Locale
from babel.numbers import format_decimal

__all__ = [
    "CompiledMessage",
    "MessageFormatError",
    "compile_message",
    "format_message",
]

_arg_name_re = re.compile(r"[^\s{},]+")
_selector_re = re.compile(r"[^\s{]+")
_type_re = re.compile(r"[^\s{,]+")
_exact_value_re = re.compile(r"=[ \t]*([-+]?\d+(?:\.\d+)?)")
_offset_re = re.compile(r"offset[ \t]*:[ \t]*(\d+)")
_whitespace_re = re.compile(r"\s*")


class MessageFormatError(ValueError):
    """Raised when an ICU MessageFormat pattern cannot be compiled.

    The ``position`` attribute holds the character offset in the pattern
    where the problem was detected.
    """

    def __init__(self, message: str, position: int | None = None) -> None:
        self.position = position
        if position is not None:
            message = f"{message} (at position {position})"
        super().__init__(message)


# ---------------------------------------------------------------------------
# AST nodes
# ---------------------------------------------------------------------------


class _Text:
    __slots__ = ("value",)

    def __init__(self, value: str) -> None:
        self.value = value


class _Argument:
    __slots__ = ("name",)

    def __init__(self, name: str) -> None:
        self.name = name


class _Pound:
    __slots__ = ()


class _Select:
    __slots__ = ("name", "cases", "position")

    def __init__(self, name: str, cases: dict[str, list], position: int) -> None:
        self.name = name
        self.cases = cases
        self.position = position


class _Plural:
    __slots__ = ("name", "offset", "exact", "cases", "ordinal", "position")

    def __init__(
        self,
        name: str,
        offset: int,
        exact: dict[decimal.Decimal, list],
        cases: dict[str, list],
        ordinal: bool,
        position: int,
    ) -> None:
        self.name = name
        self.offset = offset
        self.exact = exact
        self.cases = cases
        self.ordinal = ordinal
        self.position = position


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


class _Parser:
    def __init__(self, pattern: str) -> None:
        self.pattern = pattern
        self.length = len(pattern)

    def parse(self) -> list:
        nodes, pos = self._parse_message(0, in_plural=False)
        if pos < self.length:
            # A '}' without a matching '{'.
            raise MessageFormatError("unmatched closing brace", pos)
        return nodes

    def _skip_whitespace(self, pos: int) -> int:
        match = _whitespace_re.match(self.pattern, pos)
        return match.end()

    def _parse_message(self, pos: int, in_plural: bool) -> tuple[list, int]:
        """Parse message text until a closing brace or end of pattern.

        Returns the parsed nodes and the position of the closing brace
        (or the end of the pattern).
        """
        nodes: list = []
        literal: list[str] = []
        pattern = self.pattern

        def flush() -> None:
            if literal:
                nodes.append(_Text("".join(literal)))
                literal.clear()

        while pos < self.length:
            char = pattern[pos]
            if char == "'":
                if pattern.startswith("''", pos):
                    literal.append("'")
                    pos += 2
                elif pos + 1 < self.length and pattern[pos + 1] in "{}#|":
                    # Quoted literal until the closing apostrophe; an
                    # unterminated quote consumes the rest of the pattern,
                    # matching ICU's lenient behavior.
                    cursor = pos + 1
                    while cursor < self.length:
                        if pattern[cursor] == "'":
                            if pattern.startswith("''", cursor):
                                literal.append("'")
                                cursor += 2
                                continue
                            break
                        literal.append(pattern[cursor])
                        cursor += 1
                    pos = cursor + 1 if cursor < self.length else self.length
                else:
                    literal.append("'")
                    pos += 1
            elif char == "{":
                flush()
                node, pos = self._parse_placeholder(pos, in_plural)
                nodes.append(node)
            elif char == "}":
                flush()
                return nodes, pos
            elif char == "#" and in_plural:
                flush()
                nodes.append(_Pound())
                pos += 1
            else:
                literal.append(char)
                pos += 1
        flush()
        return nodes, pos

    def _parse_placeholder(self, pos: int, in_plural: bool) -> tuple[Any, int]:
        start = pos
        pattern = self.pattern
        pos = self._skip_whitespace(pos + 1)
        name_match = _arg_name_re.match(pattern, pos)
        if not name_match:
            raise MessageFormatError("expected an argument name", pos)
        name = name_match.group(0)
        pos = self._skip_whitespace(name_match.end())
        if pos >= self.length:
            raise MessageFormatError("unclosed argument placeholder", start)
        if pattern[pos] == "}":
            return _Argument(name), pos + 1
        if pattern[pos] != ",":
            raise MessageFormatError("expected ',' or '}' after argument name", pos)
        pos = self._skip_whitespace(pos + 1)
        type_match = _type_re.match(pattern, pos)
        arg_type = type_match.group(0) if type_match else ""
        if arg_type not in ("select", "plural", "selectordinal"):
            raise MessageFormatError(
                f"unsupported argument type {arg_type!r}; "
                "expected 'select', 'plural' or 'selectordinal'",
                pos,
            )
        pos = self._skip_whitespace(type_match.end())
        if pos >= self.length or pattern[pos] != ",":
            raise MessageFormatError(
                f"expected ',' after {arg_type!r}",
                pos if pos < self.length else start,
            )
        pos = self._skip_whitespace(pos + 1)

        offset = 0
        if arg_type != "select":
            offset_match = _offset_re.match(pattern, pos)
            if offset_match:
                offset = int(offset_match.group(1))
                pos = self._skip_whitespace(offset_match.end())

        exact: dict[decimal.Decimal, list] = {}
        cases: dict[str, list] = {}
        branch_plural = in_plural or arg_type != "select"
        while True:
            if pos >= self.length:
                raise MessageFormatError(
                    f"unclosed {arg_type!r} placeholder",
                    start,
                )
            if pattern[pos] == "}":
                pos += 1
                break
            selector_pos = pos
            if arg_type != "select" and pattern[pos] == "=":
                value_match = _exact_value_re.match(pattern, pos)
                if not value_match:
                    raise MessageFormatError("expected a number after '='", pos)
                key = decimal.Decimal(value_match.group(1))
                if key in exact:
                    raise MessageFormatError(
                        f"duplicate selector '={value_match.group(1)}'",
                        selector_pos,
                    )
                pos = self._skip_whitespace(value_match.end())
                body, pos = self._parse_branch(pos, branch_plural, start)
                exact[key] = body
            else:
                selector_match = _selector_re.match(pattern, pos)
                if not selector_match:
                    raise MessageFormatError("expected a selector", pos)
                keyword = selector_match.group(0)
                if keyword in cases:
                    raise MessageFormatError(
                        f"duplicate selector {keyword!r}",
                        selector_pos,
                    )
                pos = self._skip_whitespace(selector_match.end())
                body, pos = self._parse_branch(pos, branch_plural, start)
                cases[keyword] = body
            pos = self._skip_whitespace(pos)

        if "other" not in cases:
            raise MessageFormatError(
                f"missing required 'other' branch in {arg_type!r}",
                start,
            )
        if arg_type == "select":
            return _Select(name, cases, start), pos
        return _Plural(name, offset, exact, cases, arg_type == "selectordinal", start), pos

    def _parse_branch(self, pos: int, in_plural: bool, start: int) -> tuple[list, int]:
        if pos >= self.length or self.pattern[pos] != "{":
            raise MessageFormatError("expected '{' to open a branch", pos)
        body, pos = self._parse_message(pos + 1, in_plural)
        if pos >= self.length:
            raise MessageFormatError("unclosed branch", start)
        return body, pos + 1


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


def _to_decimal(value: Any) -> decimal.Decimal:
    if isinstance(value, decimal.Decimal):
        return value
    if isinstance(value, int):
        return decimal.Decimal(value)
    if isinstance(value, float):
        return decimal.Decimal(str(value))
    if isinstance(value, str):
        try:
            return decimal.Decimal(value.strip())
        except decimal.InvalidOperation:
            pass
    raise MessageFormatError(f"expected a numeric value, got {value!r}")


def _format_number(value: decimal.Decimal, locale: Locale) -> str:
    exponent = value.as_tuple().exponent
    if isinstance(exponent, int) and exponent < 0:
        # Keep the visible fraction digits (including trailing zeros).
        pattern = "#,##0." + "0" * (-exponent)
    else:
        pattern = "#,##0"
    return format_decimal(value, format=pattern, locale=locale)


class CompiledMessage:
    """A compiled ICU MessageFormat pattern.

    Instances are immutable after compilation and may be shared and reused
    to format any number of parameter sets. Parameter values are inserted
    verbatim; they are never parsed for template syntax and never executed.
    """

    def __init__(self, nodes: list, locale: Locale) -> None:
        self._nodes = nodes
        self.locale = locale

    def format(self, *args: Any, **kwargs: Any) -> str:
        """Format the message with the given parameters.

        Parameters may be passed as a single mapping, as positional
        arguments (addressed as ``{0}``, ``{1}``, ...) or as keyword
        arguments (addressed by name).
        """
        if len(args) == 1 and isinstance(args[0], Mapping):
            params = dict(args[0])
        else:
            params = {str(index): value for index, value in enumerate(args)}
        params.update(kwargs)
        parts: list[str] = []
        self._render(self._nodes, params, [], parts)
        return "".join(parts)

    def _render(
        self,
        nodes: list,
        params: Mapping[str, Any],
        plural_values: list[decimal.Decimal],
        parts: list[str],
    ) -> None:
        for node in nodes:
            if isinstance(node, _Text):
                parts.append(node.value)
            elif isinstance(node, _Argument):
                try:
                    value = params[node.name]
                except KeyError:
                    raise KeyError(
                        f"missing parameter {node.name!r}",
                    ) from None
                parts.append(str(value))
            elif isinstance(node, _Pound):
                parts.append(_format_number(plural_values[-1], self.locale))
            elif isinstance(node, _Select):
                try:
                    value = params[node.name]
                except KeyError:
                    raise KeyError(
                        f"missing parameter {node.name!r}",
                    ) from None
                body = node.cases.get(str(value), node.cases["other"])
                self._render(body, params, plural_values, parts)
            elif isinstance(node, _Plural):
                try:
                    raw_value = params[node.name]
                except KeyError:
                    raise KeyError(
                        f"missing parameter {node.name!r}",
                    ) from None
                value = _to_decimal(raw_value)
                shifted = value - node.offset
                # Explicit "=N" branches match the original value, before
                # the offset is subtracted.
                body = node.exact.get(value)
                if body is None:
                    if node.ordinal:
                        tag = self.locale.ordinal_form(shifted)
                    else:
                        tag = self.locale.plural_form(shifted)
                    body = node.cases.get(tag, node.cases["other"])
                plural_values.append(shifted)
                try:
                    self._render(body, params, plural_values, parts)
                finally:
                    plural_values.pop()


def compile_message(pattern: str, locale: Locale | str | None = None) -> CompiledMessage:
    """Compile an ICU MessageFormat pattern into a reusable object.

    :param pattern: the ICU MessageFormat pattern
    :param locale: the locale used for plural category selection and
                   number formatting (defaults to ``en``)
    :raise MessageFormatError: if the pattern is invalid; the error
                               carries the position of the problem
    """
    if isinstance(locale, Locale):
        resolved = locale
    else:
        resolved = Locale.parse(locale or "en")
    nodes = _Parser(pattern).parse()
    return CompiledMessage(nodes, resolved)


def format_message(
    pattern: str,
    params: Mapping[str, Any] | None = None,
    locale: Locale | str | None = None,
    **kwargs: Any,
) -> str:
    """Compile and format an ICU MessageFormat pattern in one step.

    For repeated formatting of the same pattern, prefer
    :func:`compile_message` and reuse the compiled object.
    """
    message = compile_message(pattern, locale)
    merged = dict(params or {})
    merged.update(kwargs)
    return message.format(merged)
