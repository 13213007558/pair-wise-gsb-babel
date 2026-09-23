"""
babel.messages.icu_plural
~~~~~~~~~~~~~~~~~~~~~~~~~

ICU MessageFormat style plural support for message catalogs.

This module implements a parseable and evaluable AST for the plural
subset of ICU MessageFormat, for example::

    {count, plural, offset:1 =0 {No files} =1 {just now} one {just now} other {# files}}

Selection first considers explicit ``=n`` values (matched against the
original number), then the CLDR plural category of ``value - offset``
for the locale.  ``#`` within a sub-message formats the number with
the offset deducted.

:copyright: (c) 2013-2026 by the Babel Team.
:license: BSD, see LICENSE for more details.
"""

from __future__ import annotations

import decimal
import re
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from babel.core import Locale, default_locale
from babel.numbers import format_decimal

__all__ = [
    'ICUMessage',
    'ICUPluralError',
]

#: The CLDR plural categories usable as keyword selectors.
PLURAL_CATEGORIES = frozenset({'zero', 'one', 'two', 'few', 'many', 'other'})

_IDENTIFIER_RE = re.compile(r'[A-Za-z0-9_]+')
_EXPLICIT_VALUE_RE = re.compile(r'-?\d+(?:\.\d+)?')
_OFFSET_RE = re.compile(r'\d+')


class ICUPluralError(ValueError):
    """Raised when an ICU plural message cannot be parsed or evaluated.

    The ``position`` attribute holds the 0-based offset into the source
    string at which the problem was detected, or ``None`` if the error
    is not tied to a specific location.
    """

    def __init__(self, message: str, position: int | None = None) -> None:
        self.position = position
        if position is not None:
            message = f"{message} (position {position})"
        super().__init__(message)


def _to_decimal(value: Any) -> decimal.Decimal:
    """Coerce a number to a `decimal.Decimal` without introducing
    binary floating point error, so that explicit value matching and
    offset deduction use the same precision for ints, floats, strings
    and Decimals.
    """
    if isinstance(value, decimal.Decimal):
        return value
    if isinstance(value, int):
        return decimal.Decimal(value)
    if isinstance(value, float):
        # Go through the string representation so that 0.1 stays 0.1
        # instead of becoming 0.1000000000000000055511151231257827...
        return decimal.Decimal(str(value))
    try:
        return decimal.Decimal(str(value))
    except decimal.InvalidOperation:
        raise ICUPluralError(f"plural variable value is not a number: {value!r}") from None


class _EvalContext:
    __slots__ = ('locale', 'number', 'plural_rule', 'variables')

    def __init__(
        self,
        variables: Mapping[str, Any],
        locale: Locale,
        number: decimal.Decimal | None = None,
    ) -> None:
        self.variables = variables
        self.locale = locale
        self.plural_rule = locale.plural_form
        self.number = number

    def for_number(self, number: decimal.Decimal) -> _EvalContext:
        return _EvalContext(self.variables, self.locale, number)


@dataclass(frozen=True)
class _Literal:
    text: str

    def evaluate(self, ctx: _EvalContext) -> str:
        return self.text


@dataclass(frozen=True)
class _Argument:
    name: str

    def evaluate(self, ctx: _EvalContext) -> str:
        try:
            return str(ctx.variables[self.name])
        except KeyError:
            raise ICUPluralError(f"no value given for argument {self.name!r}") from None


@dataclass(frozen=True)
class _NumberSign:
    """The ICU ``#`` placeholder: the number of the enclosing plural,
    with its offset deducted."""

    def evaluate(self, ctx: _EvalContext) -> str:
        if ctx.number is None:  # pragma: no cover - the parser prevents this
            return '#'
        return format_decimal(ctx.number, locale=ctx.locale)


