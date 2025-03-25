_default:
    @just --list

use_denv := env("USE_DENV", "true")
use_texfot := env("USE_TEXFOT", "false")

latexmk_prefix := if use_denv == "true" {
  "denv texfot "
} else if use_texfot == "true" {
  "texfot "
} else { 
  ""
}

latexmk_opts := "-pdf -shell-escape -bibtex -f -outdir=obj/"
latexmk := latexmk_prefix + "latexmk " + latexmk_opts

# compile thesis pdf into repo root directory
build:
    {{ latexmk }} thesis.tex

# have latexmk watch for changes and rebuild
watch:
    {{ latexmk }} -pvc thesis.tex

# open compiled pdf
view:
    open obj/thesis.pdf

# build slides
slides:
    cd slides && {{ latexmk }} slides.tex

# present slides with pympress
present: slides
    #!/bin/sh
    set -ex
    cd slides
    . venv/bin/activate
    pympress obj/slides.pdf

# build diagram file for quicker diagram development
diagram:
    {{ latexmk }} -pvc -outdir=obj/ diagram.tex

# make sure this location can present with pympress
init-present:
  #!/bin/sh
  sudo apt-get install \
    python3 \
    python3-pip \
    libgtk-3-0 \
    libpoppler-glib8 \
    libcairo2 \
    python3-gi \
    python3-cairo \
    python3-gi-cairo \
    gobject-introspection \
    libgirepository-1.0-1 \
    libgirepository1.0-dev \
    gir1.2-gtk-3.0 \
    gir1.2-poppler-0.18
  cd slides
  python3 -m venv venv --system-site-packages --prompt present
  . venv/bin/activate
  pip install pympress
