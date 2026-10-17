r"""
Cuts real before/after chip pairs out of the optical detector's existing
panel output in spatial/spoonbill_outputs_v2/. Writes nothing into
spoonbill_outputs_v2/ itself -- read-only against that folder, as required.

FALLBACK framing (decided with the project owner after the "preferred"
georeferenced-GeoJSON approach was found to break the frontend's Pydantic
model -- see INTEGRATION_ISSUES.md for the specific validation errors):
these chips are NOT written into any anomaly's chip_before_png/
chip_after_png. They are a separate, clearly-labeled evidence gallery,
never paired with the three synthetic fixture anomalies, so a real photo is
never shown as if it were proof of a specific (synthetic) detection.

Algorithm, per spec:
1. Glob every *_4_flags.png (the detector's own painted-magenta output).
2. Build a magenta mask (R>180, G<110, B>180), label 8-connected blobs,
   discard anything under 400 px as speckle.
3. Rank all surviving blobs across every run by pixel area, keep the
   largest --limit (default 3).
4. For each kept blob: crop a 340x340 window centred on its centre of
   mass from the matching _1_before_truecolor.png and _2_after_truecolor.png
   of the same run, clamped to the panel edges (1000x700).
5. Enhance (bilateral filter -> resize 512x512 Lanczos -> unsharp mask ->
   CLAHE on L -> saturation x1.18), draw the detection outline, burn a
   caption into the pixels, save.
6. Write manifest.json describing each sample (site, incident window,
   approximate area) for the UI's evidence gallery to read.

Approximate centroid/area in the manifest are geodesic (pyproj), derived
from the real blob geometry and the detector's own site rectangle constants
(SITES, SITE_HALF_LON, SITE_HALF_LAT, copied from spatial/ruhan code.py) --
descriptive only, never written into any schema-validated anomaly feature.

Usage:
    python build_demo_chips.py
    python build_demo_chips.py --limit 3 --out data\evidence_chips
"""
import argparse
import json
import re
import sys
from pathlib import Path

import cv2
import numpy as np
from pyproj import Geod
from scipy import ndimage

REPO_ROOT = Path(__file__).resolve().parent
PANELS_DIR = REPO_ROOT / "spatial" / "spoonbill_outputs_v2"

# Copied from spatial/ruhan code.py -- read-only reference, that file is
# never imported or modified.
SITES = {
    "mai_po_4p3ha": (114.0515, 22.4930),
    "san_tin_9ha": (114.0604, 22.5085),
}
SITE_HALF_LON = 0.010
SITE_HALF_LAT = 0.007
SITE_LABELS = {"mai_po_4p3ha": "Mai Po", "san_tin_9ha": "San Tin"}

PANEL_W, PANEL_H = 1000, 700
CROP_SIZE = 340
OUT_SIZE = 512
MIN_BLOB_PX = 400
OUTLINE_BGR = (205, 70, 255)  # (255, 70, 205) in RGB per spec

FLAGS_RE = re.compile(r"^(?P<site>.+?)__(?P<incident>.+)_4_flags\.png$")

GEOD = Geod(ellps="WGS84")


def find_runs():
    """Yields (site, incident, flags_path, before_path, after_path) for
    every detector run found in spoonbill_outputs_v2/."""
    for flags_path in sorted(PANELS_DIR.glob("*_4_flags.png")):
        m = FLAGS_RE.match(flags_path.name)
        if not m:
            continue
        site, incident = m.group("site"), m.group("incident")
        prefix = f"{site}__{incident}"
        before_path = PANELS_DIR / f"{prefix}_1_before_truecolor.png"
        after_path = PANELS_DIR / f"{prefix}_2_after_truecolor.png"
        if before_path.is_file() and after_path.is_file():
            yield site, incident, flags_path, before_path, after_path


def magenta_mask(img_bgr: np.ndarray) -> np.ndarray:
    b = img_bgr[:, :, 0].astype(np.int16)
    g = img_bgr[:, :, 1].astype(np.int16)
    r = img_bgr[:, :, 2].astype(np.int16)
    return (r > 180) & (g < 110) & (b > 180)


