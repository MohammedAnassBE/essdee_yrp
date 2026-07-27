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

			<section class="lfv-grid">
				<h6>Finished cloth requirement — Dia × Colour</h6>
				<div class="lfv-table-wrap">
					<table class="lfv-table lfv-matrix">
						<thead>
							<tr>
								<th rowspan="2" class="lfv-dia">Finished Dia</th>
								<th :colspan="colourColumns(entry).length">Finished cloth requirement (Kg)</th>
								<th rowspan="2" class="lfv-num">Total</th>
							</tr>
							<tr>
								<th
									v-for="colour in colourColumns(entry)"
									:key="colour.key"
									class="lfv-num lfv-colour"
								>
									{{ colour.label }}
								</th>
							</tr>
						</thead>
						<tbody>
							<tr v-for="dia in requirementDias(entry)" :key="dia">
								<td class="lfv-dia">{{ dia }}</td>
								<td
									v-for="colour in colourColumns(entry)"
									:key="colour.key"
									class="lfv-num"
								>
									<input
										v-if="!readonly"
										:value="requirementWeight(entry, dia, colour.key)"
										type="number"
										min="0"
										step="0.001"
										class="lfv-input"
										@change="setRequirementWeight(entry, dia, colour.key, $event.target.value)"
									/>
									<span v-else>{{ requirementWeight(entry, dia, colour.key) }}</span>
								</td>
								<td class="lfv-num lfv-program">{{ requirementDiaTotal(entry, dia) }}</td>
							</tr>
							<tr v-if="!requirementDias(entry).length">
								<td :colspan="colourColumns(entry).length + 2" class="lfv-none">
									No cloth requirement yet
								</td>
							</tr>
							<tr v-else class="lfv-total">
								<td>Total</td>
								<td
									v-for="colour in colourColumns(entry)"
									:key="colour.key"
									class="lfv-num"
								>
									{{ colourTotal(entry, colour.key) }}
								</td>
								<td class="lfv-num">{{ requirementTotal(entry) }}</td>
							</tr>
						</tbody>
					</table>
				</div>
				<h6 class="lfv-route-heading">Knitting output plan — exact routes</h6>
				<div class="lfv-table-wrap">
					<table class="lfv-table lfv-route-table">
						<thead>
							<tr>
								<th>Finished route</th>
								<th>Received from knitting as</th>
								<th class="lfv-num">Planned Kg</th>
								<th class="lfv-num">Received Kg</th>
								<th class="lfv-num">Balance Kg</th>
							</tr>
						</thead>
						<tbody>
							<tr v-for="(route, ri) in programRoutes(entry)" :key="route.reference_item_variant || ri">
								<td>
									<strong>{{ route.finished_colour || "Unspecified colour" }}</strong>
									<small>{{ route.finished_dia || "No final Dia" }}</small>
								</td>
								<td>
									<strong>{{ route.knitting_output_colour || "Unspecified colour" }}</strong>
									<small>{{ route.knitting_output_dia || "No knitting Dia" }}</small>
								</td>
								<td class="lfv-num">{{ roundKg(route.weight) }}</td>
								<td class="lfv-num lfv-received">{{ roundKg(route.received_weight) }}</td>
								<td class="lfv-num">{{ routeBalance(route) }}</td>
							</tr>
							<tr v-if="!programRoutes(entry).length">
								<td colspan="5" class="lfv-none">
									{{ entry.ipd_approved
										? "Save requirements or rebuild the plan."
										: "Approve the cloth IPD to build its route plan." }}
								</td>
							</tr>
							<tr v-else class="lfv-total">
								<td colspan="2">Total</td>
								<td class="lfv-num">{{ programTotal(entry) }}</td>
								<td class="lfv-num lfv-received">{{ receivedTotal(entry) }}</td>
								<td class="lfv-num">{{ roundKg(programTotal(entry) - receivedTotal(entry)) }}</td>
							</tr>
						</tbody>
					</table>
				</div>
				<div v-if="!entry.ipd_approved" class="lfv-hint">
					Plan builds when the IPD is approved.
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
 * One compact Dia × Colour matrix combines the two approved views: finished
 * cloth requirement cells plus an exact finished-route → physical-knitting
 * plan and read-only GRN received kg. The persisted payload remains the
 * original two long-form lists.
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
 * Adapted (widgets only): PrimeVue Button + esd-* tokens replace the Desk's
 * native button and frappe CSS vars; feedback uses useAppToast; editability
 * comes from the `readonly` prop (the parent passes
 *  the Desk's rule: Lot status !== "Open" → read-only) instead of cur_frm; the
 *  rebuild button renders only where the parent allows it (view mode — the
 *  Desk's is_dirty guard is structural there: a viewed doc is saved).
 */
import { ref, watch } from "vue"
import Button from "primevue/button"
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
	}))
}

