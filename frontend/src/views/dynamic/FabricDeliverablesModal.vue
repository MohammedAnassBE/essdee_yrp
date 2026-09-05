<template>
	<Dialog
		:visible="visible"
		modal
		class="fabric-calc-dialog"
		:style="{ width: 'min(880px, calc(100vw - 32px))' }"
		:header="dialogHeader"
		:closable="!applying && !loading"
		:closeOnEscape="!applying && !loading"
		@update:visible="(v) => emit('update:visible', v)"
		@show="loadContext"
	>
		<div v-if="loading" class="fc-loading">
			<i class="pi pi-spin pi-spinner" /> Loading fabric context…
		</div>

		<div v-else-if="!ctx || !(ctx.rows || []).length" class="esd-empty">
			<i class="pi pi-info-circle" />
			<p class="esd-empty__text">
				No fabric quantity rows are available for this Work Order's configured process.
			</p>
			<div v-for="warning in ctx?.warnings || []" :key="warning" class="fc-warning" role="status">{{ warning }}</div>
		</div>

		<div v-else class="fc-rows">
			<div class="fc-source-note" role="status">
				<template v-if="ctx.source_process">
					<strong>Filled from {{ ctx.source_process.label || ctx.source_process.process_name }} GRNs</strong>
					<span>Unallocated source stock: {{ ctx.source_process.available }} kg across all source variants. Only compatible inputs can fill the rows below.</span>
					<span>Return GRNs are excluded. Quantities remain editable and availability is checked again on Calculate.</span>
				</template>
				<template v-else>
					<strong>Planned quantities</strong>
					<span>Knitting uses the saved Lot Cloth Program; later processes use their plan. Edit quantities, or use Fill Quantity to read an earlier process's submitted GRNs.</span>
				</template>
			</div>
			<div v-for="warning in ctx.warnings || []" :key="warning" class="fc-warning" role="status">{{ warning }}</div>
			<section v-for="(row, i) in ctx.rows" :key="row.fabric_row" class="fc-row">
				<header class="esd-card__head">
					<span class="esd-card__title">{{ row.cloth_item }}</span>
					<span class="fc-ipd esd-mono">{{ row.production_detail }}</span>
				</header>
				<div v-if="row.reference_routed" class="fc-note">
					Enter quantities by <b>finished cloth Colour and Dia</b>. The IPD determines the consumed inputs and this process's output.
				</div>
				<div v-if="(row.qty_rows || []).some((qr) => qr.source_shared)" class="fc-warning">
					Some outputs share the same received input. Their quantities start at 0; allocate the shared quantity manually. Availability shown on those rows is shared, not additional stock for each row.
				</div>

				<!-- The IPD derives every attribute; the user enters ONLY quantities —
				     one row per matrix group (mirrors the Desk dialog exactly). -->
				<div
					v-if="row.kind === 'identity' && row.treated_item && row.treated_item !== row.cloth_item"
					class="fc-note"
				>
					Item: <b>{{ row.treated_item }}</b>
				</div>
				<!-- Rule-based conversion (Consume/Introduce): say what gets consumed —
				     each qty row below is one "consumed combo → produced combo" rule. -->
				<div v-if="row.kind === 'conversion' && row.input_item" class="fc-note">
					Consumes: <b>{{ row.input_item }}</b> → produces <b>{{ row.cloth_item }}</b>
				</div>
				<template v-if="row.kind === 'knitting'">
					<div v-if="needsColourPicker(row)" class="fc-field">
						<label class="field-label">Cloth Colour *</label>
						<!-- too many colour choices for columns — single-colour fallback.
						     No physical-output colour_options at all: the SAME link query the Desk
						     falls back to (IPD colour mapping, else any Colour value). -->
						<Select
							v-if="(row.colour_options || []).length"
							v-model="entries[i].colour"
							:options="row.colour_options"
							filter
							fluid
							placeholder="Select Colour"
						/>
						<LinkField
							v-else
							:modelValue="entries[i].colour || ''"
							@update:modelValue="(v) => (entries[i].colour = v || null)"
							target-doctype="Item Attribute Value"
							:search-handler="(q) => searchColourValues(row, q)"
							placeholder="Select Colour"
						/>
					</div>
				</template>

				<!-- Legacy knitting: one column per physical output colour. -->
				<div v-if="isMultiColour(row)" class="fc-colour-grid">
					<div v-for="colour in row.colour_options" :key="colour" class="fc-colour-col">
						<div class="fc-colour-head">{{ colour }}</div>
						<div v-for="(qr, j) in row.qty_rows || []" :key="qr.key" class="fc-field fc-field--tight">
							<label class="field-label">{{ qr.label }}</label>
							<InputNumber
								v-model="entries[i].colourQtys[colour][j]"
								:min="0"
								:maxFractionDigits="3"
								fluid
								placeholder="0"
								@update:modelValue="recomputeYarn(i)"
							/>
						</div>
					</div>
				</div>

				<!-- colour-section layout (2026-07-08): big multi-row popups group by
				     the server's `section` (the Colour part of each rule) with the
				     short `row_label` (the Dia part) on each input. ≤6 sections →
				     one column per section; more → stacked section blocks. -->
				<div
					v-else-if="layouts[i]"
					:class="layouts[i].asColumns ? 'fc-colour-grid' : 'fc-section-stack'"
				>
					<div
						v-for="sec in layouts[i].sections"
						:key="String(sec.name)"
						:class="layouts[i].asColumns ? 'fc-colour-col' : 'fc-section-block'"
					>
						<div class="fc-colour-head">{{ sec.name }}</div>
						<div v-for="it in sec.items" :key="it.qr.key" class="fc-field fc-field--tight">
							<label class="field-label">{{ it.qr.row_label || it.qr.label }}</label>
							<small v-if="it.qr.source_available != null" class="fc-availability">
								{{ it.qr.source_shared ? 'Shared capacity' : 'Available output' }}: {{ it.qr.source_available }} kg
							</small>
							<InputNumber
								v-model="entries[i].qtys[it.j]"
								:min="0"
								:maxFractionDigits="3"
								fluid
								placeholder="0"
							/>
						</div>
					</div>
				</div>

				<template v-else>
					<div v-for="(qr, j) in row.qty_rows || []" :key="qr.key" class="fc-field">
						<label class="field-label">{{ qr.label }}</label>
						<small v-if="qr.source_available != null" class="fc-availability">
							{{ qr.source_shared ? 'Shared capacity' : 'Available output' }}: {{ qr.source_available }} kg
						</small>
						<InputNumber
							v-model="entries[i].qtys[j]"
							:min="0"
							:maxFractionDigits="3"
							fluid
							placeholder="0"
							@update:modelValue="row.kind === 'knitting' && recomputeYarn(i)"
						/>
					</div>
				</template>

				<div
					v-if="row.kind === 'knitting' && !row.reference_routed && (row.yarns || []).length === 1"
					class="fc-field"
				>
					<label class="field-label">Yarn (deliverable) Kg</label>
					<InputNumber
						v-model="entries[i].yarnQty"
						:min="0"
						:maxFractionDigits="3"
						fluid
						placeholder="0"
					/>
				</div>
				<div v-else-if="row.kind === 'knitting' && !row.reference_routed" class="fc-yarn-breakdown">
					<div class="field-label">Calculated yarn deliverables</div>
					<div v-for="yarn in row.yarns || []" :key="yarn.yarn_item" class="fc-yarn-line">
						<span>{{ yarn.yarn_item }} · {{ yarn.ratio }}%</span>
						<strong>{{ yarnQuantity(i, yarn) }} kg</strong>
					</div>
				</div>
			</section>
		</div>

		<template #footer>
			<Button label="Cancel" severity="secondary" text :disabled="applying || loading" @click="emit('update:visible', false)" />
			<Button
				v-if="(ctx?.source_process_options || []).length"
				label="Fill Quantity"
				icon="pi pi-download"
				severity="secondary"
				:disabled="applying || loading"
				@click="openSourcePicker"
			/>
			<Button
				v-if="ctx && (ctx.rows || []).length"
				label="Calculate"
				icon="pi pi-calculator"
				:loading="applying"
				:disabled="loading"
				@click="onApply"
			/>
		</template>
	</Dialog>
	<Dialog
		v-model:visible="sourcePickerOpen"
		modal
		header="Fill Quantity from Process GRNs"
		:style="{ width: 'min(460px, calc(100vw - 32px))' }"
		:closable="!loading"
		:closeOnEscape="!loading"
	>
		<div class="fc-field">
			<label for="fabric-source-process" class="field-label">Source Process *</label>
			<Select
				v-model="selectedSource"
				inputId="fabric-source-process"
				:options="ctx?.source_process_options || []"
				optionLabel="label"
				optionValue="value"
				:disabled="loading"
				fluid
				placeholder="Select an earlier process"
			/>
			<small>Replaces the popup quantities using submitted GRNs for this Lot and cloth. Return GRNs are excluded. Nothing is saved until Calculate.</small>
			<p v-if="fillError" class="fc-warning" role="alert">{{ fillError }}</p>
		</div>
		<template #footer>
			<Button label="Cancel" severity="secondary" text :disabled="loading" @click="sourcePickerOpen = false" />
			<Button label="Fill" icon="pi pi-download" :loading="loading" :disabled="!selectedSource" @click="fillQuantity" />
		</template>
	</Dialog>
