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

from datetime import datetime
from io import BytesIO

import pytest

from babel import __version__ as VERSION
from babel.core import Locale, UnknownLocaleError
from babel.dates import format_datetime
from babel.messages import Message, checkers
from babel.messages.catalog import TranslationError
from babel.messages.checkers import (
    _validate_brace_format,
    _validate_format,
    python_brace_format,
    python_format,
)
from babel.messages.plurals import PLURALS
from babel.messages.pofile import read_po
from babel.util import LOCALTZ

# the last msgstr[idx] is always missing except for singular plural forms


def test_1_num_plurals_checkers():
    for _locale in [p for p in PLURALS if PLURALS[p][0] == 1]:
        try:
            locale = Locale.parse(_locale)
        except UnknownLocaleError:
            # Just an alias? Not what we're testing here, let's continue
            continue
        date = format_datetime(datetime.now(LOCALTZ), 'yyyy-MM-dd HH:mmZ', tzinfo=LOCALTZ, locale=_locale)
        plural = PLURALS[_locale][0]
        po_file = (f"""\
# {locale.english_name} translations for TestProject.
# Copyright (C) 2007 FooBar, Inc.
# This file is distributed under the same license as the TestProject
# project.
# FIRST AUTHOR <EMAIL@ADDRESS>, 2007.
#
msgid ""
msgstr ""
"Project-Id-Version: TestProject 0.1\\n"
"Report-Msgid-Bugs-To: bugs.address@email.tld\\n"
"POT-Creation-Date: 2007-04-01 15:30+0200\\n"
"PO-Revision-Date: {date}\\n"
"Last-Translator: FULL NAME <EMAIL@ADDRESS>\\n"
"Language-Team: {_locale} <LL@li.org>\n"
"Plural-Forms: nplurals={plural}; plural={plural};\\n"
"MIME-Version: 1.0\\n"
"Content-Type: text/plain; charset=utf-8\\n"
"Content-Transfer-Encoding: 8bit\\n"
"Generated-By: Babel {VERSION}\\n"

#. This will be a translator comment,
#. that will include several lines
#: project/file1.py:8
msgid "bar"
msgstr ""

#: project/file2.py:9
msgid "foobar"
msgid_plural "foobars"
msgstr[0] ""

""").encode('utf-8')

        # This test will fail for revisions <= 406 because so far
        # catalog.num_plurals was neglected
        catalog = read_po(BytesIO(po_file), _locale)
        message = catalog['foobar']
        checkers.num_plurals(catalog, message)


def test_2_num_plurals_checkers():
    # in this testcase we add an extra msgstr[idx], we should be
    # disregarding it
    for _locale in [p for p in PLURALS if PLURALS[p][0] == 2]:
        if _locale in ['nn', 'no']:
            _locale = 'nn_NO'
            num_plurals = PLURALS[_locale.split('_')[0]][0]
            plural_expr = PLURALS[_locale.split('_')[0]][1]
        else:
            num_plurals = PLURALS[_locale][0]
            plural_expr = PLURALS[_locale][1]
        try:
            locale = Locale(_locale)
            date = format_datetime(datetime.now(LOCALTZ),
                                   'yyyy-MM-dd HH:mmZ',
                                   tzinfo=LOCALTZ, locale=_locale)
        except UnknownLocaleError:
            # Just an alias? Not what we're testing here, let's continue
            continue
        po_file = f"""\
# {locale.english_name} translations for TestProject.
# Copyright (C) 2007 FooBar, Inc.
# This file is distributed under the same license as the TestProject
# project.
# FIRST AUTHOR <EMAIL@ADDRESS>, 2007.
#
msgid ""
msgstr ""
"Project-Id-Version: TestProject 0.1\\n"
"Report-Msgid-Bugs-To: bugs.address@email.tld\\n"
"POT-Creation-Date: 2007-04-01 15:30+0200\\n"
"PO-Revision-Date: {date}\\n"
"Last-Translator: FULL NAME <EMAIL@ADDRESS>\\n"
"Language-Team: {_locale} <LL@li.org>\\n"
"Plural-Forms: nplurals={num_plurals}; plural={plural_expr};\\n"
"MIME-Version: 1.0\\n"
"Content-Type: text/plain; charset=utf-8\\n"
"Content-Transfer-Encoding: 8bit\\n"
"Generated-By: Babel {VERSION}\\n"

#. This will be a translator comment,
#. that will include several lines
#: project/file1.py:8
msgid "bar"
msgstr ""

#: project/file2.py:9
msgid "foobar"
msgid_plural "foobars"
msgstr[0] ""
msgstr[1] ""
msgstr[2] ""

""".encode('utf-8')
        # we should be adding the missing msgstr[0]

        # This test will fail for revisions <= 406 because so far
        # catalog.num_plurals was neglected
        catalog = read_po(BytesIO(po_file), _locale)
        message = catalog['foobar']
        checkers.num_plurals(catalog, message)


