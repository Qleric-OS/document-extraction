"""Stateless extraction API. Keyless core; LLM fields need API_KEY env on the server."""
from __future__ import annotations

import logging
import os

from flask import Flask, jsonify, request
from werkzeug.utils import secure_filename

from qleric import annotate, parse, query
from qleric.packs import CONTRACT_FIELDS, INVOICE_FIELDS, PII_FIELDS, RESUME_FIELDS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)
ALLOWED = {"pdf", "docx"}
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 413 on overflow

PACKS = {"invoice": INVOICE_FIELDS, "resume": RESUME_FIELDS, "pii": PII_FIELDS,
         "contract": CONTRACT_FIELDS}


@app.get("/health")
def health():
    return jsonify({"status": "healthy", "packs": sorted(PACKS)})


@app.post("/analyze")
def analyze():
    if "file" not in request.files:
        return jsonify({"error": "No file provided."}), 400
    file = request.files["file"]
    if not file.filename or "." not in file.filename:
        return jsonify({"error": "No file selected."}), 400
    ext = file.filename.rsplit(".", 1)[1].lower()
    if ext not in ALLOWED:
        return jsonify({"error": "Invalid file type. Only PDF and DOCX are supported."}), 400
    pack = request.form.get("pack", "invoice")
    if pack not in PACKS:
        return jsonify({"error": f"Unknown pack: {pack}. Available: {sorted(PACKS)}"}), 400
    try:
        data = file.read()
        doc = parse(data, ext)
    except ValueError as e:
        return jsonify({"error": str(e)}), 422
    except Exception as e:
        logger.exception("parse failed")
        return jsonify({"error": str(e)}), 500
    try:
        result = query(doc, PACKS[pack], data if ext == "pdf" else None,
                       deep=request.form.get("deep", "false").lower() == "true")
    except Exception:
        logger.exception("query failed")
        return jsonify({"error": "Extraction failed."}), 500
    if request.form.get("annotate") == "true" and ext == "pdf":
        hits = []
        for r in result["fields"].values():
            if not (r.get("grounded") and r.get("page_number")):
                continue
            if isinstance(r.get("value"), list):  # table items: cite every row
                for it in r["value"]:
                    hits.append({"page_number": it.get("page_number", r["page_number"]),
                                 "quote": it["verbatim"]})
            elif r.get("verbatim"):
                hits.append({"page_number": r["page_number"], "quote": r["verbatim"]})
        result["annotated_pdf_base64"] = __import__("base64").b64encode(annotate(data, hits)).decode()
    return jsonify(result)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
