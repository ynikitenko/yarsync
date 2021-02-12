# -*- coding: utf-8 -*-
import subprocess
import os
import pytest
import sys
import time
# from io import StringIO

from yarsync import YARsync
from settings import TEST_DIR, TEST_DIR_EMPTY, TEST_DIR_NO_PERMS, YSDIR


def test_status_error(mocker):
    """Test a not-yarsync directory."""
    os.chdir(TEST_DIR_NO_PERMS)
    mocker_print = mocker.patch("sys.stdout")
    call = mocker.call

    args = ["yarsync", "status"]
    with pytest.raises(OSError) as err:
        ys = YARsync(args)
    assert repr(err.value) == repr(OSError('.ys not found'))
    assert mocker_print.mock_calls == [
        call.write('!'),
        call.write(' '),
        call.write("fatal: no yarsync configuration "
                   ".ys found"),
        call.write('\n')
    ]


def test_status_no_commits(mocker):
    os.chdir(TEST_DIR_EMPTY)
    # StringIO uses only utf-8
    mocker_print = mocker.patch("sys.stdout") #, new_callable=StringIO)

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
    call = mocker.call
    assert res == 0
    assert mocker_print.mock_calls == [
        call.write(
            "rsync -aun --delete -i --exclude=/.ys {} {}/ {}/commits/2"\
            .format(filter_str, ys.root_dir, ys.config_dir)
        ),
        call.write('\n'),
        call.write('# changed since last commit:\n'),
        call.write('\n'),
        call.write('# no syncronization information found'),
        call.write('\n'),
    ]
