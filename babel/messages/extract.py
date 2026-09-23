"""
babel.messages.extract
~~~~~~~~~~~~~~~~~~~~~~

Basic infrastructure for extracting localizable messages from source files.

This module defines an extensible system for collecting localizable message
strings from a variety of sources. A native extractor for Python source
files is builtin, extractors for other sources can be added using very
simple plugins.

The main entry points into the extraction functionality are the functions
`extract_from_dir` and `extract_from_file`.

:copyright: (c) 2013-2026 by the Babel Team.
:license: BSD, see LICENSE for more details.
"""

from __future__ import annotations

import ast
import io
import os
import sys
import tokenize
import warnings
from collections.abc import (
    Callable,
    Collection,
    Generator,
    Iterable,
    Mapping,
    MutableSequence,
)
from functools import lru_cache
from os.path import relpath
from textwrap import dedent
from tokenize import COMMENT, NAME, NL, OP, STRING, generate_tokens
from typing import TYPE_CHECKING, Any, NamedTuple, TypedDict

from babel.messages._compat import find_entrypoints
from babel.util import parse_encoding, parse_future_flags, pathmatch

if TYPE_CHECKING:
    from typing import IO, Final, Protocol

    from _typeshed import SupportsItems, SupportsRead, SupportsReadline
    from typing_extensions import TypeAlias

    class _PyOptions(TypedDict, total=False):
        encoding: str

    class _JSOptions(TypedDict, total=False):
        encoding: str
        jsx: bool
        template_string: bool
        parse_template_string: bool

    class _FileObj(SupportsRead[bytes], SupportsReadline[bytes], Protocol):
        def seek(self, __offset: int, __whence: int = ...) -> int: ...
        def tell(self) -> int: ...

    _SimpleKeyword: TypeAlias = tuple[int | tuple[int, int] | tuple[int, str], ...] | None
    # A "named" keyword specification maps a translation function's parameter
    # names to their roles; the declaration order also defines the positional
    # parameter order.  Recognized roles are "msgid", "msgid_plural" and
    # "msgctxt"; a parameter mapped to None is not extracted.
    _NamedKeyword: TypeAlias = dict[str, str | None]
    _Keyword: TypeAlias = (
        dict[int | None, _SimpleKeyword | _NamedKeyword] | _SimpleKeyword | _NamedKeyword
    )

    # 5-tuple of (filename, lineno, messages, comments, context)
    _FileExtractionResult: TypeAlias = tuple[str, int, str | tuple[str, ...], list[str], str | None]  # fmt: skip

    # 4-tuple of (lineno, message, comments, context)
    _ExtractionResult: TypeAlias = tuple[int, str | tuple[str, ...], list[str], str | None]

    # Required arguments: fileobj, keywords, comment_tags, options
    # Return value: Iterable of (lineno, message, comments, context)
    _CallableExtractionMethod: TypeAlias = Callable[
        [_FileObj | IO[bytes], Mapping[str, _Keyword], Collection[str], Mapping[str, Any]],
        Iterable[_ExtractionResult],
    ]  # fmt: skip

    _ExtractionMethod: TypeAlias = _CallableExtractionMethod | str

GROUP_NAME: Final[str] = 'babel.extractors'

#: Roles that may be used in a named keyword specification.
ROLE_MSGID: Final[str] = 'msgid'
ROLE_MSGID_PLURAL: Final[str] = 'msgid_plural'
ROLE_MSGCTXT: Final[str] = 'msgctxt'
SPEC_ROLES: Final[frozenset[str]] = frozenset({ROLE_MSGID, ROLE_MSGID_PLURAL, ROLE_MSGCTXT})


class _CallArgument(NamedTuple):
    """A single argument of a translation function call.

    The Python extractor emits these (instead of plain strings) for calls
    that use keyword arguments or argument unpacking, so that the arguments
    can be matched against named keyword specifications.
    """

    #: The keyword parameter name, or None for positional arguments.
    name: str | None
    #: The static string value of the argument, or None if it is not a
    #: statically determinable string.
    value: str | None
    #: The line number where the argument starts.
    lineno: int
    #: '*', '**' or '' if the argument unpacks an iterable/mapping.
    star: str = ''


#: Sentinel for call arguments that cannot be statically determined.
_UNKNOWN: Final = object()

DEFAULT_KEYWORDS: dict[str, _Keyword] = {
    '_': None,
    'gettext': None,
    'ngettext': (1, 2),
    'ugettext': None,
    'ungettext': (1, 2),
    'dgettext': (2,),
    'dngettext': (2, 3),
    'dpgettext': ((2, 'c'), 3),
    'N_': None,
    'pgettext': ((1, 'c'), 2),
    'npgettext': ((1, 'c'), 2, 3),
    'dnpgettext': ((2, 'c'), 3, 4),
}

DEFAULT_MAPPING: list[tuple[str, str]] = [('**.py', 'python')]

