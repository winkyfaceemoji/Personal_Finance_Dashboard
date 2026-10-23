# tests/test_ui_states.py — what controls look like WHILE you use them.
#
# The app's styles and Dash 4's built-in ones both style hover / focus /
# selected states; when they disagree, text can end up the colour of its own
# background (the selected period pill went blank after a click). These tests
# drive a real browser through those states, in both themes, and fail when any
# control's text drops below readable contrast with what's behind it.
#
# Needs Playwright and a Chromium: skipped when either is missing. Point
# CHROMIUM_PATH at a Chromium binary to use one Playwright didn't install.
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

REPO = Path(__file__).resolve().parent.parent
MIN_CONTRAST = 4.5

# Contrast of each matched element's text against the first opaque background
# behind it (WCAG relative luminance)
_CONTRAST_JS = """(sel) => {
  const rgb = s => (s.match(/[\\d.]+/g) || []).map(Number);
  const lum = ([r, g, b]) => { const f = c => { c /= 255; return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4) };
                               return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b) };
  const bgOf = el => { for (let e = el; e; e = e.parentElement) {
      const c = rgb(getComputedStyle(e).backgroundColor); if (c.length >= 3 && (c.length < 4 || c[3] > 0.5)) return c; }
    return [255, 255, 255] };
  return [...document.querySelectorAll(sel)].filter(el => el.offsetParent !== null && el.innerText.trim()).map(el => {
    const a = lum(rgb(getComputedStyle(el).color)), b = lum(bgOf(el));
    return {text: el.innerText.trim(), ratio: (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)} });
}"""


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    data = tmp_path_factory.mktemp("uidata")
    shutil.copytree(REPO / "Test Data" / "RAW", data / "RAW")
    shutil.copy(REPO / "Test Data" / "SORTED" / "rules.csv", data / "rules.csv")
    # The demo merchants too, so a merged merchant's card (Venmo: two
    # spellings, money in and out) is drawn and checked like any other
    (data / "SORTED").mkdir()
    for name in ("merchants.csv", "merchant_aliases.csv"):
        shutil.copy(REPO / "Test Data" / "SORTED" / name, data / "SORTED" / name)
    port = _free_port()
    env = dict(os.environ, FINANCE_DATA_DIR=str(data), FINANCE_RULES_PATH=str(data / "rules.csv"),
               FINANCE_PORT=str(port), FINANCE_DEBUG="0")
    proc = subprocess.Popen([sys.executable, str(REPO / "app.py")], cwd=REPO, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}/"
    try:
        for _ in range(120):
            try:
                urllib.request.urlopen(url, timeout=1)
                break
            except OSError:
                time.sleep(0.5)
        else:
            pytest.fail("the app didn't start")
        yield url
    finally:
        proc.terminate()
        proc.wait(timeout=10)


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        try:
            b = p.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH") or None)
        except Exception as e:                      # no browser installed here
            pytest.skip(f"no Chromium: {str(e).splitlines()[0]}")
        yield b
        b.close()


def _open(browser, server, theme, **ctx):
    page = browser.new_context(**ctx).new_page()
    page.goto(server)
    page.wait_for_selector("#period-freq label")
    page.evaluate(f"localStorage.setItem('theme-store', JSON.stringify('{theme}'))")
    page.reload()
    page.wait_for_selector(f"#app-root.{theme}-theme #period-freq label")
    page.wait_for_timeout(800)
    return page


def _assert_readable(page, selector, state):
    for r in page.evaluate(_CONTRAST_JS, selector):
        assert r["ratio"] >= MIN_CONTRAST, f"{state}: {r['text']!r} is {r['ratio']:.2f}:1 in {selector}"


