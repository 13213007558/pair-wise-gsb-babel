"""
babel.messages.checkers
~~~~~~~~~~~~~~~~~~~~~~~

Various routines that help with validation of translations.

:since: version 0.9

:copyright: (c) 2013-2026 by the Babel Team.
:license: BSD, see LICENSE for more details.
"""

from __future__ import annotations

import string
from collections.abc import Callable

from babel.messages.catalog import PYTHON_FORMAT, Catalog, Message, TranslationError

#: list of format chars that are compatible to each other
_string_format_compatibilities = [
    {'i', 'd', 'u'},
    {'x', 'X'},
    {'f', 'F', 'g', 'G'},
]

#: list of brace format presentation types that are compatible to each other
_brace_format_type_compatibilities = [
    {'b', 'c', 'd', 'o', 'x', 'X', 'n'},  # integer presentation types
    {'e', 'E', 'f', 'F', 'g', 'G', '%', 'n'},  # floating point presentation types
]

#: presentation type characters allowed in Python brace format specs
_BRACE_FORMAT_TYPE_CHARS = frozenset('bcdeEfFgGnosxX%')

#: formatter used by the brace format checker to parse format strings
_BRACE_FORMATTER = string.Formatter()


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
    """Verify the format string placeholders in the translation.

    This checker is only run for messages flagged with
    ``python-brace-format`` (i.e. messages using the ``str.format()``
    or f-string ``{}`` syntax). It verifies that the translation does not
    reference placeholders that were not present in the original string
    and that the placeholders that are used are compatible with the
    original ones.
    """
    if 'python-brace-format' not in message.flags:
        return
    msgids = message.id
    if not isinstance(msgids, (list, tuple)):
        msgids = (msgids,)
    msgstrs = message.string
    if not isinstance(msgstrs, (list, tuple)):
        msgstrs = (msgstrs,)

    for idx, msgstr in enumerate(msgstrs):
        if not msgstr:
            continue
        msgid = msgids[0] if idx == 0 else msgids[-1]
        try:
            _validate_python_brace_format(msgid, msgstr)
        except TranslationError as error:
            if message.pluralizable:
                raise TranslationError(f'msgstr[{idx}]: {error}') from error
            raise


def _validate_python_brace_format(format: str, alternative: str) -> None:
    """Test brace format string `alternative` against `format`.

    `format` can be the msgid of a message and `alternative` one of the
    `msgstr`\\s. The two arguments are not interchangeable as `alternative`
    may contain less placeholders than `format` (i.e. translations may
    omit placeholders or reorder them), but it must not contain
    placeholders that are not present in `format`.

    If the format string of `alternative` is compatible to `format` the
    function returns `None`, otherwise a `TranslationError` is raised.

    Examples for compatible format strings:

    >>> _validate_python_brace_format('Hello {name}!', 'Hallo {name}!')
    >>> _validate_python_brace_format('{0} {1}', '{1} {0}')
    >>> _validate_python_brace_format('{price:.2f}', '{price:.3f}')

    Examples for incompatible format strings:

    >>> _validate_python_brace_format('{name}', '{nam}')
    Traceback (most recent call last):
      ...
    TranslationError: unknown placeholder 'nam'

    >>> _validate_python_brace_format('{count:d}', '{count:s}')
    Traceback (most recent call last):
      ...
    TranslationError: incompatible format for placeholder 'count': 's' and 'd' are not compatible

    This function is used by the `python_brace_format` checker.

    :param format: The original format string
    :param alternative: The alternative format string that should be checked
                        against format
    :raises TranslationError: on formatting errors
    """
    try:
        old_fields = _parse_python_brace_format(format)
    except ValueError as exc:
        raise TranslationError(f'invalid format string in msgid: {exc}') from exc
    try:
        new_fields = _parse_python_brace_format(alternative)
    except ValueError as exc:
        raise TranslationError(f'invalid format string: {exc}') from exc

    old: dict[tuple[int | str, ...], dict[str, set]] = {}
    for path, conversion, presentation_type, _display, _parent in old_fields:
        entry = old.setdefault(path, {'conversions': set(), 'types': set()})
        entry['conversions'].add(conversion)
        if presentation_type is not None:
            entry['types'].add(presentation_type)

    for path, conversion, presentation_type, display, parent in new_fields:
        if path not in old:
            where = f' in format spec of {parent!r}' if parent is not None else ''
            raise TranslationError(f'unknown placeholder {display!r}{where}')
        entry = old[path]
        if conversion not in entry['conversions']:
            expected = ', '.join(sorted(repr(c) for c in entry['conversions']))
            raise TranslationError(
                f'incompatible conversion for placeholder {display!r}: '
                f'expected {expected}, got {conversion!r}',
            )
        if presentation_type is not None and entry['types']:
            if not any(
                _brace_format_type_compatible(presentation_type, type_)
                for type_ in entry['types']
            ):
                expected = sorted(entry['types'])[0]
                raise TranslationError(
                    f'incompatible format for placeholder {display!r}: '
                    f'{presentation_type!r} and {expected!r} are not compatible',
                )


