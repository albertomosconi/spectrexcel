import pytest

from spectrexcel.dpi import (
    UI_SCALE_OPTIONS,
    DisplayScale,
    configure_display_scale,
    fit_to_work_area,
    nearest_work_area,
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


WORK_AREA = (0, 0, 1920, 1040)


@pytest.mark.parametrize(
    "position",
    [
        (100, 100),
        # Straddling a monitor edge is fine while the title bar can be grabbed.
        (1700, 600),
        (-600, 10),
    ],
)
def test_reachable_window_keeps_its_position(position):
    assert fit_to_work_area(position, (800, 560), WORK_AREA, (120, 32)) == position


@pytest.mark.parametrize(
    ("position", "expected"),
    [
        # Saved on a secondary monitor that is no longer connected.
        ((2500, 300), (1120, 300)),
        ((-2500, 300), (0, 300)),
        # Title bar below the bottom edge or above the top edge.
        ((100, 1030), (100, 480)),
        ((100, -40), (100, 0)),
    ],
)
def test_unreachable_window_moves_inside_work_area(position, expected):
    assert fit_to_work_area(position, (800, 560), WORK_AREA, (120, 32)) == expected


def test_window_larger_than_work_area_aligns_top_left():
    assert fit_to_work_area((5000, 5000), (2400, 1400), WORK_AREA, (120, 32)) == (0, 0)


def test_non_windows_has_no_work_area():
    assert nearest_work_area((0, 0, 10, 10), platform="linux") is None
