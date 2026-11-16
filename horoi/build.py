"""Build an ontology's published files: the documentation page, the diagram,
and the ontology in four serialisations, for the latest version and for every
released one.

Layout of the output folder, for an ontology file named <stem>.ttl:
    index.html, <stem>.svg, <stem>.ttl, .rdf, .jsonld, .nt    the latest version
    <version>/index.html, <version>/<stem>.ttl, ...           each release

An ontology kept in several files gets one page, from them all, and each file
in its four serialisations. The page documents the first file's ontology, and
the diagram is named after that file. A file belongs to the ontology only if its
own ontology is stated to be a part of the first file's. Every part that terms
are rdfs:isDefinedBy is a module, with a section of the page.

A release is a git tag v<x.y.z>. Its files are built from the ontology as
committed at that tag, and a tag whose version differs is refused. A tag
without one of the files is left out, with a warning.
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
import warnings
from pathlib import Path

from rdflib import BNode, Graph
from rdflib.namespace import DCTERMS, OWL, RDF

from .diagram import ontology
from .page import version_of, warn, write

# RDF/XML in rdflib's plain form: its "pretty-xml" nests blank nodes, and on some builds
# writes a list twice, so that the file holds another graph.
FORMATS = {".ttl": "turtle", ".rdf": "xml", ".jsonld": "json-ld", ".nt": "nt"}


def steady(source):
    """A file's graph for its serialisations, which are then the same at every build: in
    a store that keeps the file's order, with its blank nodes named b0, b1 ... in the
    order they first appear. rdflib's own store keeps its triples in a set, whose order
    changes from one run to the next, and names blank nodes at random."""
    g = Graph(store="SimpleMemory")
    g.parse(source, format="turtle")
    out, names = Graph(store="SimpleMemory"), {}
    for prefix, uri in g.namespaces():
        out.bind(prefix, uri, override=True, replace=True)
    for t in g:
        out.add(tuple(names.setdefault(x, BNode(f"b{len(names)}")) if isinstance(x, BNode) else x for x in t))
    return out


def jsonld(g):
    """The graph in JSON-LD, its nodes and their values in an order that is the same at
    every build: rdflib writes them in the order of a set. A node's values are a set
    too, but for an @list's, which keep their order. The JSON is written as rdflib does."""
    def tidy(x, key=None):
        if isinstance(x, dict):
            return {k: tidy(v, k) for k, v in x.items()}
        if isinstance(x, list):
            items = [tidy(v) for v in x]
            return items if key == "@list" else sorted(items, key=lambda v: json.dumps(v, sort_keys=True, ensure_ascii=False))
        return x
    doc = tidy(json.loads(g.serialize(format="json-ld", encoding="utf-8")))
    return json.dumps(doc, indent=2, separators=(",", ": "), sort_keys=True, ensure_ascii=False).encode("utf-8")


def version_or_stop(g, onto=None):
    v = version_of(g, onto)
    if v is None:
        sys.exit("horoi: the ontology has no owl:versionInfo, and no version at the end of its owl:versionIRI")
    return v


def load(sources):
    """An ontology from its files: the graph of them all, each file's own graph, the
    ontology the page documents, and the files kept. The ontology is the first
    file's, or for one file None, which leaves it to the file.

    A file is kept if the files themselves say it belongs: its ontology is a part of
    the first file's, by dcterms:hasPart or dcterms:isPartOf, directly or through
    another part. So is a file that declares no other ontology. Any other file is
    left out, with a warning."""
    graphs = []
    for source in sources:
        graphs.append(Graph())
        graphs[-1].parse(source, format="turtle")
    if len(graphs) > 1 and len({Path(s).stem for s in sources}) < len(sources):
        sys.exit("horoi: two of the ontology's files have the same name")
    onto = next(graphs[0].subjects(RDF.type, OWL.Ontology), None)
    if onto is None:
        if len(graphs) == 1:
            return graphs[0], graphs, None, list(sources)
        sys.exit(f"horoi: {Path(sources[0]).name}, the first file, declares no owl:Ontology")
    links = {(s, o) for own in graphs for s, o in own.subject_objects(DCTERMS.hasPart)}
    links |= {(o, s) for own in graphs for s, o in own.subject_objects(DCTERMS.isPartOf)}
    whole = {onto}
    while True:                          # the parts, and theirs
        more = {part for of, part in links if of in whole} - whole
        if not more:
            break
        whole |= more
    kept = []
    for i, own in enumerate(graphs):
        declared = set(own.subjects(RDF.type, OWL.Ontology)) - {onto}
        if i == 0 or not declared or declared & whole:
            kept.append(i)
        else:
            warn(f"{Path(sources[i]).name} is left out, because nothing states that {min(declared, key=str)} is a part of {onto}, "
                 "with dcterms:hasPart or dcterms:isPartOf")
    found = {o for i in kept for o in graphs[i].subjects(RDF.type, OWL.Ontology)}
    for part in sorted(whole - found, key=str):
        warn(f"{part} is a part of {onto}, but none of the files declares it")
    sources, graphs = [sources[i] for i in kept], [graphs[i] for i in kept]
    if len(graphs) == 1:
        return graphs[0], graphs, None, sources
    g = Graph()
    for source in sources:
        g.parse(source, format="turtle")
    return g, graphs, onto, sources