# New tokens in Python 3.12, or None on older versions
FSTRING_START = getattr(tokenize, "FSTRING_START", None)
FSTRING_MIDDLE = getattr(tokenize, "FSTRING_MIDDLE", None)
FSTRING_END = getattr(tokenize, "FSTRING_END", None)


def _strip_comment_tags(comments: MutableSequence[str], tags: Iterable[str]):
    """Helper function for `extract` that strips comment tags from strings
    in a list of comment lines.  This functions operates in-place.
    """

    def _strip(line: str):
        for tag in tags:
            if line.startswith(tag):
                return line[len(tag) :].strip()
        return line

    comments[:] = [_strip(c) for c in comments]


def _make_default_directory_filter(
    method_map: Iterable[tuple[str, str]],
    root_dir: str | os.PathLike[str],
):
    method_map = tuple(method_map)

    def directory_filter(dirpath: str | os.PathLike[str]) -> bool:
        subdir = os.path.basename(dirpath)
        # Legacy default behavior: ignore dot and underscore directories
        if subdir.startswith('.') or subdir.startswith('_'):
            return False

        dir_rel = os.path.relpath(dirpath, root_dir).replace(os.sep, '/')

        for pattern, method in method_map:
            if method == "ignore" and pathmatch(pattern, dir_rel):
                return False

        return True

    return directory_filter


def default_directory_filter(dirpath: str | os.PathLike[str]) -> bool:  # pragma: no cover
    warnings.warn(
        "`default_directory_filter` is deprecated and will be removed in a future version of Babel.",
        DeprecationWarning,
        stacklevel=2,
    )
    subdir = os.path.basename(dirpath)
    # Legacy default behavior: ignore dot and underscore directories
    return not (subdir.startswith('.') or subdir.startswith('_'))


def extract_from_dir(
    dirname: str | os.PathLike[str] | None = None,
    method_map: Iterable[tuple[str, str]] = DEFAULT_MAPPING,
    options_map: SupportsItems[str, dict[str, Any]] | None = None,
    keywords: Mapping[str, _Keyword] = DEFAULT_KEYWORDS,
    comment_tags: Collection[str] = (),
    callback: Callable[[str, str, dict[str, Any]], object] | None = None,
    strip_comment_tags: bool = False,
    directory_filter: Callable[[str], bool] | None = None,
) -> Generator[_FileExtractionResult, None, None]:
    """Extract messages from any source files found in the given directory.

    This function generates tuples of the form ``(filename, lineno, message,
    comments, context)``.

    Which extraction method is used per file is determined by the `method_map`
    parameter, which maps extended glob patterns to extraction method names.
    For example, the following is the default mapping:

    >>> method_map = [
    ...     ('**.py', 'python')
    ... ]

    This basically says that files with the filename extension ".py" at any
    level inside the directory should be processed by the "python" extraction
    method. Files that don't match any of the mapping patterns are ignored. See
    the documentation of the `pathmatch` function for details on the pattern
    syntax.

    The following extended mapping would also use the "genshi" extraction
    method on any file in "templates" subdirectory:

    >>> method_map = [
    ...     ('**/templates/**.*', 'genshi'),
    ...     ('**.py', 'python')
    ... ]

    The dictionary provided by the optional `options_map` parameter augments
    these mappings. It uses extended glob patterns as keys, and the values are
    dictionaries mapping options names to option values (both strings).

    The glob patterns of the `options_map` do not necessarily need to be the
    same as those used in the method mapping. For example, while all files in
    the ``templates`` folders in an application may be Genshi applications, the
    options for those files may differ based on extension:

    >>> options_map = {
    ...     '**/templates/**.txt': {
    ...         'template_class': 'genshi.template:TextTemplate',
    ...         'encoding': 'latin-1'
    ...     },
    ...     '**/templates/**.html': {
    ...         'include_attrs': ''
    ...     }
    ... }

    :param dirname: the path to the directory to extract messages from.  If
                    not given the current working directory is used.
    :param method_map: a list of ``(pattern, method)`` tuples that maps of
                       extraction method names to extended glob patterns
    :param options_map: a dictionary of additional options (optional)
    :param keywords: a dictionary mapping keywords (i.e. names of functions
                     that should be recognized as translation functions) to
                     tuples that specify which of their arguments contain
                     localizable strings
    :param comment_tags: a list of tags of translator comments to search for
                         and include in the results
    :param callback: a function that is called for every file that message are
                     extracted from, just before the extraction itself is
                     performed; the function is passed the filename, the name
                     of the extraction method and and the options dictionary as
                     positional arguments, in that order
    :param strip_comment_tags: a flag that if set to `True` causes all comment
                               tags to be removed from the collected comments.
    :param directory_filter: a callback to determine whether a directory should
                             be recursed into. Receives the full directory path;
                             should return True if the directory is valid.
    :see: `pathmatch`
    """
    if dirname is None:
        dirname = os.getcwd()

    if options_map is None:
        options_map = {}

    dirname = os.path.abspath(dirname)

    if directory_filter is None:
        directory_filter = _make_default_directory_filter(
            method_map=method_map,
            root_dir=dirname,
        )

    for root, dirnames, filenames in os.walk(dirname):
        dirnames[:] = [
            subdir for subdir in dirnames if directory_filter(os.path.join(root, subdir))
        ]
        dirnames.sort()
        filenames.sort()
        for filename in filenames:
            filepath = os.path.join(root, filename).replace(os.sep, '/')

            yield from check_and_call_extract_file(
                filepath,
                method_map,
                options_map,
                callback,
                keywords,
                comment_tags,
                strip_comment_tags,
                dirpath=dirname,
            )