def _walk_pills(page, group, state):
    """Click every option of a pill group; after each click check the group
    with the pointer still on the clicked pill, then hovering another, then
    with keyboard focus on it."""
    labels = page.locator(f"{group} label")
    for i in range(labels.count()):
        labels.nth(i).click()
        page.wait_for_timeout(250)
        _assert_readable(page, f"{group} label", f"{state}: just clicked #{i}")
        labels.nth((i + 1) % labels.count()).hover()
        _assert_readable(page, f"{group} label", f"{state}: hovering after #{i}")
        page.locator(f"{group} label input").nth(i).focus()
        _assert_readable(page, f"{group} label", f"{state}: focused #{i}")


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_period_pills_stay_readable(browser, server, theme):
    page = _open(browser, server, theme)
    _walk_pills(page, "#period-freq", theme)
    # the selected pill marks itself without colour too
    assert page.evaluate("getComputedStyle(document.querySelector('#period-freq label.selected')).fontWeight") >= "600"


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_labeling_tabs_and_buttons_stay_readable(browser, server, theme):
    page = _open(browser, server, theme)
    page.click("#open-label-panel")
    page.wait_for_selector("#label-tab label")
    _walk_pills(page, "#label-tab", theme)
    page.locator("#label-tab label").nth(0).click()
    page.wait_for_selector("#label-list .btn-secondary")
    button = page.locator("#label-list .btn-secondary").first
    button.hover()
    _assert_readable(page, "#label-list .btn-secondary, #label-panel .btn-primary", f"{theme}: label buttons")


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_all_merchants_view_and_its_sort_stay_readable(browser, server, theme):
    page = _open(browser, server, theme)
    page.click("#settings-menu-btn")
    page.click("#open-merchants-btn")                          # the way in from the menu
    page.wait_for_selector("#label-tab label")
    assert not page.is_visible("#merchant-sort")               # only on All merchants
    page.locator("#label-tab label", has_text="ALL MERCHANTS").click()
    page.wait_for_selector("#label-list .lg-other")            # the folded "Other" line is drawn
    _walk_pills(page, "#merchant-sort", f"{theme} merchant sort")
    _assert_readable(page, "#label-list .lg-name, #label-list .lg-tag, #label-list .lg-example, "
                           "#label-list .hint", f"{theme}: merchant cards")
    # A change previews before it applies: rename the first merchant, see the preview, cancel
    page.locator("#label-list .lg-rows summary", has_text="Change this merchant").first.click()
    opened = page.locator("#label-list details[open]").first
    opened.locator("input").first.fill("Renamed in a test")
    opened.locator("button", has_text="RENAME").click()
    page.wait_for_selector("#merchant-preview-text:has-text('Rename')")
    _assert_readable(page, "#merchant-preview-text, #merchant-preview button, #label-list .lg-rows button",
                     f"{theme}: merchant change preview")
    page.click("#merchant-cancel")
    page.wait_for_selector("#merchant-preview", state="hidden")
    # A merge all the way through: CONFIRM applies it, UNDO takes it back
    second = page.locator("#label-list .lg-name").nth(1).inner_text()
    opened.locator("input").nth(1).fill(second)
    opened.locator("button", has_text="MERGE").click()
    page.wait_for_selector("#merchant-preview-text:has-text('Merge')")
    page.click("#merchant-confirm")
    page.wait_for_selector("#label-status:has-text('Merged')")
    _assert_readable(page, "#label-status, #label-undo-btn", f"{theme}: after a merge")
    page.click("#label-undo-btn")
    page.wait_for_selector("#label-status:has-text('Undone.')")


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_settings_buttons_stay_readable(browser, server, theme):
    page = _open(browser, server, theme)
    page.click("#settings-menu-btn")
    for sel in ("#theme-light-btn", "#theme-dark-btn", "#reload-data-btn", "#open-merchants-btn"):
        page.hover(sel)
        _assert_readable(page, "#settings-menu-panel button", f"{theme}: hovering {sel}")


def test_a_tapped_pill_stays_readable_on_a_phone(browser, server):
    page = _open(browser, server, "light", viewport={"width": 390, "height": 844},
                 is_mobile=True, has_touch=True)
    labels = page.locator("#period-freq label")
    for i in range(labels.count()):
        labels.nth(i).tap()
        page.wait_for_timeout(250)
        _assert_readable(page, "#period-freq label", f"phone: just tapped #{i}")


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_keyboard_focus_is_always_visible(browser, server, theme):
    page = _open(browser, server, theme)
    seen = set()
    for _ in range(12):
        page.keyboard.press("Tab")
        el = page.evaluate("""() => { const e = document.activeElement;
            const target = e.matches('.pills input') ? e.closest('label') : e;
            const cs = getComputedStyle(target);
            return {tag: e.tagName, id: e.id, text: (target.innerText || '').trim().slice(0, 20),
                    outline: cs.outlineStyle, width: parseFloat(cs.outlineWidth)} }""")
        if el["tag"] == "BODY":
            continue
        seen.add(el["id"] or el["text"])
        assert el["outline"] != "none" and el["width"] >= 2, f"{theme}: no focus ring on {el}"
    assert len(seen) >= 4                                  # it did walk the page's controls


def test_open_dropdown_marks_the_current_choice(browser, server):
    page = _open(browser, server, "light")
    page.click("#cashflow-metric")
    page.wait_for_selector(".dash-dropdown-option.selected")
    mark = page.evaluate("getComputedStyle(document.querySelector('.dash-dropdown-option.selected'), '::after').content")
    assert "✓" in mark


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_chat_panel_opens_beside_the_page_and_stays_readable(browser, server, theme):
    page = _open(browser, server, theme, viewport={"width": 1400, "height": 900})
    page.hover("#chat-toggle")
    _assert_readable(page, "#chat-toggle", f"{theme}: hovering CHAT")
    page.click("#chat-toggle")
    page.wait_for_selector("#chat-panel.open")
    page.wait_for_timeout(300)
    box = page.locator("#chat-panel").bounding_box()
    assert box["x"] > 900                                            # on the right, the page beside it
    assert page.locator(".stats-grid").bounding_box()["x"] + page.locator(".stats-grid").bounding_box()["width"] <= box["x"]
    for sel in ("#chat-close", "#chat-send"):
        page.hover(sel)
        _assert_readable(page, "#chat-panel button, #chat-panel .hint, #chat-health", f"{theme}: hovering {sel}")
    page.click("#chat-close")
    page.wait_for_selector("#chat-panel.open", state="detached")
