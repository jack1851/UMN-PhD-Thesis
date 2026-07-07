# Talk Slides

`beamer`-based LaTeX slides for talks about the WR boson and heavy neutrino
search, with a style using UMN colors and the experiment logos. Currently
holds the UMN HEP seminar talk.

- `slides.tex` : slide source; pulls figure and table sources from
  `../figures/` and `../tables/`
- `preamble_slides.tex` : beamer theme and colors, on top of the shared
  `../preamble.tex`
- `figs` : directory holding slide-specific figures and plots
- `cms_logo.png` and `goldy_leaning.png` : CMS and UMN logos included in the
  header of each slide

Build from the repo root with `just slides`; present with `just present`
(pympress, from the local `venv`).
