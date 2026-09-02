# Essdee MRP valuation alignment and final release qualification

Date: 2026-08-25

Target app/branch: `essdee_yrp` / `MRP`

Target site: `essdee_yrp.site`

Migration source: Frappe 15 `mrp3.site` / `production_api`
Status: complete; all final acceptance gates closed

## 1. Objective and non-negotiable scope

This document is the controlling checklist for the final Essdee MRP migration
alignment and release qualification. It exists to prevent an implementation or
test step from being silently skipped.

- Base `yrp` is finalized and is **read-only for this work**. No base source,
  fixture, branch, or repository-state change is allowed.
- Product fixes, compatibility adapters, migration changes, fixtures, and tests
  belong only in `essdee_yrp` on `MRP`.
- New custom fields must be installed through tracked fixtures/DocType JSON or
  an idempotent patch as appropriate; never by an untracked site-only mutation.
- `frappe` and `erpnext` are upstream and remain untouched.
- Historical rows are preserved. A missing lineage link is kept blank unless it
  can be proved from immutable transaction evidence; migration must never guess.
- Workflow creation tests must be driven through the rendered Desk/Vue UI.
  Backend calls are allowed only where the existing UI itself calls them and for
  read-only verification of saved records, ledgers, valuation, and projections.
- “100% tested” is not claimed until every applicable gate in sections 8–11 has
  evidence and no unresolved release blocker remains.

The owner explicitly authorized a destructive reset of **only**
`essdee_yrp.site` after the fixes, followed by a fresh migration from
`mrp3.site`. The reset is still gated by backups, source freeze, target
isolation, an Analyse/Dry Run, and recorded verification.

## 2. Frozen baselines

| Component | Frozen revision/state | Release use |
| --- | --- | --- |
| `essdee_yrp` MRP | `8be20a02201f75b69a5aeb9d9167675877b7dc37` | Change target; clean and equal to `origin/MRP` at audit start |
| `essdee_yrp` develop | `60cfd7a679336ef71b5c7773443832a5e81b7250` | Read-only reference for prior Essdee valuation work; never merge wholesale |
| base `yrp` develop | `7536d315c380157fa1d90936b2f5343b9eed6481` | Finalized base API/valuation contract; read-only |
| base uncommitted overlay | tracked diff SHA-256 `849c7a8b2ca97e2fda2c97a95f5078b92c6979cd30e7a53c4d16311eea04a88b`; untracked test SHA-256 `62e3be5d399780b1f1553df65f7ee465764b468e68d8ed0d5b11c9617291d164` | Runtime dependency currently loaded by the bench; preserve exactly and require a reproducible deployment artifact before release |
| F15 `production_api` source-site branch | `5bc6a22e66b6b455a785859e8e43d79d76e1b9fb` (`develop`, clean) | Actual code/schema currently loaded by local `mrp3.site` |
| F15 `production_api` upstream develop | `5bc6a22e66b6b455a785859e8e43d79d76e1b9fb` | Refreshed current-develop comparison on 2026-08-26 |
| F15 `production_api` upstream master | `4fc8f2f366cf8dc73557b01e13c6715c52d2c856` | Read-only divergent reference, including a GRN-validation setting absent from develop |

Installed target versions at audit start: Frappe `16.10.4` on
`version-16-hotfix`, YRP `0.0.1` develop, Essdee YRP `0.0.1` MRP, Spine
`v16_master`, and YRP E-Waybill API develop. Target maintenance mode was off.

### Base repository preservation guard

The base worktree was already dirty before this work. Those files belong to the
owner/another task and must not be staged, reverted, reformatted, or included in
the Essdee commit. Final review must recompute both fingerprints above and show
that they have not changed because of this task.

## 3. Base YRP commit contract review

### `2ac9ca8` — extensible Stock Reservation Entry references

Base changed `voucher_type` from Link to Select and `voucher_no` from Dynamic
Link to Data. Essdee's scoped Property Setter fixture that supplies the allowed
voucher options (`Work Order`, `Stock Update`, `Packing Slip`) remains necessary.
Essdee must not reintroduce a field-type override.

Decision: **KEEP** the options fixture; **REMOVE/REJECT** any duplicate type
mutation.

### `7536d31` — preserve set combinations in the GRN editor

Base now groups GRN Vue rows using normalized `set_combination`, preserves the
split, and renders set labels. Essdee must not duplicate this base behavior.
Essdee's separate migrated/cutting row-index normalizer remains required because
historical garment rows were stored size-by-size with different `row_index`
values; the base set-combination change does not repair those row indexes.

Decision: **USE BASE** for set grouping; **KEEP ESSDEE** row-index compatibility
normalization, with focused tests proving it does not collapse different
received types or dimensions.

### `ec96e0c` — auditable valuation propagation

The following are now authoritative base contracts:

1. `yrp.stock.uom.resolve_item_uom`, `apply_item_uom`, and `apply_item_uoms`
   resolve transaction UOM/stock UOM and make transaction UOM read-only.
2. Strict FIFO always consumes the oldest positive layer. An `outgoing_rate`
   may value only a negative-stock fallback; it may not select a later layer.
3. `make_sl_entries` owns period closing, stable valuation-bucket locks,
   cancellation ownership guards, transfer pairing, inline execution, and
   returned posting details.
4. Base owns Stock Valuation Adjustment, Closing, Production Link, and
   Propagation documents.
5. Base owns generic Delivery Challan-backed GRN returns and Work Order pending
   rebuilds.
6. Base mapped GRN valuation is active only when `grn_deliverables` carry a
   deterministic `goods_received_note_item` link. The mapped route consumes
   actual FIFO input, receives output at material plus process cost, persists
   material value and SLE lineage, and registers production links.
7. Goods Received Note Item owns current valuation fields.
8. Purchase Order/Purchase Invoice rates and late material/process cost
   adjustments belong to base.
9. Stock Entry owns both actual source and target location pairs for “Send to
   Warehouse”; `transfer_supplier` remains a reference only.
10. Work Order transaction UOM is normalized by base.
11. Writes, cancels, and reposts on/before an active valuation closing cutoff
    are rejected.

Essdee must call these contracts, not retain parallel valuation logic. Company
workflow semantics—cutting allocation, printing identity conversion, finishing
direct return, sewing/rework projections—remain Essdee-owned.

### Runtime overlay after `ec96e0c`

The currently loaded but uncommitted base overlay additionally:

- activates mapped GRN valuation only when **all** custom deliverable rows have
  `goods_received_note_item`;
- preserves explicit selected warehouses on internal transfers;
- uses `stock_uom` when a Stock Entry row provides it;
- hardens DC pending rebuild/locking and GRN cancel/quantity validation; and
- separates same-row-index GRN display rows when dimensions/received types
  differ.

This all-rows guard matches the historical migration rule: old rows may remain
blank and continue through the legacy path, while newly generated documents
must be completely and deterministically mapped. The base overlay is a release
dependency and must become a reproducible committed/deployed artifact outside
this Essdee-only task.

## 4. Production API comparison

The actual migration-source repository (`mrp3.site`) is now clean on
`production_api` develop revision `5bc6a22e`, equal to `upstream/develop`.
Essdee MRP already contains the worker-strength report, MRP HR
Shift/configuration, Sewing Strength APIs/UI/tests, and the Cut Bundle Layer
Sheet workflows from the preceding source commits.

The new `5bc6a22e` commit deliberately keeps a draft Production Order editable
while its status is `PPO Request`. It removes the server prohibition on editing
a pending request and the matching client-side editor exclusion, while keeping
the status-spoof guard authoritative. Essdee still contains both removed
conditions and must port this narrow behavior without weakening its additional
create/manage permission checks.

One important branch discrepancy exists: production_api master contains
`75d6b84e` (“exempt configured suppliers from GRN quantity validation”), but
neither current develop nor the source-site branch contains it. It adds the
`GRN Quantity Validation Exempt Supplier` child configuration to MRP Settings
and bypasses sewing-plan quantity validation for explicitly configured
suppliers.

Decision: add a migration-compatible Essdee fixture/schema and server-side
guard with tests, because the owner explicitly identified this MRP
Settings/GRN behavior as release-relevant. A source with no rows migrates to an
empty list and therefore preserves the current strict behavior.

## 5. Redundancy and conflict matrix