@dataclass(frozen=True)
class _Plural:
    variable: str
    offset: int
    explicit: dict[decimal.Decimal, tuple]  # =n branches, keyed by exact value
    categories: dict[str, tuple]  # keyword branches, keyed by CLDR category

    def evaluate(self, ctx: _EvalContext) -> str:
        try:
            raw_value = ctx.variables[self.variable]
        except KeyError:
            raise ICUPluralError(
                f"no value given for plural variable {self.variable!r}",
            ) from None
        value = _to_decimal(raw_value)
        shifted = value - self.offset
        if value in self.explicit:
            # Explicit values match the original number, before the
            # offset is deducted.
            branch = self.explicit[value]
        else:
            tag = ctx.plural_rule(shifted)
            branch = self.categories.get(tag, self.categories['other'])
        return _evaluate(branch, ctx.for_number(shifted))


def _evaluate(parts: tuple, ctx: _EvalContext) -> str:
    return ''.join(part.evaluate(ctx) for part in parts)


class ICUMessage:
    """A parsed ICU message with plural support.

    >>> msg = ICUMessage.parse('{count, plural, offset:1 =0 {No files} =1 {just now} one {just now} other {# files}}')
    >>> msg.format({'count': 0}, locale='en')
    'No files'
    >>> msg.format({'count': 1}, locale='en')
    'just now'
    >>> msg.format({'count': 2}, locale='en')
    'just now'
    >>> msg.format({'count': 5}, locale='en')
    '4 files'

    Use `parse` to compile a message string and `format` to evaluate it
    with a mapping of variables and a locale.
    """

    __slots__ = ('parts', 'source')

    def __init__(self, parts: tuple, source: str | None = None) -> None:
        self.parts = parts
        self.source = source

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.source!r}>"

    @classmethod
    def parse(cls, string: str) -> ICUMessage:
        """Parse an ICU message string into an `ICUMessage`.

        :param string: the message to parse
        :raise ICUPluralError: if the message is malformed; the error
                               carries the ``position`` of the problem
        """
        return _parse_cached(string)

    def format(
        self,
        variables: Mapping[str, Any] | None = None,
        locale: Locale | str | None = None,
    ) -> str:
        """Evaluate the message with the given variables.

        :param variables: a mapping of argument names to values; plural
                          variables must be numbers
        :param locale: the locale whose CLDR plural rules and number
                       formatting are used
        :raise ICUPluralError: if a variable is missing or not a number
        """
        if variables is None:
            variables = {}
        if not isinstance(locale, Locale):
            locale = Locale.parse(locale or default_locale('LC_NUMERIC'))
        return _evaluate(self.parts, _EvalContext(variables, locale))


@lru_cache(maxsize=256)
def _parse_cached(string: str) -> ICUMessage:
    return ICUMessage(tuple(_Parser(string).parse()), source=string)