def check_and_call_extract_file(
    filepath: str | os.PathLike[str],
    method_map: Iterable[tuple[str, str]],
    options_map: SupportsItems[str, dict[str, Any]],
    callback: Callable[[str, str, dict[str, Any]], object] | None,
    keywords: Mapping[str, _Keyword],
    comment_tags: Collection[str],
    strip_comment_tags: bool,
    dirpath: str | os.PathLike[str] | None = None,
) -> Generator[_FileExtractionResult, None, None]:
    """Checks if the given file matches an extraction method mapping, and if so, calls extract_from_file.

    Note that the extraction method mappings are based relative to dirpath.
    So, given an absolute path to a file `filepath`, we want to check using
    just the relative path from `dirpath` to `filepath`.

    Yields 5-tuples (filename, lineno, messages, comments, context).

    :param filepath: An absolute path to a file that exists.
    :param method_map: a list of ``(pattern, method)`` tuples that maps of
                       extraction method names to extended glob patterns
    :param options_map: a dictionary of additional options (optional)
    :param callback: a function that is called for every file that message are
                     extracted from, just before the extraction itself is
                     performed; the function is passed the filename, the name
                     of the extraction method and and the options dictionary as
                     positional arguments, in that order
    :param keywords: a dictionary mapping keywords (i.e. names of functions
                     that should be recognized as translation functions) to
                     tuples that specify which of their arguments contain
                     localizable strings
    :param comment_tags: a list of tags of translator comments to search for
                         and include in the results
    :param strip_comment_tags: a flag that if set to `True` causes all comment
                               tags to be removed from the collected comments.
    :param dirpath: the path to the directory to extract messages from.
    :return: iterable of 5-tuples (filename, lineno, messages, comments, context)
    :rtype: Iterable[tuple[str, int, str|tuple[str], list[str], str|None]
    """
    # filename is the relative path from dirpath to the actual file
    filename = relpath(filepath, dirpath)

    for pattern, method in method_map:
        if not pathmatch(pattern, filename):
            continue

        options = {}
        for opattern, odict in options_map.items():
            if pathmatch(opattern, filename):
                options = odict
                break

        # Merge keywords and comment_tags from per-format options if present.
        file_keywords = keywords
        file_comment_tags = comment_tags
        if keywords_opt := options.get("keywords"):
            if not isinstance(keywords_opt, dict):  # pragma: no cover
                raise TypeError(
                    f"The `keywords` option must be a dict of parsed keywords, not {keywords_opt!r}",
                )
            file_keywords = {**keywords, **keywords_opt}

        if comments_opt := options.get("add_comments"):
            if not isinstance(comments_opt, (list, tuple, set)):  # pragma: no cover
                raise TypeError(
                    f"The `add_comments` option must be a collection of comment tags, not {comments_opt!r}.",
                )
            file_comment_tags = tuple(set(comment_tags) | set(comments_opt))

        if callback:
            callback(filename, method, options)
        for message_tuple in extract_from_file(
            method,
            filepath,
            keywords=file_keywords,
            comment_tags=file_comment_tags,
            options=options,
            strip_comment_tags=strip_comment_tags,
        ):
            yield (filename, *message_tuple)

        break


def extract_from_file(
    method: _ExtractionMethod,
    filename: str | os.PathLike[str],
    keywords: Mapping[str, _Keyword] = DEFAULT_KEYWORDS,
    comment_tags: Collection[str] = (),
    options: Mapping[str, Any] | None = None,
    strip_comment_tags: bool = False,
) -> list[_ExtractionResult]:
    """Extract messages from a specific file.

    This function returns a list of tuples of the form ``(lineno, message, comments, context)``.

    :param filename: the path to the file to extract messages from
    :param method: a string specifying the extraction method (.e.g. "python")
    :param keywords: a dictionary mapping keywords (i.e. names of functions
                     that should be recognized as translation functions) to
                     tuples that specify which of their arguments contain
                     localizable strings
    :param comment_tags: a list of translator tags to search for and include
                         in the results
    :param strip_comment_tags: a flag that if set to `True` causes all comment
                               tags to be removed from the collected comments.
    :param options: a dictionary of additional options (optional)
    :returns: list of tuples of the form ``(lineno, message, comments, context)``
    :rtype: list[tuple[int, str|tuple[str], list[str], str|None]
    """
    if method == 'ignore':
        return []

    with open(filename, 'rb') as fileobj:
        return list(
            extract(method, fileobj, keywords, comment_tags, options, strip_comment_tags),
        )


