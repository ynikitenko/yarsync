# -*- coding: utf-8 -*-
import subprocess
import os
import pytest
import sys
import time

from yarsync import YARsync

from settings import TEST_DIR_EMPTY, YSDIR


def test_commit(mocker):
    """Test commit creation and logging."""
    os.chdir(TEST_DIR_EMPTY)

    # important that it goes before patches, we need normal initialization
    commit_msg = "initial commit"
    args = ["yarsync", "commit", "-m", commit_msg]
    ys = YARsync(args)

    # time.localtime uses time.time
    time_3 = time.localtime(3)
    def loctime(sec=None):
        return time_3
    mocker.patch("time.localtime", loctime)
    # hope this will work in another time zone.
    mocker.patch("time.tzname", "MSK")
    # time.time is called a slight instant after time.localtime
    # their order is not important though.
    commit_time = 2
    mocker.patch("time.time", lambda: commit_time)
    rename = mocker.patch("os.rename")
    mkdir = mocker.patch("os.mkdir")
    mocker.patch("socket.gethostname", lambda: "host")
    mocker.patch("getpass.getuser", lambda: "user")

    m = mocker.mock_open()
    if sys.version[0] == "2":
        mocker.patch("__builtin__.open", m)
    else:
        mocker.patch("builtins.open", m)

    popen = mocker.patch("subprocess.Popen")
    subprocess_mock = mocker.Mock()
    attrs = {'communicate.return_value': ('output', 'error')}
    subprocess_mock.configure_mock(**attrs)
    subprocess_mock.configure_mock(**{"returncode": 0})
    popen.return_value = subprocess_mock

    commit_name = str(int(commit_time))
    commit_dir = os.path.join(ys.COMMITDIR, commit_name)
    commit_dir_tmp = commit_dir + "_tmp"
    commit_log_path = os.path.join(ys.LOGDIR, commit_name + ".txt")
    commit_time_str = time.strftime(ys.DATEFMT, time.localtime())

    # call _commit
    res = ys()
    filter_ = ys._get_filter(include_commits=False)[0]
    call = mocker.call

    assert res == 0
    assert mkdir.mock_calls == [
        call(ys.COMMITDIR, ys.DIRMODE),
        call(ys.LOGDIR, ys.DIRMODE),
    ]
    assert rename.mock_calls == [
        call(commit_dir_tmp, commit_dir),
    ]
    assert popen.mock_calls == [
        call(["rsync", "-a", "--link-dest=../../..", "--exclude=/.ys"]
             + filter_ +
             [ys.root_dir + '/', os.path.join(ys.COMMITDIR, "2_tmp")],
             stdout=-1, stderr=-1),
        call().communicate(),
    ]
    assert m.mock_calls == [
        call(commit_log_path, "w"), call().__enter__(),
        call().write(commit_msg + "\n\n"
                     "When: Thu, 01 Jan 1970 03:00:03 MSK\n"
                     "Where: user@host"),
        call().write('\n'),
        call().__exit__(None, None, None),
    ]


def test_commit_rsync_error(mocker):
    os.chdir(TEST_DIR_EMPTY)

    popen = mocker.patch("subprocess.Popen")
    subprocess_mock = mocker.Mock()
    attrs = {'communicate.return_value': ('output', 'error')}
    subprocess_mock.configure_mock(**attrs)
    # some error occurred in rsync
    subprocess_mock.configure_mock(returncode=1)
    popen.return_value = subprocess_mock

    # just in case. Now it won't be called, but to make code more stable.
    mocker.patch("os.mkdir")

    args = ["yarsync", "commit"]
    ys = YARsync(args)
    res = ys()

    assert res == 1


def test_existent_commit_exception(mocker):
    os.chdir(TEST_DIR_EMPTY)
    mocker.patch("time.time", lambda: 2)

    def _os_path_exists(filepath):
        if YSDIR in filepath:
            return True
        return False

    mocker.patch("os.path.exists", _os_path_exists)

    args = "yarsync commit".split()
    ys = YARsync(args)

    with pytest.raises(RuntimeError) as err:
        res = ys()
    # can't compare them directly
    assert repr(err.value) == repr(RuntimeError(
        "commit {} exists".format(os.path.join(ys.COMMITDIR, "2"))
    ))


def test_existent_tmp_commit_exception(mocker):
    os.chdir(TEST_DIR_EMPTY)
    mocker.patch("time.time", lambda: 2)

    def _os_path_exists(filepath):
        if YSDIR in filepath:
            # print("path = ", filepath)
            return "_tmp" in filepath
        return False

    # initialization is fine, because the config file is present
    args = "yarsync commit".split()
    ys = YARsync(args)

    mocker.patch("os.path.exists", _os_path_exists)
    mocker.patch("os.mkdir")

    with pytest.raises(RuntimeError) as err:
        res = ys()
    assert repr(err.value) == repr(RuntimeError(
        "temporary commit {} exists".format(os.path.join(ys.COMMITDIR, "2_tmp"))
    ))
