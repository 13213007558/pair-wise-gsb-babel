"""
babel.messages.checkers
~~~~~~~~~~~~~~~~~~~~~~~

Various routines that help with validation of translations.

:since: version 0.9

:copyright: (c) 2013-2026 by the Babel Team.
:license: BSD, see LICENSE for more details.
"""

from __future__ import annotations

from collections.abc import Callable
from string import Formatter

from babel.messages.catalog import PYTHON_FORMAT, Catalog, Message, TranslationError

#: list of format chars that are compatible to each other
_string_format_compatibilities = [
    {'i', 'd', 'u'},
    {'x', 'X'},
    {'f', 'F', 'g', 'G'},
]

#: list of brace-format conversion characters that are compatible to each other
_brace_conversion_compatibilities = [
    {None, 's'},
]

#: list of brace-format presentation types that are compatible to each other
_brace_format_type_compatibilities = [
    {'b', 'c', 'd', 'o', 'x', 'X', 'n'},
    {'e', 'E', 'f', 'F', 'g', 'G', '%'},
    {'s', None},
]

#: conversion characters defined by the brace format syntax
_brace_conversions = frozenset({'r', 's', 'a'})


def num_plurals(catalog: Catalog | None, message: Message) -> None:
    """Verify the number of plurals in the translation."""
    if not message.pluralizable:
        if not isinstance(message.string, str):
            raise TranslationError("Found plural forms for non-pluralizable message")
        return

    # skip further tests if no catalog is provided.
    elif catalog is None:
        return

    msgstrs = message.string
    if not isinstance(msgstrs, (list, tuple)):
        msgstrs = (msgstrs,)
    if len(msgstrs) != catalog.num_plurals:
        raise TranslationError(
            f"Wrong number of plural forms (expected {catalog.num_plurals})",
        )


def python_format(catalog: Catalog | None, message: Message) -> None:
    """Verify the format string placeholders in the translation."""
    if 'python-format' not in message.flags:
        return
    msgids = message.id
    if not isinstance(msgids, (list, tuple)):
        msgids = (msgids,)
    msgstrs = message.string
    if not isinstance(msgstrs, (list, tuple)):
        msgstrs = (msgstrs,)

    if msgstrs[0]:
        _validate_format(msgids[0], msgstrs[0])
    if message.pluralizable:
        for msgstr in msgstrs[1:]:
            if msgstr:
                _validate_format(msgids[1], msgstr)


