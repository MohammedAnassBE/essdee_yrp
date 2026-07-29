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
Because compute_cloth_demand emits the finished panel/packing colour, each route
also declares the physical colour received from knitting. A Dyeing Process is
required only where those two colours differ. Direct AMEL/GMEL routes persist a
same-value routing row so their exact Dia/Colour recipe is retained, but matrix
generation and the backward planner bypass dyeing for that row.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt

from essdee_yrp.api.work_order import _guard_not_modified
from essdee_yrp.fabric_ipd import synthesize_fabric_processes_from_tabs
from essdee_yrp.fabric_program import (
    get_greige_colour,
    get_knitting_output_colour_map,
)
from essdee_yrp.fabric_requirement import compute_cloth_demand

#: The adapter's fixed sequences for the 3 tab steps (knitting / dyeing /
#: compacting). _persist_generic_fabric_rows owns EXACTLY these persisted
#: sequences; any other sequence (a manually-authored washing/printing step)
#: is never touched by the auto-builder.
TAB_SEQUENCES = (10, 20, 30)


def _normalize_yarns(selection, required=True):
    """Return the popup yarn recipe as validated ``[{yarn_item, ratio}]``.

    ``yarn_item`` remains accepted as the one-yarn legacy payload so older
    Desk assets and API callers keep working while both current UIs submit the
    full recipe.  A populated recipe is strict because the process matrix and
    Work Order calculation split the knitting input by these percentages.
    """
    raw = selection.get("yarns") or []
    if not raw and selection.get("yarn_item"):
        raw = [{"yarn_item": selection.get("yarn_item"), "ratio": 100}]

    yarns, seen, total = [], set(), 0.0
    for index, row in enumerate(raw, 1):
        yarn_item = (row.get("yarn_item") or "").strip()
        ratio = flt(row.get("ratio"))
        if not yarn_item:
            frappe.throw(_("Yarn row {0}: select a Yarn Item.").format(index))
        if yarn_item in seen:
            frappe.throw(_("Yarn row {0}: duplicate Yarn Item {1}.").format(index, yarn_item))
        if ratio <= 0:
            frappe.throw(_("Yarn row {0}: Ratio must be greater than zero.").format(index))
        seen.add(yarn_item)
        total += ratio
        yarns.append({"yarn_item": yarn_item, "ratio": ratio})

    if not yarns and not required:
        return []
    if not yarns:
        frappe.throw(_("Add at least one yarn to the Yarn Recipe."))
    if abs(total - 100.0) > 0.001:
        frappe.throw(
            _("Yarn Ratio total must be exactly 100. Current total is {0}.").format(flt(total, 3))
        )
    return yarns


def _item_yarns_for_cloth(cloth_item, required=False):
    """Return the reusable yarn recipe stored on the cloth Item master."""
    item = frappe.get_cached_doc("Item", cloth_item)
    if item.get("yarn_ratio_details") and not item.get("is_cloth_item"):
        frappe.throw(
            _("Enable 'Is Cloth Item' on Item {0} before using its Yarn Ratio.").format(
                cloth_item
            )
        )
    rows = [
        {
            "yarn_item": row.get("yarn_item"),
            "ratio": flt(row.get("ratio")),
        }
        for row in (item.get("yarn_ratio_details") or [])
        if row.get("yarn_item")
    ]
    if not rows:
        if required:
            frappe.throw(
                _(
                    "Cloth Item {0} has no Yarn Ratio. Open the Item, enable "
                    "'Is Cloth Item', and add a yarn recipe totalling 100%."
                ).format(cloth_item)
            )
        return []
    return _normalize_yarns({"yarns": rows})


def _recipe_map(rows):
    """Canonical ``{colour: {yarn_item: ratio}}`` for comparison and reuse."""
    result = {}
    for row in rows or []:
        colour = row.get("colour")
        yarn_item = row.get("yarn_item")
        if colour and yarn_item:
            result.setdefault(colour, {})[yarn_item] = flt(row.get("ratio"))
    return result


