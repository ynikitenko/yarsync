import os
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


def test_backup(tmp_path_factory):
    local_path = tmp_path_factory.mktemp("local")
    remote_path = tmp_path_factory.mktemp("remote")
    local = local_path.__str__()
    remote = remote_path.__str__()

    ## clone test_dir -> remote -> local
    # now local has remote as an "origin" remote
    ys_clone = YARsync(["yarsync", "clone", TEST_DIR, remote])
    ys_clone()
    ys_clone._clone(remote, local)
    print("created yarsync repositories {} and {}".format(remote, local))

    # corrupt a local file
    local_a = local_path / "a"
    local_a.write_text("b\n")

    os.chdir(local)
    ys_push = YARsync(["yarsync", "push", "origin"])
    # if you have problems during push because of uncommitted changes,
    # this might be because of hard links broken by git.
    ys_push()
    remote_a = remote_path / "a"
    # no evil was transferred!
    assert remote_a.read_text() == "a\n"

    ys_pull_backup = YARsync(["yarsync", "pull", "--backup", "origin"])
    ys_pull_backup()
    files = os.listdir()
    assert set(files) == set(("a", "a~", "b", ".ys", "c"))
    # the correctness was transferred back again!
    # destination files are renamed
    assert local_a.read_text() == "a\n"
    # and the wrongdoings were preserved as well
    assert (local_path / "a~").read_text() == "b\n"
