import os
import stat

import pytest

from yarsync import YARsync
from yarsync.yarsync import _is_commit, _substitute_env
from yarsync.yarsync import (
    CONFIG_EXAMPLE, YSConfigurationError, YSCommandError,
    CONFIG_ERROR, COMMAND_ERROR
)

from .helpers import clone_repo
from .settings import TEST_DIR, TEST_DIR_FILTER, TEST_DIR_YS_BAD_PERMISSIONS

clone_command = ["yarsync", "clone"]
rsync_error = 23


def test_clone_from(tmp_path_factory, capfd):
    dest = tmp_path_factory.mktemp("test")
    os.chdir(str(dest))

    # when we clone from, we don't affect the original repo
    ys = YARsync(clone_command + ["tmp", TEST_DIR])
    returncode = ys()
    assert not returncode
    test_dir_name = 'test_dir'  # os.path.basename(TEST_DIR)
    # test_dir was cloned into dest
    assert os.listdir(str(dest)) == [test_dir_name]

    # files from test_dir were transferred
    new_repo_dir = os.path.join(dest, test_dir_name)
    assert set(os.listdir(new_repo_dir)) == set(['b', 'a', 'c', '.ys'])

    # configuration files were transferred
    # clone name was used correctly
    new_ys_dir = os.path.join(new_repo_dir, ys.YSDIR)
    assert set(os.listdir(new_ys_dir)) == set([
        'sync', 'commits', 'repo_tmp.txt', 'logs', 'config.ini'
    ])

    # we don't check every commit, because that is done in pull
    new_sync_dir = os.path.join(new_ys_dir, ys.SYNCDIRNAME)
    assert set(os.listdir(new_sync_dir)) == set([
        '2_TEST.txt', '2_tmp.txt', '2_other_repo.txt'
    ])

    # no errors were issued
    captured = capfd.readouterr()
    assert not captured.err

    ## Can't clone from a directory with filter
    dest3 = tmp_path_factory.mktemp("dest")
    os.chdir(dest3)
    ys3 = YARsync(["yarsync", "clone", "clone", TEST_DIR_FILTER])
    return_code = ys3()
    assert return_code == CONFIG_ERROR


@pytest.mark.parametrize(
    "test_dir_source", (TEST_DIR, TEST_DIR_FILTER)
)
def test_clone_to(tmp_path_factory, test_dir_source):
    # todo: filter is probably irrelevant for this test
    # and doesn't work (where do we check for it?)
    source_dir = tmp_path_factory.mktemp("test")
    clone_dir = tmp_path_factory.mktemp("test")
    repo_name = os.path.basename(source_dir)

    # we copy the repository low-level to get rid of side effects
    # (synchronization, new remote, etc.)
    clone_repo(str(test_dir_source), str(source_dir))
    os.chdir(str(source_dir))

    ys = YARsync(clone_command + ["tmp", str(clone_dir)])
    returncode = ys()
    assert not returncode

    # todo: capture output
    # if "-v" in clone_command: ...

    # all files were transferred
    new_repo = os.path.join(clone_dir, repo_name)
    # we compare sets, because the ordering will be different
    new_files = set(os.listdir(new_repo))
    assert new_files.issubset(set(os.listdir(source_dir)))
    # they are not equal, because rsync-filter excludes 'b'
    assert 'a' in new_files


def test_clone_from_errors_1(tmp_path_factory, capfd):
    invalid_source = tmp_path_factory.mktemp("invalid_source")
    dest1 = tmp_path_factory.mktemp("dest_for_cloning")

    ## Can't clone from an invalid repository
    os.chdir(dest1)
    ys1 = YARsync(clone_command + ["origin", str(invalid_source)])
    # will be called clone_from, because we are outside.
    return_code = ys1._clone_from("origin", str(invalid_source))
    assert return_code == COMMAND_ERROR
    err = capfd.readouterr().err
    assert 'No yarsync repository found at ' in err

    ## Can't clone into a repository with the same name
    os.chdir(dest1)
    ys_same_name = YARsync(clone_command + ["TEST", TEST_DIR])
    returncode = ys_same_name()
    assert returncode == COMMAND_ERROR
    assert "Name 'TEST' is already used by the remote. " in capfd.readouterr().err

    ## Can't clone if the new directory already exists
    os.mkdir("test_dir")
    ys_exists = YARsync(clone_command + ["new_TEST", TEST_DIR])
    returncode = ys_exists()
    assert returncode == COMMAND_ERROR
    assert "Directory 'test_dir' exists. Aborting" in capfd.readouterr().err


def test_clone_from_errors_2(tmp_path_factory, capfd):
    ## Can't clone from a repository with bad permissions
    dest3 = str(tmp_path_factory.mktemp("dest_to_fail"))
    os.chdir(dest3)
    # slash added for variability (coverage)
    ys3 = YARsync(clone_command + ["clone", TEST_DIR_YS_BAD_PERMISSIONS + '/'])
    assert ys3() == rsync_error
    captured = capfd.readouterr()
    assert "An error occurred while pulling data from" in captured.err
    # even though the contents of the directory were not transferred,
    # it has been created.
    forbidden = os.path.join(dest3, "test_dir_ys_bad_permissions", "forbidden")
    os.chmod(forbidden, 0o777)


@pytest.mark.usefixtures("test_dir_ys_bad_permissions")
def test_clone_from_repo_with_bad_permissions(test_dir_common_copy, capfd):
    ## Can't clone from inside a repository with bad permissions
    ys = YARsync(clone_command + ["clone", test_dir_common_copy])
    # this is a COMMAND_ERROR, because there are uncommitted changes
    assert ys._clone_to("clone", test_dir_common_copy) == COMMAND_ERROR
    captured = capfd.readouterr()
    assert "local repository has uncommitted changes. Exit." in captured.err


