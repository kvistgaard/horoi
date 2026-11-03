"""Draw an ontology's terms as an SVG diagram, from the ontology file.

Classes are boxes. A property is an arrow from its domain to its range, named
along the arrow, with "any resource" where it has none, and every property
has an arrow of its own. A subclass is a hollow-headed arrow, and a
sub-property is named after its property with "⊑". Nothing is placed by hand:
each property goes to a slot by the kind of its domain and range, so a change
to the ontology changes the drawing. A shape the slots don't cover stops the script,
and the layout gets a new slot.

The slots are the same for every class on the spine: the class with the most
properties, its superclasses above it and one subclass below.

- Above and below a class is the class hierarchy alone, with the properties
  between two neighbours beside the subclass arrow.
- On the left are the values of no named class: any resource, then literals.
- On the right are the values of a named class. Self-loops come first,
  stacked rather than nested, so each name has a row of its own. Arrows to
  other classes, the ontology's own or another vocabulary's, come below them.
- A box grows with the lanes on its busier side.

The background is transparent, and the colours are CSS variables with a light
and a dark value, so the drawing works on either theme. A page that embeds it
can set the variables itself.
"""
import sys
from collections import defaultdict
from html import escape

from rdflib import Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, Namespace

VANN = Namespace("http://purl.org/vocab/vann/")


NAMES = "label"      # how a term is written: "label", "slug" or "curie"

W = 1100
BOX_W, BOX_H = 180, 52
SIDE_W, SIDE_H = 150, 56
LANE = 30            # distance between parallel arrows
LOOP_W, LOOP_H = 26, 18   # how far a self-loop reaches out from its class, and its height
LOOP_ROW = 30        # distance between stacked self-loops
GROUP_GAP = 12       # between the boxes on the right of one class
GAP = 7              # between an arrow and its name
CHAR = 8.0           # average width of a character of a property's name

LIGHT = {"ink": "#111827", "muted": "#6B7280", "class": "#EA580C", "obj": "#2563EB",
         "data": "#16A34A", "any": "#9CA3AF", "fill": "#FFFFFF"}
DARK = {"ink": "#F3F4F6", "muted": "#9CA3AF", "class": "#FB923C", "obj": "#60A5FA",
        "data": "#4ADE80", "any": "#6B7280", "fill": "#1C1C1E"}


def namespace(g):
    """The ontology's namespace and prefix, from its vann header, or guessed from its IRI."""
    onto = next(g.subjects(RDF.type, OWL.Ontology), None)
    ns = g.value(onto, VANN.preferredNamespaceUri) if onto is not None else None
    prefix = g.value(onto, VANN.preferredNamespacePrefix) if onto is not None else None
    if ns is None:
        if onto is None:
            sys.exit("horoi: the file declares no owl:Ontology")
        ns = str(onto) if str(onto).endswith(("#", "/")) else str(onto) + "#"
    if prefix is None:
        prefix = str(ns).rstrip("#/").rsplit("/", 1)[-1].lower() or "ex"
    return str(ns), str(prefix)


def local(iri, ns):
    return str(iri)[len(ns):] if str(iri).startswith(ns) else str(iri).rsplit("#", 1)[-1].rsplit("/", 1)[-1]


def name_of(g, iri, ns, prefix):
    if NAMES == "slug":
        return local(iri, ns)
    if NAMES == "curie":
        return f"{prefix}:{local(iri, ns)}"
    for o in g.objects(iri, RDFS.label):
        if isinstance(o, Literal) and o.language in (None, "en"):
            return str(o)
    return local(iri, ns)


def term(g, iri, ns):
    """A class as the layout names it: its local name if it is the ontology's own,
    its CURIE if another vocabulary's, and None if there is none."""
    if iri is None:
        return None
    if str(iri).startswith(ns):
        return local(iri, ns)
    try:
        pre, _, name = g.namespace_manager.compute_qname(str(iri))
        return f"{pre}:{name}"
    except ValueError:
        return str(iri)