</template>

<script setup>
/**
 * Calculate Fabric Deliverables — /web port of the Desk dialog in
 * essdee_yrp/public/js/work_order.js (render_fabric_dialog, qty-rows
 * contract 2026-07-08).
 *
 * Byte-faithful to the Desk reference (data contracts + branching):
 * - One quantity input per IPD Process Matrix group; every entry posts its
 *   matrix-group `key` so the server resolves the exact group (never by attrs).
 * - Legacy knitting: one column per physical output colour (≤ MAX_COLOUR_COLUMNS) with an
 *   input per dia, else a single-colour picker fallback (restricted Select
 *   when the server sent colour_options; otherwise the same link query the
 *   Desk uses — IPD colour mapping, else any Colour attribute value) + an
 *   auto-computed, editable yarn deliverable (total ÷ cloth_per_kg_yarn).
 * - Conversion: "Consumes: X → produces Y" note; no colour picker, no yarn.
 * - Colour-section layout for conversion/dyeing/compacting/identity when
 *   qty_rows > 6 AND >1 server `section` (all non-null): ≤6 sections → one
 *   column per section (bold heading, row_label per input), else stacked
 *   section blocks; small/flat lists keep the flat label list. `section` /
 *   `row_label` come verbatim from the server — no client re-derivation.
 * - Non-blocking over-balance warning (production_api stance): knitting /
 *   dyeing per-dia sums vs balance / previous-stage availability, compacting per row.
 * Adapted (widgets only): frappe.ui.Dialog → PrimeVue Dialog, Float →
 * InputNumber, Link → Select/LinkField, HTML notes → styled divs.
 */
