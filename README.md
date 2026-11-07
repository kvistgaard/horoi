# Horoi

Documentation pages for web ontologies.

Horoi writes one page that documents every term of an ontology, each on a card with its definition, and axioms. 

Each term's IRI leads to its card.

The ontology diagram is generated from the ontology file.

The name Horoi comes from the Greek ὅροι, the plural of *horos*, which means a boundary or boundary stone, and in Aristotle's logic both a term and a definition. *Horoi*, or *Definitions*, is also the title of an ancient collection of definitions handed down with Plato's works, though not written by him.

Here's an ontology page, written by Horoi: [Decision ontology](https://w3id.org/do).

## Usage

```bash
horoi build my-ontology.ttl                          # writes dist/
horoi build my-ontology.ttl --example example.ttl    # with an example in Turtle
horoi build my-ontology.ttl --all-tags               # also every release tag v<x.y.z>
horoi diagram my-ontology.ttl --out docs/diagram.svg # the diagram alone
```

`horoi build` writes into `dist/`:

| File | Contents |
|---|---|
| `index.html` | the documentation page, one self-contained file |
| `my-ontology.svg` | the diagram |
| `my-ontology.ttl`, `.rdf`, `.jsonld`, `.nt` | the ontology in four serialisations |
| `<version>/` | the same files for each release |

## What Horoi reads

| From | Horoi reads |
|---|---|
| the `owl:Ontology` | `dcterms:title`, `dcterms:description`, `owl:versionInfo`, `dcterms:modified`, `dcterms:creator`, `dcterms:contributor`, `dcterms:license` |
| people | `schema:name` |
| the namespace | `vann:preferredNamespaceUri` and `vann:preferredNamespacePrefix`, or the ontology IRI |
| each term | `rdfs:label`, `rdfs:comment`, `rdfs:domain`, `rdfs:range`, `rdfs:subClassOf`, `rdfs:subPropertyOf` |

Classes are `owl:Class`, and properties `owl:ObjectProperty` or `owl:DatatypeProperty`, in the ontology's namespace.

## Publishing on GitHub Pages

Set the repository's Pages source to GitHub Actions, and add a workflow:

```yaml
on:
  push:
    tags: ["v*.*.*"]
  workflow_dispatch:
permissions:
  contents: read
  pages: write
  id-token: write
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
        with:
          fetch-depth: 0
      - uses: actions/setup-python@v7
        with:
          python-version: "3.12"
      - run: pip install git+https://github.com/kvistgaard/horoi
      - run: horoi build my-ontology.ttl --all-tags
      - uses: actions/upload-pages-artifact@v5
        with:
          path: dist
  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: github-pages
    steps:
      - uses: actions/deploy-pages@v5
```

A release tag must match the `owl:versionInfo` of the ontology.

## Build from source

```bash
git clone https://github.com/kvistgaard/horoi
pip install -e horoi
python -m unittest discover horoi/tests
```

## Roadmap

- Mobile optimisation
- Repository links
- SHACL support
- Collapsible sidebars
- Zoomable diagrams and other features supporting larger ontologies

## Licence

Apache License 2.0. See [LICENSE](LICENSE).
