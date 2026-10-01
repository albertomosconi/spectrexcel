from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

import pandas as pd
import dearpygui.dearpygui as dpg
import pytest

from spectrexcel.assays.cinetiche import Cinetiche, export_kinetics
from spectrexcel.dpi import DisplayScale


@pytest.mark.parametrize(
    ("paths", "expected_names", "reorder_enabled"),
    [
        ([Path("sample-1.KD")], ["sample-1"], False),
        (
            [Path("sample-10.KD"), Path("sample-2.KD")],
            ["sample-2", "sample-10"],
            True,
        ),
    ],
)
def test_load_inputs_sets_reorder_state_for_dataset_count(
    monkeypatch, paths, expected_names, reorder_enabled
):
    submitted = {}
    configured = []
    values = []
    parsed = []

    class Settings:
        def set(self, _key, _value):
            pass

    def submit(task, on_success, on_error):
        submitted.update(task=task, on_success=on_success, on_error=on_error)

    def parse(path):
        parsed.append(path)
        return pd.DataFrame({0: [0.1]}, index=[300])

    monkeypatch.setattr("spectrexcel.assays.cinetiche.parse_kd_file", parse)
    monkeypatch.setattr(
        dpg,
        "configure_item",
        lambda tag, **config: configured.append((tag, config)),
    )
    monkeypatch.setattr(
        dpg, "set_value", lambda tag, value: values.append((tag, value))
    )
    assay = Cinetiche(lambda _message: None, submit, Settings(), DisplayScale())

    assay._load_inputs(paths)
    datasets = submitted["task"]()
    submitted["on_success"](datasets)

    assert parsed == paths
    assert [name for name, _dataframe in assay.datasets] == expected_names
    reorder_configurations = [
        config for tag, config in configured if tag == "kinetics.reorder"
    ]
    assert reorder_configurations[-1] == {"enabled": reorder_enabled}


def test_reorder_popup_builds():
    dpg.create_context()
    dpg.create_viewport()
    try:
        assay = Cinetiche(
            lambda _message: None,
            lambda *_args: None,
            None,
            DisplayScale(),
        )
        assay.datasets = [
            ("sample-1", pd.DataFrame()),
            ("sample-2", pd.DataFrame()),
        ]

        assay._show_reorder()

        assert dpg.does_item_exist("kinetics.reorder.modal")
        modal_config = dpg.get_item_configuration("kinetics.reorder.modal")
        assert modal_config["no_move"]
        assert modal_config["no_resize"]
        assay._move_dataset(None, None, (0, 1))
        assert dpg.does_item_exist("kinetics.reorder.modal")
        assert dpg.get_value("kinetics.reorder.filename.0") == "sample-2"
    finally:
        dpg.destroy_context()


