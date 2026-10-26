import os
from collections import defaultdict

import frappe
from frappe.utils import flt, now_datetime

from essdee_yrp.migration.cpd_import.importer import GRN_NOT_FOUND, SOURCE_KEYS, TARGET
from essdee_yrp.migration.cpd_import.masters import ImportBlocked

WATCH = [
	("Yarn 34's GL-Greige", "S-0005", "F0826-37"),
	("Yarn 30's VL-Greige", "S-0005", "F0826-36"),
]


class Verifier:
	"""Compare the imported target docs with the CPD source rows."""

	def __init__(self, importer):
		self.importer = importer
		self.data = importer.data
		self.names = importer.names
		self.lines = []

	def new_name(self, source_doctype, old):
		return self.names.get(source_doctype, {}).get(old)

	def item(self, name):
		try:
			return self.importer.item(name)
		except ImportBlocked:
			return name

	def table(self, header, rows):
		self.lines.append("| " + " | ".join(header) + " |")
		self.lines.append("|" + "---|" * len(header))
		for row in rows:
			self.lines.append("| " + " | ".join(str(c) for c in row) + " |")
		self.lines.append("")

	def run(self):
		self.counts()
		self.mrp_pairs()
		self.sle_per_voucher()
		self.balances()
		self.watch_buckets()
		self.work_order_pending()
		self.fabric_conversions()
		return self.lines

	def counts(self):
		self.lines.append("## Verification: doc counts\n")
		rows = []
		for source_doctype, key in SOURCE_KEYS.items():
			source = self.data["docs"][key]
			imported = [d["name"] for d in source if self.new_name(source_doctype, d["name"])]
			target_ok = [
				n
				for n in (self.new_name(source_doctype, o) for o in imported)
				if frappe.db.get_value(TARGET[source_doctype], n, "docstatus") == 1
			]
			rows.append(
				[source_doctype, len(source), len(imported), len(target_ok), len(source) - len(imported)]
			)
		self.table(
			["Doctype", "Source submitted", "Imported (mapped)", "Target submitted", "Not imported"], rows
		)

	def mrp_pairs(self):
		self.lines.append("## Verification: Stock Entry vs MRP GRN rule\n")
		rows = []
		for se in self.data["docs"]["stock_entries"]:
			grn = se.get("source_grn")
			values = (
				frappe.db.get_value(
					"YRP Goods Received Note",
					grn,
					["essdee_yrp_stock_entry_created", "mrp_material_issue_ref", "essdee_yrp_stock_entry"],
					as_dict=True,
				)
				if grn
				else None
			)
			new = self.new_name("Stock Entry", se["name"])
			if not values:
				rule = f"import ({GRN_NOT_FOUND})" if grn else "import (no GRN cited)"
			elif values.essdee_yrp_stock_entry_created or values.mrp_material_issue_ref:
				rule = "import (MRP issued stock out)"
			else:
				rule = "skip (stock still on target)"
			rows.append(
				[
					se["name"],
					grn or "-",
					rule,
					new or "skipped",
					"-"
					if not values
					else f"{values.essdee_yrp_stock_entry_created} / {values.mrp_material_issue_ref or '-'} / {values.essdee_yrp_stock_entry or '-'}",
				]
			)
		self.table(
			[
				"Source STE",
				"MRP GRN",
				"Rule",
				"Target STE",
				"GRN created flag / issue ref / essdee_yrp_stock_entry",
			],
			rows,
		)

	def source_sles(self):
		return [r for r in self.data["source_sles"] if not r.get("is_cancelled")]

	def sle_per_voucher(self):
		self.lines.append(
			f"## Verification: SLE count and qty per voucher ({len(self.source_sles())} source SLEs)\n"
		)
		grouped = defaultdict(list)
		for sle in self.source_sles():
			grouped[(sle["voucher_type"], sle["voucher_no"])].append(sle)
		rows, total_diffs = [], 0
		for (vtype, vno), sles in sorted(grouped.items()):
			new = self.new_name(vtype, vno)
			src_qty = round(sum(flt(s["qty"]) for s in sles), 3)
			if not new:
				rows.append([vtype, vno, "not imported", len(sles), src_qty, "-", "-", "n/a"])
				continue
			tgt = frappe.db.sql(
				"select count(*), coalesce(sum(qty),0) from `tabYRP Stock Ledger Entry` "
				"where voucher_type=%s and voucher_no=%s and is_cancelled=0",
				(TARGET[vtype], new),
			)[0]
			diff = self.bucket_diff(sles, TARGET[vtype], new)
			total_diffs += bool(diff) or tgt[0] != len(sles)
			rows.append([vtype, vno, new, len(sles), src_qty, tgt[0], round(flt(tgt[1]), 3), diff or "OK"])
		self.table(
			["Type", "Source", "Target", "Src SLEs", "Src qty", "Tgt SLEs", "Tgt qty", "Per item/wh/lot"],
			rows,
		)
		self.lines.append(f"Vouchers with a difference: {total_diffs}\n")

	def bucket_diff(self, sles, vtype, new):
		src = defaultdict(float)
		for s in sles:
			src[(self.item(s["item"]), s["warehouse"], s.get("lot"))] += flt(s["qty"])
		tgt = defaultdict(float)
		for r in frappe.db.sql(
			"select item, warehouse, lot, qty from `tabYRP Stock Ledger Entry` "
			"where voucher_type=%s and voucher_no=%s and is_cancelled=0",
			(vtype, new),
			as_dict=True,
		):
			tgt[(r.item, r.warehouse, r.lot)] += flt(r.qty)
		diffs = [
			f"{k}: src {round(src.get(k, 0), 3)} tgt {round(tgt.get(k, 0), 3)}"
			for k in set(src) | set(tgt)
			if abs(src.get(k, 0) - tgt.get(k, 0)) > 0.001
		]
		return "; ".join(sorted(diffs))

	def balances(self):
		self.lines.append("## Verification: stock balance per item / location / lot\n")
		self.lines.append(
			f"Source = net of all {len(self.source_sles())} source SLEs. Imported = net of target SLEs posted by imported vouchers. Target total = whole target bucket (includes MRP stock already there).\n"
		)
		src, imported = defaultdict(float), defaultdict(float)
		vouchers = []
		for sle in self.source_sles():
			src[(self.item(sle["item"]), sle["warehouse"], sle.get("lot"))] += flt(sle["qty"])
			new = self.new_name(sle["voucher_type"], sle["voucher_no"])
			if new:
				vouchers.append((TARGET[sle["voucher_type"]], new))
		for vtype, vno in set(vouchers):
			for r in frappe.db.sql(
				"select item, warehouse, lot, qty from `tabYRP Stock Ledger Entry` "
				"where voucher_type=%s and voucher_no=%s and is_cancelled=0",
				(vtype, vno),
				as_dict=True,
			):
				imported[(r.item, r.warehouse, r.lot)] += flt(r.qty)
		rows, diffs = [], 0
		for key in sorted(set(src) | set(imported), key=str):
			total = target_balance(*key)
			if abs(src.get(key, 0) - imported.get(key, 0)) <= 0.001:
				check = "OK"
			elif abs(src.get(key, 0) - total) <= 0.001:
				check = "OK via target total (stock from MRP GRN; CPD receipt skipped as duplicate)"
			else:
				check = "DIFF"
				diffs += 1
			rows.append(
				[*key, round(src.get(key, 0), 3), round(imported.get(key, 0), 3), round(total, 3), check]
			)
		self.table(["Item", "Warehouse", "Lot", "Source", "Imported", "Target total", "Check"], rows)
		self.lines.append(f"Buckets where the target total differs from the source: {diffs}\n")

	def watch_buckets(self):
		self.lines.append("## Verification: F0826-36 / F0826-37 yarn at S-0005\n")
		rows = []
		for item, warehouse, lot in WATCH:
			for r in frappe.db.sql(
				"select posting_date, posting_time, voucher_type, voucher_no, qty, qty_after_transaction "
				"from `tabYRP Stock Ledger Entry` where item=%s and warehouse=%s and lot=%s and is_cancelled=0 "
				"order by posting_datetime, creation",
				(item, warehouse, lot),
				as_dict=True,
			):
				rows.append(
					[
						item,
						lot,
						r.posting_date,
						str(r.posting_time)[:8],
						r.voucher_type,
						r.voucher_no,
						r.qty,
						r.qty_after_transaction,
					]
				)
			rows.append(
				[item, lot, "**final**", "", "", "", "", round(target_balance(item, warehouse, lot), 3)]
			)
		self.table(["Item", "Lot", "Date", "Time", "Voucher type", "Voucher", "Qty", "Balance after"], rows)

	def work_order_pending(self):
		self.lines.append("## Verification: Work Order pending quantities\n")
		rows, diffs = [], 0
		row_map = self.importer.row_map
		for wo in self.data["docs"]["work_orders"]:
			new = self.new_name("Work Order", wo["name"])
			for table, doctype in (
				("deliverables", "YRP Work Order Deliverables"),
				("receivables", "YRP Work Order Receivables"),
			):
				for row in wo[table]:
					new_row = row_map.get(row["name"]) if new else None
					tgt = frappe.db.get_value(doctype, new_row, "pending_quantity") if new_row else None
					ok = tgt is not None and abs(flt(tgt) - flt(row.get("pending_quantity"))) <= 0.001
					diffs += new is not None and not ok
					rows.append(
						[
							wo["name"],
							new or "not imported",
							table,
							row["item_variant"],
							row["qty"],
							row.get("pending_quantity", 0),
							"-" if tgt is None else tgt,
							"OK" if ok else ("DIFF" if new else "-"),
						]
					)
			if new:
				status = frappe.db.get_value("YRP Work Order", new, "status")
				rows.append(
					[
						wo["name"],
						new,
						"status",
						"",
						"",
						wo.get("status"),
						status,
						"OK" if status == wo.get("status") else "DIFF",
					]
				)
		self.table(
			["Source WO", "Target WO", "Table", "Item", "Qty", "Src pending", "Tgt pending", "Check"], rows
		)
		self.lines.append(f"Rows with a difference: {diffs}\n")

	def fabric_conversions(self):
		source = self.data["source_lot_fabric_conversions"]
		self.lines.append(f"## Verification: Lot fabric conversion ({len(source)} source rows)\n")
		lots = sorted({r["lot"] for r in source})
		target = frappe.get_all(
			"SD YRP Lot Fabric Conversion",
			filters={"parent": ["in", lots]},
			fields=[
				"parent",
				"process_name",
				"planned_item",
				"actual_item",
				"actual_quantity",
				"route_item",
				"production_detail",
				"received_type",
			],
		)

		def key(lot, process, planned, actual, route):
			return (lot, process, self.item(planned), self.item(actual), self.item(route))

		src = defaultdict(float)
		for r in source:
			src[key(r["lot"], r["process_name"], r["from_item"], r["to_item"], r["route_item"])] += flt(
				r["to_qty"]
			)
		tgt = defaultdict(float)
		for r in target:
			tgt[(r.parent, r.process_name, r.planned_item, r.actual_item, r.route_item)] += flt(
				r.actual_quantity
			)
		rows, diffs = [], 0
		for k in sorted(set(src) | set(tgt), key=lambda k: tuple(str(x) for x in k)):
			ok = abs(src.get(k, 0) - tgt.get(k, 0)) <= 0.001
			diffs += not ok
			rows.append([*k, src.get(k, "-"), tgt.get(k, "-"), "OK" if ok else "DIFF"])
		self.table(
			["Lot", "Process", "Planned (from)", "Actual (to)", "Route item", "Src qty", "Tgt qty", "Check"],
			rows,
		)
		self.lines.append(
			f"Source rows {len(source)}, target rows {len(target)}, keys with a difference: {diffs}\n"
		)
		totals = defaultdict(lambda: [0.0, 0.0])
		for k, qty in src.items():
			totals[k[:2]][0] += qty
		for k, qty in tgt.items():
			totals[k[:2]][1] += qty
		self.table(
			["Lot", "Process", "Source total qty", "Target total qty"],
			[[*k, round(v[0], 3), round(v[1], 3)] for k, v in sorted(totals.items())],
		)


