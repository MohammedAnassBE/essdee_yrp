<template>
	<div class="fabric-program">
		<div v-if="!entries.length" class="fp-empty">
			{{ __("Add fabric rows above and save — the program grids appear per cloth.") }}
		</div>

		<div v-for="entry in entries" :key="entry.cloth_item" class="fp-card">
			<header class="fp-head">
				<div class="fp-title">
					<b>{{ entry.cloth_item }}</b>
					<span class="fp-ipd">{{ entry.production_detail }}</span>
					<span v-if="plan_badge(entry)" class="fp-badge" :class="plan_badge(entry).cls">
						{{ plan_badge(entry).text }}
					</span>
				</div>
			</header>

			<section class="fp-grid">
				<div class="fp-table-wrap">
					<table class="fp-table fp-matrix"
						:class="{ 'fp-matrix--compact': program_colour_columns(entry).length <= 2 }">
						<colgroup>
							<col class="fp-col-dia" />
							<col class="fp-col-dia" />
							<col
								v-for="colour in program_colour_columns(entry)"
								:key="colour.key"
								class="fp-col-value"
							/>
							<col class="fp-col-total" />
						</colgroup>
						<thead>
							<tr>
								<th rowspan="2" class="fp-dia">{{ __("Fabric Type") }}</th>
								<th rowspan="2" class="fp-dia">{{ __("Dia") }}</th>
								<th :colspan="program_colour_columns(entry).length">
									{{ __("Cloth Program (Kg)") }}
								</th>
								<th rowspan="2" class="fp-num">{{ __("Total") }}</th>
							</tr>
							<tr>
								<th
									v-for="colour in program_colour_columns(entry)"
									:key="colour.key"
									class="fp-num fp-colour"
								>
									<span>{{ colour.label }}</span>
									<span
										v-if="is_dyed_yarn_colour(entry, colour.key)"
										class="fp-dyed-yarn"
									>
										{{ __("Dyed Yarn") }}
									</span>
								</th>
							</tr>
						</thead>
						<tbody v-for="group in fabric_groups(entry)" :key="group.fabric_type">
							<tr v-for="line in group.lines" :key="line.fabric_type + line.dia">
								<td class="fp-dia">{{ line.fabric_type }}</td>
								<td class="fp-dia">{{ line.dia }}</td>
								<td
									v-for="colour in program_colour_columns(entry)"
									:key="colour.key"
									class="fp-num"
								>
									<input
										v-if="editable && is_owner_share(entry, line, colour.key)"
										:value="line_weight(entry, line, colour.key)"
										type="number"
										min="0"
										step="0.001"
										class="fp-input"
										@change="set_line_weight(entry, line, colour.key, $event.target.value)"
									/>
									<span v-else>{{ line_weight(entry, line, colour.key) }}</span>
								</td>
								<td class="fp-num fp-program">{{ line_total(entry, line) }}</td>
							</tr>
							<tr class="fp-subtotal">
								<td colspan="2">{{ __("Total {0}", [group.fabric_type]) }}</td>
								<td
									v-for="colour in program_colour_columns(entry)"
									:key="colour.key"
									class="fp-num"
								>
									{{ group_colour_total(entry, group, colour.key) }}
								</td>
								<td class="fp-num">{{ group_total(entry, group) }}</td>
							</tr>
							<tr v-if="has_add_weight(entry, group)" class="fp-add-weight">
								<td colspan="2">{{ __("Add Weight") }}</td>
								<td
									v-for="colour in program_colour_columns(entry)"
									:key="colour.key"
									class="fp-num"
								>
									{{ signed_kg(add_weight(entry, group, colour.key)) }}
								</td>
								<td class="fp-num">{{ signed_kg(add_weight_total(entry, group)) }}</td>
							</tr>
						</tbody>
						<tbody>
							<tr v-if="!program_dias(entry).length">
								<td :colspan="program_colour_columns(entry).length + 3" class="fp-none">
									{{ __("No knitting program yet") }}
								</td>
							</tr>
							<tr v-else class="fp-total">
								<td colspan="2">{{ __("Total") }}</td>
								<td
									v-for="colour in program_colour_columns(entry)"
									:key="colour.key"
									class="fp-num"
								>
									{{ program_colour_total(entry, colour.key) }}
								</td>
								<td class="fp-num">{{ program_total(entry) }}</td>
							</tr>
						</tbody>
					</table>
				</div>

			</section>
		</div>
	</div>
