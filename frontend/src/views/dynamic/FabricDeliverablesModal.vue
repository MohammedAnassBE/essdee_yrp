<template>
	<Dialog
		:visible="visible"
		modal
		class="fabric-calc-dialog"
		:style="{ width: 'min(640px, calc(100vw - 32px))' }"
		:header="`Calculate Fabric Deliverables`"
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
				<template v-if="row.kind === 'knitting'">
					<div class="fc-note">
						Yarn: <b>{{ row.yarn_item }}</b> · 1 kg yarn → {{ row.ratio }} kg cloth
					</div>
					<div v-if="row.has_colour && !isMultiColour(row)" class="fc-field">
						<label class="field-label">Cloth Colour *</label>
						<Select
							v-model="entries[i].colour"
							:options="row.colour_options || []"
							filter
							fluid
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
 * essdee_yrp/public/js/work_order.js (qty-rows contract, 2026-07-03).
 *
 * One quantity input per IPD Process Matrix group; every entry posts its
 * matrix-group `key` so the server resolves the exact group (never by attrs).
 * Knitting: derived Colour select (when the cloth declares Colour) + an
 * auto-computed, editable yarn deliverable (total ÷ cloth_per_kg_yarn).
 */
import { ref } from "vue"
import Dialog from "primevue/dialog"
import Select from "primevue/select"
import InputNumber from "primevue/inputnumber"
import Button from "primevue/button"
import { callMethod } from "@/api/client"
import { useAppToast } from "@/composables/useToast"

const props = defineProps({
	visible: { type: Boolean, default: false },
	workOrder: { type: String, required: true },
})
const emit = defineEmits(["update:visible", "calculated"])

const toast = useAppToast()
const loading = ref(false)
const applying = ref(false)
const ctx = ref(null)
// One entry per context row: { colour, yarnQty, qtys: [per qty_row] }
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
		// Pre-fill the Lot program balances (server-computed) + the greige colour.
		// Multi-colour knitting: a qty slot per (colour × dia); the greige
		// colour's column gets the balance prefills.
		entries.value = (ctx.value.rows || []).map((row) => {
			const entry = {
				colour: row.greige_colour || null,
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

// One planning line per qty row (mirrors the Desk dialog's field description).
// null "available" is hidden — e.g. bought-greige lots where knitting isn't managed.
function planningLine(kind, qr) {
	const kg = (v) => `${Number(v) || 0} kg`
	const parts = []
	if (kind === "knitting") {
		parts.push(`Program ${kg(qr.program)}`)
		if (Number(qr.received)) parts.push(`Received ${kg(qr.received)}`)
		parts.push(`Ordered ${kg(qr.ordered)}`, `Balance ${kg(qr.balance)}`)
	} else if (kind === "dyeing" || kind === "compacting") {
		if (Number(qr.plan)) parts.push(`Plan ${kg(qr.plan)}`)
		parts.push(`Ordered ${kg(qr.ordered)}`)
		if (qr.available != null) parts.push(`Previous stage available ${kg(qr.available)}`)
	}
	return parts.join(" · ")
}

// Non-blocking over-balance warning (production_api stance): dyeing checks the
// per-dia SUM of this dialog's rows against the greige balance.
function warnBalanceOvershoot() {
	const overs = []
	;(ctx.value?.rows || []).forEach((row, i) => {
		const qty_at = (j) => Number(entries.value[i].qtys[j]) || 0
		if (row.kind === "knitting") {
			// balance is per dia — sum across colour columns before comparing
			;(row.qty_rows || []).forEach((qr, j) => {
				let sum = qty_at(j)
				for (const qtys of Object.values(entries.value[i].colourQtys || {})) {
					sum += Number(qtys[j]) || 0
				}
				if (sum && qr.balance != null && sum > qr.balance + 0.001) {
					overs.push(`${row.cloth_item} · ${qr.label}: ${sum} > balance ${qr.balance}`)
				}
			})
		} else if (row.kind === "dyeing") {
			const perDia = {}
			;(row.qty_rows || []).forEach((qr, j) => {
				const dia = (qr.out_attrs || {}).Dia || ""
				if (!perDia[dia]) perDia[dia] = { sum: 0, available: qr.available }
				perDia[dia].sum += qty_at(j)
			})
			Object.entries(perDia).forEach(([dia, d]) => {
				if (d.available != null && d.sum > d.available + 0.001) {
					overs.push(`${row.cloth_item} · ${dia}: ${d.sum} > greige available ${d.available}`)
				}
			})
		} else if (row.kind === "compacting") {
			;(row.qty_rows || []).forEach((qr, j) => {
				if (qty_at(j) && qr.available != null && qty_at(j) > qr.available + 0.001) {
					overs.push(`${row.cloth_item} · ${qr.label}: ${qty_at(j)} > dyed available ${qr.available}`)
				}
			})
		}
	})
	if (overs.length) toast.warn("Exceeds balance", overs.join(" — "))
}

const MAX_COLOUR_COLUMNS = 6

function isMultiColour(row) {
	return row.kind === "knitting" && row.has_colour
		&& (row.colour_options || []).length > 0
		&& row.colour_options.length <= MAX_COLOUR_COLUMNS
}

function rowQtyTotal(i) {
	const entry = entries.value[i]
	let total = (entry.qtys || []).reduce((sum, q) => sum + (Number(q) || 0), 0)
	for (const qtys of Object.values(entry.colourQtys || {})) {
		total += qtys.reduce((sum, q) => sum + (Number(q) || 0), 0)
	}
	return total
}

function recomputeYarn(i) {
	const row = ctx.value.rows[i]
	const total = rowQtyTotal(i)
	const yarn = row.ratio ? total / row.ratio : total
	entries.value[i].yarnQty = Math.round(yarn * 1000) / 1000
}

async function onApply() {
	const rows = []
	for (let i = 0; i < (ctx.value?.rows || []).length; i++) {
		const row = ctx.value.rows[i]
		const entry = entries.value[i]
		const lines = []
		if (isMultiColour(row)) {
			for (const colour of row.colour_options) {
				;(row.qty_rows || []).forEach((qr, j) => {
					const qty = Number(entry.colourQtys[colour][j]) || 0
					if (qty > 0) lines.push({ key: qr.key, out_attrs: qr.out_attrs, qty, colour })
				})
			}
		} else {
			;(row.qty_rows || []).forEach((qr, j) => {
				const qty = Number(entry.qtys[j]) || 0
				if (qty > 0) lines.push({ key: qr.key, out_attrs: qr.out_attrs, qty })
			})
		}
		if (!lines.length) continue
		if (row.kind === "knitting" && row.has_colour && !isMultiColour(row) && !entry.colour) {
			toast.warn("Colour required", `Select the cloth Colour for ${row.cloth_item}.`)
			return
		}
		rows.push({
			fabric_row: row.fabric_row,
			colour: entry.colour || null,
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
			{ work_order: props.workOrder, rows: JSON.stringify(rows) },
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
.fc-colour-grid {
	display: grid;
	grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
	gap: 4px;
	padding: 4px 0;
}
.fc-colour-col {
	border-left: 1px solid var(--esd-line);
}
.fc-colour-col:first-child {
	border-left: none;
}
.fc-colour-head {
	font-weight: 600;
	font-size: 12.5px;
	padding: 6px 14px 0;
}
.fc-field--tight {
	padding: 6px 14px;
}
</style>
