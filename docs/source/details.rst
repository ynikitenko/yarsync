========
Advanced
========

-----------
Usage tips
-----------

Since ``yarsync`` allows to use a command interface similar to ``git``,
one can synchronize several repositories simultaneously using
`myrepos <https://myrepos.branchable.com/>`_.

If new data was added to several repositories simultaneously,
commit the changes on one of them and synchronize that with the another.
``rsync`` should link the working directory with commits properly.
This may fail depending on how you actually copied files (they may have
changed attributes).
In this case, create new commits in both repositories
and manually rename them to be the same.
Try to synchronize to see that all is linked properly.
For example, when we move photographs from an SD card, we want to have
at least two copies of them.
It would be more reliable to copy data from the original source to two repositories
than to push that from one of them to another (possible errors on the intermediate filesystem
increase the risk). Make sure that the two repositories were synchronized beforehand.

------------
Development
------------

Community contributions are very important for free software projects.

If you find this tool useful and want to fix an existing or unknown issue,
clone the repository and install Python packages for tests:

.. code-block:: console

    pip install -r requirements.txt

.. To propose a feature, please open a new issue first for a design discussion.

``yarsync`` was tested on ext4, NFSv4 and SimFS on Arch Linux and CentOS.
Tests on other systems would be useful.

----------
Hard links
----------

The file system must support hard links if you plan to use *commits*.
Multiple hard links are supported by POSIX-compliant and partially POSIX-compliant operating systems,
such as Linux, Android, macOS, and also Windows NT4 and later Windows NT operating systems
[`Wikipedia <https://en.wikipedia.org/wiki/Hard_link>`_].

Notable file systems to **support hard links** include [`hard links <https://en.wikipedia.org/wiki/Hard_link>`_ and `comparison of file systems <https://en.wikipedia.org/wiki/Comparison_of_file_systems#File_capabilities>`_ from Wikipedia]:

* EncFS (an Encrypted Filesystem using FUSE). Note that it doesn't support hard links `when External IV Chaining is enabled <https://github.com/vgough/encfs/blob/master/encfs/encfs.pod>`_ (this is enabled by default in paranoia mode, and disabled by default in standard mode).
* ext2-ext4. Standard on Linux. Ext4 has a limit of `65000 hard links <https://en.wikipedia.org/wiki/Hard_link#Limitations_of_hard_links>`_ on a file.
* HFS+. Standard on Mac OS.
* NTFS. The only Windows file system to support hard links. It has a limit of `1024 hard links <https://en.wikipedia.org/wiki/NTFS>`_ on a file.
* SquashFS, a compressed read-only file system for Linux.

Hard links are **not supported** on:

* FAT, exFAT. These are used on many flash drives.
* Joliet ("CDFS"), ISO 9660. File systems on CDs.

The majority of modern file systems support hard links.
A full list of `file system capabilities <https://en.wikipedia.org/wiki/Comparison_of_file_systems#File_capabilities>`_ can be found on Wikipedia.

One can copy data to file systems without hard links, but this will reduce the functionality of ``yarsync``,
and one should take care not to consume too much disk space if accidentally copying files instead of hard linking.

-----------------
rsync limitations
-----------------

* `Millions of files <https://www.resilio.com/blog/rsync-alternative>`_ will be synced very slowly.
* ``rsync`` freezes when encountering **too many hard links**. Users report problems for repositories of `200 G <https://serverfault.com/questions/363670/rsync-avzhp-follows-hardlinks-instead-of-copying-them-as-hardlinks#comment1252592_363780>`_ or `90 GB <https://bugzilla.samba.org/show_bug.cgi?id=10678>`_, with many hard links. For the author's repository with 30 thousand files (160 thousand with commits) and 3 Gb of data ``rsync`` works fine. If you have a large repository and want to copy it with all hard links, it is recommended to create a separate partition (e.g. LVM) and copy the filesystem as a whole. You can also remove some of older backups.
* ``rsync`` may create separate files instead of hard linking them. It can be fixed quickly using the `hardlink <https://jak-linux.org/projects/hardlink/>`_ executable.

------------
Alternatives
------------

`Free software that uses rsync <https://en.wikipedia.org/wiki/Rsync#rsync_applications>`_ includes:

