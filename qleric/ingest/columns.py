"""Two-column reading order. Word-level; legacy on any doubt."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_COL_TOL = 20.0  # pt gutter tolerance around the page midline
_BAND = 0.05  # top/bottom header-footer band as a fraction of page height
_GUTTER_HALF = 6.0  # pt half-width of the mid strip; catches gutters >=12pt.
                    # Single-col rows tile across center, so this still hits;
                    # short-line layouts fall back on the prose-shape guards.


def _table_bboxes(page) -> list:
    """Table rects for column exclusion. Called only on 2-col-looking pages."""
    try:
        return [tuple(t.bbox) for t in page.find_tables()]
    except Exception:
        return []


def _covered(block, rects) -> bool:
    """True when >=60% of the block rect lies inside table rects."""
    x0, y0, x1, y1 = block[:4]
    area = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    if area <= 0:
        return False
    ov = 0.0
    for r in rects:
        ix = max(0.0, min(x1, r[2]) - max(x0, r[0]))
        iy = max(0.0, min(y1, r[3]) - max(y0, r[1]))
        ov += ix * iy
    return ov >= 0.6 * area


def _lines(words) -> list[str]:
    """Group words into lines: sort by baseline, break on >3pt vertical gaps."""
    out, cur, cy = [], [], None
    for wd in sorted(words, key=lambda wd: (wd[1], wd[0])):
        if cy is None or wd[1] - cy > 3.0:
            if cur:
                out.append(" ".join(w[4] for w in sorted(cur, key=lambda w: w[0])))
            cur, cy = [wd], wd[1]
        else:
            cur.append(wd)
    if cur:
        out.append(" ".join(w[4] for w in sorted(cur, key=lambda w: w[0])))
    return out


def _reorder_page(page, legacy_text: str) -> tuple[str, str]:
    """Two-column reading order. Returns (text, flag); legacy on any doubt.

    Word-level: block segmentation merges side-by-side columns into one
    block, so columns split on word x-centers, not blocks. Single-column
    pages return the legacy string untouched (byte-identical).
    Table-covered words are excluded from the join (they live in tables[]).
    """
    try:
        if getattr(page, "rotation", 0) % 360:
            return legacy_text, "legacy-rotation"
        rect = page.rect
        w, h = rect.width, rect.height
        if not w or not h:
            return legacy_text, "legacy"
        words = [wd for wd in page.get_text("words") if (wd[4] or "").strip()]
        if len(words) < 10:
            return legacy_text, "legacy"
        top, bottom = rect.y0 + _BAND * h, rect.y1 - _BAND * h
        heads, feet, usable = [], [], []
        for wd in words:
            x0, y0, x1, y1 = wd[:4]
            if y1 <= top:
                heads.append(wd)
            elif y0 >= bottom:
                feet.append(wd)
            else:
                usable.append(wd)
        if len(usable) < 10:
            return legacy_text, "legacy"
        mid = rect.x0 + w / 2
        rows: list = []
        for wd in sorted(usable, key=lambda wd: wd[1]):
            if rows and wd[1] - rows[-1][0] <= 3.0:
                rows[-1][1].append(wd)
            else:
                rows.append([wd[1], [wd]])
        if len(rows) < 4:
            return legacy_text, "legacy"
        glo, ghi = mid - _GUTTER_HALF, mid + _GUTTER_HALF
        hit = sum(1 for _, ws in rows
                  if any(wd[0] < ghi and wd[2] > glo for wd in ws))
        if hit > 0.2 * len(rows):
            return legacy_text, "legacy"  # no gutter: one wide column
        if len(rows) < 10 or len(usable) / len(rows) < 5.0:
            return legacy_text, "legacy-form"  # form layout: row-major pairs
        left, right, spanning_ws = [], [], []
        for wd in usable:
            x0, _, x1, _ = wd[:4]
            if x1 <= mid + _COL_TOL and x0 < mid:
                left.append(wd)
            elif x0 >= mid - _COL_TOL and x1 > mid:
                right.append(wd)
            else:
                spanning_ws.append(wd)
        if spanning_ws:
            # Tolerate a few full-width lines (URLs, titles) by y-position:
            # above the columns -> heads, below -> feet, mid-flow -> fallback.
            # Exact-overlap lines also fall back (safer than guessing an edge).
            sp_lines: list = []
            for wd in sorted(spanning_ws, key=lambda wd: wd[1]):
                if sp_lines and wd[1] - sp_lines[-1][0] <= 3.0:
                    sp_lines[-1][1].append(wd)
                else:
                    sp_lines.append([wd[1], [wd]])
            if len(sp_lines) > 3 or not left + right:
                return legacy_text, "legacy-spanning"
            col_top = min(wd[1] for wd in left + right)
            col_bottom = max(wd[3] for wd in left + right)
            for _, ws in sp_lines:
                if max(w[3] for w in ws) <= col_top:
                    heads.extend(ws)
                elif min(w[1] for w in ws) >= col_bottom:
                    feet.extend(ws)
                else:
                    return legacy_text, "legacy-spanning"
        # 10/col pre-table: needs column mass; 4/col post (below): a page that
        # loses most words to table overlap keeps legacy rather than thin columns.
        if len(left) < 10 or len(right) < 10:
            return legacy_text, "legacy"
        rects = _table_bboxes(page)
        lkept = [wd for wd in left if not _covered(wd, rects)]
        rkept = [wd for wd in right if not _covered(wd, rects)]
        if len(lkept) < 4 or len(rkept) < 4:
            return legacy_text, "legacy-tables"
        seq = (_lines(heads) + _lines(lkept) + _lines(rkept) + _lines(feet))
        return "\n".join(seq), "columns-2"
    except Exception as e:
        logger.debug("reorder failed, legacy kept: %s", e)
        return legacy_text, "legacy-error"