def _normalize_colour_yarn_recipes(selection, required_colours):
    """Validate the Build Cloth Program colour recipes.

    The popup always submits explicit colour rows. Legacy API callers that only
    send ``yarns`` remain supported by expanding that one recipe across every
    demanded colour. The expanded rows are the immutable recipe snapshot stored
    on the generated cloth IPD.
    """
    required_colours = list(dict.fromkeys(colour for colour in required_colours if colour))
    raw = selection.get("colour_yarn_recipes") or []
    if not raw:
        shared = _normalize_yarns(selection)
        return [
            {"colour": colour, "yarn_item": row["yarn_item"], "ratio": row["ratio"]}
            for colour in required_colours
            for row in shared
        ]

    groups = {}
    seen = set()
    for index, row in enumerate(raw, 1):
        colour = (row.get("colour") or "").strip()
        yarn_item = (row.get("yarn_item") or "").strip()
        ratio = flt(row.get("ratio"))
        if not colour:
            frappe.throw(_("Colour yarn row {0}: select a Colour.").format(index))
        if colour not in required_colours:
            frappe.throw(
                _("Colour yarn row {0}: {1} is not required for this Lot.").format(
                    index, colour
                )
            )
        if not yarn_item:
            frappe.throw(_("Colour yarn row {0}: select a Yarn Item.").format(index))
        key = (colour, yarn_item)
        if key in seen:
            frappe.throw(
                _("Colour yarn row {0}: duplicate Yarn Item {1} for {2}.").format(
                    index, yarn_item, colour
                )
            )
        if ratio <= 0:
            frappe.throw(
                _("Colour yarn row {0}: Ratio must be greater than zero.").format(index)
            )
        seen.add(key)
        groups.setdefault(colour, []).append(
            {"colour": colour, "yarn_item": yarn_item, "ratio": ratio}
        )

    missing = [colour for colour in required_colours if colour not in groups]
    if missing:
        frappe.throw(
            _("Add a yarn recipe for every demanded colour. Missing: {0}.").format(
                ", ".join(missing)
            )
        )
    for colour, rows in groups.items():
        total = sum(flt(row["ratio"]) for row in rows)
        if abs(total - 100.0) > 0.001:
            frappe.throw(
                _("{0}: Yarn Ratio total must be exactly 100. Current total is {1}.").format(
                    colour, flt(total, 3)
                )
            )
    return [row for colour in required_colours for row in groups[colour]]


def _normalize_knitting_output_colours(selection, required_colours):
    """Return one knitting-output colour for every demanded finished colour.

    ``greige_colour`` remains a supported legacy payload: it is expanded over
    all demanded colours.  Current callers submit explicit rows so one cloth
    can knit Grey, Greige, Anthracite Melange and Grey Melange in the same
    production profile.
    """
    required_colours = list(dict.fromkeys(colour for colour in required_colours if colour))
    raw = selection.get("knitting_output_colours") or []
    if isinstance(raw, dict):
        raw = [
            {
                "colour": colour,
                "knitting_output_colour": output_colour,
            }
            for colour, output_colour in raw.items()
        ]

    legacy = (selection.get("greige_colour") or "").strip()
    if not raw and legacy:
        raw = [
            {
                "colour": colour,
                "knitting_output_colour": legacy,
            }
            for colour in required_colours
        ]

    output_by_colour = {}
    for index, row in enumerate(raw, 1):
        colour = (
            row.get("colour")
            or row.get("target_colour")
            or row.get("finished_colour")
            or ""
        ).strip()
        output_colour = (
            row.get("knitting_output_colour")
            or row.get("output_colour")
            or ""
        ).strip()
        if not colour:
            frappe.throw(
                _("Knitting output row {0}: select the Finished Colour.").format(index)
            )
        if colour not in required_colours:
            frappe.throw(
                _("Knitting output row {0}: {1} is not required for this Lot.").format(
                    index, colour
                )
            )
        if not output_colour:
            frappe.throw(
                _(
                    "Knitting output row {0}: select the colour received after "
                    "Knitting for {1}."
                ).format(index, colour)
            )
        if colour in output_by_colour:
            frappe.throw(
                _("Knitting output row {0}: duplicate Finished Colour {1}.").format(
                    index, colour
                )
            )
        if (
            frappe.db.get_value(
                "Item Attribute Value", output_colour, "attribute_name"
            )
            != "Colour"
        ):
            frappe.throw(
                _("{0} is not a Colour attribute value.").format(output_colour)
            )
        output_by_colour[colour] = output_colour

    missing = [colour for colour in required_colours if colour not in output_by_colour]
    if missing:
        frappe.throw(
            _(
                "Select the Knitting Output Colour for every demanded colour. "
                "Missing: {0}."
            ).format(", ".join(missing))
        )
    return [
        {
            "colour": colour,
            "knitting_output_colour": output_by_colour[colour],
        }
        for colour in required_colours
    ]


