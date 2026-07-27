<template>
	<div class="fabric-program">
		<div v-if="!entries.length" class="fp-empty">
			{{ __("Add fabric rows above and save — the program grids appear per cloth.") }}
		</div>

		<div v-for="(entry, ei) in entries" :key="entry.cloth_item" class="fp-card">
			<header class="fp-head">
				<div class="fp-title">
					<b>{{ entry.cloth_item }}</b>
					<span class="fp-ipd">{{ entry.production_detail }}</span>
					<span v-if="plan_badge(entry)" class="fp-badge" :class="plan_badge(entry).cls">
						{{ plan_badge(entry).text }}
					</span>
				</div>
				<button
					v-if="ei === 0 && !is_new"
					class="btn btn-xs btn-default"
					:disabled="rebuilding"
					@click="rebuild"
				>
					{{ rebuilding ? __("Recalculating…") : __("Recalculate Received") }}
				</button>
			</header>

			<section class="fp-grid">
				<h6>{{ __("Finished cloth requirement — Dia × Colour") }}</h6>
				<div class="fp-table-wrap">
					<table class="fp-table fp-matrix">
						<thead>
							<tr>
								<th rowspan="2" class="fp-dia">{{ __("Finished Dia") }}</th>
								<th :colspan="colour_columns(entry).length">
									{{ __("Finished cloth requirement (Kg)") }}
								</th>
								<th rowspan="2" class="fp-num">{{ __("Total") }}</th>
							</tr>
							<tr>
								<th
									v-for="colour in colour_columns(entry)"
									:key="colour.key"
									class="fp-num fp-colour"
								>
									{{ colour.label }}
								</th>
							</tr>
						</thead>
						<tbody>
							<tr v-for="dia in requirement_dias(entry)" :key="dia">
								<td class="fp-dia">{{ dia }}</td>
								<td
									v-for="colour in colour_columns(entry)"
									:key="colour.key"
									class="fp-num"
								>
									<input
										v-if="editable"
										:value="requirement_weight(entry, dia, colour.key)"
										type="number"
										min="0"
										step="0.001"
										class="fp-input"
										@change="set_requirement_weight(entry, dia, colour.key, $event.target.value)"
									/>
									<span v-else>{{ requirement_weight(entry, dia, colour.key) }}</span>
								</td>
								<td class="fp-num fp-program">{{ requirement_dia_total(entry, dia) }}</td>
							</tr>
							<tr v-if="!requirement_dias(entry).length">
								<td :colspan="colour_columns(entry).length + 2" class="fp-none">
									{{ __("No cloth requirement yet") }}
								</td>
							</tr>
							<tr v-else class="fp-total">
								<td>{{ __("Total") }}</td>
								<td
									v-for="colour in colour_columns(entry)"
									:key="colour.key"
									class="fp-num"
								>
									{{ colour_total(entry, colour.key) }}
								</td>
								<td class="fp-num">{{ requirement_total(entry) }}</td>
							</tr>
						</tbody>
					</table>
				</div>

				<h6 class="fp-route-heading">{{ __("Knitting output plan — exact routes") }}</h6>
				<div class="fp-table-wrap">
					<table class="fp-table fp-route-table">
						<thead>
							<tr>
								<th>{{ __("Finished route") }}</th>
								<th>{{ __("Received from knitting as") }}</th>
								<th class="fp-num">{{ __("Planned Kg") }}</th>
								<th class="fp-num">{{ __("Received Kg") }}</th>
								<th class="fp-num">{{ __("Balance Kg") }}</th>
							</tr>
						</thead>
						<tbody>
							<tr v-for="(route, ri) in program_routes(entry)" :key="route.reference_item_variant || ri">
								<td>
									<strong>{{ route.finished_colour || __("Unspecified colour") }}</strong>
									<small>{{ route.finished_dia || __("No final Dia") }}</small>
								</td>
								<td>
									<strong>{{ route.knitting_output_colour || __("Unspecified colour") }}</strong>
									<small>{{ route.knitting_output_dia || __("No knitting Dia") }}</small>
								</td>
								<td class="fp-num">{{ round_kg(route.weight) }}</td>
								<td class="fp-num fp-received">{{ round_kg(route.received_weight) }}</td>
								<td class="fp-num">{{ route_balance(route) }}</td>
							</tr>
							<tr v-if="!program_routes(entry).length">
								<td colspan="5" class="fp-none">
									{{ entry.ipd_approved
										? __("Save requirements or rebuild the plan.")
										: __("Approve the cloth IPD to build its route plan.") }}
								</td>
							</tr>
							<tr v-else class="fp-total">
								<td colspan="2">{{ __("Total") }}</td>
								<td class="fp-num">{{ program_total(entry) }}</td>
								<td class="fp-num fp-received">{{ received_total(entry) }}</td>
								<td class="fp-num">{{ round_kg(program_total(entry) - received_total(entry)) }}</td>
							</tr>
						</tbody>
					</table>
				</div>
				<div v-if="!entry.ipd_approved" class="fp-hint">
					{{ __("Plan builds when the IPD is approved.") }}
				</div>
			</section>
		</div>
	</div>
