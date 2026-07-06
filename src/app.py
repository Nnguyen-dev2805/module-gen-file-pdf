import os
import sys
import unicodedata
from flask import Flask, request, jsonify, send_file, render_template_string

# Ensure project root is in the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.llm_client import OpenCodeClient
from src.report_image import (
    DEFAULT_OUTPUT_IMAGE_NAME,
    DEFAULT_SOURCE_IMAGE,
    prepare_report_image_section,
    render_example_image_for_pdf,
)
from src.typst_generator import compile_pdf
from src.pdf_validator import validate_pdf, run_rescue_pipeline

app = Flask(__name__)

# Directory configurations
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUTPUT_DIR = "temp"  # relative path for Typst compile references
OUTPUT_PDF = os.path.join(PROJECT_ROOT, OUTPUT_DIR, "web_report.pdf")
SOURCE_IMAGE = os.path.join(PROJECT_ROOT, DEFAULT_SOURCE_IMAGE)
OUTPUT_IMAGE = os.path.join(PROJECT_ROOT, OUTPUT_DIR, DEFAULT_OUTPUT_IMAGE_NAME)
os.makedirs(os.path.join(PROJECT_ROOT, OUTPUT_DIR), exist_ok=True)

# Keep track of last generated PDF metadata for serving
class GenerationState:
    def __init__(self):
        self.success = False
        self.badge = "OK"
        self.errors = []
        self.rescue_log = []
        self.markdown = ""
        self.source_image_path = DEFAULT_SOURCE_IMAGE
        self.output_image_path = os.path.join(OUTPUT_DIR, DEFAULT_OUTPUT_IMAGE_NAME)

state = GenerationState()

# We render the frontend template from a local templates folder.
# Let's write the route to render templates/index.html.
@app.route("/")
def index():
    try:
        # Check if templates/index.html exists and read it
        template_path = os.path.join(app.root_path, "templates", "index.html")
        if os.path.exists(template_path):
            with open(template_path, "r", encoding="utf-8") as f:
                return render_template_string(f.read())
        return "Frontend template src/templates/index.html not found.", 404
    except Exception as e:
        return f"Error loading index page: {e}", 500


