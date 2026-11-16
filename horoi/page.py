"""Write an ontology's documentation page, one self-contained HTML file.

The page holds the ontology's header, the diagram from diagram.py, a card per
term with its definition, domain and range, an optional example in Turtle,
and links to the ontology in four serialisations. Every word about a term
comes from the ontology file.
"""
import os
import re
import sys
from html import escape
from typing import Callable, NamedTuple
from urllib.parse import quote

from rdflib import BNode, Literal, Namespace
from rdflib.collection import Collection
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS, SKOS

from .axioms import expression, literal, members, union
from . import folded
from .diagram import DARK, LIGHT, Undrawable, defs, draw, draw_class, en, label, namespace, ontology

REPO = "https://github.com/kvistgaard/horoi"
SDO = Namespace("https://schema.org/")
FORMATS = [(".ttl", "Turtle"), (".rdf", "RDF/XML"), (".jsonld", "JSON-LD"), (".nt", "N-Triples")]
DARK_CSS = ("--bg:#121212; --panel:#1A1A1A; --ink:#ECECEC; --muted:#A3A3A3; --faint:#737373; --section:#7D7D7D; --line:#2E2E2E; "
            "--accent:#FB923C; --accent-soft:#2A1D14; --blue:#60A5FA; --blue-soft:#172131; --green:#4ADE80; "
            "--green-soft:#15261B; --code:#1F1F1F;")


VANN = Namespace("http://purl.org/vocab/vann/")
# The properties of an ontology that the Metadata section names in words, in the order it lists them.
METADATA = [(DCTERMS.title, "Title"), (RDFS.label, "Label"), (SKOS.prefLabel, "Label"), (DCTERMS.description, "Description"),
            (SKOS.definition, "Definition"), (RDFS.comment, "Comment"), (OWL.versionInfo, "Version"),
            (OWL.versionIRI, "Version IRI"), (OWL.priorVersion, "Prior version"),
            (OWL.backwardCompatibleWith, "Compatible with"), (OWL.incompatibleWith, "Incompatible with"),
            (DCTERMS.created, "Created"), (DCTERMS.issued, "Issued"), (DCTERMS.modified, "Modified"),
            (DCTERMS.creator, "Creator"), (DCTERMS.contributor, "Contributor"), (DCTERMS.publisher, "Publisher"),
            (DCTERMS.license, "Licence"), (DCTERMS.rights, "Rights"), (DCTERMS.bibliographicCitation, "Citation"),
            (DCTERMS.source, "Source"), (VANN.preferredNamespaceUri, "Namespace"),
            (VANN.preferredNamespacePrefix, "Prefix"), (OWL.imports, "Imports"), (DCTERMS.hasPart, "Parts"),
            (SKOS.historyNote, "History note"), (SKOS.scopeNote, "Scope note"), (RDFS.seeAlso, "See also")]


# The properties of a term that its card's "More statements" names in words.
STATEMENTS = dict(METADATA) | {
    RDF.type: "Type", RDFS.isDefinedBy: "Defined by", SKOS.altLabel: "Alternative label", SKOS.example: "Example",
    SKOS.note: "Note", SKOS.editorialNote: "Editorial note", SKOS.changeNote: "Change note",
    OWL.inverseOf: "Inverse of", OWL.disjointWith: "Disjoint with", OWL.propertyDisjointWith: "Disjoint with",
    OWL.disjointUnionOf: "Disjoint union of", OWL.propertyChainAxiom: "Property chain", OWL.hasKey: "Key",
    OWL.equivalentProperty: "Equivalent to", OWL.deprecated: "Deprecated"}
KINDS = {"class": OWL.Class, "object property": OWL.ObjectProperty, "datatype property": OWL.DatatypeProperty}


def svg_vars(colours):
    return ";".join(f"--hr-{k}:{v}" for k, v in colours.items()) + ";"


def local(iri, ns):
    return str(iri)[len(ns):] if str(iri).startswith(ns) else str(iri).rsplit("#", 1)[-1].rsplit("/", 1)[-1]


def version_of(g, onto=None):
    """The ontology's version: its owl:versionInfo, else the x.y.z that ends its owl:versionIRI."""
    onto = ontology(g, onto)
    if onto is None:
        return None
    v = g.value(onto, OWL.versionInfo)
    if isinstance(v, Literal):
        return str(v)
    m = re.search(r"\d+\.\d+\.\d+$", str(g.value(onto, OWL.versionIRI) or ""))
    return m.group() if m else None


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


def title_of(g, onto):
    return en(g, onto, DCTERMS.title, RDFS.label, SKOS.prefLabel)


def modules(g, onto):
    """An ontology's modules: the ontology itself first, then, by title, every other
    ontology among the files that terms are rdfs:isDefinedBy. None if there is no other."""
    parts = {m for m in g.subjects(RDF.type, OWL.Ontology) if m != onto and (None, RDFS.isDefinedBy, m) in g} if onto is not None else set()
    if not parts:
        return []
    return [onto] + sorted(parts, key=lambda m: ((title_of(g, m) or "").lower(), str(m)))


def definitions(g, t):
    """A term's definitions in English or no language, from the first property that
    has one: one, as a rule, but several where modules define a term differently."""
    for p in (SKOS.definition, RDFS.comment):
        found = sorted({str(o) for o in g.objects(t, p) if isinstance(o, Literal) and o.language in (None, "en")})
        if found:
            return found
    return []


def in_words(parts):
    """'a', 'a and b', 'a, b and c'."""
    return " and ".join(filter(None, [", ".join(parts[:-1]), "".join(parts[-1:])]))


class Group(NamedTuple):
    """Terms the page lists together. The sidebar, the header, the main sections
    and the diagram's caption all take their wording from these two names."""
    one: str            # "property shape", for a count of one
    many: str           # "property shapes", for its title, its anchor and other counts
    terms: list
    facts: Callable     # a term -> its badge, and the rows of its card

    @property
    def title(self):
        return self.many.capitalize()

    @property
    def anchor(self):
        return self.many.replace(" ", "-")

    @property
    def count(self):
        return f"{len(self.terms)} {self.one if len(self.terms) == 1 else self.many}"