def _normalize_fabric_routes(selection, required_routes):
    """Validate exact final -> knitting receipt routes.

    ``required_routes`` is the Lot demand's ``[(finished_dia,
    finished_colour), ...]``. Current clients submit ``fabric_routes`` with
    both physical knitting attributes. Older clients submit one output colour
    per finished colour; that remains valid and defaults the knitting Dia to
    the finished Dia.
    """
    required = list(dict.fromkeys(
        (dia, colour) for dia, colour in required_routes if dia and colour
    ))
    raw = selection.get("fabric_routes") or []
    if not raw:
        colour_rows = _normalize_knitting_output_colours(
            selection, list(dict.fromkeys(colour for _dia, colour in required))
        )
        output_by_colour = {
            row["colour"]: row["knitting_output_colour"]
            for row in colour_rows
        }
        raw = [
            {
                "finished_dia": dia,
                "finished_colour": colour,
                "knitting_output_dia": dia,
                "knitting_output_colour": output_by_colour[colour],
            }
            for dia, colour in required
        ]

    normalised = []
    seen = set()
    for index, row in enumerate(raw, 1):
        final_dia = (row.get("finished_dia") or row.get("dia") or "").strip()
        final_colour = (
            row.get("finished_colour")
            or row.get("colour")
            or ""
        ).strip()
        knitting_dia = (
            row.get("knitting_output_dia")
            or row.get("knitting_dia")
            or final_dia
        ).strip()
        knitting_colour = (
            row.get("knitting_output_colour")
            or row.get("output_colour")
            or ""
        ).strip()
        key = (final_dia, final_colour)
        if key not in required:
            frappe.throw(_(
                "Fabric route row {0}: {1} / {2} is not required for this Lot."
            ).format(index, final_colour or "?", final_dia or "?"))
        if key in seen:
            frappe.throw(_(
                "Fabric route row {0}: duplicate Finished Colour / Dia {1} / {2}."
            ).format(index, final_colour, final_dia))
        if not knitting_dia or not knitting_colour:
            frappe.throw(_(
                "Fabric route row {0}: select both Knitting Output Dia and Colour."
            ).format(index))
        for value, attribute in (
            (final_dia, "Dia"),
            (knitting_dia, "Dia"),
            (final_colour, "Colour"),
            (knitting_colour, "Colour"),
        ):
            if (
                frappe.db.get_value(
                    "Item Attribute Value", value, "attribute_name"
                )
                != attribute
            ):
                frappe.throw(_("{0} is not a {1} attribute value.").format(
                    value, attribute
                ))
        seen.add(key)
        normalised.append({
            "finished_dia": final_dia,
            "finished_colour": final_colour,
            "knitting_output_dia": knitting_dia,
            "knitting_output_colour": knitting_colour,
        })

    missing = [
        f"{colour} / {dia}"
        for dia, colour in required
        if (dia, colour) not in seen
    ]
    if missing:
        frappe.throw(_(
            "Add a fabric route for every demanded Colour / Dia. Missing: {0}."
        ).format(", ".join(missing)))
    return normalised


def _fabric_route_map(selection):
    """Canonical exact route map keyed by final ``(Dia, Colour)``."""
    return {
        (row.get("finished_dia"), row.get("finished_colour")): {
            "knitting_output_dia": row.get("knitting_output_dia"),
            "knitting_output_colour": row.get("knitting_output_colour"),
        }
        for row in selection.get("fabric_routes") or []
        if row.get("finished_dia") and row.get("finished_colour")
    }


def _knitting_output_map(selection):
    """Canonical ``{finished_colour: knitting_output_colour}``."""
    return {
        row.get("colour"): row.get("knitting_output_colour")
        for row in selection.get("knitting_output_colours") or []
        if row.get("colour") and row.get("knitting_output_colour")
    }


def _profile_matches(cpd, selection):
    """Whether a CPD can safely be reused for this operational profile."""
    comparisons = (
        ("knitting_process", selection.get("knitting_process")),
        ("dyeing_process", selection.get("dyeing_process")),
        ("compacting_process", selection.get("compacting_process")),
    )
    for fieldname, requested in comparisons:
        existing = cpd.get(fieldname)
        if existing and requested and existing != requested:
            return False
    existing_ratio = flt(cpd.get("cloth_per_kg_yarn"))
    requested_ratio = flt(selection.get("cloth_per_kg_yarn"))
    if existing_ratio and requested_ratio and abs(existing_ratio - requested_ratio) > 0.000001:
        return False

    requested_outputs = _knitting_output_map(selection)
    existing_outputs = get_knitting_output_colour_map(cpd)
    if not all(
        not existing_outputs.get(colour)
        or existing_outputs[colour] == output_colour
        for colour, output_colour in requested_outputs.items()
    ):
        return False
    requested_routes = _fabric_route_map(selection)
    existing_routes = {
        (row.finished_dia, row.finished_colour): {
            "knitting_output_dia": row.knitting_output_dia,
            "knitting_output_colour": row.knitting_output_colour,
        }
        for row in cpd.get("fabric_routes") or []
    }
    if not all(
        not existing_routes.get(key)
        or existing_routes[key] == physical
        for key, physical in requested_routes.items()
    ):
        return False
    legacy_greige = selection.get("greige_colour")
    existing_greige = get_greige_colour(cpd)
    return not (
        not requested_outputs
        and legacy_greige
        and existing_greige
        and legacy_greige != existing_greige
    )


def _profile_matches_exactly(cpd, selection):
    """Whether reuse can happen without changing an operational CPD."""
    for fieldname in (
        "knitting_process",
        "dyeing_process",
        "compacting_process",
    ):
        if (cpd.get(fieldname) or None) != (selection.get(fieldname) or None):
            return False
    if abs(
        flt(cpd.get("cloth_per_kg_yarn"))
        - flt(selection.get("cloth_per_kg_yarn"))
    ) > 0.000001:
        return False

    requested_routes = _fabric_route_map(selection)
    if requested_routes:
        existing_routes = {
            (row.finished_dia, row.finished_colour): {
                "knitting_output_dia": row.knitting_output_dia,
                "knitting_output_colour": row.knitting_output_colour,
            }
            for row in cpd.get("fabric_routes") or []
        }
        return existing_routes == requested_routes

    requested_outputs = _knitting_output_map(selection)
    if requested_outputs:
        return get_knitting_output_colour_map(cpd) == requested_outputs
    legacy_greige = selection.get("greige_colour")
    if legacy_greige:
        return get_greige_colour(cpd) == legacy_greige
    return not (
        cpd.get("fabric_routes")
        or get_knitting_output_colour_map(cpd)
        or get_greige_colour(cpd)
    )


