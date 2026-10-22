<template>
	<ReportShell
		title="Multi CCR"
		:generated="generated"
		:loading="loading"
		:error="error"
		:has-results="hasResults"
		@generate="generate"
		@reset="reset"
	>
		<template #filters>
			<AsyncLinkMultiSelect v-model="filters.lots" doctype="SD YRP Lot" label="Lots" placeholder="Search lots…" />
			<AsyncLinkMultiSelect v-model="filters.items" doctype="Item" label="Items" placeholder="Search items…" />
			<label><span class="erp-field-label">Status</span><select class="erp-native-select" v-model="filters.status"><option value="">All statuses</option><option value="Open">Open</option><option value="Closed">Closed</option></select></label>
			<LinkField v-model="filters.category" doctype="Product Category" label="Product category" placeholder="Search category…" :show-open-button="false" show-clear />
		</template>
		<template #actions><Button label="Paste" icon="pi pi-clipboard" severity="secondary" outlined :disabled="loading" @click="pasteVisible = true" /></template>

		<template #metrics>
			<div class="report-metric"><i class="pi pi-inbox" /><div><span>Output lots</span><strong>{{ number(result.output_lots?.length) }}</strong></div></div>
			<div class="report-metric"><i class="pi pi-tags" /><div><span>Output styles</span><strong>{{ number(result.output_items?.length) }}</strong></div></div>
			<div class="report-metric"><i class="pi pi-check-square" /><div><span>Completed pieces</span><strong>{{ number(totalPieces) }}</strong></div></div>
			<div class="report-metric"><i class="pi pi-chart-line" /><div><span>Panel groups</span><strong>{{ number(panelGroupCount) }}</strong></div></div>
		</template>

		<section class="selection-summary">
			<div><span>Requested lots</span><p>{{ selected.lots.length ? selected.lots.join(", ") : "Category / item selection" }}</p></div>
			<div><span>Returned lots</span><p>{{ result.output_lots?.join(", ") || "—" }}</p></div>
			<div><span>Requested items</span><p>{{ selected.items.length ? selected.items.join(", ") : "Category / lot selection" }}</p></div>
			<div><span>Returned items</span><p>{{ result.output_items?.join(", ") || "—" }}</p></div>
		</section>

		<section class="report-section">
			<header class="erp-section-header"><div><p>Consolidated</p><h3>Style-wise summary</h3></div><span class="erp-count-badge">{{ itemEntries.length }} styles</span></header>
			<div class="summary-stack">
				<details v-for="([itemName, item], index) in itemEntries" :key="itemName" class="summary-card" :open="index === 0">
					<summary><span><strong>{{ itemName }}</strong><small>{{ number(item.total_qty) }} completed pieces</small></span><i class="pi pi-chevron-down" /></summary>
					<div class="summary-card__body">
						<CompletionMatrix :groups="item.completed_json || []" :total-qty="item.total_qty" :average-piece-weight="item.average_piece_weight_by_colour || {}" :average-required-weight="item.average_required_weight_by_colour || {}" show-averages />
						<div class="subsection-label"><span>Cloth consumption</span><span class="erp-count-badge">{{ item.cloth_details?.length || 0 }}</span></div>
						<ClothTable :rows="item.cloth_details || []" :totals="item.cloth_total" />
					</div>
				</details>
			</div>
		</section>

		<section class="report-section">
			<header class="erp-section-header"><div><p>Traceability</p><h3>Lot-wise cutting detail</h3></div><span class="erp-count-badge">{{ lotEntries.length }} lots</span></header>
			<div class="summary-stack">
				<details v-for="([lotName, lot], index) in lotEntries" :key="lotName" class="summary-card" :open="index === 0">
					<summary><span><strong>{{ lotName }}</strong><small>{{ lot.item }} · {{ number(lot.total_qty) }} pieces</small></span><i class="pi pi-chevron-down" /></summary>
					<div class="summary-card__body">
						<section v-for="(group, groupIndex) in lot.panel_groups || []" :key="`${group.cutting_plan}-${groupIndex}`" class="panel-group">
							<div class="subsection-label"><span>{{ group.panels || "Panel group" }}</span><small>{{ group.cutting_plan }}</small></div>
							<div class="erp-table-wrap"><table class="erp-data-table panel-group-table"><thead><tr><th>#</th><th>Colour</th><th>Cloth type</th><th class="erp-number">Received wt.</th><th class="erp-number">Used wt.</th><th class="erp-number">Balance wt.</th><th v-for="size in group.sizes || []" :key="size" class="erp-number">{{ size }}</th><th class="erp-number">Total</th><th class="erp-number">Piece wt.</th><th class="erp-number">Required wt.</th></tr></thead><tbody>
								<tr v-for="(row, rowIndex) in group.rows || []" :key="rowIndex"><td>{{ rowIndex + 1 }}</td><td>{{ row.colour || "—" }}</td><td>{{ row.cloth_type || "—" }}</td><td class="erp-number">{{ number(row.received_weight, 3) }}</td><td class="erp-number">{{ number(row.used_weight, 3) }}</td><td class="erp-number">{{ number(row.balance_weight, 3) }}</td><td v-for="size in group.sizes || []" :key="size" class="erp-number">{{ quantity(row.sizes?.[size]) }}</td><td class="erp-number">{{ quantity(row.total_pieces) }}</td><td class="erp-number">{{ number(row.piece_weight, 4) }}</td><td class="erp-number">{{ number(row.required_weight, 4) }}</td></tr>
								<tr class="report-total"><td></td><td>Total</td><td></td><td class="erp-number">{{ number(group.totals?.received_weight, 3) }}</td><td class="erp-number">{{ number(group.totals?.used_weight, 3) }}</td><td class="erp-number">{{ number(group.totals?.balance_weight, 3) }}</td><td v-for="size in group.sizes || []" :key="size" class="erp-number">{{ quantity(group.totals?.sizes?.[size]) }}</td><td class="erp-number">{{ quantity(group.totals?.total_pieces) }}</td><td class="erp-number">{{ number(group.totals?.piece_weight, 4) }}</td><td class="erp-number">{{ number(group.totals?.required_weight, 4) }}</td></tr>
							</tbody></table></div>
						</section>

						<section v-if="lot.recut_summary?.rows?.length" class="panel-group">
							<div class="subsection-label"><span>Recut summary</span><span class="erp-status erp-status--warning">{{ lot.recut_summary.rows.length }} rows</span></div>
							<div class="erp-table-wrap"><table class="erp-data-table"><thead><tr><th>#</th><th>Cloth type</th><th>Colour</th><th>Dia</th><th>Shade</th><th class="erp-number">Weight (kg)</th><th class="erp-number">Rolls</th></tr></thead><tbody><tr v-for="(row, rowIndex) in lot.recut_summary.rows" :key="rowIndex"><td>{{ rowIndex + 1 }}</td><td>{{ row.cloth_type || "—" }}</td><td>{{ row.colour || "—" }}</td><td>{{ row.dia || "—" }}</td><td>{{ row.shade || "—" }}</td><td class="erp-number">{{ number(row.weight, 3) }}</td><td class="erp-number">{{ quantity(row.no_of_rolls) }}</td></tr><tr class="report-total"><td></td><td>Total</td><td colspan="3"></td><td class="erp-number">{{ number(lot.recut_summary.totals?.weight, 3) }}</td><td class="erp-number">{{ quantity(lot.recut_summary.totals?.no_of_rolls) }}</td></tr></tbody></table></div>
						</section>

						<div class="subsection-label"><span>Completed cut quantity</span></div>
						<CompletionMatrix :groups="lot.completed_json || []" :total-qty="lot.total_qty" />
						<div class="subsection-label"><span>Cloth consumption</span><span class="erp-count-badge">{{ lot.cloth_details?.length || 0 }}</span></div>
						<ClothTable :rows="lot.cloth_details || []" :totals="lot.cloth_total" />
					</div>
				</details>
			</div>
		</section>
	</ReportShell>
	<PasteListDialog v-model:visible="pasteVisible" @apply="paste" />
