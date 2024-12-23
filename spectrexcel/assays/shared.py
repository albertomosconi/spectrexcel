import re
from pathlib import Path
from typing import Callable, Tuple

import pandas as pd
from PyQt6 import QtWidgets as widgets


class AssayWidget(widgets.QWidget):
    def __init__(self, log: Callable[[str | list[str]], None]):
        super().__init__()

        self.log = log


def parse_txt_file(filepath: Path) -> pd.DataFrame:

    with filepath.open("r") as fp:
        contents = fp.read()

    contents = re.sub(r"[ \t]+", " ", contents.strip())
    contents = contents.split("\n")

    # TODO: validate file format

    first_line = contents[0]
    first_line = re.sub(r"<(\d+) nm>", r"\g<1>", first_line)
    columns = first_line[1:-1].split('" "')

    df = pd.DataFrame(
        data=[line.split(" ") for line in contents[1:]],
        columns=columns,
    )

    df = df.drop("WL Result", axis=1)
    df = df.apply(pd.to_numeric)

    return df


def clean_duplicate_spectra(df: pd.DataFrame) -> Tuple[pd.DataFrame, bool]:

    halfway_row = int(len(df) / 2)
    df_data = df.drop("#Sample", axis=1)
    df_1st_half = df_data.head(halfway_row).reset_index(drop=True)
    df_2nd_half = df_data.tail(halfway_row).reset_index(drop=True)

    if df_1st_half.equals(df_2nd_half):
        df = df.head(halfway_row)
        return df, True

    return df, False
