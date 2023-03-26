# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

# for readthedocs, https://pennyhow.github.io/blog/making-readthedocs/
# Otherwise yarsync module won't be found.
sys.path.insert(0, os.path.abspath('../../'))
from yarsync.version import __version__

project = 'YARsync'
copyright = '2021-2023, Yaroslav Nikitenko'
author = 'Yaroslav Nikitenko'
release = __version__


# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
        # to include the manual in Markdown
        "myst_parser",
]

templates_path = ['_templates']
exclude_patterns = []


# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'furo'
# html_theme = 'alabaster'
html_static_path = ['_static']