import { ref, computed, watch, onBeforeUnmount } from "vue"
import Dialog from "primevue/dialog"
import Select from "primevue/select"
import InputNumber from "primevue/inputnumber"
import Button from "primevue/button"
import LinkField from "@/components/LinkField.vue"
import { callMethod, searchLink } from "@/api/client"
import { useAppToast } from "@/composables/useToast"
import { MAX_COLOUR_COLUMNS, isMultiColour, useFabricDeliverableContext } from "@/composables/useFabricDeliverableContext"

const props = defineProps({
	visible: { type: Boolean, default: false },
	workOrder: { type: String, required: true },
	// The WO's process name — Desk parity: the dialog title is
	// "Calculate Fabric Deliverables — <process>" (work_order.js).
	processName: { type: String, default: "" },
	// Loaded `modified` timestamp — forwarded to calculate_fabric_deliverables so
	// the backend's stale-write guard (_guard_not_modified) rejects a concurrent edit.
	modified: { type: String, default: null },
})
// "applying" fires right BEFORE the server write so the host can open its
// realtime local-write suppression window (markLocalWrite) in time — the
// doc_update echo can arrive mid-request, before "calculated" resolves, and
// would otherwise raise a false "modified by another user" notice.
const emit = defineEmits(["update:visible", "calculated", "applying"])

