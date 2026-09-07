"""Independent evidence for explicitly disclosed legacy-blank default fills.

This module never imports migration transformers or their reference-data
export. Expectations come from original SQL relationships, narrowly reviewed
business defaults, and the deployed schema/configuration. Unknown fills fail
closed. A verified fill is NOT an exact copy of the original blank.
"""

import json
from dataclasses import dataclass


@dataclass
class FillEvidence:
	rule: str
	by_name: dict | None = None
	constant: str | None = None

	def matches(self, identity, actual_values):
		expected = self.by_name.get(identity) if self.by_name is not None else self.constant
		return expected not in (None, "") and actual_values == [expected]


def _rows(connection, query, params=()):
	with connection.cursor() as cursor:
		cursor.execute(query, params)
		return list(cursor.fetchall())


def _ledger_references(payload):
	"""Only source JSON's explicit *_ref_docname references identify ledgers."""
	if isinstance(payload, str):
		try:
			payload = json.loads(payload)
		except (ValueError, TypeError):
			return set()
	if isinstance(payload, list):
		return set().union(*(_ledger_references(value) for value in payload))
	if not isinstance(payload, dict):
		return set()
	result = set()
	for key, value in payload.items():
		if key.endswith("_ref_docname") and value:
			result.add(str(value))
		else:
			result.update(_ledger_references(value))
	return result


