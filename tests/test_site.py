import json
from html.parser import HTMLParser
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).parents[1]
SITE = ROOT / "site"
PAGES = {
    "en-home": SITE / "index.html",
    "en-docs": SITE / "docs" / "index.html",
    "it-home": SITE / "it" / "index.html",
    "it-docs": SITE / "it" / "docs" / "index.html",
}
WINDOWS_ASSET = "spectrexcel-windows-x86_64.exe"
LINUX_ASSET = "SpectrExcel-x86_64.AppImage.tar.gz"
GITHUB_URL = "https://github.com/albertomosconi/spectrexcel"
RELEASES_URL = f"{GITHUB_URL}/releases/latest"
LICENSE_URL = f"{GITHUB_URL}/blob/main/LICENSE"
DOC_IDS = {
    "install",
    "first-export",
    "kinetics",
    "binding",
    "spectra-family",
    "file-formats",
    "troubleshooting",
}


class DocumentParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.attributes = []
        self.ids = set()

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        self.attributes.append((tag, values))
        if "id" in values:
            self.ids.add(values["id"])


def parse(path):
    parser = DocumentParser()
    parser.feed(path.read_text(encoding="utf-8"))
    return parser


def test_shared_assets_exist_and_icon_matches_application():
    assert (SITE / "assets" / "styles.css").is_file()
    assert (SITE / "assets" / "site.js").is_file()
    assert (SITE / "assets" / "icon.png").read_bytes() == (
        ROOT / "spectrexcel" / "icon.png"
    ).read_bytes()


def test_download_script_contains_exact_latest_release_assets():
    script = (SITE / "assets" / "site.js").read_text(encoding="utf-8")
    assert WINDOWS_ASSET in script
    assert LINUX_ASSET in script
    assert "/releases/latest/download/" in script
    assert "/releases/latest" in script


def test_navigation_links_have_minimum_touch_targets():
    styles = (SITE / "assets" / "styles.css").read_text(encoding="utf-8")
    for selector in (
        ".site-header > a",
        ".nav-disclosure nav a",
        ".docs-nav a",
        ".site-footer a",
    ):
        block = styles.split(f"{selector} {{", 1)[1].split("}", 1)[0]
        assert "display: flex;" in block or "display: inline-flex;" in block
        assert "align-items: center;" in block
        assert "min-height: 44px;" in block
        assert "min-width: 44px;" in block


def test_download_script_enhances_supported_desktops_and_keeps_fallbacks():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is unavailable")

    harness = r"""
const fs = require("fs");
const vm = require("vm");
const testCase = JSON.parse(process.argv[1]);
const download = {
  href: "https://github.com/albertomosconi/spectrexcel/releases/latest",
  textContent: "View latest release",
  dataset: {
    windowsLabel: "Download for Windows",
    linuxLabel: "Download for Linux",
  },
};
const navigator = testCase.failure
  ? Object.defineProperty({}, "userAgentData", { get() { throw new Error("blocked"); } })
  : testCase.navigator;
const context = {
  navigator,
  document: {
    querySelector: () => download,
    querySelectorAll: () => [],
    documentElement: { lang: "en" },
  },
  location: { pathname: "/other/", replace() {} },
  localStorage: { getItem() { return null; }, setItem() {} },
};
let error = null;
try {
  vm.runInNewContext(fs.readFileSync(process.argv[2], "utf8"), context);
} catch (caught) {
  error = caught.message;
}
process.stdout.write(JSON.stringify({ href: download.href, text: download.textContent, error }));
"""
    cases = [
        (
            {"navigator": {"platform": "Win32", "userAgent": "desktop"}},
            f"{RELEASES_URL}/download/{WINDOWS_ASSET}",
            "Download for Windows",
        ),
        (
            {"navigator": {"platform": "Linux x86_64", "userAgent": "desktop"}},
            f"{RELEASES_URL}/download/{LINUX_ASSET}",
            "Download for Linux",
        ),
        (
            {"navigator": {"platform": "Linux armv8l", "userAgent": "Android Mobile"}},
            RELEASES_URL,
            "View latest release",
        ),
        (
            {"navigator": {"platform": "MacIntel", "userAgent": "desktop"}},
            RELEASES_URL,
            "View latest release",
        ),
        ({"failure": True}, RELEASES_URL, "View latest release"),
    ]
    script = SITE / "assets" / "site.js"
    for test_case, expected_href, expected_text in cases:
        result = subprocess.run(
            [node, "-e", harness, json.dumps(test_case), str(script)],
            check=True,
            capture_output=True,
            text=True,
        )
        output = json.loads(result.stdout)
        assert output == {"href": expected_href, "text": expected_text, "error": None}


