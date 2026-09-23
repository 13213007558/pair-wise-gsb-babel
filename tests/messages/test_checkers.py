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
from babel.messages.checkers import _validate_format, python_format
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
        po_file = fr"""\
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
        po_file = fr"""\
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
        po_file = fr"""\
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
        po_file = fr"""\
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


@pytest.mark.parametrize(('msgid', 'msgstr'), [
    ('foo %s', 'foo'),
    (('foo %s', 'bar'), ('foo', 'bar')),
    (('foo', 'bar %s'), ('foo', 'bar')),
    (('foo %s', 'bar'), ('foo')),
    (('foo %s', 'bar %d'), ('foo %s', 'bar %d', 'baz')),
    (('foo %s', 'bar %d'), ('foo %s', 'bar %d', 'baz %d', 'qux')),
])
def test_python_format_invalid(msgid, msgstr):
    msg = Message(msgid, msgstr)
    with pytest.raises(TranslationError):
        python_format(None, msg)


@pytest.mark.parametrize(('msgid', 'msgstr'), [
    ('foo', 'foo'),
    ('foo', 'foo %s'),
    ('foo %s', ''),
    (('foo %s', 'bar %d'), ('foo %s', 'bar %d')),
    (('foo %s', 'bar %d'), ('foo %s', 'bar %d', 'baz %d')),
    (('foo', 'bar %s'), ('foo')),
    (('foo', 'bar %s'), ('', '')),
    (('foo', 'bar %s'), ('foo', '')),
    (('foo %s', 'bar %d'), ('foo %s', '')),
])
def test_python_format_valid(msgid, msgstr):
    msg = Message(msgid, msgstr)
    python_format(None, msg)


@pytest.mark.parametrize(('msgid', 'msgstr', 'error'), [
    ('%s %(foo)s', '%s %(foo)s', 'format string mixes positional and named placeholders'),
    ('foo %s', 'foo', 'placeholders are incompatible'),
    ('%s', '%(foo)s', 'the format strings are of different kinds'),
    ('%s', '%s %d', 'positional format placeholders are unbalanced'),
    ('%s', '%d', "incompatible format for placeholder 1: 's' and 'd' are not compatible"),
    ('%s %s %d', '%s %s %s', "incompatible format for placeholder 3: 'd' and 's' are not compatible"),
    ('%(foo)s', '%(bar)s', "unknown named placeholder 'bar'"),
    ('%(foo)s', '%(bar)d', "unknown named placeholder 'bar'"),
    ('%(foo)s', '%(foo)d', "incompatible format for placeholder 'foo': 'd' and 's' are not compatible"),
])
def test__validate_format_invalid(msgid, msgstr, error):
    with pytest.raises(TranslationError, match=error):
        _validate_format(msgid, msgstr)


@pytest.mark.parametrize(('msgid', 'msgstr'), [
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
])
def test__validate_format_valid(msgid, msgstr):
    _validate_format(msgid, msgstr)


@pytest.mark.parametrize(('msgid', 'msgstr'), [
    # nested field typo in the format spec
    ('{price:{width}.{precision}f}', '{price:{widht}.{precision}f}'),
    # integer presentation changed to an incompatible one
    ('{count:d}', '{count:f}'),
    ('{count:d}', '{count:s}'),
    # default presentation changed to an explicit incompatible one
    ('{count}', '{count:d}'),
    # access path not present in the original
    ('{user}', '{user.name}'),
    ('{items[0]}', '{items[1]}'),
    ('{user.name}', '{user.name.first}'),
    # unknown named placeholder
    ('{name}', '{naem}'),
    # positional placeholders may not be omitted or added
    ('{0} {1}', '{0}'),
    ('{0}', '{0} {1}'),
    # automatic and manual field numbering may not be mixed
    ('{} {0}', '{} {0}'),
    ('{0} {}', '{0} {}'),
    # incompatible conversion flags
    ('{name!r}', '{name!s}'),
    # unknown conversion specifier
    ('{name!x}', '{name!x}'),
    # unbalanced braces
    ('{name}', '{name'),
    # pluralizable messages
    (('{count:d} file', '{count:d} files'), ('{count:d} Datei', '{count:f} Dateien')),
    (('{count} file', '{count} files'), ('{count} Datei', '{count} Dateien {bogus}')),
])
def test_python_brace_format_invalid(msgid, msgstr):
    msg = Message(msgid, msgstr)
    assert 'python-brace-format' in msg.flags
    with pytest.raises(TranslationError):
        checkers.python_brace_format(None, msg)


