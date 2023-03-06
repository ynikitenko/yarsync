import os

from yarsync import YARsync
from yarsync.yarsync import _substitute_env
from .settings import TEST_DIR


def test_env_vars():
    os.environ["VAR"] = "var"
    # variable substitution works for several lines
    lines = "[]\npath=$VAR/maybe"
    assert _substitute_env(lines).getvalue() == "[]\npath=var/maybe"
    # unset variable is not substituted
    lines = "[]\npath=$VAR1/maybe"
    assert _substitute_env(lines).getvalue() == "[]\npath=$VAR1/maybe"
