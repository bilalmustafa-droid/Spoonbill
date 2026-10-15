"""
Spoonbill - Step One, version 2

Changes from version 1, in order of how much they matter. Each is marked
[CHANGE n] at the point in the code where it happens.

[CHANGE 1] MNDWI replaces NDWI as the water test.
    NDWI is green minus near infrared. Algae and floating vegetation reflect
    strongly in NIR, so a green algal fishpond reads as NEGATIVE NDWI, exactly
    like a field. Most of the Deep Bay pond belt is green, not blue-black, so
    the old `was_water = NDWI > 0` gate was rejecting real fishponds and making
    them permanently invisible to the detector.
    MNDWI is green minus SHORTWAVE infrared (B11). Water absorbs SWIR almost
    completely no matter what is growing in it, so MNDWI separates turbid and
    algal ponds from vegetation far more reliably.
    Both indices are still computed, and the run prints how much of the box
    each one calls water, so you can see the difference for yourself.

[CHANGE 2] The background estimate is an annulus, not a filled circle.
    The old 600 m focal mean included the anomaly itself. A large conversion
    occupies enough of its own neighbourhood to drag the local mean toward
    itself and cancel part of its own signal, so big obvious changes were
    suppressed while small parcels kept their full signal. Verified on a
    synthetic field: for a 170 m radius anomaly the filled circle loses about
    8 percent of the signal, the 200 to 600 m annulus loses essentially none.

[CHANGE 3] MIN_OBS raised from 2 to 3.
    A median of two observations is just their mean, so one hazy scene moves it
    directly.

[CHANGE 4] Hectare statistics computed at 10 m, matching the flag resolution.
    The old code flagged at 10 m and counted at 20 m, so the quoted hectare
    figures described a different pixel set from the flags in the picture.

[CHANGE 5] Context pad widened to 0.012 degrees.
    The old 0.008 degrees was about 800 m against a 600 m drift radius, leaving
    no margin, and being specified in degrees it was slightly different in the
    north-south and east-west directions.

[CHANGE 6] Diagnostics on the water gate.
    The run now prints what fraction of the box passes each water test. This is
    the number that tells you whether the gate is the thing limiting detection.

[CHANGE 7] A third cue: MNDWI drop.
    Catches ponds that stop being water without becoming bright, which the
    NDWI-drop and brightness-jump cues between them can miss.

Everything else, including the overall method, the dry-season window pairing
and the output files, is unchanged from version 1.

HOW TO RUN
  python spoonbill_step_one_v2.py
  python spoonbill_step_one_v2.py mai_po_4p3ha__y2025_to_2026
"""

import os
import sys
import time
import traceback

import ee
import requests

# ------------------------------------------------------------------ CONFIG --

HERE = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(HERE, "spoonbill_outputs_v2")

EE_PROJECT = "ee-spoonbill-test"

SITES = {
    "mai_po_4p3ha": (114.0515, 22.4930),
    "san_tin_9ha": (114.0604, 22.5085),
}
SITE_HALF_LON = 0.010
SITE_HALF_LAT = 0.007
CONTEXT_PAD_DEG = 0.012  # [CHANGE 5] was 0.008, too tight against a 600 m filter

INCIDENTS = {
    "y2023_to_2024": {
        "before": ("2022-11-01", "2023-03-15"),
        "after": ("2023-11-01", "2024-03-15"),
    },
    "y2025_to_2026": {
        "before": ("2025-01-15", "2025-03-15"),
        "after": ("2026-01-15", "2026-03-15"),
    },
}

MAX_CLOUD_PCT = 60
MIN_OBS = 3                # [CHANGE 3] was 2
WATER_NDWI = 0.0           # kept, for the diagnostic comparison only
WATER_MNDWI = 0.0          # [CHANGE 1] the gate that actually decides
LOCAL_RADIUS_M = 600       # outer radius of the background annulus
INNER_RADIUS_M = 200       # [CHANGE 2] anomalies inside this are excluded
DRIFT_SCALE_M = 60
METRIC_CRS = "EPSG:32650"
T_NDWI = 0.25
T_MNDWI = 0.25             # [CHANGE 7]
T_BRIGHT = 0.08
OPEN_RADIUS_M = 20
STATS_SCALE_M = 10         # [CHANGE 4] was 20, now matches the flag resolution
PNG_WIDTHS = [1000, 700]

