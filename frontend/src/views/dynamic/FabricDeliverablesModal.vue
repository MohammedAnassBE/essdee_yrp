<template>
	<Dialog
		:visible="visible"
		modal
		class="fabric-calc-dialog"
		:style="{ width: 'min(880px, calc(100vw - 32px))' }"
		:header="dialogHeader"
		@update:visible="(v) => emit('update:visible', v)"
		@show="loadContext"
	>
		<div v-if="loading" class="fc-loading">
			<i class="pi pi-spin pi-spinner" /> Loading fabric context…
		</div>

		<div v-else-if="!ctx || !(ctx.rows || []).length" class="esd-empty">
			<i class="pi pi-info-circle" />
			<p class="esd-empty__text">
				This Work Order's process is not a fabric process (knitting / dyeing /
				compacting) for the Lot's fabrics — nothing to calculate here.
			</p>
		</div>

		<div v-else class="fc-rows">
			<section v-for="(row, i) in ctx.rows" :key="row.fabric_row" class="fc-row">
				<header class="esd-card__head">
					<span class="esd-card__title">{{ row.cloth_item }}</span>
					<span class="fc-ipd esd-mono">{{ row.production_detail }}</span>
				</header>

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
					<div class="fc-note">
						Yarn: <b>{{ row.yarn_item }}</b> · 1 kg yarn → {{ row.ratio }} kg cloth
					</div>
					<div v-if="row.has_colour && !isMultiColour(row)" class="fc-field">
						<label class="field-label">Cloth Colour *</label>
						<!-- too many colour choices for columns — single-colour fallback.
						     No greige colour_options at all: the SAME link query the Desk
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

				<!-- multi-colour knitting: one column per greige colour, an input per dia -->
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
							<small v-if="colour === row.colour_options[0] && planningLine(row.kind, qr)" class="fc-note-inline">
								{{ planningLine(row.kind, qr) }}
							</small>
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
							<InputNumber
								v-model="entries[i].qtys[it.j]"
								:min="0"
								:maxFractionDigits="3"
								fluid
								placeholder="0"
							/>
							<small v-if="planningLine(row.kind, it.qr)" class="fc-note-inline">
								{{ planningLine(row.kind, it.qr) }}
							</small>
						</div>
					</div>
				</div>

				<template v-else>
					<div v-for="(qr, j) in row.qty_rows || []" :key="qr.key" class="fc-field">
						<label class="field-label">{{ qr.label }}</label>
						<InputNumber
							v-model="entries[i].qtys[j]"
							:min="0"
							:maxFractionDigits="3"
							fluid
							placeholder="0"
							@update:modelValue="row.kind === 'knitting' && recomputeYarn(i)"
						/>
						<small v-if="planningLine(row.kind, qr)" class="fc-note-inline">
							{{ planningLine(row.kind, qr) }}
						</small>
					</div>
				</template>

				<div v-if="row.kind === 'knitting'" class="fc-field">
					<label class="field-label">Yarn (deliverable) Kg</label>
					<InputNumber
						v-model="entries[i].yarnQty"
						:min="0"
						:maxFractionDigits="3"
						fluid
						placeholder="0"
					/>
					<small class="fc-note-inline">
						Auto: total cloth ÷ {{ row.ratio }}. Edit only if reality differs.
					</small>
				</div>
			</section>
		</div>

		<template #footer>
			<Button label="Cancel" severity="secondary" text :disabled="applying" @click="emit('update:visible', false)" />
			<Button
				v-if="ctx && (ctx.rows || []).length"
				label="Calculate"
				icon="pi pi-calculator"
				:loading="applying"
				@click="onApply"
			/>
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
 * - Knitting: one COLUMN per greige colour (≤ MAX_COLOUR_COLUMNS) with an
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
 * - planning line per input = Desk's planning_description (null figures
 *   hidden, e.g. `available` on conversion / bought-greige lots).
 * - Non-blocking over-balance warning (production_api stance): knitting /
 *   dyeing per-dia sums vs balance / greige available, compacting per row.
 * Adapted (widgets only): frappe.ui.Dialog → PrimeVue Dialog, Float →
 * InputNumber, Link → Select/LinkField, HTML notes → styled divs.
 */
import { ref, computed } from "vue"
import Dialog from "primevue/dialog"
import Select from "primevue/select"
import InputNumber from "primevue/inputnumber"
import Button from "primevue/button"
import LinkField from "@/components/LinkField.vue"
import { callMethod, searchLink } from "@/api/client"
import { useAppToast } from "@/composables/useToast"

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
const emit = defineEmits(["update:visible", "calculated"])

