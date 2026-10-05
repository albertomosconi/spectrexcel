<div align="center">
<img src="spectrexcel/icon.ico" width="100" alt="spectrexcel logo" />
<h1>SpectrExcel</h1>
</div>

## Export details

Each assay has an **Include info sheet** checkbox below the Generate Excel and
Preview chart buttons. It starts unchecked and remembers your last choice across
assays and application restarts. Enable it to append an
**info** worksheet containing the SpectrExcel version, export timestamp with
timezone, source filenames and SHA-256 hashes, analysis settings, and processing
steps. Data sheets, charts, and previews are unchanged.
The info worksheet uses the app's language; source filenames and hashes are
preserved exactly.

Hashes identify the files as loaded, even if those files change before export.
Full source paths are not included. Keep the original input files alongside the
workbook: the info sheet provides traceability, not a copy of the measurements.

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
currently no setting to disable the automatic check. Requested downloads and
project links open in your browser. See the
[privacy and network disclosure](CODE_SIGNING.md#privacy-and-network-access)
for details and GitHub's privacy policy.