def _cpd_is_operationally_referenced(cpd_name):
    """True once an operational document has taken a snapshot dependency.

    Matrix rows are intentionally excluded: they are regenerated as part of
    the CPD itself. Lots and execution documents must keep their exact route
    profile, so a changed requirement creates a new CPD version instead.
    """
    references = (
        ("Lot Fabric Detail", {"production_detail": cpd_name, "parenttype": "Lot"}),
        ("Work Order", {"production_detail": cpd_name}),
        ("Delivery Challan", {"production_detail": cpd_name}),
        ("Goods Received Note", {"production_detail": cpd_name}),
        ("Work Order Correction", {"production_detail": cpd_name}),
    )
    return any(frappe.db.exists(doctype, filters) for doctype, filters in references)


def _find_reusable_cpd(cloth_item, selection):
    """Find a recipe-safe CPD or return ``None`` for a new version.

    A CPD with a different colour recipe is never mutated: an earlier Lot may
    still reference it. Exact recipe/profile matches can be shared, while an
    unconfigured and unreferenced legacy CPD may be adopted by the first build.
    """
    requested = _recipe_map(selection.get("colour_yarn_recipes") or [])
    names = frappe.get_all(
        "Item Production Detail",
        filters={"item": cloth_item, "is_cloth_item": 1},
        pluck="name",
        order_by="version desc, modified desc",
    )
    preferred = selection.get("production_detail")
    if preferred in names:
        names.remove(preferred)
        names.insert(0, preferred)

    blank_candidate = None
    for name in names:
        cpd = frappe.get_cached_doc("Item Production Detail", name)
        existing = _recipe_map(cpd.get("colour_yarn_recipes") or [])
        compatible = _profile_matches(cpd, selection)
        exact = compatible and _profile_matches_exactly(cpd, selection)
        referenced = _cpd_is_operationally_referenced(name)
        if existing == requested and compatible and (exact or not referenced):
            return frappe.get_doc("Item Production Detail", name)
        if not existing and requested and _profile_matches(cpd, selection):
            if not referenced and blank_candidate is None:
                blank_candidate = name
        if (
            not requested
            and not existing
            and compatible
            and (exact or not referenced)
        ):
            return frappe.get_doc("Item Production Detail", name)
    return (
        frappe.get_doc("Item Production Detail", blank_candidate)
        if blank_candidate
        else None
    )


