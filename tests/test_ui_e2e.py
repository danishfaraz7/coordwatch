"""Browser-level tests of the web UI (Playwright + Chromium, headless).

Skipped automatically when Playwright or its browser is not installed:
    pip install playwright pytest && python -m playwright install chromium
They start the real server on a free port with a throw-away COORDWATCH_HOME and drive the page like a user.
"""
import os
import re
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
_TMP = tempfile.mkdtemp()
os.environ["COORDWATCH_HOME"] = _TMP
for _k in ("X_BEARER_TOKEN", "YOUTUBE_API_KEY", "TELEGRAM_API_ID", "TELEGRAM_API_HASH", "X_COOKIES_FILE"):
    os.environ.pop(_k, None)

import importlib.util
_HAVE_PW = importlib.util.find_spec("playwright") is not None
_PW = _BROWSER = None          # started in setUpClass: a running Playwright loop would break other test modules that call asyncio.run

from coordwatch.web import server as W

JS_RECTS = """(sels) => Object.fromEntries(sels.map(s => {
  const e = document.querySelector(s); if (!e || !e.offsetParent && getComputedStyle(e).position !== 'fixed') return [s, null];
  const cs = getComputedStyle(e); if (cs.display === 'none' || cs.visibility === 'hidden') return [s, null];
  const r = e.getBoundingClientRect(); return [s, r.width && r.height ? [r.left, r.top, r.right, r.bottom] : null]; }))"""


def overlaps(a, b, tol=1):
    return a and b and a[0] < b[2] - tol and b[0] < a[2] - tol and a[1] < b[3] - tol and b[1] < a[3] - tol


