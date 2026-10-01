import struct

import pandas as pd
import pytest

from spectrexcel.assays.parsing import (
    WAVELENGTH_COUNT,
    WAVELENGTH_MAX,
    WAVELENGTH_MIN,
    ParseError,
    parse_kd_file,
    parse_sd_file,
    parse_txt_file,
)

SPECTRUM_SIZE = WAVELENGTH_COUNT * 8

# Header signatures, duplicated from the binary format specification so the
# fixtures break loudly if the parsers ever drift from the format.
SD_NAME_NEW = b"\x53\x00\x61\x00\x6d\x00\x70\x00\x6c\x00\x65\x00\x4e\x00\x61\x00\x6d\x00\x65\x00"
SD_NAME_OLD = b"\x28\x60\x44\x61\x74\x61\x54\x79\x70\x65"
AU_NEW = b"\x28\x00\x41\x00\x55\x00\x29\x00"
AU_OLD_SD = b"\x28\x41\x55\x29\x00"
AU_OLD_KD = b"\x28\x41\x55\x29"
KD_TIME_NEW = b"\x52\x00\x65\x00\x6c\x00\x54\x00\x69\x00\x6d\x00\x65\x00"
KD_TIME_OLD = b"\x52\x65\x6c\x54\x69\x6d\x65"


def spectrum_bytes() -> bytes:
    values = [i / 1000.0 for i in range(WAVELENGTH_COUNT)]
    return struct.pack(f"<{WAVELENGTH_COUNT}d", *values)


def write(tmp_path, name: str, contents: bytes):
    path = tmp_path / name
    path.write_bytes(contents)
    return path


def test_parse_sd_file_new_headers(tmp_path):
    contents = (
        SD_NAME_NEW + b"\x00" * 8 + b"sample-1" + b"\x09"
        + AU_NEW + b"\x00" * 9 + spectrum_bytes()
    )
    path = write(tmp_path, "data.SD", contents)

    df = parse_sd_file(path)

    assert list(df.columns) == ["#Sample"] + list(
        range(WAVELENGTH_MIN, WAVELENGTH_MAX + 1)
    )
    assert df.at[0, "#Sample"] == "sample-1"
    assert df.at[0, WAVELENGTH_MIN] == 0.0
    assert df.at[0, WAVELENGTH_MAX] == 0.91


def test_parse_sd_file_old_headers(tmp_path):
    contents = (
        SD_NAME_OLD + b"\x00" * 23 + b"sample-1" + b"\x02"
        + AU_OLD_SD + spectrum_bytes()
    )
    path = write(tmp_path, "data.SD", contents)

    df = parse_sd_file(path)

    assert df.at[0, "#Sample"] == "sample-1"
    assert df.at[0, WAVELENGTH_MAX] == 0.91


def test_parse_sd_file_fills_blank_sample_names(tmp_path):
    contents = (
        SD_NAME_NEW + b"\x00" * 8 + b"" + b"\x09"
        + AU_NEW + b"\x00" * 9 + spectrum_bytes()
    )
    path = write(tmp_path, "data.SD", contents)

    df = parse_sd_file(path)

    assert df.at[0, "#Sample"] == 1


def test_parse_sd_file_rejects_wrong_extension(tmp_path):
    with pytest.raises(ParseError):
        parse_sd_file(tmp_path / "data.KD")


def test_parse_sd_file_rejects_missing_headers(tmp_path):
    path = write(tmp_path, "data.SD", b"\x00" * 1024)

    with pytest.raises(ParseError):
        parse_sd_file(path)


def test_parse_kd_file_new_headers(tmp_path):
    contents = (
        KD_TIME_NEW + b"\x00" * 6 + struct.pack("<d", 2.5)
        + b"\x00" * SPECTRUM_SIZE
        + AU_NEW + b"\x00" * 9 + spectrum_bytes()
    )
    path = write(tmp_path, "data.KD", contents)

    df = parse_kd_file(path)

    assert df.index.name == "Wavelength (nm)"
    assert list(df.index) == list(range(WAVELENGTH_MIN, WAVELENGTH_MAX + 1))
    assert list(df.columns) == [2.5]
    assert df.loc[WAVELENGTH_MIN, 2.5] == 0.0
    assert df.loc[WAVELENGTH_MAX, 2.5] == 0.91


def test_parse_kd_file_old_headers(tmp_path):
    contents = (
        KD_TIME_OLD + b"\x00" * 14 + struct.pack("<d", 1.0)
        + b"\x00" * SPECTRUM_SIZE
        + AU_OLD_KD + b"\x00" + spectrum_bytes()
    )
    path = write(tmp_path, "data.KD", contents)

    df = parse_kd_file(path)

    assert list(df.columns) == [1.0]
    assert df.loc[WAVELENGTH_MAX, 1.0] == 0.91


