<template>
	<div class="lot-fabric-views">
		<div v-if="!entries.length" class="esd-empty">
			<i class="pi pi-inbox" />
			<p class="esd-empty__text">
				Use Build Cloth Programs to save the calculated quantities for each cloth here.
			</p>
		</div>

		<div v-for="entry in entries" :key="entry.cloth_item" class="lfv-card">
			<header class="lfv-head">
				<div class="lfv-title">
					<b>{{ entry.cloth_item }}</b>
					<span class="lfv-ipd">{{ entry.production_detail }}</span>
					<span v-if="planBadge(entry)" class="lfv-badge" :class="planBadge(entry).cls">
						{{ planBadge(entry).text }}
					</span>
				</div>
			</header>

			<section class="lfv-grid">
				<div class="lfv-table-wrap">
					<table class="lfv-table lfv-matrix">
						<thead>
							<tr>
								<th rowspan="2" class="lfv-dia">Finished Dia</th>
								<th :colspan="programColourColumns(entry).length">Cloth Program (Kg)</th>
								<th rowspan="2" class="lfv-num">Total</th>
							</tr>
							<tr>
								<th
									v-for="colour in programColourColumns(entry)"
									:key="colour.key"
									class="lfv-num lfv-colour"
								>
									{{ colour.label }}
								</th>
							</tr>
						</thead>
						<tbody>
							<tr v-for="dia in programDias(entry)" :key="dia">
								<td class="lfv-dia">{{ dia }}</td>
								<td
									v-for="colour in programColourColumns(entry)"
									:key="colour.key"
									class="lfv-num"
								>
									<input
										v-if="!readonly"
										:value="programWeight(entry, dia, colour.key)"
										type="number"
										min="0"
										step="0.001"
										class="lfv-input"
										:disabled="!programRow(entry, dia, colour.key)"
										:aria-label="`${entry.cloth_item} · ${colour.label} · ${dia} (kg)`"
										@change="setProgramWeight(entry, dia, colour.key, $event.target.value)"
									/>
									<span v-else>{{ programWeight(entry, dia, colour.key) }}</span>
								</td>
								<td class="lfv-num lfv-program">{{ programDiaTotal(entry, dia) }}</td>
							</tr>
							<tr v-if="!programDias(entry).length">
								<td :colspan="programColourColumns(entry).length + 2" class="lfv-none">
									No saved cloth program yet — use Build Cloth Programs.
								</td>
							</tr>
							<tr v-else class="lfv-total">
								<td>Total</td>
								<td
									v-for="colour in programColourColumns(entry)"
									:key="colour.key"
									class="lfv-num"
								>
									{{ programColourTotal(entry, colour.key) }}
								</td>
								<td class="lfv-num">{{ programTotal(entry) }}</td>
							</tr>
						</tbody>
					</table>
				</div>
			</section>
		</div>
	</div>
</template>

<script setup>
/**
 * Lot Fabric views — /web re-port of the Desk Vue island
 * apps/essdee_yrp/essdee_yrp/public/js/Lot/FabricProgram.vue.
 *
 * The UI shows the saved program by finished Dia × Colour. The raw
 * finished-cloth requirement remains in the payload for planning, while the
 * visible weights come from the saved program after the operator's excess.
 *
 * Data contract (byte-faithful to the Desk island):
 *  - loadData(entries): the __onload.fabric_program_details payload built by
 *    essdee_yrp.fabric_program.fetch_fabric_program_details — one entry per
 *    Lot fabric row: { cloth_item, production_detail, dias, colours,
 *    greige_colour, plan_status, plan_built_on, ipd_approved,
 *    final_options:{dias,colours}, requirement:[{dia,colour,weight}],
 *    steps:[…ignored…], program:[{dia,weight,received_weight}] }.
 *  - getData(): [{cloth_item, program:[{dia,weight}]}] — the Lot's transient
 *    `fabric_program_details` JSON (server before_validate rebuilds
 *    lot_fabric_programs, carrying received_weight forward from the DB).
 *  - getRequirement(): [{cloth_item, requirement:[{dia,colour,weight}]}] —
 *    the transient `fabric_requirement_details` JSON (server rebuilds
 *    lot_fabric_requirements + the chain plan on save).
 * Receipt quantities are intentionally not tracked here. Work Order Fill
 * Quantity reads submitted GRNs on demand. Editing preserves the physical
 * output Dia/Colour and final reference supplied by the server.
 */
import { ref, watch } from "vue"
import { programDia, programColour, roundKg, programDias, programColourColumns, programRow, serializeClothProgram } from "@/engine/lotClothProgram"

const props = defineProps({
	initialData: { type: Array, default: null },
	readonly: { type: Boolean, default: false },
})
const emit = defineEmits(["change"])

const entries = ref([])

// Prop + imperative hydration, LotOrderEditor-style: the view tab binds
// :initial-data (this watch), edit mode calls loadData() from
// hydrateLotForEdit. Never onMounted-once.
watch(
	() => props.initialData,
	(v) => {
		if (v != null) loadData(v)
	},
	{ immediate: true },
)

