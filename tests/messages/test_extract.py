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


# A keyword specification that declares parameter names and their roles;
# the declaration order also defines the positional parameter order.
NAMED_NGETTEXT_SPEC = {
    'ngettext': {'singular': 'msgid', 'plural': 'msgid_plural', 'n': None},
}


def test_named_keyword_spec_call_spellings():
    # The same ngettext call, written with positional or keyword arguments,
    # must yield the same message.
    buf = BytesIO(b"""# NOTE: deleted files
a = ngettext('file deleted', 'files deleted', count)
b = ngettext(n=count, plural='files deleted', singular='file deleted')
c = ngettext('file deleted', plural='files deleted', n=count)
d = ngettext(
    n=count,
    plural='files '
           'deleted',
    singular='file deleted',
)
""")
    messages = list(extract.extract('python', buf, NAMED_NGETTEXT_SPEC, ['NOTE:'], {}))
    assert messages == [
        (2, ('file deleted', 'files deleted'), ['NOTE: deleted files'], None),
        (3, ('file deleted', 'files deleted'), [], None),
        (4, ('file deleted', 'files deleted'), [], None),
        (9, ('file deleted', 'files deleted'), [], None),
    ]


def test_named_keyword_spec_context():
    keywords = {'pgettext': {'context': 'msgctxt', 'msgid': 'msgid'}}
    buf = BytesIO(b"""a = pgettext('button', 'Open')
b = pgettext(msgid='Open', context='button')
c = pgettext(context='button', msgid='Op'
             'en')
""")
    messages = list(extract.extract('python', buf, keywords, [], {}))
    assert messages == [
        (1, 'Open', [], 'button'),
        (2, 'Open', [], 'button'),
        (3, 'Open', [], 'button'),
    ]


def test_named_keyword_spec_context_and_plural():
    keywords = {
        'npgettext': {
            'context': 'msgctxt',
            'singular': 'msgid',
            'plural': 'msgid_plural',
            'n': None,
        },
    }
    buf = BytesIO(b"""a = npgettext('files', 'file', 'files', count)
b = npgettext(n=count, plural='files', singular='file', context='files')
""")
    messages = list(extract.extract('python', buf, keywords, [], {}))
    assert messages == [
        (1, ('file', 'files'), [], 'files'),
        (2, ('file', 'files'), [], 'files'),
    ]


def test_named_keyword_spec_translator_comments():
    buf = BytesIO(b"""# NOTE: this comment is attached
# NOTE: and this one too
a = ngettext(n=count,
             plural='files',
             singular='file')
""")
    messages = list(extract.extract('python', buf, NAMED_NGETTEXT_SPEC, ['NOTE:'], {}))
    assert messages == [
        (5, ('file', 'files'), ['NOTE: this comment is attached', 'NOTE: and this one too'], None),
    ]


def test_named_keyword_spec_nested_calls():
    keywords = {'_': None, **NAMED_NGETTEXT_SPEC}
    buf = BytesIO(b"""a = ngettext(singular=_('inner'), plural='outers', n=count)
b = ngettext('outer', 'outers', ngettext('x', 'y', 2))
""")
    messages = list(extract.extract('python', buf, keywords, [], {}))
    assert messages == [
        (1, 'inner', [], None),
        (2, ('outer', 'outers'), [], None),
        (2, ('x', 'y'), [], None),
    ]


def test_named_keyword_spec_undeterminable_arguments():
    # Only calls whose declared roles are all statically determinable
    # produce a message.
    buf = BytesIO(b"""a = ngettext(*args)
b = ngettext(**kwargs)
c = ngettext('file', *args)
d = ngettext(*args, plural='files')
e = ngettext('file', 'files', count, **kwargs)
f = ngettext('file', singular='file', plural='files')
g = ngettext(singular='file', singular='files', plural='files')
h = ngettext('file', 'files')
""")
    messages = list(extract.extract('python', buf, NAMED_NGETTEXT_SPEC, [], {}))
    assert messages == [
        (5, ('file', 'files'), [], None),
        (8, ('file', 'files'), [], None),
    ]


