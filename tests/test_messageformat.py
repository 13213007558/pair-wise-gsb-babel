import decimal

import pytest

from babel.messageformat import (
    CompiledMessage,
    MessageFormatError,
    compile_message,
    format_message,
)


def test_simple_argument():
    assert format_message("Hello, {name}!", {"name": "Ada"}) == "Hello, Ada!"


def test_positional_arguments():
    message = compile_message("{0} and {1}")
    assert message.format("a", "b") == "a and b"
    assert message.format({"0": "x", "1": "y"}) == "x and y"


def test_missing_argument_raises():
    message = compile_message("Hello, {name}!")
    with pytest.raises(KeyError):
        message.format()


def test_select():
    message = compile_message(
        "{gender, select, female{She} male{He} other{They}} replied.",
        locale="en",
    )
    assert message.format(gender="female") == "She replied."
    assert message.format(gender="male") == "He replied."
    assert message.format(gender="unknown") == "They replied."


def test_plural_categories():
    message = compile_message(
        "{count, plural, one{# message} other{# messages}}",
        locale="en",
    )
    assert message.format(count=1) == "1 message"
    assert message.format(count=2) == "2 messages"
    assert message.format(count=0) == "0 messages"


def test_plural_exact_value_matches_before_category():
    message = compile_message(
        "{count, plural, =0{no messages} one{# message} other{# messages}}",
        locale="en",
    )
    # "en" has no "zero" category; without the =0 branch this would be "other".
    assert message.format(count=0) == "no messages"
    assert message.format(count=1) == "1 message"
    assert message.format(count=3) == "3 messages"


def test_plural_offset():
    message = compile_message(
        "{n, plural, offset:1 =0{nobody} =1{just you} "
        "one{you and # other} other{you and # others}}",
        locale="en",
    )
    assert message.format(n=0) == "nobody"
    assert message.format(n=1) == "just you"
    # The offset is subtracted for both category selection and "#".
    assert message.format(n=2) == "you and 1 other"
    assert message.format(n=5) == "you and 4 others"


def test_plural_offset_without_exact_match():
    message = compile_message(
        "{n, plural, offset:1 one{# other} other{# others}}",
        locale="en",
    )
    # 1 - 1 = 0, which is "other" in English.
    assert message.format(n=1) == "0 others"
    assert message.format(n=2) == "1 other"


def test_selectordinal():
    message = compile_message(
        "{pos, selectordinal, one{#st} two{#nd} few{#rd} other{#th}}",
        locale="en",
    )
    assert [message.format(pos=n) for n in (1, 2, 3, 4, 11, 22, 103)] == [
        "1st",
        "2nd",
        "3rd",
        "4th",
        "11th",
        "22nd",
        "103rd",
    ]


def test_nested_selectors():
    message = compile_message(
        "{gender, select, "
        "female{{count, plural, one{She has # message} other{She has # messages}}} "
        "male{{count, plural, one{He has # message} other{He has # messages}}} "
        "other{{count, plural, one{They have # message} other{They have # messages}}}}",
        locale="en",
    )
    assert message.format(gender="female", count=1) == "She has 1 message"
    assert message.format(gender="male", count=5) == "He has 5 messages"
    assert message.format(gender="other", count=1) == "They have 1 message"


def test_pound_binds_to_nearest_plural():
    message = compile_message(
        "{a, plural, other{{b, plural, other{inner #}} then outer #}}",
        locale="en",
    )
    assert message.format(a=7, b=3) == "inner 3 then outer 7"


def test_pound_inside_nested_select_uses_enclosing_plural():
    message = compile_message(
        "{n, plural, other{{g, select, f{she has #} other{they have #}}}}",
        locale="en",
    )
    assert message.format(n=3, g="f") == "she has 3"
    assert message.format(n=3, g="x") == "they have 3"


def test_pound_outside_plural_is_literal():
    assert format_message("a # b", locale="en") == "a # b"


