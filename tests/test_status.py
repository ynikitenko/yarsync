# -*- coding: utf-8 -*-
import os
import pytest
import subprocess
import sys
import time

from yarsync import YARsync
from .settings import (
    TEST_DIR, TEST_DIR_EMPTY, YSDIR, TEST_DIR_YS_BAD_PERMISSIONS
)


def test_status_error(mocker, test_dir_read_only):
    ## test directory without .ys configuration
    os.chdir(test_dir_read_only)
    mocker_stdout = mocker.patch("sys.stdout")
    mocker_stderr = mocker.patch("sys.stderr")
    call = mocker.call

    args = ["yarsync", "status"]
    # issues a mocker warning
    # with mocker.patch("sys.stderr") as mocker_stderr:
    with pytest.raises(OSError) as err:
        ys = YARsync(args)
    assert ".ys not found" in repr(err.value)

    # adapted from https://stackoverflow.com/a/59398826/952234
    write_calls = mocker_stderr.write.call_args_list
    # [0] is call args, [1] is kwargs
    written_strs = "".join(call[0][0] for call in write_calls)
    # error message is correct
    assert written_strs == \
        "! fatal: no yarsync configuration directory .ys found\n"
    # no stdout output
    assert mocker_stdout.mock_calls == []

    # don't test for exact messages,
    # because we might improve them in the future.
    # assert mocker_print.mock_calls == [
    #     call.write('!'),
    #     call.write(' '),
    #     call.write("fatal: no yarsync configuration "
    #                ".ys found"),
    #     call.write('\n')
    # ]


def test_status_error_bad_permissions(mocker, test_dir_ys_bad_permissions):
    os.chdir(test_dir_ys_bad_permissions)
    # mocker_stderr.reset_mock()
    # mocker_stdout = mocker.patch("sys.stdout")
    mocker_stderr = mocker.patch("sys.stderr")
    ys = YARsync(["yarsync", "status"])
    returncode = ys()
    # rsync returns 23 in case of permission errors
    assert returncode == 23
    # mocker doesn't capture stderr output from rsync
    # (because it uses a file descriptor, not sys.stderr)
    # written_stderr = "".join(call[0][0] for call in
    #                          mocker_stderr.write.call_args_list)
    # assert 'test_dir_ys_bad_permissions/forbidden" failed: Permission denied '\
    #     in written_stderr


def test_status_no_commits(mocker):
    os.chdir(TEST_DIR_EMPTY)
    # io.StringIO uses only utf-8
    mocker_print = mocker.patch("sys.stdout")  #, new_callable=StringIO)

    args = ["yarsync", "status"]
    ys = YARsync(args)
    res = ys()
    call = mocker.call
    assert res == 0
    assert mocker_print.mock_calls == [
        call.write('No commits found'), call.write('\n')
    ]


def test_status_existing_commits(mocker):
    os.chdir(TEST_DIR)
    mocker_print = mocker.patch("sys.stdout")

    args = ["yarsync", "status"]
    ys = YARsync(args)
    res = ys()
    # filter is needed, because not only .ys can be excluded
    filter_str = ys._get_filter(include_commits=False)[1]
    assert res == 0

    ## stdout is correct
    call = mocker.call
    # it is very dubious that we shall test each output line.
    assert mocker_print.mock_calls == [
        call.write('# '),
        call.write(''),
        call.write(
            "rsync -aun --delete -i --exclude=/.ys {} --outbuf=L {}/ {}/commits/2"\
            .format(filter_str, ys.root_dir, ys.config_dir)
        ),
        call.write('\n'),
        call.write('Nothing to commit, working directory clean.'),
        call.write('\n'),
        call.write('No syncronization information found.'),
        call.write('\n'),
    ]
