=======
YARsync
=======

Yet Another Rsync is a file synchronization and backup tool.
It can be used to synchronize data between different hosts
or locally (for example, to a backup drive).
It provides a familiar ``git`` command interface while working with files.

YARsync is a Free Software project covered by the GNU General Public License version 3.

-------------
Installation
-------------
``yarsync`` is packaged for Debian/Ubuntu.

For Arch Linux, install the ``yarsync`` package `from AUR <https://aur.archlinux.org/packages/yarsync>`_.
Packages for other distributions are welcome.

For an installation `from PyPI <https://pypi.org/project/yarsync/>`_, run

.. code-block:: console

    pip3 install yarsync

If you don't want to install it system-wide (e.g. for testing), see installation in a virtual environment in the
`Developing <#developing-and-contributing>`_ section.

For macOS Ventura the built-in version of ``rsync`` in macOS is 2.6.9, while ``yarsync`` requires a newer one. Run

.. code-block:: console

    brew install rsync
    pip3 install yarsync

If ``rsync: --outbuf=L: unknown option`` occurs, make sure that a new version of rsync has been installed.

Since there is no general way to install a manual page for a Python package,
one has to do it manually. For example, run as a superuser:

.. code-block:: console

    wget https://github.com/ynikitenko/yarsync/raw/master/docs/yarsync.1
    gzip yarsync.1
    mv yarsync.1.gz /usr/share/man/man1/
    mandb

Make sure that the manual path for your system is correct.
The command ``mandb`` updates the index caches of manual pages.

One can also install the most recent program version
`from GitHub <https://github.com/ynikitenko/yarsync>`_.
It incorporates latest improvements,
but at the same time is less stable (new features can be changed or removed).

.. code-block:: console

    git clone https://github.com/ynikitenko/yarsync.git
    pip3 install -e yarsync

This installs the ``yarsync`` executable to *~/.local/bin*,
and does not require modifications of ``PYTHONPATH``.
After that, one can pull the repository updates without reinstallation.

To **uninstall**, run

.. code-block:: console

    pip3 uninstall yarsync

and remove the cloned repository.

--------------------
Design and features
--------------------

``yarsync`` can be used to manage hierarchies of unchanging files,
such as music, books, articles, photographs, etc.
Its final goal is to have the same state of files across
different computers.
It also allows to store backup copies of data and easily copy, update or recover that.
``yarsync`` is

distributed
  There is no central host or repository for ``yarsync``.
  If different replicas diverge,
  the program assists the user to merge the repositories manually.

efficient
  The program is run only on user demand,
  and does not consume system resources constantly.
  Already transferred files will never be transmitted again.
  This allows the user to rename or move files
  or whole directories without any costs,
  driving constant improvements on the repository.

non-intrusive
  ``yarsync`` does nothing to user data.
  It has no complicated packing or unpacking.
  All user data and program configuration are stored as usual files in the file system.
  If one decides to stop using ``yarsync``,
  they can simply remove the configuration directory at any time.

simple
  ``yarsync`` does not implement complicated file transfer algorithms,
  but uses an existing, widely accepted and tested tool for that.
  User configuration is stored in simple text files,
  and repository snapshots are usual directories, which can be modified, copied
  or browsed from a file manager.
  All standard command line tools can be used in the repository,
  to assist its recovery or to allow any non-standard operations
  (for the users who understand what they do).
  Read the ``yarsync`` documentation to understand its (simple) design.

safe
  ``yarsync`` does its best to preserve user data.
  It always allows one to see what will be done before any actual modifications
  (*--dry-run*). It is its advantage compared to continous synchronization tools,
  that may be dangerous if local repository gets corrupt (e.g. encrypted by a trojan).
  Removed files are stored in older commits
  (until the user explicitly removes those).

  WARNING: ``yarsync`` works for unchanged files by default. If a file was changed (corrupted),
  synchronisation will propagate that for every hard link. See safety_ below.


---------
Commands
---------

::

    checkout
    clone
    commit
    diff
    init
    log
    pull
    push
    remote
    show
    status

See ``yarsync --help`` for full command descriptions and options.

----------------------------
Requirements and limitations
----------------------------
``yarsync`` is a Python wrapper (available for ``Python>=3.6``) around ``rsync``
and requires a file system with **hard links**.
Since these are very common tools,
this means that it can easily run on any UNIX-like system.
Moreover, ``yarsync`` is not required to be installed on the remote host:
it is sufficient for ``rsync`` to be installed there.

``yarsync`` has been extensively tested on GNU/Linux distributions, and it has been successfully used on:

