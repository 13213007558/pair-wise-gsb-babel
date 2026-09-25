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

#: list of brace format conversions that are compatible to each other
_brace_format_conversion_compatibilities = [
    {None, 's'},  # the default conversion applies str(), like `!s`
    {'r', 'a'},  # `!r` and `!a` only differ in non-ASCII escaping
]

#: list of brace format presentation types that are compatible to each other
_brace_format_type_compatibilities = [
    {None, 's'},
    {'d', 'n'},
    {'x', 'X'},
    {'e', 'E'},
    {'f', 'F'},
    {'g', 'G'},
]


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

    branches: list[tuple[str, str, int]] = []
    if msgstrs[0]:
        branches.append((msgids[0], msgstrs[0], 0))
    if message.pluralizable:
        for plural_form, msgstr in enumerate(msgstrs[1:], 1):
            if msgstr:
                branches.append((msgids[1], msgstr, plural_form))

    for msgid, msgstr, plural_form in branches:
        try:
            _validate_brace_format(msgid, msgstr)
        except TranslationError as error:
            location = f'message {msgids[0]!r}'
            if message.pluralizable:
                location += f', plural form {plural_form}'
            raise TranslationError(f'{error} ({location})') from None


def _validate_brace_format(format: str, alternative: str) -> None:
    """Test brace format string "alternative" against "format".  "format" can
    be the msgid of a message and "alternative" one of the msgstrs.  The two
    arguments are not interchangeable as "alternative" may contain less
    placeholders if "format" uses named placeholders.

    The placeholders of both strings are compared statically; no formatting
    is performed, so no attributes or items of the eventual format arguments
    are accessed.  Placeholders may be reordered, but both strings must
    reference the same root arguments (positional or named) with the same
    access paths (attributes and subscripts), including placeholders nested
    in format specs.  Conversions and known presentation types must be
    compatible.

    If the brace formatting of "alternative" is compatible with "format"
    the function returns None, otherwise a TranslationError is raised.

    Examples for compatible format strings:

    >>> _validate_brace_format('Hello {name}!', 'Hallo {name}!')
    >>> _validate_brace_format('{0} meets {1}', '{1} meets {0}')
    >>> _validate_brace_format('{user.name} has {count:d}', '{count:d} messages for {user.name}')
    >>> _validate_brace_format('{{literal}} {name}', '{name}')
    >>> _validate_brace_format('{name}', '{name!s}')
    >>> _validate_brace_format('{count:d}', '{count:n}')

    Examples for incompatible format strings:

    >>> _validate_brace_format('{name!r:>{width}}', '{name}')
    Traceback (most recent call last):
      ...
    TranslationError: missing placeholder(s): width

    >>> _validate_brace_format('{name}', '{name} {other}')
    Traceback (most recent call last):
      ...
    TranslationError: unknown placeholder(s): other

    >>> _validate_brace_format('{user.name}', '{user}')
    Traceback (most recent call last):
      ...
    TranslationError: missing placeholder(s): user.name

    >>> _validate_brace_format('{name!r}', '{name!s}')
    Traceback (most recent call last):
      ...
    TranslationError: incompatible conversion for placeholder 'name': !r and !s are not compatible

    >>> _validate_brace_format('{count:d}', '{count:f}')
    Traceback (most recent call last):
      ...
    TranslationError: incompatible format type for placeholder 'count': 'd' and 'f' are not compatible

    >>> _validate_brace_format('{} {0}', '{} {0}')
    Traceback (most recent call last):
      ...
    TranslationError: cannot switch from automatic field numbering to manual field specification

    >>> _validate_brace_format('{name:{width}', '{name}')
    Traceback (most recent call last):
      ...
    TranslationError: invalid brace format string: ...

    This function is used by the python_brace_format checker.

    :param format: The original format string
    :param alternative: The alternative format string that should be checked
                        against format
    :raises TranslationError: on formatting errors
    """
    a = _parse_brace_format(format)
    b = _parse_brace_format(alternative)

    missing = a.keys() - b.keys()
    if missing:
        raise TranslationError(
            'missing placeholder(s): '
            + ', '.join(sorted(_format_field_reference(field) for field in missing)),
        )
    unknown = b.keys() - a.keys()
    if unknown:
        raise TranslationError(
            'unknown placeholder(s): '
            + ', '.join(sorted(_format_field_reference(field) for field in unknown)),
        )

    for field in a.keys() & b.keys():
        a_conversion, a_type = a[field]
        b_conversion, b_type = b[field]
        name = _format_field_reference(field)
        if not _compatible_brace_format(
            a_conversion, b_conversion, _brace_format_conversion_compatibilities,
        ):
            raise TranslationError(
                f'incompatible conversion for placeholder {name!r}: '
                f'{_conversion_name(a_conversion)} and {_conversion_name(b_conversion)} '
                'are not compatible',
            )
        if not _compatible_brace_format(
            a_type, b_type, _brace_format_type_compatibilities,
        ):
            raise TranslationError(
                f'incompatible format type for placeholder {name!r}: '
                f'{a_type!r} and {b_type!r} are not compatible',
            )


