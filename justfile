_default:
    @just --list

use_texfot := env("USE_TEXFOT", "false")

latexmk_prefix := if use_texfot == "true" {
  "texfot "
} else {
  ""
}

latexmk_opts := "-pdf -shell-escape -bibtex -f -outdir=obj/"
latexmk := latexmk_prefix + "latexmk " + latexmk_opts

# mirror the source tree under obj/ so \include can write its aux files there
_objdirs:
    for d in $(find chapters preliminaries -type d); do mkdir -p "obj/$d"; done

# compile thesis pdf into obj/thesis.pdf
build: _objdirs
    {{ latexmk }} thesis.tex

# have latexmk watch for changes and rebuild
watch: _objdirs
    {{ latexmk }} -pvc thesis.tex

# open compiled pdf
view:
    open obj/thesis.pdf

# count words and open items per chapter across git history; plot progress/out/progress.png
progress *args:
    uv run progress/progress.py {{ args }}

# build slides into slides/obj/slides.pdf
slides:
    cd slides && {{ latexmk }} slides.tex

# present slides with pympress
present: slides
    #!/bin/sh
    set -ex
    cd slides
    . venv/bin/activate
    pympress obj/slides.pdf