class SourceDefaultEvidence:
	def __init__(self, source_db, plan, configured_defaults=None):
		self.source_db = source_db
		self.plan = plan
		self.configured_defaults = configured_defaults or {}
		self.cache = {}

	def prepare(self, route, source_field, target_fields):
		# Called BEFORE opening the streaming source cursor. Never issue another
		# source SQL query from the per-value comparison loop.
		key = (route.source_doctype, route.target_doctype, source_field, tuple(target_fields))
		if key not in self.cache:
			self.cache[key] = self._prepare(route, source_field, target_fields)
		return self.cache[key]

	def _root_group(self):
		rows = _rows(self.source_db, "SELECT name FROM `tabItem Group` WHERE IFNULL(parent_item_group, '')='' AND is_group=1")
		return rows[0]["name"] if len(rows) == 1 else None

	def _prepare(self, route, field, targets):
		doctype = route.source_doctype
		pair = (doctype, field)
		received_fields = {
			("Delivery Challan Item", "item_type"),
			("Goods Received Note Item", "received_type"),
			("Lot Transfer Item", "received_type"),
			("Stock Entry Detail", "received_type"),
			("Work Order Deliverables", "item_type"),
		}
		if pair in received_fields and targets == ["received_type"]:
			rows = _rows(self.source_db, "SELECT value FROM tabSingles WHERE doctype='Stock Settings' AND field='default_received_type'")
			return FillEvidence("Source Stock Settings.default_received_type for a legacy blank", constant=rows[0]["value"] if len(rows) == 1 else None)
		if targets != [field]:
			return None
		if pair == ("Item", "item_group"):
			return FillEvidence("Unique original root Item Group", constant=self._root_group())
		if pair == ("Lot BOM", "process_name"):
			configured = self.configured_defaults.get("Lot BOM.process_name")
			return FillEvidence("Explicit reviewed migration setting Lot BOM.process_name = Packing", constant="Packing" if configured == "Packing" else None)
		if pair in {("Stiching Item Detail", "category"), ("Lotwise Item Profit", "lot_costing_type")}:
			value = "Body" if field == "category" else "Costing"
			schema = self.plan.target_schemas[route.target_doctype]
			definition = next((row for row in schema["fields"] if row.get("fieldname") == field), {})
			options = [line.strip() for line in str(definition.get("options") or "").splitlines() if line.strip()]
			return FillEvidence("Reviewed legacy blank Select default: " + value,
				constant=value if definition.get("fieldtype") == "Select" and options and options[0] == value else None)
		if pair == ("Process", "item"):
			return FillEvidence("Reviewed Cutting process billing-item default", by_name={"Cutting": "Cutting Charges"})
		if pair == ("Product", "item_name"):
			rows = _rows(self.source_db, "SELECT name, style_no FROM tabProduct WHERE item_name IS NULL OR item_name=''")
			return FillEvidence("Original Product.style_no (original identity only if style_no blank)",
				by_name={row["name"]: row["style_no"] or row["name"] for row in rows})
		if pair == ("Goods Received Note", "lot"):
			rows = _rows(self.source_db, """SELECT g.name, MIN(NULLIF(i.lot, '')) AS expected
				FROM `tabGoods Received Note` g JOIN `tabGoods Received Note Item` i
				ON i.parent=g.name AND i.parenttype='Goods Received Note' AND i.parentfield='items'
				WHERE g.lot IS NULL OR g.lot='' GROUP BY g.name HAVING COUNT(DISTINCT NULLIF(i.lot, ''))=1""")
			return FillEvidence("Unique nonblank Lot across original GRN item rows; ambiguous headers stay blank",
				by_name={row["name"]: row["expected"] for row in rows})
		if pair == ("Purchase Invoice", "against"):
			rows = _rows(self.source_db, """SELECT p.name,
				EXISTS(SELECT 1 FROM `tabPI Work Order Billed Detail` w WHERE w.parent=p.name
				 AND w.parenttype='Purchase Invoice' AND w.parentfield='pi_work_order_billed_details') AS is_work_order,
				EXISTS(SELECT 1 FROM `tabPurchase Invoice GRN` g WHERE g.parent=p.name
				 AND g.parenttype='Purchase Invoice' AND g.parentfield='grn') AS has_grn
				FROM `tabPurchase Invoice` p WHERE p.against IS NULL OR p.against=''""")
			return FillEvidence("Original WO billed detail identifies WO; otherwise original GRN-backed invoice identifies PO",
				by_name={row["name"]: "YRP Work Order" if row["is_work_order"] else "YRP Purchase Order"
					for row in rows if row["is_work_order"] or row["has_grn"]})
		if pair in {("Purchase Order Item", "uom"), ("Lot BOM", "uom"), ("Purchase Invoice Item", "item_group")}:
			# Identifiers below are selected solely from the literal allowlist.
			item_column = {"Lot BOM": "item_name", "Purchase Order Item": "item_variant", "Purchase Invoice Item": "item"}[doctype]
			master_field = "default_unit_of_measure" if field == "uom" else "item_group"
			rows = _rows(self.source_db, f"""SELECT r.name, i.name AS source_item, i.`{master_field}` AS expected
				FROM `tab{doctype}` r LEFT JOIN `tabItem Variant` v ON v.name=r.`{item_column}`
				LEFT JOIN tabItem i ON i.name=COALESCE(NULLIF(v.item,''), r.`{item_column}`)
				WHERE r.`{field}` IS NULL OR r.`{field}`=''""")
			root = self._root_group() if field == "item_group" else None
			return FillEvidence("Original row Item Variant → Item." + master_field + ("; unique root if Item group blank" if root else ""),
				by_name={row["name"]: row["expected"] or root for row in rows if row["source_item"]})
		if pair == ("Cut Panel Movement", "from_warehouse"):
			rows = _rows(self.source_db, """SELECT c.name, c.cut_panel_movement_json,
				s.from_warehouse AS stock_source, d.from_location AS challan_source
				FROM `tabCut Panel Movement` c
				LEFT JOIN `tabStock Entry` s ON c.against='Stock Entry' AND s.name=c.against_id
				LEFT JOIN `tabDelivery Challan` d ON c.against='Delivery Challan' AND d.name=c.against_id
				WHERE c.from_warehouse IS NULL OR c.from_warehouse=''""")
			references = {row["name"]: _ledger_references(row["cut_panel_movement_json"]) for row in rows}
			names = sorted(set().union(*references.values()))
			ledgers = {}
			for offset in range(0, len(names), 500):
				batch = names[offset:offset + 500]
				selected = _rows(self.source_db, "SELECT name,supplier FROM `tabCut Bundle Movement Ledger` WHERE name IN (" + ",".join(["%s"] * len(batch)) + ")", batch)
				ledgers.update({row["name"]: row["supplier"] for row in selected})
			expected = {}
			for row in rows:
				candidates = {row["stock_source"], row["challan_source"]}
				candidates.update(ledgers.get(name) for name in references[row["name"]])
				candidates -= {None, ""}
				if len(candidates) == 1:
					expected[row["name"]] = next(iter(candidates))
			return FillEvidence("Unique original source warehouse from referenced Stock Entry/DC and explicitly linked bundle ledgers", by_name=expected)
		return None
