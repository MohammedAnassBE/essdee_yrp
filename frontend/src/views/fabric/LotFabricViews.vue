<template>
	<div class="lot-fabric-views">
		<div v-if="!entries.length" class="esd-empty">
			<i class="pi pi-inbox" />
			<p class="esd-empty__text">
				Add rows in Fabric Details and save — the program grids appear per cloth.
			</p>
		</div>

		<div v-for="(entry, ei) in entries" :key="entry.cloth_item" class="lfv-card">
			<header class="lfv-head">
				<div class="lfv-title">
					<b>{{ entry.cloth_item }}</b>
					<span class="lfv-ipd">{{ entry.production_detail }}</span>
					<span v-if="planBadge(entry)" class="lfv-badge" :class="planBadge(entry).cls">
						{{ planBadge(entry).text }}
					</span>
				</div>
				<Button
					v-if="ei === 0 && canRebuild && lotName"
					label="Recalculate Received"
					icon="pi pi-refresh"
					size="small"
					severity="secondary"
					outlined
					:loading="rebuilding"
					@click="rebuild"
				/>
			</header>

			<div class="lfv-grids">
				<!-- ── View 1: Final Requirement (finished cloth) ── -->
				<section class="lfv-grid">
					<h6>Final Requirement — finished cloth</h6>
					<table class="lfv-table">
						<thead>
							<tr>
								<th>Colour</th>
								<th>Dia</th>
								<th class="lfv-num">Weight (Kg)</th>
								<th v-if="!readonly" class="lfv-x"></th>
							</tr>
						</thead>
						<tbody>
							<tr v-for="(row, ri) in entry.requirement" :key="(row.colour || '') + '::' + row.dia">
								<td>{{ row.colour || "—" }}</td>
								<td>{{ row.dia }}</td>
								<td class="lfv-num">
									<input
										v-if="!readonly"
										v-model.number="row.weight"
										type="number"
										min="0"
										step="0.001"
										class="lfv-input"
										@change="markDirty"
									/>
									<span v-else>{{ row.weight }}</span>
								</td>
								<td v-if="!readonly" class="lfv-x">
									<button class="lfv-remove" title="Remove row" @click="removeRow(entry.requirement, ri)">×</button>
								</td>
							</tr>
							<tr v-if="!entry.requirement.length">
								<td :colspan="readonly ? 3 : 4" class="lfv-none">No requirement yet</td>
							</tr>
							<tr v-if="entry.requirement.length" class="lfv-total">
								<td colspan="2">Total</td>
								<td class="lfv-num">{{ requirementTotal(entry) }}</td>
								<td v-if="!readonly"></td>
							</tr>
						</tbody>
					</table>
					<div v-if="!readonly" class="lfv-add">
						<Select
							v-if="(entry.final_options?.colours || []).length"
							v-model="entry._new_r_colour"
							:options="entry.final_options.colours"
							placeholder="Colour…"
							size="small"
							class="lfv-select"
							showClear
						/>
						<Select
							v-model="entry._new_r_dia"
							:options="entry.final_options?.dias || []"
							placeholder="Dia…"
							size="small"
							class="lfv-select"
							showClear
						/>
						<input
							v-model.number="entry._new_r_weight"
							type="number"
							min="0"
							step="0.001"
							class="lfv-add-weight"
							placeholder="Weight (Kg)"
							@keyup.enter="addRequirement(entry)"
						/>
						<Button
							label="Add"
							size="small"
							severity="secondary"
							outlined
							:disabled="!entry._new_r_dia || !(Number(entry._new_r_weight) > 0) || ((entry.final_options?.colours || []).length && !entry._new_r_colour)"
							@click="addRequirement(entry)"
						/>
					</div>
					<div v-if="!entry.ipd_approved" class="lfv-hint">
						Plan builds when the IPD is approved.
					</div>
				</section>

				<!-- ── View 2: Program — dia-wise (greige to knit) with inline weight
				     entry + received (dyed) kgs from GRN tracking ── -->
				<section class="lfv-grid">
					<h6>Program — dia-wise (greige to knit)</h6>
					<table class="lfv-table">
						<thead>
							<tr>
								<th>Dia</th>
								<th class="lfv-num">Weight (Kg)</th>
								<th class="lfv-num">Received (Kg)</th>
								<th v-if="!readonly" class="lfv-x"></th>
							</tr>
						</thead>
						<tbody>
							<tr v-for="(row, ri) in entry.program" :key="row.dia">
								<td>{{ row.dia }}</td>
								<td class="lfv-num">
									<input
										v-if="!readonly"
										v-model.number="row.weight"
										type="number"
										min="0"
										step="0.001"
										class="lfv-input"
										@change="markDirty"
									/>
									<span v-else>{{ row.weight }}</span>
								</td>
								<td class="lfv-num lfv-received">{{ row.received_weight || 0 }}</td>
								<td v-if="!readonly" class="lfv-x">
									<button
										v-if="!row.received_weight"
										class="lfv-remove"
										title="Remove row"
										@click="removeRow(entry.program, ri)"
									>×</button>
								</td>
							</tr>
							<tr v-if="!entry.program.length">
								<td :colspan="readonly ? 3 : 4" class="lfv-none">No program yet</td>
							</tr>
						</tbody>
					</table>
					<div v-if="!readonly && remainingDias(entry).length" class="lfv-add">
						<Select
							v-model="entry._new_dia"
							:options="remainingDias(entry)"
							placeholder="Dia…"
							size="small"
							class="lfv-select"
							showClear
						/>
						<input
							v-model.number="entry._new_weight"
							type="number"
							min="0"
							step="0.001"
							class="lfv-add-weight"
							placeholder="Weight (Kg)"
							@keyup.enter="addProgram(entry)"
						/>
						<Button
							label="Add"
							size="small"
							severity="secondary"
							outlined
							:disabled="!entry._new_dia || !(Number(entry._new_weight) > 0)"
							@click="addProgram(entry)"
						/>
					</div>
				</section>
			</div>
			<!-- The per-process (knitting/dyeing/compacting) chain plan-vs-received
			     view is intentionally NOT rendered (convention 2026-07-07): only the
			     two fabric views above — Final Requirement (finished cloth) and
			     Program (dia-wise / dyed) — are shown. The chain stays fully tracked
			     in the backend (lot_fabric_step_ledger + the IPD matrices); the
			     entries' `steps` payload is loaded but never displayed. -->
		</div>
	</div>