def read(g):
    ns, prefix = namespace(g)
    ours = lambda x: str(x).startswith(ns)
    classes = sorted(local(c, ns) for c in g.subjects(RDF.type, OWL.Class) if ours(c))
    props = []
    for kind in (OWL.ObjectProperty, OWL.DatatypeProperty):
        for p in g.subjects(RDF.type, kind):
            if not ours(p):
                continue
            dom, rng = g.value(p, RDFS.domain), g.value(p, RDFS.range)
            supers = sorted((x for x in g.objects(p, RDFS.subPropertyOf) if ours(x)), key=str)
            props.append({
                "name": local(p, ns),
                "text": name_of(g, p, ns, prefix) + "".join(f" ⊑ {name_of(g, x, ns, prefix)}" for x in supers),
                "curie": f"{prefix}:{local(p, ns)}" + "".join(f" ⊑ {prefix}:{local(x, ns)}" for x in supers),
                "data": kind == OWL.DatatypeProperty,
                "domain": term(g, dom, ns),
                "range": "literal" if kind == OWL.DatatypeProperty else term(g, rng, ns),
                "super": [local(x, ns) for x in supers],
            })
    by = {p["name"]: p for p in props}
    for p in props:                      # a sub-property takes its parent's domain and range
        for x in p["super"]:
            p["domain"] = p["domain"] or by[x]["domain"]
            p["range"] = p["range"] or by[x]["range"]
    subclass = sorted((local(c, ns), local(d, ns)) for c in g.subjects(RDF.type, OWL.Class)
                      for d in g.objects(c, RDFS.subClassOf) if ours(c) and ours(d))
    labels = {c: name_of(g, URIRef(ns + c), ns, prefix) for c in classes}
    return prefix, classes, labels, sorted(props, key=lambda p: p["name"]), subclass


def text_w(text):
    return CHAR * len(text)


def lanes(n):
    return [(i - (n - 1) / 2) * LANE for i in range(n)]


class Svg:
    def __init__(self):
        self.edges, self.nodes, self.texts = [], [], []

    def cls(self, cx, cy, name, curie, w=BOX_W, h=BOX_H):
        self.nodes.append(
            f'<g class="t"><title>{escape(curie)}</title>'
            f'<rect class="c" x="{cx - w / 2:.0f}" y="{cy - h / 2:.0f}" width="{w:.0f}" height="{h:.0f}" rx="7"/>'
            f'<text class="cn" x="{cx:.0f}" y="{cy + 7:.0f}" text-anchor="middle">{escape(name)}</text></g>')

    def literal(self, cx, cy, h=SIDE_H):
        self.nodes.append(
            f'<rect class="l" x="{cx - SIDE_W / 2:.0f}" y="{cy - h / 2:.0f}" width="{SIDE_W}" height="{h:.0f}"/>'
            f'<text class="ln" x="{cx:.0f}" y="{cy + 5:.0f}" text-anchor="middle">literal</text>')

    def any(self, cx, cy, h=SIDE_H, tip="No range declared."):
        self.nodes.append(
            f'<g class="t"><title>{tip}</title>'
            f'<rect class="a" x="{cx - SIDE_W / 2:.0f}" y="{cy - h / 2:.0f}" width="{SIDE_W}" height="{h:.0f}" rx="7"/>'
            f'<text class="an" x="{cx:.0f}" y="{cy + 5:.0f}" text-anchor="middle">any resource</text></g>')

    def arrow(self, d, kind):
        self.edges.append(f'<path class="e {kind}" d="{d}" marker-end="url(#m-{kind})"/>')

    def prop(self, d, p, x, y, vertical=False, beside=False):
        """An arrow, and its name along it: above a horizontal arrow, left of a vertical one,
        and to the right of a self-loop. Hovering either shows the property's CURIE."""
        kind = "data" if p["data"] else "obj"
        t = escape(p["text"])
        if beside:
            name = f'<text class="pn {kind}" x="{x:.1f}" y="{y + 5:.1f}" text-anchor="start">{t}</text>'
        elif vertical:
            name = (f'<text class="pn {kind}" x="{x - GAP:.1f}" y="{y:.1f}" text-anchor="middle" '
                    f'transform="rotate(-90 {x - GAP:.1f} {y:.1f})">{t}</text>')
        else:
            name = f'<text class="pn {kind}" x="{x:.1f}" y="{y - GAP:.1f}" text-anchor="middle">{t}</text>'
        self.edges.append(
            f'<g class="t"><title>{escape(p["curie"])}</title><path class="hit" d="{d}"/>'
            f'<path class="e {kind}" d="{d}" marker-end="url(#m-{kind})"/>{name}</g>')