def test_apostrophe_quoting():
    # A lone apostrophe not before a syntax character is literal.
    assert format_message("a'b", locale="en") == "a'b"
    # Doubled apostrophe is a literal apostrophe.
    assert format_message("a''b", locale="en") == "a'b"
    # Apostrophe quotes a syntax character.
    assert format_message("'{'x'}'", locale="en") == "{x}"
    assert format_message("'{name}'", {"name": "Ada"}, locale="en") == "{name}"


def test_literal_braces_via_quoting():
    message = compile_message("'}'{n, plural, other{#}}'{'", locale="en")
    assert message.format(n=2) == "}2{"


def test_decimal_trailing_zeros_preserved():
    message = compile_message("{n, plural, other{# kg}}", locale="en")
    assert message.format(n=decimal.Decimal("2.50")) == "2.50 kg"
    assert message.format(n=decimal.Decimal("2")) == "2 kg"


def test_decimal_trailing_zeros_affect_category():
    # Russian: integers ending in 1 are "one", but visible fraction
    # digits (v > 0) make the value "other".
    message = compile_message(
        "{n, plural, one{# file} other{# files}}",
        locale="ru",
    )
    assert message.format(n=1) == "1 file"
    assert message.format(n=decimal.Decimal("1.0")) == "1,0 files"


def test_compiled_message_is_reusable():
    message = compile_message("{count, plural, one{# hit} other{# hits}}", locale="en")
    assert isinstance(message, CompiledMessage)
    assert message.format(count=1) == "1 hit"
    assert message.format(count=10) == "10 hits"
    assert message.format(count=1) == "1 hit"


def test_parameters_are_not_parsed_as_templates():
    message = compile_message("{value}", locale="en")
    assert message.format(value="{0, plural, other{#}}") == "{0, plural, other{#}}"


def test_parameters_are_not_executed():
    message = compile_message("{value}", locale="en")
    payload = "__import__('os').system('echo unsafe')"
    assert message.format(value=payload) == payload


def test_missing_other_branch_reports_position():
    pattern = "x {count, plural, one{one}}"
    with pytest.raises(MessageFormatError) as excinfo:
        compile_message(pattern)
    assert excinfo.value.position == 2
    assert "other" in str(excinfo.value)


def test_select_missing_other_branch():
    with pytest.raises(MessageFormatError) as excinfo:
        compile_message("{g, select, female{She}}")
    assert excinfo.value.position == 0


def test_duplicate_selector_reports_position():
    pattern = "{n, plural, one{a} one{b} other{c}}"
    with pytest.raises(MessageFormatError) as excinfo:
        compile_message(pattern)
    assert excinfo.value.position == pattern.index("one{b}")


def test_duplicate_exact_value_reports_position():
    pattern = "{n, plural, =1{a} =1{b} other{c}}"
    with pytest.raises(MessageFormatError) as excinfo:
        compile_message(pattern)
    assert excinfo.value.position == pattern.index("=1{b}")


def test_unclosed_placeholder_reports_position():
    pattern = "ok {n, plural, one{a} other{b}"
    with pytest.raises(MessageFormatError) as excinfo:
        compile_message(pattern)
    assert excinfo.value.position == 3


def test_unclosed_branch_reports_position():
    pattern = "{n, plural, one{a"
    with pytest.raises(MessageFormatError) as excinfo:
        compile_message(pattern)
    assert excinfo.value.position == 0


def test_unmatched_closing_brace_reports_position():
    with pytest.raises(MessageFormatError) as excinfo:
        compile_message("a } b")
    assert excinfo.value.position == 2


def test_unsupported_argument_type():
    with pytest.raises(MessageFormatError) as excinfo:
        compile_message("{n, number}")
    assert "number" in str(excinfo.value)


def test_non_numeric_plural_value():
    message = compile_message("{n, plural, other{#}}", locale="en")
    with pytest.raises(MessageFormatError):
        message.format(n="not-a-number")


def test_format_message_one_shot():
    assert (
        format_message(
            "{n, plural, one{# apple} other{# apples}}",
            {"n": 2},
            locale="en",
        )
        == "2 apples"
    )


def test_locale_instance_accepted():
    from babel import Locale

    message = compile_message("{n, plural, one{#} other{#}}", Locale.parse("de"))
    assert message.format(n=1500) == "1.500"