class Page:
    def __init__(self, g, onto=None):
        self.g = g
        self.onto = ontology(g, onto)
        self.ns, self.prefix = namespace(g, self.onto)
        self.class_diagrams = False     # set when the ontology has no diagram of the whole
        self.cards = {t for group in self.groups() for t in group.terms}
        self.modules = modules(g, self.onto)

    def home(self, t):
        """The module whose heading a term's card stands under: the first, in page order,
        that the term is rdfs:isDefinedBy, else the ontology itself."""
        declared = set(self.g.objects(t, RDFS.isDefinedBy))
        return next((m for m in self.modules if m in declared), self.modules[0])

    def module_anchor(self, m):
        return "module-" + local(m, self.ns)

    def module_link(self, m):
        return f'<a class="chip" href="#{escape(self.module_anchor(m))}">{escape(title_of(self.g, m) or local(m, self.ns))}</a>'

    def groups(self):
        """What this ontology lists, in page order. A group with no terms doesn't appear."""
        def ours(*kinds):               # each once, though modules may type a term differently
            return list(dict.fromkeys(s for kind in kinds for s in self.g.subjects(RDF.type, kind) if str(s).startswith(self.ns)))
        return [Group("class", "classes", ours(OWL.Class), self.class_facts),
                Group("property", "properties", ours(OWL.ObjectProperty, OWL.DatatypeProperty), self.property_facts)]

    def ref(self, iri, missing="range"):
        if iri is None:
            return f'<span class="chip any" title="No {missing} declared.">any resource</span>'
        if iri == "literal":
            return '<span class="chip lit">literal</span>'
        if isinstance(iri, BNode):          # a class expression: a union is shown by its members
            return " or ".join(self.ref(m) for m in union(self.g, iri)) or self.axiom(iri)
        if str(iri).startswith(self.ns):
            n = local(iri, self.ns)
            if iri in self.cards:
                return f'<a class="chip" href="#{n}">{escape(self.prefix)}:{escape(n)}</a>'
            # a term of the namespace with no card on this page, such as another module's
            return f'<span class="chip ext" title="{escape(str(iri))}">{escape(self.prefix)}:{escape(n)}</span>'
        return f'<span class="chip ext">{escape(str(iri))}</span>'

    def having(self, p, t):
        """The properties whose domain or range, p, is this class or a union with it."""
        return sorted({s for s, o in self.g.subject_objects(p) if o == t or t in union(self.g, o)}, key=str)

    def short(self, node):
        """A term inside an axiom: a link to its card, or its CURIE, or a literal's value."""
        if isinstance(node, Literal):
            return f'<span class="chip lit">{escape(literal(node))}</span>'
        if str(node).startswith(self.ns):
            return self.ref(node)
        try:
            pre, _, name = self.g.namespace_manager.compute_qname(str(node), generate=False)
            return f'<span class="chip ext" title="{escape(str(node))}">{escape(pre)}:{escape(name)}</span>'
        except (KeyError, ValueError):
            return f'<span class="chip ext">{escape(str(node))}</span>'

    def axiom(self, node):
        return f'<span class="ax">{expression(self.g, node, self.short)}</span>'

    def axioms(self, t, p):
        """A class's superclasses or equivalents that are expressions, one to a line,
        with the members of an intersection on lines of their own."""
        lines = []
        for o in self.g.objects(t, p):
            if isinstance(o, BNode):
                parts = members(self.g, o, OWL.intersectionOf) or [o]
                texts = [x for _, _, x in sorted((isinstance(m, BNode), re.sub(r"<[^>]+>", "", x), x) for m in parts
                                                 for x in [expression(self.g, m, self.short, len(parts) > 1)])]
                lines.append("".join(f'<span class="ax">{"and " if i else ""}{x}</span>' for i, x in enumerate(texts)))
            elif p != RDFS.subClassOf:
                lines.append(f'<span class="ax">{self.ref(o)}</span>')
        # an axiom that several modules state is shown once
        return "".join(sorted(dict.fromkeys(lines), key=lambda s: re.sub(r"<[^>]+>", "", s)))

    def metadata(self):
        """Everything the ontology states about itself, a row per property: those with
        a name in words first, in their order, then the others by CURIE."""
        g, known = self.g, dict(METADATA)
        order = {p: i for i, (p, _) in enumerate(METADATA)}

        def curie(p):
            try:
                pre, _, name = g.namespace_manager.compute_qname(str(p), generate=False)
                return f"{pre}:{name}"
            except (KeyError, ValueError):
                return str(p)

        def value(p, o):
            if isinstance(o, Literal):
                text = "\n".join(line.strip() for line in str(o).strip().splitlines())
                if re.fullmatch(r"https?://\S+", text):     # an address given as text
                    return f'<a href="{escape(text)}">{escape(text)}</a>'
                lang = f' <span class="lang">@{escape(o.language)}</span>' if o.language not in (None, "en") else ""
                return escape(text) + lang
            if o in self.modules:
                return self.module_link(o)
            if en(g, o, SDO.name):
                return agent(g, o)
            text = licence_name(o) if p == DCTERMS.license else str(o)
            return f'<a href="{escape(str(o))}">{escape(text)}</a>'

        props = sorted({p for p in g.predicates(self.onto) if p != RDF.type}, key=lambda p: (order.get(p, len(order)), curie(p)))
        rows = []
        for p in props:
            values = sorted((o for o in g.objects(self.onto, p) if not isinstance(o, BNode)), key=str)
            if values:
                name = escape(known[p]) if p in known else f"<code>{escape(curie(p))}</code>"
                rows.append(f'<dt title="{escape(curie(p))}">{name}</dt><dd>' + "<br>".join(value(p, o) for o in values) + "</dd>")
        if not rows:
            return ""
        return ('<section id="metadata"><details><summary><h2>Metadata</h2></summary>'
                f'<dl class="md">{"".join(rows)}</dl></details></section>')

    def more(self, t, badge):
        """What a term states beyond what its card already shows, a row per property,
        folded under "More statements". Nothing if there is nothing more."""
        g = self.g
        # The page is the ontology's, so a term defined by it, or by its version, says nothing more.
        shown = {(RDF.type, KINDS.get(badge)), (RDFS.isDefinedBy, self.onto), (RDFS.isDefinedBy, g.value(self.onto, OWL.versionIRI))}
        skip = {RDFS.subClassOf, OWL.equivalentClass} if badge == "class" else {RDFS.domain, RDFS.range, RDFS.subPropertyOf}
        if self.modules:
            skip.add(RDFS.isDefinedBy)
        name = label(g, t)
        for p in (RDFS.label, SKOS.prefLabel):      # the label the card is headed with
            used = {(p, o) for o in g.objects(t, p) if isinstance(o, Literal) and o.language in (None, "en") and str(o) == name}
            if used:
                shown |= used
                break
        for p in (SKOS.definition, RDFS.comment):   # and its definitions
            used = {(p, o) for o in g.objects(t, p) if isinstance(o, Literal) and o.language in (None, "en")}
            if used:
                shown |= used
                break

        def curie(x):
            try:
                pre, _, local_name = g.namespace_manager.compute_qname(str(x), generate=False)
                return f"{pre}:{local_name}"
            except (KeyError, ValueError):
                return str(x)

        def value(o):
            if isinstance(o, Literal):
                text = "\n".join(line.strip() for line in str(o).strip().splitlines())
                if re.fullmatch(r"https?://\S+", text):
                    return f'<a href="{escape(text)}">{escape(text)}</a>'
                lang = f' <span class="lang">@{escape(o.language)}</span>' if o.language not in (None, "en") else ""
                return escape(text) + lang
            if isinstance(o, BNode):
                if (o, RDF.first, None) in g:        # a list
                    return ", ".join(filter(None, (value(m) for m in Collection(g, o))))
                text = expression(g, o, self.short)
                return None if text == "a class expression" else text
            if str(o).startswith(self.ns):
                return self.ref(o)
            return f'<a href="{escape(str(o))}">{escape(curie(o))}</a>'

        order = {p: i for i, p in enumerate(STATEMENTS)}
        rows = []
        for p in sorted(set(g.predicates(t)) - skip, key=lambda p: (order.get(p, len(order)), curie(p))):
            values = [v for v in (value(o) for o in sorted(g.objects(t, p), key=str) if (p, o) not in shown) if v]
            if values:
                head = escape(STATEMENTS[p]) if p in STATEMENTS else f"<code>{escape(curie(p))}</code>"
                rows.append(f'<dt title="{escape(curie(p))}">{head}</dt><dd>' + "".join(f'<span class="v">{v}</span>' for v in values) + "</dd>")
        if not rows:
            return ""
        return f'<details class="more"><summary>More statements</summary><dl>{"".join(rows)}</dl></details>'

    def turtle_html(self, text):
        out = []
        for line in escape(text).split("\n"):
            line = re.sub(r"(&quot;.*?&quot;)", r'<span class="s">\1</span>', line)
            line = re.sub(r"(@prefix|\ba\b)", r'<span class="k">\1</span>', line)
            line = re.sub(rf"\b({re.escape(self.prefix)}:[A-Za-z0-9_-]+)", r'<span class="t">\1</span>', line)
            out.append(line)
        return "\n".join(out)

    def class_facts(self, t):
        g, ref = self.g, self.ref
        rows = []
        supers = [o for o in g.objects(t, RDFS.subClassOf) if not isinstance(o, BNode)]
        subs = sorted(g.subjects(RDFS.subClassOf, t), key=str)
        dom, rng = self.having(RDFS.domain, t), self.having(RDFS.range, t)
        restricted, same = self.axioms(t, RDFS.subClassOf), self.axioms(t, OWL.equivalentClass)
        if supers or restricted:
            rows.append(("Subclass of", " ".join(ref(o) for o in supers) + restricted))
        if same:
            rows.append(("Equivalent to", same))
        if subs:
            rows.append(("Subclasses", " ".join(ref(o) for o in subs)))
        if dom:
            rows.append(("Domain of", " ".join(ref(o) for o in dom)))
        if rng:
            rows.append(("Range of", " ".join(ref(o) for o in rng)))
        return "class", rows

    def property_facts(self, t):
        g, ref = self.g, self.ref
        n = local(t, self.ns)
        rows = []
        datatype = (t, RDF.type, OWL.DatatypeProperty) in g
        supers = list(g.objects(t, RDFS.subPropertyOf))
        dom, rng = g.value(t, RDFS.domain), g.value(t, RDFS.range)
        for s in supers:
            dom = dom if dom is not None else g.value(s, RDFS.domain)
            rng = rng if rng is not None else g.value(s, RDFS.range)
        rng = rng if rng is not None else ("literal" if datatype else None)
        rows.append(("Connects", f'{ref(dom, "domain")}<span class="edge"><span class="arrow">–</span><code>{escape(n)}</code>'
                                 f'<span class="arrow">→</span></span>{ref(rng)}'))
        if supers:
            rows.append(("Sub-property of", " ".join(ref(o) for o in supers)))
        subs = sorted(g.subjects(RDFS.subPropertyOf, t), key=str)
        if subs:
            rows.append(("Sub-properties", " ".join(ref(o) for o in subs)))
        return "datatype property" if datatype else "object property", rows

    def card(self, t, facts):
        g = self.g
        n = local(t, self.ns)
        name = label(g, t) or n
        defs = "".join(f'<p class="def">{escape(d)}</p>' for d in definitions(g, t)) or '<p class="def"></p>'
        badge, rows = facts(t)
        if self.modules:                # the other modules that declare the term
            home, declared = self.home(t), set(g.objects(t, RDFS.isDefinedBy))
            also = [m for m in self.modules if m in declared and m != home]
            if also:
                rows = rows + [("Also in", " ".join(self.module_link(m) for m in also))]
        dl = "".join(f"<dt>{k}</dt><dd>{v}</dd>" for k, v in rows)
        drawing = draw_class(g, t, onto=self.onto) if self.class_diagrams and badge == "class" else None
        drawing = f'<div class="diagram own">{drawing}</div>' if drawing else ""
        return (f'<article class="term" id="{escape(n)}">'
                f'<header><h3>{escape(n)}</h3><span class="badge {badge.split()[0]}">{badge}</span></header>'
                f'<p class="iri">{escape(str(t))}<span class="lbl">label “{escape(name)}”</span></p>'
                f'{defs}<dl>{dl}</dl>{self.more(t, badge)}{drawing}</article>')

    def render(self, svg, stem, example=None, version_links="", files=None, per_class=True):
        """files: the names of the ontology's files, without .ttl, the first file's
        first; [stem] for an ontology in one file. per_class: whether an ontology
        with no diagram of the whole gets one on each class's card."""
        g, onto, files = self.g, self.onto, files or [stem]
        title = en(g, onto, DCTERMS.title, RDFS.label, SKOS.prefLabel) or "Ontology"
        desc = en(g, onto, DCTERMS.description, SKOS.definition, RDFS.comment) or ""
        version = version_of(g, onto) or ""
        modified = str(g.value(onto, DCTERMS.modified) or "")
        licence = g.value(onto, DCTERMS.license)
        creators = [agent(g, c) for c in g.objects(onto, DCTERMS.creator)]
        contributors = [agent(g, c) for c in g.objects(onto, DCTERMS.contributor)]
        groups = [group for group in self.groups() if group.terms]
        self.class_diagrams = per_class and not svg

        def link(t):
            n = local(t, self.ns)
            return (f'<a href="#{escape(n)}" title="{escape(self.prefix)}:{escape(n)}">'
                    f'{escape(label(g, t) or n)}</a>')

        def sidebar(group):
            links = "".join(link(t) for t in sorted(group.terms, key=lambda s: (label(g, s) or local(s, self.ns)).lower()))
            return f'<div class="group"><p class="navh">{group.title}</p>{links}</div>'

        def section(group):
            cards = "".join(self.card(t, group.facts) for t in sorted(group.terms, key=lambda s: local(s, self.ns).lower()))
            return f'<section id="{group.anchor}"><h2>{group.title}</h2>{cards}</section>'
        meta = [("Version", escape(version)), ("Modified", escape(modified))]
        if creators:
            meta.append(("Creator", ", ".join(creators)))
        if contributors:
            meta.append(("Contributor", ", ".join(contributors)))
        if licence is not None:
            meta.append(("Licence", escape(str(licence)) if isinstance(licence, Literal)     # a licence in words
                         else f'<a href="{escape(str(licence))}">{escape(licence_name(licence))}</a>'))
        meta_html = "".join(f"<div><dt>{k}</dt><dd>{v}</dd></div>" for k, v in meta if v)
        downloads = "".join(f'<a class="dl" href="{stem}{ext}" download><span>{label}</span><code>{stem}{ext}</code></a>'
                            for ext, label in FORMATS)
        extra_css = ""                  # only for pages of several files or modules, so others stay as they were
        if len(files) > 1:              # a row per file, with its four formats
            downloads = '<table class="dlt">' + "".join(
                f'<tr><td><code>{escape(f)}</code></td>'
                + "".join(f'<td><a href="{escape(f)}{ext}" download>{label}</a></td>' for ext, label in FORMATS) + '</tr>'
                for f in files) + '</table>'
            extra_css += MULTI_CSS
        nav = "".join(sidebar(group) for group in groups)
        group_links = "".join(f'<a href="#{group.anchor}">{group.title}</a>' for group in groups)
        sections = "\n".join(section(group) for group in groups)
        if self.modules:
            extra_css += MODULE_CSS
            homes = {t: self.home(t) for t in self.cards}
            parts = [(m, [group._replace(terms=[t for t in group.terms if homes[t] == m]) for group in groups])
                     for m in self.modules]
            parts = [(m, [group for group in gs if group.terms]) for m, gs in parts]

            def overview():
                rows = "".join(
                    f'<tr><td>{self.module_link(m)}</td>'
                    + "".join(f'<td>{len(next((x.terms for x in gs if x.many == group.many), []))}</td>' for group in groups)
                    + '</tr>' for m, gs in parts)
                heads = "".join(f'<th>{group.title}</th>' for group in groups)
                return f'<section id="modules"><h2>Modules</h2><table class="mods"><tr><th>Module</th>{heads}</tr>{rows}</table></section>'

            def module(m, gs):
                anchor, mdesc = self.module_anchor(m), en(g, m, DCTERMS.description, SKOS.definition, RDFS.comment)
                mmeta = [("Version", escape(version_of(g, m) or "")), ("Terms", in_words([x.count for x in gs]))]
                body = "".join(
                    f'<div id="{escape(anchor)}-{x.anchor}"><h3 class="grp">{x.title}</h3>'
                    + "".join(self.card(t, x.facts) for t in sorted(x.terms, key=lambda s: local(s, self.ns).lower()))
                    + '</div>' for x in gs)
                return (f'<section class="module" id="{escape(anchor)}"><h2 class="mod">{escape(title_of(g, m) or local(m, self.ns))}</h2>'
                        f'<p class="iri">{escape(str(m))}</p>' + (f'<p class="mdesc">{escape(mdesc)}</p>' if mdesc else "")
                        + '<dl class="meta">' + "".join(f"<div><dt>{k}</dt><dd>{v}</dd></div>" for k, v in mmeta if v)
                        + f'</dl>{body}</section>')

            nav = "".join(f'<div class="group"><p class="navm">{escape(title_of(g, m) or local(m, self.ns))}</p>'
                          + "".join(sidebar(x) for x in gs) + '</div>' for m, gs in parts if gs)
            group_links = '<a href="#modules">Modules</a>'
            sections = overview() + "\n" + "\n".join(module(m, gs) for m, gs in parts if gs)
        example_html = (f'<section id="example"><h2>Example</h2><pre>{self.turtle_html(example.strip())}</pre></section>'
                        if example else "")
        example_nav = '<a href="#example">Example</a>' if example else ""
        diagram_html = diagram_nav = extra_js = ""
        if self.class_diagrams:          # the arrowheads and styles of the classes' own diagrams
            diagram_html = f'<svg class="hr-diagram" width="0" height="0" aria-hidden="true">{defs()}</svg>'
        if svg:
            svg_inline = re.sub(r'\s(width|height)="\d+"', "", svg, count=2)
            counts, s = in_words([group.count for group in groups]), escape(stem)
            sources = in_words([f'<a href="{escape(f)}.ttl">{escape(f)}.ttl</a>' for f in files])
            view = '<g class="details">' in svg     # a drawing whose classes open when clicked
            kind = ""
            if view:
                kind, svg_inline, extra_css, extra_js = " view", VIEW_TOOLS + svg_inline, extra_css + VIEW_CSS, VIEW_JS
            elif 'class="hr-diagram folded"' in svg:   # boxes with their rows, at the size they are drawn
                kind, svg_inline, extra_css = " whole", svg, extra_css + WHOLE_CSS
            diagram_html = (f'<section id="diagram"><h2>Diagram</h2><div class="diagram{kind}">{svg_inline}</div>\n'
                            f'<p class="cap">{counts}, drawn from {sources}; '
                            f'also as <a href="{s}.svg">{s}.svg</a>.{" Click a class to see its properties." if view else ""}</p></section>')
            diagram_nav = '<a href="#diagram">Diagram</a>'

        return TEMPLATE.format(
            title=escape(title), desc=escape(desc), version=escape(version), ns=escape(self.ns),
            prefix=escape(self.prefix), favicon=favicon(self.prefix), stem=escape(stem), credit=f' · generated by <a href="{REPO}">horoi</a>',
            meta=meta_html, metadata=self.metadata(), diagram=diagram_html, diagram_nav=diagram_nav,
            nav=nav, group_links=group_links, sections=sections, extra_css=extra_css, extra_js=extra_js,
            example=example_html, example_nav=example_nav, downloads=downloads, versions=version_links,
            dark=DARK_CSS, svg_light=svg_vars(LIGHT), svg_dark=svg_vars(DARK))