@pytest.mark.usefixtures("test_dir_common_copy")
def test_clone_to_errors_1(tmp_path_factory, capfd):
    ## Can't clone from here if we can't read the remote parent
    # create a directory with bad permissions
    dest_bad = str(tmp_path_factory.mktemp("bad_dest"))
    # from https://stackoverflow.com/a/25988623/952234
    # cur_perm = stat.S_IMODE(os.lstat(dest_bad).st_mode)
    # os.chmod(dest_bad, cur_perm & ~stat.S_IREAD)
    os.chmod(dest_bad, 0o000)
    # do the clone
    ys_bad_parent = YARsync(clone_command + ["bad_parent", dest_bad])
    returncode = ys_bad_parent()
    # tear down permissions
    os.chmod(dest_bad, 0o755)
    # os.chmod(dest_bad, cur_perm | stat.S_IREAD)
    assert returncode == COMMAND_ERROR
    captured = capfd.readouterr()
    assert "Parent folder of the clone could not be read. Aborting"\
           in captured.err


@pytest.mark.usefixtures("test_dir_separate_copy")
def test_clone_to_errors_2(tmp_path_factory, capfd):
    ## Clone name must not exist in remotes
    dest4 = str(tmp_path_factory.mktemp("dest_for_errors"))
    ys4 = YARsync(clone_command + ["other_repo", dest4])
    assert ys4() == COMMAND_ERROR
    assert "remote other_repo exists, break." in capfd.readouterr().err

    ## synchronization changes are updated normally
    sync_dir6 = os.path.join(".ys", "sync")
    sync60 = os.listdir(sync_dir6)
    assert set(sync60) == set(['2_other_repo.txt', '2_TEST.txt'])
    dest6 = str(tmp_path_factory.mktemp("new_dest"))
    ys6 = YARsync(clone_command + ["new_clone_2", dest6])
    assert ys6() == 0
    sync61 = os.listdir(sync_dir6)
    assert set(sync61) == set(['2_new_clone_2.txt', '2_other_repo.txt', '2_TEST.txt'])

    # manually fix it, otherwise pytest complains about garbage,
    # see https://github.com/pytest-dev/pytest/issues/7821


def test_clone_to_errors_3(tmp_path_factory, test_dir_separate_copy, capfd):
    # if we don't mark it, we have to cd explicitly
    os.chdir(test_dir_separate_copy)
    # print(os.getcwd())
    ## synchronization changes are reverted in case of errors
    sync_dir5 = os.path.join(".ys", "sync")
    sync50 = set(os.listdir(sync_dir5))
    assert sync50 == {'2_other_repo.txt', '2_TEST.txt'}
    dest5 = str(tmp_path_factory.mktemp("dest"))
    ys5 = YARsync(clone_command + ["new", dest5])
    comm_1_dir = os.path.join(".ys", "commits", "1")
    repo_dir_name = os.path.basename(test_dir_separate_copy)
    comm_1_dir_copy = os.path.join(dest5, repo_dir_name, ".ys", "commits", "1")
    os.chmod(comm_1_dir, 0o000)
    returncode = ys5()
    os.chmod(comm_1_dir, 0o755)
    os.chmod(comm_1_dir_copy, 0o755)
    # command error, because the problem is with local repo
    # rsync error, because otherwise test fails
    assert returncode == rsync_error
    sync51 = set(os.listdir(sync_dir5))
    assert sync51 == sync50


def test_clone_to_errors_parent(tmp_path_factory, capfd):
    ## Can't clone if the remote contains
    ## a folder with this directory name
    test_dir2 = tmp_path_factory.mktemp("test_dir2")
    clone_repo(str(TEST_DIR), str(test_dir2))
    os.chdir(test_dir2)
    dest_exists = str(tmp_path_factory.mktemp("new_dest"))
    # create a directory with the name of local repository in dest
    os.mkdir(os.path.join(dest_exists, os.path.basename(test_dir2)))
    ys_dest_ex = YARsync(clone_command + ["new", dest_exists])
    assert ys_dest_ex() == COMMAND_ERROR
    captured = capfd.readouterr()
    assert "Repository folder already exists at " + dest_exists in captured.err


def test_clone_with_env_path(tmp_path_factory):
    ### Clone from path with an environmental variable
    ### preserves that variable in the configuration
    test_dir = tmp_path_factory.mktemp("new_test_dir")
    test_dir_name = os.path.basename(test_dir)
    clone_repo(str(TEST_DIR), str(test_dir))

    ## Clone from path with an envvar works
    dest1 = tmp_path_factory.mktemp("dest")
    os.chdir(dest1)
    os.environ["TEST_DIR"] = str(test_dir)
    ys1 = YARsync(clone_command + ["clone", "$TEST_DIR"])
    return_code = ys1()
    assert not return_code

    # remove the variable, so that it is no longer expanded in _config
    del os.environ["TEST_DIR"]
    ys11 = YARsync("yarsync remote show".split())
    ys11()
    # it is TEST, because it is the name of origin.
    assert ys11._config["TEST"]["path"] == "$TEST_DIR"

    ## Clone to path with an envvar works
    dest2 = tmp_path_factory.mktemp("dest2")
    os.environ["DEST2"] = str(dest2)
    # we are still in dest1
    ys2 = YARsync(["yarsync", "clone", "clone2", "$DEST2"])
    return_code = ys2()
    assert not return_code

    del os.environ["DEST2"]
    ys21 = YARsync("yarsync remote show".split())
    ys21()
    assert ys21._config["clone2"]["path"] == \
           os.path.join("$DEST2", test_dir_name)