def _match_messages_against_spec(
    lineno: int,
    messages: list[str | None],
    comments: list[str],
    fileobj: _FileObj,
    spec: tuple[int | tuple[int, str], ...],
):
    # Unwrap enriched arguments emitted by the Python extractor; for
    # positional specifications only the argument values, in call order,
    # are relevant.
    messages = [
        message.value if isinstance(message, _CallArgument) else message
        for message in messages
    ]

    translatable = []
    context = None

    # last_index is 1 based like the keyword spec
    last_index = len(messages)
    for index in spec:
        if isinstance(index, tuple):  # (n, 'c')
            context = messages[index[0] - 1]
            continue
        if last_index < index:
            # Not enough arguments
            return
        message = messages[index - 1]
        if message is None:
            return
        translatable.append(message)

    # keyword spec indexes are 1 based, therefore '-1'
    if isinstance(spec[0], tuple):
        # context-aware *gettext method
        first_msg_index = spec[1] - 1
    else:
        first_msg_index = spec[0] - 1
    # An empty string msgid isn't valid, emit a warning
    if not messages[first_msg_index]:
        filename = getattr(fileobj, "name", None) or "(unknown)"
        sys.stderr.write(
            f"{filename}:{lineno}: warning: Empty msgid.  It is reserved by GNU gettext: gettext(\"\") "
            f"returns the header entry with meta information, not the empty string.\n",
        )
        return

    translatable = tuple(translatable)
    if len(translatable) == 1:
        translatable = translatable[0]

    return lineno, translatable, comments, context


def _is_empty_argument(arg: Any) -> bool:
    """Return True if the given call argument carries no information,
    i.e. it is a placeholder for a missing argument."""
    if isinstance(arg, _CallArgument):
        return arg.name is None and arg.value is None and not arg.star
    return arg is None


def _is_named_spec(spec: Any) -> bool:
    """Return True if the given keyword specification is a named
    specification (mapping parameter names to roles) rather than an
    arity map or a positional specification."""
    return (
        isinstance(spec, dict)
        and bool(spec)
        and all(isinstance(key, str) for key in spec)
    )


def _match_named_spec_against_messages(
    lineno: int,
    messages: list[str | None | _CallArgument],
    comments: list[str],
    fileobj: _FileObj,
    spec: dict[str, str | None],
):
    """Match a call's arguments against a named keyword specification.

    The specification maps parameter names to roles ("msgid",
    "msgid_plural", "msgctxt" or None); its declaration order also
    defines the positional parameter order, so positional and keyword
    calls resolve to the same message.

    Only calls whose declared roles are all bound to statically
    determinable strings produce a message; calls involving ``*args``,
    ``**kwargs`` or duplicate bindings are only extracted as far as the
    binding can be determined unambiguously.
    """
    param_names = list(spec)
    # Ignore trailing empty arguments; they are an artifact of trailing
    # commas in calls such as ``ngettext(singular='file', plural='files',)``
    # and would otherwise be mistaken for positional arguments.
    messages = list(messages)
    while messages and _is_empty_argument(messages[-1]):
        messages.pop()

    bindings: dict[str, list[tuple[str | None, int]]] = {}
    position = 0
    positional_reliable = True
    for arg in messages:
        if isinstance(arg, _CallArgument):
            if arg.star == '**':
                # ``**kwargs`` cannot invalidate arguments that are
                # bound explicitly.
                continue
            if arg.star == '*':
                # ``*args`` makes the positions of all following
                # positional arguments undeterminable.
                positional_reliable = False
                continue
            value, arg_lineno, name = arg.value, arg.lineno, arg.name
            if name is None:
                if not positional_reliable:
                    continue
                name = param_names[position] if position < len(param_names) else None
                position += 1
                if name is None:
                    continue
        else:
            # Plain positional argument, e.g. from another extractor.
            if not positional_reliable:
                continue
            value, arg_lineno = arg, lineno
            name = param_names[position] if position < len(param_names) else None
            position += 1
            if name is None:
                continue
        if name in spec:
            bindings.setdefault(name, []).append((value, arg_lineno))

    def resolve(role: str) -> tuple[str | None, int] | None:
        for name, param_role in spec.items():
            if param_role != role:
                continue
            bound = bindings.get(name)
            if bound is None or len(bound) != 1:
                # The parameter is not bound, or bound more than once,
                # so its value cannot be determined.
                return _UNKNOWN
            return bound[0]
        return None  # the role is not declared in the specification

    msgid = resolve(ROLE_MSGID)
    if msgid is None or msgid is _UNKNOWN or msgid[0] is None:
        return
    plural = resolve(ROLE_MSGID_PLURAL)
    if plural is _UNKNOWN or (plural is not None and plural[0] is None):
        return
    context = resolve(ROLE_MSGCTXT)
    if context is _UNKNOWN or (context is not None and context[0] is None):
        return

    # An empty string msgid isn't valid, emit a warning
    if not msgid[0]:
        filename = getattr(fileobj, "name", None) or "(unknown)"
        sys.stderr.write(
            f"{filename}:{msgid[1]}: warning: Empty msgid.  It is reserved by GNU gettext: gettext(\"\") "
            f"returns the header entry with meta information, not the empty string.\n",
        )
        return

    if plural is not None:
        message = (msgid[0], plural[0])
    else:
        message = msgid[0]
    return msgid[1], message, comments, context[0] if context is not None else None


