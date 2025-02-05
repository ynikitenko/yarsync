import pytest

from yarsync.yarsync import YARsync
from yarsync.yarsync import (
    COMMAND_ERROR
)


@pytest.mark.usefixtures("test_dir")
def test_remote_add(capfd):
    remote_command = "yarsync remote add".split()

    # adding existing remote fails
    ys = YARsync(remote_command + ["other_repo", "/some/path/"])
    returncode = ys()
    assert returncode == COMMAND_ERROR
    captured = capfd.readouterr()
    assert "remote other_repo exists, break." in captured.err
    assert not captured.out
