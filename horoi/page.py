"""Write an ontology's documentation page, one self-contained HTML file.

The page holds the ontology's header, the diagram from diagram.py, a card per
term with its definition, domain and range, an optional example in Turtle,
and links to the ontology in four serialisations. Every word about a term
comes from the ontology file.
"""
import re
from html import escape
from urllib.parse import quote

from rdflib import Literal, Namespace
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS

from .diagram import DARK, LIGHT, draw, namespace

REPO = "https://github.com/kvistgaard/horoi"
SDO = Namespace("https://schema.org/")
FORMATS = [(".ttl", "Turtle"), (".rdf", "RDF/XML"), (".jsonld", "JSON-LD"), (".nt", "N-Triples")]
DARK_CSS = ("--bg:#121212; --panel:#1A1A1A; --ink:#ECECEC; --muted:#A3A3A3; --faint:#737373; --line:#2E2E2E; "
            "--accent:#FB923C; --accent-soft:#2A1D14; --blue:#60A5FA; --blue-soft:#172131; --green:#4ADE80; "
            "--green-soft:#15261B; --code:#1F1F1F;")


def svg_vars(colours):
    return ";".join(f"--hr-{k}:{v}" for k, v in colours.items()) + ";"


def local(iri, ns):
    return str(iri)[len(ns):] if str(iri).startswith(ns) else str(iri).rsplit("#", 1)[-1].rsplit("/", 1)[-1]


def en(g, s, p):
    for o in g.objects(s, p):
        if isinstance(o, Literal) and o.language in (None, "en"):
            return str(o)
    return None


def licence_name(iri):
    m = re.match(r"https?://creativecommons\.org/licenses/([a-z-]+)/([\d.]+)/?$", str(iri))
    return f"CC {m.group(1).upper()} {m.group(2)}" if m else str(iri)


def agent(g, iri):
    name = en(g, iri, SDO.name)
    return f'<a href="{escape(str(iri))}">{escape(name or str(iri))}</a>'


def favicon(prefix):
    svg = ("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'>"
           "<rect width='32' height='32' rx='6' fill='#EA580C'/>"
           "<text x='16' y='22' text-anchor='middle' font-family='Segoe UI,Arial,sans-serif' "
           f"font-size='{17 if len(prefix) < 3 else 12}' font-weight='700' fill='white'>{escape(prefix[:4])}</text></svg>")
    return "data:image/svg+xml," + quote(svg)


