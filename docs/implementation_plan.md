# Vietnamese PDF Generation and Validation Module

This document records the current implementation direction after the project was refactored to OpenCode-only text generation.

## 1. Current Architecture

The module converts a user prompt into a Vietnamese Markdown report, renders it to PDF through Typst, and validates the generated PDF for font/encoding issues.

```text
[User Prompt]
  -> [OpenCodeClient]
  -> [Vietnamese Markdown]
  -> [Dedicated image section from temp/example.jpg]
  -> [Typst Compile]
  -> [PDF Parse & Validate]
  -> [4-Tier Rescue Pipeline if needed]
```

## 2. Runtime Providers

| Provider | Status | Purpose |
| :--- | :--- | :--- |
| OpenCode | Active | Generates Vietnamese Markdown reports and translates diagram labels |
| Mock offline | Active fallback | Keeps tests/demo deterministic when `OPENCODE_API_KEY` is missing |
| Gemini | Removed | No longer used by runtime code |

## 3. Environment Variables

```env
OPENCODE_API_KEY=your_api_key_here
OPENCODE_MODEL=deepseek-v4-flash-free
OPENCODE_BASE_URL=https://opencode.ai/zen/v1
OPENCODE_TIMEOUT=300
```

## 4. Core Modules

| Module | Responsibility |
| :--- | :--- |
| `src/llm_client.py` | OpenCode chat-completions client plus mock fallback |
| `src/report_image.py` | Dedicated PDF image section generated from `temp/example.jpg` |
| `src/image_translator.py` | Legacy image helper/tests for mock OCR and label overlay |
| `src/typst_generator.py` | Markdown-to-Typst conversion and PDF compilation |
| `src/pdf_validator.py` | PDF text extraction, glyph checks, English label leak checks, rescue pipeline |
| `src/app.py` | Flask API for the web dashboard |
| `src/demo.py` | CLI end-to-end demo |

## 5. Font Strategy

Bundled fonts are used for deterministic Vietnamese rendering:

| Font | Role |
| :--- | :--- |
| Roboto | Primary |
| Noto Sans | Rescue fallback |
| DejaVu Sans | Rescue fallback |

## 6. Rescue Pipeline

The rescue pipeline remains unchanged:

1. Unicode NFC normalization.
2. Fallback font chain.
3. Simplified Typst layout.
4. Plain-text fallback.

Badge behavior:

| Outcome | Badge |
| :--- | :--- |
| Initial compile and validation pass | `OK` |
| Tier 1-3 rescue succeeds | `Warning` |
| Tier 4 plain-text fallback is required | `Critical Warning` |

## 7. Verification

Run offline tests:

```bash
OPENCODE_API_KEY= POLLINATIONS_API_KEY= \
venv/bin/python -m unittest discover -s tests
```

Run CLI demo:

```bash
venv/bin/python src/demo.py
```

Run web demo:

```bash
venv/bin/python -m flask --app src.app run --host 0.0.0.0 --port 8086
```