def distinct(files):
    """The files, each once, in the order first given, as a glob that also names the first file gives them."""
    return list(dict.fromkeys(Path(f).resolve() for f in files))


def build_one(sources, folder, example=None, diagram="graph"):
    """Write the page, the diagram, and the four serialisations of each of the ontology's
    files. The page and the diagram are named after the first file."""
    g, _, onto, sources = load(sources)
    version = version_or_stop(g, onto)                          # before anything is written
    folder.mkdir(parents=True, exist_ok=True)
    for source in sources:                                      # each file as itself
        stem, own = Path(source).stem, steady(source)
        for ext, fmt in FORMATS.items():
            if ext == ".ttl":
                shutil.copyfile(source, folder / f"{stem}.ttl")     # the source as written
            elif ext == ".jsonld":
                (folder / f"{stem}{ext}").write_bytes(jsonld(own))
            else:
                with warnings.catch_warnings():                     # rdflib warns once per list in RDF/XML
                    warnings.simplefilter("ignore", UserWarning)
                    own.serialize(destination=folder / f"{stem}{ext}", format=fmt, encoding="utf-8")
    write(g, folder, Path(sources[0]).stem, example, onto=onto, files=[Path(s).stem for s in sources], diagram=diagram)
    return version


def git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, check=True).stdout


def build(ontology, out, example=None, all_tags=False, diagram="graph"):
    """ontology: a file, or a list of the files an ontology is kept in, the one
    whose ontology the page documents first. diagram: the style of the drawing,
    "graph" or "folded"."""
    files = [ontology] if isinstance(ontology, (str, Path)) else list(ontology)
    files, out = distinct(files), Path(out)
    example_text = Path(example).read_text(encoding="utf-8") if example else None
    if out.exists():
        shutil.rmtree(out)
    built = []
    if all_tags:
        repo = Path(git(files[0].parent, "rev-parse", "--show-toplevel").decode().strip())
        rels = [f.relative_to(repo).as_posix() for f in files]
        tags = [t for t in git(repo, "tag", "--list", "v*").decode().split() if re.fullmatch(r"v\d+\.\d+\.\d+", t)]
        for tag in tags:
            with tempfile.TemporaryDirectory() as tmp:
                srcs = []
                for f, rel in zip(files, rels):
                    srcs.append(Path(tmp) / f"{f.stem}.ttl")
                    try:
                        srcs[-1].write_bytes(git(repo, "show", f"{tag}:{rel}"))
                    except subprocess.CalledProcessError:   # a release from before the file was there
                        warn(f"release {tag} is left out, because it has no {rel}")
                        break
                else:
                    version = build_one(srcs, Path(tmp) / "build", example_text, diagram)
                    if f"v{version}" != tag:
                        sys.exit(f"horoi: tag {tag} holds version {version}")
                    shutil.copytree(Path(tmp) / "build", out / version)
                    built.append(version)
    latest = build_one(files, out, example_text, diagram)
    if not (out / latest).exists():     # a release keeps the files of its tag
        shutil.copytree(out, out / latest, ignore=lambda d, names: [n for n in names if (Path(d) / n).is_dir()])
    return latest, built