def test_3_num_plurals_checkers():
    for _locale in [p for p in PLURALS if PLURALS[p][0] == 3]:
        plural = format_datetime(datetime.now(LOCALTZ), 'yyyy-MM-dd HH:mmZ', tzinfo=LOCALTZ, locale=_locale)
        english_name = Locale.parse(_locale).english_name
        po_file = rf"""\
# {english_name} translations for TestProject.
# Copyright (C) 2007 FooBar, Inc.
# This file is distributed under the same license as the TestProject
# project.
# FIRST AUTHOR <EMAIL@ADDRESS>, 2007.
#
msgid ""
msgstr ""
"Project-Id-Version: TestProject 0.1\n"
"Report-Msgid-Bugs-To: bugs.address@email.tld\n"
"POT-Creation-Date: 2007-04-01 15:30+0200\n"
"PO-Revision-Date: {plural}\n"
"Last-Translator: FULL NAME <EMAIL@ADDRESS>\n"
"Language-Team: {_locale} <LL@li.org>\n"
"Plural-Forms: nplurals={PLURALS[_locale][0]}; plural={PLURALS[_locale][0]};\n"
"MIME-Version: 1.0\n"
"Content-Type: text/plain; charset=utf-8\n"
"Content-Transfer-Encoding: 8bit\n"
"Generated-By: Babel {VERSION}\n"

#. This will be a translator comment,
#. that will include several lines
#: project/file1.py:8
msgid "bar"
msgstr ""

#: project/file2.py:9
msgid "foobar"
msgid_plural "foobars"
msgstr[0] ""
msgstr[1] ""

""".encode('utf-8')

        # This test will fail for revisions <= 406 because so far
        # catalog.num_plurals was neglected
        catalog = read_po(BytesIO(po_file), _locale)
        message = catalog['foobar']
        checkers.num_plurals(catalog, message)


def test_4_num_plurals_checkers():
    for _locale in [p for p in PLURALS if PLURALS[p][0] == 4]:
        date = format_datetime(datetime.now(LOCALTZ), 'yyyy-MM-dd HH:mmZ', tzinfo=LOCALTZ, locale=_locale)
        english_name = Locale.parse(_locale).english_name
        plural = PLURALS[_locale][0]
        po_file = rf"""\
# {english_name} translations for TestProject.
# Copyright (C) 2007 FooBar, Inc.
# This file is distributed under the same license as the TestProject
# project.
# FIRST AUTHOR <EMAIL@ADDRESS>, 2007.
#
msgid ""
msgstr ""
"Project-Id-Version: TestProject 0.1\n"
"Report-Msgid-Bugs-To: bugs.address@email.tld\n"
"POT-Creation-Date: 2007-04-01 15:30+0200\n"
"PO-Revision-Date: {date}\n"
"Last-Translator: FULL NAME <EMAIL@ADDRESS>\n"
"Language-Team: {_locale} <LL@li.org>\n"
"Plural-Forms: nplurals={plural}; plural={plural};\n"
"MIME-Version: 1.0\n"
"Content-Type: text/plain; charset=utf-8\n"
"Content-Transfer-Encoding: 8bit\n"
"Generated-By: Babel {VERSION}\n"

#. This will be a translator comment,
#. that will include several lines
#: project/file1.py:8
msgid "bar"
msgstr ""

#: project/file2.py:9
msgid "foobar"
msgid_plural "foobars"
msgstr[0] ""
msgstr[1] ""
msgstr[2] ""

""".encode('utf-8')

        # This test will fail for revisions <= 406 because so far
        # catalog.num_plurals was neglected
        catalog = read_po(BytesIO(po_file), _locale)
        message = catalog['foobar']
        checkers.num_plurals(catalog, message)


