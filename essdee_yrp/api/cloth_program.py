# Copyright (c) 2026, anas@essdee.fit and contributors
# For license information, please see license.txt
"""SD Lot -> Cloth Program (CPD) auto-builder.

ONE whitelisted orchestrator (`build_cloth_programs`) runs Phases 2-4:
  2. find-or-create the cloth Item's CPD (Item Production Detail, is_cloth_item=1),
     stamp yarn + processes + cloth_per_kg_yarn, ADDITIVELY seed (union-merge —
     shared cloths keep sibling lots' rows) knitting_dia_details from the demanded
     dias and dyeing_colour_details {dia, greige->demanded colour} from the
     demanded (dia,colour) tuples, auto-approve, and save() (matrices auto-rebuild
     via fabric_ipd.sync_fabric_process_matrices).
  3. attach a Lot Fabric Detail row (cloth_item + CPD) if absent.
  4. write the Lot's transient fabric_requirement_details JSON and lot.save() so
     save_fabric_requirement_details (before_validate) writes lot_fabric_requirements
     and rebuild_plans_after_save (on_update) runs the Phase-5 solver.

Reachability invariant: because the CPD's dyeing to_colours and knitting dias are
seeded from the SAME Phase-1 tuples, final_combos(CPD) contains every requirement
combo -> save_fabric_requirement_details never throws "No chain path produces".
Because compute_cloth_demand ALWAYS emits a real colour (panel/packing colour),
a colour-bearing cloth REQUIRES a dyeing_process + greige_colour so the Colour
attribute actually enters the chain; the orchestrator guards this up front and
throws a clear message rather than letting Phase 4 fail opaquely.
"""

import frappe
from frappe import _
from frappe.utils import flt

from essdee_yrp.api.work_order import _guard_not_modified
from essdee_yrp.fabric_program import get_greige_colour
from essdee_yrp.fabric_requirement import compute_cloth_demand


def _find_or_create_cpd(cloth_item, selection, tuples):
    """Phase 2. selection: {yarn_item, knitting_process, dyeing_process,
    compacting_process, cloth_per_kg_yarn, greige_colour}. tuples: {(dia,colour): kg}.
    Returns the CPD (Item Production Detail) name.

    Seeding is ADDITIVE: 50/81 cloth Items on essdee_yrp.site are shared across
    multiple garment styles (probe 2026-07-21: Lycra Rib by 24 garment items;
    40's GL Dyed Fabric New by 7) — wholesale replace would delete sibling lots'
    demanded rows and break their already-written requirements."""
    name = frappe.db.get_value(
        "Item Production Detail", {"item": cloth_item, "is_cloth_item": 1}, "name")
    cpd = frappe.get_doc("Item Production Detail", name) if name \
        else frappe.new_doc("Item Production Detail")
    cpd.item = cloth_item
    # Item Production Detail.is_cloth_item is `fetch_from: item.is_cloth_item`
    # with fetch_if_empty=0 -> Document._validate_links() (which runs BEFORE the
    # doctype's validate hook, see frappe/model/document.py insert()/save())
    # unconditionally re-pulls it from the linked Item on every save, silently
    # discarding the `cpd.is_cloth_item = 1` set below. Live data: only 3 dummy
    # test Items (TT-CLOTH/TT-CLOTH-CC/FT-CLOTH) carry Item.is_cloth_item=1 on
    # essdee_yrp.site — every real cloth Item (e.g. Polyester Velour Fabric) is
    # 0, which would flip the freshly-created CPD back to a GARMENT IPD and
    # crash in ipd_validations.validate_garment_ipd (e.g. "Enter stiching
    # attribute details"). The Item master is the source of truth the fetch
    # reads from, so it must be stamped here too, not just the CPD field.
    if not frappe.db.get_value("Item", cloth_item, "is_cloth_item"):
        frappe.db.set_value("Item", cloth_item, "is_cloth_item", 1)
    cpd.is_cloth_item = 1
    cpd.yarn_item = selection.get("yarn_item")
    cpd.cloth_per_kg_yarn = flt(selection.get("cloth_per_kg_yarn"))
    cpd.knitting_process = selection.get("knitting_process")
    cpd.dyeing_process = selection.get("dyeing_process")
    cpd.compacting_process = selection.get("compacting_process")

    greige = selection.get("greige_colour")
    dias = list(dict.fromkeys(dia for (dia, colour) in tuples))
    have_dias = {r.dia for r in (cpd.get("knitting_dia_details") or [])}
    for d in dias:
        if d not in have_dias:
            cpd.append("knitting_dia_details", {"dia": d})

    if cpd.dyeing_process:
        have_dye = {(r.dia, r.from_colour, r.to_colour)
                    for r in (cpd.get("dyeing_colour_details") or [])}
        for (dia, colour) in tuples:
            if not colour:
                continue
            key = (dia, greige, colour)
            if key in have_dye:
                continue
            have_dye.add(key)
            cpd.append("dyeing_colour_details",
                       {"dia": dia, "from_colour": greige, "to_colour": colour})

    # compacting_dia_details are NOT auto-seeded in v1: the demand model does not
    # change dia across compacting. Two sub-cases: (1) with an identity/unmaintained
    # compacting Process master, the mapping-less compacting row is skipped by
    # build_fabric_matrix (a no-op) and final_combos stays driven purely by
    # knitting dias x dyeing to_colours; (2) when the compacting Process MASTER
    # declares a Dia value-change shape, the mapping-less compacting row still
    # enters get_fabric_steps as the LAST step with no matrix, so final_combos
    # falls back to the walked-chain cross product dias x (to_colours + greige) —
    # a SUPERSET of demand, so reachability is still safe. compacting_process is
    # still stamped on the CPD so the intended process is recorded (surfaced to the
    # operator in both UIs as "recorded, not auto-chained in v1").

    cpd.approval_status = "Approved"  # base field is UI-read_only; set server-side
    cpd.save(ignore_permissions=True)
    return cpd.name


