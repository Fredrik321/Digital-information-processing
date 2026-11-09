"""Render synthesis.md to synthesis.pdf (Markdown -> HTML -> headless Edge/Chrome).

    python make_synthesis_pdf.py

Needs the `markdown` package and Edge or Chrome. Not part of the pipeline;
it only formats the portfolio synthesis for submission. Adapted from
p3/make_pdf.py, with a more compact layout so the answer fits one page.
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import markdown

HERE = Path(__file__).resolve().parent
# Chrome first: on our machine headless Edge exited without writing the PDF.
BROWSERS = [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            "google-chrome", "chromium", "chrome", "msedge"]

CSS = """
@page { size: A4; margin: 13mm 14mm; }
body { font-family: "Segoe UI", Arial, sans-serif; font-size: 9pt; line-height: 1.30; color: #1b1b1b; }
h1 { font-size: 15pt; margin: 0 0 3pt; color: #17325c; }
h2 { font-size: 10.5pt; margin: 7pt 0 2pt; color: #17325c; border-bottom: 1px solid #c9d3e0; padding-bottom: 1pt; }
code { font-family: Consolas, monospace; font-size: 8.5pt; background: #f3f5f8; padding: 0 2pt; }
a { color: #17325c; text-decoration: none; }
p { margin: 2.5pt 0; }
"""


def main():
    text = (HERE / "synthesis.md").read_text(encoding="utf-8")
    body = markdown.markdown(text, extensions=["tables", "fenced_code", "sane_lists"])
    html = HERE / "synthesis.html"
    html.write_text(f"<!doctype html><html><head><meta charset='utf-8'>"
                    f"<base href='{HERE.as_uri()}/'><style>{CSS}</style></head>"
                    f"<body>{body}</body></html>", encoding="utf-8")
    browser = next((b for b in BROWSERS if Path(b).is_file() or shutil.which(b)), None)
    if browser is None:
        sys.exit(f"no Edge/Chrome found; open {html} in a browser and print it to PDF")
    pdf = HERE / "synthesis.pdf"
    pdf.unlink(missing_ok=True)
    # A separate profile keeps an already-open browser window from taking over the job.
    with tempfile.TemporaryDirectory() as profile:
        subprocess.run([browser, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                        f"--user-data-dir={profile}", "--allow-file-access-from-files",
                        f"--print-to-pdf={pdf}", html.as_uri()],
                       check=True, capture_output=True, timeout=120)
    if not pdf.is_file():
        sys.exit(f"the browser did not write {pdf}; open {html} and print it to PDF instead")
    print(f"wrote {pdf} ({pdf.stat().st_size / 1e3:.0f} kB)")


if __name__ == "__main__":
    main()