def test_export_kinetics_preserves_dataset_and_chart_order(tmp_path):
    spectra = pd.DataFrame({0: [0.2, 0.1], 10: [0.3, 0.1]}, index=[300, 800])
    other = pd.DataFrame({0: [0.9, 0.2], 10: [0.8, 0.3]}, index=[300, 800])
    originals = [frame.copy(deep=True) for frame in (spectra, other)]
    output_path = tmp_path / "kinetics.xlsx"

    export_kinetics(
        [("sample-10", spectra), ("sample-2", other)],
        output_path,
        reading_wavelength=300,
        correction_wavelength=800,
    )

    spreadsheet_ns = {
        "s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    }
    chart_ns = {
        "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
        "c": "http://schemas.openxmlformats.org/drawingml/2006/chart",
    }
    with ZipFile(output_path) as workbook:
        shared_strings = ElementTree.fromstring(workbook.read("xl/sharedStrings.xml"))
        strings = ["".join(item.itertext()) for item in shared_strings]
        sheet = ElementTree.fromstring(workbook.read("xl/worksheets/sheet1.xml"))
        chart = ElementTree.fromstring(workbook.read("xl/charts/chart1.xml"))

    def cell_string(reference: str) -> str:
        cell = sheet.find(f".//s:c[@r='{reference}']", spreadsheet_ns)
        assert cell is not None
        value = cell.find("s:v", spreadsheet_ns)
        assert value is not None and value.text is not None
        return strings[int(value.text)]

    assert [cell_string("B2"), cell_string("C2")] == ["sample-10", "sample-2"]
    numbers = [float(sheet.findtext(f".//s:c[@r='{ref}']/s:v", namespaces=spreadsheet_ns))
               for ref in ("B3", "B4", "C3", "C4")]
    assert numbers == pytest.approx([0.1, 0.2, 0.7, 0.5])
    for actual, original in zip((spectra, other), originals):
        pd.testing.assert_frame_equal(actual, original)

    series = chart.findall(".//c:ser", chart_ns)
    assert [
        item.findtext("c:tx/c:strRef/c:f", namespaces=chart_ns) for item in series
    ] == ["data!$B$2", "data!$C$2"]
    assert [item.findtext("c:xVal/c:numRef/c:f", namespaces=chart_ns) for item in series] == [
        "data!$A$3:$A$4", "data!$A$3:$A$4",
    ]
    assert [item.findtext("c:yVal/c:numRef/c:f", namespaces=chart_ns) for item in series] == [
        "data!$B$3:$B$4", "data!$C$3:$C$4",
    ]
    assert all(
        item.find("c:spPr/a:ln/a:solidFill", chart_ns) is None for item in series
    )


def test_export_kinetics_zeroes_time_axis(tmp_path):
    spectra = pd.DataFrame({8.4: [0.2, 0.1], 15.7: [0.3, 0.1]}, index=[300, 800])
    output_path = tmp_path / "kinetics.xlsx"

    export_kinetics(
        [("sample-1", spectra)],
        output_path,
        reading_wavelength=300,
        correction_wavelength=800,
    )

    spreadsheet_ns = {
        "s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    }
    chart_ns = {
        "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
        "c": "http://schemas.openxmlformats.org/drawingml/2006/chart",
    }
    with ZipFile(output_path) as workbook:
        sheet = ElementTree.fromstring(workbook.read("xl/worksheets/sheet1.xml"))
        chart = ElementTree.fromstring(workbook.read("xl/charts/chart1.xml"))

    def cell_number(reference: str) -> float:
        cell = sheet.find(f".//s:c[@r='{reference}']", spreadsheet_ns)
        assert cell is not None
        value = cell.find("s:v", spreadsheet_ns)
        assert value is not None and value.text is not None
        return float(value.text)

    assert cell_number("A3") == 0.0
    assert cell_number("A4") == 15.7 - 8.4

    def axis_position(axis) -> str:
        position = axis.find("c:axPos", chart_ns)
        assert position is not None
        return position.get("val")

    x_axis = next(
        axis
        for axis in chart.findall(".//c:valAx", chart_ns)
        if axis_position(axis) == "b"
    )
    scaling = x_axis.find("c:scaling", chart_ns)
    assert scaling is not None
    minimum = scaling.find("c:min", chart_ns)
    maximum = scaling.find("c:max", chart_ns)
    assert minimum is not None and maximum is not None
    assert float(minimum.get("val")) == 0.0
    assert float(maximum.get("val")) == 15.7 - 8.4


@pytest.mark.parametrize("different_grids", [False, True])
def test_export_kinetics_preserves_missing_absorbance_as_blank_cell(tmp_path, different_grids):
    spectra = pd.DataFrame(
        {0: [0.2, 0.1], 10: [float("nan"), 0.1], 20: [0.4, 0.1]},
        index=[300, 800],
    )
    original = spectra.copy(deep=True)
    output = tmp_path / "existing.xlsx"
    output.write_bytes(b"previous workbook")

    datasets = [("sample", spectra)]
    if different_grids:
        datasets.append(("other", pd.DataFrame({0: [0.7, 0.1], 15: [0.9, 0.2]}, index=[300, 800])))
    export_kinetics(datasets, output, 300, 800)

    ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with ZipFile(output) as workbook:
        sheet = ElementTree.fromstring(workbook.read("xl/worksheets/sheet1.xml"))
    assert float(sheet.findtext(".//s:c[@r='B3']/s:v", namespaces=ns)) == pytest.approx(0.1)
    assert sheet.find(".//s:c[@r='B4']/s:v", ns) is None
    assert float(sheet.findtext(".//s:c[@r='B5']/s:v", namespaces=ns)) == pytest.approx(0.3)
    if different_grids:
        assert float(sheet.findtext(".//s:c[@r='C4']/s:v", namespaces=ns)) == 15.0
        assert float(sheet.findtext(".//s:c[@r='D4']/s:v", namespaces=ns)) == pytest.approx(0.7)
    pd.testing.assert_frame_equal(spectra, original)


@pytest.mark.parametrize("second_times,expected_times", [
    ([20.0, 35.0], [0.0, 15.0]),
    ([20.0, 30.0, 40.0], [0.0, 10.0, 20.0]),
    ([20.0], [0.0]),
    ([20.0, 30.0000000001], [0.0, 10.0000000001]),
])
def test_export_kinetics_preserves_each_files_time_grid(
    tmp_path, second_times, expected_times
):
    first = pd.DataFrame({5.0: [1.0, 0.25], 15.0: [0.5, 0.25]}, index=[300, 800])
    second = pd.DataFrame({time: [0.7, 0.1] for time in second_times}, index=[300, 800])
    originals = [frame.copy(deep=True) for frame in (first, second)]
    output = tmp_path / "independent.xlsx"

    export_kinetics([("first", first), ("second", second)], output, 300, 800)

    ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    chart_ns = {"c": "http://schemas.openxmlformats.org/drawingml/2006/chart"}
    with ZipFile(output) as workbook:
        sheet = ElementTree.fromstring(workbook.read("xl/worksheets/sheet1.xml"))
        chart = ElementTree.fromstring(workbook.read("xl/charts/chart1.xml"))
        shared_strings = ElementTree.fromstring(workbook.read("xl/sharedStrings.xml"))
        drawing = ElementTree.fromstring(workbook.read("xl/drawings/drawing1.xml"))
    strings = ["".join(item.itertext()) for item in shared_strings]

    def numbers(column, count):
        return [
            float(sheet.findtext(f".//s:c[@r='{column}{row}']/s:v", namespaces=ns))
            for row in range(3, count + 3)
        ]

    assert numbers("A", 2) == [0.0, 10.0]
    assert numbers("B", 2) == pytest.approx([0.75, 0.25])
    assert numbers("C", len(expected_times)) == pytest.approx(expected_times, rel=0, abs=1e-12)
    assert numbers("D", len(expected_times)) == pytest.approx([0.6] * len(expected_times))
    assert sheet.find(f".//s:c[@r='C{len(expected_times) + 3}']", ns) is None
    for ref, expected in [("A2", "Time (s)"), ("B2", "first"),
                          ("C2", "Time (s)"), ("D2", "second")]:
        index = int(sheet.findtext(f".//s:c[@r='{ref}']/s:v", namespaces=ns))
        assert strings[index] == expected
    series = chart.findall(".//c:ser", chart_ns)
    end = len(expected_times) + 2
    time_reference = "data!$C$3" if len(expected_times) == 1 else f"data!$C$3:$C${end}"
    value_reference = "data!$D$3" if len(expected_times) == 1 else f"data!$D$3:$D${end}"
    assert [item.findtext("c:xVal/c:numRef/c:f", namespaces=chart_ns) for item in series] == [
        "data!$A$3:$A$4", time_reference,
    ]
    assert [item.findtext("c:yVal/c:numRef/c:f", namespaces=chart_ns) for item in series] == [
        "data!$B$3:$B$4", value_reference,
    ]
    assert [item.findtext("c:tx/c:strRef/c:f", namespaces=chart_ns) for item in series] == [
        "data!$B$2", "data!$D$2",
    ]
    x_axis = next(axis for axis in chart.findall(".//c:valAx", chart_ns)
                  if axis.find("c:axPos", chart_ns).get("val") == "b")
    assert float(x_axis.find("c:scaling/c:max", chart_ns).get("val")) == pytest.approx(
        max(10.0, expected_times[-1]), rel=0, abs=1e-12
    )
    drawing_ns = {"d": "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"}
    assert int(drawing.findtext(".//d:from/d:col", namespaces=drawing_ns)) >= 4
    for actual, original in zip((first, second), originals):
        pd.testing.assert_frame_equal(actual, original)


@pytest.mark.parametrize("reverse", [False, True])
def test_kinetics_preview_preserves_independent_time_grids_and_longest_duration(monkeypatch, reverse):
    first = pd.DataFrame({1.5: [1.0, 0.25], 2.2: [0.5, 0.25]}, index=[300, 800])
    second = pd.DataFrame({1.5: [0.7, 0.1], 2.1: [0.9, 0.2], 3.0: [1.0, 0.3]}, index=[300, 800])
    values = {"kinetics.reading": 300, "kinetics.correction": 800}
    monkeypatch.setattr(dpg, "get_value", values.__getitem__)
    messages, previews = [], []
    view = Cinetiche(messages.append, lambda *args: None, None, DisplayScale())
    view.datasets = [("first", first), ("second", second)]
    if reverse:
        view.datasets.reverse()
    originals = [frame.copy(deep=True) for name, frame in view.datasets]
    monkeypatch.setattr(view, "show_chart_preview", previews.append)

    view._show_preview()

    assert messages == []
    assert len(previews) == 1
    spec = previews[0]
    assert [series.name for series in spec.series] == (
        ["second", "first"] if reverse else ["first", "second"]
    )
    by_name = {series.name: series for series in spec.series}
    assert by_name["first"].x == pytest.approx([0.0, 0.7])
    assert by_name["second"].x == pytest.approx([0.0, 0.6, 1.5])
    assert by_name["first"].y == pytest.approx([0.75, 0.25])
    assert by_name["second"].y == pytest.approx([0.6, 0.7, 0.7])
    assert spec.x_limits == (0.0, 1.5)
    for (name, actual), original in zip(view.datasets, originals):
        pd.testing.assert_frame_equal(actual, original)


@pytest.mark.parametrize("first_times,second_times,expected_end,value_columns", [
    ([5.0, 15.0], [20.0, 30.0], 10.0, ("B", "C")),
    ([8.4, 15.7], [20.0, 27.3], 7.3, ("B", "D")),
])
def test_kinetics_preview_zeroes_matching_relative_grids_and_preserves_trace_order(
    monkeypatch, tmp_path, first_times, second_times, expected_end, value_columns
):
    first = pd.DataFrame([[1.0, 0.5], [0.25, 0.25]], index=[300, 800], columns=first_times)
    second = pd.DataFrame([[0.7, 0.9], [0.1, 0.2]], index=[300, 800], columns=second_times)
    originals = [frame.copy(deep=True) for frame in (first, second)]
    values = {"kinetics.reading": 300, "kinetics.correction": 800}
    monkeypatch.setattr(dpg, "get_value", values.__getitem__)
    view = Cinetiche(lambda message: None, lambda *args: None, None, DisplayScale())
    view.datasets = [("first", first), ("second", second)]
    previews = []
    monkeypatch.setattr(view, "show_chart_preview", previews.append)

    view._show_preview()
    output = tmp_path / "matching.xlsx"
    export_kinetics(view.datasets, output, 300, 800)

    spec = previews[0]
    assert [series.name for series in spec.series] == ["first", "second"]
    for series in spec.series:
        assert series.x == pytest.approx([0.0, expected_end])
    assert spec.series[0].y == pytest.approx([0.75, 0.25])
    assert spec.series[1].y == pytest.approx([0.6, 0.7])
    assert spec.x_limits == pytest.approx((0.0, expected_end))
    assert spec.y_limits == (0.0, 0.75)
    ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with ZipFile(output) as workbook:
        sheet = ElementTree.fromstring(workbook.read("xl/worksheets/sheet1.xml"))
    for column, series in zip(value_columns, spec.series):
        actual = [float(sheet.findtext(f".//s:c[@r='{column}{row}']/s:v", namespaces=ns)) for row in (3, 4)]
        assert actual == pytest.approx(series.y)
    for actual, original in zip((first, second), originals):
        pd.testing.assert_frame_equal(actual, original)


@pytest.mark.parametrize("missing", [300, 800])
def test_export_kinetics_rejects_missing_wavelength_before_creating_file(tmp_path, missing):
    frame = pd.DataFrame({0: [0.2, 0.1], 10: [0.3, 0.1]}, index=[300, 800]).drop(missing)
    output = tmp_path / "invalid.xlsx"

    with pytest.raises(ValueError, match=str(missing)):
        export_kinetics([("sample", frame)], output, 300, 800)

    assert not output.exists()


@pytest.mark.parametrize("invalid", ["reading", "correction", "empty-times"])
def test_kinetics_preview_logs_invalid_data_without_showing_chart(monkeypatch, invalid):
    frame = pd.DataFrame({0: [0.2, 0.1], 10: [0.3, 0.1]}, index=[300, 800])
    datasets = [("first", frame)]
    if invalid == "empty-times":
        datasets = [("first", frame.iloc[:, :0])]
    else:
        datasets = [("first", frame.drop(300 if invalid == "reading" else 800))]
    values = {"kinetics.reading": 300, "kinetics.correction": 800}
    monkeypatch.setattr(dpg, "get_value", values.__getitem__)
    messages, previews = [], []
    view = Cinetiche(messages.append, lambda *args: None, None, DisplayScale())
    view.datasets = datasets
    monkeypatch.setattr(view, "show_chart_preview", previews.append)

    view._show_preview()

    assert not previews
    assert len(messages) == 1


@pytest.mark.parametrize("datasets", [[], [("empty", pd.DataFrame(index=[300, 800]))]])
def test_export_kinetics_rejects_empty_data_without_creating_file(tmp_path, datasets):
    output = tmp_path / "empty.xlsx"

    with pytest.raises(ValueError):
        export_kinetics(datasets, output, 300, 800)

    assert not output.exists()


@pytest.mark.parametrize("reading,expected", [([-0.1, 0.1], (-0.2, 0.0)), ([0.1, 0.1], (0.0, 1.0))])
def test_kinetics_preview_and_export_axes_show_negative_and_flat_traces(monkeypatch, tmp_path, reading, expected):
    frame = pd.DataFrame([reading, [0.1, 0.1]], index=[300, 800], columns=[0, 10])
    values = {"kinetics.reading": 300, "kinetics.correction": 800}
    monkeypatch.setattr(dpg, "get_value", values.__getitem__)
    view = Cinetiche(lambda message: None, lambda *args: None, None, DisplayScale())
    view.datasets = [("sample", frame)]
    previews = []
    monkeypatch.setattr(view, "show_chart_preview", previews.append)

    view._show_preview()
    output = tmp_path / "limits.xlsx"
    export_kinetics(view.datasets, output, 300, 800)

    assert previews[0].y_limits == expected
    ns = {"c": "http://schemas.openxmlformats.org/drawingml/2006/chart"}
    with ZipFile(output) as workbook:
        chart = ElementTree.fromstring(workbook.read("xl/charts/chart1.xml"))
    y_axis = next(axis for axis in chart.findall(".//c:valAx", ns) if axis.find("c:axPos", ns).get("val") == "l")
    bounds = tuple(float(y_axis.find(f"c:scaling/c:{name}", ns).get("val")) for name in ("min", "max"))
    assert bounds == expected