@lru_cache(maxsize=None)
def _find_extractor(name: str):
    for ep_name, load in find_entrypoints(GROUP_NAME):
        if ep_name == name:
            return load()
    return None


def extract(
    method: _ExtractionMethod,
    fileobj: _FileObj,
    keywords: Mapping[str, _Keyword] = DEFAULT_KEYWORDS,
    comment_tags: Collection[str] = (),
    options: Mapping[str, Any] | None = None,
    strip_comment_tags: bool = False,
) -> Generator[_ExtractionResult, None, None]:
    """Extract messages from the given file-like object using the specified
    extraction method.

    This function returns tuples of the form ``(lineno, message, comments, context)``.

    The implementation dispatches the actual extraction to plugins, based on the
    value of the ``method`` parameter.

    >>> source = b'''# foo module
    ... def run(argv):
    ...    print(_('Hello, world!'))
    ... '''

    >>> from io import BytesIO
    >>> for message in extract('python', BytesIO(source)):
    ...     print(message)
    (3, 'Hello, world!', [], None)

    :param method: an extraction method (a callable), or
                   a string specifying the extraction method (.e.g. "python");
                   if this is a simple name, the extraction function will be
                   looked up by entry point; if it is an explicit reference
                   to a function (of the form ``package.module:funcname`` or
                   ``package.module.funcname``), the corresponding function
                   will be imported and used
    :param fileobj: the file-like object the messages should be extracted from
    :param keywords: a dictionary mapping keywords (i.e. names of functions
                     that should be recognized as translation functions) to
                     tuples that specify which of their arguments contain
                     localizable strings
                     ; a specification may also be a dictionary mapping the
                     function's parameter names to their roles ("msgid",
                     "msgid_plural", "msgctxt" or None), in which case the
                     declaration order defines the positional parameter order
    :param comment_tags: a list of translator tags to search for and include
                         in the results
    :param options: a dictionary of additional options (optional)
    :param strip_comment_tags: a flag that if set to `True` causes all comment
                               tags to be removed from the collected comments.
    :raise ValueError: if the extraction method is not registered
    :returns: iterable of tuples of the form ``(lineno, message, comments, context)``
    :rtype: Iterable[tuple[int, str|tuple[str], list[str], str|None]
    """
    if callable(method):
        func = method
    elif ':' in method or '.' in method:
        if ':' not in method:
            lastdot = method.rfind('.')
            module, attrname = method[:lastdot], method[lastdot + 1 :]
        else:
            module, attrname = method.split(':', 1)
        func = getattr(__import__(module, {}, {}, [attrname]), attrname)
    else:
        func = _find_extractor(method)
        if func is None:
            # if no named entry point was found,
            # we resort to looking up a builtin extractor
            func = _BUILTIN_EXTRACTORS.get(method)

    if func is None:
        raise ValueError(f"Unknown extraction method {method!r}")

    results = func(fileobj, keywords.keys(), comment_tags, options=options or {})

    for lineno, funcname, messages, comments in results:
        if not isinstance(messages, (list, tuple)):
            messages = [messages]
        if not messages:
            continue

        specs = keywords[funcname] or None if funcname else None
        # {None: x} may be collapsed into x for backwards compatibility.
        if _is_named_spec(specs):
            # A named specification maps parameter names to roles; it
            # applies to calls of any arity.
            specs = {None: specs}
        elif not isinstance(specs, dict):
            specs = {None: specs}

        if strip_comment_tags:
            _strip_comment_tags(comments, comment_tags)

        # None matches all arities.
        for arity in (None, len(messages)):
            try:
                spec = specs[arity]
            except KeyError:
                continue
            if spec is None:
                spec = (1,)
            if isinstance(spec, dict):
                result = _match_named_spec_against_messages(lineno, messages, comments, fileobj, spec)
            else:
                result = _match_messages_against_spec(lineno, messages, comments, fileobj, spec)
            if result is not None:
                yield result


def extract_nothing(
    fileobj: _FileObj,
    keywords: Mapping[str, _Keyword],
    comment_tags: Collection[str],
    options: Mapping[str, Any],
) -> list[_ExtractionResult]:
    """Pseudo extractor that does not actually extract anything, but simply
    returns an empty list.
    """
    return []