</template>

<script setup>
// Lot Fabric island: the UI shows the saved knitting program pivoted by
// Dia × Colour. The raw finished-cloth requirement remains in the payload for
// planning; visible weights include the operator-entered knitting excess.
import { computed, ref } from "vue";

const entries = ref([]);

// cur_frm reads are not reactive — these stay correct only because lot.js
// re-mounts this island on every form refresh (same as OCRDetail).
const editable = computed(() => {
	const doc = cur_frm ? cur_frm.doc : {};
	return (doc.status || "Open") === "Open";
});

function load_data(data) {
	entries.value = (data || []).map((entry) => ({
		...entry,
		additions: JSON.parse(JSON.stringify(entry.additions || {})),
		program: entry.program || [],
		requirement: entry.requirement || [],
		steps: entry.steps || [],
	}));
}

function get_data() {
	return entries.value.map((entry) => ({
		cloth_item: entry.cloth_item,
		program: entry.program.map((r) => ({
			dia: frappe.yrp.attribute_value(r.dia),
			colour: frappe.yrp.attribute_value(r.colour) || null,
			reference_item_variant: r.reference_item_variant || null,
			weight: r.weight || 0,
		})),
	}));
}

function get_requirement() {
	return entries.value.map((entry) => ({
		cloth_item: entry.cloth_item,
		requirement: entry.requirement.map((r) => ({
			dia: frappe.yrp.attribute_value(r.dia), colour: frappe.yrp.attribute_value(r.colour) || null, weight: r.weight || 0,
		})),
	}));
}

function plan_badge(entry) {
	const status = entry.plan_status || "";
	if (!status) return null;
	if (status === "Built") return null;
	if (status === "Pending Approval") return { text: __("Plan waiting for IPD approval"), cls: "fp-badge--wait" };
	if (status === "Stale") return { text: __("Plan outdated — IPD changed"), cls: "fp-badge--warn" };
	return { text: __("Plan error — open the fabric row"), cls: "fp-badge--err" };
}

function round_kg(value) {
	return Math.round((Number(value) || 0) * 1000) / 1000;
}

function dia_number(value) {
	const match = String(value || "").match(/-?\d+(?:\.\d+)?/);
	return match ? Number(match[0]) : Number.MAX_SAFE_INTEGER;
}

function program_dia(row) {
	return frappe.yrp.attribute_value(row.finished_dia) || frappe.yrp.attribute_value(row.dia) || "";
}

function program_colour(row) {
	return frappe.yrp.attribute_value(row.finished_colour) || frappe.yrp.attribute_value(row.colour) || "";
}

function program_dias(entry) {
	const values = entry.program.map(program_dia).filter(Boolean);
	return [...new Set(values)].sort((a, b) =>
		dia_number(a) - dia_number(b) || String(a).localeCompare(String(b)));
}

function program_colour_columns(entry) {
	const colours = [...new Set(entry.program.map(program_colour).filter(Boolean))]
		.sort((a, b) => String(a).localeCompare(String(b)));
	return colours.length
		? colours.map((colour) => ({ key: colour, label: colour }))
		: [{ key: "", label: __("Program") }];
}

function is_dyed_yarn_colour(entry, colour) {
	return (entry.dyed_yarn_colours || []).some(
		(value) => frappe.yrp.attribute_value(value) === colour);
}

function program_row(entry, dia, colour) {
	return entry.program.find(
		(row) => program_dia(row) === dia && program_colour(row) === colour);
}