| ID | Current Essdee area | Finding | Action |
| --- | --- | --- | --- |
| A01 | `fabric_grn.py` | Builds unlinked GRN Deliverables and separately posts legacy SLEs; this duplicates base mapped valuation for new documents. | CHANGE: build complete mapped lineage for new fabric GRNs; retain legacy submit/cancel only for historical all-unmapped records. |
| A02 | `garment_grn.py` | Printing/identity receipts create consumption without output-row links, so mapped valuation never activates. | CHANGE: deterministic input-to-output mapping and base valuation route. |
| A03 | Cutting LaySheet → GRN | Cloth/accessory consumption is not allocated to exact received output rows. | ADD: deterministic proportional allocation, with residual on the final row; preserve exact input total and give every output lineage. |
| A04 | Packing GRN | Already maps output row and stock dimensions. | KEEP; add contract tests and use shared mapped-plan apply/cancel path. |
| A05 | YRP GRN Deliverable schema | `goods_received_note_item` is hidden Data; no `received_item_variant`. Frappe child-table DocTypes cannot be Link targets. | CHANGE via tracked schema: keep exact GRN Item and Work Order child identities as hidden optional Data, add optional received-variant Link, and validate child ownership server-side. Never make historical lineage required in metadata. |
| A06 | Migration transformer | Correctly derives dimensions and leaves unknown lineage blank. | KEEP; test blank historical links remain blank and supplied exact links survive. |
| A07 | GRN Work Order stock update | Fabric-only legacy hook updates Work Order consumption; other mapped processes can diverge. | CHANGE: one idempotent, locked, generic mapped-consumption apply/reverse for fabric, cutting, printing, and packing. |
| A08 | Fabric GRN calculation | Aggregation can merge demand from distinct output rows. | CHANGE: retain exact output receipt identity throughout calculation; never aggregate across output rows. |
| A09 | Generated fabric Work Order UOM | Base can overwrite quantity semantics before Essdee converts source UOM quantity to the item transaction UOM. | CHANGE: normalize generated row quantities before consolidation/save, then apply base UOM contract. |
| A10 | Lot Transfer | Preflight valuation rate is persisted instead of the actual FIFO transfer result. | CHANGE: use paired transfer keys and returned outgoing/incoming SLE result; persist actual stock-UOM rate, amount, and dimensions. |
| A11 | Finishing direct GRN return | Broad no-DC return detection conflicts with base generic return validation; warehouse defaults and SLE pairing are incomplete. | CHANGE: specialize only `from_finishing=1`, `is_return=1`, no-DC returns; derive explicit source/target warehouses; pair transfer entries; keep base guards elsewhere. |
| A12 | Generic DC-backed return | Base now owns it. | REMOVE/AVOID Essdee duplication; UI and tests must use the base action and pending rebuild. |
| A13 | Rework received-type conversion | Direct stock movement needs exact pairing and actual FIFO value propagation. | CHANGE/VERIFY: transfer keys, returned valuation, dimensions, cancel symmetry, closed-period guard. |
| A14 | Other direct stock paths | Recut, finished-goods creation, item conversion, CLS, and no-DC finishing paths call stock ledger directly. | AUDIT each for authoritative UOM, paired movements, period gate, force-inline boundary, result lineage, and cancellation ownership. |
| A15 | Work Order close | Current MRP clips/updates consumption without recording excess FIFO cost into exact outputs. | CHANGE: port only the reviewed Essdee valuation-aware close concepts; post full excess or fail; persist SLE/value/dimensions, production links, valuation adjustment, and reason. |
| A16 | Historical Work Order close | Old outputs may have no deterministic lineage. | KEEP a safe explicit legacy route/report; never manufacture production links. |
| A17 | GRN editor | Base owns set-combination grouping; Essdee owns migrated row-index normalization. | REMOVE no base duplication; KEEP scoped normalizer and regression coverage. |
| A18 | Stock Entry source/target fields | Base now owns actual From/To supplier/warehouse visibility. | KEEP no Essdee duplicate field/property setter; retain only Essdee purpose/options/additional-amount semantics. |
| A19 | SRE reference fields | Base owns generic field types; Essdee owns allowed business voucher values. | KEEP only the scoped options fixture. |
| A20 | Setup/install | MRP setup lacks a full valuation contract assertion. | ADD idempotent setup validation without mutating base metadata. |
| A21 | Historical lineage backfill | Multi-output history cannot always be inferred safely. | ADD readiness/reporting and backfill only exact single-output/provable pairs; unresolved rows remain blank and reported. |
| A22 | Supplier GRN exemption | Present only on production_api master, absent from source/develop and current MRP. | ADD optional fixture/configuration + server enforcement + authorized tests; empty config remains strict. |
| A23 | Base dirty runtime dependency | Site behavior is ahead of base HEAD without a reproducible base commit. | BLOCK RELEASE until owner supplies/records the deployable base artifact; do not change it in this task. |
| A24 | Attachments | Local source DB has 1,004 File rows but only two locally available physical blobs. | MIGRATE/AUDIT metadata; mark archive transfer as an external production gate—local testing cannot prove missing blobs. |
| A25 | MRP Data Migration Desk actions | Required Source/Target fields were populated only in server `before_insert`, so Desk mandatory validation blocked a UI-created audit run. The action builder also assumed Frappe 16 `add_custom_button` returns a jQuery object and raised a page error while disabling unavailable actions. | FIX in Essdee: expose only the server-owned non-secret profile identity to System Managers, populate read-only fields on new-form refresh, keep server validation authoritative, and render only currently valid actions without dereferencing the button return value. |
| A26 | Cutting Laysheet Planner runtime schema | Live `mrp3.site` contains Lot, Description, and Item standard fields added on 2026-08-25, but production_api JSON does not contain them; Analyse therefore found three target-field blockers. | ADD the exact fields to the Essdee-owned tracked DocType JSON and test them. Do not mutate the source or base YRP repositories. |
| A27 | Lineage readiness alert | The initial patch treated healthy total/fully-mapped counters as unresolved because it used `any(readiness.values())`. | FIX: alert only on explicit missing, partial, ambiguous, invalid, contract, or unpaired counters; cover the fully-mapped case. |
| A28 | Post-load lineage timing | A normal framework patch runs before the migration engine loads legacy documents, while the preserved Patch Log prevents it from rerunning after the reset. | FIX: retain the install patch, and also run the same idempotent/provable-only backfill inside the successful Migrate phase before completion; persist its readiness result in the run report. |
| A29 | Historical Planner descriptions | All seven source Planners predate the new required Description field and store a genuine blank. The first full Dry Run reported exactly those seven rows. | PRESERVE/AUDIT that exact DocType-field blank during migration; keep Description required for all new target records. |
| A30 | Missing-blob UI policy | The runner supports strict vs audited missing-source-blob handling, but Desk jobs always used strict mode; the prior rehearsal required a manual runner call. | ADD an explicit default-off, create-time-only audit flag and pass it identically to Dry Run/Migrate. Use audited omission only for this documented local archive gap; production remains strict. |
| A31 | Empty new mapped plan | A selected new Essdee consumption planner could return no rows, leaving base mapping inactive and silently posting an output-only legacy receipt. | BLOCK submit whenever positive output exists but the selected cutting/packing/identity/fabric planner returns no deterministic consumption; historical all-unmapped GRNs retain their explicit compatibility route. |
| A32 | Reset/backfill population scans | Frappe `get_all` defaults to a page limit; an omitted explicit limit could inventory only the first page of attachments or historical lineage rows while presenting an incomplete result as exhaustive. Loading every child identity just to classify roughly one thousand attachments would also consume unnecessary memory on the 2.8M-row child graph. | FIX: every full-population reset/backfill query is explicitly unbounded; attachment ownership queries only the child identities named by File rows, in bounded chunks. Post-reset verification checks the exact pre-reset File identities. |
| A33 | Dry-run prerequisite drift | The initial frozen snapshot bound source data, code, schema, and server defaults, but a stored IPD/Stock Settings value could change to another valid value after Dry Run. | FIX: hash the complete validated target-prerequisite payload, including the exact Lot/Received Type stock-dimension flags, into the Dry Run snapshot; Reset, Migrate, and Verify require an exact match. |
| A34 | One-time reset acknowledgement parsing | Plain Python truthiness would treat a string configuration value of `"0"` as enabled. | FIX: parse the server-owned flag as an integer/check value and prove `"0"` is disabled and `"1"` is enabled. |
| A35 | Naming-series reset safety | The first complete Dry Run proved that 166/172 source counters were already equal to or behind the target, including the real blank identity (`target=5207`, `source=5023`). Deleting source-named target counters before the documented `GREATEST(target_current, source_current)` merge would therefore reuse established identifiers and contradict the migration contract. | FIX: reset deletes no `tabSeries` row. Snapshot every target name/current pair, including the blank identity, exclude counters from the deletion total, and exact-verify the complete snapshot after reset. Migrate then advances only counters that are behind the source. |
| A36 | Reset File progress accounting | The reviewed File lifecycle loop added the whole chunk length after each individual File deletion, inflating visible progress by up to 50× even though the deletion scope itself was correct. | FIX: advance exactly one record per successfully lifecycle-deleted File and prove the cumulative File/warehouse/child/parent sequence in a focused regression test. |
| A37 | Reset retry identities | A generated supplier Warehouse was originally inventoried through an inner join to Supplier, so a retry could miss an orphan if a prior partial attempt had already deleted that Supplier. | FIX: use the deterministic nonblank `Warehouse.name = Warehouse.supplier` identity without requiring the linked Supplier row. |
| A38 | Post-reset scope | Rechecking only pre-preview File/Warehouse names proves those identities disappeared but does not detect a newly introduced in-scope row. Re-inventorying only current child ownership can also miss a reviewed File after its child row has been removed. | FIX: the postcondition is the union of every original reviewed identity still present and a complete current-scope re-inventory; any remaining or new row fails reset. |
| A39 | Queued preflight failures | Job failure handling began after the worker marked Running, so a code/settings/source-maintenance failure during preflight could leave the audit record stuck Queued with its previous action. | FIX: record the intended action when queued, enqueue only after that transaction commits, and execute through guarded entrypoints that turn every Queued/Running preflight exception into a retryable Failed state. |
| A40 | Stock-dimension check parsing | Python truthiness treats the serialized check value `"0"` as true. | FIX: parse every mandatory/valuation/production-group flag with Frappe's numeric check parser and prove string `"0"` remains false. |
| A41 | Reset File queue saturation | Standard `File.delete()` enqueued one dynamic-link cleanup job per row; the first `00007` reset reached the queue's 900-job ceiling and rolled back the active chunk. That failed attempt also correctly created 900 File `Deleted Document` rows and 900 `Attachment Removed` comments before the exception. | FIX: retain File-owned protected-file and physical-blob cleanup, delete metadata without enqueueing, remove dynamic links synchronously, preserve the original reset-start checkpoint, and include only the retry-generated File audit rows in preview/deletion/postconditions. The retry crossed the former 900-row boundary, processed 6,348,334 reviewed rows with zero failures, and left no queued cleanup jobs. |
| A42 | Contextual target child reset scope | The reset manifest collected only direct child-spec targets. `Item Production Detail.item_attributes` contextually maps source `Item Item Attribute` rows to target `IPD Item Attribute`, so five old UAT child rows for a no-longer-present parent survived reset and were caught only by the final target-only verification. | FIX: include every table DocType referenced by each migration-owned target parent's schema in the child reset manifest, while retaining the existing `parenttype` scope. Add a focused contextual-child regression and repeat the complete reset/migrate/two-pass Verify cycle from a fresh reviewed boundary. |
| A43 | Fresh reset checkpoint timestamp | Retry checkpoints already contained a string timestamp, but a brand-new reset used `now_datetime()` directly and attempted to JSON-encode the resulting Python `datetime`, failing before the first delete. | FIX: normalize `reset_started_on` to its stable string form at the checkpoint boundary and prove a fresh reset timestamp serializes exactly. The failed `00008` attempt processed no reset row and the one-time flag was disabled immediately. |
| A44 | Failed reset Desk retry | The form rendered `Reset Target Data` after a failed reset, and the server reset method allowed that retry, but the required preview endpoint accepted only `Dry Run Complete`; the rendered retry path therefore stopped before confirmation. | FIX: use one shared state predicate for preview and reset. Accept only a completed Dry Run or `Failed` with `last_action = Reset Target`; reject every other failed action. Add a focused state-matrix regression. |
| A45 | Desk sidebar startup | Frappe v16 sends divider and failed-condition sidebar definitions through its image renderer, producing `<img src="undefined">`, a `/undefined` 404, and a console error on every Desk form load. | FIX in Essdee only: install a pre-`start_app` prototype guard that filters dividers, false conditions, and definitions without either icon form. The focused source contract and the rebuilt live Production Order form both pass; the live browser produced zero `/undefined` requests and zero console errors. Upstream Frappe remains untouched. |
| A46 | Production Order PPO Request editing | Current `production_api` develop `5bc6a22e` allows ordinary field edits while PPO approval is pending but still rejects client-spoofed status transitions. Essdee retains the removed server edit prohibition and client `status !== "PPO Request"` condition. | CHANGE: port only this new develop behavior, preserve Essdee create/manage permissions and status-spoof protection, and add server/client source regressions. |
| A47 | Draft identity/printing GRN planning | Hook order runs `fabric_grn.before_validate` before `garment_grn.before_validate`. An identity garment receipt currently qualifies for both, so the generic draft plan performs redundant calculation/queries and is immediately overwritten. Identity matching also falls back to an unrelated single candidate when an explicitly supplied set combination, Lot, or Received Type has no match. | CHANGE: exclude identity garment GRNs from the fabric draft planner and make every explicit identity key a strict filter; mismatch must fail, never silently broaden. |
| A48 | New mapped GRN ownership and concurrency | Base proves the mapped GRN item belongs to the current receipt but does not own Essdee's Data-typed Work Order child link or received-variant/dimension contract. Sewing quantity validation also runs before the Work Order is locked, so concurrent receipts can both pass the same cap. The Work Order `stock_update` helper claims retry idempotency without a persisted lifecycle state. | CHANGE: lock the Work Order before any quantity/plan preflight; validate exact GRN item, output variant, Work Order child ownership, input item/UOM, and every stock dimension before base posting; persist an Essdee mapped-stock-update state so submit/cancel hook retries cannot double-apply. Historical state `0` remains cancellable and no lineage is fabricated. |
| A49 | Cutting LaySheet mapped GRN association | `calculate_cutting_consumption_plan` trusts the GRN's `against_id` independently of the LaySheet's Cutting Plan. A crafted payload can combine a valid LaySheet with a different Work Order whose inputs happen to match. | CHANGE: prove the saved LaySheet's Cutting Plan belongs to the exact GRN Work Order before allocating any input. |
| A50 | Recut and Print Panel UOM valuation | The controller sets both transaction and stock UOM to the Item default, requests a transaction-UOM-converted balance rate, then uses it as the stock-unit `outgoing_rate` while `weight` is posted as physical stock quantity. A non-1 Item conversion therefore misvalues the issue. | CHANGE: resolve the base Item UOM contract, retain `weight` as stock quantity, request the unconverted stock-UOM rate, and post the authoritative stock UOM/rate; add a non-1 conversion regression. |
| A51 | Lot Transfer transient dimension payload | Validation assigns `row.stock_dimensions`, but `Lot Transfer Item` has no such field; the value is discarded and can mislead later code/review into assuming a persisted audit payload. Exact configured dimension columns already persist and drive both SLEs. | REMOVE the non-persistent assignment and prove the source/target rows still use the exact dimension map. |
| A52 | MRP migration action serialization | Desk action methods check in-memory status without a locking reload and enqueue before atomically reserving the run. Concurrent requests can enqueue the same action twice; distinct audit records can also begin overlapping long jobs. | CHANGE: serialize action reservation, reload status under lock, atomically mark Queued/Analysing before work becomes runnable, reject another active run, and add same-run/cross-run state regressions. |
| A53 | New Cutting LaySheet rendered UI | The new-form script calls `LaySheetCloths.load_data([])`, while the Vue component dereferences `item_detail.manual_items` and then calls `Object.keys(undefined)`. Opening a fresh LaySheet raises a page error before the user can enter cloth. | FIX both sides of the component contract with an empty structured default and a source regression; later re-prove the rendered new form has zero page/console errors. |
| A54 | Work Order close output ownership | Excess-usage allocation reads an SLE named by mapped lineage but the final lookup does not explicitly require an active GRN receipt owned by that mapped GRN/output variant. | HARDEN: carry the exact GRN/output identity into each allocation and accept only a positive, active Goods Received Note SLE owned by that voucher and item. Add no-excess retry and invalid-output regressions. |
| A55 | Work Order close authorization | The Essdee override inherits base's role-driven close/request behavior and saves with ignored permissions, but it does not first require write permission on the selected Work Order. Any authenticated caller could reach the request route even when DocType/User Permissions deny that record. | HARDEN in Essdee: require authoritative Work Order write permission before returning status, requesting close, or manager close; retain the configured approver-role decision and add a denial regression. |
| A56 | Mapped-GRN completeness dispatch | The newly introduced `_has_complete_mapped_consumption` helper imports base's mapping predicate but does not return its result; the intended return was displaced below `_claim_mapped_stock_update_transition` and is unreachable. Real mapped submissions therefore skip Essdee ownership validation and persisted-plan loading even though tests that mocked the helper remained green. | FIX before any migration or UI flow: restore the exact guarded return in the helper, remove the unreachable block, and add an unmocked regression that proves both the Work Order guard and base predicate dispatch. |
| A57 | Legacy packing mapped-plan UOM | Packing availability and fixed-ratio allocation are physical piece/stock quantities, but the mapped row currently stores that number as `quantity` in the matched Work Order Deliverable's transaction UOM and then multiplies it again through `_stock_uom_values`. A 20-piece allocation against a 10 Pieces/Box deliverable becomes 20 Boxes / 200 Pieces. | CHANGE: resolve the matched input's conversion, persist physical allocation unchanged as `stock_qty`, persist `quantity = stock_qty / conversion_factor`, and cover a non-1 packing conversion. |
| A58 | Work Order-close exact output child | The hardened close lookup proves the mapped output SLE's GRN voucher and item variant, but it does not carry or require the exact mapped `goods_received_note_item`. Two same-variant receipt rows in one GRN can therefore satisfy the ownership filter without proving the SLE belongs to the mapped output child. | HARDEN: carry the mapped GRN item identity through allocation and require `Stock Ledger Entry.voucher_detail_no` to equal that exact child, in addition to voucher, item, direction, and active state. |
| A59 | Reset retry audit-row scope | Retry inventory selects every `Deleted Document` for File and every `Attachment Removed` Comment created after `reset_started_on`. That timestamp is not ownership: unrelated target activity after the same time can be counted and later deleted. The current `for_reload=True` reset lifecycle creates neither audit type, so a broad compatibility sweep is unnecessary and violates the migration-owned-only reset boundary. | CHANGE: inventory only explicit audit-row identities stored in the reset checkpoint, intersect them with rows that still exist, preserve those exact lists across retry, and never discover deletion scope from a timestamp. |
| A60 | Mapped-GRN cancel ownership gate | Submit validates the complete Essdee mapping before base posting, but cancel activates from base's output-link predicate and loads persisted rows without revalidating the exact Work Order child, received variant, UOM conversion, output coverage, or dimensions. A partially mapped historical document can therefore enter the mapped reversal path before failing later in bookkeeping. | CHANGE: under the same Work Order lock, run the complete ownership validation before base mapped cancellation or loading/applying the persisted plan. |
| A61 | Direct finishing-return deliverable identity | `_find_deliverable` trusts an explicit Work Order child name without proving the returned item/UOM/combination matches it; without a reference it returns the first matching item/combination even when several Work Order rows remain. Submit/cancel can therefore update an arbitrary pending row while stock posts for another logical row. | HARDEN: validate every explicit reference against the returned row, resolve an unreferenced row only when the business key is unique, and reject mismatched or ambiguous rows. |
| A62 | Cutting consumption before input delivery | The Cutting LaySheet planner caps consumed cloth at `Deliverable.qty - stock_update` and ignores `pending_quantity`. If the same stock bucket already contains stock, a LaySheet GRN can consume a planned Work Order input that was never delivered through the cutting DC, violating the required PO/Lot/IPD/WO/DC/Marker/LaySheet order. | CHANGE: calculate cutting availability as delivered transaction quantity (`qty - pending_quantity`) minus mapped `stock_update`; stock balance remains the separate physical authority. Add an undelivered-input regression. |
| A63 | Cutting duplicate input resolution | Cutting maps calculated Work Order inputs through a dictionary keyed only by `(item_variant, uom)`. Multiple same-item/UOM rows—potentially with different Stock Dimensions—silently overwrite each other and the last child receives all mapped consumption. | HARDEN: retain all candidates and require one exact calculated Deliverable for each weighed input; ambiguous input rows must be corrected rather than selected by row order. |
| A64 | Dead pre-mapped GRN converter | After cutting, packing, fabric, and identity planning moved to `populate_grn_deliverables` under the override controller, `_to_grn_deliverables` and its private `_stock_uom_values` helper have no caller. Retaining them duplicates the old unmapped/first-row planning model and invites accidental reuse. | REMOVE both unreachable helpers; historical submitted documents continue through `_apply_consumption`, which does not call them. |
| A65 | Historical mapped-GRN cancellation state | Review initially questioned whether `mapped_stock_update_state = 0` should skip the Essdee Work Order decrement. The F15 source contract proves the legacy GRN hook already applied `Work Order Deliverable.stock_update`, and migration imports that counter with the Work Order. | KEEP cancel-from-zero as a real reversal: run base stock cancellation, subtract the imported legacy Work Order counter once, and persist `-1`. A focused state-matrix regression prevents a future “base-only” interpretation. |
| A66 | Historical lineage SLE ownership | The conservative backfill accepts an explicitly stored `consumption_sle` after checking only that the named row exists and is outgoing. A stale or malformed historical reference could therefore register an active production edge from another voucher, child, or item. The single output lookup likewise needs the output item in its ownership filter. | HARDEN: accept only one active outgoing SLE owned by the exact GRN, YRP GRN Deliverable child, and input item; accept the output SLE only when the exact GRN Item and output item own it. Unproved references remain blank and reported. |
| A67 | Lot cloth-program excess persistence | The cloth-program builder returns the selected excess percentage and rebuilds requirements, but does not persist that selection to `Lot.cloth_excess_percentage`. A later form reload can therefore show/use a different value from the calculation just saved. | FIX: persist the selected percentage on the same Lot save and prove it through the cloth-program integration test. |
| A68 | Work Order Delivery Challan address defaults | The Essdee Work Order action delegates item defaults to base but omits the Work Order's already-selected source and supplier address identities/details. The rendered Delivery Challan then reaches mandatory address validation without the transaction's authoritative addresses. | FIX: copy the four saved Work Order address values into the UI defaults; keep base item/pending logic authoritative. |
| A69 | Cutting Marker delayed Vue controls | The marker component schedules control creation and an async callback without an unmount guard, and validates selected panels against a module-load snapshot of `calculated_parts`. Form refresh/unmount can therefore dereference removed elements or validate against stale panels. | FIX: cancel behavior through an active-component guard, null-check delayed control targets/callbacks, and read the current form panel value. Re-prove in the rendered marker flow later. |
| A70 | Process-scoped garment accessory BOM | The caller asks for accessories for selected Work Order processes but the BOM calculator evaluates every IPD BOM row before the caller filters the result. An unrelated process with an invalid/inapplicable attribute mapping can therefore block a valid Work Order calculation. | FIX: pass the selected process set into the calculator and skip unrelated BOM rows before variant/mapping evaluation; retain the caller's final process filter as defense in depth. |
| A71 | Legacy GRN Work Order input resolution | The historical all-unmapped compatibility route trusts an explicit `work_order_deliverable` without validating its item/UOM/combination/dimensions. Its fallback also retains broader candidates when an explicitly stored combination or dimension has no match. A malformed migrated row can therefore update the wrong Work Order counter on submit/cancel. | HARDEN: validate saved child identities against the complete stored business key and make every explicit legacy filter strict; mismatch fails for review instead of broadening or selecting by row order. |
| A72 | F15 same-instant GRN SLE order | Fresh audit `00010` proved 98,882 exact outgoing GRN SLEs exist, but candidate single-output vouchers commonly store the positive output row before the negative input row at the same `posting_datetime`. A first Essdee-only relaxation reached the finalized base `register_production_links` guard, which independently rejects that chronology. Bypassing or duplicating the finalized base causal contract would activate valuation edges that base YRP does not accept. | KEEP those historical rows wholly unmapped and explicitly reported, exactly as the owner allowed for legacy rows without a safe GRN Item mapping. Require Essdee's preflight to mirror the base `(posting_datetime, creation)` order so no partial child mapping is written before registration. New transactions remain fully mapped by the normal base contract. |
| A73 | Frozen migration contract coverage | The Dry Run fingerprint binds migration modules and the F15 bridge but omits the post-load valuation-lineage patch that Migrate executes. A backfill code change could therefore reuse a stale Dry Run fingerprint. | FIX: include the exact post-load backfill source in the migration contract digest; repeat Analyse/Dry Run/reset/migrate after this finding before accepting `00010` or any later run. |
| A74 | Completion Stock Entry rendered rows | Base DC/GRN completion copies string source indexes such as `matrix-0001` into the integer `Stock Entry Detail.row_index`; every row becomes zero, so the grouped Vue editor renders only the first parent Item even though all child rows exist. | FIX in Essdee only: normalize every DC/GRN Completion child to a distinct integer index during validation and repair the read-only onload payload for existing drafts. Keep base YRP untouched and prove both the four-row rendered draft and normal Stock Entry non-interference. |
| A75 | LaySheet single-option set-combination value | The LaySheet cloth editor visibly renders the only valid `Major Colour`/`Set Colour` Select option but leaves the Frappe control value empty. A user therefore sees `White` yet **Add Item** throws `Enter the Set Combination`; the first UI attempt wrote no cloth child. | FIX in Essdee's Vue editor: when a dynamic Select has exactly one non-empty valid option and no authored default, commit that option to the control. Preserve explicit user choice whenever multiple options exist; rebuild assets and re-prove Top, Sleeve, Rib, and Bottom rendered entry. |
| A76 | Cutting custom-permission override | Essdee created only a System Manager `Custom DocPerm` to restore cancel authority. In Frappe, the first custom permission replaces the entire standard DocPerm set, so Store User and Store Manager silently lost their standard Cut Panel Movement submit authority; assigning the correct Store role still rendered no Submit action. | FIX in Essdee setup only: mirror every standard DocPerm row into Custom DocPerm before applying the intended System Manager cancel/submit override. Preserve floor-role authorization and keep base YRP untouched; prove the effective permissions and rendered Submit action. |
| A77 | CBML availability groups raw JSON text | Cut Panel Movement availability grouped `set_combination` as raw SQL text. Initial LaySheet rows retain marker metadata/compact JSON while later Stock Entry rows carry the same major-colour/part business identity with reduced/spaced JSON, so the zero-balance movement and positive opening became separate groups and consumed S-0164 bundles reappeared selectable. | FIX in Essdee only: select the latest CBML row by canonical major-colour/part business identity in Python, matching the existing ledger-history comparator, for both exact and collapsed availability. Add a whitespace/key-order/extra-marker-metadata regression and prove source zero/target exact availability after movement. |
| A78 | CPM → DC UI loses exact split | `build_delivery_challan_defaults` returned the correct CPM subset, but opening the new Delivery Challan triggered the base Work Order field fetch asynchronously and replaced that subset with every pending Work Order size. The first 50-piece split visibly became 120 before save. | FIX in Essdee's CPM form handoff only: after the base fetch settles, restore the prepared `item_details` for both Delivery Challan and GRN, clear the transient child rows, remount the matrix, and mark the form dirty. Keep base YRP untouched; prove S/M only in the rendered draft and submitted DC. |
| A79 | Exact bundle return has no rendered CPM link | Base Return creates the correct draft GRN and Essdee/server bundle validation supports linking a submitted CPM, but the `cut_panel_movement` field was hidden. The only rendered path therefore always became an implicit collapsed-bundle return; an operator could not select the exact bundle CPM used by the tested server lifecycle. | FIX in Essdee GRN JS only: show the CPM Link only on editable Return GRNs, filter it to an unlinked submitted CPM from the returning supplier/Lot, and explain that selecting it means exact whole-bundle return while leaving it empty means collapsed return. Preserve server validation and keep base YRP untouched. |
| A80 | Collapsed CPM UI flag serialized as text | The Cut Panel Movement form called the availability API with `get_collapsed: true`. Frappe's rendered `frappe.call` serialized that browser boolean as the string `"true"`, while the server reads the flag with `cint`; `cint("true")` is zero. The live UI therefore returned HTTP 200 but never rendered a collapsed bundle even though the same read-only method called with numeric/typed truth showed the balance. | FIX in Essdee CPM JS only: send `get_collapsed: 1`, which preserves the existing API contract and survives browser serialization. Recover and reuse the already-created draft rather than duplicating it; prove the rendered collapsed row can be selected and submitted. Base YRP remains untouched. |
| A81 | Saved CPM Delivery Challan cannot reopen | Base DC deliberately retains zero-size matrix rows across ordinary draft saves. A CPM-prepared DC has a narrower submitted-movement scope, but its generated zero placeholders persisted numeric `0` into Link fields such as `ref_doctype`; the immediate-session Submit path worked, while reopening the saved draft failed with authenticated `DoesNotExistError: DocType 0 not found`. | FIX through an Essdee-only Delivery Challan subclass: before base onload grouping, and after base Vue sync/before persistence, remove only zero-quantity rows when `cut_panel_movement` is set. Ordinary Delivery Challans retain base draft re-edit semantics. Recover the same draft, prove authenticated getdoc changes 404→200, and cover CPM/ordinary behavior with focused tests. Base YRP remains untouched. |
| A82 | Collapsed internal-unit DC Completion loses transaction mode | The rendered completion flow for collapsed Stitching DC `DC-2026-00023` created `YRP-STE-2026-00055` with the correct CPM link but `allow_non_bundle=0`. Essdee's completion adapter copied only `cut_panel_movement`, so Submit re-entered exact whole-bundle validation and failed with `Top Front / White / M: transaction quantity 30.0 does not match the selected whole-bundle quantity 0.0`. The HTTP 417 rolled back Submit and left the recoverable draft. | FIXED in Essdee only: completion validation now inherits both CPM identity and the authoritative collapsed/non-bundle mode from the referenced DC/GRN even for an already-saved draft, and forces a spoofed client flag back to the source value. All 15 bundle-filtering unit tests pass. The same UI draft then submitted successfully and exact independent SLE/CBML verification passed. Base YRP remains untouched. |
| A83 | Stitching GRN has no deterministic input-consumption planner | Rendered retry of partial Stitching GRN `YRP-GRN-2026-00055` passed the Sewing quantity prerequisite but Submit returned HTTP 417: `No deterministic fabric consumption plan was found for this receipt.` The Essdee dispatcher classified every ordinary Work Order GRN that was not Cutting, Packing, or identity conversion as generic fabric. Stitching was explicitly excluded from identity conversion, yet had neither a fabric step nor a fabric identity row, so that planner returned an empty plan. The transaction rolled back and retained the same recoverable five-row, 50-piece draft with no SLE. | FIXED in Essdee only: the configured IPD Stitching process now has its own deterministic planner backed by the same authoritative garment Work Order calculation engine. Every positive received row must own an exact Work Order Receivable; every calculated panel/accessory input must match one exact delivered Work Order Deliverable by item/UOM/set combination and remaining balance. Stitching is excluded from generic fabric planning. All 35 valuation-contract unit tests pass, the same rendered draft submitted with 30 mapped inputs, and complete SLE/value/counter/production-link/internal-transfer verification passed. Base YRP remains untouched. |
| A84 | Stitching planner rejects supported non-default output Received Type | S19 used the rendered GRN editor's **+ Misstitch** split and entered 5 per size, with the default Accepted split at zero. Draft Save returned HTTP 417 before insert: `Received row 1 received_type does not match Work Order Receivable ...`. The A83 output-ownership matcher treated the Work Order receivable's default `Accepted` stock bucket as immutable, even though the base GRN editor intentionally permits a receipt to split one pending receivable into another configured Received Type. No GRN/SLE was written and Stitching pending remained 70. | FIXED in Essdee only: referenced receivable ownership, item, UOM, Lot, and set combination remain strict, while the new output Received Type may differ from the receivable template's default type. All 36 valuation-contract unit tests pass, including the focused non-default-output regression. The same rendered flow then submitted and completed `YRP-GRN-2026-00056` as Misstitch with exact input/output lineage, valuation links, Work Order counters, and Finishing projection. Base YRP remains untouched. |
| A85 | Create Rework availability ignores direct Rework Details conversions | After S20 converted 1 of each size from Misstitch to Accepted through rendered Rework Details, independent stock proof showed only 4 Misstitch per size at `S-0170`. The base `get_rework_source_rows` API still returned 5 per size because it subtracts converted Inspection Entries and prior rework Work Orders but cannot know Essdee's separate `GRN Rework Item` conversion ledger. The generic popup would therefore visibly over-offer already-cleared stock. | FIXED in Essdee only: the API override retains base permission, source, dimension, inspection, and prior-Work-Order reservation logic, then batch-subtracts the authoritative direct-clearing quantity (`reworked` while open, full source quantity once completed) by exact `source_grn_item`. The base create endpoint's live-bucket validation remains the final concurrency guard. All 38 valuation-contract tests pass. The rendered popup proved five max-4 cells and created/submitted exact 20-piece rework Work Order `YRP-WO-2026-00050`; independent reconciliation found no remaining parent rework source and no premature stock/Finishing mutation. Base YRP remains untouched. |
| A86 | Generic rework GRN double-counts Finishing inward and leaves rework pending | Rework GRN `YRP-GRN-2026-00057` correctly consumed 4 Misstitch and returned 4 Accepted per size with exact DC-item FIFO value, but Essdee's Finishing event treated it as another ordinary Stitching inward. The plan changed from original 15 delivered per size to 19 and Accepted 10 to 14, while `finishing_plan_reworked_details` remained only 1/5 cleared from the direct Rework Details branch. An authoritative rebuild would lose the generic rework result entirely because `_collect_rework` read only `GRN Rework Item`, not submitted GRNs against rework Work Orders. | FIXED in Essdee only: authoritative rebuild now aggregates submitted rework-Work-Order outputs by exact variant/set combination, counts default Received Type as reworked and configured Rejected as rejected, and leaves another rework type pending. Rework submit/cancel routes through that rebuild instead of ordinary inward increments. The legacy **Fetch Rejected Quantity** button now invokes the same full permission-checked rebuild instead of a second partial implementation. All 18 Finishing service and 38 valuation tests pass. Rendered correction proved every size changed from false 19/14/reworked1 to original inward 15/Accepted10/reworked5, with each rework row exactly 5/5 and zero rejected. Base YRP remains untouched. |
| A87 | Migrated Process retains obsolete allowance and loses base GRN excess contract | S22 preflight found migrated `Cutting` has legacy `additional_allowance = 300%` but base `wo_excess_allowed_percentage = 0%`. Current `production_api` uses the former to validate Work Order GRN excess while finalized base YRP uses only the latter. Essdee recreated the legacy custom field and its generic migration copied it unchanged, so an additional LaySheet receipt would be rejected after the planned quantity even though the source Process explicitly permits it. | FIXED in Essdee migration/setup only: `Process.additional_allowance` now maps to base `Process.wo_excess_allowed_percentage`; the post-sync patch carries legacy values only when no nonzero base value was authored, then removes the duplicate Custom Field. Fresh setup/fixtures no longer create it. All 17 transformer tests pass, including value-preservation policy. The rendered Process form saved live `Cutting` from base 0% to the migrated 300% with HTTP 200 and no browser error. Base YRP remains untouched. |
| A88 | Rendered excess Delivery Challan quantity is clamped to zero | Base intentionally returns every Work Order deliverable even at zero pending so a fully delivered Work Order can dispatch additional stock, and its server lifecycle deliberately lets pending become negative. The inherited Vue editor nevertheless uses `pending_quantity` as the Delivery Challan input maximum. S22 rendered all four Cutting inputs with quantity/pending zero and HTML `max="0"`; entering an additional quantity was immediately clamped back to zero, so the documented excess route could not be completed from the UI. | FIXED in Essdee only: the adapter preserves the authoritative zero pending value in flat defaults and clears only the grouped editor maximum for zero/negative normal deliverables. Both the Work Order action and manual Delivery Challan Work Order selection use it; draft onload reapplies it after Save, while positive pending caps remain unchanged. Four focused tests pass. Rendered new/save/reload/submit proved no `max` regression and created `DC-2026-00026` with exact quantities/rates, HTTP 200 throughout, and zero browser errors. Base YRP remains untouched. |
| A89 | Ordinary Delivery Challan draft cannot reload after an expanded zero matrix cell is saved | S23 used the rendered Work Order **Make DC** editor to zero only the five garment quantities while retaining 19 packing accessories. Base correctly preserves legitimate zero Work Order rows while a draft is editable, but the grouped editor also expanded seven unrelated Transparent Size Sticker values. Those generated zero rows carried numeric `0` in Link fields (`ref_doctype`/`ref_docname`); draft `DC-2026-00027` saved, then rendered reload failed HTTP 404 through `DocType 0 not found` behavior. No submit occurred at this failed boundary. | FIXED in Essdee only: before persistence and before base onload grouping, remove only zero generated rows whose Link values are numeric zero. Valid zero Work Order rows remain, so base draft re-edit and submit-strip behavior is preserved; CPM drafts retain their existing narrower all-zero cleanup. The new ordinary-draft regression and existing CPM regression pass. The same saved draft then loaded through the rendered form, retained five valid zero garment rows plus 19 accessories, submitted to exactly 19 positive rows, and completed its internal transfer with every request HTTP 200 and zero browser errors. Base YRP remains untouched. |
| A90 | Current dynamic packing GRN can post output without consuming its delivered inputs | S23 stopped before creating its first packing GRN. The current ratio dialog creates `packing_calculation_version = 2`, but Essdee selected its mapped packing planner only when that version was zero, and the existing planner calculated only the five garment rows. Continuing would therefore have received packed output without consuming either those garments or the 19 delivered packing accessories, with no complete input/output valuation lineage. Historical submitted records are not rewritten by this finding. | FIXED in Essdee only: every new Packing GRN now selects deterministic mapped consumption. Dynamic batches allocate exact colour/size garment pieces and every available set part; the same Item BOM engine that built the Work Order recalculates all 19 piece/pack accessory variants, caps them by delivered-minus-consumed Work Order stock, and maps them to the exact output. Size-specific accessory value stays with its size; common accessory value is proportionally split across all positive outputs with final-row rounding conservation. A two-box current-Lot dry run produces 60 mapped rows over 24 distinct inputs and all five outputs. A 2-box → 3-box → blocked over-allocation → simulated second delivery → 5-box sequence ends at exactly 10 boxes/120 pieces with all 24 inputs fully consumed. The full valuation-contract, Finishing-service, and dynamic-packing test modules pass. Submit/cancel retains the existing exactly-once mapped counter and base-YRP lineage lifecycle. Base YRP remains untouched. |
| A91 | Dynamic packing output displays piece counts as Boxes | The first rendered two-box retry submitted `YRP-GRN-2026-00062` with correct batch totals (2 boxes/24 pieces), stock quantities, 60 mapped input rows, SLE lineage, and value, but each size output displayed quantities 4/6/6/4/4 with transaction UOM `Box`. Base correctly reapplies the packed Item Variant's master dependent-attribute UOM, while dynamic packing version 2 deliberately stores size quantities as physical pieces and stores boxes only in `packing_batches`; the result therefore visibly contradicts its own two-box total. | FIXED in Essdee only: after base UOM validation, current dynamic Packing GRN outputs use the Lot's piece/packing UOM with conversion factor 1, while batch rows remain the sole physical-box ledger. New dynamic packing Work Order receivables preserve the same piece UOM after base validation. Legacy/migrated fixed-ratio documents remain unchanged. The undispatched bad-display GRN was cancelled through its rendered form with complete counter, SLE, lineage, balance, and Finishing-projection reversal. Its rendered replacement `YRP-GRN-2026-00063` shows Pieces on all five outputs and preserves the exact 2-box/24-piece, 60-mapping, 24-input, ₹4,204.378510476 valuation contract. Focused regressions, the full valuation-contract module, clean rendered-form verification, and an independent ledger/value verifier pass. Base YRP remains untouched. |
| A92 | Dynamic packing GRN Completion reverts physical Pieces to Box | After A91 passed, rendered **Complete Transfer** created draft `YRP-STE-2026-00065` with the correct five items, physical quantities 4/6/6/4/4, ₹4,204.378510476 value, transit source `S-0165`, and destination `S-0170`, but Stock Entry validation independently reapplied each packed Item Variant's master transaction UOM `Box`. The completion therefore contradicted its source GRN and would risk interpreting physical piece quantities as boxes on later validation. The driver stopped before Submit, so no transfer SLE or GRN completion counter changed. | FIXED in Essdee only: a GRN Completion against a current version-2 dynamic Packing GRN inherits the physical Piece UOM, stock UOM, conversion, and quantity semantics of its exact linked GRN Item after base Stock Entry validation. Onload repairs a pre-fix draft's rendered grouped view without writing; Save/Submit persists and enforces the correction. Other Stock Entries and legacy/migrated packing completions remain base-controlled. All eight Stock Entry customization tests pass. The same rendered draft `YRP-STE-2026-00065` showed Pieces before Submit and completed 24/24 with zero browser errors; independent proof reconciles ten SLE legs and ₹4,204.378510476 transit-to-destination value exactly. Base YRP remains untouched. |
| A93 | Dynamic packing dispatch Stock Entry reverts physical Pieces to Box | The first S24 direct rendered dispatch correctly selected the two-box/24-piece immutable batch and submitted `YRP-STE-2026-00069` with five physical quantities 4/6/6/4/4, stock UOM Pieces, conversion 1, exact FIFO rates, and a correct 24-piece Finishing projection. Base Stock Entry validation nevertheless relabeled every transaction UOM as the packed Item Variant master UOM `Box`, reproducing the A92 semantic contradiction on outbound dispatch. The accepted API mutation was stopped before its planned cancel/retry; no Finishing Plan Dispatch record was created. | FIXED in Essdee only: current version-2 dynamic batch Material Issues against either Finishing Plan route retain each Lot's physical packing UOM after base validation and on rendered onload, with exact normalized batch-to-row quantity validation. Legacy/non-batch Material Issues remain base-controlled. The pre-fix direct entry was cancelled through the rendered Finishing Plan action with complete stock, batch, audit-log, and projection reversal. Its rendered retry submitted `YRP-STE-2026-00070`; independent proof requires persisted Piece UOM on all five rows, exact 4/6/6/4/4 quantities, five active source SLEs, ₹4,204.378510476 FIFO issue value, 96 source Pieces, and a 2-box/24-piece Partially Dispatched projection. Ten focused Stock Entry tests, compile, diff, and both mutating UI runs pass. Base YRP remains untouched. |
| A94 | New Finishing Plan Dispatch cannot be saved from the rendered UI | S24 selected the exact remaining 5-box and 3-box batches for 96 Pieces in the new Finishing Plan Dispatch grid, but both toolbar Save attempts made no server request. Rendered validation showed the required Naming Series was empty. The DocType still shipped only the obsolete `FPD-2526-` option with no default, while the site's authoritative MRP fiscal window is 2026-04-01 through 2027-03-31 and live current records use `FPD-2627-`. No document or stock mutation occurred. | FIXED in Essdee only: the controller derives `FPD-<start-YY><end-YY>-` from the authoritative MRP Settings fiscal window, enforces it on every fresh insert, and exposes the same permission-protected resolver to new Desk forms because Frappe's transient new-form loader does not serialize direct `onload` field assignments. The Select displays only that value. Setup removes the obsolete hard-coded Property Setter; the shipped schema has no stale FY option. All 11 focused tests, compile, JS syntax, and diff checks pass. The rendered retry submitted `FPD-2627-00155` with `FPD-2627-`, exact 5+3 batch selection, five Piece rows totaling 96, no Stock Entry, and clean browser/network channels. An initial successful Save/Submit revealed and then removed a jQuery-promise `.finally()` incompatibility; a clean rendered reopen plus independent persisted proof pass. Base YRP and production_api remain untouched. |
| A95 | Finishing Plan Dispatch omits the direct route's stock-rate preparation | The first separate-route FPD Stock Entry `YRP-STE-2026-00071` issued the exact remaining 96 Pieces and ₹16,817.514041904 FIFO value, but its five transaction rows had rate/amount zero because this route omitted the shared dimension-aware preparation already used by direct Finishing Plan dispatch. The first cancellation audit initially treated zero-valued +quantity cancellation SLEs as a second defect. Finalized base YRP deliberately marks both original and cancellation rows `is_cancelled=1`, excludes the complete voucher from live replay, and retains those +quantity rows as inactive zero-value tombstones; the authoritative live Bin correctly restored both 96 Pieces and ₹16,817.514041904. | FIXED in Essdee only: the rate helper is now an explicit shared Finishing service used by direct dispatch, ironing receipt, and Finishing Plan Dispatch before insert. All 12 focused FPD tests pass, including call ordering. Rendered post-fix `FPD-2627-00156` / `YRP-STE-2026-00072` persisted positive row rates/amounts and the same exact FIFO SLE value. Its rendered cancellation produced the finalized base contract—five inactive original value rows plus five inactive zero-value tombstones—while independently restoring 96 Pieces, ₹16,817.51404192 live Bin value, 5+3 available boxes, the single direct dispatch, and Partially Dispatched status. No base change is required or permitted. A final rendered retry remains. |
| A96 | Runtime hook inventory replays protected live transactions as if they were unused samples | The first complete Essdee suite ran after final S24 state and selected latest submitted packing GRN `YRP-GRN-2026-00065` for `before_cancel` plus final dispatch `YRP-STE-2026-00073` for `on_submit`. Their correct dependency/idempotency guards raised `ValidationError`, so the inventory counted only 75/77 handlers even though both handlers resolved and executed. | FIXED in the acceptance harness only: a domain `ValidationError` now counts as successful runtime execution against an already-protected live document, while import, signature, `TypeError`, `AttributeError`, and every other unexpected exception still fail. Dedicated lifecycle tests retain semantic assertions. All six runtime-acceptance tests pass, including all 77 handlers. |
| A97 | Offline migration planner blocks on removed F15 `Item.description` and stale classification totals | Finalized base YRP has no `Item.description`; the frozen F15 production_api schema still declares it. The planner correctly failed closed with one unmapped field. The new reviewed Process allowance mapping also changes one DocType from identity to mapped, making the old expected 228/32 totals stale. | FIXED in Essdee migration rules/tests: a read-only SQL audit of live source `mrp3.site` proves zero nonblank Item descriptions, so the removed field is explicitly ignored with that reason instead of silently dropped or recreated in base. Planner expectations are 227 identity / 33 mapped / 3 custom, totaling the same 263 source DocTypes. All five planner tests pass with zero schema blockers. |
| A98 | Provisional rework regression calls the pre-A86 helper signature | The full suite reached `test_finishing_ignores_provisional_rejection`, which still called `_collect_rework(lot, items)` after A86 added authoritative default/rejected Received Type inputs and generic rework-Work-Order receipt projection. This was a stale test invocation, not a production failure. | FIXED in the regression only: pass the two authoritative Received Types and return no rework Work Orders after the mocked direct-rework record. All four GRN Rework Item tests pass, including zero projection for an unposted provisional rejection. |
| A99 | Root transaction Cancel tries to cascade-cancel its CPM first | U10 reverse-order cleanup correctly cancelled the reduced collapsed GRN, then rendered Cancel on `DC-2026-00030` opened Frappe's linked-document cascade and called `cancel_all_linked_docs` for submitted `CPM-2608-00240`. The CPM correctly rejected that invalid order with `Cancel Delivery Challan DC-2026-00030 before cancelling this Cut Panel Movement.`, leaving the DC and CPM submitted. The server root-cancel hook already reverses CBML and clears the CPM owner, but the Desk form had not excluded CPM from the generic cancel-all preflight. | FIXED in Essdee only: submitted DC/GRN/Stock Entry forms with `cut_panel_movement` add `Cut Panel Movement` to `frm.ignore_doctypes_on_cancel_all`, allowing the root transaction's normal server cancellation first; the unlinked CPM can then be cancelled explicitly. All 19 UI-mirror tests pass, all three scripts pass `node --check`, diff check and the Essdee asset build pass. After a site-cache refresh, rendered Cancel sent `get_submitted_linked_docs` and `save.cancel` HTTP 200 for the DC without a cascade call, then cancelled the CPM separately; every retry browser/page/network/response channel was clean. Base YRP remains untouched. |
| A100 | Material Receipt rejects ordinary positive rates in native HTML validation | U16 entered rate `100` in the rendered Stock Entry Material Receipt editor. Every Rate control combined `min=0.000001` with `step=0.001`, so the browser declared `100` invalid (nearest valid values `99.999001`/`100.000001`) and **Add Item** made no request or row. This affects normal three-decimal rates even though the server accepts them. | FIXED in Essdee's Stock Entry form only: a scoped observer changes only the rendered Rate inputs' HTML step to `any` while preserving the positive `0.000001` minimum and all server validation. The focused UI-mirror module now has 20 passing tests, JavaScript and diff checks pass, assets rebuild, and cache is refreshed. A fresh rendered probe entered exact rate `100` in all five cells; every input retained the positive minimum, reported native-valid, and **Add Item** created the expected S-size editor row. The probe remained an unsaved local draft (`docItems=0`) and all browser/page/network channels were clean. Base YRP remains untouched. |
| A101 | Yolk Fusing GRN consumes the panel but omits its calculated fusing-sticker input | Rendered U20 Work Order `YRP-WO-2026-00053` correctly calculated and delivered both `Casual Designer vest - 6-Back-Wine-S` and `Fusing Sticker-Designer Vest (Essdee)-S-White`, 135 each. The first rendered GRN save nevertheless created only the panel `YRP GRN Deliverable`, leaving the draft output at process-only `₹0.40`/`₹54`. The Essdee identity planner inherited Production API's legacy same-item-only rule and never replayed the process-owned accessory route. | FIXED in Essdee only: identity garment receipts preserve the migrated/manual exact-panel fallback, then replay each saved Work Order calculated demand separately to recover size/colour-specific accessory routes. Non-garment inputs are deterministically apportioned across that demand's outputs, mapped to the exact GRN output and saved Work Order Deliverable, normalized to stock UOM, and valued from the authoritative supplier bucket. Routes that legitimately require no accessory remain valid. The shared ambiguous-input error no longer says “Stitching” for other planners. Focused suites pass 44/44 valuation-contract and 11/11 GRN-customization tests; Python compile and `git diff --check` pass. The corrected rendered GRN submitted with two exact input rows, two production links, and `₹1.375037037` output valuation. Submit/cancel and final restoration are recorded under U20. Base YRP remains untouched. |
| A102 | Finishing Plan incomplete Stitching-GRN cache is neither added nor cleared by authoritative rebuild | U27 submitted internal-unit GRN `YRP-GRN-2026-00069` and correctly rebuilt every Work Order/Finishing quantity, but `FP-2526-00238.incomplete_transfer_grn_list` did not include the submitted uncompleted GRN. Cancelling it restored all quantities yet left the cancelled GRN name in the JSON cache. Repeating **Calculate Pieces** reproduced the stale-cache result, proving that quantity projection was idempotent while the incomplete-transfer list was still event-maintained rather than source-replayed. | FIXED in Essdee only: every Finishing rebuild now resolves the configured Stitching Process/Process group and replaces `incomplete_transfer_grn_list` from submitted, internal-unit, transfer-incomplete Work Order GRNs for that Lot. The same source query powers the incomplete-transfer API, so submit, cancel, retry, and manual Calculate Pieces converge on one authoritative result. Fresh rendered GRN `YRP-GRN-2026-00070` appeared as `{\"YRP-GRN-2026-00070\": true}` after submit, disappeared as `{}` after Cancel, and remained `{}` after repeated Calculate Pieces. Focused Finishing-source, Finishing-service, Work-Order-piece, and Sewing-business suites pass 46/46; final cleanup restored the exact pre-test plan and zero stock. Base YRP remains untouched. |
| A103 | Create Rework source API exposes stock-bearing rows without checking the caller can create a Work Order | The Essdee override's comment said base YRP remained authoritative for permission checks, but base `get_rework_source_rows` validates document state and stock eligibility without calling `check_permission`; only the later create endpoint checks Work Order create permission. An authenticated read-only user could therefore call the source method directly and receive exact GRN child, Received Type, Stock Dimension, and available-quantity data even though no rework Work Order could be created. | FIXED in Essdee only: the override now checks read permission on the exact source Work Order and Work Order create permission before invoking base source calculation. The Essdee Desk script also removes the base Create Rework action when client create permission is false; the existing non-manager Desk gate remains only navigation, not authorization. Restricted rendered user `u28-no-create@essdee.fit`, holding only `YRP Floor Verify`, had `canCreate=false`, was routed to `/web`, rendered no Create Rework action, and received HTTP 403 `PermissionError` from the direct source endpoint; it was disabled after proof. Valuation-contract and UI-mirror suites pass 46/46 and 21/21, JavaScript/Python compile, diff check, asset build, and cache refresh pass. Base YRP remains untouched. |
| A104 | External Packing Work Orders could create internal Finishing Plan side effects | The Essdee Work Order submit hook keyed only on `includes_packing` and non-Rework status. It did not apply base YRP's authoritative `is_internal_unit`, even though every migrated packing/finishing Work Order linked to a Finishing Plan uses a company-location supplier. A submitted external-supplier Packing Work Order could therefore create a Finishing Plan, box stickers, and alternative-plan stock side effects intended for the configured internal finishing unit. | FIXED in Essdee only: packing submit now requires base-derived `is_internal_unit` before any internal finishing side effect. Cancel mirrors that boundary while still deleting a stale pre-fix plan if one is linked. Rendered external Process Cost `PC-02008` and Work Order `YRP-WO-2026-00057` proved the Work Order remains valid but creates no Finishing Plan, Box Sticker, Stock Entry, or retained-plan mutation; UI cleanup canceled/expired both. The internal positive chain `PC-02007` → `YRP-WO-2026-00049` → `FP-2526-00238` remains exact. Focused tests pass 5/5, compile/diff/cache checks pass, and base YRP remains untouched. |
| A105 | Finishing Plan Return Item UI is blocked by the generic different-warehouse validator | The rendered **Return Item** flow deliberately sets both source and destination to the Finishing location and uses paired SLEs to reclassify the same physical stock from default Accepted to the selected Received Type. The first U34 request therefore reached Essdee's specialized direct-return controller but inherited base YRP's ordinary-GRN `From Warehouse and To Warehouse must be different` validation and returned HTTP 417 before insert. No GRN, counter, or SLE was written. | FIXED in Essdee only: same-warehouse validation is allowed only for a direct `from_finishing` return or the existing Cutting conversion; ordinary GRNs retain the base rejection and all mandatory item/warehouse checks remain. The same rendered flow then submitted Accepted, Rejected, and Misstitch direct returns with exact paired/value-preserving SLEs. Focused tests pass 8/8 together with A106, compile/diff/cache checks pass, and base YRP remains untouched. |
| A106 | Finishing direct-return cancel re-prices an already-empty Accepted source bucket | Rejected return `YRP-GRN-2026-00077` submitted correctly and moved one Piece/₹163.582 from Accepted to Rejected. Its first rendered Cancel then returned HTTP 417 because the cancellation path rebuilt the forward transfer and called `get_last_sle_rate` on the now-empty Accepted bucket. The failed cancel rolled back and left the submitted GRN, stock, and Finishing projection consistent. | FIXED in Essdee only: cancellation builds the same voucher identity/dimension rows without a live price lookup and lets finalized base YRP derive the reversal rate from the persisted original SLE. The same submitted GRN then canceled through the Finishing Plan UI, retained its immutable original pair plus cancellation tombstones, restored Accepted qty/value, removed Rejected stock, restored Work Order pending, and restored every Finishing counter. Accepted and Misstitch cancel paths pass the same lifecycle. The regression asserts cancel never calls the live-rate lookup; all 8 focused tests pass and base YRP remains untouched. |
| A107 | Manual identity Work Order outputs were forced through an unrelated calculated accessory route | U44 reran the actual Cut Panel Movement DC→GRN lifecycle against retained `WO-2627-00857`. Its manually appended exact `Top Front` receivables correctly owned their matching panel inputs, but the A101 accessory replay considered only the Work Order's saved calculated `Top Back` fusing routes and rejected every manual output as an unmatched calculated embellishment row. The transaction rolled back before GRN insert. | FIXED in Essdee only: accessory inference first requires the received Item Variant to exist in a saved calculated route. A migrated/manual exact identity output with no such route consumes its exact panel without fabricating an accessory; a calculated variant with a mismatched combination/index remains a hard error. The new regression and full valuation contract pass 47/47, and the actual DC→GRN submit/cancel round trip passes in 148.3 seconds. Base YRP remains untouched. |
| A108 | Offline migration planner blocks on removed F15 `Item Production Detail.description` | The diagnostic complete-suite run reached the fail-closed planner after the live source schema gained `Item Production Detail.description`. Finalized base YRP intentionally has no such field, so leaving it unclassified made the migration plan invalid even though no row carried business data. | FIXED in Essdee migration rules/tests: a final read-only SQL audit of live F15 `mrp3.site` proves 437 IPDs, zero nonblank descriptions, and maximum stored length zero. The field is explicitly ignored with that exact reviewed reason; it is neither guessed, copied, nor recreated in base YRP. Transformer and planner modules pass 17/17 and 5/5, and the final unfiltered suite finishes with zero planner blockers. |
| A109 | Late-valuation integration commits escaped the test rollback and polluted retained acceptance counts | The first post-U44 state audit after a green complete suite found 789 rather than 780 active retained-Lot SLEs and 134 rather than 94 immutable idempotent adjustments. The nine active SLEs belonged only to the latest `_Test Valuation U40 Reverse ...` Stock Entries. The base valuation worker correctly commits between lock/apply phases, so the test's source transactions and audit rows crossed Frappe's outer rollback while its final cancellations did not. Repeated diagnostic runs had retained 40 immutable, uniquely keyed adjustment audit rows. | FIXED in the Essdee integration test only: patch the worker's commit boundary for the duration of this single-threaded test so production phase ordering executes inside the runner transaction and rolls back atomically. The existing prefix-guarded helper cancelled exactly `YRP-STE-2026-00191` through `00199`, restoring 780 active retained SLEs and zero active U40 Stock Entries; no retained business voucher was eligible. Immutable audit history was not deleted, so the documented adjustment inventory is now 134. Transaction safety passes 1/1, the focused chain passes in 193.3 seconds with 780/134/0 unchanged, and the final complete suite again leaves 780/134/0 unchanged. |
| A110 | Desk Delivery Challan inherits its source from the Work Order | Manual post-release UAT found that choosing a Work Order copied `delivery_location` into the DC From Location and derived its Warehouse, even though the physical issue source is specific to each Essdee dispatch and must be chosen by the operator. Base YRP deliberately supplies that convenience default. | FIXED in Essdee only: both Work-Order default routes now return blank From Location/From Warehouse, the Desk form clears both when the Work Order changes, a scoped Property Setter removes base `from_warehouse.supplier` fetching so From Location is truly enabled, and the Essdee controller preserves blank or explicitly selected source values across base `set_missing_values` so Save cannot silently restore the Work Order location. Both fields remain editable/required and base YRP is untouched. `/web` was excluded at the owner's direction because that frontend is planned for retirement. Focused test/build/rendered-Desk evidence is recorded in the 2026-08-28 follow-up below. |
| A111 | Same-location Cutting Delivery Challan is rejected as a same-warehouse transfer | Manual post-release UAT requires a Work Order DC even when cloth is already in the Machine Cutting location and therefore does not physically move warehouses. Base YRP rejected every same-warehouse DC before the Work Order/Cutting lifecycle could advance. | FIXED in Essdee only: the DC override retains the complete base item and positive-quantity validation but permits equal From/To Location and equal From/To Warehouse. Same-location endpoints remain non-internal, submit still reduces the Work Order deliverable pending quantity, Cutting Plan received cloth still reads the DC delivered quantity, and stock posting remains an auditable value-preserving `-qty/+qty` transfer pair in the same warehouse. Ordinary stock-availability, Work Order, dimension, UOM, and rate validation remain authoritative. Base YRP, GRN behavior, and `/web` are untouched. Focused evidence is recorded in the 2026-08-28 follow-up below. |
| A112 | Cutting Plan received-cloth tables are empty despite a submitted cloth DC | Manual UAT on `CP-2608-00018` found no required/received/used/balance cloth table. The plan contains 32 garment rows and submitted DC `DC-2026-00038` contains four exact 116.4 kg cloth deliveries, but the plan was submitted with zero generated cloth child rows; `onload` therefore correctly returned empty arrays. The same component renders all columns on migrated `CP-2608-00015`, proving this is a lifecycle/data-generation gap rather than a missing Vue component. Empty submitted plans can also be incorrectly promoted to Ready to Cut because the status loop treats zero rows as all requirements satisfied. | FIXED in Essdee Desk only: every new submission generates and validates cloth requirements when missing; missing IPD consumption/mapping rows now fail clearly instead of being silently skipped; Fetch Received Cloth regenerates historical empty plans before projecting submitted DC quantities; regeneration preserves existing received/used weights; empty plans remain Planned; Fetch reloads the form; and the component has valid single-table markup plus an explicit empty state. Rendered no-screenshot repair of `CP-2608-00018` produced four visible 116.4/116.4/0/116.4 rows and Ready to Cut with clean browser/network channels. Base YRP and `/web` remain untouched. |

## 6. Lineage, migration, and API rules

### New transaction rule

A newly created mapped Essdee GRN must have, for every deliverable row:

- exact `goods_received_note_item`;
- exact input `item_variant`, quantity, stock UOM, and dimensions;
- exact received output variant (`received_item_variant` where different);
- Work Order deliverable link when the source is a Work Order;
- after submit, actual consumption SLE, output receipt SLE, and material value;
- no parallel Essdee-generated SLE for the same physical movement.

If a new transaction cannot establish the complete mapping, submission must
fail with an actionable error. It must not silently fall back to legacy posting.

### Historical transaction rule

Migrated `goods_received_note_item`, `received_item_variant`, consumption SLE,
output SLE, and Work Order deliverable fields remain optional. The migration may
populate them only when an immutable source link or a unique single-output
relationship proves the value. Unknown multi-output history remains blank and
uses the explicit legacy compatibility route. The migration report must count
mapped, unmapped, ambiguous, and invalid references separately.

Pre-reset readiness evidence on 2026-08-25 reports 106,975 submitted regular
Work Order GRN Deliverable rows: 212 fully mapped, 106,563 wholly unmapped, 200
partially mapped, and 102,615 ambiguous multi-output/unmapped rows. Missing
output-map, consumption-SLE, and output-SLE counts are each 106,763; the missing
Work Order Deliverable count is 106,563. Invalid GRN-item, consumption-SLE, and
output-SLE references are all zero, and active Lot Transfer SLEs have zero
unpaired rows. These values prove why no broad row-order backfill is permitted;
the post-reset migration must reproduce or explain every count delta.

### API compatibility rule

For every Essdee override/hook, verify the current base signature, return value,
transaction boundary, and lock expectations. Tests must fail on an incompatible
base signature rather than swallowing `TypeError` or retrying with an assumed
old API. Frappe session user and server permissions remain authoritative.

### UOM rule

All item-bearing generated rows are converted from the source quantity/UOM to
the selected item's configured transaction UOM before base applies read-only
UOM metadata. SLE quantities/rates use stock UOM. Tests include non-1 conversion
factors and a 20 Pieces → 2 Boxes example.

## 7. Implementation checklist

The status markers below are updated as evidence is produced.

- [x] P01 Freeze target/base/source revisions, dirty fingerprints, and site versions.
- [x] P02 Review the last three base YRP commits and the loaded base overlay.
- [x] P03 Compare actual source-site production_api, upstream develop, and the relevant master-only GRN setting.
- [x] P04 Inventory Essdee stock/GRN/WO/migration paths and classify keep/remove/change/add.
- [x] I01 Update optional YRP GRN Deliverable lineage schema through tracked Essdee fixtures/DocType metadata.
- [x] I02 Add shared complete-mapping detection, validation, construction, and idempotent Work Order consumption apply/reverse.
- [x] I03 Convert fabric GRN generation to exact mapped base valuation; retain explicit historical compatibility.
- [x] I04 Convert printing/identity garment GRN generation to exact mapped base valuation.
- [x] I05 Allocate cutting cloth/accessory consumption deterministically across exact GRN output rows.
- [x] I06 Route packing through the shared mapped lifecycle and prove no duplicate posting.
- [x] I07 Normalize generated fabric Work Order quantities/UOM before base metadata application.
- [x] I08 Align Lot Transfer and every Essdee direct transfer/conversion path with actual FIFO transfer results, dimensions, pairing, and cancel guards.
- [x] I09 Restrict and repair the finishing direct no-DC return; defer generic DC returns to base.
- [x] I10 Implement valuation-aware Work Order close for new mapped lineage and safe historical handling.
- [x] I11 Add idempotent valuation contract/setup checks without modifying base.
- [x] I12 Add supplier GRN-validation exemption fixture/configuration and enforcement.
- [x] I13 Add deterministic historical-lineage readiness/backfill tooling and migration report counters.
- [x] I14 Extend migration transforms for the new optional fields without fabricating values.
- [x] I15 Make new MRP Data Migration audit runs savable from Desk without exposing or accepting editable connection endpoints.
- [x] I16 Track the live source Cutting Laysheet Planner identity fields required for lossless migration.
- [x] I17 Gate migration Analyse/Dry Run/Migrate on the reviewed IPD production defaults and the exact mandatory, valuation-bearing `lot`/`received_type` stock-dimension contract.
- [x] I18 Add an audited, preview-first, server-enabled target reset action that preserves Singles/configuration and every naming-series counter, deletes only the migration-owned non-Single/child/File/generated-warehouse graph, verifies exact deleted identities are gone and every series value is unchanged, and requires the frozen source snapshot plus maintenance mode.
- [x] I18A Bind all migration target prerequisites to the frozen Dry Run and make every reset/backfill population query exhaustive without loading the full child graph into memory.
- [x] I19 Add focused regression tests for every item above, including submit/cancel/return/closed-period/permission/concurrency cases.
- [x] I20 Make the failed-reset preview and retry state contract identical in Desk and on the server.
- [x] I21 Port current production_api PPO Request edit parity without weakening status or permission checks.
- [x] I22 Make identity GRN planner selection/matching exclusive and strict.
- [x] I23 Lock and validate the complete Essdee mapped-GRN ownership contract and make Work Order stock-update lifecycle retry-safe.
- [x] I24 Enforce Cutting LaySheet/Work Order association before mapped allocation.
- [x] I25 Correct Recut stock-UOM rate handling and remove the Lot Transfer transient dimension assignment.
- [x] I26 Serialize migration action reservation across duplicate requests and audit records.
- [x] I27 Repair the new Cutting LaySheet empty UI data contract.
- [x] I28 Harden Work Order-close output SLE ownership and no-excess retry behavior.
- [x] I29 Require Work Order write permission before every Essdee close/request route.
- [x] I30 Restore and directly test mapped-GRN completeness dispatch so validation and lifecycle hooks cannot be bypassed.
- [x] I31 Normalize legacy packing mapped consumption from physical stock quantity into the Work Order input's transaction UOM.
- [x] I32 Bind Work Order-close output SLE ownership to the exact mapped Goods Received Note Item child.
- [x] I33 Restrict reset retry audit cleanup to exact checkpointed audit-row identities; remove timestamp-based discovery.
- [x] I34 Apply the complete mapped-GRN ownership gate to cancellation before any base or Work Order reversal.
- [x] I35 Make direct finishing-return Work Order Deliverable resolution exact and ambiguity-safe.
- [x] I36 Require cutting mapped inputs to be delivered against the Work Order before LaySheet consumption.
- [x] I37 Reject ambiguous duplicate Cutting Work Order inputs instead of overwriting by `(item_variant, uom)`.
- [x] I38 Remove the unreachable pre-mapped GRN converter and stock-UOM helper.
- [x] I39 Preserve the imported legacy Work Order counter contract when cancelling a historical mapped GRN whose lifecycle state is zero.
- [x] I40 Require exact voucher/child/item/direction/activity ownership before historical SLE lineage becomes an active valuation propagation link.
- [x] I41 Persist the selected Lot cloth excess percentage with the calculated cloth program.
- [x] I42 Carry authoritative Work Order source/supplier addresses into Delivery Challan UI defaults.
- [x] I43 Make Cutting Marker delayed control creation unmount-safe and panel validation current-state aware.
- [x] I44 Filter garment accessory BOM rows by selected Work Order processes before evaluating their mappings.
- [x] I45 Make historical all-unmapped GRN Work Order input resolution exact for both saved links and fallback business keys.
- [x] I46 Mirror base YRP's complete causal ordering gate before any historical child mapping; keep base-incompatible same-instant F15 rows wholly unmapped and reported.
- [x] I47 Bind the executed post-load valuation-lineage backfill source into the frozen migration contract fingerprint.
- [x] I48 Keep every DC/GRN Completion Stock Entry child visible by assigning distinct integer Vue grouping indexes in Essdee onload/validation hooks.
- [x] I49 Commit a dynamic LaySheet set-combination Select's sole valid option so its visible value and saved control value cannot disagree.
- [x] I50 Serialize bundle and Finishing GRN retry roots, persist a client request identity without schema changes, and prove SLE/CBML/projection/GRN/valuation-adjustment idempotence.
- [x] I51 Explicitly classify the removed, entirely blank F15 IPD description field so the frozen migration plan remains fail-closed with zero blockers.
- [x] I52 Contain valuation-worker commits inside the U40 test rollback and prove repeated focused/full runs leave no active test stock or new adjustment audit rows.
- [x] I53 Keep Essdee Desk DC source selection operator-controlled: never inherit From Location/From Warehouse from the Work Order and never restore them during Save.
- [x] I54 Allow an Essdee same-location/same-warehouse DC to advance Work Order and Cutting Plan lineage while preserving balanced stock and every unrelated base validation.
- [x] I55 Guarantee that every submitted Cutting Plan has generated cloth requirements before received/used/balance projection, and render those values in Desk with an explicit safe empty state.
- [x] R01 Independent diff review: no redundant base behavior, no mixed mapped/unmapped new GRN, no leaked base changes.
- [x] R02 Final independent diff/review pass covering the later A74/A75 UI findings and the completed end-to-end acceptance changes.
- [x] R03 Final post-U44/A108/A109 diff, permission, artifact, build, full-suite, rendered-state, and repository-preservation review.

