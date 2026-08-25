#!/usr/bin/env python3
"""Render v2/analysis.json into a self-contained dashboard page.

Regenerated as the run proceeds, so it is written to be re-read rather than
read once: the regressions sit at the top where they cannot be missed, and
every number carries its denominator, because "17 improved" means something
different at 101 projects than at 251.
"""

import json
import pathlib
from datetime import datetime, timezone

ROOT = pathlib.Path("/home/ubuntu/sbomify-eval")
D = json.loads((ROOT / "v2" / "analysis.json").read_text())
try:
    V3 = json.loads((ROOT / "v3" / "analysis.json").read_text())
except Exception:
    V3 = None

# Causes established by reading the logs, not guessed from the numbers. A bare
# "-10 components" invites the reader to assume the worst or shrug it off; the
# interesting one here is a side effect of our own change.
DIAGNOSED = {
    "abpframework/abp": "#353 side effect: 175 of the 200 discovery slots are .csproj, "
                        "evicting every yarn.lock in the repo",
    "denoland/deno": "3 of 1131 -- third-party registry drift, not a code change",
    "apache/spark": "the baseline was itself a 1-component document",
}

FIELD_LABEL = {
    "metadata.supplier": "Supplier", "metadata.manufacturer": "Manufacturer",
    "metadata.authors": "Authors", "metadata.licenses": "Licences",
    "metadata.lifecycles": "Lifecycles", "metadata.tools": "Tools",
    "root.licenses": "Root licence", "root.supplier": "Root supplier",
    "root.externalReferences": "Root ext. refs", "root.vcs": "Root VCS",
}


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def pct(n, d):
    return round(100.0 * n / d) if d else 0


def bar(before, after, denom):
    """Two stacked rules: the before as a ghost, the after solid over it."""
    b, a = pct(before, denom), pct(after, denom)
    delta = a - b
    cls = "up" if delta > 0 else ("down" if delta < 0 else "flat")
    sign = "+" if delta > 0 else ""
    return f'''<div class="bar-wrap">
      <div class="bar-ghost" style="width:{b}%"></div>
      <div class="bar-fill {cls}" style="width:{a}%"></div>
    </div>
    <span class="bar-num">{before}<span class="arrow">&rarr;</span>{after}
      <em class="{cls}">{sign}{delta if delta else "0"}pp</em></span>'''


gen = D["generation"]
done, total = D["done"], D["total"]
regressions = [r for r in D["rows"] if "LOST" in r["verdict"] or r["verdict"].startswith("-")]
wins = [r for r in D["rows"] if r["verdict"].startswith("+") or r["verdict"] in
        ("gained an SBOM", "no flag needed now", "empty SBOM now refused")]

eco_rows = "".join(
    f'''<tr><td class="eco">{esc(k)}</td><td class="num">{v["n"]}</td>
    <td class="num good">{v["improved"] or ""}</td>
    <td class="num bad">{v["regressed"] or ""}</td>
    <td class="num dim">{v["same"]}</td></tr>'''
    for k, v in D["ecosystems"].items())

def reg_row(r):
    why = DIAGNOSED.get(r["slug"])
    why_html = f'<div class="why">{esc(why)}</div>' if why else ""
    return (f'<tr><td>{esc(r["slug"])}{why_html}</td>'
            f'<td class="eco">{esc(r["ecosystem"])}</td>'
            f'<td class="num">{r["before"] if r["before"] is not None else "&mdash;"}</td>'
            f'<td class="num">{r["after"] if r["after"] is not None else "&mdash;"}</td>'
            f'<td class="verdict bad">{esc(r["verdict"])}</td></tr>')


reg_rows = "".join(reg_row(r) for r in regressions) or \
    '<tr><td colspan="5" class="empty">No regressions so far.</td></tr>'

win_rows = "".join(
    f'''<tr><td>{esc(r["slug"])}</td><td class="eco">{esc(r["ecosystem"])}</td>
    <td class="num">{r["before"] if r["before"] is not None else "&mdash;"}</td>
    <td class="num">{r["after"] if r["after"] is not None else "&mdash;"}</td>
    <td class="verdict good">{esc(r["verdict"])}</td></tr>'''
    for r in sorted(wins, key=lambda r: -(r["after"] or 0))[:24])

enr = D["enrichment"]
enr_rows = "".join(
    f'''<tr><td>{esc(f)}</td><td class="barcell">{bar(
        enr["before"].get(f) or 0, enr["after"].get(f) or 0, 100)}</td></tr>'''
    for f in ("license", "purl", "version", "description", "supplier", "hashes", "extrefs", "vcs")
    if enr["before"].get(f) is not None or enr["after"].get(f) is not None)