* `Back In Time <https://backintime.readthedocs.io/>`_. See previous snapshots using a GUI.
* Grsync, graphical interface for rsync.
* `LuckyBackup <http://luckybackup.sourceforge.net/manual.html>`_. It is written in C++ and is mostly used from a graphical shell.
* `rsnapshot <https://rsnapshot.org/>`_, a filesystem snapshot utility. ``rsnapshot`` makes it easy to make periodic snapshots of local machines, and remote machines over ssh. Files can be restored by the users who own them, without the root user getting involved.

Other syncronization / backup / archiving software:

* `casync <https://github.com/systemd/casync>`_ is a combination of the rsync algorithm and content-addressable storage. It is an efficient way to deliver and update directory trees and large images over the Internet in an HTTP and CDN friendly way. Other systems that use `similar algorithms <https://github.com/systemd/casync#casync--content-addressable-data-synchronizer>`_ include `bup <https://bup.github.io/>`_.
* `Duplicity <http://www.nongnu.org/duplicity/>`_ backs directories by producing encrypted tar-format volumes and uploading them to a remote or local file server. ``duplicity`` uses ``librsync`` and is space efficient. It supports many cloud providers. In 2021 ``duplicity`` supports deleted files, full unix permissions, directories, and symbolic links, fifos, and device files, but not hard links. It can be run on Linux, MacOS and Windows (`under Cygwin <https://en.wikipedia.org/wiki/Duplicity_(software)>`_).
* `Git-annex <https://git-annex.branchable.com/>`_ manages distributed copies of files using git. This is a very powerful tool written in Haskell. It allows for each file to track the number of backups that contain it and their names, and it allows to plan downloading of a file to the local storage. This is its author's `use case <https://git-annex.branchable.com/testimonials/>`_: "I have a ton of drives. I have a lot of servers. I live in a cabin on dialup and often have 1 hour on broadband in a week to get everything I need". I tried to learn ``git-annex``, it was `uneasy <http://git-annex.branchable.com/tips/centralized_git_repository_tutorial/on_your_own_server/#comment-29cc31b898ba34a1f59a96ba7b001e08>`_ , and finally I found that it `doesn't preserve timestamps <https://git-annex.branchable.com/todo/does_not_preserve_timestamps/>`_ (because ``git`` doesn't) and `permissions <https://git-annex.branchable.com/bugs/assistant_doesn__39__t_sync_file_permissions/>`_. If that suits you, there is also a list of specialized `related software <https://git-annex.branchable.com/related_software/>`_. ``git-annex`` allows to use many cloud services as `special remotes <https://git-annex.branchable.com/special_remotes/>`_, including all `rclone remotes <https://git-annex.branchable.com/special_remotes/rclone/>`_.
* `Rclone <https://en.wikipedia.org/wiki/Rclone>`_ focuses on cloud and other high latency storage. It supports more than 50 different providers. As of 2021, it doesn't preserve permissions and attributes.

Continuous synchronization software:

* `gut-sync <https://github.com/tillberg/gut>`_ offers a real-time bi-directional folder synchronization.
* `Syncthing <https://syncthing.net/>`_. A very powerful and developed tool, works on Linux, MacOS, Windows and Android. Mostly uses a GUI (admin panel is managed through a Web interface), but also has a `command line interface <https://docs.syncthing.net/users/syncthing.html>`_.
* `Unison <https://www.cis.upenn.edu/~bcpierce/unison/>`_ is a file-synchronization tool for OSX, Unix, and Windows. It allows two replicas of a collection of files and directories to be stored on different hosts (or different disks on the same host), modified separately, and then brought up to date by propagating the changes in each replica to the other (pretty much like other syncronization tools work).
* Dropbox, Google Drive, Yandex Disk and many other closed-source tools fall into this cathegory. 

ArchWiki includes several useful `scripts for rsync <https://wiki.archlinux.org/index.php/Rsync>`_ and a list of its
`graphical front-ends <https://wiki.archlinux.org/index.php/Rsync#Front-ends>`_.
It also has a `list of cloud synchronization clients <https://wiki.archlinux.org/index.php/List_of_applications/Internet#Cloud_synchronization_clients>`_
and a `list of synchronization and backup programs <https://wiki.archlinux.org/index.php/Synchronization_and_backup_programs>`_. 
Wikipedia offers a `comparison of file synchronization software <https://en.wikipedia.org/wiki/Comparison_of_file_synchronization_software>`_ and a `comparison of backup software <https://en.wikipedia.org/wiki/Comparison_of_backup_software>`_.
Git-annex has a list of `git-related <https://git-annex.branchable.com/not/>`_ tools.