## 8. Destructive migration rehearsal checklist

No step begins until implementation tests and independent diff review pass.

- [x] M01 Reconfirm target is exactly `essdee_yrp.site`, source is exactly F15 `mrp3.site`, and neither is production.
- [x] M02 Record Git revisions, installed apps, site configs excluding secrets, scheduler/worker state, and current target document counts.
- [x] M03 Take verified database backups of source and target through supported database/bench tooling; record paths/checksums without copying them into Git.
- [x] M04 Audit source freeze/maintenance readiness and active writes; do not migrate from a changing source.
- [x] M04A Capture and UI-verify target prerequisites before reset: IPD Settings item group/primary attribute and Cutting/Knitting/Dyeing/Packing/Stitching defaults; YRP Stock Settings transit/default received types and the exact `lot`/`received_type` valuation-dimension rows; server-owned legacy migration defaults. Analyse now enforces these prerequisites and records their non-secret values in `target_prerequisites`; verify all values again after migration.
- [x] M05 Run migration **Analyse** and save the complete Doctype/field/child/single/link plan.
- [x] M06 Run **Dry Run** and require zero blockers, zero unexpected invalid links, deterministic naming-series handling, and acceptable runtime/space.
- [x] M07 Audit all File rows and explicitly separate database metadata from available physical blobs.
- [x] M08 Reset only migrated business data on `essdee_yrp.site` through the migration engine's preview-first `Reset Target Data` action; preserve the documented 11 target Single/configuration DocTypes, authentication/runtime configuration, and the exact complete target naming-series snapshot. The action remains disabled until the one-time server reset acknowledgement is enabled on the isolated target.
- [x] M09 Run **Migrate** with source maintenance and target isolation enabled; no controllers execute for historical inserts.
- [x] M10 Run post-load exact-link readiness/backfill only for proven relationships; report every unresolved lineage row.
- [x] M11 Verify source/target parent, child, value, Single, naming-series, link-integrity, stock-bucket, SLE, CBML, calculated-item, Sewing Plan, Rework, and Finishing Plan counts/totals.
- [x] M12 Verify rollback artifacts and restore procedure before accepting the migrated target.
- [x] M13 Disable maintenance/isolation only after the verification report passes.

### 2026-08-25 rehearsal evidence

- Target backup: bench-generated `20260825_184956-essdee_yrp_site-*`; database
  SHA-256 `55673acf4631cede8e8a480d2235e3d4a5e4643359aeddc07bcdb0b21e50c768`.
  Database gzip and both file tar archives passed integrity checks.
- Source backup: `/home/anas/frappe-15/mrp3-final-backup-PR4yI6jD`; database
  SHA-256 `5ed8f2c835b5dd096930b27de8c21d8bd585fc13df923026f2a461dfdc917c7a`.
  All database/config/public/private checksums pass. Two Frappe 15 backup-wrapper
  attempts failed reproducibly on a roughly 19 MB `tabVersion.data` value
  because the wrapper omitted the dump client's packet override; the complete
  transactional dump therefore used `mariadb-dump --max-allowed-packet=256M`
  with the same single-transaction/quick/no-table-lock semantics.
- Pre-reset settings screenshots:
  `screenshots/2026-08-25_13-19-27-app-ipd-settings.png` and
  `screenshots/2026-08-25_13-19-27-app-yrp-stock-settings.png`; both had zero
  browser console errors. Post-migration comparison is still required before
  M04A can pass.
- Post-migration settings screenshots:
  `screenshots/2026-08-25_20-09-51-post-migration-ipd-settings.png` and
  `screenshots/2026-08-25_20-09-51-post-migration-yrp-stock-settings.png`;
  both had zero browser console errors. The required IPD process/attribute
  defaults, transit/default received types, and exact Lot/Received Type
  dimension flags match the frozen prerequisite payload, completing M04A.
- UI audit run `MRP-MIG-2026-00003` initially proved three live source-only
  Cutting Laysheet Planner fields, then reached Ready after the tracked target
  schema fix: 263 source / 327 target DocTypes, 227 identity, 33 mapped, 3
  custom, zero blockers. Analyse was executed from Desk with zero console errors.
- Pre-final whole-app code pass on 2026-08-25: 545/545 tests passed (39 unit,
  296 integration, 111 legacy-category, 99 optimizer/migration/other). This
  included the real CPM/DC/GRN lifecycle, exact and collapsed-bundle return and
  cancellation matrices, closed-sewing GRN submit/cancel, finishing source
  projections, rework transfer, dispatch, Item Conversion, Lot Transfer, and
  migrated-history compatibility. The final pass is rerun after the reset-scope
  hardening and fresh migration.
- Post-migration whole-app pass on 2026-08-26: all four test buckets completed
  in one serial process with zero failures: 39 unit, 296 integration, 111
  legacy-category, and 112 optimizer/migration/other tests (558 discovered;
  548 executed assertions and 10 dataset-conditional skips). The executed
  integration coverage includes the 163-second CPM/DC/GRN round trip, migrated
  LaySheet GRN creation, Stock Entry and Item Conversion submit/cancel,
  closed-sewing GRN submit/cancel, Finishing Plan source replay, rework stock
  conversion, dispatch, report compatibility, transaction safety, permission
  checks, and exact Production/IPD plus Lot/Received Type migration-prerequisite
  fingerprinting. The ten skipped historical-oracle tests are four garment
  setup branches and six exact/collapsed Printing-bundle matrices whose prior
  local UAT records were intentionally removed by the clean reset; they remain
  explicit UI qualification work under U01-U20 and are not counted as passed.
- Final-review whole-app pass on 2026-08-26 after A44 and the Work Order-close
  test expansion: all four buckets again completed in one serial process with
  zero failures: 42 unit, 296 integration, 112 legacy-category, and 114
  optimizer/migration/other tests (564 discovered; 554 executed and passed,
  with the same 10 dataset-conditional skips). The additional executed checks
  prove failed-reset UI/server retry state parity, actual FIFO excess-use value
  and production lineage on Work Order close, fail-without-clipping when exact
  stock is short, and closed-period rejection before the Work Order is saved.
  The skipped Printing bundle matrices remain open for S12-S14 UI execution.
- Post-alignment qualification on 2026-08-26 after A46-A71: one complete app
  run discovered 590 tests. All 58 unit, 114 legacy-category, and 117
  optimizer/migration/other tests passed; the integration category executed and
  passed 291 of 301, with only the same ten explicit migrated-dataset skips
  (four absent garment setup oracles and six Printing bundle matrices reserved
  for S12-S14). The executed coverage includes the 161-second CPM/DC/GRN round
  trip, 88-second migrated LaySheet-to-GRN lifecycle, Item Conversion and stock
  submit/cancel, closed-sewing GRN, Finishing projection, Work Order-close
  valuation/permission/period gates, migration action concurrency, exact reset
  scope, historical lineage ownership, and non-1 UOM cases. Focused modules also
  passed: valuation contract 29/29, Work Order close 9/9, migration live 56/56,
  direct finishing return 5/5, cloth program 50/50, Work Order API 19/19, and UI
  source contracts 18/18. `git diff --check`, Python compilation, and JSON parse
  checks passed. A normal `bench --site essdee_yrp.site migrate`, Desk asset
  build, and Vite frontend production build all completed successfully. Base YRP
  remains at `7536d315` with tracked fingerprint `849c7a8b...a04a88b` and
  untracked fingerprint `62e3be5d...d1d164`; F15 production_api remains clean at
  `5bc6a22e`; Frappe and ERPNext are clean. This qualifies implementation only:
  a fresh frozen migration and the rendered S01-S24 flow are still mandatory.
- Fresh UI audit `MRP-MIG-2026-00009` analysed cleanly and traversed all
  3,437,177 database rows with zero row failures, then failed safely at the
  attachment gate because its create-time `allow_missing_source_blobs` policy
  was off. It reported the first absent physical blob and did not reset or write
  target business data. The record is retained as strict-policy evidence only.
- Replacement UI audit `MRP-MIG-2026-00010` was created in Desk with the
  documented local-archive omission policy explicitly enabled. Analyse reported
  263 source / 327 target DocTypes and zero blockers. Its full Dry Run completed
  3,437,177/3,437,177 with zero failures. The frozen snapshot is
  `d7b4cc6e...f8174`, migration contract `8e0aba47...cf70`, and target
  prerequisite fingerprint `798d314b...2ebf`; the 25 known source broken links
  retain digest `0ca53f5d...db01`. It reviewed all 1,004 File rows: two physical
  blobs are available, 1,002 are audited local omissions (including 35 source
  orphan attachments), and no target file was written during Dry Run. All 172
  source naming-series counters are equal to or behind the target and the frozen
  merge rule remains `GREATEST(target_current, source_current)`.
- A fresh pre-reset target backup was completed through Bench at
  `20260826_122426-essdee_yrp_site-*`. The database archive SHA-256 is
  `4f97692f0f87a04d5387760a8abae8ef63a177320327995b230ea20ab305c59f`;
  config/public/private archive hashes are respectively `649a7d20...a1811`,
  `e29ac812...ec503`, and `33c9d7bb...bbe8`. Database gzip and both file tar
  archives passed integrity checks. At this boundary Essdee is at baseline
  `8be20a02` plus the reviewed task worktree, base YRP is the preserved
  `7536d315` overlay, and F15 production_api is clean at `5bc6a22e`. Installed
  target apps are Frappe, YRP, Essdee YRP, Spine, and YRP E-Waybill API; target
  maintenance is off, scheduler is disabled, one worker is online, and the
  one-time reset acknowledgement remains off pending the reviewed UI preview.
- On UI audit `MRP-MIG-2026-00010`, the visible reset preview reviewed exactly
  3,437,407 parent rows, 2,889,870 child rows, 969 target File rows, and 3,218
  generated supplier warehouses: 6,331,464 rows total. It checkpointed all 189
  target naming-series values and 11 preserved Single/configuration DocTypes.
  After the exact Desk confirmation, reset processed 6,331,464/6,331,464 with
  zero failures. Its exhaustive postcondition found zero remaining parent,
  child, File, generated-warehouse, or reset-audit rows; all 189 series matched
  exactly and all 11 Singles plus the frozen target prerequisites were
  preserved. The one-time server acknowledgement was returned to off as soon as
  the guarded worker started.
- The first `00010` Migrate loaded 3,437,177/3,437,177 rows with zero transport
  failures and restored the two locally available blobs, but its mandatory
  lineage report exposed A72: all 106,563 submitted regular Work Order input
  rows remained wholly unmapped even though the source contains 98,882 exact
  owned outgoing GRN SLEs. Diagnosis proved F15 creates the positive output row
  before the negative input row at the same business posting instant. A73 also
  proved that the post-load backfill source was absent from the frozen contract
  digest. This completed load is therefore diagnostic evidence only and is not
  accepted or verified; a new UI audit must repeat the full frozen cycle.
- Post-A72/A73 validation discovered 591 app tests: 59 unit, 301 integration,
  114 legacy-category, and 117 migration/optimizer/other. All 581 executed tests
  passed and the same ten explicit migrated-dataset cases were skipped for the
  later rendered UI qualification. The run includes the 135-second CPM/DC/GRN
  lifecycle and 75.6-second migrated LaySheet GRN. Focused valuation and live
  migration modules passed 30/30 and 56/56. `git diff --check` and Python
  compilation also passed before the replacement audit.
- Replacement Desk audit `MRP-MIG-2026-00011` analysed the corrected code with
  263 source / 327 target DocTypes and zero blockers. Its full Dry Run completed
  3,437,177/3,437,177 with zero failures. The source snapshot remains
  `d7b4cc6e...f8174` and target prerequisites remain `798d314b...2ebf`, while
  the corrected contract is now `ddc852b6...fe237`, proving the executed
  post-load backfill is part of the frozen gate. File and series audits remain
  exactly 1,004 rows / 1,002 audited missing blobs / 35 source orphans and 172
  source counters.
- The first `00011` load copied all 3,437,177 documents with zero transport
  failures, then failed safely when finalized base YRP rejected the proposed
  same-instant output-before-input production link. This proves A72 must remain
  an unmapped historical compatibility case rather than an Essdee-only active
  valuation edge. The run is not accepted: its partially attempted post-load
  transaction requires another complete reset, and the final audit must freeze
  the restored base-compatible preflight plus the A73 fingerprint coverage.
- After restoring the base-compatible historical order gate, the complete app
  suite again discovered 591 tests: all 59 unit, 114 legacy-category, and 117
  migration/optimizer/other passed; integration passed 291/301 with only the
  same ten rendered-UI dataset skips. The 136-second CPM/DC/GRN round trip and
  77-second migrated LaySheet GRN passed. Focused valuation passed 30/30;
  `git diff --check` and compilation passed. Because A73 now binds this restored
  backfill source, neither `00010` nor `00011` may be reused: a fresh audit is
  required from Analyse onward.
- Final Desk audit `MRP-MIG-2026-00012` froze the corrected code from a fresh
  Analyse and Dry Run. Analyse reported 263 source / 327 target DocTypes and
  zero blockers; Dry Run processed 3,437,177/3,437,177 rows with zero failures.
  The frozen source, migration-contract, target-prerequisite, and known-broken-
  link fingerprints are respectively `d7b4cc6e...f8174`,
  `947be7ae...e98ad`, `798d314b...2ebf`, and `0ca53f5d...db01`. The reviewed
  reset preview contained 3,437,166 parents, 2,888,666 children, 969 Files,
  3,218 generated supplier warehouses, 189 preserved naming-series counters,
  and 11 preserved Singles: 6,330,019 rows total. The exact Desk confirmation
  reset all 6,330,019 rows with zero failures and immediately returned the
  one-time acknowledgement to off. Migrate then loaded all 3,437,177 source
  parents with zero transport failures.
- The `00012` post-load lineage pass intentionally activated no unsafe legacy
  production edge. Its final read-only readiness audit reports 106,563
  submitted regular Work Order GRN deliverables: all 106,563 are wholly
  unmapped, none are partially mapped, 102,415 belong to ambiguous multi-output
  GRNs, and all invalid GRN-item/consumption-SLE/output-SLE link counts are zero.
  Active Lot Transfer SLEs have zero unpaired rows. This is the explicit A72
  legacy exception; new transactions must use the complete base-owned lineage
  contract and are qualified separately in S09, S14, S17, S19-S24, and U38-U44.
- The independent `00012` Verify completed both exhaustive source passes with
  zero failures: 6,325,980 parent/child identities and documents and
  161,629,286 stored field values. It passed all 1,004 File rows (two verified
  local blobs, 967 audited missing blobs, and 35 audited source-orphan
  attachments), all 172 source naming-series counters, and 736 link fields with
  exactly 25 frozen source-broken values and zero unexpected broken values.
  Source and target stock match across 293,125 buckets with digest
  `d717572f...ffc2f0`, quantity `54673037.951885493`, and stock-value difference
  `545392426.229999981`. Exact operational identity checks include 1,360,434
  SLEs, 1,180,897 CBML rows, 82,018 Work Order Calculated Items, 122,441 YRP GRN
  Deliverables, 148 Sewing Plans / 20,250 details, 325 Finishing Plans / 10,814
  details, 7,617 reworked details, and 358 Finishing Plan Dispatches / 5,525
  items / 938 logs. The preserved IPD and stock settings still contain the
  required process/attribute/warehouse/received-type values and exact
  `lot`/`received_type` valuation-dimension flags. Final status: **Verified**,
  failures: **0**.
- The accepted rollback boundary is Bench backup
  `20260826_122426-essdee_yrp_site-*`. Rechecking produced database/config/
  public/private SHA-256 values `4f97692f...c59f`, `649a7d20...a1811`,
  `e29ac812...ec503`, and `33c9d7bb...bbe8`; database gzip and both uncompressed
  file tar archives pass integrity checks. `bench restore --help` confirms the
  reviewed recovery form: restore the database archive for exactly
  `essdee_yrp.site` with the matching `--with-public-files` and
  `--with-private-files` archives. The destructive restore itself is reserved
  for an owner-approved rollback and was not executed against the Verified
  target.
- Only after `00012` reached **Verified**, target maintenance was disabled and
  the cache cleared. `essdee_yrp.site` then returned HTTP 200 on port 8003; the
  one-time target-reset acknowledgement remains disabled/absent. F15 source
  `mrp3.site` remains frozen in maintenance mode. This completes M13 and opens
  the rendered-UI qualification boundary without reopening source writes.
- UI run `MRP-MIG-2026-00005` reached Ready and completed a 3,437,177-record
  Dry Run with zero failures. Its reset preview then exposed A35 before any
  destructive action: the source has a real blank naming-series identity and
  most target counters are already equal/ahead. The reset flag remained off and
  no target row was deleted. Because A35 changes the frozen migration contract,
  `00005` is retained only as evidence; a fresh Analyse/Dry Run is required.
- UI run `MRP-MIG-2026-00006` repeated the 3,437,177-record zero-failure Dry
  Run while the independent reset review found A36-A40. It is likewise retained
  as read-only evidence only; no reset flag was enabled and no target row was
  deleted. The final reset fingerprint must come from a later frozen-code run.
- UI run `MRP-MIG-2026-00007` completed another 3,437,177-record zero-failure
  Dry Run. Its first reset failed safely at the standard File deletion queue's
  900-job ceiling and generated exactly 900 File deletion-audit rows plus 900
  attachment-removal comments; no partial business reset was accepted. After
  A41, the retry preview reviewed 6,348,334 rows, the UI reset processed all of
  them with zero failures, all migration-owned post-counts were zero, all 188
  target naming-series values matched the checkpoint exactly, and all 11
  Single/settings DocTypes were preserved. The real migration then processed
  3,437,177/3,437,177 with zero failures. Verify completed both the full
  identity pass and full transformed-value pass with zero row failures, then
  correctly stopped on five target-only contextual `IPD Item Attribute` rows,
  exposing A42. `00007` is therefore failure evidence, not final acceptance;
  a fresh frozen-code run is required after A42.
- UI run `MRP-MIG-2026-00008` reached Ready and completed a fresh
  3,437,177-record zero-failure Dry Run after A42. Its corrected preview
  included 159 target child DocTypes and all 1,891 current `IPD Item Attribute`
  rows. The first reset attempt then failed before deletion on A43's fresh
  checkpoint timestamp serialization; the guarded record reported one failure,
  no target reset row was processed, and the one-time flag returned to off.
  Because A43 changes the frozen contract, `00008` must be re-Analysed and its
  Dry Run repeated before the reset can be retried.
- After A43, `MRP-MIG-2026-00008` was re-Analysed and repeated the full
  3,437,177-record Dry Run with zero failures. The corrected UI reset processed
  6,330,024 reviewed rows with zero failures and proved zero remaining parent,
  child, File, generated-warehouse, reset-audit, and `IPD Item Attribute` rows;
  all 189 target naming-series values matched exactly and all 11 settings
  Singles were preserved. The real migration then processed
  3,437,177/3,437,177 with zero failures. Independent Verify passed both full
  source passes: 6,325,980 parent/child identities/documents and 161,629,286
  stored field values. It verified all 1,004 File rows (two available local
  blobs, 967 audited missing blobs, and 35 audited orphan attachments), all 172
  source series, and 736 link fields with 25 frozen known broken values and zero
  unexpected broken values. Stock passed with identical source/target values
  across 293,125 buckets: quantity `54673037.951885493` and stock-value
  difference `545392426.229999981`. The live contextual child count is exactly
  the expected 1,886 `IPD Item Attribute` rows. Final status: **Verified**,
  failures: **0**.

## 9. Full UI workflow qualification matrix

Every creation/edit/submit/cancel action below is executed in the rendered UI
as an authorized test user. The purpose is to expose and fix real form, button,
dialog, validation, and navigation difficulties. Screenshots are not a task
deliverable. Record names, visible UI results, browser console/network results,
and read-only database/API queries prove the stored state and side effects.

### Owner-mandated sequential business transaction

This is one continuous acceptance transaction after the clean migration. It is
not replaceable by isolated controller tests or pre-existing sample records.
Every downstream document must be created from the document produced by the
preceding step, through the rendered UI. Existing server APIs may be used only
through the buttons/dialogs that already invoke them; direct API/console writes
are not substitutes for creation. Read-only queries are used after each action
to prove stored links, quantities, stock, valuation, projections, and rollback.

- [x] S01 Create a new Production Order through the UI and capture its exact order quantities, ratio/price fields, approval state, and console result.
- [x] S02 Create and link a new Lot from that Production Order; prove the Production Order/Lot relationship in both records.
- [x] S03 Create the Lot's Item Production Detail and its required IPD Process configuration/matrices; use this exact IPD for every downstream Work Order.
- [x] S04 Create and submit the Cutting Work Order from that Lot/IPD, with approved Process Cost and the correct cutting supplier/location.
- [x] S05 Create and submit the Cutting Plan against that Work Order.
- [x] S06 Before creating the Cutting Marker, attempt the Cutting Work Order Delivery Challan. If its exact stock bucket is short, create the required Stock Reconciliation/Stock Update through the UI, then create and submit the Delivery Challan. Record before/after stock quantities, dimensions, rates, and SLEs.
- [x] S07 Create the Cutting Marker from the same Cutting Plan and verify panel/ratio/group behavior.
- [x] S08 Create the Cutting LaySheet and complete its cloth/accessory/bundle calculation.
- [x] S09 Use the testing recovery path on that LaySheet: set/retain the Reverted state as required and invoke **Update Status** to reach the label/GRN boundary. Prove that the generated Goods Received Note belongs to this LaySheet and carries complete mapped input-to-output valuation lineage.
- [x] S10 Create and submit the Printing Work Order from the exact cut output.
- [x] S11 Create Cut Panel Movement records that move bundles from the machine-cutting location to Cut Panel Store; prove paired stock movement and CBML source/target state.
- [x] S12 Execute colour-wise Printing Delivery Challans across multiple documents and verify that only eligible bundles remain selectable.
- [x] S13 Exercise both normal-bundle return and collapsed-bundle return, including pending rebuild and CBML conservation.
- [x] S14 Receive a Printing GRN using collapsed bundles, then deliver that same collapsed bundle again against the same Printing Work Order and receive it again. Verify no duplicate/lost bundle, quantity, SLE, Work Order, or valuation lineage.
- [x] S15 Create the Stitching Work Order with supplier/location **Sewing Unit Tiruppur** and verify that its Sewing Plan is created and linked only under the configured rule.
- [x] S16 In Sewing Details, enter the configured sequence through the UI: Input Quantity, Line/Output Quantity, Checking Output, and AQL Output. Prove that a later stage cannot exceed or precede its configured predecessor and allowance.
- [x] S17 Attempt a Stitching GRN before the configured Checking Output quantity is available and retain the blocking error/no-write evidence; then correct the Sewing entries and submit the valid GRN.
- [x] S18 Before receiving all Stitching pieces, create the Ironing and Packing Work Orders for **Ironing Unit Tiruppur** and verify the Finishing Plan is created and linked.
- [x] S19 Receive part of the Stitching output into an eligible non-default, non-Accepted, non-Rejected Rework Received Type. Do not consume the whole stitching balance in the normal Accepted bucket.
- [x] S20 Use the Rework Details page to dispatch, enter/clear as applicable, and receive that quantity; prove exact Received Type/FIFO value transfer and the Finishing Plan rework projection.
- [x] S21 Submit the remaining/required Stitching GRN transactions and prove that Finishing Plan stitching received changes only at the authoritative completed Work Order calculation boundary.
- [x] S22 Create an additional Cutting LaySheet and receipt for additional stock, then prove the Finishing Plan cutting received projection rebuilds correctly without double counting.
- [x] S23 Execute Ironing/Packing/Finishing Delivery Challans and Goods Received Notes, including partial/multiple receipt and configured Received Type cases; prove Finishing Plan cutting, stitching, rework, packing, and remaining quantities after each submit/cancel boundary.
- [x] S24 Create a dispatch from inside the Finishing Plan and independently create a dispatch through the **Finishing Plan Dispatch** DocType. Verify both routes use the approved dispatch API, post paired/value-preserving stock, update the same remaining-dispatch projection idempotently, and support the documented cancel/retry behavior.

### Sequential UI execution evidence — 2026-08-26

- S01: rendered Desk form created `PPO-00261` for `XMAS PJ5 - MENS`.
  Visible controls supplied naming series `PPO-`, Delivery Date `2026-08-30`,
  Don't Deliver After `2026-09-15`, Production Term
  `5 Piece Pack Term 1`, and five size-grid rows. Save, **Request PPO
  Approval**, the confirmation, and **Approve & Submit PPO** were all clicked
  in the UI; their savedocs/request/approve requests returned HTTP 200 with
  zero console, page, failed-request, or failed-response errors. Authoritative
  state is `docstatus=1`, `status=Open`, Posting Date `2026-08-26`, lead time
  four days, requester/submitter `ui-verify@essdee.fit`, and zero linked Lots
  before S02. S/M/L/XL/2XL quantities are 20/30/30/20/20, ratios
  2/3/3/2/2, and MRP 500 each; wholesale and retail prices are the rendered
  zero defaults.
- S02: from `PPO-00261`'s rendered **Lot → Create Lot** dialog, entered
  `MRP-UAT-260826-01`; the button-triggered API returned HTTP 200 with zero
  browser errors and routed to the rendered Lot. The stored and rendered Lot
  both show `production_order=PPO-00261`, `item=XMAS PJ5 - MENS`,
  `status=Open`, and `owner=ui-verify@essdee.fit`. The Production Order's
  authoritative linked-Lot lookup returns this exact Lot. At the required S02
  boundary `production_detail` is blank and both Lot quantity totals are zero;
  no IPD or order-calculation side effect was started early.
- S03: the rendered approved `XMAS PJ5 - MENS-1` form's **Duplicate IPD**
  action created `XMAS PJ5 - MENS-2` (version 2). The visible
  **Generate / Regenerate IPD Process Matrix** action generated 15 `Cutting`
  matrices for all ten reference size/part variants with zero skipped rows,
  and **Approve** set the new IPD to `Approved`. Its copied authored contract
  includes Cutting/Stitching/Packing, Printing `Cut→Cut`, Ironing
  `Piece→Piece`, 3 cloth rows, 9 stitching-item rows, Stage as the dependent
  attribute, Size as primary, and `Cut→Piece→Pack` stage boundaries. The Lot
  UI then linked this exact IPD, saved, and ran **Calculate Order Items**.
  `MRP-UAT-260826-01` now has 10 size/part rows, 120 finished pieces and 240
  part-level order quantity, UOM `Box`, packing UOM `Pieces`, and matching
  `PPO-00261` generic Lot-reference rows. Duplicate, matrix generation,
  approval, Lot save, and calculation all returned HTTP 200 with zero browser
  errors. The historical Top/Bottom rows retain the template's intentional
  shared set-combination key; this exactly matches `F0426-77` rather than being
  a new transformation anomaly.
- S04: the rendered Process Cost form duplicated the exact Cutting template
  into `PC-02003`, linked it to `MRP-UAT-260826-01`, retained supplier
  `S-0164`, Panel-dependent rates (0.375 for Top Front/Back, Sleeve, and Neck
  Rib; 0.300 for all five Bottom panels), 5% tax slab, Pieces UOM, and
  `2026-08-26` through `2026-09-15` validity, then used visible workflow
  **Submit** and **Approve** actions to reach `docstatus=1`, `Approved`.
  The rendered Work Order form then selected Cutting, this exact Lot/item/IPD,
  supplier `S-0164`, delivery location `S-0170`, their visible Billing
  addresses, and the `2026-08-26` through `2026-08-30` dates. **Calculate
  Items** displayed all ten size/part source rows at their full 20/30/30/20/20
  quantities (240 part-level total); its visible **Submit** generated four
  cloth deliverables and 47 receivables. Work Order `YRP-WO-2026-00046` then
  submitted from the form with `status=Submitted`, `open_status=Open`, planned
  and total quantity 240, IPD `XMAS PJ5 - MENS-2`, and Process Cost `PC-02003`.
  Every costed panel row references `PC-02003` with the approved 0.375/0.300
  rate, while two calculated accessory-cloth outputs correctly carry zero
  process cost. Both workflow calls, both savedocs calls, and both Calculate
  Items calls returned HTTP 200 with zero console, page, failed-request, or
  failed-response errors.
- S05: from submitted `YRP-WO-2026-00046`, the rendered **Create → Make
  Cutting Plan** action opened a prelinked plan with Lot
  `MRP-UAT-260826-01`, item/IPD `XMAS PJ5 - MENS` / `XMAS PJ5 - MENS-2`,
  maximum 100 plies, and the complete visible 240-piece Top/Bottom matrix.
  The UI set 10% maximum allowance and `Machine Cutting`, then saved and
  submitted `CP-2608-00015`. Stored/rendered state is `docstatus=1`,
  `cp_status=Planned`, 10 item rows totalling 240, two colours/groups, zero
  completed, and the configured 0.01 kg piece-weight tolerance. No cloth or
  accessory rows were generated early. Its rendered **Planned Detail** tab
  shows Top 120 + Bottom 120, size totals 40/60/60/40/40, and zero completed.
  The source Work Order's rendered **Summary** independently shows the same
  planned matrix with zero delivered and zero received at this pre-DC/GRN
  boundary. Cutting Plan item fetches, saves/submission, and both summary
  fetches returned HTTP 200 with zero browser errors. The first verifier pass
  submitted the plan correctly but used a normal-button selector for the tab;
  the read-only second pass selected the rendered navigation tab and proved
  its contents without creating another plan.
- S06: before any Marker existed, rendered **Create → Make DC** opened all four
  Cutting input rows for exact dimensions `lot=MRP-UAT-260826-01` and
  `received_type=Accepted`, moving from `S-0170` to internal cutting unit
  `S-0164`. Draft `DC-2026-00017` saved, then its first visible **Submit**
  failed safely with HTTP 417: White Dyed Fabric available 0, required 18.24;
  it remained draft and posted no stock. The rendered Stock Reconciliation
  form then added all four rows through Lot/Received Type/Item/Dia/Colour/Qty/
  Rate controls and submitted `YRP-ST-RECO-2026-00003` at quantities
  18.24/21.60/0.96/45.72 kg and established historical rates
  370/370/280/400. Its four SLEs and Bins exactly equal those quantities,
  rates, and values 6,748.80/7,992.00/268.80/18,288.00.

  Reopening the same DC and using its visible **Submit** then succeeded at
  posting time `2026-08-26 16:34:26.319293`: total 86.52 kg and value
  33,297.60. Four paired DC transfers reduce every `S-0170` bucket to zero
  and place the same qty/value in transit `S-0165`; all four Work Order input
  pending quantities became zero. Because this is an internal-unit DC, visible
  **Complete Transfer** created draft `YRP-STE-2026-00052`. That rendered
  audit exposed A74: all four stored rows had integer `row_index=0`, so only
  the first appeared. The Essdee-only onload/validation normalizer (base YRP
  unchanged) made all four rows visible with exact per-DC-child links; six
  focused tests passed and the repaired form reloaded with zero browser errors.
  Its visible **Submit** moved the four equal FIFO values from transit to
  `S-0164`. The DC now records 86.52 transferred, 100%, `transfer_complete=1`;
  final `S-0164` Bins are exactly 18.24@370, 21.60@370, 0.96@280, and
  45.72@400. All successful saves/actions returned HTTP 200. The single
  post-reconciliation `fieldobj` page error occurred only when the verifier
  submitted before the asynchronously remounted editor completed; a fresh
  rendered submitted-record load was clean and retained all four rows. Back on
  the submitted Cutting Plan, the visible **Generate** and **Fetch and
  Calculate → Fetch Received Cloth** actions then populated its four cloth
  rows from that exact transfer. Required/received/balance weights are
  18.24/18.24/18.24, 21.60/21.60/21.60, 0.96/0.96/0.96, and
  45.72/45.72/45.72 kg with zero used weight, moving `CP-2608-00015` from
  `Planned` to `Ready to Cut`; both UI-triggered calls returned HTTP 200 with
  no browser errors.
- S07: the first rendered marker probe selected all nine panels and proved that
  Save/reload/Submit retained its visible ratios/groups after A69's delayed-
  control hardening. Comparison with migrated XMAS PJ5 transaction `F0426-77`
  then proved that this style requires four fabric-specific markers and one V3
  group per physical panel. The unused all-panel probe `CM-2608-00077` was
  cancelled before any LaySheet used it. A second probe showed why Top/Bottom
  panels must not be combined into one group: bundle generation divides a
  combined group's quantity. Its empty draft LaySheet `CLS-2608-00116` was
  cancelled, then probe markers `CM-2608-00078` and `CM-2608-00081` were
  cancelled through the rendered UI; none produced cloth, bundles, GRN, stock,
  or CBML side effects.

  The final submitted Machine/V3 marker set against `CP-2608-00015` is
  `CM-2608-00082` for Top Front/Top Back (two separate groups),
  `CM-2608-00079` for Sleeve, `CM-2608-00080` for Neck Rib, and
  `CM-2608-00083` for all five Bottom panels (five separate groups). Every
  marker has exact S/M/L/XL/2XL ratios 2/3/3/2/2 and 10 plies; stored
  ratio/group child counts are 10/2, 5/1, 5/1, and 25/5. Required piece
  weights equal the exact corresponding received cloth divided by 120 output
  pieces: 0.152/0.180/0.008/0.381 kg. Saved calculated panels, submitted
  ratios, and group views now exactly match the migrated reference. The final
  marker creation runs returned HTTP 200 with zero console, page,
  failed-request, or failed-response errors.
- S08: four rendered LaySheets used only those final markers and their exact
  transferred fabrics: `CLS-2608-00117` Top (18.24 kg White MAIN FABRIC 1,
  10 Open Width bits), `CLS-2608-00118` Sleeve (21.60 kg Green MAIN FABRIC 1,
  10 Open Width bits), `CLS-2608-00119` Neck Rib (0.96 kg White RIB FABRIC,
  5 Tubler bits = 10 effective bits), and `CLS-2608-00120` Bottom (45.72 kg
  White MAIN FABRIC 2, 10 Open Width bits). Every row uses Dia/Actual Dia
  `72 Dia`, shade A, one roll, zero end-bit/balance, and the exact saved
  Top/Bottom set combination. Each visible cloth Save moved `Started` to
  `Completed`; each visible **Generate** dialog retained 100 maximum plies,
  10% allowance, and `2026-08-26`, then moved the record to
  `Bundles Generated`.

  Stored/rendered bundle rows are 10/5/5/25 with 10/5/5/25 unique hashes.
  Every one of the nine panels has exact S/M/L/XL/2XL quantities
  20/30/30/20/20 (120 per panel); each LaySheet reports 120 finished pieces.
  Used weights and piece weights are exact at 18.24/0.152,
  21.60/0.180, 0.96/0.008, and 45.72/0.381. Cutting Plan cloth used weights
  now equal received weights and all four balances are zero. Its calculated
  accessory requirements remain FOLDING 0.24 kg and DRAW CARD 1.80 kg, but
  both have zero received/used weight; accordingly no unsupported accessory
  row was invented in these LaySheets. There is correctly no CBML before the
  label/GRN boundary in S09.

  The first Top **Add Item** attempt exposed A75 and wrote no cloth child.
  After the single-option control fix, `bench build --app essdee_yrp` and
  target cache clear succeeded; the same saved draft and the other three forms
  completed through visible controls. The final four-form run had zero console,
  page, failed-request, or failed-response errors; every savedocs,
  set-combination, parts, and bundle-generation request returned HTTP 200.