aug = D["augmentation"]
aug_n = aug["after_n"] or 1
aug_rows = "".join(
    f'''<tr><td>{esc(FIELD_LABEL.get(f, f))}</td><td class="barcell">{bar(
        aug["before"].get(f, 0), aug["after"].get(f, 0), aug_n)}</td></tr>'''
    for f in aug["fields"])

purl_rows = "".join(
    f'''<tr><td>{esc(r["type"])}</td><td class="num">{r["components"]:,}</td>
    <td class="num">{r["enriched"]:,}</td><td class="barcell">
    <div class="bar-wrap"><div class="bar-fill {"down" if r["ratio"] < 0.5 else "up"}"
         style="width:{round(r["ratio"]*100)}%"></div></div>
    <span class="bar-num">{r["ratio"]:.2f}</span></td></tr>'''
    for r in D.get("by_purl", []))

src_after = sorted(enr["after_sources"].items(), key=lambda x: -x[1])[:8]
src_max = max([v for _, v in src_after], default=1)
src_rows = "".join(
    f'''<tr><td>{esc(k)}</td><td class="barcell">
    <div class="bar-wrap"><div class="bar-fill accent" style="width:{pct(v, src_max)}%"></div></div>
    <span class="bar-num">{v:,}<em class="dim">fields</em></span></td></tr>'''
    for k, v in src_after)

v3_rows = ""
v3_header = ""
if V3 and V3["done"]:
    v3_rows = "".join(
        f'''<tr><td>{esc(r["ecosystem"])}{" <span class=\"tag\">new</span>" if r["is_new"] else ""}
        {" <span class=\"tag ok\">supported in #357</span>" if r["supported"] else ""}</td>
        <td class="num">{r["run"]}</td>
        <td class="num {"good" if r["with_sbom"] else "dim"}">{r["with_sbom"]}</td>
        <td class="num dim">{r["empty"] or ""}</td>
        <td class="num dim">{r["no_lockfile"] or ""}</td>
        <td class="num">{r["median"] or "&mdash;"}</td></tr>'''
        for r in V3["rows"])
    v3_header = (f'{V3["done"]} of {V3["total"]} run &middot; '
                 f'{V3["with_sbom"]} produced an SBOM &middot; '
                 f'{V3["no_lockfile"]} found no recognised input')

stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
progress = pct(done, total)
running = done < total

