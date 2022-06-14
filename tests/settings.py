import os

# directory with commits and logs
TEST_DIR = os.path.join(os.path.dirname(__file__), "test_dir")
# directory without commits and logs, but with a .ys configuration
TEST_DIR_EMPTY = os.path.join(os.path.dirname(__file__), "test_dir_empty")
# directory with no files and no .ys directory
TEST_DIR_READ_ONLY = os.path.join(os.path.dirname(__file__),
                                  "test_dir_read_only")
# directory with a .ys repository, but with a forbidden subdirectory
TEST_DIR_YS_BAD_PERMISSIONS = os.path.join(os.path.dirname(__file__),
                                           "test_dir_ys_bad_permissions")

YSDIR = ".ys"