def warn(message):
    """Print a warning, which GitHub Actions also shows on the run's summary."""
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::warning::horoi: {message}")
    else:
        print(f"horoi: warning: {message}", file=sys.stderr)


def write(g, folder, stem, example=None, version_links="", onto=None, files=None, diagram="graph"):
    """Write index.html and <stem>.svg into folder. For an ontology in several
    files, g holds them all, onto is the first file's ontology and files their names.
    diagram is the style of the drawing: "graph", with an arrow per property, or
    "folded", with a class's properties folded into its box.

    A shape the diagram can't draw leaves the diagram off the page, with a
    warning, so that no ontology goes unpublished for its shape."""
    try:
        svg = file = draw(g, onto) if diagram == "graph" else folded.draw(g, onto)
        if '<g class="details">' in svg:                # the file has the drawing alone
            file = folded.draw(g, onto, page=False)
    except Undrawable as e:
        svg = None
        warn(f"the page of {stem} {version_of(g, onto)} has no diagram, because {e}")
    else:
        (folder / f"{stem}.svg").write_text(file, encoding="utf-8", newline="\n")
    html = Page(g, onto).render(svg, stem, example, version_links, files, per_class=diagram == "graph")
    (folder / "index.html").write_text(html, encoding="utf-8", newline="\n")


