"""HTML reporter.

Renders a single self-contained HTML file (CSS inline, no external
assets) suitable for CI artifact upload.
"""

from __future__ import annotations

import html
from typing import Iterable

from ..core import Cluster


_CSS = """
:root {
  --fg: #0f172a;
  --fg-dim: #475569;
  --bg: #f8fafc;
  --card: #ffffff;
  --border: #e2e8f0;
  --accent: #6366f1;
  --warn: #d97706;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
  background: var(--bg);
  color: var(--fg);
  font-size: 14px;
  line-height: 1.5;
  padding: 32px 24px;
}
h1 { font-size: 22px; margin: 0 0 4px; }
.summary { color: var(--fg-dim); margin-bottom: 24px; }
.cluster {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px 20px;
  margin-bottom: 16px;
}
.cluster header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 12px;
}
.tags { font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 13px; color: var(--accent); }
.size { font-weight: 600; color: var(--warn); }
ul { margin: 0; padding-left: 18px; }
li { margin-bottom: 4px; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 12px; }
li .lang { display: inline-block; min-width: 80px; color: var(--fg-dim); }
.empty { color: var(--fg-dim); padding: 16px; text-align: center; background: var(--card); border-radius: 8px; }
"""


def render_html(
    clusters: Iterable[Cluster],
    *,
    scanned_units: int,
    extractors: list[str],
    min_resources: int,
    min_cluster_size: int,
) -> str:
    clusters = list(clusters)
    body_parts: list[str] = []

    body_parts.append(
        f"<h1>parallax report</h1>"
        f"<p class='summary'>Scanned <strong>{scanned_units}</strong> units "
        f"with <strong>{html.escape(', '.join(extractors))}</strong>. "
        f"Found <strong>{len(clusters)}</strong> clusters "
        f"(≥ {min_resources} resources, ≥ {min_cluster_size} members).</p>"
    )

    if not clusters:
        body_parts.append("<div class='empty'>No clusters found.</div>")
    else:
        for c in clusters:
            resources = ", ".join(html.escape(r) for r in sorted(c.resources))
            body_parts.append("<div class='cluster'>")
            body_parts.append("  <header>")
            body_parts.append(f"    <span class='tags'>[{resources}]</span>")
            body_parts.append(
                f"    <span class='size'>{c.size} units · score {c.score:.2f}</span>"
            )
            body_parts.append("  </header>")
            body_parts.append("  <ul>")
            for u in c.units:
                lang = html.escape(u.language) if u.language else "—"
                loc = html.escape(u.location)
                name = html.escape(u.name)
                body_parts.append(
                    f"    <li><span class='lang'>[{lang}]</span> {loc} :: {name}</li>"
                )
            body_parts.append("  </ul>")
            body_parts.append("</div>")

    body = "\n".join(body_parts)
    return (
        "<!doctype html>\n"
        "<html lang='en'>\n"
        "<head>\n"
        "<meta charset='utf-8'>\n"
        "<title>parallax report</title>\n"
        f"<style>{_CSS}</style>\n"
        "</head>\n"
        f"<body>\n{body}\n</body>\n"
        "</html>\n"
    )