def target_balance(item, warehouse, lot):
	return flt(
		frappe.db.sql(
			"select coalesce(sum(qty),0) from `tabYRP Stock Ledger Entry` where item=%s and warehouse=%s "
			"and ifnull(lot,'')=ifnull(%s,'') and is_cancelled=0",
			(item, warehouse, lot),
		)[0][0]
	)


def get_report_lines(importer, mode, verification, extra=()):
	log = importer.log
	verb = "Would create" if mode.startswith("dry") else "Created"
	lines = [f"# CPD import {mode} ({frappe.local.site}, {now_datetime()})\n", "## Summary\n"]
	lines += table(["Doctype", verb, "Skipped", "Failed"], get_summary_rows(log))
	lines += [f"## {verb} (old -> new)\n"]
	lines += table(["Doctype", "Old", "New"], [[r["doctype"], r["old"], r["new"]] for r in log["created"]])
	lines += ["## Skipped\n"]
	lines += table(
		["Doctype", "Old", "Target", "Reason"],
		[[r["doctype"], r["old"], r.get("new", "-"), r["reason"]] for r in log["skipped"]],
	)
	lines += ["## Failed\n"]
	lines += table(
		["Doctype", "Old", "Lot", "Error", "Rolled back"],
		[
			[
				r["doctype"],
				r["old"],
				r.get("lot", "-"),
				r["error"].replace("|", "/").replace("\n", " "),
				", ".join(r.get("rolled_back", [])) or "-",
			]
			for r in log["failed"]
		],
	)
	lines += [
		f"## Stock Entries imported with {GRN_NOT_FOUND}\n",
		"The cited MRP GRN does not exist here, so the CPD receipt is the only receipt and is imported.\n",
	]
	lines += table(
		["Source STE", "MRP GRN", "Target STE", "Status"],
		importer.get_grn_not_found_rows(),
	)
	lines += ["## Notes\n", *([f"- {n}" for n in log["notes"]] or ["- none"]), ""]
	return [*lines, *extra, *verification]


