# Mock OS functions and check that they are called properly

import os

from sys import version_info

from yarsync import YARsync
from yarsync.yarsync import CONFIG_EXAMPLE

from .helpers import mock_compare
from .settings import YSDIR


def test_init_mixed(mocker):
    ## Mock existing directory and non-existent files ##
    args = "yarsync init".split()
    ys0 = YARsync(args)
    conffile = ys0.CONFIGFILE
    repofile = ys0.REPOFILE.format("my_repo")

    def _os_path_exists(filepath):
        if filepath == YSDIR:
            return True
        elif filepath == conffile:
            return True
        elif filepath.startswith(YSDIR):
            print(filepath)
            return False
        else:
            return False  # won't get access to real os.path.exists(filepath)

    m = mocker.mock_open()
    mocker.patch("builtins.open", m)
    # the user inputs "my_host"
    mocker.patch("builtins.input", lambda _: "my_repo")
    mocker.patch("os.path.exists", _os_path_exists)
    # otherwise listdir will complain that .ys doesn't exist
    mocker.patch("os.listdir", lambda _: [])

    # call _init
    res = ys0()
    assert res == 0

    call = mocker.call
    # if version_info.minor >= 13, there is also call().close()
    assert mock_compare(
        m.mock_calls,
        [call(repofile, "x")]
    )

    # clear the calls
    m.reset_mock()

    # the user inputs nothing, and hostname is taken
    mocker.patch("builtins.input", lambda _: "")
    mocker.patch("socket.gethostname", lambda: "my_host")
    # don't forget to call the function
    ys1 = YARsync(["yarsync", "init"])
    ys1._init()

    repofile = ys1.REPOFILE.format("my_host")
    # assert call(repofile, "x") in m.mock_calls
    assert mock_compare(
        m.mock_calls,
        [call(repofile, "x")]
    )


def test_init_non_existent(mocker):
    def _os_path_exists(filepath):
        return False

    m = mocker.mock_open()
    mocker.patch("builtins.open", m)
    mocker.patch("os.path.exists", _os_path_exists)
    mkdir = mocker.patch("os.mkdir")
    mocker.patch("os.listdir", lambda _: [])

    args = "yarsync init myhost".split()
    ys = YARsync(args)
    conffile = ys.CONFIGFILE
    repofile = ys.REPOFILE.format("myhost")

    res = ys()
    assert res == 0
    call = mocker.call
    assert mock_compare(mkdir.mock_calls, [call(YSDIR)])
    # assert mkdir.mock_calls == [call(YSDIR, ys.DIRMODE)]

    # if version_info.minor >= 13, also call().close(),
    assert mock_compare(
        m.mock_calls,
        [
            # mkdir is recorded separately
            call(conffile, "w"),
            call().write(CONFIG_EXAMPLE), call().write(''),
            call().close(),
            call(repofile, "x"),
            call().close(),
        ]
    )


def test_init_existent(mocker):
    def _os_path_exists(filepath):
        # assume only files within YSDIR exist,
        # otherwise you'll have problems with gettext
        if os.path.commonprefix([filepath, YSDIR]) == YSDIR:
            return True
        # otherwise os.path.exists(filepath)
        # would cause infinite recursion here
        return False

    args = "yarsync init myhost".split()

    m = mocker.mock_open()
    mocker.patch("builtins.open", m)
    # no input is prompted when we provide repo name in CL args
    input_ = mocker.patch("builtins.input")
    mocker.patch("os.path.exists", _os_path_exists)
    mocker.patch("os.listdir", lambda _: ["repo_myhost.txt"])
    mkdir = mocker.patch("os.mkdir")

    ys = YARsync(args)

    res = ys()
    assert res == 0
    # todo: use mock_compare if these fail in future Python versions
    assert input_.mock_calls == []
    assert mkdir.mock_calls == []
    assert m.mock_calls == []
