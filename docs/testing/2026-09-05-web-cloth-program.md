# /web Cloth Program and Fill Quantity verification

Verified on `yrp-test.site:8004`, Premium White layout. Code changes are confined
to `essdee_yrp` on `develop`; no commit, push, PR, or Work Order submission.

## Implemented

- Lot's **Cloth Program** tab reads the saved program through the same explicit
  endpoint used by Desk, including after Build Cloth Programs. Display uses the
  finished Colour/Dia; edits retain the physical output attributes and reference.
- The tab shows loading/failure/retry states. A failed program read never sends
  an empty replacement program during a Lot edit/save.
- Work Order's Calculate Deliverables popup offers **Fill Quantity**, with
  source options supplied by the configured IPD process order. The exact source
  step is passed to both the reader and Calculate endpoint.
- Failed fills preserve existing edits and the previously successful source.
  Late/obsolete requests cannot replace current popup data.
- Shared input availability is labelled and starts at zero for manual allocation.
- No receipt tracking or Recalculate Received action on the Lot. Return GRNs
  remain excluded by the existing backend API.

## Automated checks

All passed:

```sh
cd frontend
node --test tests/*.test.js       # 20 tests
npm run build
```

```sh
bench --site yrp-test.site run-tests --app essdee_yrp --module essdee_yrp.test_fabric_source
# 6 tests, including real transaction SQL for submitted receipts, returns and reservations
bench --site yrp-test.site run-tests --app essdee_yrp --module essdee_yrp.api.test_work_order
# 20 tests
bench --site yrp-test.site run-tests --app essdee_yrp --module essdee_yrp.api.test_cloth_program
# 59 tests
```

The build has the existing Vite large-chunk advisory; no build failure.

## Browser data entry against real test-site records

1. `GY0726-89`: rebuilt all four cloths through `/web` with **5% excess**.
   Existing IPD links and program quantities stayed the same. On completion,
   the Cloth Program tab was selected and all four grids loaded automatically.

   | Cloth | Saved program and popup total, kg |
   | --- | ---: |
   | Dyed Fabric 36's RL | 2824 |
   | 30's GL Dyed Fabric | 120 |
   | 34's Grey Melange Fabric | 70 |
   | 30's Andhra Melange Fabric | 499 |

2. Checked every quantity input for the four knitting cloths against its server
   context: 30, 6, 3 and 5 quantity rows respectively. This includes dyed-yarn
   Red/Black, greige inputs for later dyeing, and greige yarn whose output already
   has its finished melange colour. No physical Greige column substitutes for the
   finished colours in the entry grid.
3. Created draft **YRP-WO-2026-00024** through the `/web` Duplicate/Save flow,
   then used Calculate: 3 yarn deliverables and 18 physical cloth receivables,
   both totalling 2824 kg. Left **unsubmitted** for manual verification.
4. **YRP-WO-2026-00020**, Washing, test Lot `FFLOW-20260905-01`: selected Dyeing
   in Fill Quantity. Its submitted receipt filled **Grey / 34 Dia / 5 kg**.
   Edited to 4 kg, selected an unavailable Knitting source, and confirmed the
   error preserved the 4 kg edit and Dyeing source. Tried 6 kg: backend rejected
   it and the draft still had no saved deliverables. Calculating 4 kg then saved
   one correct input/output pair plus `Dyeing` / `1::Dyeing` source metadata.
   Reopened and refilled: received 5 kg, not 1 kg (current WO excluded from its
   own reservation). Calculated again and left this existing test draft at
   **5 kg, unsubmitted**. The Lot program was unchanged by WO calculation.
5. **YRP-WO-2026-00017**, Dyeing: Fill Quantity from Knitting showed actual
   shared Greige capacities of 1.725, 0.784 and 0.740 kg for the relevant dias.
   Grey/Maroon/Navy input fields stayed at zero, with a shared-allocation note;
   incompatible Red/Black receipts were listed as ignored. Closed without saving.
6. Test Lot `FFLOW-20260905-01`: removed only the program key from the browser's
   onload response to simulate cached/omitted onload data. Explicit program read
   still populated the editor. Changed 5 to 6 kg through the UI and saved; the
   reference and physical attributes were preserved. Restored **5 kg** through
   the UI afterward.
7. Injected a browser-only program-read failure (HTTP 503), confirmed the visible
   error instead of a misleading empty grid, then restored the transport and
   used Retry: the saved program returned. This was a simulated network failure,
   not a database outage.
8. Checked desktop and 390 px viewport layouts: no document-level horizontal
   overflow; the Lot matrix scrolls inside its container and popup actions fit.

No DC/GRN submissions were needed in this UI pass: existing submitted receipts
from the earlier workflow test were used. Core `/apps/yrp` was not modified.
