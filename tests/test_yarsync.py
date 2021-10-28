# -*- coding: utf-8 -*-
# Test various small yarsync commands
import os

from yarsync import YARsync
from yarsync.yarsync import _is_commit

from settings import TEST_DIR, TEST_DIR_NO_PERMS


def test_error():
    if not os.path.exists(TEST_DIR_NO_PERMS):
        # git doesn't preserve permissions,
        # so we recreate this ourselves.
        # It's safe to call mkdir on non-Linux systems.
        # Docs write that permissions are ignored in that case
        # (however the test shall then fail)
        os.mkdir(TEST_DIR_NO_PERMS, 0o555)
    os.chdir(TEST_DIR_NO_PERMS)
    ys = YARsync(["yarsync", "init"])
    returncode = ys()
    print("if this test fails, check that permissions are correct")
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
    ys.DEBUG = True

    ys._print("debug", debug=True)
    assert mocker_print.mock_calls == [
        call.write('debug'), call.write('\n')
    ]

    ys.DEBUG = False

    mocker_print.reset_mock()
    # will print unconditionally
    ys._print("general")
    assert mocker_print.mock_calls == [
        call.write('general'), call.write('\n')
    ]

    mocker_print.reset_mock()
    ys._print("debug unavailable", debug=True)
    assert mocker_print.mock_calls == []
