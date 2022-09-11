# Yet Another Rsync is a file synchronization tool

import argparse
import collections
import configparser
import datetime
import functools
# for user name
import getpass
import io
import json
import os
import re
# for host name
import socket
import subprocess
import sys
import time


########################
### MODULE CONSTANTS ###
########################

## Return codes ##
# argparse error (raised during YARsync.__init__)
SYNTAX_ERROR = 1
# ys configuration error: not in a repository,
# a config file missing, etc.
CONFIG_ERROR = 7
# ys command error: the repository is correct,
# but in a state forbidding the action
# (for example, one can't push when there are uncommitted changes
#  or add a remote with an already present name)
COMMAND_ERROR = 8
# Python interpreter could get KeyboardInterrupt
# or other exceptions leading to sys.exit()
SYS_EXIT_ERROR = 9


## Custom exception classes ##
class YSError(Exception):
    """Base for all yarsync exceptions."""

    pass


class YSConfigurationError(YSError):

    def __init__(self, arg="", msg=""):
        self.arg = arg
        self.msg = msg


class YSCommandError(YSError):
    """Can be raised if a yarsync command was not successful."""

    def __init__(self, code=0):
        # code might be unimportant, therefore we allow 0
        self.code = code


## command line arguments errors
class YSArgumentError(YSError):
    # don't know how to initialize an argparse.ArgumentError,
    # so create a custom exception

    def __init__(self, arg="", msg=""):
        self.arg = arg
        self.msg = msg


class YSUnrecognizedArgumentsError(YSError, SystemExit):

    def __init__(self, code):
        # actually the code is never used later
        SystemExit.__init__(self, code)
        # super(YSUnrecognizedArgumentsError, self).__init__(code)


## Example configuration ##
CONFIG_EXAMPLE = """\
# uncomment and edit sections or use
# $ yarsync remote add <remote> <path>
# to add a remote.
#
# [remote]
# # comments are allowed
# path = remote:/path/on/remote/to/my_repo
# # spaces around '=' are allowed
# # spaces in section names are not allowed
# # (will be treated as part of the name)
#
# # several sections are allowed
# [my_drive]
# path = $MY_DRIVE/my_repo
# # inline comments are not allowed
# # don't write this!
# # host =   # empty host means localhost
# # this is correct:
# # empty host means localhost
# host = 
#
# Variables in paths are allowed.
# For them to take the effect, run
# $ export MY_DRIVE=/run/media/my_drive
# $ yarsync push -n my_drive
# Always try --dry-run first to ensure
# that all paths still exist and are correct!
"""

######################
## Helper functions ##
######################


def _get_root_directory(config_dir_name):
    """Search for a directory containing *config_dir_name*
    higher in the file system hierarchy.
    """
    cur_path = os.getcwd()
    # path without symlinks
    root_path = os.path.realpath(cur_path)
    # git stops at the file system boundary,
    # but we ignore that for now.
    while True:
        test_path = os.path.join(root_path, config_dir_name)
        if os.path.exists(test_path):
            # without trailing slash
            return root_path
        if os.path.dirname(root_path) == root_path:
            # won't work on Windows shares with '\\server\share',
            # but ignore for now.
            # https://stackoverflow.com/a/10803459/952234
            break
        root_path = os.path.dirname(root_path)
    raise OSError(
        "configuration directory {} not found".format(config_dir_name)
    )


def _is_commit(file_name):
    """A *file_name* is a commit if it can be converted to int."""
    try:
        int(file_name)
    except (TypeError, ValueError):
        return False
    return True


def _print_error(msg):
    # todo: allow arbitrary number of arguments.
    # not a class method, because it can be run
    # when YARsync was not fully initialized yet.
    print("!", msg, file=sys.stderr)


# copied with some modifications from
# https://github.com/DiffSK/configobj/issues/144#issuecomment-347019778
# Another proposed option is
# config = ConfigParser(os.environ),
# which is awful and unsafe,
# because it adds all the environment to the configuration
def _substitute_env(content):
    """Read filename, substitute environment variables and return a file-like
    object of the result.

    Substitution maps text like "$FOO" for the environment variable "FOO".
    """

    def lookup(match):
        """Replace a match like $FOO with the env var FOO.
        """
        key = match.group(2)
        if key not in os.environ:
            # variables should be set for values that are used,
            # but not necessarily for all values.
            # raise OSError("variable {} unset".format(key))
            # unset variables return unchanged (with $)
            return match.group(1)
            # raise Exception("Config env var '{key}' not set".format(key))
        return os.environ.get(key)

    # todo: allow more sophisticated variables, like ${VAR}
    # (and that's all), should be an OR of this and 
    # r'(\${(\w+)})'), untested.
    # Not sure it's needed: why such complications to a config file?..
    pattern = re.compile(r'(\$(\w+))')
    replaced = pattern.sub(lookup, content)

    try:
        result = io.StringIO(replaced)
    except TypeError:  # Python2
        result = io.StringIO(unicode(replaced, "utf-8"))
    return result


def _mkhostpath(host, path):
    if host:
        return host + ":" + path
    # localhost
    return path


