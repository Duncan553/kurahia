#!/usr/bin/env python3
"""
Assemble the Ivy Document from the authored fragments plus captured evidence.

Figures are referenced in the fragments by marker, never by file path, so a
screenshot that was NOT captured simply drops out instead of producing a broken
image or -- far worse -- a caption describing a picture that isn't there.

    <!--IMG:id|caption-->                       one full-width plate
    <!--ROW:id|caption::id|caption-->           two side by side
    <!--EVIDENCE_SUMMARY-->                     the capture scoreboard
"""
import base64
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
SHOTS = Path("/home/wachira/kurahia/docs/ivy/shots")
EVIDENCE = Path("/home/wachira/kurahia/docs/ivy/evidence.json")
OUT = HERE / "ivy_final.html"

missing: list[str] = []
used: list[str] = []


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def figure(shot_id: str, caption: str) -> str | None:
    """One <figure>, or None if that screenshot was never captured."""
    for ext in (".jpg", ".jpeg", ".png"):
        path = SHOTS / f"{shot_id}{ext}"
        if path.exists() and path.stat().st_size > 0:
            mime = "image/png" if ext == ".png" else "image/jpeg"
            b64 = base64.b64encode(path.read_bytes()).decode()
            used.append(shot_id)
            return (
                f'<figure><img alt="{esc(caption)}" src="data:{mime};base64,{b64}">'
                f'<figcaption><span class="tag">{esc(shot_id)}</span>'
                f'<span>{esc(caption)}</span></figcaption></figure>'
            )
    missing.append(shot_id)
    return None


def sub_img(m: re.Match) -> str:
    shot_id, caption = m.group(1).split("|", 1)
    return figure(shot_id.strip(), caption.strip()) or ""


def sub_row(m: re.Match) -> str:
    """Two figures side by side; if only one survives it stands alone."""
    parts = []
    for half in m.group(1).split("::"):
        shot_id, caption = half.split("|", 1)
        fig = figure(shot_id.strip(), caption.strip())
        if fig:
            parts.append(fig)
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return '<div class="figrow">' + "".join(parts) + "</div>"


def evidence_summary() -> str:
    """The capture scoreboard -- including, deliberately, what failed."""
    if not EVIDENCE.exists():
        return ""
    data = json.loads(EVIDENCE.read_text())
    screens = data if isinstance(data, list) else data.get("screens", [])
    ok = [s for s in screens if s.get("captured")]
    bad = [s for s in screens if not s.get("captured")]

    rows = "".join(
        f'<tr><td><strong>{esc(str(s.get("id","?")))}</strong></td>'
        f'<td>{esc(str(s.get("route","")))}</td>'
        f'<td>{esc(str(s.get("failure") or s.get("notes") or "did not open"))}</td></tr>'
        for s in bad
    )
    failed_block = (
        '<h3>Screens that did not open</h3>'
        '<p>Listed because leaving them out would make this document a brochure.</p>'
        '<div class="tablewrap"><table><thead><tr><th>Screen</th><th>Address</th>'
        f'<th>What happened</th></tr></thead><tbody>{rows}</tbody></table></div>'
        if bad else
        '<p>Every screen attempted opened and was verified before capture.</p>'
    )

    return (
        '<div class="tablewrap"><table><thead><tr><th>Capture run</th><th>Count</th></tr></thead>'
        f'<tbody><tr><td>Screens verified and photographed</td><td class="num">{len(ok)}</td></tr>'
        f'<tr><td>Screens that failed their check</td><td class="num">{len(bad)}</td></tr>'
        f'<tr><td>Total attempted</td><td class="num">{len(screens)}</td></tr>'
        '</tbody></table></div>' + failed_block
    )


def main() -> None:
    head = (HERE / "ivy.html").read_text()
    body = "".join(
        (HERE / name).read_text()
        for name in ("acts.html", "dashboards.html", "closing.html")
    )
    html = head.replace("<!-- FIGURES AND ACTS INSERTED HERE -->", body)

    html = re.sub(r"<!--ROW:(.+?)-->", sub_row, html, flags=re.S)
    html = re.sub(r"<!--IMG:(.+?)-->", sub_img, html, flags=re.S)
    html = html.replace("<!--EVIDENCE_SUMMARY-->", evidence_summary())

    OUT.write_text(html)
    size_mb = OUT.stat().st_size / 1024 / 1024
    print(f"wrote {OUT}  ({size_mb:.2f} MB)")
    print(f"figures embedded : {len(used)}")
    print(f"figures missing  : {len(missing)}" + (f"  -> {', '.join(missing)}" if missing else ""))
    if size_mb > 15:
        print("WARNING: over the 16MB artifact limit -- recapture at lower quality", file=sys.stderr)


if __name__ == "__main__":
    main()
