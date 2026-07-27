# Apparelo vs essdee_yrp — Knitting-to-Packing Production Review

**Date:** 2026-07-25
**Systems reviewed:**

- Frappe 13: `apparelo` on `/home/anas/frappe-13`, site `apparelo.site`
- Frappe 16: `yrp` + `essdee_yrp` on `/home/anas/frappe-16`, site `essdee_yrp.site`

## Executive verdict

**Keep `essdee_yrp` as the production and calculation engine. Do not replace it
with Apparelo.**

Apparelo is better at expressing familiar garment-process inputs because it has
a dedicated DocType for each supported operation. That is the useful part to
borrow. Its backend, however, is a hard-coded Item Variant/BOM generator tied to
specific process names and Frappe/ERPNext 13 internals. It does not cover the
full requested route, does not implement Apparelo Washing despite listing it as
a final process, has no Embroidery process, and the inspected Compacting and
Steaming generation does not apply the configured output Dia.

`essdee_yrp` has the stronger long-term model:

- one configurable `Process` master;
- one generic, ratio-aware `IPD Process Matrix` contract;
- exact attribute/reference routing;
- the same calculation contract for Lot and Work Order;
- deliverable/receivable tracking through Delivery Challan and Goods Received
  Note;
- cost, stock, rework, close, correction, approval, and audit support;
- live configured processes covering the complete requested route;
- one shared web implementation that can be presented through multiple layouts.

The right target is therefore:

> **Apparelo-style guided process forms and defaults, compiled into the existing
> essdee_yrp Process/IPD Matrix engine.**

The manager is right that Apparelo contains valuable process-domain defaults.
The statement that “only its UI is the problem” is not correct for the revision
reviewed here; there are material backend limitations as well.

## Evidence and review boundary

This was a static code review plus read-only inspection of both sites. No
production transaction was created or modified.

The Apparelo repository's latest commit is dated 2020-06-30. The restored
`apparelo.site` has three Item Production Details, all Draft, and returned no
Lot Creation, DC, or GRN rows. Therefore its end-to-end behavior could be traced
from code, but not validated against completed transactions on that site.

The `essdee_yrp.site` inspection returned:

- 453 Item Production Details;
- 1,780 Lots;
- 25 current custom Work Orders;
- live Process masters for Knitting, Dyeing, Compacting, Re-Compacting,
  Washing, Cutting, several Fusing operations, Printing, Embroidery, Stitching,
  Ironing, Packing, and grouped operations.

The F16 worktrees also contain active, uncommitted feature work. New
Build-Cloth-Program and multi-yarn behavior must be completed and regression
tested before being described as production-ready.

## Architecture comparison

### Apparelo

```text
Item Production Detail
  -> linked dedicated process records
     (Knitting, Dyeing, Cutting, Stitching, ...)
  -> background submission
  -> create intermediate Item templates and variants
  -> create and submit ERPNext BOMs
  -> persist IPD Item/BOM mappings
  -> Lot Creation explodes BOMs
  -> Material Requests
  -> DC creates subcontract Purchase Order + raw-material Stock Entry
  -> GRN creates Purchase Receipt
```

This is a **materialized routing** model: approving an IPD creates large amounts
of permanent ERPNext master data.

### essdee_yrp

```text
Item Production Detail
  -> ordered Process rows
  -> IPD Process Matrices + accessory Item BOM rules
  -> Lot variant demand
  -> generic matrix engine / fabric backward solver
  -> per-process Work Order deliverables and receivables
  -> Delivery Challan / Goods Received Note
  -> stock, cost, received balance, rework, close and billing tracking
```

This is a **declarative routing** model: matrices retain process ratios and
attribute transformations, and Lot/Work Order demand is scaled when needed.

## Stage-by-stage findings

