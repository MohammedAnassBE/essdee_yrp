# Cloth Actual-Dia and Exact-Source Execution Design

**Date:** 2026-10-06  
**Status:** Conversation design and Opus 5.5 review approved; user written-spec review pending  
**Target bench:** `frappe-16`  
**Reference bench:** `frappe-16-yrp`; Essdee commit `a83d353d908aa290686fd87d80615753ac1cb3a5`; YRP commit `85e1a0958cc36fcd1625f7d0bc99891b22942c3c` plus the seven-file local execution patch whose binary diff SHA-256 is `c5ffd39a1d79243d08eca9e03bf5448dd2a32e65fb9ed041176e2d442807cff6`

## Purpose

Complete the existing cloth-production execution path in the current Frappe 16 bench without replacing its already-ported planning model. The supported production sequence for this phase is:

`Cloth Program -> Knitting WO/DC/GRN -> Dyeing WO/DC/GRN -> Washing WO/DC/GRN`

The implementation must preserve the physical fabric received at Knitting, including Actual Dia, and carry its exact source lineage through Dyeing and Washing. A submitted Delivery Challan is the stock-allocation authority. Draft Work Orders may show the same available source, but they do not reserve it.

## Success Criteria

1. A Knitting GRN can receive one planned fabric as one or more physical Actual Dia Items in Desk.
2. The Lot shows a read-only, server-owned mapping from planned fabric to actual physical fabric.
3. Dyeing and Washing Work Orders calculate from the actual upstream fabric Item, not the obsolete planned Item.
4. Every calculated fabric input retains its exact source GRN row, Received Type and configured stock dimensions.
5. DC submission rejects source swapping and quantities above the exact remaining source quantity under a database lock.
6. GRN submit/cancel updates the Lot conversion state atomically and preserves valuation lineage.
7. When no actual substitution is present, current Cloth Program and Work Order Item identities, quantities, UOMs and fabric-reference allocations remain unchanged. New hidden execution metadata is allowed.
8. Garment, cutting, sewing, finishing, packing, rework, purchase and generic stock flows behave exactly as before, except for the explicitly listed base-YRP correctness fixes and only within their stated guards.

## Scope

### Included

- ERPNext Desk UI only.
- New transactions only; schema migration is allowed, but no historical data backfill.
- Knitting Actual Dia entry and validation.
- Lot actual-fabric conversion model and read-only Desk view.
- Exact physical source discovery, Work Order calculation and persisted execution metadata.
- Exact-source Delivery Challan validation.
- GRN physical-row aggregation and saved execution-contract consumption.
- Actual Item projection through Dyeing and Washing.
- Submit, cancel, partial, excess, Received Type, stock-dimension and concurrency behaviour.
- Focused base-YRP fixes required by this flow.
- Automated regression coverage and a complete Desk smoke flow.

### Excluded

- `/web` UI.
- Compacting and later fabric processes.
- Inspection Entry allocation protection.
- Historical Lot/WO/DC/GRN backfill.
- Stock Entry to Delivery Challan convenience flow.
- Cross-site migration orchestration.
- Unrelated Purchase Order, finishing, packing, cutting or UI redesign work.

### New-transaction cutoff

Add a hidden, read-only, `no_copy` Int field `cloth_execution_version` to `YRP Work Order`. A route-only helper used by `before_insert` sets it to `1` on newly inserted WOs whose IPD has the exact three-stage route defined below. Existing and migrated WOs remain `0`/unset, including in-flight drafts, and always use the legacy path even if recalculated.

The new execution path is then identified by `cloth_execution_version == 1` and a `fabric_execution_key` saved in each calculated child row's existing `additional_parameters`. Only a Knitting GRN whose referenced Work Order/receivable carries both markers can create Lot conversion rows. On the first calculation of a newly inserted Dyeing/Washing WO, all selected upstream sources being versioned/keyed keeps version `1`; all selected sources being legacy downgrades the new WO to version `0` and runs the current legacy calculation; a mixed selection is rejected. An existing version-`0` WO can never upgrade or consume keyed stock. Pre-deployment and migrated documents remain on the current legacy path and are never pulled into a conversion rebuild. No date comparison or historical scan is used.

