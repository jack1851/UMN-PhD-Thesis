# UMN PhD Thesis — Billy Jackson

Search for a right-handed W boson and heavy neutrino of the Left-Right
Symmetric Standard Model, with the CMS experiment. Based on the
[UMN PhD Thesis Template](https://github.com/agude/UMN-PhD-Thesis-Template)
(`mnthesis.cls`).

## Layout

- `thesis.tex` — top-level document; `preamble.tex` holds packages and macros
  shared between the thesis and the slides
- `chapters/` — chapter sources, grouped into groundwork / detector /
  analysis / conclusion
- `preliminaries/` — title page, abstract, acknowledgements, dedication
- `figures/`, `tables/` — standalone TikZ figure sources, images, and tables
- `slides/` — beamer talks that reuse the thesis figure sources
- `thesis.bib` — bibliography, formatted with `hunsrt.bst`

## Building

Requires a TeX distribution with `latexmk` (MacTeX locally, `danteev/texlive`
in CI) and [just](https://github.com/casey/just):

- `just build` — compile the thesis to `obj/thesis.pdf`
- `just watch` — recompile on change
- `just view` — open the compiled PDF
- `just slides` — compile the slides to `slides/obj/slides.pdf`
- `just present` — present the slides with pympress

GitHub Actions builds the thesis PDF on releases and manual dispatch, and
uploads it as the "Compiled Thesis" artifact.