class YARsync():
    """Synchronize data. Provide configuration and wrap rsync calls."""

    def __init__(self, argv):
        """*argv* is the list of command line arguments."""

        parser = argparse.ArgumentParser(
            description="yarsync is a file synchronization and backup tool",
            # exit_on_error appeared only in Python 3.9
            # and doesn't seem to work. Skip and be more cross-platform.
            # exit_on_error=False
        )
        # failed to implement that with ArgumentError
        # parser = _ErrorCatchingArgumentParser(...)
        subparsers = parser.add_subparsers(
            title="Available commands",
            dest="command_name",
            # description="valid commands",
            help="type 'yarsync <command> --help' for additional help",
            # or it will print a list of commands in curly braces.
            metavar="command",
        )

        ###################################
        ## Initialize optional arguments ##
        ###################################
        # .ys directory
        parser.add_argument("--config-dir", default="",
                            help="path to the configuration directory")
        parser.add_argument("--root-dir", default="",
                            help="path to the root of the working directory")

        # this option is applied not to all commands.
        # Moreover, we can't write "yarsync -n 2 log" =>
        # don't create an illusion
        # that we can put an option at any place.
        # However, the upside of leaving it here might be
        # its better visibility during the general help
        # (not for a subcommand).
        # parser.add_argument(
        #     "-n", "--dry-run", action="store_true",
        #     default=False,
        #     help="print what would be transferred during a real run, "
        #          "but do not make any changes"
        # )

        verbose_group = parser.add_mutually_exclusive_group()
        verbose_group.add_argument("-q", "--quiet",
                                   action="count",
                                   # otherwise default will be None
                                   default=0,
                                   help="decrease verbosity")
        verbose_group.add_argument("-v", "--verbose",
                                   action="count",
                                   default=0,
                                   help="increase verbosity")

        ############################
        ## Initialize subcommands ##
        ############################
        # or sub-commands

        # checkout #
        parser_checkout = subparsers.add_parser(
            "checkout",
            # help="check out a commit"
            help="restore the working directory to a commit"
        )
        parser_checkout.add_argument(
            "-n", "--dry-run", action="store_true",
            default=False,
            help="print what will be transferred during a real checkout, "
                 "but don't make any changes"
        )
        # we write metavars <var> as in git,
        # to distinguish them from rsync VAR.
        parser_checkout.add_argument(
            "commit", metavar="<commit>", help="commit name"
        )
        parser_checkout.set_defaults(func=self._checkout)

        # clone #
        parser_clone = subparsers.add_parser(
            "clone",
            help="clone a repository into a new directory"
        )
        parser_clone.add_argument(
            "-o", "--origin", default="origin", metavar="<origin>",
            help="name of the remote repository (by default 'origin')",
        )
        parser_clone.add_argument(
            "-n", "--name", metavar="<clone>",
            help="name of the new repository",
        )
        parser_clone.add_argument(
            "repository", metavar="<repository>", help="source repository path"
        )
        parser_clone.add_argument(
            "directory", metavar="<directory>", nargs="?", default="",
            help="directory with the new cloned repository"
        )

        # commit #
        parser_commit = subparsers.add_parser(
            "commit", help="commit the working directory"
        )
        parser_commit.add_argument(
            "-m", "--message", metavar="<message>", default="",
            help="a string with the commit message"
        )
        parser_commit.set_defaults(func=self._commit)

        # diff #
        parser_status = subparsers.add_parser(
            "diff", help="print the difference between two commits"
        )
        parser_status.add_argument(
            "commit", metavar="<commit>", help="commit name"
        )
        parser_status.add_argument(
            "other_commit", metavar="<commit>", nargs="?", default=None,
            help="other commit name"
        )
        parser_status.set_defaults(func=self._diff)

        # init #
        parser_init = subparsers.add_parser("init",
                                            help="initialize a repository")
        parser_init.add_argument(
            "--merge", action="store_true", help="merge existing repositories"
        )
        # reponame is used during commits
        parser_init.add_argument(
            "reponame", nargs="?", metavar="<reponame>",
            help="name of the repository (for commits and logs)"
        )

        # log #
        parser_log = subparsers.add_parser(
            "log", help="print commit logs"
        )
        parser_log.add_argument(
            "-n", "--max-count", metavar="<number>",
            type=int, default=-1,
            help="maximum number of logs shown"
        )
        parser_log.add_argument("-r", "--reverse", action="store_true",
                                help="reverse the order of the output")
        parser_log.set_defaults(func=self._log)
        # todo: log <commit_number>

        # pull #
        parser_pull = subparsers.add_parser(
            "pull", help="fetch data from source"
        )

        # mutually exclusive arguments
        pull_group = parser_pull.add_mutually_exclusive_group()
        force_help = "remove commits and logs missing on source"
        pull_group.add_argument(
            "-f", "--force", action="store_true",
            help=force_help
        )
        pull_group.add_argument(
            "--new", action="store_true",
            help="do not remove local data that is missing on source"
        )
        pull_group.add_argument(
            "-b", "--backup", action="store_true",
            help="changed local files are renamed (not overwritten or ignored)"
        )
        pull_group.add_argument(
            "--backup-dir", default="", metavar="DIR",
            help="changed local files are put into DIR preserving their paths"
        )

        parser_pull.add_argument("source", metavar="<source>",
                                 help="source name")

        # push #
        parser_push = subparsers.add_parser(
            "push", help="send data to a destination"
        )
        parser_push.add_argument(
            "-f", "--force", action="store_true",
            help=force_help
        )
        # we don't allow pushing new files to remote,
        # because that could cause its inconsistent state
        # (while locally we merge new files manually)
        parser_push.add_argument(
            "destination", metavar="<destination>",
            help="destination name"
        )

        # common pull and push options
        for pparser in (parser_pull, parser_push):
            pparser.add_argument(
                "-n", "--dry-run", action="store_true",
                default=False,
                help="print what would be transferred during a real run, "
                     "but do not make any change"
            )
            pparser.add_argument(
                # not sure whether -o would be a good shortening
                # (-o might go for options)
                "--overwrite", action="store_true",
                default=False,
                help="propagate file changes"
            )

        # remote #
        parser_remote = subparsers.add_parser(
            "remote", help="manage remote repositories"
        )
        # this is a different option from "yarsync -v" here.
        parser_remote.add_argument(
            "-v", "--verbose",
            action="store_true",
            # action="count",
            help="print repository paths"
        )
        subparsers_remote = parser_remote.add_subparsers(
            title="remote commands",
            dest="remote_command",
            help="type 'yarsync remote <command> --help' for additional help",
            metavar="<command>",
        )

        # parse_intermixed_args is missing in Python 2,
        # that's why we allow -v flag only after 'remote'.
        #
        # remote_parent_parser = argparse.ArgumentParser(add_help=False)
        # remote_parent_parser.add_argument(
        #     "-v", "--verbose", action="count",
        #     help="show remote paths. Insert after a remote command"
        # )
        ## remote add
        parser_remote_add = subparsers_remote.add_parser(
            "add", help="add a remote"
        )
        parser_remote_add.add_argument(
            "repository", metavar="<repository>",
            help="repository name",
        )
        parser_remote_add.add_argument(
            "path", metavar="<path>", help="repository path",
        )
        # not used yet.
        # parser_remote_add.add_argument(
        #     "options", nargs='*', help="repository options",
        # )
        ## remote rm
        parser_remote_rm = subparsers_remote.add_parser(
            "rm", help="remove a remote"
        )
        parser_remote_rm.add_argument(
            "repository", metavar="<repository>",
            help="repository name",
        )

        for remote_subparser in [parser_remote_add, parser_remote_rm]:
            remote_subparser.set_defaults(func=self._remote)

        ## remote show, default
        parser_remote_show = subparsers_remote.add_parser(
            "show", help="print remotes"
        )
        parser_remote_show.set_defaults(func=self._remote_show)

        # show #
        parser_show = subparsers.add_parser(
            "show", help="print log messages and actual changes for commit(s)"
        )
        parser_show.add_argument(
            "commit", nargs="+", metavar="<commit>", help="commit name"
        )
        parser_show.set_defaults(func=self._show)

        # status #
        parser_status = subparsers.add_parser(
            "status", help="print updates since last commit"
        )
        parser_status.set_defaults(func=self._status)

        if len(argv) > 1:  # 0th argument is always present
            try:
                args = parser.parse_args(argv[1:])
            except SystemExit as err:
                # argparse can raise SystemExit
                # in case of unrecognized arguments
                # (apart from ArgumentError and ArgumentTypeError;
                #  hope this is the complete list)
                if err.code == 0:
                    raise err
                raise YSUnrecognizedArgumentsError(err.code)
        else:
            # default is print help.
            # Will raise SystemExit(0).
            args = parser.parse_args(["--help"])

        ########################
        ## Init configuration ##
        ########################

        # basename, because ipython may print full path
        self.NAME = os.path.basename(argv[0])  # "yarsync"
        # directory with commits and other metadata
        # (may be updated by command line arguments)
        CONFIGDIRNAME = ".ys"
        # default name for most repositories.
        # Mostly used directly and hardly will be ever changed.
        self.YSDIR = ".ys"

        root_dir = os.path.expanduser(args.root_dir)
        config_dir = os.path.expanduser(args.config_dir)
        if not root_dir and not config_dir:
            if args.command_name == "init":
                root_dir = "."
                config_dir = CONFIGDIRNAME
            elif args.command_name != "clone":
                # search the current directory and its parents
                try:
                    root_dir = _get_root_directory(CONFIGDIRNAME)
                except OSError as err:
                    # config dir not found.
                    _print_error(
                        "fatal: no {} configuration directory {} found".
                        format(self.NAME, CONFIGDIRNAME) +
                        "\n  Check that you are inside an existing repository"
                        "\n  or initialize a new repository with '{} init'.".
                        format(self.NAME)
                    )
                    raise err
                config_dir = os.path.join(root_dir, CONFIGDIRNAME)
        elif config_dir:
            if not root_dir:
                # If we are right in the root dir,
                # this argument should not be required.
                # But it is error prone if we move to a subdirectory
                # and call checkout (because root-dir will be wrong).
                # If the user wants safety,
                # they can provide the root-dir themselves
                # together with config-dir
                # (we say about an alias for 'yarsync --config-dir=...')
                root_dir = "."
        else:
            err_msg = "yarsync: error: --root-dir requires --config-dir "\
                      "to be provided"
            # we don't _print_error here,
            # because we want to mimic an argparse error.
            print(err_msg)
            # could not initialize ArgumentError here,
            # so created a new one
            raise YSArgumentError("root-dir", err_msg)
        self.root_dir = root_dir
        self.config_dir = config_dir

        # directory creation mode could be set from:
        # - command line argument
        # - global configuration
        # - mode of the sync-ed directory (may be best)
        # - hardcoded
        # - just skipped (and will be set correctly by the OS).
        # self.DIRMODE = 0o755

        self.COMMITDIR = os.path.join(self.config_dir, "commits")
        self.CONFIGFILE = os.path.join(self.config_dir, "config.ini")
        self.DATEFMT = "%a, %d %b %Y %H:%M:%S %Z"
        self.HEADFILE = os.path.join(self.config_dir, "HEAD.txt")
        self.LOGDIR = os.path.join(self.config_dir, "logs")
        self.MERGEFILE = os.path.join(self.config_dir, "MERGE.txt")
        # contains repository name
        self.REPOFILE = os.path.join(self.config_dir, "repository.txt")
        self.RSYNCFILTER = os.path.join(self.config_dir, "rsync-filter")
        # yarsync repositories are owned by one user.
        # However, different machines can have different user
        # and group ids, so we don't push extraneous ids there.
        # Used in pull and push (and indirectly in clone).
        self.RSYNCOPTIONS = ["-avH", "--no-owner", "--no-group"]
        # stores last synchronized commit
        self.SYNCFILE = os.path.join(self.config_dir, "sync.txt")

        ## Check for CONFIGFILE
        # "checkout", "diff", "init", "log", "show", "status"
        # work fine without config.
        if args.command_name in ["pull", "push", "remote"]:
            try:
                with open(self.CONFIGFILE, "r") as conf_file:
                    config_text = conf_file.read()
            except OSError as err:
                if (args.command_name == "remote"
                    and args.remote_command == "add"
                    and not os.path.exists(self.CONFIGFILE)):
                    config_text = ""
                else:
                    # we are in an existing repository,
                    # because .ys exists.
                    _print_error(
                        "fatal: could not read {} configuration at {}.".
                        format(self.NAME, self.CONFIGFILE) +
                        "\n  Check your permissions or restore missing files "
                        "with '{} init'".
                        format(self.NAME)
                    )
                    raise err
            try:
                config, configdict = self._read_config(config_text)
            except configparser.Error as err:
                err_descr = type(err).__name__ + ":\n    " + str(err)
                _print_error(
                    "{} configuration error in {}:\n  ".
                    format(self.NAME, self.CONFIGFILE) +
                    err_descr
                )
                raise YSConfigurationError(err, err_descr)
            self._configdict = configdict
            # Don't economize on memory here, but enhance our object
            # (better to store than to re-read).
            # if args.command_name == "remote":
            #     # config is not needed for any other command
            self._config = config

        ####################################
        ## Initialize optional parameters ##
        ####################################

        #########################
        ## Initialize commands ##
        #########################

        # there is no easy way to set a default command
        # for a subparser, https://stackoverflow.com/a/46964652/952234
        if args.command_name == "clone":
            self._func = functools.partial(
                self._clone,
                repository=args.repository, directory=args.directory,
                origin=args.origin, name=args.name
            )
        elif args.command_name == "init":
            # https://stackoverflow.com/a/41070441/952234
            self._func = functools.partial(self._init, args.reponame, args.merge)
            # this also works, but lambdas can't be pickled
            # (even though we don't need that)
            # self._func = lambda: self._init(self._args.reponame)

        elif args.command_name in ["pull", "push"]:

            if args.command_name == "pull":
                new = args.new
                backup_dir = args.backup_dir
                backup = args.backup or backup_dir
                remote = args.source
            else:
                new = False
                backup = False
                backup_dir = ""
                remote = args.destination

            self._func = functools.partial(
                # common options
                self._pull_push, args.command_name, remote,
                force=args.force, overwrite=args.overwrite,
                # pull options
                new=new, backup=backup, backup_dir=backup_dir
            )

        elif args.command_name == "remote" and args.remote_command is None:
            self._func = self._remote_show
        else:
            self._func = args.func

        if args.command_name == "pull":
            args._remote = args.source
        elif args.command_name == "push":
            args._remote = args.destination

        self.print_level = 2 - args.quiet + args.verbose

        self._args = args

    def _clone(self, repository, directory="", origin="origin", name=None):
        """Clone a yarsync *repository* to a *directory*.

        The new repository will have the name *name* in self.REPOFILE.
        The original repository will be added as a remote
        with the name *origin* to the new one.

        Note that only data (working directory, commits and logs,
        and not any of yarsync configuration files!) will be cloned.

        If the *directory* path ends with a slash,
        a new repository will be created as its subdirectory
        with the name taken from the last path element of the
        source *repository*.
        Otherwise, the new repository will be the *directory* itself.

        If the path *directory* (or any its parent directories)
        do not exist, they will be created. If the resulting
        directory exists and is non-empty, it will be preserved
        and an error issued.
        """

        ## check that repository has no rsync-filter
        try:
            remote_configs = self._get_remote_files(
                os.path.join(repository, self.YSDIR) + '/'
            )
        except OSError:
            raise OSError(
                "could not read configuration at the repository {}".
                format(repository)
            )

        if "rsync-filter" in remote_configs:
            _print_error(
                "repository configuration must not contain rsync-filter."
                " Abort.\n  Repositories with filters can be synchronized "
                "only as local ones (with pull or push)."
            )
            raise YSCommandError()

        if repository.endswith('/'):
            # ignore trailing slash
            repository = repository[:-1]

        ## get directory name from the repository path
        if directory == "" or directory.endswith('/'):
            # os.path.split(path) returns a (head, tail) pair.
            # It is important that the path does not end in '/',
            # or tail will be empty!
            repo_name = os.path.split(repository)[1]
            directory = os.path.join(directory, repo_name)

        if ':' not in repository or os.path.exists(repository):
            ## If the path is local, make it absolute.
            # Otherwise it will not work when we enter the *directory*.
            # rsync accepts paths like [USER@]HOST:SRC
            # todo: this will fail on Windows with C:\...
            # '~' in the path will be handled by shell.
            repository = os.path.abspath(repository)

        try:
            os.makedirs(directory, exist_ok=True)
        except OSError as err:
            _print_error("could not create a directory {}. Abort."
                         .format(directory))
            raise YSCommandError()

        if any(os.scandir(directory)):
            _print_error("directory {} non-empty. Abort.".format(directory))
            raise YSCommandError()
            # it is recommended to close the scandir iterator
            # https://docs.python.org/3/library/os.html#os.scandir,
            # but if we return right here, it is not needed
            # (I don't receive a warning here).

        try:
            # no need to remember the path
            # (it won't be changed for the user).
            # old_path = os.getcwd()
            os.chdir(directory)
            # todo: what about verbosity?
            # Probably make _print a separate function for that?
            command = ["yarsync", "init"]
            if name is not None:
                command.append(name)
            ys = YARsync(command)
            ys.print_level = self.print_level - 2
            returncode = ys()

            if self.print_level <= 2:
                # otherwise it will be printed by subcommands
                init_str = "Initialized a new repository"
                if name is not None:
                    init_str += " " + name
                self._print(init_str, "in {}".format(directory))

            if returncode:
                raise YSCommandError(returncode)
                # We don't exit here but raise,
                # in order to clean up the created new repository.

            ys._remote_add(origin, repository)
            if self.print_level <= 2:
                self._print("Added a remote '{}' with path {}".
                            format(origin, repository))
            # raise YSCommandError(1)
        except YSCommandError as err:
            # we import shutil lazily here,
            # because it is not used in other places
            # and because this use case is marginal (not likely).
            import shutil
            # don't remove the base 'directory',
            # because it could be created before us.
            # It is safer to remove only .ys .
            # Since ys is initialized without any config-dir options,
            # this should be safe.
            ysdir = ys.config_dir
            # this is wrong for ysdir, since we already entered the directory
            ysdir_full_path = os.path.join(directory, ys.config_dir)
            # Cleaning up the directory allows to repeat the clone command
            # without errors.
            self._print("Cleaning up. Removing '{}'...".
                        format(ysdir_full_path))
            # one could only remove the .ys dir and the few config files
            # explicitly.
            shutil.rmtree(ysdir)
            self._print("Done.")
            # print("Removed {}.".format(ysdir))
            raise err

        # todo: can we make pull or push accepting arguments?
        # Or should we fix self._args to reuse the existing object?
        ys_pull = YARsync(["yarsync", "pull", origin])
        ys_pull.print_level = self.print_level - 2
        returncode = ys_pull()
        self._print("\n{} cloned.".format(origin))
        return returncode

    def _checkout(self, commit=None):
        """Checkout a commit.

        Warning: all changes in the working directory will be overwritten!
        """
        # todo: do we allow a default (most recent) commit?
        # also think about ^, ^^, etc.
        # However, see no real usage for them.
        if commit is None:
            commit = int(self._args.commit)
        # todo: improve verbosity handling
        verbose = True

        if commit not in self._get_local_commits():
            raise ValueError("commit {} not found".format(commit))

        # copied from _status()
        commit_dir = os.path.join(self.COMMITDIR, str(commit))

        command_begin = ["rsync", "-au"]
        if self._args.dry_run:
            command_begin += ["-n"]
        command_begin.extend(["--delete", "-i", "--exclude=/.ys"])
        command_str = " ".join(command_begin)

        filter_command, filter_str = self._get_filter(include_commits=False)
        command = command_begin + filter_command
        if filter_str:
            command_str += " " + filter_str

        # outbuf option added in Rsync 3.1.0 (28 Sep 2013)
        # https://download.samba.org/pub/rsync/NEWS#ENHANCEMENTS-3.1.0
        # from https://stackoverflow.com/a/35775429
        command.append('--outbuf=L')
        command_str += " --outbuf=L"

        command_end = [commit_dir + '/', self.root_dir]
        command += command_end
        command_str += " " + " ".join(command_end)

        if verbose:
            self._print_command(command_str)
            sp = subprocess.run(command)
        else:
            sp = subprocess.run(command, stdout=subprocess.PIPE)

        # we don't check for error code here,
        # because if checkout was wrong, we can't be sure
        # in the resulting state.
        if commit == self._get_last_commit():
            # remove HEADFILE
            self._update_head()
        else:
            # write HEADFILE
            with open(self.HEADFILE, "w") as head_file:
                print(commit, file=head_file)

        return sp.returncode

    def _commit(self):
        """Commit the working directory and create a log."""
        # commit directory name is based on UNIX time
        # date = datetime.date.today()
        # date_str = "{}{:#02}{:#02}"\
        #            .format(date.year, date.month, date.day)
        # print(date_str)

        short_commit_mess = self._args.message

        try:
            with open(self.REPOFILE) as repofile:
                reponame = repofile.read()
        except OSError:
            # platform.node() just calls socket.gethostname()
            # with an error check
            reponame = socket.gethostname()

        username = getpass.getuser()
        time_str = time.strftime(self.DATEFMT, time.localtime())

        log_str = "When: {date}\nWhere: {user}@{repo}".format(
            date=time_str, user=username, repo=reponame
        )
        if short_commit_mess:
            short_commit_mess += "\n\n"

        if os.path.exists(self.MERGEFILE):
            # copied from _status
            with open(self.MERGEFILE, "r") as fil:
                merge_str = fil.readlines()[0].strip()
            merges = merge_str.split(',')
            short_commit_mess += "Merge {} and {} (common commit {})\n"\
                                 .format(*merges)

        short_commit_mess += log_str

        if not os.path.exists(self.COMMITDIR):
            os.mkdir(self.COMMITDIR)

        commit_name = str(int(time.time()))
        commit_dir = os.path.join(self.COMMITDIR, commit_name)
        commit_dir_tmp = commit_dir + "_tmp"

        # Raise if this commit exists
        # We don't want rsync to write twice to one commit
        # even though it's hard to imagine how this could be possible
        # (probably broken clock?)
        if os.path.exists(commit_dir):
            raise RuntimeError("commit {} exists".format(commit_dir))
        elif os.path.exists(commit_dir_tmp):
            raise RuntimeError(
                "temporary commit {} exists".format(commit_dir_tmp)
            )

        # exclude .ys, otherwise an empty .ys/ will appear in the commit
        command = ["rsync", "-a", "--link-dest=../../..", "--exclude=/.ys"]
        full_command_str = " ".join(command)

        filter_list, filter_str = self._get_filter(include_commits=False)
        command.extend(filter_list)
        if filter_str:
            full_command_str += " " + filter_str
        # the trailing slash is very important for rsync
        # on Windows the separator is the same for rsync.
        # https://stackoverflow.com/a/59987187/952234
        # However, this may or may not work in cygwin
        # https://stackoverflow.com/a/18797771/952234
        root_dir = self.root_dir + '/'
        command.append(root_dir)
        command.append(commit_dir_tmp)
        full_command_str += " " + root_dir + " " + commit_dir_tmp

        self._print_command(full_command_str)
        if self.print_level >= 3:
            # with run there will be problems during testing
            completed_process = subprocess.Popen(command)
        else:
            completed_process = subprocess.Popen(
                command, stdout=subprocess.DEVNULL
            )
        completed_process.communicate()
        returncode = completed_process.returncode
        if returncode:
            # if the run was not verbose enough, we won't see stdout.
            # Make a more verbose commit then.
            _print_error("an error occurred during hard linking, "
                         "rsync returned {}".format(returncode))
            return returncode

        # commit is done
        self._print_command("mv {} {}".format(commit_dir_tmp, commit_dir),
                            level=3)
        os.rename(commit_dir_tmp, commit_dir)

        ## log ##
        if not os.path.exists(self.LOGDIR):
            self._print_command("mkdir {}".format(self.LOGDIR))
            os.mkdir(self.LOGDIR)

        commit_log_name = os.path.join(self.LOGDIR, commit_name + ".txt")

        # write log file
        with open(commit_log_name, "w") as commit_file:
            print(short_commit_mess, file=commit_file)

        # print to stdout
        self._print(
            "commit {} created\n\n".format(commit_name),
            short_commit_mess,
            sep=""
        )

        try:
            # merge is done, if that was active
            os.remove(self.MERGEFILE)
        except FileNotFoundError:
            pass

        # if we were not at HEAD, move that now
        self._update_head()

        return 0

    def _diff(self, commit1=None, commit2=None, verbose=True):
        # arguments are positional only
        """Print the difference between *commit1* and *commit2*
        (from the old to the new one).
        """

        if commit1 is None:
            commit1 = int(self._args.commit)

        if commit2 is None:
            commit2 = self._args.other_commit
            if commit2 is None:
                commit2 = self._get_last_commit()
            else:
                commit2 = int(commit2)

        comm1 = min(commit1, commit2)
        comm2 = max(commit1, commit2)

        comm1_dir = os.path.join(self.COMMITDIR, str(comm1))
        comm2_dir = os.path.join(self.COMMITDIR, str(comm2))

        if not os.path.exists(comm1_dir):
            raise ValueError("commit {} does not exist".format(comm1))
        if not os.path.exists(comm2_dir):
            raise ValueError("commit {} does not exist".format(comm2))

        command = [
            "rsync", "-aun", "--delete", "-i", 
        ]
        # outbuf option added in Rsync 3.1.0 (28 Sep 2013)
        # https://download.samba.org/pub/rsync/NEWS#ENHANCEMENTS-3.1.0
        # from https://stackoverflow.com/a/35775429
        command.append('--outbuf=L')

        # what changes should be applied for comm1 to become comm2
        # / is extremely important!
        command += [comm2_dir + '/', comm1_dir]

        if verbose:
            self._print_command(*command)

        sp = subprocess.Popen(command, stdout=subprocess.PIPE)
        for line in iter(sp.stdout.readline, b''):
            print(line.decode("utf-8"), end='')

        return sp.returncode

    def _get_dest_path(self, dest=None):
        """Return a pair *(host, destpath)*, where
        *host* is a real host (its ip/name/etc.) at the destination
        and *destpath* is a path on that host.

        If *host* is not present in the configuration,
        it is set to localhost.
        If destination path is missing, `KeyError` is raised.
        """
        config = self._configdict
        # if dest:
        try:
            dest_section = config[dest]
        except KeyError:
            raise KeyError(
                "no destination '{}' found in the configuration {}. ".
                format(dest, self.CONFIGFILE)
            )
        # todo:
        # else:
        #     # find a section with a key "upstream".
        #     # It could be also "upstream-push" or "upstream-pull",
        #     # but this looks too remote for now.
        #     try:
        #         dest = config["default"]["name"]
        #     except KeyError:
        #         raise KeyError(
        #             'no default destination found in config. '
        #         )

        # destpath must be present (checked during _read_config).
        destpath = dest_section["destpath"]

        if not destpath.endswith('/'):
            destpath += '/'

        return destpath

    def _get_filter(self, include_commits=True):
        # todo: .ys, commits and logs should not be fixed here.
        if os.path.exists(self.RSYNCFILTER):
            filter_ = ["--filter=merge {}".format(self.RSYNCFILTER)]
            filter_str = "--filter='merge {}'".format(self.RSYNCFILTER)
        else:
            filter_ = []
            filter_str = ""
        if include_commits:
            includes = ["/.ys/commits", "/.ys/logs"]
            include_commands = ["--include={}".format(inc) for inc in includes]
            # since we don't have spaces in the command,
            # single ticks are not necessary
            include_command_str = " ".join(["--include={}".format(inc)
                                            for inc in includes])
            filter_ += include_commands
            if filter_str:
                # otherwise an empty string will be joined by a space
                filter_str = " ".join([filter_str, include_command_str])
            else:
                filter_str = include_command_str
        # exclude can go before or after include,
        # because the first matching rule is applied.
        # It's important to place /* after .ys,
        # because it means files exactly one level below .ys
        filter_ += ["--exclude=/.ys/*"]
        if filter_str:
            filter_str += " "
        filter_str += "--exclude=/.ys/*"
        # print("filter_str: '{}'".format(filter_str))
        return (filter_, filter_str)

    def _get_head_commit(self):
        try:
            with open(self.HEADFILE, "r") as head:
                # strip trailing newline
                head_commit = head.readlines()[0].strip()
        except OSError:
            # no HEADFILE means HEAD is the most recent commit
            return None
        return int(head_commit)

    def _get_last_commit(self, commits=None):
        # todo: cache the last commit (or all commits)
        # but: pull can update that!
        if commits is None:
            commits = self._get_local_commits()
        if not commits:
            return None
        return max(commits)

    def _get_last_sync(self, verbose=True):
        try:
            with open(self.SYNCFILE) as fil:
                data = fil.readlines()[0].strip()  # remove trailing newline
                commit, repo = data.split(sep=",", maxsplit=1)
        except OSError:
            # this is not an error
            # verbose is False for automatic usage.
            if verbose:
                self._print("No synchronization information found.")
            return (None, None)
        return (int(commit), repo)

    def _get_local_commits(self):
        """Return local commits as an iterable of integers."""
        # todo: cache results.
        try:
            # listdir always returns a list (Python 2 and 3)
            commit_candidates = os.listdir(self.COMMITDIR)
        except OSError:
            # no commits exist
            # todo: do we print about that here?
            commit_candidates = []
        return list(map(int, filter(_is_commit, commit_candidates)))

    def _get_remote_commits(self, commit_dir, print_level=3):
        """Return remote commits as a list of integers."""
        try:
            remote_files = self._get_remote_files(commit_dir, print_level=print_level)
        except OSError:
            return []
            # allow a missing commit directory for a new repository
            # (can simply push local commits there).
            # # detailed error messages are already printed by rsync
            # raise OSError(
            #     "error during listing remote commits"
            # )

        commits = []
        for comm in remote_files:
            if not _is_commit(comm):
                raise OSError(
                    "not a commit found on remote: {}".format(comm)
                )
            commits.append(int(comm))

        return commits

    def _get_remote_files(self, path, print_level=3):
        """Return a list of files at the remote path.
        Path can be one file (why though).
        The result does not contain '.' and '..'.
        Remote can be local.
        """
        command = ["rsync", "--list-only", path]
        # Another variant:
        # "-r --exclude='/*/*'" means
        # to list a single directory without recursion.
        # If a pattern ends with a '/',
        # then it will only match a directory.
        # command = "rsync -nr --info=NAME --include=/ --exclude=/*/*".split() \
        #           + [from_path, to_path]
        self._print_command(" ".join(command), level=print_level)
        if print_level:
            stderr = None  # all errors printed
        else:
            stderr = subprocess.PIPE
        sp = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=stderr)
        sp.wait()

        returncode = sp.returncode
        if returncode:
            raise OSError(
                "error during listing remote files: rsync returned {}"\
                .format(returncode)
            )

        files = []
        for line in iter(sp.stdout.readline, b''):
            fil = line.split()[-1]
            if fil not in [b'.', b'..']:
                # make them strings for easier use
                # and coherent with os.listdir
                files.append(fil.decode("utf-8"))

        return files

    def _init(self, reponame, merge=False):
        """Initialize default configuration.

        Create configuration folder, configuration and repository files.

        If a configuration file already exists, it is not changed.
        This operation is safe and idempotent (can be repeated safely).

        *reponame* will be written to self.REPOFILE
        and used during commits.

        If *merge* is ``True``, the repository comprises several existing ones.
        This can be used to rearrange them
        without re-sending present remote files.
        """
        """
How to merge:
    1) Prepare the merge.
       a) synchronize all needed repositories (bring them to the same state).
          This is not needed (see comment about commits), but will make things easier.
       b) Check that you have not too many files (hard links),
          because they will triple during the merge.
          Consider removing some old commits (and sync again).
          But don't be overly cautious:
          for hundreds of thousands of files this worked fine for the author.
       c') Move non-merging repositories out of the directory with merging ones.
          This might be safer, but is unnecessary unless you care about more hard links.
       c'') Alternatively, move all merging repositories to a new directory.
           Since you've already synchronized them, preserving their remote paths is not needed.
    3) (actually now 2) Init and commit.
       [source] yarsync init --merge
       [source] yarsync commit -m "Merging. Initialize."
    4) Check that the repositories and filters are correct.
    5) create a remote merging repository (--merge is needed, otherwise
       remote status will show files in subdir/.ys/ .
       Probably won't affect actual transfers, because all filters
       will act on the sending side).
       [dest] yarsync init --merge
       Remove new rsync filters on dest, but it is not needed
       (we assume that the destination has no filters!)
    6) Push commits to destination
       # test, as ever
       [source] yarsync push -n <dest>
       [source] yarsync push <dest>
    7) now they are synced. Reorganize data (tip: just move gross directories
       to corresponding repositories, finely rearrange them any time later).
       Can remove the merging subrepository. It is saved in commits.
       [source] # yarsync status
       [source] yarsync commit -m "Merge done."
       May remove the merging repository from .ys/rsync-filter .
    7') (optional) make commits in the resulting subrepositories.
       [source/repo] yarsync commit -m "Merged that and that data from <merged repo>."
       Probably don't do that, or deal with rsync filters in their roots.
    8) push data to its destination.
       [source] # yarsync push -n <dest>
       [source] yarsync push <dest>
       If you removed the repository locally, but didn't wipe it from the filter,
       rsync will refuse to delete its remote configuration,
       because it is still protected by filter rules.
       You can remove it manually on the destination.
       [dest] # rm -rf <merged_dir>
    9) Finish merge. Move all repositories to their initial directories.
    9') If you didn't commit during 7', commit changes to local repositories
        and push them to the destination.
        This should be really quick, because all files are already there.
        This could be done after 10), but is a bit safer before that.
    10) Remove the merging repository. Check that the current path is correct before that!
        [local] rm -rf .ys
        [remote] rm -rf .ys
        """
        init_repo_str = "Initialize configuration"
        if reponame:
            init_repo_str += " for '{}'".format(reponame)
        self._print(init_repo_str, level=2)

        # create config_dir
        ysdir = self.config_dir
        if not os.path.exists(ysdir):
            self._print_command("mkdir {}".format(ysdir))
            # self._print_command("mkdir -m {:o} {}".
            #                     format(self.DIRMODE, ysdir))
            # can raise "! [Errno 13] Permission denied: '.ys'"
            os.mkdir(ysdir)
            # if every configuration file existed,
            # new_config will be False
            new_config = True
        else:
            self._print("{} already exists, skip".format(ysdir), level=2)
            new_config = False

        # create self.CONFIGFILE
        # todo: create example configuration file.
        if not os.path.exists(self.CONFIGFILE):
            self._print("# create configuration file {}".format(self.CONFIGFILE))
            with open(self.CONFIGFILE, "w") as fil:
                print(CONFIG_EXAMPLE, end="", file=fil)
            new_config = True
        else:
            self._print("{} already exists, skip".format(self.CONFIGFILE),
                        level=2)

        # create repofile
        repofile = self.REPOFILE
        if not os.path.exists(repofile):
            if not reponame:
                self._print(
                    "# (to use a repository name different from `hostname`"
                    " for commit logs,\n"
                    "#  provide it as an argument to 'init'"
                    " or write it to {})".format(repofile)
                )
            else:
                self._print("# create configuration file {}".format(repofile))
                with open(repofile, "w") as fil:
                    print(reponame, end="", file=fil)
                new_config = True
        else:
            self._print("{} already exists, skip".format(repofile), level=2)

        if merge:
            rsync_filter = "rsync-filter"
            dirs = os.listdir('.')
            # it is recommended to merge existing repositories
            # (not just any directories),
            # but we don't check it here.
            filter_strs = ["# created by 'yarsync init --merge'"]
            for dir_ in dirs:
                if not os.path.exists(os.path.join(dir_, ".ys")):
                    # not yarsync repositories
                    continue
                if not os.path.isdir(dir_):
                    # simple files
                    continue
                if dir_ == ysdir:
                    # we are already in a merging repository,
                    # and init is idempotent.
                    continue
                # transfer commits and logs.
                # This allows to sync the resulting
                # repositories simultaneously.
                # If one wants have fewer hard links,
                # they should remove these include lines manually.
                filter_strs.append("+ /" + dir_ + "/.ys/commits")
                filter_strs.append("+ /" + dir_ + "/.ys/logs")
                ys_filter = os.path.join(dir_, ".ys", rsync_filter)
                if os.path.exists(ys_filter):
                    # copy rsync filters, so that they have effect
                    # on the repository (not only inside .ys directory).
                    filter_copy = os.path.join(dir_, rsync_filter)
                    # check that we don't destroy existing files.
                    if os.path.exists(filter_copy):
                        if (os.stat(filter_copy).st_ino !=
                            os.stat(ys_filter).st_ino):
                            # st_ino is platform dependent,
                            # but since we use commits
                            # and we are on Linux,
                            # it should always work (for Windows too).
                            # https://docs.python.org/3/library/os.html#os.stat_result
                            _print_error(
                                filter_copy + " exists. "
                                "Can't link existing filter {}/.ys/rsync-filter."
                                "\n  Remove or rename that file.".format(dir_)
                            )
                            raise YSCommandError()
                    else:
                        os.link(ys_filter, filter_copy)
                    # Filters for different repositories
                    # must be independent,
                    # therefore they are "per-directory"
                    # (single-instance ones
                    #  are simply incorporated into the filter).
                    # Possible problems:
                    # - stray rsync-filters (thouse outside .ys,
                    #   that would normally have no effect).
                    # -- seems a larger path works fine.
                    # - excluding/including more than needed.
                    # -- surprisingly, various/repos
                    #    was correctly created.
                    filter_strs.append(": " + dir_ + "/.ys/rsync-filter")
                    filter_strs.append("- " + filter_copy)
                    # don't use a slash before dir_,
                    # otherwise it will search in upper directories.
                # not transfer repository configuration.
                # /* is very important at the end,
                # because with /.ys it will not consider anything there
                # (includes discarded).
                filter_strs.append("- /" + dir_ + "/.ys/*")
            # --merge overwrites this file every init.
            # if os.path.exists(self.RSYNCFILTER):
            with open(self.RSYNCFILTER, 'w') as fil:
                for str_ in filter_strs:
                    print(str_, file=fil)
            new_config = True
            self._print("# Created configuration file {}".format(self.RSYNCFILTER))

        ysdir_fp = os.path.realpath(ysdir)
        if new_config:
            self._print("\nInitialized yarsync configuration in {} "
                        .format(ysdir_fp))
        else:
            self._print("\nConfiguration in {} already initialized."
                        .format(ysdir_fp))

        return 0

    def _make_commit_list(self, commits=None, logs=None):
        """Make a list of *(commit, commit_log)*
        for all logs and commits.

        *commits* and *logs* are sorted lists of integers.

        If a log is missing for a given commit,
        or a commit is missing for a log, the result contains ``None``.
        """
        # commits and logs in the interface
        # are only for testing purposes

        def get_sorted_logs_int(files, commits=None):
            # discard '.log' extension
            log_names = (fil[:-4] for fil in files)
            sorted_logs = sorted(map(int, filter(_is_commit, log_names)))
            if commits is None:
                return sorted_logs
            else:
                # if commits are set explicitly,
                # return logs only for those commits
                return [log for log in sorted_logs if log in commits]

        if logs is None:
            try:
                log_files = os.listdir(self.LOGDIR)
            except OSError:
                # no log directory exists
                log_files = []
            logs = get_sorted_logs_int(log_files, commits)
        
        if commits is None:
            commits = sorted(self._get_local_commits())
        else:
            commits = sorted(commits)
            # note that we don't check whether these commits
            # actually exist. This function logic doesn't require that.
            # todo: allow commits in the defined order.
            # that would require first yielding all commits,
            # then all logs without commits. Looks good.
            # And much simpler. But will that be a good log?..

        if not commits and not logs:
            return []

        results = []
        commit_ind = 0
        commits_len = len(commits)
        log_ind = 0
        logs_len = len(logs)
        commit = None
        log = None

        while True:
            logs_finished = (log_ind > logs_len - 1)
            commits_finished = (commit_ind > commits_len - 1)
            if not commits_finished:
                commit = commits[commit_ind]
            if not logs_finished:
                log = logs[log_ind]

            if commits_finished and logs_finished:
                break
            elif logs_finished:
                results.append((commit, None))
                commit_ind += 1
                continue
            elif commits_finished:
                results.append((None, log))
                log_ind += 1
                continue
            # print(commit_ind, log_ind)

            # both commits and logs are present
            if commit == log:
                results.append((commit, log))
                commit_ind += 1
                log_ind += 1
            elif commit < log:
                results.append((commit, None))
                commit_ind += 1
            else:
                results.append((None, log))
                log_ind += 1
        return results

    def _log(self):
        """Print commits and log information.

        If only a commit or only a log are present, they are listed as well.

        By default most recent commits are printed first.
        Set *reverse* to ``False`` to print last commits last.
        """
        reverse = self._args.reverse
        max_count = self._args.max_count

        cl_list = self._make_commit_list()

        if not reverse:
            commit_log_list = list(reversed(cl_list))
        else:
            commit_log_list = cl_list
        if max_count != -1:
            # otherwise the last element is excluded
            commit_log_list = commit_log_list[:max_count]

        synced_commit, remote = self._get_last_sync(verbose=True)
        head_commit = self._get_head_commit()

        def print_logs(commit_log_list):
            for ind, (commit, log) in enumerate(commit_log_list):
                if ind:
                    print()
                self._print_log(commit, log, synced_commit, remote, head_commit)

        print_logs(commit_log_list)

        if not commit_log_list:
            self._print("No commits found")

        # in fact, sys.exit(None) still returns 0 to the shell
        return 0

    def _print(self, *args, level=1, **kwargs):
        """Print output messages."""
        if level > self.print_level:
            return
        if level >= 2:
            print("# ", end='')
        print(*args, **kwargs)

    def _print_command(self, *args, **kwargs):
        """Print called commands."""
        # A separate function to semantically distinguish that
        # from _print in code.
        # However, _print is used internally - to handle output levels.
        self._print(*args, **kwargs)

    def _print_log(self, commit, log, synced_commit=None, remote=None,
                   head_commit=None):
        if commit is None:
            commit_str = "commit {} is missing".format(log)
            commit = log
        else:
            commit_str = "commit " + str(commit)
            if commit == head_commit:
                commit_str += " (HEAD)"
            if commit == synced_commit:
                commit_str += " <-> {}".format(remote)
        if log is None:
            log_str = "Log is missing"
            # time.time is timezone independent.
            # Therefore localtime is the local time
            # corresponding to that universal time.
            # Commit could be made in any time zone.
            commit_time_str = time.strftime(self.DATEFMT, time.localtime(commit))
            log_str += "\nWhen: {}".format(commit_time_str) + '\n'
        else:
            log_file = open(os.path.join(self.LOGDIR, str(log) + ".txt"))
            # read returns a redundant newline
            log_str = log_file.read()
            # print("log_str: '{}'".format(log_str))
        # hard to imagine a "quiet log", but still.
        self._print(commit_str, log_str, sep='\n', end='')
        # print(commit_str, log_str, sep='\n', end='')

    def _pull_push(
            self, command_name, remote,
            force=False, new=False, overwrite=False,
            backup=False, backup_dir=""
        ):
        """Push/pull commits to/from destination or source.

        By default, several checks are made to prevent corruption:
            - source has no uncommitted changes,
            - source has not a detached HEAD,
            - source is not in a merging state,
            - destination has no commits missing on source.

        Note that the destination might have uncommitted changes:
        check that with *-n* (*--dry-run*) first!

        *backup*, *backup_dir* and *new* only apply to pull.
        """

        if self._get_head_commit() is not None:
            # it could be safe to push a repo with a detached HEAD,
            # but that would be messy.
            # OSError is for exceptions
            # that can occur outside the Python system
            raise OSError("local repository has detached HEAD.\n"
                          "*checkout* the most recent commit first.")
        if os.path.exists(self.MERGEFILE):
            raise OSError(
                "local repository has unmerged changes.\n"
                "Manually update the working directory and *commit*."
            )

        if not new:
            returncode, changed = self._status(check_changed=True)
            if changed:
                _print_error(
                    "local repository has uncommitted changes. Exit.\n  "
                    "Run '{} status' for more details.".format(self.NAME)
                )
                return COMMAND_ERROR
            if returncode:
                _print_error(
                    "could not check for uncommitted changes, "
                    "rsync returned {}. Exit\n  ".format(returncode) +
                    "Run '{} status' for more details.".format(self.NAME)
                )
                return COMMAND_ERROR

        try:
            full_destpath = self._get_dest_path(remote)
        except KeyError as err:
            raise err from None

        # --link-dest is not needed, since if a file is new,
        # it won't be in remote commits.
        # -H preserves hard links in one set of files (but see the note in todo.txt).
        command = ["rsync"]
        command.extend(self.RSYNCOPTIONS)
        # Don't print progress by default,
        # because it clutters output for new commits.
        # (it will create an additional line for each file
        #  and will require extra work to get rid of it).
        if self.print_level >= 3:
            command.append("-P")

        dry_run = self._args.dry_run
        if dry_run:
            command.append("-n")
        command_str = " ".join(command)

        if not new:
            command.append("--delete-after")
            command_str += " --delete-after"

        if backup:
            if backup_dir:
                # create a full hierarchy in the backup_dir
                command.extend(["--backup-dir", backup_dir])
                # may contain spaces, ignore.
                command_str += " --backup-dir " + backup_dir
            # --backup is implied during --backup-dir
            # only since this pull request in 2020
            # https://github.com/WayneD/rsync/pull/35
            # write new files near originals
            command.append("--backup")
            command_str += " --backup"
        # allow after a fix of https://github.com/WayneD/rsync/issues/357
        # elif not overwrite:
        #     command.append("--ignore-existing")
        #     command_str += " --ignore-existing"

        # we don't include commits (filter them in)
        # only if we do backups
        include_commits = not backup
        # if there exists .ys/rsync-filter, command string needs quotes
        filter_, filter_str = self._get_filter(include_commits=include_commits)
        command.extend(filter_)
        command_str += " " + filter_str

        root_path = self.root_dir + "/"
        if command_name == "push":
            command.append(root_path)
            command.append(full_destpath)
            command_str += " {} {}".format(root_path, full_destpath)
        else:
            # pull
            command.append(full_destpath)
            command.append(root_path)
            command_str += " {} {}".format(full_destpath, root_path)

        # old local commits (before possible pull)
        local_commits = list(self._get_local_commits())

        # if there are no remote commits (a new repository),
        # push will still work
        remote_commits_dir = os.path.join(full_destpath, ".ys", "commits/")
        remote_commits = self._get_remote_commits(
            remote_commits_dir,
            # don't complain about errors
            print_level=0
        )

        # missing_commits can be overwritten by pull or push
        if command_name == "push":
            source_commits = local_commits
            dest_commits = remote_commits
        else:
            # pull
            source_commits = remote_commits
            dest_commits = local_commits
            rmcomm = set(remote_commits)
            missing_commits = [comm for comm in local_commits
                               if comm not in rmcomm]

        # use a set to economize testing membership in a list,
        # https://stackoverflow.com/a/3462202/952234
        # Can move into the comprehension. Not used anywhere else.
        # https://docs.python.org/3/reference/simple_stmts.html#grammar-token-python-grammar-target_list
        _source_commits = set(source_commits)
        missing_commits = [comm for comm in dest_commits
                           if comm not in _source_commits]

        if not (force or new) and missing_commits:
            missing_commits_str = ", ".join(map(str, missing_commits))
            raise OSError(
                "\ndestination has commits missing on source: {}, "\
                .format(missing_commits_str) +
                "synchronize these commits first:\n"
                "1) pull missing commits with 'pull --new',\n"
                "2) push if these commits were successfully merged, or\n"
                "2') optionally checkout,\n"
                "3') manually update the working directory "
                "to the desired state, commit and push,\n"
                "2'') --force local state to remote "
                "(removing all commits and logs missing on the destination)."
            )

        if self.print_level >= 3:
            stdout = None
        elif self.print_level == 2:
            stdout = subprocess.PIPE
        else:
            stdout = subprocess.DEVNULL

        self._print_command(command_str, level=3)

        # ----------------------------------------------------------
        #         Run
        completed_process = subprocess.Popen(command, stdout=stdout)
        # ----------------------------------------------------------

        if self.print_level == 2:
            # if we transfer a whole commit, merge all its output into one line.
            # Print transfers only for the working directory and existing commits.
            commits_to_transfer = set(source_commits) - set(dest_commits)
            transferred_commits = set()
            for line in iter(completed_process.stdout.readline, b''):
                # iteration copied from https://stackoverflow.com/a/1606870/952234
                # Not self.COMMITDIR, because it involves the complete path.
                COMMITDIR = os.path.join(".ys", "commits")
                if line.startswith(bytes(COMMITDIR, "utf-8")):
                    # commits
                    com_start = len(COMMITDIR) + 1
                    # or os.sep
                    com_end = line.find(b'/', com_start)
                    com_str = line[com_start:com_end]
                    if not com_str:
                        # ".ys/commits/"
                        print(line.decode("utf-8"), end='')
                        continue
                    cur_commit = int(com_str)
                    if cur_commit in commits_to_transfer:
                        # don't print transfers for complete new commits.
                        transferred_commits.add(cur_commit)
                    else:
                        # print changes for existing commits
                        print(line.decode("utf-8"), end='')
                else:
                    # working directory
                    print(line.decode("utf-8"), end='')
            # there can be also lines like
            # file => .ys/commits/.../file
            # leave them as they are.
            #
            # actually, this may be only part of the data
            # (if there is no space left)
            print()  # "data transferred for commits:")
            for comm in sorted(transferred_commits):
                print("commit", comm)
        else:
            completed_process.wait()

        returncode = completed_process.returncode
        if returncode:
            _print_error(
                "an error occurred, rsync returned {}. Exit".
                format(returncode)
            )
            return returncode

        if new:
            last_remote_comm = max(remote_commits)
            if last_remote_comm in local_commits:
                # remote commits are within locals (except some old ones)
                # update the working directory
                self._checkout(max(local_commits))
                self._print("remote commits automatically merged")
            else:
                # remote commits diverged, need to merge them manually
                common_commits = set(local_commits)\
                                 .intersection(remote_commits)
                if common_commits:
                    common_comm = max(common_commits)
                else:
                    common_comm = "missing"
                merge_str = "{},{},{}".format(max(local_commits),
                                              last_remote_comm, common_comm)
                # todo: check that it is taken into account in other places!
                if not dry_run:
                    try:
                        with open(self.MERGEFILE, "w") as fil:
                            print(merge_str, end="", file=fil)
                    except OSError:
                        _print_error(
                            "could not create a merge file {}, ".
                            format(self.MERGEFILE) +
                            "create that manually with " + merge_str
                        )
                        raise OSError from None
                self._print(
                    "merge {} and {} manually and commit "
                    "(most recent common commit is {})".
                    format(max(local_commits), last_remote_comm, common_comm)
                )

        if not new and not dry_run:
            # --new means we've not fully synchronized yet
            last_commit = self._get_last_commit()
            # is it not possible that we have no commits at all,
            # because that would mean uncommitted changes.
            # todo: store information about
            # synchronization with several remotes?
            sync_str = "{},{}".format(last_commit, remote)
            try:
                with open(self.SYNCFILE, "w") as fil:
                    print(sync_str, end="", file=fil)
            except OSError:
                _print_error("data transferred, but could not log to {}"
                             .format(self.SYNCFILE))

            # either HEAD was correct ("not detached") (for push)
            # or it was updated (by pull)
            self._update_head()

        return 0

    def _read_config(self, config_text):

        # substitute environmental variables (those that are available)
        # todo: what if an envvar is not present for the current section?
        subst_lines = _substitute_env(config_text).getvalue()

        # no value is allowed
        # for a configuration key "host_from_section_name"
        config = configparser.ConfigParser(allow_no_value=True)
        # ConfigParser.read_string
        # is undocumented in Python2, but present!
        config.read_string(subst_lines)

        # configdict is config with some evaluations,
        # like full paths.
        configdict = {}
        for section in config.sections():
            sectiond = dict(config[section])
            configdict[section] = sectiond
            if section == config.default_section:
                continue

            try:
                host = sectiond["host"]
            except KeyError:
                if "host_from_section_name" in config[config.default_section]:
                    # sections for remotes are named after their hosts
                    host = section
                else:
                    host = ""
            try:
                path = sectiond["path"]
            except KeyError as err:
                err_descr = "a required key 'path' is missing. "\
                    "Provide the path to the remote '{}'.".\
                    format(section)
                _print_error(
                    "{} configuration error in {}:\n  ".
                    format(self.NAME, self.CONFIGFILE) +
                    err_descr
                )
                raise YSConfigurationError(err, err_descr)

            # If host is empty, then this is a local host
            # or it is already present in the path.
            # If host is non-empty, that can't be present in the path.
            sectiond["destpath"] = _mkhostpath(host, path)

        # print all values:
        # formatter = lambda s: json.dumps(s, sort_keys=True, indent=4)
        # print(formatter(configdict))

        # config.items() includes the DEFAULT section, which can't be removed.
        return (config, configdict)

    def _remote(self):
        """Manage remotes."""
        # Since self._func() is called without arguments,
        # this is the place for all remote-related operations.
        if self._args.remote_command == "add":
            repository = self._args.repository
            path = self._args.path
            # options = self._args.options
            return self._remote_add(repository, path)
            # return self._remote_add(repository, path, options)
        elif self._args.remote_command == "rm":
            return self._remote_rm(self._args.repository)

    def _remote_add(self, remote, path, options=""):
        """Add a remote and its path to the config file."""
        # from https://docs.python.org/2.7/library/configparser.html#examples
        if not hasattr(self, "_config"):
            # config might be missing if we first call 'init'
            # and then '_remote_add' (as in 'clone').
            # In that case it is not necessary to check for all errors.
            with open(self.CONFIGFILE, "r") as conf_file:
                config_text = conf_file.read()
                self._config, self._configdict = self._read_config(config_text)

        config = self._config

        try:
            config.add_section(remote)
        except configparser.DuplicateSectionError:
            _print_error(
                "remote {} exists, break.\n  Remove {} "
                "or choose a new remote name.".format(remote, remote)
            )
            return COMMAND_ERROR
        config.set(remote, "path", path)
        # todo: options not implemented
        if options:
            config.set(remote, "options", options)
        with open(self.CONFIGFILE, "w") as configfile:
            config.write(configfile)
        self._print("Remote {} added.".format(remote))
        return 0

    def _remote_rm(self, remote):
        """Remove a *remote*."""
        config = self._config
        try:
            del config[remote]
        except KeyError:
            _print_error(
                "no remote {} found, exit".format(remote)
            )
            return COMMAND_ERROR
        with open(self.CONFIGFILE, "w") as configfile:
            config.write(configfile)
        self._print("Remote {} removed.".format(remote))
        return 0

    def _remote_show(self):
        """Print names of remotes. If verbose, print paths as well."""
        # that might be useful to specify a remote name,
        # but git doesn't do that, and we won't.
        if self._args.verbose:
            for section, options in self._configdict.items():
                print(section, options["destpath"], sep="\t")
        else:
            for section in self._config.sections():
                print(section)
        if not self._config.sections():
            self._print("No remotes found.")

    def _show(self, commits=None):
        """Show commit(s).

        Print log and difference with the previous commit
        for each commit.
        """
        # commits argument is for testing
        if commits is None:
            commits = [int(commit) for commit in self._args.commit]

        all_commits = sorted(self._get_local_commits())
        for commit in commits:
            if commit not in all_commits:
                raise ValueError(
                    "no commit {} found".format(commit)
                )

        # commit logs can be None
        commits_with_logs = self._make_commit_list(commits=commits)
        synced_commit, remote = self._get_last_sync(verbose=True)

        for ind, cl in enumerate(commits_with_logs):
            commit, log = cl
            # print log
            if ind:
                print()
            self._print_log(commit, log, synced_commit, remote)
            # print commit
            commit_ind = all_commits.index(commit)
            if not commit_ind:
                print("commit {} is initial commit".format(commit))
                continue
            previous_commit = all_commits[commit_ind - 1]
            self._diff(commit, previous_commit)

    def _status(self, check_changed=False):
        """Print files and directories that were updated more recently
        than the last commit.

        Return exit code of `rsync`.
        If *check_changed* is `True`,
        return a tuple *(returncode, changed)*,
        where *changed* is `True` if and only if
        the working directory has changes since last commit.
        """
        # We don't return an error if the directory has changed,
        # because it is a normal situation (not an error).
        # This is the same as in git.

        if os.path.exists(self.COMMITDIR):
            commit_subdirs = [fil for fil in os.listdir(self.COMMITDIR)
                              if _is_commit(fil)]
        else:
            commit_subdirs = []

        # decided to leave the condition explicit in code.
        # def cond_print(*args, **kwargs):
        #     """A wrapper to ignore check in every place."""
        #     if check_changed:
        #         return
        #     self._print(*args, **kwargs)

        ## no commits is fine for an initial commit
        if not commit_subdirs:
            if check_changed:
                for subdir in os.scandir(self.root_dir):
                    if subdir.path != self.config_dir or subdir.is_file():
                        return (0, True)
                # if there is only '.ys' in the working directory,
                # then the repository is unchanged.
                return (0, False)
            self._print("No commits found")
            return 0

        head_commit = self._get_head_commit()
        if head_commit is None:
            newest_commit = max(map(int, commit_subdirs))
            ref_commit_dir = os.path.join(self.COMMITDIR, str(newest_commit))
        else:
            ref_commit_dir = os.path.join(self.COMMITDIR, str(head_commit))

        filter_command, filter_str = self._get_filter(include_commits=False)

        command_begin = [
            "rsync", "-aun", "--delete", "-i", "--exclude=/.ys"
        ]
        command_str = " ".join(command_begin)

        command = command_begin + filter_command
        if filter_str:
            command_str += " " + filter_str

        # outbuf option added in Rsync 3.1.0 (28 Sep 2013)
        # https://download.samba.org/pub/rsync/NEWS#ENHANCEMENTS-3.1.0
        # from https://stackoverflow.com/a/35775429
        command.append('--outbuf=L')
        command_str += " --outbuf=L"

        root_path = self.root_dir + "/"
        command_end = [root_path, ref_commit_dir]
        command += command_end
        command_str += " " + " ".join(command_end)

        if not check_changed:
            self._print(command_str, level=3)

        # default stderr (None) outputs to parent's stderr
        sp = subprocess.Popen(command, stdout=subprocess.PIPE)
        # this works correctly, but strangely for pytest:
        # https://github.com/pytest-dev/pytest-mock/issues/295#issuecomment-1155091491
        # sp = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=sys.stderr)
        # changed means there were actual changes in the working dir
        changed = False
        # note that directories may appear to be changed
        # just because of timestamps (add and remove a file), e.g.
        # b'.d..t...... ./\n'
        # b'' means EOF in the iteration.
        lines = iter(sp.stdout.readline, b'')
        for line in lines:
            if line:
                # if not check_changed:
                self._print("Changed since head commit:\n")
                # skip permission changes
                if not line.startswith(b'.'):
                    changed = True
                    # if check_changed:
                    #     # return code is unimportant in this case
                    #    return (0, changed)

                # print the line and all following lines.
                # todo: use terminal encoding
                print(line.decode("utf-8"), end='')
                # in fact, readline could be used twice.
                for line in lines:
                    if not line.startswith(b'.'):
                        changed = True
                        # if check_changed:
                        #     return (0, changed)
                    print(line.decode("utf-8"), end='')

        sp.wait()  # otherwise returncode might be None
        # None is fine for sys.exit() though,
        # because it will be converted to 0.
        # For testing, it is better to have it 0 here.
        returncode = sp.returncode

        if head_commit is not None:
            self._print("\nDetached HEAD (see '{} log' for more recent commits)"
                        .format(self.NAME))

        if os.path.exists(self.MERGEFILE):
            with open(self.MERGEFILE, "r") as fil:
                merge_str = fil.readlines()[0].strip()
            merges = merge_str.split(',')
            self._print("Merging {} and {} (most recent common commit {})."\
                        .format(*merges))

        if not changed and not check_changed:
            self._print("Nothing to commit, working directory clean.")
        if changed:  # and not check_changed:
            # better formatting
            self._print()

        synced_commit, repo = self._get_last_sync(verbose=not check_changed)

        if (synced_commit is not None and repo is not None
            and not check_changed):
            # if we only check for changes (to push or pull),
            # we are not interested in the commit synchronization status
            commits = list(self._get_local_commits())
            last_commit = self._get_last_commit(commits)
            if synced_commit == last_commit:
                self._print("\nCommits are up to date with {}."\
                            .format(repo))
            else:
                n_newer_commits = sum([1 for comm in commits
                                       if comm > synced_commit])
                # here we print a hash
                # to distinguish this line from others
                self._print("# local repository is {} commits ahead of {}"\
                            .format(n_newer_commits, repo))

        # called from an internal method
        if check_changed:
            # changed is always False here
            return (returncode, changed)
        # called as the main command
        return returncode

    def _update_head(self):
        try:
            # no HEADFILE means HEAD is the most recent commit
            os.remove(self.HEADFILE)
        except FileNotFoundError:
            pass

    def __call__(self):
        """Call the command set during the initialisation."""
        try:
            # all errors are usually transferred as returncode
            # and functions throw no exceptions
            returncode = self._func()
        # in Python 3 EnvironmentError is an alias to OSError
        except OSError as err:
            # In Python 3 there are more errors, e.g. PermissionError, etc.
            # PermissionError belongs to OSError in Python 3,
            # but to IOError in Python 2.
            _print_error(err)
            returncode = 8
        # in case of other errors, None will be returned!
        # todo: what code to return for RuntimeError?
        return returncode