@pytest.mark.parametrize(('msgid', 'msgstr'), [
    ('{name}', '{name}'),
    # empty translations are skipped
    ('{name}', ''),
    (('{count} file', '{count} files'), ('', '')),
    (('{count} file', '{count} files'), ('{count} Datei', '')),
    # named placeholders may be reordered and omitted
    ('{name} {age}', '{age} {name}'),
    ('{name} {age}', '{name}'),
    # width and precision changes are fine
    ('{count:8d}', '{count:12d}'),
    ('{price:8.2f}', '{price:12.4f}'),
    # compatible presentation types
    ('{count:d}', '{count:x}'),
    ('{price:.2f}', '{price:.3g}'),
    ('{name}', '{name:s}'),
    # explicit and automatic positional numbering resolve alike
    ('{} {}', '{1} {0}'),
    ('{0} {1}', '{} {}'),
    # positional and named placeholders may be mixed
    ('{0:d} {name}', '{name} {0:d}'),
    # attribute and item access paths from the original
    ('{user.name}', '{user.name}'),
    ('{items[0].price}', '{items[0].price}'),
    # conversions
    ('{name!r}', '{name!r}'),
    ('{name}', '{name!s}'),
    # nested fields in the format spec
    ('{price:{width}.{precision}f}', '{price:{width}.{precision}f}'),
    ('{price:{width}.{precision}f}', '{price:{precision}.{width}f}'),
    # doubled braces are literals
    ('{{literal}} {x}', '{{literal}} {x}'),
    ('{{literal}} {x}', '{x}'),
])
def test_python_brace_format_valid(msgid, msgstr):
    msg = Message(msgid, msgstr)
    checkers.python_brace_format(None, msg)


def test_python_brace_format_not_flagged():
    # Messages not flagged as python-brace-format are not checked,
    # even if the translation contains braces.
    msg = Message('plain text', '{not: a format string')
    assert 'python-brace-format' not in msg.flags
    checkers.python_brace_format(None, msg)


def test_python_brace_format_plural_msgstr_location():
    msg = Message(
        ('{count} file', '{count} files'),
        ('{count} Datei', '{count} Dateien {bogus}'),
    )
    with pytest.raises(TranslationError, match=r"^msgstr\[1\]: unknown named placeholder 'bogus'$"):
        checkers.python_brace_format(None, msg)


def test_python_brace_format_nested_field_location():
    msg = Message('{price:{width}.{precision}f}', '{price:{widht}.{precision}f}')
    with pytest.raises(
        TranslationError,
        match=r"unknown named placeholder 'widht' \(nested in the format spec of 'price'\)",
    ):
        checkers.python_brace_format(None, msg)


@pytest.mark.parametrize(('msgid', 'msgstr', 'error'), [
    ('{price:{width}.{precision}f}', '{price:{widht}.{precision}f}',
     r"unknown named placeholder 'widht' \(nested in the format spec of 'price'\)"),
    ('{0:8d}', '{0:8f}',
     r"incompatible format for placeholder '0': 'f' and 'd' are not compatible"),
    ('{user}', '{user.name}', r"unknown named placeholder 'user\.name'"),
    ('{0} {1}', '{0}', r'positional format placeholders are unbalanced'),
    ('{} {0}', '{} {0}',
     r'cannot switch from automatic field numbering to manual field specification'),
    ('{0} {}', '{0} {}',
     r'cannot switch from manual field specification to automatic field numbering'),
    ('{name!r}', '{name!a}',
     r"incompatible conversion for placeholder 'name': 'a' and 'r' are not compatible"),
    ('{name!y}', '{name!y}', r"unknown conversion specifier 'y' in field 'name'"),
    ('{name', '{name', r'invalid brace format string'),
])
def test__validate_brace_format_invalid(msgid, msgstr, error):
    with pytest.raises(TranslationError, match=error):
        checkers._validate_brace_format(msgid, msgstr)


def test_python_brace_format_catalog_check():
    # A message read from a PO file is automatically flagged and
    # reported by Catalog.check().
    po_file = b'''
msgid ""
msgstr ""
"Content-Type: text/plain; charset=utf-8\\n"

msgid "Total: {price:{width}.{precision}f}"
msgstr "Gesamt: {price:{widht}.{precision}f}"

msgid "{count} file"
msgid_plural "{count} files"
msgstr[0] "{count} Datei"
msgstr[1] "{count} Dateien {bogus}"
'''
    catalog = read_po(BytesIO(po_file), locale='de_DE')
    errors = {}
    for message, message_errors in catalog.check():
        errors[message.id] = message_errors
    assert len(errors) == 2
    singular_errors = errors['Total: {price:{width}.{precision}f}']
    assert len(singular_errors) == 1
    assert "unknown named placeholder 'widht'" in str(singular_errors[0])
    plural_errors = errors[('{count} file', '{count} files')]
    assert len(plural_errors) == 1
    assert "msgstr[1]: unknown named placeholder 'bogus'" in str(plural_errors[0])
