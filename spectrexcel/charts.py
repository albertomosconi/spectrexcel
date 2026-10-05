"""Chart descriptions and Dear PyGui rendering shared by both preview modes."""

from dataclasses import dataclass

import dearpygui.dearpygui as dpg


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
            *(
                round(light[channel] + (dark[channel] - light[channel]) * step)
                for channel in range(3)
            ),
            255,
        )
        for step in (index / (count - 1) for index in range(count))
    ]


def display_limits(limits: tuple[float, float]) -> tuple[float, float]:
    minimum, maximum = limits
    return limits if minimum < maximum else (minimum, minimum + 1.0)


class ChartRenderer:
    """Own a plot and its themes, leaving the hosting container untouched."""

    def __init__(self, parent: str | int) -> None:
        self.parent = parent
        self.plot: int | None = None
        self.themes: list[int] = []

    def clear(self) -> None:
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
                dpg.set_axis_limits(x_axis, *display_limits(spec.x_limits))
                dpg.set_axis_limits(y_axis, *display_limits(spec.y_limits))
        except Exception:
            self.clear()
            raise