# What only a page with a drawing whose classes open carries: its buttons, styles and script.
FS_ENTER = "M1 5V1h4M9 1h4v4M13 9v4H9M5 13H1V9"
FS_EXIT = "M5 1v4H1M13 5H9V1M9 13V9h4M1 9h4v4"
VIEW_TOOLS = ('<div class="tools">'
              '<button type="button" data-do="help" title="How to use the diagram" aria-label="How to use the diagram" '
              'aria-expanded="false" aria-controls="hint">?</button>'
              '<button type="button" data-do="in" title="Zoom in" aria-label="Zoom in">+</button>'
              '<button type="button" data-do="out" title="Zoom out" aria-label="Zoom out">−</button>'
              '<button type="button" data-do="fit" title="Show the whole diagram" aria-label="Show the whole diagram">'
              '<svg viewBox="0 0 14 14" aria-hidden="true"><rect x="1.5" y="3" width="11" height="8" rx="1.5"/></svg></button>'
              '<button type="button" data-do="full" title="Full screen" aria-label="Full screen">'
              f'<svg viewBox="0 0 14 14" aria-hidden="true"><path d="{FS_ENTER}"/></svg></button></div>'
              '<ul class="hint" id="hint" hidden>'
              '<li>Click a class to see its properties, and those that point to it.</li>'
              '<li>Click a class named in a row to go to it.</li>'
              '<li>Click the class’s name at the top of the box, or a property’s name, to go to its card.</li>'
              '<li>Click outside the box, or press Esc, to go back.</li>'
              '<li>Drag to move the diagram.</li>'
              '<li>Zoom with + and −, or with Ctrl and the mouse wheel.</li></ul>')
