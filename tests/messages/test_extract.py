#
# Copyright (C) 2007-2011 Edgewall Software, 2013-2025 the Babel team
# All rights reserved.
#
# This software is licensed as described in the file LICENSE, which
# you should have received as part of this distribution. The terms
# are also available at https://github.com/python-babel/babel/blob/master/LICENSE.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://github.com/python-babel/babel/commits/master/.

import sys
from io import BytesIO, StringIO

import pytest

from babel.messages import extract


def test_invalid_filter():
    buf = BytesIO(b"""\
msg1 = _(i18n_arg.replace(r'\"', '"'))
msg2 = ungettext(i18n_arg.replace(r'\"', '"'), multi_arg.replace(r'\"', '"'), 2)
msg3 = ungettext("Babel", multi_arg.replace(r'\"', '"'), 2)
msg4 = ungettext(i18n_arg.replace(r'\"', '"'), "Babels", 2)
msg5 = ungettext('bunny', 'bunnies', random.randint(1, 2))
msg6 = ungettext(arg0, 'bunnies', random.randint(1, 2))
msg7 = _(hello.there)
msg8 = gettext('Rabbit')
msg9 = dgettext('wiki', model.addPage())
msg10 = dngettext(domain, 'Page', 'Pages', 3)
""")
    messages = \
        list(extract.extract('python', buf, extract.DEFAULT_KEYWORDS, [],
                             {}))
    assert messages == [
        (5, ('bunny', 'bunnies'), [], None),
        (8, 'Rabbit', [], None),
        (10, ('Page', 'Pages'), [], None),
    ]


def test_invalid_extract_method():
    buf = BytesIO(b'')
    with pytest.raises(ValueError):
        list(extract.extract('spam', buf))


def test_different_signatures():
    buf = BytesIO(b"""
foo = _('foo', 'bar')
n = ngettext('hello', 'there', n=3)
n = ngettext(n=3, 'hello', 'there')
n = ngettext(n=3, *messages)
n = ngettext()
n = ngettext('foo')
""")
    messages = \
        list(extract.extract('python', buf, extract.DEFAULT_KEYWORDS, [],
                             {}))
    assert len(messages) == 2
    assert messages[0][1] == 'foo'
    assert messages[1][1] == ('hello', 'there')


def test_empty_string_msgid():
    buf = BytesIO(b"""\
msg = _('')
""")
    stderr = sys.stderr
    sys.stderr = StringIO()
    try:
        messages = \
            list(extract.extract('python', buf, extract.DEFAULT_KEYWORDS,
                                 [], {}))
        assert messages == []
        assert 'warning: Empty msgid.' in sys.stderr.getvalue()
    finally:
        sys.stderr = stderr


def test_warn_if_empty_string_msgid_found_in_context_aware_extraction_method():
    buf = BytesIO(b"\nmsg = pgettext('ctxt', '')\n")
    stderr = sys.stderr
    sys.stderr = StringIO()
    try:
        messages = extract.extract('python', buf)
        assert list(messages) == []
        assert 'warning: Empty msgid.' in sys.stderr.getvalue()
    finally:
        sys.stderr = stderr


def test_extract_allows_callable():
    def arbitrary_extractor(fileobj, keywords, comment_tags, options):
        return [(1, None, (), ())]
    for x in extract.extract(arbitrary_extractor, BytesIO(b"")):
        assert x[0] == 1


def test_future():
    buf = BytesIO(br"""
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
nbsp = _('\xa0')
""")
    messages = list(extract.extract('python', buf,
                                    extract.DEFAULT_KEYWORDS, [], {}))
    assert messages[0][1] == '\xa0'


def test_f_strings():
    buf = BytesIO(br"""
t1 = _('foobar')
t2 = _(f'spameggs' f'feast')  # should be extracted; constant parts only
t2 = _(f'spameggs' 'kerroshampurilainen')  # should be extracted (mixing f with no f)
t3 = _(f'''whoa! a '''  # should be extracted (continues on following lines)
f'flying shark'
'... hello'
)
t4 = _(f'spameggs {t1}')  # should not be extracted
""")
    messages = list(extract.extract('python', buf, extract.DEFAULT_KEYWORDS, [], {}))
    assert len(messages) == 4
    assert messages[0][1] == 'foobar'
    assert messages[1][1] == 'spameggsfeast'
    assert messages[2][1] == 'spameggskerroshampurilainen'
    assert messages[3][1] == 'whoa! a flying shark... hello'


