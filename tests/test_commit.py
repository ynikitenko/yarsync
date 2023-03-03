import os
import pytest
import subprocess
import sys
import time

from yarsync import YARsync

from .settings import TEST_DIR, TEST_DIR_EMPTY, YSDIR
from .helpers import clone_repo


def test_commit(mocker):
    """Test commit creation and logging."""
    os.chdir(TEST_DIR_EMPTY)

    # important that it goes before patches, need normal initialization
    commit_msg = "initial commit"
    args = ["yarsync", "commit", "-m", commit_msg]
    # we initialize ys here, but don't create a commit.
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
    # adapted from https://stackoverflow.com/a/38618056/952234
    def my_open(filename, mode="r"):
        if mode != "r":
            return m.return_value

        if filename == ys.REPOFILE:
            content = "myhost"
        else:
            raise FileNotFoundError(filename)
        file_object = mocker.mock_open(read_data=content).return_value
        file_object.__iter__.return_value = content.splitlines(True)
        return file_object

    mocker.patch("builtins.open", new=my_open)

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
    filter_ = ys._get_filter(include_commits=False)
    call = mocker.call

    assert res == 0
    assert mkdir.mock_calls == [
        call(ys.COMMITDIR),
        call(ys.LOGDIR),
    ]
    assert rename.mock_calls == [
        call(commit_dir_tmp, commit_dir),
    ]
    assert popen.mock_calls == [
        call(["rsync", "-a", "--link-dest=../../..", "--exclude=/.ys"]
             + filter_ +
             [ys.root_dir + '/', os.path.join(ys.COMMITDIR, "2_tmp")],
             stdout=-3),
        call().communicate(),
    ]

    # this seems patched, but the date on Python 3.6 is still different
    assert time.tzname == "MSK"
    # if sys.version_info.minor <= 6:
    #     # will be UTC
    #     time_str = time.strftime(ys.DATEFMT, time_3)
    # else:
    #     time_str = "Thu, 01 Jan 1970 03:00:03 MSK"
    time_str = time.strftime(ys.DATEFMT, time.localtime(3))

    assert m.mock_calls == [
        # call(ys.REPOFILE),
        # call().__enter__(),
        # call().read(),
        # call().__exit__(None, None, None),
        # call(commit_log_path, "w"),
        call().__enter__(),
        call().write(commit_msg + "\n\n"
                     "When: {}\n".format(time_str) +
                     "Where: user@myhost"),
        call().write('\n'),
        call().__exit__(None, None, None),
    ]


@pytest.mark.parametrize("commit_time", [4, 0])
def test_commit_with_limits(tmpdir, mocker, commit_time):
    """Test commit creation and logging."""
    clone_repo(TEST_DIR, str(tmpdir))

    os.chdir(tmpdir)
    ys = YARsync(["yarsync", "commit", "--limit", "1"])
    # initially there are two commits cloned
    assert set(os.listdir(ys.COMMITDIR)) == set(("1", "2"))

    # copied from test_commit
    # time.localtime uses time.time
    time_new = time.localtime(commit_time)
    def loctime(sec=None):
        return time_new
    # no idea why need two time patches (but see above about Python 3.6)
    mocker.patch("time.localtime", loctime)
    mocker.patch("time.tzname", "MSK")

    # commit_time = 2
    # this patch is needed for Python 3.9
    mocker.patch("time.time", lambda: commit_time)

    commit_name = str(int(commit_time))
    commit_dir = os.path.join(ys.COMMITDIR, commit_name)

    # call _commit with limit
    res = ys()
    assert res == 0
    # older commits were removed
    if commit_time > 2:
        assert os.listdir(ys.COMMITDIR) == [str(commit_time)]
    if commit_time < 1:
        assert os.listdir(ys.COMMITDIR) == ["2"]


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


def test_existing_commit_exception(mocker):
    os.chdir(TEST_DIR_EMPTY)
    mocker.patch("time.time", lambda: 2)

    def _os_path_exists(filepath):
        if YSDIR in filepath and not filepath.endswith("MERGE.txt"):
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


def test_existing_tmp_commit_exception(mocker):
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