const dialogHeader = computed(() =>
	props.processName
		? `Calculate Fabric Deliverables — ${props.processName}`
		: "Calculate Fabric Deliverables",
)

const toast = useAppToast()
const applying = ref(false)
const { ctx, entries, loading, load, invalidate } = useFabricDeliverableContext(
	(args) => callMethod("essdee_yrp.api.work_order.get_fabric_deliverable_context", args),
)
const sourcePickerOpen = ref(false)
const selectedSource = ref(null)
const fillError = ref("")

watch(() => props.visible, (visible) => {
	if (!visible) {
		invalidate()
		sourcePickerOpen.value = false
	}
})
watch(() => props.workOrder, () => {
	invalidate()
	sourcePickerOpen.value = false
	if (props.visible) loadContext()
})
onBeforeUnmount(invalidate)

async function loadContext() {
	fillError.value = ""
	try {
		await load(props.workOrder, null, { reset: true })
	} catch (e) {
		toast.error("Couldn't load fabric context", e.message)
		emit("update:visible", false)
	}
}

function openSourcePicker() {
	selectedSource.value = ctx.value?.source_process?.value || ctx.value?.source_process_options?.[0]?.value || null
	fillError.value = ""
	sourcePickerOpen.value = true
}

async function fillQuantity() {
	if (!selectedSource.value || loading.value || applying.value) return
	fillError.value = ""
	try {
		if (await load(props.workOrder, selectedSource.value)) sourcePickerOpen.value = false
	} catch (e) {
		fillError.value = e.message
	}
}

// Desk fallback colour query when the server sent no physical-output options:
// the IPD's Colour attribute-mapping values, else any Item Attribute Value of
// the Colour attribute (same order as work_order.js's get_query).
async function searchColourValues(row, q) {
	if (row.colour_mapping) {
		const res = await callMethod("frappe.desk.search.search_link", {
			doctype: "Item Attribute Value",
			txt: q || "",
			query: "essdee_yrp.ipd_ui.get_attribute_detail_values",
			filters: { mapping: row.colour_mapping },
		})
		const rows = Array.isArray(res) ? res : res?.results || []
		return rows.map((r) => ({ name: r.value ?? r.name ?? r }))
	}
	return searchLink("Item Attribute Value", q, { attribute_name: "Colour" })
}

function needsColourPicker(row) {
	if (row.kind !== "knitting" || !row.has_colour || isMultiColour(row)) return false
	if (!row.reference_routed) return true
	return (row.qty_rows || []).some((qr) => !qr.knit_colour)
}

// Colour-section layout descriptor (mirrors the Desk's `sectionable` branch):
// null = flat list. Sections keep server encounter order; each item keeps its
// ORIGINAL qty_rows index j, so entry collection / payload are layout-blind.
const SECTIONABLE_KINDS = ["conversion", "dyeing", "compacting", "identity"]