</template>

<script setup>
import Button from "primevue/button"
import { computed, reactive, ref } from "vue"

import { getMultiCcrReport } from "../../../api/cuttingReports.js"
import LinkField from "../../../components/common/LinkField.vue"
import AsyncLinkMultiSelect from "./AsyncLinkMultiSelect.vue"
import ClothTable from "./ClothTable.vue"
import CompletionMatrix from "./CompletionMatrix.vue"
import ReportShell from "../../../components/reports/ReportShell.vue"
import PasteListDialog from "../../../components/reports/PasteListDialog.vue"
import { mergeNames } from "../../../components/reports/pasteValues.js"
import { errorMessage, number, quantity } from "../../../components/reports/reportUtils.js"

const filters = reactive(defaultFilters())
const selected = reactive({ lots: [], items: [] })
const result = reactive(emptyResult())
const loading = ref(false)
const pasteVisible = ref(false)
const generated = ref(false)
const error = ref("")

const lotEntries = computed(() => Object.entries(result.data || {}))
const itemEntries = computed(() => Object.entries(result.item_data || {}))
const hasResults = computed(() => lotEntries.value.length > 0 || itemEntries.value.length > 0)
const totalPieces = computed(() => itemEntries.value.reduce((total, [, item]) => total + Number(item.total_qty || 0), 0))
const panelGroupCount = computed(() => lotEntries.value.reduce((total, [, lot]) => total + (lot.panel_groups?.length || 0), 0))

