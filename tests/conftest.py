import os
import pathlib

import pytest

from yarsync import YARsync
from .settings import TEST_DIR, TEST_DIR_READ_ONLY, TEST_DIR_YS_BAD_PERMISSIONS

collect_ignore_glob = ["test_dir_*"]


def fix_hardlinks(main_dir, dest_dirs):
    for fil in os.listdir(main_dir):
        # be careful that dest_dirs are a list, not an exhaustable iterator
        for dest_dir in dest_dirs:
            dest_path = dest_dir / fil
            if dest_path.exists():
                # it is important that files were never renamed,
                # only unlinked (in the general sense).
                # Note that if there were two old commits with one file
                # (now deleted from the workdir), these won't be linked.
                if dest_path.is_file():
                    # not is_dir()
                    dest_path.unlink()
                    # print("link ", main_dir / fil, dest_path)
                    os.link(main_dir / fil, dest_path)
                    # there is also Path.hardlink_to,
                    # but only available since version 3.10.
                else:
                    fix_hardlinks(main_dir / fil, [dest_path])


def fix_ys_hardlinks(test_dir):
    # since we clone only TEST_DIR, it would be enough
    # to fix hard links there (they can get messed up by git).
    test_dir = pathlib.Path(test_dir)
    commit_dir = test_dir / ".ys" / "commits"
    fix_hardlinks(test_dir, list(commit_dir.iterdir()))


@pytest.fixture(scope="session", autouse=True)
def fix_test_dir():
    test_dir = TEST_DIR
    fix_ys_hardlinks(test_dir)
    # this fixture must be always used with the TEST_DIR,
    # but we allow it to be used in test arguments for explicitness
    return test_dir


@pytest.fixture
def test_dir():
    os.chdir(TEST_DIR)


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
    # tear down, because otherwise may have problems with cleaning up
    os.chmod(TEST_DIR_READ_ONLY, 0o755)


@pytest.fixture(scope="session")
def test_dir_ys_bad_permissions():
    subdir_bad_perms = os.path.join(TEST_DIR_YS_BAD_PERMISSIONS, "forbidden")
    os.chmod(subdir_bad_perms, 0o000)
    # we tear down later, because otherwise pytest will have problems
    # with searching in that directory
    yield TEST_DIR_YS_BAD_PERMISSIONS
    os.chmod(subdir_bad_perms, 0o755)
