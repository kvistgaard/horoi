"""Draw an ontology's terms as an SVG diagram, from the ontology file.

Classes are boxes. A property is an arrow from its domain to its range, named
along the arrow, with "any resource" where it has none, and every property
has an arrow of its own. A subclass is a hollow-headed arrow, and a
sub-property is named after its property with "⊑". Nothing is placed by hand:
each property goes to a slot by the kind of its domain and range, so a change
to the ontology changes the drawing. A shape the slots don't cover raises
Undrawable rather than drawing something wrong, and the layout gets a new slot.

The slots are the same for every class on the spine: the class with the most
properties, its superclasses above it and one subclass below.

- Above and below a class is the class hierarchy alone, with the properties
  between two neighbours beside the subclass arrow.
- On the left are the values of no named class: any resource, then literals.
- On the right are the values of a named class. Self-loops come first,
  stacked rather than nested, so each name has a row of its own. Arrows to
  other classes, the ontology's own or another vocabulary's, come below them.
- A box grows with the lanes on its busier side.
- The properties with no domain start from an "any resource" node under the
  spine, which has the same sides as a class.
- A box on the right has its own self-loops on its right edge, and a box that
  two neighbouring rows reach is drawn once, spanning both.

The background is transparent, and the colours are CSS variables with a light
and a dark value, so the drawing works on either theme. A page that embeds it
can set the variables itself.
"""
import re
import sys
from collections import Counter, defaultdict
from html import escape

from rdflib import BNode, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SKOS, Namespace

from .axioms import common, expression, is_datatype, quantifier, restrictions, stated, union

VANN = Namespace("http://purl.org/vocab/vann/")


class Undrawable(Exception):
    """A shape of the ontology that the diagram's slots don't cover."""


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
CLASS_CHAR = 11.0    # and of a class's name
UNION_ROW = 22       # distance between the members of a union, one to a line

LIGHT = {"ink": "#111827", "muted": "#6B7280", "class": "#EA580C", "obj": "#2563EB",
         "data": "#16A34A", "any": "#9CA3AF", "fill": "#FFFFFF"}
DARK = {"ink": "#F3F4F6", "muted": "#9CA3AF", "class": "#FB923C", "obj": "#60A5FA",
        "data": "#4ADE80", "any": "#6B7280", "fill": "#1C1C1E"}


def ontology(g, onto=None):
    """The ontology a page documents: the one given, which is the first file's when
    an ontology comes in several files, else the one the file declares."""
    return onto if onto is not None else next(g.subjects(RDF.type, OWL.Ontology), None)


def namespace(g, onto=None):
    """The ontology's namespace and prefix: from its vann header, else the namespace
    most of its classes and properties share, else its own IRI."""
    onto = ontology(g, onto)
    ns = g.value(onto, VANN.preferredNamespaceUri) if onto is not None else None
    prefix = g.value(onto, VANN.preferredNamespacePrefix) if onto is not None else None
    if ns is None:
        if onto is None:
            sys.exit("horoi: the file declares no owl:Ontology")
        shared = Counter(re.match(r".*[#/]", str(s)).group() for kind in (OWL.Class, OWL.ObjectProperty, OWL.DatatypeProperty)
                         for s in g.subjects(RDF.type, kind) if isinstance(s, URIRef) and re.match(r".*[#/]", str(s)))
        if shared:
            ns = min(shared, key=lambda n: (-shared[n], n))
        else:
            ns = str(onto) if str(onto).endswith(("#", "/")) else str(onto) + "#"
    if prefix is None:
        prefix = str(ns).rstrip("#/").rsplit("/", 1)[-1].lower() or "ex"
    return str(ns), str(prefix)


def en(g, s, *props):
    """The first of these properties' values that is in English or in no language."""
    for p in props:
        for o in g.objects(s, p):
            if isinstance(o, Literal) and o.language in (None, "en"):
                return str(o)
    return None


