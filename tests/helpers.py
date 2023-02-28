import os
import subprocess


def clone_repo(from_path, to_path):
    if not from_path.endswith(os.path.sep):
        from_path += os.path.sep
    rsync_command = (
        "rsync -avHP --delete-after "  # --filter='merge .ys/rsync-filter' "
        # we also copy configuration files,
        # because we need a real repository
        # with config.ini, etc.
        # "--include=/.ys/commits --include=/.ys/logs --exclude=/.ys/* "
        + from_path + " " + to_path
    )
    print(rsync_command)
    subprocess.check_call(rsync_command, shell=True,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