function sectionLayout(row) {
	const qtyRows = row.qty_rows || []
	const sections = []
	const bySection = {}
	qtyRows.forEach((qr, j) => {
		const key = qr.section == null ? " null" : String(qr.section)
		if (!bySection[key]) {
			bySection[key] = { name: qr.section, items: [] }
			sections.push(bySection[key])
		}
		bySection[key].items.push({ qr, j })
	})
	const sectionable = (SECTIONABLE_KINDS.includes(row.kind) || row.reference_routed)
		&& (row.reference_routed || qtyRows.length > 6)
		&& sections.length > 1
		&& qtyRows.every((qr) => qr.section != null)
	if (!sectionable) return null
	return { sections, asColumns: sections.length <= MAX_COLOUR_COLUMNS }
}

const layouts = computed(() => (ctx.value?.rows || []).map(sectionLayout))

// Every rendered qty input of context row i, with its qty_row — one place that
// knows both layouts, shared by the yarn total and the overshoot check.
function collectInputs(i) {
	const row = ctx.value.rows[i]
	const entry = entries.value[i]
	const inputs = []
	if (isMultiColour(row)) {
		for (const colour of row.colour_options) {
			;(row.qty_rows || []).forEach((qr, j) => {
				inputs.push({ qty: Number(entry.colourQtys[colour][j]) || 0, qr, colour })
			})
		}
	} else {
		;(row.qty_rows || []).forEach((qr, j) => {
			inputs.push({
				qty: Number(entry.qtys[j]) || 0,
				qr,
				colour: qr.knit_colour || null,
			})
		})
	}
	return inputs
}

// Non-blocking over-balance warning (production_api stance — knitting can
// legitimately over-deliver). Knitting and dyeing check the per-dia SUM of
// the dialog's own inputs (colours share one dia's balance); compacting is
// per row. Mirrors the Desk's warn_balance_overshoot.
function warnBalanceOvershoot() {
	const overs = []
	;(ctx.value?.rows || []).forEach((row, i) => {
		const inputs = collectInputs(i)
		if (row.kind === "knitting" || row.kind === "dyeing") {
			const perDia = {}
			const limitLabel = row.kind === "knitting" ? "balance" : "previous stage available"
			inputs.forEach(({ qty, qr }) => {
				const dia = qr.reference_item_variant
					|| (qr.out_attrs || {}).Dia
					|| qr.label
				const limit = row.kind === "knitting" ? qr.balance : qr.available
				if (!perDia[dia]) perDia[dia] = { sum: 0, limit }
				perDia[dia].sum += qty
			})
			Object.entries(perDia).forEach(([dia, agg]) => {
				if (agg.limit != null && agg.sum > agg.limit + 0.001) {
					overs.push(`${row.cloth_item} · ${dia}: ${agg.sum} > ${limitLabel} ${agg.limit}`)
				}
			})
		} else if (row.kind === "compacting") {
			inputs.forEach(({ qty, qr }) => {
				if (qty && qr.available != null && qty > qr.available + 0.001) {
					overs.push(`${row.cloth_item} · ${qr.label}: ${qty} > previous stage available ${qr.available}`)
				}
			})
		}
	})
	if (overs.length) toast.warn("Exceeds balance", overs.join(" — "))
}

function recomputeYarn(i) {
	const row = ctx.value.rows[i]
	const total = collectInputs(i).reduce((sum, { qty }) => sum + qty, 0)
	const yarn = row.ratio ? total / row.ratio : total
	entries.value[i].yarnQty = Math.round(yarn * 1000) / 1000
}

function yarnQuantity(i, yarn) {
	const row = ctx.value.rows[i]
	const totalCloth = collectInputs(i).reduce((sum, { qty }) => sum + qty, 0)
	const totalYarn = row.ratio ? totalCloth / row.ratio : totalCloth
	return Math.round(totalYarn * (Number(yarn.ratio) || 0) / 100 * 1000) / 1000
}

