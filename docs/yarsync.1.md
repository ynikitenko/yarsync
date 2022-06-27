% YARSYNC(1) yarsync 0.1
% Written by Yaroslav Nikitenko
% June 2022

# NAME
Yet Another Rsync is a file synchronization and backup tool

# SYNOPSIS
yarsync [-h] \[\--config-dir CONFIG\_DIR\] \[\--root-dir ROOT\_DIR\] \[-q | -v\] command \[args\]

[comment]: # (to see it converted to man, use pandoc yarsync.1.md -s -t man | /usr/bin/man -l -)

# DESCRIPTION
**yarsync** is a wrapper around rsync to store configuration
and synchronize repositories with the interface similar to git.
It is efficient (files in the repository can be removed and renamed freely without additional transfers)
and distributed (several replicas of the repository can diverge, and in that case a manual merge is supported).

# QUICK START

To create a new repository, enter the directory with its files and type

    yarsync init

This operation is safe and will not affect existing files
(including configuration files in an existing repository).
Alternatively, run **init** inside an empty directory and add files afterwards.
To complete the initialization, make a commit:

    yarsync commit -m "Initial commit"

**commit** creates a snapshot of the working directory,
which is all files in the repository except **yarsync** configuration and data.
This snapshot is very small, because it uses hard links.
To check how much your directory size has changed, run **du**(1).

Commit name is the number of seconds since the Epoch (integer Unix time).
This allows commits to be ordered in time, even for hosts in different zones.
Though this works on most Unix systems and Windows, the epoch is platform dependent.

After creating a commit, files can be renamed, deleted or added.
To see what was changed since the last commit, use **status**.
To see the history of existing commits, use **log**.

Hard links are excellent at tracking file moves or renames
and storing accidentally removed files.
Their downside is that if a file gets corrupt,
this will apply to all of its copies in local commits.
The 3-2-1 backup rule implies that one should have at least 3 copies of data,
so let us add a remote repository \"my\_remote\":

    yarsync remote add my_remote remote:/path/on/my/remote

For local copies we still call the repositories \"remote\",
but their paths will be local:

    yarsync remote add my_drive /mnt/my_drive/my_repo

This command only updated our configuration,
but did not make any changes at the remote path (which may not exist).
To make a local copy of our repository, run

    yarsync clone . /mnt/my_drive/my_repo

**clone** copies all repository data (except the configuration) to the new replica
and adds the original repository to its remotes with the name \"origin\".
To copy the repository to a remote host, just copy its files (preserving hard links):

    rsync -avHP ./ remote:/path/on/my/remote

Here \'**-H**\' stands for hard links. If the first path ends with
a slash, data will be copied to \"remote/\", otherwise to its subdirectory.
Similarly, one can copy a repository *from* a remote: just change the order of paths
and don't forget about the slash.
To check that we set up the repositories correctly, make a dry run with \'**-n**\':

    yarsync push -n my_remote

If there are no errors and no file transfers, then we have a functioning remote.
We can continue working locally, adding and removing files and making commits.
When we want to synchronize repositories, we **push** the changes *to*
or **pull** them *from* a remote (first with a **\--dry-run**).
This is the recommended workflow, and if we work on different repositories
in sequence and always synchronize changes, our life will be easy.
Sometimes, however, we may forget to synchronize two replicas
and they will end up in a diverged state;
we may actually change some files or find them corrupt.
Solutions to these problems involve user decisions
and are described in **pull** and **push** options.

# OPTION SUMMARY

|                    |                                                       |
|--------------------|-------------------------------------------------------|
| \--help, -h        |    show help message and exit
| \--config-dir=DIR  |    path to the configuration directory
| \--root-dir=DIR    |    path to the root of the working directory
| \--quiet, -q       |    decrease verbosity
| \--verbose, -v     |    increase verbosity

# COMMAND SUMMARY

