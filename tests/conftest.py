import os

import pytest


@pytest.fixture(scope="session")
def test_dir_read_only():
    from .settings import TEST_DIR_READ_ONLY
    os.chmod(TEST_DIR_READ_ONLY, 0o544)
    return TEST_DIR_READ_ONLY
    # no need to tear down,
    # since git has no problems with read-only directories