def get_summary_rows(log):
	rows = defaultdict(lambda: [0, 0, 0])
	for index, key in enumerate(("created", "skipped", "failed")):
		for row in log[key]:
			rows[row["doctype"]][index] += 1
	totals = [sum(r[i] for r in rows.values()) for i in range(3)]
	return [*([k, *v] for k, v in sorted(rows.items())), ["**Total**", *totals]]


def table(header, rows):
	rows = rows or [["-"] * len(header)]
	lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
	lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
	return [*lines, ""]


def write_report(lines, mode):
	"""Write the report under the site's private folder and return its path."""
	folder = frappe.get_site_path("private", "cpd_import")
	os.makedirs(folder, exist_ok=True)
	path = os.path.abspath(os.path.join(folder, f"{mode}_{now_datetime():%Y%m%d_%H%M%S}.md"))
	with open(path, "w") as handle:
		handle.write("\n".join(lines) + "\n")
	return path


def print_summary(importer, mode, path):
	log = importer.log
	print(f"\n=== CPD import {mode}: {frappe.local.site} ===")
	for doctype, created, skipped, failed in get_summary_rows(log):
		print(
			f"{doctype:<24} {'create' if mode.startswith('dry') else 'created'} {created:>3}  "
			f"skipped {skipped:>3}  failed {failed:>3}"
		)
	for row in log["failed"]:
		print("FAILED", row["doctype"], row["old"], row.get("lot", ""), row["error"][:300])
	for row in importer.get_grn_not_found_rows():
		print(GRN_NOT_FOUND.upper(), *row[:3])
	print("REPORT", path)