# [CHANGE 1] B11 added for MNDWI. B11 is natively 20 m; Earth Engine resamples
# it onto the 10 m grid automatically, which is fine for a pond-scale index.
BANDS = ["B2", "B3", "B4", "B8", "B11"]

# ---------------------------------------------------------------- SETUP -----


def get_project_id():
    env = os.environ.get("EE_PROJECT", "").strip()
    if env:
        return env
    saved = os.path.join(HERE, "ee_project.txt")
    if os.path.exists(saved):
        with open(saved, "r") as f:
            value = f.read().strip()
        if value:
            return value
    if EE_PROJECT.strip():
        return EE_PROJECT.strip()
    try:
        value = input("Paste your Earth Engine Cloud project id (one time only): ").strip()
    except EOFError:
        value = ""
    if not value:
        sys.exit("No project id given. Get it from console.cloud.google.com.")
    with open(saved, "w") as f:
        f.write(value)
    print("Saved to %s" % saved)
    return value


def init_ee(project):
    try:
        ee.Initialize(project=project)
    except Exception as err:
        print("Earth Engine is not ready yet (%s)." % err)
        print("Starting one-time login in your browser...")
        ee.Authenticate()
        ee.Initialize(project=project)


# ------------------------------------------------------------- PIPELINE -----


def clear_mask(image):
    """Drop no-data, saturated, cloud shadow, cloud and cirrus pixels (SCL)."""
    scl = image.select("SCL")
    bad = (
        scl.eq(0).Or(scl.eq(1)).Or(scl.eq(3))
        .Or(scl.eq(8)).Or(scl.eq(9)).Or(scl.eq(10))
    )
    return image.updateMask(bad.Not())


def composite(aoi, window, label):
    start, end = window
    col = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(aoi)
        .filterDate(start, end)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", MAX_CLOUD_PCT))
        .map(clear_mask)
    )
    n = col.size().getInfo()
    print("  %s: %d scenes between %s and %s" % (label, n, start, end))
    if n == 0:
        raise ValueError(
            "No scenes for %s %s to %s. Widen that window in INCIDENTS."
            % (label, start, end)
        )
    obs = col.select("B3").count()
    img = col.select(BANDS).median().updateMask(obs.gte(MIN_OBS)).clip(aoi)
    return img, n


def indices(img):
    """NDWI, MNDWI and visible brightness.

    NDWI  = (B3 - B8)  / (B3 + B8)   green vs near infrared
    MNDWI = (B3 - B11) / (B3 + B11)  green vs shortwave infrared

    [CHANGE 1] MNDWI is the one to trust for pond water. Algae raises NIR, which
    pushes NDWI negative on a pond that is unmistakably still full of water.
    SWIR is absorbed by the water itself, so MNDWI stays positive.
    """
    ndwi = img.normalizedDifference(["B3", "B8"]).rename("ndwi")
    mndwi = img.normalizedDifference(["B3", "B11"]).rename("mndwi")
    bright = (
        img.select(["B2", "B3", "B4"])
        .reduce(ee.Reducer.mean())
        .divide(10000)
        .rename("bright")
    )
    return ndwi.addBands(mndwi).addBands(bright)


def local_drift(image, inner_m=INNER_RADIUS_M, outer_m=LOCAL_RADIUS_M):
    """Background drift estimated from an ANNULUS around each pixel.

    [CHANGE 2] The old version averaged a filled 600 m circle, which includes
    the anomaly itself. The mean over an annulus is recovered from two circle
    means by area-weighted subtraction:

        annulus = (outer*Ro^2 - inner*Ri^2) / (Ro^2 - Ri^2)

    which for 200 and 600 m is  outer*1.125 - inner*0.125.

    Two focalMean calls rather than a custom kernel, because focalMean on a
    coarse grid is fast and the algebra is exact.
    """
    coarse = image.reproject(crs=METRIC_CRS, scale=DRIFT_SCALE_M)
    outer = coarse.focalMean(outer_m, "circle", "meters")
    inner = coarse.focalMean(inner_m, "circle", "meters")

    ro2 = float(outer_m) ** 2
    ri2 = float(inner_m) ** 2
    denominator = ro2 - ri2

    annulus = outer.multiply(ro2 / denominator).subtract(inner.multiply(ri2 / denominator))
    return annulus.resample("bilinear")


