<div align="center">
<img src="spectrexcel/icon.ico" width="100" alt="spectrexcel logo" />
<h1>SpectrExcel</h1>
<a href="https://zenodo.org/badge/latestdoi/1299302270"><img src="https://zenodo.org/badge/1299302270.svg" alt="DOI" /></a>
</div>

## Documentation

See the [documentation website](https://spectrexcel.albertomosconi.it/docs/) for
usage instructions and export details.

## Citation

If you use SpectrExcel in your work, please cite it using the metadata in
[`CITATION.cff`](CITATION.cff). Releases are archived on Zenodo; for
reproducibility, cite the DOI of the version you used. The app's right-aligned
footer link shows that version's DOI when the startup lookup succeeds, otherwise
the [all-versions DOI](https://doi.org/10.5281/zenodo.23161786), which resolves to
the latest release. Hover over the link to see which citation it represents.

## Development

Install dependencies and run the application with [uv](https://docs.astral.sh/uv/):

```shell
uv sync
uv run start
```

Build the platform-specific executable with PyInstaller:

```shell
uv run build
```

Run the test suite:

```shell
uv run pytest
```

Run type checks:

```shell
uv run pyright
```

In VS Code, select the interpreter inside `.venv` using **Python: Select
Interpreter**. After installing dependencies, reload the window if diagnostics
have not refreshed. `pyproject.toml` enables standard type checking, deprecation
warnings, and Python 3.10 compatibility. The `All` platform setting lets the
checker inspect both Linux and Windows APIs regardless of the editor's OS.

Development dependencies include `pandas-stubs`. Narrow local Dear PyGui
corrections in `typings/dearpygui/` fix its context-manager annotations and
child-slot return types while retaining its bundled native API signatures.
After upgrading Dear PyGui, regenerate public wrapper signatures with
`uv run python scripts/generate_dearpygui_stubs.py`, then rerun type checks.

## Releases

Windows x86-64 executables and Linux x86-64 AppImages are published on the
[GitHub Releases](https://github.com/albertomosconi/spectrexcel/releases) page.
On Linux, download and extract the `.AppImage.tar.gz` asset to preserve the
executable permission. If you download the raw AppImage instead, enable it
before launching:

```shell
chmod +x SpectrExcel-x86_64.AppImage
./SpectrExcel-x86_64.AppImage
```

The Linux application requires a working X11/GLX OpenGL implementation. The
AppImage uses the graphics libraries and drivers installed by the host system.

SpectrExcel checks the latest stable release at startup. When an update is
available, it opens the platform download in your browser and closes. Replace
the old executable or AppImage with the downloaded file before restarting.

To publish a release, update the version in `pyproject.toml`, refresh
`uv.lock`, commit the changes, and push a matching tag:

```shell
uv lock
git tag v1.1.0
git push origin main v1.1.0
```

GitHub Actions validates the version, runs the tests, builds both supported
platform artifacts, creates `SHA256SUMS`, and publishes the GitHub Release.

## Windows executable signing

Windows releases are unsigned, and executable signing is not currently planned.
Windows or antivirus software may warn about or block unsigned executables. See
the [Windows executable signing notes](CODE_SIGNING.md) for release details.

Windows builds include product and file metadata derived from the package
version in `pyproject.toml`; this metadata is not a digital signature.

## Privacy

Measurement files and Excel exports are processed locally and are not uploaded.
SpectrExcel automatically contacts GitHub at startup to check for updates and
also contacts it when **Check updates** is selected. GitHub receives normal
connection information, including the public IP address and request headers;
the installed application version is compared locally, not sent. There is
currently no setting to disable the automatic check. SpectrExcel also contacts
Zenodo at startup to look up the installed version's DOI. Zenodo receives normal
connection information; version matching happens locally. No measurement data
is sent. Requested downloads, project links, and DOI links open in your browser.
See the
[privacy and network disclosure](CODE_SIGNING.md#privacy-and-network-access)
for details and links to the services' privacy policies.