def style():
    def vars_(c):
        return ";".join(f"--hr-{k}:{v}" for k, v in c.items())
    return (
        f"svg{{{vars_(LIGHT)}}}"
        f"@media (prefers-color-scheme:dark){{svg{{{vars_(DARK)}}}}}"
        "text{font-family:Inter,'Segoe UI',system-ui,-apple-system,'Helvetica Neue',Arial,sans-serif}"
        ".c{fill:none;stroke:var(--hr-class);stroke-width:2}"
        ".cn{font-size:20px;font-weight:600;fill:var(--hr-ink)}"
        ".hit{fill:none;stroke:transparent;stroke-width:12}"
        ".l{fill:none;stroke:var(--hr-ink);stroke-width:1.8}.ln{font-size:15px;font-weight:600;fill:var(--hr-ink)}"
        ".a{fill:none;stroke:var(--hr-any);stroke-width:1.6;stroke-dasharray:6 5}"
        ".an{font-size:15px;font-style:italic;fill:var(--hr-muted)}"
        ".e{fill:none;stroke-width:1.7}.e.obj{stroke:var(--hr-obj)}.e.data{stroke:var(--hr-data)}.e.sub{stroke:var(--hr-class)}"
        ".pn{font-size:15.5px}.pn.obj{fill:var(--hr-obj)}.pn.data{fill:var(--hr-data)}"
        ".mo{fill:var(--hr-obj)}.md{fill:var(--hr-data)}.ms{fill:var(--hr-fill);stroke:var(--hr-class);stroke-width:1.4}")