def test_named_keyword_spec_non_static_arguments_ignored():
    buf = BytesIO(b"""a = ngettext(f'file {name}', 'files', count)
b = ngettext('file' + suffix, 'files', count)
c = ngettext(get_msgid(), 'files', count)
d = ngettext(msgid, 'files', count)
e = ngettext('file'.upper(), 'files', count)
def ngettext(singular, plural, n):
    pass
f = not_a_keyword('file', 'files')
g = ngettext('file', 'files', count)
""")
    messages = list(extract.extract('python', buf, NAMED_NGETTEXT_SPEC, [], {}))
    assert messages == [(9, ('file', 'files'), [], None)]


def test_named_keyword_spec_empty_msgid_warning():
    buf = BytesIO(b"msg = ngettext(singular='', plural='files', n=count)\n")
    stderr = sys.stderr
    sys.stderr = StringIO()
    try:
        messages = list(extract.extract('python', buf, NAMED_NGETTEXT_SPEC, [], {}))
        assert messages == []
        assert 'warning: Empty msgid.' in sys.stderr.getvalue()
    finally:
        sys.stderr = stderr


def test_named_keyword_spec_positional_spec_still_works_with_keyword_calls():
    # A classic numeric spec keeps its original semantics even for calls
    # that use keyword arguments: argument values are matched by their
    # position in the call.
    buf = BytesIO(b"""a = ngettext('file', 'files', n=count)
b = ngettext(n=count, plural='files', singular='file')
""")
    messages = list(extract.extract('python', buf, {'ngettext': (1, 2)}, [], {}))
    assert messages == [(1, ('file', 'files'), [], None)]


def test_named_keyword_spec_with_javascript_extractor():
    # Other extractors keep the original protocol; their positional
    # arguments are mapped to parameter names by declaration order.
    buf = BytesIO(b"""a = ngettext('file', 'files', count);
""")
    messages = list(extract.extract('javascript', buf, NAMED_NGETTEXT_SPEC, [], {}))
    assert messages == [(1, ('file', 'files'), [], None)]


def test_extract_from_file_with_named_keyword_spec(tmp_path):
    source = tmp_path / 'messages.py'
    source.write_text(
        '# NOTE: via file\n'
        'a = ngettext(n=count, plural="files", singular="file")\n',
        encoding='utf-8',
    )
    messages = extract.extract_from_file(
        'python',
        str(source),
        keywords=NAMED_NGETTEXT_SPEC,
        comment_tags=['NOTE:'],
    )
    assert messages == [(2, ('file', 'files'), ['NOTE: via file'], None)]


def test_named_keyword_spec_via_mapping_config(tmp_path):
    # A named keyword specification declared in a mapping configuration
    # file must reach the extractor through the standard config path.
    from babel.messages import frontend

    (tmp_path / 'module.py').write_text(
        '# NOTE: from config\n'
        'msg = ngettext(n=count, plural="files", singular="file")\n',
        encoding='utf-8',
    )
    config = StringIO(
        '[python: **.py]\n'
        'keywords = ngettext:singular=msgid,plural=msgid_plural,n=\n',
    )
    method_map, options_map = frontend.parse_mapping_cfg(config)
    messages = list(
        extract.extract_from_dir(
            str(tmp_path),
            method_map=method_map,
            options_map=options_map,
            keywords={},
            comment_tags=['NOTE:'],
        ),
    )
    assert messages == [
        ('module.py', 2, ('file', 'files'), ['NOTE: from config'], None),
    ]


def test_extract_from_file_does_not_execute_source(tmp_path):
    # Extraction must not execute or import the scanned module: this module
    # would create a file as a side effect of being executed.
    marker = tmp_path / 'side_effect.txt'
    source = tmp_path / 'side_effect_module.py'
    source.write_text(
        'from pathlib import Path\n'
        f'Path({str(marker)!r}).write_text("executed")\n'
        'msg = ngettext(plural="files", singular="file", n=count)\n',
        encoding='utf-8',
    )
    messages = extract.extract_from_file('python', str(source), keywords=NAMED_NGETTEXT_SPEC)
    assert messages == [(3, ('file', 'files'), [], None)]
    assert not marker.exists()
