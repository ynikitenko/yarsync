import os
import pathlib
import pytest
import subprocess

from yarsync import YARsync
from .settings import (
    TEST_DIR, TEST_DIR_EMPTY, YSDIR, TEST_DIR_YS_BAD_PERMISSIONS
)


# run tests for each combination of arguments
# https://docs.pytest.org/en/latest/how-to/parametrize.html#pytest-mark-parametrize-parametrizing-test-functions
@pytest.mark.parametrize("pull", [True, False])
@pytest.mark.parametrize("dry_run", [True, False])
def test_pull_push_uncommitted(
        capfd, origin_test_dir, test_dir_ys_bad_permissions,
        pull, dry_run,
    ):
    """Pull and push always fail when there are uncommitted changes."""
    os.chdir(test_dir_ys_bad_permissions)
    command = ["yarsync"]
    if pull:
        command.append("pull")
    else:
        command.append("push")
    if dry_run:
        command.append("--dry-run")
    ys = YARsync(command + ["origin"])
    # remote "origin" is added in origin_test_dir.
    returncode = ys()
    # todo: should it be really 8?..
    assert returncode == 8
    captured = capfd.readouterr()
    assert "local repository has uncommitted changes" in captured.err
    assert "Changed since head commit:\n" in captured.out
    # we allow printing changes.
    # assert not captured.out


@pytest.mark.parametrize("backup_dir", [True, False])
def test_backup(tmp_path_factory, backup_dir, test_dir):
    local_path = tmp_path_factory.mktemp("local")
    remote_path = tmp_path_factory.mktemp("remote")
    local = local_path.__str__()
    remote = remote_path.__str__()

    ## clone test_dir -> remote -> local
    # now local has remote as an "origin" remote
    ys_clone = YARsync(["yarsync", "-qq", "clone", test_dir, remote])
    ys_clone()
    ys_clone._clone(remote, local)
    print("created yarsync repositories {} and {}".format(remote, local))

    # corrupt some local files
    local_a = local_path / "a"
    local_a.write_text("b\n")
    local_d = local_path / "c" / "d"
    local_d.write_text("c\n")

    os.chdir(local)
    ys_push = YARsync(["yarsync", "push", "origin"])
    # if you have problems during push because of uncommitted changes,
    # this might be because of hard links broken by git.
    ys_push()
    remote_a = remote_path / "a"
    # no evil was transferred!
    # it won't be transferred after rsync is improved,
    # https://github.com/WayneD/rsync/issues/357
    # assert remote_a.read_text() == "a\n"

    ys_command = ["yarsync", "pull"]
    if backup_dir:
        ys_command.extend(["--backup-dir", "BACKUP"])
    else:
        ys_command.append("--backup")
    ys_command.append("origin")
    ys_pull_backup = YARsync(ys_command)
    ys_pull_backup()

    files = os.listdir()
    # the correctness was transferred back again!
    # destination files are renamed
    # *** fix after https://github.com/WayneD/rsync/issues/357
    # assert local_a.read_text() == "a\n"
    # *** fix
    # if backup_dir:
    #     # there are two nested BACKUP-s: probably an rsync bug...
    #     bd = pathlib.Path(".") / "BACKUP" / "BACKUP"
    #     assert set(files) == set(("a", "b", ".ys", "c", "BACKUP"))
    #     # old corrupt a is saved here
    #     assert (bd / "a").read_text() == "b\n"
    #     # the real hierarchy is backed up
    #     assert (bd / "c" / "d").read_text() == "c\n"
    # else:
    #     assert set(files) == set(("a", "a~", "b", ".ys", "c"))
    #     # and the wrongdoings were preserved as well
    #     assert (local_path / "a~").read_text() == "b\n"
    #     assert (local_path / "c" / "d~").read_text() == "c\n"

    # we can't pull or push in an updated state
    # *** fix
    # assert ys_pull_backup._status(check_changed=True)[1] is True