def label(g, s):
    return en(g, s, RDFS.label, SKOS.prefLabel)


def local(iri, ns):
    return str(iri)[len(ns):] if str(iri).startswith(ns) else str(iri).rsplit("#", 1)[-1].rsplit("/", 1)[-1]


def name_of(g, iri, ns, prefix):
    if NAMES == "slug":
        return local(iri, ns)
    if NAMES == "curie":
        return f"{prefix}:{local(iri, ns)}"
    return label(g, iri) or local(iri, ns)


def term(g, iri, ns):
    """A class as the layout names it: its local name if it is the ontology's own,
    its CURIE if another vocabulary's, by a prefix the graph has, and its IRI if the
    graph has no prefix for it. None if there is none."""
    if iri is None:
        return None
    if str(iri).startswith(ns):
        return local(iri, ns)
    try:                                 # never a prefix of Horoi's own making, such as ns1
        pre, _, name = g.namespace_manager.compute_qname(str(iri), generate=False)
        return f"{pre}:{name}"
    except (KeyError, ValueError):
        return str(iri)


def read(g, onto=None):
    ns, prefix = namespace(g, onto)
    ours = lambda x: str(x).startswith(ns)
    classes = sorted(local(c, ns) for c in g.subjects(RDF.type, OWL.Class) if ours(c))
    props = []
    for kind in (OWL.ObjectProperty, OWL.DatatypeProperty):
        for p in g.subjects(RDF.type, kind):
            if not ours(p):
                continue
            doms, rngs = stated(g, p, RDFS.domain), stated(g, p, RDFS.range)
            if len(doms) > 1 or len(rngs) > 1:
                raise Undrawable(f"no slot for {local(p, ns)}, which states several domains or ranges")
            dom, rng = (doms or [None])[0], (rngs or [None])[0]
            if isinstance(dom, BNode) or isinstance(rng, BNode):
                raise Undrawable(f"no slot for {local(p, ns)}, whose domain or range is a class expression")
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
    for _, d in subclass:                # a superclass declared in another file, such as another module's
        labels.setdefault(d, name_of(g, URIRef(ns + d), ns, prefix))
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
            + self.lines(cx, cy, name) + '</g>')

    @staticmethod
    def lines(cx, cy, name):
        """A class's name, or the members of a union, one to a line."""
        parts = name.split("\n")
        if len(parts) == 1:
            return f'<text class="cn" x="{cx:.0f}" y="{cy + 7:.0f}" text-anchor="middle">{escape(name)}</text>'
        top = cy - UNION_ROW * (len(parts) - 1) / 2
        return "".join(f'<text class="un" x="{cx:.0f}" y="{top + i * UNION_ROW + 5:.0f}" text-anchor="middle">{escape(part)}</text>'
                       for i, part in enumerate(parts))

    def literal(self, cx, cy, h=SIDE_H):
        self.nodes.append(
            f'<rect class="l" x="{cx - SIDE_W / 2:.0f}" y="{cy - h / 2:.0f}" width="{SIDE_W}" height="{h:.0f}"/>'
            f'<text class="ln" x="{cx:.0f}" y="{cy + 5:.0f}" text-anchor="middle">literal</text>')

    def any(self, cx, cy, h=SIDE_H, tip="No range declared.", w=SIDE_W, text="any resource"):
        self.nodes.append(
            f'<g class="t"><title>{tip}</title>'
            f'<rect class="a" x="{cx - w / 2:.0f}" y="{cy - h / 2:.0f}" width="{w:.0f}" height="{h:.0f}" rx="7"/>'
            f'<text class="an" x="{cx:.0f}" y="{cy + 5:.0f}" text-anchor="middle">{text}</text></g>')

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
        ".cn{font-size:20px;font-weight:600;fill:var(--hr-ink)}.un{font-size:15px;font-weight:600;fill:var(--hr-ink)}"
        ".hit{fill:none;stroke:transparent;stroke-width:12}"
        ".l{fill:none;stroke:var(--hr-ink);stroke-width:1.8}.ln{font-size:15px;font-weight:600;fill:var(--hr-ink)}"
        ".a{fill:none;stroke:var(--hr-any);stroke-width:1.6;stroke-dasharray:6 5}"
        ".an{font-size:15px;font-style:italic;fill:var(--hr-muted)}"
        ".e{fill:none;stroke-width:1.7}.e.obj{stroke:var(--hr-obj)}.e.data{stroke:var(--hr-data)}.e.sub{stroke:var(--hr-class)}"
        ".pn{font-size:15.5px}.pn.obj{fill:var(--hr-obj)}.pn.data{fill:var(--hr-data)}"
        ".mo{fill:var(--hr-obj)}.md{fill:var(--hr-data)}.ms{fill:var(--hr-fill);stroke:var(--hr-class);stroke-width:1.4}")