def test_landing_pages_are_localized_and_progressively_enhanced():
    cases = [
        (PAGES["en-home"], "en", "Turn spectrophotometer files"),
        (PAGES["it-home"], "it", "Trasforma i file dello spettrofotometro"),
    ]
    for path, language, heading in cases:
        text = path.read_text(encoding="utf-8")
        parser = parse(path)
        assert f'<html lang="{language}">' in text
        assert heading in text
        assert "three assays" not in text.lower()
        assert "tre saggi" not in text.lower()
        assert {"features", "privacy", "download-options"} <= parser.ids
        downloads = [attrs for tag, attrs in parser.attributes if "data-download" in attrs]
        assert len(downloads) == 1
        assert downloads[0]["href"].endswith("/releases/latest")
        assert WINDOWS_ASSET in downloads[0]["data-windows-url"]
        assert LINUX_ASSET in downloads[0]["data-linux-url"]


def test_mobile_hero_places_icon_before_copy_and_desktop_restores_copy_left():
    for key in ("en-home", "it-home"):
        text = PAGES[key].read_text(encoding="utf-8")
        hero = text.split('<section class="hero"', 1)[1].split("</section>", 1)[0]
        assert hero.index('<img src="/assets/icon.png"') < hero.index(
            '<div class="hero-copy">'
        )

    styles = (SITE / "assets" / "styles.css").read_text(encoding="utf-8")
    desktop = styles.split("@media (min-width: 48rem) {", 1)[1].split("\n}", 1)[0]
    assert ".hero-copy { grid-column: 1; grid-row: 1; }" in desktop
    assert ".hero > img { grid-column: 2; grid-row: 1; }" in desktop


def test_full_header_navigation_waits_for_wide_desktop():
    styles = (SITE / "assets" / "styles.css").read_text(encoding="utf-8")
    tablet = styles.split("@media (min-width: 48rem) {", 1)[1].split("\n}", 1)[0]
    assert ".nav-disclosure summary" not in tablet
    assert "details.nav-disclosure:not([open]) > nav" not in tablet

    wide = styles.split("@media (min-width: 64rem) {", 1)[1].split("\n}", 1)[0]
    assert ".nav-disclosure summary { display: none; }" in wide
    assert "details.nav-disclosure:not([open]) > nav { display: flex; }" in wide


def test_landing_pages_have_equivalent_required_content():
    cases = [
        {
            "path": PAGES["en-home"],
            "github_label": "View SpectrExcel on GitHub",
            "docs_href": "/docs/",
            "docs_text": "Docs",
            "downloads_text": "Other downloads",
            "privacy": ("no account", "no upload", "open source"),
            "footer_text": ("Documentation", "GitHub", "Latest release", "License"),
        },
        {
            "path": PAGES["it-home"],
            "github_label": "Visita SpectrExcel su GitHub",
            "docs_href": "/it/docs/",
            "docs_text": "Documentazione",
            "downloads_text": "Altri download",
            "privacy": ("nessun account", "nessun caricamento", "open source"),
            "footer_text": ("Documentazione", "GitHub", "Ultima versione", "Licenza"),
        },
    ]
    for case in cases:
        path = case["path"]
        text = path.read_text(encoding="utf-8")
        parser = parse(path)
        anchors = [attrs for tag, attrs in parser.attributes if tag == "a"]
        assert any(
            attrs.get("href") == GITHUB_URL
            and attrs.get("aria-label") == case["github_label"]
            for attrs in anchors
        )
        assert f'href="{case["docs_href"]}"' in text
        assert f">{case['docs_text']}</a>" in text
        assert f'href="#download-options">{case["downloads_text"]}</a>' in text
        for phrase in case["privacy"]:
            assert phrase in text.lower()
        footer = text.split('<footer class="site-footer">', 1)[1].split("</footer>", 1)[0]
        assert case["docs_href"] in footer
        assert GITHUB_URL in footer
        assert RELEASES_URL in footer
        assert LICENSE_URL in footer
        assert 'data-language="en"' in footer
        assert 'data-language="it"' in footer
        for label in case["footer_text"]:
            assert label in footer


def test_pages_use_local_icon_for_favicon_and_content():
    for key in ("en-home", "it-home"):
        path = PAGES[key]
        parser = parse(path)
        icons = [a for tag, a in parser.attributes if tag == "link" and a.get("rel") == "icon"]
        images = [a for tag, a in parser.attributes if tag == "img"]
        assert icons and icons[0]["href"].endswith("/assets/icon.png")
        assert any(image.get("src", "").endswith("/assets/icon.png") for image in images)