async function onApply() {
	if (loading.value || applying.value) return
	const rows = []
	for (let i = 0; i < (ctx.value?.rows || []).length; i++) {
		const row = ctx.value.rows[i]
		const entry = entries.value[i]
		const lines = []
		for (const { qty, qr, colour } of collectInputs(i)) {
			if (qty > 0) {
				const line = { key: qr.key, out_attrs: qr.out_attrs, qty }
				if (colour) line.colour = colour
				lines.push(line)
			}
		}
		if (!lines.length) continue
		if (row.kind === "knitting" && row.has_colour
			&& lines.some((line) => !line.colour) && !entry.colour) {
			toast.warn("Colour required", `Select the cloth Colour for ${row.cloth_item}.`)
			return
		}
		rows.push({
			fabric_row: row.fabric_row,
			// Desk parity (work_order.js fallback_colour): multi-colour rows post
			// null — each line already carries its own line-level colour.
			colour: isMultiColour(row) ? null : entry.colour || null,
			yarn_qty: !row.reference_routed && (row.yarns || []).length === 1
				? entry.yarnQty || null
				: null,
			entries: lines,
		})
	}
	if (!rows.length) {
		toast.warn("Nothing to calculate", "Enter a quantity for at least one row.")
		return
	}
	warnBalanceOvershoot()
	applying.value = true
	emit("applying") // before the write — see defineEmits note
	try {
		const res = await callMethod(
			"essdee_yrp.api.work_order.calculate_fabric_deliverables",
			{
				work_order: props.workOrder,
				rows: JSON.stringify(rows),
				modified: props.modified,
				source_process: ctx.value.source_process?.value || null,
			},
		)
		emit("update:visible", false)
		emit("calculated", res || {})
	} catch (e) {
		toast.error("Calculate failed", e.message)
	} finally {
		applying.value = false
	}
}
</script>

<style scoped>
.fc-source-note {
	display: flex;
	flex-direction: column;
	gap: 4px;
	padding: 12px 14px;
	border-radius: 8px;
	background: var(--esd-accent-50);
	font-size: 12.5px;
}
.fc-warning {
	padding: 10px 14px;
	background: var(--esd-warn-50);
	color: var(--esd-warn);
	font-size: 12px;
}
.fc-availability {
	color: var(--esd-muted);
	font-size: 11px;
}
.fc-loading {
	display: flex;
	align-items: center;
	gap: 8px;
	color: var(--esd-muted);
	padding: 16px 4px;
}
.fc-rows {
	display: flex;
	flex-direction: column;
	gap: 14px;
}
.fc-row {
	border: 1px solid var(--esd-line);
	border-radius: 10px;
	overflow: hidden;
	background: var(--esd-card);
}
.fc-row .esd-card__head {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: 8px;
}
.fc-ipd {
	font-size: 11px;
	color: var(--esd-muted);
}
.fc-note {
	padding: 8px 14px 0;
	font-size: 12.5px;
	color: var(--esd-muted);
}
.fc-field {
	display: flex;
	flex-direction: column;
	gap: 4px;
	padding: 8px 14px;
}
.fc-field:last-child {
	padding-bottom: 14px;
}
.fc-yarn-breakdown {
	display: flex;
	flex-direction: column;
	gap: 5px;
	padding: 8px 14px 14px;
}
.fc-yarn-line {
	display: flex;
	justify-content: space-between;
	gap: 16px;
	font-size: 12.5px;
}
/* one column per physical output colour / server section — wraps on small screens */
.fc-colour-grid {
	display: grid;
	grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
	gap: 4px;
	padding: 4px 0;
}
.fc-colour-col {
	border-left: 1px solid var(--esd-line);
	min-width: 0;
}
.fc-colour-col:first-child {
	border-left: none;
}
.fc-colour-head {
	font-weight: 600;
	font-size: 12.5px;
	padding: 6px 14px 0;
}
/* > MAX_COLOUR_COLUMNS sections: stacked full-width section blocks */
.fc-section-stack {
	display: flex;
	flex-direction: column;
	padding: 4px 0;
}
.fc-section-block + .fc-section-block {
	border-top: 1px solid var(--esd-line);
	margin-top: 6px;
	padding-top: 2px;
}
.fc-field--tight {
	padding: 6px 14px;
}
</style>