def collect_blobs():
    """Returns a list of dicts, one per surviving blob, across every run."""
    blobs = []
    for site, incident, flags_path, before_path, after_path in find_runs():
        flags_img = cv2.imread(str(flags_path))
        if flags_img is None:
            print(f"  WARNING: could not read {flags_path.name}, skipping")
            continue
        mask = magenta_mask(flags_img)
        labeled, n = ndimage.label(mask, structure=np.ones((3, 3)))
        if n == 0:
            continue
        sizes = ndimage.sum(mask, labeled, index=range(1, n + 1))
        centers = ndimage.center_of_mass(mask, labeled, index=range(1, n + 1))
        for label_id, size, center in zip(range(1, n + 1), sizes, centers):
            if size < MIN_BLOB_PX:
                continue
            blobs.append({
                "site": site,
                "incident": incident,
                "before_path": before_path,
                "after_path": after_path,
                "label_id": label_id,
                "labeled_array": labeled,
                "size_px": int(size),
                "center_row": center[0],
                "center_col": center[1],
            })
    return blobs


def crop_window(center_row: float, center_col: float):
    """Returns (row_start, col_start) for a CROP_SIZE window centred on
    (center_row, center_col), clamped to the PANEL_H x PANEL_W panel."""
    row_start = int(round(center_row - CROP_SIZE / 2))
    col_start = int(round(center_col - CROP_SIZE / 2))
    row_start = max(0, min(row_start, PANEL_H - CROP_SIZE))
    col_start = max(0, min(col_start, PANEL_W - CROP_SIZE))
    return row_start, col_start


def enhance(crop_bgr: np.ndarray) -> np.ndarray:
    # 1. Bilateral filter -- removes compression blockiness before anything
    # else touches the image; sharpening a blocky crop first just amplifies
    # the blocks.
    img = cv2.bilateralFilter(crop_bgr, d=7, sigmaColor=40, sigmaSpace=7)

    # 2. Resize to final size with Lanczos.
    img = cv2.resize(img, (OUT_SIZE, OUT_SIZE), interpolation=cv2.INTER_LANCZOS4)

    # 3. Unsharp mask.
    blur = cv2.GaussianBlur(img, (0, 0), sigmaX=1.6)
    img = cv2.addWeighted(img, 1.55, blur, -0.55, 0)

    # 4. CLAHE on L channel of LAB only, so colours do not shift.
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l = clahe.apply(l)
    img = cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)

    # 5. Saturation x1.18.
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[:, :, 1] = np.clip(hsv[:, :, 1] * 1.18, 0, 255)
    img = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
    return img


def outline_mask_512(labeled_array: np.ndarray, label_id: int, row_start: int, col_start: int) -> np.ndarray:
    blob_mask = (labeled_array == label_id)
    crop = blob_mask[row_start:row_start + CROP_SIZE, col_start:col_start + CROP_SIZE].astype(np.uint8)
    mask_512 = cv2.resize(crop, (OUT_SIZE, OUT_SIZE), interpolation=cv2.INTER_NEAREST).astype(bool)
    eroded = ndimage.binary_erosion(mask_512, structure=np.ones((5, 5)))
    return mask_512 & ~eroded


def draw_outline(img: np.ndarray, outline: np.ndarray) -> np.ndarray:
    img = img.copy()
    img[outline] = OUTLINE_BGR
    return img