WHOLE_CSS = ".diagram.whole svg { width:auto; max-width:100%; min-width:0; margin:0 auto; }\n"
VIEW_CSS = """.diagram.view { position:relative; height:min(72vh,760px); min-height:420px; padding:0; overflow:hidden;
  background:var(--bg); cursor:grab; touch-action:pan-y; user-select:none; }
.diagram.view svg.folded { width:100%; height:100%; min-width:0; }
.diagram.view.drag { cursor:grabbing; }
.diagram.view:fullscreen { height:100vh; border:none; border-radius:0; touch-action:none; }
.tools { position:absolute; top:10px; right:10px; display:flex; gap:6px; }
.tools button { display:grid; place-items:center; width:32px; height:32px; padding:0; border:1px solid var(--line); border-radius:4px;
  background:var(--panel); color:var(--muted); cursor:pointer; font:18px/1 var(--sans); }
.tools button:hover { background:var(--accent-soft); color:var(--accent); }
.hint { position:absolute; top:50px; right:10px; z-index:1; width:min(300px, calc(100% - 20px)); margin:0; padding:12px 16px 12px 30px;
  border:1px solid var(--line); border-radius:6px; background:var(--panel); color:var(--muted); font:13.5px/1.5 var(--sans);
  box-shadow:0 4px 14px rgb(0 0 0 / .12); cursor:default; }
.hint li + li { margin-top:4px; }
.tools button[aria-expanded="true"] { background:var(--accent-soft); color:var(--accent); }
.tools svg { display:block; width:14px; height:14px; min-width:0; fill:none; stroke:currentColor; stroke-width:1.6; stroke-linecap:round; }
"""
VIEW_JS = """(() => {
  const wrap = document.querySelector('.diagram.view'), svg = wrap.querySelector('svg.folded');
  const home = svg.getAttribute('viewBox').split(' ').map(Number);
  const still = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const full = wrap.querySelector('[data-do="full"]'), help = wrap.querySelector('[data-do="help"]'), hint = wrap.querySelector('.hint');
  const tell = on => { hint.hidden = !on; help.setAttribute('aria-expanded', on); };
  let at = null, open = null, before = null, frame = 0, down = null;
  // The view is a centre and a scale, in pixels per unit, so it keeps its place when the box changes size.
  const size = () => [wrap.clientWidth, wrap.clientHeight];
  const whole = () => { const [w, h] = size();
    return { x: home[0] + home[2] / 2, y: home[1] + home[3] / 2, s: Math.min(w / home[2], h / home[3]) }; };
  const show = v => { at = v; const [w, h] = size();
    svg.setAttribute('viewBox', [v.x - w / v.s / 2, v.y - h / v.s / 2, w / v.s, h / v.s].map(n => n.toFixed(2)).join(' ')); };
  const fly = to => { cancelAnimationFrame(frame);
    if (still) return show(to);
    const from = at, t0 = performance.now();
    const step = t => { const k = Math.min(1, Math.max(0, (t - t0) / 240)), e = 1 - Math.pow(1 - k, 3);
      show({ x: from.x + (to.x - from.x) * e, y: from.y + (to.y - from.y) * e, s: from.s * Math.pow(to.s / from.s, e) });
      if (k < 1) frame = requestAnimationFrame(step); };
    frame = requestAnimationFrame(step); };
  const zoom = (f, px, py) => { const [w, h] = size(), s = Math.min(6, Math.max(whole().s / 2, at.s * f));
    px = px === undefined ? w / 2 : px; py = py === undefined ? h / 2 : py;
    const x = at.x + (px - w / 2) / at.s, y = at.y + (py - h / 2) / at.s;
    return { x: x - (px - w / 2) / s, y: y - (py - h / 2) / s, s }; };
  const close = () => { if (!open) return false;
    open.setAttribute('display', 'none'); open = null; svg.classList.remove('focus'); return true; };
  const focus = i => { const d = svg.querySelector(`[data-d="${i}"]`);
    if (!d) return;
    if (!close()) before = at;
    open = d; d.removeAttribute('display'); svg.classList.add('focus');
    const [x, y, bw, bh] = d.dataset.box.split(' ').map(Number), [w, h] = size();
    // The whole box if it fits at a readable size; else its width, from its top.
    const s = Math.min(1.8, Math.max(Math.min(w * .9 / bw, h * .9 / bh), Math.min(1, w * .9 / bw)));
    fly({ x: x + bw / 2, y: bh * s > h * .9 ? y + (h / 2 - 24) / s : y + bh / 2, s }); };
  const back = () => { if (close()) fly(before || whole()); };
  show(whole());
  let fitted = whole().s;
  new ResizeObserver(() => { const was = at.s === fitted; fitted = whole().s; show(was && !open ? whole() : at); }).observe(wrap);
  svg.addEventListener('pointerdown', e => { tell(false);
    if (e.button) return;
    down = { x: e.clientX, y: e.clientY, cx: at.x, cy: at.y, target: e.target, moved: false }; });
  svg.addEventListener('pointermove', e => { if (!down) return;
    const dx = e.clientX - down.x, dy = e.clientY - down.y;
    if (!down.moved && Math.hypot(dx, dy) < 5) return;
    if (!down.moved) { down.moved = true; cancelAnimationFrame(frame); wrap.classList.add('drag'); svg.setPointerCapture(e.pointerId); }
    show({ x: down.cx - dx / at.s, y: down.cy - dy / at.s, s: at.s }); });
  const up = e => { if (!down) return;
    const d = down; down = null; wrap.classList.remove('drag');
    if (d.moved || e.type === 'pointercancel') return;
    const go = d.target.closest('[data-c]');
    if (go) focus(go.dataset.c); else if (!d.target.closest('.d')) back(); };
  svg.addEventListener('pointerup', up); svg.addEventListener('pointercancel', up);
  svg.addEventListener('click', e => { if (e.target.closest('.d a') && document.fullscreenElement) document.exitFullscreen(); });
  svg.addEventListener('keydown', e => { const n = e.target.closest('.n');
    if (n && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); focus(n.dataset.c); } });
  wrap.addEventListener('keydown', e => { if (e.key !== 'Escape') return;
    if (!hint.hidden) tell(false); else if (open && !document.fullscreenElement) back(); });
  wrap.addEventListener('wheel', e => { if (!e.ctrlKey && document.fullscreenElement !== wrap) return;
    e.preventDefault(); cancelAnimationFrame(frame);
    const r = wrap.getBoundingClientRect(); show(zoom(Math.exp(-e.deltaY * .0025), e.clientX - r.left, e.clientY - r.top)); }, { passive: false });
  if (!wrap.requestFullscreen) full.hidden = true;
  wrap.querySelector('.tools').addEventListener('click', e => { const b = e.target.closest('button');
    if (!b) return;
    if (b.dataset.do === 'help') return tell(hint.hidden);
    tell(false);
    if (b.dataset.do === 'in') fly(zoom(1.5)); else if (b.dataset.do === 'out') fly(zoom(1 / 1.5));
    else if (b.dataset.do === 'fit') { close(); fly(whole()); }
    else if (document.fullscreenElement) document.exitFullscreen(); else wrap.requestFullscreen().catch(() => {}); });
  document.addEventListener('fullscreenchange', () => { const on = document.fullscreenElement === wrap;
    full.title = on ? 'Leave full screen' : 'Full screen'; full.setAttribute('aria-label', full.title);
    full.querySelector('path').setAttribute('d', on ? 'FS_EXIT' : 'FS_ENTER');
    setTimeout(() => { if (open) focus(open.dataset.d); else show(whole()); }, 150); });
})();
""".replace("FS_EXIT", FS_EXIT).replace("FS_ENTER", FS_ENTER)