</template>

<script setup>
/**
 * Lot Fabric views — /web re-port of the Desk Vue island
 * apps/essdee_yrp/essdee_yrp/public/js/Lot/FabricProgram.vue.
 *
 * The 2 approved views ONLY (user decision 2026-07-07; the per-process chain
 * views are deliberately absent — display-hiding only, not a data change):
 *   1. Final Requirement — finished cloth (colour + dia + kg, inline entry,
 *      choices limited to what the chain can produce: entry.final_options).
 *   2. Program — dia-wise greige-to-knit kg with INLINE weight entry (no popup
 *      round-trips) + read-only Received kgs (GRN tracking, server-owned).
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
 *  - Rebuild button = the Desk's "Recalculate Received": the SAME whitelisted
 *    essdee_yrp.fabric_tracking.rebuild_fabric_tracking; emits "rebuilt" so
 *    the parent reloads the doc + onload (Desk does cur_frm.reload_doc()).
 *
 * Adapted (widgets only): PrimeVue Select/Button + esd-* tokens replace the
 *  Desk's native selects/btn-xs and frappe CSS vars; frappe.show_alert →
 *  useAppToast; editability comes from the `readonly` prop (the parent passes
 *  the Desk's rule: Lot status !== "Open" → read-only) instead of cur_frm; the
 *  rebuild button renders only where the parent allows it (view mode — the
 *  Desk's is_dirty guard is structural there: a viewed doc is saved).
 */
import { ref, watch } from "vue"
import Button from "primevue/button"
import Select from "primevue/select"
import { callMethod } from "@/api/client"
import { useAppToast } from "@/composables/useToast"

const props = defineProps({
	initialData: { type: Array, default: null },
	readonly: { type: Boolean, default: false },
	// Rebuild ("Recalculate Received") is offered only on a saved, non-dirty doc
	// — the parent (view mode) decides. Needs lotName for the server call.
	canRebuild: { type: Boolean, default: false },
	lotName: { type: String, default: "" },
})
const emit = defineEmits(["change", "rebuilt"])
const toast = useAppToast()

const entries = ref([])
const rebuilding = ref(false)

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
		_new_dia: "",
		_new_weight: null,
		_new_r_dia: "",
		_new_r_colour: "",
		_new_r_weight: null,
	}))
}

// → transient `fabric_program_details` (Desk get_data, byte-identical shape)
function getData() {
	return entries.value.map((entry) => ({
		cloth_item: entry.cloth_item,
		program: entry.program.map((r) => ({ dia: r.dia, weight: r.weight || 0 })),
	}))
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
	if (status === "Built") {
		const when = (entry.plan_built_on || "").slice(0, 10)
		return { text: `Plan ready ${when}`, cls: "lfv-badge--ok" }
	}
	if (status === "Pending Approval") return { text: "Plan waiting for IPD approval", cls: "lfv-badge--wait" }
	if (status === "Stale") return { text: "Plan outdated — IPD changed", cls: "lfv-badge--warn" }
	return { text: "Plan error — open the fabric row", cls: "lfv-badge--err" }
}

