"""horoi build ONTOLOGY [MORE ...] [--out dist] [--example FILE] [--all-tags] [--diagram graph|folded]
horoi diagram ONTOLOGY [MORE ...] [--out FILE] [--diagram graph|folded]"""
import argparse
import sys
from pathlib import Path

from . import __version__
from .build import build, distinct, load
from . import folded
from .diagram import Undrawable, draw

STYLE = "the diagram's style: graph, with an arrow per property, or folded, with a class's properties folded into its box (default: graph)"
FILES = "the ontology, in Turtle; for an ontology kept in several files, all of them, the one the page documents first"


def main(argv=None):
    ap = argparse.ArgumentParser(prog="horoi", description="Publish an OWL ontology as a documentation page with a diagram.")
    ap.add_argument("--version", action="version", version=f"horoi {__version__}")
    sub = ap.add_subparsers(dest="command", required=True)

    b = sub.add_parser("build", help="write the page, the diagram and four serialisations")
    b.add_argument("ontology", nargs="+", help=FILES)
    b.add_argument("--out", default="dist", help="output folder (default: dist)")
    b.add_argument("--example", help="a Turtle file to show as the example")
    b.add_argument("--all-tags", action="store_true", help="also build every git tag v<x.y.z>")
    b.add_argument("--diagram", choices=("graph", "folded"), default="graph", help=STYLE)

    d = sub.add_parser("diagram", help="draw the diagram only")
    d.add_argument("ontology", nargs="+", help=FILES)
    d.add_argument("--out", help="the SVG file (default: <ontology>.svg beside the first file)")
    d.add_argument("--diagram", choices=("graph", "folded"), default="graph", help=STYLE)

    args = ap.parse_args(argv)
    if args.command == "build":
        latest, built = build(args.ontology, args.out, args.example, args.all_tags, args.diagram)
        print(f"built {latest} at {args.out}" + (f"; releases: {', '.join(built)}" if built else ""))
        return 0

    g, _, onto = load(distinct(args.ontology))
    try:
        svg = draw(g, onto) if args.diagram == "graph" else folded.draw(g, onto, page=False)
    except Undrawable as e:
        sys.exit(f"horoi: {e}")
    out = Path(args.out) if args.out else Path(args.ontology[0]).with_suffix(".svg")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(svg, encoding="utf-8", newline="\n")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
