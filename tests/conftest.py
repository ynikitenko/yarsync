import os

import pytest

from .settings import TEST_DIR_READ_ONLY, TEST_DIR_YS_BAD_PERMISSIONS

collect_ignore_glob = ["test_dir_*"]


@pytest.fixture(scope="session")
def test_dir_read_only():
    os.chmod(TEST_DIR_READ_ONLY, 0o544)
    return TEST_DIR_READ_ONLY
    # no need to tear down,
    # since git has no problems with read-only directories


@pytest.fixture(scope="session")
def test_dir_ys_bad_permissions():
    dir_bad_perms = os.path.join(TEST_DIR_YS_BAD_PERMISSIONS, "forbidden")
    os.chmod(dir_bad_perms, 0o000)
    # we tear down later, because otherwise pytest will have problems
    # with searching in that directory
    yield TEST_DIR_YS_BAD_PERMISSIONS
    os.chmod(dir_bad_perms, 0o544)
