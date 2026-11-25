"""Ingest circuit: hermetic red pairs for every slice. No CUAD, no network.

Run: python -m unittest tests.test_ingest -v
"""
from __future__ import annotations

import dataclasses
import os
import subprocess
import sys
import unittest

import fitz

from qleric import ingest, parse as root_parse
from qleric import query as root_query
from qleric.documents import Document, Page, Table, parse as doc_parse
from qleric.ingest import INGEST_VERSION, Provenance
from qleric.ingest import api as ingest_api
from qleric.ingest import errors as ingest_errors
from qleric.ingest import scripts as ingest_scripts
from qleric.ingest.errors import EncryptedPDF, NoTextLayer

WORDS_L = "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu "
WORDS_R = "one two three four five six seven eight nine ten eleven twelve "


def two_col_page(pg, y0=72, n=12, lw=None, rw=None, x_mid=306, x0=50, x1=562):
    lw = lw or WORDS_L * 8
    rw = rw or WORDS_R * 8
    y = y0
    for _ in range(n):
        pg.insert_textbox(fitz.Rect(x0, y, x_mid - 7, 700), lw, fontsize=10, align=3)
        pg.insert_textbox(fitz.Rect(x_mid + 7, y, x1, 700), rw, fontsize=10, align=3)
        y += 16
    return y


def solid(w, h, r, g, b):
    p = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, w, h))
    p.set_rect(p.irect, (r, g, b))
    return p


def iou(a, b):
    ix0, iy0 = max(a[0], b[0]), max(a[1], b[1])
    ix1, iy1 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, ix1 - ix0) * max(0, iy1 - iy0)
    aa = (a[2] - a[0]) * (a[3] - a[1])
    bb = (b[2] - b[0]) * (b[3] - b[1])
    return inter / (aa + bb - inter)


def has_tesseract():
    try:
        p = subprocess.run(["tesseract", "--version"], capture_output=True, timeout=10)
        return p.returncode == 0
    except Exception:
        return False


def cjk_font():
    for p in ("/System/Library/Fonts/Supplemental/Songti.ttc",
              "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
              "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"):
        if os.path.exists(p):
            return p
    return None


class TestLegacy(unittest.TestCase):
    def test_constructors(self):
        d = Document(format="TXT", pages=[Page(number=1, text="hello")])
        self.assertEqual(d.meta, {})
        self.assertFalse(d.pages[0].sparse or d.pages[0].ocr)
        self.assertEqual(Table(page_number=1, headers=["a"], rows=[["b"]]).headers, ["a"])

    def test_frozen(self):
        with self.assertRaises(dataclasses.FrozenInstanceError):
            Page(number=1, text="x").sparse = True  # type: ignore[misc]

    def test_single_col_byte_identical(self):
        doc = fitz.open()
        pg = doc.new_page()
        pg.insert_text((72, 72), "A plain single column control line with words here.", fontsize=12)
        d = root_parse(doc.tobytes(), "pdf")
        self.assertEqual(d.meta["ingest"]["reading_order"], ["legacy"])
        self.assertEqual(d.pages[0].text, pg.get_text("text"))