def test_5_num_plurals_checkers():
    for _locale in [p for p in PLURALS if PLURALS[p][0] == 5]:
        date = format_datetime(datetime.now(LOCALTZ), 'yyyy-MM-dd HH:mmZ', tzinfo=LOCALTZ, locale=_locale)
        english_name = Locale.parse(_locale).english_name
        plural = PLURALS[_locale][0]
        po_file = rf"""\
# {english_name} translations for TestProject.
# Copyright (C) 2007 FooBar, Inc.
# This file is distributed under the same license as the TestProject
# project.
# FIRST AUTHOR <EMAIL@ADDRESS>, 2007.
#
msgid ""
msgstr ""
"Project-Id-Version: TestProject 0.1\n"
"Report-Msgid-Bugs-To: bugs.address@email.tld\n"
"POT-Creation-Date: 2007-04-01 15:30+0200\n"
"PO-Revision-Date: {date}\n"
"Last-Translator: FULL NAME <EMAIL@ADDRESS>\n"
"Language-Team: {_locale} <LL@li.org>\n"
"Plural-Forms: nplurals={plural}; plural={plural};\n"
"MIME-Version: 1.0\n"
"Content-Type: text/plain; charset=utf-8\n"
"Content-Transfer-Encoding: 8bit\n"
"Generated-By: Babel {VERSION}\n"

#. This will be a translator comment,
#. that will include several lines
#: project/file1.py:8
msgid "bar"
msgstr ""

#: project/file2.py:9
msgid "foobar"
msgid_plural "foobars"
msgstr[0] ""
msgstr[1] ""
msgstr[2] ""
msgstr[3] ""

""".encode('utf-8')

        # This test will fail for revisions <= 406 because so far
        # catalog.num_plurals was neglected
        catalog = read_po(BytesIO(po_file), _locale)
        message = catalog['foobar']
        checkers.num_plurals(catalog, message)


def test_6_num_plurals_checkers():
    for _locale in [p for p in PLURALS if PLURALS[p][0] == 6]:
        english_name = Locale.parse(_locale).english_name
        date = format_datetime(datetime.now(LOCALTZ), 'yyyy-MM-dd HH:mmZ', tzinfo=LOCALTZ, locale=_locale)
        plural = PLURALS[_locale][0]
        po_file = rf"""\
# {english_name} translations for TestProject.
# Copyright (C) 2007 FooBar, Inc.
# This file is distributed under the same license as the TestProject
# project.
# FIRST AUTHOR <EMAIL@ADDRESS>, 2007.
#
msgid ""
msgstr ""
"Project-Id-Version: TestProject 0.1\n"
"Report-Msgid-Bugs-To: bugs.address@email.tld\n"
"POT-Creation-Date: 2007-04-01 15:30+0200\n"
"PO-Revision-Date: {date}\n"
"Last-Translator: FULL NAME <EMAIL@ADDRESS>\n"
"Language-Team: {_locale} <LL@li.org>\n"
"Plural-Forms: nplurals={plural}; plural={plural};\n"
"MIME-Version: 1.0\n"
"Content-Type: text/plain; charset=utf-8\n"
"Content-Transfer-Encoding: 8bit\n"
"Generated-By: Babel {VERSION}\n"

#. This will be a translator comment,
#. that will include several lines
#: project/file1.py:8
msgid "bar"
msgstr ""

#: project/file2.py:9
msgid "foobar"
msgid_plural "foobars"
msgstr[0] ""
msgstr[1] ""
msgstr[2] ""
msgstr[3] ""
msgstr[4] ""

""".encode('utf-8')

        # This test will fail for revisions <= 406 because so far
        # catalog.num_plurals was neglected
        catalog = read_po(BytesIO(po_file), _locale)
        message = catalog['foobar']
        checkers.num_plurals(catalog, message)


