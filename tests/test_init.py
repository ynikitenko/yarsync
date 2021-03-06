# -*- coding: utf-8 -*-
import subprocess
import os
import sys

from yarsync import YARsync

# test can be called from the upper directory as well,
# and the relative name is gotten dynamically.
TEST_DIR_EMPTY = os.path.dirname(__file__)
YSDIR = ".ys"


def test_init_mixed(mocker):
    """Mock OS functions and check that they are called properly."""
    # os.chdir(TEST_DIR_EMPTY)

    ## Mock mixed existing directory and non-existent files ###

    def _os_path_exists(filepath):
        if filepath == YSDIR:
            return True
        elif filepath.startswith(YSDIR):
            print(filepath)
            return False
        else:
            return False  # won't get access to real os.path.exists(filepath)

    m = mocker.mock_open()
    if sys.version[0] == "2":
        mocker.patch("__builtin__.open", m)
    else:
        mocker.patch("builtins.open", m)
    mocker.patch("os.path.exists", _os_path_exists)

    args = "yarsync init myhost".split()
    ys = YARsync(args)
    conffile = ys.CONFIGFILE
    repofile = ys.REPOFILE
    # call _init
    res = ys()
    assert res == 0

    call = mocker.call
    assert m.mock_calls == [
        call(conffile, "w"), call().__enter__(),
        call().write(''), call().write(''),
        call().__exit__(None, None, None),
        call(repofile, "w"), call().__enter__(),
        call().write("myhost"),
        call().write(''),  # this write is because of print(end='').
        call().__exit__(None, None, None)
    ]
    old_calls = m.mock_calls[:]
    # don't know how to clear the calls
    # m.mock_calls.clear()
    # so had to split it into 3 functions


def test_init_non_existent(mocker):
    def _os_path_exists(filepath):
        return False

    m = mocker.mock_open()
    if sys.version[0] == "2":
        mocker.patch("__builtin__.open", m)
    else:
        mocker.patch("builtins.open", m)
    mocker.patch("os.path.exists", _os_path_exists)
    mkdir = mocker.patch("os.mkdir")

    args = "yarsync init myhost".split()
    ys = YARsync(args)
    conffile = ys.CONFIGFILE
    repofile = ys.REPOFILE

    res = ys()
    assert res == 0
    call = mocker.call
    assert mkdir.mock_calls == [call(YSDIR, ys.DIRMODE)]
    assert m.mock_calls == [
        # mkdir is recorded separately
        call(conffile, "w"), call().__enter__(),
        call().write(''), call().write(''),
        call().__exit__(None, None, None),
        call(repofile, "w"), call().__enter__(),
        call().write("myhost"),
        call().write(''),  # this write is because of print(end='').
        call().__exit__(None, None, None)
    ]


def test_init_existent(mocker):
    def _os_path_exists(filepath):
        # assume only files within YSDIR exist,
        # otherwise you'll have problems with gettext
        if os.path.commonprefix([filepath, YSDIR]) == YSDIR:
            return True
        # os.path.exists(filepath) would cause infinite recursion here!
        return False

    m = mocker.mock_open()
    if sys.version[0] == "2":
        mocker.patch("__builtin__.open", m)
    else:
        mocker.patch("builtins.open", m)
    mocker.patch("os.path.exists", _os_path_exists)
    mkdir = mocker.patch("os.mkdir")

    args = "yarsync init myhost".split()
    ys = YARsync(args)

    res = ys()
    assert res == 0
    assert mkdir.mock_calls == []
    assert m.mock_calls == []