## Existing Architecture to Preserve

The current bench already owns the following behaviour and remains authoritative for it:

- cloth IPD process matrices and generalized fabric process planning;
- dyed and non-dyed yarn recipes;
- panel-wise fabric mapping;
- Cloth Program build and recalculation on `SD YRP Lot`;
- compacting references in planning data, even though Compacting execution is out of scope here;
- current Work Order selection and calculation API;
- fabric reference allocations;
- GRN valuation, stock-ledger lineage, finishing, packing and cutting integrations;
- ERPNext `Item` as the actual item master.

The reference-branch code is a behavioural source, not a merge target. The current namespaces and Item model remain intact.

## Name and Field Mapping

| Reference model | Current model |
|---|---|
| `Lot` | `SD YRP Lot` |
| `Work Order` | `YRP Work Order` |
| `Delivery Challan` | `YRP Delivery Challan` |
| `Goods Received Note` | `YRP Goods Received Note` |
| `Item Production Detail` | `YRP Item Production Detail` |
| `Process` | `YRP Process` |
| `Received Type` | `YRP Received Type` |
| `Item Variant` | ERPNext `Item` |

Existing base child fields named `item_variant` are not renamed. They already link to ERPNext `Item`, and renaming them would break the base YRP contract. New Python code should call their values `item_code` or `item` internally. New Essdee-owned fields must use Item-accurate names.

## Data Model

### New child DocType: `SD YRP Lot Fabric Conversion`

This is a server-owned, read-only child table. It represents the planned-to-physical conversion derived from submitted Knitting GRNs and its projection through the configured fabric route.

| Field | Type / option | Meaning |
|---|---|---|
| `process_name` | Link / `YRP Process` | Route process represented by this conversion |
| `planned_item` | Link / `Item` | Planned Item at this process stage |
| `actual_item` | Link / `Item` | Physical/projected Item at this process stage |
| `actual_quantity` | Float | Physical quantity represented by this row |
| `production_detail` | Link / `YRP Item Production Detail` | Cloth IPD owning the route |
| `route_item` | Link / `Item` | Cloth Program route Item used to disambiguate routes |
| `knitting_planned_item` | Link / `Item` | Original planned Knitting output |
| `knitting_actual_item` | Link / `Item` | Original physical Knitting receipt |
| `process_stage_index` | Int | Stable position in the fabric route |
| `received_type` | Link / `YRP Received Type` | Physical stock classification |
| `stock_uom` | Link / `UOM` | Stock UOM of the physical Item |
| `source_grn_count` | Int | Computed number of submitted Knitting GRNs aggregated into the row |

All fields are read-only and `no_copy`. `source_grn_count` is rebuilt, never incrementally trusted. Individual source-GRN lineage stays on Work Order/GRN rows; the Lot table intentionally aggregates physical conversions.

### `SD YRP Lot` additions

- `actual_dia_conversion_tab`: Tab Break.
- `actual_dia_conversion_html`: HTML read-only Desk rendering.
- `lot_fabric_conversions`: Table -> `SD YRP Lot Fabric Conversion`, hidden/read-only as the server-owned source.

No enablement flag is added. Qualification is derived from existing document facts and the new execution key so users do not maintain duplicate configuration.

### Existing transaction fields reused

- `YRP Work Order Deliverables.source_grn`
- `YRP Work Order Deliverables.source_grn_item`
- dynamic stock-dimension fields, including Received Type when configured;
- `fabric_reference_variant` and `fabric_reference_allocations` on WO input/output rows;
- `additional_parameters` for compact persisted execution metadata such as the fabric execution key;
- GRN/DC `ref_doctype`, `ref_docname`, quantities, UOM conversion and stock-dimension fields;
- `SD YRP GRN Deliverable` for valuation and exact consumption lineage.