class TestColumns(unittest.TestCase):
    def test_interleaved_two_col(self):
        doc = fitz.open()
        pg = doc.new_page(width=612, height=792)
        left = ["LEFT-WORD row%d extra filler words here" % i for i in range(12)]
        right = ["RIGHT-WORD row%d more filler words there" % i for i in range(12)]
        y = 72
        for a, b in zip(left, right):
            pg.insert_text((50, y), a, fontsize=11)
            pg.insert_text((320, y), b, fontsize=11)
            y += 16
        t = root_parse(doc.tobytes(), "pdf").pages[0].text
        self.assertLess(max(t.index(s) for s in left), min(t.index(s) for s in right))

    def test_justified_gutter_floor(self):
        self.assertEqual(two_col_doc(14).meta["ingest"]["reading_order"], ["columns-2"])
        self.assertEqual(two_col_doc(8).meta["ingest"]["reading_order"], ["legacy"])

    def test_form_layout_row_major(self):
        doc = fitz.open()
        pg = doc.new_page()
        for i, s in enumerate(["Initech", "Invoice #: GB-4532-A", "Issued 03/01/2026",
                               "Bill To: Soylent Co", "Due On 2026-03-01",
                               "Total Amount EUR 6505,98", "Page 1 of 1", "VAT EUR 54.19"]):
            pg.insert_text((50 if i % 2 == 0 else 320, 60 + i * 15), s, fontsize=11)
        d = root_parse(doc.tobytes(), "pdf")
        self.assertIn(d.meta["ingest"]["reading_order"][0], ("legacy", "legacy-form"))

    def test_spanning_top_url(self):
        doc = fitz.open()
        pg = doc.new_page(width=612, height=792)
        pg.insert_text((50, 40), "https://example.com/document/12/section-that-crosses-the-center", fontsize=10)
        two_col_page(pg)
        d = root_parse(doc.tobytes(), "pdf")
        t = d.pages[0].text
        self.assertEqual(d.meta["ingest"]["reading_order"], ["columns-2"])
        self.assertEqual(t.count("example.com"), 1)
        self.assertLess(t.index("example.com"), t.index("alpha"))

    def test_spanning_mid_url(self):
        doc = fitz.open()
        pg = doc.new_page(width=612, height=792)
        y = two_col_page(pg, n=5)
        pg.insert_text((50, y + 4), "https://example.com/document/12/section-that-crosses-the-center", fontsize=10)
        two_col_page(pg, y0=y + 20, n=7)
        d = root_parse(doc.tobytes(), "pdf")
        self.assertEqual(d.meta["ingest"]["reading_order"], ["legacy-spanning"])

    def test_spanning_cap(self):
        doc = fitz.open()
        pg = doc.new_page(width=612, height=792)
        y = 30
        for i in range(5):
            pg.insert_text((50, y), "https://example.com/document/%d/section-that-crosses-the-center" % i, fontsize=10)
            y += 14
        two_col_page(pg, y0=y + 6)
        d = root_parse(doc.tobytes(), "pdf")
        self.assertEqual(d.meta["ingest"]["reading_order"], ["legacy-spanning"])


def two_col_doc(gutter):
    from qleric import parse as _parse
    doc = fitz.open()
    pg = doc.new_page(width=612, height=792)
    mid = 306
    words = "lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod tempor " * 8
    pg.insert_textbox(fitz.Rect(50, 72, mid - gutter / 2, 700), words, fontsize=10, align=3)
    pg.insert_textbox(fitz.Rect(mid + gutter / 2, 72, 562, 700), words, fontsize=10, align=3)
    return _parse(doc.tobytes(), "pdf")


@unittest.skipUnless(has_tesseract(), "tesseract binary absent")
class TestOCR(unittest.TestCase):
    def test_scan_recall(self):
        doc = fitz.open()
        pg = doc.new_page()
        pg.insert_text((72, 72), "The quick brown fox jumps over the lazy dog clause here.", fontsize=14)
        px = doc[0].get_pixmap(matrix=fitz.Matrix(2, 2))
        img = fitz.open()
        q = img.new_page(width=doc[0].rect.width, height=doc[0].rect.height)
        q.insert_image(q.rect, pixmap=px)
        d = root_parse(img.tobytes(), "pdf")
        self.assertEqual(d.meta["ingest"]["reading_order"], ["ocr"])
        self.assertTrue(d.pages[0].ocr)
        self.assertIn("quick brown fox", d.pages[0].text)

    def test_short_scan_accepted(self):
        doc = fitz.open()
        pg = doc.new_page()
        pg.insert_text((72, 72), "Scanned content about governing law Texas provisions here.", fontsize=14)
        px = doc[0].get_pixmap(matrix=fitz.Matrix(2, 2))
        img = fitz.open()
        q = img.new_page(width=doc[0].rect.width, height=doc[0].rect.height)
        q.insert_image(q.rect, pixmap=px)
        d = root_parse(img.tobytes(), "pdf")
        self.assertIn("governing law Texas", d.pages[0].text)

    def test_blank_page_empty(self):
        doc = fitz.open()
        p1 = doc.new_page()
        p1.insert_text((72, 72), "Only real page with enough words to avoid sparse single doc.", fontsize=12)
        doc.new_page()
        d = root_parse(doc.tobytes(), "pdf")
        self.assertIn("ocr-empty", d.meta["ingest"]["reading_order"])

    def test_all_blank_raises(self):
        doc = fitz.open()
        doc.new_page()
        with self.assertRaises(NoTextLayer):
            root_parse(doc.tobytes(), "pdf")