</template>

<script setup>
// Lot Fabric island: finished-cloth requirements are pivoted by Dia × Colour,
// with the knitting program total and GRN-received kg at the right. The stored
// data remains the same long-form requirement/program payload used by the
// planner and Work Orders.
import { computed, ref } from "vue";

const entries = ref([]);
const rebuilding = ref(false);

// cur_frm reads are not reactive — these stay correct only because lot.js
// re-mounts this island on every form refresh (same as OCRDetail).
const editable = computed(() => {
	const doc = cur_frm ? cur_frm.doc : {};
	return (doc.status || "Open") === "Open";
});
const is_new = computed(() => Boolean(cur_frm && cur_frm.doc.__islocal));

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
	if (status === "Built") {
		const when = (entry.plan_built_on || "").slice(0, 10);
		return { text: __("Plan ready {0}", [when]), cls: "fp-badge--ok" };
	}
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

function requirement_dias(entry) {
	const values = [
		...(entry.final_options?.dias || []),
		...entry.requirement.map((row) => row.dia),
	].filter(Boolean);
	return [...new Set(values)].sort((a, b) =>
		dia_number(a) - dia_number(b) || String(a).localeCompare(String(b)));
}

function colour_columns(entry) {
	const values = [
		...entry.requirement.map((row) => row.colour),
		...(entry.colours || []),
		...(entry.final_options?.colours || []),
	].filter(Boolean);
	const colours = [...new Set(values)];
	return colours.length
		? colours.map((colour) => ({ key: colour, label: colour }))
		: [{ key: "", label: __("Requirement") }];
}

function requirement_row(entry, dia, colour) {
	return entry.requirement.find(
		(row) => row.dia === dia && (row.colour || "") === colour);
}

function requirement_weight(entry, dia, colour) {
	return round_kg(requirement_row(entry, dia, colour)?.weight);
}

function set_requirement_weight(entry, dia, colour, value) {
	const weight = Math.max(0, Number(value) || 0);
	const row = requirement_row(entry, dia, colour);
	if (row) {
		row.weight = weight;
	} else if (weight > 0) {
		entry.requirement.push({ dia, colour: colour || null, weight });
	}
	mark_dirty();
}

function colour_total(entry, colour) {
	return round_kg(entry.requirement.reduce(
		(sum, row) => sum + ((row.colour || "") === colour ? Number(row.weight) || 0 : 0), 0));
}

function requirement_dia_total(entry, dia) {
	return round_kg(entry.requirement.reduce(
		(sum, row) => sum + (row.dia === dia ? Number(row.weight) || 0 : 0), 0));
}

function requirement_total(entry) {
	return round_kg(entry.requirement.reduce(
		(sum, row) => sum + (Number(row.weight) || 0), 0));
}

function program_routes(entry) {
	return entry.program.slice().sort((a, b) =>
		String(a.finished_colour || "").localeCompare(String(b.finished_colour || ""))
		|| dia_number(a.finished_dia) - dia_number(b.finished_dia)
		|| String(a.finished_dia || "").localeCompare(String(b.finished_dia || "")));
}

function route_balance(route) {
	return round_kg(Math.max(
		(Number(route.weight) || 0) - (Number(route.received_weight) || 0),
		0,
	));
}

function program_total(entry) {
	return round_kg(entry.program.reduce((sum, row) => sum + (Number(row.weight) || 0), 0));
}

function received_total(entry) {
	return round_kg(entry.program.reduce(
		(sum, row) => sum + (Number(row.received_weight) || 0), 0));
}

function mark_dirty() {
	if (cur_frm) cur_frm.dirty();
}

function rebuild() {
	if (!cur_frm || cur_frm.doc.__islocal) return;
	if (cur_frm.is_dirty()) {
		frappe.show_alert({ message: __("Save the Lot first."), indicator: "orange" });
		return;
	}
	rebuilding.value = true;
	frappe.call({
		method: "essdee_yrp.fabric_tracking.rebuild_fabric_tracking",
		args: { lot: cur_frm.doc.name },
		callback() {
			cur_frm.reload_doc();
		},
		always() {
			rebuilding.value = false;
		},
	});
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
.fp-grid h6,
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
.fp-route-heading {
	margin-top: 14px !important;
}
.fp-route-table {
	min-width: 650px;
}
.fp-route-table td > strong,
.fp-route-table td > small {
	display: block;
}
.fp-route-table td > small {
	margin-top: 2px;
	color: var(--text-muted);
	font-size: 11px;
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
.fp-received {
	color: var(--text-muted);
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
.fp-hint {
	margin-top: 6px;
	color: var(--text-muted);
	font-size: 11.5px;
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
