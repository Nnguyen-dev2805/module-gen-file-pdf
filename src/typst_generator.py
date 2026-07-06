import os
import re
import typst
from typing import List, Optional

def convert_markdown_table_to_typst(markdown_table_lines: List[str]) -> str:
    """
    Converts a Markdown table string list into a Typst table representation.
    Example:
    | H1 | H2 |
    |---|---|
    | C1 | C2 |
    ➔
    #table(
      columns: (1fr, 1fr),
      align: (left, left),
      [*H1*], [*H2*],
      [C1], [C2]
    )
    """
    rows = []
    for line in markdown_table_lines:
        # Strip trailing/leading spaces and pipes
        line = line.strip()
        if not line:
            continue
        # Split by pipe
        parts = [p.strip() for p in line.split("|")]
        # Remove first and last empty elements if they exist due to outer pipes
        if line.startswith("|") and parts:
            parts.pop(0)
        if line.endswith("|") and parts:
            parts.pop()
        
        # Skip separator rows like | :--- | :--- |
        if parts and all(re.match(r'^:?-+:?$', p) for p in parts):
            continue
            
        rows.append(parts)

    if not rows:
        return ""

    num_cols = len(rows[0])
    
    # Generate Typst columns configuration
    cols_str = f"({', '.join(['1fr'] * num_cols)})"
    
    # Generate cells
    cell_lines = []
    # Header row gets bold text
    for cell in rows[0]:
        cell_lines.append(f"  [* {cell} *]")
    # Content rows
    for row in rows[1:]:
        # Ensure row matches column count
        row_extended = row + [""] * (num_cols - len(row))
        for cell in row_extended:
            cell_lines.append(f"  [{cell}]")

    cells_str = ",\n".join(cell_lines)

    typst_table = f"""#table(
  columns: {cols_str},
  align: (left, ) * {num_cols},
  {cells_str}
)"""
    return typst_table


def convert_markdown_to_typst(markdown_text: str) -> str:
    """
    Translates standard Markdown elements to Typst markup syntax.
    """
    lines = markdown_text.splitlines()
    typst_lines = []
    
    in_table = False
    table_lines = []
    in_code_block = False

    for line in lines:
        stripped = line.strip()
        
        # Handle Code Block parsing
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            typst_lines.append(line)
            continue
            
        if in_code_block:
            typst_lines.append(line)
            continue

        # Handle Table parsing
        if stripped.startswith("|"):
            in_table = True
            table_lines.append(line)
            continue
        elif in_table:
            # End of table block
            typst_lines.append(convert_markdown_table_to_typst(table_lines))
            table_lines = []
            in_table = False
            
        # Parse block structure
        is_header = False
        is_ul = False
        is_ol = False
        
        header_match = re.match(r'^(#{1,6})\s+(.+)$', line)
        ul_match = re.match(r'^(\s*)[-*+]\s+(.+)$', line)
        ol_match = re.match(r'^(\s*)\d+\.\s+(.+)$', line)
        
        if header_match:
            is_header = True
            level = len(header_match.group(1))
            content = header_match.group(2)
        elif ul_match:
            is_ul = True
            content = ul_match.group(2)
        elif ol_match:
            is_ol = True
            content = ol_match.group(2)
        else:
            content = line

        # Apply inline formatting to content
        # Convert italics first, matching single asterisks but NOT double asterisks
        content = re.sub(r'(?<!\*)\*(?!\*)(.*?)(?<!\*)\*(?!\*)', r'_\1_', content)
        # Convert bold, matching double asterisks
        content = re.sub(r'\*\*(.*?)\*\*', r'*\1*', content)
        # Images: ! [Alt] (Path) ➔ #image("Path", width: 90%)
        content = re.sub(r'!\s*\[(.*?)\]\s*\((.*?)\)', r'#image("\2", width: 90%)', content)

        # Re-assemble block
        if is_header:
            typst_lines.append(f"{'=' * level} {content}")
        elif is_ul:
            typst_lines.append(f"- {content}")
        elif is_ol:
            typst_lines.append(f"+ {content}")
        else:
            typst_lines.append(content)

    # If document ends on a table
    if in_table:
        typst_lines.append(convert_markdown_table_to_typst(table_lines))

    return "\n".join(typst_lines)


def generate_typst_document(content_markdown: str, font_name: str = "Roboto", simplified: bool = False) -> str:
    """
    Wraps the translated content in a styled Typst template configured with page layout,
    margins, footers, line height, and standard Vietnamese font setup.
    """
    # Translate content
    typst_content = convert_markdown_to_typst(content_markdown)
    
    if simplified:
        # Simplified layout for rescue mode: no header/footer, no justification
        template = f"""// Simplified Typst Layout (Rescue Mode)
#set page(
  paper: "a4",
  margin: (x: 2.5cm, y: 3cm)
)

#set text(
  font: "{font_name}",
  size: 11pt,
  lang: "vi",
  region: "vn"
)

// Document Body Content
{typst_content}
"""
    else:
        # Combine into styled template
        template = f"""// Typst Layout Template Configured for Vietnamese PDF
#set page(
  paper: "a4",
  margin: (x: 2cm, y: 2.5cm),
  header: align(right)[Báo cáo Kho hàng Thông minh],
  footer: context align(center)[Trang #counter(page).display("1 / 1", both: true)]
)

#set text(
  font: "{font_name}",
  size: 11pt,
  lang: "vi",
  region: "vn",
  spacing: 120% // Line spacing
)

#set par(
  leading: 0.65em,
  justify: true
)

// Document Body Content
{typst_content}
"""
    return template


def compile_pdf(content_markdown: str, output_pdf_path: str, font_name: str = "Roboto", simplified: bool = False) -> None:
    """
    Compiles a Vietnamese markdown string into a PDF using Typst, linking local fonts directory.
    """
    # 1. Generate full Typst document source
    typst_code = generate_typst_document(content_markdown, font_name, simplified)
    
    # 2. Write code to a temporary file
    temp_typ_path = "temp_doc.typ"
    with open(temp_typ_path, "w", encoding="utf-8") as f:
        f.write(typst_code)

    # 3. Call the typst compiler
    # Typst font path requires search folders where .ttf are stored
    # We pass local directories: "fonts" and "fonts/NotoSans" / "fonts/DejaVuSans"
    font_dirs = ["fonts", "fonts/NotoSans", "fonts/DejaVuSans"]
    
    try:
        os.makedirs(os.path.dirname(output_pdf_path), exist_ok=True)
        # compile(input, output, font_paths)
        typst.compile(
            input=temp_typ_path,
            output=output_pdf_path,
            font_paths=font_dirs,
            ignore_system_fonts=True  # Guarantees offline font determinism
        )
    finally:
        # Clean up temporary Typst source file
        if os.path.exists(temp_typ_path):
            os.remove(temp_typ_path)