def test_parse_kd_file_rejects_wrong_extension(tmp_path):
    with pytest.raises(ParseError):
        parse_kd_file(tmp_path / "data.SD")


def test_parse_kd_file_rejects_missing_headers(tmp_path):
    path = write(tmp_path, "data.KD", b"\x00" * 1024)

    with pytest.raises(ParseError):
        parse_kd_file(path)


def test_parse_kd_file_rejects_time_without_spectra(tmp_path):
    contents = KD_TIME_NEW + b"\x00" * 6 + struct.pack("<d", 2.5)
    path = write(tmp_path, "data.KD", contents)

    with pytest.raises(ParseError):
        parse_kd_file(path)


def test_parse_txt_file(tmp_path):
    path = tmp_path / "data.txt"
    path.write_text(
        '"WL Result" "<190 nm>" "<191 nm>"\n'
        "0 0.5 0.6\n"
        "0 0.7 0.8\n"
    )

    df = parse_txt_file(path)

    assert list(df.columns) == ["190", "191"]
    assert df.at[0, "190"] == 0.5
    assert df.at[1, "191"] == 0.8


def sd_record(variant, name=b"sample", values=None):
    payload = spectrum_bytes() if values is None else values
    if name is None:
        return (AU_NEW + b"\x00" * 9 if variant == "new" else AU_OLD_SD) + payload
    if variant == "new":
        return SD_NAME_NEW + b"\x00" * 8 + name + b"\x09" + AU_NEW + b"\x00" * 9 + payload
    return SD_NAME_OLD + b"\x00" * 23 + name + b"\x02" + AU_OLD_SD + payload


def kd_record(variant, time=2.5, values=None, padded=True):
    payload = spectrum_bytes() if values is None else values
    padding = b"\x00" * SPECTRUM_SIZE if padded else b""
    if variant == "new":
        return (
            KD_TIME_NEW + b"\x00" * 6 + struct.pack("<d", time)
            + padding + AU_NEW + b"\x00" * 9 + payload
        )
    return (
        KD_TIME_OLD + b"\x00" * 14 + struct.pack("<d", time)
        + padding + AU_OLD_KD + b"\x00" + payload
    )


@pytest.mark.parametrize("variant", ["old", "new"])
def test_parse_sd_preserves_multiple_samples_and_all_absorbances(tmp_path, variant):
    second = struct.pack(f"<{WAVELENGTH_COUNT}d", *([0.75] * WAVELENGTH_COUNT))
    path = write(tmp_path, "multiple.sd", sd_record(variant, b"first") + sd_record(variant, b"", second))

    actual = parse_sd_file(path)

    expected = pd.DataFrame(
        [["first", *[i / 1000.0 for i in range(911)]], [2, *([0.75] * 911)]],
        columns=["#Sample", *range(190, 1101)],
    )
    pd.testing.assert_frame_equal(actual, expected)


@pytest.mark.parametrize("variant", ["old", "new"])
@pytest.mark.parametrize("names,expected_names", [
    ([b"first", None], ["first", 2]),
    ([None, None], [1, 2]),
    ([b"", b"middle", b""], [1, "middle", 3]),
    ([b"first", b"", b"last"], ["first", 2, "last"]),
])
def test_parse_sd_generates_labels_without_losing_spectra(tmp_path, variant, names, expected_names):
    values = [float(index + 1) / 4 for index in range(len(names))]
    contents = b"".join(
        sd_record(variant, name, struct.pack("<911d", *([value] * 911)))
        for name, value in zip(names, values)
    )
    path = write(tmp_path, "missing-labels.SD", contents)

    actual = parse_sd_file(path)

    assert actual["#Sample"].tolist() == expected_names
    expected_spectra = pd.DataFrame(
        [[value] * 911 for value in values], columns=pd.Index(range(190, 1101), dtype=object)
    )
    pd.testing.assert_frame_equal(actual.drop(columns="#Sample"), expected_spectra)


@pytest.mark.parametrize("variant", ["old", "new"])
@pytest.mark.parametrize("missing_bytes", [1, 8, 64])
@pytest.mark.parametrize("following_count", [1, 2])
def test_parse_sd_rejects_truncated_unlabeled_nonfinal_spectrum(
    tmp_path, variant, missing_bytes, following_count
):
    record = sd_record(variant, None)
    path = write(tmp_path, "unlabeled-truncated.SD", record[:-missing_bytes] + record * following_count)

    with pytest.raises(ParseError):
        parse_sd_file(path)


