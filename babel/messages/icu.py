"""
babel.messages.icu
~~~~~~~~~~~~~~~~~~

A self-contained compiler and formatter for a subset of ICU MessageFormat
patterns.

The entry points are :func:compile_message, which parses a pattern once and
returns a reusable :class:ICUMessage object, and :func:format_message, which
compiles and formats in a single call.

Supported syntax:

* simple arguments: '{name}'
* selects: '{gender, select, female{...} male{...} other{...}}'
* plurals: '{count, plural, offset:1 =0{...} one{...} other{...}}'
* ordinals: '{place, selectordinal, one{#st} two{#nd} few{#rd} other{#th}}'
* the '#' placeholder, bound to the nearest enclosing plural
* apostrophe quoting of literal text ('' is a literal apostrophe)

Formatting never evaluates Python code and argument values are inserted
verbatim; they are never re-parsed as message patterns.

:copyright: (c) 2013-2026 by the Babel Team.
:license: BSD, see LICENSE for more details.
"""

from __future__ import annotations

import decimal
import re
from typing import Any, Mapping

from babel.core import Locale, default_locale
from babel.numbers import format_decimal

__all__ = [
    "ICUMessage",
    "MessageFormatError",
    "compile_message",
    "format_message",
]

_plural_tags = frozenset({"zero", "one", "two", "few", "many", "other"})

_name_re = re.compile(r"[^\s{},]+")
_exact_key_re = re.compile(r"=-?\d+(?:\.\d+)?")
_offset_re = re.compile(r"offset:\s*(\d+)")


class MessageFormatError(ValueError):
    """Raised when an ICU message pattern cannot be compiled or formatted.

    For compile-time errors the 'position' attribute holds the offset of the
    offending token within the pattern, or None for format-time errors.
    """

    def __init__(self, message: str, position: int | None = None) -> None:
        self.position = position
        if position is not None:
            message = f"{message} (at position {position})"
        super().__init__(message)


class _Node:
    __slots__ = ()


class _Text(_Node):
    __slots__ = ("value",)

    def __init__(self, value: str) -> None:
        self.value = value


class _Argument(_Node):
    __slots__ = ("name",)

    def __init__(self, name: str) -> None:
        self.name = name


class _Pound(_Node):
    __slots__ = ("plural",)

    def __init__(self, plural: _Plural) -> None:
        self.plural = plural


class _Select(_Node):
    __slots__ = ("name", "cases")

    def __init__(self, name: str, cases: dict[str, list[_Node]]) -> None:
        self.name = name
        self.cases = cases


class _Plural(_Node):
    __slots__ = ("name", "ordinal", "offset", "exact", "cases")

    def __init__(
        self,
        name: str,
        ordinal: bool,
        offset: int,
        exact: dict[decimal.Decimal, list[_Node]],
        cases: dict[str, list[_Node]],
    ) -> None:
        self.name = name
        self.ordinal = ordinal
        self.offset = offset
        self.exact = exact
        self.cases = cases