* `Mac OS <https://eshop.macsales.com/blog/45185-mac-101-learn-the-power-of-rsync-for-backup-remote-archive-systems/>`_,
* `Windows <https://superuser.com/questions/300263/how-to-use-rsync-from-windows-pc-to-remote-linux-server>`_ with WSL.

If it ever fails on your specific system, please inform us. Patches are welcome.

.. _safety:

-------
Safety
-------
``yarsync`` has been used by the author for several years without problems and is tested.
However, any data synchronization may lead to data loss,
and it is recommended to have several data copies
and always do a *--dry-run* (*-n*) first before the actual transfer.

See the open `issues <https://github.com/ynikitenko/yarsync/issues?q=state%3Aopen%20label%3A%22safety%22>`_ on safety.

..
  If a file gets corrupt, it will not be transferred by default,
  but when the user chooses to *pull --backup*, any diverged files will be visible
  (with their different versions preserved).

-------------
Documentation
-------------

For the complete documentation, read the installed
or online `manual <https://yarsync.readthedocs.io/en/latest/yarsync.1.html>`_.

A 10-minute `video <https://www.youtube.com/watch?v=1qRZ1mIuD3U>`_ with motivation, implementation ideas and overview
of the tool (and 6 minutes more for questions) was recorded during a conference in 2024.

For more in-depth topics or alternatives, see
`details <https://yarsync.readthedocs.io/en/latest/details.html>`_.

On the repository github, `release notes <https://github.com/ynikitenko/yarsync/blob/master/NEWS.rst>`_ can be found.
On github pages there is the manual for `yarsync 0.1 <https://ynikitenko.github.io/yarsync/man>`_.

An article in Russian that deals more with ``yarsync`` internals was posted
on `Habr <https://habr.com/ru/post/662163/>`_.

---------------------------
Developing and contributing
---------------------------

You can use a virtual environment in order to avoid messing with your system while working on ``yarsync``:

.. code-block:: console

    python3 -m venv ~/.venv/yarsync_dev
    source ~/.venv/yarsync_dev/bin/activate
    # download a clean repository or use the existing one with your changes
    mkdir tmp && cd tmp
    git clone https://github.com/ynikitenko/yarsync

To build and then install ``yarsync``, run the following commands from the root of the repository:

.. code-block:: console

    cd yarsync
    pip install -r requirements.txt
    pip install .

Please make sure to run the tests and ensure you haven't broken anything before submitting a pull request.

.. code-block:: console

    pytest
    # Or to increase verbosity level
    # pytest -vvv

You can run tests on all supported Python versions by simply running ``tox`` in your virtual environment.
Make sure to have installed some supported Python versions beforehand (at least two for ``tox`` to be useful).

.. code-block:: console

    tox

After all tests you can remove the created directories or leave them for future tests.

Tools you may like to use
=========================

A linter, like `pylint <https://github.com/pylint-dev/pylint>`_ or `ruff <https://docs.astral.sh/ruff/>`_, can improve the quality of your code.

A dependency manager (like `uv <https://docs.astral.sh/uv/>`_) permits one to easily code in several Python versions and manage virtual environments.

These are the most basic commands associated with uv.

``uv tool install tox --with tox-uv``

``uv tool install ruff``

``uv python install 3.13``

``uv python pin 3.13``

``uv sync``

``uv run -- yarsync``

You can also directly enter a venv with

``uv venv``

``uv`` can be really useful when combined with `tox` because it will automatically create the required virtualenvs, install the required version, and install for each versions its dependencies before running the tests for all python versions.

.. code-block:: console

    # first, make sure you have uv installed.
    # you then need to install tox with the tox-uv plugin.
    uv tool install tox --with tox-uv
    # You will maybe need to enable tox-uv in the pyproject.toml file.
    # Finally, you can just run tox and it will do the rest.
    tox

------
Thanks
------

A good number of people have contributed to the improvement of this software.
I'd like to thank
(in most recent order):
AUR user Simona for reporting an issue, Colin Watson for reporting a similar issue and fixing a packaging bug
and *statzitz* for extending documentation for release *v0.3.2*,
*statzitz* for great help with updating tests for release *v0.3.1*, documentation and configuration,
Yong Xiang Lin for several bug reports and useful discussions,
Arch Linux users for their notifications and improvements of my PKGBUILD,
Nilson Silva for packaging ``yarsync`` for Debian,
Mikhail Zelenyy from MIPT NPM for the explanation of
Python `entry points <https://npm.mipt.ru/youtrack/articles/GENERAL-A-87/>`_,
Jason Ryan and Matthew T Hoare for the inspiration to create a package for Arch,
Scimmia for a comprehensive review and suggestions for my PKGBUILD,
Open Data Russia chat for discussions about backup safety,
Habr users and editors, and, finally,
to the creators and developers of ``git`` and ``rsync``.