def _ensure_lot_fabric_detail(lot_doc, cloth_item, cpd_name):
    """Phase 3. One row per cloth (validate_unique_fabric_cloths); find-or-append."""
    for row in lot_doc.get("lot_fabric_details") or []:
        if row.cloth_item == cloth_item:
            row.production_detail = cpd_name
            return
    lot_doc.append("lot_fabric_details", {"cloth_item": cloth_item, "production_detail": cpd_name})


def _requirement_payload(by_cloth):
    """Phase 4 payload: the shape save_fabric_requirement_details parses -
    [{cloth_item, requirement:[{dia, colour, weight}]}]."""
    entries = []
    for cloth, tuples in by_cloth.items():
        req = [{"dia": dia, "colour": colour or None, "weight": flt(kg)}
               for (dia, colour), kg in tuples.items()]
        entries.append({"cloth_item": cloth, "requirement": req})
    return entries


@frappe.whitelist()
def build_cloth_programs(lot, selections, modified=None):
    """Orchestrator entrypoint (Desk button + /web modal). selections:
    [{cloth_item, yarn_item, knitting_process, dyeing_process, compacting_process,
    cloth_per_kg_yarn, greige_colour}]."""
    selections = frappe.parse_json(selections) if isinstance(selections, str) else selections
    lot_doc = frappe.get_doc("Lot", lot)
    lot_doc.check_permission("write")
    _guard_not_modified(lot_doc, modified)

    demand = compute_cloth_demand(lot_doc.name)
    if not demand:
        frappe.throw(_("This lot has no cloth demand. Run 'Calculate Order Items' first, then retry."))

    by_cloth = {}
    for (cloth, dia, colour), kg in demand.items():
        by_cloth.setdefault(cloth, {})[(dia, colour)] = flt(kg)

    sel_by_cloth = {s["cloth_item"]: s for s in selections or []}
    built, payload = [], {}
    for cloth, tuples in by_cloth.items():
        selection = sel_by_cloth.get(cloth)
        if not selection:
            continue
        has_colour = any(colour for (dia, colour) in tuples)
        if has_colour and not selection.get("dyeing_process"):
            frappe.throw(_("Cloth {0} has coloured demand — a Dyeing Process is required "
                           "so the colour enters the chain.").format(cloth))
        if has_colour and not selection.get("greige_colour"):
            frappe.throw(_("Cloth {0} has coloured demand — a Greige Colour is required "
                           "(the dyeing from-colour).").format(cloth))
        cpd_name = _find_or_create_cpd(cloth, selection, tuples)
        _ensure_lot_fabric_detail(lot_doc, cloth, cpd_name)
        payload[cloth] = tuples
        built.append({"cloth_item": cloth, "cpd": cpd_name})

    if not built:
        frappe.throw(_("No selected cloth matches the lot's cloth demand."))

    lot_doc.fabric_requirement_details = frappe.as_json(_requirement_payload(payload))
    lot_doc.save(ignore_permissions=True)
    return {"cloths_built": len(built), "programs": built}


