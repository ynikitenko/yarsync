import os
import pytest

from yarsync import YARsync
from yarsync.yarsync import _Sync as Sync, YSConfigurationError
# from .settings import (
#     TEST_DIR, TEST_DIR_EMPTY, YSDIR, TEST_DIR_YS_BAD_PERMISSIONS
# )


def test_sync():
    sync_list = [
        "1_a",
        "1_b2",
        "2_c",
        "2_a"
    ]
    s0 = Sync(sync_list)

    assert s0.by_repos == {
        "a": 2,
        "b2": 1,
        "c": 2,
    }
    # by_commits works, but is not used.
    # assert s0.by_commits == {
    #     2: set(("c", "a")),
    #     1: set(("b2",)),
    # }
    # assert s0.repos == frozenset(("a", "b", "c"))

    sync_list_2 = ["1_a", "2_b2", "3_dd"]
    s1 = Sync(sync_list_2)
    s0.update(s1.by_repos.items())
    repos1 = {
        "a": 2,
        "b2": 2,
        "c": 2,
        "dd": 3,
    }
    assert s0.by_repos == repos1
    # assert s0.by_commits == {
    #     2: set(("c", "a", "b2")),
    #     3: set(("dd",)),
    # }
    # assert s0.repos == frozenset(("a", "b", "c"))
    # tuple, otherwise set contains characters from the string
    removed1 = set(("1_a",))
    assert s0.removed == removed1
    new1 = set(("2_b2", "3_dd"))
    assert s0.new == new1
    # update is idempotent (doesn't change new and removed, as well as sync)
    s0.update(s1.by_repos.items())
    assert s0.by_repos == repos1
    assert s0.removed == removed1
    assert s0.new == new1

    # incorrect commit number raises
    with pytest.raises(YSConfigurationError):
        Sync(["a_a"])


def test_sync_bool():
    # False for an empty synchronization
    assert not Sync([])

    # True if there is data
    sync_list = ["1_a"]
    assert Sync(sync_list)
