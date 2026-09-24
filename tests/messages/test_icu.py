"""
Tests for the ICU MessageFormat compiler and formatter in babel.messages.icu.
"""

from decimal import Decimal

import pytest

from babel.messages.icu import (
    ICUMessage,
    MessageFormatError,
    compile_message,
    format_message,
)

GENDER_NOTIFICATION = (
    "{gender, select, "
    "female{{count, plural, =0{She has no unread messages} "
    "one{She has # unread message} other{She has # unread messages}}} "
    "male{{count, plural, =0{He has no unread messages} "
    "one{He has # unread message} other{He has # unread messages}}} "
    "other{{count, plural, =0{They have no unread messages} "
    "one{They have # unread message} other{They have # unread messages}}}}"
)


def test_simple_argument():
    assert format_message("Hello, {name}!", {"name": "Ada"}, locale="en") == "Hello, Ada!"


def test_numeric_argument_is_locale_formatted():
    assert format_message("{n}", {"n": 1234567}, locale="en") == "1,234,567"


def test_argument_value_is_not_reparsed():
    value = "{count, plural, other{#}} __import__('os')"
    assert format_message("{x}", {"x": value}, locale="en") == value


def test_missing_argument_raises():
    with pytest.raises(MessageFormatError, match="missing argument 'name'"):
        format_message("Hi {name}", locale="en")


def test_nested_gender_select_with_plural():
    message = compile_message(GENDER_NOTIFICATION, locale="en")
    assert message.format(gender="female", count=0) == "She has no unread messages"
    assert message.format(gender="female", count=1) == "She has 1 unread message"
    assert message.format(gender="male", count=2) == "He has 2 unread messages"
    assert message.format(gender="other", count=7) == "They have 7 unread messages"
    # Unknown gender falls back to the 'other' select branch.
    assert message.format(gender="robot", count=1) == "They have 1 unread message"


def test_compiled_message_is_reusable():
    message = compile_message(GENDER_NOTIFICATION, locale="en")
    first = message.format(gender="female", count=1)
    second = message.format(gender="male", count=3)
    assert first == "She has 1 unread message"
    assert second == "He has 3 unread messages"
    # Formatting again still yields the same result (no per-format state).
    assert message.format(gender="female", count=1) == first


def test_select_nested_in_plural():
    pattern = (
        "{count, plural, other{{gender, select, "
        "female{She has # messages} other{They have # messages}}}}"
    )
    message = compile_message(pattern, locale="en")
    assert message.format(count=2, gender="female") == "She has 2 messages"
    assert message.format(count=5, gender="male") == "They have 5 messages"


def test_plural_categories_follow_locale():
    pattern = "{n, plural, one{one} few{few} many{many} other{other}}"
    assert format_message(pattern, {"n": 1}, locale="ru") == "one"
    assert format_message(pattern, {"n": 3}, locale="ru") == "few"
    assert format_message(pattern, {"n": 5}, locale="ru") == "many"
    assert format_message(pattern, {"n": 0}, locale="en") == "other"


def test_exact_value_matches_before_category():
    pattern = "{n, plural, =1{exactly one} one{category one} other{other}}"
    assert format_message(pattern, {"n": 1}, locale="en") == "exactly one"
    assert format_message(pattern, {"n": 2}, locale="en") == "other"


def test_exact_value_compares_number_before_offset():
    pattern = "{n, plural, offset:1 =2{you two} other{you and # others}}"
    # '=2' matches the original value 2, even though 2 - offset == 1.
    assert format_message(pattern, {"n": 2}, locale="en") == "you two"


def test_offset_affects_display_and_category():
    pattern = "{n, plural, offset:1 =0{nobody} one{you and one other} other{you and # others}}"
    assert format_message(pattern, {"n": 0}, locale="en") == "nobody"
    # 2 - 1 == 1 -> 'one' category; '#' shows the adjusted number.
    assert format_message(pattern, {"n": 2}, locale="en") == "you and one other"
    assert format_message(pattern, {"n": 3}, locale="en") == "you and 2 others"


