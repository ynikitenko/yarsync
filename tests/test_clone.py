import os
import stat

import pytest

from yarsync import YARsync
from yarsync.yarsync import _is_commit, _substitute_env
from yarsync.yarsync import (
    CONFIG_EXAMPLE, YSConfigurationError, YSCommandError
)

from .settings import TEST_DIR, TEST_DIR_FILTER


@pytest.mark.parametrize(
    "clone_command",
    [
        ["yarsync", "-v", "clone", TEST_DIR + os.path.sep],
        ["yarsync", "clone", TEST_DIR_FILTER + os.path.sep]
    ]
)
def test_clone(tmpdir, clone_command):
    clone_command.append(str(tmpdir))
    ys = YARsync(clone_command)
    returncode = ys()
    assert not returncode

    # todo: capture output
    # if "-v" in clone_command: ...

    test_dir = clone_command[-1]

    # all files were transferred
    # we compare sets, because the ordering would be different
    new_files = set(os.listdir(tmpdir))
    assert new_files.issubset(set(os.listdir(TEST_DIR)))
    # they are not equal, because rsync-filter excludes 'b'
    assert 'a' in new_files


def test_clone_2(tmpdir, capfd, test_dir_ys_bad_permissions):
    # additional checks
    clone_command = ["yarsync", "clone"]

    # not a yarsync repository can't be cloned
    src1 = "." +  os.path.sep
    dest1 = str(tmpdir)
    ys1 = YARsync(clone_command + [src1, dest1])
    with pytest.raises(OSError):
        ys1._clone(src1, dest1)

    captured = capfd.readouterr()
    assert 'rsync: [sender] change_dir ' in captured.err
    assert 'failed: No such file or directory' in captured.err

    # todo: no idea how to efficiently test remotes
    # (probably some environmental variables?)

    src2 = test_dir_ys_bad_permissions + os.path.sep
    ys2 = YARsync(clone_command + [src2, dest1])
    rsync_return = 23
    assert ys2._clone(src2, dest1) == rsync_return
    captured = capfd.readouterr()
    assert "rsync: [sender] opendir " in captured.err
    assert 'forbidden" failed: Permission denied' in captured.err
    # print("ERR:", captured.err)
    # print("OUT:", captured.out)
    assert captured.err.endswith(
        "an error occurred, rsync returned {}. Exit\n".format(rsync_return)
    )

    # manually fix that, otherwise pytest complains about garbage,
    # see https://github.com/pytest-dev/pytest/issues/7821
    bad_dir = os.path.join(dest1, "forbidden")
    os.chmod(bad_dir, stat.S_IWRITE)