def _find_or_create_cpd(cloth_item, selection, tuples):
    """Phase 2. selection: {yarns, yarn_item, knitting_process, dyeing_process,
    compacting_process, cloth_per_kg_yarn,
    knitting_output_colours:[{colour, knitting_output_colour}]}.
    tuples: {(dia,colour): kg}.
    Returns the CPD (Item Production Detail) name.

    Seeding is ADDITIVE: 50/81 cloth Items on essdee_yrp.site are shared across
    multiple garment styles (probe 2026-07-21: Lycra Rib by 24 garment items;
    40's GL Dyed Fabric New by 7) — wholesale replace would delete sibling lots'
    demanded rows and break their already-written requirements."""
    cpd = _find_reusable_cpd(cloth_item, selection) or frappe.new_doc(
        "Item Production Detail"
    )
    # The Lot popup selection is already the authoritative, fully-normalised
    # process profile.  Do not let the new-document defaults hook silently
    # replace an explicit blank (notably compacting_process=None) with the
    # singleton setting while this generated CPD is being saved.
    cpd.flags.skip_ipd_settings_defaults = True
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
    colour_recipes = selection.get("colour_yarn_recipes") or []
    cpd.set(
        "colour_yarn_recipes",
        [
            {
                "cloth_item": cloth_item,
                "colour": row["colour"],
                "yarn_item": row["yarn_item"],
                "ratio": flt(row["ratio"]),
            }
            for row in colour_recipes
        ],
    )
    route_map = _fabric_route_map(selection)
    if not route_map:
        # Backward-compatible direct helper/test callers. The orchestrator
        # always normalises exact routes before reaching this function.
        output_by_colour = _knitting_output_map(selection)
        legacy_greige = selection.get("greige_colour")
        route_map = {
            (dia, colour): {
                "knitting_output_dia": dia,
                "knitting_output_colour": (
                    output_by_colour.get(colour) or legacy_greige
                ),
            }
            for dia, colour in tuples
            if dia and colour
        }
    # Direct legacy callers do not have route-aware downstream matrices. Keep
    # their generated CPD in the legacy shape, while every UI/orchestrated
    # colour recipe persists the exact final-to-knitting route.
    persist_exact_routes = bool(
        selection.get("fabric_routes") or colour_recipes
    )
    existing_routes = {
        (row.finished_dia, row.finished_colour): {
            "finished_dia": row.finished_dia,
            "finished_colour": row.finished_colour,
            "knitting_output_dia": row.knitting_output_dia,
            "knitting_output_colour": row.knitting_output_colour,
        }
        for row in cpd.get("fabric_routes") or []
    }
    if persist_exact_routes:
        for (final_dia, final_colour), physical in route_map.items():
            existing_routes[(final_dia, final_colour)] = {
                "finished_dia": final_dia,
                "finished_colour": final_colour,
                **physical,
            }
        cpd.set("fabric_routes", list(existing_routes.values()))

    yarns = _normalize_yarns(selection, required=False)
    if not yarns and colour_recipes:
        first_colour = colour_recipes[0]["colour"]
        yarns = [
            {"yarn_item": row["yarn_item"], "ratio": row["ratio"]}
            for row in colour_recipes if row["colour"] == first_colour
        ]
    cpd.set("yarn_ratio_details", yarns)
    # Legacy readers still use yarn_item as the primary/first yarn.  The child
    # table is the recipe source of truth and the matrix builder emits every
    # yarn with its percentage.
    cpd.yarn_item = yarns[0]["yarn_item"] if yarns else None
    cpd.cloth_per_kg_yarn = flt(selection.get("cloth_per_kg_yarn"))
    cpd.knitting_process = selection.get("knitting_process")
    cpd.dyeing_process = selection.get("dyeing_process")
    cpd.compacting_process = selection.get("compacting_process")

    route_values = (
        existing_routes.values() if persist_exact_routes else route_map.values()
    )
    dias = list(dict.fromkeys(
        route["knitting_output_dia"] for route in route_values
        if route.get("knitting_output_dia")
    ))
    have_dias = {r.dia for r in (cpd.get("knitting_dia_details") or [])}
    for d in dias:
        if d not in have_dias:
            cpd.append("knitting_dia_details", {"dia": d})

    if cpd.dyeing_process:
        have_dye = {(r.dia, r.from_colour, r.to_colour)
                    for r in (cpd.get("dyeing_colour_details") or [])}
        for (final_dia, colour), route in route_map.items():
            knitting_output = route.get("knitting_output_colour")
            knitting_dia = route.get("knitting_output_dia")
            if not knitting_output or not knitting_dia:
                frappe.throw(
                    _(
                        "Select the Knitting Output Colour and Dia for {0} / {1} / {2}."
                    ).format(cloth_item, colour, final_dia)
                )
            key = (knitting_dia, knitting_output, colour)
            if key in have_dye:
                continue
            have_dye.add(key)
            cpd.append("dyeing_colour_details",
                       {
                           "dia": knitting_dia,
                           "from_colour": knitting_output,
                           "to_colour": colour,
                       })

    if cpd.compacting_process:
        have_compact = {
            (row.colour, row.from_dia, row.to_dia)
            for row in cpd.get("compacting_dia_details") or []
        }
        for (final_dia, colour), route in route_map.items():
            knitting_dia = route.get("knitting_output_dia")
            if not knitting_dia or knitting_dia == final_dia:
                continue
            key = (colour, knitting_dia, final_dia)
            if key in have_compact:
                continue
            have_compact.add(key)
            cpd.append("compacting_dia_details", {
                "colour": colour,
                "from_dia": knitting_dia,
                "to_dia": final_dia,
            })

    _persist_generic_fabric_rows(cpd)
    cpd.approval_status = "Approved"  # base field is UI-read_only; set server-side
    cpd.save(ignore_permissions=True)
    return cpd.name


