% YARSYNC(1) yarsync 0.1
% Written by Yaroslav Nikitenko
% June 2022

# NAME
Yet Another Rsync is a file synchronization tool

# SYNOPSIS
**yarsync** [-h] [-n] [-q] command [args]

# DESCRIPTION
**yarsync** is a wrapper around rsync to store configuration
and synchronize repositories with the interface similar to git.
It is efficient (files in the repository can be removed and renamed freely without additional transfers)
and distributed (several replicas of the repository can diverge, and in that case a manual merge is supported).

[comment]: # (**yarsync** stores snapshot versions in commits in .ys/commits subdirectory. It is non-intrusive)

# OPTIONS
**-h**, **--help**
: Prints help message and exits.

# EXIT STATUS
**0**
: Success

**7**
: Invalid option

In case of rsync errors, yarsync returns the corresponding rsync error code.

# SEE ALSO
**rsync**(1)

The yarsync page is <https://github.com/ynikitenko/yarsync>.

# BUGS
Please report bugs to <https://github.com/ynikitenko/yarsync/issues>.

# COPYRIGHT
Copyright (C) 2021-2022 Yaroslav Nikitenko.

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program. If not, see <https://www.gnu.org/licenses/>.
