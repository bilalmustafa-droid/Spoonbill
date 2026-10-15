"""Record the UI demo walkthrough: numbered screenshots plus a captioned video.

Drives the running app in headless Microsoft Edge through the pitch path (map click, every brief state,
language switch, filters, demo mode, export). Useful for the README, the submission package and as the
backup demo video. Re-run after real data lands to refresh everything.

Dev-only dependency (not in requirements.txt):  pip install playwright
Uses the installed Edge (channel="msedge"), so no browser download is needed.

Run (app must already be running):
    python track3_app/scripts/capture_demo.py [--url http://localhost:8501]
Output: track3_app/docs/demo/  (NN_name.png, walkthrough.webm, exported PDF/DOCX samples)
"""

from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path

from playwright.sync_api import Frame, Page, sync_playwright

APP_DIR = Path(__file__).resolve().parents[1]
OUT = APP_DIR / "docs" / "demo"
VIEWPORT = {"width": 1440, "height": 900}

CAPTION_JS = """(text) => {
  let el = document.getElementById('demo-caption');
  if (!el) {
    el = document.createElement('div');
    el.id = 'demo-caption';
    el.style.cssText = 'position:fixed;left:50%;bottom:24px;transform:translateX(-50%);z-index:99999;' +
      'background:rgba(20,20,20,.88);color:#fff;font:600 20px/1.4 system-ui,sans-serif;padding:12px 22px;' +
      'border-radius:10px;max-width:80%;text-align:center;box-shadow:0 4px 18px rgba(0,0,0,.35)';
    document.body.appendChild(el);
  }
  el.textContent = text;
  el.style.display = text ? 'block' : 'none';
}"""