function requirementTotal(entry) {
	return Math.round(entry.requirement.reduce((sum, r) => sum + (Number(r.weight) || 0), 0) * 1000) / 1000
}

function remainingDias(entry) {
	const used = new Set(entry.program.map((r) => r.dia))
	return (entry.dias || []).filter((d) => !used.has(d))
}

function addProgram(entry) {
	// Weight must be > 0 — the server silently skips 0-weight rows on save,
	// so an empty add would just vanish (guards the Enter-key path too).
	if (!entry._new_dia || !(Number(entry._new_weight) > 0)) return
	entry.program.push({ dia: entry._new_dia, weight: Number(entry._new_weight) || 0, received_weight: 0 })
	entry._new_dia = ""
	entry._new_weight = null
	markDirty()
}

function addRequirement(entry) {
	const dia = entry._new_r_dia
	const colour = entry._new_r_colour || null
	// Same 0-weight guard as addProgram (server skips weightless rows).
	if (!dia || !(Number(entry._new_r_weight) > 0)) return
	if (entry.requirement.some((r) => r.dia === dia && (r.colour || null) === colour)) {
		toast.warn("Already exists", `${colour || ""} / ${dia} is already in the requirement.`)
		return
	}
	entry.requirement.push({ dia, colour, weight: Number(entry._new_r_weight) || 0 })
	entry._new_r_dia = ""
	entry._new_r_colour = ""
	entry._new_r_weight = null
	markDirty()
}

function removeRow(rows, index) {
	rows.splice(index, 1)
	markDirty()
}

function markDirty() {
	emit("change")
}

// Desk "Recalculate Received": zero + replay every submitted fabric GRN.
// Offered only on a saved doc (canRebuild), so the Desk's is_dirty guard is
// satisfied structurally; the parent reloads doc + onload on "rebuilt".
async function rebuild() {
	if (!props.lotName || rebuilding.value) return
	rebuilding.value = true
	try {
		await callMethod("essdee_yrp.fabric_tracking.rebuild_fabric_tracking", { lot: props.lotName })
		toast.success("Received quantities recalculated")
		emit("rebuilt")
	} catch (e) {
		toast.error("Recalculate Received failed", e.message)
	} finally {
		rebuilding.value = false
	}
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
.lfv-grids {
	display: grid;
	grid-template-columns: 1fr 1fr;
}
@media (max-width: 900px) {
	.lfv-grids {
		grid-template-columns: 1fr;
	}
	.lfv-grid + .lfv-grid {
		border-left: none;
		border-top: 1px solid var(--esd-line);
	}
}
.lfv-grid {
	padding: 10px 12px;
	min-width: 0;
}
.lfv-grid + .lfv-grid {
	border-left: 1px solid var(--esd-line);
}
.lfv-grid h6 {
	font-size: 11px;
	text-transform: uppercase;
	letter-spacing: 0.04em;
	color: var(--esd-muted);
	margin: 0 0 6px;
}
.lfv-table {
	width: 100%;
	border-collapse: collapse;
	font-size: 12.5px;
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
.lfv-received {
	color: var(--esd-muted);
}
.lfv-x {
	width: 28px;
	text-align: center !important;
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
.lfv-remove {
	border: none;
	background: transparent;
	color: var(--esd-muted);
	cursor: pointer;
	font-size: 14px;
	line-height: 1;
}
.lfv-remove:hover {
	color: var(--esd-danger);
}
.lfv-none {
	color: var(--esd-muted-2);
	text-align: center;
	font-size: 12px;
}
.lfv-hint {
	margin-top: 6px;
	color: var(--esd-muted);
	font-size: 11.5px;
}
.lfv-add {
	display: flex;
	gap: 6px;
	margin-top: 8px;
	align-items: center;
	flex-wrap: wrap;
}
.lfv-select {
	min-width: 110px;
}
.lfv-add-weight {
	border: 1px solid var(--esd-line);
	border-radius: 6px;
	background: var(--esd-card);
	color: var(--esd-ink);
	font-size: 12px;
	padding: 5px 8px;
	width: 110px;
	text-align: right;
	outline: none;
}
.lfv-add-weight:focus {
	border-color: var(--esd-accent);
}
</style>