- S09 (completed 2026-08-27): for each of the four S08 LaySheets, the test
  browser exposed the standard hidden `reverted` Check control in the rendered
  Frappe form, physically clicked that checkbox, and used the visible **Save**
  action. No direct database/API write set the flag. On a fresh form load the
  visible **Update Status** action and its **Yes** confirmation were clicked.
  Each record then reloaded as `Label Printed`, `reverted=0`, with exactly one
  submitted linked Cutting GRN and no remaining **Update Status** action. The
  Top browser was paused after its server transition had committed; read-only
  recovery inspection proved the one completed transaction and the resumed run
  did not call it again. The remaining three savedocs and update-status calls
  all returned HTTP 200. Final LaySheet and GRN form loads had zero console,
  page, failed-request, or failed-response errors.

  The exact links are `CLS-2608-00117 → YRP-GRN-2026-00045` (Top),
  `CLS-2608-00118 → YRP-GRN-2026-00046` (Sleeve),
  `CLS-2608-00119 → YRP-GRN-2026-00047` (Neck Rib), and
  `CLS-2608-00120 → YRP-GRN-2026-00048` (Bottom). Every GRN is submitted
  against `YRP-WO-2026-00046`, Cutting, Lot `MRP-UAT-260826-01`, with supplier,
  delivery location, source warehouse, and destination warehouse all `S-0164`.
  Their rendered grouped tables show respectively 10/5/5/25 positive output
  rows and 240/240/120/720 physical panel pieces. These physical quantities
  correctly apply the IPD panel multiplier to the 120 garment-set bundle
  quantities (for example, two Sleeves and two Pockets per garment); this is
  not a duplicate receipt.

  Read-only exhaustive reconciliation proved 45/45 GRN Items have exactly one
  mapped YRP GRN Deliverable, exact received variant, exact Work Order input
  child, stock UOM conversion, Lot/Accepted Stock Dimensions, material value,
  grouped input-consumption SLE, and exact output-receipt SLE. The four physical
  input groups created four outgoing SLEs and the 45 output children created 45
  incoming SLEs; all are active and valuation-fresh. The same 45 child edges
  exist as active Stock Valuation Production Links with matching source row,
  SLE pair, input quantity, allocation weight, and Stock Dimensions. No second
  Essdee SLE path or duplicate active GRN exists.

  Value conservation is exact: Top consumed 18.24 kg / `₹6,748.80`, added
  `₹90.00` Cutting cost, and received `₹6,838.80`; Sleeve consumed 21.60 kg /
  `₹7,992.00`, added `₹90.00`, and received `₹8,082.00`; Neck Rib consumed
  0.96 kg / `₹268.80`, added `₹45.00`, and received `₹313.80`; Bottom consumed
  45.72 kg / `₹18,288.00`, added `₹216.00`, and received `₹18,504.00`.
  Combined: 86.52 kg input, 1,320 physical output panels, `₹33,297.60` material,
  `₹441.00` process cost, and `₹33,738.60` received value. All four Work Order
  input counters equal the mapped quantities and their S-0164/Lot/Accepted
  balances are zero; all 45 output-variant balances equal their received
  quantities at positive process-inclusive valuation rates.

  CBML reconciliation likewise passed 45/45 exact bundle rows (10/5/5/25):
  Lay/Bundle/Size/Colour/Panel/Shade/Set Combination match the saved LaySheet,
  initial quantity-after-transaction equals the bundle quantity, and every row
  is active, uncollapsed, untransformed, and owned by the exact LaySheet at
  S-0164. Cutting Plan cloth used equals received with zero balance. Its
  completed/incomplete quantity structures contain the full cut quantities and
  zero remaining panel quantities; `cp_status=Cutting In Progress` is the
  separate manual completion-flag state, not missing cut stock or S09 lineage.
- S10 prerequisite (2026-08-27): the migrated XMAS reference uses Printing
  only for `Top Front`, supplier `Sri Krishna Printing`, destination Cut Panel
  Store `S-0170`, and process rate `₹1.00/Pieces`. Its historical Process Cost
  is expired, so the rendered `PC-01575` **Duplicate** flow created
  `PC-02004` for Lot `MRP-UAT-260826-01`, valid 2026-08-27 through 2026-09-30.
  Visible **Actions → Submit** and **Actions → Approve** completed the standard
  workflow; the final document is submitted/Approved, Panel-dependent, and has
  exactly one `Top Front = ₹1.00` rate. Savedocs and both workflow calls returned
  HTTP 200 with zero browser errors.
- S10 (completed 2026-08-27): the rendered Work Order form saved draft
  `YRP-WO-2026-00047`, then its visible **Calculate Items** dialog exposed the
  eligible Top and Bottom cut groups. The browser physically unchecked Bottom,
  leaving only Top selected at 120 garment pieces, and submitted the dialog.
  The same rendered draft—not a replacement or direct API-created record—then
  used the visible **Submit** action and confirmation. Final state is
  `docstatus=1`, `status=Submitted`, `open_status=Open`, process `Printing`,
  Lot `MRP-UAT-260826-01`, item/IPD `XMAS PJ5 - MENS` /
  `XMAS PJ5 - MENS-2`, supplier `Sri Krishna Printing`, delivery location
  `S-0170`, Billing addresses `Sri Krishna Printing-Billing` and
  `S-0170-Billing`, Process Cost `PC-02004`, and planned quantity 120. Dates
  are 2026-08-27 posting, 2026-08-30 expected delivery, and 2026-08-30 delivery.

  Its five calculated Top rows, five Top Front deliverables, and five Top Front
  receivables are exactly S/M/L/XL/2XL = 20/30/30/20/20. Every deliverable is
  Accepted, linked to the same Lot, has its full quantity pending, and has zero
  stock update before movement/DC; every receivable carries `₹1.00/Pieces`
  process cost from approved `PC-02004`. The rendered **Summary** independently
  shows Planned 120, Delivered 0, Received 0. Read-only reconciliation proves
  the exact 120 Top Front pieces remain at machine-cutting location `S-0164`
  with their positive process-inclusive rates, while `S-0170` is zero before
  S11. There is exactly one submitted Printing Work Order for this Lot and no
  premature Printing DC, GRN, SLE, Sewing Plan, or Finishing Plan. The final
  UI run had zero console, page, failed-request, or failed-response errors; all
  context, calculation, savedocs, and Summary calls returned HTTP 200.
- S11 (completed 2026-08-27): the rendered Cut Panel Movement form selected
  Lot `MRP-UAT-260826-01`, source machine-cutting location `S-0164`,
  **Movement From Cutting**, and Cutting Plan `CP-2608-00015`, then saved draft
  `CPM-2608-00228`. Its fetched editor correctly combined the physical history
  into two visible Top/Bottom tables: `White-Top` has Top Front, Top Back,
  Green Sleeve, and Neck Rib; `(White)White-Bottom` has all four Bottom panels
  plus Pocket. The browser physically clicked each table's select-all checkbox,
  saved the selection, and submitted the same draft through the visible action.
  Stored/rendered selection is 45 exact bundle-panel identities, five sizes per
  each of nine panels, each totalling 120 garment-bundle pieces. Applying the
  IPD multiplier of two to Sleeve and Pocket yields the authoritative 1,320
  physical stock pieces; no collapsed bundle or unsupported accessory was
  selected.

  This UI boundary exposed A76. The dedicated test user had no submit action
  after receiving the correct Store Manager role through the rendered User
  form because Essdee's lone System Manager Custom DocPerm suppressed both
  standard Store rows. `ensure_mrp_cancel_permissions` now mirrors all standard
  roles before applying only the intended System Manager override. The live
  effective rows are Store Manager `submit=1`, Store User `submit=1`, and
  System Manager `cancel=1`/`submit=0`; the same CPM then rendered **Submit**
  and completed. One focused integration permission regression passes. Base
  YRP metadata/code remains untouched.

  From the submitted CPM, visible **Create → Stock Entry** prepared all nine
  grouped panel matrices. The UI selected target Cut Panel Store `S-0170`,
  physically enabled **Skip Transit**, supplied vehicle/comment fields, saved,
  and submitted `YRP-STE-2026-00053`. It has 45 physical item rows, exact
  Lot/Accepted dimensions and set combination, source/target suppliers and
  warehouses `S-0164 → S-0170`, quantity 1,320 Pieces, and value
  `₹33,738.60`. Its fresh submitted rendered form shows all nine groups and
  their exact S/M/L/XL/2XL quantities/rates with zero console, page,
  failed-request, or failed-response errors. The first immediate post-submit
  verifier observed the known asynchronous dimension-control `fieldobj` page
  error while the editor remounted; it did not affect the transaction, and the
  fresh authoritative form load was clean.

  Exhaustive read-only reconciliation proves exactly 90 active SLEs: one
  S-0164 outgoing and one S-0170 incoming row for every Stock Entry child.
  Every pair is mutually linked, Lot/Accepted and valuation-fresh, quantity
  symmetric, and value symmetric; outgoing and incoming totals both equal
  `₹33,738.60`. No transit SLE exists. All 45 source Bins are zero and all 45
  target Bins equal the physical row quantity at the exact carried FIFO rate,
  totalling 1,320.

  CBML likewise has exactly 90 active rows for this Stock Entry: 45 source
  movements end at zero and 45 target movements retain the exact positive
  garment-bundle quantity, with Lay/Bundle/Size/Colour/Panel/Shade/combination
  conserved. That check exposed A77: raw JSON grouping initially made all 45
  consumed source panels selectable again. Availability now uses the ledger's
  canonical major-colour/part identity, including historical marker metadata,
  whitespace, and key-order differences. The 11-test movement unit class and
  focused regression pass; final endpoint proof returns zero S-0164 selectable
  panels and exactly 45 at S-0170. Printing Work Order
  `YRP-WO-2026-00047` remains Delivered 0/Received 0 with no premature DC or
  GRN, preserving the S12 boundary.
- S12 (in progress, checkpoint 1 on 2026-08-27): the rendered UI created and
  submitted `CPM-2608-00229` from Cut Panel Store `S-0170`. The fetched editor
  exposed the full two-table eligible balance, but the browser physically
  selected only White / Top Front bundles S=20 and M=30 (Lay 2, Bundles 1 and
  2). The stored and freshly rendered submitted CPM contains exactly those two
  bundle-panel identities totalling 50; Top Back, Sleeve, Neck Rib, every
  Bottom panel, accessories, and collapsed quantities are all excluded. The
  form completed with zero console, page, failed-request, or failed-response
  errors.

  Visible **Create → Delivery Challan** then selected Printing Work Order
  `YRP-WO-2026-00047`. This exposed A78 before any DC was saved: the endpoint's
  exact S/M matrix was replaced asynchronously by all five Work Order sizes.
  Essdee's CPM handoff now restores the prepared matrix after the base fetch for
  both DC and GRN; base YRP is unchanged. Repeating the same visible action
  rendered S=20, M=30, and zero L/XL/2XL, then saved and submitted
  `DC-2026-00018`. Its only two child rows total 50 at `₹28.495` and
  `₹1,424.75`, and it links back to `CPM-2608-00229`.

  Read-only reconciliation proves four paired SLEs (source -50/value
  `-₹1,424.75`, Printing warehouse +50/value `₹1,424.75`) and four exact CBML
  movements (S/M source zero, Printing target positive). Work Order pending is
  now S=0, M=0, L=30, XL=20, 2XL=20. The fresh availability endpoint likewise
  omits only the consumed S/M Top Front identities from `S-0170`, retains all
  unrelated panels, and exposes exactly L/XL/2XL Top Front totalling 70 for the
  second S12 split. The saved/submitted/fresh-rendered DC run had zero console,
  page, failed-request, or failed-response errors.

  The second rendered CPM form then fetched that reduced balance and physically
  selected only L=30, XL=20, and 2XL=20 Top Front. Submitted
  `CPM-2608-00230` stores exactly those three Lay-2 bundle identities totalling
  70, with no S/M resurrection, other panels, accessory, or collapsed row; its
  browser run was clean.

  Its visible **Create → Delivery Challan** action rendered zero S/M and exact
  L=30, XL=20, 2XL=20, then saved/submitted `DC-2026-00019`. It has only those
  three positive child rows, links one-to-one to `CPM-2608-00230`, and moves 70
  pieces at `₹28.495`, value `₹1,994.65`. The fresh rendered DC and all prepare,
  savedocs, and submit calls were clean.

  Final exhaustive S12 reconciliation proves the two CPM/DC roots are
  `CPM-2608-00229 → DC-2026-00018` and
  `CPM-2608-00230 → DC-2026-00019`, with no draft or unlinked split left. Their
  five exact bundle identities total 120 and `₹3,419.40`. Ten active SLEs form
  five mutually linked source/target pairs, preserve each child detail,
  quantity and value, and are valuation-fresh. Ten active CBML rows likewise
  leave every S-0170 Top Front bundle at zero and reproduce its exact positive
  quantity at Sri Krishna Printing. All five Printing Work Order deliverable
  pending quantities are zero. S-0170 availability contains the other 40
  untouched panel identities but no Top Front; Sri Krishna availability is
  exactly the five Top Front sizes S/M/L/XL/2XL = 20/30/30/20/20. No Printing
  GRN exists yet, preserving the ordered S13 return boundary. Python/JavaScript
  syntax and `git diff --check` pass, and all 11 focused CPM split/overlay/
  canonical-availability unit tests pass.
- S13 (in progress, exact-return checkpoint on 2026-08-27): code/UI analysis
  confirmed that a Return GRN without a CPM intentionally follows Essdee's
  implicit collapsed-bundle transformation, while exact whole-bundle return
  requires a submitted CPM. This exposed A79 because that supported link was
  hidden from the return draft. The Essdee GRN form now renders the Link only
  for an editable Return, filters it to an unlinked submitted CPM at the source
  supplier/Lot, and labels the exact-versus-collapsed choice; base YRP remains
  untouched.

  The rendered CPM form at Sri Krishna Printing then fetched the five delivered
  Top Front bundles and physically selected only S=20 (Lay 2, Bundle 1).
  Submitted `CPM-2608-00231` stores that one exact identity, no other panel,
  accessory, or collapsed row. Its save/fetch/submit run had zero browser or
  network failures.

  On submitted `DC-2026-00018`, the visible **Return** dialog then selected only
  S=20 with Received Type Accepted and created draft `YRP-GRN-2026-00049`.
  The rendered Return form showed the new exact-versus-collapsed explanation;
  the browser selected `CPM-2608-00231` through that Link, saved, and submitted.
  The result is an exact normal-bundle return with one S child, quantity/stock
  quantity 20, rate `₹28.495`, value `₹569.90`, source Sri Krishna Printing,
  destination `S-0170`, `allow_non_bundle=0`, and one-to-one CPM/GRN linkage.
  The returned matrix freshly renders S=20 and zero other sizes; all Return,
  Link, savedocs, and submit requests returned HTTP 200 with zero console, page,
  failed-request, or failed-response errors.

  The same rendered Return dialog was then reopened and selected M=10 while
  deliberately leaving the now-visible CPM field empty. It created, saved, and
  submitted `YRP-GRN-2026-00050` as the intended implicit collapsed-bundle
  return: one M child, quantity/stock quantity 10, rate `₹28.495`, value
  `₹284.95`, no CPM, and `allow_non_bundle=0` (the authoritative implicit-return
  detector owns this branch). Its fresh rendered matrix shows M=10 and
  Remaining=20; the complete browser/network run was clean.

  Exhaustive S13 reconciliation proves both return GRNs' four SLEs are two
  mutually linked, valuation-fresh source/target pairs. Exact S moved
  Sri Krishna -20 / `S-0170` +20 at `₹569.90`, and collapsed M moved -10/+10
  at `₹284.95`. The exact GRN has two ordinary CBML rows and links
  `CPM-2608-00231 → YRP-GRN-2026-00049`; supplier S ends at zero and store S at
  20 with Lay/Bundle identity intact. The collapsed return transforms the
  former exact M history out of exact availability and leaves canonical
  collapsed balances M=20 at Sri Krishna and M=10 at `S-0170`, exactly 30 in
  total with no duplicate/loss. Work Order deliverable pending rebuilt to
  S=20, M=10, all other sizes zero; the Return API reports only the remaining
  M=20 as returnable and already-returned=10. No return draft remains. The
  dedicated read-only verifier, JavaScript syntax checks, and diff check pass.
  Two older hard-coded integration-oracle tests skipped because their prior
  fixture documents are unavailable; the live UI transaction and exhaustive
  SLE/CBML/pending assertions provide the authoritative S13 proof.
- S14 (in progress, first collapsed-receipt CPM checkpoint on 2026-08-27): the
  initial rendered fetch on draft `CPM-2608-00232` returned HTTP 200 but showed
  no collapsed row, exposing A80. Essdee now sends numeric `get_collapsed=1`.
  The same draft was recovered instead of creating a duplicate, its rendered
  availability then showed Sri Krishna Printing's collapsed Top Front M=20,
  and the browser physically selected and submitted that exact quantity.
  `CPM-2608-00232` is submitted with no exact bundles, one collapsed M row,
  available/move quantity 20, source Sri Krishna Printing, and no transaction
  link yet. Save, availability, and submit requests completed without browser,
  console, page, network, or response failures.

  The browser then used that CPM's visible **Create → Goods Received Note**
  action, selected `YRP-WO-2026-00047` and `DC-2026-00018`, and submitted
  `YRP-GRN-2026-00051`. Its one rendered/physical row is collapsed Top Front
  M=20, Accepted, supplier Sri Krishna Printing → `S-0170`, with
  `allow_non_bundle=1`, input rate `₹28.495`, Printing process cost `₹1.000`,
  output rate `₹29.495`, and value `₹589.90`. This ordinary non-rework GRN
  correctly maps the output to its Work Order Receivable and intentionally has
  no `delivery_challan_item`; that child link is the base YRP rework/DC split
  contract, not the new valuation lineage contract.

  The required new lineage is complete: its single `YRP GRN Deliverable`
  carries the exact `goods_received_note_item`, received/input variant,
  Work Order Deliverable, consumption SLE `YRP-SLE-2026-07343`, and output SLE
  `YRP-SLE-2026-07344`. One active `Stock Valuation Production Link` joins
  those exact rows for quantity/weight 20. The source SLE consumes `₹569.90`,
  the output SLE receives `₹589.90`, and both are valuation-fresh. Two CBML
  rows move collapsed M -20/+20, leaving supplier zero and store M=30 without
  duplicate/loss. Work Order M deliverable is qty 30, pending delivery 10,
  stock update 20; its receivable is qty 30, pending receipt 10. The dedicated
  read-only S14 verifier passed every document, mapping, SLE, production-link,
  CBML, pending, availability, rate, and value assertion. No GRN draft remains.
  The rendered store CPM then showed collapsed Top Front M=30 and physically
  selected only M=10. Submitted `CPM-2608-00233` has source `S-0170`, no exact
  bundle/accessory row, one collapsed M row with available 30/move 10, and no
  transaction link yet; its complete save/fetch/submit run was clean.

  Its rendered Create action prepared and saved `DC-2026-00020` with only M10
  positive at the store's current `₹29.161666667` material rate/value
  `₹291.61666667`. Reopening that saved draft exposed A81: authenticated Desk
  getdoc returned 404/`DocType 0 not found` because four generated zero-size
  children carried numeric-zero Link values. The Essdee-only subclass now
  strips zero placeholders only for CPM-bound DCs before onload grouping and
  after base Vue sync. The same draft then loaded HTTP 200, rendered only its
  legitimate M10 child, and submitted through the UI—no replacement/duplicate
  record or direct business API mutation. `DC-2026-00020` is submitted with
  `allow_non_bundle=1`, `CPM-2608-00233`, `S-0170` → Sri Krishna Printing,
  quantity 10, and exactly the rate/value above. The full resumed browser run
  had zero console, page, request, or response failures. Thirteen focused
  movement tests pass, including CPM zero-row removal and ordinary base-DC
  zero-row preservation.

  After that DC, the supplier-side rendered CPM showed exactly one collapsed
  Top Front balance, M=10. The browser selected all 10 and submitted
  `CPM-2608-00234`; it contains no exact bundle/accessory row, source Sri
  Krishna Printing, and no transaction link yet. Its save/fetch/submit run was
  clean.

  That CPM's rendered Create action selected `YRP-WO-2026-00047` and
  `DC-2026-00020`, then created/saved/submitted `YRP-GRN-2026-00052` with only
  collapsed Top Front M=10, Accepted, Sri Krishna Printing → `S-0170`, and
  `allow_non_bundle=1`. The editable draft showed the current pooled/DC rate
  `₹29.161666667` plus process cost as `₹30.161666667`; submission correctly
  normalized the transaction to input `₹28.495` + one Printing cost `₹1.000` =
  output `₹29.495`, total `₹294.95`. This is not a lost charge: FIFO proves the
  DC consumed the older M10 layer returned before Printing (`₹284.95`), while
  leaving the already-printed M20 layer at `₹29.495`. The second GRN therefore
  charges Printing exactly once, not twice.

  Final exhaustive S14 reconciliation passes. The three CPM links are
  `00232 → GRN51` (M20 receipt), `00233 → DC20` (M10 redelivery), and
  `00234 → GRN52` (M10 receipt), each with no exact/accessory leakage. DC20's
  two valuation-fresh SLEs are a paired -10/+10 FIFO transfer at `₹284.95`;
  its two CBML rows leave store M20/supplier M10. GRN52 has an exact mapped
  `goods_received_note_item`, Work Order Deliverable, consumption/output SLE,
  and one active production link for 10; its two CBML rows restore store M30
  and supplier zero. Final store SLE state is one FIFO layer
  `[[30, 29.495]]`, stock value `₹884.85`, with no stale valuation. Collapsed
  availability is exactly store M30/supplier zero; normal availability remains
  store S20 and supplier L30/XL20/2XL20. Work Order M delivery pending,
  receipt pending, and unconsumed stock are all zero (`stock_update=30`). No
  draft CPM/DC/GRN remains. The rendered runs, 13 focused tests, syntax checks,
  and the dedicated full S14 document/SLE/production-link/CBML/FIFO/pending/
  availability verifier all pass. S14 and U12 are complete; exact remaining
  Printing sizes must now be received before starting Stitching.
- Pre-S15 Printing closure (in progress on 2026-08-27): the rendered store CPM
  showed the exact returned Top Front S=20 (Lay 2, Bundle 1). The browser
  selected that one whole bundle and submitted `CPM-2608-00235` with no other
  size/panel, collapsed row, or accessory. It is currently unlinked and its
  save/fetch/submit run was clean. Its rendered Create action then submitted
  `DC-2026-00021`: only exact S=20, `S-0170` → Sri Krishna Printing, rate
  `₹28.495`, value `₹569.90`, linked to `CPM-2608-00235`. The A81 guard left
  exactly one persisted child and the full browser/API run was clean. The next
  rendered supplier CPM then selected that same whole S20 identity and
  submitted `CPM-2608-00236`, with no other size/panel, collapsed row, or
  accessory. Its rendered Create action submitted `YRP-GRN-2026-00053`
  against `DC-2026-00021`: exact S20 only, Accepted, supplier → `S-0170`,
  input `₹28.495`, output `₹29.495`, total `₹589.90`, ordinary bundle mode,
  and linked `CPM-2608-00236`. Both matrix and persisted child show S20 with
  all other sizes zero/absent, and the browser/API run was clean. The next
  rendered supplier CPM then physically selected the final exact Top Front
  L30 (Lay 2/Bundle 3), XL20 (Bundle 4), and 2XL20 (Bundle 5). Submitted
  `CPM-2608-00237` totals 70 with no S/M, other panel, collapsed row, or
  accessory. Its rendered Create action submitted `YRP-GRN-2026-00054`
  against `DC-2026-00019`: exact L30/XL20/2XL20, Accepted, ordinary-bundle
  mode, input `₹28.495`, output `₹29.495`, and total `₹2,064.65`. It has three
  exact GRN Item → YRP GRN Deliverable → consumption/output SLE → active
  production-link chains and six matching exact CBML rows. The rendered matrix
  is one logical Top Front row with only those three size columns positive;
  the browser/API run was clean.

  The full Printing closure verifier now passes across `GRN51/52/53/54` and
  every child, link, SLE and CBML row. Total material is `120 × ₹28.495 =
  ₹3,419.40`; total process cost is `₹120.00`; final output is
  `120 × ₹29.495 = ₹3,539.40`. All 120 Work Order deliverables have
  `pending=0` and `stock_update=qty`; all 120 receivables have `pending=0`.
  Sri Krishna Printing has no exact or collapsed Top Front remaining.
  `S-0170` has exact S20/L30/XL20/2XL20 plus collapsed M30, exactly 120 with no
  duplicate/loss. Every production SLE is valuation-fresh, every receipt has
  exact `goods_received_note_item` lineage, and no CPM/DC/GRN draft remains.
  U08, U09, U18, and U19 are complete. Printing is closed before S15.
- S15 (in progress, prerequisite checkpoint on 2026-08-27): the owner's Sewing
  Unit Tiruppur master resolves to Supplier/Warehouse `S-0172`, display name
  **Essdee Sewing Unit - Tirupur**, billing address
  `Essdee Knitting Mills Private Limited-Billing-5`. It is enabled and is the
  authoritative `apply_sewing_plan=1` company location; MRP Settings names
  `Stitching` as `finishing_inward_process`. Through the rendered Process Cost
  form, approved `PC-02005` was created for this exact Lot/item/Supplier,
  Stitching, Part=Top, `₹14` per piece, valid 2026-08-27 through 2026-09-30.
  Save, workflow Submit, and Approve all returned HTTP 200 with a clean browser
  run. The rendered Work Order form then created draft `YRP-WO-2026-00048`
  with `Stitching`, `S-0172`, source/delivery location `S-0170`, both billing
  addresses, and `is_internal_unit=1`. Its calculation dialog correctly exposes
  separate Top and Bottom garment rows (120 each). The first acceptance guard
  stopped before calculation submission because its initial 120-total
  assumption had left both rows selected. Historical submitted Work Order
  `WO-2627-00327-1` proves that a Stitching Work Order for this same item is
  intentionally calculated for one Part at a time, and `PC-02005` is explicitly
  Part=Top. Therefore this acceptance Work Order must select Top 120 and clear
  Bottom through the rendered row toggle; no direct API mutation is permitted.
  That Top-only calculation was then submitted from the UI and persisted on the
  draft with 5 calculated Top rows / 120 garments, 20 Piece cut-panel rows /
  600 panels, 5 Nos label rows / 120 labels, one Meter elastic row / 102.7 m,
  and 5 Top receivables / 120 garments at `PC-02005`, ₹14 each. All 26
  deliverables and all 5 receivables have `pending_quantity=qty`. The second
  guard stopped before Work Order submission only because its provisional check
  had incorrectly added mixed Piece/Nos/Meter quantities; the persisted rows
  themselves match the IPD recipe and are now the exact submission contract.
- S15 (complete on 2026-08-27): the rendered Work Order form submitted
  `YRP-WO-2026-00048`; savedocs returned HTTP 200 with zero console, page,
  request, or response errors. The configured submit hook automatically created
  exactly one linked Sewing Plan, `SP-2526-00231`. Its rendered form shows the
  same Work Order, Lot, item, `S-0172`, billing address, and five Top size rows
  S/M/L/XL/2XL = 20/30/30/20/20, total 120. An independent read-only verifier
  reconfirmed the submitted Work Order's process cost, internal-unit flag, all
  calculated/deliverable/receivable quantities and pending balances, one-plan
  uniqueness, exact plan row equality, configured `Stitching` rule, Supplier
  `apply_sewing_plan=1`, and zero Sewing Plan entries before S16. U21 is
  complete.
- S16 (in progress, sequence-rejection checkpoint on 2026-08-27): the rendered
  `/app/sewing-details` page loads `SP-2526-00231` under `S-0172` and the exact
  White/Top S/M/L/XL/2XL matrix 20/30/30/20/20. Before any entry existed, its
  **Record Entry** modal was set to `Sewing Line 1`, `Line Output`, `Accepted`
  and S=1. The UI rendered `Entered quantity cannot be greater than remaining
  Input Qty`; it made no `submit_data_entry_log` request, and read-only before /
  after queries both returned zero rows. This proves a downstream stage cannot
  precede its configured predecessor without leaving a partial write.
  Next, the same rendered modal created `Input Qty` entry `f8n0sq7o68` for
  `Sewing Line 1`, `Accepted`, with 10 in each of the five sizes (total 50).
  Its POST returned HTTP 200, and the persisted entry has the exact five plan
  variants with no missing or extra row; a clean idempotent rerun verified the
  record without creating a duplicate.
  With S Input Qty=10 and the configured Line Output allowance=20%, the UI then
  rejected an attempted S Line Output=13 (maximum 12) with the same predecessor
  balance error. It made no submit request and retained only `f8n0sq7o68`;
  therefore both the order and the configured allowance are enforced before
  persistence.
  The subsequent valid rendered `Line Output` entry is `g9a9e8g03u`: 10 in
  every size, total 50, against the visible Input Qty 10/10/10/10/10. The UI
  POST returned HTTP 200, the modal closed/refreshed, and read-only verification
  proves the exact five variants, `Sewing Line 1`, and `Accepted`.
  The valid rendered `Checking Output` entry is `giqc2pnujl`: it visibly used
  Line Output 10/10/10/10/10 as its predecessor and persisted the same five
  quantities, total 50, under `Accepted`. Its POST and refresh returned HTTP
  200 with a clean browser run.
  Finally, rendered `AQL Output` entry `gs3lr95h6p` visibly used Checking Output
  10/10/10/10/10 and persisted the same total 50 under `Accepted`; its POST and
  refresh also returned HTTP 200 with zero browser errors. The independent S16
  verifier proves exactly four entries and no extras, every entry has exactly
  the five plan variants at 10 each, and the live configuration is precisely
  Input Qty←Order Qty (75%), Line Output←Input Qty (20%), Checking Output←Line
  Output (3%), AQL Output←Checking Output (3%). S16 and U23 are complete. The
  deliberate 50-piece partial chain remains in place for S17's GRN prerequisite
  rejection and correction.
- Pre-S17/U22 Stitching input delivery (in progress on 2026-08-27): read-only
  stock and bundle checks proved all exact Top panels are at Cut Panel Store
  `S-0170`, with only M Top Front 30 remaining as the collapsed bundle returned
  from Printing. Through the rendered Cut Panel Movement form,
  `CPM-2608-00238` selected and submitted the 19 exact bundle-panel identities:
  Top Front 4 sizes, Top Back 5, Sleeve 5, and Neck Rib 5. The JSON's 450 bundle
  units expand by the IPD Sleeve multiplier to 570 physical Pieces for the
  Stitching DC. Both saves returned HTTP 200 with a clean browser; the CPM is
  submitted. Its rendered **Create → Delivery Challan** flow selected
  `YRP-WO-2026-00048` and submitted `DC-2026-00022`, `S-0170 → S-0172`, with
  all 19 exact variant rows / 570 physical Pieces and `allow_non_bundle=0`.
  Preparation, save, and submit returned HTTP 200 with zero browser errors.
  A separate rendered CPM then selected the remaining collapsed M Top Front 30
  (and no exact row) and submitted `CPM-2608-00239`; the stored/rendered moved
  quantity is exactly 30. Its rendered DC flow submitted `DC-2026-00023`,
  `S-0170 → S-0172`, one M Top Front row / 30, with
  `allow_non_bundle=1`; all API calls returned HTTP 200 and the browser was
  clean. The two panel DCs leave all 20 panel deliverables at pending zero.
  Read-only stock proof then found no Lot-specific labels/elastic in `S-0170`.
  The rendered Stock Reconciliation matrix created and submitted
  `YRP-ST-RECO-2026-00004` with five label sizes 20/30/30/20/20 at ₹0.80 and
  `Inner Elastic-40 mm` 102.7 m at ₹3.899635369, all under Lot
  `MRP-UAT-260826-01`, `Accepted`, `S-0170`. The initial zero entry fields were
  normalized to those authoritative item rates on save; the clean reopen and
  submit run returned HTTP 200 with no browser error.
- Pre-S17/U22 Stitching transfer continuation (in progress on 2026-08-27): the
  rendered Work Order action reused and submitted accessory DC
  `DC-2026-00024`, `S-0170 → S-0172`, with five label rows
  20/30/30/20/20 at ₹0.80 and one `Inner Elastic-40 mm` row 102.7 m at
  ₹3.899635369. Its ordinary non-CPM draft correctly retained 20 zero panel
  placeholders for re-editing, while base YRP removed those placeholders on
  Submit; the submitted document therefore has exactly six positive rows and
  total 222.7. All 26 Stitching Work Order deliverables now have pending zero.
  Because this is an internal-unit route, the three DCs first post into the
  configured transit warehouse `S-0165`. Rendered **Complete Transfer** for
  exact-bundle `DC-2026-00022` created and submitted
  `YRP-STE-2026-00054` successfully, transferring all 19 rows / 570 physical
  Pieces from transit to `S-0172`. The same UI action for collapsed
  `DC-2026-00023` created recoverable draft `YRP-STE-2026-00055`, but Submit
  returned HTTP 417 and wrote no submitted transaction: the draft inherited
  `CPM-2608-00239` but not `allow_non_bundle=1`, so exact-bundle validation
  reported M Top Front required 30 versus selected whole-bundle zero. This is
  A82. Essdee completion validation now copies the authoritative
  `allow_non_bundle` mode even when the CPM was already present and also forces
  a spoofed mode back to the referenced transaction's value. All 15 owning
  bundle-filtering unit tests pass. The rendered retry reopened and submitted
  the same `YRP-STE-2026-00055`; its collapsed CBML rows move M Top Front
  `-30/+30` from `S-0165` to `S-0172`. Rendered completion of accessory DC
  `00024` then submitted `YRP-STE-2026-00056`. Independent U22 proof passed all
  three DC legs (38/2/12 SLEs into transit), all three completion legs
  (38/2/12 SLEs into `S-0172`), reciprocal quantity/value pairing, exact Lot
  and Received Type dimensions, and 100% DC transfer fields. A82 and U22 are
  complete.
- S17 negative boundary (in progress on 2026-08-27): rendered **Work Order →
  Create → Make GRN** left Delivery Challan intentionally blank and prepared
  the five accepted Top sizes 20/30/30/20/20, total 120 at ₹14, from `S-0172`
  to `S-0170`. UI save created draft `YRP-GRN-2026-00055`. Submit returned the
  expected HTTP 417 **Sewing Plan Qty Mismatch** for every size: configured
  Checking Output is 10 each; the attempted GRN quantities are
  20/30/30/20/20 and the overages are 10/20/20/10/10. The draft remains
  docstatus 0 and an authenticated post-failure check found zero active Stock
  Ledger Entries for it. This completes the required rejection/no-stock-write
  half of S17; the same draft is retained for retry after the remaining Sewing
  entries are created through the rendered Sewing Details UI.
- S17 correction continuation (in progress on 2026-08-27): the rendered Sewing
  Details UI created the remaining 70 pieces at each stage in configured size
  order 10/20/20/10/10. The new Input `7a7dti59ru`, Line Output `7h3rnf71s5`,
  Checking Output `7o65nfov97`, and AQL Output `7v225idd53` entries combine with
  the earlier 50-piece entries to give exactly 20/30/30/20/20 and total 120 at
  every stage. Independent read-only verification found exactly two entries per
  stage, the approved Sewing Plan/station/Accepted dimensions, and no duplicate
  stage or variant quantity.
- S17 valid partial-receipt attempt (blocked by A83 on 2026-08-27): the same
  rendered draft `YRP-GRN-2026-00055` was corrected to exactly five Accepted
  Work Order Receivable rows, 10 per size and total 50 at ₹14, deliberately
  retaining the remaining 70 pieces for the later Rework Received Type case.
  Save completed successfully. Submit then returned HTTP 417
  `No deterministic fabric consumption plan was found for this receipt.` The
  draft remains docstatus 0 with the five exact `ref_docname` links and no Stock
  Ledger Entry. Code tracing proved Stitching was falling through to the generic
  fabric planner, which cannot produce a fabric step or identity row for this
  garment process. This is tracked as A83; no S18 or later business record will
  be created until the same UI draft submits with deterministic mapped inputs.
- S17/A83 correction complete (2026-08-27): the Essdee-only planner reuses the
  garment Work Order engine and maps each received size to its exact four panel
  inputs, size label, and elastic allocation. All 35 focused valuation-contract
  unit tests pass. The rendered UI reopened and submitted the same
  `YRP-GRN-2026-00055`; five Accepted output rows of 10 each produced exactly 30
  mapped input rows and no browser console/page/request/response failures.
  Independent verification proved 343 total input units, 26 grouped outgoing
  SLEs, five output SLEs, exact Work Order input counters, receivable pending
  sizes 10/20/20/10/10, and 30 active production valuation links. Actual
  material value is ₹6,605.434320866; process value is exactly ₹700 (50 × ₹14);
  output value is ₹7,305.434320866. The rendered **Complete Transfer** action
  created and submitted `YRP-STE-2026-00057`; its ten paired SLEs conserve
  quantity/value and move all 50 Accepted pieces from transit `S-0165` to
  destination `S-0170`. The GRN now reports transfer complete, 50 transferred,
  and 100%. A83, S17, and U24 are complete; 70 Stitching pieces remain for the
  mandated pre-full-receipt Finishing/Rework sequence.
- S18 setup correction (in progress on 2026-08-27): the rendered Process Cost
  form initially duplicated historical Ironing/Packing template `PC-02001` and
  approved test cost `PC-02006` at ₹3 against `Colour = White`. The rendered
  Work Order calculation then saved recoverable draft `YRP-WO-2026-00049` with
  the correct five Top calculated rows (20/30/30/20/20), 24 positive input
  rows, and five Pack receivables, but their computed process rate was ₹0. The
  reason is deterministic: these Pack-stage output variants carry `Size` and
  `Stage`, not `Colour`, while base YRP resolves a dependent Process Cost from
  the attributes on each receivable variant. This is an invalid test-cost
  attribute selection, not a submitted transaction or an Essdee code defect.
  The Work Order remains draft and no Finishing Plan exists. The incorrect test
  cost will be expired through its rendered workflow and replaced by a
  Size-based ₹3 cost before the same draft is saved, submitted, and verified.
- S18 complete (2026-08-27): the rendered workflow expired incorrect test cost
  `PC-02006` and approved replacement `PC-02007`, dependent on `Size`, with
  ₹3 rates for S/M/L/XL/2XL. The clean browser then saved and submitted the same
  `YRP-WO-2026-00049` for internal supplier `S-0171` (**Essdee Ironing Unit -
  Tirupur**) and delivery location `S-0170`; all savedocs/workflow calls returned
  HTTP 200 with no console, page, request, or response failures. It contains five
  Top calculated rows 20/30/30/20/20, 24 positive deliverables, five Pack
  receivables at ₹3, and total process value ₹360. Submission created and linked
  Finishing Plan `FP-2526-00238` while Stitching Work Order
  `YRP-WO-2026-00048` still had exactly 70 pending pieces. Rendered and
  independent read-only verification agree on plan totals: Cutting/Inward 120,
  Stitching Delivered 50, Accepted 50, Rework/Rejected zero, five detail rows,
  five GRN projection rows, status **Partially Received**, and no incomplete
  internal GRN transfers. No downstream Ironing/Packing DC or GRN exists yet.
  Automatic box-sticker creation correctly skipped this test item because no
  `FG Item Master` exists for `XMAS PJ5 - MENS`; this is outside S18 and is not
  counted as sticker coverage. S18 is complete; the configured-company-location
  negative boundary was later proved under U32/A104.
- S19 preflight (in progress on 2026-08-27): independent state proof finds only
  completed Stitching GRN `YRP-GRN-2026-00055`, Finishing Plan baseline
  Delivered/Accepted/Rework = 50/50/0, and exact Stitching receivable pending
  S/M/L/XL/2XL = 10/20/20/10/10 (70 total). `Misstitch` is an eligible migrated
  Received Type and is neither the configured default `Accepted` nor configured
  rejected type `Rejected`. S19 will receive exactly 5 of each size (25 total)
  into `Misstitch`, complete the internal transfer, and deliberately leave
  5/15/15/5/5 (45 total) for S21. No business mutation was made by this
  preflight.