@pytest.mark.parametrize("variant", ["old", "new"])
@pytest.mark.parametrize("missing_bytes", [0, 1, 8, 64])
def test_parse_sd_checks_unlabeled_records_before_trailing_name_metadata(tmp_path, variant, missing_bytes):
    marker = AU_NEW if variant == "new" else AU_OLD_SD
    metadata = sd_record(variant, b"known").split(marker, 1)[0]
    record = sd_record(variant, None)
    first = record[:-missing_bytes] if missing_bytes else record
    path = write(tmp_path, "trailing-name.SD", first + record + metadata)

    if missing_bytes:
        with pytest.raises(ParseError):
            parse_sd_file(path)
    else:
        actual = parse_sd_file(path)
        assert actual["#Sample"].tolist() == ["known", 2]
        assert actual.iloc[0, 1:].tolist() == [i / 1000.0 for i in range(911)]
        assert actual.iloc[1, 1:].tolist() == [i / 1000.0 for i in range(911)]


@pytest.mark.parametrize("variant", ["old", "new"])
def test_parse_sd_accepts_spectrum_marker_inside_unlabeled_absorbance(tmp_path, variant):
    payload = bytearray(struct.pack("<911d", *([0.25] * 911)))
    marker = AU_NEW if variant == "new" else AU_OLD_SD
    payload[80:80 + len(marker)] = marker
    path = write(
        tmp_path, "marker-in-values.SD",
        sd_record(variant, None, payload) + sd_record(variant, None),
    )

    actual = parse_sd_file(path)

    assert actual["#Sample"].tolist() == [1, 2]
    assert actual.iloc[0, 1:].tolist() == list(struct.unpack("<911d", payload))
    assert actual.iloc[1, 1:].tolist() == [i / 1000.0 for i in range(911)]


@pytest.mark.parametrize("variant", ["old", "new"])
@pytest.mark.parametrize("padded", [False, True])
def test_parse_kd_preserves_multiple_times_and_all_absorbances(tmp_path, variant, padded):
    second = struct.pack(f"<{WAVELENGTH_COUNT}d", *([0.75] * WAVELENGTH_COUNT))
    path = write(
        tmp_path, "multiple.kd",
        kd_record(variant, 2.5, padded=padded) + kd_record(variant, 9.0, second, padded=padded),
    )

    actual = parse_kd_file(path)

    expected = pd.DataFrame(
        {2.5: [i / 1000.0 for i in range(911)], 9.0: [0.75] * 911},
        index=pd.Index(range(190, 1101), name="Wavelength (nm)"),
    )
    pd.testing.assert_frame_equal(actual, expected)


def test_parse_kd_accepts_time_marker_bytes_inside_finite_absorbance(tmp_path):
    payload = bytearray(spectrum_bytes())
    payload[80:88] = b"RelTime\x3f"
    # Some KD exports place spectra immediately after time metadata, without
    # the extra padding used by the other fixtures.
    contents = (
        KD_TIME_OLD + b"\x00" * 14 + struct.pack("<d", 2.5)
        + AU_OLD_KD + b"\x00" + payload
    )
    path = write(tmp_path, "compact.KD", contents)

    actual = parse_kd_file(path)

    expected = [i / 1000.0 for i in range(911)]
    expected[10] = 0.002615648004746043
    assert list(actual.columns) == [2.5]
    assert actual[2.5].tolist() == expected


@pytest.mark.parametrize("variant", ["old", "new"])
def test_parse_kd_rejects_compact_record_truncated_before_next_acquisition(tmp_path, variant):
    path = write(
        tmp_path, "compact-truncated.KD",
        kd_record(variant, 2.5, padded=False)[:-64] + kd_record(variant, 9.0, padded=False),
    )

    with pytest.raises(ParseError):
        parse_kd_file(path)


@pytest.mark.parametrize("variant,name", [
    ("new", "control (AU)".encode("utf-16le")),
    ("old", b"control (AU)\x00"),
])
def test_parse_sd_allows_spectrum_marker_in_terminated_sample_name(tmp_path, variant, name):
    path = write(tmp_path, "marker-name.SD", sd_record(variant, name))

    actual = parse_sd_file(path)

    assert actual.at[0, "#Sample"] == "control (AU)"
    assert actual.iloc[0, 1:].tolist() == [i / 1000.0 for i in range(911)]


@pytest.mark.parametrize("variant", ["old", "new"])
@pytest.mark.parametrize("missing_bytes", [1, 8])
@pytest.mark.parametrize("extension,parser,record", [
    ("SD", parse_sd_file, sd_record), ("KD", parse_kd_file, kd_record),
])
def test_binary_parsers_reject_truncated_nonfinal_spectrum(
    tmp_path, variant, missing_bytes, extension, parser, record
):
    contents = record(variant)[:-missing_bytes] + record(variant)
    path = write(tmp_path, f"nonfinal.{extension}", contents)

    with pytest.raises(ParseError):
        parser(path)


