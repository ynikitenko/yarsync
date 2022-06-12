# -*- coding: utf-8 -*-
import os
import pytest
import subprocess
import sys
import time

from yarsync import YARsync
from .settings import TEST_DIR, TEST_DIR_EMPTY, YSDIR


def test_status_error(mocker, test_dir_read_only):
    """Test a not-yarsync directory."""
    os.chdir(test_dir_read_only)
    mocker_print = mocker.patch("sys.stdout")
    call = mocker.call

    args = ["yarsync", "status"]
    with pytest.raises(OSError) as err:
        ys = YARsync(args)
    assert ".ys not found" in repr(err.value)
    # don't test for exact messages,
    # because we might improve them in the future.
    # assert mocker_print.mock_calls == [
    #     call.write('!'),
    #     call.write(' '),
    #     call.write("fatal: no yarsync configuration "
    #                ".ys found"),
    #     call.write('\n')
    # ]


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
