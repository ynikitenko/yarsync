"""Test various small yarsync commands and configuration."""
import os

import pytest

from yarsync import YARsync
from yarsync.yarsync import _is_commit, _substitute_env
from yarsync.yarsync import CONFIG_EXAMPLE, YSConfigurationError

from .settings import TEST_DIR


def test_config(tmp_path):
    # example configuration is written during the initialisation
    os.chdir(tmp_path)
    ys = YARsync(["yarsync", "init"])
    ys()
    config_filename = ys.CONFIGFILE
    with open(config_filename) as config:
        assert config.read() == CONFIG_EXAMPLE

    # wrong configuration raises
    wrong_config = """\
    [repo1]
    path = /
    # duplicate sections are forbidden
    [repo1]
    path = /
    """
    with open(config_filename, "w") as config:
        config.write(wrong_config)
    # config is used only by pull, push and remote add.
    # So it should be rather remotes.ini
    # But we don't have any other config then.
    with pytest.raises(YSConfigurationError):
        YARsync(["yarsync", "pull", "-n", "repo1"])


def test_env_vars():
    os.environ["VAR"] = "var"
    # variable substitution works for several lines
    lines = "[]\npath=$VAR/maybe"
    assert _substitute_env(lines).getvalue() == "[]\npath=var/maybe"
    # unset variable is not substituted
    lines = "[]\npath=$VAR1/maybe"
    assert _substitute_env(lines).getvalue() == "[]\npath=$VAR1/maybe"


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


def test_print(mocker):
    # ys must be initialised with some settings.
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
