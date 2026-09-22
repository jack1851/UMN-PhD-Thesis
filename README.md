# UMN PhD Thesis — Billy Jackson

Search for a right-handed W boson and heavy neutrino of the Left-Right
Symmetric Standard Model, with the CMS experiment. Based on the
[UMN PhD Thesis Template](https://github.com/agude/UMN-PhD-Thesis-Template)
(`mnthesis.cls`).

## Layout

- `thesis.tex` — top-level document; `preamble.tex` holds the packages shared
  between the thesis and the slides. Notation macros (`\WR`, `\mlljj`, `\pt`,
  ...), units, cleveref, and acronyms come from
  [billy-common](https://github.com/jack1851/billy-common), whose particle
  macros mirror the analysis note's `tex/macros.tex` so note text pastes in
  unchanged. Locally it is found through `~/Library/texmf`; CI checks it out
  next to the thesis.
- `chapters/` — chapter sources, grouped into groundwork / detector /
  analysis / conclusion
- `preliminaries/` — title page, abstract, acknowledgements, dedication
- `figures/`, `tables/` — standalone TikZ figure sources, images, and tables
- `slides/` — beamer talks that reuse the thesis figure sources
- `thesis.bib` — bibliography, formatted with `hunsrt.bst`
- `progress/` — word-count and open-item tracking; see `just progress`

## Building

Requires a TeX distribution with `latexmk` (MacTeX locally, `danteev/texlive`
in CI) and [just](https://github.com/casey/just):

- `just build` — compile the thesis to `obj/thesis.pdf`
- `just watch` — recompile on change
- `just view` — open the compiled PDF
- `just slides` — compile the slides to `slides/obj/slides.pdf`
- `just present` — present the slides with pympress
- `just progress` — count words and open items per chapter at every commit
  (needs [uv](https://github.com/astral-sh/uv) and `texcount`), print a
  summary, and draw `progress/out/progress.png`; targets live in
  `progress/targets.toml`

GitHub Actions builds the thesis PDF on releases and manual dispatch, and
uploads it as the "Compiled Thesis" artifact.
