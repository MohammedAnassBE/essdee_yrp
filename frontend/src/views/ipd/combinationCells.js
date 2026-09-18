// Shared column/cell typing for the IPD combination grids (Cutting, Cloth,
// Accessory, Stiching-Accessory). Mirrors the Desk widgets' createInput()
// dispatch: a column is read-only when it is one of the CHECKED combination
// attributes (or a fixed label column); "Dia" picks Item Attribute Values of
// the Dia attribute; "Weight" is a float; "Required GSM" is an optional int;
// "Cloth" selects from the tab's select_list; everything else picks from the
// packing attribute's mapping.
import { callMethod, searchLink } from "@/api/client";

export const CELL = {
	RO: "ro",
	LINK_MAPPING: "link-mapping",
	LINK_DIA: "link-dia",
	FLOAT: "float",
	INT: "int",
	SELECT: "select",
};

export function cellKind(column, readOnlyColumns) {
	if ((readOnlyColumns || []).includes(column) || column === "Accessory") return CELL.RO;
	if (column === "Dia") return CELL.LINK_DIA;
	if (column === "Weight") return CELL.FLOAT;
	if (column === "Required GSM") return CELL.INT;
	if (column === "Cloth") return CELL.SELECT;
	return CELL.LINK_MAPPING;
}

// Item Attribute Value search restricted to an Item Item Attribute Mapping
// (Desk get_query → essdee_yrp.ipd_ui.get_attribute_detail_values).
export function mappingSearch(mapping) {
	return async (q) => {
		if (!mapping) return [];
		const res = await callMethod("essdee_yrp.ipd_ui.get_attribute_detail_values", {
			doctype: "Item Attribute Value",
			txt: q || "",
			searchfield: "name",
			start: 0,
			page_len: 20,
			filters: { mapping },
		});
		return (res || []).map((t) => ({ name: Array.isArray(t) ? t[0] : t }));
	};
}

// Dia values — plain Item Attribute Value search filtered by attribute (Desk
// filters: { attribute_name: "Dia" }).
export const diaSearch = (q) => searchLink("Item Attribute Value", q, { attribute_name: "Dia" });

// Required-cell check for a grid save: every cell must be filled except
// "Required GSM" (Desk CuttingItemDetail.get_data allows only that blank).
// Desk's loose `value == ""` check also treats a 0 Weight as blank — mirror it.
export function findBlankCell(items, columns) {
	for (const row of items || []) {
		for (const col of columns || []) {
			if (col === "Required GSM") continue;
			const v = row[col];
			if (v === null || v === undefined || v === "") return col;
			if (col === "Weight" && !Number(v)) return col;
		}
	}
	return null;
}

// Canonical (sorted-key) stringify for content-equality checks: stored JSON
// and a client-rebuilt candidate can differ in key ORDER while being the same
// data — writing such a value only pollutes the doc's Version trail.
export function stableStringify(v) {
	return JSON.stringify(v, (_k, val) =>
		val && typeof val === "object" && !Array.isArray(val)
			? Object.fromEntries(Object.entries(val).sort(([a], [b]) => a.localeCompare(b)))
			: val,
	);
}