@pytest.mark.parametrize("variant", ["old", "new"])
@pytest.mark.parametrize("missing_bytes", [1, 8, SPECTRUM_SIZE])
@pytest.mark.parametrize("extension,parser,record", [("SD", parse_sd_file, sd_record), ("KD", parse_kd_file, kd_record)])
def test_binary_parsers_reject_truncated_spectra(tmp_path, variant, missing_bytes, extension, parser, record):
    path = write(tmp_path, f"truncated.{extension}", record(variant)[:-missing_bytes])

    with pytest.raises(ParseError):
        parser(path)


@pytest.mark.parametrize("variant", ["old", "new"])
def test_parse_kd_rejects_truncated_time(tmp_path, variant):
    header = KD_TIME_NEW + b"\x00" * 6 if variant == "new" else KD_TIME_OLD + b"\x00" * 14
    path = write(tmp_path, "truncated.KD", header + b"\x00" * 7)

    with pytest.raises(ParseError):
        parse_kd_file(path)


@pytest.mark.parametrize("variant", ["old", "new"])
def test_parse_sd_rejects_sample_without_terminator(tmp_path, variant):
    contents = sd_record(variant)
    terminator = b"\x09" if variant == "new" else b"\x02"
    path = write(tmp_path, "unterminated.SD", contents.replace(terminator, b"", 1))

    with pytest.raises(ParseError):
        parse_sd_file(path)


@pytest.mark.parametrize("variant", ["old", "new"])
def test_parse_sd_rejects_sample_spectrum_count_mismatch(tmp_path, variant):
    extra_name = SD_NAME_NEW + b"\x00" * 8 + b"extra\x09" if variant == "new" else SD_NAME_OLD + b"\x00" * 23 + b"extra\x02"
    path = write(tmp_path, "mismatch.SD", sd_record(variant) + extra_name)

    with pytest.raises(ParseError):
        parse_sd_file(path)


@pytest.mark.parametrize("variant", ["old", "new"])
def test_parse_kd_rejects_time_spectrum_count_mismatch(tmp_path, variant):
    extra_spectrum = AU_NEW + b"\x00" * 9 if variant == "new" else AU_OLD_KD + b"\x00"
    path = write(tmp_path, "mismatch.KD", kd_record(variant) + extra_spectrum + spectrum_bytes())

    with pytest.raises(ParseError):
        parse_kd_file(path)


@pytest.mark.parametrize("contents", [
    "", '"WL Result" "<190 nm>"\n',
    '"<190 nm>"\n0.5\n', 'WL Result <190 nm>\n0 0.5\n',
    '"WL Result" "<190 nm>"\n0 0.5 0.6\n',
    '"WL Result" "<190 nm>"\n0 invalid\n',
])
def test_parse_txt_rejects_malformed_tables(tmp_path, contents):
    path = tmp_path / "malformed.txt"
    path.write_text(contents)

    with pytest.raises(ParseError):
        parse_txt_file(path)


@pytest.mark.parametrize("rows,expected_190,expected_191", [
    (["0 1 0.5 0.6", "0 2 0.7"], [0.5, 0.7], [0.6, float("nan")]),
    (["0 1 0.5", "0 2 0.7"], [0.5, 0.7], [float("nan"), float("nan")]),
    (["0 1 0.5 0.6", "0 2"], [0.5, float("nan")], [0.6, float("nan")]),
])
def test_parse_txt_preserves_missing_trailing_absorbances_as_nan(
    tmp_path, rows, expected_190, expected_191
):
    path = tmp_path / "missing-values.txt"
    path.write_text('"WL Result" "#Sample" "<190 nm>" "<191 nm>"\n' + "\n".join(rows) + "\n")

    actual = parse_txt_file(path)

    expected = pd.DataFrame({"#Sample": [1, 2], "190": expected_190, "191": expected_191})
    pd.testing.assert_frame_equal(actual, expected)


def test_parse_txt_accepts_tabs_crlf_and_indented_rows(tmp_path):
    path = tmp_path / "whitespace.txt"
    path.write_bytes(b'"WL Result"\t"<190 nm>"\t"<191 nm>"\r\n  0\t0.5\t0.6  \r\n  0\t0.7\t0.8\r\n')

    pd.testing.assert_frame_equal(parse_txt_file(path), pd.DataFrame({"190": [0.5, 0.7], "191": [0.6, 0.8]}))


@pytest.mark.parametrize("extension,parser", [("SD", parse_sd_file), ("KD", parse_kd_file), ("txt", parse_txt_file)])
def test_parsers_wrap_missing_file_errors(tmp_path, extension, parser):
    with pytest.raises(ParseError):
        parser(tmp_path / f"missing.{extension}")


def test_parse_txt_wraps_decoding_errors(tmp_path):
    path = write(tmp_path, "invalid.txt", b"\xff\xfe\xff")

    with pytest.raises(ParseError):
        parse_txt_file(path)
