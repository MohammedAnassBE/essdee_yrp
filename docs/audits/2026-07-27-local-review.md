# SD YRP local review — 2026-07-27

## Scope

- Re-reviewed the SD YRP web/API audit dated 2026-07-16.
- Checked the active YRP UI vocabulary, generated schema, local layout files,
  imported UI Layout records, desktop rendering, mobile rendering, and a
  restricted floor-user rendering.
- Preserved the existing cloth-program, IPD process-matrix, Work Order,
  Delivery Challan, GRN, Stock Entry, and print-format behavior.
- No commit or push was made in this review pass.

## Corrected findings

- Serialized tuple-form list filters before calling Frappe's previous/next API.
- Prevented the Lot IPD picker from querying before an Item is selected.
- Restored Item Group and UOM legal-subset filters in the web Item editor.
- Routed controller-sensitive Item bulk edits through `doc.save()`.
- Rejected cross-attribute Item Attribute Value reuse and made duplicate
  creation races resolve against a locking current read.
- Removed the database write from Lot `onload`.
- Added stale-write guards to BOM, process-matrix, inline IPD, and bulk
  submit/cancel edits.
- Preserved all grouped-entry fields through the stock pivot editor.
- Enforced child-mapping and parent-field permission levels in the web UI.
- Permission-gated SMS, WhatsApp, and e-Waybill mutations.
- Corrected local-date prefill in the e-Waybill modal.
- Exposed the existing internal-unit GRN completion flow in the web UI without
  weakening its server-side permission check.
- Added 15 regression-contract tests for these seams.

## UI gaps and layout integrity

- Regenerated `custom ui/catalog/LAYOUT_SCHEMA.json` from the active
  vocabulary. The schema now includes `build_cloth_programs` and
  `complete_transfer`.
- Corrected the catalog: `hoverCard` is not currently a supported layout knob.
- Replaced the unsupported Loomline Lot hover-card declaration with a supported
  `cardTemplate`.
- Browser review found the first two-column card version too dense. The final
  Lot card uses a short vertical hierarchy: Lot, Item, IPD, and Order Qty.
- Added `complete_transfer` to explicit action filters where required.
- Updated Lot Workbench home recents and quick-create configuration without
  enabling creation for catalog entries marked `noCreate`.
- Imported only the changed existing records; their enabled state and all user
  assignments were preserved.

## Verification

- `bench --site essdee_yrp.site run-tests --app essdee_yrp`: **113/113 passed**.
- YRP UI config tests: **297/297 passed**.
- YRP UI metrics tests: **22/22 passed**.
- YRP UI fleet tests: **16/16 passed**.
- Production frontend build: **passed**, 504 modules transformed.
- Python compile check: **passed**.
- Generated layout schema check: **passed**.
- Six authored layouts and three templates: **0 warnings, 0 hard errors**.
- Lot Workbench desktop: **6/6 screenshots**, no console/page errors.
- Lot Workbench mobile as the restricted floor user: **6/6 screenshots**, no
  console/page errors.
- Trial Loomline desktop: **6/6 screenshots**, no console/page errors.
- Trial Loomline Lot cards: direct browser check after the density correction,
  no console/page errors.
- `git diff --check` passed in both SD YRP and YRP.

## Deliberately not changed

- The broader UI-gaps document remains a roadmap, not a promise that every
  proposed component already exists. Unsupported grammar was not invented or
  silently accepted.
- E-Waybill field metadata / log-role policy and other DocType-field decisions
  remain deferred, matching the instruction to discuss fields separately.
- Base-YRP concurrency and endpoint-policy findings outside the Essdee-owned
  surfaces were not broadened into this local compatibility pass.
