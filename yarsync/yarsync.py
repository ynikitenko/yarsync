# Yet Another Rsync

import argparse
import collections
import configparser
import datetime
# for user name
import getpass
import io
import json
import os
import re
# for host name
# import platform
import socket
import subprocess
import sys
import time


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
    # not a class method, because it can be run
    # when YARsync was not fully initialised yet.
    # Will not work in Python 2 (if I ever use that here).
    print("!", msg, file=sys.stderr)


# copied from https://github.com/DiffSK/configobj/issues/144#issuecomment-347019778
# with some modifications.
# Another, and maybe a better option, would be
# config = ConfigParser(os.environ)
# config.read('config.ini')
# where it's probably not necessary to add all the ENV to the config,
# but only those variables that occur in the config file.
def _substitute_env(content):
    """Reads filename, substitutes environment variables and returns a file-like
     object of the result.

    Substitution maps text like "$FOO" for the environment variable "FOO".
    """

    def lookup(match):
        """Replaces a match like $FOO with the env var FOO.
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
            description="synchronize directories"
        )
        subparsers = parser.add_subparsers(
            title="Available commands",
            dest="command_name",
            # description="valid commands",
            help="type 'yarsync <command> --help' for additional help",
            # or will print a list of commands in curly braces.
            metavar="command",
        )

        ###################################
        ## Initialize optional arguments ##
        ###################################
        # or ys_dir
        parser.add_argument("--config-dir", default="",
                            help="path to the configuration directory")
        parser.add_argument("--root-dir", default="",
                            help="path to the root of the working directory")

        parser.add_argument("-D", "--destname",
                            help="destination name used for logging")
        ## host = target = destination name,
        ## or source name during yarsync init.
        ## -H, because -h corresponds to --help
        # the algorithm is different depending on
        # whether it's a remote or a local repository.

        parser.add_argument(
            "-n", "--dry-run", action="store_true",
            default=False,
            help="print what would be transferred during a real run, "
                 "but do not make any changes"
        )
        # I think this should work with push, pull, and anything involving rsync
        # (but not init or log or status? Or maybe give a hint what's going on?)
        # Oh no, -n with log is number of commits.

        parser.add_argument("-q", "--quiet",
                            action="count",
                            default=0,
                            help="decrease verbosity")

        ############################
        ## Initialize subcommands ##
        ############################
        # or sub-commands

        # checkout #
        parser_checkout = subparsers.add_parser(
            "checkout",
            help="check out a commit"
            # help="restore the working directory to a local commit"
        )
        parser_checkout.add_argument(
            "-n", "--dry-run", action="store_true",
            default=False,
            help="print what will be transferred during a real checkout, "
                 "but don't make any changes"
        )
        parser_checkout.add_argument("commit", help="commit name")
        parser_checkout.set_defaults(func=self._checkout)

        # commit #
        parser_commit = subparsers.add_parser(
            "commit", help="commit the working directory"
        )
        parser_commit.add_argument("-m", "--message", default="",
                                   help="commit message")
        parser_commit.set_defaults(func=self._commit)

        # diff #
        parser_status = subparsers.add_parser(
            "diff", help="print the difference between two commits"
        )
        parser_status.add_argument("commit", help="commit name")
        parser_status.add_argument("other_commit", nargs="?", default=None,
                                   help="other commit name")
        parser_status.set_defaults(func=self._diff)

        # init #
        parser_init = subparsers.add_parser("init",
                                            help="initialise a repository")
        parser_init.add_argument("reponame", nargs="?",
                                 help="name of the local initialised repository")
        parser_init.set_defaults(func=self._init)

        # log #
        parser_log = subparsers.add_parser(
            "log", help="print commit logs"
        )
        parser_log.add_argument(
            "-n", "--max-count", metavar="<number>", type=int,
            default=-1,
            help="maximum number of logs shown"
        )
        parser_log.add_argument("-r", "--reverse", action="store_true",
                                help="reverse the order of the output")
        parser_log.set_defaults(func=self._log)

        # pull #
        parser_pull = subparsers.add_parser(
            "pull", help="fetch data from the source"
        )
        parser_pull.add_argument(
            "--new", action="store_true",
            help="do not remove files here that are missing on source"
        )
        parser_pull.add_argument("source", nargs="?",
                                 help="source name or path")
        parser_pull.add_argument(
            "-n", "--dry-run", action="store_true",
            default=False,
            help="print what would be transferred during a real run, "
                 "but do not make any change"
        )
        parser_pull.set_defaults(func=self._pull_push)

        # push #
        parser_push = subparsers.add_parser(
            "push", help="send data to the destination"
        )
        parser_push.add_argument(
            "-f", "--force", action="store_true",
            help="remove commits and logs missing on source"
        )
        parser_push.add_argument(
            "-n", "--dry-run", action="store_true",
            default=False,
            help="print what would be transferred during a real run, "
                 "but do not make any change"
        )
        # we don't allow pushing new files to remote,
        # because that could cause its inconsistent state
        # (while locally we merge new files manually)
        # parser_push.add_argument(
        #     "--new", action="store_true",
        #     help="don't remove files missing here on the destination"
        # )
        parser_push.add_argument("destination", nargs="?",
                                 help="destination name or path")
        parser_push.set_defaults(func=self._pull_push)

        # remote #
        parser_remote = subparsers.add_parser(
            "remote", help="manage remote repositories"
        )
        parser_remote.add_argument(
            "-v", "--verbose",
            action="store_true",
            # action="count",
            help="be verbose"
        )
        subparsers_remote = parser_remote.add_subparsers(
            title="remote commands",
            dest="remote_command",
            help="type 'yarsync remote <command> --help' for additional help",
            metavar="command",
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
            "add", help="add remote"
        )
        parser_remote_add.add_argument(
            "repository", help="repository name",
            # metavar="name"
        )
        parser_remote_add.add_argument(
            "path", help="repository path",
            # metavar=("name", "path", "options")
        )
        parser_remote_add.add_argument(
            "options", nargs='*', help="repository options",
            # metavar=("name", "path", "options")
        )
        ## remote rm
        parser_remote_rm = subparsers_remote.add_parser(
            "rm", help="remove remote"
        )
        parser_remote_rm.add_argument(
            "repository", help="repository name",
        )

        for remote_subparser in [parser_remote_add, parser_remote_rm]:
            remote_subparser.set_defaults(func=self._remote)

        ## remote show, default
        parser_remote_show = subparsers_remote.add_parser(
            "show", help="print remote"
            # "show", parents=[remote_parent_parser]
        )
        parser_remote_show.set_defaults(func=self._remote_show)

        # show #
        parser_show = subparsers.add_parser(
            "show", help="print log messages and actual changes for commit(s)"
        )
        parser_show.add_argument("commit", nargs="+",
                                   help="commit name")
        parser_show.set_defaults(func=self._show)

        # status #
        parser_status = subparsers.add_parser(
            "status", help="print updates since last commit"
        )
        parser_status.set_defaults(func=self._status)

        # other useful commands (to be implemented):
        # clone? So that 1) can be bidirectional, to and from (unlike for git)
        #                2) know about hardlinks
        #                3) know target name
        # log <commit_number>

        if len(argv) > 1:  # 0th argument is always present
            args = parser.parse_args(argv[1:])
        else:
            # default is print help.
            # Will raise SystemExit(0).
            args = parser.parse_args(["--help"])

        ########################
        ## Init configuration ##
        ########################

        # basename, because ipython may print full path
        self.NAME = os.path.basename(argv[0])  # "yarsync"
        # this file contains repository name
        self.REPOFILENAME = "repository.txt"
        # directory with commits and other metadata
        # (may be updated by command line arguments)
        CONFIGDIRNAME = ".ys"

        root_dir = os.path.expanduser(args.root_dir)
        config_dir = os.path.expanduser(args.config_dir)
        if not root_dir and not config_dir:
            if args.command_name == "init":
                root_dir = "."
                config_dir = CONFIGDIRNAME
            else:
                # search the current directory and its parents
                try:
                    root_dir = _get_root_directory(CONFIGDIRNAME)
                except OSError as err:
                    # config dir not found.
                    _print_error(
                        "fatal: no {} configuration directory {} found".
                        format(self.NAME, CONFIGDIRNAME)
                    )
                    raise err
                config_dir = os.path.join(root_dir, CONFIGDIRNAME)
        else:
            # at least one of them is provided.
            # check that they are both provided
            if not root_dir or not config_dir:
                parser.error(
                    "both --config-dir and --root-dir must be provided"
                )
        self.root_dir = root_dir
        self.config_dir = config_dir

        # directory creation mode can be set from:
        # - command line argument
        # - global configuration
        # - mode of the sync-ed directory (may be best).
        self.DIRMODE = 0o755

        # CONFIG = "config.ini"
        self.CONFIGFILE = os.path.join(self.config_dir, "config.ini")
        self.HEADFILE = os.path.join(self.config_dir, "HEAD.txt")
        self.COMMITDIR = os.path.join(self.config_dir, "commits")
        self.DATEFMT = "%a, %d %b %Y %H:%M:%S %Z"
        self.LOGDIR = os.path.join(self.config_dir, "logs")
        self.MERGEFILENAME = os.path.join(self.config_dir, "MERGE.txt")
        # REMOTESDIR = os.path.join(self.config_dir, "remotes")
        self.RSYNCFILTER = os.path.join(self.config_dir, "rsync-filter")
        # this could be a useful configuration, for example
        # when mounting a local repo and making a commit.
        self.REPOFILE = os.path.join(self.config_dir, self.REPOFILENAME)
        # stores last synchronized commit
        self.SYNCFILENAME = os.path.join(self.config_dir, "sync.txt")

        ## Check for CONFIGFILE
        if (args.command_name in ['pull', 'push']
            or (args.command_name == "remote"
                and args.remote_command != "add")
        ):
        # 'checkout', 'diff', 'init', 'log', 'show', 'status'
        # work fine without config.
            if not os.path.exists(self.CONFIGFILE):
                _print_error(
                    "fatal: no {} configuration {} found".
                    format(self.NAME, self.CONFIGFILE)
                )
                raise OSError(
                    "{} not found".format(self.CONFIGFILE)
                )
            self._read_config()
            # now there are self._config and self._configdict

        ####################################
        ## Initialize optional parameters ##
        ####################################

        #########################
        ## Initialize commands ##
        #########################

        # there is no easy way to set a default command
        # for a subparser, https://stackoverflow.com/a/46964652/952234
        if args.command_name == "remote" and args.remote_command is None:
            self._func = self._remote_show
        else:
            self._func = args.func

        if args.command_name == "pull":
            args._remote = args.source
        elif args.command_name == "push":
            args._remote = args.destination

        self.print_level = 2 - args.quiet

        self._args = args

    def _checkout(self, commit=None):
        """Checkout a commit.

        Warning: all changes in the working directory will be overwritten!
        """
        # todo: do we allow a default (most recent) commit?
        # also think about ^, ^^, etc.
        # However, see no real usage for them.
        if commit is None:
            commit = int(self._args.commit)
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

        sp = subprocess.Popen(command, stdout=subprocess.PIPE)

        # todo: stderr?
        # todo: verbose/quiet flags?
        for line in iter(sp.stdout.readline, b''):
            print(line.decode("utf-8"), end='')

        returncode = sp.returncode

        if commit == self._get_last_commit():
            # remove HEADFILE
            self._update_head()
        else:
            # write HEADFILE
            with open(self.HEADFILE, "w") as head_file:
                print(commit, file=head_file)

    def _commit(self):
        """Commit the working directory and create a log."""
        # commit directory name is based on UNIX time
        # date = datetime.date.today()
        # date_str = "{}{:#02}{:#02}"\
        #            .format(date.year, date.month, date.day)
        # print(date_str)

        short_commit_mess = self._args.message

        # platform.node() just calls socket.gethostname()
        # with an error check
        localhost = socket.gethostname()
        username = getpass.getuser()
        time_str = time.strftime(self.DATEFMT, time.localtime())

        log_str = "When: {date}\nWhere: {user}@{host}".format(
            date=time_str, user=username, host=localhost
        )
        if short_commit_mess:
            short_commit_mess += "\n\n"

        if os.path.exists(self.MERGEFILENAME):
            # copied from _status
            with open(self.MERGEFILENAME, "r") as fil:
                merge_str = fil.readlines()[0].strip()
            merges = merge_str.split(',')
            short_commit_mess += "Merge {} and {} (common commit {})\n"\
                                 .format(*merges)

        short_commit_mess += log_str

        if not os.path.exists(self.COMMITDIR):
            os.mkdir(self.COMMITDIR, self.DIRMODE)

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
        # self._print("command =", command, debug=True)
        completed_process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        # The data read is buffered in memory,
        # so do not use this method
        # if the data size is large or unlimited.
        # https://docs.python.org/2/library/subprocess.html?highlight=subprocess#subprocess.Popen.communicate
        stdoutdata, stderrdata = completed_process.communicate()
        returncode = completed_process.returncode
        if returncode:
            _print_error("an error occurred during hard linking, "
                         "rsync returned {}".format(returncode))
            return returncode

        # commit is done
        self._print_command("mv {} {}".format(commit_dir_tmp, commit_dir))
        os.rename(commit_dir_tmp, commit_dir)

        ## log ##
        if not os.path.exists(self.LOGDIR):
            self._print_command("mkdir {}".format(self.LOGDIR))
            os.mkdir(self.LOGDIR, self.DIRMODE)

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
            os.remove(self.MERGEFILENAME)
        except FileNotFoundError:
            pass

        # if we were not at HEAD, move that now
        self._update_head()

        return 0

    def _diff(self, commit1=None, commit2=None, /, verbose=True):
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
            print_command(*command)

        # todo: what about stderr?
        # todo: verbose/quiet flags
        sp = subprocess.Popen(command, stdout=subprocess.PIPE)
        for line in iter(sp.stdout.readline, b''):
            print(line.decode("utf-8"), end='')

        # returncode = sp.returncode

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

    def _get_last_sync(self):
        try:
            with open(self.SYNCFILENAME) as fil:
                data = fil.readlines()[0].strip()  # remove trailing newline
                commit, repo = data.split(sep=",", maxsplit=1)
        except OSError:
            # this is not an error
            self._print("No syncronization information found.")
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
        return map(int, filter(_is_commit, commit_candidates))

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
            include_command_str = " ".join(["--include={}".format(inc) for inc in includes])
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

    def _get_dest_path(self, dest=None):
        """Return a pair *(host, destpath)*, where
        *host* is a real host (its ip/name/etc.) at the destination
        and *destpath* is a path on that host.

        If *host* is not present in the configuration,
        it is set to localhost.
        If destination path is missing, `KeyError` is raised.
        """
        config = self._configdict
        if not dest:
            try:
                dest = config["default"]["name"]
            except KeyError:
                raise KeyError(
                    'no default destination found in config. '
                    'Add subsection "default" with name=<default subsection>'
                )
            # This doesn't give the first section, helas.
            # defaultsect = list(configdict.items())[0]
            # dest = defaultsect[0]

        try:
            destpath = config[dest]["path"]
        except KeyError:
            raise KeyError("destination path must be present "
                           "in the configuration") from None
        try:
            host = config[dest]["host"]
        except KeyError:
            # localhost
            host = ""

        # destpath = "{}:{}".format(dest, configdict[remote]["path"])
        if not destpath.endswith('/'):
            destpath += '/'
        return (host, destpath)

    def _get_remote_commits(self, commit_dir):
        """Return remote commits as a list of integers."""
        command = ["rsync", "--list-only", commit_dir]

        self._print_command(" ".join(command))
        sp = subprocess.Popen(command, stdout=subprocess.PIPE)

        returncode = sp.returncode
        if returncode:
            raise OSError(
                "error during listing of remote commits: rsync returned {}"\
                .format(returncode)
            )

        commits = []
        for line in iter(sp.stdout.readline, b''):
            comm = line.split()[-1]
            if comm not in [b'.', b'..']:
                if not _is_commit(comm):
                    raise OSError(
                        "not a commit found on remote: {}".format(comm)
                    )
                commits.append(int(comm))

        return commits

    def _init(self):
        """Initialize default configuration.

        Create configuration folder, configuration and repository files.

        If a configuration file already exists, it is not changed.
        This operation is safe and idempotent (can be repeated safely).
        """
        ysdir = self.config_dir
        repofile = self.REPOFILE

        # reponame will be written to repofile and used in logs.
        reponame = self._args.reponame
        reponame_from_args = True
        if reponame is None:
            reponame = socket.gethostname()
            reponame_from_args = False
        if not reponame:
            _print_error(
                "provide a repository name (for logging)"
            )
            return 7

        if reponame_from_args:
            self._print("Initialise configuration for {}".format(reponame), level=2)
        else:
            self._print("Initialise configuration", level=2)

        # create config_dir
        new_config = True
        if not os.path.exists(ysdir):
            self._print_command("mkdir -m {:o} {}".format(self.DIRMODE, ysdir))
            # can raise "! [Errno 13] Permission denied: '.ys'"
            os.mkdir(ysdir, self.DIRMODE)
        else:
            self._print("{} already exists, skip".format(ysdir), level=2)
            new_config = False

        # create self.CONFIGFILE
        # todo: create example configuration file.
        if not os.path.exists(self.CONFIGFILE):
            self._print("# create configuration file {}".format(self.CONFIGFILE))
            with open(self.CONFIGFILE, "w") as fil:
                print("", end="", file=fil)
            new_config = True
        else:
            self._print("{} already exists, skip".format(self.CONFIGFILE),
                        level=2)

        # create self.REPOFILE
        if not os.path.exists(repofile):
            if not reponame_from_args:
                self._print(
                    "# Repository name '{}' set from host name"\
                    .format(reponame)
                )
            self._print("# create configuration file {}".format(repofile))
            with open(repofile, "w") as fil:
                print(reponame, end="", file=fil)
            new_config = True
        else:
            self._print("{} already exists, skip".format(repofile), level=2)

        ysdir_fp = os.path.realpath(ysdir)
        if new_config:
            self._print("\nInitialised yarsync configuration in {} "
                        .format(ysdir_fp))
        else:
            self._print("\nConfiguration in {} already initialised."
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

        synced_commit, remote = self._get_last_sync()
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

    def _print_command(self, comm):
        """Print called commands."""
        # A separate function
        # to semantically distinguish that from _print in code.
        # However, _print is used internally - to handle output levels.
        self._print(comm)

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

    def _pull_push(self):
        """Push/pull commits to/from destination or source.

        Several checks are made to prevent corruption:
            - source has no uncommitted changes,
            - source has not a detached HEAD,
            - source is not in a merging state,
            - destination has no commits missing on source.

        Note that the destination might have uncommitted changes:
        check that with *-n* (*--dry-run*) first!
        """

        if self._get_head_commit() is not None:
            # it could be safe to push a repo with a detached HEAD,
            # but that would be messy.
            # OSError is for exceptions
            # that can occur outside the Python system
            raise OSError("local repository has detached HEAD.\n"
                          "*checkout* the most recent commit first.")
        if os.path.exists(self.MERGEFILENAME):
            raise OSError(
                "local repository has unmerged changes.\n"
                "Manually update the working directory and *commit*."
            )

        returncode, changed = self._status(check_changed=True)
        if changed:
            raise OSError("local repository has uncommitted changes")
        if returncode:
            raise OSError("could not check for uncommitted changes, "
                          "rsync returned {}\n".format(returncode) +
                          "run *status* manually to check the error")

        remote = self._args._remote

        try:
            host, destpath = self._get_dest_path(remote)
        except KeyError as err:
            raise err from None
        full_destpath = _mkhostpath(host, destpath)

        # --link-dest is not needed, since if a file is new,
        # it won't be in remote commits.
        # -H preserves hard links in one set of files (but see the note in todo.txt)
        command = ["rsync", "-avHP"]

        dry_run = self._args.dry_run
        if dry_run:
            command += ["-n"]
        command_str = " ".join(command)

        # --new can only be called with pull
        # --force can only be called with push,
        #   because we check working tree and other local issues
        if self._args.command_name == "pull":
            new = self._args.new
            force = False
        else:
            force = self._args.force
            new = False

        if not new:
            command.append("--delete-after")
            command_str += " --delete-after"

        # if there exists .ys/rsync-filter, command string needs quotes
        filter_, filter_str = self._get_filter()
        command.extend(filter_)
        command_str += " " + filter_str

        root_path = self.root_dir + "/"
        if self._args.command_name == "push":
            command.append(root_path)
            command.append(full_destpath)
            command_str += " {} {}".format(root_path, full_destpath)
        else:
            # pull
            command.append(full_destpath)
            command.append(root_path)
            command_str += " {} {}".format(full_destpath, root_path)

        # self._print("#", command, debug=True)
        self._print_command(command_str)

        # old local commits (before possible pull)
        local_commits = list(self._get_local_commits())

        # if there are no remote commits (a new repository),
        # push will still work
        remote_commits_dir = os.path.join(full_destpath, ".ys", "commits/")
        remote_commits = self._get_remote_commits(remote_commits_dir)

        if not force:
            # todo: do we need all missing commits?
            # We should look at only the most recent commits.
            if self._args.command_name == "push":
                missing_commits = self._test_missing_commits(
                    remote_commits_dir, self.COMMITDIR + '/'
                )
            else:
                missing_commits = self._test_missing_commits(
                    self.COMMITDIR + '/', remote_commits_dir
                )

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

        completed_process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        stdoutdata, stderrdata = completed_process.communicate()
        returncode = completed_process.returncode
        if returncode:
            # todo: error message?
            _print_error(
                "an error occurred, rsync returned {}".format(returncode)
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
                        with open(self.MERGEFILENAME, "w") as fil:
                            print(merge_str, end="", file=fil)
                    except OSError:
                        _print_error(
                            "could not create a merge file {}, "\
                            .format(self.MERGEFILENAME) +
                            "create that manually with " + merge_str
                        )
                        raise OSError from None
                self._print(
                    "merge {} and {} manually and commit "
                    "(most recent common commit is {})".\
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
                with open(self.SYNCFILENAME, "w") as fil:
                    print(sync_str, end="", file=fil)
            except OSError:
                _print_error("data transferred, but could not log to {}"
                             .format(self.SYNCFILENAME))

            # either HEAD was correct ("not detached") (for push)
            # or it was updated (by pull)
            self._update_head()

        return 0

    def _read_config(self):

        # substitute environmental variables (those that are available)
        # todo: what if an envvar is not present for the current section?
        with open(self.CONFIGFILE, "r") as conf_file:
            subst_lines = _substitute_env(conf_file.read()).getvalue()

        config = configparser.ConfigParser()
        # ConfigParser.read_string
        # is undocumented in Python2, but present!
        config.read_string(subst_lines)

        configdict = {}
        for section in config.sections():
            sectiond = dict(config[section])
            configdict[section] = sectiond
            if section == "default":
                continue

            try:
                # all local repositories must have an entry "host"
                # (can be empty or localhost, or equivalent)
                host = sectiond["host"]
            except KeyError:
                # sections for remotes can be named after their hosts
                host = ""  # section
            destpath = sectiond["path"]
            sectiond["destpath"] = _mkhostpath(host, destpath)

        # print all values:
        # configdict = self._configdict
        # formatter = lambda s: json.dumps(s, sort_keys=True, indent=4)
        # print(formatter(configdict))

        # config.items() includes the DEFAULT section, which can't be removed.
        self._config = config
        self._configdict = configdict

    def _remote(self):
        """Manage remotes."""
        # Since self._func() is called without arguments,
        # this is the place for all remote-related operations.
        if self._args.remote_command == "add":
            repository = self._args.repository
            path = self._args.path
            options = self._args.options
            return self._remote_add(repository, path, options)
        elif self._args.remote_command == "rm":
            return self._remote_rm(self._args.repository)

    def _remote_add(self, remote, path, options=""):
        """Add a remote and its path to the config file."""
        # from https://docs.python.org/2.7/library/configparser.html#examples
        config = configparser.RawConfigParser()
        config.read(self.CONFIGFILE)
        try:
            config.add_section(remote)
        except configparser.DuplicateSectionError:
            _print_error(
                "remote {} exists, break.\n  Remove {} "
                "or choose a new remote name.".format(remote, remote)
            )
            return 7
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
            return 7
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
        synced_commit, remote = self._get_last_sync()

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
        than last commit.

        If no yarsync configuration is found, an error is printed
        and 7 returned.

        Return exit code of `rsync`.
        If *check_changed* is `True`,
        return a tuple *(returncode, changed)*,
        where *changed* is `True`
        if the working directory has changes since last commit.
        """
        # We don't return an error if the directory has changed,
        # because it is a normal situation (not an error).
        # This is the same as in git.

        if os.path.exists(self.COMMITDIR):
            commit_subdirs = [fil for fil in os.listdir(self.COMMITDIR)
                              if _is_commit(fil)]
        else:
            commit_subdirs = []

        ## no commits is fine for an initial commit
        if not commit_subdirs:
            self._print("No commits found")
            if check_changed:
                return (0, True)
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

        self._print(command_str, level=2)

        sp = subprocess.Popen(command, stdout=subprocess.PIPE)
        # changed means there were actual changes in the working dir
        changed = False
        # note that directories may appear to be changed
        # just because of timestamps (add and remove a file), e.g.
        # b'.d..t...... ./\n'
        # b'' means EOF in the iteration.
        lines = iter(sp.stdout.readline, b'')
        for line in lines:
            if line:
                self._print("Changed since head commit:")
                # skip permissions
                if not line.startswith(b'.'):
                # if not line.startswith(b'.d..t......'):
                    # todo: shall we return here if only check_changed?
                    changed = True

                # print the line and all following lines.
                # todo: use terminal encoding
                print(line.decode("utf-8"), end='')
                # in fact, readline could be used twice.
                for line in lines:
                    if not line.startswith(b'.'):
                        changed = True
                    print(line.decode("utf-8"), end='')

        sp.wait()  # otherwise returncode might be None
        # None is fine for sys.exit() though,
        # because it will be converted to 0.
        # For testing, it is better to have it 0 here.
        returncode = sp.returncode

        if head_commit is not None:
            self._print("\nDetached HEAD (see '{} log' for more recent commits)"
                        .format(self.NAME))

        if os.path.exists(self.MERGEFILENAME):
            with open(self.MERGEFILENAME, "r") as fil:
                merge_str = fil.readlines()[0].strip()
            merges = merge_str.split(',')
            self._print("Merging {} and {} (most recent common commit {})."\
                        .format(*merges))

        if not changed:
            self._print("Nothing to commit, working directory clean.")

        synced_commit, repo = self._get_last_sync()

        if synced_commit is not None and repo is not None:
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
            return (returncode, changed)
        # called as the main command
        return returncode

    def _test_missing_commits(self, from_path, to_path):
        """Return a list of commits (directories) present on *from_path*
        and missing on *to_path*.
        """
        # "-r" means recursive
        # "-r --exclude='/*/*'" means
        # to list a single directory without recursion.
        # If a pattern ends with a '/',
        # then it will only match a directory
        command = "rsync -nr --info=NAME --include=/ --exclude=/*/*".split() \
                  + [from_path, to_path]
        # self._print(" ".join(command), debug=True)
        completed_process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        stdoutdata, stderrdata = completed_process.communicate()
        returncode = completed_process.returncode
        raw_names = stdoutdata.split()
        # commit folder can have files from the user
        # (maybe it should not be allowed: are they transferred at all?..)
        dirs = (os.path.dirname(str(dir_, 'utf-8')) for dir_ in raw_names)
        missing_commits = [int(os.path.basename(dir_)) for dir_ in dirs if dir_]
        return missing_commits

    def _update_head(self):
        try:
            # no HEADFILE means HEAD is the most recent commit
            os.remove(self.HEADFILE)
        except FileNotFoundError:
            pass

    def __call__(self):
        """Call the command set during the initialization.

        Return values:
        8 - not a yarsync directory or an OS error
        """
        # 7 is returned in case of bad argparse
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
