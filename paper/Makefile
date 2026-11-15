# Paper 1 build (spec/paper_build_spec.md).
#   make artifacts            generated tables, figures and numbers (refuses before the paper-v1.2 tag)
#   make pdf [MODE=final]     runs make artifacts first; review version by default (anonymous, line numbers); final = camera-ready
#   make check                generator twice (byte compare), source checks, both PDFs build, aclpubcheck on the
#                             final PDF only (the review PDF's line and page numbers are review features)
#   make pubcheck-env         install aclpubcheck (pinned) into .venv-pubcheck
MODE ?= review
ROOT := ..
PY ?= $(abspath $(ROOT)/.venv/bin/python)
PUBCHECK_COMMIT := fb584f3de4b0c1d68b6e02f961e896c12440644b
PUBCHECK := .venv-pubcheck/bin/aclpubcheck
BUILD := build
TEXENV := TEXINPUTS=./acl//: BSTINPUTS=./acl//: BIBINPUTS=.:
PRETEX := $(if $(filter final,$(MODE)),-usepretex='\def\PaperModeFinal{}',)

# aclpubcheck always exits 0: fail on its own summary ("We detected N error(s)", N >= 1) or any parsing error;
# warnings are printed but do not fail. Report: build/pubcheck-<mode>.txt and build/pubcheck-<mode>/errors-*.json.
define pubcheck
$(PUBCHECK) --paper_type long -o $(BUILD)/pubcheck-$(1) $(BUILD)/main-$(1).pdf | tee $(BUILD)/pubcheck-$(1).txt
! grep -Eq "We detected [1-9][0-9]* errors?|Parsing Error" $(BUILD)/pubcheck-$(1).txt
endef

.PHONY: artifacts pdf check pubcheck-env clean

artifacts:
	cd $(ROOT) && $(PY) -m paper.scripts.make_artifacts

pdf: artifacts
	$(TEXENV) latexmk -pdf -interaction=nonstopmode -halt-on-error -outdir=$(BUILD) -jobname=main-$(MODE) $(PRETEX) main.tex

check:
	rm -rf $(BUILD)/check-1 $(BUILD)/check-2
	cd $(ROOT) && $(PY) -m paper.scripts.make_artifacts --out paper/$(BUILD)/check-1
	cd $(ROOT) && $(PY) -m paper.scripts.make_artifacts --out paper/$(BUILD)/check-2
	diff -r $(BUILD)/check-1 $(BUILD)/check-2
	diff -r $(BUILD)/check-1 generated
	cd $(ROOT) && $(PY) -m paper.scripts.check_sources
	$(MAKE) pdf MODE=review
	$(MAKE) pdf MODE=final
	$(call pubcheck,final)

pubcheck-env:
	python3 -m venv .venv-pubcheck
	.venv-pubcheck/bin/pip install --quiet "git+https://github.com/acl-org/aclpubcheck@$(PUBCHECK_COMMIT)"

clean:
	rm -rf $(BUILD)
