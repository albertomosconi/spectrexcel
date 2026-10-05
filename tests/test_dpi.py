import pytest

from spectrexcel.dpi import (
    UI_SCALE_OPTIONS,
    DisplayScale,
    configure_display_scale,
    resolve_ui_scale,
    ui_scale_label,
)


def test_non_windows_uses_unscaled_pixels():
    scale = configure_display_scale(platform="linux")

    assert scale == DisplayScale(1.0)
    assert scale.pixels(16) == 16


def test_display_scale_converts_logical_and_physical_pixels():
    scale = DisplayScale(1.25)

    assert scale.pixels(16) == 20
    assert scale.pixels(105) == 131
    assert scale.pixels(-174) == -218
    assert scale.pixels(-1) == -1
    assert scale.position((100, -40)) == (125, -50)


def test_display_scale_round_trips_window_geometry():
    scale = DisplayScale(1.5)

    physical = [scale.pixels(value) for value in (800, 560, 100, 100)]

    assert [scale.logical_pixels(value) for value in physical] == [800, 560, 100, 100]


def test_display_scale_applies_user_multiplier():
    scale = DisplayScale(1.5).scaled(0.9)

    assert scale == DisplayScale(1.35)
    assert scale.pixels(16) == 22
    assert scale.logical_pixels(22) == 16


@pytest.mark.parametrize("value,expected", [
    (1.25, 1.25), (0.5, 0.5), (1, 1.0),
    (2.0, 1.0), (0.6, 1.0), ("1.25", 1.0), (True, 1.0), (None, 1.0), ([1.25], 1.0),
])
def test_resolve_ui_scale_accepts_only_known_options(value, expected):
    assert resolve_ui_scale(value) == expected


def test_ui_scale_labels_are_round_percentages():
    assert [ui_scale_label(option) for option in UI_SCALE_OPTIONS] == [
        "50%", "75%", "90%", "100%", "110%", "125%", "150%",
    ]
