import struct

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
