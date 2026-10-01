"""Rendered-site checks: uv sync --group browser, then run this module with pytest.

Install Chromium first with: uv run python -m playwright install chromium.
"""

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest

playwright = pytest.importorskip("playwright.sync_api")


@pytest.fixture(scope="module")
def site_url():
    handler = partial(
        SimpleHTTPRequestHandler, directory=str(Path(__file__).parents[1] / "site")
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()
    thread.join()


@pytest.fixture(scope="module")
def browser():
    with playwright.sync_playwright() as manager:
        instance = manager.chromium.launch()
        yield instance
        instance.close()


@pytest.mark.parametrize("route", ["/", "/it/"])
def test_mobile_download_is_visible_before_product_image(browser, site_url, route):
    page = browser.new_page(viewport={"width": 375, "height": 667})
    try:
        page.goto(site_url + route)
        page.evaluate("document.fonts.ready")
        download = page.locator("[data-download]").bounding_box()
        image = page.locator(".hero img").bounding_box()
        copy = page.locator(".hero-copy").bounding_box()
        assert download["y"] + download["height"] <= 667
        assert image["y"] > copy["y"] + copy["height"]
    finally:
        page.close()


@pytest.mark.parametrize("route", ["/", "/it/", "/docs/", "/it/docs/"])
@pytest.mark.parametrize("width", [320, 375, 768, 1024, 1440])
def test_pages_fit_viewport_without_horizontal_scroll(browser, site_url, route, width):
    page = browser.new_page(viewport={"width": width, "height": 900})
    try:
        page.goto(site_url + route)
        page.evaluate("document.fonts.ready")
        assert page.evaluate(
            "document.documentElement.scrollWidth <= window.innerWidth"
        )
    finally:
        page.close()


def test_system_theme_changes_surface_and_keeps_text_readable(browser, site_url):
    page = browser.new_page()
    surfaces = []
    try:
        for theme in ("light", "dark"):
            page.emulate_media(color_scheme=theme)
            page.goto(site_url)
            colors = page.evaluate("""() => {
                const body = getComputedStyle(document.body);
                const button = getComputedStyle(document.querySelector('[data-download]'));
                return [body.backgroundColor, body.color, button.backgroundColor, button.color];
            }""")
            surfaces.append(colors[0])
            for background, foreground in (colors[:2], colors[2:]):
                def luminance(color):
                    channels = [int(v) / 255 for v in color[4:-1].split(",")]
                    linear = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in channels]
                    return sum(v * w for v, w in zip(linear, (.2126, .7152, .0722)))

                values = sorted([luminance(background), luminance(foreground)])
                assert (values[1] + .05) / (values[0] + .05) >= 4.5
        assert surfaces[0] != surfaces[1]
    finally:
        page.close()


@pytest.mark.parametrize("route", ["/", "/it/"])
def test_mobile_menu_is_keyboard_accessible(browser, site_url, route):
    page = browser.new_page(viewport={"width": 375, "height": 667})
    try:
        page.goto(site_url + route)
        summary = page.locator(".nav-disclosure summary")
        summary.focus()
        page.keyboard.press("Enter")
        assert page.locator(".nav-disclosure").get_attribute("open") is not None
        page.keyboard.press("Tab")
        assert page.locator(".nav-disclosure nav a").first.evaluate(
            "element => element === document.activeElement"
        )
        assert page.locator(".nav-disclosure nav a").first.evaluate(
            "element => getComputedStyle(element).outlineStyle !== 'none'"
        )
    finally:
        page.close()


@pytest.mark.parametrize("route", ["/", "/it/"])
def test_desktop_navigation_and_button_labels_stay_on_one_line(browser, site_url, route):
    page = browser.new_page(viewport={"width": 1024, "height": 768})
    try:
        page.goto(site_url + route)
        page.evaluate("document.fonts.ready")
        assert page.locator(".nav-disclosure nav a").first.evaluate(
            "element => element.checkVisibility()"
        )
        positions = page.locator(".nav-disclosure nav a").evaluate_all(
            "elements => elements.map(element => element.getBoundingClientRect().top)"
        )
        assert len(set(positions)) == 1
        for button in page.locator(".button").all():
            assert button.evaluate("""element => {
                const range = document.createRange();
                range.selectNodeContents(element);
                return range.getClientRects().length === 1;
            }""")
    finally:
        page.close()


@pytest.mark.parametrize("route", ["/docs/", "/it/docs/"])
@pytest.mark.parametrize("width", [375, 768, 1024])
def test_docs_navigation_disclosure_only_collapses_on_mobile(browser, site_url, route, width):
    page = browser.new_page(viewport={"width": width, "height": 768})
    try:
        page.goto(site_url + route)
        summary = page.locator(".docs-nav > summary")
        links = page.locator(".docs-nav nav a")
        assert page.locator(".docs-nav").get_attribute("open") is not None
        assert links.first.is_visible()
        assert summary.is_visible() == (width < 768)
        page.locator(".docs-nav").evaluate("element => element.open = false")
        assert links.first.evaluate(
            "element => element.checkVisibility()"
        ) == (width >= 768)
        if width < 768:
            summary.focus()
            page.keyboard.press("Enter")
            assert links.first.is_visible()
    finally:
        page.close()


