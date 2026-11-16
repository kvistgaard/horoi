"""Draw an ontology in the folded style, as an SVG, from the ontology file.

A class is a box with its name and a row per property whose domain it is, its
restrictions among them: the datatype properties under a thin line, then the
object properties under another. A row ends with "→ Range" only where the ontology
declares a range. The properties with no domain are the rows of an "any
resource" box. The only arrows are those of the class hierarchy.

Nothing is placed by hand. A superclass stands above its subclasses, which
share its arrowhead. More than three subclasses with none of their own hang
in columns under it, each on a rail. The trees go in rows, the largest first,
and the classes with neither a superclass nor a subclass after them, by name.
A class with several superclasses is placed under the first by name, and a
fainter arrow runs to each of the others.

An ontology of more than FULL classes is drawn with the names alone. Its
drawing for the page also holds a box per class, hidden, with the class's
rows and, under a line of their own, the properties that reach it. The page shows
that box when the class is clicked.
"""
import math
from collections import defaultdict
from html import escape

from rdflib import BNode, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS

from .axioms import expression, is_datatype, literal, quantifier, restrictions, union
from .diagram import Undrawable, local, name_of, namespace, style, term

FULL = 12            # the most classes drawn with their rows
ANY = "any resource"

HEAD = 40            # the height of a box's name
ROW = 23             # and of a row
PAD = 8              # above and below the rows of a compartment
MIN_W = 130
NAME_CHAR = 9.8      # average width of a character of a class's name
ROW_CHAR = 7.7       # and of a row
LONG = 64            # the most characters of a class expression in a row
RISE = 50            # between a class and its subclasses
BUS = 22             # how far above the subclasses their lines join
HGAP = 26            # between neighbours
VGAP = 10            # between the boxes of a column
RAIL = 20            # from a column's rail to its boxes
HANG = 6             # the most boxes in a column
SHELF = 44           # between rows of trees
MARGIN = 24

STYLE = (".uc{font-size:17px;font-weight:600;fill:var(--hr-ink)}"
         ".ur{font-size:14.5px}.ur.obj{fill:var(--hr-obj)}.ur.data{fill:var(--hr-data)}"
         ".ty{fill:var(--hr-ink)}.ty.no{fill:var(--hr-muted);font-style:italic}"
         ".sep{stroke:var(--hr-class);stroke-width:1}.sep.no{stroke:var(--hr-any)}"
         ".f{fill:var(--hr-fill)}.e.tree{stroke-linecap:square}.e.also{stroke-width:1.1;opacity:.4}"
         ".n{cursor:pointer}.n rect{pointer-events:all}.n:focus{outline:none}"
         ".n:hover rect,.n:focus-visible rect{stroke-width:3.2}"
         ".go{cursor:pointer}.go:hover,a:hover .uc{text-decoration:underline}"
         ".tree{transition:opacity .24s}.focus .tree{opacity:.2}")


def defs():
    return ('<defs><marker id="m-sub" viewBox="0 0 12 12" refX="11" refY="6" markerWidth="13" markerHeight="13" orient="auto">'
            '<path class="ms" d="M1,1 L11,6 L1,11 z"/></marker>'
            f'<style>{style()}{STYLE}</style></defs>')


def first(g, s, p):
    """One value of a property, the same at every build."""
    return min(g.objects(s, p), key=str, default=None)