# Styles that only pages of several files, or of an ontology with modules, carry.
MULTI_CSS = """.dlt { grid-column:1/-1; border-collapse:collapse; font-size:14.5px; }
.dlt td { padding:7px 16px 7px 0; border-bottom:1px solid var(--line); } .dlt td:first-child { padding-right:28px; }
"""
MODULE_CSS = """.mods { border-collapse:collapse; font-size:14.5px; } .mods th { text-align:left; font-size:12px; font-weight:400; color:var(--faint); }
.mods th, .mods td { padding:6px 22px 6px 0; border-bottom:1px solid var(--line); } .mods td + td { text-align:right; color:var(--muted); }
.mods .chip { font-family:var(--sans); }
.module { padding-top:28px; border-top:2px solid var(--line); }
h2.mod { font-size:30px; line-height:1.2; letter-spacing:-.4px; text-transform:none; color:var(--ink); font-weight:600; margin:0 0 4px; }
.mdesc { font-size:17px; color:var(--muted); max-width:760px; margin:0 0 16px; }
h3.grp { font-size:13px; letter-spacing:2px; text-transform:uppercase; color:var(--accent); margin:32px 0 16px; }
.navm { margin:0 0 8px; font:600 14.5px/1.35 var(--sans); color:var(--ink); }
.group .group:not([hidden]) ~ .group { margin-top:10px; } .group .navh { font-size:11.5px; margin-bottom:2px; }
"""

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
  --bg:#FFFFFF; --panel:#FFFFFF; --ink:#111827; --muted:#4B5563; --faint:#9CA3AF; --section:#6E7788; --line:#E5E7EB;
  --accent:#EA580C; --accent-soft:#FFF1E8; --blue:#2563EB; --blue-soft:#EEF4FF; --green:#16A34A; --green-soft:#ECFBF1; --code:#F6F7F9;
  --mono:ui-monospace,"Cascadia Mono",Consolas,"SF Mono",Menlo,monospace;
  --sans:Inter,"Segoe UI",system-ui,-apple-system,"Helvetica Neue",Arial,sans-serif;
  --gutter:28px; --side:230px; --toggle:36px; --rail:calc(var(--gutter) + var(--side) + 40px);
  --fold:240ms; --ease:cubic-bezier(.2,0,.38,.9); }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ {dark} }} }}