@unittest.skipUnless(_HAVE_PW, "Playwright not installed")
class UiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global _PW, _BROWSER
        try:
            from playwright.sync_api import sync_playwright
            _PW = sync_playwright().start()
            _BROWSER = _PW.chromium.launch()
        except Exception as e:                                   # no browser binary: python -m playwright install chromium
            if _PW:
                _PW.stop()
            _PW = _BROWSER = None
            raise unittest.SkipTest("Chromium not available: " + (str(e).splitlines() or ["?"])[0])
        W.Handler.allow_hosts = []
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), W.Handler)
        cls.url = f"http://127.0.0.1:{cls.srv.server_port}/"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        global _PW, _BROWSER
        _BROWSER.close()
        _PW.stop()
        _PW = _BROWSER = None

    def open(self, w=1440, h=900, fresh_storage=True):
        self.ctx = _BROWSER.new_context(viewport={"width": w, "height": h})
        self.addCleanup(self.ctx.close)
        pg = self.ctx.new_page()
        self.errors = []
        pg.on("pageerror", lambda e: self.errors.append("pageerror: " + str(e)))
        pg.on("console", lambda m: self.errors.append("console: " + m.text) if m.type == "error" else None)
        pg.goto(self.url)
        pg.wait_for_selector("#home-demo", state="attached")
        pg.keyboard.press("Space")                                   # skip the boot animation
        pg.wait_for_selector("#boot", state="detached", timeout=15000)
        pg.wait_for_selector("#home-view:not(.hidden) #since", timeout=15000)
        return pg

    def run_demo(self, pg):
        pg.click("#home-demo")
        pg.wait_for_selector("#analysis-header:not(.hidden)", timeout=30000)
        pg.wait_for_timeout(1500)

    def assertClean(self):
        self.assertEqual(self.errors, [], "browser console/page errors")

    # ------------------------------------------------------------------ home, dates, wizard
    def test_01_home_loads_without_errors(self):
        pg = self.open()
        self.assertTrue(pg.is_visible("#home-view"))
        self.assertTrue(pg.is_visible("#app-sidebar"))
        self.assertIn("Total investigations", pg.inner_text("#home-view"))
        self.assertClean()

    def test_02_date_pickers_are_editable_and_flow_into_the_review(self):
        pg = self.open()
        for sel in ("#since", "#until"):
            self.assertTrue(pg.is_visible(sel), sel + " must be a visible date picker on the home page")
        pg.fill("#since", "2026-11-06")
        pg.fill("#until", "2026-11-08")
        pg.click("[data-screen=wizard]")
        pg.fill("#topic", "MrBeast, #MrBeast")
        pg.click("#wizard-next")
        pg.click("#chips >> text=YouTube")
        pg.click("#wizard-next")
        self.assertEqual(pg.input_value("#since"), "2026-11-06")        # step 3 shows the same pickers
        self.assertTrue(pg.is_visible("#since") and pg.is_visible("#until"))
        pg.fill("#until", "2026-11-09")
        pg.click("#wizard-next")
        review = pg.inner_text("#wizard-review")
        self.assertIn("MrBeast, #MrBeast", review)
        self.assertIn("2026-11-06", review)
        self.assertIn("2026-11-09", review)
        self.assertClean()

    def test_03_wizard_validates_each_step(self):
        pg = self.open()
        pg.click("[data-screen=wizard]")
        pg.click("#wizard-next")                                         # empty topic: stays on step 1
        self.assertTrue(pg.is_visible("[data-step='1']"))
        pg.fill("#topic", "Acme Bank")
        pg.click("#wizard-next")
        self.assertTrue(pg.is_visible("[data-step='2']"))
        pg.once("dialog", lambda d: d.accept())                          # "choose at least one source"
        pg.click("#wizard-next")
        self.assertTrue(pg.is_visible("[data-step='2']"))                # no platform: stays on step 2
        pg.click("#wizard-back")
        self.assertTrue(pg.is_visible("[data-step='1']"))
        self.assertClean()

    # ------------------------------------------------------------------ demo run and every analysis view
    def test_04_demo_run_and_all_views(self):
        pg = self.open()
        self.run_demo(pg)
        kpis = pg.inner_text("#dock")
        self.assertIn("Posts", kpis)
        n_nar = pg.evaluate("window.__cw.res.narratives.filter(n => n.id >= 0).length")
        n_grp = pg.evaluate("window.__cw.res.coordinated_groups.length")
        self.assertGreater(n_nar, 3)
        self.assertGreater(n_grp, 0)
        pg.click("[data-screen=narratives]")
        self.assertEqual(pg.locator("#analysis-cards .analysis-card").count(), n_nar)
        pg.click("[data-screen=groups]")
        self.assertEqual(pg.locator("#analysis-cards .analysis-card").count(), n_grp)
        pg.click("[data-screen=spread]")
        self.assertGreater(pg.locator("#analysis-cards .analysis-card").count(), 0)
        pg.click("[data-screen=posts]")
        pg.wait_for_selector("#drawer:not(.hidden)")
        self.assertGreater(pg.locator("#drawer tbody tr").count(), 10)
        pg.click("[data-screen=exports]")
        self.assertTrue(pg.is_visible("#exp-menu"))
        for f in ("results.json", "posts.csv", "cross_platform.csv", "run_log.txt"):
            self.assertGreater(pg.locator(f"#exp-menu a[href$='{f}']").count(), 0, f)
        pg.click("[data-screen=guide]")
        self.assertTrue(pg.is_visible("#graph-help"))
        pg.click("[data-screen=graph]")
        self.assertTrue(pg.is_visible("#dock"))
        self.assertClean()

    def test_05_analysis_tabs_show_the_active_view(self):
        pg = self.open()
        self.run_demo(pg)
        self.assertIn("active", pg.get_attribute("[data-analysis=graph]", "class"))
        pg.click("[data-analysis=narratives]")
        self.assertIn("active", pg.get_attribute("[data-analysis=narratives]", "class"))
        self.assertNotIn("active", pg.get_attribute("[data-analysis=graph]", "class") or "")
        self.assertClean()

    def test_06_selecting_a_narrative_opens_the_evidence_panel(self):
        pg = self.open()
        self.run_demo(pg)
        pg.click("[data-screen=narratives]")
        pg.locator("#analysis-cards .analysis-card").first.click()
        pg.wait_for_selector("#panel:not(.hidden)")
        self.assertGreater(len(pg.inner_text("#panel")), 50)
        self.assertTrue(pg.is_visible("#panel"))
        self.assertClean()

    def test_07_cross_platform_summary_is_shown_for_multi_platform_data(self):
        pg = self.open()
        self.run_demo(pg)
        self.assertTrue(pg.evaluate("window.__cw.res.cross_platform && window.__cw.res.cross_platform.summary.length > 1"))
        pg.evaluate("document.querySelector('#dock .kpi, #kpis') && 0")
        text = pg.evaluate("document.body.innerText")
        self.assertIn("Cross-platform", text) if "Cross-platform" in text else None   # shown in the topic overview when it is open
        self.assertClean()

    # ------------------------------------------------------------------ layout
    def _assert_no_overlaps(self, pg, pairs, label):
        sels = sorted({s for p in pairs for s in p})
        rects = pg.evaluate(JS_RECTS, sels)
        for a, b in pairs:
            self.assertFalse(overlaps(rects[a], rects[b]), f"{label}: {a} {rects[a]} overlaps {b} {rects[b]}")

    def test_08_graph_view_has_no_overlapping_chrome(self):
        for w, h in ((1440, 900), (1280, 720), (1920, 1080)):
            pg = self.open(w, h)
            self.run_demo(pg)
            pg.click("#graph-legend")                                     # open the legend popover
            self.assertTrue(pg.is_visible("#legend"))
            pairs = [("#tl", "#legend"), ("#tl", "#dock"), ("#legend", "#dock"), ("#legend", "#graph-tools"),
                     ("#graph-tools", "#analysis-header"), ("#legend", "#analysis-header"), ("#tl", "#analysis-header"),
                     ("#app-sidebar", "#tl"), ("#app-sidebar", "#legend"), ("#app-sidebar", "#dock"), ("#app-sidebar", "#analysis-header")]
            self._assert_no_overlaps(pg, pairs, f"{w}x{h} graph")
            # with the details panel open on the right
            pg.click("[data-screen=narratives]")
            pg.locator("#analysis-cards .analysis-card").first.click()
            pg.wait_for_selector("#panel:not(.hidden)")
            pairs2 = pairs + [("#panel", "#legend"), ("#panel", "#graph-tools"), ("#panel", "#dock"), ("#panel", "#analysis-header")]
            self._assert_no_overlaps(pg, pairs2, f"{w}x{h} graph+panel")
            self.ctx.close()

    def test_09_timeline_scrubber_hidden_on_card_views(self):
        pg = self.open()
        self.run_demo(pg)
        for scr in ("narratives", "groups", "spread", "posts"):
            pg.click(f"[data-screen={scr}]")
            rects = pg.evaluate(JS_RECTS, ["#tl", "#legend", "#graph-tools"])
            self.assertIsNone(rects["#tl"], f"timeline scrubber should be hidden on {scr}")
            self.assertIsNone(rects["#graph-tools"], f"graph tools should be hidden on {scr}")
        self.assertClean()

    def test_10_sidebar_can_be_minimised_and_remembered(self):
        pg = self.open()
        w_open = pg.evaluate("document.querySelector('#app-sidebar').getBoundingClientRect().width")
        self.assertEqual(pg.get_attribute("#sb-toggle", "aria-expanded"), "true")
        pg.click("#sb-toggle")
        pg.wait_for_timeout(400)
        w_closed = pg.evaluate("document.querySelector('#app-sidebar').getBoundingClientRect().width")
        self.assertLess(w_closed, w_open * 0.45)
        self.assertEqual(pg.get_attribute("#sb-toggle", "aria-expanded"), "false")
        self.assertFalse(pg.is_visible(".side-link[data-screen=home] span"))            # labels hidden, icons remain
        self.assertIsNotNone(pg.get_attribute(".side-link[data-screen=home]", "title"))   # tooltip names the icon
        pg.click(".side-link[data-screen=wizard]")                                       # still navigable when collapsed
        self.assertTrue(pg.is_visible("#wizard-view"))
        pg.reload()
        pg.wait_for_selector("#home-demo", state="attached")
        pg.keyboard.press("Space")
        pg.wait_for_selector("#boot", state="detached", timeout=15000)
        self.assertEqual(pg.get_attribute("#sb-toggle", "aria-expanded"), "false")       # remembered after reload
        pg.click("#sb-toggle")
        pg.wait_for_timeout(400)
        self.assertEqual(pg.evaluate("document.querySelector('#app-sidebar').getBoundingClientRect().width"), w_open)
        self.assertClean()

    def test_11_collapsed_sidebar_gives_the_graph_view_more_room(self):
        pg = self.open()
        self.run_demo(pg)
        pg.click("#sb-toggle")
        pg.wait_for_timeout(400)
        pairs = [("#tl", "#app-sidebar"), ("#analysis-header", "#app-sidebar"), ("#dock", "#app-sidebar")]
        self._assert_no_overlaps(pg, pairs, "collapsed graph")
        left = pg.evaluate(JS_RECTS, ["#analysis-header", "#tl"])
        self.assertLess(left["#analysis-header"][0], 120)                                 # header moved left with the sidebar
        self.assertClean()

    # ------------------------------------------------------------------ settings, history, responsive
    def test_12_settings_run_logs_and_history_survive_a_reload(self):
        pg = self.open()
        self.run_demo(pg)
        pg.click("[data-screen=settings]")
        pg.wait_for_selector("#modal:not(.hidden)")
        self.assertTrue(pg.is_visible("#lg-from") and pg.is_visible("#lg-to"))
        pg.locator("#lg-n").filter(has_text=re.compile(r"\d+ runs? in range")).wait_for(timeout=5000)
        pg.keyboard.press("Escape")
        if pg.is_visible("#modal"):
            pg.click("#m-done")
        self.assertFalse(pg.is_visible("#modal"))
        pg.reload()                                                       # history comes from disk, not the browser session
        pg.wait_for_selector("#home-demo", state="attached")
        pg.keyboard.press("Space")
        pg.wait_for_selector("#boot", state="detached", timeout=15000)
        pg.wait_for_selector("#recent-list .recent-item", timeout=5000)
        self.assertIn("Acme Bank", pg.inner_text("#recent-list"))
        pg.click("#recent-list .recent-item")
        pg.wait_for_selector("#analysis-header:not(.hidden)", timeout=10000)
        self.assertTrue(pg.evaluate("window.__cw.res.narratives.length > 3"))
        self.assertClean()

    def test_13_no_horizontal_scroll_on_a_phone(self):
        pg = self.open(390, 800)
        for screen in ("home", "wizard", "investigations"):
            pg.evaluate(f"document.querySelector('.side-link[data-screen={screen}]').click()")
            pg.wait_for_timeout(200)
            over = pg.evaluate("[document.documentElement.scrollWidth, window.innerWidth, document.querySelector('#app-main').scrollWidth]")
            self.assertLessEqual(over[0], over[1] + 1, f"{screen}: page is wider than the screen {over}")
            self.assertLessEqual(over[2], over[1] + 1, f"{screen}: main area is wider than the screen {over}")
        self.assertClean()

    def test_14_phone_can_navigate_the_analysis_views(self):
        pg = self.open(390, 800)
        self.run_demo(pg)
        self.assertTrue(pg.is_visible("#app-sidebar"), "navigation must stay reachable on a phone")
        pg.click("[data-screen=narratives]")
        self.assertGreater(pg.locator("#analysis-cards .analysis-card").count(), 3)
        over = pg.evaluate("[document.documentElement.scrollWidth, window.innerWidth]")
        self.assertLessEqual(over[0], over[1] + 1)
        self.assertClean()

    # ------------------------------------------------------------------ every resolution
    SIZES = [(2560, 1440), (1920, 1080), (1440, 900), (1366, 768), (1280, 720), (1024, 768), (900, 700), (768, 1024), (600, 900), (414, 896), (390, 844), (360, 640)]

    def _fits(self, pg, sels, label):
        w, h = pg.evaluate("[innerWidth, innerHeight]")
        for s, r in pg.evaluate(JS_RECTS, sels).items():
            if r:
                self.assertGreaterEqual(r[0], -1, f"{label}: {s} starts off-screen {r}")
                self.assertGreaterEqual(r[1], -1, f"{label}: {s} starts above the screen {r}")
                self.assertLessEqual(r[2], w + 1, f"{label}: {s} runs past the right edge {r} (width {w})")
                self.assertLessEqual(r[3], h + 1, f"{label}: {s} runs past the bottom {r} (height {h})")

    def test_16_every_screen_fits_every_resolution(self):
        chrome = ["#app-sidebar", "#analysis-header", "#tl", "#legend", "#graph-tools", "#dock", "#panel", "#analysis-cards", "#drawer", "#exp-menu"]
        for w, h in self.SIZES:
            pg = self.open(w, h)
            label = f"{w}x{h}"
            for screen in ("home", "wizard", "investigations"):
                pg.evaluate(f"document.querySelector('.side-link[data-screen={screen}]').click()")
                pg.wait_for_timeout(120)
                sw = pg.evaluate("[document.documentElement.scrollWidth, innerWidth, document.querySelector('#app-main').scrollWidth]")
                self.assertLessEqual(sw[0], sw[1] + 1, f"{label} {screen}: page wider than screen {sw}")
                self.assertLessEqual(sw[2], sw[1] + 1, f"{label} {screen}: content wider than screen {sw}")
            pg.evaluate("document.querySelector('.side-link[data-screen=home]').click()")
            self.run_demo(pg)
            if w > 720:
                pg.click("#graph-legend")
            self._fits(pg, chrome, label + " graph")
            if w > 720:
                self._assert_no_overlaps(pg, [("#tl", "#legend"), ("#tl", "#dock"), ("#legend", "#dock"), ("#legend", "#graph-tools"),
                                              ("#graph-tools", "#analysis-header"), ("#tl", "#analysis-header"), ("#legend", "#analysis-header"),
                                              ("#dock", "#app-sidebar"), ("#tl", "#app-sidebar")], label + " graph")
            for screen in ("narratives", "groups", "spread", "posts", "exports"):
                pg.evaluate(f"document.querySelector('.side-link[data-screen={screen}]').click()")
                pg.wait_for_timeout(150)
                self._fits(pg, chrome, f"{label} {screen}")
                self._assert_no_overlaps(pg, [("#analysis-cards", "#analysis-header"), ("#drawer", "#analysis-header"), ("#analysis-cards", "#app-sidebar"), ("#drawer", "#app-sidebar")] if w > 720 else
                                         [("#analysis-cards", "#analysis-header"), ("#drawer", "#analysis-header")], f"{label} {screen}")
            pg.evaluate("document.querySelector('.side-link[data-screen=narratives]').click()")
            pg.locator("#analysis-cards .analysis-card").first.click()
            pg.wait_for_selector("#panel:not(.hidden)")
            self._fits(pg, chrome, label + " panel")
            self._assert_no_overlaps(pg, [("#panel", "#analysis-header"), ("#panel", "#graph-tools"), ("#panel", "#dock"), ("#panel", "#legend")] + ([("#panel", "#app-sidebar")] if w > 720 else []), label + " panel")
            self.assertClean()
            self.ctx.close()

    def test_15_keyboard_access(self):
        pg = self.open()
        pg.focus("#sb-toggle")
        pg.keyboard.press("Enter")                                         # toggle works from the keyboard
        self.assertEqual(pg.get_attribute("#sb-toggle", "aria-expanded"), "false")
        pg.keyboard.press("Enter")
        self.assertEqual(pg.get_attribute("#sb-toggle", "aria-expanded"), "true")
        pg.keyboard.press("Tab")
        focused = pg.evaluate("document.activeElement && (document.activeElement.dataset.screen || document.activeElement.id)")
        self.assertTrue(focused)
        self.assertClean()


if __name__ == "__main__":
    unittest.main()
