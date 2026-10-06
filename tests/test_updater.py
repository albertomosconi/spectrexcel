import dearpygui.dearpygui as dpg
import pytest
from packaging.version import Version

from spectrexcel import main, updater
from spectrexcel.dpi import DisplayScale
from spectrexcel.i18n import get_language, set_language


WINDOWS_ASSET = "spectrexcel-windows-x86_64.exe"
LINUX_ASSET = "SpectrExcel-x86_64.AppImage"


class FakeResponse:
    def __init__(self, json_data):
        self._json_data = json_data

    def json(self):
        return self._json_data

    def raise_for_status(self):
        return None


RELEASE_BODY = (
    "## What's Changed\n"
    "\n"
    "### Features\n"
    "- something new\n"
    "\n"
    "**Full Changelog**: https://example/compare/v1.0.3...v1.1.0\n"
)


def release_payload(tag="v1.1.0", body=RELEASE_BODY, windows=True, linux=True):
    assets = []
    if windows:
        assets.append(
            {"name": WINDOWS_ASSET, "browser_download_url": "https://example/windows"}
        )
    if linux:
        assets.append(
            {"name": LINUX_ASSET, "browser_download_url": "https://example/linux"}
        )
    return {"tag_name": tag, "body": body, "assets": assets}


def fake_get(payload):
    return lambda *args, **kwargs: FakeResponse(payload)


@pytest.fixture
def dpg_context():
    previous_language = get_language()
    dpg.create_context()
    # Tall viewport so changelog dialog growth is not clamped in the
    # sizing tests; clamping itself is covered in its own test.
    dpg.create_viewport(width=800, height=900)
    try:
        yield
    finally:
        dpg.destroy_context()
        set_language(previous_language)


def dialog_app(version: str = "1.0.0") -> main.SpectrExcelApp:
    app = object.__new__(main.SpectrExcelApp)
    app.version = version
    app.display_scale = DisplayScale()
    return app


def test_find_update_selects_platform_download(monkeypatch):
    monkeypatch.setattr(
        updater.requests, "get", fake_get([release_payload()])
    )

    update = updater.find_update("1.0.3", platform="linux")

    assert update is not None
    assert update.tag == "v1.1.0"
    assert update.version == Version("1.1.0")
    assert update.asset == updater.ReleaseAsset(LINUX_ASSET, "https://example/linux")
    assert update.notes == RELEASE_BODY
    assert update.previous_notes == ()


def test_find_update_returns_none_for_installed_version(monkeypatch):
    monkeypatch.setattr(
        updater.requests, "get", fake_get([release_payload()])
    )

    assert updater.find_update("1.1.0", platform="win32") is None


def test_find_update_rejects_missing_platform_asset(monkeypatch):
    payload = release_payload()
    payload["assets"] = payload["assets"][:1]
    monkeypatch.setattr(updater.requests, "get", fake_get([payload]))

    with pytest.raises(updater.UpdateError, match=LINUX_ASSET):
        updater.find_update("1.0.3", platform="linux")


def test_find_update_rejects_unsupported_platform():
    with pytest.raises(updater.UpdateError, match="not supported"):
        updater.find_update("1.0.3", platform="darwin")


def test_find_update_defaults_missing_notes(monkeypatch):
    payload = release_payload()
    del payload["body"]
    monkeypatch.setattr(updater.requests, "get", fake_get([payload]))

    update = updater.find_update("1.0.3", platform="linux")

    assert update is not None
    assert update.notes == ""


def test_find_update_collects_every_newer_release(monkeypatch):
    body_130 = "## What's Changed\n\n### Features\n- third feature\n"
    body_120 = "## What's Changed\n\n### Bug Fixes\n- fix export\n"
    body_110 = "## What's Changed\n\n### Features\n- first feature\n"
    payload = [
        release_payload("v1.3.0", body=body_130),
        release_payload("v1.2.0", body=body_120),
        release_payload("v1.1.0", body=body_110),
    ]
    monkeypatch.setattr(updater.requests, "get", fake_get(payload))

    update = updater.find_update("1.0.0", platform="linux")

    assert update is not None
    assert update.tag == "v1.3.0"
    assert update.version == Version("1.3.0")
    assert update.notes == body_130
    assert update.previous_notes == (
        updater.ReleaseNotes("v1.2.0", body_120),
        updater.ReleaseNotes("v1.1.0", body_110),
    )


