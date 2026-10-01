# Code signing policy

## Current status

SpectrExcel's Windows releases are currently unsigned. This policy describes
the intended signing process for an application to SignPath Foundation;
enrollment and signing integration are not yet complete. Executable metadata
is not a digital signature.

The proposed service is [SignPath.io](https://about.signpath.io), with a
certificate provided by [SignPath Foundation](https://signpath.org). No
sponsorship or approval is claimed before acceptance. Once enrollment is
approved and signed releases are available, the project will publish the
required attribution: “Free code signing provided by SignPath.io, certificate
by SignPath Foundation”.

## Team and responsibilities

- **Author / committer:** [Alberto Mosconi](https://github.com/albertomosconi).
- **Reviewer:** [Alberto Mosconi](https://github.com/albertomosconi), responsible
  for reviewing contributions before merging, including build scripts and CI
  changes.
- **Signing approver:** [Alberto Mosconi](https://github.com/albertomosconi),
  responsible for manually approving each release signing request.

Before enrollment, the maintainer must enable multi-factor authentication for
GitHub and SignPath access. These responsibilities describe the intended
process, not a claim that account settings have been verified.

## Intended release signing process

Only Windows release executables built from this repository by its GitHub
Actions release workflow will be submitted for signing. The workflow must
validate the release tag against the project version and pass the test suite
before building. Product name is `SpectrExcel`; file and product versions are
derived from the installed package version, which comes from `pyproject.toml`.
SignPath artifact restrictions must enforce this metadata during enrollment.

Each release signing request requires manual approval. After signing, the
workflow must verify the signature and generate release checksums from the
signed executable before publishing. Third-party binaries must not be
independently signed using the project's certificate. Signing does not
guarantee that antivirus software will permit execution.

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

When the user requests an update download, the full changelog, or the source
repository, SpectrExcel opens the relevant GitHub URL in the user's browser.
The browser then makes its own network requests. GitHub's processing of these
requests is governed by the
[GitHub Privacy Statement](https://docs.github.com/en/site-policy/privacy-policies/github-privacy-statement).

The startup network check must be disclosed during the SignPath application;
the project does not claim that all network access is explicitly requested by
the user. SignPath may require additional privacy controls before approval.

## Removing the application

The released application is portable. To remove it, close SpectrExcel and
delete its executable or AppImage. This does not delete input files or exported
workbooks. To also remove saved preferences, delete the `spectrexcel` settings
directory: normally `%LOCALAPPDATA%\magichemistry\spectrexcel` on Windows or
`${XDG_CONFIG_HOME:-~/.config}/spectrexcel` on Linux.