def _cloth_rows_from_ipd(ipd):
    """The popup cloth list: exactly ONE row per cloth Item. Multiple cloth_detail
    labels mapping to the same cloth Item (live: CS-34606/34605 Half Sleeve
    Polo-1's 'Main Fabric' + 'Foam Fabric' -> one Tencel fabric; Casual Designer
    Vest - 4-1) are MERGED into one card ('label / label', first required_gsm
    kept) — kills sel_by_cloth's last-card-wins ambiguity. Rows without a cloth
    Item link are dropped; is_bom_item is deliberately ignored (include-all)."""
    by_item = {}
    rows = []
    for c in ipd.get("cloth_detail") or []:
        if not c.cloth:
            continue
        if c.cloth in by_item:
            by_item[c.cloth]["label"] += " / " + c.name1
            continue
        row = {
            "cloth_item": c.cloth,
            "label": c.name1,
            "required_gsm": flt(c.get("required_gsm")),
        }
        by_item[c.cloth] = row
        rows.append(row)
    return rows


def _default_yarn_for_cloth(cloth_item):
    """The cloth's own existing CPD yarn, used ONLY as the popup's starting yarn
    (re-open convenience). Returns '' when the cloth has no CPD yet. The process /
    ratio / greige PREFILL is NOT taken from here — it is derived from the picked
    yarn via _yarn_profile (spec: reverse-query by yarn)."""
    return frappe.db.get_value(
        "Item Production Detail", {"item": cloth_item, "is_cloth_item": 1}, "yarn_item") or ""


def _yarn_profile(yarn_item):
    """Spec prefill: reverse-query ANY existing cloth IPD whose yarn_item = the
    picked yarn and echo its processes / cloth_per_kg_yarn / greige. Most-recent
    wins. Empty when the yarn has never been used on a cloth CPD."""
    if not yarn_item:
        return {}
    name = frappe.db.get_value(
        "Item Production Detail",
        {"yarn_item": yarn_item, "is_cloth_item": 1},
        "name",
        order_by="modified desc",
    )
    if not name:
        return {}
    cpd = frappe.get_cached_doc("Item Production Detail", name)
    return {
        "knitting_process": cpd.get("knitting_process"),
        "dyeing_process": cpd.get("dyeing_process"),
        "compacting_process": cpd.get("compacting_process"),
        "cloth_per_kg_yarn": flt(cpd.get("cloth_per_kg_yarn")),
        "greige_colour": get_greige_colour(cpd),
    }


@frappe.whitelist()
def get_cloth_program_context(lot):
    """Popup context: the garment's cloth list + each cloth's default (own-CPD) yarn.
    Filtered to DEMANDED cloths only — never-mapped zero-demand cloth_detail rows
    (22 live IPDs, incl. 437765's 'Piping Fabric') would otherwise render
    all-required cards that block submission and are then silently discarded.
    Calling compute_cloth_demand here also surfaces the incomplete-IPD /
    unmapped-label errors at popup-OPEN in both UIs. The per-field profile
    prefill is fetched by the UI via get_yarn_profile once a yarn is known (on
    open and on every yarn change)."""
    lot_doc = frappe.get_doc("Lot", lot)
    lot_doc.check_permission("read")
    if not lot_doc.production_detail:
        return {"cloths": []}
    ipd = frappe.get_cached_doc("Item Production Detail", lot_doc.production_detail)
    cloths = _cloth_rows_from_ipd(ipd)
    demanded = {cloth for (cloth, _dia, _colour) in compute_cloth_demand(lot_doc.name)}
    cloths = [c for c in cloths if c["cloth_item"] in demanded]
    for c in cloths:
        c["default_yarn"] = _default_yarn_for_cloth(c["cloth_item"])
    return {"cloths": cloths}


@frappe.whitelist()
def get_yarn_profile(yarn_item):
    """Reverse-query the profile (processes / ratio / greige) for a picked yarn.
    Called by the Desk dialog + /web modal on yarn selection to prefill fields."""
    if not frappe.has_permission("Item Production Detail", "read"):
        frappe.throw(_("Not permitted"), frappe.PermissionError)
    return _yarn_profile(yarn_item)
