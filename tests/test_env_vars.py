import os

from yarsync.yarsync import _substitute_env


def test_env_vars():
    os.environ["VAR"] = "var"
    # variable substitution works for several lines
    lines = "[]\npath=$VAR/maybe"
    assert _substitute_env(lines).getvalue() == "[]\npath=var/maybe"
    # unset variable is not substituted
    lines = "[]\npath=$VAR1/maybe"
    assert _substitute_env(lines).getvalue() == "[]\npath=$VAR1/maybe"