class Page:
    def __init__(self, g):
        self.g = g
        self.ns, self.prefix = namespace(g)

    def ref(self, iri):
        if iri is None:
            return '<span class="chip any">any resource</span>'
        if iri == "literal":
            return '<span class="chip lit">literal</span>'
        if str(iri).startswith(self.ns):
            n = local(iri, self.ns)
            return f'<a class="chip" href="#{n}">{escape(self.prefix)}:{escape(n)}</a>'
        return f'<span class="chip ext">{escape(str(iri))}</span>'

    def turtle_html(self, text):
        out = []
        for line in escape(text).split("\n"):
            line = re.sub(r"(&quot;.*?&quot;)", r'<span class="s">\1</span>', line)
            line = re.sub(r"(@prefix|\ba\b)", r'<span class="k">\1</span>', line)
            line = re.sub(rf"\b({re.escape(self.prefix)}:[A-Za-z0-9_-]+)", r'<span class="t">\1</span>', line)
            out.append(line)
        return "\n".join(out)

    def card(self, t, kind):
        g, ref = self.g, self.ref
        n = local(t, self.ns)
        label = en(g, t, RDFS.label) or n
        definition = en(g, t, RDFS.comment) or ""
        rows = []
        if kind == "class":
            supers = list(g.objects(t, RDFS.subClassOf))
            subs = sorted(g.subjects(RDFS.subClassOf, t), key=str)
            dom = sorted(g.subjects(RDFS.domain, t), key=str)
            rng = sorted(g.subjects(RDFS.range, t), key=str)
            if supers:
                rows.append(("Subclass of", " ".join(ref(o) for o in supers)))
            if subs:
                rows.append(("Subclasses", " ".join(ref(o) for o in subs)))
            if dom:
                rows.append(("Properties from it", " ".join(ref(o) for o in dom)))
            if rng:
                rows.append(("Properties to it", " ".join(ref(o) for o in rng)))
            badge = "class"
        else:
            datatype = (t, RDF.type, OWL.DatatypeProperty) in g
            supers = list(g.objects(t, RDFS.subPropertyOf))
            dom, rng = g.value(t, RDFS.domain), g.value(t, RDFS.range)
            for s in supers:
                dom = dom if dom is not None else g.value(s, RDFS.domain)
                rng = rng if rng is not None else g.value(s, RDFS.range)
            rng = rng if rng is not None else ("literal" if datatype else None)
            rows.append(("Connects", f'{ref(dom)}<span class="arrow">→</span><code>{escape(n)}</code>'
                                     f'<span class="arrow">→</span>{ref(rng)}'))
            if supers:
                rows.append(("Sub-property of", " ".join(ref(o) for o in supers)))
            subs = sorted(g.subjects(RDFS.subPropertyOf, t), key=str)
            if subs:
                rows.append(("Sub-properties", " ".join(ref(o) for o in subs)))
            badge = "datatype property" if datatype else "object property"
        facts = "".join(f"<dt>{k}</dt><dd>{v}</dd>" for k, v in rows)
        return (f'<article class="term" id="{escape(n)}">'
                f'<header><h3>{escape(n)}</h3><span class="badge {badge.split()[0]}">{badge}</span></header>'
                f'<p class="iri">{escape(str(t))}<span class="lbl">label “{escape(label)}”</span></p>'
                f'<p class="def">{escape(definition)}</p><dl>{facts}</dl></article>')

    def render(self, svg, stem, example=None, version_links=""):
        g = self.g
        onto = next(g.subjects(RDF.type, OWL.Ontology))
        title = en(g, onto, DCTERMS.title) or en(g, onto, RDFS.label) or "Ontology"
        desc = en(g, onto, DCTERMS.description) or en(g, onto, RDFS.comment) or ""
        version = str(g.value(onto, OWL.versionInfo) or "")
        modified = str(g.value(onto, DCTERMS.modified) or "")
        licence = g.value(onto, DCTERMS.license)
        creators = [agent(g, c) for c in g.objects(onto, DCTERMS.creator)]
        contributors = [agent(g, c) for c in g.objects(onto, DCTERMS.contributor)]

        def ours(kind):
            return [s for s in g.subjects(RDF.type, kind) if str(s).startswith(self.ns)]
        key = lambda s: local(s, self.ns).lower()
        classes = sorted(ours(OWL.Class), key=key)
        props = sorted(ours(OWL.ObjectProperty) + ours(OWL.DatatypeProperty), key=key)

        def link(t):
            n = local(t, self.ns)
            return (f'<a href="#{escape(n)}" title="{escape(self.prefix)}:{escape(n)}">'
                    f'{escape(en(g, t, RDFS.label) or n)}</a>')
        by_label = lambda s: (en(g, s, RDFS.label) or local(s, self.ns)).lower()
        nav = ('<p class="navh">Classes</p>' + "".join(link(c) for c in sorted(classes, key=by_label))
               + '<p class="navh">Properties</p>' + "".join(link(p) for p in sorted(props, key=by_label)))
        meta = [("Version", escape(version)), ("Modified", escape(modified))]
        if creators:
            meta.append(("Creator", ", ".join(creators)))
        if contributors:
            meta.append(("Contributor", ", ".join(contributors)))
        if licence is not None:
            meta.append(("Licence", f'<a href="{escape(str(licence))}">{escape(licence_name(licence))}</a>'))
        meta_html = "".join(f"<div><dt>{k}</dt><dd>{v}</dd></div>" for k, v in meta if v)
        downloads = "".join(f'<a class="dl" href="{stem}{ext}" download><span>{label}</span><code>{stem}{ext}</code></a>'
                            for ext, label in FORMATS)
        example_html = (f'<section id="example"><h2>Example</h2><pre>{self.turtle_html(example.strip())}</pre></section>'
                        if example else "")
        example_nav = '<a href="#example">Example</a>' if example else ""
        svg_inline = re.sub(r'\s(width|height)="\d+"', "", svg, count=2)

        return TEMPLATE.format(
            title=escape(title), desc=escape(desc), version=escape(version), ns=escape(self.ns),
            prefix=escape(self.prefix), favicon=favicon(self.prefix), stem=escape(stem), credit=f' · generated by <a href="{REPO}">horoi</a>',
            meta=meta_html, nav=nav, svg=svg_inline,
            classes="".join(self.card(c, "class") for c in classes),
            props="".join(self.card(p, "property") for p in props),
            example=example_html, example_nav=example_nav, downloads=downloads, versions=version_links,
            ncls=len(classes), nprop=len(props), dark=DARK_CSS, svg_light=svg_vars(LIGHT), svg_dark=svg_vars(DARK))