class Demo:
    def __init__(self, page: Page):
        self.page = page
        self.shot_no = 0
        self.last_caption = ""
        self.gallery: list[tuple[str, str]] = []   # (filename, caption) for index.html

    # ------------------------------------------------------------------ helpers
    def wait_idle(self, extra_ms: int = 700) -> None:
        """Wait for the Streamlit rerun to finish (status widget gone), then let the browser paint."""
        self.page.wait_for_timeout(300)
        try:
            self.page.wait_for_function(
                "() => !document.querySelector('[data-testid=\"stStatusWidget\"]')", timeout=30_000)
        except Exception:
            pass
        self.page.wait_for_timeout(extra_ms)

    def caption(self, text: str, hold_ms: int = 1800) -> None:
        self.page.evaluate(CAPTION_JS, text)
        self.last_caption = text
        self.page.wait_for_timeout(hold_ms)

    def shot(self, name: str) -> None:
        """Viewport screenshot without the video caption overlay."""
        self.page.evaluate("() => { const c = document.getElementById('demo-caption'); if (c) c.style.visibility='hidden'; }")
        self.shot_no += 1
        filename = f"{self.shot_no:02d}_{name}.png"
        self.page.screenshot(path=str(OUT / filename))
        self.gallery.append((filename, self.last_caption))
        self.page.evaluate("() => { const c = document.getElementById('demo-caption'); if (c) c.style.visibility='visible'; }")

    def scroll_to(self, locator, block: str = "start") -> None:
        locator.first.evaluate(f"el => el.scrollIntoView({{block: '{block}', behavior: 'instant'}})")
        self.page.wait_for_timeout(600)

    def scroll_top(self) -> None:
        self.scroll_to(self.page.locator("h1"), "start")

    def map_frame(self) -> Frame:
        """The map iframe can be briefly re-mounted after a rerun; wait for it and for Leaflet."""
        for _ in range(60):
            frame = next((f for f in self.page.frames if "streamlit_folium" in f.url), None)
            if frame is not None:
                try:
                    if frame.evaluate("() => !!window.map_div"):
                        return frame
                except Exception:
                    pass
            self.page.wait_for_timeout(250)
        raise RuntimeError("map iframe did not appear")

    def tag_polygons(self) -> None:
        """Label each Leaflet path with its anomaly_id so Playwright can hover/click it like a user."""
        self.map_frame().evaluate("""() => {
          window.map_div.eachLayer(l => {
            if (l.feature && l.feature.properties && l.feature.properties.anomaly_id && l._path)
              l._path.setAttribute('data-aid', l.feature.properties.anomaly_id);
          });
        }""")

    def fly_to(self, anomaly_id: str, zoom: int = 17) -> None:
        self.map_frame().evaluate("""([aid, zoom]) => {
          window.map_div.eachLayer(l => {
            if (l.feature && l.feature.properties && l.feature.properties.anomaly_id === aid)
              window.map_div.flyTo(l.getBounds().getCenter(), zoom, {duration: 1.2});
          });
        }""", [anomaly_id, zoom])
        self.page.wait_for_timeout(2500)  # fly animation + satellite tiles

    def fit_all(self) -> None:
        self.map_frame().evaluate("""() => {
          const g = []; window.map_div.eachLayer(l => { if (l.feature && l.feature.properties
            && l.feature.properties.anomaly_id) g.push(l); });
          if (g.length) window.map_div.flyToBounds(L.featureGroup(g).getBounds().pad(0.1), {duration: 1.0});
        }""")
        self.page.wait_for_timeout(2200)

    def polygon(self, anomaly_id: str):
        self.tag_polygons()
        return self.page.frame_locator('iframe[title*="streamlit_folium"]').locator(f'path[data-aid="{anomaly_id}"]')

    def expect_selected(self, anomaly_id: str) -> None:
        self.page.locator("h2", has_text=anomaly_id).first.wait_for(timeout=30_000)
        self.wait_idle()

    def select_from_list(self, anomaly_id: str) -> None:
        self.page.locator('[data-testid="stSelectbox"]').first.click()
        self.page.get_by_role("option", name=re.compile(re.escape(anomaly_id))).click()
        self.expect_selected(anomaly_id)

    def click_text(self, text: str, exact: bool = True) -> None:
        self.page.get_by_text(text, exact=exact).first.click()
        self.wait_idle()

    # ------------------------------------------------------------------ the walkthrough
    def run(self) -> None:
        p = self.page
        p.locator(".sb-disclaimer").first.wait_for(timeout=60_000)
        self.wait_idle(2500)  # base map tiles

        self.caption("Project Spoonbill: satellite screening of Deep Bay wetland change (fixture data)")
        self.shot("landing_overview")

        self.caption("Anomalies are coloured by confidence tier; outline style also encodes the tier")
        self.fly_to("DB-0004", 17)
        self.polygon("DB-0004").hover()
        self.caption("Hover shows ID, tier, area and indicative zoning", 2200)
        self.shot("map_hover_tooltip")

        self.caption("Click a polygon to open its detail panel")
        self.polygon("DB-0004").click()
        self.expect_selected("DB-0004")
        self.shot("map_click_selected")

        self.scroll_to(p.locator("h2", has_text="DB-0004"))
        self.caption("Confidence badge, persistence meter, indicative zoning and the metrics table")
        self.shot("detail_metrics")

        self.scroll_to(p.locator('[data-testid="stImage"]'))
        self.caption("Before and after image chips (synthetic placeholders in fixture mode)")
        self.shot("detail_chips")

        self.scroll_to(p.get_by_text("Monthly time series"))
        self.caption("Monthly radar and NDWI time series against the 2023-2024 baseline")
        self.shot("detail_timeseries")

        self.scroll_to(p.get_by_text("Preliminary brief", exact=True))
        p.get_by_text(re.compile(r"Synthetic Test Document A \(fixture\) · Page 3")).first.click()
        self.wait_idle()
        self.caption("Cited brief: every statutory claim opens to its source, page, section and quote")
        self.shot("brief_cited_with_citation")

        self.scroll_top()
        self.fit_all()
        self.select_from_list("DB-0003")
        self.scroll_to(p.locator(".sb-missing-cite"), "center")
        self.caption("A citation ID that does not resolve is flagged visibly, never dropped or invented")
        self.shot("brief_citation_unavailable")

        self.scroll_top()
        self.select_from_list("DB-0005")
        self.scroll_to(p.locator("h2", has_text="DB-0005"))
        self.caption("Radar-only detection (cloud) with a missing 'before' image placeholder")
        self.shot("detail_radar_only_missing_chip")

        self.scroll_to(p.locator(".sb-panel-amber"))
        self.caption("Abstained brief: a deliberate 'Requires human review' state, not an error")
        self.shot("brief_abstained_human_review")

        self.scroll_top()
        self.select_from_list("DB-0007")
        self.scroll_to(p.locator(".sb-panel-grey"), "center")
        self.caption("Generation error: neutral notice, no stack trace; satellite metrics still shown")
        self.shot("brief_error_notice")

        self.scroll_top()
        self.select_from_list("DB-0008")
        self.scroll_to(p.locator(".sb-panel-grey"), "center")
        self.caption("No brief yet: 'analysis pending'")
        self.shot("brief_pending")

        self.scroll_top()
        self.select_from_list("DB-0005")
        self.click_text("繁體中文")
        self.wait_idle(1500)
        self.caption("Switch to Traditional Chinese: selection, filters and map view are kept")
        self.shot("zh_landing")

        self.scroll_to(p.locator(".sb-panel-amber"))
        self.caption("The same abstained brief in Traditional Chinese")
        self.shot("zh_brief_abstained")

        self.scroll_top()
        self.click_text("English")
        self.click_text("Show low confidence")
        self.wait_idle(1200)
        self.fit_all()
        self.caption("Low-confidence detections are hidden by default; the toggle reveals them (dotted grey)")
        self.shot("filters_show_low")
        self.click_text("Reset filters")

        self.click_text("Demo mode")
        self.wait_idle(1500)
        self.caption("Demo mode: preloads the three strongest detections and a scripted click path")
        self.shot("demo_mode_panel")
        for _ in range(2):
            p.get_by_role("button", name="Next").click()
            self.wait_idle(1200)
        self.caption("Step through the strongest detections with Next")
        self.shot("demo_mode_step3")
        self.click_text("Demo mode")

        self.select_from_list("DB-0004")
        export = p.get_by_text("Export preliminary brief")
        self.scroll_to(export, "center")
        self.caption("One-click export: bilingual PDF and DOCX, generated in memory")
        self.shot("export_buttons")
        for label, ext in (("Download PDF", "pdf"), ("Download DOCX", "docx")):
            with p.expect_download(timeout=60_000) as dl:
                p.get_by_role("button", name=label).click()
            dl.value.save_as(str(OUT / f"sample_export_DB-0004_en.{ext}"))
            self.wait_idle(500)

        self.scroll_to(p.locator(".sb-disclaimer"), "end")
        self.caption("Footer: methodology from the data file and the mandatory disclaimer")
        self.shot("footer_methodology_disclaimer")
        self.caption("")


