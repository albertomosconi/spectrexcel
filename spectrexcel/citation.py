"""Resolve a release-specific DOI without substituting the latest release."""

import re

import requests
from packaging.version import InvalidVersion, Version

from spectrexcel.updater import REPOSITORY_URL


CONCEPT_RECORD_ID = "23161786"
CONCEPT_DOI = "10.5281/zenodo.23161786"
API_URL = "https://zenodo.org/api/records"
REQUEST_HEADERS = {
    "Accept": "application/vnd.zenodo.v1+json",
    "User-Agent": "SpectrExcel citation lookup",
}


def find_version_doi(current_version: str) -> str | None:
    """Search all versions in this project's record family; compare locally.

    Network/JSON errors propagate to the app's worker error handler, which
    leaves the all-versions DOI visible. No credentials are needed.
    """
    try:
        installed_version = Version(current_version)
    except InvalidVersion:
        return None

    page = 1
    while True:
        response = requests.get(
            API_URL,
            params={
                "q": f"conceptrecid:{CONCEPT_RECORD_ID}",
                "all_versions": "true",
                "size": 25,
                "page": page,
                "sort": "mostrecent",
            },
            headers=REQUEST_HEADERS,
            timeout=10,
        )
        response.raise_for_status()
        hits = response.json().get("hits", {})
        records = hits.get("hits", [])
        for record in records:
            if not isinstance(record, dict):
                continue
            if (
                str(record.get("conceptrecid")) != CONCEPT_RECORD_ID
                or record.get("status") != "published"
            ):
                continue
            metadata = record.get("metadata") or {}
            version = metadata.get("version")
            if not isinstance(version, str):
                continue
            try:
                if Version(version) != installed_version:
                    continue
            except InvalidVersion:
                continue
            release_url = f"{REPOSITORY_URL}/tree/{version}"
            if not any(
                isinstance(identifier, dict)
                and identifier.get("identifier") == release_url
                and identifier.get("relation") == "isSupplementTo"
                for identifier in metadata.get("related_identifiers", [])
            ):
                continue
            doi = record.get("doi")
            if (
                isinstance(doi, str)
                and re.fullmatch(r"10\.5281/zenodo\.[0-9]+", doi)
                and doi != CONCEPT_DOI
            ):
                return doi
        if not records or page * 25 >= hits.get("total", 0):
            return None
        page += 1
