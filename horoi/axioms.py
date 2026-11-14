"""Read a class's OWL axioms: its restrictions, and the class expressions in them.

An expression is written in the words of the Manchester syntax, such as
"hasParty some (Person or Organization)". Whoever asks decides how a term is
written, by passing `ref`: the page passes its chips, and the diagram CURIEs.
"""
from rdflib import BNode, Literal
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
        for o in sorted(g.objects(cls, p), key=str):
            walk(o)
    return found


def literal(node):
    return f'"{node}"' if isinstance(node, Literal) and node.datatype in (None, XSD.string) else str(node)
