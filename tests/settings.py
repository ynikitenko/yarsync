import os

# directory with commits and logs
TEST_DIR = os.path.join(os.path.dirname(__file__), "test_dir")
# directory without commits and logs, but with a .ys configuration
TEST_DIR_EMPTY = os.path.join(os.path.dirname(__file__), "test_dir_empty")
# directory with no files and no .ys directory
TEST_DIR_NO_PERMS = os.path.join(os.path.dirname(__file__), "test_dir_no_permissions")

YSDIR = ".ys"
