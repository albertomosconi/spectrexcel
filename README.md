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
SpectrExcel checks the latest stable release at startup and can download,
verify, install, and restart into an available update. Linux automatic updates
require running the AppImage from a writable location.

To publish a release, update the version in `pyproject.toml`, refresh
`uv.lock`, commit the changes, and push a matching tag:

```shell
uv lock
git tag v1.1.0
git push origin main v1.1.0
```

GitHub Actions validates the version, runs the tests, builds both supported
platform artifacts, creates `SHA256SUMS`, and publishes the GitHub Release.
