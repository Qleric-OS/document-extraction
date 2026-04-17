"""
Document Intelligence API - Frontier V1
=============================================

A simplified Flask API server for the Document Intelligence Engine.
This version removes SaaS logic
and serves as a clean reference implementation.

Usage:
    pip install -r requirements.txt
    python simple_api.py
"""

import os
import logging
import base64
from flask import Flask, jsonify, request
from werkzeug.utils import secure_filename
import fitz  # PyMuPDF
from dotenv import load_dotenv

from contract_extractor import ContractExtractor

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configuration
ALLOWED_EXTENSIONS = {"pdf", "docx"}
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

# Initialize Extractor
try:
    extractor = ContractExtractor()
    logger.info("ContractExtractor initialized successfully.")
except Exception as e:
    logger.error(f"FATAL: Could not initialize ContractExtractor. {e}")
    extractor = None

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({
        "status": "healthy",
        "extractor_loaded": extractor is not None
    })

@app.route("/analyze", methods=["POST"])
def analyze_contract():
    """
    Analyze a contract PDF or DOCX.
    
    Form Parameters:
        file: The PDF or DOCX file
        fields: Comma-separated list of custom fields (optional)
        
    Returns:
        JSON extraction results including legal graph and grounding data.
    """
    if not extractor:
        return jsonify({"error": "Extractor not initialized"}), 503

    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    fields_str = request.form.get("fields")
    fields = [f.strip() for f in fields_str.split(",")] if fields_str else None

    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    if file and allowed_file(file.filename):
        try:
            filename = secure_filename(file.filename)
            ext = filename.rsplit(".", 1)[1].lower()
            logger.info(f"Processing {filename} (Format: {ext})")
            
            # Read file
            file_content = file.read()
            
            # Extract
            results = extractor.extract_from_file(file_content, extension=ext, fields=fields)
            
            if "error" in results:
                return jsonify(results), 500
                
            return jsonify(results)

        except Exception as e:
            logger.error(f"Error processing file: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    return jsonify({"error": "Invalid file type. Only PDF and DOCX are supported."}), 400

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