|              |                                                             |
|--------------|-------------------------------------------------------------|
|              |
| **checkout** |    restore the working directory to a commit
| **clone**    |    clone a repository into a new directory
| **commit**   |    commit the working directory
| **diff**     |    print the difference between two commits
| **init**     |    initialize a repository
| **log**      |    print commit logs
| **pull**     |    get data from a source
| **push**     |    send data to a destination
| **remote**   |    manage remote repositories
| **show**     |    print log messages and actual changes for commit(s)
| **status**   |    print updates since last commit

# OPTIONS

**\--help**, **-h**
: Prints help message and exits.
Default if no arguments are given.
After a command name, prints help for that command.

**\--config-dir=DIR**
: Provides the path to the configuration directory if it is detached.
Both **\--config-dir** and **\--root-dir** support tilde expansion for
user's home directory. See SPECIAL REPOSITORIES for usage details.

**\--root-dir=DIR**
: Provides the path to the root of the working directory for a detached repository.
Requires **\--config-dir**.
If not set explicitly, the default working directory is the current one.

**\--quiet**, **-q**
: Decreases verbosity. Does not affect error messages (redirect them if needed).

**\--verbose**, **-v**
: Increases verbosity. May print more rsync commands and output.
Conflicts with **\--quiet**.

# SPECIAL REPOSITORIES

A **detached** repository is one with the **yarsync** configuration directory
outside the working directory.
To use such repository, one must provide **yarsync** options
**\--config-dir** and **\--root-dir** with every command
(**alias**(1p) may be of help).
To create a detached repository, use **init** with these options
or move the existing configuration directory manually.
For example, if one wants to have several versions of static Web pages,
they may create a detached repository and publish the working directory
without the Web server having access to the configuration.
Commits can be created or checked out,
but **pull** or **push** are not supported for such repositories
(one will have to synchronize them manually).
A detached repository is similar to a bare repository in git,
but always has a working directory.

A repository with a **filter** can exclude (disable tracking) some files or directories
from the working directory.
This may be convenient, but makes synchronization less reliable,
and such repository can not be used as a remote.
See **rsync-filter** in the FILES section for more details.

# FILES

All **yarsync** repository configuration and data is stored
in the hidden directory **.ys** under the root of the working directory.
If the user no longer wants to use **yarsync** and the working directory
is in the desired state, they can safely remove the **.ys** directory.

Note that only commits and logs (apart from the working directory)
are synchronized between the repositories.
Each repository has its own configuration and name.

## User configuration files

**.ys/config.ini**
: Contains names and paths of remote repositories.
This file can be edited directly or with **remote** commands
according to user's preference.

    **yarsync** supports synchronization
with only existing remotes.
A simple configuration for a remote \"my\_remote\" could be:

        [my_remote]
        path = remote:/path/on/my/remote

    Several sections can be added for more remotes.
An example (non-effective) configuration is created during **init**.
Note that comments in **config.ini** can be erased
during **remote {add,rm}**.

    Since removable media or remote hosts can change their paths
or IP addresses, one may use variable substitution in paths:

        [my_drive]
        path = $MY_DRIVE/my_repo

    For the substitutions to take the effect,
export these variables before run:

        $ export MY_DRIVE=/run/media/my_drive
        $ yarsync push -n my_drive

    If we made a mistake in the variable or path,
it will be shown in the printed command.
Always use **\--dry-run** first to ensure proper synchronization.

    Another **yarsync** remote configuration option is **host**.
If both **path** and **host** are present, the effective path
will be their concatenation \"\<host\>:\<path\>\".
Empty **host** means local host and does not prepend the path.

    It is possible to set default **host** for each section
from the section name.
For that, add a default section with an option **host_from_section_name**:

        [DEFAULT]
        host_from_section_name

    Empty lines and lines starting with \'**#**\' are ignored.
White spaces in a section name will be considered parts of its name.
Spaces around \'**=**\' are allowed.
Full syntax specification can be found at
<https://docs.python.org/3/library/configparser.html>.

