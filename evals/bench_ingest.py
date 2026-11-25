"""Ingest bench: parse-only throughput, per-page shape, peak RSS, degenerates.

A meter, not a test: machine-dependent, run manually before/after perf-sensitive
changes. Fail bar: parse-only median >2x the recorded baseline (real regression,
not noise). Usage: python3 evals/bench_ingest.py [--save baseline.json]
"""
from __future__ import annotations

import glob
import json
import resource
import subprocess
import sys
import time

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))


def rss_mb() -> float:
    # ru_maxrss units are platform-specific; only deltas on one machine matter.
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def bench_parse(files: list[str]) -> dict:
    from qleric import parse  # noqa: E402

    pages, per_doc = 0, []
    t0 = time.perf_counter()
    for p in files:
        t1 = time.perf_counter()
        d = parse(open(p, "rb").read(), "pdf")
        per_doc.append((time.perf_counter() - t1) * 1000)
        pages += len(d.pages)
    dt = time.perf_counter() - t0
    per_doc.sort()
    return {"docs": len(files), "pages": pages, "total_s": round(dt, 3),
            "ms_per_doc_p50": round(per_doc[len(per_doc) // 2], 2),
            "ms_per_doc_max": round(per_doc[-1], 2),
            "peak_rss": round(rss_mb(), 1)}


def bench_cold_import() -> dict:
    p = subprocess.run([sys.executable, "-c", "import qleric.ingest"],
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr[-300:]
    t0 = time.perf_counter()
    subprocess.run([sys.executable, "-c", "import qleric.ingest"],
                   capture_output=True, timeout=60)
    return {"cold_import_s": round(time.perf_counter() - t0, 3)}


def bench_degenerate() -> dict:
    import fitz  # noqa: E402

    from qleric import parse  # noqa: E402

    out = {}
    doc = fitz.open()  # 200 text pages
    for i in range(200):
        pg = doc.new_page()
        pg.insert_text((72, 72), ("Body row content for page %d with enough words to look real here. " % i) * 6,
                       fontsize=11)
    t0 = time.perf_counter()
    d = parse(doc.tobytes(), "pdf")
    out["200_pages"] = {"ms": round((time.perf_counter() - t0) * 1000, 1),
                        "pages": len(d.pages)}
    big = fitz.open()  # poster-size page
    pg = big.new_page(width=2480, height=3508)
    pg.insert_text((100, 100), "Poster title words here for the parser to read.", fontsize=48)
    t0 = time.perf_counter()
    parse(big.tobytes(), "pdf")
    out["poster_a0_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    img = fitz.open()  # image-heavy page
    pg = img.new_page()
    red = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 200, 200))
    for i in range(20):
        pg.insert_image(fitz.Rect(10 + i * 5, 10 + i * 5, 210 + i * 5, 210 + i * 5), pixmap=red)
    pg.insert_text((72, 700), "words here so the parser accepts this page as text", fontsize=12)
    t0 = time.perf_counter()
    d = parse(img.tobytes(), "pdf")
    out["20_images"] = {"ms": round((time.perf_counter() - t0) * 1000, 1),
                        "inventoried": d.meta["ingest"]["images"][0]["total"]}
    out["peak_rss"] = round(rss_mb(), 1)
    return out


def main() -> None:
    files = sorted(glob.glob("samples/*/*.pdf") + glob.glob("samples/*/*/*.pdf"))
    report = {"corpus": bench_parse(files), "cold": bench_cold_import(),
              "degenerate": bench_degenerate()}
    print(json.dumps(report, indent=1))
    if len(sys.argv) > 2 and sys.argv[1] == "--save":
        json.dump(report, open(sys.argv[2], "w"), indent=1, sort_keys=True)
        print("saved", sys.argv[2])


if __name__ == "__main__":
    main()
