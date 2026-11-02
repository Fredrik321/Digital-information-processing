"""Render p3.md to Deliverable/p3.pdf (Markdown -> HTML -> headless Edge/Chrome).

    python make_pdf.py

Needs the `markdown` package and Edge or Chrome. Not part of the pipeline;
it only formats the report for submission.
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import markdown

HERE = Path(__file__).resolve().parent
OUT = HERE / "Deliverable"
# Chrome first: on our machine headless Edge exited without writing the PDF.
BROWSERS = [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            "google-chrome", "chromium", "chrome", "msedge"]

CSS = """
@page { size: A4; margin: 16mm 15mm; }
body { font-family: "Segoe UI", Arial, sans-serif; font-size: 9.5pt; line-height: 1.38; color: #1b1b1b; }
h1 { font-size: 18pt; margin: 0 0 4pt; color: #17325c; }
h2 { font-size: 13pt; margin: 14pt 0 4pt; color: #17325c; border-bottom: 1px solid #c9d3e0; padding-bottom: 2pt; }
h3 { font-size: 10.5pt; margin: 10pt 0 3pt; color: #17325c; }
table { border-collapse: collapse; width: 100%; margin: 5pt 0 8pt; font-size: 8.5pt; page-break-inside: auto; }
tr { page-break-inside: avoid; }
th, td { border: 1px solid #c9d3e0; padding: 3pt 5pt; vertical-align: top; text-align: left; }
th { background: #eef2f7; }
code { font-family: Consolas, monospace; font-size: 8.5pt; background: #f3f5f8; padding: 0 2pt; }
pre { background: #f3f5f8; padding: 5pt 7pt; font-size: 8pt; white-space: pre-wrap; word-break: break-all; }
pre code { background: none; padding: 0; }
img { max-width: 100%; }
p, li { margin: 3pt 0; }
"""


def main():
    text = (HERE / "p3.md").read_text(encoding="utf-8")
    body = markdown.markdown(text, extensions=["tables", "fenced_code", "sane_lists"])
    OUT.mkdir(exist_ok=True)
    html = OUT / "p3.html"
    html.write_text(f"<!doctype html><html><head><meta charset='utf-8'>"
                    f"<base href='{HERE.as_uri()}/'><style>{CSS}</style></head>"
                    f"<body>{body}</body></html>", encoding="utf-8")
    browser = next((b for b in BROWSERS if Path(b).is_file() or shutil.which(b)), None)
    if browser is None:
        sys.exit(f"no Edge/Chrome found; open {html} in a browser and print it to PDF")
    pdf = OUT / "p3.pdf"
    pdf.unlink(missing_ok=True)
    # A separate profile keeps an already-open browser window from taking over the job.
    with tempfile.TemporaryDirectory() as profile:
        subprocess.run([browser, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                        f"--user-data-dir={profile}", "--allow-file-access-from-files",
                        f"--print-to-pdf={pdf}", html.as_uri()],
                       check=True, capture_output=True, timeout=120)
    if not pdf.is_file():
        sys.exit(f"the browser did not write {pdf}; open {html} and print it to PDF instead")
    print(f"wrote {pdf} ({pdf.stat().st_size / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
