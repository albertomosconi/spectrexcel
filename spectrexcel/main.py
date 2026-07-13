import importlib.metadata
import queue
import sys
import webbrowser
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import dearpygui.dearpygui as dpg
import requests
from packaging.version import InvalidVersion, Version

from spectrexcel.assays import BindingTitolazione, Cinetiche, FamigliaDiSpettri
from spectrexcel.assays.shared import AssayView
from spectrexcel.settings import Settings


@dataclass(frozen=True)
class Assay:
    name: str
    view: type[AssayView]


ASSAYS = (
    Assay("binding / titolazione", BindingTitolazione),
    Assay("cinetiche", Cinetiche),
    Assay("famiglia di spettri", FamigliaDiSpettri),
)


class SpectrExcelApp:
    def __init__(self, version: str) -> None:
        self.version = version
        self.settings = Settings()
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="spectrexcel")
        self.results: queue.SimpleQueue[
            tuple[Callable[[Any], None], Any, Exception | None]
        ] = queue.SimpleQueue()
        self.latest_release_version: str | None = None
        self.assay_view: AssayView | None = None
        self.log_scroll_pending = 0

    def build(self) -> None:
        font_path = Path(__file__).parent / "fonts" / "InterVariable.ttf"
        log_font_path = Path(__file__).parent / "fonts" / "JetBrainsMono-Regular.ttf"
        with dpg.font_registry():
            default_font = dpg.add_font(str(font_path), 16, tag="main.font")
            dpg.add_font(str(log_font_path), 16, tag="main.log_font")
        dpg.bind_font(default_font)

        with dpg.theme() as theme:
            with dpg.theme_component(dpg.mvAll):
                dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 18, 16)
                dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 10, 6)
                dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 8, 7)
                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 4)
                dpg.add_theme_color(dpg.mvThemeCol_WindowBg, (24, 27, 32))
                dpg.add_theme_color(dpg.mvThemeCol_ChildBg, (30, 34, 40))
                dpg.add_theme_color(dpg.mvThemeCol_Button, (36, 91, 130))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (46, 116, 163))
                dpg.add_theme_color(dpg.mvThemeCol_FrameBg, (42, 47, 55))
        dpg.bind_theme(theme)

        with dpg.theme() as header_theme:
            with dpg.theme_component(dpg.mvTable):
                dpg.add_theme_style(dpg.mvStyleVar_CellPadding, 0, 4)

        with dpg.theme() as log_theme:
            with dpg.theme_component(dpg.mvAll):
                dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 8, 0)
                dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 8, 4)

        with dpg.theme() as assay_theme:
            with dpg.theme_component(dpg.mvChildWindow):
                dpg.add_theme_color(dpg.mvThemeCol_ChildBg, (24, 27, 32))

        with dpg.window(
            tag="main.window",
            no_title_bar=True,
            no_move=True,
            no_resize=True,
            no_collapse=True,
        ):
            with dpg.table(
                tag="main.header",
                header_row=False,
                policy=dpg.mvTable_SizingStretchProp,
                no_pad_outerX=True,
            ):
                dpg.add_table_column(width_stretch=True, init_width_or_weight=1)
                dpg.add_table_column(width_fixed=True)
                dpg.add_table_column(width_fixed=True)
                with dpg.table_row():
                    with dpg.group(horizontal=True):
                        dpg.add_text("ASSAY")
                        selected_index = self.settings.get("main/selected_assay", 0)
                        if not 0 <= selected_index < len(ASSAYS):
                            selected_index = 0
                        dpg.add_combo(
                            items=[assay.name for assay in ASSAYS],
                            default_value=ASSAYS[selected_index].name,
                            tag="main.assay",
                            callback=self._assay_changed,
                            width=250,
                        )
                    dpg.add_text(f"v{self.version}", color=(150, 150, 150))
                    with dpg.group(horizontal=True, horizontal_spacing=0):
                        dpg.add_spacer(width=4)
                        dpg.add_button(
                            label="Check updates",
                            tag="main.update",
                            callback=self._check_and_download_update,
                        )
            dpg.bind_item_theme("main.header", header_theme)

            dpg.add_separator()
            with dpg.child_window(tag="assay.content", height=-174, border=False):
                pass
            dpg.bind_item_theme("assay.content", assay_theme)

            dpg.add_text("ACTIVITY", color=(104, 190, 255))
            dpg.add_child_window(
                tag="main.log",
                height=105,
                width=-1,
                horizontal_scrollbar=True,
            )
            dpg.bind_item_theme("main.log", log_theme)
            dpg.add_text("", tag="main.log.text", parent="main.log")
            dpg.bind_item_font("main.log.text", "main.log_font")
            with dpg.group(horizontal=True):
                dpg.add_text("Developed by Alberto Mosconi", color=(135, 135, 135))
                dpg.add_button(label="Source code", small=True, callback=self._open_source)
                dpg.add_text("GPLv3 or later", color=(135, 135, 135))

        dpg.set_primary_window("main.window", True)
        self._load_assay(selected_index)
        self.submit(self._find_update, self._update_check_finished, self._update_check_failed)

    def submit(
        self,
        task: Callable[[], Any],
        on_success: Callable[[Any], None],
        on_error: Callable[[Exception], None],
    ) -> None:
        future = self.executor.submit(task)

        def completed(done: Future[Any]) -> None:
            try:
                self.results.put((on_success, done.result(), None))
            except Exception as error:
                self.results.put((on_error, None, error))

        future.add_done_callback(completed)

    def process_results(self) -> None:
        while True:
            try:
                callback, value, error = self.results.get_nowait()
            except queue.Empty:
                return
            if error is None:
                try:
                    callback(value)
                except Exception as callback_error:
                    self.log(f"ERROR: {callback_error}")
            else:
                try:
                    callback(error)
                except Exception as callback_error:
                    self.log(f"ERROR: {callback_error}")

    def log(self, text: str | list[str]) -> None:
        messages = [text] if isinstance(text, str) else text
        at_bottom = (
            dpg.get_y_scroll_max("main.log") - dpg.get_y_scroll("main.log") <= 2
            or self.log_scroll_pending > 0
        )
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        new_lines = "\n".join(f"[ {timestamp} ] {message}" for message in messages)
        current = dpg.get_value("main.log.text")
        dpg.set_value("main.log.text", f"{current}\n{new_lines}" if current else new_lines)
        if at_bottom:
            # The new scroll maximum is available after the next rendered frame.
            self.log_scroll_pending = 2

    def maintain_log_scroll(self) -> None:
        if self.log_scroll_pending == 0:
            return
        dpg.set_y_scroll("main.log", dpg.get_y_scroll_max("main.log"))
        self.log_scroll_pending -= 1

    def _assay_changed(self, _sender: Any, assay_name: str) -> None:
        index = next(
            index for index, assay in enumerate(ASSAYS) if assay.name == assay_name
        )
        self._load_assay(index)

    def _load_assay(self, index: int) -> None:
        if self.assay_view is not None:
            self.assay_view.dispose()
        dpg.delete_item("assay.content", children_only=True)
        assay = ASSAYS[index]
        self.assay_view = assay.view(self.log, self.submit, self.settings)
        self.assay_view.build("assay.content")
        self.settings.set("main/selected_assay", index)
        self.log(f"LOADED ASSAY: {assay.name}")

    def _find_update(self) -> str | None:
        response = requests.get(
            "https://gitlab.com/api/v4/projects/65488480/repository/tags",
            params={"order_by": "updated", "sort": "desc", "per_page": 100},
            timeout=10,
        )
        response.raise_for_status()
        current = Version(self.version)
        available: list[tuple[Version, str]] = []
        for release in response.json():
            name = release.get("name", "")
            try:
                available.append((Version(name.removeprefix("v")), name))
            except InvalidVersion:
                continue
        if not available:
            return None
        latest, name = max(available)
        return name if latest > current else None

    def _update_check_finished(self, version: str | None) -> None:
        self.latest_release_version = version
        if version is not None:
            dpg.configure_item("main.update", label=f"Update {version}")

    def _update_check_failed(self, _error: Exception) -> None:
        # Startup update checks are intentionally silent.
        pass

    def _check_and_download_update(self) -> None:
        dpg.configure_item("main.update", enabled=False, label="Checking...")
        self.log("checking for updates...")
        self.submit(self._find_update, self._manual_update_finished, self._manual_update_failed)

    def _manual_update_finished(self, version: str | None) -> None:
        dpg.configure_item("main.update", enabled=True)
        self.latest_release_version = version
        if version is None:
            dpg.configure_item("main.update", label="Check updates")
            self.log("no updates found")
            return
        dpg.configure_item("main.update", label=f"Update {version}")
        self.log(f"NEW APP VERSION FOUND: {version}")
        self._show_update_confirmation(version)

    def _manual_update_failed(self, error: Exception) -> None:
        dpg.configure_item("main.update", enabled=True, label="Check updates")
        self.log(f"ERROR: unable to check for updates: {error}")

    def _show_update_confirmation(self, version: str) -> None:
        if dpg.does_item_exist("update.modal"):
            dpg.delete_item("update.modal")
        with dpg.window(
            label="Update available",
            tag="update.modal",
            modal=True,
            no_close=True,
            width=470,
            height=180,
            pos=(165, 155),
        ):
            dpg.add_text(
                f"Version {version} is available. Open the download page and close SpectrExcel?",
                wrap=430,
            )
            dpg.add_spacer(height=12)
            with dpg.group(horizontal=True):
                dpg.add_button(
                    label="Download and close",
                    callback=lambda: self._download_update(version),
                    width=180,
                )
                dpg.add_button(
                    label="Not now",
                    callback=lambda: dpg.delete_item("update.modal"),
                    width=100,
                )

    def _download_update(self, version: str) -> None:
        download_url = (
            "https://gitlab.com/albertomosconi/spectrexcel/-/raw/"
            f"{version}/dist/spectrexcel.exe"
        )
        webbrowser.open(download_url)
        dpg.stop_dearpygui()

    @staticmethod
    def _open_source() -> None:
        webbrowser.open("https://gitlab.com/albertomosconi/spectrexcel")

    def save_viewport(self) -> None:
        width = dpg.get_viewport_width()
        height = dpg.get_viewport_height()
        position = dpg.get_viewport_pos()
        self.settings.set("window/width", width)
        self.settings.set("window/height", height)
        self.settings.set("window/position", list(position))

    def shutdown(self) -> None:
        self.executor.shutdown(wait=True, cancel_futures=True)