No duplicate Item, source or execution-contract columns are added unless implementation proves that an existing field cannot preserve the reference-branch contract.

### `YRP Work Order` cutoff field

- `cloth_execution_version`: hidden, read-only, `no_copy` Int; `0`/unset for all pre-existing records and `1` for newly inserted WOs whose route is a candidate for this P0 flow. A new downstream candidate may be downgraded to `0` at its first calculation when all sources are legacy.

This is a server-owned contract version, not a user feature flag. It exists solely to make the new-transaction boundary deterministic without touching migrated data.

## Qualification and Isolation

Two helpers keep insert-time detection separate from runtime enforcement:

- the **route-candidate helper** reads only Lot/IPD/process facts and is used by `before_insert` to stamp a newly inserted candidate WO;
- the **full qualification helper** additionally requires the saved version and execution metadata and is used by every transaction hook/override.

A document fully qualifies only when:

1. it resolves to an `SD YRP Lot` and a cloth `YRP Item Production Detail`;
2. its process belongs to that IPD's fabric route;
3. its IPD route is the exact supported three-stage sequence defined below;
4. DC/GRN documents resolve through their referenced Work Order;
5. its Work Order has `cloth_execution_version == 1` and its transaction rows carry the new `fabric_execution_key`, except while that new versioned draft WO calculation is creating the key;
6. the transaction is not a garment, cutting, finishing, packing, rework, return or unrelated stock flow.

Every new hook or override starts with this qualification. Unqualified documents immediately return to the existing implementation. Existing hook handlers are appended, not replaced or reordered. Existing method signatures remain stable.

Version boundaries are closed in both directions: a version-`0` WO rejects keyed source rows, and a version-`1` WO rejects mixed keyed/unkeyed rows. A newly inserted version-`1` Dyeing/Washing candidate with only unkeyed sources is atomically downgraded to `0` only on its first successful calculation, before legacy output is written, and can never later upgrade. Any later recalculation of a still-version-`1` WO with unkeyed sources is rejected rather than downgraded.

### Process-role resolution

- **Default Knitting** is step 0 and means the `YRP Process` stored in `SD YRP IPD Settings.default_knitting_process`.
- **Dyeing** is step 1 and is the immediately following normalized fabric step. Its Process shape must change `Colour`, or it must equal `SD YRP IPD Settings.default_dyeing_process` when legacy shape metadata is incomplete.
- **Washing** is step 2 and is the one immediately following Dyeing. It must be an identity cloth-process step. The exact `process_name` comes from that IPD route row; no English process-name string is hard-coded.
- A WO qualifies for version `1` only when `get_fabric_steps()` begins with exactly this contiguous Knitting -> Dyeing -> identity-Washing sequence. Any different, missing or intervening step keeps the WO on the legacy path.
- A Dia-changing step, including Compacting, is never part of the supported P0 segment. Later route steps may exist after Washing, but this phase stops projection at Washing and their transactions use the current legacy flow unchanged.
- An explicit Dia transform means a normalized process step whose Process `value_change_attributes` contains `Dia`, or whose IPD process-row Change mapping changes `Dia`. This phase does not execute such a step.

## Execution Flow

### 1. Knitting Work Order

- Existing Cloth Program and matrix calculation remains the demand authority.
- Default Knitting may consolidate colour routes that result in one physical output while preserving route/reference allocations.
- Manual yarn quantities, when used by the current calculation UI, are validated and saved as the execution contract.
- Calculation stores a stable fabric execution key in `additional_parameters` on paired input/output rows.
- Draft recalculation remains allowed until a submitted DC or GRN exists. Submitted Work Orders follow the current update-after-submit rules; once execution begins, their calculated fabric rows are immutable.

### 2. Knitting Delivery Challan

