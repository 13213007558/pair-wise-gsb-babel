# Copyright (C) 2007-2011 Edgewall Software, 2013-2026 the Babel team
# All rights reserved.
#
# This software is licensed as described in the file LICENSE, which
# you should have received as part of this distribution. The terms
# are also available at https://github.com/python-babel/babel/blob/master/LICENSE.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://github.com/python-babel/babel/commits/master/.
import decimal

import pytest

from babel.messages.catalog import Catalog
from babel.messages.icu_plural import ICUMessage, ICUPluralError

EN_FILES = (
    '{count, plural, offset:1 '
    '=0 {No files} '
    '=1 {just now} '
    'one {just now} '
    'other {# files}}'
)

RU_FILES = (
    '{count, plural, offset:1 '
    '=0 {Нет файлов} '
    'one {# файл} '
    'few {# файла} '
    'many {# файлов} '
    'other {# файла}}'
)

AR_FILES = (
    '{count, plural, offset:1 '
    '=0 {لا ملفات} '
    'one {ملف واحد} '
    'two {ملفان} '
    'few {# ملفات} '
    'many {# ملفًا} '
    'other {# ملف}}'
)


def test_english_offset_and_explicit():
    msg = ICUMessage.parse(EN_FILES)
    assert msg.format({'count': 0}, locale='en') == 'No files'
    assert msg.format({'count': 1}, locale='en') == 'just now'  # explicit =1
    assert msg.format({'count': 2}, locale='en') == 'just now'  # 2 - offset = 1 -> one
    assert msg.format({'count': 5}, locale='en') == '4 files'  # '#' deducts the offset
    assert msg.format({'count': 1235}, locale='en') == '1,234 files'


def test_russian_categories():
    msg = ICUMessage.parse(RU_FILES)
    assert msg.format({'count': 0}, locale='ru') == 'Нет файлов'
    assert msg.format({'count': 2}, locale='ru') == '1 файл'
    assert msg.format({'count': 5}, locale='ru') == '4 файла'
    assert msg.format({'count': 7}, locale='ru') == '6 файлов'
    assert msg.format({'count': 2.5}, locale='ru') == '1,5 файла'


def test_arabic_categories():
    msg = ICUMessage.parse(AR_FILES)
    assert msg.format({'count': 0}, locale='ar') == 'لا ملفات'
    assert msg.format({'count': 2}, locale='ar') == 'ملف واحد'
    assert msg.format({'count': 3}, locale='ar') == 'ملفان'
    assert msg.format({'count': 5}, locale='ar') == '4 ملفات'
    assert msg.format({'count': 13}, locale='ar') == '12 ملفًا'
    assert msg.format({'count': 102}, locale='ar') == '101 ملف'


@pytest.mark.parametrize('value', [
    2,
    2.0,
    decimal.Decimal('2'),
    decimal.Decimal('2.00'),
    '2',
])
def test_same_branch_regardless_of_number_type(value):
    msg = ICUMessage.parse('{n, plural, offset:1 =2 {two} one {one} other {#}}')
    assert msg.format({'n': value}, locale='en') == 'two'


def test_float_error_does_not_leak_into_selection():
    msg = ICUMessage.parse('{n, plural, =0.3 {three tenths} other {other}}')
    assert msg.format({'n': 0.3}, locale='en') == 'three tenths'
    # 0.1 + 0.2 is 0.30000000000000004 and must not match =0.3
    assert msg.format({'n': 0.1 + 0.2}, locale='en') == 'other'


def test_decimal_offset_deduction_is_exact():
    msg = ICUMessage.parse('{n, plural, offset:1 other {#}}')
    assert msg.format({'n': decimal.Decimal('3.5')}, locale='en') == '2.5'
    assert msg.format({'n': 3.5}, locale='en') == '2.5'


def test_negative_numbers():
    msg = ICUMessage.parse('{n, plural, =-2 {minus two} one {one} other {#}}')
    assert msg.format({'n': -2}, locale='en') == 'minus two'
    # the category is selected on the absolute value, per CLDR operands
    assert msg.format({'n': -1}, locale='en') == 'one'
    assert msg.format({'n': -3}, locale='en') == '-3'


def test_nested_plural():
    msg = ICUMessage.parse(
        '{files, plural, offset:1 '
        '=0 {No files} '
        'one {One file} '
        'other {# files{stars, plural, =0 {} other {, # starred}}}}',
    )
    assert msg.format({'files': 0, 'stars': 0}, locale='en') == 'No files'
    assert msg.format({'files': 2, 'stars': 0}, locale='en') == 'One file'
    assert msg.format({'files': 3, 'stars': 0}, locale='en') == '2 files'
    assert msg.format({'files': 3, 'stars': 4}, locale='en') == '2 files, 4 starred'


