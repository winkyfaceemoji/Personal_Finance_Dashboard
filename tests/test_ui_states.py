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
def server(tmp_path_factory, old_demo_rules):
    data = tmp_path_factory.mktemp("uidata")
    shutil.copytree(REPO / "Test Data" / "RAW", data / "RAW")
    # The demo merchants too, so a merged merchant's card (Venmo: two
    # spellings, money in and out) is drawn and checked like any other
    (data / "SORTED").mkdir()
    for name in ("merchants.csv", "merchant_aliases.csv"):
        shutil.copy(REPO / "Test Data" / "SORTED" / name, data / "SORTED" / name)
    # the old keywords too, so the CONVERT RULES review is drawn
    shutil.copy(old_demo_rules, data / "SORTED" / "rules.csv")
    # and a pattern that matches a demo bakery, so a "Same as …?" line is drawn
    with open(data / "SORTED" / "merchants.csv", "a", encoding="utf-8") as f:
        f.write("Bakeries,Expense,,bakery,\n")
    port = _free_port()
    env = dict(os.environ, FINANCE_DATA_DIR=str(data), FINANCE_PORT=str(port), FINANCE_DEBUG="0",
               FINANCE_LLM_URL="http://127.0.0.1:9")           # no chat model: the same on every machine
    env.pop("FINANCE_EMBED_URL", None)
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
    # Relabel previews the past rows it would change, then CANCEL leaves them
    opened.locator("button", has_text="TRANSFER").click()
    page.wait_for_selector("#merchant-preview-text:has-text('Relabel')")
    _assert_readable(page, "#merchant-preview-text, #merchant-preview button", f"{theme}: relabel preview")
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
def test_a_suggestion_line_stays_readable_and_only_previews(browser, server, theme):
    page = _open(browser, server, theme)
    page.click("#open-label-panel")
    page.wait_for_selector("#label-list .lg-example:has-text('Same as Bakeries?')")
    line = page.locator("#label-list .lg-text", has_text="Same as Bakeries?").first
    line.locator("button", has_text="YES").hover()
    _assert_readable(page, "#label-list .lg-text", f"{theme}: suggestion line")
    line.locator("button", has_text="YES").click()
    page.wait_for_selector("#merchant-preview-text:has-text('Join')")      # a preview, nothing joined yet
    page.click("#merchant-cancel")


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_the_rules_conversion_review_stays_readable_and_previews(browser, server, theme):
    page = _open(browser, server, theme)
    page.click("#open-convert")
    page.wait_for_selector("#label-list .lg-example")                  # one card per keyword
    page.wait_for_selector("#cv-go", state="visible")
    _assert_readable(page, "#label-list .lg-tag, #label-list .lg-example, #label-list label, #cv-go",
                     f"{theme}: conversion review")
    page.click("#cv-go")
    page.wait_for_selector("#merchant-preview-text:has-text('Convert')")
    page.click("#merchant-cancel")


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


# ── Keyboard and screen-reader paths (WCAG 2.1 AA) ────────────────────────────

_ACTIVE_IN = "sel => !!document.activeElement.closest(sel)"


def test_label_panel_is_a_dialog_that_holds_and_returns_focus(browser, server):
    page = _open(browser, server, "light")
    page.focus("#open-label-panel")
    page.keyboard.press("Enter")
    page.wait_for_selector("#label-panel", state="visible")
    page.wait_for_timeout(300)
    panel = page.locator("#label-panel")
    assert panel.get_attribute("role") == "dialog" and panel.get_attribute("aria-modal") == "true"
    title = page.evaluate("document.getElementById(document.getElementById('label-panel')"
                          ".getAttribute('aria-labelledby')).innerText")
    assert title == "LABEL TRANSACTIONS"
    assert page.evaluate(_ACTIVE_IN, "#label-panel")                  # focus moved in
    for _ in range(30):                                                # and never leaves it
        page.keyboard.press("Tab")
        assert page.evaluate(_ACTIVE_IN, "#label-panel")
    page.keyboard.press("Escape")
    page.wait_for_selector("#label-panel", state="hidden")
    assert page.evaluate("document.activeElement.id") == "open-label-panel"   # back where it was


