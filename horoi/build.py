"""Build an ontology's published files: the documentation page, the diagram,
and the ontology in four serialisations, for the latest version and for every
released one.

Layout of the output folder, for an ontology file named <stem>.ttl:
    index.html, <stem>.svg, <stem>.ttl, .rdf, .jsonld, .nt    the latest version
    <version>/index.html, <version>/<stem>.ttl, ...           each release

An ontology kept in several files gets one page, from them all, and each file
in its four serialisations. The page documents the first file's ontology, and
the diagram is named after that file. If that ontology lists modules with
dcterms:hasPart, each listed module needs one of the files, and the page has a
section per module.

A release is a git tag v<x.y.z>. Its files are built from the ontology as
committed at that tag, and a tag whose version differs is refused. A tag
without one of the files is left out, with a warning.
"""
import re
import shutil
import subprocess
import sys
import tempfile
import warnings
from pathlib import Path

from rdflib import Graph
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS

from .diagram import ontology
from .page import version_of, warn, write

FORMATS = {".ttl": "turtle", ".rdf": "pretty-xml", ".jsonld": "json-ld", ".nt": "nt"}


def version_or_stop(g, onto=None):
    v = version_of(g, onto)
    if v is None:
        sys.exit("horoi: the ontology has no owl:versionInfo, and no version at the end of its owl:versionIRI")
    return v


def load(sources):
    """An ontology from its files: the graph of them all, each file's own graph, and
    the ontology the page documents. That is the first file's, or for one file
    None, which leaves it to the file."""
    graphs = []
    for source in sources:
        graphs.append(Graph())
        graphs[-1].parse(source, format="turtle")
    if len(graphs) == 1:
        check_modules(graphs[0], ontology(graphs[0]), graphs, sources)
        return graphs[0], graphs, None
    if len({Path(s).stem for s in sources}) < len(sources):
        sys.exit("horoi: two of the ontology's files have the same name")
    onto = next(graphs[0].subjects(RDF.type, OWL.Ontology), None)
    if onto is None:
        sys.exit(f"horoi: {Path(sources[0]).name}, the first file, declares no owl:Ontology")
    g = Graph()
    for source in sources:
        g.parse(source, format="turtle")
    check_modules(g, onto, graphs, sources)
    return g, graphs, onto


def check_modules(g, onto, graphs, sources):
    """An ontology's modules are the parts it lists with dcterms:hasPart. Stop if a
    part has no file, or a file's ontology defines terms without being a part."""
    if onto is None:
        return
    parts = set(g.objects(onto, DCTERMS.hasPart))
    for part in sorted(parts, key=str):
        if (part, RDF.type, OWL.Ontology) not in g:
            sys.exit(f"horoi: {part} is a part of {onto}, by dcterms:hasPart, but none of the files declares it")
    for source, own in zip(sources, graphs):
        for other in own.subjects(RDF.type, OWL.Ontology):
            if other != onto and other not in parts and (None, RDFS.isDefinedBy, other) in g:
                sys.exit(f"horoi: {Path(source).name} declares {other}, which defines terms, "
                         f"but {onto} does not list it as a part, with dcterms:hasPart")


def distinct(files):
    """The files, each once, in the order first given, as a glob that also names the first file gives them."""
    return list(dict.fromkeys(Path(f).resolve() for f in files))


def build_one(sources, folder, example=None, diagram="graph"):
    """Write the page, the diagram, and the four serialisations of each of the ontology's
    files. The page and the diagram are named after the first file."""
    g, graphs, onto = load(sources)
    version = version_or_stop(g, onto)                          # before anything is written
    folder.mkdir(parents=True, exist_ok=True)
    for source, own in zip(sources, graphs):                   # each file as itself
        stem = Path(source).stem
        for ext, fmt in FORMATS.items():
            if ext == ".ttl":
                shutil.copyfile(source, folder / f"{stem}.ttl")     # the source as written
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
