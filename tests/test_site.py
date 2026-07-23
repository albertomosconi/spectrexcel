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
