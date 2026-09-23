"""
babel.messages.checkers
~~~~~~~~~~~~~~~~~~~~~~~

Various routines that help with validation of translations.

:since: version 0.9

:copyright: (c) 2013-2026 by the Babel Team.
:license: BSD, see LICENSE for more details.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from string import Formatter
from typing import NamedTuple

from babel.messages.catalog import PYTHON_FORMAT, Catalog, Message, TranslationError

#: list of format chars that are compatible to each other
_string_format_compatibilities = [
    {'i', 'd', 'u'},
    {'x', 'X'},
    {'f', 'F', 'g', 'G'},
]

#: list of brace-format presentation types that are compatible to each other.
#: Width, precision and other format spec details are deliberately not part
#: of the compatibility check; only the presentation type is compared.
_brace_format_compatibilities = [
    {'b', 'c', 'd', 'n', 'o', 'x', 'X'},  # integer presentations
    {'e', 'E', 'f', 'F', 'g', 'G', '%'},  # float presentations
    {'', 's'},  # default / string presentations
]

#: conversions that are compatible to each other (str() is the default)
_brace_conversion_compatibilities = [
    {None, 's'},
]

_brace_field_accessor_re = re.compile(r"""
    \.(?P<attribute>[^.\[]+)
  | \[(?P<index>[^\]]*)\]
