/**
 * fabricValues.js — shared Item Attribute Value autocomplete cache for the
 * /web Fabric Processes entry.
 *
 * Desk reference: essdee_yrp/public/js/Fabric/FabricProcesses.vue
 * (loadValues + valueCache — one fetch per attribute, failed fetch = []).
 * Adapted: frappe.db.get_list → getList REST helper; the datalist consumers
 * become PrimeVue AutoCompletes filtering the cached list client-side
 * (instant suggestions, no round-trip per keystroke). Free text stays allowed —
 * the server's Link validation is the final gate, exactly like the Desk.
 */
import { reactive } from "vue";
import { getList } from "@/api/client";

export const valueCache = reactive({});

export async function loadValues(attr) {
	if (!attr || valueCache[attr]) return;
	valueCache[attr] = [];
	try {
		const { data } = await getList("Item Attribute Value", {
			filters: { attribute_name: attr },
			fields: ["name"],
			order_by: "name asc",
			limit_page_length: 0,
		});
		valueCache[attr] = (data || []).map((r) => r.name);
	} catch (_) {
		valueCache[attr] = [];
	}
}

export function suggestionsFor(attr, query) {
	const vals = valueCache[attr] || [];
	const q = String(query || "").toLowerCase();
	return q ? vals.filter((v) => String(v).toLowerCase().includes(q)) : [...vals];
}