@pytest.mark.parametrize(
    ('msgid', 'msgstr'),
    [
        ('foo %s', 'foo'),
        (('foo %s', 'bar'), ('foo', 'bar')),
        (('foo', 'bar %s'), ('foo', 'bar')),
        (('foo %s', 'bar'), ('foo')),
        (('foo %s', 'bar %d'), ('foo %s', 'bar %d', 'baz')),
        (('foo %s', 'bar %d'), ('foo %s', 'bar %d', 'baz %d', 'qux')),
    ],
)
def test_python_format_invalid(msgid, msgstr):
    msg = Message(msgid, msgstr)
    with pytest.raises(TranslationError):
        python_format(None, msg)


@pytest.mark.parametrize(
    ('msgid', 'msgstr'),
    [
        ('foo', 'foo'),
        ('foo', 'foo %s'),
        ('foo %s', ''),
        (('foo %s', 'bar %d'), ('foo %s', 'bar %d')),
        (('foo %s', 'bar %d'), ('foo %s', 'bar %d', 'baz %d')),
        (('foo', 'bar %s'), ('foo')),
        (('foo', 'bar %s'), ('', '')),
        (('foo', 'bar %s'), ('foo', '')),
        (('foo %s', 'bar %d'), ('foo %s', '')),
    ],
)
def test_python_format_valid(msgid, msgstr):
    msg = Message(msgid, msgstr)
    python_format(None, msg)


@pytest.mark.parametrize(
    ('msgid', 'msgstr', 'error'),
    [
        ('%s %(foo)s', '%s %(foo)s', 'format string mixes positional and named placeholders'),
        ('foo %s', 'foo', 'placeholders are incompatible'),
        ('%s', '%(foo)s', 'the format strings are of different kinds'),
        ('%s', '%s %d', 'positional format placeholders are unbalanced'),
        ('%s', '%d', "incompatible format for placeholder 1: 's' and 'd' are not compatible"),
        (
            '%s %s %d',
            '%s %s %s',
            "incompatible format for placeholder 3: 'd' and 's' are not compatible",
        ),
        ('%(foo)s', '%(bar)s', "unknown named placeholder 'bar'"),
        ('%(foo)s', '%(bar)d', "unknown named placeholder 'bar'"),
        (
            '%(foo)s',
            '%(foo)d',
            "incompatible format for placeholder 'foo': 'd' and 's' are not compatible",
        ),
    ],
)
def test__validate_format_invalid(msgid, msgstr, error):
    with pytest.raises(TranslationError, match=error):
        _validate_format(msgid, msgstr)


@pytest.mark.parametrize(
    ('msgid', 'msgstr'),
    [
        ('foo', 'foo'),
        ('foo', 'foo %s'),
        ('%s foo', 'foo %s'),
        ('%i', '%d'),
        ('%d', '%u'),
        ('%x', '%X'),
        ('%f', '%F'),
        ('%F', '%g'),
        ('%g', '%G'),
        ('%(foo)s', 'foo'),
        ('%(foo)s', '%(foo)s %(foo)s'),
        ('%(bar)s foo %(n)d', '%(n)d foo %(bar)s'),
    ],
)
def test__validate_format_valid(msgid, msgstr):
    _validate_format(msgid, msgstr)