- S19/A84 correction complete (2026-08-27): the failed rendered Save wrote no
  document or stock. The Essdee-only ownership matcher now permits the GRN's
  configured output Received Type to differ from the Work Order receivable
  template while retaining exact ref/item/UOM/Lot/set-combination validation;
  all 36 focused valuation-contract tests pass. The same rendered **Work Order
  → Create → Make GRN → + Misstitch** flow saved and submitted
  `YRP-GRN-2026-00056` with five rows of 5, total 25, and exactly 30 mapped
  panel/accessory inputs. All three savedocs calls returned HTTP 200 and the
  successful retry had no console/page/request/response failure. Rendered
  **Complete Transfer** submitted `YRP-STE-2026-00058`, moving the five output
  rows from transit `S-0165` to `S-0170` under Lot
  `MRP-UAT-260826-01` and Received Type `Misstitch`.
  Independent verification proved 26 Accepted input SLEs / 171.5 input units,
  five Misstitch output SLEs / 25 pieces, 30 active valuation production links,
  ₹3,302.717160433 material value, ₹350 process value, and
  ₹3,652.717160433 output value. The completion has ten reciprocal,
  value-preserving SLEs. Work Order pending is now exactly 5/15/15/5/5 (45),
  and its five calculated rows each hold `Accepted: 10, Misstitch: 5`.
  Finishing Plan `FP-2526-00238` rebuilt at the authoritative Work Order
  calculation boundary to Delivered 75, Accepted 50, and five rework rows of 5
  (25 total), with no incomplete transfer. A84, S19, U25, and U26 are complete.
- S20 preflight (in progress on 2026-08-27): S19 idempotently created Rework
  Details source `RW-04433` with five Misstitch rows of 5 and no prior
  reworked/rejected quantity. Its historical header warehouse is transit
  `S-0165`, while independent stock checks correctly find the completed live
  stock as 5 per size at final warehouse `S-0170`. Finishing baseline is 25
  rework and zero reworked; no rework Work Order exists. The acceptance user has
  GRN Rework Item read/write and Work Order create permission. To cover both
  operator paths without double-consuming stock, the rendered Rework Details
  page will first convert 1 per size (5) to Accepted, then the generic rendered
  **Create Rework** Work Order/DC/GRN flow will dispatch and receive the remaining
  4 per size (20). Every conversion/transfer will be reconciled against its
  source FIFO value and Finishing projection before S21.
- S20 Rework Details partial clear complete (2026-08-27): the rendered
  `/desk/rework-details` page filtered Lot `MRP-UAT-260826-01` and Received Type
  `Misstitch`, loaded only `RW-04433`, expanded all five sizes, and entered
  Reworked = 1 in each size. **Update Reworked Piece** and its confirmation
  returned HTTP 200; the rendered pending total changed 25 → 20 with no browser
  error. Independent proof found five source rows updated from reworked 0 → 1,
  five conversion audit rows, and ten paired SLEs at actual warehouse `S-0170`:
  Misstitch -1 / Accepted +1 per size with Lot preserved. Total quantity and
  value both net to zero; ₹730.543432086 moved at source FIFO value. Live stock
  is now exactly Misstitch 4 and Accepted 11 per size. Finishing Plan remains 25
  total rework but now records 1 reworked per size (5 total). The remaining 20
  is reserved for the S20 rework Work Order/DC/GRN branch.
- S20/A85 boundary failure recorded before rework Work Order creation
  (2026-08-27): a permission-checked read of the exact generic **Create
  Rework** source API still returned available 5 for every Misstitch source
  child of `YRP-GRN-2026-00056`, while the independently reconciled live stock
  after Rework Details is 4 per size. No popup selection, Work Order, DC, GRN,
  or SLE was written by this check. The missing decrement is the direct clear
  recorded against the exact `source_grn_item` in `RW-04433`; A85 must pass
  focused tests and the rendered quantity-cap retry before the remaining 20
  pieces can be dispatched.
- S20/A85 correction and generic rework Work Order complete (2026-08-27):
  the Essdee override hook was refreshed and all 38 valuation-contract tests
  passed. From submitted Stitching `YRP-WO-2026-00048`, the rendered **Create
  Rework** popup returned five exact `YRP-GRN-2026-00056` source children,
  visibly rendered S/M/L/XL/2XL with availability/max 4 each, and retained Same
  Supplier. Entering 4 in every cell created and then submitted
  `YRP-WO-2026-00050`: parent `YRP-WO-2026-00048`, No Cost, supplier `S-0172`,
  delivery `S-0170`, five Misstitch deliverables of 4 carrying the exact source
  GRN child, and five Accepted receivables of 4 at zero process cost. All
  rendered API calls returned HTTP 200 with no console/page/request errors.
  Independent proof reconciled 20 pending in and out, no DC/GRN/SLE yet, zero
  remaining eligible source on the parent, and an intentionally unchanged
  Finishing projection of rework 25 / reworked 5. A85 is complete; the next
  permitted mutation is this rework Work Order's Delivery Challan.
- S20 rework dispatch first leg complete (2026-08-27): from submitted
  `YRP-WO-2026-00050`, rendered **Create → Make DC** prepared five exact
  Work Order Deliverable references at 4 Misstitch pieces per size. A new DC
  correctly derives internal-unit mode only at its authoritative Save boundary;
  the unsaved client default of zero is not a defect. The UI saved and submitted
  `DC-2026-00025`, `S-0170` → supplier `S-0172`, total 20, stock value
  ₹2922.173728344, with no browser/API error. Independent SLE proof found five
  reciprocal pairs: -4 from `S-0170` and +4 into transit `S-0165`, exact Lot and
  Misstitch bucket, identical per-size FIFO rate/value, net quantity/value zero.
  All five rework Work Order deliverable pending quantities are now zero;
  `transfer_complete=0` is correct until the rendered DC Completion reaches the
  supplier warehouse.
- S20 rework dispatch completion complete (2026-08-27): rendered **Complete
  Transfer** created recoverable draft `YRP-STE-2026-00059` with five exact DC
  item references, 4 Misstitch pieces per size, total value ₹2922.173728344.
  The form header intentionally retains the original `S-0170` → `S-0172`
  route; the DC Completion posting contract resolves transit at ledger time.
  Submitting the same UI draft completed `DC-2026-00025` at 20/20 and 100%,
  with no browser/API error. Independent proof found five value-preserving SLE
  pairs that actually debit transit `S-0165` and credit supplier warehouse
  `S-0172`, exact Lot/Misstitch and FIFO rate per size. `S-0165` and `S-0170`
  Misstitch are now zero, while `S-0172` is exactly 4 per size. The next
  permitted mutation is the rework GRN against this completed DC.
- S20 rework GRN first leg and A86 boundary (in progress on 2026-08-27): the
  rendered Work Order **Make GRN** selector chose completed
  `DC-2026-00025`; the editor showed five Accepted outputs of 4 and saved and
  submitted `YRP-GRN-2026-00057` as an internal-unit rework receipt, total 20
  and ₹2922.173728344. Base's dedicated rework posting correctly used each
  exact GRN item/DC item as lineage: supplier `S-0172` Misstitch -4 and transit
  `S-0165` Accepted +4 per size at identical FIFO value, all Work Order
  receivables and DC received quantities reached zero/4 respectively. Zero
  Essdee `grn_deliverables` is expected for this base-owned route. However,
  Finishing incorrectly became delivered 19 / Accepted 14 per size while its
  rework row remained quantity 5 / reworked 1, proving A86. No GRN Completion
  was created; correct the authoritative projection before moving stock from
  transit to `S-0170`.
- S20/A86 correction complete (2026-08-27): 18/18 Finishing service tests and
  38/38 valuation-contract tests pass. The rendered Finishing Plan **Fetch
  Rejected Quantity** action now uses the complete authoritative rebuild. On
  `FP-2526-00238`, the live UI proved the exact before/after transition for all
  five sizes: false delivered 19 / Accepted 14 / reworked 1 became original
  delivered 15 / Accepted 10 / reworked 5; every rework child became quantity
  5 / reworked 5 / rejected 0. No browser, page, request, or API error occurred.
  A86 is complete. `YRP-GRN-2026-00057` remains submitted and correctly holds
  20 Accepted pieces in transit; the next permitted mutation is its rendered
  GRN Completion to `S-0170`.
- S20 complete (2026-08-27): rendered GRN Completion
  `YRP-STE-2026-00060` moved five Accepted rows of 4 from transit `S-0165` to
  final warehouse `S-0170`, total 20 / ₹2922.173728344, and completed
  `YRP-GRN-2026-00057` at 20/20 and 100% without changing the corrected
  Finishing projection. Independent end-to-end reconciliation covered
  `YRP-WO-2026-00050`, `DC-2026-00025`, DC Completion
  `YRP-STE-2026-00059`, `YRP-GRN-2026-00057`, and GRN Completion
  `YRP-STE-2026-00060`. Every one of the 40 SLE legs retained the exact child,
  item, Lot, Received Type, FIFO rate, and reciprocal value; every voucher and
  the full round trip net to zero quantity/value. Final per-size stock is
  `S-0170` Accepted 15 / Misstitch 0, with transit and supplier rework buckets
  zero. Finishing remains original inward 15, Accepted 10, reworked 5; all five
  rework children are 5/5 with zero rejection. S20, U29, and U30 are complete.
- S21 preflight (in progress on 2026-08-27): submitted Stitching
  `YRP-WO-2026-00048` has one exact remaining Accepted receipt boundary:
  S/M/L/XL/2XL pending 5/15/15/5/5 (45 total). Its five calculated rows each
  remain authoritative at received 15 with `Accepted: 10, Misstitch: 5` before
  the transaction. The only ordinary active Stitching GRNs are completed
  `YRP-GRN-2026-00055` and `YRP-GRN-2026-00056`; no draft exists. Finishing
  baseline is delivered 15 / Accepted 10 / reworked 5 per size and every rework
  child is 5/5. The next permitted mutation is a rendered blank-DC **Make GRN**
  for exactly the 45 pending Accepted pieces.
- S21 final Stitching GRN first leg complete (2026-08-27): rendered blank-DC
  **Make GRN** prepared exact Accepted S/M/L/XL/2XL quantities 5/15/15/5/5,
  rate ₹14, and saved/submitted `YRP-GRN-2026-00058` for 45 with 30 exact
  mapped consumption rows. It is an internal-unit receipt correctly awaiting
  Completion. All UI/API calls returned HTTP 200 with no browser error.
  Immediately after the authoritative submitted Work Order calculation
  boundary, all five `YRP-WO-2026-00048` receivable pending quantities became
  zero; calculated received became 20/30/30/20/20 with Accepted
  15/25/25/15/15 and Misstitch 5 each. Finishing changed in the same exact
  shape to delivered 20/30/30/20/20 and Accepted 15/25/25/15/15 while retaining
  reworked 5 and every rework child 5/5. The next permitted mutation is this
  GRN's rendered Completion; S21 remains open until its mapped SLE/value and
  final warehouse balance are independently reconciled.
- S21 complete (2026-08-27): rendered GRN Completion
  `YRP-STE-2026-00061` moved exact Accepted 5/15/15/5/5 from transit `S-0165`
  to `S-0170`, total 45 and ₹6572.94107109, and completed
  `YRP-GRN-2026-00058` at 45/45 and 100% with no UI/browser/API error.
  Independent proof reconciled all five output children, 30 mapped input rows,
  26 aggregated consumption SLEs, five output SLEs, 30 active valuation
  production links, and five value-preserving Completion pairs. Material value
  is ₹5942.941071095, Stitching process value is exactly ₹630, and output value
  is ₹6572.94107109. Every exact child, Work Order input/output ownership, Lot,
  Received Type, and lineage link passed. Final Accepted stock at `S-0170` is
  S/M/L/XL/2XL 20/30/30/20/20 with zero transit; all Stitching receivable
  pending is zero. Finishing remains delivered 20/30/30/20/20, Accepted
  15/25/25/15/15, and reworked 5 each. S21 is complete; S22 is now the only
  permitted next phase.
- S22/A87 preflight boundary (2026-08-27): no business mutation was made. The
  submitted Cutting Work Order has every one of its 45 panel receivables at
  zero pending, while its Process carries source-era `additional_allowance =
  300%` and finalized base `wo_excess_allowed_percentage = 0%`. Existing
  Cutting Plan cloth is fully consumed and its four initial DC/LaySheet/GRN
  paths reconcile exactly. Base GRN validation reads only the zero target
  field, so an additional receipt would contradict the migrated source
  configuration. A87 is recorded before correcting the migration/setup
  redundancy; S22 stays open and no additional stock, DC, LaySheet, or GRN has
  yet been created.
- S22/A87 correction complete (2026-08-27): Essdee migration, setup patch, and
  fixtures now use only base `wo_excess_allowed_percentage`; a safe post-sync
  patch preserves an existing nonzero base value and otherwise carries the
  legacy percentage before removing the obsolete Custom Field. All 17
  transformer tests, Python compilation, fixture JSON validation, and diff
  whitespace checks pass. Through the rendered `Cutting` Process form, the
  acceptance user changed the base field from 0% to the migrated source value
  300%; Save returned HTTP 200 with no console, page, request, or response
  error. A87 is complete. S22 remains open; its next mutation is the additional
  cloth Stock Reconciliation required before an excess Cutting DC/LaySheet run.
- S22 additional-cloth stock boundary complete (2026-08-27): through the
  rendered Stock Reconciliation form, saved and submitted
  `YRP-ST-RECO-2026-00005` at warehouse `S-0170`, Lot
  `MRP-UAT-260826-01`, Received Type `Accepted`. It established exactly
  1.824 kg of `30's GL Dyed Fabric New-72 Dia-White` at ₹370/kg
  (₹674.88), 2.160 kg of `30's GL Dyed Fabric New-72 Dia-Green` at
  ₹370/kg (₹799.20), and 0.096 kg of `30's GL Lycra Rib-72 Dia-White`
  at ₹280/kg (₹26.88), total value ₹1,500.96. Save and Submit both
  returned HTTP 200 and independent read-only ledger inspection confirmed the
  three exact posted buckets. The automation clicked Submit immediately after
  Save and exposed a delayed base dimension-control callback after the form
  remounted; the submitted record itself is valid. A stable rendered reopen
  subsequently displayed all three exact rows and returned the dimension API
  at HTTP 200 with zero console/page/request errors, proving this was the
  resolved automation readiness race rather than a persistent record/UI error.
- S22/A88 preflight boundary (2026-08-27): no Delivery Challan was saved. The
  rendered **Work Order → Create → Make DC** route correctly offered all
  four fully delivered Cutting inputs for excess entry, each with stored
  quantity/pending zero. However, every number input rendered `max="0"`, and
  the Vue change handler clamped any positive entry back to zero. This
  contradicts the base server's explicit excess-delivery contract and blocks
  the next UI mutation. A88 is recorded before the Essdee-only adapter fix;
  the stocked fabric remains at `S-0170` and no DC/transfer/LaySheet/GRN was
  created from it.
- S22/A88 correction and additional Cutting dispatch first leg complete
  (2026-08-27): four focused adapter tests and Python compilation pass. The
  rendered **Work Order → Create → Make DC** form showed all four inputs
  without `max="0"`; it retained no cap after Draft Save/reload. The UI entered
  only white main 1.824 kg at ₹370, green main 2.160 kg at ₹370, and white
  rib 0.096 kg at ₹280, leaving AOP at zero, then saved and submitted
  `DC-2026-00026`. The internal-unit first leg moved total 4.080 kg / ₹1,500.96
  from `S-0170` to transit `S-0165`; Save and Submit returned HTTP 200 with
  zero console/page/request errors. Independent proof found reciprocal pairs
  `YRP-SLE-2026-07645/07646`, `07647/07648`, and `07649/07650`, preserving
  exact child, item, Lot, Accepted bucket, rate, and value. Source balances are
  zero and transit balances are 1.824/2.160/0.096 kg; Work Order pending is now
  intentionally -1.824/-2.160/-0.096 kg while its consumption counter remains
  at the original 18.24/21.60/0.96 kg. A88 is complete. The next permitted
  mutation is the rendered DC Completion for `DC-2026-00026`.
- S22 additional Cutting dispatch completion complete (2026-08-27): rendered
  **Complete Transfer** created and submitted `YRP-STE-2026-00062`, preserving
  the three exact `DC-2026-00026` child references, quantities, Lot, Accepted
  bucket, rates, and total value ₹1,500.96. The form shows the original
  `S-0170` → `S-0164` business route while the authoritative internal-unit
  ledger correctly debits transit `S-0165` and credits cutting supplier
  warehouse `S-0164`. Pairs `YRP-SLE-2026-07651/07652`, `07653/07654`, and
  `07655/07656` preserve equal value and finish with transit zero and supplier
  balances 1.824/2.160/0.096 kg. `DC-2026-00026` is 4.08/4.08, 100% complete,
  with no remaining **Complete Transfer** action. All rendered calls returned
  HTTP 200 with zero browser errors. The next permitted mutation is only
  **Cutting Plan → Fetch and Calculate → Fetch Received Cloth**; do not
  regenerate the plan's already-finalized requirements.
- S22 Cutting Plan received-cloth refresh complete (2026-08-27): used only the
  rendered **Fetch and Calculate → Fetch Received Cloth** action; **Generate**
  was not invoked. `CP-2608-00015` retained its finalized required weights
  18.24/21.60/0.96/45.72 kg and existing used weights, while received weights
  became 20.064 kg white main, 23.760 kg green main, 1.056 kg white rib, and
  45.720 kg AOP. Exact new balances are 1.824/2.160/0.096/0 kg. The action and
  reload returned HTTP 200 with zero browser errors. The next permitted
  mutations are three existing-marker LaySheets for Top Front/Back, Sleeve,
  and Neck Rib; all must complete before the Finishing cutting projection can
  advance one ratio without double counting.
- S22 additional Cutting LaySheets and GRNs complete (2026-08-27): all three
  existing markers were reused through the rendered LaySheet form; no Cutting
  Plan requirements or markers were regenerated. `CLS-2608-00121` (Lay 6)
  consumed exactly 1.824 kg white main fabric in one Open Width/effective bit
  and created Top Front plus Top Back S/M/L/XL/2XL bundles 2/3/3/2/2 per
  panel. Its rendered recovery **Update Status** boundary submitted
  `YRP-GRN-2026-00059` with ten exact output rows / 24 components, ten mapped
  GRN Deliverables, material ₹674.88, Cutting ₹9.00, and output ₹683.88.
  `CLS-2608-00122` (Lay 7) consumed exactly 2.160 kg green main fabric in one
  Open Width/effective bit and created Sleeve garment bundles 2/3/3/2/2; the
  two-Sleeve component multiplier correctly produced GRN quantities
  4/6/6/4/4. `YRP-GRN-2026-00060` therefore contains five exact rows / 24
  components and five mapped deliverables, material ₹799.20, Cutting ₹9.00,
  and output ₹808.20. `CLS-2608-00123` (Lay 8) consumed exactly 0.096 kg white
  rib in one Open Width/effective bit and created Neck Rib 2/3/3/2/2;
  `YRP-GRN-2026-00061` contains five exact rows / 12 components and five mapped
  deliverables, material ₹26.88, Cutting ₹4.50, and output ₹31.38. Every
  LaySheet finishes `Label Printed`, `reverted=0`, and links its submitted GRN.
  The first traversal initially navigated away while one Finishing background
  read was still settling; the driver was corrected to await that response.
  A complete rendered reuse traversal then loaded all three LaySheets, all
  three GRNs, and the Finishing Plan with every API at HTTP 200 and zero
  console, page, failed-request, or failed-response errors.
- S22 independent stock/value/projection proof complete (2026-08-27): the
  three GRNs have 20 exact output children, 20 nonblank
  `goods_received_note_item` mappings, three consolidated cloth-consumption
  SLEs, 20 exact output SLEs, and 20 active Stock Valuation Production Links.
  `YRP-SLE-2026-07657` through `07679` conserve the exact 4.080 kg inputs and
  ₹1,500.96 material value; all are Lot `MRP-UAT-260826-01`, Accepted,
  warehouse `S-0164`, and valuation-fresh. Cutting adds exactly ₹22.50, so
  output value is ₹1,523.46. All three input fabric buckets at `S-0164` are
  zero after consumption, while every extra panel/component bucket equals its
  exact GRN quantity. Cutting Work Order deliverable counters are now
  20.064/23.760/1.056/45.720 kg against ordered
  18.24/21.60/0.96/45.72, with intentional excess pending
  -1.824/-2.160/-0.096/0. The Cutting Plan now has received=used and zero
  balance for all four cloth rows. Crucially, intermediate GRNs `00059` and
  `00060` created no Work Order Track Piece: only final required-component GRN
  `00061` created the five extra Top piece rows 2/3/3/2/2. Calculated Top and
  Finishing Cutting therefore rebuild exactly to 22/33/33/22/22, while Bottom
  remains 20/30/30/20/20. Through the rendered Finishing Plan, **Fetch Rejected
  Quantity** invoked the complete authoritative rebuild twice. Before, after
  the first click, and after the second click were byte-for-byte equal for the
  business projection: Cutting 22/33/33/22/22, Stitching delivered
  20/30/30/20/20, Accepted 15/25/25/15/15, Misstitch 5 each, reworked 5 each,
  and zero rejection. Both rebuilds and reloads returned HTTP 200 with zero
  browser errors. S22 is complete without incremental double counting; S23 is
  now the only permitted next phase.
- S23 preflight boundary (2026-08-27): no business mutation was made. Rendered
  `FP-2526-00238` is **Ready to Pack** and shows the exact Accepted White/Top
  balance S/M/L/XL/2XL = 20/30/30/20/20, Rework 5/5 complete per size, zero
  delivered-to-finishing, zero packed/dispatched, and empty DC/GRN/Stock Entry/
  return/incomplete-transfer lists. Its **Item Details → Create DC** dialog
  renders one checked White/Top row with the same 120-piece balance and five
  editable quantities. Its **GRN → Make GRN** dialog correctly renders dynamic
  Size Ratio Packing, colours White/Green, the configured 2:3:3:2:2 ratio, and
  12/12 pieces per box. The submitted internal `YRP-WO-2026-00049` has five
  garment deliverables and 19 packing-accessory deliverables; every pending
  counter is still original and there is no downstream transaction. Read-only
  stock proof found all five Accepted garment buckets fully available at
  `S-0170` (20/30/30/20/20) with zero transit/supplier stock, but all 19
  required tags/stickers/hangers/polybags/pads/cartons are zero for this Lot at
  `S-0170`, transit, and `S-0171`. The rendered dialogs and all background APIs
  returned HTTP 200 with zero browser error. Therefore the next permitted S23
  mutation is a rendered Stock Reconciliation for those exact 19 accessory
  requirements, followed by their Work Order delivery; creating a Finishing
  GRN before that prerequisite would not qualify the complete packing flow.
- S23 packing-accessory stock boundary (2026-08-27): through the rendered Stock
  Reconciliation form, 11 base-item selections were expanded into exactly 19
  required variants for Lot `MRP-UAT-260826-01`, Accepted, warehouse `S-0170`.
  All quantities and nonzero historical rates were entered in the UI; the 12
  available Transparent Size Sticker columns were explicitly inspected and
  only S/M/L/XL/2XL were populated. Submitted
  `YRP-ST-RECO-2026-00006` contains exactly 19 positive children and produced
  exactly 19 active SLEs, `YRP-SLE-2026-07680` through `07698`, with one unique
  voucher-detail mapping each. Every resulting bucket equals its Work Order
  requirement, all quantity/rate/value/dimension checks pass, total target
  quantity is 880 and total value is ₹3,130.80, and the Work Order pending
  counters correctly remain unchanged until delivery. The first post-submit
  transition raised one asynchronous Frappe control-construction page error
  after both Save and Submit had already returned HTTP 200; a separate clean
  rendered load of the submitted document showed all 19 rows/rates correctly,
  every API at HTTP 200, and zero console/page/network errors. This is recorded
  as a non-reproduced transition race, not silently discarded; G02 remains
  open. The next permitted S23 mutation is the Work Order accessory Delivery
  Challan and its internal transfer completion.
- S23 packing-accessory delivery boundary and A89 correction (2026-08-27): the
  rendered Work Order **Create → Make DC** editor initially offered all five
  garment sizes plus the 19 accessories. The five garment inputs were visibly
  set to zero so their exact 20/30/30/20/20 balance remains available for the
  later partial Finishing Plan DCs. Draft Save exposed A89: seven unrelated
  zero-size Sticker placeholders with numeric-zero Link values made the draft
  non-reloadable. After the Essdee-only cleanup and two focused passing
  regressions, the same `DC-2026-00027` rendered with five valid editable zero
  garment rows and 19 positive accessory rows, then submitted with exactly the
  19 positive children, total quantity 880, and stock value ₹3,130.80. Its
  rendered **Complete Transfer** created/submitted `YRP-STE-2026-00063` with
  the same 19 exact item/rate/value/dimension rows. Independent ledger proof
  found 38 mutually paired DC SLEs for `S-0170 → S-0165` and 38 mutually
  paired completion SLEs for `S-0165 → S-0171`, with equal/opposite quantity
  and value per voucher detail. Every accessory bucket is now zero at source
  and transit and equals its requirement at `S-0171`; all 19 accessory Work
  Order pending counters are zero, while the five garment pending counters
  remain exactly 20/30/30/20/20. Save/reload/submit/completion were HTTP 200
  with zero console/page/network error after the fix. The next permitted S23
  mutation is the first partial garment Delivery Challan from Finishing Plan.
- S23 first partial garment delivery boundary and A90 preflight (2026-08-27):
  through the rendered Finishing Plan **Item Details → Create DC** dialog,
  S/M/L/XL/2XL = 10/15/15/10/10 were entered and submitted as
  `DC-2026-00028`; all five rows are Accepted, linked to the exact Ironing and
  Packing Work Order inputs, and total 60 pieces with stock value
  ₹8,765.54627619. Its rendered **Complete Transfer** created/submitted
  `YRP-STE-2026-00064`. Independent verification found exactly 10 mutually
  paired SLEs on each leg, `S-0170 → S-0165 → S-0171`, with equal/opposite
  quantity and value and reciprocal pair links per voucher detail. Current
  source and supplier balances are each 10/15/15/10/10 and transit is zero;
  the garment Work Order delivered and pending balances are also exactly
  10/15/15/10/10 with received/consumed still zero. The rendered Finishing
  Plan remains **Ready to Pack**, shows Delivered 10/15/15/10/10 and Balance
  10/15/15/10/10, and preserves all prior cutting/stitching/rework values;
  every inspected request returned HTTP 200 with zero browser error. No packing
  GRN was created: pre-submit code review exposed A90, because current dynamic
  packing version 2 bypasses the mapped planner and the old planner omits all
  19 accessories. The next permitted S23 mutation is the first partial packing
  GRN only after A90 is fixed and focused deterministic allocation tests pass.
- A90 correction boundary (2026-08-27): no business record was written. New
  dynamic Packing GRNs now enter the mapped planner, allocate the immutable
  batch colour/size to the exact delivered garment rows, recalculate the 19
  accessories through the same Item BOM engine that created the Work Order,
  and cap every input by delivered-minus-consumed stock. Size-specific inputs
  map to their matching packed-size output; the nine shared accessory variants
  are proportionally mapped across every positive output so material value is
  not concentrated into one size, with the last share conserving all rounding.
  The current two-box White 2:3:3:2:2 dry run maps 5 garment plus 19 distinct
  accessory inputs into 60 exact GRN Deliverable rows across all five outputs:
  garments/tags/size stickers = 4/6/6/4/4, seven shared piece accessories = 24
  each, and four pack accessories = 2 each. A no-write sequential proof then
  passed 2 boxes/24 pieces, 3 boxes/36 pieces, a blocked over-allocation before
  further garment delivery, and 5 boxes/60 pieces after simulating that second
  delivery; totals end at exactly 10 boxes/120 pieces with all 24 Work Order
  inputs fully consumed. The full valuation-contract, Finishing-service, and
  dynamic-packing modules all exit zero, compile and diff checks pass, and base
  YRP was not edited for A90. The next permitted S23 mutation is the first
  two-box Packing GRN through the rendered Finishing Plan dialog.
- S23 first two-box Packing GRN / A91 failed display boundary (2026-08-27):
  the rendered Finishing Plan GRN dialog selected White, entered 2 boxes, kept
  the visible 2:3:3:2:2 ratio at 12/12 pieces per box, and displayed totals
  S/M/L/XL/2XL = 4/6/6/4/4 and 24 pieces. Its existing UI API returned HTTP 200
  and submitted `YRP-GRN-2026-00062`. The transaction itself proves A90:
  version 2, one exact two-box/24-piece batch, five positive outputs, 60 mapped
  rows over all 24 distinct Work Order inputs, mapped state 1, nonzero material
  value on every row, and persisted consumption/output SLE lineage. Total
  packed output value is ₹4,204.378510476. Verification deliberately stopped
  before internal transfer completion because A91 is visible on the submitted
  form: output quantities 4/6/6/4/4 carry UOM `Box` even though they are stock
  Pieces and the authoritative batch total is only 2 boxes. Two background
  Finishing projection requests were aborted only because the driver navigated
  away during the successful callback reload; there was no HTTP failure,
  console error, or page error. The next permitted mutation is rendered cancel
  of this undispatched/uncompleted GRN after the Essdee-only A91 fix and focused
  reversal tests are ready; then the same two-box receipt must be recreated.
- A91 rendered cancellation/reversal boundary (2026-08-27): focused dynamic
  GRN and Work Order UOM regressions pass under the Essdee-only correction.
  The rendered submitted form for `YRP-GRN-2026-00062` proved it was still
  undispatched and uncompleted, then **Cancel** returned HTTP 200. The browser
  observed zero console, page, network, or HTTP failures and reloaded the
  document as docstatus 2 with mapped state -1. Independent reversal proof
  found zero active GRN SLEs, all 58 immutable submit/cancel history SLEs,
  all 60 valuation-production links inactive, every one of the 24 Work Order
  input `stock_update` counters back at zero, and every calculated garment
  `received_qty` back at zero. All source balances at `S-0171` equal their
  delivered quantities, all five packed outputs are zero at both transit
  `S-0165` and destination `S-0170`, and `FP-2526-00238` reports packed and
  dispatched quantities zero for every size. No amendment was made. The next
  permitted mutation is the same rendered two-box Packing GRN recreated under
  the A91 fix, with Piece UOM and unchanged mapping/value proof required before
  internal transfer.
- A91 corrected two-box Packing GRN boundary (2026-08-27): from the rendered
  `FP-2526-00238` GRN dialog, the operator selected White, entered 2 boxes, and
  retained the visible S/M/L/XL/2XL ratio 2:3:3:2:2 (12 pieces per box). The
  existing UI create method returned HTTP 200 and submitted replacement
  `YRP-GRN-2026-00063`; no draft or amendment of the cancelled document was
  reused. A clean rendered reload proves five outputs 4/6/6/4/4, all with UOM
  and stock UOM `Pieces`, conversion 1, version 2 batch totals 2 boxes/24
  pieces, mapped state 1, and no console/page/request/HTTP error. Independent
  proof finds 60 exact mappings over 24 distinct Work Order inputs, 24 active
  consumption SLEs followed by five output SLEs, and 60 active production
  links. Material value ₹4,132.378510476 plus process value ₹72 equals output
  value ₹4,204.378510476 exactly; Work Order counters, `S-0171` source balances,
  and `S-0165` transit outputs reconcile. The two slow Finishing stock requests
  labelled `ERR_ABORTED` in the mutating browser run were navigation artefacts:
  the business request and every returned request were HTTP 200, and the
  subsequent no-mutation rendered reload recorded zero failed requests. A91 is
  fixed. The next permitted mutation is this GRN's internal transfer completion
  through its rendered form, followed by destination balance proof.
- A92 pre-submit completion boundary (2026-08-27): rendered **Complete Transfer**
  on corrected GRN `YRP-GRN-2026-00063` returned HTTP 200 and created draft
  `YRP-STE-2026-00065`. It contains exactly five linked GRN Item rows and the
  correct stock quantities S/M/L/XL/2XL = 4/6/6/4/4, positive source rates,
  Lot/Received Type, transit `S-0165`, and destination `S-0170`. The rendered
  draft nevertheless labels every row `Box`; A92 was therefore recorded and
  execution stopped before Submit. There were zero console/page/network/HTTP
  errors, no Stock Entry SLE exists, `transfer_complete` remains zero, and the
  draft must be recovered rather than duplicated after the Essdee-only fix.
- A92 corrected completion/transfer boundary (2026-08-27): the focused Stock
  Entry customization module now passes all eight tests, including current
  dynamic Piece preservation and a legacy-packing non-regression; compile and
  diff checks pass. After refreshing only the site hook cache, the rendered
  form recovered the same `YRP-STE-2026-00065` and showed all five linked rows
  as UOM/stock UOM `Pieces`, conversion 1, quantities 4/6/6/4/4, and their
  exact positive source rates before Submit. Submit returned HTTP 200 with no
  console/page/request/HTTP failures. `YRP-GRN-2026-00063` then reports 24/24,
  100% transferred, and no Complete Transfer action. Independent proof finds
  exactly five `S-0165` outgoing plus five `S-0170` incoming SLEs, 24 Pieces
  each side, and ₹4,204.378510476 value each side; every GRN Item completion
  counter equals its quantity, transit is zero, destination balances are
  4/6/6/4/4, and `FP-2526-00238` remains exactly 2 packed boxes/24 packed
  pieces with zero dispatched. A92 is fixed. The next permitted mutation is
  the second partial Packing GRN for 3 boxes/36 pieces through the rendered
  Finishing Plan dialog.
- S23 second partial Packing GRN boundary (2026-08-27): the rendered Finishing
  Plan dialog selected White and visibly showed 3 boxes, ratio 2:3:3:2:2,
  S/M/L/XL/2XL = 6/9/9/6/6, 12 pieces per box, and 36 total pieces. Its existing
  create method returned HTTP 200 and submitted `YRP-GRN-2026-00064`; both the
  mutating run and clean submitted-form reload recorded zero console, page,
  request, or HTTP failures. All five outputs are UOM/stock UOM `Pieces` with
  conversion 1. Independent proof finds 60 mapped rows over the same 24 exact
  Work Order inputs, 24 consumption plus five output SLEs, and 60 active
  valuation-production links. Material value ₹6,198.567765714 plus process
  value ₹108 equals output value ₹6,306.567765714. Cumulative Work Order input
  counters and calculated garment receipts equal S/M/L/XL/2XL = 10/15/15/10/10,
  consuming the first garment delivery exactly; source balances reconcile,
  the first GRN remains at destination, the second remains in transit, and
  `FP-2526-00238` reports exactly 5 packed boxes/60 packed pieces with zero
  dispatched. The next permitted mutation is rendered completion of this
  second GRN transfer, followed by exact SLE/value/destination proof.
- S23 second partial Packing GRN completion boundary (2026-08-27): rendered
  **Complete Transfer** created `YRP-STE-2026-00066`; its draft showed exactly
  five Piece rows 6/9/9/6/6 with conversion 1, exact GRN Item links, positive
  rates, Lot and Received Type before Submit. Submit returned HTTP 200 and the
  rendered GRN reloaded as 36/36, 100% transferred with no completion button;
  every observed browser and HTTP channel was clean. Independent proof finds
  five transit outgoing plus five destination incoming SLEs, 36 Pieces and
  ₹6,306.567765714 on each side, exact GRN Item completion counters, zero
  remaining packed output in `S-0165`, and cumulative `S-0170` destination
  balances 10/15/15/10/10. The Finishing projection remains exactly 5 boxes/
  60 pieces and zero dispatched. The next permitted action is a rendered
  over-allocation attempt before any second garment delivery; it must not
  create a GRN or alter any ledger/counter/projection.
- S23 packing over-allocation rejection boundary (2026-08-27): with only the
  first garment delivery available and now fully consumed, the rendered dialog
  accepted a visible one-box ratio entry (2/3/3/2/2, 12 pieces). Its create
  request reached the authoritative server validator and returned the expected
  HTTP 417: White/S needs 2 pieces but zero are pending in Work Order
  `YRP-WO-2026-00049`. This is the expected negative-test response, not an
  unhandled business failure. The response named no new record; read-only
  inventory before and after remained exactly `YRP-GRN-2026-00063` (2 boxes)
  and `YRP-GRN-2026-00064` (3 boxes). A post-rejection independent verifier
  reconfirmed both completion transfers, ten SLE legs for the second transfer,
  ₹6,306.567765714 value each side, cumulative destination 10/15/15/10/10,
  and Finishing 5 boxes/60 pieces unchanged. The next permitted mutation is
  the second partial garment Delivery Challan and its internal completion;
  packing must remain blocked until that delivery is submitted.
- S23 second garment delivery/completion boundary (2026-08-27): the rendered
  Finishing Plan flow created submitted `DC-2026-00029` with only the five
  garment rows S/M/L/XL/2XL = 10/15/15/10/10, exact Work Order Deliverable
  references, Accepted/Lot dimensions, and ₹8,765.54627619 stock value; no
  packing accessory row was duplicated. Rendered completion then created and
  submitted `YRP-STE-2026-00067` with the same five quantities/rates and exact
  DC Item links. Both UI operations returned HTTP 200 with zero console, page,
  request, or response failure. Independent proof finds ten paired SLE legs
  on the DC route `S-0170 → S-0165` and ten on completion `S-0165 → S-0171`,
  with ₹8,765.54627619 conserved. Work Order cumulative garment delivered is
  20/30/30/20/20, prior packing consumption/received remains 10/15/15/10/10,
  delivery pending is zero, `S-0170` and transit are zero, and new available
  garment stock at `S-0171` is exactly 10/15/15/10/10. The next permitted
  mutation is the final rendered Packing GRN for 5 boxes/60 pieces; it must
  exactly exhaust all 24 garment/accessory Work Order inputs.
