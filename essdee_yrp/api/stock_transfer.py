# Copyright (c) 2026, anas@essdee.fit and contributors
"""Cross-bench receiver: mrp production_api GRN <-> yrp_stock Material Receipt.

Warehouse is resolved server-side from the supplier (mrp GRN delivery_location, a
Supplier docname; the mrp->yrp sync gives it a 1:1 Warehouse named after the supplier).
Every row carries the mrp lot and received_type="Accepted". item_variant, lot,
warehouse, and the "Accepted" Received Type must already exist on yrp (no auto-create).
Both create and cancel are idempotent on `source_grn`.
"""
import json
import re

import frappe
from frappe import _
from frappe.utils import flt
from frappe.utils import synchronization


def _as_dict(payload):
    return json.loads(payload) if isinstance(payload, str) else (payload or {})


def _lock_name(source_grn):
    """Filesystem-safe, per-source_grn lock name (keeps the raw grn as a substring)."""
    return "yrp_grn_transfer_" + re.sub(r"[^A-Za-z0-9_-]", "_", str(source_grn))


def _resolve_warehouse(supplier):
    if not supplier:
        frappe.throw(_("supplier is required to resolve the target warehouse."))
    wh = frappe.db.get_value("Warehouse", {"supplier": supplier}, "name") or supplier
    if not wh or not frappe.db.exists("Warehouse", wh):
        frappe.throw(_("No yrp warehouse for supplier '{0}' — sync gap. "
                       "Nothing was transferred.").format(supplier))
    return wh


@frappe.whitelist()
def receive_grn_transfer(payload):
    """Create+submit a Material Receipt for the mrp GRN. Never raises to the HTTP layer;
    failures become {"ok": False, "error": <clear message>}."""
    # Authorization gate: this endpoint creates+submits a Stock Entry with
    # ignore_permissions, so an explicit permission check must precede it (a bare
    # @frappe.whitelist() otherwise lets any authenticated user create stock). Raised
    # deliberately OUTSIDE the try below so it surfaces as a real PermissionError (403).
    frappe.has_permission("Stock Entry", "create", throw=True)
    try:
        data = _as_dict(payload)
        source_grn = data.get("source_grn")
        if not source_grn:
            return {"ok": False, "error": _("source_grn is required.")}

        # Serialize the check-then-insert per source_grn: a retried/concurrent transfer
        # for the same GRN must not create duplicate Material Receipts. A named file lock
        # (not a DB unique index, which would collide on the blank source_grn of every
        # other Stock Entry) makes the existence re-check + insert atomic across processes.
        with synchronization.filelock(_lock_name(source_grn), timeout=60):
            existing = frappe.db.get_value("Stock Entry", {"source_grn": source_grn, "docstatus": 1}, "name")
            if existing:
                return {"ok": True, "stock_entry": existing, "duplicate": True,
                        "warehouse": frappe.db.get_value("Stock Entry", existing, "to_warehouse"),
                        "message": _("Already transferred (idempotent).")}

            supplier = data.get("supplier")
            warehouse = _resolve_warehouse(supplier)

            items = data.get("items") or []
            if not items:
                return {"ok": False, "error": _("No items in payload.")}

            missing_var = [r.get("item_variant") for r in items
                           if not (r.get("item_variant") and frappe.db.exists("Item Variant", r.get("item_variant")))]
            if missing_var:
                return {"ok": False, "error": _("Item Variants missing on essdee_yrp (sync gap): {0}. "
                                                "Nothing was transferred.").format(", ".join(map(str, missing_var)))}
            missing_lot = [r.get("lot") for r in items
                           if not (r.get("lot") and frappe.db.exists("Lot", r.get("lot")))]
            if missing_lot:
                return {"ok": False, "error": _("Lots missing on essdee_yrp: {0}. "
                                                "Nothing was transferred.").format(", ".join(map(str, missing_lot)))}
            if not frappe.db.exists("Received Type", "Accepted"):
                return {"ok": False, "error": _("Received Type 'Accepted' is missing on essdee_yrp. "
                                                "Nothing was transferred.")}

            se = frappe.new_doc("Stock Entry")
            se.purpose = "Material Receipt"
            se.to_warehouse = warehouse
            se.to_supplier = supplier
            se.source_grn = source_grn                       # Custom Field (Step 4)
            se.comments = _("mrp GRN {0}").format(source_grn)
            # Give every row its OWN row_index. The yrp Stock Entry desk form does NOT
            # render the flat child table — its Vue grid renders group_items_for_ui(items)
            # (pushed via onload -> __onload.item_details), which groups rows by row_index
            # and builds each group from its FIRST row's parent item. Left unset, the Int
            # column defaults every row to 0, so two different parent items collapse into a
            # single grouped entry and all rows but the first silently vanish from the form
            # (data + total_amount stay correct — this is a pure display bug). One distinct
            # row_index per row keeps every (item, lot, qty) visible. This is per ROW (not per
            # logical item as a desk-created SE would do): intentional — it favours completeness
            # (every row rendered, even same-parent sizes as separate entries) over the merged
            # size-grid, and is the only safe choice since same-item different-lot rows must not
            # share a row_index (dimensions are read from the group's first row only).
            for idx, r in enumerate(items):
                se.append("items", {
                    "item": r["item_variant"], "qty": flt(r.get("qty")), "uom": r.get("uom") or None,
                    "lot": r["lot"], "received_type": "Accepted", "conversion_factor": 1.0,
                    "rate": flt(r.get("rate")) if r.get("rate") is not None else 0,
                    "row_index": idx, "table_index": 0,
                    "remarks": _("mrp GRN {0}").format(source_grn)})
            se.insert(ignore_permissions=True)
            se.submit()
            frappe.db.commit()
            return {"ok": True, "stock_entry": se.name, "warehouse": warehouse,
                    "duplicate": False, "message": _("Stock received on essdee_yrp.")}

    except Exception:
        frappe.db.rollback()
        frappe.log_error(title="essdee_yrp receive_grn_transfer", message=frappe.get_traceback())
        msg = frappe.local.message_log[-1].get("message") if frappe.local.message_log \
            else _("Unexpected error creating the essdee_yrp Stock Entry.")
        return {"ok": False, "error": frappe.utils.strip_html(str(msg))}