@pytest.mark.parametrize(
    ('msgid', 'msgstr'),
    [
        # missing placeholders (root arguments)
        ('{name}', 'Hallo'),
        ('{name} {pet}', '{name}'),
        ('{0} {1}', '{0}'),
        ('{} {}', '{0}'),
        # additional placeholders in the translation
        ('{name}', '{name} {pet}'),
        ('{0}', '{0} {1}'),
        # renamed placeholder changes the parameter contract
        ('{name!r:>{width}}', '{name}'),
        ('{name}', '{named}'),
        # missing or differing access paths
        ('{user.name}', '{user}'),
        ('{user}', '{user.name}'),
        ('{items[0]}', '{items[1]}'),
        ('{items[0]}', '{items.name}'),
        # incompatible conversions and presentation types
        ('{name!r}', '{name}'),
        ('{name!r}', '{name!a}'),
        ('{count:d}', '{count:s}'),
        ('{count:d}', '{count:f}'),
        # syntax errors
        ('{} {0}', '{} {0}'),  # mixes automatic and manual numbering
        ('{0} {}', '{0} {}'),  # mixes manual and automatic numbering
        ('{name}', '{name'),  # unbalanced braces
        ('{a:{b}}', '{a:{b}'),  # broken nested format spec
        ('{name!x}', '{name!x}'),  # unknown conversion specifier
        # pluralizable messages
        (('{count} file', '{count} files'), ('{count} file', 'files')),
        (('{count} file', '{count} files'), ('file', '{count} files')),
    ],
)
def test_python_brace_format_invalid(msgid, msgstr):
    msg = Message(msgid, msgstr)
    with pytest.raises(TranslationError):
        python_brace_format(None, msg)


@pytest.mark.parametrize(
    ('msgid', 'msgstr'),
    [
        ('{name}', '{name}'),
        ('{name}', ''),  # untranslated
        # placeholders may be reordered
        ('{0} {1}', '{1} {0}'),
        ('{name} {pet}', '{pet} {name}'),
        # automatic numbering in the msgid, explicit in the translation
        ('{} {}', '{1} {0}'),
        # attribute and subscript access
        ('{user.name}', '{user.name}'),
        ('{items[0]}', '{items[0]}'),
        ('{user.address[0]}', '{user.address[0]}'),
        # placeholders nested in the format spec
        ('{name:>{width}}', '{name:>{width}}'),
        ('{name!r:>{width}}', '{name!r:>{width}}'),
        # compatible conversions and presentation types
        ('{name}', '{name:s}'),
        ('{name!s}', '{name}'),
        ('{count:d}', '{count:x}'),
        ('{value:f}', '{value:g}'),
        # escaped braces are literals, not placeholders
        ('{{name}}', '{{name}}'),
        ('{name}', '{{{name}}}'),
        # pluralizable messages
        (('{count} file', '{count} files'), ('{count} Datei', '{count} Dateien')),
        (('{count} file', '{count} files'), ('{count} Datei', '{count} Dateien', '')),
    ],
)
def test_python_brace_format_valid(msgid, msgstr):
    msg = Message(msgid, msgstr)
    python_brace_format(None, msg)


@pytest.mark.parametrize(
    ('msgid', 'msgstr', 'error'),
    [
        (
            '{name!r:>{width}}',
            '{name}',
            "incompatible conversion for placeholder 'name': 'r' and None are not compatible",
        ),
        (
            '{name!r}',
            '{name!a}',
            "incompatible conversion for placeholder 'name': 'r' and 'a' are not compatible",
        ),
        (
            '{count:d}',
            '{count:s}',
            "incompatible format for placeholder 'count': 'd' and 's' are not compatible",
        ),
        ('{name} {pet}', '{name}', "missing placeholder 'pet'"),
        ('{0} {1}', '{0}', "missing placeholder '1'"),
        ('{name}', '{name} {pet}', "unknown placeholder 'pet'"),
        ('{user.name}', '{user}', "missing placeholder 'user.name'"),
        ('{user}', '{user.name}', "missing placeholder 'user'"),
        ('{items[0]}', '{items[1]}', r"missing placeholder 'items\[0\]'"),
        (
            '{} {0}',
            '{} {0}',
            'cannot switch from automatic field numbering to manual field specification',
        ),
        (
            '{0} {}',
            '{0} {}',
            'cannot switch from manual field specification to automatic field numbering',
        ),
        ('{name}', '{name', 'invalid brace format string'),
        ('{a:{b}', '{a:{b}', 'invalid brace format string'),
        ('{name!x}', '{name!x}', "unknown conversion specifier 'x'"),
    ],
)
def test__validate_brace_format_invalid(msgid, msgstr, error):
    with pytest.raises(TranslationError, match=error):
        _validate_brace_format(msgid, msgstr)


