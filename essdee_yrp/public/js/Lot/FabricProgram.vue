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
					<table class="fp-table fp-matrix">
						<thead>
							<tr>
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
									{{ colour.label }}
								</th>
							</tr>
						</thead>
						<tbody>
							<tr v-for="dia in program_dias(entry)" :key="dia">
								<td class="fp-dia">{{ dia }}</td>
								<td
									v-for="colour in program_colour_columns(entry)"
									:key="colour.key"
									class="fp-num"
								>
									<input
										v-if="editable"
										:value="program_weight(entry, dia, colour.key)"
										type="number"
										min="0"
										step="0.001"
										class="fp-input"
										@change="set_program_weight(entry, dia, colour.key, $event.target.value)"
									/>
									<span v-else>{{ program_weight(entry, dia, colour.key) }}</span>
								</td>
								<td class="fp-num fp-program">{{ program_dia_total(entry, dia) }}</td>
							</tr>
							<tr v-if="!program_dias(entry).length">
								<td :colspan="program_colour_columns(entry).length + 2" class="fp-none">
									{{ __("No knitting program yet") }}
								</td>
							</tr>
							<tr v-else class="fp-total">
								<td>{{ __("Total") }}</td>
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
		program: entry.program || [],
		requirement: entry.requirement || [],
		steps: entry.steps || [],
	}));
}

function get_data() {
	return entries.value.map((entry) => ({
		cloth_item: entry.cloth_item,
		program: entry.program.map((r) => ({
			dia: r.dia,
			colour: r.colour || null,
			reference_item_variant: r.reference_item_variant || null,
			weight: r.weight || 0,
		})),
	}));
}

function get_requirement() {
	return entries.value.map((entry) => ({
		cloth_item: entry.cloth_item,
		requirement: entry.requirement.map((r) => ({
			dia: r.dia, colour: r.colour || null, weight: r.weight || 0,
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
	return row.finished_dia || row.dia || "";
}

function program_colour(row) {
	return row.finished_colour || row.colour || "";
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

function program_row(entry, dia, colour) {
	return entry.program.find(
		(row) => program_dia(row) === dia && program_colour(row) === colour);
}

function program_weight(entry, dia, colour) {
	return round_kg(program_row(entry, dia, colour)?.weight);
}

function set_program_weight(entry, dia, colour, value) {
	const weight = Math.max(0, Number(value) || 0);
	const row = program_row(entry, dia, colour);
	if (row) row.weight = weight;
	mark_dirty();
}

function program_colour_total(entry, colour) {
	return round_kg(entry.program.reduce(
		(sum, row) => sum + (program_colour(row) === colour ? Number(row.weight) || 0 : 0), 0));
}

function program_dia_total(entry, dia) {
	return round_kg(entry.program.reduce(
		(sum, row) => sum + (program_dia(row) === dia ? Number(row.weight) || 0 : 0), 0));
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
}
.fp-table th,
.fp-table td {
	border: 1px solid var(--border-color);
	padding: 4px 8px;
	text-align: left;
}
.fp-table th {
	background: var(--subtle-fg, transparent);
	font-weight: 500;
	color: var(--text-muted);
}
.fp-num {
	text-align: right !important;
	width: 90px;
}
.fp-dia {
	min-width: 105px;
	white-space: nowrap;
	font-weight: 500;
}
.fp-colour {
	min-width: 82px;
}
.fp-program {
	background: var(--subtle-fg, transparent);
	font-weight: 600;
}
.fp-total td {
	font-weight: 600;
	border-top: 2px solid var(--border-color);
}
.fp-input {
	width: 100%;
	border: none;
	background: transparent;
	text-align: right;
	outline: none;
}
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