const dialogHeader = computed(() =>
	props.processName
		? `Calculate Fabric Deliverables — ${props.processName}`
		: "Calculate Fabric Deliverables",
)

const toast = useAppToast()
const loading = ref(false)
const applying = ref(false)
const ctx = ref(null)
// One entry per context row: { colour, yarnQty, qtys: [per qty_row], colourQtys }
const entries = ref([])

async function loadContext() {
	loading.value = true
	ctx.value = null
	entries.value = []
	try {
		const r = await callMethod(
			"essdee_yrp.api.work_order.get_fabric_deliverable_context",
			{ work_order: props.workOrder },
		)
		ctx.value = r || { is_fabric_process: false, rows: [] }
		;(ctx.value.warnings || []).forEach((w) => toast.warn("Fabric row skipped", w))
		// Pre-fill the Lot program/plan balances (server-computed) + the greige
		// colour. Multi-colour knitting: a qty slot per (colour × dia); the
		// greige colour's column gets the balance prefills.
		entries.value = (ctx.value.rows || []).map((row) => {
			const entry = {
				// Row-level colour is the SINGLE-COLOUR fallback only. Multi-colour
				// rows carry a line-level colour per column — the Desk renders no
				// colour_${i} field there, so fallback_colour posts as null.
				colour: isMultiColour(row) ? null : row.greige_colour || null,
				yarnQty: null,
				qtys: (row.qty_rows || []).map((qr) => qr.prefill || null),
				colourQtys: {},
			}
			if (isMultiColour(row)) {
				entry.qtys = (row.qty_rows || []).map(() => null)
				for (const colour of row.colour_options) {
					entry.colourQtys[colour] = (row.qty_rows || []).map((qr) =>
						colour === row.greige_colour ? qr.prefill || null : null,
					)
				}
			}
			return entry
		})
		;(ctx.value.rows || []).forEach((row, i) => {
			if (row.kind === "knitting") recomputeYarn(i)
		})
	} catch (e) {
		toast.error("Couldn't load fabric context", e.message)
		emit("update:visible", false)
	} finally {
		loading.value = false
	}
}

// Desk fallback colour query when the server sent no greige colour_options:
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

// One planning line per qty row (mirrors the Desk dialog's field description).
// null figures are hidden — e.g. "available" on conversion steps (previous
// stage not tracked item-aware) or bought-greige lots where knitting isn't
// managed. `kg` rounds to 3 decimals like the Desk's flt(v, 3).
function planningLine(kind, qr) {
	const kg = (v) => `${Math.round((Number(v) || 0) * 1000) / 1000} kg`
	const parts = []
	if (kind === "knitting") {
		parts.push(`Program ${kg(qr.program)}`)
		if (Number(qr.received)) parts.push(`Received ${kg(qr.received)}`)
		parts.push(`Ordered ${kg(qr.ordered)}`, `Balance ${kg(qr.balance)}`)
	} else if (kind === "dyeing" || kind === "compacting" || kind === "conversion") {
		if (Number(qr.plan)) parts.push(`Plan ${kg(qr.plan)}`)
		parts.push(`Ordered ${kg(qr.ordered)}`)
		if (qr.available != null) parts.push(`Previous stage available ${kg(qr.available)}`)
	}
	return parts.join(" · ")
}

const MAX_COLOUR_COLUMNS = 6

function isMultiColour(row) {
	return row.kind === "knitting" && row.has_colour
		&& (row.colour_options || []).length > 0
		&& row.colour_options.length <= MAX_COLOUR_COLUMNS
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
	const sectionable = SECTIONABLE_KINDS.includes(row.kind)
		&& qtyRows.length > 6
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
			inputs.push({ qty: Number(entry.qtys[j]) || 0, qr, colour: null })
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
			const limitLabel = row.kind === "knitting" ? "balance" : "greige available"
			inputs.forEach(({ qty, qr }) => {
				const dia = (qr.out_attrs || {}).Dia || qr.label
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
					overs.push(`${row.cloth_item} · ${qr.label}: ${qty} > dyed available ${qr.available}`)
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

async function onApply() {
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
			yarn_qty: entry.yarnQty || null,
			entries: lines,
		})
	}
	if (!rows.length) {
		toast.warn("Nothing to calculate", "Enter a quantity for at least one row.")
		return
	}
	warnBalanceOvershoot()
	applying.value = true
	try {
		const res = await callMethod(
			"essdee_yrp.api.work_order.calculate_fabric_deliverables",
			{ work_order: props.workOrder, rows: JSON.stringify(rows), modified: props.modified },
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
.fc-note-inline {
	color: var(--esd-muted);
	font-size: 11.5px;
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
/* one column per greige colour / per server section — wraps on small screens */
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
