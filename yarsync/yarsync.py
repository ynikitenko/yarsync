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


def _is_remote(path):
    """A path is remote (for rsync) if ':' goes before '/'."""
    # todo: change to _get_remote_host, which returns "" for a local one
    host_sep = path.find(':')
    if host_sep == -1:
        # local
        return False

    # or '\' for Windows
    first_dir_sep = path.find('/')
    if first_dir_sep != -1:
        # if host_sep > first_dir_sep,
        # then our local path contain a colon
        return host_sep < first_dir_sep
    else:
        # no path separator
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


class Sync():
    """Manage synchronizations for different repositories.

    Public fields: by_repos.
    """

    def __init__(self, sync_list):
        """*sync_list* is a list of syncronization files in a format
        <commit>_<repository> .
        """
        br = {}
        for s in sync_list:
            commit, repo = s.split("_", maxsplit=1)
            commit = int(commit)
            # for each repository, store the most recent
            # synchronized commit.
            if repo in br:
                br[repo] = max(commit, br[repo])
            else:
                br[repo] = commit
        # to quickly get synchronized commits, use br.values()
        # bc = {}
        # for repo, commit in br.items():
        #     if commit in bc:
        #         bc[commit].add(repo)
        #     else:
        #         bc[commit] = set((repo,))
        # self.by_commits = bc
        self.by_repos = br
        # outdated commits from other to be removed
        # sets, because dictionary iteration is arbitrary
        self.removed = set()
        self.new = set()
        # self.repos = frozenset(br)  # keys

    def update(self, other):
        """Update synchronization information with that from *other*.

        *other* is an iterable of (commit, repo) pairs,
        for example, *Sync.by_repos.items()*.
        """
        br = self.by_repos
        new = self.new
        removed = self.removed
        for repo, commit in other:
            sync_str = "{}_{}".format(commit, repo)
            if repo in br:
                if commit > br[repo]:
                    br[repo] = commit
                    new.add(sync_str)
                elif commit < br[repo]:
                    removed.add(sync_str)
            else:
                br[repo] = commit
                new.add(sync_str)
        # bc = {}
        # for repo, commit in br.items():
        #     if commit in bc:
        #         bc[commit].add(repo)
        #     else:
        #         bc[commit] = set((repo,))
        # self.by_commits = bc

        # self.repos = frozenset(br)


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
            help="clone a repository"
        )
        parser_clone.add_argument(
            "source", metavar="<source>",
            help="path to the source repository"
        )
        parser_clone.add_argument(
            "destination", metavar="<destination>",
            help="path to the cloned repository"
        )

        # commit #
        def check_positive(value):
            # based on https://stackoverflow.com/a/14117511/952234
            err = argparse.ArgumentTypeError("must be a natural number")
            try:
                natural_num = int(value)
            except ValueError:
                raise err
            if natural_num <= 0:
                raise err
            return natural_num

        parser_commit = subparsers.add_parser(
            "commit", help="commit the working directory"
        )
        parser_commit.add_argument(
            "-m", "--message", metavar="<message>", default="",
            help="a string with the commit message"
        )
        parser_commit.add_argument(
            "--limit", metavar="<number>", type=check_positive,
            help="maximum number of commits"
        )

        # diff #
        parser_diff = subparsers.add_parser(
            "diff", help="print the difference between two commits"
        )
        parser_diff.add_argument(
            "commit", metavar="<commit>", help="commit name"
        )
        parser_diff.add_argument(
            "other_commit", metavar="<commit>", nargs="?", default=None,
            help="other commit name"
        )
        parser_diff.set_defaults(func=self._diff)

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
        self.YSDIR = ".ys"
        _ysdir = self.YSDIR

        root_dir = os.path.expanduser(args.root_dir)
        config_dir = os.path.expanduser(args.config_dir)
        if not root_dir and not config_dir:
            if args.command_name == "init":
                root_dir = "."
                config_dir = _ysdir
            elif args.command_name != "clone":
                # search the current directory and its parents
                try:
                    root_dir = _get_root_directory(_ysdir)
                except OSError as err:
                    # config dir not found.
                    _print_error(
                        "fatal: no {} configuration directory {} found".
                        format(self.NAME, _ysdir) +
                        "\n  Check that you are inside an existing repository"
                        "\n  or initialize a new repository with '{} init'.".
                        format(self.NAME)
                    )
                    raise err
                config_dir = os.path.join(root_dir, _ysdir)
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

        self.COMMITDIRNAME = "commits"
        self.COMMITDIR = os.path.join(self.config_dir, self.COMMITDIRNAME)
        self.CONFIGFILE = os.path.join(self.config_dir, "config.ini")
        self.DATEFMT = "%a, %d %b %Y %H:%M:%S %Z"
        self.HEADFILE = os.path.join(self.config_dir, "HEAD.txt")
        self.COMMITLIMITNAME = "COMMIT_LIMIT_"
        self.LOGDIRNAME = "logs"
        self.LOGDIR = os.path.join(self.config_dir, self.LOGDIRNAME)
        self.MERGEFILE = os.path.join(self.config_dir, "MERGE.txt")
        # contains repository name
        self.REPOFILE = os.path.join(self.config_dir, "repository.txt")
        self.RSYNCFILTERNAME = "rsync-filter"
        self.RSYNCFILTER = os.path.join(self.config_dir, self.RSYNCFILTERNAME)
        # yarsync repositories are owned by one user.
        # However, different machines can have different user
        # and group ids, so we don't push extraneous ids there.
        # Used in pull and push (and indirectly in clone).
        self.RSYNCOPTIONS = ["-avH", "--no-owner", "--no-group"]
        # stores synchronization information
        self.SYNCDIR = os.path.join(self.config_dir, "sync")
        # self.SYNCFILE = os.path.join(self.config_dir, "sync.txt")

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
        if args.command_name == "commit":
            self._func = functools.partial(
                self._commit,
                limit=args.limit, message=args.message
            )
        elif args.command_name == "clone":
            self._func = functools.partial(
                self._clone,
                source=args.source, destination=args.destination,
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

    def _clone(self, source, destination):
        """Clone a yarsync *source* to a *destination*.

        Only data (working directory, commits and logs)
        and *rsync-filter* will be cloned.

        *source* or *destination* (not both) can be remote paths.
        If a remote *source* has an *rsync-filter*, the command fails and
        an error is raised.

        If *source* ends with a slash, its contents are copied
        inside *destination*, otherwise *source* becomes its subfolder
        (standard *rsync* semantics).
        """
        ## check for rsync-filter in source
        try:
            # all os.path.join are incorrect if remote is on Windows.
            # The path must end with a '/'
            # for rsync to list directory contents (not its name).
            source_ys_dir = os.path.join(source, self.YSDIR, "")
            source_configs = [os.path.split(path)[1]
                              for path in self._get_remote_files(source_ys_dir)]
        except OSError as err:
            raise OSError(
                "could not read configuration in the repository {} ".
                format(source) + str(err)
            )

        source_is_remote = _is_remote(source)
        has_rsync_filter = self.RSYNCFILTERNAME in source_configs

        if has_rsync_filter and source_is_remote:
            _print_error(
                "remote source configuration contains rsync-filter. "
                "Aborting.\n  "
                "Only local repositories with filters can be cloned.\n"
                "  As a workaround, initialize a local repository,"
                "  copy remote filter locally, add source as a remote\n"
                "  and pull remote data."
            )
            raise YSCommandError()
        elif has_rsync_filter:
            self._print(
                "source has an rsync-filter. For a complete synchronization, "
                "a manual copy of filtered files/directories might be needed."
            )

        # if not source.endswith('/'):
        #     # add trailing slash
        #     source += '/'
        #     # remove trailing slash (it would be meaningless for a repo)
        #     # source = source[:-1]

        command = ["rsync"]
        command.extend(self.RSYNCOPTIONS)
        command.append("--no-inc-recursive")
        # todo: include rsync-filter into the transferred set!
        filter_ = self._get_filter(path=source)
        command.extend(filter_)

        command.append(source)
        command.append(destination)

        if self.print_level >= 3:
            stdout = None
            self._print_command(command, level=3)
        else:
            # for push and pull we pipe stdout,
            # but for clone it would be redundant
            # (one can list all local files with find)
            stdout = subprocess.DEVNULL

        # todo: create sync locally. Write it.

        # run rsync
        completed_process = subprocess.Popen(command, stdout=stdout)
        completed_process.wait()
        returncode = completed_process.returncode

        if returncode:
            _print_error(
                "an error occurred, rsync returned {}. Exit".
                format(returncode)
            )
            return returncode

        self._print("\n{} cloned.".format(source))
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

        command_begin = [
            "rsync", "-au",
            # completely meaningless: "--no-inc-recursive"
            "--link-dest=.ys/commits/{}".format(commit),
        ]
        if self._args.dry_run:
            command_begin += ["-n"]
        command_begin.extend(["--delete", "-i", "--exclude=/.ys"])

        filter_command = self._get_filter(include_commits=False)
        command = command_begin + filter_command

        # outbuf option added in Rsync 3.1.0 (28 Sep 2013)
        # https://download.samba.org/pub/rsync/NEWS#ENHANCEMENTS-3.1.0
        # from https://stackoverflow.com/a/35775429
        command.append('--outbuf=L')

        command += [commit_dir + '/', self.root_dir]

        if verbose:
            self._print_command(command)
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

    def _commit(self, limit=None, message=""):
        """Commit the working directory and create a log."""
        # commit directory name is based on UNIX time
        # date = datetime.date.today()
        # date_str = "{}{:#02}{:#02}"\
        #            .format(date.year, date.month, date.day)
        # print(date_str)

        reponame = self._get_repo_name()

        username = getpass.getuser()
        time_str = time.strftime(self.DATEFMT, time.localtime())

        log_str = "When: {date}\nWhere: {user}@{repo}".format(
            date=time_str, user=username, repo=reponame
        )
        if message:
            message += "\n\n"

        if os.path.exists(self.MERGEFILE):
            # copied from _status
            with open(self.MERGEFILE, "r") as fil:
                merge_str = fil.readlines()[0].strip()
            merges = merge_str.split(',')
            message += "Merge {} and {} (common commit {})\n"\
                                 .format(*merges)

        message += log_str

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

        filter_list = self._get_filter(include_commits=False)
        command.extend(filter_list)

        # the trailing slash is very important for rsync
        # on Windows the separator is the same for rsync.
        # https://stackoverflow.com/a/59987187/952234
        # However, this may or may not work in cygwin
        # https://stackoverflow.com/a/18797771/952234
        root_dir = self.root_dir + '/'
        command.extend([root_dir, commit_dir_tmp])

        self._print_command(command)
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
            print(message, file=commit_file)

        # print to stdout
        self._print(
            "commit {} created\n\n".format(commit_name),
            message, sep=""
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
            "rsync", "-aun",
            # useless now, see comment in _status()
            # "--no-inc-recursive",
            "--delete", "-i",
        ]
        # outbuf option added in Rsync 3.1.0 (28 Sep 2013)
        # https://download.samba.org/pub/rsync/NEWS#ENHANCEMENTS-3.1.0
        # from https://stackoverflow.com/a/35775429
        command.append('--outbuf=L')

        # what changes should be applied for comm1 to become comm2
        # / is extremely important!
        command += [comm2_dir + '/', comm1_dir]

        if verbose:
            self._print_command(command)

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

    def _get_filter(self, path="", include_commits=True):
        """Get filters to be used during synchronization.

        If *path* is non-empty,
        filters and configuration are relative to that path.
        """
        if path:
            rsync_filter = os.path.join(path, self.YSDIR, self.RSYNCFILTERNAME)
        else:
            rsync_filter = self.RSYNCFILTER

        if os.path.exists(rsync_filter):
            # for merge filter rsync requires a full path,
            # while for include/exclude only relative ones
            filter_ = ["--filter=merge {}".format(rsync_filter)]
        else:
            filter_ = []
        if include_commits:
            includes = [
                "/".join([self.YSDIR, self.COMMITDIRNAME]),
                "/".join([self.YSDIR, self.LOGDIRNAME]),
                # "/.ys/logs"
            ]
            include_commands = ["--include={}".format(inc) for inc in includes]
            # since we don't have spaces in the command,
            # single ticks are not necessary
            filter_ += include_commands

        # exclude can go before or after include,
        # because the first matching rule is applied.
        # It's important to place /* after .ys,
        # because it means files exactly one level below .ys
        filter_ += ["--exclude=/.ys/*"]

        return filter_

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

    def _get_local_sync(self, syncdata=None, verbose=True):
        """Get local synchronization information."""
        if syncdata is None:
            try:
                syncdata = os.listdir(self.SYNCDIR)
            except FileNotFoundError:  # sybtype of OSError
                syncdata = []
                # this is not an error
                # verbose is False for automatic usage.
                if verbose:
                    self._print("No synchronization directory found.")

        # parse synchronization data
        sync = Sync(syncdata)

        if not sync.by_repos and verbose:
            self._print("No synchronization information found.")

        return sync

    def _get_remote_config(self, config_dir, print_level=3):
        """Return remote commits as a list of integers."""
        try:
            remote_files = self._get_remote_files(
                config_dir, with_commits=True, print_level=print_level
            )
        except OSError:
            return []
            # allow a missing .ys directory for a new repository
            # (can simply push local commits there).
            # # detailed error messages are already printed by rsync
            # raise OSError(
            #     "error while listing remote commits"
            # )

        commits = []
        try:
            cmts = remote_files["commits"]
        except KeyError:
            pass
        else:
            for comm in cmts:
                try:
                    commit = int(comm)
                except ValueError:
                    continue
                    # this is not a crucial error.
                    # Maybe we'd like to store there a symlink "head"?
                    # Neither is this checked in local commits.
                    # raise OSError(
                    #     "not a commit found on remote: {}".format(comm)
                    # )
                commits.append(commit)

        if "sync" in remote_files:
            sync = Sync(remote_files["sync"])
        else:
            sync = Sync([])

        remote_files["commits"] = commits
        remote_files["sync"] = sync
        # leave other files as they are

        return remote_files

    def _get_remote_files(self, path, with_commits=False, print_level=3):
        """Return a list of files at the remote path.
        Path can be one file (why though).
        The result does not contain '.' and '..'.
        Remote can be local.
        """
        command = ["rsync", "--list-only"]
        if with_commits:
            # list commits, but not their contents
            command.extend(["-r", "--exclude=/*/*/*", "--exclude=logs/"])
        command.append(path)

        # no idea what from_path was in that case.
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

        files = {}
        for line in iter(sp.stdout.readline, b''):
            # print(line, line[0])
            # probably files with a space won't work here.
            fil = line.split()[-1]
            if fil in [b'.', b'..']:
                continue
            # make them strings for easier use
            # and coherent with os.listdir
            path = fil.decode("utf-8")
            # example: commits/1579013756
            parts = path.split('/')
            # or pathlib.PurePath(path).parts
            if len(parts) == 1:
                if line[0] == 100:  # b'd'
                    # a directory
                    dir_ = parts[0]
                    if dir_ not in files:
                        files[dir_] = []
                else:
                    # a file in .ys
                    files[path] = None
            else:
                dir_ = parts[0]
                subpath = "/".join(parts[1:])
                if dir_ in files:
                    files[dir_].append(subpath)
                else:
                    files[dir_] = [subpath]

        return files

    def _get_repo_name(self):
        try:
            with open(self.REPOFILE) as repofile:
                reponame = repofile.read()
        except OSError:
            # platform.node() just calls socket.gethostname()
            # with an error check
            reponame = socket.gethostname()
        return reponame

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

        sync = self._get_local_sync(verbose=True)
        head_commit = self._get_head_commit()

        def print_logs(commit_log_list):
            for ind, (commit, log) in enumerate(commit_log_list):
                if ind:
                    print()
                self._print_log(commit, log, sync, head_commit)

        print_logs(commit_log_list)

        if not commit_log_list:
            self._print("No commits found")

        # in fact, sys.exit(None) still returns 0 to the shell
        return 0

    def _print(self, *args, level=None, **kwargs):
        """Print output messages."""

        # in other print functions we use default level as None
        if level is None:
            level = 1

        if level > self.print_level:
            return
        if level >= 2:
            print("# ", end='')
        print(*args, **kwargs)

    def _print_command(self, command, level=None):
        """Print called commands."""
        # A separate function to semantically distinguish that
        # from _print in code.
        # However, _print is used internally - to handle output levels.

        def command_str(command):
            for comm in command:
                if ' ' in comm:
                    # can be present for
                    # --filter='merge test_dir_filter/.ys/rsync-filter'
                    # Alternatively, one can put '' to the right of '='
                    yield "'{}'".format(comm)
                else:
                    yield comm

        if isinstance(command, str):
            self._print(command, level=level)
        else:
            # list
            self._print(" ".join(command_str(command)), level=level)

    def _print_log(self, commit, log, sync=None, head_commit=None):
        if commit is None:
            commit_str = "commit {} is missing".format(log)
            commit = log
        else:
            commit_str = "commit " + str(commit)
            if commit == head_commit:
                commit_str += " (HEAD)"
            if commit in sync.by_repos.values():
                remote_str = ", ".join(sync[commit])
                commit_str += " <-> {}".format(remote_str)
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

        if not (new or force):
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

        command.append("--no-inc-recursive")
        if not new:
            command.append("--delete")

        if backup:
            if backup_dir:
                # create a full hierarchy in the backup_dir
                command.extend(["--backup-dir", backup_dir])
            # --backup is implied during --backup-dir
            # only since this pull request in 2020
            # https://github.com/WayneD/rsync/pull/35
            # write new files near originals
            command.append("--backup")
        # allow after a fix of https://github.com/WayneD/rsync/issues/357
        # elif not overwrite:
        #     command.append("--ignore-existing")
        #     command_str += " --ignore-existing"

        # we don't include commits (filter them in)
        # only if we do backups
        include_commits = not backup
        filter_ = self._get_filter(include_commits=include_commits)
        command.extend(filter_)

        root_path = self.root_dir + "/"
        if command_name == "push":
            command.extend([root_path, full_destpath])
        else:
            # pull
            command.extend([full_destpath, root_path])

        # old local commits (before possible pull)
        local_commits = list(self._get_local_commits())
        local_sync = self._get_local_sync(verbose=True)

        # if there are no remote commits (a new repository),
        # push will still work
        remote_config_dir = os.path.join(full_destpath, ".ys/")
        remote_config = self._get_remote_config(
            remote_config_dir,
            # don't complain about errors
            print_level=0
        )
        remote_commits = remote_config["commits"]
        remote_sync = remote_config["sync"]

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

        self._print_command(command, level=3)

        def write_sync(self, sync, verbose=True):
            if verbose:
                self._print("update synchronization:")
            for sync_str in sync.removed:
                if verbose:
                    self._print("  remove", sync_str)
                os.remove(os.path.join(self.SYNCDIR, sync_str))
            for sync_str in sync.new:
                if verbose:
                    self._print("  create", sync_str)
                if not os.path.exists(self.SYNCDIR):
                    os.mkdir(self.SYNCDIR)
                with open(os.path.join(self.SYNCDIR, sync_str), "x"):
                    # just create this file
                    pass

        # push synchronization information to the remote
        if command_name == "push" and not new and not dry_run:
            # forbid --new sync update,
            # because it messes all sync together.
            # Obsolete local sync will be removed.
            remote_sync.update(local_sync.by_repos.items())
            last_commit = self._get_last_commit()
            local_repo = self._get_repo_name()
            # todo: get remote name from remote .ys/repo_<name>
            # forbid several files with such name
            remote_sync.update([
                (local_repo, last_commit),
                (remote, last_commit)
            ])
            try:
                write_sync(self, remote_sync)
            except OSError as err:
                _print_error("could not log to {}. Abort."
                             .format(self.SYNCDIR))
                raise err

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

        not_all_commits_exist = not local_commits or not remote_commits
        if not_all_commits_exist:
            if not local_commits:
                self._print("local commits missing")
            if not remote_commits:
                self._print("remote commits missing")
            self._print("run {} without --new to fully synchronize "
                        "repositories".format(command_name))
        elif new:
            last_remote_comm = max(remote_commits)
            if last_remote_comm in local_commits:
                # remote commits are within locals (except some old ones)
                # automatic checkout is forbidden,
                # because it can delete files in the working directory
                # despite --new . Examples: uncommitted files,
                # interrupted (incomplete) commits.
                # self._checkout(max(local_commits))
                self._print(
                    "\nRemote commits can be automatically merged.\n"
                    "Check the working directory first with\n"
                    "  yarsync status\n"
                    "and commit or check out most recent commit:\n"
                    "  yarsync checkout {}".format(max(local_commits))
                )
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

        # update synchronization information locally
        if command_name == "pull" and not new and not dry_run:
            local_sync.update(remote_sync.by_repos.items())
            # we have some commits,
            # because otherwise that would mean uncommitted changes.
            last_commit = self._get_last_commit()
            local_repo = self._get_repo_name()
            # see todo for push
            local_sync.update([
                (local_repo, last_commit),
                (remote, last_commit)
            ])
            try:
                write_sync(self, local_sync)
            except OSError as err:
                _print_error("data transferred, but could not log to "\
                             + self.SYNCDIR)

        if not new and not dry_run:
            # --new means we've not fully synchronized yet.
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
        sync = self._get_local_sync(verbose=True)

        for ind, cl in enumerate(commits_with_logs):
            commit, log = cl
            # print log
            if ind:
                print()
            self._print_log(commit, log, sync)
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

        command = [
            "rsync", "-aun",
            # allow incremental recursion until the implementation of
            # https://github.com/WayneD/rsync/issues/380
            # "--no-inc-recursive",
            "--delete", "-i",
            "--no-group", "--no-owner",
            "--exclude=/.ys"
        ]

        filter_command = self._get_filter(include_commits=False)
        command += filter_command

        # outbuf option added in Rsync 3.1.0 (28 Sep 2013)
        # https://download.samba.org/pub/rsync/NEWS#ENHANCEMENTS-3.1.0
        # from https://stackoverflow.com/a/35775429
        command.append('--outbuf=L')

        root_path = self.root_dir + "/"
        command += ["--link-dest="+ref_commit_dir, root_path, ref_commit_dir]

        if not check_changed:
            self._print_command(command, level=3)

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
                # todo efficiency: check print levels beforehand,
                # not for each line (as done with _print)
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

        sync = self._get_local_sync(verbose=not check_changed)

        if sync and not check_changed:
            # if we only check for changes (to push or pull),
            # we are not interested in the commit synchronization status
            commits = list(self._get_local_commits())
            last_commit = self._get_last_commit(commits)
            if last_commit in sync.by_repos.values():
                last_repos = ", ".join(sync[last_commit])
                self._print("\nCommits are up to date with {}."\
                            .format(last_repos))
            else:
                # last synchronized commit is present locally,
                # if it is present in sync/ .
                synced_commits = sync.by_repos.values()
                # todo: fix tests or think over this possibility
                # more thoroughly
                if synced_commits:
                    last_synced_commit = max(synced_commits)
                    n_newer_commits = sum([1 for comm in commits
                                           if comm > last_synced_commit])
                    last_repos = ", ".join(sync[last_synced_commit])
                    # here we print a hash
                    # to distinguish this line from others
                    self._print("# local repository is {} commits ahead of {}"\
                                .format(n_newer_commits, last_repos))

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