def write(g, folder, stem, example=None, version_links=""):
    """Write index.html and <stem>.svg into folder."""
    svg = draw(g)
    (folder / f"{stem}.svg").write_text(svg, encoding="utf-8", newline="\n")
    html = Page(g).render(svg, stem, example, version_links)
    (folder / "index.html").write_text(html, encoding="utf-8", newline="\n")


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} {version}</title>
<meta name="description" content="{desc}">
<link rel="icon" href="{favicon}">
<link rel="alternate" type="text/turtle" href="{stem}.ttl">
<style>
:root {{ color-scheme:light dark;
  --bg:#FFFFFF; --panel:#FFFFFF; --ink:#111827; --muted:#4B5563; --faint:#9CA3AF; --line:#E5E7EB;
  --accent:#EA580C; --accent-soft:#FFF1E8; --blue:#2563EB; --blue-soft:#EEF4FF; --green:#16A34A; --green-soft:#ECFBF1; --code:#F6F7F9;
  --mono:ui-monospace,"Cascadia Mono",Consolas,"SF Mono",Menlo,monospace;
  --sans:Inter,"Segoe UI",system-ui,-apple-system,"Helvetica Neue",Arial,sans-serif; }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ {dark} }} }}
:root[data-theme="dark"] {{ {dark} }}
:root[data-theme="light"] svg.hr-diagram {{ {svg_light} }}
:root[data-theme="dark"] svg.hr-diagram {{ {svg_dark} }}
* {{ box-sizing:border-box; }}
html {{ scroll-behavior:smooth; scroll-padding-top:84px; }}
body {{ margin:0; background:var(--bg); color:var(--ink); font:16px/1.6 var(--sans); }}
a {{ color:var(--accent); text-decoration:none; }} a:hover {{ text-decoration:underline; }}
code {{ font-family:var(--mono); font-size:.9em; }}
.top {{ position:sticky; top:0; z-index:5; display:flex; align-items:center; gap:14px; padding:12px 28px;
  background:color-mix(in srgb, var(--bg) 85%, transparent); backdrop-filter:blur(10px); border-bottom:1px solid var(--line); }}
.mark {{ width:30px; height:30px; border-radius:6px; background:#EA580C; display:grid; place-items:center; color:#fff;
  font:700 15px var(--sans); }}
.top .name {{ font-size:21px; font-weight:400; letter-spacing:-.2px; align-self:baseline; }}
.top .v {{ font:500 12px var(--mono); color:var(--muted); border:1px solid var(--line); padding:2px 8px; border-radius:4px; align-self:baseline; }}
.top nav {{ margin-left:auto; display:flex; gap:20px; font-size:14px; align-items:center; }} .top nav a {{ color:var(--muted); }}
#theme {{ border:none; background:transparent; color:var(--muted); border-radius:4px; width:32px; height:28px;
  cursor:pointer; font-size:15px; line-height:1; }}