:root[data-theme="dark"] {{ {dark} }}
:root[data-theme="light"] svg.hr-diagram {{ {svg_light} }}
:root[data-theme="dark"] svg.hr-diagram {{ {svg_dark} }}
* {{ box-sizing:border-box; }}
html {{ scroll-behavior:smooth; scroll-padding-top:84px; }}
body {{ margin:0; background:var(--bg); color:var(--ink); font:16px/1.6 var(--sans); }}
a {{ color:var(--accent); text-decoration:none; }} a:hover {{ text-decoration:underline; }}
code {{ font-family:var(--mono); font-size:.9em; }}
.top {{ position:sticky; top:0; z-index:5; display:flex; align-items:center; gap:14px; padding:12px var(--gutter);
  background:color-mix(in srgb, var(--bg) 85%, transparent); backdrop-filter:blur(10px); border-bottom:1px solid var(--line); }}
.mark {{ width:30px; height:30px; border-radius:6px; background:#EA580C; display:grid; place-items:center; color:#fff;
  font:700 15px var(--sans); }}
.top .name {{ font-size:21px; font-weight:400; letter-spacing:-.2px; align-self:baseline; }}
.top .v {{ font:500 12px var(--mono); color:var(--muted); border:1px solid var(--line); padding:2px 8px; border-radius:4px; align-self:baseline; }}
.top nav {{ margin-left:auto; display:flex; gap:20px; font-size:14px; align-items:center; }} .top nav a {{ color:var(--muted); }}
#theme {{ border:none; background:transparent; color:var(--muted); border-radius:4px; width:32px; height:28px;
  cursor:pointer; font-size:15px; line-height:1; }}
.wrap {{ display:grid; grid-template-columns:minmax(var(--rail),1fr) minmax(0,914px) minmax(var(--gutter),1fr);
  padding:36px 0 80px; }}
aside {{ position:sticky; top:95px; align-self:start; width:var(--side); margin-left:var(--gutter); }}
.terms {{ display:flex; flex-direction:column; max-height:calc(100vh - 115px); }}
aside input {{ flex:none; width:100%; height:var(--toggle); margin:0 0 28px; padding:0 11px;
  border:1px solid var(--line); border-radius:4px; background:var(--panel); color:var(--ink); font:14.5px var(--sans); }}