def test_escape_in_an_open_dropdown_closes_only_the_dropdown(browser, server):
    page = _open(browser, server, "light")
    page.click("#settings-menu-btn")
    page.click("#open-merchants-btn")
    page.wait_for_selector("#label-tab label")
    page.locator("#label-tab label", has_text="CONVERT RULES").click()
    page.wait_for_selector("#label-list .dash-dropdown")
    page.locator("#label-list .dash-dropdown").first.click()
    page.wait_for_selector(".dash-dropdown-content[data-state=open]")
    page.keyboard.press("Escape")
    page.wait_for_selector(".dash-dropdown-content[data-state=open]", state="detached")
    page.wait_for_timeout(500)
    assert page.is_visible("#label-panel")                             # still open
    page.keyboard.press("Escape")
    page.wait_for_selector("#label-panel", state="hidden")


def test_a_category_can_be_picked_from_the_keyboard(browser, server):
    page = _open(browser, server, "light")
    page.focus("#category-pick")
    page.keyboard.press("Enter")                                       # opens the list
    page.wait_for_selector(".dash-dropdown-option")
    page.wait_for_timeout(300)
    in_list = "!!document.activeElement.closest('.dash-dropdown-content')"
    if not page.evaluate(in_list):                                     # Dash doesn't always move focus in;
        page.keyboard.press("Tab")                                     # Tab reaches the options then
    assert page.evaluate(in_list)
    name = page.evaluate("document.activeElement.value")
    page.keyboard.press("Enter")                                       # picks the option with focus
    page.wait_for_selector("#category-drilldown .drilldown")
    assert name.upper() in page.inner_text("#category-drilldown")      # the same drilldown as a bar click
    # the picker has a name a screen reader can say
    assert page.evaluate("document.getElementById('category-pick').closest('[role=group]')"
                         ".getAttribute('aria-label')") == "Category"


def test_chat_answers_and_status_are_announced(browser, server):
    page = _open(browser, server, "light")
    page.click("#chat-toggle")
    page.wait_for_selector("#chat-panel.open")
    log = page.locator("#chat-log")
    assert log.get_attribute("role") == "log" and log.get_attribute("aria-live") == "polite"
    assert page.locator("#chat-status").get_attribute("role") == "status"
    assert page.locator("#chat-health").get_attribute("role") == "status"


_UNLABELED_INPUTS = """() => [...document.querySelectorAll('input[type=text], input:not([type])')]
    .filter(i => i.getClientRects().length && !(i.labels && i.labels.length) && !i.getAttribute('aria-label'))
    .map(i => i.id || i.placeholder)"""


def test_every_text_box_has_a_label_not_just_a_placeholder(browser, server):
    page = _open(browser, server, "light")
    page.click("#chat-toggle")
    page.wait_for_selector("#chat-panel.open")
    assert page.evaluate(_UNLABELED_INPUTS) == []
    page.click("#chat-close")
    page.click("#settings-menu-btn")
    page.click("#open-merchants-btn")
    page.wait_for_selector("#label-tab label")
    page.locator("#label-tab label", has_text="TO LABEL").click()
    page.wait_for_selector("#label-list .lg-sub")
    assert page.evaluate(_UNLABELED_INPUTS) == []
    page.locator("#label-tab label", has_text="ALL MERCHANTS").click()
    page.wait_for_selector("#label-list .lg-other")
    page.locator("#label-list details summary", has_text="Change this merchant").first.click()
    assert page.evaluate(_UNLABELED_INPUTS) == []


def test_label_buttons_say_what_they_label(browser, server):
    page = _open(browser, server, "light")
    page.click("#settings-menu-btn")
    page.click("#open-merchants-btn")
    page.wait_for_selector("#label-tab label")
    page.locator("#label-tab label", has_text="TO LABEL").click()
    page.wait_for_selector("#label-list .lg-buttons button")
    page.locator("#label-list .lg-rows summary").first.click()        # one row list open too
    names = page.evaluate("""() => [...document.querySelectorAll('#label-list button')]
        .filter(b => b.getClientRects().length && /^(★ )?(EXPENSE|INCOME|TRANSFER|YES|NO)$/.test(b.innerText.trim()))
        .map(b => b.getAttribute('aria-label') || '')""")
    assert names and all(names), "a label button has only its one word as a name"
    assert len(set(names)) == len(names), "two label buttons have the same name"
    assert any("Same as" in n or "Not " in n for n in names)          # the suggestion's YES / NO too
    # and every merchant's change buttons (RENAME, MERGE, relabel EXPENSE, …)
    page.locator("#label-tab label", has_text="ALL MERCHANTS").click()
    page.wait_for_selector("#label-list .lg-other")
    for s in page.locator("#label-list details summary", has_text="Change this merchant").all()[:3]:
        s.click()
    names = page.evaluate("""() => [...document.querySelectorAll('#label-list details[open] button')]
        .filter(b => b.getClientRects().length).map(b => b.getAttribute('aria-label') || '')""")
    assert names and all(names), "a merchant-change button has only its one word as a name"
    assert len(set(names)) == len(names), "two merchant-change buttons have the same name"


