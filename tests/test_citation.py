import copy

import pytest
import requests


def record(version="v1.7.0", doi="10.5281/zenodo.23161787"):
    return {
        "conceptrecid": "23161786",
        "doi": doi,
        "status": "published",
        "metadata": {
            "version": version,
            "related_identifiers": [{
                "identifier": "https://github.com/albertomosconi/spectrexcel/tree/" + version,
                "relation": "isSupplementTo",
                "scheme": "url",
            }],
        },
    }


def serve_records(monkeypatch, citation, pages):
    calls = []

    class Response:
        def __init__(self, data):
            self.data = data

        def raise_for_status(self):
            pass

        def json(self):
            return self.data

    def get(url, *, params, headers, timeout):
        calls.append((url, params.copy(), headers, timeout))
        assert url == "https://zenodo.org/api/records"
        assert params["q"] == "conceptrecid:23161786"
        assert params["all_versions"] == "true"
        assert timeout == 10
        return Response(pages[params["page"] - 1])

    monkeypatch.setattr(citation.requests, "get", get)
    return calls


def test_lookup_finds_installed_version_not_latest(monkeypatch):
    from spectrexcel import citation

    serve_records(monkeypatch, citation, [{"hits": {"hits": [
        record("v1.8.0", "10.5281/zenodo.99999999"), record(),
    ], "total": 2}}])
    assert citation.find_version_doi("1.7.0") == "10.5281/zenodo.23161787"


@pytest.mark.parametrize("mutation", ["version", "family", "repository", "doi", "concept_doi", "draft"])
def test_lookup_rejects_unverified_record(monkeypatch, mutation):
    from spectrexcel import citation

    candidate = copy.deepcopy(record())
    if mutation == "version":
        candidate["metadata"]["version"] = "v1.8.0"
    elif mutation == "family":
        candidate["conceptrecid"] = "123"
    elif mutation == "repository":
        candidate["metadata"]["related_identifiers"][0]["identifier"] = (
            "https://github.com/someone/spectrexcel/tree/v1.7.0"
        )
    elif mutation == "doi":
        candidate["doi"] = "not-a-doi"
    elif mutation == "concept_doi":
        candidate["doi"] = "10.5281/zenodo.23161786"
    else:
        candidate["status"] = "draft"
    serve_records(monkeypatch, citation, [{"hits": {"hits": [candidate], "total": 1}}])
    assert citation.find_version_doi("1.7.0") is None


def test_lookup_checks_older_pages(monkeypatch):
    from spectrexcel import citation

    calls = serve_records(monkeypatch, citation, [
        {"hits": {"hits": [record("v2.0.0")] * 25, "total": 26}},
        {"hits": {"hits": [record()], "total": 26}},
    ])
    assert citation.find_version_doi("1.7.0") == "10.5281/zenodo.23161787"
    assert len(calls) == 2


def test_lookup_exhausts_pages_without_substituting_other_version(monkeypatch):
    from spectrexcel import citation

    calls = serve_records(monkeypatch, citation, [
        {"hits": {"hits": [record("v2.0.0")] * 25, "total": 26}},
        {"hits": {"hits": [record("v1.7.0")], "total": 26}},
    ])
    assert citation.find_version_doi("1.6.2") is None
    assert len(calls) == 2


@pytest.mark.parametrize("payload", [{}, {"hits": {"hits": [], "total": 0}},
                                      {"hits": {"hits": [None, {}], "total": 2}}])
def test_lookup_handles_missing_metadata(monkeypatch, payload):
    from spectrexcel import citation

    serve_records(monkeypatch, citation, [payload])
    assert citation.find_version_doi("1.7.0") is None


def test_lookup_network_error_reaches_worker_error_handler(monkeypatch):
    from spectrexcel import citation

    def fail(*args, **kwargs):
        raise requests.Timeout("offline")

    monkeypatch.setattr(citation.requests, "get", fail)
    with pytest.raises(requests.Timeout):
        citation.find_version_doi("1.7.0")
