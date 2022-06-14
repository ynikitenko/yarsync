# -*- coding: utf-8 -*-
import os
import pytest
import sys

from yarsync import YARsync
from .settings import TEST_DIR, TEST_DIR_EMPTY


def test_log_error(test_dir_read_only):
    """Test a not-yarsync directory."""
    os.chdir(test_dir_read_only)

    args = ["yarsync", "log"]
    with pytest.raises(OSError) as err:
        ys = YARsync(args)
    # the exact representation of value and the printed error message
    # are tested in test_status


def test_log_empty(mocker):
    os.chdir(TEST_DIR_EMPTY)
    mocker_print = mocker.patch("sys.stdout")

    args = ["yarsync", "log"]
    ys = YARsync(args)

    # call _log
    res = ys()
    call = mocker.call
    assert res == 0
    assert mocker_print.mock_calls == [
        call.write('No synchronization information found.'),
        call.write('\n'),
        call.write('No commits found'), call.write('\n')
    ]


def test_log(mocker):
    os.chdir(TEST_DIR)
    mocker_print = mocker.patch("sys.stdout")

    args = ["yarsync", "log"]
    ys = YARsync(args)

    # call _log
    res = ys()
    call = mocker.call
    assert res == 0
    assert mocker_print.mock_calls == [
        call.write('No synchronization information found.'),
        call.write('\n'),
        call.write('commit 3 is missing'),
        call.write('\n'),
        call.write('log 3\n'),
        call.write(''),
        call.write('\n'),
        call.write('commit 2'),
        call.write('\n'),
        call.write('When: Thu, 01 Jan 1970 03:00:02 MSK\nWhere: user@host\n'),
        call.write(''),
        call.write('\n'),
        call.write('commit 1'),
        call.write('\n'),
        call.write('Log is missing\nWhen: Thu, 01 Jan 1970 03:00:01 MSK\n'),
        call.write(''),
    ]

    mocker_print.reset_mock()
    # yarsync log -n 1 -r
    args = ["yarsync", "log", "--max-count", "1", "--reverse"]
    ys = YARsync(args)
    res = ys()
    call = mocker.call
    assert res == 0
    assert mocker_print.mock_calls == [
        call.write('No synchronization information found.'),
        call.write('\n'),
        call.write('commit 1'),
        call.write('\n'),
        call.write('Log is missing\nWhen: Thu, 01 Jan 1970 03:00:01 MSK\n'),
        call.write(''),
    ]


def test_make_commit_log_list():
    commits = [1, 3]
    logs = [2]
    ys = YARsync(["yarsync", "log"])  # the function is not called
    assert ys._make_commit_list(commits, logs) == [(1, None), (None, 2), (3, None)]
