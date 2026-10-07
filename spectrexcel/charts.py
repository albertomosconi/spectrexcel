"""Chart descriptions and Dear PyGui rendering shared by both preview modes."""

from dataclasses import dataclass

import dearpygui.dearpygui as dpg

from spectrexcel.dpi import DisplayScale
from spectrexcel.i18n import _

RESET_ICON = "\N{ANTICLOCKWISE OPEN CIRCLE ARROW}"
BUTTON_SIDE = 32
FONT_SIZE = 16
LIMIT_EPSILON = 1e-5


@dataclass(frozen=True)
class ChartSeries:
    name: str
    x: list[float]
    y: list[float]


@dataclass(frozen=True)
class ChartSpec:
    x_label: str
    y_label: str
    x_limits: tuple[float, float]
    y_limits: tuple[float, float]
    series: tuple[ChartSeries, ...]
    title: str | None = None
    legend: bool = False


def green_shades(count: int) -> list[tuple[int, int, int, int]]:
    """Monochromatic green scale matching Excel chart style 5."""
    light = (197, 224, 180)
    dark = (56, 87, 35)
    if count <= 1:
        return [(112, 173, 71, 255)]
    return [
        (
            round(light[0] + (dark[0] - light[0]) * step),
            round(light[1] + (dark[1] - light[1]) * step),
            round(light[2] + (dark[2] - light[2]) * step),
            255,
        )
        for step in (index / (count - 1) for index in range(count))
    ]


def display_limits(limits: tuple[float, float]) -> tuple[float, float]:
    minimum, maximum = limits
    return limits if minimum < maximum else (minimum, minimum + 1.0)


def at_initial_limits(
    current: tuple[float, float], initial: tuple[float, float]
) -> bool:
    """Compare the live view against the initial limits within float32 noise.

    Dear PyGui stores axis limits as single-precision floats, so a freshly
    applied limit (e.g. 298.7) reads back rounded (298.70001220703125).
    """
    span = max(abs(initial[1] - initial[0]), 1e-12)
    return (abs(current[0] - initial[0]) <= span * LIMIT_EPSILON
            and abs(current[1] - initial[1]) <= span * LIMIT_EPSILON)