def main():
    # parse arguments
    try:
        ys = YARsync(sys.argv)
    except (argparse.ArgumentError, argparse.ArgumentTypeError,
            YSArgumentError, YSUnrecognizedArgumentsError) as err:
        ## Argparse error ##
        # rsync returns 1 in case of syntax or usage error,
        # therefore we use the same code
        # (rsync is never called during __init__).
        # the error message is printed by argparse.
        sys.exit(SYNTAX_ERROR)
    except (OSError, YSConfigurationError):
        ## ys configuration error ##
        # (not in a repository, configuration file missing, etc.)
        # the error is printed by YARsync
        sys.exit(CONFIG_ERROR)
    except SystemExit as err:
        ## Some runtime error ##
        # SystemExit can be 130 for python
        # and 1 for pypy for KeyboardInterrupt.
        # Since this is interpreter-dependent => unreliable,
        # we don't capture and return it.
        # Moreover: we guarantee that our error code does not interfere
        # with real rsync error codes (during the __init__).
        if err.code == 0:
            # normal argparse exit. For example, --help.
            sys.exit(0)
        else:
            sys.exit(SYS_EXIT_ERROR)
    except YSCommandError:
        sys.exit(COMMAND_ERROR)

    # make actual call
    try:
        # should this throw exceptions (_clone)
        # or return a non-zero code (_pull_push)?
        returncode = ys()
    except YSCommandError:
        sys.exit(COMMAND_ERROR)
    sys.exit(returncode)


if __name__ == "__main__":
    main()
