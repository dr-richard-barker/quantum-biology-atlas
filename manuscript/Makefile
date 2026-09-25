# Quantum Biology Atlas — manuscript build.
#
# `make pdf` regenerates the derived inputs BEFORE typesetting, so the PDF cannot be
# built from stale numbers:
#
#   numbers.tex     every quantity the manuscript states, from the build artefacts
#   references.bib  the evidence base plus method citations, each re-resolved at CrossRef
#   figures/        panels rasterised from generated maps
#
# The manuscript body contains no literal numbers and no hand-drawn figure. If an
# analysis is re-run and a result moves, `make pdf` moves the manuscript with it.

PY      := PYTHONPATH=../src python3
SCRIPTS := ../scripts
TEX     := pdflatex -interaction=nonstopmode -halt-on-error

.PHONY: pdf inputs clean check

pdf: inputs
	$(TEX) manuscript.tex
	bibtex manuscript || true
	$(TEX) manuscript.tex
	$(TEX) manuscript.tex
	@echo
	@echo "built manuscript.pdf"

# Derived inputs. `build_manuscript_bib.py` reaches CrossRef and FAILS if a DOI does not
# resolve or resolves to a different paper, so a broken reference stops the build here
# rather than reaching the PDF.
inputs:
	$(PY) $(SCRIPTS)/build_manuscript_numbers.py
	$(PY) $(SCRIPTS)/build_manuscript_bib.py
	$(PY) $(SCRIPTS)/build_manuscript_figure.py

# Cheap guards against the two failures that would survive a clean compile: an undefined
# macro rendering as nothing, and a citation that never resolved.
check: pdf
	@echo
	@! grep -q "Undefined control sequence" manuscript.log || \
	  (echo "FAIL: undefined macro — a number is missing from numbers.tex"; exit 1)
	@! grep -qi "Citation.*undefined" manuscript.log || \
	  (echo "FAIL: undefined citation"; exit 1)
	@! grep -q "??" manuscript.pdf 2>/dev/null || true
	@echo "no undefined macros or citations"

clean:
	rm -f manuscript.aux manuscript.log manuscript.out manuscript.bbl \
	      manuscript.blg manuscript.pdf