// MRP splits each route into fabric types; accessory shares come from demand,
// so only the first (Main Fabric) share of a route is editable.
function fabric_shares(row) {
	return row.fabric_split || [{ fabric_type: "Main Fabric", weight: row.weight }];
}

function fabric_share(entry, line, colour) {
	const row = program_row(entry, line.dia, colour);
	return row && fabric_shares(row).find((share) => share.fabric_type === line.fabric_type);
}

function program_lines(entry) {
	const lines = new Map();
	for (const row of entry.program) {
		for (const share of fabric_shares(row)) {
			const line = { fabric_type: share.fabric_type, dia: program_dia(row) };
			lines.set(line.fabric_type + "\u0000" + line.dia, line);
		}
	}
	return [...lines.values()].sort((a, b) =>
		(a.fabric_type !== "Main Fabric") - (b.fabric_type !== "Main Fabric")
		|| a.fabric_type.localeCompare(b.fabric_type)
		|| dia_number(a.dia) - dia_number(b.dia) || String(a.dia).localeCompare(String(b.dia)));
}

function is_owner_share(entry, line, colour) {
	const row = program_row(entry, line.dia, colour);
	return !row || fabric_shares(row)[0].fabric_type === line.fabric_type;
}

function line_weight(entry, line, colour) {
	return round_kg(fabric_share(entry, line, colour)?.weight);
}

function line_total(entry, line) {
	return round_kg(program_colour_columns(entry).reduce(
		(sum, colour) => sum + (Number(fabric_share(entry, line, colour.key)?.weight) || 0), 0));
}

function set_line_weight(entry, line, colour, value) {
	const weight = Math.max(0, Number(value) || 0);
	const row = program_row(entry, line.dia, colour);
	if (!row) return;
	const share = fabric_share(entry, line, colour);
	if (row.fabric_split && share) {
		row.weight = (Number(row.weight) || 0) - (Number(share.weight) || 0) + weight;
		share.weight = weight;
	} else {
		row.weight = weight;
	}
	mark_dirty();
}

function fabric_groups(entry) {
	const groups = new Map();
	for (const line of program_lines(entry)) {
		if (!groups.has(line.fabric_type)) groups.set(line.fabric_type, { fabric_type: line.fabric_type, lines: [] });
		groups.get(line.fabric_type).lines.push(line);
	}
	return [...groups.values()];
}

function group_colour_total(entry, group, colour) {
	return round_kg(group.lines.reduce(
		(sum, line) => sum + (Number(fabric_share(entry, line, colour)?.weight) || 0), 0));
}

function group_total(entry, group) {
	return round_kg(group.lines.reduce((sum, line) => sum + line_total(entry, line), 0));
}

// Add Weight: saved whole kg per fabric type + colour (Build Cloth Program spreads it over the Dias).
function add_weight(entry, group, colour) {
	return Number(entry.additions[group.fabric_type]?.[colour]) || 0;
}

function has_add_weight(entry, group) {
	return program_colour_columns(entry).some((colour) => add_weight(entry, group, colour.key));
}

function add_weight_total(entry, group) {
	return program_colour_columns(entry).reduce((sum, colour) => sum + add_weight(entry, group, colour.key), 0);
}

function signed_kg(value) {
	return value > 0 ? `+${value}` : value ? String(value) : "—";
}

function program_colour_total(entry, colour) {
	return round_kg(entry.program.reduce(
		(sum, row) => sum + (program_colour(row) === colour ? Number(row.weight) || 0 : 0), 0));
}

function program_total(entry) {
	return round_kg(entry.program.reduce(
		(sum, row) => sum + (Number(row.weight) || 0), 0));
}

function mark_dirty() {
	if (cur_frm) cur_frm.dirty();
}

defineExpose({ load_data, get_data, get_requirement });
</script>

