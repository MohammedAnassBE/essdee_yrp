# SD YRP Spine Field-Value Audit

Audit date: 2026-08-14
Source: F15 `mrp3.site` / `production_api`
Target: F16 `essdee_yrp.site` / `essdee_yrp`
Topic: `sd_yrp_master`

## Question answered

This audit checks whether the existing Spine path carries the complete values
of each synchronized document. It compares parent fields, every child table,
each child field, renamed/derived mappings, and populated fields that the
target schema or custom mapper drops. Document-count parity is covered by the
separate identity audit and is not treated as proof of field parity here.

The reusable read-only probes are:

- `scripts/sd_yrp_field_snapshot.py` — runtime metadata and populated-field
  statistics on either Frappe version.
- `scripts/compare_sd_yrp_field_values.py` — cross-site parent/child value
  comparison for records that exist on both sites. It ignores only child-row
  names for approved compatibility mappers; child order and business values
  are compared.

## Verdict

The answer before remediation was **no**: not every populated source value was
being stored on F16.

- 22 of the 31 DocTypes use the generic exact mapper. For fields available on
  both schemas, it copies all scalar values and recursively replaces every
  child table included in the payload.
- Nine DocTypes use custom mappers. Production Order's 25 source scalar fields
  and all five child tables are covered, but its ordered-row `lot` value was
  missing from the direct target field.
- Six business-data gaps were confirmed from live populated records and fixed
  in code. One additional business identity field (`User.telegram_user_id`)
  was absent from the target schema and is now packaged.
- User authentication/session data remains deliberately partial. Passwords,
  API credentials, reset keys, sessions, social-login state, and source-site
  activity metadata must not be copied to another site by this master sync.

## Confirmed gaps and remediation

| DocType / field | Live source evidence | Previous behavior | Remediation |
|---|---:|---|---|
| Production Order → Production Ordered Detail `lot` | 1,137/1,137 rows populated | Only `reference_doctype` + `reference_name` were set; target `lot` was blank | Map the value to all three fields in PO sync and Lot back-fill |
| MRP Settings child tables | 3 series, 2 action-role, 3 grammage-role, 7 status-summary, 4 input-order rows | Single mapper wrote table values into `tabSingles`; no child rows were created | Delete/rebuild every supplied Single child table at DB level |
| Lot → `lot_time_and_action_details` | 818 rows under 90 Lots | Producer and consumer both stripped the whole table | Preserve and store the table end to end |
| Supplier → `supplier_users` | 50 rows under 18 Suppliers | Rows were transformed into Warehouse users but removed from Supplier | Keep Supplier rows and retain the Warehouse compatibility mapping |
| Address → `gstin` | 2,252 populated Addresses | Target had no field, so the exact mapper filtered it out | Package Essdee-owned `Address-gstin` Custom Field |
| User → `telegram_user_id` | One populated business user | Target had no field and User mapper omitted it | Package Essdee-owned field and include it in the safe User mapper |

`Supplier.terms_and_condition` and `Supplier.price_html` were also being
discarded explicitly. The target now supports both. The discard was removed;
the current source has no populated values, so no current rows were lost.

## Production Order coverage

All 25 source parent fields are accepted by the target metadata and are passed
through the current mapper, including the requested history/status/request
fields: `comment_log`, `date_change_history`,
`incoming_quantity_transfer_request`, `item`, `lot_price_overrides`,
`ppo_requested_by`, `ppo_requested_on`, `quantity_ratio_request`,
`quantity_transfer_history`, `status`, `status_change_request`,
`transferred_on`, and `transferred_to_ppo`.

Child-table handling:

| Source table | Value handling |
|---|---|
| Production Order Detail | Copies Item Variant, Quantity, Ratio, MRP, Production Order MRP, Retail Price, Wholesale Price; derives target Item and Attributes JSON |
| Production Ordered Detail | Copies Item Variant, Quantity, Lot; Lot is now stored in direct and dynamic-reference fields |
| PPO Quantity Transfer History | All 12 source fields copied unchanged |
| Production Order Date Change | All seven source fields copied unchanged |
| PPO Lot Price Detail | All five source fields copied unchanged |

The live target is not yet converged: all 186 Production Orders currently
present on both sites have a blank target `item` and target `status` differs
from source. This is stale stored data, not a current mapper omission: the
current mapper passes both fields. The same read-only audit found seven source
Production Order Items and 62 referenced Item Variants still absent on target,
so their dependency messages must land before an ordered PO republish can
succeed.

## Approved transformations and exclusions

- `IPD Process.stage` is intentionally transformed to both target `in_stage`
  and `out_stage`. The live comparison checked 808 common rows and found zero
  transformation mismatches.
- Item Production Detail's first three reshaped child tables may receive new
  child-row identities, but their business fields are preserved. Other IPD
  child tables are copied generically.
- Source-only `MRP Settings.yrp_site_url`, `yrp_api_key`, and `yrp_api_secret`
  are intentionally excluded and currently blank on the source.
- User sync is a safe account bootstrap, not a credential clone. It syncs
  identity, enabled state, available roles, user type, and Telegram identity.
  It does not copy passwords, API secrets/keys, password-reset state, sessions,
  last IP/login/activity, or social-login state. Nine source Roles do not yet
  exist on target; those roles are skipped until their master data exists.

## Live-state warning

This remediation changes the producer/consumer code but does not rewrite
already stored target rows. The identity audit recorded 187 Pending messages,
653 historical Failed messages, and a disabled target scheduler. Therefore:

1. Apply the two new Essdee Custom Fields through the normal reviewed schema
   migration/reload process.
2. Ensure all 31 dependencies are present in source order.
3. Drain/retry current messages, then run the ordered initial sync.
4. Rerun both identity and field-value audits.
5. Begin historical business-data migration only after both audits pass.

No historical migration, destructive cleanup, scheduler change, or bulk
republish was performed during this audit.

## Verification

- F15 focused producer tests: 3 passed.
- F16 focused consumer tests: 9 passed.
- Python compile checks passed for producer, consumer, tests, and both audit
  scripts.
- Fixture JSON parses successfully and contains no duplicate Custom Field
  names.
- `ruff` is not installed in either bench, so the optional lint command could
  not be run.
