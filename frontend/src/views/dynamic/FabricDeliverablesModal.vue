<template>
	<Dialog
		:visible="visible"
		modal
		class="fabric-calc-dialog"
		:style="{ width: 'min(960px, calc(100vw - 32px))' }"
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
			<div v-if="ctx.source_process?.unavailable || !ctx.source_process" class="fc-source-note" role="status">
				<template v-if="ctx.source_process?.unavailable">
					<strong>No predecessor stock available</strong>
					<span>No unallocated submitted {{ ctx.source_process.label || ctx.source_process.process_name }} GRN quantity is available. Submit the predecessor GRN, then reopen this calculation.</span>
				</template>
				<template v-else-if="(ctx.rows || []).some((row) => row.manual_io)">
					<strong>Available knitting inputs and outputs</strong>
					<span>The IPD defines every yarn you can deliver and every fabric variant you can receive. Enter the required quantity against each item.</span>
				</template>
				<template v-else-if="(ctx.source_process_options || []).length">
					<strong>Immediate predecessor stock</strong>
					<span>Quantities are loaded from the immediately preceding process's submitted GRNs and checked again on Calculate.</span>
				</template>
				<template v-else>
					<strong>Planned quantities</strong>
					<span>Edit the process quantities shown below.</span>
				</template>
			</div>
			<div v-for="warning in ctx.warnings || []" :key="warning" class="fc-warning" role="status">{{ warning }}</div>
			<section v-for="(row, i) in ctx.rows" :key="row.fabric_row" class="fc-row">
				<header class="esd-card__head">
					<span class="esd-card__title">{{ row.cloth_item }}</span>
					<span class="fc-ipd esd-mono">{{ row.production_detail }}</span>
				</header>
				<div v-if="row.reference_routed && !row.manual_io" class="fc-note">
					Enter quantities by <b>finished cloth Colour and Dia</b>. The IPD determines the consumed inputs and this process's output.
				</div>
				<div v-if="row.manual_io" class="fc-contract-note">
					<strong>Enter deliverable and receivable quantities</strong>
					<span>Left: inputs you can deliver. Right: outputs you can receive. Each IPD-valid physical variant appears once.</span>
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

				<!-- Match the Work Order itself: one physical deliverable/receivable
				     row, with route allocations deliberately hidden from the operator. -->
				<div v-if="row.manual_io" class="fc-contract-lists">
					<section class="fc-contract-list fc-contract-list--send">
						<header class="fc-contract-list-title">
							<div>
								<strong>Yarn Deliverables</strong>
								<span>What you send</span>
							</div>
						</header>
						<div class="fc-contract-list-head" aria-hidden="true">
							<span>Item / Attributes</span>
							<span>Quantity</span>
						</div>
						<label
							v-for="item in entries[i].manualDeliverables || []"
							:key="item.key"
							class="fc-contract-item"
						>
							<span class="fc-contract-item-name">
								<strong>{{ item.item }}</strong>
								<small>{{ contractAttributeLabel(item.attrs) || 'No attributes' }}</small>
							</span>
							<span class="fc-contract-qty">
								<InputNumber
									v-model="item.qty"
									:min="0"
									:maxFractionDigits="3"
									fluid
									placeholder="0"
								/>
								<small>{{ item.uom || 'Kg' }}</small>
							</span>
						</label>
					</section>

					<section class="fc-contract-list fc-contract-list--receive">
						<header class="fc-contract-list-title">
							<div>
								<strong>Fabric Receivables</strong>
								<span>What you expect back</span>
							</div>
						</header>
						<div class="fc-contract-list-head" aria-hidden="true">
							<span>Item / Attributes</span>
							<span>Quantity</span>
						</div>
						<label
							v-for="item in entries[i].manualReceivables || []"
							:key="item.key"
							class="fc-contract-item"
						>
							<span class="fc-contract-item-name">
								<strong>{{ item.item }}</strong>
								<small>{{ contractAttributeLabel(item.attrs) || 'No attributes' }}</small>
							</span>
							<span class="fc-contract-qty">
								<InputNumber
									v-model="item.qty"
									:min="0"
									:maxFractionDigits="3"
									fluid
									placeholder="0"
								/>
								<small>{{ item.uom || 'Kg' }}</small>
							</span>
						</label>
					</section>
				</div>

				<!-- Legacy knitting: one column per physical output colour. -->
				<div v-else-if="isMultiColour(row)" class="fc-colour-grid">
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
								@update:modelValue="!row.manual_io && recomputeYarn(i)"
							/>
						</div>
					</div>
				</div>

				<!-- Colour is the primary card heading. Dia is the next visual group;
				     duplicate source-stock rows sit below one Dia heading. -->
				<div v-else-if="layouts[i]" class="fc-colour-card-grid">
					<section
						v-for="sec in layouts[i].sections"
						:key="String(sec.name)"
						class="fc-colour-card"
					>
						<header class="fc-colour-card-head">
							<span>
								<small class="fc-colour-kicker">Colour</small>
								<strong class="fc-colour-name">{{ sec.name }}</strong>
							</span>
							<small class="fc-entry-count">{{ sec.items.length }} entries</small>
						</header>
						<section v-for="dia in sec.diaGroups" :key="String(dia.name)" class="fc-dia-group">
							<header class="fc-dia-head">
								<span class="fc-dia-identity">
									<small class="fc-dia-kicker">Dia</small>
									<strong class="fc-dia-name">{{ dia.name }}</strong>
								</span>
								<small class="fc-dia-count">
									{{ dia.items.length }} {{ dia.items.length === 1 ? 'entry' : 'entries' }}
								</small>
							</header>
							<div class="fc-allocation-head" aria-hidden="true">
								<span>{{ availabilityHeading(row) }}</span>
								<span>Quantity to receive</span>
							</div>
							<div
								v-for="(it, stockIndex) in dia.items"
								:key="it.qr.key"
								class="fc-allocation-row"
							>
								<span class="fc-available-output">
									<strong>{{ availableOutputLabel(it.qr) }}</strong>
									<small
										v-if="dia.items.length > 1"
										:title="sourceReferenceLabel(row, it.qr)"
									>Stock {{ stockIndex + 1 }}</small>
								</span>
								<InputNumber
									v-model="entries[i].qtys[it.j]"
									:min="0"
									:maxFractionDigits="3"
									suffix=" Kg"
									fluid
									placeholder="0"
								/>
							</div>
						</section>
					</section>
				</div>

				<template v-else>
					<div v-for="(qr, j) in row.qty_rows || []" :key="qr.key" class="fc-field">
						<label class="field-label">{{ qr.label }}</label>
						<small v-if="sourceReferenceLabel(row, qr)" class="fc-source-ref">
							{{ sourceReferenceLabel(row, qr) }}
						</small>
						<InputNumber
							v-model="entries[i].qtys[j]"
							:min="0"
							:maxFractionDigits="3"
							fluid
							placeholder="0"
							@update:modelValue="row.kind === 'knitting' && !row.manual_io && recomputeYarn(i)"
						/>
					</div>
				</template>

				<div
					v-if="row.kind === 'knitting' && !row.manual_io && !row.reference_routed && (row.yarns || []).length === 1"
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
				<div v-else-if="row.kind === 'knitting' && !row.manual_io && !row.reference_routed" class="fc-yarn-breakdown">
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
				v-if="(ctx?.source_process_options || []).length > 1"
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
				:disabled="loading || ctx?.source_process?.unavailable"
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
 * - Knitting shows the same consolidated physical deliverable/receivable rows
 *   as the Work Order. Hidden matrix routes are restored proportionally on
 *   submit, and every entry posts its opaque matrix-group `key`.
 * - Other fabric processes keep one quantity input per IPD Process Matrix group.
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
import {
	buildColourDiaLayout,
	collectManualKnittingContract,
	isMultiColour,
	useFabricDeliverableContext,
} from "@/composables/useFabricDeliverableContext"

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