def test_selectordinal():
    pattern = "{p, selectordinal, one{#st} two{#nd} few{#rd} other{#th}}"
    message = compile_message(pattern, locale="en")
    assert message.format(p=1) == "1st"
    assert message.format(p=2) == "2nd"
    assert message.format(p=3) == "3rd"
    assert message.format(p=11) == "11th"


def test_pound_binds_to_nearest_plural():
    pattern = "{a, plural, other{A# {b, plural, other{B#}} A#}}"
    assert format_message(pattern, {"a": 2, "b": 3}, locale="en") == "A2 B3 A2"


def test_pound_outside_plural_is_literal():
    assert format_message("hash # here", locale="en") == "hash # here"


def test_apostrophe_quoting():
    assert format_message("a''b", locale="en") == "a'b"
    assert format_message("'{x}'", locale="en") == "{x}"
    assert format_message("don't", locale="en") == "don't"
    assert format_message("'{'quoted'}'", locale="en") == "{quoted}"


def test_quoted_pound_inside_plural():
    pattern = "{n, plural, other{'#' means number, value #}}"
    assert format_message(pattern, {"n": 4}, locale="en") == "# means number, value 4"


def test_decimal_trailing_zeros_preserved():
    assert format_message("{n}", {"n": Decimal("1.50")}, locale="en") == "1.50"
    pattern = "{n, plural, one{one} other{other #}}"
    # Decimal('1.0') has a visible fraction digit, so it is not 'one' in English.
    assert format_message(pattern, {"n": Decimal("1.0")}, locale="en") == "other 1.0"
    assert format_message(pattern, {"n": Decimal("1")}, locale="en") == "one"


def test_plural_argument_must_be_numeric():
    with pytest.raises(MessageFormatError, match="must be a number"):
        format_message("{n, plural, other{#}}", {"n": "abc"}, locale="en")


def test_missing_other_branch_raises_with_position():
    with pytest.raises(MessageFormatError) as excinfo:
        compile_message("{g, select, female{x}}", locale="en")
    assert "missing required 'other' branch" in str(excinfo.value)
    assert excinfo.value.position == 0


def test_duplicate_selector_raises_with_position():
    pattern = "{n, plural, one{a} one{b} other{c}}"
    with pytest.raises(MessageFormatError) as excinfo:
        compile_message(pattern, locale="en")
    assert "duplicate selector 'one'" in str(excinfo.value)
    assert excinfo.value.position == pattern.index("one{b}")


def test_duplicate_exact_selector_raises_with_position():
    pattern = "{n, plural, =1{a} =1{b} other{c}}"
    with pytest.raises(MessageFormatError) as excinfo:
        compile_message(pattern, locale="en")
    assert "duplicate selector '=1'" in str(excinfo.value)
    assert excinfo.value.position == pattern.index("=1{b}")


def test_unclosed_branch_raises_with_position():
    with pytest.raises(MessageFormatError) as excinfo:
        compile_message("{n, plural, one{a} other{b}", locale="en")
    assert "unclosed plural branches" in str(excinfo.value)
    assert excinfo.value.position == 0


def test_unmatched_brace_raises():
    with pytest.raises(MessageFormatError):
        compile_message("hello }", locale="en")


def test_unknown_plural_selector_raises():
    with pytest.raises(MessageFormatError, match="unknown plural selector"):
        compile_message("{n, plural, dozen{x} other{y}}", locale="en")


def test_format_message_kwargs():
    assert format_message("{a} and {b}", locale="en", a=1, b=2) == "1 and 2"


def test_compiled_message_repr_and_attributes():
    message = compile_message("Hi {name}", locale="en")
    assert isinstance(message, ICUMessage)
    assert message.pattern == "Hi {name}"
    assert str(message.locale) == "en"
    assert "Hi {name}" in repr(message)
