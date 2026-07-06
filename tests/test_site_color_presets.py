"""
Tests for services/site_color_presets.py.

Symbols under test:
  Module:services/site_color_presets.py
    is_valid_color_scheme, resolve_color_scheme
"""

import pytest

from services.site_color_presets import (
    COLOR_PRESETS,
    PRESET_NAMES,
    is_valid_color_scheme,
    resolve_color_scheme,
)


def test_preset_names_match_color_presets_keys():
    assert set(PRESET_NAMES) == set(COLOR_PRESETS.keys())
    assert len(PRESET_NAMES) == 10


def test_every_preset_has_primary_accent_background():
    for name, colors in COLOR_PRESETS.items():
        assert set(colors.keys()) == {"primary", "accent", "background"}
        for hex_value in colors.values():
            assert hex_value.startswith("#")


def test_is_valid_color_scheme_true_for_known_name():
    assert is_valid_color_scheme("teal") is True


def test_is_valid_color_scheme_false_for_unknown_name():
    assert is_valid_color_scheme("neon-pink") is False


def test_resolve_color_scheme_returns_requested_when_valid():
    assert resolve_color_scheme("any-slug", "maroon") == "maroon"


def test_resolve_color_scheme_rejects_invalid_requested():
    with pytest.raises(ValueError):
        resolve_color_scheme("any-slug", "neon-pink")


def test_resolve_color_scheme_is_deterministic_for_same_slug():
    first = resolve_color_scheme("bedants-tuition", None)
    second = resolve_color_scheme("bedants-tuition", None)
    assert first == second
    assert first in PRESET_NAMES


def test_resolve_color_scheme_can_differ_across_slugs():
    results = {resolve_color_scheme(f"slug-{i}", None) for i in range(10)}
    assert len(results) > 1