def test_f_strings_non_utf8():
    buf = BytesIO(b"""
# -- coding: latin-1 --
t2 = _(f'\xe5\xe4\xf6' f'\xc5\xc4\xd6')
""")
    messages = list(extract.extract('python', buf, extract.DEFAULT_KEYWORDS, [], {}))
    assert len(messages) == 1
    assert messages[0][1] == 'åäöÅÄÖ'


def test_issue_1195():
    buf = BytesIO(b"""
foof = {
    'test_string': StringWithMeta(
        # NOTE: Text describing a test string
        string=_(
            'Text string that is on a new line'
        ),
    ),
}
""")
    messages = list(extract.extract('python', buf, {'_': None}, ["NOTE"], {}))
    message = messages[0]
    assert message[0] in (5, 6)  # Depends on whether #1126 is in
    assert message[1] == 'Text string that is on a new line'
    assert message[2] == ['NOTE: Text describing a test string']


def test_issue_1195_2():
    buf = BytesIO(b"""
# NOTE: This should still be considered, even if
#       the text is far away
foof = _(









            'Hey! Down here!')
""")
    messages = list(extract.extract('python', buf, {'_': None}, ["NOTE"], {}))
    message = messages[0]
    assert message[1] == 'Hey! Down here!'
    assert message[2] == [
        'NOTE: This should still be considered, even if',
        'the text is far away',
    ]


# Keywords declaring parameter names alongside their positions, so that
# both positional and keyword calls are matched.
NAMED_PARAMETER_KEYWORDS = {
    'ngettext': ((1, 'singular'), (2, 'plural')),
    'npgettext': ((1, 'msgctxt', 'c'), (2, 'singular'), (3, 'plural')),
}


def test_named_keyword_parameters_equivalent_spellings():
    # All of these spellings of the same ngettext call must yield the
    # same message.
    sources = [
        'msg = ngettext("file", "files", count)',
        'msg = ngettext("file", "files", n=count)',
        'msg = ngettext("file", plural="files", n=count)',
        'msg = ngettext(plural="files", singular="file", n=count)',
        'msg = ngettext(n=count, plural="files", singular="file")',
        'msg = ngettext(singular="fi" "le", plural="files", n=count)',
    ]
    for source in sources:
        messages = list(extract.extract(
            'python', BytesIO(source.encode()), NAMED_PARAMETER_KEYWORDS, [], {},
        ))
        assert messages == [(1, ('file', 'files'), [], None)], source


def test_named_keyword_parameters_multiline_and_comments():
    buf = BytesIO(b"""\
# TRANSLATORS: shown in the file menu
msg = ngettext(
    n=count,
    plural="files",
    singular="file",
)
""")
    messages = list(extract.extract(
        'python', buf, NAMED_PARAMETER_KEYWORDS, ['TRANSLATORS:'], {},
    ))
    assert messages == [
        (3, ('file', 'files'), ['TRANSLATORS: shown in the file menu'], None),
    ]


def test_named_keyword_parameters_context():
    sources = [
        'msg = npgettext(msgctxt="menu", singular="file", plural="files", n=count)',
        'msg = npgettext("menu", "file", "files", count)',
        'msg = npgettext("menu", "file", plural="files", n=count)',
    ]
    for source in sources:
        messages = list(extract.extract(
            'python', BytesIO(source.encode()), NAMED_PARAMETER_KEYWORDS, [], {},
        ))
        assert messages == [(1, ('file', 'files'), [], 'menu')], source


