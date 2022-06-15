# -*- coding: utf-8 -*-
import os
import pytest
import subprocess

from yarsync import YARsync
from .settings import (
    TEST_DIR, TEST_DIR_EMPTY, YSDIR, TEST_DIR_YS_BAD_PERMISSIONS
)


def test_remote_add(capfd, origin_test_dir, test_dir_ys_bad_permissions):
    # remote is added fine
    # bad permissions don't affect .ys config
    os.chdir(test_dir_ys_bad_permissions)
    ys = YARsync("yarsync remote add origin".split() + [origin_test_dir])
    # remote "origin" is already added in origin_test_dir.
    # adding remote with same name is forbidden
    returncode = ys()
    assert returncode == 7
    captured = capfd.readouterr()
    assert "! remote origin exists, break." in captured.err
    # we disabled stdout in the fixture.
    assert not captured.out
    # # It seems this is captured from the fixture.
    # # assert "Remote origin added." in captured.out
