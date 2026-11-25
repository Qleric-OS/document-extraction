"""XObject image inventory. Records placements, never rasterizes."""
from __future__ import annotations

import logging

from .provenance import ImagePlacement, PageImages

logger = logging.getLogger(__name__)

_IMG_CAP = 50  # max inventoried placements per page; total recorded honestly
_ICON_PX = 32


def _page_images(page) -> PageImages:
    """XObject image inventory for one page. Records, never rasterizes.

    One entry per placement (an xref stamped twice = two entries, shared
    xref). `bbox` is the entry's own rect; `bboxes` lists every placement
    rect known for the xref on this page (`bbox` kept for compat).
    """
    try:
        raw = page.get_images(full=True)
    except Exception:
        raw = []
    items, seen = [], set()
    for it in raw:
        try:
            xref = it[0]
            if xref in seen:
                continue  # same XObject listed per use; placements expand below
            seen.add(xref)
            smask, w, h = it[1], it[2], it[3]
            cs = it[5] if len(it) > 5 else ""
            try:
                rects = page.get_image_rects(xref)
                boxes = [tuple([r.x0, r.y0, r.x1, r.y1]) for r in rects]
            except Exception as e:
                logger.debug("image rects failed for xref %s: %s", it[0] if it else "?", e)
                boxes = []
            base = {"width": w, "height": h,
                    "colorspace": cs if isinstance(cs, str) else str(cs),
                    "smask": smask or 0,
                    "icon": (w or 0) < _ICON_PX or (h or 0) < _ICON_PX,
                    "bboxes": tuple(boxes)}
            if boxes:
                for b in boxes:
                    items.append(ImagePlacement(xref, b, **base))
            else:
                items.append(ImagePlacement(xref, None, **base))
        except Exception as e:
            logger.debug("image entry skipped: %s", e)
            continue
    return PageImages(total=len(items), placements=tuple(items[:_IMG_CAP]))