def test_landing_pages_use_custom_domain_and_root_relative_routes():
    cases = [
        (
            PAGES["en-home"],
            "https://spectrexcel.albertomosconi.it/",
            "/",
            "/docs/",
        ),
        (
            PAGES["it-home"],
            "https://spectrexcel.albertomosconi.it/it/",
            "/it/",
            "/it/docs/",
        ),
    ]
    for path, canonical_url, home_path, docs_path in cases:
        parser = parse(path)
        links = [attrs for tag, attrs in parser.attributes if tag == "link"]
        anchors = [attrs for tag, attrs in parser.attributes if tag == "a"]
        metadata = {
            attrs["property"]: attrs["content"]
            for tag, attrs in parser.attributes
            if tag == "meta" and "property" in attrs
        }
        scripts = [attrs for tag, attrs in parser.attributes if tag == "script"]
        images = [attrs for tag, attrs in parser.attributes if tag == "img"]

        canonical = [attrs for attrs in links if attrs.get("rel") == "canonical"]
        assert canonical == [{"rel": "canonical", "href": canonical_url}]
        assert metadata["og:url"] == canonical_url
        assert metadata["og:image"] == (
            "https://spectrexcel.albertomosconi.it/assets/icon.png"
        )
        assert any(
            attrs.get("rel") == "icon" and attrs.get("href") == "/assets/icon.png"
            for attrs in links
        )
        assert any(
            attrs.get("rel") == "stylesheet"
            and attrs.get("href") == "/assets/styles.css"
            for attrs in links
        )
        assert any(attrs.get("src") == "/assets/site.js" for attrs in scripts)
        assert images and all(attrs.get("src") == "/assets/icon.png" for attrs in images)

        hrefs = {attrs.get("href") for attrs in anchors}
        assert {home_path, docs_path, "/", "/it/"} <= hrefs
        language_routes = {
            attrs["data-language"]: attrs["href"]
            for attrs in anchors
            if "data-language" in attrs
        }
        assert language_routes == {"en": "/", "it": "/it/"}


def test_docs_have_equivalent_sections_and_platform_requirements():
    github_labels = {
        "en-docs": "View SpectrExcel on GitHub",
        "it-docs": "Visita SpectrExcel su GitHub",
    }
    for key in ("en-docs", "it-docs"):
        path = PAGES[key]
        text = path.read_text(encoding="utf-8")
        parser = parse(path)
        assert DOC_IDS <= parser.ids
        assert WINDOWS_ASSET in text
        assert LINUX_ASSET in text
        assert "X11/GLX" in text
        assert ".KD" in text and ".SD" in text and ".txt" in text
        icons = [
            a
            for tag, a in parser.attributes
            if tag == "link" and a.get("rel") == "icon"
        ]
        images = [a for tag, a in parser.attributes if tag == "img"]
        assert icons and icons[0]["href"].endswith("/assets/icon.png")
        assert any(
            image.get("src", "").endswith("/assets/icon.png") for image in images
        )
        scripts = [a for tag, a in parser.attributes if tag == "script"]
        assert {"src": "/assets/site.js", "defer": None} in scripts
        assert any(
            tag == "a"
            and attrs.get("href") == GITHUB_URL
            and attrs.get("aria-label") == github_labels[key]
            for tag, attrs in parser.attributes
        )


def test_desktop_docs_navigation_is_always_visible_without_changing_mobile_disclosure():
    styles = (SITE / "assets" / "styles.css").read_text(encoding="utf-8")
    desktop = styles.split("@media (min-width: 48rem) {", 1)[1].split("\n}", 1)[0]
    assert ".docs-nav > summary { display: none; }" in desktop
    assert "details.docs-nav:not([open]) > nav { display: block; }" in desktop
    for key in ("en-docs", "it-docs"):
        text = PAGES[key].read_text(encoding="utf-8")
        assert '<details class="docs-nav" open>' in text
        assert "<summary>" in text


def test_internal_links_and_fragments_resolve():
    for path in PAGES.values():
        parser = parse(path)
        for _, attrs in parser.attributes:
            href = attrs.get("href", "")
            if not (href.startswith("/") or href.startswith("#")):
                continue
            route, _, fragment = href.partition("#")
            target = path if not route else SITE / route.lstrip("/")
            target = target / "index.html" if target.is_dir() or route.endswith("/") else target
            assert target.is_file(), f"{path}: broken link {href}"
            if fragment:
                assert fragment in parse(target).ids, f"{path}: broken fragment {href}"


def test_custom_domain_and_pages_workflow():
    assert (SITE / "CNAME").read_text(encoding="utf-8") == (
        "spectrexcel.albertomosconi.it\n"
    )
    workflow = (ROOT / ".github" / "workflows" / "pages.yml").read_text(
        encoding="utf-8"
    )
    assert "site" in workflow
    deploy = workflow.split("jobs:\n  deploy:\n", 1)[1]
    permissions = deploy.split("    permissions:\n", 1)[1].split("    steps:\n", 1)[0]
    assert set(permissions.splitlines()) == {
        "      contents: read",
        "      pages: write",
        "      id-token: write",
    }
    assert "45bfe0192ca1faeb007ade9deae92b16b8254a0d" in workflow
    assert "fc324d3547104276b827a68afc52ff2a11cc49c9" in workflow
    assert "cd2ce8fcbc39b97be8ca5fce6e763baed58fa128" in workflow