def defs():
    """The arrowheads and the styles every drawing uses. A page with bare drawings holds them once."""
    return ('<defs><marker id="m-obj" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="9" markerHeight="9" orient="auto">'
            '<path class="mo" d="M0,0 L10,5 L0,10 z"/></marker>'
            '<marker id="m-data" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="9" markerHeight="9" orient="auto">'
            '<path class="md" d="M0,0 L10,5 L0,10 z"/></marker>'
            '<marker id="m-sub" viewBox="0 0 12 12" refX="11" refY="6" markerWidth="13" markerHeight="13" orient="auto">'
            '<path class="ms" d="M1,1 L11,6 L1,11 z"/></marker>'
            f'<style>{style()}</style></defs>')


def draw(g, onto=None):
    prefix, classes, labels, props, subclass = read(g, onto)
    if not classes:
        raise Undrawable("the ontology declares no class of its own")
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
        raise Undrawable("only one chain of subclasses, through the central class, has a slot")
    return layout(prefix, labels, spine, props, classes, "The terms of the ontology and how they connect")


def layout(prefix, labels, spine, props, classes, title, bare=False, curies=None):
    """Draw the spine with its properties. `classes` are those to draw even if nothing
    reaches them, `curies` the hover text of a box that is not one class, and a bare
    drawing leaves its markers and styles to the page."""
    curies = curies or {}
    # The rows: the classes of the spine, then any resource, for the properties with no domain.
    rows = spine + ([None] if any(p["domain"] is None for p in props) else [])
    at = {c: i for i, c in enumerate(rows)}

    left, loops, right = defaultdict(list), defaultdict(list), defaultdict(list)
    between = defaultdict(list)          # arrows between neighbours on the spine, by the upper one
    side_loops = defaultdict(list)       # self-loops of a class drawn on the right
    for p in props:
        d, r = p["domain"], p["range"]
        if d in at and r in ("literal", "expression", None):
            left[d].append(p)
        elif d in at and r == d:
            loops[d].append(p)
        elif d is not None and d in at and r in at and abs(at[d] - at[r]) == 1:
            between[min(d, r, key=at.get)].append(p)
        elif d in at and r not in at:
            right[d].append(p)
        elif d is not None and d == r:
            side_loops[d].append(p)
        else:
            raise Undrawable(f"no slot for {p['name']} ({d} -> {r})")
    reached = defaultdict(set)           # the rows that reach each box on the right
    for c in rows:
        for p in right[c]:
            reached[p["range"]].add(at[c])
    shared = {}                          # a box two neighbouring rows reach, by the upper row
    for t, ix in sorted(reached.items()):
        if len(ix) == 1:
            continue
        if len(ix) > 2 or max(ix) - min(ix) != 1:
            raise Undrawable(f"no slot for {t}, which rows that are not neighbours reach")
        if min(ix) in shared.values():
            raise Undrawable(f"no slot for {t}, a second class that the same two rows reach")
        shared[t] = min(ix)
    for c in side_loops:
        if c not in reached:
            raise Undrawable(f"no slot for the self-loops of {c}, which no row reaches")
    free = sorted(set(classes) - set(spine) - set(reached))     # classes no property reaches

    def curie(c):
        return c if ":" in c else f"{prefix}:{c}"

    def reach(ps):        # an arrow just long enough for its longest name
        return max((text_w(p["text"]) for p in ps), default=0) + 56

    def ext(ps):          # the height of a box beside a class, and of its arrows
        return max(SIDE_H, LANE * len(ps) + 12)

    def own_loops(t):     # the height a box on the right needs for its own self-loops, or for a union's members
        loops_h = LOOP_ROW * len(side_loops.get(t, [])) + 12 if t not in shared else 0
        lines = labels.get(t, t).count("\n") + 1
        return max(loops_h, UNION_ROW * lines + 14 if lines > 1 else 0)

    def box_ext(t, ps):   # the room a box on the right takes in its row
        return max(ext(ps), own_loops(t))

    def left_groups(c):
        """The boxes on the left of a row, top to bottom: any resource, class expressions, then literals."""
        by = defaultdict(list)
        for p in left[c]:
            by[p["range"]].append(p)
        return sorted(by.items(), key=lambda kv: (None, "expression", "literal").index(kv[0]))

    def groups(c):
        """The boxes on the right of a row, top to bottom: the box it shares with the row
        above, the classes by name, then the box it shares with the row below."""
        by = defaultdict(list)
        for p in right[c]:
            by[p["range"]].append(p)
        place = lambda t: 0 if shared.get(t) == at[c] - 1 else 2 if shared.get(t) == at[c] else 1
        return sorted(by.items(), key=lambda kv: (place(kv[0]), kv[0]))

    def left_block(c):    # the height of a row's left side
        gs = left_groups(c)
        return sum(ext(ps) for _, ps in gs) + GROUP_GAP * max(len(gs) - 1, 0)

    def block(c):         # the height of a row's right side: its loops, then its boxes
        gs = groups(c)
        gaps = max(len(gs) - 1, 0) + (1 if loops[c] and gs else 0)
        return LOOP_ROW * len(loops[c]) + sum(box_ext(t, ps) for t, ps in gs) + GROUP_GAP * gaps

    def box_h(c):         # a box grows with its busier side
        return max(BOX_H, max(left_block(c), block(c)) + 16)

    # Arrows between neighbours: the subclass arrow, then one lane per property.
    pairs = list(zip(spine[:-1], spine[1:]))
    xs = {u: [(i - len(between[u]) / 2) * 46 for i in range(len(between[u]) + 1)] for u, _ in pairs}
    cw = max([BOX_W] + [2 * (max(map(abs, xs[u])) + 24) for u, _ in pairs if between[u]]
             + [CLASS_CHAR * len(labels[c]) + 28 for c in spine])
    side_w = max([BOX_W] + [CLASS_CHAR * max(map(len, labels.get(t, t).split("\n"))) + 28 for t in reached])

    cx = W / 2
    all_left = [p for c in rows for p in left[c]]
    lx = cx - cw / 2 - reach(all_left) - SIDE_W / 2
    loop_reach = max((LOOP_W + GAP + text_w(p["text"]) + 24 for c in spine for p in loops[c]), default=0)
    tx = cx + cw / 2 + max(reach([p for c in rows for p in right[c]]), loop_reach)   # where the boxes on the right start

    s = Svg()
    lo, hi = (lx - SIDE_W / 2 if all_left else cx - cw / 2), cx + cw / 2

    def stack(x0, top, ps):
        """Self-loops down the right edge of a box, each name on its own row beside its loop."""
        nonlocal hi
        x1 = x0 + LOOP_W
        for p in ps:
            y0 = top + (LOOP_ROW - LOOP_H) / 2
            y1 = y0 + LOOP_H
            s.prop(f"M{x0:.0f},{y0:.0f} H{x1 - 6:.0f} Q{x1:.0f},{y0:.0f} {x1:.0f},{y0 + 6:.0f} "
                   f"V{y1 - 6:.0f} Q{x1:.0f},{y1:.0f} {x1 - 6:.0f},{y1:.0f} H{x0 + 2:.0f}", p,
                   x1 + GAP, (y0 + y1) / 2, beside=True)
            hi = max(hi, x1 + GAP + text_w(p["text"]))
            top += LOOP_ROW

    def side_box(t, top, bottom):
        """A box on the right, with its own self-loops centred on its right edge."""
        nonlocal hi
        s.cls(tx + side_w / 2, (top + bottom) / 2, labels.get(t, t), curies.get(t) or curie(t), side_w, bottom - top)
        ps = side_loops.get(t, [])
        stack(tx + side_w, (top + bottom) / 2 - LOOP_ROW * len(ps) / 2, ps)
        hi = max(hi, tx + side_w)

    y = 24
    span = {}
    spans = defaultdict(list)            # where the arrows of each row meet a shared box
    for i, c in enumerate(rows):
        h = box_h(c)
        cy = y + h / 2
        span[c] = (y, y + h)
        if c is None:
            s.any(cx, cy, h, "No domain declared.", cw)
        else:
            s.cls(cx, cy, labels[c], curie(c), cw, h)

        ly = cy - left_block(c) / 2
        for target, ps in left_groups(c):
            e = ext(ps)
            gy = ly + e / 2
            if target is None:
                s.any(lx, gy, e)
            elif target == "expression":
                s.any(lx, gy, e, "A class expression, written out on the card.", text="class expression")
            else:
                s.literal(lx, gy, e)
            for off, p in zip(lanes(len(ps)), ps):
                s.prop(f"M{cx - cw / 2:.0f},{gy + off:.0f} H{lx + SIDE_W / 2 + 2:.0f}", p,
                       (cx - cw / 2 + lx + SIDE_W / 2) / 2, gy + off)
            ly += e + GROUP_GAP

        x0 = cx + cw / 2
        ry = cy - block(c) / 2
        stack(x0, ry, loops[c])
        ry += LOOP_ROW * len(loops[c])
        if loops[c] and groups(c):
            ry += GROUP_GAP
        for target, ps in groups(c):
            e = box_ext(target, ps)
            gy = ry + e / 2
            bh = max(BOX_H, LANE * len(ps) + 12, own_loops(target))
            if target in shared:
                spans[target] += [gy - bh / 2, gy + bh / 2]
            else:
                side_box(target, gy - bh / 2, gy + bh / 2)
            for off, p in zip(lanes(len(ps)), ps):
                s.prop(f"M{x0:.0f},{gy + off:.0f} H{tx - 2:.0f}", p, (x0 + tx) / 2, gy + off)
            ry += e + GROUP_GAP

        if i + 1 < len(rows) and rows[i + 1] is None:
            y += h + 60
        elif i + 1 < len(rows):
            names = [text_w(p["text"]) for p in between[c]]
            y += h + max(70, max(names, default=0) + 40)
        else:
            y += h
    for t, ys in spans.items():
        side_box(t, min(ys), max(ys))

    for u, l in pairs:
        y0, y1 = span[u][1], span[l][0]
        s.arrow(f"M{cx + xs[u][0]:.0f},{y1:.0f} V{y0 + 2:.0f}", "sub")
        for i, p in enumerate(between[u]):
            a, b = (y0, y1 - 2) if p["domain"] == u else (y1, y0 + 2)
            s.prop(f"M{cx + xs[u][i + 1]:.0f},{a:.0f} V{b:.0f}", p, cx + xs[u][i + 1], (y0 + y1) / 2, vertical=True)

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
    return (f'<svg xmlns="http://www.w3.org/2000/svg" class="hr-diagram" viewBox="{x0:.0f} 0 {width:.0f} {total_h:.0f}" width="{width:.0f}" height="{total_h:.0f}" role="img" aria-label="{escape(title)}">\n'
            f'<title>{escape(title)}</title>\n' + ("" if bare else defs() + "\n")
            + "\n".join(s.edges + s.nodes + s.texts) + "\n</svg>\n")


