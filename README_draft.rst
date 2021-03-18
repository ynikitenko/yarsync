------
Theory
------
rsync is a batch replication system (https://en.wikipedia.org/wiki/Replication_(computing)#Batch_replication)
This is the process of comparing the source and destination file systems and ensuring that the destination matches the source. The key benefit is that such solutions are generally free or inexpensive. The downside is that the process of synchronizing them is quite system-intensive, and consequently this process generally runs infrequently.

The Amazon CloudFront distribution is configured to block access from your country.

Backup:
incremental/full (both)
this is a personal backup tool!

In information technology, a backup, or data backup is a copy of computer data taken and stored elsewhere so that it may be used to restore the original after a data loss event.
https://en.wikipedia.org/wiki/Backup

-----------------
Why I use yarsync
-----------------
rsync always verifies that each transferred file was correctly reconstructed on the receiving side by checking a `whole-file checksum <https://linux.die.net/man/1/rsync>`_ that is generated as the file is transferred


How to
Checksums
---------

bit rot problem: https://www.reddit.com/r/DataHoarder/comments/4sil8l/adding_par2_files_for_all_my_photos_to_protect/
