# -*- coding: utf-8 -*-
# Test various small yarsync commands and configuration.
import os

from yarsync import YARsync
from yarsync.yarsync import _is_commit

from .settings import TEST_DIR


def test_error(test_dir_read_only):
    os.chdir(test_dir_read_only)
    ys = YARsync(["yarsync", "init"])
    # error messages are reasonable, so we don't test them here.
    returncode = ys()
    assert returncode == 8


def test_is_commit():
    assert _is_commit("1") is True
    assert _is_commit("01") is True
    assert _is_commit("abc") is False


def test_init():
    os.chdir(TEST_DIR)
    init_utf8 = YARsync("yarsync init источник".split())
    assert init_utf8.reponame == "источник"


def test_print(mocker):
    # ys must be initialized with some settings.
    os.chdir(TEST_DIR)

    mocker_print = mocker.patch("sys.stdout")
    call = mocker.call

    args = ["yarsync", "log"]
    ys = YARsync(args)  # command is not called
    # ys.print_level = 2

    ys._print("debug", level=2)
    assert mocker_print.mock_calls == [
        call.write('# '), call.write(''), call.write('debug'), call.write('\n')
    ]

    ys.print_level = 1

    mocker_print.reset_mock()
    # will print unconditionally
    ys._print("general")
    assert mocker_print.mock_calls == [
        call.write('general'), call.write('\n')
    ]

    mocker_print.reset_mock()
    ys._print("debug unavailable", level=2)
    assert mocker_print.mock_calls == []