class TestImages(unittest.TestCase):
    def test_known_embeds(self):
        doc = fitz.open()
        pg = doc.new_page()
        red, blue = solid(100, 100, 255, 0, 0), solid(200, 50, 0, 0, 255)
        pg.insert_text((72, 700), "enough words on this page for the parser to accept it fully", fontsize=12)
        r1, r2 = fitz.Rect(50, 50, 150, 150), fitz.Rect(300, 400, 500, 450)
        pg.insert_image(r1, pixmap=red)
        pg.insert_image(r2, pixmap=blue)
        inv = root_parse(doc.tobytes(), "pdf").meta["ingest"]["images"][0]
        self.assertEqual(inv["total"], 2)
        for want in (tuple(r1), tuple(r2)):
            self.assertGreater(max(iou(e["bbox"], want) for e in inv["images"]), 0.95)

    def test_placement_pair_shared_xref(self):
        doc = fitz.open()
        pg = doc.new_page()
        red = solid(100, 100, 255, 0, 0)
        pg.insert_text((72, 700), "enough words on this page for the parser to accept it fully now", fontsize=12)
        r1, r2 = fitz.Rect(50, 50, 150, 150), fitz.Rect(300, 300, 420, 380)
        pg.insert_image(r1, pixmap=red)
        pg.insert_image(r2, pixmap=red)
        inv = root_parse(doc.tobytes(), "pdf").meta["ingest"]["images"][0]
        self.assertEqual(inv["total"], 2)
        self.assertEqual(len({e["xref"] for e in inv["images"]}), 1)
        for want in (tuple(r1), tuple(r2)):
            self.assertGreater(max(iou(e["bbox"], want) for e in inv["images"]), 0.95)

    def test_icon_flag(self):
        doc = fitz.open()
        pg = doc.new_page()
        pg.insert_text((72, 700), "text words here for parser acceptance now", fontsize=12)
        pg.insert_image(fitz.Rect(10, 10, 26, 26), pixmap=solid(16, 16, 0, 255, 0))
        inv = root_parse(doc.tobytes(), "pdf").meta["ingest"]["images"][0]
        self.assertTrue(inv["images"][0]["icon"])

    def test_shared_xref_pages(self):
        doc = fitz.open()
        red = solid(100, 100, 255, 0, 0)
        for _ in range(5):
            pg = doc.new_page()
            pg.insert_text((72, 700), "text words here for parser acceptance now", fontsize=12)
            pg.insert_image(fitz.Rect(20, 20, 120, 120), pixmap=red)
        xs = [p["images"][0]["xref"] for p in root_parse(doc.tobytes(), "pdf").meta["ingest"]["images"]]
        self.assertEqual(len(set(xs)), 1)

    def test_annotate_roundtrip(self):
        from qleric.highlight import annotate
        from qleric.packs import CONTRACT_FIELDS
        raw = open("samples/corpus/con_000.pdf", "rb").read()
        doc = root_parse(raw, "pdf")
        field = {f["name"]: f for f in CONTRACT_FIELDS}["governing_law"]
        v = root_query(doc, [field], None, deep=False)["fields"]["governing_law"]
        ann = annotate(raw, [{"page_number": v["page_number"], "quote": v["verbatim"]}])
        self.assertEqual(root_parse(ann, "pdf").meta["ingest"]["images"],
                         doc.meta["ingest"]["images"])


