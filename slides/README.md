# Defense Slides
Holding `beamer`-based LaTeX slides for my defense with
a `beamer` style using UMN colors and the experimental logos.

- `figs` : directory holding slide-specific figures and plots
- `heavy_photon_logo.jpg` and `ldmx_logo.pdf` : experimental logos included in header of each slide
- `preamble.tex` : preamble that defines helpful commands and colors
- `both-style.tex` : another, second preamble defining style of slides
    - "both" references both experiments, this is where you would change logos if desired
- `slides.tex` : actual source for slides that `\input`s the other preamble files at the top