@pytest.mark.parametrize(
    ('msgid', 'msgstr'),
    [
        ('{name}', '{name}'),
        ('{0} {1}', '{1} {0}'),
        ('{} {}', '{1} {0}'),
        ('{user.name}', '{user.name}'),
        ('{items[0]}', '{items[0]}'),
        ('{name:>{width}}', '{name:>{width}}'),
        ('{a:{b:{c}}}', '{a:{b:{c}}}'),
        ('{:{}}', '{:{}}'),
        ('{name}', '{name:s}'),
        ('{name!s}', '{name}'),
        ('{count:d}', '{count:x}'),
        ('{value:f}', '{value:g}'),
        ('{{name}}', '{{name}}'),
        ('{name}', '{{{name}}}'),
    ],
)
def test__validate_brace_format_valid(msgid, msgstr):
    _validate_brace_format(msgid, msgstr)


def test_python_brace_format_plural_branch_located():
    # errors are located to the plural form they occurred in
    msg = Message(('{count} file', '{count} files'), ('{count} Datei', 'Dateien'))
    with pytest.raises(TranslationError, match=r"plural form 1: missing placeholder 'count'"):
        python_brace_format(None, msg)
    msg = Message(('{count} file', '{count} files'), ('Datei', '{count} Dateien'))
    with pytest.raises(TranslationError, match=r"plural form 0: missing placeholder 'count'"):
        python_brace_format(None, msg)


def test_python_brace_format_message_check():
    # errors are associated with the message they occurred in
    msg = Message('{name}', '{named}')
    errors = msg.check()
    assert len(errors) == 1
    assert "missing placeholder 'name'" in str(errors[0])
    msg = Message(('{count} file', '{count} files'), ('{count} Datei', 'Dateien'))
    errors = msg.check()
    assert len(errors) == 1
    assert "plural form 1: missing placeholder 'count'" in str(errors[0])


def test_python_brace_format_is_registered():
    assert python_brace_format in checkers.checkers


def test_python_brace_format_does_not_format_user_objects():
    # A sentinel that explodes on any kind of access; if the checker
    # detected placeholders by actually formatting user objects, any
    # of these operations would be triggered.
    class Sentinel:
        def __getattr__(self, name):
            raise AssertionError('attribute access')

        def __getitem__(self, key):
            raise AssertionError('item access')

        def __format__(self, format_spec):
            raise AssertionError('format')

        def __repr__(self):
            raise AssertionError('repr')

        def __str__(self):
            raise AssertionError('str')

    sentinel = Sentinel()
    msgid = '{obj.attr} and {obj[0]!r:>{width}}'
    msgstr = '{obj[0]!r:>{width}} and {obj.attr}'
    # the static analysis never touches the sentinel ...
    _validate_brace_format(msgid, msgstr)
    # ... while actually formatting the string would
    with pytest.raises(AssertionError):
        msgid.format(obj=sentinel, width=1)


def test_python_brace_format_and_python_format_are_independent():
    # a message may carry both kinds of placeholders; each checker only
    # validates its own kind
    msg = Message('%(pct)d {name}', '%(pct)d {name}')
    assert 'python-format' in msg.flags
    assert 'python-brace-format' in msg.flags
    python_format(None, msg)
    python_brace_format(None, msg)

    # the brace checker does not care about %-format problems ...
    bad_percent = Message('%(pct)d {name}', '%(pct)s {name}')
    python_brace_format(None, bad_percent)
    with pytest.raises(TranslationError):
        python_format(None, bad_percent)

    # ... and the %-format checker does not care about brace problems
    bad_brace = Message('%(pct)d {name}', '%(pct)d {named}')
    python_format(None, bad_brace)
    with pytest.raises(TranslationError):
        python_brace_format(None, bad_brace)