def draw(g):
    prefix, classes, labels, props, subclass = read(g)
    count = defaultdict(int)
    for p in props:
        if p["domain"]:
            count[p["domain"]] += 1
    centre = max(classes, key=lambda c: (count[c], c))

    # The spine: the central class, its superclasses above it and one subclass below.
    supers = defaultdict(list)
    for c, d in subclass:
        supers[c].append(d)
    spine = [centre]
    while len(supers[spine[0]]) == 1 and supers[spine[0]][0] not in spine:
        spine.insert(0, supers[spine[0]][0])
    children = sorted(c for c, d in subclass if d == centre)
    spine += children[:1]
    if len(children) > 1 or set(subclass) != set(zip(spine[1:], spine[:-1])):
        sys.exit("horoi: only one chain of subclasses, through the central class, has a slot")
    at = {c: i for i, c in enumerate(spine)}

    left, loops, right = defaultdict(list), defaultdict(list), defaultdict(list)
    between = defaultdict(list)          # arrows between neighbours on the spine, by the upper one
    ups = defaultdict(list)              # arrows from any resource up to a class off the spine
    for p in props:
        d, r = p["domain"], p["range"]
        if d in at and r in ("literal", None):
            left[d].append(p)
        elif d in at and r == d:
            loops[d].append(p)
        elif d in at and r in at and abs(at[d] - at[r]) == 1:
            between[min(d, r, key=at.get)].append(p)
        elif d in at and r not in at:
            right[d].append(p)
        elif d is None and r in classes and r not in at:
            ups[r].append(p)
        else:
            sys.exit(f"horoi: no slot for {p['name']} ({d} -> {r})")
    owner = {}
    for c in spine:
        for p in right[c]:
            if p["range"] is not None and owner.setdefault(p["range"], c) != c:
                sys.exit(f"horoi: no slot for {p['range']}, which two classes of the spine reach")
    if ups and (len(ups) > 1 or spine[0] != centre or set(ups) & set(owner)):
        sys.exit("horoi: only one class reached from any resource, with no class above the central one, has a slot")
    free = sorted(set(classes) - set(spine) - set(owner) - set(ups))     # classes no property reaches

    def curie(c):
        return c if ":" in c else f"{prefix}:{c}"

    def reach(ps):        # an arrow just long enough for its longest name
        return max((text_w(p["text"]) for p in ps), default=0) + 56

    def ext(ps):          # the height of a box beside a class, and of its arrows
        return max(SIDE_H, LANE * len(ps) + 12)

    def left_groups(c):
        """The boxes on the left of a class, top to bottom: any resource, then literals."""
        by = defaultdict(list)
        for p in left[c]:
            by[p["range"]].append(p)
        if c == centre and ups:
            by.setdefault(None, [])
        return sorted(by.items(), key=lambda kv: kv[0] is not None)

    def groups(c):
        """The boxes on the right of a class, top to bottom: the classes by name."""
        by = defaultdict(list)
        for p in right[c]:
            by[p["range"]].append(p)
        return sorted(by.items())

    def left_block(c):    # the height of a class's left side
        gs = left_groups(c)
        return sum(ext(ps) for _, ps in gs) + GROUP_GAP * max(len(gs) - 1, 0)

    def block(c):         # the height of a class's right side: its loops, then its boxes
        gs = groups(c)
        gaps = max(len(gs) - 1, 0) + (1 if loops[c] and gs else 0)
        return LOOP_ROW * len(loops[c]) + sum(ext(ps) for _, ps in gs) + GROUP_GAP * gaps

    def box_h(c):         # a box grows with its busier side
        return max(BOX_H, max(left_block(c), block(c)) + 16)

    # Arrows between neighbours: the subclass arrow, then one lane per property.
    pairs = list(zip(spine[:-1], spine[1:]))
    xs = {u: [(i - len(between[u]) / 2) * 46 for i in range(len(between[u]) + 1)] for u, _ in pairs}
    cw = max([BOX_W] + [2 * (max(map(abs, xs[u])) + 24) for u, _ in pairs if between[u]])

    cx = W / 2
    all_left = [p for c in spine for p in left[c]]
    lx = cx - cw / 2 - reach(all_left) - SIDE_W / 2
    loop_reach = max((LOOP_W + GAP + text_w(p["text"]) + 24 for c in spine for p in loops[c]), default=0)
    tx = cx + cw / 2 + max(reach([p for c in spine for p in right[c]]), loop_reach)   # where the boxes on the right start

    s = Svg()
    lo, hi = (lx - SIDE_W / 2 if all_left or ups else cx - cw / 2), cx + cw / 2
    up_len = max((text_w(p["text"]) for ps in ups.values() for p in ps), default=0)
    y = 24 + (BOX_H + up_len + 60 if ups else 0)
    span, any_box = {}, {}
    for i, c in enumerate(spine):
        h = box_h(c)
        cy = y + h / 2
        span[c] = (y, y + h)
        s.cls(cx, cy, labels[c], curie(c), cw, h)

        ly = cy - left_block(c) / 2
        for target, ps in left_groups(c):
            e = ext(ps)
            gy = ly + e / 2
            if target is None:
                tip = ("No range declared." if not (c == centre and ups)
                       else "No domain or range declared." if ps else "No domain declared.")
                s.any(lx, gy, e, tip)
                any_box[c] = (lx, gy - e / 2)
            else:
                s.literal(lx, gy, e)
            for off, p in zip(lanes(len(ps)), ps):
                s.prop(f"M{cx - cw / 2:.0f},{gy + off:.0f} H{lx + SIDE_W / 2 + 2:.0f}", p,
                       (cx - cw / 2 + lx + SIDE_W / 2) / 2, gy + off)
            ly += e + GROUP_GAP

        # Self-loops stack down the right edge, each name on its own row beside its loop.
        x0, x1 = cx + cw / 2, cx + cw / 2 + LOOP_W
        ry = cy - block(c) / 2
        for p in loops[c]:
            y0 = ry + (LOOP_ROW - LOOP_H) / 2
            y1 = y0 + LOOP_H
            s.prop(f"M{x0:.0f},{y0:.0f} H{x1 - 6:.0f} Q{x1:.0f},{y0:.0f} {x1:.0f},{y0 + 6:.0f} "
                   f"V{y1 - 6:.0f} Q{x1:.0f},{y1:.0f} {x1 - 6:.0f},{y1:.0f} H{x0 + 2:.0f}", p,
                   x1 + GAP, (y0 + y1) / 2, beside=True)
            hi = max(hi, x1 + GAP + text_w(p["text"]))
            ry += LOOP_ROW
        if loops[c] and groups(c):
            ry += GROUP_GAP
        for target, ps in groups(c):
            e = ext(ps)
            gy = ry + e / 2
            w = BOX_W
            s.cls(tx + w / 2, gy, labels.get(target, target), curie(target), w, max(BOX_H, LANE * len(ps) + 12))
            for off, p in zip(lanes(len(ps)), ps):
                s.prop(f"M{x0:.0f},{gy + off:.0f} H{tx - 2:.0f}", p, (x0 + tx) / 2, gy + off)
            hi = max(hi, tx + w)
            ry += e + GROUP_GAP

        if i < len(pairs):
            names = [text_w(p["text"]) for p in between[c]]
            y += h + max(70, max(names, default=0) + 40)
        else:
            y += h

    for u, l in pairs:
        y0, y1 = span[u][1], span[l][0]
        s.arrow(f"M{cx + xs[u][0]:.0f},{y1:.0f} V{y0 + 2:.0f}", "sub")
        for i, p in enumerate(between[u]):
            a, b = (y0, y1 - 2) if p["domain"] == u else (y1, y0 + 2)
            s.prop(f"M{cx + xs[u][i + 1]:.0f},{a:.0f} V{b:.0f}", p, cx + xs[u][i + 1], (y0 + y1) / 2, vertical=True)

    if ups:
        target, up = next(iter(ups.items()))
        bx, btop = any_box[centre]
        ty = 24 + BOX_H / 2
        s.cls(bx, ty, labels[target], curie(target))
        for off, p in zip(lanes(len(up)), up):
            s.prop(f"M{bx + off:.0f},{btop:.0f} V{ty + BOX_H / 2 + 2:.0f}", p,
                   bx + off, (btop + ty + BOX_H / 2) / 2, vertical=True)
        lo, hi = min(lo, bx - BOX_W / 2), max(hi, bx + BOX_W / 2)

    height = y
    if free:                             # a row of their own, under the rest
        fy = height + 60 + BOX_H / 2
        step = BOX_W + 30
        first = cx - (len(free) - 1) * step / 2
        for i, c in enumerate(free):
            s.cls(first + i * step, fy, labels[c], curie(c))
        lo, hi = min(lo, first - BOX_W / 2), max(hi, first + (len(free) - 1) * step + BOX_W / 2)
        height = fy + BOX_H / 2

    total_h = height + 24
    x0 = lo - 24
    width = hi + 24 - x0
    defs = ('<marker id="m-obj" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="9" markerHeight="9" orient="auto">'
            '<path class="mo" d="M0,0 L10,5 L0,10 z"/></marker>'
            '<marker id="m-data" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="9" markerHeight="9" orient="auto">'
            '<path class="md" d="M0,0 L10,5 L0,10 z"/></marker>'
            '<marker id="m-sub" viewBox="0 0 12 12" refX="11" refY="6" markerWidth="13" markerHeight="13" orient="auto">'
            '<path class="ms" d="M1,1 L11,6 L1,11 z"/></marker>')
    title = "The terms of the ontology and how they connect"
    return (f'<svg xmlns="http://www.w3.org/2000/svg" class="hr-diagram" viewBox="{x0:.0f} 0 {width:.0f} {total_h:.0f}" width="{width:.0f}" height="{total_h:.0f}" role="img" aria-label="{title}">\n'
            f'<title>{title}</title>\n<defs>{defs}<style>{style()}</style></defs>\n'
            + "\n".join(s.edges + s.nodes + s.texts) + "\n</svg>\n")