function defaultFilters() { return { lots: [], items: [], status: "Open", category: "Inner" } }
function emptyResult() { return { output_lots: [], output_items: [], data: {}, item_data: {} } }
async function generate() {
	if (!filters.lots.length && !filters.items.length && !filters.category) { error.value = "Select at least one Item or Lot, or select a Product category."; return }
	error.value = ""
	loading.value = true
	try {
		const response = await getMultiCcrReport({ open_status: filters.status, lot_list: filters.lots, item_list: filters.items, category: filters.category }) || emptyResult()
		Object.assign(result, emptyResult(), response)
		selected.lots = [...filters.lots]
		selected.items = [...filters.items]
		generated.value = true
	} catch (exception) { error.value = errorMessage(exception) }
	finally { loading.value = false }
}
function paste({ target, names }) { const key = target === "item" ? "items" : "lots"; filters[key] = mergeNames(filters[key], names) }
function reset() {
	Object.assign(filters, defaultFilters())
	Object.assign(selected, { lots: [], items: [] })
	Object.assign(result, emptyResult())
	generated.value = false
	error.value = ""
}
</script>

<style scoped>
.selection-summary {
	display: grid;
	grid-template-columns: repeat(2, minmax(0, 1fr));
	overflow: hidden;
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-control-radius);
}

.selection-summary div {
	min-width: 0;
	padding: 9px 11px;
	border-right: 1px solid var(--erp-border);
	border-bottom: 1px solid var(--erp-border);
	background: var(--erp-surface-soft);
}

.selection-summary div:nth-child(2n) {
	border-right: 0;
}

.selection-summary div:nth-last-child(-n + 2) {
	border-bottom: 0;
}

.selection-summary span {
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
	font-weight: 800;
	text-transform: uppercase;
}

.selection-summary p {
	margin: 3px 0 0;
	overflow: hidden;
	color: #33483f;
	font-size: var(--erp-font-size-caption);
	line-height: 1.35;
	text-overflow: ellipsis;
	white-space: nowrap;
}

.report-section {
	display: grid;
	gap: 9px;
}

.report-section > .erp-section-header {
	padding: 0 2px;
}

.report-section > .erp-section-header p {
	margin: 0 0 2px;
	color: var(--erp-accent);
	font-size: var(--erp-font-size-min);
	font-weight: 800;
	letter-spacing: 0.055em;
	text-transform: uppercase;
}

.summary-stack {
	display: grid;
	gap: 9px;
}

.summary-card {
	overflow: hidden;
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-control-radius);
}

.summary-card summary {
	display: flex;
	align-items: center;
	justify-content: space-between;
	padding: 10px var(--erp-space-3);
	background: var(--erp-surface-soft);
	cursor: pointer;
	list-style: none;
}

.summary-card summary::-webkit-details-marker {
	display: none;
}

.summary-card summary span {
	display: grid;
	min-width: 0;
	gap: 2px;
}

.summary-card summary strong,
.summary-card summary small {
	max-width: min(980px, 72vw);
	overflow: hidden;
	text-overflow: ellipsis;
	white-space: nowrap;
}

.summary-card summary strong {
	font-size: 13px;
}

.summary-card summary small {
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
}

.summary-card summary i {
	color: var(--erp-accent);
	font-size: var(--erp-font-size-caption);
	transition: transform var(--erp-transition-fast);
}

.summary-card[open] summary i {
	transform: rotate(180deg);
}

.summary-card__body {
	display: grid;
	gap: var(--erp-space-3);
	padding: var(--erp-space-3);
	border-top: 1px solid var(--erp-border);
}

.subsection-label {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: var(--erp-space-2);
	color: #354b41;
	font-size: var(--erp-font-size-caption);
	font-weight: 800;
}

.subsection-label small {
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
	font-weight: 600;
}

.panel-group {
	display: grid;
	gap: 7px;
}

.panel-group-table {
	min-width: 1080px;
}

.report-total td {
	background: #f0f7f3;
	font-weight: 800;
}

@media (max-width: 700px) {
	.selection-summary {
		grid-template-columns: 1fr;
	}

	.selection-summary div {
		border-right: 0;
	}

	.selection-summary div:nth-last-child(2) {
		border-bottom: 1px solid var(--erp-border);
	}
}
</style>