def _compatible_brace_format(
    a: str | None,
    b: str | None,
    compatibilities: list[set[str | None]],
) -> bool:
    if a == b:
        return True
    return any(a in group and b in group for group in compatibilities)


def _conversion_name(conversion: str | None) -> str:
    return f'!{conversion}' if conversion else 'default conversion'


#: root argument (position or name) and access path of a brace format field
_BraceFieldReference = tuple[int | str, tuple[tuple[str, str | int], ...]]


def _parse_brace_format(string: str) -> dict[_BraceFieldReference, tuple[str | None, str | None]]:
    """Parse a brace format string into a mapping of field references.

    Each field reference maps to the (conversion, presentation type) pair of
    its first occurrence.  Placeholders nested in format specs are included.
    """
    fields: dict[_BraceFieldReference, tuple[str | None, str | None]] = {}
    auto_number = 0
    numbering = None

    def parse(string: str, depth: int) -> None:
        nonlocal auto_number, numbering
        try:
            parsed = list(Formatter().parse(string))
        except ValueError as exc:
            raise TranslationError(f'invalid brace format string: {exc}') from None
        for _literal, field_name, format_spec, conversion in parsed:
            if field_name is None:
                continue
            root, path = _split_field_name(field_name)
            if root is None:
                if numbering == 'manual':
                    raise TranslationError(
                        'cannot switch from manual field specification '
                        'to automatic field numbering',
                    )
                numbering = 'auto'
                root = auto_number
                auto_number += 1
            else:
                if numbering == 'auto':
                    raise TranslationError(
                        'cannot switch from automatic field numbering '
                        'to manual field specification',
                    )
                numbering = 'manual'
            reference = (root, path)
            fields.setdefault(reference, (conversion, _extract_format_type(format_spec)))
            if '{' in format_spec:
                if depth >= 1:
                    raise TranslationError('brace format string nests too deeply')
                parse(format_spec, depth + 1)

    parse(string, 0)
    return fields


def _split_field_name(field_name: str) -> tuple[int | str | None, tuple[tuple[str, str | int], ...]]:
    """Split a brace format field name into its root argument and access path.

    The root is None for automatic field numbering, an int for explicit
    positional arguments and a str for named arguments.  The access path is
    a tuple of ('attr', name) and ('item', key) accessors describing
    attribute and subscript access on the root argument.
    """
    root_end = len(field_name)
    for separator in '.[':
        pos = field_name.find(separator)
        if pos != -1:
            root_end = min(root_end, pos)
    root = field_name[:root_end]
    path = []
    pos = root_end
    while pos < len(field_name):
        if field_name[pos] == '.':
            end = pos + 1
            while end < len(field_name) and field_name[end] not in '.[':
                end += 1
            attribute = field_name[pos + 1:end]
            if not attribute:
                raise TranslationError('empty attribute in brace format field name')
            path.append(('attr', attribute))
            pos = end
        else:  # field_name[pos] == '['
            end = field_name.find(']', pos + 1)
            if end == -1:
                raise TranslationError("missing ']' in brace format field name")
            key = field_name[pos + 1:end]
            if not key:
                raise TranslationError('empty index in brace format field name')
            path.append(('item', int(key) if key.isdigit() else key))
            pos = end + 1
    if not root:
        return None, tuple(path)
    return (int(root) if root.isdigit() else root), tuple(path)


def _extract_format_type(format_spec: str) -> str | None:
    """Extract the presentation type of a brace format spec, if there is one.

    Only the trailing character of the spec is inspected; nested format
    specs are never evaluated.
    """
    if not format_spec:
        return None
    char = format_spec[-1]
    if char.isalpha() or char == '%':
        return char
    return None


def _format_field_reference(reference: _BraceFieldReference) -> str:
    """Render a parsed field reference back to its placeholder form."""
    root, path = reference
    parts = [str(root)]
    for kind, key in path:
        if kind == 'attr':
            parts.append(f'.{key}')
        else:
            parts.append(f'[{key}]')
    return ''.join(parts)


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