def test_plain_message_and_arguments():
    assert ICUMessage.parse('plain text').format(locale='en') == 'plain text'
    msg = ICUMessage.parse('{user} posted # photos')
    # '#' outside a plural is just a literal character
    assert msg.format({'user': 'Anne'}, locale='en') == 'Anne posted # photos'


def test_missing_variable():
    msg = ICUMessage.parse('{n, plural, other {#}}')
    with pytest.raises(ICUPluralError) as excinfo:
        msg.format({}, locale='en')
    assert excinfo.value.position is None


def test_non_numeric_variable():
    msg = ICUMessage.parse('{n, plural, other {#}}')
    with pytest.raises(ICUPluralError):
        msg.format({'n': 'not-a-number'}, locale='en')


def test_missing_other_is_rejected():
    pattern = '{n, plural, one {x}}'
    with pytest.raises(ICUPluralError) as excinfo:
        ICUMessage.parse(pattern)
    assert excinfo.value.position == 0
    assert 'other' in str(excinfo.value)


def test_duplicate_explicit_value_is_rejected():
    pattern = '{n, plural, =0 {a} =0 {b} other {c}}'
    with pytest.raises(ICUPluralError) as excinfo:
        ICUMessage.parse(pattern)
    assert excinfo.value.position == pattern.index('=0', pattern.index('=0') + 1)


def test_duplicate_category_is_rejected():
    pattern = '{n, plural, one {a} one {b} other {c}}'
    with pytest.raises(ICUPluralError) as excinfo:
        ICUMessage.parse(pattern)
    assert excinfo.value.position == pattern.index('one', pattern.index('one') + 1)


@pytest.mark.parametrize('offset', ['-1', '1.5', 'x'])
def test_invalid_offset_is_rejected(offset):
    pattern = '{n, plural, offset:' + offset + ' other {x}}'
    with pytest.raises(ICUPluralError) as excinfo:
        ICUMessage.parse(pattern)
    assert excinfo.value.position == pattern.index(offset)


def test_invalid_category_is_rejected():
    pattern = '{n, plural, couple {x} other {y}}'
    with pytest.raises(ICUPluralError) as excinfo:
        ICUMessage.parse(pattern)
    assert excinfo.value.position == pattern.index('couple')


def test_unsupported_placeholder_type_is_rejected():
    pattern = '{n, select, a {x} other {y}}'
    with pytest.raises(ICUPluralError) as excinfo:
        ICUMessage.parse(pattern)
    assert excinfo.value.position == pattern.index('select')


def test_unterminated_plural_is_rejected():
    pattern = '{n, plural, other {x'
    with pytest.raises(ICUPluralError) as excinfo:
        ICUMessage.parse(pattern)
    assert excinfo.value.position == len(pattern)


def test_unmatched_closing_brace_is_rejected():
    with pytest.raises(ICUPluralError) as excinfo:
        ICUMessage.parse('foo}')
    assert excinfo.value.position == 3


def test_catalog_icu_format_with_context():
    catalog = Catalog(locale='en')
    catalog.add('files', EN_FILES, context='dashboard')
    assert catalog.icu_format('files', context='dashboard', count=0) == 'No files'
    assert catalog.icu_format('files', context='dashboard', count=1) == 'just now'
    assert catalog.icu_format('files', context='dashboard', count=2) == 'just now'
    assert catalog.icu_format('files', context='dashboard', count=5) == '4 files'
    # the message is still stored and accessible the gettext way
    message = catalog.get('files', context='dashboard')
    assert message.string == EN_FILES


def test_catalog_icu_format_uses_catalog_locale():
    catalog = Catalog(locale='ru')
    catalog.add('files', RU_FILES)
    assert catalog.icu_format('files', count=5) == '4 файла'


def test_catalog_icu_format_untranslated_falls_back_to_id():
    catalog = Catalog(locale='en')
    catalog.add('files', EN_FILES)
    untranslated = Catalog(locale='en')
    untranslated.add('files')
    assert untranslated.icu_format('files', count=0) == 'files'
    assert catalog.icu_format('files', count=0) == 'No files'


def test_catalog_icu_format_missing_message():
    catalog = Catalog(locale='en')
    with pytest.raises(KeyError):
        catalog.icu_format('no-such-message')


def test_catalog_messages_without_icu_plural_are_unaffected():
    catalog = Catalog(locale='en')
    catalog.add('hello', 'Hello {name}!')
    catalog.add(('%(num)s apple', '%(num)s apples'), ('%(num)s apple', '%(num)s apples'))
    assert catalog.icu_format('hello', name='World') == 'Hello World!'
    # gettext-style plural metadata and storage stay as they were
    assert catalog.num_plurals == 2
    assert catalog['%(num)s apple'].string == ('%(num)s apple', '%(num)s apples')
