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

			<div class="fp-grids">
				<section class="fp-grid">
					<h6>{{ __("Final Requirement — finished cloth") }}</h6>
					<table class="fp-table">
						<thead>
							<tr>
								<th>{{ __("Colour") }}</th>
								<th>{{ __("Dia") }}</th>
								<th class="fp-num">{{ __("Weight (Kg)") }}</th>
								<th v-if="editable" class="fp-x"></th>
							</tr>
						</thead>
						<tbody>
							<tr v-for="(row, ri) in entry.requirement" :key="(row.colour || '') + '::' + row.dia">
								<td>{{ row.colour || "—" }}</td>
								<td>{{ row.dia }}</td>
								<td class="fp-num">
									<input
										v-if="editable"
										v-model.number="row.weight"
										type="number"
										min="0"
										step="0.001"
										class="fp-input"
										@change="mark_dirty"
									/>
									<span v-else>{{ row.weight }}</span>
								</td>
								<td v-if="editable" class="fp-x">
									<button class="fp-remove" :title="__('Remove row')" @click="remove_row(entry.requirement, ri)">×</button>
								</td>
							</tr>
							<tr v-if="!entry.requirement.length">
								<td :colspan="editable ? 4 : 3" class="fp-none">{{ __("No requirement yet") }}</td>
							</tr>
							<tr v-if="entry.requirement.length" class="fp-total">
								<td colspan="2">{{ __("Total") }}</td>
								<td class="fp-num">{{ requirement_total(entry) }}</td>
								<td v-if="editable"></td>
							</tr>
						</tbody>
					</table>
					<div v-if="editable" class="fp-add">
						<select v-if="(entry.final_options?.colours || []).length" v-model="entry._new_r_colour" class="fp-select">
							<option value="">{{ __("Colour…") }}</option>
							<option v-for="c in entry.final_options.colours" :key="c" :value="c">{{ c }}</option>
						</select>
						<select v-model="entry._new_r_dia" class="fp-select">
							<option value="">{{ __("Dia…") }}</option>
							<option v-for="d in entry.final_options?.dias || []" :key="d" :value="d">{{ d }}</option>
						</select>
						<input
							v-model.number="entry._new_r_weight"
							type="number"
							min="0"
							step="0.001"
							class="fp-add-weight"
							:placeholder="__('Weight (Kg)')"
							@keyup.enter="add_requirement(entry)"
						/>
						<button
							class="btn btn-xs btn-default"
							:disabled="!entry._new_r_dia || ((entry.final_options?.colours || []).length && !entry._new_r_colour)"
							@click="add_requirement(entry)"
						>
							{{ __("Add") }}
						</button>
					</div>
					<div v-if="!entry.ipd_approved" class="fp-hint">
						{{ __("Plan builds when the IPD is approved.") }}
					</div>
				</section>

				<section class="fp-grid">
					<h6>{{ __("Program — dia-wise (greige to knit)") }}</h6>
					<table class="fp-table">
						<thead>
							<tr>
								<th>{{ __("Dia") }}</th>
								<th class="fp-num">{{ __("Weight (Kg)") }}</th>
								<th class="fp-num">{{ __("Received (Kg)") }}</th>
								<th v-if="editable" class="fp-x"></th>
							</tr>
						</thead>
						<tbody>
							<tr v-for="(row, ri) in entry.program" :key="row.dia">
								<td>{{ row.dia }}</td>
								<td class="fp-num">
									<input
										v-if="editable"
										v-model.number="row.weight"
										type="number"
										min="0"
										step="0.001"
										class="fp-input"
										@change="mark_dirty"
									/>
									<span v-else>{{ row.weight }}</span>
								</td>
								<td class="fp-num fp-received">{{ row.received_weight || 0 }}</td>
								<td v-if="editable" class="fp-x">
									<button
										v-if="!row.received_weight"
										class="fp-remove"
										:title="__('Remove row')"
										@click="remove_row(entry.program, ri)"
									>×</button>
								</td>
							</tr>
							<tr v-if="!entry.program.length">
								<td :colspan="editable ? 4 : 3" class="fp-none">{{ __("No program yet") }}</td>
							</tr>
						</tbody>
					</table>
					<div v-if="editable && remaining_dias(entry).length" class="fp-add">
						<select v-model="entry._new_dia" class="fp-select">
							<option value="">{{ __("Dia…") }}</option>
							<option v-for="d in remaining_dias(entry)" :key="d" :value="d">{{ d }}</option>
						</select>
						<input
							v-model.number="entry._new_weight"
							type="number"
							min="0"
							step="0.001"
							class="fp-add-weight"
							:placeholder="__('Weight (Kg)')"
							@keyup.enter="add_program(entry)"
						/>
						<button class="btn btn-xs btn-default" :disabled="!entry._new_dia" @click="add_program(entry)">
							{{ __("Add") }}
						</button>
					</div>
				</section>
			</div>
			<!-- The per-process (knitting/dyeing/compacting) chain plan-vs-received
			     view was intentionally removed from the Lot display (2026-07-07):
			     only the two fabric views above — Final Requirement (finished cloth)
			     and Program (dia-wise / dyed) — are shown. The chain is still fully
			     tracked in the backend (`lot_fabric_step_ledger` + the IPD matrices);
			     this is a display-hiding change only, not a data-model change. -->
		</div>
	</div>