def test_the_page_tells_a_screen_reader_what_each_part_is(browser, server):
    page = _open(browser, server, "light")
    assert page.evaluate("document.documentElement.lang") == "en"
    assert page.locator("main").count() == 1 and page.locator("main .period-bar").count() == 1
    # ‹ › are read out by name, not as symbols
    assert page.get_attribute("#period-prev", "aria-label") == "Previous period"
    assert page.get_attribute("#period-next", "aria-label") == "Next period"
    # pill groups have a name
    for sel, name in (("#period-freq", "Period length"), ("#label-tab", "Panel section"),
                      ("#merchant-sort", "Sort merchants")):
        assert page.evaluate(f"document.querySelector('{sel}').closest('[role=group]').getAttribute('aria-label')") == name
    # the gear says whether its menu is open, the theme buttons which is on
    assert page.get_attribute("#settings-menu-btn", "aria-expanded") == "false"
    page.click("#settings-menu-btn")
    page.wait_for_selector("#settings-menu-panel", state="visible")
    assert page.get_attribute("#settings-menu-btn", "aria-expanded") == "true"
    assert page.get_attribute("#theme-light-btn", "aria-pressed") == "true"
    assert page.get_attribute("#theme-dark-btn", "aria-pressed") == "false"


def test_import_csv_is_one_tab_stop_and_still_opens_the_file_picker(browser, server):
    page = _open(browser, server, "light")
    page.click("#settings-menu-btn")
    page.wait_for_selector("#settings-menu-panel", state="visible")
    page.focus("#import-csv-upload button")
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.id") == "export-csv-btn"
    with page.expect_file_chooser():
        page.click("#import-csv-upload button")


_SMALL_TEXT = """() => {
  const out = new Set();
  const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (walk.nextNode()) {
    const el = walk.currentNode.parentElement, t = walk.currentNode.textContent.trim();
    if (!t || !el || !el.getClientRects().length || el.closest('.sr-only')) continue;
    if (parseFloat(getComputedStyle(el).fontSize) < 12) out.add(t.slice(0, 30));
  }
  return [...out];
}"""


def test_no_text_is_smaller_than_12px(browser, server):
    page = _open(browser, server, "light")
    assert page.evaluate(_SMALL_TEXT) == [], "main page"              # charts' SVG text included
    page.click("#settings-menu-btn")
    page.wait_for_selector("#settings-menu-panel", state="visible")
    assert page.evaluate(_SMALL_TEXT) == [], "settings menu"
    page.click("#open-merchants-btn")
    page.wait_for_selector("#label-tab label")
    for tab in ("TO LABEL", "ALL MERCHANTS", "TRANSFER PAIRS", "CONVERT RULES"):
        page.locator("#label-tab label", has_text=tab).click()
        page.wait_for_timeout(1200)
        for s in page.locator("#label-list details summary").all()[:3]:
            s.click()                                                  # open a few row lists too
        assert page.evaluate(_SMALL_TEXT) == [], tab
        assert "txn" not in page.inner_text("#label-panel"), tab


def test_spellings_say_what_a_spelling_is(browser, server):
    page = _open(browser, server, "light")
    page.click("#settings-menu-btn")
    page.click("#open-merchants-btn")
    page.wait_for_selector("#label-tab label")
    page.locator("#label-tab label", has_text="ALL MERCHANTS").click()
    page.wait_for_selector("#label-list .lg-other")
    # said once, as visible text above the cards (a title shows only on hover)
    assert page.locator("#label-list .lg-legend").inner_text().startswith(
        "Spellings: the bank's text with store numbers")


def test_each_chart_has_a_text_version(browser, server):
    page = _open(browser, server, "light")
    spend = page.inner_text("#period-chart-text")
    assert spend.startswith("Spent per month") and "$" in spend and "median" in spend
    cats = page.inner_text("#category-chart-text")
    assert "%" in cats and "$" in cats
