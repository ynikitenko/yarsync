"""Test various small yarsync commands and configuration."""
import os
import socket

import pytest

from yarsync import YARsync
from yarsync.yarsync import _is_commit, _substitute_env
from yarsync.yarsync import (
    CONFIG_EXAMPLE, YSConfigurationError, YSCommandError
)

from .settings import TEST_DIR


def test_config(tmp_path):
    # Test real configuration file
    # example configuration is written during the initialisation
    os.chdir(tmp_path)
    ys = YARsync(["yarsync", "init"])
    ys()
    config_filename = ys.CONFIGFILE
    with open(config_filename) as config:
        assert config.read() == CONFIG_EXAMPLE

    # wrong configuration raises
    wrong_config = """\
    [remote1]
    path = /
    # duplicate sections are forbidden
    [remote1]
    path = /
    """
    with open(config_filename, "w") as config:
        config.write(wrong_config)
    # config is used only by pull, push and remote add.
    # So it should be rather remotes.ini
    # But we don't have any other config then.
    with pytest.raises(YSConfigurationError) as err:
        YARsync(["yarsync", "pull", "-n", "remote1"])
    # err is not a YSConfigurationError, but a pytest.ExceptionInfo,
    # that is why we take err.value
    assert "DuplicateSectionError" in err.value.msg
    assert "[line  4]: section 'remote1' already exists" in err.value.msg


def test_read_config():
    os.chdir(TEST_DIR)
    # we need to initialise one object to test its method
    ys = YARsync(["yarsync", "status"])
    # actual configuration is ignored here

    config_with_default = """\
    [DEFAULT]
    host_from_section_name

    [myremote]
    path = /

    [mylocal]
    # localhost
    host = 
    path = /
    """
    config, config_dict = ys._read_config(config_with_default)
    # path is unchanged. Changes are in the destpath.
    assert config_dict["myremote"]["path"] == "/"
    assert config_dict["myremote"]["destpath"] == "myremote:/"
    # section host overwrites the default host.
    assert config_dict["mylocal"]["destpath"] == "/"

    config_without_default = """\
    [myremote]
    path = /

    [mylocal]
    # localhost
    host = 
    path = /

    [myremote1]
    host = myremote1
    path = /

    [myremote2]
    path = myremote2:/
    """
    config, config_dict = ys._read_config(config_without_default)
    # oops, remote is considered a local path now...
    assert config_dict["myremote"]["destpath"] == "/"
    assert config_dict["mylocal"]["destpath"] == "/"
    # but we can provide a correct host:
    assert config_dict["myremote1"]["destpath"] == "myremote1:/"
    # or a correct path:
    assert config_dict["myremote2"]["destpath"] == "myremote2:/"


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


def test_print_command(capfd):
    os.chdir(TEST_DIR)
    args = ["yarsync", "log"]
    ys = YARsync(args)  # command is not called

    # any string command is printed as it is
    command_str = "just a string, will be unchanged"
    ys._print_command(command_str)

    captured = capfd.readouterr()
    assert not captured.err
    assert command_str + '\n' == captured.out

    command = ["this", "should be quoted"]
    ys._print_command(command)
    captured = capfd.readouterr()
    assert not captured.err
    assert captured.out == "this 'should be quoted'\n"
