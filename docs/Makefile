# Minimal makefile for Sphinx documentation
#

# You can set these variables from the command line, and also
# from the environment for the first two.
SPHINXOPTS    ?=
SPHINXBUILD   ?= sphinx-build
SOURCEDIR     = source
BUILDDIR      = build

# Put it first so that "make" without argument is like "make help".
help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

# to see a man page on the fly, use
# cat source/yarsync.1.md | sed 's/^##/#/g' | pandoc -s -t man | /usr/bin/man -l -
man:
	@cat source/yarsync.1.md | grep -v '# YARsync manual' | sed 's/^##/#/g' \
     | pandoc -s -t man > yarsync.1

.PHONY: help Makefile man

# Catch-all target: route all unknown targets to Sphinx using the new
# "make mode" option.  $(O) is meant as a shortcut for $(SPHINXOPTS).
%: Makefile
	@$(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)
