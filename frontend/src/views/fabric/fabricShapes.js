/**
 * fabricShapes.js — shared shape/summary/draft logic for the /web Fabric
 * Processes entry (IPD).
 *
 * RE-PORT of the Desk master-detail entry:
 *   Desk reference: essdee_yrp/public/js/Fabric/FabricProcesses.vue
 *     (2026-07-07 UI rebuild — the byte-truth for behavior).
 *
 * Byte-faithful (data contracts + algorithms):
 *   - shapeOf / hasConversion / ratioLabel — card classification from the
 *     persisted sibling child tables (fabric_processes + fabric_value_mappings,
 *     roles Change / Introduce / Pin / Consume, keyed sequence + mapping_index).
 *   - shortSummaryOf — the ultra-compact glance label on each process card
 *     (which attributes change + rule count; full detail lives in the editor).
 *   - blankDraft / blankGroup / blankRule / isCompleteRule / crossProduct /
 *     buildStepFromDraft — the editor draft model and the EXACT mapping-row
 *     emission on save (rules mode, chips cross-product, change groups with
 *     one Pin per rule).
 *
 * Adapted for /web:
 *   - frappe.utils.escape_html → local esc(); __() → plain English strings
 *     (the /web SPA carries no translation layer).
 */

export const num = (v) => (v == null || v === "" ? 0 : Number(v));