def _persist_generic_fabric_rows(cpd):
    """Materialize the generic Fabric Processes rows (`fabric_processes` +
    `fabric_value_mappings`) from the just-seeded tab fields — the SAME rows
    manual authoring writes.

    The legacy Knitting/Dyeing/Compacting tabs were REMOVED from the IPD form
    (patches/remove_cloth_ipd_fabric_tabs.py): the generic Fabric Processes tab
    is the only authoring/inspection UI, and it reads the persisted tables. A
    tabs-only CPD renders that tab EMPTY (owner bug, lot F0426-79/3) and is one
    UI-added step away from chain corruption — get_fabric_process_rows prefers
    the persisted table the moment it has ANY row, silently dropping the
    synthesized knitting/dyeing steps.

    Persisting the adapter's own output (synthesize_fabric_processes_from_tabs)
    verbatim guarantees the persisted path rebuilds byte-identical matrices —
    _attach_persisted_mappings reconstitutes exactly these rows. Idempotent:
    the managed TAB_SEQUENCES rows are replaced wholesale on every build; rows
    at any other sequence (manually-authored extra steps) are preserved.

    All-or-nothing guard: input_item/output_item are REQD on IPD Fabric
    Process, and the knitting input (yarn_item) may legitimately be blank. A
    PARTIAL persist would disable the tab adapter and drop the unpersistable
    step from the chain — so with any unpersistable row nothing NEW is
    persisted. Previously-persisted managed rows cannot be left behind either
    (they would serve a STALE chain: old yarn input, freshly-seeded dias
    missing from the Introduce mappings -> opaque reachability failure), so
    they are cleared when that empties the table (the adapter then serves the
    fresh tabs, pre-fix behavior exactly) and the build refuses loudly when
    custom unmanaged steps would make the leftover table partial."""
    synthesized = synthesize_fabric_processes_from_tabs(cpd)
    managed = set(TAB_SEQUENCES)
    keep_fp = [r for r in cpd.get("fabric_processes") or [] if cint(r.sequence) not in managed]
    keep_vm = [r for r in cpd.get("fabric_value_mappings") or [] if cint(r.sequence) not in managed]

    if any(not (row.get("input_item") and row.get("output_item")) for row in synthesized):
        if not (cpd.get("fabric_processes") or cpd.get("fabric_value_mappings")):
            return  # never persisted -> the tab adapter keeps serving the chain
        if keep_fp or keep_vm:
            frappe.throw(_(
                "Cloth {0}: select a Yarn — its production detail carries custom fabric "
                "steps, so the persisted knitting/dyeing steps cannot be refreshed "
                "without the knitting input item."
            ).format(cpd.item))
        cpd.set("fabric_processes", [])
        cpd.set("fabric_value_mappings", [])
        return

    cpd.set("fabric_processes", keep_fp)
    cpd.set("fabric_value_mappings", keep_vm)
    for row in synthesized:
        cpd.append("fabric_processes", {
            "sequence": row.get("sequence"),
            "fabric_process": row.get("fabric_process"),
            "input_item": row.get("input_item"),
            "output_item": row.get("output_item"),
            "quantity_ratio": row.get("quantity_ratio"),
        })
        for m in row.get("value_mappings") or []:
            cpd.append("fabric_value_mappings", {
                "sequence": row.get("sequence"),
                "mapping_index": m.get("mapping_index"),
                "attribute": m.get("attribute"),
                "role": m.get("role"),
                "from_value": m.get("from_value"),
                "to_value": m.get("to_value"),
            })

    # Renumber idx sequence-ordered: kept rows RETAIN their old idx while
    # appended rows get idx=len(table) (BaseDocument.append), so a
    # preserve-rebuild would persist DUPLICATE idx values and the Desk grid
    # (ordered by idx) could render the chain out of order. The sort is
    # stable, so within one sequence the synthesized order (Change before
    # Pin per mapping group) is untouched.
    for table in ("fabric_processes", "fabric_value_mappings"):
        rows = sorted(cpd.get(table) or [], key=lambda r: cint(r.sequence))
        for i, r in enumerate(rows, 1):
            r.idx = i
        cpd.set(table, rows)


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
def build_cloth_programs(lot, selections, modified=None, excess_percentage=0):
    """Orchestrator entrypoint (Desk button + /web modal). selections:
    [{cloth_item, yarns:[{yarn_item,ratio}], yarn_item, knitting_process,
    dyeing_process, cloth_per_kg_yarn,
    knitting_output_colours:[{colour,knitting_output_colour}]}].
    ``greige_colour`` remains accepted as the legacy one-colour shortcut.
    Compacting references are maintained separately on the F16 cloth IPD and
    are not calculated."""
    selections = frappe.parse_json(selections) if isinstance(selections, str) else selections
    lot_doc = frappe.get_doc("Lot", lot)
    lot_doc.check_permission("write")
    _guard_not_modified(lot_doc, modified)
    excess_percentage = flt(excess_percentage)
    if excess_percentage < 0:
        frappe.throw(_("Knitting program excess percentage cannot be negative."))
    excess_factor = 1 + excess_percentage / 100

    demand = compute_cloth_demand(lot_doc.name)
    if not demand:
        frappe.throw(_("This lot has no cloth demand. Run 'Calculate Order Items' first, then retry."))

    by_cloth = {}
    for (cloth, dia, colour), kg in demand.items():
        by_cloth.setdefault(cloth, {})[(dia, colour)] = flt(kg)

    sel_by_cloth = {s.get("cloth_item"): s for s in (selections or []) if s.get("cloth_item")}
    current_cpd = {
        row.cloth_item: row.production_detail
        for row in lot_doc.get("lot_fabric_details") or []
        if row.cloth_item and row.production_detail
    }
    built, payload = [], {}
    for cloth, tuples in by_cloth.items():
        selection = sel_by_cloth.get(cloth)
        if not selection:
            continue
        # The Item master is the source of truth for yarn composition. Legacy
        # callers may still submit a recipe only while an old cloth Item has not
        # yet been configured; current Desk and /web callers submit none.
        item_yarns = _item_yarns_for_cloth(cloth)
        required_colours = list(
            dict.fromkeys(colour for (_dia, colour) in tuples if colour)
        )
        if required_colours:
            colour_recipes = (
                [
                    {
                        "colour": colour,
                        "yarn_item": row["yarn_item"],
                        "ratio": row["ratio"],
                    }
                    for colour in required_colours
                    for row in item_yarns
                ]
                if item_yarns
                else _normalize_colour_yarn_recipes(selection, required_colours)
            )
            selection["colour_yarn_recipes"] = colour_recipes
            selection["fabric_routes"] = _normalize_fabric_routes(
                selection,
                list(tuples),
            )
            # Keep the colour-only compatibility view for older profile readers.
            selection["knitting_output_colours"] = [
                {
                    "colour": colour,
                    "knitting_output_colour": next(
                        route["knitting_output_colour"]
                        for route in selection["fabric_routes"]
                        if route["finished_colour"] == colour
                    ),
                }
                for colour in required_colours
            ]
            first_colour = required_colours[0]
            selection["yarns"] = [
                {
                    "yarn_item": row["yarn_item"],
                    "ratio": row["ratio"],
                }
                for row in colour_recipes
                if row["colour"] == first_colour
            ]
            selection["yarn_item"] = selection["yarns"][0]["yarn_item"]
        else:
            selection["colour_yarn_recipes"] = []
            selection["knitting_output_colours"] = []
            selection["fabric_routes"] = []
            selection["yarns"] = item_yarns or _normalize_yarns(selection)
            selection["yarn_item"] = selection["yarns"][0]["yarn_item"]
        selection["production_detail"] = current_cpd.get(cloth)
        route_map = _fabric_route_map(selection)
        needs_dyeing = any(
            final_colour
            and route.get("knitting_output_colour") != final_colour
            for (_final_dia, final_colour), route in route_map.items()
        )
        if needs_dyeing and not selection.get("dyeing_process"):
            frappe.throw(_(
                "Cloth {0} has routes whose Knitting Output Colour differs "
                "from the Finished Colour — select a Dyeing Process."
            ).format(cloth))
        needs_compacting = any(
            route.get("knitting_output_dia") != final_dia
            for (final_dia, _final_colour), route in route_map.items()
        )
        if needs_compacting and not selection.get("compacting_process"):
            frappe.throw(_(
                "Cloth {0} has routes whose Knitting Output Dia differs from "
                "the Finished Dia — select a Compacting/Dia-changing Process."
            ).format(cloth))
        cpd_name = _find_or_create_cpd(cloth, selection, tuples)
        _ensure_lot_fabric_detail(lot_doc, cloth, cpd_name)
        payload[cloth] = tuples
        built.append({"cloth_item": cloth, "cpd": cpd_name})

    if not built:
        frappe.throw(_("No selected cloth matches the lot's cloth demand."))

    # Build is authoritative for the calculated knitting program. Drop old
    # unreceived rows and zero received rows so the plan pre-seed replaces their
    # quantity without ever losing receipt tracking.
    lot_doc.set("lot_fabric_programs", [
        row for row in lot_doc.get("lot_fabric_programs") or []
        if row.cloth_item not in payload or flt(row.received_weight)
    ])
    for row in lot_doc.get("lot_fabric_programs") or []:
        if row.cloth_item in payload:
            row.weight = 0
    lot_doc.flags.force_fabric_plan_rebuild = True
    lot_doc.fabric_requirement_details = frappe.as_json(_requirement_payload(payload))
    lot_doc.save(ignore_permissions=True)
    for row in frappe.get_all(
        "Lot Fabric Program",
        filters={"parent": lot_doc.name, "parenttype": "Lot"},
        fields=["name", "cloth_item", "weight"],
    ):
        if row.cloth_item in payload:
            frappe.db.set_value(
                "Lot Fabric Program",
                row.name,
                "weight",
                flt(flt(row.weight) * excess_factor, 3),
                update_modified=False,
            )
    return {
        "cloths_built": len(built),
        "programs": built,
        "excess_percentage": excess_percentage,
    }


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
    yarns = _default_yarns_for_cloth(cloth_item)
    return yarns[0]["yarn_item"] if yarns else ""


