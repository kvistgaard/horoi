"""horoi build ONTOLOGY [--out dist] [--example FILE] [--all-tags]
horoi diagram ONTOLOGY [--out FILE] [--check]"""
import argparse
import sys
from pathlib import Path

from rdflib import Graph

from . import __version__
from .build import build
from .diagram import draw


def main(argv=None):
    ap = argparse.ArgumentParser(prog="horoi", description="Publish an OWL ontology as a documentation page with a diagram.")
    ap.add_argument("--version", action="version", version=f"horoi {__version__}")
    sub = ap.add_subparsers(dest="command", required=True)

    b = sub.add_parser("build", help="write the page, the diagram and four serialisations")
    b.add_argument("ontology", help="the ontology, in Turtle")
    b.add_argument("--out", default="dist", help="output folder (default: dist)")
    b.add_argument("--example", help="a Turtle file to show as the example")
    b.add_argument("--all-tags", action="store_true", help="also build every git tag v<x.y.z>")

    d = sub.add_parser("diagram", help="draw the diagram only")
    d.add_argument("ontology", help="the ontology, in Turtle")
    d.add_argument("--out", help="the SVG file (default: <ontology>.svg beside it)")
    d.add_argument("--check", action="store_true", help="exit 1 if the SVG file differs from a fresh drawing")

    args = ap.parse_args(argv)
    if args.command == "build":
        latest, built = build(args.ontology, args.out, args.example, args.all_tags)
        print(f"built {latest} at {args.out}" + (f"; releases: {', '.join(built)}" if built else ""))
        return 0

    g = Graph()
    g.parse(args.ontology, format="turtle")
    svg = draw(g)
    out = Path(args.out) if args.out else Path(args.ontology).with_suffix(".svg")
    if args.check:
        if not out.exists() or out.read_text(encoding="utf-8") != svg:
            print(f"{out} is out of date; run horoi diagram {args.ontology} --out {out}", file=sys.stderr)
            return 1
        print(f"{out} is up to date")
        return 0
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(svg, encoding="utf-8", newline="\n")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
