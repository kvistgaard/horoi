"""Build an ontology's published files: the documentation page, the diagram,
and the ontology in four serialisations, for the latest version and for every
released one.

Layout of the output folder, for an ontology file named <stem>.ttl:
    index.html, <stem>.svg, <stem>.ttl, .rdf, .jsonld, .nt    the latest version
    <version>/index.html, <version>/<stem>.ttl, ...           each release

A release is a git tag v<x.y.z>. Its files are built from the ontology as
committed at that tag, and a tag whose owl:versionInfo differs is refused.
"""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from rdflib import Graph, Literal
from rdflib.namespace import OWL, RDF

from .page import CREDIT, write

FORMATS = {".ttl": "turtle", ".rdf": "pretty-xml", ".jsonld": "json-ld", ".nt": "nt"}


def version_of(g):
    onto = next(g.subjects(RDF.type, OWL.Ontology), None)
    v = g.value(onto, OWL.versionInfo) if onto is not None else None
    if not isinstance(v, Literal):
        sys.exit("horoi: the ontology has no owl:versionInfo")
    return str(v)


def build_one(source, folder, stem, example=None, credit=CREDIT):
    """Write the page, the diagram and the four serialisations of one ontology file."""
    folder.mkdir(parents=True, exist_ok=True)
    g = Graph()
    g.parse(source, format="turtle")
    for ext, fmt in FORMATS.items():
        if ext == ".ttl":
            shutil.copyfile(source, folder / f"{stem}.ttl")     # the source as written
        else:
            g.serialize(destination=folder / f"{stem}{ext}", format=fmt, encoding="utf-8")
    write(g, folder, stem, example, credit=credit)
    return version_of(g)


def git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, check=True).stdout


def build(ontology, out, example=None, all_tags=False, credit=CREDIT):
    ontology, out = Path(ontology).resolve(), Path(out)
    stem = ontology.stem
    example_text = Path(example).read_text(encoding="utf-8") if example else None
    if out.exists():
        shutil.rmtree(out)
    built = []
    if all_tags:
        repo = Path(git(ontology.parent, "rev-parse", "--show-toplevel").decode().strip())
        rel = ontology.relative_to(repo).as_posix()
        tags = [t for t in git(repo, "tag", "--list", "v*").decode().split() if re.fullmatch(r"v\d+\.\d+\.\d+", t)]
        for tag in tags:
            with tempfile.TemporaryDirectory() as tmp:
                src = Path(tmp) / f"{stem}.ttl"
                src.write_bytes(git(repo, "show", f"{tag}:{rel}"))
                version = build_one(src, Path(tmp) / "build", stem, example_text, credit)
                if f"v{version}" != tag:
                    sys.exit(f"horoi: tag {tag} holds owl:versionInfo {version}")
                shutil.copytree(Path(tmp) / "build", out / version)
            built.append(version)
    latest = build_one(ontology, out, stem, example_text, credit)
    if not (out / latest).exists():     # a release keeps the files of its tag
        shutil.copytree(out, out / latest, ignore=lambda d, names: [n for n in names if (Path(d) / n).is_dir()])
    return latest, built
