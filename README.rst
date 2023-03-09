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

    pip install yarsync

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
    pip install -e yarsync

This installs the ``yarsync`` executable to *~/.local/bin*,
and does not require modifications of ``PYTHONPATH``.
After that, one can pull the repository updates without reinstallation.

To **uninstall**, run

.. code-block:: console

    pip uninstall yarsync

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
  (*--dry-run*).
  Removed files are stored in older commits
  (until the user explicitly removes those).

..
  If a file gets corrupt, it will not be transferred by default,
  but when the user chooses to *pull --backup*, any diverged files will be visible
  (with their different versions preserved).

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
``yarsync`` is a ``Python`` wrapper around ``rsync``
and requires a file system with **hard links**.
Since these are very common tools,
this means that it can easily run on any UNIX-like system.
Moreover, ``yarsync`` is not required to be installed on the remote host:
it is sufficient for ``rsync`` to be installed there.

In particular, ``rsync`` can be found:

* installed on most GNU/Linux distributions,
* installed on `Mac OS <https://eshop.macsales.com/blog/45185-mac-101-learn-the-power-of-rsync-for-backup-remote-archive-systems/>`_,
* can be installed on `Windows <https://superuser.com/questions/300263/how-to-use-rsync-from-windows-pc-to-remote-linux-server>`_.

``yarsync`` runs successfully on Linux.
Please report to us if you have problems (or success) running it on your system.

-------
Safety
-------
``yarsync`` has been used by the author for several years without problems and is tested.
However, any data synchronization may lead to data loss,
and it is recommended to have several data copies
and always do a *--dry-run* (*-n*) first before the actual transfer.

-------------
Documentation
-------------

For the complete documentation, read the installed
or online `manual <https://yarsync.readthedocs.io/en/latest/yarsync.1.html>`_.

For more in-depth topics or alternatives, see
`details <https://yarsync.readthedocs.io/en/latest/details.html>`_.

On the repository github, `release notes <https://github.com/ynikitenko/yarsync/blob/master/NEWS.rst>`_ can be found.
On github pages there is the manual for `yarsync 0.1 <https://ynikitenko.github.io/yarsync/man>`_.

An article in Russian that deals more with ``yarsync`` internals was posted
on `Habr <https://habr.com/ru/post/662163/>`_.

------
Thanks
------

A good number of people have contributed to the improvement of this software.
I'd like to thank
Nilson Silva for packaging ``yarsync`` for Debian,
Mikhail Zelenyy from MIPT NPM for the explanation of
Python `entry points <https://npm.mipt.ru/youtrack/articles/GENERAL-A-87/>`_,
Jason Ryan and Matthew T Hoare for the inspiration to create a package for Arch,
Scimmia for a comprehensive review and suggestions for my PKGBUILD,
Open Data Russia chat for discussions about backup safety,
Habr users and editors, and, finally,
to the creators and developers of ``git`` and ``rsync``.