def _validate_format(format: str, alternative: str) -> None:
    """Test format string `alternative` against `format`.  `format` can be the
    msgid of a message and `alternative` one of the `msgstr`\\s.  The two
    arguments are not interchangeable as `alternative` may contain less
    placeholders if `format` uses named placeholders.

    If the string formatting of `alternative` is compatible to `format` the
    function returns `None`, otherwise a `TranslationError` is raised.

    Examples for compatible format strings:

    >>> _validate_format('Hello %s!', 'Hallo %s!')
    >>> _validate_format('Hello %i!', 'Hallo %d!')

    Example for an incompatible format strings:

    >>> _validate_format('Hello %(name)s!', 'Hallo %s!')
    Traceback (most recent call last):
      ...
    TranslationError: the format strings are of different kinds

    This function is used by the `python_format` checker.

    :param format: The original format string
    :param alternative: The alternative format string that should be checked
                        against format
    :raises TranslationError: on formatting errors
    """

    def _parse(string: str) -> list[tuple[str, str]]:
        result: list[tuple[str, str]] = []
        for match in PYTHON_FORMAT.finditer(string):
            name, format, typechar = match.groups()
            if typechar == '%' and name is None:
                continue
            result.append((name, str(typechar)))
        return result

    def _compatible(a: str, b: str) -> bool:
        if a == b:
            return True
        for set in _string_format_compatibilities:
            if a in set and b in set:
                return True
        return False

    def _check_positional(results: list[tuple[str, str]]) -> bool:
        positional = None
        for name, _char in results:
            if positional is None:
                positional = name is None
            else:
                if (name is None) != positional:
                    raise TranslationError(
                        'format string mixes positional and named placeholders',
                    )
        return bool(positional)

    a = _parse(format)
    b = _parse(alternative)

    if not a:
        return

    # now check if both strings are positional or named
    a_positional = _check_positional(a)
    b_positional = _check_positional(b)
    if a_positional and not b_positional and not b:
        raise TranslationError('placeholders are incompatible')
    elif a_positional != b_positional:
        raise TranslationError('the format strings are of different kinds')

    # if we are operating on positional strings both must have the
    # same number of format chars and those must be compatible
    if a_positional:
        if len(a) != len(b):
            raise TranslationError('positional format placeholders are unbalanced')
        for idx, ((_, first), (_, second)) in enumerate(zip(a, b)):
            if not _compatible(first, second):
                raise TranslationError(
                    f'incompatible format for placeholder {idx + 1:d}: '
                    f'{first!r} and {second!r} are not compatible',
                )

    # otherwise the second string must not have names the first one
    # doesn't have and the types of those included must be compatible
    else:
        type_map = dict(a)
        for name, typechar in b:
            if name not in type_map:
                raise TranslationError(f'unknown named placeholder {name!r}')
            elif not _compatible(typechar, type_map[name]):
                raise TranslationError(
                    f'incompatible format for placeholder {name!r}: '
                    f'{typechar!r} and {type_map[name]!r} are not compatible',
                )


def python_brace_format(catalog: Catalog | None, message: Message) -> None:
    """Verify the brace format string placeholders in the translation."""
    if 'python-brace-format' not in message.flags:
        return
    msgids = message.id
    if not isinstance(msgids, (list, tuple)):
        msgids = (msgids,)
    msgstrs = message.string
    if not isinstance(msgstrs, (list, tuple)):
        msgstrs = (msgstrs,)

    if message.pluralizable:
        for idx, msgstr in enumerate(msgstrs):
            if msgstr:
                msgid = msgids[0] if idx == 0 else msgids[1]
                try:
                    _validate_brace_format(msgid, msgstr)
                except TranslationError as error:
                    raise TranslationError(f'plural form {idx}: {error}') from error
    elif msgstrs[0]:
        _validate_brace_format(msgids[0], msgstrs[0])