def _brace_format_type_compatible(a: str, b: str) -> bool:
    if a == b:
        return True
    for group in _brace_format_type_compatibilities:
        if a in group and b in group:
            return True
    return False


def _parse_python_brace_format(
    format_string: str,
) -> list[tuple[tuple[int | str, ...], str | None, str | None, str, str | None]]:
    """Parse a Python brace format string into a list of placeholders.

    Each placeholder is a ``(path, conversion, presentation_type, display,
    parent)`` tuple, where:

    * ``path`` is the canonical access path of the placeholder: positional
      argument indices are `int`\\s (automatic field numbering is resolved
      to positional indices), named arguments, attribute names and mapping
      keys are `str`\\s.
    * ``conversion`` is the ``!`` conversion flag (``'r'``, ``'s'`` or
      ``'a'``) or `None`.
    * ``presentation_type`` is the type character of the format spec or
      `None` if the spec does not contain one.
    * ``display`` is a human-readable representation of the placeholder
      for error messages.
    * ``parent`` is the ``display`` of the placeholder this placeholder is
      nested in (for placeholders inside format specs), or `None`.

    Placeholders nested inside format specs (e.g. ``{width}`` in
    ``{price:{width}.{precision}f}``) are included in the result.

    Raises `ValueError` if the format string is malformed.
    """
    fields: list[tuple[tuple[int | str, ...], str | None, str | None, str, str | None]] = []
    auto_index = 0
    numbering: str | None = None

    def check_numbering(kind: str) -> None:
        nonlocal numbering
        if numbering is None:
            numbering = kind
        elif numbering != kind:
            raise ValueError(
                'format string mixes automatic and manual field numbering',
            )

    def parse_field_name(field_name: str) -> tuple[int | str, ...]:
        nonlocal auto_index
        if not field_name or field_name[0] in '.[':
            # automatic field numbering: `{}`, `{[0]}`, `{.name}`
            first: int | str = auto_index
            auto_index += 1
            check_numbering('auto')
            start = 0
        else:
            end = 0
            while end < len(field_name) and field_name[end] not in '.[':
                end += 1
            arg_name = field_name[:end]
            if arg_name.isdecimal():
                check_numbering('manual')
                first = int(arg_name)
            else:
                first = arg_name
            start = end
        return (first, *_parse_field_accessors(field_name, start))

    def add_field(
        field_name: str,
        conversion: str | None,
        format_spec: str,
        parent: str | None,
        depth: int,
    ) -> None:
        if conversion is not None and conversion not in {'s', 'r', 'a'}:
            raise ValueError(f'unknown conversion specifier {conversion!r}')
        path = parse_field_name(field_name)
        display = field_name if field_name else str(path[0])
        fields.append((path, conversion, _presentation_type(format_spec), display, parent))
        if format_spec and '{' in format_spec:
            if depth > 0:
                raise ValueError(
                    f'nested replacement field in format spec of {parent!r}',
                )
            for _, nested_name, nested_spec, nested_conversion in _BRACE_FORMATTER.parse(
                format_spec,
            ):
                if nested_name is None:
                    continue
                add_field(nested_name, nested_conversion, nested_spec, display, depth + 1)

    for _, field_name, format_spec, conversion in _BRACE_FORMATTER.parse(format_string):
        if field_name is None:
            continue
        add_field(field_name, conversion, format_spec, None, 0)

    return fields


def _parse_field_accessors(field_name: str, pos: int) -> list[int | str]:
    """Parse the attribute/index accessors of a brace format field name.

    Returns a list of attribute names (`str`) and indices (`int` for
    numeric indices, `str` otherwise). Raises `ValueError` if the
    accessors are malformed.
    """
    parts: list[int | str] = []
    while pos < len(field_name):
        if field_name[pos] == '.':
            end = pos + 1
            while end < len(field_name) and field_name[end] not in '.[':
                end += 1
            name = field_name[pos + 1 : end]
            if not name:
                raise ValueError(f'empty attribute in field name {field_name!r}')
            parts.append(name)
            pos = end
        elif field_name[pos] == '[':
            end = field_name.find(']', pos + 1)
            if end == -1:
                raise ValueError(f'unmatched "[" in field name {field_name!r}')
            index = field_name[pos + 1 : end]
            if not index:
                raise ValueError(f'empty index in field name {field_name!r}')
            parts.append(int(index) if index.isdecimal() else index)
            pos = end + 1
        else:
            raise ValueError(
                f'unexpected character {field_name[pos]!r} in field name {field_name!r}',
            )
    return parts


def _presentation_type(format_spec: str) -> str | None:
    """Extract the presentation type character from a brace format spec.

    Nested replacement fields (e.g. ``{width}`` in ``{price:{width}.2f}``)
    are ignored; only the literal parts of the spec are considered.
    Returns `None` if the spec does not contain a presentation type.
    """
    if not format_spec:
        return None
    if '{' in format_spec or '}' in format_spec:
        format_spec = ''.join(t[0] for t in _BRACE_FORMATTER.parse(format_spec))
    if format_spec and format_spec[-1] in _BRACE_FORMAT_TYPE_CHARS:
        return format_spec[-1]
    return None


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
