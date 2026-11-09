# Changelog

All notable changes to Horoi are recorded here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] – 2026-11-09

### Added

- A button and a shortcut, Ctrl+[, to hide and show the sidebar
- A workflow that an ontology's repository calls to publish on GitHub Pages

### Changed

- If the diagram can't be drawn, `horoi build` now publishes the page without it
- The sidebar now lists terms by their labels, with each term's CURIE on hover
- A property's **Connects** row now shows one arrow, with the property's name on it
- On wide screens, the page's main column is now centred
- The sidebar's text is now slightly larger, and its section titles larger still
- The sidebar's sections now have more space between them
- While you search the sidebar, sections with no match now disappear

### Fixed

- In dark mode, the prefix badge beside the title now matches the favicon's colour
- The sidebar labels now use the page's text font
- Hovering **any resource** now says that no range or domain is declared
- On wide screens, the sidebar now lines up with the prefix and title in the header
- The sidebar's section titles now meet the WCAG AA contrast ratio
- On Python versions before 3.12, Horoi no longer stops with a syntax error

### Removed

- The `--check` option of `horoi diagram`

## [0.1.0] – 2026-11-03

First release.

[Unreleased]: https://github.com/kvistgaard/horoi/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/kvistgaard/horoi/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/kvistgaard/horoi/releases/tag/v0.1.0