@pytest.mark.parametrize("route", ["/", "/it/", "/docs/", "/it/docs/"])
@pytest.mark.parametrize("width", [375, 768, 1024])
def test_navigation_links_have_minimum_touch_targets(browser, site_url, route, width):
    page = browser.new_page(viewport={"width": width, "height": 900})
    try:
        page.goto(site_url + route)
        page.evaluate("document.fonts.ready")
        page.locator(".nav-disclosure").evaluate("element => element.open = true")
        for selector in (
            ".site-header > a", ".nav-disclosure nav a", ".site-footer a",
            *([".docs-nav a"] if "docs" in route else []),
        ):
            links = page.locator(selector).all()
            assert links, selector
            for link in links:
                assert link.is_visible()
                bounds = link.bounding_box()
                assert bounds["width"] >= 44, (selector, bounds)
                assert bounds["height"] >= 44, (selector, bounds)
    finally:
        page.close()


@pytest.mark.parametrize("route", ["/", "/it/"])
@pytest.mark.parametrize("width", [768, 1024, 1440])
def test_desktop_hero_keeps_copy_left_of_screenshot(browser, site_url, route, width):
    page = browser.new_page(viewport={"width": width, "height": 900})
    try:
        page.goto(site_url + route)
        page.evaluate("document.fonts.ready")
        copy = page.locator(".hero-copy").bounding_box()
        image = page.locator(".product-image").bounding_box()
        assert copy["x"] + copy["width"] <= image["x"]
        assert max(copy["y"], image["y"]) < min(
            copy["y"] + copy["height"], image["y"] + image["height"]
        )
    finally:
        page.close()


@pytest.mark.parametrize("route", ["/", "/it/", "/docs/", "/it/docs/"])
@pytest.mark.parametrize("width", [375, 768, 1023, 1024, 1440])
def test_full_header_navigation_waits_for_wide_desktop(browser, site_url, route, width):
    page = browser.new_page(viewport={"width": width, "height": 900})
    try:
        page.goto(site_url + route)
        page.locator(".nav-disclosure").evaluate("element => element.open = false")
        summary = page.locator(".nav-disclosure summary")
        link = page.locator(".nav-disclosure nav a").first
        assert summary.is_visible() == (width < 1024)
        assert link.evaluate("element => element.checkVisibility()") == (width >= 1024)
        if width < 1024:
            summary.click()
            assert link.is_visible()
    finally:
        page.close()


@pytest.mark.parametrize("route,docs_route", [("/", "/docs/"), ("/it/", "/it/docs/")])
def test_landing_copy_uses_width_while_docs_keep_readable_lines(browser, site_url, route, docs_route):
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    try:
        page.goto(site_url + docs_route)
        page.evaluate("document.fonts.ready")
        docs = page.locator(".docs-layout article p").first.bounding_box()
        article = page.locator(".docs-layout article").bounding_box()
        assert docs["width"] < article["width"]

        page.goto(site_url + route)
        page.evaluate("document.fonts.ready")
        landing = page.locator("#privacy p").first.bounding_box()
        assert landing["width"] > docs["width"]
        assert page.locator("#download-options").evaluate("""element => {
            const style = getComputedStyle(element);
            const fontSize = parseFloat(getComputedStyle(document.documentElement).fontSize);
            return parseFloat(style.paddingTop) >= 3 * fontSize
                && parseFloat(style.paddingBottom) >= 3 * fontSize;
        }""")
    finally:
        page.close()


@pytest.mark.parametrize("route", ["/", "/it/"])
def test_enlarged_text_keeps_download_labels_inside_mobile_buttons(browser, site_url, route):
    page = browser.new_page(viewport={"width": 320, "height": 900})
    try:
        page.goto(site_url + route)
        page.evaluate("document.fonts.ready")
        page.evaluate("document.documentElement.style.fontSize = '200%'")
        brand = page.locator(".site-header > a span").bounding_box()
        menu = page.locator(".nav-disclosure summary").bounding_box()
        assert (
            menu["y"] >= brand["y"] + brand["height"]
            or menu["x"] >= brand["x"] + brand["width"]
        )
        assert page.evaluate(
            "document.documentElement.scrollWidth <= window.innerWidth"
        )
        for button in page.locator(".button").all():
            assert button.evaluate("element => element.scrollWidth <= element.clientWidth")
    finally:
        page.close()


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_notebook_grid_repeats_in_squares_while_panels_stay_solid(browser, site_url, theme):
    page = browser.new_page(color_scheme=theme)
    try:
        page.goto(site_url)
        styles = page.evaluate("""() => {
            const body = getComputedStyle(document.body);
            const panel = getComputedStyle(document.querySelector('#privacy'));
            return {
                grid: body.backgroundImage,
                size: body.backgroundSize,
                panelImage: panel.backgroundImage,
                panelColor: panel.backgroundColor,
            };
        }""")
        assert styles["grid"].count("linear-gradient(") == 2
        for layer in styles["size"].split(","):
            width, height = layer.split()
            assert width == height
            assert float(width.removesuffix("px")) > 0
        assert styles["panelImage"] == "none"
        assert styles["panelColor"].startswith("rgb(")
    finally:
        page.close()