- S23 final Packing GRN submit/exhaustion boundary (2026-08-27): the rendered
  dialog visibly showed White, 5 boxes, ratio 2:3:3:2:2, size totals
  10/15/15/10/10, 12 pieces per box, and 60 total pieces. HTTP 200 submitted
  `YRP-GRN-2026-00065`; the mutating and clean submitted-form runs recorded no
  console/page/request/HTTP failures. All outputs remain physical `Pieces`.
  Independent proof finds 60 mapped rows over all 24 exact inputs, 24 active
  consumption plus five output SLEs, and 60 active lineage links. Material
  value ₹10,330.94627619 plus process value ₹180 equals output value
  ₹10,510.94627619. Across the 2-box, 3-box, and 5-box GRNs, cumulative Work
  Order consumption now equals every delivered/planned input exactly:
  garments 20/30/30/20/20, each corresponding size tag/sticker the same,
  every shared piece accessory 120, and every box-level accessory 10. Source
  balances reconcile to zero without negative stock, and `FP-2526-00238`
  reports exactly 10 packed boxes/120 packed pieces, zero dispatched. The final
  five-box output remains in transit; the next permitted mutation is its
  rendered GRN Completion and exact destination/value proof.
- S23 final Packing GRN completion boundary (2026-08-27): rendered completion
  created `YRP-STE-2026-00068` with exactly five linked Piece rows
  10/15/15/10/10, conversion 1, exact GRN Item references, positive rates,
  Lot and Received Type before Submit. Submit returned HTTP 200; the rendered
  GRN reloaded as 60/60, 100% transferred with no completion action, and all
  browser/request/response channels were clean. Independent proof finds five
  transit outgoing plus five destination incoming SLEs, 60 Pieces and
  ₹10,510.94627619 each side, exact Item completion counters, zero transit,
  and final packed destination balances 20/30/30/20/20. The authoritative
  Finishing projection is now exactly 10 boxes/120 pieces, zero dispatched,
  across the three immutable batches and all Work Order garment/accessory
  inputs remain exactly exhausted. Packing receipt and completion testing is
  complete. The next permitted mutation is dispatch testing through the
  rendered Finishing Plan flow, followed by the separate Finishing Plan
  Dispatch DocType flow and their stock/projection reconciliation.
- S23 closure / S24 rendered dispatch preflight (2026-08-27): S23 is checked
  complete after its partial, multiple, rejection, cancellation, retry,
  Received Type/rework, mapped valuation, and exact transfer evidence. No S24
  business record was mutated during this preflight. The rendered Finishing
  Plan **Dispatch Box** dialog shows 120 packed and 120 balance Pieces with the
  three exact immutable batches available at 5, 3, and 2 boxes; every batch
  input is integer-only, starts at zero, and is capped to its own remaining
  balance. Its source defaults to `S-0170`. A rendered new **Finishing Plan
  Dispatch** form independently fetched `FP-2526-00238`, showed the same five
  size balances 20/30/30/20/20, the same 5/3/2 batch caps, Piece UOM, and zero
  selected dispatch. Both screens loaded with HTTP 200 throughout and zero
  console/page/request/network errors. `YRP Stock Settings` has
  `add_finishing_plan_goods_value = 0`; the exact source value will therefore
  be entered as Goods Value and reconciled independently at every submit and
  cancel/retry boundary. The next permitted mutation is a two-box direct
  Finishing Plan dispatch from batch `YRP-GRN-2026-00063`, `S-0170` to
  `S-0167`.
- S24 first direct dispatch / A93 correction-and-cancel boundary (2026-08-27):
  the rendered Finishing Plan dialog selected only `YRP-GRN-2026-00063`, two
  boxes/24 Pieces with size quantities 4/6/6/4/4, destination `S-0167`, Goods
  Value ₹4,204.38 at configured currency precision, and vehicle
  `TN 39 UAT 2401`. The approved `create_stock_entry` API returned HTTP 200 and
  submitted `YRP-STE-2026-00069`; FIFO issue value was
  ₹4,204.378510476, batch/projection became 2 boxes/24 Pieces, and status became
  Partially Dispatched with no browser error. A93 was found because persisted
  transaction UOMs were `Box` even though stock UOM, conversion-1 quantities,
  and the rendered batch contract were physical Pieces. The Essdee-only
  post-base-validation adapter now scopes to current version-2 normalized batch
  Material Issues through both approved dispatch routes, proves batch totals
  equal the exact Stock Entry row totals by Lot, and restores Piece UOM without
  changing legacy/non-batch issues. Both direct and Finishing Plan Dispatch
  regressions plus the legacy guard pass in the ten-test Stock Entry module;
  compile and diff checks pass. Read-only onload rendered the pre-fix submitted
  entry as 4/6/6/4/4 Pieces. The rendered Finishing Plan **Cancel** action then
  returned HTTP 200 for `YRP-STE-2026-00069`. Independent reversal proof finds
  docstatus 2, ten immutable submit/cancel SLE rows all inactive, zero active
  SLE, exact 120-Piece source restoration, batch 2 boxes available again, zero
  dispatched projection, one cancelled audit log, and Ready to Pack status.
  No Finishing Plan Dispatch record exists. The next permitted mutation is the
  same two-box direct rendered retry; it must persist physical Pieces.
- S24/A93 corrected direct retry boundary (2026-08-27): after the development
  bench process was restored, two read-only Link-control retries timed out
  before submission and made no business mutation. The corrected rendered
  attempt again selected only the two-box `YRP-GRN-2026-00063` batch and the
  approved API returned HTTP 200 with `YRP-STE-2026-00070`; every browser,
  page, request, and response error channel was clean. Independent persisted
  proof now finds all five Stock Entry rows as physical `Pieces`, conversion 1,
  exact quantities 4/6/6/4/4, five active `S-0170` issue SLEs, and conserved
  FIFO value ₹4,204.378510476. Source balance is 96 Pieces, only that immutable
  batch is fully dispatched at two boxes/24 Pieces, the active audit log records
  the same box/piece totals, and `FP-2526-00238` is Partially Dispatched. A93 is
  fixed. The next permitted mutation is a new rendered Finishing Plan Dispatch
  selecting the remaining 3-box and 5-box batches for 8 boxes/96 Pieces.
- S24/A94 submitted Finishing Plan Dispatch boundary (2026-08-27): the same
  rendered 5-box `YRP-GRN-2026-00065` plus 3-box `YRP-GRN-2026-00064`
  selection first proved A94's dynamic `FPD-2627-` value reached the browser,
  then saved and submitted `FPD-2627-00155` through the standard toolbar. The
  accepted document has exactly five `Pieces` rows 16/24/24/16/16, exact batch
  lineage, 96 selected pieces, a 120-piece cumulative dispatch snapshot, and no
  Stock Entry yet. The first successful run exposed only a client cleanup
  incompatibility because Frappe's jQuery-style call promise has no
  `.finally()`; replacing it with `try/finally` produced a clean rendered
  reopen with every console/page/request/response channel empty. Independent
  persisted proof confirms the submitted series, child quantities/UOMs,
  packing-source lineage, 5+3 boxes, no active FPD Stock Entry, the unchanged
  direct-route 2-box/24-piece dispatch, and exactly 8 boxes/96 pieces remaining.
  A94 is fixed. The next permitted mutation is only this submitted document's
  rendered **Dispatch Stock** popup from `S-0170` to `S-0167`, followed by
  independent stock, FIFO-value, and Finishing-projection proof.
- S24 first Finishing Plan Dispatch stock boundary (2026-08-27): the rendered
  **Dispatch Stock** popup on `FPD-2627-00155` accepted source `S-0170`,
  destination `S-0167`, Goods Value ₹16,817.51, and vehicle
  `TN 39 UAT 9601`; the approved API returned HTTP 200 with
  `YRP-STE-2026-00071`, the form linked that entry, removed the duplicate
  dispatch action, and every browser/network channel stayed clean. Independent
  proof finds five persisted Piece rows 16/24/24/16/16, five active source SLEs
  totaling 96 Pieces and exact FIFO issue value ₹16,817.514041904, zero source
  Pieces, all three immutable batches fully dispatched at 5+3+2 boxes, two
  distinct active route Stock Entries/logs, a 10-box/120-piece projection, and
  `Dispatched` status. The Goods Value remains the separately entered dispatch
  value while the SLE `stock_value_difference` preserves the authoritative FIFO
  issue value. The next permitted mutation is the rendered Cancel of
  `FPD-2627-00155`; it must cascade to its Stock Entry and restore only this
  8-box/96-piece route before a rendered retry.
- S24/A95 corrected cancel boundary (2026-08-27): rendered Cancel of the first
  FPD/Stock Entry pair completed with HTTP 200 and restored quantity/value, but
  exposed that its transaction rows had never received the rate preparation
  already used by the direct dispatch route. The Essdee-only FPD path now calls
  that shared dimension-aware helper before insert; all 12 focused tests and
  static checks pass. A rendered post-fix retry submitted
  `FPD-2627-00156`, dispatched `YRP-STE-2026-00072`, persisted positive
  Piece-row rates/amounts, and again removed exactly 96 Pieces with FIFO value
  ₹16,817.514041904. Its second rendered Cancel returned HTTP 200 with clean
  browser/network channels. Independent proof finds both documents cancelled,
  zero active SLEs for that pair, exact 96-Piece/₹16,817.51404192 live source
  restoration, 5+3 boxes available, only direct `YRP-STE-2026-00070` active,
  and Partially Dispatched status. The ten historical rows match finalized base
  YRP cancellation semantics: five inactive original value rows and five
  inactive zero-value +quantity tombstones; live valuation excludes the entire
  cancelled voucher. A95 is fixed. The next permitted mutation is one final
  rendered 5+3 FPD create/submit/dispatch retry, which must remain active as the
  accepted 10-box/120-piece final state.
- S24 final retained dispatch and idempotence boundary (2026-08-27): the final
  rendered 5+3 selection submitted `FPD-2627-00157` with the authoritative
  `FPD-2627-` series and dispatched `YRP-STE-2026-00073` through the approved
  popup/API with `S-0170` → supplier `S-0167`, Goods Value ₹16,817.51, and
  vehicle `TN 39 UAT 9601`. All browser/page/request/response channels were
  clean. Independent final proof finds five positive-rate Piece rows
  16/24/24/16/16, five active source SLEs totaling 96 Pieces and exact FIFO
  value ₹16,817.514041904, zero source quantity/value, all three immutable
  batches dispatched at 5+3+2 boxes, and exactly the intended active route pair:
  direct `YRP-STE-2026-00070` for 2 boxes/24 Pieces plus FPD
  `YRP-STE-2026-00073` for 8 boxes/96 Pieces. The external supplier dispatch is
  correctly the approved one-sided Material Issue; value conservation is its
  exact FIFO issue value rather than an invented destination-Warehouse receipt.
  The rendered **Fetch Rejected Quantity** authoritative rebuild was then run
  twice. Before/after-one/after-two were byte-equivalent for all five fully
  dispatched size rows, `Dispatched` status, the active direct-entry map, and
  all five active/cancelled route audit logs. A final independent stock read
  remained 10 boxes/120 Pieces dispatched. S24, U36, and U37 are complete.
- Post-S24 first complete-suite boundary (2026-08-27): the first unfiltered
  `bench --site essdee_yrp.site run-tests --app essdee_yrp` pass ran 75 unit,
  308 integration, 120 legacy-category, and 121 unspecified-category tests.
  It exposed only A96-A98 plus the associated final handler-count assertion and
  two planner assertions: protected live transaction samples correctly raised,
  one rework regression used a stale helper signature, F15 Item description had
  no reviewed target rule, and Process mapping changed classification totals.
  The 120 legacy-category tests and every surrounding business module passed.
  After the scoped corrections, Python compile and diff checks pass, followed
  by green focused reruns of all 6 runtime-acceptance, 4 GRN Rework Item, and 5
  offline migration-planner tests. A fresh full-suite rerun remains mandatory;
  G03 is not checked from focused results.
- Post-S24 clean complete-suite rerun (2026-08-27): the mandatory fresh
  `bench --site essdee_yrp.site run-tests --app essdee_yrp` rerun completed
  with exit code 0. All four discovered categories are green: 75 unit tests,
  308 integration tests with 10 intentional skips, 120 legacy-category tests,
  and 121 unspecified-category tests (624 tests discovered in total). The
  corrected runtime-hook inventory executed all 77 handlers, the provisional
  rework regression passed, and the offline migration planner finished with
  zero schema blockers. This closes the full-suite portion of G03 only; asset
  build, frontend build, permitted schema qualification, and final rendered-UI
  health evidence remain separate gates.
- R02/current-build qualification (2026-08-27): a fresh review pass covered all
  71 changed/untracked Essdee files (6,106 insertions and 661 deletions), with
  particular re-review of the A74/A75 Desk repairs, migration/reset safety,
  mapped GRN ownership, Work Order close, Stock Entry UOM/rate adapters,
  rework, Packing, and both dispatch routes. No new production finding was
  identified. Every changed/untracked Python file compiles, every changed
  JavaScript file passes `node --check`, every changed JSON file parses, and
  `git diff --check` is clean; Ruff is not installed in this bench. The Desk
  `bench build --app essdee_yrp` and the separate `frontend` Vite production
  build both pass. Vite reports only its existing advisory that some minified
  chunks exceed 500 kB; this is an optimization observation, not a correctness
  failure, and optimization remains deferred until the acceptance gates close.
  Base YRP is still exactly `7536d315` with tracked SHA-256
  `849c7a8b...a04a88b` and untracked SHA-256 `62e3be5d...d1d164`; Frappe and
  ERPNext remain clean. Generated ignored Python bytecode found during review
  was removed from the new child-DocType directory. G03 remains open because a
  new schema migrate is not authorized by this evidence and the screenshot-
  producing generic UI verifier is intentionally not used in this no-screenshot
  acceptance run; rendered Playwright evidence is recorded per S/U scenario.
- U04 standalone Cutting Plan linkage boundary (2026-08-27): the rendered Desk
  form created `CP-2608-00016` without a Work Order, visibly entered the
  required Maximum Plies as 100, retained the ten size/set rows totaling 240
  Pieces, and submitted it. The submitted form then accepted
  `YRP-WO-2026-00046` in the allow-on-submit Work Order control and persisted it
  only after the visible **Update** action. The linked rendered flows submitted
  `CM-2608-00084` with the single `Top Front` group and ratios 2/3/3/2/2, then
  created `CLS-2608-00124` with the same plan/marker/Lot/item lineage, five
  ratios, and calculated part `Top Front`. Every creation/update browser, page,
  request, and response error channel was clean. Cleanup used the rendered
  LaySheet custom **Cancel**, Marker toolbar **Cancel**, and Plan toolbar
  **Cancel** actions. The first cleanup runner observed HTTP 200 for both the
  LaySheet and Marker cancellations but timed out because it watched the wrong
  standard-cancel endpoint name; a state-aware resumed run cancelled only the
  remaining Plan and completed cleanly. Independent reads prove final Plan and
  Marker docstatus 2, LaySheet status `Cancelled`, no LaySheet bundles, zero
  cloth/accessory/used weight, and no linked GRN. The probe therefore left no
  stock or bundle transaction while proving the required no-WO → Update-WO →
  Marker → LaySheet sequence. U04 is complete.
- U05 cloth/accessory precision and whole-piece excess boundary (2026-08-27):
  the isolated rendered plan `CP-2608-00017` used 18 maximum plies, 15%
  allowance, linked Work Order `YRP-WO-2026-00046`, and fetched the exact
  three-decimal received-cloth projection 20.064/23.760/1.056/45.720 kg. Its
  submitted marker `CM-2608-00085` retained the Top Front ratios 2/3/3/2/2.
  On `CLS-2608-00125`, the UI deliberately added the FOLDING accessory first
  at 0.123 kg and the cloth second at received/used/balance weights
  1.521/1.520/0.001 kg with 10 effective Open Width bits; one visible Save
  persisted both child tables in that order without losing or rounding either
  entry. The visible **Generate** dialog then used 18 plies and 15%, whose
  mathematical ceiling is 20.7 pieces. It generated exactly seven whole-piece
  bundles with quantities only 10 or 20, no quantity above 20.7, and exact
  S/M/L/XL/2XL totals 20/30/30/20/20. A second visible **Generate** produced
  the identical size/part/quantity signature. Before and after regeneration,
  the persisted plan usage remained exactly 1.643 kg (1.520 cloth + 0.123
  accessory) with 18.421 kg balance rather than accumulating to 3.286 kg.
  Every browser/page/request/response channel was clean and no GRN existed.
  Rendered cleanup cancelled the LaySheet, Marker, and Plan; the queued parent
  rebuild reached zero used weight before parent cancellation. Independent
  final reads prove LaySheet status `Cancelled`, Marker/Plan docstatus 2, zero
  plan usage, and zero linked GRN, CBML, SLE, or stock mutation. U05 is
  complete.
- U10 reduced collapsed/no-CPM boundary before cleanup (2026-08-27): the
  isolated rendered setup submitted temporary Printing Work Order
  `YRP-WO-2026-00052` for exactly the nominal Top quantities
  20/30/30/20/20 at source `S-0172`; an earlier unused `S-0170` attempt
  `YRP-WO-2026-00051` was cancelled before any child transaction. The UI
  reused empty CPM draft `CPM-2608-00240`, fetched only the retained collapsed
  M/White/Top Front quantity 30 at `S-0172`, and submitted it. Because the
  retained Stitching flow had already consumed physical cut-panel stock, the
  UI created temporary Stock Reconciliation `YRP-ST-RECO-2026-00007` for
  exactly 30 Pieces at rate 29.162, then submitted collapsed DC
  `DC-2026-00030` for those 30 pieces to Sri Krishna Printing. The actual U10
  GRN deliberately left the optional DC selector empty, checked the rendered
  **Allow Non Bundle** field, zeroed S/L/XL/2XL, reduced M from 30 to 10, and
  submitted `YRP-GRN-2026-00066` with both `delivery_challan` and
  `cut_panel_movement` empty. The clean rendered reopen proves one M row,
  quantity 10, Printing output rate 30.162 and total 301.62. Exact CBML rows
  move -10/+10 and end Sri Krishna Printing/S-0172 at 20/10; exact SLEs are
  `YRP-SLE-2026-08033` (-10, -291.62, rate 29.162) and
  `YRP-SLE-2026-08034` (+10, +301.62, rate 30.162). Every U10 GRN creation and
  verification browser/page/request/response channel is clean. The temporary
  reconciliation's successful submit recorded one late base item-editor
  teardown `fieldobj` page error; it did not affect persistence, and its clean
  rendered reopen/cancel had zero errors. Rendered cleanup first cancelled the
  GRN, then exposed A99 when generic Cancel All attempted the invalid
  CPM-before-DC order; that failed 417 made no DC/CPM/stock mutation. After
  A99's Essdee-only client fix and build, the rendered retry cancelled DC →
  CPM → Work Order → Stock Reconciliation with HTTP 200 throughout and zero
  browser/page/network/response errors. Final reads prove all five temporary
  records docstatus 2, zero active temporary SLE/CBML, restored collapsed
  balances S-0172/Sri Krishna Printing = 30/0, zero live physical panel
  quantity/value at both warehouses, and retained dispatch Stock Entries
  `YRP-STE-2026-00070`/`00073` still submitted. U10 and A99 are complete.
- U13 cancellation dependency and rollback boundary (2026-08-27): after the
  U10 GRN was cancelled, the first rendered DC cancellation deliberately
  exercised the invalid dependent-first path through Frappe's cascade. CPM
  `CPM-2608-00240` rejected cancellation while its owner DC remained submitted
  with the exact message `Cancel Delivery Challan DC-2026-00030 before
  cancelling this Cut Panel Movement.` The request returned 417 and an
  immediate read proved DC/CPM/Work Order/Reconciliation all remained
  docstatus 1; no SLE or CBML was partially reversed. After A99 aligned the
  Desk preflight with the existing server contract, the rendered valid order
  cancelled root DC `DC-2026-00030` first, then the unlinked CPM, Work Order,
  and Stock Reconciliation, all HTTP 200. Together with the earlier rendered
  GRN cancel, final proof finds all five temporary documents cancelled, no
  active temporary SLE/CBML, exact restoration of the retained collapsed
  30-piece balance at `S-0172`, zero physical panel stock/value created by the
  temporary reconciliation, and both final dispatch Stock Entries untouched.
  The corrected retry had zero console/page/request/response errors. U13 is
  complete.
- U14 CBML lifecycle reconciliation (2026-08-27): the dedicated checkpoint
  verifiers prove quantity conservation and canonical source/target ownership
  after every required lifecycle branch, rather than inferring it only from
  the final balance. Initial movement `YRP-STE-2026-00053` created exactly 90
  active CBML rows for 45 exact bundle-panel identities: each source row ended
  at zero, each target row reproduced the same positive quantity, and all
  Lay/Bundle/Size/Colour/Panel/Shade/set-combination dimensions were conserved.
  Split Printing DCs `DC-2026-00018`/`00019` then created ten paired rows for
  the five Top Front identities (120 pieces), leaving the store at zero and
  Sri Krishna Printing at the exact S/M/L/XL/2XL quantities 20/30/30/20/20.
  Exact return `YRP-GRN-2026-00049` moved the S20 identity back without losing
  Lay/Bundle identity; collapsed return `YRP-GRN-2026-00050` transformed only
  M10 and left the canonical collapsed M balances printer/store = 20/10, still
  totalling the original M30. Collapsed receipt `YRP-GRN-2026-00051`,
  redelivery `DC-2026-00020`, and receipt `YRP-GRN-2026-00052` each produced
  one -/+ pair and checkpoint balances store/printer M = 30/0, 20/10, and
  30/0 respectively, with no exact/accessory leakage or duplicate/lost row.
  Finally, the isolated U10 submit produced exactly one collapsed -/+ pair;
  its rendered GRN-first and DC-root cancellation sequence reversed all
  temporary rows. The deliberately invalid CPM-first attempt returned 417 and
  changed no CBML status or balance. Final reads found zero active temporary
  CBML rows, the retained S-0172/printer collapsed balance restored to 30/0,
  and no submitted CPM left without its recorded root transaction. These
  submit, return, redelivery, valid-cancel, invalid-cancel, status, dimension,
  and orphan checks complete U14.
- U15 rendered GRN grouping qualification (2026-08-27): fresh submitted-form
  loads proved the base set-combination contract and Essdee's migrated
  row-index compatibility without creating or mutating a business document.
  Retained Printing GRN `YRP-GRN-2026-00054` stores three L/XL/2XL children
  but renders one White/Top/Top Front row with the five size columns
  `0/0/30/20/20`; retained Stitching GRN `YRP-GRN-2026-00055` stores five
  children but renders one White/Top garment row `10/10/10/10/10`. Migrated
  GRN `GRN-2627-05049` then proved that the same item and reused historical
  row indexes do not collapse four distinct set combinations: Navy, Maroon,
  Airforce Navy, and Military Green render as four separately labelled
  matrices. Navy and Military Green each retain separate Accepted and Adas
  received-type rows, producing six logical editor rows from 16 children.
  Migrated GRN `GRN-00016` independently renders one Sky Blue five-size matrix
  with three distinct Received Type rows: Accepted `199/808/861/525/305`, Adas
  `0/0/25/0/0`, and Oil Mark `1/20/41/12/9`. Strict UI assertions covered the
  child/group counts, labels, all positive size cells, and received-type
  separation. Every getdoc, stock-dimension, and rework-type request returned
  HTTP 200 with zero console, page, failed-request, or failed-response errors.
  The full suite's focused row-index normalizer regressions also prove that
  canonical JSON formatting differences group together while differing stock
  dimensions, set combinations, and Received Types remain separate. U15 is
  complete; base YRP remains unchanged.
- U16 Inspection split, authorization, conversion, cancel, and conservation
  qualification (2026-08-27): the rendered Stock Entry UI created isolated
  Material Receipt `YRP-STE-2026-00074` for exactly three
  `XMAS PJ5 - MENS-S-White-Top` Pieces at `S-0170`, Lot
  `MRP-UAT-260826-01`, Accepted, rate `100.000001`, and value `300.000003`.
  Its visible **Create Inspection Entry** action loaded that exact source. The
  editor allocated S=1 to Rejected, S=1 to the eligible non-default/non-
  Rejected rework type Misstitch, and left S=1 Accepted, then saved/submitted
  `INS-2026-00013`. Before conversion the configured approver role was Stock
  Manager, the acceptance user did not hold it, the permission endpoint
  returned HTTP 200 with `can_convert=false`, and no **Convert Stock** button
  rendered. A second UI-created identity-only Inspection
  `INS-2026-00014` submitted and then cancelled HTTP 200; it is docstatus 2,
  status Cancelled, `is_converted=0`, and has zero SLE.

  Stock Manager was then granted through the rendered User form solely for the
  authorization boundary. A fresh session rendered **Convert Stock** on
  `INS-2026-00013`; the confirmation named source Stock Entry `00074`, and the
  visible **Convert** action returned HTTP 200. The Inspection remains
  submitted with status Converted/`is_converted=1`, and the button disappears.
  Exactly four valuation-fresh SLEs form two reciprocal pairs:
  `YRP-SLE-2026-08041↔08042` moves Accepted -1 / Rejected +1 and
  `YRP-SLE-2026-08043↔08044` moves Accepted -1 / Misstitch +1. Each pair
  carries the exact Item/Warehouse/Lot and `₹100.000001` FIFO value; total
  conversion quantity and value are both zero. Rendered Cancel on this
  converted Inspection correctly returned 417 with `already converted stock
  and cannot be cancelled`; the document and all four SLEs were byte-identical
  before/after. The 417 resource/trace console lines are the expected negative
  response and no unrelated browser/page/request failure occurred.

  Rendered cleanup submitted three separate one-piece Material Issues so stock
  dimensions could not merge: `YRP-STE-2026-00075` Accepted,
  `YRP-STE-2026-00076` Rejected, and `YRP-STE-2026-00077` Misstitch. Final SQL
  reconciliation finds the four Stock Entries submitted, the two Inspection
  states exact, U16 active SLE quantity/value `0/₹0`, and Accepted/Rejected/
  Misstitch Bins all `0 Pieces/₹0`; final dispatch entries
  `YRP-STE-2026-00070`/`00073` remain submitted. Stock Manager was revoked
  through the rendered User form and the role row is absent. The immediate
  initial Receipt save and each immediate cleanup Save→Submit sequence logged
  one already-observed late base Item Editor `fieldobj` teardown page error;
  persistence and posting were correct, and a fresh rendered reopen of all
  three cleanup entries was fully clean. A100 separately fixes the ordinary-
  rate native-validation struggle and its unsaved exact-rate-100 UI probe is
  clean. Together with the earlier S19/S20 live Misstitch rework round trip,
  these checks complete U16; base YRP remains unchanged.
- U20 Yolk Fusing and remaining-embellishment boundary (2026-08-27): read-only
  configuration review first proved that Yolk Fusing is an active non-group,
  non-manual, non-item-conversion Process, distinct from Printing. Approved
  Process Cost `PC-01982` owns item `Casual Designer vest - 6`, supplier
  `Balaji Fushing`, and Lot `C0326-32/1`; migrated rendered Work Order
  `WO-2627-00832` opened cleanly with the same process/IPD/supplier lineage.
  The isolated rendered UI then submitted Work Order `YRP-WO-2026-00053` for
  Wine/S=135 only. Its authoritative rows were panel deliverable
  `Casual Designer vest - 6-Back-Wine-S` 135 Pieces, fusing-sticker
  deliverable `Fusing Sticker-Designer Vest (Essdee)-S-White` 135 Nos, and
  fused-panel receivable 135 Pieces at process cost `₹0.40`/`₹54`.

  Rendered Cut Panel Movement `CPM-2608-00241` selected exact Lay 1/Bundle 9,
  Wine/S/Back=135 at `S-0170`. Panel DC `DC-2026-00031` submitted from
  `S-0170` to `Balaji Fushing` and posted paired external-location SLEs
  `YRP-SLE-2026-08048/08049`; its persisted UI value was `₹96.525`, while the
  FIFO ledger carried the stock engine's precise `₹96.529999995`. Rendered
  Stock Reconciliation `YRP-ST-RECO-2026-00008` seeded only the exact sticker
  bucket at `S-0070`, 135 Nos × `₹0.26` = `₹35.10`. To switch the second DC's
  source, the UI required clearing visible From Warehouse before selecting
  `S-0070`; saved DC `DC-2026-00032` then recalculated the initially stale
  editor preview to the authoritative `₹0.26`, removed its zero panel row, and
  posted paired SLEs `YRP-SLE-2026-08051/08052` for `₹35.10`.

  The first blank-DC **Work Order → Create → Make GRN** draft exposed A101:
  only the panel was mapped and the output remained process-only `₹54`. No
  incorrect GRN was submitted. After the Essdee-only correction, the same
  rendered draft `YRP-GRN-2026-00067` retained one fused-panel output but two
  mapped inputs: panel 135 at `₹0.715037037` and sticker 135 at `₹0.26`.
  Submit recalculated the output to
  `₹0.715037037 + ₹0.26 + ₹0.40 = ₹1.375037037`, total
  `₹185.629999995`, and changed the Work Order to Fully Received with both
  Deliverable `stock_update` values exactly 135. Consumption SLEs
  `YRP-SLE-2026-08053` (`-135`, `-₹96.529999995`) and
  `YRP-SLE-2026-08054` (`-135`, `-₹35.10`) feed output SLE
  `YRP-SLE-2026-08055` (`+135`, `+₹185.629999995`). Active production links
  `r2cef0fujf` and `r2c567in7v` persisted each input SLE, the shared output
  SLE, exact GRN child, Work Order Deliverable, Lot/Received Type dimensions,
  input quantity, and material value. Thus the net stock-value increase is
  exactly the `₹54` process cost, not an unexplained transfer difference.

  Creation/submission browser console, page, request, and response channels
  were clean. The immediate reconciliation submit emitted the already-known
  late base Item Editor `fieldobj` teardown error; a fresh rendered reopen of
  `YRP-ST-RECO-2026-00008` showed the exact matrix and was fully clean. Cleanup
  used rendered Cancel in reverse dependency order: GRN → sticker DC → panel
  DC → CPM → Work Order → reconciliation. All six cancel requests returned
  HTTP 200 with zero browser/page/network errors. The runner's subsequent
  read-only CBML REST query alone timed out at 30 seconds; independent SQL
  verification proves all six documents docstatus 2, zero active temporary
  SLE, zero active temporary CBML, and both production links retained inactive.
  Exact Lay 1/Bundle 9 is restored at `S-0170` with 135 pieces; panel Bin is
  restored to 135 Pieces/`₹96.525`, and every temporary sticker/supplier bucket
  is zero. U20 and A101 are complete; no screenshot was produced and base YRP
  remains unchanged.

- U27 Stitching return/cancel projection replay and idempotency qualification
  (2026-08-27): before mutation, the rendered retained Finishing Plan
  `FP-2526-00238` was captured as the exact control. Its S row was Cutting 22,
  inward/delivered 20/20, Accepted 15, Reworked 5, Rejected 0, DC 20; M/L were
  33, 30/30, 25, 5, 0, 30; XL/2XL were 22, 20/20, 15, 5, 0, 20. Received Type
  totals were Accepted/Misstitch and every size's rework row was quantity 5,
  reworked 5, rejected 0.

  The UI then submitted isolated Stitching Work Order `YRP-WO-2026-00054`
  and linked Sewing Plan `SP-2526-00232` for Sewing Unit Tiruppur, Top/S=1.
  Its exact calculated inputs were Front 1, Back 1, Sleeve 2, Neck Rib 1,
  woven label 1 Nos, and Inner Elastic 0.76 Meter; its receivable was
  `XMAS PJ5 - MENS-S-White-Top` 1 Piece at `₹14`. Rendered Stock
  Reconciliation `YRP-ST-RECO-2026-00009` supplied only those exact Lot
  `MRP-UAT-260826-01` input buckets at `S-0170`. Rendered DC
  `DC-2026-00033` delivered the six input rows and its completion Stock Entry
  `YRP-STE-2026-00078` posted the internal transfer. Work Order delivered
  changed 0→1 and the Finishing S inward quantity changed 20→21.

  The rendered complete-panel-set Return action submitted
  `YRP-GRN-2026-00068` with Front 1, Back 1, Sleeve 2, and Neck Rib 1.
  Submit changed Work Order delivered 1→0 and Finishing inward 21→20; rendered
  Cancel restored both exactly to 1 and 21. The Sewing Details Registered
  Experience then created, in configured order, Input `altmstf548`, Line
  Output `arv0uh02fa`, Checking Output `b1uio7cn86`, and AQL Output
  `b7vk69rcps`, each for S=1. Rendered output GRN `YRP-GRN-2026-00069`
  submitted Accepted S=1 and changed Work Order received 0→1 plus Finishing
  delivered/Accepted 20→21 and 15→16. Completion
  `YRP-STE-2026-00079` posted successfully. Cancelling completion and GRN
  through their rendered forms restored every counter. Clicking visible
  **Calculate Pieces** twice retained the same quantities, proving replay
  idempotency.

  That cancellation exposed A102: the quantities were correct while the
  Finishing Plan's incomplete-GRN cache retained the cancelled GRN and had not
  reliably included it on submit. After the Essdee-only source-replay fix,
  fresh rendered GRN `YRP-GRN-2026-00070` changed the cache to exactly
  `{\"YRP-GRN-2026-00070\": true}` on Submit, `{}` on Cancel, and still `{}`
  after another visible Calculate Pieces replay. Quantity transitions remained
  0→1→0 and the complete plan projection remained exact. The related focused
  modules pass 46/46: Finishing source sync 7, Finishing services 18, Work
  Order piece tracking 6, and Sewing business logic 15.

  Cleanup used only rendered business actions in reverse dependency order:
  cancel DC completion, DC, all four Sewing entries, Work Order, and Stock
  Reconciliation; the Return GRN, both output GRNs, and GRN completion were
  already cancelled at their tested boundaries. Final read-only verification
  proves all nine transaction documents are docstatus 2, the Sewing Plan and
  its entries no longer exist, there are no active SLEs for any U27 voucher,
  and every affected test-Lot Bin at `S-0170`, `S-0172`, and `S-0165` is
  exactly 0 quantity/`₹0`. `FP-2526-00238` is byte-for-business-value equal to
  the captured five-size baseline, including its received-type and rework
  totals, and both incomplete DC/GRN caches are `{}`. All fresh browser console,
  page, request, and response channels were clean. The Stock Reconciliation's
  immediate submit alone showed the already-recorded late base Item Editor
  `fieldobj` teardown after its HTTP-200 submit; its fresh rendered lifecycle
  and final cancellation were clean. U27 and A102 are complete; no screenshot
  was produced and base YRP remains unchanged.

- U28 grouped Create Rework source/cap/removal/permission qualification
  (2026-08-27): this gate reuses the exact continuous S20 transaction rather
  than manufacturing a second rework stock path. On parent Stitching Work Order
  `YRP-WO-2026-00048`, the rendered base-YRP **Create Rework** dialog grouped
  the five source children of `YRP-GRN-2026-00056` into one garment/colour/part
  matrix with S/M/L/XL/2XL columns and one exact Misstitch Received Type row.
  Every cell visibly showed available/max 4 and HTML min/max 0/4 after A85's
  Essdee direct-clear subtraction. Entering 4 in all five cells created and
  submitted `YRP-WO-2026-00050` with five exact source-GRN-child deliverables;
  attempting to invent a larger source quantity remained blocked by both the
  rendered maximum and the base server's fresh availability validation.

  The checklist's earlier phrase “received-type add/remove” is corrected to
  the finalized base contract: Received Type identifies the physical source
  stock bucket and is not a free-form operator row. Eligible source types are
  added to the grouped matrix only by submitted GRN/Inspection stock and are
  removed when direct clearing or a prior rework Work Order consumes them. A
  fresh rendered retry after S20 clicked **Create Rework**, received an exact
  empty source list with HTTP 200, rendered
  `No rework-eligible stock (non-Accepted, non-Rejected) is available`, and
  opened no Create Rework dialog. Thus fully consumed Misstitch stock cannot
  be selected again and Accepted/Rejected cannot be invented as rework input.

  The final permission pass exposed and fixed A103. Rendered User setup created
  `u28-no-create@essdee.fit` as a System User holding only
  `YRP Floor Verify`: it can read Work Order but cannot create one. The normal
  non-manager navigation gate sent its `/app/work-order/...` attempt to the
  rendered `/web` experience, where `canCreate=false` and no Create Rework
  action or text appeared. Its authenticated direct source-endpoint request
  returned HTTP 403 `PermissionError`, proving server authorization rather
  than UI hiding. The User was disabled through its rendered form immediately
  afterward. Main and restricted browser console/page/request channels were
  clean apart from that expected 403 negative response. Valuation-contract
  tests pass 46/46 and UI-mirror tests pass 21/21; Python/JavaScript compile,
  `git diff --check`, Essdee asset build, and cache refresh pass. U28 and A103
  are complete; no screenshot was produced and base YRP remains unchanged.

- U31 rework-return/redelivery/cancel qualification (2026-08-27): an isolated
  one-piece Stitching path was created entirely through rendered business UI so
  the retained dispatch path stayed untouched. Parent Work Order
  `YRP-WO-2026-00055`, Stock Reconciliation `YRP-ST-RECO-2026-00010`, DC
  `DC-2026-00034`, DC completion `YRP-STE-2026-00080`, and the configured
  Sewing sequence (Input `b86bt1jgs1`, Line Output `be482ag1gf`, Checking
  Output `bk2hfde7ta`, AQL Output `bq33im6q0q`) produced Misstitch output GRN
  `YRP-GRN-2026-00072`. GRN completion `YRP-STE-2026-00081` transferred one
  `XMAS PJ5 - MENS-S-White-Top` from `S-0165` to `S-0170` at the exact
  authoritative material value `₹163.582`, using reciprocal SLEs
  `YRP-SLE-2026-08225/08226`. The S Finishing projection moved inward and
  delivered 20→21 and Misstitch/rework quantity 5→6 without changing Accepted
  or reworked quantity.

  Rendered **Create Rework** then submitted `YRP-WO-2026-00056` from the exact
  source GRN child and its Misstitch bucket. DC `DC-2026-00035` and completion
  `YRP-STE-2026-00082` moved the unit `S-0170`→`S-0165`→`S-0172`; paired SLEs
  `YRP-SLE-2026-08227/08228` and `YRP-SLE-2026-08229/08230` preserved the same
  `₹163.582` value and all dimensions. The rendered DC Return flow was then
  exercised sequentially for every required destination type. Accepted GRN
  `YRP-GRN-2026-00073` used SLEs `YRP-SLE-2026-08231/08232`; Rejected GRN
  `YRP-GRN-2026-00074` used `YRP-SLE-2026-08235/08236`; and other eligible
  type Misstitch GRN `YRP-GRN-2026-00075` used
  `YRP-SLE-2026-08239/08240`. Each submit moved exactly one unit/value from
  supplier Misstitch to the selected `S-0170` Received Type, restored rework
  deliverable pending quantity to one, and left the parent Work Order and
  Finishing projection unchanged. Rendered cancel of Accepted and Rejected
  left no active voucher SLE, zeroed their source buckets, and restored
  `S-0172/Misstitch` to qty 1/value `₹163.582`.

  The active Misstitch return made one additional delivery newly eligible.
  Rendered DC `DC-2026-00036` submitted with reciprocal/value-preserving SLEs
  `YRP-SLE-2026-08241/08242`. Attempting to cancel the earlier return while
  that later DC existed rendered HTTP 417 and the exact message `Cannot cancel
  this return because XMAS PJ5 - MENS-S-White-Top has already been
  re-delivered. Cancel the later Delivery Challan first.` The failed action did
  not mutate the GRN. Cancelling the later DC through its form restored pending
  quantity and `S-0170/Misstitch` stock; cancelling the return then succeeded
  and restored `S-0172/Misstitch` with the original quantity and value.

  Cleanup reversed every isolated dependency through rendered actions. Final
  read-only audit proves both Work Orders, all three DCs, all five GRNs, all
  three completions, and the reconciliation are docstatus 2; the Sewing Plan
  and its entries are absent; there are no active SLEs; and every affected
  test-Lot Bin at `S-0170`, `S-0165`, and `S-0172` is exactly zero quantity and
  value. `FP-2526-00238` is restored to its five-size baseline (S inward 20,
  delivered 20, Accepted 15, Misstitch/rework/reworked 5) with both incomplete
  caches `{}`. Positive browser channels were clean; the sole error channel was
  the deliberately asserted 417 dependency rejection. U31 is complete; no
  screenshot was produced and base YRP remains unchanged.