def test_find_update_sorts_newer_releases_by_version(monkeypatch):
    payload = [
        release_payload("v1.1.0", body="oldest"),
        release_payload("v1.3.0", body="latest"),
        release_payload("v1.2.0", body="middle"),
    ]
    monkeypatch.setattr(updater.requests, "get", fake_get(payload))

    update = updater.find_update("1.0.0", platform="linux")

    assert update is not None
    assert update.tag == "v1.3.0"
    assert update.notes == "latest"
    assert [note.tag for note in update.previous_notes] == ["v1.2.0", "v1.1.0"]


def test_find_update_ignores_drafts_prereleases_and_bad_tags(monkeypatch):
    payload = [
        {"tag_name": "v1.4.0", "body": "draft", "draft": True, "assets": []},
        {"tag_name": "v1.3.0-rc1", "body": "pre", "prerelease": True, "assets": []},
        {"tag_name": "not-a-version", "body": "bad", "assets": []},
        release_payload("v1.2.0", body="stable"),
    ]
    monkeypatch.setattr(updater.requests, "get", fake_get(payload))

    update = updater.find_update("1.0.0", platform="linux")

    assert update is not None
    assert update.tag == "v1.2.0"
    assert update.previous_notes == ()


def test_find_update_ignores_prerelease_when_no_stable_update(monkeypatch):
    payload = [
        {"tag_name": "v1.2.0-rc1", "body": "pre", "prerelease": True, "assets": []},
        release_payload("v1.1.0"),
    ]
    monkeypatch.setattr(updater.requests, "get", fake_get(payload))

    assert updater.find_update("1.1.0", platform="linux") is None


def test_format_notes_summarizes_generated_release():
    body = (
        "## What's Changed\n"
        "\n"
        "### Features\n"
        "- add translations\n"
        "- reorder kinetic files\n"
        "\n"
        "### Bug Fixes\n"
        "- align selects\n"
        "\n"
        "**Full Changelog**: https://example/compare/v1.0.0...v1.1.0\n"
    )

    assert updater.format_notes(body) == (
        "Features:\n"
        "- add translations\n"
        "- reorder kinetic files\n"
        "\n"
        "Bug Fixes:\n"
        "- align selects",
        False,
    )


def test_format_notes_handles_empty_body():
    assert updater.format_notes("") == ("", False)
    assert updater.format_notes("  \n \n  ") == ("", False)
    assert updater.format_notes("## What's Changed\n") == ("", False)


def test_format_notes_passes_through_plain_text():
    assert (
        updater.format_notes("Just a note.\n\nAnother line.")
        == ("Just a note.\n\nAnother line.", False)
    )


def test_format_notes_hides_other_changes_section():
    body = (
        "## What's Changed\n"
        "\n"
        "### Features\n"
        "- add translations\n"
        "\n"
        "### Other Changes\n"
        "- split parsing module\n"
        "- generate release notes\n"
        "\n"
        "**Full Changelog**: https://example/compare/v1.0.0...v1.1.0\n"
    )

    assert updater.format_notes(body) == ("Features:\n- add translations", True)


def test_format_notes_reports_hidden_only_changes():
    body = "## What's Changed\n\n### Other Changes\n- tidy up\n"

    assert updater.format_notes(body) == ("", True)


def test_format_notes_ignores_empty_other_changes_heading():
    assert updater.format_notes("### Other Changes\n") == ("", False)


def test_format_notes_keeps_sections_after_other_changes():
    body = (
        "### Other Changes\n"
        "- tidy up\n"
        "\n"
        "### Bug Fixes\n"
        "- align selects\n"
    )

    assert updater.format_notes(body) == ("Bug Fixes:\n- align selects", True)


