===========================
YARsync 0.2
===========================

To convert old synchronization file to the new directory format, one can use from the working directory

    cat .ys/sync.txt && mkdir .ys/sync && touch .ys/sync/$(cat .ys/sync.txt|sed 's/,/_/g').txt && rm .ys/sync.txt

Every repository must have its name. It is no longer automatically deduced from host name.
In particular, nameless repositories on external drives can no longer be mixed with local repositories.

Bug fixes
---------

* --no-inc-recursion is always active for pull and push.
  Fixes a bug when pull --new retransferred files already present in commits.
* pull --new disables automatic checkout of commits after merge.
  This prevents deletion of uncommitted files in the working directory (they should be preserved when using --new).

Improvements
------------

* commit adds an option *--limit*.
  pull and push allow destination to have commits missing on source
  if local repository has a commit limit.
  Status shows the commit limit (if present). Commit limits are logged (during commit).
* init prompts for input when no repository name on the command line is given.
* status no longer outputs group and owner changes.
  This information is ignored by yarsync and is considered noise.
  Set proper user and group for all files when needed.
* improves output in case of errors.

* pull changes:

  * *--new* allows local repository to have uncommitted changes.
  * --new allows local or remote commits to be missing.

* pull and push changes:

  * Improves output for pull and push. All files for commits that are transferred as a whole (that is new ones)
    are being output on a single line (that commit name).
    This makes output more focused on the actual changes in the working directory
    and on existing commits (if they contained changes).
  * yarsync no longer updates user and group ids for pull and push (and indirectly clone).
    This allows one to have different user and group ids on different machines and storage drives, ignoring this metadata.
    yarsync repositories are supposed to contain data belonging to one user.
  * Repositories are not checked for changes in the working directory if --force is used for push or pull.

Backward incompatible changes
-----------------------------

* clone semantics changed.
  sets name of the cloned repository.
* Turns off "overwrite" (--ignore-existing) functionality.
  Waiting for https://github.com/WayneD/rsync/issues/357 to be fixed.
* Name is required for each repository. This assists synchronization.
* Repository name is no longer stored in repository.txt, but in repo_<name>.txt.
  This allows to know remote repository names from listing their configuration files.

Technical changes
-----------------
* yarsync is tested for Python 3.11.

* yarsync development classifier on PyPI becomes "5 - Production/Stable".

* Adds .gitattributes (to log revisions of functions).

* Test improvements:

  * Adds helpers.py (for cloning test repositories). Removes test_real_copy.py.
  * Fixes hardlink fixtures. 

* Implements init --merge option. It is not tested and shall be added in the next release.
* _print_command accepts lists and properly escapes commands with spaces.
  String and list representations of commands are no longer needed.
* _commit method accepts arguments explicitly.
* Adds *_Config* and *_Sync* helper classes.

* Documentation improvements:

  * Adds a howto for synchronizing repositories after adding external data to both of them (see details).
  * Documentation uses Sphinx. Needs fixes for pdf version.

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
