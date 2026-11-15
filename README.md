# Horoi

Documentation pages for web ontologies.

Horoi writes one HTML page that documents every term of an ontology, each on a card with its definition, and axioms. Each term's IRI leads to its card. The ontology diagram is generated from the ontology file.

The name Horoi comes from the Greek ὅροι, the plural of *horos*, which means a boundary or boundary stone, and in Aristotle's logic both a term and a definition. *Horoi*, or *Definitions*, is also the title of an ancient collection of definitions handed down with Plato's works.

Here's an ontology page, written by Horoi: [Decision ontology](https://w3id.org/do).

## Installation

Horoi needs Python 3.10 or later. Install Horoi from this repository:

```bash
pip install git+https://github.com/kvistgaard/horoi
```

To work on Horoi itself, clone it, install that copy, and run the tests:

```bash
git clone https://github.com/kvistgaard/horoi
pip install -e horoi
python -m unittest discover horoi/tests
```

## Usage

```bash
horoi build my-ontology.ttl                          # writes dist/
horoi build my-ontology.ttl --example example.ttl    # with an example in Turtle
horoi build my-ontology.ttl --all-tags               # also every release tag v<x.y.z>
horoi diagram my-ontology.ttl --out diagram.svg      # the diagram alone
horoi build my-ontology.ttl --diagram folded         # the diagram in the folded style
```

`horoi build` writes into `dist/`:

| File | Contents |
|---|---|
| `index.html` | the documentation page, one self-contained file |
| `my-ontology.svg` | the diagram |
| `my-ontology.ttl`, `.rdf`, `.jsonld`, `.nt` | the ontology in four serialisations |
| `<version>/` | the same files for each release |

### Diagram styles

Choose the style with `--diagram`, on `horoi build` and `horoi diagram`.

| Style             | Diagram                                                                                                                                                                                                            |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `graph` (default) | Each property is an arrow from its domain to its range. The ontology gets one diagram, or a diagram on each class's card, by the rule below.                                                                       |
| `folded`          | Each class is a box listing its properties, with arrows only to its superclasses. A property shows its range only if the ontology declares one. With more than 12 classes, the diagram shows only the class names. |

In the `graph` style, the ontology gets one diagram only if:

- its subclass links form a single chain of classes
- every property starts from a class in that chain, declares no domain, or points back to its own class
- no domain or range is a union or another class expression

Otherwise each class's card gets a diagram of that class.

In the `folded` style, a diagram of more than 12 classes can be zoomed and opened full screen. Click a class to see its properties and the properties that point to it.

Here is the gist ontology in [graph](https://kvistgaard.github.io/horoi/tests/gist/) and in [folded](https://kvistgaard.github.io/horoi/tests/gist-folded/) style.

### Several files and modules

When ontology is kept in several files, that fact should be stated in the main file, in the modules, or in both. 

Give Horoi the files, with the main file first:

```bash
horoi build core.ttl core_restrictions.ttl modules/*.ttl
```

Horoi writes one page from the main file and the files of its parts, and each of those files in four serialisations. The page takes its title, description, version and metadata from the main ontology file.

A file whose ontology is not stated to be a part is left out, with a warning. A file that declares no ontology of its own counts as part of the main one.

Each module gets a section of the page, with its metadata and the cards of its terms. The main file's section comes first, then the modules' sections in the order of their titles. A term defined in several modules has one card, in the first of their sections. The card lists the other modules.

A part that defines no terms, such as a file of restrictions, gets no section. What it states about a term is shown on that term's card.

With `--all-tags`, a release tag that lacks one of the files is left out.

## What the page shows

The page gives the statements below a place of their own. Everything else a term states is on its card, folded under **More statements**.

| About | The page shows |
|---|---|
| the `owl:Ontology` | `dcterms:title` or `skos:prefLabel`, `dcterms:description` or `skos:definition`, `owl:versionInfo` or the version that ends `owl:versionIRI`, `dcterms:modified`, `dcterms:creator`, `dcterms:contributor`, `dcterms:license`. Everything else the ontology states about itself appears in the page's Metadata section. |
| people | `schema:name` |
| the namespace | `vann:preferredNamespaceUri` and `vann:preferredNamespacePrefix`, or the namespace most terms share |
| each term | `rdfs:label` or `skos:prefLabel`, `skos:definition` or `rdfs:comment`, `rdfs:domain`, `rdfs:range`, `rdfs:subClassOf`, `rdfs:subPropertyOf` |
| each class | `owl:equivalentClass`, and the restrictions and unions it is declared with |
| parts and modules | `dcterms:hasPart` and `dcterms:isPartOf` between the files' ontologies, and `rdfs:isDefinedBy` on each term |

A term gets a card only if it is in the ontology's namespace and is typed `owl:Class`, `owl:ObjectProperty` or `owl:DatatypeProperty`.

## Publishing on GitHub Pages

Set the repository's Pages source to GitHub Actions. Under **Settings > Environments > github-pages**, add a deployment tag rule for `v*.*.*`, so that release tags can deploy. Then add a workflow that calls Horoi's:

```yaml
on:
  push:
    tags: ["v*.*.*"]
  workflow_dispatch:
jobs:
  publish:
    uses: kvistgaard/horoi/.github/workflows/publish.yml@main
    with:
      ontology: my-ontology.ttl
      example: example.ttl     # optional
    permissions:
      contents: read
      pages: write
      id-token: write
```

To publish only when your own tests pass, give the tests a job of their own, and make `publish` wait for it with `needs:`.

```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - run: ./run-tests.sh     # your own tests
  publish:
    needs: test
    uses: kvistgaard/horoi/.github/workflows/publish.yml@main
    with:
      ontology: my-ontology.ttl
    permissions:
      contents: read
      pages: write
      id-token: write
```

For an ontology in several files, list them all under `ontology:`, separated by spaces, with the main file first. As with `horoi build`, a file is used only if its ontology is stated to be a part.

For the folded style, add `diagram: folded` under `with:`.

A release tag must match the version of the ontology.

## Roadmap

- Mobile optimisation
- Repository links
- RDFS vocabularies
- SHACL support

## Licence

Apache License 2.0. See [LICENSE](LICENSE).