def test_aggregate_notes_groups_by_release_newest_first():
    assert updater.aggregate_notes(
        (
            ("v1.2.0", "### Features\n- second feature\n"),
            ("v1.1.0", "### Bug Fixes\n- align selects\n"),
        )
    ) == (
        "v1.2.0:\n"
        "Features:\n"
        "- second feature\n"
        "\n"
        "v1.1.0:\n"
        "Bug Fixes:\n"
        "- align selects",
        False,
    )


def test_aggregate_notes_skips_empty_releases():
    assert updater.aggregate_notes(
        (
            ("v1.2.0", ""),
            ("v1.1.0", "### Bug Fixes\n- align selects\n"),
        )
    ) == ("v1.1.0:\nBug Fixes:\n- align selects", False)


def test_aggregate_notes_reports_hidden_from_any_release():
    notes, has_hidden = updater.aggregate_notes(
        (
            ("v1.2.0", "### Features\n- second feature\n"),
            ("v1.1.0", "### Other Changes\n- tidy up\n"),
        )
    )

    assert notes == "v1.2.0:\nFeatures:\n- second feature"
    assert has_hidden is True


def test_aggregate_notes_empty_input():
    assert updater.aggregate_notes(()) == ("", False)


def test_update_dialog_lists_every_spanned_version(dpg_context, monkeypatch):
    set_language("en")
    release = updater.UpdateRelease(
        "v1.3.0",
        Version("1.3.0"),
        updater.ReleaseAsset(WINDOWS_ASSET, "https://example/windows"),
        notes="## What's Changed\n\n### Features\n- import wizard\n",
        previous_notes=(
            updater.ReleaseNotes("v1.2.0", "### Bug Fixes\n- align selects\n"),
            updater.ReleaseNotes("v1.1.0", "### Other Changes\n- tidy up\n"),
        ),
    )

    dialog_app()._show_update_confirmation(release)

    assert dpg.does_item_exist("update.modal")
    assert dpg.get_value("update.modal.header") == "What's new since 1.0.0:"
    notes = dpg.get_value("update.modal.notes")
    assert "v1.3.0:\nFeatures:\n- import wizard" in notes
    assert "v1.2.0:\nBug Fixes:\n- align selects" in notes
    assert "v1.1.0" not in notes
    opened = []
    monkeypatch.setattr(main.webbrowser, "open", lambda url: opened.append(url))
    dpg.get_item_callback("update.modal.more")()
    assert opened == [f"{main.REPOSITORY_URL}/releases"]
    dpg.delete_item("update.modal")


def test_update_dialog_keeps_single_version_layout(dpg_context):
    set_language("en")
    release = updater.UpdateRelease(
        "v1.2.0",
        Version("1.2.0"),
        updater.ReleaseAsset(WINDOWS_ASSET, "https://example/windows"),
        notes="### Features\n- import wizard\n",
    )

    dialog_app()._show_update_confirmation(release)

    assert dpg.get_value("update.modal.header") == "What's new in v1.2.0:"
    assert dpg.get_value("update.modal.notes") == "Features:\n- import wizard"
    assert not dpg.does_item_exist("update.modal.more")
    dpg.delete_item("update.modal")


def test_update_dialog_grows_for_each_extra_release(dpg_context):
    set_language("en")

    def confirmation(release):
        dialog_app()._show_update_confirmation(release)
        height = dpg.get_item_configuration("update.modal")["height"]
        dpg.delete_item("update.modal")
        return height

    def release(tag, version, notes, previous=()):
        return updater.UpdateRelease(
            tag,
            Version(version),
            updater.ReleaseAsset(WINDOWS_ASSET, "https://example/windows"),
            notes=notes,
            previous_notes=previous,
        )

    single = confirmation(
        release("v1.2.0", "1.2.0", "### Features\n- import wizard\n")
    )
    with_two = confirmation(
        release(
            "v1.3.0",
            "1.3.0",
            "## What's Changed\n\n### Features\n- import wizard\n",
            (updater.ReleaseNotes("v1.2.0", "### Bug Fixes\n- align selects\n"),),
        )
    )
    with_three = confirmation(
        release(
            "v1.4.0",
            "1.4.0",
            "## What's Changed\n\n### Features\n- import wizard\n",
            (
                updater.ReleaseNotes("v1.3.0", "### Bug Fixes\n- align selects\n"),
                updater.ReleaseNotes("v1.2.0", "### Features\n- tidy up\n"),
            ),
        )
    )

    assert with_two == single + 258
    assert with_three == with_two + 159