def draw_class(g, cls, bare=True, onto=None):
    """One class with what its properties reach: the properties whose domain it is,
    and its restrictions, with its superclasses above it and theirs. None if the
    class has neither. A subclass is not drawn: the class's card lists them."""
    ns, prefix = namespace(g, onto)
    labels, curies = {}, {}

    def short(iri):
        return str(iri) if isinstance(iri, Literal) else f"{prefix}:{local(iri, ns)}" if str(iri).startswith(ns) else term(g, iri, ns)

    def box(iri):
        """The box a class or a union is drawn in, by its key."""
        if isinstance(iri, BNode):
            members = union(g, iri)
            key = " or ".join(term(g, m, ns) for m in members)
            labels[key] = "\n".join(("or " if i else "") + name_of(g, m, ns, prefix) for i, m in enumerate(members))
            curies[key] = " or ".join(short(m) for m in members)
            return key
        key = term(g, iri, ns)
        labels[key] = name_of(g, iri, ns, prefix) if str(iri).startswith(ns) else key
        return key

    def target(prop, values, data):
        """Where an arrow to these ranges or this filler goes. Several ranges, which OWL
        reads as their intersection, are a class expression."""
        if not values:
            return "literal" if data else None
        if data or any(is_datatype(g, v) for v in values):
            return "literal"
        filler = values[0]
        if len(values) > 1 or isinstance(filler, BNode) and not union(g, filler):
            return "expression"
        return box(filler)

    def edges(c):
        key, found = box(c), []
        for kind in (OWL.ObjectProperty, OWL.DatatypeProperty):
            for p in g.subjects(RDF.type, kind):
                data = kind == OWL.DatatypeProperty
                if c in common(g, stated(g, p, RDFS.domain)):
                    found.append({"name": local(p, ns), "text": name_of(g, p, ns, prefix), "curie": short(p), "data": data,
                                  "domain": key, "range": target(p, stated(g, p, RDFS.range), data), "super": []})
        for r in restrictions(g, c):
            p, (word, filler) = g.value(r, OWL.onProperty), quantifier(g, r)
            if isinstance(p, BNode) or word in ("value", "Self"):
                continue                 # an inverse, a single value, or itself: the card has them
            data = (p, RDF.type, OWL.DatatypeProperty) in g
            # a bare cardinality reaches the property's range
            values = [filler] if filler is not None else stated(g, p, RDFS.range)
            found.append({"name": local(p, ns), "text": f"{name_of(g, p, ns, prefix)} ({word})",
                          "curie": expression(g, r, short), "data": data or any(is_datatype(g, v) for v in values),
                          "domain": key, "range": target(p, values, data), "super": []})
        found = list({(e["name"], e["text"], str(e["range"]), e["curie"]): e for e in found}.values())    # stated twice, drawn once
        return sorted(found, key=lambda e: (e["name"], e["text"], str(e["range"])))

    chain = [cls]
    while True:
        above = [o for o in g.objects(chain[0], RDFS.subClassOf) if not isinstance(o, BNode) and str(o).startswith(ns)]
        if len(above) != 1 or above[0] in chain:
            break
        chain.insert(0, above[0])
    title = f"{name_of(g, cls, ns, prefix)} and what its properties reach"
    for spine in (chain, [cls]):         # with its superclasses if they fit, else alone
        props = [e for c in spine for e in edges(c)]
        if not props:
            return None
        try:
            return layout(prefix, labels, [box(c) for c in spine], props, [], title, bare, curies)
        except Undrawable:
            continue
    return None