def read(g, onto=None):
    """The boxes, by key: a class's IRI, a class expression's node, or ANY. Each has its
    name, its hover text, its rows and the rows that reach it. With them, each
    class's superclasses, and the classes that have a card on the page."""
    ns, prefix = namespace(g, onto)
    ours = lambda x: str(x).startswith(ns)
    classes = sorted({c for c in g.subjects(RDF.type, OWL.Class) if isinstance(c, URIRef) and ours(c)}, key=str)
    if not classes:
        raise Undrawable("the ontology declares no class of its own")

    def name(x):
        if isinstance(x, Literal):
            return literal(x)
        if isinstance(x, BNode):
            text = expression(g, x, name)
            return text if len(text) <= LONG else text[:LONG - 1].rstrip() + "…"
        return name_of(g, x, ns, prefix) if ours(x) else term(g, x, ns)

    def curie(x):
        if isinstance(x, Literal):
            return literal(x)
        return f"{prefix}:{local(x, ns)}" if ours(x) else term(g, x, ns)

    def range_of(filler, data):
        """What a row says after its colon, in parts joined by "or": each with the class it names, if any."""
        if filler is None:
            return []
        if isinstance(filler, BNode):
            return [(name(m), m) for m in union(g, filler)] or [(name(filler), None)]
        return [(name(filler), None if data or is_datatype(g, filler) else filler)]

    rows = defaultdict(list)

    def add(owner, p, data, filler, text, tip):
        parts = range_of(filler, data)
        said = " or ".join(t for t, _ in parts)
        if len(said) > LONG:             # a long union is cut short; the hover text and the card have it whole
            parts = [(said[:LONG - 1].rstrip() + "…", None)]
        rows[owner].append({"name": text, "data": data, "parts": parts, "type": " or ".join(t for t, _ in parts) or None,
                            "targets": [c for _, c in parts if c is not None], "tip": tip})

    for kind in (OWL.DatatypeProperty, OWL.ObjectProperty):
        for p in sorted({p for p in g.subjects(RDF.type, kind) if isinstance(p, URIRef)}, key=str):
            data = kind == OWL.DatatypeProperty
            parents = sorted((x for x in g.objects(p, RDFS.subPropertyOf) if isinstance(x, URIRef)), key=str)
            dom, rng = first(g, p, RDFS.domain), first(g, p, RDFS.range)
            for x in parents:            # a sub-property takes its parent's domain and range
                dom = dom if dom is not None else first(g, x, RDFS.domain)
                rng = rng if rng is not None else first(g, x, RDFS.range)
            owners = [ANY] if dom is None else union(g, dom) or [dom]
            if not ours(p) and not any(o in classes for o in owners):
                continue
            under = [x for x in parents if ours(x)]
            for owner in owners:
                add(owner, p, data, rng, name(p) + "".join(f" ⊑ {name(x)}" for x in under),
                    curie(p) + "".join(f" ⊑ {curie(x)}" for x in under))
    for c in classes:
        for r in restrictions(g, c):
            p, (word, filler) = g.value(r, OWL.onProperty), quantifier(g, r)
            if isinstance(p, BNode) or word in ("value", "Self"):
                continue                 # an inverse, a single value, or itself: the card has them
            data = (p, RDF.type, OWL.DatatypeProperty) in g
            if filler is None:           # a bare cardinality reaches the property's range
                filler = first(g, p, RDFS.range)
            add(c, p, data or (filler is not None and is_datatype(g, filler)), filler,
                f"{name(p)} ({word})", expression(g, r, curie))

    supers = {c: sorted((d for d in set(g.objects(c, RDFS.subClassOf))
                         if isinstance(d, URIRef) and d not in (c, OWL.Thing)), key=str) for c in classes}
    keys = list(dict.fromkeys(classes + sorted({d for ds in supers.values() for d in ds}, key=str)
                              + sorted((o for o in rows if o != ANY), key=str) + ([ANY] if ANY in rows else [])))
    boxes = {}
    for k in keys:
        mine = {(r["name"], r["type"], r["tip"]): r for r in rows.get(k, [])}      # stated twice, drawn once
        boxes[k] = {"name": ANY if k == ANY else name(k),
                    "tip": "No domain declared." if k == ANY else expression(g, k, curie),
                    "plain": isinstance(k, URIRef),
                    "out": sorted(mine.values(), key=lambda r: (not r["data"], r["name"].lower(), r["type"] or "")),
                    "in": []}
    for k in keys:
        for r in boxes[k]["out"]:
            for t in r["targets"]:
                if t in boxes and t != k:
                    boxes[t]["in"].append({"name": r["name"], "data": r["data"], "from": k, "tip": r["tip"]})
    for b in boxes.values():
        b["in"].sort(key=lambda r: (r["name"].lower(), boxes[r["from"]]["name"].lower()))
    cards = {c: local(c, ns) for c in classes}
    return boxes, supers, cards


def groups(box, rows, reached):
    """A box's rows in groups, each under a thin line: its datatype properties, its
    object properties, and the properties that reach it. A group with no rows is left out."""
    own = [[r for r in box["out"] if r["data"] == data] for data in (True, False)] if rows else []
    return [(part, back) for part, back in [(p, False) for p in own] + ([(box["in"], True)] if reached else []) if part]


def size(box, rows, reached):
    """A box's width and height: with its name alone, with its rows, or also with the rows that reach it."""
    w, h = max(MIN_W, NAME_CHAR * len(box["name"]) + 32), HEAD
    for part, _ in groups(box, rows, reached):
        w = max(w, max(ROW_CHAR * len(r["text"]) for r in part) + 28)
        h += 2 * PAD + ROW * len(part)
    return w, h


def clip(box, to):
    """Where the line from a box's centre to a point leaves the box."""
    x, y, w, h = box
    cx, cy = x + w / 2, y + h / 2
    dx, dy = to[0] - cx, to[1] - cy
    if not dx and not dy:
        return cx, cy
    k = min(w / 2 / abs(dx) if dx else math.inf, h / 2 / abs(dy) if dy else math.inf)
    return cx + dx * k, cy + dy * k