- Existing DC creation remains the entry path.
- Source rows carry their existing Work Order child reference and stock dimensions.
- DC submission remains the stock-allocation authority. Draft Work Orders do not reserve source quantities.
- Preserve the current Essdee same-warehouse DC/GRN override exactly as it behaves before this feature. P0 adds no new same-warehouse rule and does not tighten the existing one.

### 3. Knitting GRN and Actual Dia

- Desk displays physical receipt rows, not duplicated hidden colour-route rows.
- A user may keep the planned Dia or split a planned output across multiple Actual Dia Items.
- Actual Dia substitution is offered only because the next two normalized steps are the supported Dyeing and identity-Washing stages. A Knitting route without that supported continuation receives the planned Item through the legacy editor.
- Server validation resolves each Item through ERPNext Item attributes and permits only the Dia attribute to differ from the planned output. Parent item, colour and all other declared attributes must remain compatible.
- Actual quantities may be short, exact or excess subject to the existing Work Order/process receipt policy.
- Hidden route allocations are scaled to the physical quantity without multiplying physical stock.
- Identical physical Item + warehouse + UOM + stock-dimension receipts are grouped into one positive SLE while each GRN row keeps valuation lineage.

### 4. Lot conversion rebuild

- Before GRN lifecycle writes, lock affected Lots in stable name order.
- On submitted default-Knitting GRN submit/cancel, rebuild the complete conversion table from all currently submitted eligible, execution-keyed Knitting GRNs for that Lot/IPD. Historical unkeyed GRNs are ignored.
- Rebuild is idempotent and replaces server-owned rows atomically.
- Eligible physical quantities use `YRP Stock Settings.default_received_type` and exact stock dimensions. Other Received Types are not normal production sources in this phase and continue through the current inspection/rework behaviour.
- Planned-to-actual factors preserve fractional totals and short/exact/excess receipts.
- Project the Actual Dia through the supported Dyeing and Washing matrices only. Identity Washing carries Dia forward. Projection stops before the first Dia-changing or otherwise unsupported step.

### 5. Dyeing Work Order

- Source discovery uses submitted upstream GRN rows, not Item-level totals.
- One source bucket is keyed by exact source GRN row, Item, Received Type, warehouse, set combination and all configured stock dimensions.
- Fully consumed historical rows are hidden from selection.
- Draft Work Orders do not subtract availability. Submitted DC/actual stock movement does.
- Calculation projects the selected actual Knitting Item through the Dyeing route and stores exact source fields plus the execution key on calculated inputs.
- Submission/recalculation validation rejects stale, changed or over-allocated source contracts.

### 6. Dyeing DC and GRN

- DC validation rebuilds the source pool under row locks and consumes each exact source bucket.
- It rejects changed Item, Received Type, dimensions, lineage or quantity above the exact remaining balance.
- Multiple DC rows referencing one bucket are aggregated before validation.
- GRN uses saved WO execution inputs instead of recomputing ambiguous matrices.
- The output retains original Knitting planned/actual lineage and becomes the exact source for Washing.

### 7. Washing WO/DC/GRN

- Washing repeats the exact-source contract against submitted, keyed Dyeing GRNs from the immediately preceding route stage.
- Identity Washing carries Actual Dia through unchanged. A Washing step that changes Dia is outside this phase and stays on the current legacy path.
- DC locking, GRN physical aggregation, valuation and cancellation follow the same rules.

## Cancellation and Concurrency

- Lock order is deterministic: affected Lots, source GRN parents/rows, then target Work Order/DC/GRN documents as required by the current controllers.
- DC validation is repeated during submit while the relevant source rows are locked, preventing two DCs from both consuming the same balance.
- Cancelling a DC releases availability implicitly because only submitted movement is counted.
- Cancelling a source GRN is blocked when a submitted downstream DC/GRN consumes its physical source.
- Cancelling an unconsumed default-Knitting GRN rebuilds the Lot conversion table without that receipt.
- Sub-nanounit floating-point stock residues are normalized to zero before genuine negative-stock enforcement.

## Desk UI

### Lot