.list {{ flex:1; min-height:0; overflow:auto; margin:0 -10px; padding:0 10px; scrollbar-width:none; }}
.list::-webkit-scrollbar {{ display:none; }}
aside a {{ display:block; margin-left:-10px; padding:3px 10px; border-radius:4px; color:var(--muted); font:14.5px var(--sans); }}
aside a:hover {{ background:var(--accent-soft); color:var(--accent); text-decoration:none; }}
.group:not([hidden]) ~ .group {{ margin-top:24px; }}
.navh {{ margin:0 0 6px; font:700 13px var(--sans); letter-spacing:1.6px; text-transform:uppercase; color:var(--section); }}
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
#metadata summary {{ display:flex; align-items:center; gap:10px; width:fit-content; cursor:pointer; list-style:none; }}
#metadata summary::-webkit-details-marker {{ display:none; }}
#metadata summary h2 {{ margin:0; }}
#metadata summary::after {{ content:""; width:7px; height:7px; border-right:1.5px solid var(--accent); border-bottom:1.5px solid var(--accent);
  transform:rotate(-45deg); transition:transform var(--fold) var(--ease); }}
#metadata details[open] summary::after {{ transform:translateY(-2px) rotate(45deg); }}
.md {{ display:grid; grid-template-columns:150px minmax(0,1fr); gap:8px 16px; margin:18px 0 0; font-size:14.5px; }}
.md dt {{ font-size:13px; color:var(--faint); padding-top:2px; }} .md dd {{ margin:0; overflow-wrap:anywhere; white-space:pre-line; }}
.md .lang {{ color:var(--faint); font-size:12px; }}
.diagram {{ border:1px solid var(--line); border-radius:6px; padding:16px; overflow:auto; }}
.diagram svg {{ display:block; width:100%; height:auto; min-width:640px; }}
.diagram.own {{ margin-top:16px; }} .diagram.own svg {{ width:auto; max-width:100%; min-width:0; }}
.ax {{ flex-basis:100%; font-size:14.5px; line-height:1.9; }}
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
.more {{ margin-top:14px; }}
.more summary {{ display:flex; align-items:center; gap:8px; width:fit-content; cursor:pointer; list-style:none; font-size:13px; color:var(--faint); }}
.more summary::-webkit-details-marker {{ display:none; }}
.more summary::after {{ content:""; width:6px; height:6px; border-right:1.5px solid currentColor; border-bottom:1.5px solid currentColor;
  transform:rotate(-45deg); transition:transform var(--fold) var(--ease); }}
.more[open] summary::after {{ transform:translateY(-2px) rotate(45deg); }}
.term .more dl {{ margin-top:10px; padding-top:0; border-top:none; }}
.more .v {{ flex-basis:100%; font-size:14.5px; overflow-wrap:anywhere; white-space:pre-line; }} .more .lang {{ color:var(--faint); font-size:12px; }}
.term dt {{ font-size:13px; color:var(--faint); padding-top:3px; }} .term dd {{ margin:0; display:flex; flex-wrap:wrap; gap:6px; align-items:center; }}
.chip {{ font:13px var(--mono); padding:2px 8px; border-radius:4px; background:var(--accent-soft); color:var(--accent); }}
.chip.any {{ background:var(--code); color:var(--muted); font-style:italic; font-family:var(--sans); }}
.chip.lit {{ background:var(--code); color:var(--ink); font-family:var(--sans); }}
.chip.ext {{ background:var(--code); color:var(--muted); }}
.edge {{ white-space:nowrap; }} .arrow {{ color:var(--faint); }}
pre {{ background:var(--code); border:1px solid var(--line); border-radius:6px; padding:16px 18px; overflow:auto;
  font:13.5px/1.6 var(--mono); }}
pre .k {{ color:var(--faint); }} pre .s {{ color:var(--green); }} pre .t {{ color:var(--blue); font-weight:600; }}
.dls {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:12px; }}
.dl {{ background:var(--panel); border:1px solid var(--line); border-radius:6px; padding:12px 16px; color:var(--ink); }}
.dl:hover {{ border-color:var(--accent); text-decoration:none; }} .dl span {{ display:block; font-weight:600; }}
.dl code {{ color:var(--muted); }}
footer {{ border-top:1px solid var(--line); padding:24px 28px; color:var(--faint); font-size:13px; text-align:center; }}
@media (max-width:900px) {{ .wrap {{ grid-template-columns:minmax(0,1fr); padding:24px 16px 60px; }} aside {{ display:none; }}
  .top nav a {{ display:none; }} h1 {{ font-size:34px; }} .term dl, .md {{ grid-template-columns:1fr; }} }}
{extra_css}</style>
</head>
<body>
<div class="top"><span class="mark">{prefix}</span><span class="name">{title}</span><span class="v">{version}</span>
<nav><a href="#metadata">Metadata</a>{diagram_nav}{group_links}{example_nav}<a href="#download">Download</a><button id="theme" type="button" title="Switch between light and dark" aria-label="Switch between light and dark">◐</button></nav></div>
<div class="wrap">
<aside>
<div class="terms" id="terms"><input id="q" type="search" placeholder="Find a term" aria-label="Find a term"><div class="list">{nav}</div></div></aside>
<main>
<section id="top">
<h1>{title}</h1>
<p class="lead">{desc}</p>
<div class="ns"><span class="p">{prefix}:</span><code id="nsiri">{ns}</code><button id="copy" type="button">Copy</button></div>
<dl class="meta">{meta}</dl>
</section>
{metadata}
{diagram}
{sections}
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
(() => {{
  const d = document.querySelector('#metadata details');
  const open = () => {{ if (d && location.hash === '#metadata') d.open = true; }};
  open(); addEventListener('hashchange', open);
}})();
const q = document.getElementById('q');
q.addEventListener('input', () => {{
  const s = q.value.toLowerCase();
  document.querySelectorAll('aside .group').forEach(group => {{
    let found = false;
    group.querySelectorAll('a').forEach(a => {{
      const hit = (a.textContent + ' ' + a.title).toLowerCase().includes(s);
      a.style.display = hit ? '' : 'none';
      found = found || hit;
    }});
    group.hidden = !found;
  }});
}});
document.getElementById('copy').addEventListener('click', e => {{
  navigator.clipboard.writeText(document.getElementById('nsiri').textContent).then(() => {{ e.target.textContent = 'Copied'; }});
}});
{extra_js}</script>
</body>
</html>
"""