""", re.VERBOSE)

_brace_nested_field_re = re.compile(r"\{[^{}]*\}")

_brace_format_types = frozenset("bcdeEfFgGnosxX%")

_brace_formatter = Formatter()


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


class _BraceField(NamedTuple):
    """A single replacement field parsed out of a brace format string."""

    #: the argument key: an int for positional arguments, a str for named ones
    key: int | str
    #: the access path (attribute names and item keys) below the argument
    path: tuple[str | int, ...]
    #: the conversion flag ('r', 's' or 'a'), if any
    conversion: str | None
    #: the presentation type character of the format spec, or '' if none
    type: str
    #: the field name as written in the source string, for error messages
    name: str
    #: where the field was found (top-level or nested in another field)
    where: str | None


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
            if not msgstr:
                continue
            msgid = msgids[0] if idx == 0 else msgids[-1]
            try:
                _validate_brace_format(msgid, msgstr)
            except TranslationError as e:
                raise TranslationError(f'msgstr[{idx}]: {e}') from e
    elif msgstrs[0]:
        _validate_brace_format(msgids[0], msgstrs[0])


def _validate_brace_format(format: str, alternative: str) -> None:
    """Test brace format string `alternative` against `format`.

    `alternative` may reorder or omit named placeholders of `format`, but
    it must not introduce argument access paths that `format` does not
    contain, and the presentation types of shared placeholders must be
    compatible.  Only the format strings are analyzed; no attribute or
    item access is ever performed on actual objects.

    This function is used by the `python_brace_format` checker.

    :param format: The original format string
    :param alternative: The alternative format string that should be checked
                        against format
    :raises TranslationError: on formatting errors
    """
    a = _parse_brace_fields(format)
    b = _parse_brace_fields(alternative)

    if not a:
        return

    def _key_of(field: _BraceField) -> tuple[int | str, tuple[str | int, ...]]:
        return (field.key, field.path)

    def _describe(field: _BraceField) -> str:
        description = repr(field.name)
        if field.where is not None:
            description += f' (nested in the format spec of {field.where!r})'
        return description

    def _compatible_type(a_type: str, b_type: str) -> bool:
        if a_type == b_type:
            return True
        return any(
            a_type in group and b_type in group
            for group in _brace_format_compatibilities
        )

    def _compatible_conversion(a_conv: str | None, b_conv: str | None) -> bool:
        if a_conv == b_conv:
            return True
        return any(
            a_conv in group and b_conv in group
            for group in _brace_conversion_compatibilities
        )

    a_positional = [field for field in a if isinstance(field.key, int)]
    a_named = [field for field in a if isinstance(field.key, str)]
    b_positional = [field for field in b if isinstance(field.key, int)]
    b_named = [field for field in b if isinstance(field.key, str)]

    if a_positional:
        # Positional arguments may not be omitted and no new positional
        # argument may be introduced; explicit and automatic numbering
        # resolve to the same indices, so reordering is fine.
        a_indices = {field.key for field in a_positional}
        b_indices = {field.key for field in b_positional}
        if a_indices != b_indices:
            raise TranslationError('positional format placeholders are unbalanced')
        a_positional_map = {_key_of(field): field for field in a_positional}
        for field in b_positional:
            original = a_positional_map.get(_key_of(field))
            if original is None:
                raise TranslationError(
                    f'unknown positional placeholder {_describe(field)}',
                )
            if not _compatible_type(original.type, field.type):
                raise TranslationError(
                    f'incompatible format for placeholder {_describe(field)}: '
                    f'{field.type!r} and {original.type!r} are not compatible',
                )
            if not _compatible_conversion(original.conversion, field.conversion):
                raise TranslationError(
                    f'incompatible conversion for placeholder {_describe(field)}: '
                    f'{field.conversion!r} and {original.conversion!r} are not compatible',
                )

    if b_named:
        # Named placeholders may be omitted or reordered, but the
        # translation must not use access paths the original does not have.
        a_named_map = {_key_of(field): field for field in a_named}
        for field in b_named:
            original = a_named_map.get(_key_of(field))
            if original is None:
                raise TranslationError(
                    f'unknown named placeholder {_describe(field)}',
                )
            if not _compatible_type(original.type, field.type):
                raise TranslationError(
                    f'incompatible format for placeholder {_describe(field)}: '
                    f'{field.type!r} and {original.type!r} are not compatible',
                )
            if not _compatible_conversion(original.conversion, field.conversion):
                raise TranslationError(
                    f'incompatible conversion for placeholder {_describe(field)}: '
                    f'{field.conversion!r} and {original.conversion!r} are not compatible',
                )


def _parse_brace_fields(string: str, where: str | None = None) -> list[_BraceField]:
    """Parse `string` into a list of `_BraceField`\\s.

    Fields nested in the format spec of another field are parsed
    recursively and reported with `where` set to the enclosing field name.
    """
    try:
        parsed = list(_brace_formatter.parse(string))
    except ValueError as e:
        raise TranslationError(f'invalid brace format string: {e}') from e

    fields: list[_BraceField] = []
    auto_index = 0
    numbering: str | None = None
    for _literal, field_name, format_spec, conversion in parsed:
        if field_name is None:
            continue
        key, path = _parse_brace_field_name(field_name)
        if key is None:
            if numbering == 'manual':
                raise TranslationError(
                    'cannot switch from manual field specification to '
                    'automatic field numbering',
                )
            numbering = 'auto'
            key = auto_index
            auto_index += 1
        elif isinstance(key, int):
            if numbering == 'auto':
                raise TranslationError(
                    'cannot switch from automatic field numbering to '
                    'manual field specification',
                )
            numbering = 'manual'
        if conversion is not None and conversion not in ('r', 's', 'a'):
            raise TranslationError(
                f'unknown conversion specifier {conversion!r} in field {field_name!r}',
            )
        fields.append(_BraceField(
            key=key,
            path=path,
            conversion=conversion,
            type=_brace_format_spec_type(format_spec),
            name=field_name,
            where=where,
        ))
        if '{' in format_spec:
            fields.extend(_parse_brace_fields(format_spec, where=field_name))
    return fields


def _parse_brace_field_name(field_name: str) -> tuple[int | str | None, tuple[str | int, ...]]:
    """Split a brace format field name into the argument key and the
    attribute/item access path below it.

    Returns ``(None, path)`` for automatic field numbering, ``(int, path)``
    for explicit positional arguments and ``(str, path)`` for named ones.
    """
    split = len(field_name)
    for char in '.[':
        pos = field_name.find(char)
        if pos != -1:
            split = min(split, pos)
    arg_name = field_name[:split]
    accessors = field_name[split:]

    path: list[str | int] = []
    pos = 0
    while pos < len(accessors):
        match = _brace_field_accessor_re.match(accessors, pos)
        if match is None:
            raise TranslationError(f'invalid field name {field_name!r}')
        attribute = match.group('attribute')
        if attribute is not None:
            path.append(attribute)
        else:
            index = match.group('index')
            path.append(int(index) if index.isdigit() else index)
        pos = match.end()

    if arg_name == '':
        key: int | str | None = None
    elif arg_name.isdigit():
        key = int(arg_name)
    else:
        key = arg_name
    return key, tuple(path)


def _brace_format_spec_type(format_spec: str) -> str:
    """Extract the presentation type character from a format spec,
    ignoring any nested replacement fields.  Returns '' if the spec does
    not specify a presentation type.
    """
    spec = format_spec
    while '{' in spec:
        stripped = _brace_nested_field_re.sub('', spec)
        if stripped == spec:
            break
        spec = stripped
    if spec and spec[-1] in _brace_format_types:
        return spec[-1]
    return ''


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
