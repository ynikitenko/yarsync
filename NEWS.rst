===============
  YARsync 0.2
===============

YARsync v0.2 was released on the 8th of March, 2023.
Its main features were synchronization, commit limit and cloning.

Synchronization information is now stored in the directory *.ys/sync/*.
It contains information on the most recent synchronized commits for each known repository.
This information is transferred between replicas during ``pull``, ``push`` and ``clone``.
This allows ``yarsync`` repositories to better support the 3-2-1 backup rule.

To convert an old synchronization file to the new directory format, from the working directory one can use

    cat .ys/sync.txt && mkdir .ys/sync && touch .ys/sync/$(cat .ys/sync.txt|sed 's/,/_/g').txt && rm .ys/sync.txt

To properly support synchronization information, now each repository must have a unique name.
The name is no longer automatically deduced from the host name,
but contained in *.ys/repo_<repo_name>.txt*.
In particular, nameless repositories on external drives cannot be mixed with nameless local repositories.
One can set repository name with ``init`` (this command does not affect existing files and is always safe).

A user of ``yarsync`` was concerned about the fact that ``rsync`` does not work well with millions of files,
and proposed automatically removing old commits.
To achieve that, *commit limit* was introduced. It can be set using an option *limit* of ``commit``.
When there appears more than that limit, older commits are removed during ``commit``.
``pull`` and ``push`` don't check whether destination has commits missing on source if
the local repository has commit limits
(it makes a repository with commit limit more like a central repository).

Bug fixes
---------

* *--no-inc-recursion* is always active for ``pull`` and ``push``.
  Fixes a bug when ``pull`` *--new* retransferred files already present in commits.
* ``pull`` *--new* disables automatic checkout of commits after merge.
  This prevents deletion of uncommitted files in the working directory
  (they should be preserved when using *--new*).

Improvements
------------

* ``commit`` adds an option *--limit*.
  ``status`` shows the commit limit (if present). Commit limits are logged (during commit).
* ``init`` prompts for input when no repository name on the command line is given.
* ``status`` no longer outputs group and owner changes.
  This information is ignored by ``yarsync`` and considered noise.
  Set proper user and group for all files when needed.
* Improves output in case of errors.

* ``pull`` changes:

  * *--new* allows local repository to have uncommitted changes.
  * *--new* allows local or remote commits to be missing.

* ``pull`` and ``push`` changes:

  * Improves output for ``pull`` and ``push``. All files for commits that are transferred as a whole (that is new ones)
    are being output on a single line (that commit name).
    This makes output more focused on the actual changes in the working directory
    and on existing commits (if they contained changes).
  * ``yarsync`` no longer updates user and group ids for ``pull`` and ``push`` (and indirectly ``clone``).
    This allows one to have different user and group ids on different machines and storage drives, ignoring this metadata.
    yarsync repositories are supposed to contain data belonging to one user.
  * If local repository has a commit limit,
    destination can have commits missing on source.

Backward incompatible changes
-----------------------------

* ``clone`` command and interface changed. ``clone`` allows copying to a remote.
  New repository name must be provided explicitly.
  Cloning from inside a repository with *rsync-filter* is allowed.
* Turns off ``pull/push`` *--overwrite* (``rsync`` *--ignore-existing*) functionality.
  Waiting for https://github.com/WayneD/rsync/issues/357 to be fixed.
* Repositories are not checked for changes in the working directory
  for ``push`` or ``pull`` if *--force* option is given.
* Name for each repository is required (to assist synchronization).
* Repository name is no longer stored in *repository.txt*, but in *repo_<name>.txt*.
  This allows ``yarsync`` to know remote repository names from listing their configuration files.

Technical changes
-----------------
Documentation has been moved to ReadTheDocs.

* ``yarsync`` is tested for Python 3.11.

* ``yarsync`` development classifier on PyPI becomes "5 - Production/Stable".

* Adds *.gitattributes* (to log revisions of functions).

* Tests improvements:

  * Adds *helpers.py* (for cloning test repositories).
  * Fixes hardlink fixtures. 

* Implements ``init`` *--merge* option. It is not tested and shall be added in the next release.
* *_print_command* accepts lists and properly escapes commands with spaces.
  String and list representations of commands are no longer needed.
* *_commit* method accepts arguments explicitly.
* Adds *_Config* and *_Sync* helper classes.

* Documentation improvements:

  * Adds a how-to for synchronizing repositories after adding external data to both of them (see details section).
  * Documentation uses Sphinx. Needs fixes for pdf version.

Test coverage is 79% (253/1224 missing/total).

Publication
-----------
``yarsync`` v0.1 was packaged for Arch Linux, Debian and PyPI (and will be updated for v0.2).

A talk on ``yarsync`` was made at the Winter seminar of the Physics Institute of the RWTH Aachen University
in Montafon on February 2023.

The program was announced on the ``rsync`` mailing list, published on Arch Wiki and Arch Forum,
and in several Russian programming Telegram chats.

===========================
YARsync 0.1.1+deb
===========================
YARsync patch release 0.1.1+deb was done on 6 July 2022.

* Fixes manual for whatis (lexgrog) parsing.
* Documentation improvements. Adds Installation, Documentation and Thanks sections to README.

===========================
YARsync 0.1.1
===========================
YARsync patch release 0.1.1 was made on 30 June 2022.
It adds a manual page, improves output and supports Python 3.6.

Improvements
------------
Tested and works for Python 3.6.
Improves output handling in commit (allows verbosity settings).
rsync always outputs error messages.

Bug fixes
---------
pull and push print output correctly.

=======================
  YARsync release 0.1
=======================

The first tagged release YARsync v0.1 was made on 21st-23rd June 2022.
The program works with Python 3.7, 3.8, 3.9, 3.10 and PyPy 3.
Test coverage is 76% (209/889 missing to total).