def save_png(image, aoi, path):
    last_error = None
    for width in PNG_WIDTHS:
        began = time.time()
        try:
            url = image.getThumbURL(
                {"region": aoi, "dimensions": width, "format": "png", "crs": "EPSG:4326"}
            )
            response = requests.get(url, timeout=300)
            response.raise_for_status()
            with open(path, "wb") as f:
                f.write(response.content)
            print("    saved in %.0f s" % (time.time() - began))
            return True
        except Exception as err:
            last_error = err
            print("    failed after %.0f s, retrying smaller (%s)"
                  % (time.time() - began, str(err)[:120]))
    print("    could not save %s: %s" % (os.path.basename(path), last_error))
    return False


def make_panel(items, out_path):
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print("  (Pillow not installed, skipping combined panel)")
        return
    tiles = []
    for title, path in items:
        if not os.path.exists(path):
            continue
        im = Image.open(path).convert("RGB")
        w = 900
        h = int(im.height * w / im.width)
        im = im.resize((w, h))
        bar = 34
        canvas = Image.new("RGB", (w, h + bar), (25, 25, 25))
        canvas.paste(im, (0, bar))
        ImageDraw.Draw(canvas).text((10, 10), title, fill=(255, 255, 255))
        tiles.append(canvas)
    if not tiles:
        return
    cw, ch = tiles[0].size
    panel = Image.new("RGB", (cw * 2, ch * 2), (25, 25, 25))
    for i, tile in enumerate(tiles):
        panel.paste(tile, ((i % 2) * cw, (i // 2) * ch))
    panel.save(out_path)


def run_incident(core, context, name, before_window, after_window):
    print("\n=== %s ===" % name)
    before, n_before = composite(context, before_window, "BEFORE")
    after, n_after = composite(context, after_window, "AFTER")
    b = indices(before)
    a = indices(after)

    # Change, then remove the local background drift from it.
    d_ndwi = a.select("ndwi").subtract(b.select("ndwi"))
    d_mndwi = a.select("mndwi").subtract(b.select("mndwi"))
    d_bright = a.select("bright").subtract(b.select("bright"))

    an_ndwi = d_ndwi.subtract(local_drift(d_ndwi)).rename("an_ndwi")
    an_mndwi = d_mndwi.subtract(local_drift(d_mndwi)).rename("an_mndwi")
    an_bright = d_bright.subtract(local_drift(d_bright)).rename("an_bright")

    # [CHANGE 1] MNDWI decides what counted as water. NDWI kept for comparison.
    was_water_mndwi = b.select("mndwi").gt(WATER_MNDWI)
    was_water_ndwi = b.select("ndwi").gt(WATER_NDWI)
    was_water = was_water_mndwi

    lost_water = an_mndwi.lt(-T_MNDWI).And(was_water).unmask(0)        # [CHANGE 7]
    lost_ndwi = an_ndwi.lt(-T_NDWI).And(was_water).unmask(0)
    tarped = an_bright.gt(T_BRIGHT).And(was_water).unmask(0)
    flags = lost_water.Or(lost_ndwi).Or(tarped)
    flags = (
        flags.focalMin(OPEN_RADIUS_M, "square", "meters")
        .focalMax(OPEN_RADIUS_M, "square", "meters")
        .rename("flag")
    )

    print("  Counting flagged hectares (one call, may take a minute)...")
    valid = b.select("mndwi").mask().And(a.select("mndwi").mask())
    area = ee.Image.pixelArea()
    stack = ee.Image.cat([
        area.rename("total"),
        area.updateMask(valid).rename("valid"),
        # [CHANGE 6] the two water gates, so the difference is visible
        area.updateMask(was_water_ndwi).rename("water_ndwi"),
        area.updateMask(was_water_mndwi).rename("water_mndwi"),
        area.updateMask(lost_water).rename("mndwi_drop"),
        area.updateMask(lost_ndwi).rename("ndwi_drop"),
        area.updateMask(tarped).rename("tarp"),
        area.updateMask(flags).rename("flag"),
    ])
    sums = stack.reduceRegion(
        reducer=ee.Reducer.sum(), geometry=core, scale=STATS_SCALE_M, maxPixels=1e9,
    ).getInfo()

    total = sums.get("total") or 1
    def pct(key):
        return 100.0 * (sums.get(key) or 0) / total
    def ha(key):
        return (sums.get(key) or 0) / 10000.0

    print("  Valid coverage in both images: %.0f%%" % pct("valid"))
    print("  WATER GATE, the key diagnostic:")
    print("    pixels called water by NDWI  > 0 : %5.1f%% of box" % pct("water_ndwi"))
    print("    pixels called water by MNDWI > 0 : %5.1f%% of box" % pct("water_mndwi"))
    print("    If MNDWI is much higher, NDWI was rejecting real fishponds.")
    print("  Flagged (MNDWI drop):       %.1f ha" % ha("mndwi_drop"))
    print("  Flagged (NDWI drop):        %.1f ha" % ha("ndwi_drop"))
    print("  Flagged (brightness jump):  %.1f ha" % ha("tarp"))
    print("  Flagged total after despeckle: %.1f ha" % ha("flag"))

    rgb = {"bands": ["B4", "B3", "B2"], "min": 0, "max": 2500, "gamma": 1.3}
    before_rgb = before.visualize(**rgb).unmask(160)
    after_rgb = after.visualize(**rgb).unmask(160)
    anomaly_rgb = an_mndwi.visualize(
        min=-0.5, max=0.5, palette=["red", "white", "green"]
    ).unmask(160)
    water_rgb = was_water.selfMask().visualize(min=0, max=1, palette=["00AAFF"])
    before_water = before_rgb.blend(water_rgb)
    flag_layer = flags.selfMask().visualize(min=0, max=1, palette=["FF00FF"])
    overlay_rgb = after_rgb.blend(flag_layer)

    jobs = [
        ("1_before_truecolor", "BEFORE (true colour)", before_rgb),
        ("2_after_truecolor", "AFTER (true colour)", after_rgb),
        ("3_anomaly", "MNDWI change vs annulus background (red = lost water)", anomaly_rgb),
        ("4_flags", "AFTER with flagged ponds in magenta", overlay_rgb),
        # [CHANGE 6] see the gate, not just its consequences
        ("5_watergate", "BEFORE with MNDWI water gate in blue", before_water),
    ]
    panel_items = []
    for suffix, title, img in jobs:
        path = os.path.join(OUTPUT_DIR, "%s_%s.png" % (name, suffix))
        print("  Saving %s ..." % os.path.basename(path))
        save_png(img, core, path)
        if suffix != "5_watergate":
            panel_items.append((title, path))
    panel_path = os.path.join(OUTPUT_DIR, "%s_panel.png" % name)
    make_panel(panel_items, panel_path)
    print("  Panel: %s" % panel_path)

    return {
        "name": name, "before_scenes": n_before, "after_scenes": n_after,
        "coverage": pct("valid") / 100.0, "ha_flagged": ha("flag"),
        "water_ndwi_pct": pct("water_ndwi"), "water_mndwi_pct": pct("water_mndwi"),
    }


def main():
    started = time.time()
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    project = get_project_id()
    init_ee(project)

    runs = {}
    for site, (lon, lat) in SITES.items():
        for inc in INCIDENTS:
            runs["%s__%s" % (site, inc)] = (site, inc, lon, lat)

    wanted = sys.argv[1:] or list(runs.keys())
    unknown = [w for w in wanted if w not in runs]
    if unknown:
        sys.exit("Unknown run %s. Choose from: %s" % (unknown, list(runs.keys())))

    summary = []
    for name in wanted:
        site, inc, lon, lat = runs[name]
        core = ee.Geometry.Rectangle(
            [lon - SITE_HALF_LON, lat - SITE_HALF_LAT,
             lon + SITE_HALF_LON, lat + SITE_HALF_LAT])
        context = ee.Geometry.Rectangle(
            [lon - SITE_HALF_LON - CONTEXT_PAD_DEG,
             lat - SITE_HALF_LAT - CONTEXT_PAD_DEG,
             lon + SITE_HALF_LON + CONTEXT_PAD_DEG,
             lat + SITE_HALF_LAT + CONTEXT_PAD_DEG])
        windows = INCIDENTS[inc]
        try:
            summary.append(
                run_incident(core, context, name, windows["before"], windows["after"])
            )
        except Exception:
            print("\nThis run failed. Copy the error below to Claude:")
            traceback.print_exc()

    print("\n================ SUMMARY ================")
    for item in summary:
        print(
            "%s: scenes %d -> %d, coverage %.0f%%, water NDWI %.0f%% vs MNDWI %.0f%%, flagged %.1f ha"
            % (item["name"], item["before_scenes"], item["after_scenes"],
               100 * (item["coverage"] or 0), item["water_ndwi_pct"],
               item["water_mndwi_pct"], item["ha_flagged"])
        )
    print("Pictures are in: %s" % OUTPUT_DIR)
    print("Send the *_panel.png and *_5_watergate.png files. Took %.0f seconds."
          % (time.time() - started))


if __name__ == "__main__":
    main()