def draw(g, onto=None, page=True):
    """The ontology in the folded style. A drawing for the page of an ontology of more
    than FULL classes also holds the box the page shows for a clicked class."""
    boxes, supers, cards = read(g, onto)
    keys = list(boxes)
    at = {k: i for i, k in enumerate(keys)}
    full = sum(b["plain"] for b in boxes.values()) <= FULL
    for b in boxes.values():
        for r in b["out"]:
            r["text"] = r["name"] + (f" → {r['type']}" if r["type"] else "")
        for r in b["in"]:
            r["text"] = f"{r['name']} ← {boxes[r['from']]['name']}"
    sizes = {k: size(b, full, False) for k, b in boxes.items()}
    by_name = lambda k: (boxes[k]["name"].lower(), str(k))

    # Each class under its first superclass by name, unless that closes a circle.
    parent = {}
    for c in sorted(supers, key=by_name):
        for d in sorted(supers[c], key=by_name):
            x = d
            while x in parent and x != c:
                x = parent[x]
            if x != c:
                parent[c] = d
                break
    kids = defaultdict(list)
    for c in sorted(parent, key=by_name):
        kids[parent[c]].append(c)
    also = [(c, d) for c in sorted(supers, key=by_name) for d in supers[c] if parent.get(c) != d]

    dims = {}

    def measure(n):
        """The room a class takes with all under it, and the blocks under it: a subclass
        with its own tree, or a column of subclasses that have none."""
        w, h = sizes[n]
        leaves = [k for k in kids[n] if not kids[k]]
        hung = leaves if len(leaves) > 3 else []
        blocks = [([k], *measure(k), False) for k in kids[n] if k not in hung]
        per = math.ceil(len(hung) / math.ceil(len(hung) / HANG)) if hung else 0
        for i in range(0, len(hung), per or 1):
            col = hung[i:i + per]
            blocks.append((col, RAIL + max(sizes[k][0] for k in col),
                           sum(sizes[k][1] for k in col) + VGAP * (len(col) - 1), True))
        if blocks:
            row = sum(b[1] for b in blocks) + HGAP * (len(blocks) - 1)
            w, h = max(w, row), h + RISE + max(b[2] for b in blocks)
        dims[n] = (w, h, blocks)
        return w, h

    pos, edges = {}, []
    click = page and not full        # the page shows a clicked class's box

    def place(n, x, y):
        bw, _, blocks = dims[n]
        nw, nh = sizes[n]
        cx = x + bw / 2
        pos[n] = (cx - nw / 2, y, nw, nh)
        if not blocks:
            return
        bx = cx - (sum(b[1] for b in blocks) + HGAP * (len(blocks) - 1)) / 2
        top = y + nh + RISE
        bus, d, drops = top - BUS, "", [cx]
        for ks, w, _, column in blocks:
            if column:
                rail, ky = bx + 7, top
                for k in ks:             # a column: each box on a tick from the rail
                    pos[k] = (bx + RAIL, ky, w - RAIL, sizes[k][1])
                    d += f"M{rail:.0f},{ky + HEAD / 2:.0f} H{bx + RAIL:.0f}"
                    last = ky + HEAD / 2
                    ky += sizes[k][1] + VGAP
                d += f"M{rail:.0f},{last:.0f} V{bus:.0f}"
                drops.append(rail)
            else:
                place(ks[0], bx, top)
                d += f"M{bx + w / 2:.0f},{top:.0f} V{bus:.0f}"
                drops.append(bx + w / 2)
            bx += w + HGAP
        d += f"M{min(drops):.0f},{bus:.0f} H{max(drops):.0f}M{cx:.0f},{bus:.0f} V{y + nh + 2:.0f}"
        edges.append(f'<path class="e sub tree" d="{d}" marker-end="url(#m-sub)"/>')

    # The trees in rows, the largest first, then the classes on their own, by name.
    roots = [k for k in keys if k not in parent]
    for r in roots:
        measure(r)

    def count(n):
        return 1 + sum(count(k) for k in kids[n])
    trees = sorted((r for r in roots if kids[r]), key=lambda r: (-count(r), by_name(r)))
    lone = sorted((r for r in roots if not kids[r]), key=lambda r: (r == ANY, by_name(r)))
    cell = max((sizes[r][0] for r in lone), default=0)
    if not full:                         # names alone: the classes on their own in a grid
        for r in lone:
            sizes[r] = (cell, sizes[r][1])
            dims[r] = (cell, sizes[r][1], [])
    area = sum((dims[r][0] + HGAP) * (dims[r][1] + SHELF) for r in roots)
    limit = max([math.sqrt(area * 1.7)] + [dims[r][0] for r in roots])
    x = y = tall = 0
    for group, gap in ((trees, SHELF), (lone, SHELF if full else VGAP + 6)):
        if x:                            # the classes on their own start a row
            x, y, tall = 0, y + tall + SHELF, 0
        for r in group:
            w, h = dims[r][:2]
            if x and x + w > limit:
                x, y, tall = 0, y + tall + gap, 0
            place(r, x, y)
            x, tall = x + w + HGAP, max(tall, h)
    for c, d in also:                    # the other superclasses
        a, b = pos[c], pos[d]
        x0, y0 = clip(a, (b[0] + b[2] / 2, b[1] + b[3] / 2))
        x1, y1 = clip(b, (a[0] + a[2] / 2, a[1] + a[3] / 2))
        edges.append(f'<path class="e sub also" d="M{x0:.0f},{y0:.0f} L{x1:.0f},{y1:.0f}" marker-end="url(#m-sub)"/>')

    def rows_of(part, x, y, w, reached, plain):
        """A thin line, then a row per property."""
        out = [f'<path class="sep{"" if plain else " no"}" d="M{x:.0f},{y:.0f} H{x + w:.0f}"/>']
        for i, r in enumerate(part):
            if reached:
                k = r["from"]
                tail = (f'<tspan class="ty"> ← </tspan><tspan class="ty go{"" if k != ANY else " no"}" '
                        f'data-c="{at[k]}">{escape(boxes[k]["name"])}</tspan>')
            elif r["type"]:
                tail = '<tspan class="ty"> → </tspan>' + '<tspan class="ty"> or </tspan>'.join(
                    f'<tspan class="ty{f""" go" data-c="{at[c]}""" if click and c in at else ""}">{escape(text)}</tspan>'
                    for text, c in r["parts"])
            else:
                tail = ""
            out.append(f'<g class="t"><title>{escape(r["tip"])}</title><text class="ur {"data" if r["data"] else "obj"}" '
                       f'x="{x + 14:.0f}" y="{y + PAD + ROW * i + 16:.0f}">{escape(r["name"])}{tail}</text></g>')
        return "".join(out), 2 * PAD + ROW * len(part)

    def box(k, x, y, w, h, rows, reached, filled=False):
        b = boxes[k]
        shape, text = ("c", "uc") if b["plain"] else ("a", "an")
        name = (f'<g class="t"><title>{escape(b["tip"])}</title><text class="{text}" x="{x + w / 2:.0f}" y="{y + 26:.0f}" '
                f'text-anchor="middle">{escape(b["name"])}</text></g>')
        if filled and k in cards:        # in the box of a clicked class, the name leads to its card
            name = f'<a href="#{escape(cards[k])}">{name}</a>'
        out = (f'<rect class="{shape}{" f" if filled else ""}" x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" height="{h:.0f}" rx="7"/>' + name)
        top = y + HEAD
        for part, back in groups(b, rows, reached):
            drawn, used = rows_of(part, x, top, w, back, b["plain"])
            out, top = out + drawn, top + used
        return out

    nodes = []
    for k in keys:
        x, y, w, h = pos[k]
        if click:
            open_ = (f'<g class="n" data-c="{at[k]}" tabindex="0" role="button" aria-label="{escape(boxes[k]["name"])}">'
                     f'<title>{escape(boxes[k]["tip"])}</title>')
        else:
            open_ = '<g>'
        nodes.append(f'{open_}{box(k, x, y, w, h, full, False)}</g>')
    details = []
    if click:                            # the box of each class, over its place in the drawing
        for k in keys:
            x, y, w, h = pos[k]
            dw, dh = size(boxes[k], True, True)
            dx = x + w / 2 - dw / 2
            details.append(f'<g class="d" data-d="{at[k]}" data-box="{dx:.0f} {y:.0f} {dw:.0f} {dh:.0f}" display="none">'
                           f'{box(k, dx, y, dw, dh, True, True, True)}</g>')

    lo_x = min(p[0] for p in pos.values()) - MARGIN
    lo_y = min(p[1] for p in pos.values()) - MARGIN
    width = max(p[0] + p[2] for p in pos.values()) + MARGIN - lo_x
    height = max(p[1] + p[3] for p in pos.values()) + MARGIN - lo_y
    title = "The classes of the ontology, with their properties" if full else "The classes of the ontology"
    return (f'<svg xmlns="http://www.w3.org/2000/svg" class="hr-diagram folded" viewBox="{lo_x:.0f} {lo_y:.0f} {width:.0f} {height:.0f}" '
            f'width="{width:.0f}" height="{height:.0f}" role="img" aria-label="{title}">\n'
            f'<title>{title}</title>\n{defs()}\n<g class="tree">\n' + "\n".join(edges + nodes) + '\n</g>\n'
            + ('<g class="details">\n' + "\n".join(details) + '\n</g>\n' if details else "") + '</svg>\n')