def render_pdf_preview() -> None:
    try:
        import pypdfium2 as pdfium
    except ImportError:
        return
    pdf_path = OUT / "sample_export_DB-0004_en.pdf"
    if pdf_path.is_file():
        doc = pdfium.PdfDocument(str(pdf_path))
        for i in range(len(doc)):
            doc[i].render(scale=1.4).to_pil().save(OUT / f"sample_export_DB-0004_en_page{i + 1}.png")


def write_gallery(items: list[tuple[str, str]]) -> None:
    """Self-contained local index.html: video first, then every screenshot with its caption."""
    from html import escape
    figures = "\n".join(
        f'<figure><figcaption><b>{i}.</b> {escape(cap)}</figcaption><img src="{name}" alt="{escape(cap)}" '
        f'loading="lazy"></figure>' for i, (name, cap) in enumerate(items, start=1))
    pdf_pages = "".join(f'<img src="{p.name}" alt="Exported PDF page">' for p in sorted(OUT.glob("sample_export_*page*.png")))
    (OUT / "index.html").write_text(f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Spoonbill UI walkthrough</title>
<style>
body{{font:16px/1.5 system-ui,sans-serif;margin:0;background:#f4f5f7;color:#1d1f23}}
main{{max-width:1180px;margin:0 auto;padding:24px 16px 64px}}
h1{{margin:.2em 0}} .note{{background:#7a1f1f;color:#fff;padding:8px 14px;border-radius:6px;display:inline-block}}
figure{{margin:28px 0;background:#fff;border:1px solid #dde1e6;border-radius:8px;overflow:hidden}}
figcaption{{padding:10px 14px;font-weight:500;border-bottom:1px solid #eceef1}}
img,video{{width:100%;display:block}} .pdf{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
.pdf img{{border:1px solid #dde1e6;border-radius:6px;background:#fff}}
</style></head><body><main>
<h1>Project Spoonbill: UI walkthrough</h1>
<p class="note">Recorded on synthetic fixture data, not real satellite results.</p>
<figure><figcaption>Captioned video of the full demo path</figcaption>
<video src="walkthrough.webm" controls muted playsinline></video></figure>
{figures}
<h2>Exported PDF (downloaded through the app's button)</h2><div class="pdf">{pdf_pages}</div>
</main></body></html>
""", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8501")
    args = parser.parse_args()

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    video_dir = OUT / "_video"

    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(viewport=VIEWPORT, record_video_dir=str(video_dir),
                                      record_video_size=VIEWPORT, accept_downloads=True)
        page = context.new_page()
        page.goto(args.url)
        demo = Demo(page)
        try:
            demo.run()
        except Exception:
            page.screenshot(path=str(OUT / "ERROR_state.png"))
            raise
        finally:
            video = page.video
            context.close()
            browser.close()
            if video:
                Path(video.path()).replace(OUT / "walkthrough.webm")
            shutil.rmtree(video_dir, ignore_errors=True)
    render_pdf_preview()
    write_gallery(demo.gallery)
    print(f"OK: wrote {len(list(OUT.glob('[0-9]*.png')))} screenshots and walkthrough.webm to {OUT}")


if __name__ == "__main__":
    main()