@frappe.whitelist()
def cancel_grn_transfer(source_grn):
    """Cancel the yrp Material Receipt created for `source_grn` (reverses its SLEs).
    Idempotent: a missing or already-cancelled SE returns ok."""
    # Authorization gate before the cancel (reverses stock ledger entries). Raised
    # OUTSIDE the try so an unauthorized caller gets a real PermissionError (403).
    frappe.has_permission("Stock Entry", "cancel", throw=True)
    try:
        if not source_grn:
            return {"ok": False, "error": _("source_grn is required.")}
        name = frappe.db.get_value("Stock Entry", {"source_grn": source_grn, "docstatus": 1}, "name")
        if name:
            se = frappe.get_doc("Stock Entry", name)
            # Mark this as the legitimate mrp GRN-cancel path so the before_cancel
            # guard (guard_transfer_se_cancel) lets a source_grn SE cancel here.
            se.flags.from_grn_transfer = True
            se.cancel()
            frappe.db.commit()
            return {"ok": True, "stock_entry": name, "message": _("essdee_yrp Stock Entry cancelled.")}
        if frappe.db.exists("Stock Entry", {"source_grn": source_grn, "docstatus": 2}):
            return {"ok": True, "stock_entry": None, "message": _("Already cancelled (idempotent).")}
        return {"ok": True, "stock_entry": None, "message": _("No yrp Stock Entry to cancel.")}
    except Exception:
        frappe.db.rollback()
        frappe.log_error(title="essdee_yrp cancel_grn_transfer", message=frappe.get_traceback())
        msg = frappe.local.message_log[-1].get("message") if frappe.local.message_log \
            else _("Unexpected error cancelling the essdee_yrp Stock Entry.")
        return {"ok": False, "error": frappe.utils.strip_html(str(msg))}


def guard_transfer_se_cancel(doc, method=None):
    """before_cancel guard (hooked in essdee_yrp.hooks.doc_events).

    A Stock Entry that was created by the cross-bench GRN transfer carries
    `source_grn`. Such an SE must be cancelled ONLY by the mrp GRN-cancel flow,
    which reaches yrp via `cancel_grn_transfer` and sets
    `doc.flags.from_grn_transfer = True` just before cancelling. Any other cancel
    path (desk button, direct API .cancel()) is blocked so the mrp GRN and the yrp
    Material Receipt cannot drift out of sync.
    """
    if doc.get("source_grn") and not doc.flags.get("from_grn_transfer"):
        frappe.throw(_("This Stock Entry was created from an mrp GRN transfer; "
                       "cancel it by cancelling the source GRN in mrp."))