class ChartRenderer:
    """Own a plot and its themes, leaving the hosting container untouched."""

    def __init__(self, parent: str | int, scale: DisplayScale | None = None) -> None:
        self.parent = parent
        self.scale = scale
        self.plot: str | int | None = None
        self.axes: list[str | int] = []
        self.render_frame = -1
        self.themes: list[str | int] = []
        self.toolbar: str | int | None = None
        self.toolbar_buttons: list[str | int] = []
        self.hint_spacer: str | int | None = None
        self.hint_text: str | int | None = None
        self.align_frame = -1
        self.spec_limits: tuple[tuple[float, float], tuple[float, float]] = ((0, 1), (0, 1))
        self.interactive = False
        self.pending: dict[str | int, tuple[float, float]] | None = None
        self.pending_frame = -1

    def clear(self) -> None:
        self.axes = []
        self.render_frame = -1
        self.interactive = False
        self.pending = None
        self.pending_frame = -1
        self.toolbar_buttons = []
        self.hint_spacer = None
        self.hint_text = None
        self.align_frame = -1
        if self.toolbar is not None and dpg.does_item_exist(self.toolbar):
            dpg.delete_item(self.toolbar)
        self.toolbar = None
        if self.plot is not None and dpg.does_item_exist(self.plot):
            dpg.delete_item(self.plot)
        self.plot = None
        for theme in self.themes:
            if dpg.does_item_exist(theme):
                dpg.delete_item(theme)
        self.themes.clear()

    def dispose(self) -> None:
        self.clear()

    def render(self, spec: ChartSpec) -> None:
        self.clear()
        try:
            x_limits = display_limits(spec.x_limits)
            y_limits = display_limits(spec.y_limits)
            self.spec_limits = (x_limits, y_limits)
            self._build_toolbar()
            with dpg.plot(
                label=spec.title or "",
                no_title=spec.title is None,
                width=-1,
                height=-1,
                parent=self.parent,
            ) as plot:
                self.plot = plot
                with dpg.theme() as plot_theme:
                    self.themes.append(plot_theme)
                    with dpg.theme_component(dpg.mvPlot):
                        for color in (
                            dpg.mvPlotCol_FrameBg,
                            dpg.mvPlotCol_PlotBg,
                            dpg.mvPlotCol_LegendBg,
                            dpg.mvPlotCol_LegendBorder,
                        ):
                            dpg.add_theme_color(color, (0, 0, 0, 0), category=dpg.mvThemeCat_Plots)
                dpg.bind_item_theme(plot, plot_theme)
                if spec.legend:
                    dpg.add_plot_legend(
                        location=dpg.mvPlot_Location_South,
                        horizontal=True,
                        outside=True,
                    )
                x_axis = dpg.add_plot_axis(dpg.mvXAxis, label=spec.x_label)
                y_axis = dpg.add_plot_axis(dpg.mvYAxis, label=spec.y_label)
                shades = green_shades(len(spec.series))
                for index, series in enumerate(spec.series):
                    item = dpg.add_line_series(
                        series.x, series.y,
                        label=series.name if spec.legend else f"##series{index}",
                        parent=y_axis,
                    )
                    with dpg.theme() as theme:
                        self.themes.append(theme)
                        with dpg.theme_component(dpg.mvLineSeries):
                            dpg.add_theme_color(
                                dpg.mvPlotCol_Line, shades[index],
                                category=dpg.mvThemeCat_Plots,
                            )
                    dpg.bind_item_theme(item, theme)
                dpg.set_axis_limits(x_axis, *x_limits)
                dpg.set_axis_limits(y_axis, *y_limits)
                self.axes = [x_axis, y_axis]
                self.render_frame = dpg.get_frame_count()
        except Exception:
            self.clear()
            raise

    def _build_toolbar(self) -> None:
        px = self.scale.pixels if self.scale else (lambda size: size)
        side = px(BUTTON_SIDE)
        text_offset = (BUTTON_SIDE - FONT_SIZE) // 2
        with dpg.group(parent=self.parent, horizontal=True) as toolbar:
            self.toolbar = toolbar
            reset = dpg.add_button(
                label=RESET_ICON, width=side, height=side,
                enabled=False, callback=self.reset_view,
            )
            self.toolbar_buttons.append(reset)
            with dpg.tooltip(reset):
                dpg.add_text(_("Reset zoom to the original view"))
            # Vertical centering: the spacer pushes the hint text down to the
            # button row middle; align_hint_to_buttons fine-tunes the offset
            # from the rendered geometry once the first frame is drawn.
            with dpg.group():
                self.hint_spacer = dpg.add_spacer(width=0, height=px(text_offset))
                self.hint_text = dpg.add_text(_("Click and drag to pan. Scroll to zoom."))

    def align_hint_to_buttons(self) -> None:
        """Center the toolbar hint text on the zoom buttons once rendered."""
        if not self.interactive or self.hint_text is None or self.hint_spacer is None:
            return
        frame = dpg.get_frame_count()
        if frame == self.align_frame:
            # The spacer geometry only updates on the next rendered frame.
            return
        button = self.toolbar_buttons[0]
        if any(tag is not None and not dpg.does_item_exist(tag)
               for tag in (*self.toolbar_buttons, self.hint_spacer, self.hint_text)):
            return
        state = dpg.get_item_state(button)
        hint = dpg.get_item_state(self.hint_text)
        if not state["rect_size"][0] or not hint["rect_size"][0]:
            return
        delta = (state["pos"][1] + state["rect_size"][1] / 2
                 - hint["pos"][1] - hint["rect_size"][1] / 2)
        if abs(delta) < 1:
            self.align_frame = frame
            return
        height = dpg.get_item_configuration(self.hint_spacer)["height"]
        dpg.configure_item(self.hint_spacer, height=max(0, int(height + delta)))
        self.align_frame = frame

    def reset_view(self) -> None:
        """Queue a return to the axis limits of the last rendered spec."""
        if not self.interactive:
            return
        self._request(dict(zip(self.axes, self.spec_limits)))

    def _request(self, target: dict[str | int, tuple[float, float]]) -> None:
        self.pending = target
        self.pending_frame = -1

    def maintain(self) -> None:
        """Apply and release fixed axis limits frame by frame.

        Dear PyGui keeps pan and zoom locked while ``set_axis_limits`` is in
        effect, so the initial view is applied for one frame only; after that
        ``set_axis_limits_auto`` restores the built-in scale and drag
        interactions without changing the rendered range. Zoom and reset
        commands take the same path: limits reapply for one frame and unlock
        again on the next.
        """
        if not self.axes:
            return
        self.maintain_reset_availability()
        self._maintain_limits()
        self.align_hint_to_buttons()

    def maintain_reset_availability(self) -> None:
        """Enable the reset button only when the view drifted from the initial limits."""
        reset = self.toolbar_buttons[0] if self.toolbar_buttons else None
        if reset is None or not dpg.does_item_exist(reset):
            return
        if self.interactive and self.pending is not None and self.pending_frame >= 0:
            # Apply phase: limits fixed for this frame; check again later.
            return
        if not self.interactive:
            # Fixed limits still equal to the spec values: not drifted.
            drifted = False
        elif self.pending is not None:
            # Command queued but not yet applied; the view has moved.
            drifted = True
        else:
            current = []
            for axis in self.axes:
                if dpg.does_item_exist(axis):
                    current.append(tuple(dpg.get_axis_limits(axis)))
            drifted = len(current) == 2 and any(
                not at_initial_limits(current[index], self.spec_limits[index])
                for index in range(2)
            )
        if dpg.get_item_configuration(reset)["enabled"] != drifted:
            dpg.configure_item(reset, enabled=drifted)

    def _maintain_limits(self) -> None:
        frame = dpg.get_frame_count()
        if not self.interactive:
            if frame > self.render_frame:
                self.interactive = True
                self.render_frame = -1
                if self.plot is not None and dpg.does_item_exist(self.plot):
                    for axis in self.axes:
                        dpg.set_axis_limits_auto(axis)
            return
        if self.pending is None:
            return
        if self.pending_frame < 0:
            exists = self.plot is not None and dpg.does_item_exist(self.plot)
            for axis, limits in self.pending.items():
                if exists:
                    dpg.set_axis_limits(axis, *limits)
            self.pending_frame = frame
        elif frame > self.pending_frame:
            for axis in self.pending:
                if dpg.does_item_exist(axis):
                    dpg.set_axis_limits_auto(axis)
            self.pending = None
            self.pending_frame = -1
