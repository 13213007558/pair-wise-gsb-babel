"""
Tests for supplemental CLDR data import helpers.
"""
from pathlib import Path

from scripts.import_cldr import _extract_plural_range_rules


CLDR_ROOT = (
    Path(__file__).resolve().parents[1] / 'cldr' / 'cldr-common-48.2' / 'common'
)


def test_extract_plural_range_rules():
    rules = _extract_plural_range_rules(CLDR_ROOT / 'supplemental' / 'pluralRanges.xml')
    assert rules['ka']('one', 'other') == 'one'
    assert rules['ka']('other', 'one') == 'other'
    assert rules['ka']('one', 'one') == 'other'
    assert rules['sl']('one', 'one') == 'few'