export const esc = (v) =>
	String(v == null ? "" : v)
		.replace(/&/g, "&amp;")
		.replace(/</g, "&lt;")
		.replace(/>/g, "&gt;")
		.replace(/"/g, "&quot;");

// ---- shape / card display (Desk shapeOf / hasConversion / ratioLabel) ------

export function shapeOf(step) {
	const hasIntro = step.mappings.some((m) => m.role === "Introduce");
	const hasConsume = step.mappings.some((m) => m.role === "Consume");
	const changeAttrs = new Set(step.mappings.filter((m) => m.role === "Change").map((m) => m.attribute));
	if (hasIntro || hasConsume || (step.input_item && step.output_item && step.input_item !== step.output_item))
		return { key: "conv", label: "Item conversion" };
	if (changeAttrs.size > 1) return { key: "combo", label: "Combination" };
	if (changeAttrs.size === 1) return { key: "swap", label: "Attribute swap" };
	return { key: "idle", label: "Identity" };
}

export function hasConversion(step) {
	return step.input_item && step.output_item && step.input_item !== step.output_item;
}

export function ratioLabel(step) {
	const r = Number(step.quantity_ratio);
	return r && r !== 1 ? `×${r} out/in` : "";
}

// Ultra-compact card label for the floor user — just WHICH attributes change
// and how many rules, no from→to detail. Plain text (bind with {{ }}). The full
// rule breakdown lives in the Edit pop-up (FabricStepEditor). Keeps each card to
// a glance instead of a wall of letters.
export function shortSummaryOf(step) {
	const key = shapeOf(step).key;
	if (key === "idle") return "No change";
	const n = new Set(step.mappings.map((m) => num(m.mapping_index))).size;
	const suffix = n > 1 ? ` · ${n} rules` : "";
	if (key === "conv") {
		const intro = [...new Set(step.mappings.filter((m) => m.role === "Introduce").map((m) => m.attribute))];
		if (intro.length) return `Adds ${intro.join(", ")}${suffix}`;
		return step.output_item ? `→ ${step.output_item}` : "Converts";
	}
	const attrs = [...new Set(step.mappings.filter((m) => m.role === "Change").map((m) => m.attribute))];
	return `${attrs.join(", ") || "—"}${suffix}`;
}

// ---- editor draft model (Desk blankDraft / blankGroup / blankRule) ---------

export function blankDraft(process, seq, shapeKey, changeAttrs, { item, defaultInput, attributes }) {
	return {
		index: null,
		sequence: seq,
		fabric_process: process,
		shapeKey,
		input_item: shapeKey === "conv" ? (defaultInput || "") : (item || ""),
		output_item: item || "",
		quantity_ratio: 1,
		// conversion
		introduce: [{ attr: attributes.includes("Dia") ? "Dia" : (attributes[0] || ""), chips: [], input: "" }],
		// conversion, rules mode — consumed INPUT attributes + per-rule correspondence
		consume_attrs: [],
		rules: [],
		// change
		change_attrs: (changeAttrs && changeAttrs.length ? changeAttrs.slice() : [attributes[0] || ""]).filter(Boolean),
		groups: [],
		pin_attr: "",
	};
}

export function blankGroup(attrs) {
	const g = {};
	(attrs || []).forEach((a) => { g[a] = { from: "", to: "" }; });
	// Per-rule held value ("__" prefix so it can never collide with an
	// attribute key living on the same object). Blank = any.
	g.__pin = "";
	return g;
}

// A rule pairs one consumed input combination with one produced output
// combination. Missing keys read as "" (v-model creates them on first type).
export function blankRule(d) {
	const r = { in: {}, out: {} };
	d.consume_attrs.forEach((a) => { r.in[a] = ""; });
	d.introduce.map((x) => x.attr).filter(Boolean).forEach((a) => { r.out[a] = ""; });
	return r;
}

// Complete = every consumed from-value AND every introduced to-value filled.
// No introduced attribute at all is still complete — that DROPS the consumed
// attribute (consume it, introduce no replacement).
export function isCompleteRule(d, r) {
	return (
		d.consume_attrs.filter(Boolean).every((a) => r.in && r.in[a]) &&
		d.introduce.map((x) => x.attr).filter(Boolean).every((a) => r.out && r.out[a])
	);
}

export function crossProduct(lists) {
	return lists.reduce((acc, list) => {
		const out = [];
		acc.forEach((a) => list.forEach((v) => out.push([...a, v])));
		return out;
	}, [[]]);
}

// ---- build the persisted step from a draft (Desk saveDraft, minus the
// chip-input commit — the editor commits pending chip inputs before calling).
export function buildStepFromDraft(d, itemName) {
	const mappings = [];

	if (d.shapeKey === "conv" && d.consume_attrs.length) {
		// RULES MODE — one mapping_index per COMPLETE rule (incomplete rules are
		// filtered exactly like the Change branch filters groups): Consume rows
		// stamp the consumed input values, Introduce rows the produced output.
		const consAttrs = d.consume_attrs.filter(Boolean);
		const introAttrs = d.introduce.map((x) => x.attr).filter(Boolean);
		const validRules = d.rules.filter((r) => isCompleteRule(d, r));
		validRules.forEach((r, idx) => {
			consAttrs.forEach((a) => {
				mappings.push({ mapping_index: idx, attribute: a, role: "Consume", from_value: r.in[a], to_value: "" });
			});
			introAttrs.forEach((a) => {
				mappings.push({ mapping_index: idx, attribute: a, role: "Introduce", from_value: "", to_value: r.out[a] });
			});
		});
	} else if (d.shapeKey === "conv") {
		// Cross-product the introduced value sets into one group per combination;
		// each combination stamps every introduced attribute (Introduce, output-only).
		const active = d.introduce.filter((x) => x.attr && x.chips.length);
		const combos = active.length ? crossProduct(active.map((x) => x.chips)) : [];
		combos.forEach((combo, idx) => {
			active.forEach((x, k) => {
				mappings.push({ mapping_index: idx, attribute: x.attr, role: "Introduce", from_value: "", to_value: combo[k] });
			});
		});
	} else if (d.shapeKey === "change") {
		const validGroups = d.groups.filter((g) => d.change_attrs.every((a) => g[a] && g[a].from && g[a].to));
		validGroups.forEach((g, idx) => {
			d.change_attrs.forEach((a) => {
				mappings.push({ mapping_index: idx, attribute: a, role: "Change", from_value: g[a].from, to_value: g[a].to });
			});
			// One Pin per rule: the hold ATTRIBUTE is step-wide, the held VALUE is
			// this rule's own ("when <attr> = …", blank = any/wildcard). Emitted
			// after the Change rows with the same mapping_index — matching the
			// seeded order so an untouched open→save round-trips identically.
			if (d.pin_attr) {
				const pv = g.__pin || "";
				mappings.push({ mapping_index: idx, attribute: d.pin_attr, role: "Pin", from_value: pv, to_value: pv });
			}
		});
	}

	return {
		sequence: d.sequence,
		fabric_process: d.fabric_process,
		input_item: d.shapeKey === "conv" ? d.input_item : (itemName || d.input_item || ""),
		output_item: d.shapeKey === "conv" ? d.output_item : (itemName || ""),
		quantity_ratio: d.shapeKey === "conv" ? (Number(d.quantity_ratio) || 1) : 1,
		mappings,
	};
}