class _Parser:
    """Recursive-descent parser for the supported ICU MessageFormat subset."""

    def __init__(self, pattern: str) -> None:
        self.pattern = pattern
        self.length = len(pattern)
        self.pos = 0

    def error(self, message: str, position: int | None = None) -> MessageFormatError:
        return MessageFormatError(message, self.pos if position is None else position)

    def parse(self) -> list[_Node]:
        nodes = self._parse_message(enclosing_plural=None)
        if self.pos < self.length:
            # The only way to stop early at top level is an unmatched brace.
            raise self.error("unmatched '}'")
        return nodes

    def _parse_message(self, enclosing_plural: _Plural | None) -> list[_Node]:
        """Parse literal text and placeholders until '}' or end of input."""
        nodes: list[_Node] = []
        buf: list[str] = []

        def flush() -> None:
            if buf:
                nodes.append(_Text("".join(buf)))
                del buf[:]

        while self.pos < self.length:
            ch = self.pattern[self.pos]
            if ch == "{":
                flush()
                nodes.append(self._parse_placeholder(enclosing_plural))
            elif ch == "}":
                flush()
                return nodes
            elif ch == "#" and enclosing_plural is not None:
                flush()
                nodes.append(_Pound(enclosing_plural))
                self.pos += 1
            elif ch == "'":
                self._parse_quoted(buf, in_plural=enclosing_plural is not None)
            else:
                buf.append(ch)
                self.pos += 1
        flush()
        return nodes

    def _parse_quoted(self, buf: list[str], in_plural: bool) -> None:
        """Handle an apostrophe at the current position, appending to buf."""
        start = self.pos
        nxt = self.pattern[self.pos + 1] if self.pos + 1 < self.length else ""
        if nxt == "'":
            buf.append("'")
            self.pos += 2
            return
        syntax_chars = "{}#" if in_plural else "{}"
        if nxt and nxt in syntax_chars:
            # Quoted literal until the closing apostrophe; an unterminated
            # quote swallows the rest of the pattern, as ICU does.
            self.pos += 1
            while self.pos < self.length:
                ch = self.pattern[self.pos]
                if ch == "'":
                    if self.pos + 1 < self.length and self.pattern[self.pos + 1] == "'":
                        buf.append("'")
                        self.pos += 2
                    else:
                        self.pos += 1
                        return
                else:
                    buf.append(ch)
                    self.pos += 1
            return
        # An apostrophe not followed by a syntax character is literal.
        buf.append("'")
        self.pos = start + 1

    def _skip_whitespace(self) -> None:
        while self.pos < self.length and self.pattern[self.pos].isspace():
            self.pos += 1

    def _parse_placeholder(self, enclosing_plural: _Plural | None) -> _Node:
        start = self.pos
        self.pos += 1  # consume '{'
        self._skip_whitespace()
        match = _name_re.match(self.pattern, self.pos)
        if not match:
            raise self.error("expected an argument name")
        name = match.group(0)
        self.pos = match.end()
        self._skip_whitespace()
        if self.pos < self.length and self.pattern[self.pos] == "}":
            self.pos += 1
            return _Argument(name)
        if self.pos >= self.length or self.pattern[self.pos] != ",":
            raise self.error("expected ',' or '}' after the argument name")
        self.pos += 1
        self._skip_whitespace()
        match = _name_re.match(self.pattern, self.pos)
        keyword = match.group(0) if match else ""
        if keyword not in ("select", "plural", "selectordinal"):
            if keyword:
                raise self.error(
                    f"expected 'select', 'plural' or 'selectordinal', got {keyword!r}",
                )
            raise self.error("expected a message type")
        self.pos = match.end()
        self._skip_whitespace()
        if self.pos >= self.length or self.pattern[self.pos] != ",":
            raise self.error(f"expected ',' after {keyword!r}")
        self.pos += 1
        self._skip_whitespace()

        offset = 0
        if keyword != "select":
            offset_match = _offset_re.match(self.pattern, self.pos)
            if offset_match:
                offset = int(offset_match.group(1))
                self.pos = offset_match.end()
                self._skip_whitespace()

        exact: dict[decimal.Decimal, list[_Node]] = {}
        cases: dict[str, list[_Node]] = {}
        plural: _Plural | None = None
        branch_plural: _Plural | None
        if keyword != "select":
            plural = _Plural(name, keyword == "selectordinal", offset, exact, cases)
            branch_plural = plural
        else:
            # A select does not shadow '#': it still binds to the nearest
            # enclosing plural, if any.
            branch_plural = enclosing_plural

        while True:
            self._skip_whitespace()
            if self.pos >= self.length:
                raise self.error(f"unclosed {keyword} branches", start)
            if self.pattern[self.pos] == "}":
                self.pos += 1
                break
            key_pos = self.pos
            exact_key: decimal.Decimal | None = None
            selector: str | None = None
            if keyword != "select" and self.pattern[self.pos] == "=":
                match = _exact_key_re.match(self.pattern, self.pos)
                if not match:
                    raise self.error("expected a number after '='")
                exact_key = decimal.Decimal(match.group(0)[1:])
                self.pos = match.end()
            else:
                match = _name_re.match(self.pattern, self.pos)
                if not match:
                    raise self.error("expected a selector")
                selector = match.group(0)
                self.pos = match.end()
                if keyword != "select" and selector not in _plural_tags:
                    raise self.error(f"unknown plural selector {selector!r}", key_pos)
            self._skip_whitespace()
            if self.pos >= self.length or self.pattern[self.pos] != "{":
                raise self.error("expected '{' to start a branch")
            self.pos += 1
            branch = self._parse_message(enclosing_plural=branch_plural)
            if self.pos >= self.length:
                raise self.error("unclosed branch", key_pos)
            self.pos += 1  # consume '}'

            if exact_key is not None:
                if exact_key in exact:
                    raise self.error(f"duplicate selector '={exact_key}'", key_pos)
                exact[exact_key] = branch
            else:
                if selector in cases:
                    raise self.error(f"duplicate selector {selector!r}", key_pos)
                cases[selector] = branch

        if "other" not in cases:
            raise self.error(f"missing required 'other' branch in {keyword}", start)
        if plural is not None:
            return plural
        return _Select(name, cases)


def _resolve_locale(locale: Locale | str | None) -> Locale:
    if isinstance(locale, Locale):
        return locale
    if locale is None:
        locale = default_locale("LC_MESSAGES") or "en"
    return Locale.parse(locale)