| Stage | Apparelo | essdee_yrp | Finding |
|---|---|---|---|
| Knitting | Dedicated Knitting record with Type, Dias, input/output ratio; creates Knitted Cloth variants and one-material BOMs. An IPD process row has one `input_item`. | Item-conversion matrix; can produce exact Dia/Colour reference routes and multiple input rows/ratios; Lot Build Cloth Program can be the guided entry point. | Apparelo is simpler for a basic one-yarn recipe. essdee's matrix is required for colour-wise multi-yarn ratios and exact routing. |
| Dyeing | Dedicated colour list; expands colours across inherited input variants. | Colour-change mappings can be pinned by Dia and resolved against exact reference variants. | Apparelo naturally produces a broad cross-product. essdee is safer for “this Dia/colour only” requirements. |
| Compacting / Steaming | Dedicated `from_dia`/`to_dia` table and input/output ratio. In the inspected code, `to_dia` is never used while building output variants/BOMs; output variants copy input attributes. | Dia-change mappings, optionally pinned by Colour; Re-Compacting is another configured step using the same contract. F16-only compacting reference data may remain informational. | Apparelo's form is good, but its inspected output-Dia behavior is incorrect/incomplete. |
| Washing | Listed as an IPD final-process choice, but there is no Washing DocType or execution branch. | Configured as an identity process; input and output can remain the same variant, with Work Order tracking. | essdee wins. |
| Cutting | Strong dedicated model: Part × Size maps to Dia/Weight, and Part maps to Colour/Style; produces cut variants/BOMs. | Panel-wise consumption matrix supports exact Primary Attribute × Panel × Colour rows with per-row Dia and kg/piece, then expands to canonical Cutting rows/matrices. | Apparelo is an excellent UI reference. Its separate mappings imply the same Dia for every colour of a Part/Size; essdee can represent colour-specific Dia. |
| Fusing | Dedicated Label Fusing plus additional-part colour/size mappings. | Any configured Fusing Process, including several live Fusing masters; accessory and major-item rules remain process-linked. | Apparelo has a useful specific form; essdee has broader routing coverage. |
| Printing | Dedicated Piece Printing and Roll Printing. | Live Printing/Pocket Printing masters; handled through the same Process and matrix/accessory contracts. | Apparelo gives clearer terminology; essdee is more extensible. |
| Embroidery | No dedicated process and no branch in IPD generation. | Live Embroidery Process; can use identity or configured transformation plus accessories. | essdee wins. |
| Stitching | Dedicated part count, piece-to-part colour mapping, and additional part colour/size rules. | Stitching combination records panel counts and colour routing; accessory combinations feed Item BOM rules; matrices calculate panel inputs and piece outputs. | Apparelo's input form is strong. essdee's downstream contract is stronger and supports exact panel references. |
| Checking / Ironing | Dedicated operations producing stage-specific intermediate variants. | Identity/group processes with the same Work Order tracking; live Checking and Ironing masters. | Comparable behavior; essdee avoids mandatory new template families. |
| Packing | Dedicated ratio/combo logic, additional parts, combined-IPD packing. | Size Ratio and Size Wise packing, assortment rules, grouped `Includes Packing` processes, and matrix-backed Work Order output. | Both are capable. essdee is better integrated with the current Lot/WO lifecycle. |

## Detailed strengths

### What Apparelo does well

1. **The user's vocabulary is visible.** Knitting asks for Dia and Type;
   Compacting asks for Dia conversion; Cutting asks for Parts, Sizes, Dias and
   weights; Stitching asks for part counts and colour mapping.
2. **It uses standard ERPNext manufacturing and subcontract documents.**
   Intermediate variants and submitted BOMs are understandable to ERPNext's
   Production Plan, Material Request, Purchase Order, Stock Entry and Purchase
   Receipt logic.
3. **The Cutting and Stitching models capture important garment rules.**
   Combined parts, panel counts, panel colours, sizes, styles and extra
   components are first-class inputs.
4. **There is process-specific test coverage.** Most dedicated DocTypes have a
   corresponding test module.
