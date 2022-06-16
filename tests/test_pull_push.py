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