def _default_yarns_for_cloth(cloth_item, cpd_name=None):
    """The cloth's complete persisted yarn recipe for the popup.

    Existing pre-ratio CPDs still appear as one yarn at 100%, so users never
    see a blank recipe merely because the document predates the child table.
    """
    name = cpd_name or frappe.db.get_value(
        "Item Production Detail",
        {"item": cloth_item, "is_cloth_item": 1},
        "name",
        order_by="version desc, modified desc",
    )
    if not name:
        return []
    cpd = frappe.get_cached_doc("Item Production Detail", name)
    rows = [
        {"yarn_item": row.yarn_item, "ratio": flt(row.ratio)}
        for row in (cpd.get("yarn_ratio_details") or [])
        if row.yarn_item
    ]
    if rows:
        return rows
    return [{"yarn_item": cpd.yarn_item, "ratio": 100.0}] if cpd.yarn_item else []


def _profile_from_cpd(cpd):
    return {
        "knitting_process": cpd.get("knitting_process"),
        "dyeing_process": cpd.get("dyeing_process"),
        "compacting_process": cpd.get("compacting_process"),
        "cloth_per_kg_yarn": flt(cpd.get("cloth_per_kg_yarn")),
        "greige_colour": get_greige_colour(cpd),
        "knitting_output_colours": get_knitting_output_colour_map(cpd),
        "fabric_routes": [
            {
                "finished_colour": row.finished_colour,
                "finished_dia": row.finished_dia,
                "knitting_output_colour": row.knitting_output_colour,
                "knitting_output_dia": row.knitting_output_dia,
            }
            for row in cpd.get("fabric_routes") or []
        ],
    }


