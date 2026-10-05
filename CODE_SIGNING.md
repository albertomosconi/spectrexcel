# Windows executable signing

## Current status

SpectrExcel's Windows releases are unsigned. Executable signing is not currently
planned. Windows builds include product and file metadata derived from the
package version in `pyproject.toml`; this metadata is not a digital signature.

## Release artifacts

The GitHub Actions release workflow validates the release tag against the
project version, runs the test suite, builds the Windows executable and Linux
AppImage, and publishes them with `SHA256SUMS`. Checksums can verify that a
download matches the published artifact; they are not digital signatures.

Download releases from the project's
[GitHub Releases](https://github.com/albertomosconi/spectrexcel/releases) page.
Windows or antivirus software may warn about or block unsigned executables.

## Privacy and network access

SpectrExcel processes measurement files and generates Excel workbooks locally.
It does not upload measurement contents, generated workbooks, file paths, or
application settings, and it includes no analytics or telemetry.

**The application automatically contacts GitHub at startup** to check the
latest stable release. The same request is made when the user selects
**Check updates**. There is currently no in-app setting to disable the startup
check. The HTTPS request is sent to
`https://api.github.com/repos/albertomosconi/spectrexcel/releases/latest`, with
a generic `SpectrExcel updater` User-Agent. It does not send the installed
application version; version comparison happens locally. GitHub receives
normal connection information such as the public IP address and request
headers.

**The application also automatically contacts Zenodo at startup** to look up
the DOI for the installed release. Requests go to `https://zenodo.org/api/records`
and search the project's record family (`conceptrecid:23161786`), including
older pages when needed, with a generic `SpectrExcel citation lookup` User-Agent.
The installed version is compared locally and is not sent. Zenodo receives
normal connection information such as the public IP address and request headers.
There is no in-app setting to disable this lookup. If lookup fails or no matching
release is archived, the footer keeps the all-versions DOI, which resolves to
the latest release rather than necessarily the installed version.

Selecting the footer DOI opens `https://doi.org/` in the user's browser, which
redirects to Zenodo. These requests are governed by the services' privacy
policies, including the [Zenodo Privacy Policy](https://about.zenodo.org/privacy-policy/).

When the user requests an update download, the full changelog, or the source
repository, SpectrExcel opens the relevant GitHub URL in the user's browser.
The browser then makes its own network requests. GitHub's processing of these
requests is governed by the
[GitHub Privacy Statement](https://docs.github.com/en/site-policy/privacy-policies/github-privacy-statement).

## Removing the application

The released application is portable. To remove it, close SpectrExcel and
delete its executable or AppImage. This does not delete input files or exported
workbooks. To also remove saved preferences, delete the `spectrexcel` settings
directory: normally `%LOCALAPPDATA%\magichemistry\spectrexcel` on Windows or
`${XDG_CONFIG_HOME:-~/.config}/spectrexcel` on Linux.
