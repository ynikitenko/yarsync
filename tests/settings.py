import os


# directory with commits and logs
TEST_DIR = os.path.join(os.path.dirname(__file__), "test_dir")
# same as TEST_DIR, but with an rsync-filter
TEST_DIR_FILTER = os.path.join(os.path.dirname(__file__), "test_dir_filter")
# directory without commits and logs, but with a .ys configuration
TEST_DIR_EMPTY = os.path.join(os.path.dirname(__file__), "test_dir_empty")
# directory with no files and no .ys directory
TEST_DIR_READ_ONLY = os.path.join(os.path.dirname(__file__),
                                  "test_dir_read_only")
# directory with a .ys repository, but with a forbidden subdirectory
TEST_DIR_YS_BAD_PERMISSIONS = os.path.join(os.path.dirname(__file__),
                                           "test_dir_ys_bad_permissions")
# content must be same as in TEST_DIR, but the YSDIR is detached.
TEST_DIR_CONFIG_DIR = os.path.join(os.path.dirname(__file__),
                                   "test_dir_config_dir")
TEST_DIR_WORK_DIR = os.path.join(os.path.dirname(__file__),
                                 "test_dir_work_dir")

YSDIR = ".ys"
