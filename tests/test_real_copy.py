# -*- coding: utf-8 -*-
### Not called, does not actually work ###
import os
import subprocess
import sys

from .settings import TEST_DIR


# tmpdir is pytest fixture, https://docs.pytest.org/en/latest/tmpdir.html
# Hard to say how much that is useful.
def _test_real_copy(tmpdir):
    # simple push works
    # nothing real yet. By default my yarsync is '-n'.
    p_tmp = subprocess.Popen(
        ["yarsync", "push", "-n", tmpdir.__str__()],
        cwd=TEST_DIR, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    stdoutdata, stderrdata = p_tmp.communicate()
    returncode = p_tmp.returncode
    # print(stdoutdata, stderrdata, returncode)
    rsync_command_base = (
        b"rsync -avHP --delete-after --filter='merge .ys/rsync-filter' "
        b"--include=/.ys/commits --include=/.ys/logs --exclude=/.ys/* "
    )
    # this won't work with real tmpdir, but now we have a fixed one.
    rsync_command = rsync_command_base + b"./ "
    print(tmpdir.__str__())

    if sys.version_info[0] == 2:
        rsync_command += bytes(tmpdir.__str__()) + b"/\n"
    else:
        rsync_command += bytes(tmpdir.__str__(), 'utf-8') + b"/\n"
    # rsync_command = rsync_command_base + b"./ ../tmp_test_dir/\n"
    # print(rsync_command)
    print(stdoutdata)
    assert stdoutdata == rsync_command

    # UTF8 names work
    p_utf8 = subprocess.Popen(
        ["yarsync", "push", "-n", "../директория"],
        cwd=TEST_DIR, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    stdoutdata, stderrdata = p_utf8.communicate()
    returncode = p_utf8.returncode
    if sys.version_info[0] == 2:
        # in fact a byte string, but Python3 prohibits UTF8 in byte strings,
        # even when not executing that!
        rsync_command_utf8 = rsync_command_base + "./ ../директория/\n"
    else:
        rsync_command_utf8 = rsync_command_base + "./ ../директория/\n".encode('utf-8')

    # print(stdoutdata, stderrdata, returncode)
    assert stdoutdata == rsync_command_utf8
    return returncode

    # pwd = subprocess.call(["pwd"])
    # cd executable is not found, but there is a kwarg cwd
    # cd = subprocess.call(["cd", TEST_DIR])