.wrap {{ display:grid; grid-template-columns:230px minmax(0,1fr); gap:40px; max-width:1240px; margin:0 auto; padding:36px 28px 80px; }}
aside {{ position:sticky; top:90px; align-self:start; max-height:calc(100vh - 110px); overflow:auto; }}
aside input {{ width:100%; padding:8px 11px; border:1px solid var(--line); border-radius:4px; background:var(--panel);
  color:var(--ink); font:14px var(--sans); margin-bottom:14px; }}
aside a {{ display:block; padding:3px 10px; border-radius:4px; color:var(--muted); font:13.5px var(--mono); }}
aside a:hover {{ background:var(--accent-soft); color:var(--accent); text-decoration:none; }}
.navh {{ margin:14px 0 4px; font:700 11px var(--sans); letter-spacing:1.6px; text-transform:uppercase; color:var(--faint); }}
main section {{ margin-bottom:56px; }}
h1 {{ font-size:44px; line-height:1.1; letter-spacing:-.8px; margin:0 0 14px; font-weight:600; }}
h2 {{ font-size:13px; letter-spacing:2px; text-transform:uppercase; color:var(--accent); margin:0 0 18px; }}
.lead {{ font-size:20px; color:var(--muted); max-width:760px; margin:0 0 28px; }}
.ns {{ display:flex; align-items:center; gap:12px; flex-wrap:wrap; background:var(--panel); border:1px solid var(--line);
  border-radius:6px; padding:12px 16px; margin-bottom:16px; }}
.ns .p {{ font:700 13px var(--mono); color:var(--accent); background:var(--accent-soft); padding:3px 9px; border-radius:4px; }}
.ns code {{ font-size:15px; }} .ns button {{ margin-left:auto; border:1px solid var(--line); background:transparent; color:var(--muted);
  border-radius:4px; padding:5px 11px; font:13px var(--sans); cursor:pointer; }}
.meta {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; margin:0; }}
.meta div {{ background:var(--panel); border:1px solid var(--line); border-radius:6px; padding:11px 14px; }}
.meta dt {{ font-size:12px; color:var(--faint); }} .meta dd {{ margin:2px 0 0; font-weight:600; }}
.diagram {{ border:1px solid var(--line); border-radius:6px; padding:16px; overflow:auto; }}
.diagram svg {{ display:block; width:100%; height:auto; min-width:640px; }}
.cap {{ font-size:14px; color:var(--muted); margin-top:10px; }}
.term {{ background:var(--panel); border:1px solid var(--line); border-radius:6px; padding:20px 22px; margin-bottom:14px; }}
.term:target {{ border-color:var(--accent); box-shadow:0 0 0 3px var(--accent-soft); }}
.term header {{ display:flex; align-items:center; gap:12px; }}
.term h3 {{ margin:0; font:600 20px var(--mono); }}
.badge {{ font-size:12px; font-weight:600; padding:2px 8px; border-radius:4px; background:var(--accent-soft); color:var(--accent); }}
.badge.datatype {{ background:var(--green-soft); color:var(--green); }} .badge.object {{ background:var(--blue-soft); color:var(--blue); }}
.iri {{ margin:6px 0 12px; font:13px var(--mono); color:var(--faint); }} .iri .lbl {{ font-family:var(--sans); margin-left:12px; }}
.def {{ font-size:17.5px; margin:0 0 6px; }}
.term dl {{ display:grid; grid-template-columns:150px 1fr; gap:8px 16px; margin:16px 0 0; padding-top:14px; border-top:1px dashed var(--line); }}
.term dt {{ font-size:13px; color:var(--faint); padding-top:3px; }} .term dd {{ margin:0; display:flex; flex-wrap:wrap; gap:6px; align-items:center; }}
.chip {{ font:13px var(--mono); padding:2px 8px; border-radius:4px; background:var(--accent-soft); color:var(--accent); }}
.chip.any {{ background:var(--code); color:var(--muted); font-style:italic; font-family:var(--sans); }}
.chip.lit {{ background:var(--code); color:var(--ink); font-family:var(--sans); }}
.chip.ext {{ background:var(--code); color:var(--muted); }}
.arrow {{ color:var(--faint); }}
pre {{ background:var(--code); border:1px solid var(--line); border-radius:6px; padding:16px 18px; overflow:auto;
  font:13.5px/1.6 var(--mono); }}