def test_named_keyword_parameters_nested_calls():
    keywords = {'_': None, **NAMED_PARAMETER_KEYWORDS}
    # The inner translation call is extracted; the outer call cannot be
    # determined statically and is skipped.
    buf = BytesIO(b'msg = ngettext(singular=_("file"), plural="files", n=count)')
    messages = list(extract.extract('python', buf, keywords, [], {}))
    assert messages == [(1, 'file', [], None)]

    # A translation call nested inside another is still recognized.
    buf = BytesIO(b'msg = _(ngettext("file", "files", count))')
    messages = list(extract.extract('python', buf, keywords, [], {}))
    assert messages == [(1, ('file', 'files'), [], None)]


def test_named_keyword_parameters_undeterminable_calls():
    keywords = NAMED_PARAMETER_KEYWORDS
    undeterminable = [
        # Star arguments cannot be determined statically.
        'ngettext(*args)',
        'ngettext(**kwargs)',
        # Only the plural is determinable here, so nothing is extracted.
        'ngettext(*args, plural="files")',
        # The same parameter bound both positionally and by keyword.
        'ngettext("file", plural="files", singular="other")',
        # The same keyword argument bound twice.
        'ngettext(singular="file", singular="other", plural="files")',
        # Dynamic f-strings are not static messages.
        'ngettext(singular=f"{name}", plural="files", n=count)',
        # Values computed at runtime are not static messages.
        'ngettext(singular=get_file_name(), plural="files", n=count)',
        'ngettext(singular=prefix, plural="files", n=count)',
    ]
    for source in undeterminable:
        messages = list(extract.extract(
            'python', BytesIO(source.encode()), keywords, [], {},
        ))
        assert messages == [], source

    determinable = [
        # Explicitly bound arguments remain determinable even in the
        # presence of **kwargs.
        'ngettext(singular="file", plural="files", **kwargs)',
        # Positional arguments before a *args expansion remain determinable.
        'ngettext("file", "files", *args)',
        # Static f-strings are extracted.
        'ngettext(singular=f"file", plural="files", n=count)',
    ]
    for source in determinable:
        messages = list(extract.extract(
            'python', BytesIO(source.encode()), keywords, [], {},
        ))
        assert messages == [(1, ('file', 'files'), [], None)], source


def test_named_only_keyword_parameters():
    # Specifications may also name parameters without a position; they
    # then only match keyword arguments.
    keywords = {'ngettext': ('singular', 'plural')}
    messages = list(extract.extract(
        'python',
        BytesIO(b'ngettext(n=count, plural="files", singular="file")'),
        keywords, [], {},
    ))
    assert messages == [(1, ('file', 'files'), [], None)]
    messages = list(extract.extract(
        'python', BytesIO(b'ngettext("file", "files", count)'), keywords, [], {},
    ))
    assert messages == []


def test_named_only_keyword_parameters_context():
    keywords = {'pgettext': (('msgctxt', 'c'), 'message')}
    messages = list(extract.extract(
        'python', BytesIO(b'pgettext(msgctxt="menu", message="file")'),
        keywords, [], {},
    ))
    assert messages == [(1, 'file', [], 'menu')]


def test_named_keyword_parameters_empty_msgid_warning():
    buf = BytesIO(b'msg = ngettext(singular="", plural="files", n=count)')
    stderr = sys.stderr
    sys.stderr = StringIO()
    try:
        messages = list(extract.extract(
            'python', buf, NAMED_PARAMETER_KEYWORDS, [], {},
        ))
        assert messages == []
        assert 'warning: Empty msgid.' in sys.stderr.getvalue()
    finally:
        sys.stderr = stderr


def test_extract_from_file_does_not_execute_source(tmp_path):
    marker = tmp_path / 'side_effect.txt'
    source = tmp_path / 'side_effect_module.py'
    source.write_text(
        'import pathlib\n'
        f'pathlib.Path({str(marker)!r}).write_text("executed", encoding="utf-8")\n'
        '# TRANSLATORS: extracted, not executed\n'
        'msg = ngettext(n=count, plural="files", singular="file")\n',
        encoding='utf-8',
    )
    messages = extract.extract_from_file(
        'python', str(source), NAMED_PARAMETER_KEYWORDS, ['TRANSLATORS:'],
    )
    assert messages == [
        (4, ('file', 'files'), ['TRANSLATORS: extracted, not executed'], None),
    ]
    # The module was analyzed statically, not imported or executed.
    assert not marker.exists()