class _Parser:
    """Recursive descent parser for the ICU plural message grammar::

        message    = (literal | argument | plural)*
        argument   = '{' name '}'
        plural     = '{' name ',' 'plural' ',' ('offset:' number)? selector* '}'
        selector   = explicit_value '{' message '}' | category '{' message '}'
        explicit_value = '=' number
        category   = 'zero' | 'one' | 'two' | 'few' | 'many' | 'other'

    Within a plural sub-message, ``#`` is the number placeholder.
    Sub-messages may themselves contain nested plurals.
    """

    def __init__(self, source: str) -> None:
        self.source = source
        self.pos = 0

    def parse(self) -> list:
        parts = self.parse_message(in_plural=False)
        if self.pos != len(self.source):
            raise self.error("unmatched '}'")
        return parts

    def error(self, message: str, position: int | None = None) -> ICUPluralError:
        return ICUPluralError(message, self.pos if position is None else position)

    def peek(self) -> str | None:
        if self.pos < len(self.source):
            return self.source[self.pos]
        return None

    def skip_ws(self) -> None:
        source = self.source
        while self.pos < len(source) and source[self.pos].isspace():
            self.pos += 1

    def expect(self, char: str, message: str) -> None:
        if self.peek() != char:
            raise self.error(message)
        self.pos += 1

    def parse_identifier(self, message: str) -> str:
        match = _IDENTIFIER_RE.match(self.source, self.pos)
        if match is None:
            raise self.error(message)
        self.pos = match.end()
        return match.group()

    def parse_message(self, in_plural: bool) -> list:
        """Parse literal text and placeholders up to the closing ``}``
        (or the end of the string).  The position is left on the
        closing brace, if any.
        """
        parts = []
        literal_start = self.pos
        while self.pos < len(self.source):
            char = self.source[self.pos]
            if char == '}':
                break
            if char == '{':
                self._flush_literal(parts, literal_start)
                parts.append(self.parse_placeholder())
                literal_start = self.pos
            elif char == '#' and in_plural:
                self._flush_literal(parts, literal_start)
                parts.append(_NumberSign())
                self.pos += 1
                literal_start = self.pos
            else:
                self.pos += 1
        self._flush_literal(parts, literal_start)
        return parts

    def _flush_literal(self, parts: list, start: int) -> None:
        if self.pos > start:
            parts.append(_Literal(self.source[start:self.pos]))

    def parse_placeholder(self):
        brace_pos = self.pos
        self.pos += 1
        self.skip_ws()
        name = self.parse_identifier("expected an argument name after '{'")
        self.skip_ws()
        if self.peek() == '}':
            self.pos += 1
            return _Argument(name)
        self.expect(',', "expected ',' or '}' after the argument name")
        self.skip_ws()
        type_pos = self.pos
        type_name = self.parse_identifier("expected a placeholder type such as 'plural'")
        if type_name != 'plural':
            raise self.error(f"unsupported placeholder type {type_name!r}", type_pos)
        self.skip_ws()
        self.expect(',', "expected ',' after 'plural'")
        self.skip_ws()
        offset = 0
        if self.source.startswith('offset:', self.pos):
            offset = self.parse_offset()
        explicit: dict[decimal.Decimal, tuple] = {}
        categories: dict[str, tuple] = {}
        while True:
            self.skip_ws()
            char = self.peek()
            if char is None:
                raise self.error('unterminated plural expression', brace_pos)
            if char == '}':
                self.pos += 1
                break
            if char == '=':
                value_pos = self.pos
                self.pos += 1
                value = self.parse_explicit_value(value_pos)
                if value in explicit:
                    raise self.error(f"duplicate explicit value '={value}'", value_pos)
                explicit[value] = tuple(self.parse_sub_message())
            else:
                keyword_pos = self.pos
                keyword = self.parse_identifier('expected a plural selector')
                if keyword not in PLURAL_CATEGORIES:
                    raise self.error(f"invalid plural category {keyword!r}", keyword_pos)
                if keyword in categories:
                    raise self.error(f"duplicate plural category {keyword!r}", keyword_pos)
                categories[keyword] = tuple(self.parse_sub_message())
        if 'other' not in categories:
            raise self.error("missing required 'other' plural category", brace_pos)
        return _Plural(name, offset, explicit, categories)

    def parse_offset(self) -> int:
        self.pos += len('offset:')
        self.skip_ws()
        value_pos = self.pos
        match = _OFFSET_RE.match(self.source, self.pos)
        if match is None or self.source[match.end():match.end() + 1] == '.':
            raise self.error(
                'invalid plural offset; expected a non-negative integer',
                value_pos,
            )
        self.pos = match.end()
        return int(match.group())

    def parse_explicit_value(self, equals_pos: int) -> decimal.Decimal:
        self.skip_ws()
        match = _EXPLICIT_VALUE_RE.match(self.source, self.pos)
        if match is None:
            raise self.error("expected a number after '='", equals_pos)
        self.pos = match.end()
        return decimal.Decimal(match.group())

    def parse_sub_message(self) -> list:
        self.skip_ws()
        self.expect('{', "expected '{' to start a sub-message")
        parts = self.parse_message(in_plural=True)
        if self.peek() != '}':
            raise self.error('unterminated sub-message')
        self.pos += 1
        return parts