def _validate_brace_format(format: str, alternative: str) -> None:
    """Test brace format string `alternative` against `format`.  `format` can
    be the msgid of a message and `alternative` one of the `msgstr`\\s.  The
    two arguments are not interchangeable.

    The strings are analyzed statically; they are never actually formatted
    against any arguments, so no user object is ever accessed.  If the
    placeholders of `alternative` are compatible to those of `format` the
    function returns `None`, otherwise a `TranslationError` is raised.

    Examples for compatible format strings:

    >>> _validate_brace_format('Hello, {name}!', 'Hallo, {name}!')
    >>> _validate_brace_format('{0} {1}', '{1} {0}')
    >>> _validate_brace_format('{count:d}', '{count:x}')

    Examples for incompatible format strings:

    >>> _validate_brace_format('{name!r:>{width}}', '{name}')
    Traceback (most recent call last):
      ...
    TranslationError: incompatible conversion for placeholder 'name': 'r' and None are not compatible

    >>> _validate_brace_format('{name} {pet}', '{name}')
    Traceback (most recent call last):
      ...
    TranslationError: missing placeholder 'pet'

    >>> _validate_brace_format('{name}', '{name} {pet}')
    Traceback (most recent call last):
      ...
    TranslationError: unknown placeholder 'pet'

    This function is used by the `python_brace_format` checker.

    :param format: The original format string
    :param alternative: The alternative format string that should be checked
                        against format
    :raises TranslationError: on formatting errors
    """

    def _index(placeholders: list[tuple]) -> dict:
        result: dict = {}
        for root, path, conversion, format_type in placeholders:
            uses = result.setdefault(root, {}).setdefault(path, set())
            uses.add((conversion, format_type))
        return result

    def _sorted_roots(index: dict) -> list:
        # positional (integer) roots first, then named ones
        return sorted(index, key=lambda root: (isinstance(root, str), root))

    a = _index(_BraceFormatParser().parse(format))
    b = _index(_BraceFormatParser().parse(alternative))

    if not a:
        return

    for root in _sorted_roots(a):
        if root not in b:
            raise TranslationError(
                f'missing placeholder {_render_brace_placeholder(root)!r}',
            )
        a_paths, b_paths = a[root], b[root]
        for path in sorted(a_paths):
            field = _render_brace_placeholder(root, path)
            if path not in b_paths:
                raise TranslationError(f'missing placeholder {field!r}')
            a_uses = sorted(a_paths[path], key=lambda use: (str(use[0]), str(use[1])))
            b_uses = sorted(b_paths[path], key=lambda use: (str(use[0]), str(use[1])))
            for conversion, format_type in a_uses:
                if not any(
                    _brace_compatible(conversion, other, _brace_conversion_compatibilities)
                    for other, _ in b_uses
                ):
                    raise TranslationError(
                        f'incompatible conversion for placeholder {field!r}: '
                        f'{conversion!r} and {b_uses[0][0]!r} are not compatible',
                    )
                if not any(
                    _brace_compatible(format_type, other, _brace_format_type_compatibilities)
                    for _, other in b_uses
                ):
                    raise TranslationError(
                        f'incompatible format for placeholder {field!r}: '
                        f'{format_type!r} and {b_uses[0][1]!r} are not compatible',
                    )
            for conversion, format_type in b_uses:
                if not any(
                    _brace_compatible(conversion, other, _brace_conversion_compatibilities)
                    for other, _ in a_uses
                ):
                    raise TranslationError(
                        f'incompatible conversion for placeholder {field!r}: '
                        f'{conversion!r} and {a_uses[0][0]!r} are not compatible',
                    )
                if not any(
                    _brace_compatible(format_type, other, _brace_format_type_compatibilities)
                    for _, other in a_uses
                ):
                    raise TranslationError(
                        f'incompatible format for placeholder {field!r}: '
                        f'{format_type!r} and {a_uses[0][1]!r} are not compatible',
                    )
        for path in sorted(b_paths):
            if path not in a_paths:
                raise TranslationError(
                    f'unknown placeholder {_render_brace_placeholder(root, path)!r}',
                )
    for root in _sorted_roots(b):
        if root not in a:
            raise TranslationError(
                f'unknown placeholder {_render_brace_placeholder(root)!r}',
            )


def _brace_compatible(
    value: str | None, other: str | None, compatibilities: list[set],
) -> bool:
    if value == other:
        return True
    return any(
        value in compatibility and other in compatibility for compatibility in compatibilities
    )


def _render_brace_placeholder(root: int | str, path: tuple[tuple[str, str], ...] = ()) -> str:
    """Render a placeholder root and access path the way they appear in the
    format string, e.g. ``user.address[0]``.
    """
    result = [str(root)]
    for kind, key in path:
        if kind == 'attribute':
            result.append(f'.{key}')
        else:
            result.append(f'[{key}]')
    return ''.join(result)