const QTY_EPSILON = 1e-9
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

const layouts = computed(() => (ctx.value?.rows || []).map(buildColourDiaLayout))

function displayQty(value) {
	const qty = Number(value)
	if (!Number.isFinite(qty)) return "—"
	return `${qty.toLocaleString(undefined, { maximumFractionDigits: 3 })} kg`
}

function availableOutputLabel(qr) {
	return displayQty(qr.source_available ?? qr.balance ?? qr.prefill)
}

function availabilityHeading(row) {
	return (row.qty_rows || []).some((qr) => qr.source_available != null)
		? "Available output"
		: "Planned quantity"
}

// Every rendered qty input of context row i, with its qty_row — one place that
// knows both layouts, shared by the yarn total and the overshoot check.
function collectInputs(i) {
	const row = ctx.value.rows[i]
	const entry = entries.value[i]
	if (row.manual_io) return collectManualKnittingContract(row, entry).routes
	const inputs = []
	if (isMultiColour(row)) {
		for (const colour of row.colour_options) {
			;(row.qty_rows || []).forEach((qr, j) => {
				inputs.push({
					qty: Number(entry.colourQtys[colour][j]) || 0,
					qr,
					colour,
				})
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

function contractAttributeLabel(attrs) {
	return Object.entries(attrs || {})
		.filter(([, value]) => value)
		.map(([attribute, value]) => `${attribute}: ${value}`)
		.join(" · ")
}

function sourceReferenceLabel(row, qr) {
	if (!qr?.source_bucket_key) return ""
	const route = `${qr.section || ""}|${qr.row_label || qr.label || ""}`
	const duplicates = (row.qty_rows || []).filter((candidate) => (
		candidate.source_bucket_key
		&& `${candidate.section || ""}|${candidate.row_label || candidate.label || ""}` === route
	))
	if (duplicates.length < 2) return ""
	const parts = [qr.source_grn || "Source GRN"]
	if (qr.source_grn_row) parts.push(`row ${qr.source_grn_row}`)
	if (qr.source_stock_available != null) {
		parts.push(`${Number(qr.source_stock_available).toLocaleString()} kg available`)
	}
	return parts.join(" · ")
}

function appendSourceOvershoots(row, inputs, overs) {
	const bySource = {}
	inputs.forEach(({ qty, qr }) => {
		const perOutput = Number(qr.source_stock_per_output)
		const capacity = Number(qr.source_stock_available)
		if (!qty || !qr.source_bucket_key || !(perOutput > 0) || !Number.isFinite(capacity)) return
		if (!bySource[qr.source_bucket_key]) {
			bySource[qr.source_bucket_key] = {
				demand: 0,
				capacity,
				label: qr.source_grn || qr.source_bucket_key,
			}
		}
		bySource[qr.source_bucket_key].demand += qty * perOutput
	})
	Object.values(bySource).forEach((source) => {
		if (source.demand > source.capacity + QTY_EPSILON) {
			overs.push(
				`${row.cloth_item} · ${source.label}: ${source.demand.toFixed(3)} kg > ${source.capacity} kg available`,
			)
		}
	})
}

// Non-blocking preview only. The server rechecks each exact GRN source on
// Calculate and again when a DC is submitted.
function warnBalanceOvershoot() {
	const overs = []
	;(ctx.value?.rows || []).forEach((row, i) => {
		const inputs = collectInputs(i)
		if (row.kind === "knitting") {
			const perDia = {}
			inputs.forEach(({ qty, qr }) => {
				const dia = qr.reference_item_variant
					|| (qr.out_attrs || {}).Dia
					|| qr.label
				const limit = qr.balance
				if (!perDia[dia]) perDia[dia] = { sum: 0, limit }
				perDia[dia].sum += qty
			})
			Object.entries(perDia).forEach(([dia, agg]) => {
				if (agg.limit != null && agg.sum > agg.limit + QTY_EPSILON) {
					overs.push(`${row.cloth_item} · ${dia}: ${agg.sum} > balance ${agg.limit}`)
				}
			})
		} else if (inputs.some(({ qr }) => qr.source_bucket_key)) {
			appendSourceOvershoots(row, inputs, overs)
		} else if (row.kind === "dyeing" || row.kind === "compacting") {
			inputs.forEach(({ qty, qr }) => {
				if (qty && qr.source_available != null && qty > qr.source_available + QTY_EPSILON) {
					overs.push(`${row.cloth_item} · ${qr.label}: ${qty} > previous stage available ${qr.source_available}`)
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
		const manualContract = row.manual_io
			? collectManualKnittingContract(row, entry)
			: null
		if (manualContract?.orphanDeliverables.length) {
			const item = manualContract.orphanDeliverables[0]
			toast.warn(
				"Fabric receivable required",
				`Enter a fabric receivable quantity before sending ${item.item}.`,
			)
			return
		}
		const lines = []
		const inputRows = manualContract?.routes || collectInputs(i)
		for (const { qty, qr, colour, manualInputs } of inputRows) {
			if (row.manual_io && qty <= 0 && manualInputs.some((input) => input.qty > 0)) {
				toast.warn(
					"Expected cloth required",
					`Enter the expected receivable quantity for ${qr.label}.`,
				)
				return
			}
			if (qty > 0) {
				const line = {
					key: qr.key,
					matrix_key: qr.matrix_key || qr.key,
					out_attrs: qr.out_attrs,
					qty,
				}
				if (qr.source_bucket_key) line.source_bucket_key = qr.source_bucket_key
				if (colour) line.colour = colour
				if (row.manual_io) {
					if (!manualInputs.some((input) => input.qty > 0)) {
						toast.warn(
							"Yarn quantity required",
							`Enter at least one yarn deliverable for ${qr.label}.`,
						)
						return
					}
					line.inputs = manualInputs
				}
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
			yarn_qty: !row.manual_io && !row.reference_routed && (row.yarns || []).length === 1
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
.fc-source-breakdown {
	margin-top: 4px;
	border-top: 1px solid var(--esd-line);
	padding-top: 6px;
}
.fc-source-breakdown summary {
	cursor: pointer;
	font-weight: 600;
}
.fc-source-line {
	display: grid;
	grid-template-columns: minmax(140px, 1fr) minmax(140px, 1fr) auto;
	gap: 10px;
	padding: 6px 0;
	border-bottom: 1px solid var(--esd-line);
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
.fc-source-ref {
	color: var(--esd-muted);
	font-size: 10.5px;
	line-height: 1.25;
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
.fc-contract-note {
	display: flex;
	flex-direction: column;
	gap: 3px;
	margin: 10px 14px;
	padding: 10px 12px;
	border: 1px solid var(--esd-line);
	border-radius: 8px;
	background: var(--esd-accent-50);
	font-size: 12px;
}
.fc-contract-lists {
	display: grid;
	grid-template-columns: repeat(2, minmax(0, 1fr));
	gap: 12px;
	margin: 0 14px 14px;
	align-items: start;
}
.fc-contract-list {
	border: 1px solid var(--esd-line);
	border-radius: 8px;
	overflow: hidden;
	background: var(--esd-card);
}
.fc-contract-list-title {
	display: flex;
	align-items: center;
	justify-content: space-between;
	padding: 11px 12px;
	border-left: 4px solid var(--esd-accent);
	background: var(--esd-accent-50);
}
.fc-contract-list--receive .fc-contract-list-title {
	border-left-color: var(--esd-success, #2f855a);
}
.fc-contract-list-title div,
.fc-contract-item-name {
	display: flex;
	flex-direction: column;
	min-width: 0;
}
.fc-contract-list-title strong {
	font-size: 13px;
}
.fc-contract-list-title span {
	font-size: 11px;
	color: var(--esd-muted);
}
.fc-contract-list-head,
.fc-contract-item {
	display: grid;
	grid-template-columns: minmax(0, 1fr) 130px;
	gap: 12px;
}
.fc-contract-list-head {
	padding: 7px 10px;
	background: var(--esd-surface);
	border-top: 1px solid var(--esd-line);
	border-bottom: 1px solid var(--esd-line);
	font-size: 10.5px;
	font-weight: 650;
	letter-spacing: 0.04em;
	text-transform: uppercase;
	color: var(--esd-muted);
}
.fc-contract-item {
	align-items: center;
	padding: 10px;
	cursor: text;
}
.fc-contract-item + .fc-contract-item {
	border-top: 1px solid var(--esd-line);
}
.fc-contract-item-name strong {
	font-size: 13px;
	font-weight: 600;
	color: var(--esd-text);
	line-height: 1.35;
	overflow-wrap: anywhere;
}
.fc-contract-item-name small {
	margin-top: 3px;
	font-size: 11px;
	color: var(--esd-muted);
	line-height: 1.35;
	overflow-wrap: anywhere;
}
.fc-contract-qty {
	display: grid;
	grid-template-columns: minmax(0, 1fr) auto;
	align-items: center;
	gap: 6px;
}
.fc-contract-qty small {
	font-size: 11px;
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
.fc-colour-card-grid {
	display: grid;
	grid-template-columns: repeat(auto-fit, minmax(270px, 1fr));
	gap: 12px;
	padding: 12px 14px 14px;
}
.fc-colour-card {
	min-width: 0;
	overflow: hidden;
	border: 1px solid var(--esd-line);
	border-radius: 9px;
	background: var(--esd-card);
}
.fc-colour-card-head {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: 10px;
	padding: 11px 12px;
	border-bottom: 1px solid var(--esd-line);
	background: var(--esd-slate-50);
}
.fc-colour-kicker,
.fc-dia-kicker {
	display: block;
	color: var(--esd-muted);
	font-size: 9px;
	font-weight: 750;
	letter-spacing: 0.12em;
	line-height: 1.1;
	text-transform: uppercase;
}
.fc-colour-name {
	display: block;
	margin-top: 2px;
	color: var(--esd-ink);
	font-size: 22px;
	font-weight: 700;
	letter-spacing: -0.02em;
	line-height: 1.1;
}
.fc-entry-count,
.fc-dia-count {
	flex: 0 0 auto;
	padding: 3px 7px;
	border: 1px solid var(--esd-line);
	border-radius: 999px;
	color: var(--esd-muted);
	background: var(--esd-card);
	font-size: 9.5px;
	font-weight: 650;
}
.fc-dia-group + .fc-dia-group {
	border-top: 3px solid var(--esd-slate-50);
}
.fc-dia-head {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: 10px;
	padding: 9px 12px;
	border-bottom: 1px solid var(--esd-line);
	background: var(--esd-accent-50);
}
.fc-dia-identity {
	display: flex;
	align-items: baseline;
	gap: 7px;
}
.fc-dia-kicker {
	display: inline;
	color: var(--esd-accent-700);
}
.fc-dia-name {
	color: var(--esd-accent-700);
	font-size: 17px;
	font-weight: 700;
	letter-spacing: -0.01em;
	line-height: 1;
}
.fc-dia-count {
	border-color: color-mix(in srgb, var(--esd-accent) 25%, var(--esd-line));
	color: var(--esd-accent-700);
}
.fc-allocation-head,
.fc-allocation-row {
	display: grid;
	grid-template-columns: minmax(90px, 0.9fr) minmax(120px, 1.1fr);
	align-items: center;
	gap: 12px;
}
.fc-allocation-head {
	padding: 7px 12px;
	border-bottom: 1px solid var(--esd-line);
	color: var(--esd-muted);
	background: var(--esd-card);
	font-size: 9px;
	font-weight: 700;
	letter-spacing: 0.07em;
	text-transform: uppercase;
}
.fc-allocation-row {
	min-height: 54px;
	padding: 8px 12px;
}
.fc-allocation-row + .fc-allocation-row {
	border-top: 1px solid var(--esd-line);
}
.fc-available-output {
	display: flex;
	flex-direction: column;
	min-width: 0;
}
.fc-available-output strong {
	color: var(--esd-ink-2);
	font-size: 12.5px;
	font-weight: 500;
	font-variant-numeric: tabular-nums;
}
.fc-available-output small {
	margin-top: 2px;
	color: var(--esd-muted);
	font-size: 10px;
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
@media (max-width: 720px) {
	.fc-contract-lists {
		grid-template-columns: 1fr;
	}
	.fc-colour-card-grid {
		grid-template-columns: 1fr;
		padding-inline: 10px;
	}
}
</style>
