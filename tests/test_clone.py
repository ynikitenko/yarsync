import os
import stat

import pytest

from yarsync import YARsync
from yarsync.yarsync import _is_commit, _substitute_env
from yarsync.yarsync import (
    CONFIG_EXAMPLE, YSConfigurationError, YSCommandError, COMMAND_ERROR
)

from .helpers import clone_repo
from .settings import TEST_DIR, TEST_DIR_FILTER


@pytest.mark.parametrize(
    "test_dir_source", (TEST_DIR, TEST_DIR_FILTER)
)
def test_clone(tmp_path_factory, test_dir_source):
    clone_name = "tmp"
    source_dir = tmp_path_factory.mktemp("test")
    clone_dir = tmp_path_factory.mktemp("test")
    repo_name = os.path.basename(source_dir)

    # we copy the repository low-level to get rid of side effects
    # (synchronization, new remote, etc.)
    clone_repo(str(test_dir_source), str(source_dir))
    os.chdir(str(source_dir))
    clone_command = ["yarsync", "clone", clone_name, str(clone_dir)]

    ys = YARsync(clone_command)
    returncode = ys()
    assert not returncode

    # todo: capture output
    # if "-v" in clone_command: ...

    # all files were transferred
    new_repo = os.path.join(clone_dir, repo_name)
    # we compare sets, because the ordering will be different
    new_files = set(os.listdir(new_repo))
    assert new_files.issubset(set(os.listdir(source_dir)))
    # they are not equal, because rsync-filter excludes 'b'
    assert 'a' in new_files


def test_clone_2(tmp_path_factory, capfd, test_dir_ys_bad_permissions):
    # additional checks
    clone_command = ["yarsync", "clone"]
    source1 = tmp_path_factory.mktemp("source")
    dest1 = tmp_path_factory.mktemp("dest")

    ## Can't clone from outside a repository
    os.chdir(dest1)
    ys1 = YARsync(clone_command + ["origin", str(source1)])
    # will be called clone_from, because we are outside.
    return_code = ys1._clone_from("origin", str(source1))

    assert return_code == COMMAND_ERROR
    err = capfd.readouterr().err
    assert 'remote contains no yarsync repository' in err
    assert 'no yarsync repository found at ' in err

    src2 = test_dir_ys_bad_permissions
    dest2 = str(tmp_path_factory.mktemp("dest"))
    os.chdir(src2)
    ys2 = YARsync(clone_command + ["clone", dest2])
    # rsync_return = 23

    # this is COMMAND_ERROR, because there are uncommitted changes
    assert ys2._clone_to("clone", dest2) == COMMAND_ERROR  # rsync_return
    captured = capfd.readouterr()
    assert "local repository has uncommitted changes. Exit." in captured.err
    # print("ERR:", captured.err)
    # print("OUT:", captured.out)

    # # manually fix it, otherwise pytest complains about garbage,
    # # see https://github.com/pytest-dev/pytest/issues/7821
    # bad_dir = os.path.join(dest1, "forbidden")
    # os.chmod(bad_dir, stat.S_IWRITE)
