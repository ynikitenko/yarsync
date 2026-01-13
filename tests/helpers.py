import os
import subprocess
import sys
import unittest

# (major, minor)
SYSVERSION = (sys.version_info[0], sys.version_info[1])


def clone_repo(from_path, to_path):
    if not from_path.endswith(os.path.sep):
        from_path += os.path.sep
    rsync_command = (
        "rsync -avHP --delete-after "  # --filter='merge .ys/rsync-filter' "
        # we also copy configuration files,
        # because we need a real repository
        # with config.ini, etc.
        # "--include=/.ys/commits --include=/.ys/logs --exclude=/.ys/* "
        + from_path + " " + to_path
    )
    print(rsync_command)
    subprocess.check_call(rsync_command, shell=True,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def mock_compare(l1, l2, ignore_list=None):
    """Compare two lists l1 and l2 ignoring objects in *ignore*."""
    # function copied from lena/tests/output/test_write.py
    call = unittest.mock.call
    ignore = [unittest.mock.call().close(),]
    # if SYSVERSION[1] == 11:
    ignore.extend([
        call().__enter__(),
        call().read(-1),
        call().__exit__(None, None, None),
    ])
    if SYSVERSION[1] >= 14:
        ignore.extend([
            call.fileno(),
            call.fileno().__index__(),
        ])
    # a custom list to explicitly ignore specific calls for specific tests
    if ignore_list:
        ignore.extend(ignore_list)
    # prune lists
    l1p = [el for el in l1 if el not in ignore]
    l2p = [el for el in l2 if el not in ignore]
    return l1p == l2p
