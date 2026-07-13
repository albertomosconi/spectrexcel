from spectrexcel.dpi import DisplayScale, configure_display_scale


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