def _split_brace_field_name(field_name: str) -> tuple[str, tuple[tuple[str, str], ...]]:
    """Split a brace-format field name into its root argument name and the
    access path (attribute and subscript lookups) applied to it.

    >>> _split_brace_field_name('user.address[0]')
    ('user', (('attribute', 'address'), ('item', '0')))
    >>> _split_brace_field_name('0')
    ('0', ())
    """
    path: list[tuple[str, str]] = []
    tail = field_name
    root_end = len(tail)
    for idx, char in enumerate(tail):
        if char in '.[':
            root_end = idx
            break
    root, tail = tail[:root_end], tail[root_end:]
    while tail:
        if tail[0] == '.':
            end = len(tail)
            for idx, char in enumerate(tail[1:], 1):
                if char in '.[':
                    end = idx
                    break
            attribute = tail[1:end]
            if not attribute:
                raise TranslationError(
                    f'invalid field name {field_name!r} in brace format string',
                )
            path.append(('attribute', attribute))
            tail = tail[end:]
        else:  # tail[0] == '['
            end = tail.find(']')
            if end == -1:
                raise TranslationError(
                    f'invalid field name {field_name!r} in brace format string',
                )
            path.append(('item', tail[1:end]))
            tail = tail[end + 1 :]
    return root, tuple(path)


def _brace_format_type(format_spec: str) -> str | None:
    """Extract the presentation type character from a brace format spec,
    ignoring replacement fields nested within it.

    >>> _brace_format_type('>10.2f')
    'f'
    >>> _brace_format_type('>{width}') is None
    True
    """
    static = []
    depth = 0
    for char in format_spec:
        if char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
        elif not depth:
            static.append(char)
    if static and (static[-1].isalpha() or static[-1] == '%'):
        return static[-1]
    return None


class _BraceFormatParser:
    """Statically parse a brace format string into the placeholders it uses.

    The string is never formatted against real arguments; the analysis is
    purely syntactic, so no user object is ever touched.
    """

    def __init__(self) -> None:
        # (root, access path, conversion, presentation type) tuples; the root
        # is an integer for positional arguments and a string for named ones
        self.placeholders: list[tuple] = []
        self._auto_numbering: bool | None = None
        self._auto_index = 0

    def parse(self, string: str) -> list[tuple]:
        try:
            # `Formatter.parse` returns a lazy iterator, so syntax errors
            # are only raised while it is being consumed
            parsed = list(Formatter().parse(string))
        except ValueError as error:
            raise TranslationError(f'invalid brace format string: {error}') from None
        for _literal, field_name, format_spec, conversion in parsed:
            if field_name is None:
                # literal text only (e.g. escaped '{{' and '}}' braces)
                continue
            self._parse_field(field_name, format_spec, conversion)
        return self.placeholders

    def _parse_field(self, field_name: str, format_spec: str, conversion: str | None) -> None:
        root_name, path = _split_brace_field_name(field_name)
        root = self._resolve_root(root_name)
        if conversion is not None and conversion not in _brace_conversions:
            raise TranslationError(f'unknown conversion specifier {conversion!r}')
        self.placeholders.append((root, path, conversion, _brace_format_type(format_spec)))
        if '{' in format_spec:
            # replacement fields nested in the format spec reference arguments
            # of their own and share the auto-numbering state
            self.parse(format_spec)

    def _resolve_root(self, root_name: str) -> int | str:
        if not root_name:
            if self._auto_numbering is False:
                raise TranslationError(
                    'cannot switch from manual field specification '
                    'to automatic field numbering',
                )
            self._auto_numbering = True
            root = self._auto_index
            self._auto_index += 1
            return root
        if root_name.isascii() and root_name.isdigit():
            if self._auto_numbering is True:
                raise TranslationError(
                    'cannot switch from automatic field numbering '
                    'to manual field specification',
                )
            self._auto_numbering = False
            return int(root_name)
        return root_name


def _find_checkers() -> list[Callable[[Catalog | None, Message], object]]:
    from babel.messages._compat import find_entrypoints

    checkers: list[Callable[[Catalog | None, Message], object]] = []
    checkers.extend(load() for (name, load) in find_entrypoints('babel.checkers'))
    if len(checkers) == 0:
        # if entrypoints are not available or no usable egg-info was found
        # (see #230), just resort to hard-coded checkers
        return [num_plurals, python_format, python_brace_format]
    return checkers


checkers: list[Callable[[Catalog | None, Message], object]] = _find_checkers()