class TestScripts(unittest.TestCase):
    def test_matrix(self):
        en = " ".join(["the quick brown fox jumps over the lazy dog"] * 12)
        self.assertEqual(ingest_scripts._scripts_of(en, set())[0], ["latin"])
        self.assertEqual(ingest_scripts._scripts_of(" ".join(["le renard brun"] * 12), set())[0], ["latin"])
        self.assertEqual(ingest_scripts._scripts_of(" ".join(["быстрая лиса"] * 12), set())[0], ["cyrillic"])
        self.assertEqual(ingest_scripts._scripts_of("快速棕色狐狸" * 12, set()), (["cjk"], 1.0))
        self.assertEqual(ingest_scripts._scripts_of("hi", set())[0], ["unknown"])
        top, share = ingest_scripts._scripts_of(en + " " + "快速棕色狐狸" * 12, set())
        self.assertEqual(top, ["latin", "cjk"])
        self.assertGreater(share, 0)

    @unittest.skipUnless(cjk_font(), "no CJK font on this machine")
    def test_cjk_pdf(self):
        font = cjk_font()
        doc = fitz.open()
        pg = doc.new_page()
        pg.insert_text((72, 72), "快速的棕色狐狸跳过懒狗" * 20, fontname="song",
                       fontfile=font, fontsize=12)
        pg.insert_text((72, 400), "governing law Texas agreement here", fontsize=12)
        d = root_parse(doc.tobytes(), "pdf")
        self.assertIn("cjk", d.meta["ingest"]["scripts"][0])
        self.assertNotIn(1, d.meta["ingest"]["sparse_pages"])


class TestContract(unittest.TestCase):
    def test_error_hierarchy(self):
        self.assertTrue(issubclass(ingest_errors.NoTextLayer, ValueError))
        self.assertTrue(issubclass(EncryptedPDF, ingest_errors.IngestError))

    def test_old_paths(self):
        self.assertIs(root_parse, doc_parse)
        self.assertIs(root_parse, ingest_api.parse)
        self.assertIs(Document, ingest.types.Document)

    def test_meta_shape(self):
        d = root_parse(open("samples/corpus/con_000.pdf", "rb").read(), "pdf")
        self.assertEqual(list(d.meta["ingest"].keys()),
                         ["parser", "ocr_pages", "ocr_attempted", "ocr_rotated",
                          "ocr_engine", "ocr_ms", "sparse_pages", "reading_order",
                          "images", "scripts", "cjk_share", "version"])
        self.assertEqual(d.meta["ingest"]["version"], INGEST_VERSION)

    def test_provenance_shape(self):
        from qleric.ingest import ImagePlacement, PageImages
        prov = Provenance(
            reading_order=("legacy",), ocr_pages=(), ocr_attempted=(),
            ocr_rotated=(), ocr_engine="none", ocr_ms=0, sparse_pages=(),
            images=(PageImages(total=1, placements=(
                ImagePlacement(xref=7, bbox=(1.0, 2.0, 3.0, 4.0),
                               bboxes=((1.0, 2.0, 3.0, 4.0),),
                               width=16, height=16, colorspace="ICCBased",
                               smask=0, icon=True),)),),
            scripts=(["latin"],), cjk_share=(0.0,))
        self.assertEqual(prov.as_dict(),
                         {"parser": "pymupdf-text", "ocr_pages": [], "ocr_attempted": [],
                          "ocr_rotated": [], "ocr_engine": "none", "ocr_ms": 0,
                          "sparse_pages": [], "reading_order": ["legacy"],
                          "images": [{"total": 1, "images": [
                              {"xref": 7, "width": 16, "height": 16,
                               "colorspace": "ICCBased", "smask": 0, "icon": True,
                               "bboxes": [[1.0, 2.0, 3.0, 4.0]],
                               "bbox": [1.0, 2.0, 3.0, 4.0]}]}],
                          "scripts": [["latin"]], "cjk_share": [0.0], "version": 1})

    def test_import_closure(self):
        code = ("import sys; import qleric.ingest; "
                "mods = sorted(m for m in sys.modules if m.startswith(('qleric','rapidfuzz','fitz','docx','flask'))); "
                "print(','.join(mods))")
        p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                           cwd=".", timeout=60)
        self.assertEqual(p.stdout.strip(), "qleric,qleric.ingest,qleric.ingest.errors,qleric.ingest.provenance,qleric.ingest.types",
                         p.stderr[-500:])


if __name__ == "__main__":
    unittest.main()