5. **It is a useful requirements catalogue.** The dedicated schemas show what
   an operator expects to enter for each operation.

### What Apparelo does poorly

1. **The process dispatcher is hard-coded.** `create_process_details` contains
   explicit branches for particular process names. A new operation requires a
   new DocType, Python generator, installation wiring, and dispatcher changes.
2. **Coverage is incomplete.** There is no Embroidery DocType. Washing is
   offered in the final-process Select but has no process implementation.
3. **The Dia conversion implementation is suspect.** Compacting and Steaming
   read `from_dia` but do not use `to_dia` when creating output variants or BOM
   matches.
4. **Complex routing is stored as strings.** `input_index` and
   `ipd_process_index` are comma-delimited index lists. This is a weak process
   graph and is difficult to validate, refactor, or inspect.
5. **It causes variant/BOM explosion.** IPD submission creates and submits
   intermediate Item templates, variants and BOMs for combinations. Editing a
   route can collide with an existing active BOM and requires master-data
   cleanup.
6. **Its “generic” common branch is only signature reuse.** The common
   Dyeing/Roll Printing/Bleaching/Ironing/Checking/Packing path still assumes
   every process DocType implements matching `create_variants` and
   `create_boms` methods.
7. **The IPD UI is fragmented.** The IPD contains a table of Dynamic Links to
   separate process records. Users must create, open, fill and submit several
   documents before submitting the IPD.
8. **Installation changes global ERPNext behavior.** It clears Stock Settings'
   default stock UOM and creates global item attributes, templates, warehouse
   types and custom fields.
9. **The reviewed branch is old and tied to ERPNext 13 internal APIs.** It
   cannot be safely copied into F16 without a rewrite.

## essdee_yrp strengths

1. **One calculation contract.** `IPD Process Matrix` groups declare inputs,
   outputs, ratios, UOMs, wastage and attributes. The same rows drive Lot
   requirements and Work Order calculation.
2. **Process behavior is metadata-driven.** A Process declares item conversion,
   changed attributes, input/output UOM, wastage, excess, lead time and optional
   sub-processes. Adding a normal identity process does not require a new
   Python DocType.
3. **Exact routing is representable.** Reference variants plus combination
   attributes can distinguish Size, Panel, Colour and Dia instead of relying on
   broad cross-products.
4. **Fabric demand is solved backward.** Finished Dia/Colour kg can be traced
   backward through Compacting, Dyeing and Knitting to source requirements.
5. **Work Order is a real operational aggregate.** It owns calculated and
   manual deliverables, receivables, pending quantities, process cost, supplier,
   dates, stock movement, status, corrections, rework and closing controls.
6. **Actual receipts feed the plan.** Goods Received Note events update
   process/Dia/Colour/reference ledgers used by later Work Orders.
7. **Approval is reversible and role-controlled.** IPD supports Not Approved,
   Cutting Approved and Approved, with explicit approve and revert methods.
8. **UI logic is reusable across layouts.** Default, Lot Workbench and Premium
   White use the same Vue detail components and server contracts, reducing
   calculation drift between presentations.
9. **It covers the requested live route.** All requested process names exist on
   `essdee_yrp.site`, including Washing and Embroidery.

## essdee_yrp weaknesses

1. **The generic engine is harder for operators to understand.** A matrix is a
   good execution contract but a poor raw data-entry form for most production
   users.
2. **Process-specific defaults are incomplete.** The system has basic IPD
   Settings defaults for Cutting, Stitching and Packing, but does not yet offer
   a complete template/wizard for every stage.
3. **Some garment behavior still lives in legacy custom tabs/JSON.** Cutting,
   stitching and packing data are adapted into the generic model instead of
   being authored in one uniform schema.
4. **The engine has more moving parts.** Exact references, backward planning,
   matrices, child-row item overrides and identity processes require strong
   validation and regression tests.
