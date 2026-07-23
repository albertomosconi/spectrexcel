from html.parser import HTMLParser
from pathlib import Path


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
    for selector in (".site-header > a", ".nav-disclosure nav a", ".docs-nav a"):
        block = styles.split(f"{selector} {{", 1)[1].split("}", 1)[0]
        assert "display: flex;" in block or "display: inline-flex;" in block
        assert "align-items: center;" in block
        assert "min-height: 44px;" in block
        assert "min-width: 44px;" in block


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


def test_internal_links_and_fragments_resolve():
    for path in PAGES.values():
        parser = parse(path)
        for _, attrs in parser.attributes:
            href = attrs.get("href", "")
            if not href.startswith("/"):
                continue
            route, _, fragment = href.partition("#")
            target = SITE / route.lstrip("/")
            target = target / "index.html" if target.is_dir() or route.endswith("/") else target
            assert target.is_file(), f"{path}: broken link {href}"
            if fragment:
                assert fragment in parse(target).ids, f"{path}: broken fragment {href}"