**.ys/repository.txt**
: Contains the repository name, which is used in logs
and usually coincides with the remote name
(how local repository is called on remotes).
The name can be set during **init** or edited later.

    It is recommended (but not required) to have different names
for the repository replicas on different hosts or devices.
For example, if one has repositories \"programming/\" and \"music/\"
on a laptop \"my\_host\", their names would probably be \"my\_host\",
and the names of their copies on an external drive could be \"my\_drive\"
(this is different from git, which uses only author's name in logs).
If one never creates commits directly on \"my\_drive\",
these names can be empty.

    If the repository name is missing (empty or no file), host name will be used.
If there is an error getting the host name during **commit**,
provide the name in the **repository.txt**.

**.ys/rsync-filter**
: Contains rsync filter rules, which effectively define what data belongs
to the repository.
The **rsync-filter** does not exist by default, but can be added for flexibility.

    For example, the author has a repository \"~/work\",
but wants to keep his presentations in \"tex/\" in a separate repository.
Instead of having a different directory \"~/work\_tex\", he adds such rules
to **rsync-filter**:

        \# all are in git repositories
        \- /repos
        \# take care to sync separately
        \- /tex

    In this way, \"~/work/tex\" and contained git repositories will be excluded
from \"~/work\" synchronization. Lines starting with \'**#**\' are ignored,
as well as empty lines. To complicate things, one can include a subdirectory
of \"tex\" into \"work\" with an include filter \'**+**\'.
For complete details, see FILTER RULES section of **rsync**(1).

    While convenient for everyday use, filters make backup more difficult.
To synchronize repository with them, one has to remember that it has subdirectories
that need to be synchronized too. If the remote repository had
its own filters, that would make synchronization even more unreliable.
Therefore filters are generally discouraged: **pull** and **push** ignore
remote filters (make sure you synchronize only *from* a repository with filters),
while **clone** refuses to copy a repository with **rsync-filter**.

## yarsync technical directories
**.ys/commits/**
: Contains local commits (snapshots of the working directory).
If some of the old commits are no longer needed (there are too many of them
or they contain a large file), they can be removed.
Make sure, however, that all remote repositories contain at least some of
the present commits, otherwise future synchronization will get complicated.
Alternatively, remove unneeded files or folders manually:
commits can be edited, with care taken to synchronize them correctly.

**.ys/logs/**
: Contains text logs produced during **commit**.
They are not necessary, so removing any of them will not break the repository.
If one wants to fix or improve a commit message though,
they may edit the corresponding log
(the change will be propagated during **push** with the **\--overwrite** option).
It is recommended to store logs even for old deleted commits,
which may be present on formerly used devices.

# EXIT STATUS

**0**
: Success

**1**
: Invalid option

**7**
: Configuration error

**8**
: Command error

**9**
: System error

If the command could be run successfully, a zero code is returned.
Invalid option code is returned for mistakes in command line argument syntax.
Configuration error can occur when we are outside an existing repository
or a **yarsync** configuration file is missing.
If the repository is correct, but the command is not allowed in its current state
(for example, one can not push or pull when there are uncommitted changes
or add a remote with an already present name), the command error is returned.
It is also possible that a general system error, such as a keyboard interrupt,
is raised in the Python interpreter.

In case of rsync errors, its error code is returned.

# SEE ALSO
**rsync**(1)

The yarsync page is <https://github.com/ynikitenko/yarsync>.

# BUGS
This is the first release.
Some corner cases during **clone** are not handled
and raise Python errors instead of correct return codes.
The output messages deserve to be improved.
Please be patient and please report bugs to
<https://github.com/ynikitenko/yarsync/issues>.

# COPYRIGHT
Copyright © 2021-2022 Yaroslav Nikitenko.
License GPLv3: GNU GPL version 3 <https://gnu.org/licenses/gpl.html>.\
This is free software: you are free to change and redistribute it. There is NO
WARRANTY, to the extent permitted by law.
