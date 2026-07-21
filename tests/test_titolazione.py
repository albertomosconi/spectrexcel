import pandas as pd

from spectrexcel.assays.titolazione import clean_duplicate_spectra


def test_clean_duplicate_spectra_keeps_single_spectrum():
    dataframe = pd.DataFrame([
        {"#Sample": "sample-1", 190: 0.1, 191: 0.2},
    ])

    cleaned, did_clean = clean_duplicate_spectra(dataframe)

    assert not did_clean
    assert cleaned.equals(dataframe)


def test_clean_duplicate_spectra_removes_matching_halves():
    dataframe = pd.DataFrame([
        {"#Sample": "sample-1", 190: 0.1, 191: 0.2},
        {"#Sample": "sample-2", 190: 0.3, 191: 0.4},
        {"#Sample": "sample-3", 190: 0.1, 191: 0.2},
        {"#Sample": "sample-4", 190: 0.3, 191: 0.4},
    ])

    cleaned, did_clean = clean_duplicate_spectra(dataframe)

    assert did_clean
    assert cleaned.equals(dataframe.head(2))


def test_clean_duplicate_spectra_keeps_odd_number_of_rows():
    dataframe = pd.DataFrame([
        {"#Sample": "sample-1", 190: 0.1, 191: 0.2},
        {"#Sample": "sample-2", 190: 0.3, 191: 0.4},
        {"#Sample": "sample-3", 190: 0.1, 191: 0.2},
    ])

    cleaned, did_clean = clean_duplicate_spectra(dataframe)

    assert not did_clean
    assert cleaned.equals(dataframe)