// → transient `fabric_program_details` (Desk get_data, byte-identical shape)
function getData() {
	return entries.value.map((entry) => ({
		cloth_item: entry.cloth_item,
		program: entry.program.map((r) => ({
			dia: r.dia,
			colour: r.colour || null,
			reference_item_variant: r.reference_item_variant || null,
			weight: r.weight || 0,
		})),
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

function roundKg(value) {
	return Math.round((Number(value) || 0) * 1000) / 1000
}

function diaNumber(value) {
	const match = String(value || "").match(/-?\d+(?:\.\d+)?/)
	return match ? Number(match[0]) : Number.MAX_SAFE_INTEGER
}

function requirementDias(entry) {
	const values = [
		...(entry.final_options?.dias || []),
		...entry.requirement.map((row) => row.dia),
	].filter(Boolean)
	return [...new Set(values)].sort(
		(a, b) => diaNumber(a) - diaNumber(b) || String(a).localeCompare(String(b)),
	)
}

function colourColumns(entry) {
	const values = [
		...entry.requirement.map((row) => row.colour),
		...(entry.colours || []),
		...(entry.final_options?.colours || []),
	].filter(Boolean)
	const colours = [...new Set(values)]
	return colours.length
		? colours.map((colour) => ({ key: colour, label: colour }))
		: [{ key: "", label: "Requirement" }]
}

function requirementRow(entry, dia, colour) {
	return entry.requirement.find(
		(row) => row.dia === dia && (row.colour || "") === colour,
	)
}

function requirementWeight(entry, dia, colour) {
	return roundKg(requirementRow(entry, dia, colour)?.weight)
}

function setRequirementWeight(entry, dia, colour, value) {
	const weight = Math.max(0, Number(value) || 0)
	const row = requirementRow(entry, dia, colour)
	if (row) {
		row.weight = weight
	} else if (weight > 0) {
		entry.requirement.push({ dia, colour: colour || null, weight })
	}
	markDirty()
}

function colourTotal(entry, colour) {
	return roundKg(entry.requirement.reduce(
		(sum, row) => sum + ((row.colour || "") === colour ? Number(row.weight) || 0 : 0),
		0,
	))
}

function requirementDiaTotal(entry, dia) {
	return roundKg(entry.requirement.reduce(
		(sum, row) => sum + (row.dia === dia ? Number(row.weight) || 0 : 0),
		0,
	))
}

function requirementTotal(entry) {
	return roundKg(entry.requirement.reduce(
		(sum, row) => sum + (Number(row.weight) || 0),
		0,
	))
}

function programRoutes(entry) {
	return entry.program.slice().sort(
		(a, b) =>
			String(a.finished_colour || "").localeCompare(String(b.finished_colour || "")) ||
			diaNumber(a.finished_dia) - diaNumber(b.finished_dia) ||
			String(a.finished_dia || "").localeCompare(String(b.finished_dia || "")),
	)
}

function routeBalance(route) {
	return roundKg(Math.max(
		(Number(route.weight) || 0) - (Number(route.received_weight) || 0),
		0,
	))
}

function programTotal(entry) {
	return roundKg(entry.program.reduce((sum, row) => sum + (Number(row.weight) || 0), 0))
}

function receivedTotal(entry) {
	return roundKg(entry.program.reduce(
		(sum, row) => sum + (Number(row.received_weight) || 0),
		0,
	))
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
.lfv-grid {
	padding: 10px 12px;
	min-width: 0;
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
.lfv-table-wrap {
	overflow-x: auto;
}
.lfv-matrix {
	min-width: 720px;
}
.lfv-route-heading {
	margin-top: 14px !important;
}
.lfv-route-table {
	min-width: 650px;
}
.lfv-route-table td > strong,
.lfv-route-table td > small {
	display: block;
}
.lfv-route-table td > small {
	margin-top: 2px;
	color: var(--esd-muted);
	font-size: 11px;
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
.lfv-received {
	color: var(--esd-muted);
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
.lfv-hint {
	margin-top: 6px;
	color: var(--esd-muted);
	font-size: 11.5px;
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
