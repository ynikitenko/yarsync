import os
import pathlib

import pytest

from yarsync import YARsync
from .settings import TEST_DIR, TEST_DIR_READ_ONLY, TEST_DIR_YS_BAD_PERMISSIONS
# TEST_DIR = "test_dir"

collect_ignore_glob = ["test_dir_*"]


def fix_hardlinks(main_path, dest_paths):
    for fil in os.listdir(main_path):
        for dest in dest_paths:
            dest_fil = dest / fil
            if dest_fil.exists():
                # it is important that files were never renamed,
                # only unlinked (in the general sense).
                # Note that if there were two old commits with one file
                # (now deleted from the workdir), these won't be linked.
                if dest_fil.is_file():
                    # not is_dir()
                    dest_fil.unlink()
                    os.link(main_path / fil, dest_fil)
                    # there is also Path.hardlink_to,
                    # but only available since version 3.10.
                else:
                    new_dests = [dp / fil for dp in dest_paths]
                    fix_hardlinks(main_path / fil, new_dests)


@pytest.fixture(scope="package", autouse=True)
def fix_test_hardlinks():
    # since we clone only TEST_DIR, it would be enough
    # to fix hard links there (they can get messed up by git).
    test_dir = pathlib.Path(TEST_DIR)
    commit_dir = test_dir / ".ys" / "commits"
    fix_hardlinks(test_dir, commit_dir.iterdir())


@pytest.fixture(scope="session")
def origin_test_dir(origin_dir=TEST_DIR, test_dir=TEST_DIR_YS_BAD_PERMISSIONS):
    """Add a remote "origin" with a path to origin_dir to test_dir."""
    os.chdir(test_dir)
    # disable stdout, or it will interfere with other tests.
    # There are open problems with capfd in pytest:
    # https://github.com/pytest-dev/pytest/issues/4428
    ys_add = YARsync("yarsync -qq remote add origin ".split() + [origin_dir])
    # this will fail (return 7) if the remote is already there,
    # but it doesn't affect the results.
    ys_add()
    yield origin_dir
    # remove remote "origin"
    # Enter test_dir again, because the current directory could change.
    os.chdir(test_dir)
    ys_rm = YARsync("yarsync remote rm origin".split())
    assert not ys_rm()


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