- Mount a read-only Actual Dia conversion summary in `actual_dia_conversion_html`.
- Show process, planned Item, actual Item, actual quantity, Received Type, UOM and source-GRN count.
- Users cannot edit the child table directly.

### Work Order

- Preserve the existing Calculate and cloth selection UI.
- Add source labels/details only inside the qualifying cloth calculation result.
- Show enough exact source information to distinguish otherwise identical Items.
- Do not change fields/buttons for unqualified Work Orders.

### Goods Received Note

- For qualifying default-Knitting GRNs, allow Actual Dia item selection and physical-row splitting.
- Group hidden route rows for display and Received Type editing.
- Do not cap qualifying physical receipt input at hidden route pending quantity; the server remains authoritative.
- Dyeing/Washing show their inherited physical Item and exact source context without enabling arbitrary attribute substitution.

No `/web` components, routes or frontend engine changes are part of this phase.

## Base YRP Changes

Only generic corrections proven necessary by the reference flow are included:

1. group production GRN positive receipts by physical Item and all stock dimensions while preserving row-to-SLE lineage;
2. support Desk GRN physical-row aggregation and excess entry only when the Essdee qualification helper marks the Work Order GRN as a new keyed cloth execution; ordinary base editors remain unchanged;
3. normalize only absolute stock residues below `1e-9` to zero before negative-stock rejection. This generic numerical correction is the sole allowed behaviour change outside qualifying cloth transactions.

The current Essdee same-warehouse override is baseline behaviour and remains untouched. Physical SLE grouping is activated only for a qualifying versioned cloth transaction through the Essdee controller boundary; generic garment/PO/other Work Order GRN SLE shape remains unchanged. These changes require focused base-YRP regression tests, and generic base helpers must not import Essdee doctypes.

## Error Handling

Errors must identify the document and failing physical source. The following fail closed:

- missing or cancelled source GRN row;
- Item or attribute mismatch other than permitted Knitting Dia substitution;
- Received Type, warehouse, set combination or stock-dimension mismatch;
- requested quantity above the locked exact-source balance;
- duplicate/ambiguous route identity;
- recalculation after execution has begun;
- cancellation of an upstream receipt already consumed downstream;
- actual-dia rows whose physical total or route allocations do not reconcile within `QTY_TOLERANCE = 0.000001` stock units.

Validation errors occur before stock or valuation side effects. Lifecycle writers are idempotent so a retry cannot duplicate conversion or valuation rows.

## Testing Strategy

### Pre-change baseline

Run the existing current-branch tests covering Cloth Program, Work Order calculation, fabric source, GRN valuation, DC/GRN controllers, cutting, finishing, packing and rework. Record failures already present in the dirty worktree separately; new changes may not add failures.

### Unit and contract tests

- route/process qualification returns false for every excluded flow;
- planned-to-actual quantity allocation preserves fractional totals;
- Actual Dia factor calculation handles short, exact, excess and split receipts;
- conversion rebuild aggregates multiple submitted GRNs idempotently;
- conversion cancel/rebuild removes only cancelled sources;
- actual attributes carry through Dyeing and Washing correctly;
- source bucket keys differ for source GRN row, Received Type or any stock dimension;
- a physical source row cannot be reused across incompatible routes;
- existing fabric-reference allocation readers return unchanged totals.

### Work Order tests

- existing Cloth Program and Work Order outputs stay unchanged without a substitution;
- default Knitting consolidates one physical output without losing route allocations;
- saved/manual yarn quantities survive reopen and scale for a partial GRN;
- Dyeing selects the correct actual Knitting Item and exact GRN row;
- Washing selects the correct Dyeing GRN row;
- draft WOs do not reserve; actual submitted use is deducted;
- stale/relabelled/forged source contracts are rejected;
- recalculation after transaction start is rejected;
- garment, cutting, sewing, finishing, packing and rework Work Orders remain unchanged.
- an in-flight pre-deployment Lot whose rows have no execution key stays completely on the legacy path.
- an existing blank-version draft WO remains legacy when recalculated; a newly inserted qualifying WO receives version `1` and execution keys.
- Dyeing/Washing calculation rejects a mixture of keyed and unkeyed upstream sources.
- a new downstream candidate with only legacy sources downgrades to version `0` and produces byte-identical legacy output.
- a legacy version-`0` WO rejects a keyed source; it cannot bypass exact-source locking.
- after its first calculation, a version-`1` WO rejects an all-unkeyed recalculation instead of silently downgrading.