@app.route("/api/generate", methods=["POST"])
def generate():
    global state
    
    # Initialize state
    state = GenerationState()
    
    try:
        # Check if multipart form request or JSON
        if request.is_json:
            data = request.get_json() or {}
            prompt = data.get("prompt", "").strip()
            font_name = data.get("font", "Roboto").strip()
            uploaded_file = None
        else:
            prompt = request.form.get("prompt", "").strip()
            font_name = request.form.get("font", "Roboto").strip()
            uploaded_file = request.files.get("image")
        
        if not prompt:
            return jsonify({"success": False, "error": "Prompt cannot be empty"}), 400
            
        # Initialize dynamic paths in generation state
        if uploaded_file and uploaded_file.filename != '':
            ext = os.path.splitext(uploaded_file.filename)[1].lower()
            if not ext:
                ext = ".png"
            source_filename = f"uploaded_source{ext}"
            source_path = os.path.join(PROJECT_ROOT, "temp", source_filename)
            uploaded_file.save(source_path)
            
            state.source_image_path = os.path.join("temp", source_filename)
            state.output_image_path = os.path.join("temp", "uploaded_translated.png")
            source_log_name = uploaded_file.filename
        else:
            state.source_image_path = DEFAULT_SOURCE_IMAGE
            state.output_image_path = os.path.join("temp", DEFAULT_OUTPUT_IMAGE_NAME)
            source_log_name = "temp/example.jpg"

        state.rescue_log.append("Step 1: Contacting configured LLM provider for report generation...")
        
        # 1. Generate Report
        client = OpenCodeClient()
        if getattr(client, "provider", "") == "opencode":
            state.rescue_log.append(f"Info: Using OpenCode model '{client.opencode_model}'.")
        report_md = client.generate_report(prompt)
        report_md = unicodedata.normalize("NFC", report_md)
        state.markdown = report_md
        
        # Import MOCK_REPORT to compare
        from src.llm_client import MOCK_REPORT
        if client.mock_mode:
            state.rescue_log.append("Info: Running in offline mock mode (no API key detected).")
        elif report_md == MOCK_REPORT:
            state.rescue_log.append("Warning: Live API call was rate-limited or failed. Using mock warehouse layout fallback.")
            
        state.rescue_log.append(f"Step 1 Complete: Generated {len(report_md):,} characters of Markdown.")
        state.rescue_log.append(f"Step 2: Preparing dedicated report image section from {source_log_name}...")
        
        # 2. Prepare dedicated image section dynamically.
        image_result = prepare_report_image_section(
            report_md,
            source_image_path=state.source_image_path,
            output_dir=OUTPUT_DIR,
            output_name=os.path.basename(state.output_image_path),
            client=client,
        )
        document_md = image_result.markdown
        state.markdown = document_md

        for log_entry in image_result.log:
            state.rescue_log.append(f"Step 2: {log_entry}")

        if image_result.success:
            state.rescue_log.append(f"Step 2 Complete: Added image section: {image_result.output_image_path}")
        else:
            state.rescue_log.append("Step 2 Warning: Image section was not added.")
            
        state.rescue_log.append("Step 3: Compiling styled document using Typst...")
        
        # 3. Compile PDF
        compile_ok = False
        try:
            compile_pdf(document_md, OUTPUT_PDF, font_name=font_name)
            compile_ok = True
            state.rescue_log.append("Step 3 Complete: Initial compilation succeeded.")
        except Exception as e:
            state.rescue_log.append(f"Step 3 Warning: Initial compilation failed: {e}")
            state.rescue_log.append("Step 3: Falling back to rescue pipeline...")
            
        # 4. Validation & Rescue
        state.rescue_log.append("Step 4: Executing PDF validation checks...")
        
        badge = "OK"
        rescue_applied = False
        
        if compile_ok:
            validation = validate_pdf(OUTPUT_PDF)
            encoding_errors = [e for e in validation.errors if e.error_type == "encoding"]
            leak_errors = [e for e in validation.errors if e.error_type == "leak"]
            
            state.errors = [{"type": e.error_type, "message": e.message, "detail": e.detail, "page": e.page_number} for e in validation.errors]
            
            if encoding_errors:
                state.rescue_log.append(f"Step 4: Found {len(encoding_errors)} encoding error(s). Triggering rescue...")
                rescue = run_rescue_pipeline(document_md, OUTPUT_PDF, font_name=font_name)
                rescue_applied = True
                
                for log_entry in rescue.rescue_log:
                    state.rescue_log.append(f"  {log_entry}")
                    
                if rescue.success:
                    badge = rescue.badge
                    compile_ok = True
                else:
                    badge = rescue.badge
                    compile_ok = False
            elif leak_errors:
                state.rescue_log.append(f"Step 4: Found {len(leak_errors)} English leak warning(s). Rendering with Warning Badge.")
                badge = "Warning"
            else:
                state.rescue_log.append("Step 4 Complete: Validation passed with zero errors.")
        else:
            # S3 failed - run rescue pipeline
            state.rescue_log.append("Step 4: Initial compilation failed entirely. Triggering rescue...")
            rescue = run_rescue_pipeline(document_md, OUTPUT_PDF, font_name=font_name)
            rescue_applied = True
            
            for log_entry in rescue.rescue_log:
                state.rescue_log.append(f"  {log_entry}")
                
            if rescue.success:
                badge = rescue.badge
                compile_ok = True
            else:
                badge = rescue.badge
                compile_ok = False
                
        # Update generation status
        state.success = (compile_ok and os.path.exists(OUTPUT_PDF))
        state.badge = badge
        
        state.rescue_log.append(f"Step 5 Complete: Pipeline execution completed. Badge set to '{state.badge}'.")
        
        return jsonify({
            "success": state.success,
            "badge": state.badge,
            "errors": state.errors,
            "rescue_log": state.rescue_log,
            "markdown": state.markdown,
            "api_status": client.api_status
        })
        
    except Exception as e:
        state.rescue_log.append(f"CRITICAL ERROR: Pipeline crashed: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "rescue_log": state.rescue_log
        }), 500


@app.route("/api/pdf")
def get_pdf():
    if os.path.exists(OUTPUT_PDF):
        return send_file(
            OUTPUT_PDF,
            mimetype="application/pdf",
            as_attachment=False,
            download_name="báo_cáo_kho_hàng.pdf"
        )
    return "No PDF has been generated yet.", 404


@app.route("/api/image/original")
def get_original_image():
    path = os.path.join(PROJECT_ROOT, state.source_image_path)
    if os.path.exists(path):
        mime = "image/png" if path.lower().endswith(".png") else "image/jpeg"
        return send_file(path, mimetype=mime)
    return f"Source image {state.source_image_path} not found.", 404


@app.route("/api/image/translated")
def get_translated_image():
    path = os.path.join(PROJECT_ROOT, state.output_image_path)
    if os.path.exists(path):
        return send_file(path, mimetype="image/png")
    # If the output translated image doesn't exist yet, we can render it dynamically if the source exists
    source_abs = os.path.join(PROJECT_ROOT, state.source_image_path)
    if os.path.exists(source_abs):
        try:
            render_example_image_for_pdf(
                source_image_path=state.source_image_path,
                output_dir=OUTPUT_DIR,
                output_name=os.path.basename(state.output_image_path)
            )
            if os.path.exists(path):
                return send_file(path, mimetype="image/png")
        except Exception as e:
            print(f"Error rendering image on request: {e}")
    return get_original_image()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8085, debug=True)