def test_update_dialog_leaves_room_for_changelog_button(dpg_context):
    set_language("en")

    dialog_app()._show_update_confirmation(
        updater.UpdateRelease(
            "v1.3.0",
            Version("1.3.0"),
            updater.ReleaseAsset(WINDOWS_ASSET, "https://example/windows"),
            notes="## What's Changed\n\n### Features\n- import wizard\n",
            previous_notes=(
                updater.ReleaseNotes("v1.2.0", "### Bug Fixes\n- align selects\n"),
                updater.ReleaseNotes("v1.1.0", "### Other Changes\n- tidy up\n"),
            ),
        )
    )

    # Three releases with a hidden section: the changelog button stays
    # inside the dialog without scrolling (previously hidden below the fold).
    assert dpg.does_item_exist("update.modal.more")
    height = dpg.get_item_configuration("update.modal")["height"]
    assert height >= 600
    dpg.delete_item("update.modal")


def test_aggregated_notes_fill_remaining_dialog_space(dpg_context):
    set_language("en")

    def notes_child_height(release):
        dialog_app()._show_update_confirmation(release)
        children = dpg.get_item_children("update.modal.body", 1)
        notes_child = next(
            item for item in children
            if dpg.get_item_info(item)["type"] == "mvAppItemType::mvChildWindow"
        )
        height = dpg.get_item_configuration(notes_child)["height"]
        dpg.delete_item("update.modal")
        return height

    single = notes_child_height(
        updater.UpdateRelease(
            "v1.2.0",
            Version("1.2.0"),
            updater.ReleaseAsset(WINDOWS_ASSET, "https://example/windows"),
            notes="### Features\n- import wizard\n",
        )
    )
    aggregated = notes_child_height(
        updater.UpdateRelease(
            "v1.3.0",
            Version("1.3.0"),
            updater.ReleaseAsset(WINDOWS_ASSET, "https://example/windows"),
            notes="## What's Changed\n\n### Features\n- import wizard\n",
            previous_notes=(updater.ReleaseNotes("v1.2.0", "### Bug Fixes\n- align selects\n"),),
        )
    )

    # Single-release notes keep their compact box; aggregated changelogs
    # fill every leftover pixel so the button never hides below the fold.
    assert single == 150
    assert aggregated == -56


def test_update_dialog_links_single_version_to_its_release(dpg_context, monkeypatch):
    set_language("en")
    release = updater.UpdateRelease(
        "v1.2.0",
        Version("1.2.0"),
        updater.ReleaseAsset(WINDOWS_ASSET, "https://example/windows"),
        notes="### Other Changes\n- tidy up\n",
    )
    opened = []
    monkeypatch.setattr(main.webbrowser, "open", lambda url: opened.append(url))

    dialog_app()._show_update_confirmation(release)

    assert dpg.does_item_exist("update.modal.more")
    dpg.get_item_callback("update.modal.more")()
    assert opened == [f"{main.REPOSITORY_URL}/releases/tag/v1.2.0"]
    dpg.delete_item("update.modal")


def test_download_closes_only_after_browser_opens(monkeypatch):
    app = object.__new__(main.SpectrExcelApp)
    app.has_running_tasks = lambda: False
    monkeypatch.setattr(app, "log", lambda _message: None)
    browser_results = iter((False, True))
    stopped = []
    monkeypatch.setattr(main.webbrowser, "open", lambda _url: next(browser_results))
    monkeypatch.setattr(main.dpg, "stop_dearpygui", lambda: stopped.append(True))
    release = updater.UpdateRelease(
        "v1.1.0",
        Version("1.1.0"),
        updater.ReleaseAsset(WINDOWS_ASSET, "https://example/windows"),
    )

    app._open_update_download(release)
    assert stopped == []

    app._open_update_download(release)
    assert stopped == [True]
