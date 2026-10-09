# EACR final evaluation backup — 2026-10-08

The 26 binary part files in this directory are one gzip-compressed tar archive. It snapshots the 940 included files changed or added in the local workspace relative to GitHub master commit `170adeddda6be6b5b96fd44454ccdabdd9adfce3`; it retains valid and invalid result attempts and includes `BACKUP_MANIFEST.json` with file hashes and paths deleted in the local snapshot.

Reassemble from the repository root:

```sh
cat backups/eacr_final_workspace_diff_20261008.tar.gz.part-* > /tmp/eacr_final_workspace_diff_20261008.tar.gz
printf '%s  %s\n' '3209ea228d1beff6e81f39ab584b6587763a9c236641b8d299f864ac8a9ad2b8' /tmp/eacr_final_workspace_diff_20261008.tar.gz | sha256sum -c
tar -xzf /tmp/eacr_final_workspace_diff_20261008.tar.gz -C .
```

Archive size: 18,025,665 bytes. It contains 362,377,555 bytes across 940 files before compression. The separately committed report and aggregate are at `results/phase4_final_report.md` and `results/phase4_final_aggregate.json`.
