<div align="center">
<img src="spectrexcel/icon.ico" width="100" alt="spectrexcel logo" />
<h1>SpectrExcel</h1>
</div>

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