html = f'''<title>SBOM benchmark &mdash; fix validation</title>
<style>
:root {{
  --ink: #141035; --paper: #f7f6fb; --card: #ffffff;
  --text: #1c1a2e; --muted: #5f5c7a; --line: #e3e0ee;
  --accent: #6c5ce7; --good: #1e8a5f; --bad: #c0392b; --ghost: #d6d2e8;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --paper: #0d0b1c; --card: #17142c; --text: #eceafa; --muted: #a09cc0;
    --line: #2a2544; --accent: #8a7dff; --good: #3fc98a; --bad: #ff6b6b; --ghost: #2f2a4d;
  }}
}}
:root[data-theme="dark"] {{
  --paper: #0d0b1c; --card: #17142c; --text: #eceafa; --muted: #a09cc0;
  --line: #2a2544; --accent: #8a7dff; --good: #3fc98a; --bad: #ff6b6b; --ghost: #2f2a4d;
}}
:root[data-theme="light"] {{
  --paper: #f7f6fb; --card: #ffffff; --text: #1c1a2e; --muted: #5f5c7a;
  --line: #e3e0ee; --accent: #6c5ce7; --good: #1e8a5f; --bad: #c0392b; --ghost: #d6d2e8;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0; background: var(--paper); color: var(--text);
  font: 15px/1.55 ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  -webkit-font-smoothing: antialiased;
}}
.wrap {{ max-width: 1040px; margin: 0 auto; padding: 40px 24px 80px; }}
header {{ display: flex; flex-direction: column; gap: 14px; margin-bottom: 34px; }}
.eyebrow {{
  font-size: 11px; letter-spacing: .13em; text-transform: uppercase;
  color: var(--muted); font-weight: 600;
}}
h1 {{ margin: 0; font-size: clamp(26px, 4vw, 36px); letter-spacing: -.02em; text-wrap: balance; }}
.sub {{ color: var(--muted); max-width: 62ch; margin: 0; }}
.progress {{ height: 6px; background: var(--ghost); border-radius: 99px; overflow: hidden; }}
.progress i {{ display: block; height: 100%; width: {progress}%; background: var(--accent); }}
.progress-label {{
  display: flex; justify-content: space-between; font-size: 13px; color: var(--muted);
  font-variant-numeric: tabular-nums;
}}
.live {{ color: {"var(--accent)" if running else "var(--good)"}; font-weight: 600; }}
.stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin-bottom: 40px; }}
.stat {{ background: var(--card); border: 1px solid var(--line); border-radius: 10px; padding: 16px 18px; }}
.stat b {{ display: block; font-size: 30px; letter-spacing: -.02em; font-variant-numeric: tabular-nums; }}
.stat span {{ font-size: 12.5px; color: var(--muted); }}
.stat.good b {{ color: var(--good); }} .stat.bad b {{ color: var(--bad); }}
section {{ margin-bottom: 42px; }}
h2 {{ font-size: 13px; letter-spacing: .1em; text-transform: uppercase; color: var(--muted);
     margin: 0 0 4px; font-weight: 700; }}
.note {{ color: var(--muted); font-size: 13.5px; margin: 0 0 16px; max-width: 68ch; }}
.tablecard {{ background: var(--card); border: 1px solid var(--line); border-radius: 10px; overflow-x: auto; }}
table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
th {{
  text-align: left; font-size: 11px; letter-spacing: .08em; text-transform: uppercase;
  color: var(--muted); padding: 11px 14px; border-bottom: 1px solid var(--line); font-weight: 600;
  white-space: nowrap;
}}
td {{ padding: 9px 14px; border-bottom: 1px solid var(--line); }}
tr:last-child td {{ border-bottom: 0; }}
.num {{ text-align: right; font-variant-numeric: tabular-nums;
        font-family: ui-monospace, SFMono-Regular, Menlo, monospace; white-space: nowrap; }}
.eco {{ color: var(--muted); font-size: 12.5px; }}
.good {{ color: var(--good); }} .bad {{ color: var(--bad); }} .dim {{ color: var(--muted); }}
.verdict {{ font-size: 13px; white-space: nowrap; }}
.empty {{ color: var(--muted); text-align: center; padding: 22px; font-style: italic; }}
.barcell {{ display: flex; align-items: center; gap: 12px; }}
.bar-wrap {{ position: relative; flex: 1; min-width: 120px; height: 8px;
             background: var(--ghost); border-radius: 99px; overflow: hidden; }}
.bar-ghost {{ position: absolute; inset: 0 auto 0 0; background: var(--muted); opacity: .35; }}
.bar-fill {{ position: absolute; inset: 0 auto 0 0; background: var(--accent); }}
.bar-fill.up {{ background: var(--good); }} .bar-fill.down {{ background: var(--bad); }}
.bar-num {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12.5px;
            font-variant-numeric: tabular-nums; white-space: nowrap; min-width: 128px; }}
.arrow {{ color: var(--muted); padding: 0 4px; }}
.bar-num em {{ font-style: normal; padding-left: 7px; }}
em.up {{ color: var(--good); }} em.down {{ color: var(--bad); }} em.flat {{ color: var(--muted); }}
footer {{ color: var(--muted); font-size: 13px; border-top: 1px solid var(--line); padding-top: 18px; }}
footer code {{ font-size: 12.5px; }}
.why {{ color: var(--muted); font-size: 12.5px; margin-top: 3px; max-width: 52ch; }}
.tag {{ font-size: 10.5px; letter-spacing: .06em; text-transform: uppercase; padding: 2px 6px;
        border: 1px solid var(--line); border-radius: 99px; color: var(--muted); margin-left: 6px;
        white-space: nowrap; }}
.tag.ok {{ color: var(--good); border-color: var(--good); }}
</style>

<div class="wrap">
<header>
  <div class="eyebrow">sbomify-action &middot; post-fix validation</div>
  <h1>Do the fixes hold up across 251 projects?</h1>
  <p class="sub">Every project re-run against the image CI built from master, with augmentation
  and enrichment on and upload off &mdash; the same environment as the original survey, so what
  moves is our code and not the harness.</p>
  <div class="progress"><i></i></div>
  <div class="progress-label">
    <span class="live">{"running" if running else "complete"}</span>
    <span>{done} of {total} projects &middot; {progress}%</span>
  </div>
</header>

<div class="stats">
  <div class="stat good"><b>{gen["improved"]}</b><span>improved</span></div>
  <div class="stat bad"><b>{gen["regressed"]}</b><span>regressed</span></div>
  <div class="stat"><b>{gen["same"]}</b><span>unchanged</span></div>
  <div class="stat"><b>{gen["gained"]}</b><span>gained an SBOM</span></div>
  <div class="stat"><b>{gen["refused"]}</b><span>empty &rarr; refused</span></div>
  <div class="stat"><b>{gen.get("no_baseline", 0)}</b><span>no trusted baseline</span></div>
</div>

<section>
  <h2>Regressions</h2>
  <p class="note">Listed first and in full, however few. A project whose SBOM had zero components
  and now gets a refusal naming the missing file is <em>not</em> counted here &mdash; an empty
  document certifies nothing, and treating that fix as damage would be scoring it backwards.
  JVM projects with no isolated baseline are excluded too: the shared-cache survey cannot measure
  them (F16), and comparing against a contaminated figure invents regressions.</p>
  <div class="tablecard"><table>
    <tr><th>Project</th><th>Stack</th><th class="num">Before</th><th class="num">After</th><th>Change</th></tr>
    {reg_rows}
  </table></div>
</section>

<section>
  <h2>By ecosystem</h2>
  <div class="tablecard"><table>
    <tr><th>Stack</th><th class="num">Run</th><th class="num">Better</th><th class="num">Worse</th><th class="num">Same</th></tr>
    {eco_rows}
  </table></div>
</section>

<section>
  <h2>Enrichment coverage</h2>
  <p class="note">Mean field coverage across dependency components, over the
  {enr["after_n"]} projects comparable on both sides. The faint bar is the original survey,
  the solid bar this run.</p>
  <div class="tablecard"><table>{enr_rows}</table></div>
</section>

<section>
  <h2>Which source filled what</h2>
  <p class="note">Counted from the <code>sbomify:enrichment:source</code> property the enricher
  stamps on every field it fills.</p>
  <div class="tablecard"><table>{src_rows}</table></div>
</section>

<section>
  <h2>Enrichment by package ecosystem</h2>
  <p class="note">Fields filled per component, attributed by each document's dominant purl type.
  This is where the headline reading resolves: mean coverage fell about two points, and not because
  anything got worse. .NET generation started working &mdash; <code>dotnet/runtime</code> went from
  1 component to 1,530 &mdash; and .NET is the one ecosystem our sources do not cover, so thousands
  of un-enrichable components joined an average that had barely any before.</p>
  <div class="tablecard"><table>
    <tr><th>Ecosystem</th><th class="num">Components</th><th class="num">Fields filled</th><th>Per component</th></tr>
    {purl_rows}
  </table></div>
</section>

<section>
  <h2>Augmentation</h2>
  <p class="note">Documents carrying each field, of {aug["after_n"]} compared. Supplier and
  manufacturer are expected to stay at zero: with no token the sbomify API provider skips itself,
  so this run exercises the local and VCS paths only. That is a limit of the harness, not a defect
  &mdash; recorded here rather than left to be inferred from a blank row.</p>
  <div class="tablecard"><table>{aug_rows}</table></div>
</section>

<section>
  <h2>Biggest movers</h2>
  <div class="tablecard"><table>
    <tr><th>Project</th><th>Stack</th><th class="num">Before</th><th class="num">After</th><th>Change</th></tr>
    {win_rows}
  </table></div>
</section>

<section>
  <h2>Coverage sweep &mdash; 249 newly added projects</h2>
  <p class="note">{"A second corpus, chosen against the gaps rather than by popularity: twelve ecosystems that had no coverage at all, the positive path of fixes whose negative path we had already measured, and a deliberate pile of monorepos. These have no baseline, so the question is not whether they improved but whether anything comes out at all." if V3 and V3["done"] else "Running now &mdash; results appear here as they land."}</p>
  <p class="note">{v3_header}</p>
  <div class="tablecard"><table>
    <tr><th>Ecosystem</th><th class="num">Run</th><th class="num">With SBOM</th><th class="num">Empty</th><th class="num">No input found</th><th class="num">Median comps</th></tr>
    {v3_rows or '<tr><td colspan="6" class="empty">No results yet.</td></tr>'}
  </table></div>
</section>

<footer>
  Updated {stamp}. Each of the 5 workers holds its own runtime cache, so no two projects share a
  Gradle journal &mdash; the contamination behind F16 that made the first survey's Java numbers
  unusable. Generation is not deterministic by design: it depends on third-party registries, so
  small component deltas are drift rather than evidence.
</footer>
</div>
'''

out = ROOT / "v2" / "dashboard.html"
out.write_text(html)
print(f"wrote {out} ({done}/{total} projects, {len(regressions)} regressions)")
