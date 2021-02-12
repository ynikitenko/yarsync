=======
Yarsync
=======

Yarsync is a program to synchronize data (files and directories) between Linux systems. 

It allows to use ``git`` semantics while working with files. This can be helpful in two ways:

* easier manage files and backups, not to repeat complete paths and synchronization options every time.
* allow files synchronization to be done uniformly with other repositories (e.g. while using `myrepos <https://myrepos.branchable.com/>`_).

Examples::

    yarsync push <remote>
    # push data to the remote
    yarsync pull <remote>
    # pull data from the remote

------------------
Development status
------------------
This program works and is used by its author without errors, and has a good test coverage.

At the moment I'm going to add several special options. Documentation will be also improved before the first tagged release.

Stay tuned!