- U32 internal/external finishing-creation boundary (2026-08-27): the positive
  rendered chain remains approved Process Cost `PC-02007` (supplier `S-0171`,
  company location, five Size rates at `₹3`) → submitted Ironing/Packing Work
  Order `YRP-WO-2026-00049` (`includes_packing=1`, `is_internal_unit=1`) →
  linked Finishing Plan `FP-2526-00238`. The migrated oracle independently
  shows every active packing/finishing Work Order with a Finishing Plan uses
  the same company-location supplier boundary.

  Code review exposed A104 before the negative mutation: the Essdee submit hook
  checked only `includes_packing`, so an external-supplier Work Order would
  enter the internal Finishing Plan path. After the Essdee-only guard and its
  focused regression, rendered Process Cost duplicate `PC-02008` was changed
  to external `S S R Garments` (`is_company_location=0`), retained the exact
  five Size rates at `₹3`, and passed Draft → Approval Pending → Approved with
  all Save/workflow calls HTTP 200. Rendered Work Order
  `YRP-WO-2026-00057` then selected the same Lot/IPD, external supplier/address,
  and delivery location `S-0170`. **Calculate Items** visibly selected Top only
  and used the current post-S22 quantities 22/33/33/22/22 (132 total), 24
  positive deliverable rows, five receivables, and exact `PC-02008` cost links.
  Submit persisted `includes_packing=1` and base-derived `is_internal_unit=0`.

  The external submit created no Finishing Plan, Box Sticker Print, Stock
  Entry, SLE, or change to `FP-2526-00238`; all browser console/page/request/
  response channels were clean. Rendered cleanup canceled
  `YRP-WO-2026-00057` and expired `PC-02008`. Final read-only proof shows both
  docstatus 2, zero forbidden side effects, and the exact retained five-size
  Finishing baseline with empty incomplete-transfer caches. The focused
  Finishing Work Order suite passes 5/5, Python compile, `git diff --check`, and
  cache refresh pass. U32 and A104 are complete; no screenshot was produced and
  base YRP remains unchanged.

- U33 calculated-item/Finishing projection qualification (2026-08-27): after
  the completed normal receipt, partial receipt, return/cancel replay, S22
  additional Cutting receipt, and U31 rework submit/return/redelivery/cancel
  lifecycles, the rendered **Fetch Rejected Quantity** action was run twice on
  retained plan `FP-2526-00238`. Before, after the first rebuild, and after the
  second rebuild were byte-for-byte equal. A separate five-size parity audit
  then compared the plan directly with submitted Cutting Work Order
  `YRP-WO-2026-00046` and Stitching Work Order `YRP-WO-2026-00048` calculated
  rows. Cutting `received_qty` equals plan Cutting exactly at
  22/33/33/22/22. Stitching `delivered_quantity` and `received_qty` equal plan
  inward/delivered exactly at 20/30/30/20/20. Each size preserves identical
  received-type JSON: Accepted 15/25/25/15/15 plus Misstitch 5 each, with zero
  Rejected. Every rework row independently equals quantity 5, reworked 5, and
  rejected 0. Both incomplete-transfer caches are `{}`. All rendered rebuild
  calls returned HTTP 200 and the final browser audit had zero console, page,
  request, or response failures. U33 is complete without incremental counters
  or double counting; no screenshot was produced and base YRP remains
  unchanged.

- U34 Finishing transaction/return qualification (2026-08-27): S23 already
  proved partial garment DCs `DC-2026-00028/00029`, partial/multiple Packing
  GRNs `YRP-GRN-2026-00063/00064/00065`, exact completion transfers, the
  blocked one-box excess attempt, the original `YRP-GRN-2026-00062` rendered
  cancel/reversal, and Accepted/Misstitch source handling. U34 then exercised
  the Finishing Plan's own **Return Item** UI without disturbing those retained
  120 packed/dispatched Pieces. Rendered temporary Stock Reconciliation
  `YRP-ST-RECO-2026-00011` supplied exactly one S-size White/Top Piece at
  `S-0170`, Lot `MRP-UAT-260826-01`, Accepted, and rate/value `₹163.582`.

  The first return attempt exposed and then verified A105. The three rendered
  returns were `YRP-GRN-2026-00076` as Accepted,
  `YRP-GRN-2026-00077` as Rejected, and `YRP-GRN-2026-00078` as Misstitch.
  Each linked the exact `YRP-WO-2026-00049` Deliverable and created a reciprocal
  same-warehouse SLE pair: outgoing `S-0170/Accepted` and incoming selected
  Received Type, one Piece and `₹163.582` on both legs. Accepted changed only
  loose return/delivered counters; Rejected changed S Accepted 15→14, rework
  5→6, rejected 0→1, and delivered 20→19; Misstitch changed Accepted 15→14,
  rework 5→6, rejected 0, and delivered 20→19. Their exact selected buckets and
  Work Order pending counter moved with each submit.

  All three were canceled using the **Cancel** button in the Finishing Plan's
  rendered Return Item List. A106 was found on the first Rejected cancel and
  the same still-submitted GRN passed after the persisted-SLE reversal fix.
  Every return now has docstatus 2, no active SLE, zero selected-type Bin, and
  restored Work Order pending zero/stock-update 20. The temporary
  reconciliation was then canceled through its rendered form; all temporary
  Accepted/Rejected/Misstitch Bins are qty/value zero. Final rendered reload is
  clean and retains `Dispatched`, the three original active DCs, three original
  packing GRNs, both active dispatch routes, 10 boxes/120 Pieces fully
  dispatched, and the exact U33 five-size projection. The immediate
  post-submit reconciliation remount reproduced the already-recorded G02
  Frappe control race once; Accepted/Misstitch cancel callbacks each aborted
  one superseded duplicate stock read while their replacement read returned
  HTTP 200. These navigation artefacts made no business mutation and the final
  clean reload has zero console/page/request/response failures. U34, A105, and
  A106 are complete; no screenshot was produced and base YRP remains
  unchanged.

- U35 Packing many-to-one/UOM qualification (2026-08-27): a fresh read-only
  rendered-form pass opened all three retained Packing GRNs and their exact GRN
  Completion Stock Entries. `YRP-GRN-2026-00063/00064/00065` remain submitted
  and completed at 2/3/5 boxes, 24/36/60 physical Pieces, one White batch each,
  12 pieces per box, and ratio S/M/L/XL/2XL = 2:3:3:2:2. Their five outputs are
  respectively 4/6/6/4/4, 6/9/9/6/6, and 10/15/15/10/10; every output and each
  linked transaction row is UOM/stock UOM `Pieces`, conversion 1. Boxes remain
  only in the authoritative packing-batch rows.

  Each GRN has exactly 60 mappings over 24 distinct Work Order inputs, 24
  consumption SLEs, five output SLEs, and 60 active production links whose
  persisted consumption/output SLE names match those mappings. Material/output
  values reconcile exactly at ₹4,132.378510476/₹4,204.378510476,
  ₹6,198.567765714/₹6,306.567765714, and
  ₹10,330.94627619/₹10,510.94627619; the differences are the exact process
  values ₹72/₹108/₹180. Completion Stock Entries
  `YRP-STE-2026-00065/00066/00068` each retain five Piece rows with conversion
  1 and exact GRN Item references. Each has five outgoing plus five incoming
  SLEs, equal physical quantities on both sides, and identical values of
  ₹4,204.378510476, ₹6,306.567765714, and ₹10,510.94627619 respectively.

  Cumulatively, all 24 `YRP-WO-2026-00049` inputs have `stock_update == qty`
  and zero pending; its five outputs have zero pending and calculated receipts
  20/30/30/20/20. This retained Work Order predates A91 and therefore keeps its
  submitted planning receivable metadata at the packed Item master UOM `Box`;
  it was not rewritten. The actual post-A91 GRN and transfer transactions above
  are all physical `Pieces`, which is the U35 transaction-UOM boundary. New
  dynamic Packing Work Orders are covered by A91's focused Piece-UOM regression.
  All six rendered forms and every related API load returned HTTP 200 with zero
  console, page, request, or response failures. U35 is complete; no screenshot
  was produced and base YRP remains unchanged.

- U38 complete retained-flow transfer-ledger qualification (2026-08-27): an
  authenticated browser-session audit read all 780 active SLEs across the 62
  retained `MRP-UAT-260826-01` vouchers, using the site's actual configured
  dimensions (`lot` and `received_type`, both mandatory valuation dimensions).
  It identified 34 physical-transfer/reclassification vouchers and proved all
  460 of their SLEs form exactly 230 mutually linked outgoing/incoming pairs.
  Coverage is 13 Delivery Challans, nine DC Completions, one Send to Warehouse,
  two direct-return GRNs, seven GRN Completions, one GRN Rework Item, and one
  Inspection Entry.

  Every pair has the same voucher, Item, stock UOM, absolute quantity, and
  opposite stock-value difference; every reciprocal
  `paired_stock_ledger_entry` points to the active counterpart. The 223
  cross-warehouse pairs preserve Lot and Received Type exactly. The seven
  same-warehouse reclassification pairs preserve Lot and change only the
  intended Received Type. All 34 vouchers net to zero quantity/value, no active
  retained-flow SLE is valuation-stale, and the paired incoming value audited
  is ₹229,740.83993343. One-sided Stock Reconciliations/Material Receipts are
  inventory origins, Material Issues are dispatches out of inventory, and
  mapped production GRNs are consumption/output transformations; they are not
  misclassified as warehouse transfers and are qualified separately by U39.
  The audit completed with zero console, page, request, or response failures.
  U38 is complete; no screenshot was produced and base YRP remains unchanged.

- U39 complete production-lineage qualification (2026-08-27): the retained Lot
  contains 17 active production GRNs against the four exact Work Orders
  `YRP-WO-2026-00046/00047/00048/00049`. A full authenticated audit followed
  all 341 active production links—not a sample—from each named GRN Deliverable
  source row to its active negative consumption SLE and positive GRN output SLE.
  It also proved every source row names an exact Work Order Deliverable, every
  output names an exact GRN Item and Work Order Receivable, link input quantity,
  allocation weight, and stock-dimension JSON equal the mapped row, and every
  Work Order input/output counter is the sum of those exact active rows. Grouped
  consumption correctly permits one physical input SLE to serve multiple mapped
  output allocations; causality remains one exact production-link row per
  allocation.

  Coverage is seven Cutting GRNs/65 mappings, four Printing GRNs/6 mappings,
  three Stitching GRNs/90 mappings, and three Ironing/Packing GRNs/180 mappings.
  Material/process/output totals reconcile per document and in aggregate:
  Cutting ₹34,798.56 + ₹463.50 = ₹35,262.06; Printing ₹3,419.40 + ₹120 =
  ₹3,539.40; Stitching ₹15,851.092552396 + ₹1,680 = ₹17,531.09255238; and
  Ironing/Packing ₹20,661.89255238 + ₹360 = ₹21,021.89255238. Across all 17,
  exact input material ₹74,730.945104776 plus Work Order process cost ₹2,623.50
  equals output SLE/GRN value ₹77,354.44510476. All involved SLEs are active,
  correctly signed, in the retained Lot, and trace to the persisted GRN/Work
  Order child names. The audit had zero console, page, request, or response
  failures. U39 is complete; no screenshot was produced and base YRP remains
  unchanged.

- U40 late-cost/order-independence qualification (2026-08-27): Stock Valuation
  Adjustment is deliberately read-only and cannot legitimately be fabricated
  through a Desk form, so this engine boundary was qualified by the new
  Essdee-side integration regression `test_late_valuation_chain.py` against the
  finalized base API. It builds two isolated source → Cutting → Printing →
  Stitching → Packing causal chains with four persisted production links. Each
  chain starts with 10 units at rate ₹10 and ends with 10 units at the base
  Packing rate ₹20. A late material `Purchase Invoice Rate Difference` of ₹10
  and late Cutting/Printing/Stitching/Packing process differences of
  ₹1/₹2/₹3/₹4 are then applied once in forward order and once in reverse order.

  Both orders produce identical cumulative receipt overlays
  `[₹10, ₹11, ₹13, ₹16, ₹20]`; the final Packing receipt is exactly quantity 10,
  original rate ₹20, adjustment ₹20, stock value ₹220, and live Bin rate ₹22.
  Every adjustment completes with its exact signed source/propagated difference,
  zero terminal difference, no stale SLE/Bin state, and only Applied/Terminal
  propagation entries. The focused module passes 1/1 in 184.8 seconds. Both
  chains are then reversed through the base API and their nine Stock Entries
  canceled in dependency order; the post-test cleanup audit finds no active U40
  probe entry. Fresh U38 and U39 audits still pass at the exact retained counts
  of 780 active Lot SLEs, 230 transfer pairs, 17 production GRNs, and 341 links.
  Thus the actual four-Work-Order Essdee topology and the base late-cost engine
  are qualified together without mutating retained business data. U40 is
  complete; no screenshot was produced and base YRP remains unchanged.

- U41 Work Order-close qualification (2026-08-27): the focused Essdee close
  suite passes all 9 cases. Its successful manager boundary requires the full
  two-unit excess, posts exactly `qty=-2` at actual FIFO rate ₹13/value ₹26,
  advances the Work Order input counter by the full two units, persists the
  excess audit row and consumption/output production link, and allocates the
  complete ₹26 late-value difference to the exact active GRN output SLE. The
  insufficient-stock boundary requires two units but exposes only one and
  raises before `make_sl_entries` or Work Order save, proving there is no clipped
  quantity/value. The suite also proves closed-period failure before save,
  exact active GRN/output ownership, authoritative Work Order write permission,
  and repeated no-excess close as a read-only success.

  The rendered `YRP-WO-2026-00049` form then opened its real **Close** dialog
  without submitting it. The dialog visibly contained Debit selection, every
  approved reason (`NA`, Cutting/Printing/Sewing shortages, Sewing Missing,
  Others), other-reason/remarks controls, and the **Close Work Order** action;
  closing the dialog made no request or document mutation. A complete read-only
  audit of retained Cutting/Printing/Stitching/Packing Work Orders
  `00046/00047/00048/00049` finds `delivered - stock_update = 0` on every input,
  zero excess-usage children, and zero active Work Order-close SLEs. Thus the
  retained flow has no unexplained residual while the full-post/fail boundary
  is directly regression-qualified. Browser console/page/request/response
  channels were clean. U41 is complete; no screenshot was produced and base
  YRP remains unchanged.

- U42 Stock Valuation Closing qualification (2026-08-27): the finalized base
  closing integration module passes all 15 cases. It exercises the real
  submit/cancel lifecycle and settings cutoff restoration, requires each later
  closing to move forward, permits cancellation only for the latest submitted
  closing, blocks an unready snapshot, and rejects Stock Ledger creation and
  cancellation on the cutoff date while allowing the next open date. It also
  proves a closing cannot submit while a repost or valuation adjustment is
  pending/failed. The full base adjustment/reversal module passes 13/13,
  including closed-period create/reversal rejection before enqueue, restart and
  retry ordering, transfer/production propagation, terminal differences, and
  cancellation ownership. These are read-only qualifications of finalized base
  behavior; no base file was edited.

  An Essdee-owned repost regression now invokes the actual `Repost Item
  Valuation.validate` boundary: a transaction repost dated exactly
  `2026-08-20` against a mocked `2026-08-20` cutoff raises
  `StockValuationPeriodClosedError`, while the otherwise identical
  `2026-08-21` open-period repost validates. The focused Essdee module passes
  3/3 and inserts no document. The rendered Desk route
  `/app/stock-valuation-closing/new-stock-valuation-closing-1` was then opened
  as `ui-verify@essdee.fit`. It visibly exposed required Closing Through Date
  and Closing Remarks, Pending validation state, the Save action, and the
  Closing Period/Valuation Readiness sections; all period, ledger/value,
  repost/adjustment, and negative/zero-bucket results are authoritative
  read-only fields. No actual closing was saved or submitted: submitted closing
  count and the settings cutoff remained empty before and after, and every
  browser channel was clean.

  The base adjustment suite generated 18 isolated `_Test Valuation …` Stock
  Entries (19 active SLEs) as test fixtures. The guarded Essdee test helper
  accepted only their exact voucher list and warehouse prefix, applied normal
  signed reversals, and canceled them in dependency order. A fresh retained
  audit is again exact at 780 active Lot SLEs/62 vouchers/230 transfer pairs and
  17 production GRNs/341 links, proving no business-flow mutation. U42 is
  complete; no screenshot was produced.

- U43 server-side authorization qualification (2026-08-27): the Essdee-owned
  approval gates now raise `frappe.PermissionError` for a caller lacking the
  configured role, so a crafted direct request receives an authorization
  failure rather than a generic validation response. This applies to PPO
  submit/request/change/approval, quantity/ratio/status/transfer approvals, and
  IPD approve/revert. Configuration-missing errors remain validation errors;
  System Manager and explicitly configured roles retain their intended access.

  The new focused `test_server_side_permissions.py` passes 9 isolated ordering
  regressions plus one real-session integration regression. The isolated cases
  prove denial occurs before Inspection Entry document load, Production Order
  lock/load, IPD load/save, migration config load/write check, GRN Rework sync
  or parent mutation, and Finishing Plan Dispatch Stock Entry creation. The
  integration case creates an enabled roleless System User, switches the actual
  Frappe session to it, and calls the real authenticated whitelisted methods for
  Inspection conversion, PPO request/approval, IPD approval, migration
  configuration, rework sync, and stock dispatch. All seven raise
  `PermissionError`; the temporary user is removed and a follow-up query finds
  no `u43-%@example.com` user.

  Surrounding modules remain green: Production Order business logic 13/13,
  panel-wise/IPD approval 11/11, GRN Rework 4/4, migration schema 6/6, and
  Finishing Plan Dispatch 12/12. The successful rendered actions were already
  exercised through their real U16 Inspection, U28/U31 Rework, migration Desk,
  and S24/U36/U37 dispatch flows; this gate adds the missing negative server
  proof and does not create a business transaction. The retained ledger remains
  exactly 780 active rows/62 vouchers/230 pairs with clean browser channels.
  U43 is complete; no screenshot was produced and base YRP remains unchanged.

- U44 concurrent/retry idempotence qualification (2026-08-27): every
  bundle-moving Delivery Challan, Goods Received Note, and Stock Entry now
  locks its own persisted voucher row before inspecting the active CBML
  completion marker. The guard runs before both exact and collapsed paths;
  repeated submit returns without another ledger, and repeated cancel returns
  after the active rows are already gone. LaySheet bundle generation likewise
  locks the LaySheet before its active-ledger check, complementing the existing
  Cutting GRN/LaySheet lock. Direct in-memory compatibility callers without a
  persisted voucher continue to execute their explicit operation.

  Finishing Plan packing GRN creation now accepts a safe 128-character request
  ID, locks the Work Order before availability calculation, and stores the
  request marker in the standard GRN `comments` field. A committed submitted
  winner is returned on retry; an existing draft fails with its exact name;
  cancelled requests may be intentionally recreated with a new ID. The
  rendered Vue component retains one UUID across uncertain network retries and
  clears it only after the success callback. This needs no Custom Field or
  schema migration. The built Desk asset contains the request ID in the actual
  `create_grn` call.

  The focused U44 module passes 6/6. The existing real Cutting regression
  creates its GRN once, calls the creation/label/CBML endpoints again, proves
  the same GRN name and unchanged SLE/CBML/projection counts, then cancels the
  lifecycle. The repaired actual CPM DC→GRN round trip passes. Work Order and
  Finishing projection replay passes 7/7, including two locked Finishing Plan
  rebuilds with identical business rows and no duplicate identities. Finishing
  services/packing/return/source-sync pass 18/18, 5/5, 8/8, and 7/7. The late
  valuation integration now calls `create_adjustment` twice with the same key
  for every material/process difference; both forward and reverse order runs
  return the same durable adjustment names and pass in 188.2 seconds.

  Finally, authenticated rendered route
  `/app/finishing-plan/FP-2526-00238` opened its **GRN** tab and displayed the
  built **Make GRN** component. A complete read-only inventory found exactly
  780 active retained-Lot SLEs, 265 active CBML rows, 20 active GRNs, and 134
  immutable valuation adjustments after A109's retained diagnostic audit rows.
  It found zero duplicate SLE transaction
  identities, CBML transaction identities, active Cutting GRNs per LaySheet,
  Finishing request markers, valuation idempotency keys, or Finishing
  projection identities. Fresh U38/U39 audits remain exact at 62 vouchers/230
  transfer pairs and 17 production GRNs/341 links. Every browser channel is
  clean. U44 is complete; no screenshot was produced and base YRP remains
  unchanged.

- Final post-A109 complete-suite and zero-drift boundary (2026-08-27): the
  mandatory fresh unfiltered
  `bench --site essdee_yrp.site run-tests --app essdee_yrp` run completed with
  exit code 0. All four categories are green: 96 unit, 318 integration with 10
  explicit dataset skips, 124 legacy-category, and 121 unspecified-category
  tests. That is 659 discovered, 649 executed successfully, and 10 explicitly
  skipped. The late material/process valuation chain passed again in 180
  seconds inside the complete run. A direct database audit immediately after
  exit remained exactly 780 active retained-Lot SLEs, 265 active CBML rows, 20
  active retained-Lot GRNs, 134 uniquely keyed immutable adjustments, and zero
  active `_Test Valuation U40 ...` Stock Entries. The suite therefore left no
  persistent test stock or new valuation-adjustment audit rows.
- Final rendered/reconciliation boundary (2026-08-27): the no-screenshot
  Playwright U44 route reopened `FP-2526-00238` as Dispatched, rendered **Make
  GRN**, and passed every browser, page, request, and response channel. All six
  SLE/CBML/Cutting-GRN/Finishing-request/valuation/projection duplicate classes
  remain zero at 780/265/20/134. Fresh U38 is exact at 62 active vouchers, 34
  transfer vouchers, 460 paired SLEs, and 230 equal-value transfer pairs. Fresh
  U39 is exact at 17 production GRNs and 341 production links across Cutting,
  Printing, Stitching, and Ironing/Packing. No screenshot was created.
- R03 final review boundary (2026-08-27): the complete Essdee worktree contains
  93 changed/untracked files: 81 tracked files with 6,785 insertions and 710
  deletions plus 12 new release-candidate files added by this work. All 71
  changed/untracked Python files compile, all 10 JavaScript files pass
  `node --check`, all 7 JSON files parse, `git diff --check` is clean, and no
  test module calls `frappe.db.commit()`. Ruff is not installed. The Desk bundle
  and separate Vite production build both pass; Vite reports only its existing
  chunk-size optimization advisory. Permission-sensitive endpoints retain the
  U43 negative server proof and the final risk scan found no new unreviewed
  mutation boundary. The 12 new paths are only Essdee source/tests/schema/audit
  files; no site data, credentials, blobs, environment, build cache, or
  `node_modules` are release candidates.
- Final repository/source preservation boundary (2026-08-27): base YRP remains
  exactly at `7536d315c380157fa1d90936b2f5343b9eed6481`, with tracked diff
  SHA-256 `849c7a8b...a04a88b` and untracked test SHA-256
  `62e3be5d...d1d164`; Frappe and ERPNext remain clean. The F15 source checkout
  independently advanced after the original freeze to `300a09d0` and currently
  has four owner/other-session dirty files. It was inspected read-only and was
  not modified here. Its only new migration-schema values are blank
  descriptions: 0/4,463 nonblank Items and 0/437 nonblank IPDs. The new
  Production Order `Close Request` option also has zero historical source rows,
  so none of this external source drift changes the accepted migrated dataset;
  A97/A108 classify the schema fields explicitly. The checkout must be
  independently re-frozen before any later migration is rerun. As the owner
  stated during acceptance, `mrp3.site` is currently out of maintenance mode;
  this does not alter the already-Verified `00012` snapshot but is another
  required preflight if a later migration is attempted.
- Owner-approved release-gate closure (2026-08-28):
  `bench --site essdee_yrp.site migrate` completed successfully, synced all
  DocTypes/fixtures/customizations, ran both tracked Essdee patches, completed
  after-migrate hooks, and rebuilt the `/web` SPA. Patch Log contains both
  `backfill_deterministic_valuation_lineage` and
  `move_process_allowance_to_base_field`. The legacy Process Custom Field is
  absent, `Cutting.wo_excess_allowed_percentage` remains exactly 300%, and the
  new GRN-validation exempt-supplier child DocType is installed. Post-migrate
  physical-schema, migration-DocType, planner, and transformer modules pass
  6/6, 6/6, 5/5, and 17/17. The final no-screenshot rendered U44/U38/U39 rerun
  remains exact at 780 active SLEs, 265 active CBML rows, 20 active GRNs, 134
  uniquely keyed adjustments, 62 vouchers/230 transfer pairs, and 17
  production GRNs/341 lineage links, with zero duplicate or browser-error
  classes.
- The unchanged dirty base-YRP runtime overlay now has a committed-release
  deployment artifact under
  `docs/release-artifacts/2026-08-28-base-yrp-overlay/`. The tracked binary
  patch archive SHA-256 is
  `17b6556a5ccaeba964cd9aebd1e6978f76cb4121f7856f414f9bdfec9e2dc61b`;
  its decompressed SHA-256 is the exact frozen diff hash
  `849c7a8b2ca97e2fda2c97a95f5078b92c6979cd30e7a53c4d16311eea04a88b`;
  the untracked-file archive SHA-256 is
  `fdd8a604cc67b18bf38dea07dc4ebdf628b3c846a762b070cdbabd659e20136b`,
  and its extracted test retains SHA-256
  `62e3be5d399780b1f1553df65f7ee465764b468e68d8ed0d5b11c9617291d164`.
  `git apply --reverse --check --binary` proves the patch exactly matches the
  loaded base overlay, the gzip archive passes integrity validation, and base
  YRP itself remains unchanged at `7536d315`.
- Reviewed Essdee MRP release payload commit
  `a68fd97c0a796843fa69bf5ca2997ff8c0e3cef2` was created from the complete
  qualified worktree and pushed successfully to `origin/MRP` on 2026-08-28.
  The repository was clean immediately after the commit and the pushed remote
  advanced from `8be20a02` to `a68fd97c`.

The sequential script is accepted only when every created record name and
evidence result is recorded here or in a linked evidence manifest. A green test
against an older/manual Work Order, IPD, Lot, Sewing Plan, or Finishing Plan does
not satisfy any `Sxx` item.

### Foundation and cutting

- [x] U01 Production Order → Lot → Item Production Detail links and configuration.
- [x] U02 Cutting Process Cost approval and Work Order submit; Summary planned/delivered/received projection.
- [x] U03 Stock Reconciliation/Stock Update input stock with all stock dimensions and UOM/rate evidence.
- [x] U04 Cutting Plan without WO, submit, then link WO through Update; markers and LaySheets.
- [x] U05 Cloth/accessory entry ordering, received-weight precision, bundle generation, 15%/whole-piece excess, persisted idempotent usage.
- [x] U06 Bundle tables and CBML creation for every panel/accessory; no lost/duplicate movement.
- [x] U07 Cut Panel Movement split across multiple CPM/DC documents; balance filters show only eligible bundles.

### DC/GRN/CBML exhaustive cases

- [x] U08 Normal delivery and full GRN.
- [x] U09 Partial delivery and partial GRN across multiple documents.
- [x] U10 GRN with reduced quantity using collapsed bundles and no CPM.
- [x] U11 Return against DC, return as collapsed bundles, and pending rebuild.
- [x] U12 Send as collapsed, redeliver collapsed bundle, and receive it again.
- [x] U13 Cancel attempts in valid/invalid dependency order; error messages and complete rollback.
- [x] U14 CBML after each submit/cancel/return/redelivery: quantity conservation, status, source/target, and no orphan rows.
- [x] U15 GRN grouped table: one logical SKU/panel/colour row with all size columns; set-combinations and received types stay distinct.
- [x] U16 Inspection split (Accepted/Rejected/other Rework type), role-gated Convert Stock visibility, conversion/cancel rules, and SLE conservation.

### Printing and embellishment

- [x] U17 Printing Work Order, approved Process Cost, supplier/address, Summary.
- [x] U18 Only eligible panels delivered; multiple DCs and normal/partial/reduced/collapsed/return cases.
- [x] U19 Printing GRNs use exact 1:1 input/output lineage, correct material plus process value, and Work Order projections.
- [x] U20 Remaining configured embellishment process (including Yolk Fusing) basic WO/DC/GRN lineage and valuation.

### Sewing

- [x] U21 Stitching Work Order for a company-location supplier creates/links the Sewing Plan only when configured.
- [x] U22 All required panel/accessory stock transferred and DC created from UI.
- [x] U23 Sewing Details Registered Experience parity: stage/configuration order prevents later output before required prior entries.
- [x] U24 Input, sewing output, AQL/checking output, GRN prerequisite errors, correction, and successful GRN.
- [x] U25 Partial colour GRN updates Finishing Plan stitching received only after authoritative Work Order calculation completion.
- [x] U26 Remaining stitching receipts include an eligible non-Accepted/non-Rejected Rework type.
- [x] U27 Sewing/DC/GRN return and cancel idempotently rebuild Work Order and Finishing Plan projections.

### Rework

- [x] U28 GRN-style grouped Create Rework UI, authoritative received-type source appearance/removal, quantity caps, and permission checks.
- [x] U29 Rework dispatch consumes the correct received-type bucket with actual FIFO value and paired SLEs.
- [x] U30 Rework Details entry/clear updates Finishing Plan only at the completed authoritative boundary.
- [x] U31 Rework GRN returns Accepted/Rejected/other type, allows newly eligible additional delivery, and conserves stock/value through cancel.

### Finishing, ironing, packing, and dispatch

- [x] U32 Ironing/Packing Work Orders and Process Costs create/link the Finishing Plan only for configured company-location suppliers.
- [x] U33 Finishing Plan cutting/stitching projections match Work Order Calculated Items after normal, return, cancel, and rework flows.
- [x] U34 Finishing DCs and GRNs cover partial, multiple, excess, received types, return, and cancel.
- [x] U35 Packing many-to-one consumption/output lineage and transaction-UOM conversion.
- [x] U36 Finishing Plan Dispatch popup matches production_api, creates the dispatch Stock Entry through its existing API, and posts paired/value-preserving stock.
- [x] U37 Dispatch cancellation/retry and remaining-dispatch projection.

### Valuation, accounting boundary, and security

- [x] U38 Every physical transfer has exactly paired outgoing/incoming SLEs with equal stock value and dimensions.
- [x] U39 Every production receipt traces to exact consumption SLE(s), GRN output SLE, Work Order output, and material/process value.
- [x] U40 Late material/process cost propagation across Cutting → Printing/Fusing → Stitching → Ironing/Packing produces order-independent final valuation.
- [x] U41 Work Order close posts full excess or fails; no clipped unexplained quantity/value.
- [x] U42 Stock Valuation Closing rejects create/cancel/repost on or before cutoff and allows valid open-period work.
- [x] U43 Role checks are enforced server-side for Inspection conversion, approvals, rework, migration, and dispatch—not only hidden in UI.
- [x] U44 Concurrent/idempotent retry checks create no duplicate SLE, CBML, projection, GRN, or valuation adjustment.

## 10. Evidence required per scenario

For each applicable `Uxx` item, retain:

1. the exact rendered-UI route, action/button used, and visible result;
2. browser console, page-error, and relevant network-request result;
3. document names, `docstatus`, status, and authoritative links;
4. source/destination stock bucket quantities by item, warehouse, lot,
   received type, and other valuation dimensions;
5. outgoing/incoming SLE names, quantities, stock-UOM rates, values, transfer
   pairs, posting order, and cancellation state;
6. GRN Deliverable input/output/SLE lineage and production links;
7. CBML conservation for bundle cases;
8. Work Order Calculated Item and Finishing Plan before/after totals;
9. negative-path error text and proof that no partial transaction committed;
10. a checklist entry linking the evidence path/result.

The transactions themselves must be created through the rendered UI; direct
API/console writes cannot substitute for UI creation. Read-only ledger/API
queries are then required to prove database, stock, and valuation correctness.

## 11. Final acceptance gates

- [x] G01 Every implementation and migration checklist item is complete or explicitly marked non-applicable with evidence.
- [x] G02 Every UI scenario is complete; zero unexplained console/page errors.
- [x] G03 Focused Python/JS tests, full Essdee suite, asset build, frontend build, schema migrate, and UI verification pass.
- [x] G04 Migration has zero blockers/unexpected invalid links and documented historical unresolved-lineage counts.
- [x] G05 Stock quantity, CBML, valuation, transfer-pair, production-link, Work Order, Sewing, Rework, and Finishing projections reconcile.
- [x] G06 Independent final diff confirms changes are Essdee-only and all custom schema is tracked.
- [x] G07 Base `yrp` dirty fingerprints are unchanged and its final deployment artifact is recorded.
- [x] G08 No site data, credentials, attachment blobs, environment, build cache, or node modules are committed.
- [x] G09 Local missing attachment blobs are resolved from the production archive or formally accepted as an external deployment action.
- [x] G10 Final MRP commit is reviewed, pushed, and the release evidence/report identifies its exact SHA.

All ten final acceptance gates are closed. The no-screenshot owner instruction
remained authoritative, so no generic screenshot-producing verifier was run.

### 2026-08-28 manual UAT follow-up — A110

- The Essdee Work Order adapter now returns blank `from_location` and
  `from_warehouse`; the Desk Work Order handler clears both when the source Work
  Order changes; a scoped Essdee Property Setter clears base YRP's
  `from_warehouse.supplier` fetch from From Location; and the Essdee Delivery
  Challan controller preserves both the submitted blanks and explicit operator
  selections across base `set_missing_values`. Both fields remain editable and
  required. No `/web`
  source was changed or qualified because the owner directed that frontend to
  be excluded and retired.
- Focused regressions are green: `essdee_yrp.api.test_work_order` passed 23/23
  across its integration and unspecified categories, and
  `essdee_yrp.test_delivery_challan_customization` passed 14/14 after the A111
  same-endpoint coverage was added. The specialized
  bulk-LaySheet route passes 12/12, while the broader Cutting module passes all
  16 unit cases plus 16/16 executed integration cases with six explicit
  migrated-dataset skips; that includes the 161-second real CPM → DC → GRN
  round trip and 87-second migrated LaySheet → GRN lifecycle. Changed Python
  compiles, the Desk script passes `node --check`, `git diff --check` is clean,
  and `bench build --app essdee_yrp` succeeds.
- No-screenshot rendered Desk probes used submitted/open Work Orders
  `YRP-WO-2026-00058` and `YRP-WO-2026-00046`. After selection both source
  fields were blank, required, enabled, and in Frappe `Write` status; From
  Location had no `fetch_from`. Manual source selections persisted, and changing
  the Work Order cleared both again. Console, page-error, and HTTP-error
  collections were all empty. The probes remained unsaved local drafts and
  created no transaction.
- Base YRP remains untouched: tracked diff fingerprint
  `849c7a8b2ca97e2fda2c97a95f5078b92c6979cd30e7a53c4d16311eea04a88b`
  and untracked-test fingerprint
  `62e3be5d399780b1f1553df65f7ee465764b468e68d8ed0d5b11c9617291d164`
  are unchanged.

### 2026-08-28 manual UAT follow-up — A111

- Base YRP's only same-warehouse DC rejection is in `validate_items`; Essdee now
  overrides that method with the otherwise identical item/correction-row and
  submitted-positive-quantity checks, omitting only the warehouse-inequality
  rule. Equal From/To Location is also accepted. No GRN rule was widened.
- A same-location endpoint is non-internal, so no transit/DC Completion step is
  fabricated. Submit continues through the standard Work Order pending update,
  Cutting Plan `fetch_received_cloth` reads the submitted DC item's delivered
  quantity, and the stock engine writes matched outgoing/incoming rows with the
  same transfer key and warehouse. The warehouse's net quantity and value stay
  unchanged while the DC and production lineage remain auditable.
- Focused regressions prove the relaxed validation, retained missing-item and
  zero-quantity failures, balanced same-warehouse SLE legs, Work Order pending
  reduction, and Cutting Plan received/balance cloth projection: the Delivery
  Challan customization module passes 14/14, including proof that the live site
  resolves Delivery Challan to the Essdee controller and the new Property Setter
  is included in the scoped deployment fixture. The broader Cutting module passes
  all 16 unit cases and all 16 executed integration cases, with six explicit
  migrated-dataset skips; this includes the 147-second real CPM → DC → GRN
  submit/cancel round trip and 80.6-second migrated LaySheet → GRN lifecycle.
  The separate Finishing-return module passes 8/8, including its explicit proof
  that an ordinary same-warehouse GRN remains rejected.
- A no-screenshot rendered Desk probe used open Work Order
  `YRP-WO-2026-00058`. The unsaved form retained `S-0164` as both From/To
  Location and both From/To Warehouse; From Location and From Warehouse were
  required, enabled, and had Frappe control status `Write`; From Location's
  effective `fetch_from` was blank. Console, page-error, and failed-request
  collections were empty, and the probe created no transaction.

### 2026-08-28 manual UAT follow-up — A112