def _cloth_program_defaults():
    """Configurable first-entry defaults shared by Desk and frontend popups."""
    defaults = {
        "knitting_process": "",
        "dyeing_process": "",
        "knitting_output_colour": "",
        "compacting_process": "",
        "cloth_per_kg_yarn": 1.0,
    }
    if not frappe.db.exists("DocType", "IPD Settings"):
        return defaults

    settings = frappe.get_single("IPD Settings")
    defaults.update({
        "knitting_process": settings.get("default_knitting_process") or "",
        "dyeing_process": settings.get("default_dyeing_process") or "",
        "knitting_output_colour": (
            settings.get("default_knitting_output_colour") or ""
        ),
        "compacting_process": settings.get("default_compacting_process") or "",
        "cloth_per_kg_yarn": (
            flt(settings.get("default_cloth_per_kg_yarn")) or 1.0
        ),
    })
    return defaults


def _yarn_profile(yarn_item):
    """Reverse-query a cloth IPD containing the picked yarn.

    Search the ratio child table first so a secondary yarn in a blend resolves
    the same process profile as the primary yarn; fall back to the legacy
    ``yarn_item`` field for pre-ratio documents.
    """
    if not yarn_item:
        return {}
    parents = frappe.get_all(
        "IPD Yarn Ratio",
        filters={"yarn_item": yarn_item, "parenttype": "Item Production Detail"},
        pluck="parent",
    )
    name = None
    if parents:
        name = frappe.db.get_value(
            "Item Production Detail",
            {"name": ["in", parents], "is_cloth_item": 1},
            "name",
            order_by="modified desc",
        )
    if not name:
        name = frappe.db.get_value(
            "Item Production Detail",
            {"yarn_item": yarn_item, "is_cloth_item": 1},
            "name",
            order_by="modified desc",
        )
    if not name:
        return {}
    cpd = frappe.get_cached_doc("Item Production Detail", name)
    return _profile_from_cpd(cpd)


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
        return {"cloths": [], "defaults": _cloth_program_defaults()}
    ipd = frappe.get_cached_doc("Item Production Detail", lot_doc.production_detail)
    cloths = _cloth_rows_from_ipd(ipd)
    demand = compute_cloth_demand(lot_doc.name)
    demanded = {cloth for (cloth, _dia, _colour) in demand}
    demanded_colours = {}
    demanded_routes = {}
    for (cloth, dia, colour), weight in demand.items():
        demanded_routes.setdefault(cloth, []).append({
            "dia": dia,
            "colour": colour,
            "weight": flt(weight),
        })
        if colour:
            demanded_colours.setdefault(cloth, [])
            if colour not in demanded_colours[cloth]:
                demanded_colours[cloth].append(colour)
    cloths = [c for c in cloths if c["cloth_item"] in demanded]
    lot_cpds = {
        row.cloth_item: row.production_detail
        for row in lot_doc.get("lot_fabric_details") or []
        if row.cloth_item and row.production_detail
    }
    for c in cloths:
        cpd_name = lot_cpds.get(c["cloth_item"]) or frappe.db.get_value(
            "Item Production Detail",
            {"item": c["cloth_item"], "is_cloth_item": 1},
            "name",
            order_by="version desc, modified desc",
        )
        c["production_detail"] = cpd_name
        c["required_colours"] = demanded_colours.get(c["cloth_item"], [])
        c["required_routes"] = demanded_routes.get(c["cloth_item"], [])
        c["item_yarns"] = _item_yarns_for_cloth(c["cloth_item"])
        c["default_yarns"] = _default_yarns_for_cloth(c["cloth_item"], cpd_name)
        c["default_yarn"] = (
            c["default_yarns"][0]["yarn_item"] if c["default_yarns"] else ""
        )
        cpd = frappe.get_cached_doc("Item Production Detail", cpd_name) if cpd_name else None
        c["profile"] = _profile_from_cpd(cpd) if cpd else (
            _yarn_profile(c["item_yarns"][0]["yarn_item"])
            if c["item_yarns"]
            else {}
        )
        c["colour_yarn_recipes"] = [
            {
                "colour": row.colour,
                "yarn_item": row.yarn_item,
                "ratio": flt(row.ratio),
            }
            for row in ((cpd.get("colour_yarn_recipes") or []) if cpd else [])
            if row.colour in c["required_colours"]
        ]
    return {
        "cloths": cloths,
        "defaults": _cloth_program_defaults(),
    }


@frappe.whitelist()
def get_yarn_profile(yarn_item):
    """Reverse-query the profile (processes / ratio / greige) for a picked yarn.
    Called by the Desk dialog + /web modal on yarn selection to prefill fields."""
    if not frappe.has_permission("Item Production Detail", "read"):
        frappe.throw(_("Not permitted"), frappe.PermissionError)
    return _yarn_profile(yarn_item)