<style scoped>
.fabric-program {
	margin-top: 8px;
}
.fp-empty {
	color: var(--text-muted);
	font-size: 12.5px;
	padding: 4px 0 8px;
}
.fp-card {
	border: 1px solid var(--border-color);
	border-radius: 8px;
	margin-bottom: 12px;
	background: var(--card-bg, var(--fg-color));
	overflow: hidden;
}
.fp-head {
	display: flex;
	align-items: center;
	justify-content: space-between;
	padding: 8px 12px;
	border-bottom: 1px solid var(--border-color);
	background: var(--subtle-fg, transparent);
}
.fp-ipd {
	margin-left: 8px;
	color: var(--text-muted);
	font-size: 11.5px;
}
.fp-badge {
	margin-left: 10px;
	font-size: 11px;
	padding: 2px 8px;
	border-radius: 10px;
	font-weight: 500;
}
.fp-badge--ok { background: var(--green-100, #d1fadf); color: var(--green-700, #027a48); }
.fp-badge--wait { background: var(--blue-100, #d1e9ff); color: var(--blue-700, #175cd3); }
.fp-badge--warn { background: var(--orange-100, #fef0c7); color: var(--orange-700, #b54708); }
.fp-badge--err { background: var(--red-100, #fee4e2); color: var(--red-700, #b42318); }
.fp-grid {
	padding: 10px 12px;
	min-width: 0;
}
.fp-ledger h6 {
	font-size: 11.5px;
	text-transform: uppercase;
	letter-spacing: 0.04em;
	color: var(--text-muted);
	margin: 0 0 6px;
}
.fp-table {
	width: 100%;
	border-collapse: collapse;
	font-size: 12.5px;
}
.fp-table-wrap {
	overflow-x: auto;
}
.fp-matrix {
	min-width: 680px;
	table-layout: fixed;
}
.fp-col-dia {
	width: 150px;
}
.fp-col-total {
	width: 90px;
}
.fp-matrix--compact {
	width: min(680px, 100%);
	min-width: 480px;
}
.fp-table th,
.fp-table td {
	border: 1px solid var(--border-color);
	padding: 7px 10px;
	text-align: left;
}
.fp-table th {
	background: var(--subtle-fg, transparent);
	font-weight: 500;
	color: var(--text-muted);
}
.fp-num {
	text-align: right !important;
}
.fp-dia {
	white-space: nowrap;
	font-weight: 500;
}
.fp-matrix thead th {
	text-align: center;
	vertical-align: middle;
}
.fp-matrix thead .fp-dia {
	text-align: left;
}
.fp-matrix thead .fp-num {
	text-align: center !important;
}
.fp-colour {
	min-width: 0;
	line-height: 1.35;
}
.fp-dyed-yarn {
	display: flex;
	align-items: center;
	justify-content: center;
	width: max-content;
	margin: 4px auto 0;
	padding: 2px 7px;
	border-radius: 10px;
	background: var(--purple-100, #ebe9fe);
	color: var(--purple-700, #5925dc);
	font-size: 10px;
	font-weight: 600;
	line-height: 1.5;
	white-space: nowrap;
}
.fp-program {
	background: var(--subtle-fg, transparent);
	font-weight: 600;
}
.fp-subtotal td,
.fp-add-weight td {
	font-weight: 600;
	background: var(--subtle-fg, transparent);
}
.fp-total td {
	font-weight: 600;
	border-top: 2px solid var(--border-color);
}
.fp-input {
	width: 100%;
	padding: 4px 6px;
	border: 1px solid var(--border-color);
	border-radius: 5px;
	background: var(--control-bg, var(--fg-color));
	font-variant-numeric: tabular-nums;
	text-align: right;
	outline: none;
}
.fp-input:hover { border-color: var(--gray-400); }
.fp-input:focus { border-color: var(--primary); box-shadow: 0 0 0 2px var(--gray-100); }
.fp-none {
	color: var(--text-muted);
	text-align: center;
	font-size: 12px;
}
@media (max-width: 700px) {
	.fp-head {
		align-items: flex-start;
		gap: 8px;
	}
	.fp-title {
		display: flex;
		flex-direction: column;
		gap: 3px;
	}
	.fp-ipd,
	.fp-badge {
		margin-left: 0;
	}
	.fp-grid {
		padding: 8px;
	}
}
</style>