def burn_caption(img: np.ndarray, line1: str, line2: str) -> np.ndarray:
    bar_h = 46
    out = np.zeros((OUT_SIZE + bar_h, OUT_SIZE, 3), dtype=np.uint8)
    out[:OUT_SIZE] = img
    out[OUT_SIZE:] = (30, 30, 30)
    font = cv2.FONT_HERSHEY_SIMPLEX
    cv2.putText(out, line1, (8, OUT_SIZE + 18), font, 0.42, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.putText(out, line2, (8, OUT_SIZE + 36), font, 0.42, (255, 255, 255), 1, cv2.LINE_AA)
    return out


def approx_centroid_area_ha(site: str, labeled_array: np.ndarray, label_id: int):
    """Descriptive only -- never written into a schema-validated anomaly
    feature. Linear pixel-to-degree mapping over the panel's known bounding
    box (confirmed empirically: 1000x700 px matches the box's exact degree
    aspect ratio, 0.02/0.014, so no distortion correction is needed), area
    computed geodesically rather than by multiplying pixel counts."""
    lon0, lat0 = SITES[site]
    min_lon, max_lon = lon0 - SITE_HALF_LON, lon0 + SITE_HALF_LON
    min_lat, max_lat = lat0 - SITE_HALF_LAT, lat0 + SITE_HALF_LAT

    def to_lonlat(row, col):
        lon = min_lon + (col + 0.5) / PANEL_W * (max_lon - min_lon)
        lat = max_lat - (row + 0.5) / PANEL_H * (max_lat - min_lat)
        return lon, lat

    blob_mask = (labeled_array == label_id).astype(np.uint8)
    contours, _ = cv2.findContours(blob_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None, None, None
    contour = max(contours, key=cv2.contourArea)
    pts = contour.reshape(-1, 2)  # (col, row) pairs
    lons, lats = [], []
    for col, row in pts:
        lon, lat = to_lonlat(row, col)
        lons.append(lon)
        lats.append(lat)
    if len(lons) < 3:
        return None, None, None
    area_m2, _ = GEOD.polygon_area_perimeter(lons, lats)
    area_ha = abs(area_m2) / 10000.0
    cy, cx = ndimage.center_of_mass(blob_mask)
    clon, clat = to_lonlat(cy, cx)
    return round(clon, 5), round(clat, 5), round(area_ha, 3)


def generate(limit: int = 3, out_dir: Path | None = None) -> dict:
    """Core logic, callable directly (e.g. from scripts/run_pipeline.py) as
    well as from the CLI below. Returns the manifest dict; raises if no
    panels are found so a caller can decide how to handle that rather than
    this function calling sys.exit itself."""
    out_dir = Path(out_dir) if out_dir else REPO_ROOT / "data" / "evidence_chips"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Scanning detector panels for magenta-flagged blobs ...")
    blobs = collect_blobs()
    if not blobs:
        raise RuntimeError("No blobs >= 400 px found in any *_4_flags.png in spoonbill_outputs_v2/.")

    blobs.sort(key=lambda b: b["size_px"], reverse=True)
    kept = blobs[:limit]
    print(f"Found {len(blobs)} blob(s) total, keeping the largest {len(kept)}:")
    for b in kept:
        print(f"  {b['site']} / {b['incident']}: {b['size_px']} px")

    manifest = {"generated_from": "spatial/spoonbill_outputs_v2/", "samples": []}

    for rank, b in enumerate(kept, start=1):
        before_img = cv2.imread(str(b["before_path"]))
        after_img = cv2.imread(str(b["after_path"]))
        row_start, col_start = crop_window(b["center_row"], b["center_col"])

        before_crop = before_img[row_start:row_start + CROP_SIZE, col_start:col_start + CROP_SIZE]
        after_crop = after_img[row_start:row_start + CROP_SIZE, col_start:col_start + CROP_SIZE]

        before_enh = enhance(before_crop)
        after_enh = enhance(after_crop)

        outline = outline_mask_512(b["labeled_array"], b["label_id"], row_start, col_start)
        before_enh = draw_outline(before_enh, outline)
        after_enh = draw_outline(after_enh, outline)

        site_label = SITE_LABELS.get(b["site"], b["site"])
        caption2 = "Illustrative Sentinel-2, Deep Bay -- not tied to a specific anomaly"
        before_final = burn_caption(before_enh, f"BEFORE -- {site_label}, {b['incident']}", caption2)
        after_final = burn_caption(after_enh, f"AFTER -- {site_label}, {b['incident']}", caption2)

        before_name = f"evidence_{rank}_before.png"
        after_name = f"evidence_{rank}_after.png"
        cv2.imwrite(str(out_dir / before_name), before_final)
        cv2.imwrite(str(out_dir / after_name), after_final)

        clon, clat, area_ha = approx_centroid_area_ha(b["site"], b["labeled_array"], b["label_id"])
        manifest["samples"].append({
            "rank": rank,
            "site": b["site"],
            "site_label": site_label,
            "incident": b["incident"],
            "blob_size_px": b["size_px"],
            "approx_area_ha": area_ha,
            "approx_centroid_lon": clon,
            "approx_centroid_lat": clat,
            "before_file": before_name,
            "after_file": after_name,
        })
        print(f"  wrote {before_name} / {after_name} (~{area_ha} ha near {site_label})")

    with open(out_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"\nDone. {len(kept)} evidence chip pair(s) written to {out_dir.resolve()}")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--out", default=str(REPO_ROOT / "data" / "evidence_chips"))
    args = parser.parse_args()
    try:
        generate(limit=args.limit, out_dir=Path(args.out))
    except RuntimeError as e:
        print(f"ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
