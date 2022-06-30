"""a file synchronization and backup tool.

To list available commands, run

    $ yarsync --help

Read YARsync manual for complete documentation.
https://github.com/ynikitenko/yarsync
"""

# otherwise one would have to write 'from yarsync.yarsync import YARsync'
from .yarsync import YARsync