def extract_python(
    fileobj: IO[bytes],
    keywords: Mapping[str, _Keyword],
    comment_tags: Collection[str],
    options: _PyOptions,
) -> Generator[_ExtractionResult, None, None]:
    """Extract messages from Python source code.

    It returns an iterator yielding tuples in the following form ``(lineno,
    funcname, message, comments)``.

    For calls that use keyword arguments or argument unpacking, the message
    items are emitted as `_CallArgument` tuples (carrying the parameter
    name, the static value, the line number and any unpacking marker), so
    that `extract` can match them against keyword specifications that
    declare parameter names and roles.

    :param fileobj: the seekable, file-like object the messages should be
                    extracted from
    :param keywords: a list of keywords (i.e. function names) that should be
                     recognized as translation functions
    :param comment_tags: a list of translator tags to search for and include
                         in the results
    :param options: a dictionary of additional options (optional)
    :rtype: ``iterator``
    """
    funcname = lineno = message_lineno = None
    call_stack = []  # line numbers of calls
    buf = []
    messages = []
    translator_comments = []
    in_def = in_translator_comments = False
    comment_tag = None

    # State for the argument currently being parsed at call depth 1.
    arg_name = None  # keyword parameter name of the current argument
    arg_star = ''  # '*', '**' or '' for unpacking arguments
    arg_lineno = None  # line number where the current argument starts
    arg_started = False  # whether the current argument has any value tokens
    pending_name = None  # a NAME token that may be a keyword parameter name
    arg_static = True  # whether the current argument consists only of string tokens

    def flush_argument():
        nonlocal arg_name, arg_star, arg_lineno, arg_started, arg_static, pending_name
        messages.append(
            _CallArgument(
                arg_name,
                ''.join(buf) if buf and arg_static else None,
                arg_lineno or lineno,
                arg_star,
            ),
        )
        del buf[:]
        arg_name = None
        arg_star = ''
        arg_lineno = None
        arg_started = False
        arg_static = True
        pending_name = None

    encoding = parse_encoding(fileobj) or options.get('encoding', 'UTF-8')
    future_flags = parse_future_flags(fileobj, encoding)
    next_line = lambda: fileobj.readline().decode(encoding)

    tokens = generate_tokens(next_line)

    # Current prefix of a Python 3.12 (PEP 701) f-string, or None if we're not
    # currently parsing one.
    current_fstring_start = None

    for tok, value, (lineno, _), _, _ in tokens:
        if not call_stack and tok == NAME and value in ('def', 'class'):
            in_def = True
        elif tok == OP and value == '(':
            if in_def:
                # Avoid false positives for declarations such as:
                # def gettext(arg='message'):
                in_def = False
                continue
            if funcname:
                call_stack.append(lineno)
                if len(call_stack) > 1 and pending_name is not None:
                    # A name followed by `(` is a call, not a keyword argument.
                    pending_name = None
                    arg_started = True
                    arg_static = False
        elif in_def and tok == OP and value == ':':
            # End of a class definition without parens
            in_def = False
            continue
        elif not call_stack and tok == COMMENT:
            # Strip the comment token from the line
            value = value[1:].strip()
            if in_translator_comments and translator_comments[-1][0] == lineno - 1:
                # We're already inside a translator comment, continue appending
                translator_comments.append((lineno, value))
                continue
            # If execution reaches this point, let's see if comment line
            # starts with one of the comment tags
            for comment_tag in comment_tags:
                if value.startswith(comment_tag):
                    in_translator_comments = True
                    translator_comments.append((lineno, value))
                    break
        elif funcname and len(call_stack) == 1:
            nested = tok == NAME and value in keywords
            if pending_name is not None and tok not in (NL, COMMENT) and not (tok == OP and value == '='):
                # The previous NAME token was part of a runtime expression,
                # not a keyword argument name.
                pending_name = None
                arg_started = True
                arg_static = False
            if (tok == OP and value == ')') or nested:
                flush_argument()

                if any(arg.name is not None or arg.star for arg in messages):
                    # The call used keyword arguments or argument unpacking;
                    # emit the enriched argument representation so that the
                    # arguments can be matched against named keyword
                    # specifications.
                    collected = tuple(messages)
                else:
                    values = [arg.value for arg in messages]
                    collected = tuple(values) if len(values) > 1 else values[0]

                if translator_comments:
                    last_comment_lineno = translator_comments[-1][0]
                    if last_comment_lineno < min(message_lineno, call_stack[-1]) - 1:
                        # Comments don't apply unless they immediately
                        # precede the message, or the line where the parenthesis token
                        # to start this message's translation call is.
                        translator_comments.clear()

                yield (
                    message_lineno,
                    funcname,
                    collected,
                    [comment[1] for comment in translator_comments],
                )

                funcname = lineno = message_lineno = None
                call_stack.clear()
                messages = []
                translator_comments = []
                in_translator_comments = False
                if nested:
                    funcname = value
            elif tok == STRING:
                val = _parse_python_string(value, encoding, future_flags)
                if val is not None:
                    if not message_lineno:
                        message_lineno = lineno
                    buf.append(val)
                arg_started = True
                if arg_lineno is None:
                    arg_lineno = lineno

            # Python 3.12+, see https://peps.python.org/pep-0701/#new-tokens
            elif tok == FSTRING_START:
                current_fstring_start = value
                if not message_lineno:
                    message_lineno = lineno
                arg_started = True
                if arg_lineno is None:
                    arg_lineno = lineno
            elif tok == FSTRING_MIDDLE:
                if current_fstring_start is not None:
                    current_fstring_start += value
            elif tok == FSTRING_END:
                if current_fstring_start is not None:
                    fstring = current_fstring_start + value
                    val = _parse_python_string(fstring, encoding, future_flags)
                    if val is not None:
                        buf.append(val)

            elif tok == OP and value == ',':
                flush_argument()
                if translator_comments:
                    # We have translator comments, and since we're on a
                    # comma(,) user is allowed to break into a new line
                    # Let's increase the last comment's lineno in order
                    # for the comment to still be a valid one
                    old_lineno, old_comment = translator_comments.pop()
                    translator_comments.append((old_lineno + 1, old_comment))

            elif tok == OP and value == '=' and pending_name is not None and not buf:
                # `name=` at call depth: a keyword argument.
                arg_name, arg_lineno = pending_name
                pending_name = None
            elif (
                tok == OP
                and value in ('*', '**')
                and pending_name is None
                and arg_name is None
                and not buf
                and not arg_started
                and not arg_star
            ):
                # `*args` or `**kwargs` unpacking.
                arg_star = value
                if arg_lineno is None:
                    arg_lineno = lineno
                if not message_lineno:
                    message_lineno = lineno
            elif tok == NAME and arg_name is None and not buf and not arg_started and not arg_star:
                # A bare name may turn out to be a keyword argument name
                # if an `=` token follows.
                pending_name = (value, lineno)
                if arg_lineno is None:
                    arg_lineno = lineno
                if not message_lineno:
                    message_lineno = lineno
            elif tok == COMMENT:
                if not message_lineno:
                    message_lineno = lineno
            elif tok != NL:
                # Any other token is part of a runtime expression.
                pending_name = None
                arg_started = True
                arg_static = False
                if arg_lineno is None:
                    arg_lineno = lineno
                if not message_lineno:
                    message_lineno = lineno
        elif len(call_stack) > 1 and tok == OP and value == ')':
            call_stack.pop()
        elif funcname and not call_stack:
            funcname = None
        elif tok == NAME and value in keywords:
            funcname = value

        if current_fstring_start is not None and tok not in {FSTRING_START, FSTRING_MIDDLE}:
            # In Python 3.12, tokens other than FSTRING_* mean the
            # f-string is dynamic, so we don't wan't to extract it.
            # And if it's FSTRING_END, we've already handled it above.
            # Let's forget that we're in an f-string.
            current_fstring_start = None