### Delivery Challan tests

- exact source partial dispatch succeeds;
- aggregate dispatch equal to availability succeeds;
- over-dispatch fails;
- changed Item, Received Type or dimension fails;
- multiple partial DCs share the current locked counter;
- cancelling a DC restores availability;
- concurrent submissions exceeding one bucket allow at most the valid total;
- current Essdee same-warehouse DC/GRN tests remain unchanged and passing.
- PO and garment DC/GRN stock movement and positive-SLE shape remain byte-for-byte unchanged.

### GRN and valuation tests

- unchanged Dia receipt;
- one changed Actual Dia;
- multiple split Actual Dias;
- changed colour, parent Item, extra attribute or missing declared attribute is rejected even when Dia is valid;
- short, exact and excess physical quantities;
- Received Type split produces physical rows without multiplying hidden routes;
- one positive SLE per physical Item/dimension combination;
- consumption rows stay separate by exact Work Order input;
- total material value is conserved across splits;
- submit/cancel reverses the saved physical shape without recalculation;
- Dyeing and Washing retain exact Knitting lineage;
- upstream cancellation is blocked after downstream consumption;
- non-fabric GRNs still run all existing base and Essdee guards.

### Desk tests

- Use Node tests for pure Desk row-grouping/Actual Dia editor behaviour and Playwright, via the existing `/home/anas/.claude/playwright` harness, for the browser smoke flow on `erp-migration-test.site`.
- Lot conversion component renders read-only current rows;
- Knitting GRN editor creates, edits and removes physical Actual Dia splits;
- hidden route rows aggregate without quantity loss;
- server errors are shown without mutating the saved document;
- no new controls appear for non-qualifying documents.
- migrated/pre-deployment unkeyed documents show no new execution controls.

### Full end-to-end smoke flow

On the target test site, create new test records and execute:

1. build/recalculate Cloth Program;
2. create and calculate Knitting WO;
3. submit Knitting DC;
4. submit Knitting GRN with split Actual Dias;
5. verify Lot conversion rows and stock/SLE totals;
6. create Dyeing WO from one exact physical source;
7. submit partial Dyeing DC and verify over-dispatch rejection;
8. submit Dyeing GRN and verify lineage/valuation;
9. create Washing WO from the exact Dyeing receipt;
10. submit Washing DC and GRN;
11. verify final stock, valuation, pending quantities and Lot lineage;
12. verify cancellation behaviour on an unconsumed branch;
13. rerun current Cloth Program/WO and excluded-flow regressions.

## Rollout and Rollback

- Implement in small tested units: schema, pure conversion logic, source buckets, WO integration, DC validation, GRN lifecycle, Desk UI, base-YRP corrections.
- Apply schema changes to `erp-migration-test.site` only after automated tests for the preceding unit pass.
- Pilot with newly created test Lots; no historical documents are modified.
- A code rollback removes the new hooks/UI while leaving the additive child schema harmless. Transactional rebuilds prevent partially written Lot conversion state.

## Review Decisions

The Opus 5.5 architecture review reinforced strict hook gates, immutable execution metadata, row locking, cancellation checks and complete regression/concurrency coverage. It also suggested extra enablement, bucket and execution-contract fields. Those extra fields are intentionally omitted because the reference implementation already proves the contract using existing source fields, stock dimensions, `fabric_reference_allocations` and `additional_parameters`. The implementation plan may add a field only if a failing test demonstrates that the existing contract cannot safely represent the required state.