def application_version() -> str:
    try:
        return importlib.metadata.version("spectrexcel")
    except importlib.metadata.PackageNotFoundError:
        return "0.0.0"


def main() -> None:
    dpg.create_context()
    dpg.configure_app(manual_callback_management=True)
    app = SpectrExcelApp(application_version())
    width = app.settings.get("window/width", 800)
    height = app.settings.get("window/height", 560)
    position = app.settings.get("window/position", [100, 100])
    if width < 1:
        width = 800
    if height < 1:
        height = 560
    if (
        len(position) != 2
        or not all(isinstance(coordinate, int) for coordinate in position)
    ):
        position = [100, 100]
    icon_path = Path(__file__).with_name("icon.ico")

    try:
        dpg.create_viewport(
            title="SpectrExcel",
            width=max(width, 720),
            height=max(height, 520),
            x_pos=position[0],
            y_pos=position[1],
            min_width=720,
            min_height=520,
        )
        if icon_path.exists():
            dpg.set_viewport_large_icon(str(icon_path))
            dpg.set_viewport_small_icon(str(icon_path))
        app.build()
        dpg.setup_dearpygui()
        dpg.show_viewport()
        while dpg.is_dearpygui_running():
            dpg.run_callbacks(dpg.get_callback_queue())
            app.process_results()
            dpg.render_dearpygui_frame()
            app.maintain_log_scroll()
        app.save_viewport()
    finally:
        app.shutdown()
        dpg.destroy_context()


if __name__ == "__main__":
    main()
