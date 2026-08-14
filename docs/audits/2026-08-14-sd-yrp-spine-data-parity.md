# SD YRP Spine Data Parity Audit

> This file audits document identities/counts. It does **not** prove that all
> parent and child field values synchronize. The field-by-field result is in
> `2026-08-14-sd-yrp-spine-field-value-audit.md`.

Audit time: 2026-08-14 11:20 IST
Source: F15 `mrp3.site` / `production_api`
Target: F16 `essdee_yrp.site` / `essdee_yrp`
Topic: `sd_yrp_master`

## Result

- 31 DocTypes are enabled in the source SD-YRP publish order and target
  consumer mappings.
- 6 DocTypes are perfect for the synchronized source fields and identities.
- 4 more contain every source record with matching synchronized fields, but
  also contain intentional/test F16-only records.
- 21 DocTypes are not currently at source parity.
- Historical migration must not start until this master-sync gap is resolved
  and the comparison is rerun.

The source `Spine Producer Config` table itself contains only the older ERP
topic mappings. SD-YRP publishing is intentionally registered through
`production_api/hooks.py` and `production_api.sd_yrp_sync`, while the F16
`Spine Consumer Config` contains all 31 `sd_yrp_master` mappings.

## Live identity comparison

`Missing` means a source identity is absent on F16. `Target only` means an F16
identity is absent on F15. Singles are compared by synchronized field values.

| # | Source DocType | Mapper | Source | Target | Missing | Target only | Result |
|---:|---|---|---:|---:|---:|---:|---|
| 1 | Country | Exact/special country guard | 249 | 251 | 0 | 2 | Source data matches; target also has Kosovo and Türkiye |
| 2 | UOM | Exact | 17 | 17 | 0 | 0 | Perfect |
| 3 | Brand | Exact | 3 | 3 | 0 | 0 | Perfect |
| 4 | Terms and Condition | Exact | 1 | 2 | 1 | 2 | Not matched |
| 5 | Product Season | Exact | 17 | 15 | 2 | 0 | Not matched |
| 6 | Product Category | Exact | 5 | 4 | 1 | 0 | Not matched |
| 7 | Additional Parameter Key | Exact | 2 | 2 | 0 | 0 | Perfect |
| 8 | Additional Parameter Value | Exact | 29 | 28 | 1 | 0 | Not matched |
| 9 | Item Attribute | Exact | 21 | 22 | 0 | 1 | Source data matches; target also has Weight |
| 10 | Production Term | Exact | 3 | 5 | 0 | 2 | Source parent/child data matches; target has two test terms |
| 11 | User | Custom | 97 | 104 | 6 | 13 | Not matched |
| 12 | Item Category | Exact | 32 | 32 | 0 | 0 | Perfect |
| 13 | Address | Exact | 2,940 | 2,881 | 60 | 1 | Not matched |
| 14 | Item Group | Exact | 80 | 81 | 0 | 1 | Source data matches; target also has Test Group |
| 15 | Item Attribute Value | Exact | 2,087 | 2,058 | 40 | 11 | Not matched |
| 16 | Department | Exact | 10 | 10 | 0 | 0 | Parent data matches; child users do not match |
| 17 | Contact | Exact | 120 | 426 | 9 | 315 | Not matched |
| 18 | Item Item Attribute Mapping | Exact | 6,872 | 6,827 | 230 | 185 | Not matched |
| 19 | Supplier | Custom | 3,218 | 3,157 | 65 | 4 | Not matched |
| 20 | Item | Custom | 4,463 | 4,355 | 124 | 16 | Not matched |
| 21 | Process | Exact | 24 | 27 | 1 | 4 | Not matched |
| 22 | Item Variant | Exact | 75,017 | 71,990 | 3,240 | 213 | Not matched |
| 23 | Item Dependent Attribute Mapping | Exact/safe cycle back-fill | 1,258 | 1,231 | 40 | 13 | Not matched |
| 24 | Item BOM Attribute Mapping | Exact | 2,785 | 2,647 | 195 | 57 | Not matched |
| 25 | IPD Settings | Custom Single | 1 | 1 | 0 | 0 | Perfect for all 13 synchronized fields; 5 F16-only fabric defaults retained |
| 26 | MRP Settings | Custom Single | 1 | 1 | — | — | 12 business fields differ; 2 numeric values differ only by formatting |
| 27 | Production Order | Custom | 277 | 187 | 91 | 1 | Not matched |
| 28 | Lot Template | Custom | 1 | 1 | 0 | 0 | Perfect, including Item Attribute and BOM children |
| 29 | Item Production Detail | Custom | 437 | 482 | 21 | 66 | Not matched |
| 30 | IPD Compacting | Exact | 2 | 2 | 2 | 2 | Counts equal but identities are completely different |
| 31 | Lot | Custom | 1,857 | 1,797 | 82 | 22 | Not matched |

## Perfectly matched source data

These are exact for the source identities and synchronized values:

1. UOM
2. Brand
3. Additional Parameter Key
4. Item Category
5. IPD Settings
6. Lot Template

These also contain all source identities and matching synchronized values, but
the target deliberately has extra records:

1. Country
2. Item Attribute
3. Production Term
4. Item Group

Department is not in either list because target KNITTING contains one extra
`Department User` (`monisha@essdee.fit`), shifting two source row indexes.

## MRP Settings differences

Real value differences:

- `cloth_allowance_percentage`: source `0`, target `8.4`
- `default_major_aql_level`: source `Level-2.5`, target blank
- `default_minor_aql_level`: source `Level-4.0`, target blank
- `production_order_quantity_approver_role`: source `Production Planner`, target blank
- Four source sticker-format values are blank on target
- Four source sewing/output-type values are blank on target

Formatting-only differences:

- `partial_received_percentage`: `90` versus `90.0`
- `partially_dispatched_percentage`: `90` versus `90.0`

The source-only YRP API URL/key/secret are intentionally excluded.

## Runtime blocker

Target `Message Log` currently contains:

| Status | Count |
|---|---:|
| Processed | 123,266 |
| Pending | 187 |
| Failed | 653 |

The 653 failures are historical attempts dated up to 2026-07-31; many may have
later successful replacements. The 187 Pending rows are still unresolved.

`bench --site essdee_yrp.site scheduler status` reports that the scheduler is
disabled. Spine's Event Dispatcher can receive Kafka events, but scheduled
message processing cannot drain Pending rows while the site scheduler is
disabled. A full ordered initial sync is also required because many master
DocTypes were last bulk-synced in July and the current F15 dataset is newer.

## Required gate before historical migration

1. Enable the target scheduler and prove Pending messages drain.
2. Run the ordered source sync in `SD_YRP_INITIAL_SYNC_ORDER`.
3. Resolve current failures rather than trusting old Failed rows.
4. Rerun this identity and mapped-value comparison.
5. Start historical SQL migration only after every source identity is present
   and every mapper-specific comparison passes.