pre .k {{ color:var(--faint); }} pre .s {{ color:var(--green); }} pre .t {{ color:var(--blue); font-weight:600; }}
.dls {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:12px; }}
.dl {{ background:var(--panel); border:1px solid var(--line); border-radius:6px; padding:12px 16px; color:var(--ink); }}
.dl:hover {{ border-color:var(--accent); text-decoration:none; }} .dl span {{ display:block; font-weight:600; }}
.dl code {{ color:var(--muted); }}
footer {{ border-top:1px solid var(--line); padding:24px 28px; color:var(--faint); font-size:13px; text-align:center; }}
@media (max-width:900px) {{ .wrap {{ grid-template-columns:1fr; padding:24px 16px 60px; }} aside {{ display:none; }}
  .top nav a {{ display:none; }} h1 {{ font-size:34px; }} .term dl {{ grid-template-columns:1fr; }} }}
</style>
</head>
<body>
<div class="top"><span class="mark">{prefix}</span><span class="name">{title}</span><span class="v">{version}</span>
<nav><a href="#diagram">Diagram</a><a href="#classes">Classes</a><a href="#properties">Properties</a>{example_nav}<a href="#download">Download</a><button id="theme" type="button" title="Switch between light and dark" aria-label="Switch between light and dark">◐</button></nav></div>
<div class="wrap">
<aside><input id="q" type="search" placeholder="Find a term" aria-label="Find a term">{nav}</aside>
<main>
<section id="top">
<h1>{title}</h1>
<p class="lead">{desc}</p>
<div class="ns"><span class="p">{prefix}:</span><code id="nsiri">{ns}</code><button id="copy" type="button">Copy</button></div>
<dl class="meta">{meta}</dl>
</section>
<section id="diagram"><h2>Diagram</h2><div class="diagram">{svg}</div>
<p class="cap">{ncls} classes and {nprop} properties, drawn from <a href="{stem}.ttl">{stem}.ttl</a>; also as <a href="{stem}.svg">{stem}.svg</a>.</p></section>
<section id="classes"><h2>Classes</h2>{classes}</section>
<section id="properties"><h2>Properties</h2>{props}</section>
{example}
<section id="download"><h2>Download</h2><div class="dls">{downloads}</div>{versions}</section>
</main>
</div>
<footer>{title} {version}{credit}</footer>
<script>
(() => {{
  const root = document.documentElement, key = 'horoi-theme';
  try {{ const t = localStorage.getItem(key); if (t) root.dataset.theme = t; }} catch (e) {{}}
  document.getElementById('theme').addEventListener('click', () => {{
    const dark = root.dataset.theme ? root.dataset.theme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
    root.dataset.theme = dark ? 'light' : 'dark';
    try {{ localStorage.setItem(key, root.dataset.theme); }} catch (e) {{}}
  }});
}})();
const q = document.getElementById('q');
q.addEventListener('input', () => {{
  const s = q.value.toLowerCase();
  document.querySelectorAll('aside a').forEach(a => a.style.display = (a.textContent + ' ' + a.title).toLowerCase().includes(s) ? '' : 'none');
}});
document.getElementById('copy').addEventListener('click', e => {{
  navigator.clipboard.writeText(document.getElementById('nsiri').textContent).then(() => {{ e.target.textContent = 'Copied'; }});
}});
</script>
</body>
</html>
"""
