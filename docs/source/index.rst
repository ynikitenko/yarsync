.. YARsync documentation master file, created by
   sphinx-quickstart on Mon Jan  2 17:35:34 2023.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

***********************************
Welcome to YARsync documentation!
***********************************

..
    ***********************************
    ***********************************
    ===================================
    ===================================

============
Introduction
============

.. include:: ../../README.rst
   :start-line: 4

.. toctree::
  :caption: Documentation:

  Manual <yarsync.1.md>
  Advanced <details>

.. raw:: latex

    \chapter{Manual}

.. only:: latex

    .. include:: yarsync.1.md
       :parser: myst_parser.sphinx_

.. only:: latex

    .. include:: details.rst

..
   # have no idea why it doesn't affect anything
   :maxdepth: 2
   :titlesonly:

..
    Indices and tables
    ==================

    * :ref:`genindex`
    * :ref:`modindex`
    * :ref:`search`