def _parse_python_string(value: str, encoding: str, future_flags: int) -> str | None:
    # Unwrap quotes in a safe manner, maintaining the string's encoding
    # https://sourceforge.net/tracker/?func=detail&atid=355470&aid=617979&group_id=5470
    code = compile(
        f'# coding={str(encoding)}\n{value}',
        '<string>',
        'eval',
        ast.PyCF_ONLY_AST | future_flags,
    )
    if isinstance(code, ast.Expression):
        body = code.body
        if isinstance(body, ast.Constant):
            return body.value
        if isinstance(body, ast.JoinedStr):  # f-string
            if all(isinstance(node, ast.Constant) for node in body.values):
                return ''.join(node.value for node in body.values)
            # TODO: we could raise an error or warning when not all nodes are constants
    return None


def extract_javascript(
    fileobj: _FileObj,
    keywords: Mapping[str, _Keyword],
    comment_tags: Collection[str],
    options: _JSOptions,
    lineno: int = 1,
) -> Generator[_ExtractionResult, None, None]:
    """Extract messages from JavaScript source code.

    :param fileobj: the seekable, file-like object the messages should be
                    extracted from
    :param keywords: a list of keywords (i.e. function names) that should be
                     recognized as translation functions
    :param comment_tags: a list of translator tags to search for and include
                         in the results
    :param options: a dictionary of additional options (optional)
                    Supported options are:
                    * `jsx` -- set to false to disable JSX/E4X support.
                    * `template_string` -- if `True`, supports gettext(`key`)
                    * `parse_template_string` -- if `True` will parse the
                                                 contents of javascript
                                                 template strings.
    :param lineno: line number offset (for parsing embedded fragments)
    """
    from babel.messages.jslexer import Token, tokenize, unquote_string

    funcname = message_lineno = None
    messages = []
    last_argument = None
    translator_comments = []
    concatenate_next = False
    encoding = options.get('encoding', 'utf-8')
    last_token = None
    call_stack = -1
    dotted = any('.' in kw for kw in keywords)
    for token in tokenize(
        fileobj.read().decode(encoding),
        jsx=options.get("jsx", True),
        template_string=options.get("template_string", True),
        dotted=dotted,
        lineno=lineno,
    ):
        if (  # Turn keyword`foo` expressions into keyword("foo") calls:
            # have a keyword...
            funcname
            # and we've seen nothing after the keyword...
            and (last_token and last_token.type == 'name')
            # and this is a template string
            and token.type == 'template_string'
        ):
            message_lineno = token.lineno
            messages = [unquote_string(token.value)]
            call_stack = 0
            token = Token('operator', ')', token.lineno)

        if (
            options.get('parse_template_string')
            and not funcname
            and token.type == 'template_string'
        ):
            yield from parse_template_string(
                token.value,
                keywords,
                comment_tags,
                options,
                token.lineno,
            )

        elif token.type == 'operator' and token.value == '(':
            if funcname:
                message_lineno = token.lineno
                call_stack += 1

        elif call_stack == -1 and token.type == 'linecomment':
            value = token.value[2:].strip()
            if translator_comments and translator_comments[-1][0] == token.lineno - 1:
                translator_comments.append((token.lineno, value))
                continue

            for comment_tag in comment_tags:
                if value.startswith(comment_tag):
                    translator_comments.append((token.lineno, value.strip()))
                    break

        elif token.type == 'multilinecomment':
            # only one multi-line comment may precede a translation
            translator_comments = []
            value = token.value[2:-2].strip()
            for comment_tag in comment_tags:
                if value.startswith(comment_tag):
                    lines = value.splitlines()
                    if lines:
                        lines[0] = lines[0].strip()
                        lines[1:] = dedent('\n'.join(lines[1:])).splitlines()
                        for offset, line in enumerate(lines):
                            translator_comments.append((token.lineno + offset, line))
                    break

        elif funcname and call_stack == 0:
            if token.type == 'operator' and token.value == ')':
                if last_argument is not None:
                    messages.append(last_argument)
                if len(messages) > 1:
                    messages = tuple(messages)
                elif messages:
                    messages = messages[0]
                else:
                    messages = None

                # Comments don't apply unless they immediately precede the
                # message
                if translator_comments and translator_comments[-1][0] < message_lineno - 1:
                    translator_comments = []

                if messages is not None:
                    yield (
                        message_lineno,
                        funcname,
                        messages,
                        [comment[1] for comment in translator_comments],
                    )

                funcname = message_lineno = last_argument = None
                concatenate_next = False
                translator_comments = []
                messages = []
                call_stack = -1

            elif token.type in ('string', 'template_string'):
                new_value = unquote_string(token.value)
                if concatenate_next:
                    last_argument = (last_argument or '') + new_value
                    concatenate_next = False
                else:
                    last_argument = new_value

            elif token.type == 'operator':
                if token.value == ',':
                    if last_argument is not None:
                        messages.append(last_argument)
                        last_argument = None
                    else:
                        messages.append(None)
                    concatenate_next = False
                elif token.value == '+':
                    concatenate_next = True

        elif call_stack > 0 and token.type == 'operator' and token.value == ')':
            call_stack -= 1

        elif funcname and call_stack == -1:
            funcname = None

        elif (
            call_stack == -1
            and token.type == 'name'
            and token.value in keywords
            and (
                last_token is None
                or last_token.type != 'name'
                or last_token.value != 'function'
            )
        ):
            funcname = token.value

        last_token = token