- The table implementation was present and healthy: migrated control plan
  `CP-2608-00015` rendered four cloth rows and two accessory rows with Required,
  Received, Used, and Balance columns. The failing plan `CP-2608-00018` instead
  had zero cloth/accessory children even though its 32 garment rows calculate to
  four requirements and submitted same-location DC `DC-2026-00038` carries the
  matching Mint, Black, Olive, and Navy variants at 116.4 kg each. This isolated
  the defect to requirement generation and refresh lifecycle rather than the
  Vue table or Delivery Challan data.
- Essdee now generates missing requirements during initial Cutting Plan submit
  and makes the existing Fetch Received Cloth action repair historical submitted
  plans before applying DC quantities. The calculator adopts production_api's
  current fail-closed consumption/mapping behavior, so one missing panel row can
  no longer silently create a partial or empty requirement table. Manual
  regeneration retains operational received and used values for matching rows,
  and a genuinely empty submitted plan remains Planned instead of satisfying an
  empty Ready-to-Cut loop.
- The Desk controller always supplies the cloth/accessory table type and reloads
  after Fetch. The component now uses valid single-table markup and renders an
  explicit operator message when requirements are absent. No `/web` source was
  changed. A pre-repair rendered no-screenshot check on `CP-2608-00018` showed
  that safe empty state with one table and no console/page/request errors.
- The real rendered **Fetch and Calculate → Fetch Received Cloth** action then
  returned `generated_requirements=true` and four rows. After the automatic
  reload, `CP-2608-00018` visibly showed Mint, Black, Olive, and Navy, each with
  Required 116.4 kg, Received 116.4 kg, Used 0 kg, and Balance 116.4 kg; status
  was Ready to Cut. One valid table was mounted, the child and `__onload` counts
  both equalled four, and browser console, page-error, failed-request, and API
  error collections were empty.
- Verification is green: all 12 fabric-requirement tests, all 19 Cutting unit
  tests, and all 16 executed Cutting integration tests pass, with six intentional
  dataset skips among the 22 discovered integrations. The real suite includes
  the 149-second CPM → DC → GRN round trip and the 87.3-second migrated
  LaySheet → GRN lifecycle. Python compile, `git diff --check`, and
  `bench build --app essdee_yrp` also pass. Base YRP remains untouched with
  tracked fingerprint `849c7a8b2ca97e2fda2c97a95f5078b92c6979cd30e7a53c4d16311eea04a88b`
  and untracked-test fingerprint
  `62e3be5d399780b1f1553df65f7ee465764b468e68d8ed0d5b11c9617291d164`.

### 2026-08-28 manual UAT follow-up — A113 (completed)

The owner paused the Printing DC/GRN manual test and reported the following
Desk regressions. This batch is intentionally limited to Essdee's MRP branch;
base YRP and the retired `/web` frontend remain out of scope.

- [x] A113.1 Restore Lot piece-to-box derivation using the IPD packing combo,
  then let the existing Lot save lifecycle update Production Order quantities.
  Remove the Edit action from the derived box table while retaining piece-entry
  editing.
- [x] A113.2 Restore Lot-aware Process Cost attribute-value population from the
  selected IPD/process mapping.
- [x] A113.3 Restore the Delivery Challan **Update Secondary** interaction and
  editable secondary quantities in the Desk matrix.
- [x] A113.4 Rebuild Cutting Plan received-cloth quantities automatically after
  Delivery Challan submit/cancel and internal-unit DC Completion submit/cancel;
  retain Fetch Received Cloth as an idempotent historical repair action.
- [x] A113.5 Render and persist panel-wise IPD Cloth Mapping Details when the
  panel-wise consumption mode is enabled.
- [x] A113.6 Make Reverted Cutting LaySheet **Update Status** visibly freeze,
  report the restored state/GRN, and reload the document after success.
- [x] A113.7 Restore Cutting Plan list indicators for Planned, Partially Ready,
  Ready to Cut, Partially Completed, and Completed states.
- [x] A113.8 Stop fresh/saved Goods Received Note matrices from materializing
  every Received Type as an unselected zero row; keep the default and explicitly
  selected types only, while preserving the UI action for adding another type.
- [x] A113.9 Replace the generic Frappe child-table DC return popup with the
  production-style responsive return matrix, while continuing to call base
  YRP's authoritative return-availability and draft-GRN endpoints.
- [x] A113.10 Profile Stock Entry, Delivery Challan, and Goods Received Note
  submits against recent UAT documents; remove demonstrated synchronous or
  repeated work without weakening stock, valuation, pending, or lineage rules.
- [x] A113.11 Run focused Python/JS tests, Essdee build, Desk no-screenshot UI
  checks, submit timing checks, diff review, and unchanged-base fingerprint
  proof before returning the manual test to the owner.

Initial comparison evidence: production_api still contains
`Lot.derive_items_from_order_details`, its box table has no Edit column, and its
Process Cost script resolves attribute values from the Lot IPD. Essdee currently
has none of those three adapters. Essdee also has no Delivery Challan/Cutting
Plan lifecycle sync, no panel-wise cloth-mapping renderer, and no Cutting Plan
list script. Base YRP's normal GRN default builder currently emits one row for
every Received Type, including zero-quantity unselected types; Essdee's current
normalization preserves those rows. Base YRP's DC Return action uses a generic
Frappe Table even though its server endpoints already enforce returnable stock,
previous returns, consumption, dimensions, and quantity caps. Those findings
are the implementation targets for this batch.

Completion evidence:

- Lot now derives its server-owned box quantities with
  `ceil(piece quantity / IPD packing_combo)` and uses only the major set part
  where applicable. The derived Desk matrix no longer has an Edit action; the
  piece-entry matrix remains editable and the normal Lot save path continues to
  update the linked Production Order. Rendered record `Test Lot 1` showed 32
  piece rows, eight derived box rows, and zero box Edit actions.
- Process Cost now scopes both Attribute and Attribute Value choices to the
  selected Lot's IPD/process mapping. Base YRP's concurrent item-only callback
  is neutralized through the Essdee override so it cannot race and replace the
  Lot result. A rendered unsaved retrigger on `YRP-PC-00026` repopulated Panel
  value `Top Front` without saving a transaction.
- The draft DC matrix now mounts one **Update Secondary** control per item
  group, obtains the Item's secondary UOM, and edits the same data object saved
  by the base DC editor. Rendered draft `DC-2026-00037` showed the control and
  its configured `Roll` UOM. The zero-primary-attribute case is explicitly
  represented by a default quantity column.
- Cutting Plan receipt projection is now an idempotent rebuild. Submitted
  direct DC rows are counted immediately; cross-location internal DCs are
  counted only from submitted DC Completion Stock Entries; submit, cancel, and
  repeated Fetch operations converge on the same result. Missing historical
  requirement rows are regenerated before receipt application, while existing
  received/used values are preserved during explicit regeneration.
- Current production_api panel-wise consumption and Cloth Mapping behavior was
  ported into Essdee and wired into IPD validate/save. Rendered IPD
  `JUNIOR POLO GYM VEST-1` mounted both matrices; Cloth Mapping showed one table
  and `5 / 5 complete`.
- Reverted LaySheet **Update Status** now freezes with a restoring message,
  reports the resulting Label Printed state and GRN, and reloads the form.
  There was no persisted Reverted LaySheet oracle at final verification, so the
  callback/return contract was covered by the focused regression instead of
  mutating a completed operational record.
- Cutting Plan list view loads the Essdee indicator map. The rendered list
  returned 21 rows with live Completed/Cutting In Progress indicators and no
  browser errors; Planned, Fabric Partially Received, Ready to Cut, Partially
  Completed, Completed, and dispatch-pending branches are covered by the list
  regression.
- Fresh and saved draft normal Work Order GRNs now retain only the default or
  explicitly selected Received Type rows. Rendered drafts `GRN-2627-05043` and
  `GRN-2627-05033` each displayed only Accepted splits, while still showing the
  **Add Received Type** choices for rejected/rework categories.
- Submitted `DC-2026-00041` opened the custom responsive return matrix with
  authoritative quantities, normal/collapsed and whole-bundle controls, one
  native HTML table, and zero Frappe child grids. The server wrapper continues
  to delegate quantity/lineage validation and GRN creation to base YRP's
  existing endpoints.
- Profiling isolated the submit freeze to four voucher-ownership checks that
  each scanned all 1,362,774 Stock Ledger Entries. Essdee now deploys the
  composite `voucher_type, voucher_no, is_cancelled` index idempotently after
  install/migrate; the live site has that exact index. The same real CPM → DC →
  GRN submit/cancel lifecycle fell from 154.2 seconds to 23.9–24.8 seconds
  (about 84% faster) with stock, valuation, pending, bundle, and cancellation
  assertions retained. The real CPM → Stock Entry lifecycle completed in
  5.0 seconds in the full suite (13.8 seconds on a cold standalone run), and the
  FG-created Stock Entry submit/cancel integration completed in 10.2 seconds.
- Final focused verification discovered 108 tests: 102 passed and six migrated
  dataset-dependent Cutting oracles skipped explicitly. This includes Lot 4/4,
  Process Cost 4/4, panel consumption/mapping 16/16, DC 18/18, GRN 13/13,
  lifecycle/performance guards 4/4, Cutting unit 19/19, Cutting integration
  16 passed plus six skips, and Stock integration 8/8. Python compilation, Desk
  JavaScript syntax, `git diff --check`, and `bench build --app essdee_yrp`
  passed. No screenshot was produced, as directed; the rendered probes found no
  console, page, or failed-request errors and saved no transaction.
- Base YRP was not edited by this batch. Its tracked diff fingerprint remains
  `849c7a8b2ca97e2fda2c97a95f5078b92c6979cd30e7a53c4d16311eea04a88b`;
  its untracked delivery-challan test fingerprint remains
  `62e3be5d399780b1f1553df65f7ee465764b468e68d8ed0d5b11c9617291d164`.

### 2026-08-28 manual UAT stock setup — A114

- Submitted Stock Reconciliation `YRP-ST-RECO-2026-00013` through the Desk for
  Stitching Work Order `YRP-WO-2026-00060`. It targets warehouse `S-0070`
  (Essdee Accessories Store - Tirupur), Lot `Test Lot 1`, and Received Type
  `Accepted`.
- Only the five Work Order accessories were reconciled: Compo Label 5,600 Nos,
  Flag Woven Label Black 800 Nos, Flag Woven Label White 4,800 Nos, Essdee
  Junior Printed PolyCotton Tape 10 mm 1,280 Meter, and Twill Tape 5 mm 168
  Meter. The reconciliation contains zero `CS-34820 Heavy Tee-*` panel rows.
- Each submitted Stock Ledger Entry and resulting Bin equals its target
  quantity, warehouse, Lot, Received Type, and latest ledger valuation rate;
  browser console, page-error, and failed-request collections were empty.

### 2026-08-28 stock transaction performance follow-up — A115 (completed)

The owner reported that submitting stitching Delivery Challan
`DC-2026-00043` took more than two minutes and required the same performance
class to be fixed for DC, GRN, Stock Entry, and Stock Reconciliation.

- [x] A115.1 Trace the real voucher volume and shared stock-ledger path. The DC
  contains 144 effective item rows and creates 288 Stock Ledger Entries.
- [x] A115.2 Compare the current YRP engine with production_api's stock
  optimizations. production_api's `0bbc0769` optimization adds an active
  item/warehouse/received-type/docstatus/status reservation index; the current
  Essdee database has 322,193 reservation rows and no usable reservation index.
- [x] A115.3 Prove the missing-index cost before changing code. Each active
  reservation lookup performed a full 316,717-row table scan and took
  0.11–0.24 seconds cold; the ledger invokes that query once per effective SLE.
- [x] A115.3a The first cold rollback benchmark then exposed the second
  reservation path: cancelling the DC spent 207.2 seconds looking up each Work
  Order reservation by voucher/detail against the same unindexed 322,193-row
  table. This query is specific to YRP's authoritative DC/SRE lifecycle and is
  not covered by production_api's newer active-bucket index.
- [x] A115.4 Deploy an idempotent Essdee-owned reservation-bucket index that
  includes Item, Warehouse, Lot, Received Type, docstatus, and status, plus a
  separate voucher/detail/docstatus ownership index, without changing base
  YRP's stock or valuation rules.
- [x] A115.5 Re-run the exact query plan and a rollback-protected 144-row
  DC/288-SLE submit/cancel benchmark, then verify document status, SLE/Bin
  quantities and values, Work Order projection, and zero persistent test data.
- [x] A115.6 Run the focused stock regressions, setup/index test, compilation,
  diff review, and unchanged-base fingerprint proof before handoff.

Completion evidence:

- `ensure_stock_transaction_indexes` now installs both reservation indexes
  idempotently from Essdee's existing after-install/after-migrate setup path.
  The base YRP engine and its validation, reservation, valuation, dimension,
  FIFO, pending, and lineage behavior are unchanged.
- The exact active-bucket query changed from a full 316,717-row scan at
  0.112–0.243 seconds to an indexed 36-row range at 0.00040–0.00055 seconds.
  The exact Work Order reservation-owner query changed from a full table scan
  to one indexed row at 0.00026 seconds.
- On the real 144-row `DC-2026-00043` dataset, the cold rollback-protected
  cancellation exposed the second scan at 207.2 seconds. With both indexes,
  the identical cancellation completed in 3.833 seconds and the amended
  144-row submission completed in 4.888 seconds.
- The replay produced 144 outgoing and 144 incoming active SLEs. Their
  quantities were -62,400/+62,400 and values were
  -356,530.0112/+356,530.0112; all 288 rows had paired transfer lineage. All
  288 affected Bin quantity/rate/value snapshots and all 144 Work Order
  deliverable projections matched the pre-replay state exactly.
- The savepoint was rolled back. Temporary amendment `DC-2026-00043-1` is
  absent, original `DC-2026-00043` remains submitted with its original 288
  active SLEs, and the post-rollback Bin and Work Order snapshots still match.
- Focused verification is green: Essdee setup/manual UAT 4/4, Delivery Challan
  18/18, Goods Received Note 13/13, and stock integration 8/8. Base stock
  engine verification passes 39/39, including reconciliation, reservation,
  dimensions, FIFO/Moving Average, repost, and the two full-ledger integrity
  audits; Stock Entry passes 13/13. Total: 95/95 tests. Python compilation and
  `git diff --check` pass. No UI or `/web` source was changed.
- Base YRP was not edited by A115. Its tracked diff fingerprint remains
  `849c7a8b2ca97e2fda2c97a95f5078b92c6979cd30e7a53c4d16311eea04a88b`,
  and its untracked delivery-challan test fingerprint remains
  `62e3be5d399780b1f1553df65f7ee465764b468e68d8ed0d5b11c9617291d164`.

### 2026-08-28 Stock Entry and Stock Reconciliation matrix alignment — A116 (completed)

The owner reported that draft Stock Entry `YRP-STE-2026-00202` renders every
Size as a separate Desk row, most visibly for Lot `Test Lot 1`, Received Type
`Accepted`, Stage `Cut`, Panel `Top Front`, Colour `Mint`. The same matrix
contract must be verified and applied to Stock Reconciliation.

- [x] A116.1 Inspect the live Stock Entry and compare its flat child data with
  the Work Order, Delivery Challan, Goods Received Note, and production_api
  grouping contracts. The document has 144 valid physical rows, but a previous
  Essdee compatibility hook rewrites their display indexes to `0..143`.
- [x] A116.2 Establish the target projection without changing stock data: 18
  logical panel/colour rows (nine panels x two colours), each with the eight
  Size values shown as columns. Lot, Received Type, other Stock Dimensions,
  non-primary attributes, and set combination remain grouping boundaries.
- [x] A116.3 Replace the Stock Entry per-child display workaround with the
  existing Essdee logical item-matrix projection. Do not mutate saved children,
  quantities, source references, validation, or ledger behavior.
- [x] A116.4 Apply the identical read-model projection to Stock Reconciliation
  so migrated/programmatic size rows align like Work Order, DC, and GRN while
  reconciliation targets and stock buckets remain distinct.
- [x] A116.5 Add focused regressions for both DocTypes, verify the exact live
  Stock Entry projection and Stock Reconciliation dimension boundaries, inspect
  both rendered Desk forms without screenshots, and run proportionate stock,
  compilation, diff, and unchanged-base checks.

Completion evidence:

- production_api and current base YRP both define `row_index` as the logical
  item row shared by primary-attribute variants. Essdee's former completion
  workaround instead assigned one index per physical child, which preserved all
  children but deliberately disabled Size-column grouping. Stock Entry now uses
  the same copied logical matrix projection already used by Essdee Work Order,
  DC, and GRN. Stock Reconciliation receives the same onload projection.
- The grouping key retains parent Item, every non-primary attribute, canonical
  set combination, Lot, Received Type, all configured Stock Dimensions, and the
  Stock Reconciliation child warehouse. Therefore only the primary attribute is
  pivoted into columns; distinct valuation/stock buckets cannot be merged.
- Exact server verification of `YRP-STE-2026-00202` produced 18 logical rows
  from 144 physical children. `Top Front / Mint / Accepted / Test Lot 1` became
  exactly one logical row with 45, 50, 55, 60, 65, 70, 75, and 80 cm values of
  100 Pieces each. All 144 in-memory children and saved database row indexes
  remained value-for-value unchanged. Applying the reconciliation projection to
  those same 144 physical rows produced the identical 18-row result.
- No-screenshot Desk verification opened the real draft Stock Entry and real
  submitted reconciliation `ST-RECO-2025-00145`. The Stock Entry rendered one
  `Top Front / Mint` row with all eight Size headers and values. The
  reconciliation rendered its eight `EE-34142 HALF SLEEVE T-SHIRT` sizes in one
  row. Both routes had zero console/page errors and zero failed requests; no
  document was saved, submitted, cancelled, or created.
- Verification is green: Essdee Stock Entry/matrix customization 11/11, base
  Stock Entry 13/13, base Stock Reconciliation 1/1, and the cross-bench Stock
  Entry integration 13 passed with one dataset-only display oracle skipped
  because its isolated test fixture exposed fewer than two parent Items. Total:
  38 passed, one skipped. Python compilation and `git diff --check` pass.
- Base YRP was not edited. Its tracked diff fingerprint remains
  `849c7a8b2ca97e2fda2c97a95f5078b92c6979cd30e7a53c4d16311eea04a88b`,
  and its untracked delivery-challan test fingerprint remains
  `62e3be5d399780b1f1553df65f7ee465764b468e68d8ed0d5b11c9617291d164`.

### 2026-08-28 GRN calculated-input validation lifecycle — A117 (completed)

The owner found that saving a Stitching GRN draft for Work Order
`YRP-WO-2026-00060` fails because calculated Compo Label stock has not yet been
delivered. This availability check belongs to Submit, not ordinary Draft Save.

- [x] A117.1 Trace the exact failure. The shared calculated-input allocator is
  invoked by `garment_grn.before_validate`; `before_validate` runs during Draft
  Save. The Work Order plans 5,600 labels, all 5,600 remain pending, and the
  attempted 100-piece receipt therefore sees zero delivered input available.
- [x] A117.2 Confirm the authoritative submit gate already exists. The Essdee
  GRN controller locks the Work Order and rebuilds the applicable cutting,
  packing, stitching, identity, or fabric consumption plan in `before_submit`.
- [x] A117.3 Remove only the three draft consumption-planner event hooks while
  retaining every ordinary draft structural/default/dimension validation and
  the locked submit-time stock, mapping, quantity, valuation, and lineage gate.
- [x] A117.4 Prove a representative draft saves with undelivered calculated
  inputs, prove Submit still rejects the same state, run focused GRN/valuation
  regressions, and preserve base YRP.

Completion evidence:

- Removed only `finishing.packing_grn.before_validate`,
  `fabric_grn.before_validate`, and `garment_grn.before_validate` from the GRN
  Draft Save event list. Packing defaults, purchase-lot validation, and cutting
  transaction-link validation still run during Draft Save. The Essdee GRN
  controller's locked `before_submit` consumption-plan rebuild is unchanged.
- A rollback-protected live draft against `YRP-WO-2026-00060` saved successfully
  for 100 pieces of Mint / 45 cm while the calculated Compo Label remained
  completely undelivered. No calculated consumption rows were persisted during
  that Draft Save, and the temporary GRN was rolled back and confirmed absent.
- Normal Submit of that same live draft remained blocked first by the Sewing
  Plan's authoritative Checking Output gate (`Checking Output: 0`, `This GRN:
  100`). With only that earlier gate isolated, `before_submit` then produced
  the original authoritative calculated-input error: Compo Label available
  `0.0`, received row requires `100.0`. Thus Draft Save is allowed, but Submit
  still cannot create stock without the required output and delivered input.
- Focused Essdee verification is green: GRN customization 14/14 and valuation
  contract 47/47. Four independent base GRN modules are also green (internal
  unit transfer 13/13, rework 3/3, cancel guards 5/5, excess allowance 10/10).
  Base's aggregate DocType discovery is unavailable because it expects a
  nonexistent `test_goods_received_note.py`. Two other base modules expose
  unrelated shared-site fixture assumptions: Purchase Order GRN has one reused
  Lot item mismatch and one Essdee valuation-rate expectation mismatch; Freight
  Allocation omits the Supplier/Delivery Address fields that are mandatory on
  this site. These failures do not enter the changed Work Order draft/submit
  path and are recorded rather than represented as green.
- Python compilation and `git diff --check` pass. Base YRP was not edited by
  A117: its tracked diff fingerprint remains
  `849c7a8b2ca97e2fda2c97a95f5078b92c6979cd30e7a53c4d16311eea04a88b`,
  and its untracked delivery-challan test fingerprint remains
  `62e3be5d399780b1f1553df65f7ee465764b468e68d8ed0d5b11c9617291d164`.

### 2026-08-29 GRN same-warehouse lifecycle — A118 (completed)

The owner superseded the earlier DC-only same-warehouse decision after manual
UAT found the same base-YRP warehouse-inequality error in Goods Received Note.

- [x] A118.1 Trace the error to base GRN `validate_items` and confirm Essdee's
  existing override allows equal endpoints only for Cutting conversion and
  direct Finishing return.
- [x] A118.2 Extend the Essdee override to permit equal From/To Warehouses for
  every GRN while retaining mandatory warehouse, row, item, and positive-
  quantity checks and every later submit/stock/valuation/lineage validation.
- [x] A118.3 Run focused GRN, return, valuation, compile, diff, and base-YRP
  preservation checks; then record the exact evidence here.

Completion evidence:

- The site resolves GRN to `EssdeeGoodsReceivedNote`. Its `validate_items`
  delegates unchanged to base YRP when endpoints differ; when both warehouses
  match, it omits only the warehouse-inequality exception and repeats base's
  existing row, applicable warehouse, Item Variant, and positive-quantity
  gates. Source-pending, calculated-input, Work Order, stock ledger, valuation,
  UOM, dimension, and lineage methods were not bypassed or changed.
- The focused return module proves an ordinary same-warehouse GRN now passes,
  then proves the same document still rejects a missing Item Variant and zero
  quantity. Its direct Finishing-return submit/cancel and value-preserving
  paired-SLE coverage also remains green: 8/8.
- GRN customization passes 14/14 and the valuation contract passes 47/47.
  Total focused verification: 69/69. Python compilation and `git diff --check`
  pass. `ruff` is not installed in this bench, so no ruff result is claimed.
- No Desk JavaScript or `/web` source changed; this was the server validation
  that raised during Desk Save/Submit. Site cache was cleared so the override
  is active for the owner's next manual attempt.
- Base YRP was not edited by A118. Its tracked diff fingerprint remains
  `849c7a8b2ca97e2fda2c97a95f5078b92c6979cd30e7a53c4d16311eea04a88b`,
  and its untracked delivery-challan test fingerprint remains
  `62e3be5d399780b1f1553df65f7ee465764b468e68d8ed0d5b11c9617291d164`.

### 2026-08-29 IPD-backed Item BOM combination generation — A119 (completed)

The owner found that Desk Item BOM Attribute Mapping `qupp2fta20` rendered the
selected Item Colour/Size and BOM Colour headers but generated no combination
rows. All three Same Attribute checkboxes were unchecked; this is a mapped-axis
case, not a Same Attribute case.

- [x] A119.1 Trace the selected axes and compare base YRP, production_api, the
  linked IPD, and the rendered editor. The base Item has eight Size values but
  no direct Colour values, while IPD `CS-34820 Heavy Tee-1` owns four Colours
  and the exact 32 Colour/Size Cutting combinations.
- [x] A119.2 Keep base YRP unchanged and add an Essdee Desk adapter that replaces
  only the IPD-backed combination source. Non-IPD mappings retain the base
  Item-master fallback.
- [x] A119.3 Preserve the IPD engine's exact row relationships rather than
  generating a new Cartesian product in the browser, and enforce read access
  plus IPD-to-Item identity on the server endpoint.
- [x] A119.4 Verify the exact live endpoint, the unsaved two-axis Desk form, the
  real saved mapping route, focused tests, compilation, asset build, console,
  diff, and unchanged-base fingerprints.

Completion evidence:

- The failure was a calculation/data-source integration defect, not a table
  rendering defect: the Vue grid rendered its headers correctly but the base
  Item-master Cartesian generator received an empty Colour axis and therefore
  produced zero rows. production_api instead delegates to the linked IPD's
  Cutting combination engine.
- Essdee now subclasses the existing Desk mapping wrapper at form-load time and
  replaces only `set_attributes` for records carrying
  `item_production_detail`. The whitelisted Essdee endpoint calls the existing
  `ipd_ui.get_combination(..., "Cutting")`, removes duplicate/blank invalid
  rows, adds the editable BOM placeholders, and returns the current editor's
  row contract. No `/web` frontend or base-YRP source was changed.
- The exact live endpoint for `CS-34820 Heavy Tee-1`, Item
  `CS-34820 Heavy Tee`, Item axes Colour + Size, and BOM axis Colour returned 32
  rows in IPD order: Mint, Black, Olive, and Navy, each with 45, 50, 55, 60,
  65, 70, 75, and 80 cm.
- A non-saving Desk browser drive recreated the owner's unchecked three-row
  attribute selection and generated/rendered all 32 rows. The first row was
  Mint / 45 cm and the last Navy / 80 cm; the Essdee adapter was active and the
  browser reported zero console/page errors. Opening the real saved mapping
  `qupp2fta20` also rendered its currently saved Colour axis as four IPD rows
  with zero console/page errors. The owner's unsaved Size row will produce the
  verified 32-row result after reloading the new Desk asset and clicking Get
  Combination again.
- Follow-up Save verification found the BOM-side Colour values were persisted
  correctly (`Black` in all four saved BOM rows), but base Vue's
  `toggle_row(index, true)` cleared the visible Link input while restoring each
  enabled row. The Essdee adapter now preserves BOM values when enabling/loading
  and clears them only when disabling. A fresh Desk load of real mapping
  `qupp2fta20` rendered all four saved `Black` values and quantities of `1.000`
  with zero console/page errors.
- Focused regression verification passes 4/4. The live endpoint check, Python
  compilation, Desk JavaScript syntax check, `git diff --check`,
  `bench build --app essdee_yrp`, and site cache clear pass. `ruff` is not
  installed in this bench, so no ruff result is claimed.
- Base YRP was not edited by A119. Its tracked diff fingerprint remains
  `849c7a8b2ca97e2fda2c97a95f5078b92c6979cd30e7a53c4d16311eea04a88b`,
  and its untracked delivery-challan test fingerprint remains
  `62e3be5d399780b1f1553df65f7ee465764b468e68d8ed0d5b11c9617291d164`.

### 2026-08-29 Work Order BOM variant-mapping gate — A120 (completed)

The owner found that Work Order `YRP-WO-2026-00061` had retained generic
accessory `Tag Bullet` even though the Item declares the `Colour` variant
attribute and the IPD had no Tag Bullet attribute mapping when that Work Order
was calculated. The later GRN correctly calculated `Tag Bullet-Black`, so the
saved generic Work Order input could not satisfy its exact lineage check.

- [x] A120.1 Compare production_api variant/BOM validation, base YRP tuple
  lookup, the live Item/Item Variant records, IPD timing, saved Work Order
  input, and current mapping.
- [x] A120.2 Add the generic rule to base YRP: an Item BOM row whose Item
  declares variant attributes cannot be calculated without enabling and
  selecting an attribute mapping.
- [x] A120.3 Apply that base rule at both base IPD accessory calculation
  boundaries and consume the same rule from Essdee's garment Work Order
  calculator. Preserve the explicitly supported non-BOM partial-variant paths.
- [x] A120.4 Add base and Essdee Work Order-calculation regressions, verify the
  exact current IPD mapping result, compile, run focused suites, review the
  diff, and leave the already-submitted Work Order/data unchanged.

Completion evidence:

- Live `Tag Bullet` declares Item attribute `Colour`, but the migrated database
  also contains an empty Item Variant named exactly `Tag Bullet`. With tuple
  lookup enabled, that legacy exact-name record was returned before
  `create_variant()` ran, bypassing its existing missing-Colour exception. This
  is why the original Work Order calculation did not show an error.
- Base YRP now validates authored Item BOM mapping intent before lookup. The
  guard is called by both `calculate_accessory_bom` and `get_consumables`.
  Essdee's garment accessory calculator calls that same base guard, so Desk
  Work Order calculation stops before it can retain a legacy empty variant.
- The guard is intentionally scoped to the proven defect: an attribute-bearing
  BOM Item with no enabled/selected mapping. It does not globally outlaw
  partial variants because the fabric engine has an explicit legacy contract
  for some non-BOM attr-less inputs, and it does not rewrite older migrated
  mappings or Item masters.
- The current IPD row 16 is now mapped through `qupp2fta20`. A read-only live
  base calculation for Packing quantity 15 and Colour Black returns
  `Tag Bullet`, quantity 15, with BOM attributes `{Colour: Black}`; downstream
  variant resolution therefore selects `Tag Bullet-Black`. The earlier
  submitted Work Order remains a historical snapshot and was not recalculated
  or mutated by this fix.
- Verification is green: base Item BOM/mapping boundary 5/5, Essdee garment
  BOM/Work Order calculation 6/6, and Lot packing boundary 12/12. The broader
  garment Work Order module loaded successfully but skipped its four
  dataset-gated integration cases on this site. Total executed assertions:
  23/23 passed. Python compilation and both app `git diff --check` pass. No
  Desk JavaScript, `/web` source, DocType data, Work Order, or stock record was
  changed.
- A120 intentionally edits generic base-YRP source in
  `item_bom.py`, `ipd_engine.py`, and the focused base regression file. All
  unrelated pre-existing base changes and the untracked Delivery Challan test
  were preserved. Essdee changes only its garment BOM adapter, focused test,
  and this audit entry.

### 2026-08-29 Submitted Work Order Tag Bullet test-data correction — A121 (completed)

The owner explicitly requested that the stale generic Tag Bullet calculated
input on submitted test Work Order `YRP-WO-2026-00061` be corrected to
`Tag Bullet-Black` so manual finishing/GRN testing can continue.

- [x] A121.1 Resolve the exact child and prove it has no downstream stock or
  transaction ownership before changing submitted test data.
- [x] A121.2 Change only the child Item Variant, preserve its quantities,
  dimensions, UOM, pending state, and identity, clear site cache, and re-read
  the saved row.

Completion evidence:

- The exact child was Work Order Deliverable `ee8cnllpdg`: `Tag Bullet`, qty
  6,400 Nos, pending 6,400, stock update zero, cancelled zero, Lot `Test Lot 1`,
  Received Type `Accepted`. No DC Item, GRN Item, Stock Reservation Entry, or
  Work Order Correction referenced that Item Variant or child.
- Target `Tag Bullet-Black` exists under parent Item `Tag Bullet`, carries exact
  attribute `Colour = Black`, and uses UOM `Nos`.
- Only `item_variant` on child `ee8cnllpdg` was changed. The post-change Work
  Order contains one `Tag Bullet-Black` deliverable and zero generic
  `Tag Bullet` deliverables; qty, pending, stock update, cancellation, UOM, Lot,
  and Received Type remain unchanged. Site cache was cleared.
- This correction does not mark the accessory delivered. Its pending quantity
  intentionally remains 6,400, so the manual test must deliver the required
  `Tag Bullet-Black` quantity against this Work Order before the GRN can consume
  it. No stock ledger or transaction document was created or altered.

### 2026-08-29 Final owner Desk usability fixes — A122 (completed)

After completing the full Production Order through Finishing Plan Dispatch
manual flow, the owner requested four final Desk corrections before beginning
valuation verification.

- [x] A122.1 Replace Essdee's appended Delivery Challan Secondary Quantity view
  with an editable Secondary Qty control inside the existing base item/size
  matrix. Keep Secondary UOM server-derived and remove the redundant host-only
  Vue component.
- [x] A122.2 Make Item Production Detail refresh wait for the async Cutting and
  Cloth Mapping mounts in order, and make the migrated Cloth Mapping column
  visible. Saved `cutting_cloths_json` for `CS-34820 Heavy Tee-1` must render,
  not remain populated inside a hidden parent column.
- [x] A122.3 Restore the production_api-style saved-draft GRN Calculate action,
  but replay the current F16 `work_order_calculated_items` through Essdee's
  authoritative garment process calculator. Rebuild item, UOM, dimension,
  Received Type, rate, and Work Order Receivable linkage on the server.
- [x] A122.4 Make Purchase Order Stock Dimensions row-owned: show the configured
  dimensions in the existing Purchase Order Item matrix, keep the generated
  header production-group field and old Essdee Linked Lots block hidden for
  legacy compatibility, synchronize hidden legacy Lot links from PO Item rows,
  and carry exact PO Item dimensions into Purchase Order GRN defaults.
- [x] A122.5 Run focused Python/UI-source tests, apply the idempotent dimension
  metadata update to `essdee_yrp.site`, rebuild both Desk asset bundles, verify
  the named IPD plus representative DC/GRN/PO routes in the rendered Desk and
  browser console, then complete the independent diff/data-safety review.

Implementation boundary:

- Base YRP owns the reusable inline secondary-field rendering and Purchase
  Order row-dimension transport. Essdee removes its redundant secondary editor,
  owns the IPD refresh ordering, and owns the garment-specific GRN calculation
  adapter/dialog. No retired `/web` source is included.
- The GRN Calculate endpoint accepts only selected saved Work Order calculation
  row IDs and quantities. It does not accept browser-supplied variants, UOMs,
  rates, dimensions, or receivable references, and it preserves quantities in
  other Received Type splits already saved on the draft.

Completion evidence:

- Delivery Challan `DC-2627-03405` renders Secondary Qty as editable number
  controls inside its existing size cells. The saved Secondary UOM appears next
  to the relevant input, blank padded cells no longer display a numeric UOM,
  and the redundant appended Essdee editor is absent. The Desk reported zero
  console/page errors.
- The exact IPD `CS-34820 Heavy Tee-1` renders both saved matrices in the
  Cutting tab: nine Cutting Detail panel rows and nine Cloth Mapping rows, each
  mapped to `MAIN FABRIC`. The final root cause was a migrated hidden
  `column_break_gwca`; its Vue content existed but Frappe assigned the parent
  column `display:none`. The packaged custom-field source and live metadata now
  keep that column visible. The final Desk route reported zero console/page
  errors.
- Draft `GRN-2627-05043` renders the Calculate button and the production-style
  matrix dialog: Received Type `Accepted`, two garment rows, eight size
  columns, and calculated total 11,800. The live read endpoint returned all 16
  saved Work Order calculation rows. A rollback-contained server apply test
  rebuilt an exact one-unit linked GRN row and restored the draft transaction;
  no business document was left changed. The Desk dialog reported zero
  console/page errors.
- Draft `PO-2627-0787` now shows Lot and Received Type on each existing item row
  and in the Fetch Item controls. The generated header Lot and the old empty
  Essdee Linked Lots section are absent from the Desk, while their stored legacy
  data and submitted-PO APIs remain intact. Exact PO Item dimensions are used
  when matching and building PO GRN rows. The Desk reported zero console/page
  errors.
- Final focused verification passes 59/59: base stock grouping 4/4, Essdee DC
  18/18, IPD Cloth Mapping 5/5, GRN customization 16/16, Essdee Lot/PO boundary
  13/13, and three focused PO dimension/GRN transport assertions. Python
  compilation, Desk JavaScript syntax, custom-field JSON parsing, both apps'
  `git diff --check`, and fresh `yrp` plus `essdee_yrp` Desk asset builds
  all pass. The intended idempotent dimension and visibility metadata updates
  were applied to `essdee_yrp.site`; the rendered checks did not save, submit,
  cancel, or otherwise mutate DC, IPD, GRN, or PO business records.

### 2026-08-29 GRN Calculate versus Submit validation boundary — A123 (completed)

The owner confirmed that GRN Calculate is only a draft quantity-entry action.
Work Order pending, checking-output, calculated-input stock, and other business
availability gates must run at Submit, not inside the Calculate dialog.

- [x] A123.1 Reproduce the exact failure on `YRP-GRN-2026-00090`: selecting
  Mint quantity 5 for eight sizes produced 40 in the dialog, but Mint was fully
  received and the pending-row builder omitted it, causing Calculate's internal
  draft Save to raise the unrelated empty-items message.
- [x] A123.2 Let Calculate rebuild selected draft rows from their authoritative
  saved Work Order Receivables even when current pending is zero. Preserve
  browser-trust boundaries and all Submit validations.
- [x] A123.3 Verify Calculate success and Submit rejection as two separate
  transaction boundaries, restore the exact draft, and run focused regression,
  compilation, cache, and diff checks.

Completion evidence:

- A rollback-contained call using the owner's exact selection saved eight Mint
  rows of quantity 5 and returned total quantity 40 without a Calculate error.
- Submitting that calculated draft was then rejected at Submit with the
  specific checking-output evidence for every Mint size: Checking Output 100,
  Already received 100, This GRN 5, Over by 5. This proves availability stayed
  authoritative while moving to the requested lifecycle boundary.
- The transaction was rolled back and re-read: `YRP-GRN-2026-00090` remained a
  Draft with its same modified timestamp and original 16 Olive/Navy rows.
  Focused GRN customization passes 17/17; Python compilation and Essdee
  `git diff --check` pass. No Desk asset change was required.

## 12. Known hard limitations at audit start

- The local source database contains 1,004 File records but only two matching
  physical blobs are present locally. This run can prove File metadata and the
  two available blobs; it cannot prove an archive it does not possess.
- The currently loaded base behavior includes uncommitted changes. Essdee tests
  can qualify against that runtime, but a release is not reproducible until the
  owner records the exact committed/deployed base artifact.
- “Line-by-line verification” means every changed line receives diff review and
  every reachable business branch receives a focused/unit/integration/UI gate.
  It does not mean claiming that arbitrary unexecuted third-party code is
  exhaustively proven.

These limitations are release gates, not reasons to weaken transaction checks or
invent historical lineage.