function loadData(data) {
	// Deep copy: the payload object is shared (lotOnload) between the view tab
	// and the edit hydration — in-place mutation would corrupt the other mode.
	const copy = JSON.parse(JSON.stringify(data || []))
	entries.value = copy.map((entry) => ({
		...entry,
		program: entry.program || [],
		requirement: entry.requirement || [],
	}))
}

// → transient `fabric_program_details` (Desk get_data, byte-identical shape)
function getData() {
	return serializeClothProgram(entries.value)
}

// → transient `fabric_requirement_details` (Desk get_requirement)
function getRequirement() {
	return entries.value.map((entry) => ({
		cloth_item: entry.cloth_item,
		requirement: entry.requirement.map((r) => ({
			dia: r.dia,
			colour: r.colour || null,
			weight: r.weight || 0,
		})),
	}))
}

function hasItems() {
	return entries.value.some((e) => e.requirement.length || e.program.length)
}

function planBadge(entry) {
	const status = entry.plan_status || ""
	if (!status) return null
	if (status === "Built") return null
	if (status === "Pending Approval") return { text: "Plan waiting for IPD approval", cls: "lfv-badge--wait" }
	if (status === "Stale") return { text: "Plan outdated — IPD changed", cls: "lfv-badge--warn" }
	return { text: "Plan error — open the fabric row", cls: "lfv-badge--err" }
}

function programWeight(entry, dia, colour) {
	return roundKg(programRow(entry, dia, colour)?.weight)
}

function setProgramWeight(entry, dia, colour, value) {
	const weight = Math.max(0, Number(value) || 0)
	const row = programRow(entry, dia, colour)
	if (row) row.weight = weight
	markDirty()
}

function programColourTotal(entry, colour) {
	return roundKg(entry.program.reduce(
		(sum, row) => sum + (programColour(row) === colour ? Number(row.weight) || 0 : 0),
		0,
	))
}

function programDiaTotal(entry, dia) {
	return roundKg(entry.program.reduce(
		(sum, row) => sum + (programDia(row) === dia ? Number(row.weight) || 0 : 0),
		0,
	))
}

function programTotal(entry) {
	return roundKg(entry.program.reduce(
		(sum, row) => sum + (Number(row.weight) || 0),
		0,
	))
}

function markDirty() {
	emit("change")
}

defineExpose({ loadData, getData, getRequirement, hasItems })
</script>

<style scoped>
.lot-fabric-views {
	display: flex;
	flex-direction: column;
	gap: 12px;
}
.lfv-card {
	border: 1px solid var(--esd-line);
	border-radius: 10px;
	background: var(--esd-card);
	overflow: hidden;
}
.lfv-head {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: 8px;
	padding: 8px 12px;
	border-bottom: 1px solid var(--esd-line);
	background: var(--esd-accent-50);
}
.lfv-title b {
	color: var(--esd-accent-ink);
	font-size: 13px;
}
.lfv-ipd {
	margin-left: 8px;
	color: var(--esd-muted);
	font-size: 11.5px;
}
.lfv-badge {
	margin-left: 10px;
	font-size: 11px;
	padding: 2px 8px;
	border-radius: 10px;
	font-weight: 500;
	white-space: nowrap;
}
.lfv-badge--ok { background: var(--esd-success-50); color: var(--esd-success); }
.lfv-badge--wait { background: var(--esd-accent-50); color: var(--esd-accent-700); }
.lfv-badge--warn { background: var(--esd-warn-50); color: var(--esd-warn); }
.lfv-badge--err { background: var(--esd-danger-50); color: var(--esd-danger); }
.lfv-grid {
	padding: 10px 12px;
	min-width: 0;
}
.lfv-table {
	width: 100%;
	border-collapse: collapse;
	font-size: 12.5px;
}
.lfv-table-wrap {
	overflow-x: auto;
}
.lfv-matrix {
	min-width: 720px;
}
.lfv-table th,
.lfv-table td {
	border: 1px solid var(--esd-line);
	padding: 4px 8px;
	text-align: left;
	color: var(--esd-ink);
}
.lfv-table th {
	background: var(--esd-slate-50);
	font-weight: 500;
	color: var(--esd-muted);
	font-size: 11px;
	text-transform: uppercase;
	letter-spacing: 0.04em;
}
.lfv-num {
	text-align: right !important;
	width: 90px;
}
.lfv-dia {
	min-width: 105px;
	white-space: nowrap;
	font-weight: 600;
}
.lfv-colour {
	min-width: 82px;
}
.lfv-program {
	background: var(--esd-slate-50);
	font-weight: 600;
}
.lfv-total td {
	font-weight: 600;
	border-top: 2px solid var(--esd-line);
}
.lfv-input {
	width: 100%;
	border: none;
	background: transparent;
	color: var(--esd-ink);
	text-align: right;
	outline: none;
	font: inherit;
}
.lfv-none {
	color: var(--esd-muted-2);
	text-align: center;
	font-size: 12px;
}
@media (max-width: 700px) {
	.lfv-head {
		align-items: flex-start;
	}
	.lfv-title {
		display: flex;
		flex-direction: column;
		gap: 3px;
	}
	.lfv-ipd,
	.lfv-badge {
		margin-left: 0;
	}
	.lfv-grid {
		padding: 8px;
	}
}
</style>