def _format_number(value: Any, locale: Locale) -> str:
    """Format a number for output, preserving decimal trailing zeros."""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return format_decimal(value, locale=locale)
    if isinstance(value, float):
        value = decimal.Decimal(str(value))
    if isinstance(value, decimal.Decimal):
        fraction_digits = max(-value.as_tuple().exponent, 0)
        pattern = "#,##0" + ("." + "0" * fraction_digits if fraction_digits else "")
        return format_decimal(
            value,
            format=pattern,
            locale=locale,
            decimal_quantization=False,
        )
    return str(value)


def _coerce_number(value: Any, name: str) -> decimal.Decimal | int:
    if isinstance(value, bool):
        raise MessageFormatError(f"argument {name!r} must be a number, got {value!r}")
    if isinstance(value, (int, decimal.Decimal)):
        return value
    if isinstance(value, float):
        return decimal.Decimal(str(value))
    if isinstance(value, str):
        try:
            return decimal.Decimal(value)
        except decimal.InvalidOperation:
            pass
    raise MessageFormatError(f"argument {name!r} must be a number, got {value!r}")


class ICUMessage:
    """A compiled ICU message pattern, reusable for any number of formats.

    Instances are created via :func:compile_message.  The compiled object
    holds no per-request state, so a single instance may be shared across
    requests and threads.
    """

    __slots__ = ("pattern", "locale", "_nodes")

    def __init__(
        self,
        pattern: str,
        nodes: list[_Node],
        locale: Locale,
    ) -> None:
        self.pattern = pattern
        self.locale = locale
        self._nodes = nodes

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.pattern!r}>"

    def format(self, params: Mapping[str, Any] | None = None, **kwargs: Any) -> str:
        """Format the message with the given parameters.

        Parameter values are inserted as-is and are never parsed as message
        patterns themselves.

        :param params: a mapping of argument names to values
        :param kwargs: additional arguments, merged over params
        :raise MessageFormatError: if a required argument is missing or a
                                   plural argument is not numeric
        """
        args: dict[str, Any] = {}
        if params:
            args.update(params)
        args.update(kwargs)
        out: list[str] = []
        self._render(self._nodes, args, out)
        return "".join(out)

    def _lookup(self, args: Mapping[str, Any], name: str) -> Any:
        try:
            return args[name]
        except KeyError:
            raise MessageFormatError(f"missing argument {name!r}") from None

    def _render(
        self,
        nodes: list[_Node],
        args: Mapping[str, Any],
        out: list[str],
    ) -> None:
        for node in nodes:
            if isinstance(node, _Text):
                out.append(node.value)
            elif isinstance(node, _Argument):
                value = self._lookup(args, node.name)
                if isinstance(value, (int, float, decimal.Decimal)) and not isinstance(
                    value,
                    bool,
                ):
                    out.append(_format_number(value, self.locale))
                else:
                    out.append(str(value))
            elif isinstance(node, _Pound):
                plural = node.plural
                value = _coerce_number(self._lookup(args, plural.name), plural.name)
                out.append(_format_number(value - plural.offset, self.locale))
            elif isinstance(node, _Select):
                value = str(self._lookup(args, node.name))
                self._render(node.cases.get(value, node.cases["other"]), args, out)
            elif isinstance(node, _Plural):
                value = _coerce_number(self._lookup(args, node.name), node.name)
                branch = node.exact.get(decimal.Decimal(value))
                if branch is None:
                    adjusted = value - node.offset
                    rule = (
                        self.locale.ordinal_form if node.ordinal else self.locale.plural_form
                    )
                    tag = rule(adjusted)
                    branch = node.cases.get(tag, node.cases["other"])
                self._render(branch, args, out)


def compile_message(pattern: str, locale: Locale | str | None = None) -> ICUMessage:
    """Compile an ICU message pattern into a reusable :class:ICUMessage.

    :param pattern: the message pattern to compile
    :param locale: the locale used for plural category selection and number
                   formatting; defaults to the system locale
    :raise MessageFormatError: if the pattern is malformed (the 'position'
                               attribute points at the offending token)
    """
    resolved = _resolve_locale(locale)
    nodes = _Parser(pattern).parse()
    return ICUMessage(pattern, nodes, resolved)


def format_message(
    pattern: str,
    params: Mapping[str, Any] | None = None,
    locale: Locale | str | None = None,
    **kwargs: Any,
) -> str:
    """Compile pattern and format it in a single call.

    For messages formatted more than once, prefer :func:compile_message and
    reuse the resulting object.

    :param pattern: the message pattern to format
    :param params: a mapping of argument names to values
    :param locale: the locale used for plural category selection and number
                   formatting
    :param kwargs: additional arguments, merged over params
    """
    return compile_message(pattern, locale=locale).format(params, **kwargs)