def parse_template_string(
    template_string: str,
    keywords: Mapping[str, _Keyword],
    comment_tags: Collection[str],
    options: _JSOptions,
    lineno: int = 1,
) -> Generator[_ExtractionResult, None, None]:
    """Parse JavaScript template string.

    :param template_string: the template string to be parsed
    :param keywords: a list of keywords (i.e. function names) that should be
                     recognized as translation functions
    :param comment_tags: a list of translator tags to search for and include
                         in the results
    :param options: a dictionary of additional options (optional)
    :param lineno: starting line number (optional)
    """
    from babel.messages.jslexer import line_re

    prev_character = None
    level = 0
    inside_str = False
    expression_contents = ''
    for character in template_string[1:-1]:
        if not inside_str and character in ('"', "'", '`'):
            inside_str = character
        elif inside_str == character and prev_character != r'\\':
            inside_str = False
        if level:
            expression_contents += character
        if not inside_str:
            if character == '{' and prev_character == '$':
                level += 1
            elif level and character == '}':
                level -= 1
                if level == 0 and expression_contents:
                    expression_contents = expression_contents[0:-1]
                    fake_file_obj = io.BytesIO(expression_contents.encode())
                    yield from extract_javascript(
                        fake_file_obj,
                        keywords,
                        comment_tags,
                        options,
                        lineno,
                    )
                    lineno += len(line_re.findall(expression_contents))
                    expression_contents = ''
        prev_character = character


_BUILTIN_EXTRACTORS = {
    'ignore': extract_nothing,
    'python': extract_python,
    'javascript': extract_javascript,
}
