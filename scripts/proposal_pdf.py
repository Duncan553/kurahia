"""
scripts/proposal_pdf.py — print the proposal to a PDF the client can be sent.

The web page and the PDF are the SAME document: this loads the built page in a
real browser and prints it, so the print stylesheet in the template is what
shapes the pages. Nothing is written twice, which is how the two would drift.

Two things the print CSS does that matter here, and why:
  - it forces the LIGHT palette. The page follows the reader's theme, and a
    dark PDF is unreadable on paper and wastes a cartridge printing it.
  - it keeps each plate whole with its caption (`break-inside: avoid`), so a
    photograph never lands on one sheet with its explanation on the next.

Run:  .venv/bin/python scripts/proposal_pdf.py
"""
import http.server
import pathlib
import socketserver
import subprocess
import sys
import threading

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs/proposal"
OUT = DOCS / "Waterfront_Juja_Proposal.pdf"
PORT = 8931

if not (DOCS / "index.html").exists():
    sys.exit("No built page. Run scripts/build_proposal.py first.")


class Quiet(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(DOCS), **kw)

    def log_message(self, *a):
        pass


class Reusable(socketserver.TCPServer):
    # Without this a rebuild moments after the last one dies on "Address
    # already in use", because the previous socket is still in TIME_WAIT.
    allow_reuse_address = True


def serve(port):
    # file:// cannot fetch the Google Fonts stylesheet, and a PDF set in Times
    # is not the document. Serve it over http so the page renders as designed.
    with Reusable(("127.0.0.1", port), Quiet) as httpd:
        httpd.serve_forever()


def free_port(start):
    """Take `start` if it is free, otherwise the next port that is.

    A leftover server from an earlier run used to kill the whole build with a
    stack trace, for no better reason than a number being taken.
    """
    import socket
    for candidate in range(start, start + 20):
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", candidate)) != 0:
                return candidate
    raise SystemExit(f"no free port in {start}..{start + 19}")


PORT = free_port(PORT)
threading.Thread(target=serve, args=(PORT,), daemon=True).start()

SCRIPT = f"""
const {{ chromium }} = require('playwright');
(async () => {{
  const b = await chromium.launch();
  const p = await b.newPage();
  // The page follows the reader's theme; a PDF must not. Ask for light
  // explicitly as well as forcing it in the print stylesheet.
  await p.emulateMedia({{ media: 'print', colorScheme: 'light' }});
  await p.goto('http://127.0.0.1:{PORT}/index.html', {{ waitUntil: 'networkidle', timeout: 120000 }});
  await p.evaluate(() => document.fonts.ready);
  // Every plate is lazy-loaded. Printing before they decode gives blank boxes,
  // so wait for each <img> to actually have pixels.
  await p.evaluate(async () => {{
    const imgs = [...document.images];
    imgs.forEach(i => i.loading = 'eager');
    await Promise.all(imgs.map(i => i.complete && i.naturalWidth > 0
      ? null
      : new Promise(r => {{ i.addEventListener('load', r); i.addEventListener('error', r); }})));
  }});
  const blank = await p.evaluate(() =>
    [...document.images].filter(i => !(i.naturalWidth > 0)).map(i => i.getAttribute('src')));
  if (blank.length) {{
    console.error('REFUSING: these images never loaded:\\n  ' + blank.join('\\n  '));
    process.exit(1);
  }}
  await p.pdf({{
    path: '{OUT}',
    format: 'A4',
    printBackground: true,
    margin: {{ top: '14mm', bottom: '14mm', left: '12mm', right: '12mm' }},
  }});
  console.log('images printed: ' + (await p.evaluate(() => document.images.length)));
  await b.close();
}})();
"""

tmp = ROOT / "scripts/.pdf_run.cjs"
tmp.write_text(SCRIPT)
try:
    r = subprocess.run(["node", str(tmp)], cwd=ROOT, capture_output=True, text=True)
    print(r.stdout.strip() or r.stderr.strip())
    if r.returncode != 0:
        sys.exit(r.returncode)
finally:
    tmp.unlink(missing_ok=True)

size = OUT.stat().st_size
print(f"{OUT}  —  {size/1_000_000:.2f} MB")