</template>

<script setup>
// Lot Fabric island (fabric-chain plan, 2026-07-04): the user enters the FINAL
// REQUIREMENT (colour+dia+kg) and the knitting PROGRAM (dia+kg); the chain
// plan (per-step planned kgs) is back-computed on IPD approval and shown next
// to the GRN receipts. load_data(__onload payload); get_data()/get_requirement()
// feed the Lot's transient JSON fields.
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
		_new_dia: "",
		_new_weight: null,
		_new_r_dia: "",
		_new_r_colour: "",
		_new_r_weight: null,
	}));
}

function get_data() {
	return entries.value.map((entry) => ({
		cloth_item: entry.cloth_item,
		program: entry.program.map((r) => ({ dia: r.dia, weight: r.weight || 0 })),
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

function requirement_total(entry) {
	return Math.round(entry.requirement.reduce((sum, r) => sum + (Number(r.weight) || 0), 0) * 1000) / 1000;
}

function remaining_dias(entry) {
	const used = new Set(entry.program.map((r) => r.dia));
	return (entry.dias || []).filter((d) => !used.has(d));
}

function add_program(entry) {
	if (!entry._new_dia) return;
	entry.program.push({ dia: entry._new_dia, weight: Number(entry._new_weight) || 0, received_weight: 0 });
	entry._new_dia = "";
	entry._new_weight = null;
	mark_dirty();
}

function add_requirement(entry) {
	const dia = entry._new_r_dia;
	const colour = entry._new_r_colour || null;
	if (!dia) return;
	if (entry.requirement.some((r) => r.dia === dia && (r.colour || null) === colour)) {
		frappe.show_alert({ message: __("{0} / {1} already exists", [colour || "", dia]), indicator: "orange" });
		return;
	}
	entry.requirement.push({ dia, colour, weight: Number(entry._new_r_weight) || 0 });
	entry._new_r_dia = "";
	entry._new_r_colour = "";
	entry._new_r_weight = null;
	mark_dirty();
}

function remove_row(rows, index) {
	rows.splice(index, 1);
	mark_dirty();
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
.fp-grids {
	display: grid;
	grid-template-columns: 1fr 1fr;
	gap: 0;
}
@media (max-width: 900px) {
	.fp-grids {
		grid-template-columns: 1fr;
	}
}
.fp-grid {
	padding: 10px 12px;
}
.fp-grid + .fp-grid {
	border-left: 1px solid var(--border-color);
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
.fp-received {
	color: var(--text-muted);
}
.fp-x {
	width: 28px;
	text-align: center !important;
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
.fp-remove {
	border: none;
	background: transparent;
	color: var(--text-muted);
	cursor: pointer;
	font-size: 14px;
	line-height: 1;
}
.fp-remove:hover {
	color: var(--red-500, #e03636);
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
.fp-add {
	display: flex;
	gap: 6px;
	margin-top: 8px;
	align-items: center;
}
.fp-select {
	border: 1px solid var(--border-color);
	border-radius: 6px;
	background: var(--control-bg, transparent);
	color: inherit;
	font-size: 12px;
	padding: 3px 6px;
	min-width: 90px;
}
.fp-add-weight {
	border: 1px solid var(--border-color);
	border-radius: 6px;
	background: var(--control-bg, transparent);
	color: inherit;
	font-size: 12px;
	padding: 3px 6px;
	width: 100px;
	text-align: right;
}
</style>
