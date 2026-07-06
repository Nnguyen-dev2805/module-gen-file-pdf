# AI Agent Context: Vietnamese PDF Generation & Validation

This workspace now uses an OpenCode-only LLM path.

## 1. Project Overview

The module uses the OpenCode API to generate structured Vietnamese Markdown content. It then appends a dedicated image section generated from `temp/example.jpg`, converts the combined Markdown into PDF using Typst, and validates the generated PDF with a 4-tier rescue loop:

```text
[OpenCode Prompt] -> [Vietnamese Markdown] -> [Example Image Section] -> [Typst Compile] -> [PDF Parse & Validate]
                                                                                              |
                                      [Rescue Loop: NFC / Fonts / Simplified / PlainText] <----+
```

## 2. Current LLM Provider

Runtime code should use:

```python
from src.llm_client import OpenCodeClient
```

Do not add another LLM provider dependency unless the user explicitly asks for it.

## 3. Environment

```env
OPENCODE_API_KEY=your_api_key_here
OPENCODE_MODEL=deepseek-v4-flash-free
OPENCODE_BASE_URL=https://opencode.ai/zen/v1
OPENCODE_TIMEOUT=300
```

## 4. Font Locations

- Roboto:
  - `fonts/Roboto-Regular.ttf`
  - `fonts/Roboto-Bold.ttf`
- Noto Sans:
  - `fonts/NotoSans/NotoSans-Regular.ttf`
  - `fonts/NotoSans/NotoSans-Bold.ttf`
- DejaVu Sans:
  - `fonts/DejaVuSans/DejaVuSans.ttf`
  - `fonts/DejaVuSans/DejaVuSans-Bold.ttf`

## 5. Coding Guidelines

1. Enforce Unicode NFC before compiling or comparing Vietnamese text.
2. Keep OpenCode request failures isolated and fall back to mock content.
3. Keep the PDF image section deterministic through `src/report_image.py` and `temp/example.jpg`.
4. Preserve the 4-tier rescue pipeline.

## 6. Run & Test Commands

```bash
venv/bin/python src/demo.py
```

```bash
OPENCODE_API_KEY= POLLINATIONS_API_KEY= \
venv/bin/python -m unittest discover -s tests
```
