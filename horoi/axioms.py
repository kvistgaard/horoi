"""Read a class's OWL axioms: its restrictions, and the class expressions in them;
and a property's domains and ranges, which OWL reads, when there are several, as
their intersection.

An expression is written in the words of the Manchester syntax, such as
"hasParty some (Person or Organization)". Whoever asks decides how a term is
written, by passing `ref`: the page passes its chips, and the diagram CURIEs.

Nothing here depends on what blank nodes are called, which changes at every build.
"""
from rdflib import BNode, Literal, URIRef
from rdflib.collection import Collection
from rdflib.namespace import OWL, RDF, RDFS, XSD

FACETS = {XSD.minInclusive: "≥", XSD.maxInclusive: "≤", XSD.minExclusive: "above", XSD.maxExclusive: "below"}
CARDINALITIES = ((OWL.cardinality, "exactly"), (OWL.minCardinality, "min"), (OWL.maxCardinality, "max"),
                 (OWL.qualifiedCardinality, "exactly"), (OWL.minQualifiedCardinality, "min"),
                 (OWL.maxQualifiedCardinality, "max"))


def members(g, node, p):
    """The members of a union or an intersection, or nothing if the node is not one."""
    head = g.value(node, p)
    return list(Collection(g, head)) if head is not None else []


def union(g, node):
    """The named members of a union, or nothing if the node is anything else."""
    found = members(g, node, OWL.unionOf) if isinstance(node, BNode) else []
    return [] if any(isinstance(m, BNode) for m in found) else found


def quantifier(g, r):
    """A restriction's word and its filler: ("some", Person), ("exactly 1", None)."""
    for p, word in ((OWL.someValuesFrom, "some"), (OWL.allValuesFrom, "only"), (OWL.hasValue, "value")):
        filler = g.value(r, p)
        if filler is not None:
            return word, filler
    for p, word in CARDINALITIES:
        n = g.value(r, p)
        if n is not None:
            filler = g.value(r, OWL.onClass)
            return f"{word} {n}", filler if filler is not None else g.value(r, OWL.onDataRange)
    if g.value(r, OWL.hasSelf) is not None:
        return "Self", None
    return "some", None


def is_datatype(g, node):
    """Whether a filler is a datatype: one of XSD's or RDF's, or a range of values of one."""
    if isinstance(node, BNode):
        return (node, RDF.type, RDFS.Datatype) in g or g.value(node, OWL.onDatatype) is not None
    return str(node).startswith(str(XSD)) or node in (RDFS.Literal, RDF.langString, RDF.PlainLiteral)


def expression(g, node, ref, nested=False):
    """A class expression in words. `ref` writes each named term and each literal."""
    if not isinstance(node, BNode):
        return ref(node)
    wrap = (lambda s: f"({s})") if nested else (lambda s: s)
    for p, word in ((OWL.intersectionOf, " and "), (OWL.unionOf, " or ")):
        parts = members(g, node, p)
        if parts:
            return wrap(word.join(expression(g, m, ref, True) for m in parts))
    for p in (OWL.complementOf, OWL.datatypeComplementOf):
        other = g.value(node, p)
        if other is not None:
            return "not " + expression(g, other, ref, True)
    listed = members(g, node, OWL.oneOf)
    if listed:
        return "{" + ", ".join(ref(m) for m in listed) + "}"
    prop = g.value(node, OWL.onProperty)
    if prop is not None:
        inverse = g.value(prop, OWL.inverseOf) if isinstance(prop, BNode) else None
        name = f"inverse {ref(inverse)}" if inverse is not None else ref(prop)
        word, filler = quantifier(g, node)
        return wrap(f"{name} {word}" + (f" {expression(g, filler, ref, True)}" if filler is not None else ""))
    datatype = g.value(node, OWL.onDatatype)
    if datatype is not None:
        facets = [f"{FACETS.get(p, str(p).rsplit('#', 1)[-1])} {ref(o)}"
                  for f in members(g, node, OWL.withRestrictions) for p, o in g.predicate_objects(f)]
        return ref(datatype) + (f" [{', '.join(facets)}]" if facets else "")
    return "a class expression"


def canonical(g, node):
    """A term or an expression in words that name each term by its full IRI: the same
    for the same expression at every build, whatever its blank nodes are called."""
    return expression(g, node, lambda x: x.n3() if isinstance(x, Literal) else str(x))


def in_order(g, nodes):
    """Nodes in an order that is the same at every build: named terms and literals
    first, by their text, then expressions, by their words."""
    return sorted(nodes, key=lambda n: (isinstance(n, BNode), canonical(g, n) if isinstance(n, BNode) else str(n)))


def distinct(g, values):
    """Values in the order of in_order, each once: a value that says what an earlier one
    says, such as a union of the same classes in another order, is left out."""
    seen, out = set(), []
    for v in in_order(g, values):
        same = frozenset(union(g, v)) or (frozenset([v]) if not isinstance(v, BNode) else canonical(g, v))
        if same not in seen:
            seen.add(same)
            out.append(v)
    return out


def stated(g, p, pred):
    """The values a property states for pred, rdfs:domain or rdfs:range, by distinct.
    OWL reads several values as their intersection."""
    return distinct(g, g.objects(p, pred))


def declared(g, p, pred):
    """What a property states for pred or, if it states nothing, what its super-properties
    state, all of them: a sub-property has each domain and range of each."""
    return stated(g, p, pred) or distinct(g, [v for x in g.objects(p, RDFS.subPropertyOf) if isinstance(x, URIRef)
                                              for v in g.objects(x, pred)])


def common(g, values):
    """The named classes that a property with these domains, or ranges, starts from or
    reaches: each class that every value is or names as a member of its union, in the
    first value's order. For one value, the class or the union's members; for one that
    is any other expression, none."""
    sets = [[v] if isinstance(v, URIRef) else union(g, v) for v in values]
    return [m for m in sets[0] if all(m in s for s in sets[1:])] if sets else []


def restrictions(g, cls):
    """The restrictions a class is declared with: as a superclass, or as a member of
    the intersection it is a subclass of or equivalent to."""
    found, seen = [], set()

    def walk(node):
        if not isinstance(node, BNode) or node in seen:
            return
        seen.add(node)
        if g.value(node, OWL.onProperty) is not None:
            found.append(node)
        for m in members(g, node, OWL.intersectionOf):
            walk(m)
    for p in (RDFS.subClassOf, OWL.equivalentClass):
        for o in in_order(g, g.objects(cls, p)):
            walk(o)
    return found


def literal(node):
    return f'"{node}"' if isinstance(node, Literal) and node.datatype in (None, XSD.string) else str(node)