5. **Current feature work is unfinished.** Multi-yarn Build Cloth Program
   changes in the working tree must not be treated as complete until Desk/web
   parity, the three target layouts, migration, and end-to-end tests pass.

## Decision matrix

| Criterion | Better choice | Reason |
|---|---|---|
| Basic process-specific data entry | Apparelo | Dedicated fields match operator terminology. |
| Full requested process coverage | essdee_yrp | Apparelo lacks executable Washing and Embroidery. |
| Colour/panel-specific Dia and consumption | essdee_yrp | Exact matrix rows avoid Apparelo's Cartesian assumptions. |
| Multi-yarn and ratio extensibility | essdee_yrp | Multiple matrix input rows are a first-class representation. |
| New process extensibility | essdee_yrp | Process metadata instead of a Python branch per name. |
| Standard ERPNext BOM/MR lineage | Apparelo | It materializes standard BOMs and uses Production Plan/MR directly. |
| Subcontract operational control | essdee_yrp | Current custom WO/DC/GRN flow includes balances, costs, corrections, rework and close controls. |
| Maintainability on Frappe 16 | essdee_yrp | Current platform and active codebase. |
| Current-site evidence | essdee_yrp | Substantial live records versus three Draft IPDs on the restored Apparelo site. |
| Best future system | essdee_yrp + Apparelo UX ideas | Preserve one engine while adding guided process adapters. |

## Recommended target design

Do not port Apparelo's `create_process_details` dispatcher or its process
DocTypes as a parallel backend. Introduce **Process Entry Templates** on top of
the existing essdee model:

1. A template identifies a Process and UI kind, such as:
   `KnittingRecipe`, `ColourChange`, `DiaChange`, `Identity`, `PanelCutting`,
   `PanelAssembly`, `AccessoryApplication`, or `PackingAssortment`.
2. The template stores defaults and validations: UOMs, ratio, wastage, required
   attributes, allowed item roles, and operator help.
3. A guided form captures process-language inputs.
4. A deterministic adapter compiles those inputs to canonical
   `IPD Process Matrix`, `IPD Process`, and `Item BOM` rows.
5. Lot and Work Order calculations continue to read only the canonical rows.

Suggested guided views:

- **Fabric route:** yarn recipe → knitting Dia → dyeing colour/Dia →
  compacting Dia → washing.
- **Panel route:** Size/Panel/Colour matrix with Dia and kg/piece.
- **Assembly route:** panel count and panel colour mapping, followed by Fusing,
  Printing, Embroidery and Stitching accessories.
- **Finishing route:** checking, ironing and packing assortment.

This keeps the operator experience that makes Apparelo attractive without
creating a second calculation engine.

## Implementation sequence

1. Finish and regression-test the current panel matrix and Build Cloth Program
   ownership model.
2. Define golden examples covering:
   - one yarn;
   - two/three yarn ratios by colour;
   - colour-specific panel Dia;
   - panel count greater than one;
   - Washing identity;
   - Fusing, Printing and Embroidery accessories;
   - ratio packing and size-wise packing.
3. Add Process Entry Template metadata and compiler contracts.
4. Implement the four guided views above in the shared Vue components; Desk
   should call the same server methods.
5. Verify Default, Lot Workbench and Premium White against the same golden
   documents.
6. Test the complete lifecycle:
   IPD → Lot → calculated WO → Delivery Challan → Goods Received Note → stock
   and balance → close/rework.
7. If standard ERPNext BOM visibility is required by management, generate a
   read-only/exported BOM representation from approved matrices. Do not make
   permanent variant/BOM generation the primary routing engine.

## Final recommendation

**Choose essdee_yrp for the real system. Use Apparelo as a domain-design
reference, not as the backend to migrate.**

Apparelo demonstrates how process entry should feel. essdee_yrp provides the
better foundation for the actual requirements: multi-yarn, colour/panel-specific
Dia, complete process coverage, exact Lot calculation, and controlled Work
Order execution.
