# Base YRP runtime overlay deployment artifact

Created: 2026-08-28

Base repository: `apps/yrp`

Required base HEAD: `7536d315c380157fa1d90936b2f5343b9eed6481`

This artifact records the pre-existing base YRP runtime overlay qualified by
the Essdee MRP migration and end-to-end acceptance run. Creating this artifact
did not change the base YRP worktree.

## Contents and checksums

- `tracked-overlay.patch.gz`
  - Archive SHA-256:
    `17b6556a5ccaeba964cd9aebd1e6978f76cb4121f7856f414f9bdfec9e2dc61b`
  - Decompressed patch SHA-256:
    `849c7a8b2ca97e2fda2c97a95f5078b92c6979cd30e7a53c4d16311eea04a88b`
  - Exact gzip-compressed `git diff --binary` from the required base HEAD.
- `untracked-files.tar.gz`
  - SHA-256: `fdd8a604cc67b18bf38dea07dc4ebdf628b3c846a762b070cdbabd659e20136b`
  - Contains only
    `yrp/yrp/doctype/delivery_challan/test_delivery_challan_pending_rebuild.py`.
- Extracted untracked test file
  - SHA-256: `62e3be5d399780b1f1553df65f7ee465764b468e68d8ed0d5b11c9617291d164`

## Reproduction

Starting from a clean checkout at the required base HEAD:

```bash
gzip -dc /path/to/tracked-overlay.patch.gz | git apply --binary -
tar -xzf /path/to/untracked-files.tar.gz
```

Then verify:

```bash
git diff --binary | sha256sum
sha256sum yrp/yrp/doctype/delivery_challan/test_delivery_challan_pending_rebuild.py
```

The results must match the tracked and untracked SHA-256 values above. This is
a deployment artifact only; the base repository remains read-only for the
Essdee MRP release.
