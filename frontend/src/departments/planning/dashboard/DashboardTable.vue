<template>
	<section class="pd-panel pd-section" aria-label="Lot-wise table">
		<header class="pd-toolbar">
			<div>
				<h2>{{ isGrouped ? "PPOs" : "Lots" }}</h2>
				<p :data-count="sorted.length">{{ rangeText }} · sorted by {{ sortLabel }}<template v-if="isGrouped"> · {{ plural(rows.length, "lot") }} grouped</template></p>
			</div>
			<div class="pd-toolbar__end">
				<div v-if="paged.pages > 1" class="pd-pager">
					<Button label="‹ Prev" size="small" severity="secondary" outlined :disabled="!paged.page" @click="page = paged.page - 1" />
					<span>Page {{ paged.page + 1 }} of {{ paged.pages }}</span>
					<Button label="Next ›" size="small" severity="secondary" outlined :disabled="paged.page >= paged.pages - 1" @click="page = paged.page + 1" />
				</div>
				<label class="pd-check"><Checkbox v-model="isGrouped" binary input-id="pd-group-by-ppo" /><span>Group by PPO</span></label>
				<Button label="Copy CSV" size="small" severity="secondary" outlined @click="copy" />
			</div>
		</header>
		<div class="pd-table-wrap">
			<table class="pd-table pd-dash-table" :class="{ 'is-grouped': isGrouped }">
				<thead>
					<tr>
						<th class="pd-number">#</th>
						<th v-for="column in COLUMNS" :key="column.key" :class="{ 'pd-number': column.isNumber }" :title="columnTitle(column)" :aria-sort="ariaSort(column.key)">
							<button type="button" class="pd-sort" :data-sort="column.key" @click="sortBy(column.key)">{{ isGrouped && column.key === "lot" ? "Lots" : column.label }}<i>{{ sortMark(column.key) }}</i></button>
						</th>
					</tr>
				</thead>
				<tbody>
					<tr v-for="(row, index) in paged.rows" :key="isGrouped ? row.ppo : row.lot" :class="{ 'is-dispatched': row.status === 'Dispatched' }" :data-row="isGrouped ? row.ppo : row.lot">
						<td class="pd-number pd-muted">{{ paged.start + index + 1 }}</td>
						<td><button type="button" class="pd-link" @click="emit('drill', rowDrill(row, false))">{{ row.ppo }}</button></td>
						<td :class="isGrouped ? 'pd-lots-cell' : 'pd-lot-cell'">
							<template v-if="isGrouped">
								<template v-for="(lot, lotIndex) in row.lots" :key="lot.lot"><span v-if="lotIndex" class="pd-muted">, </span><button type="button" class="pd-link" @click="emit('drill', rowDrill(lot, true))">{{ lot.lot }}</button></template>
							</template>
							<button v-else type="button" class="pd-link pd-ellipsis" :title="row.lot" @click="emit('drill', rowDrill(row, true))">{{ row.lot }}</button>
						</td>
						<td class="pd-item-cell" :title="row.isGroup && row.items.length > 1 ? row.items.join(', ') : row.item">{{ row.item }}</td>
						<td>
							<span class="pd-status-mix" :title="row.isGroup ? row.breakdown : undefined"><LotStatusPill :status="row.status" /><em v-if="row.isGroup && row.otherStatuses">+{{ row.otherStatuses }}</em></span>
						</td>
						<td class="pd-number">{{ ppoQuantityText(row.ppo) }}<small v-if="!ppos[row.ppo]?.pieces" class="pd-unit">box</small></td>
						<td v-for="field in SUMMED_FIELDS" :key="field" class="pd-number" :data-col="field">{{ formatQuantity(row[field]) }}</td>
					</tr>
					<tr v-if="!paged.rows.length"><td :colspan="COLUMNS.length + 1" class="pd-empty">No lots match these filters.</td></tr>
				</tbody>
			</table>
		</div>
	</section>
</template>

<script setup>
import Button from "primevue/button"
import Checkbox from "primevue/checkbox"
import { useToast } from "primevue/usetoast"
import { computed, ref, watch } from "vue"

import LotStatusPill from "./LotStatusPill.vue"
import { copyCsv } from "./copyCsv.js"
import { formatQuantity, plural } from "./dashboardFormat.js"
import { SUMMED_FIELDS, dashboardCsv, groupDashboardRows, pageRows, rowDrill, sortDashboardRows } from "./dashboardRows.js"

/** Flat lot table (or one row per PPO) with sorting, 50-row pages and Copy CSV. */
const props = defineProps({
	rows: { type: Array, required: true },
	ppos: { type: Object, required: true },
	sewingProcesses: { type: Array, default: () => [] },
})
const emit = defineEmits(["drill"])
const toast = useToast()
const COLUMNS = [
	{ key: "ppo", label: "PPO" },
	{ key: "lot", label: "Lot" },
	{ key: "item", label: "Item" },
	{ key: "status", label: "Status" },
	{ key: "ppoQty", label: "PPO Qty", isNumber: true, title: "PPO pcs = boxes × pieces per box; 'box' when the PPO has no single pieces per box. Repeated on every lot of the PPO" },
	{ key: "qty", label: "Lot Qty", isNumber: true, title: "Lot order pcs (as Lot pcs in PPO Tracking)" },
	{ key: "cut", label: "Cut Qty", isNumber: true, title: "Pcs received from Cutting Work Orders" },
	{ key: "stitch", label: "Stitching Qty", isNumber: true, title: "" },
	{ key: "packed", label: "Packed Qty", isNumber: true, title: "Pcs received from the lot's packing Work Orders (Includes Packing); each WO counted once" },
	{ key: "dispatch", label: "Dispatched Qty", isNumber: true, title: "Dispatch pcs (as in PPO Tracking)" },
]
const sort = ref({ key: "ppo", direction: 1 })
const page = ref(0)
const isGrouped = ref(false)

const tableRows = computed(() => (isGrouped.value ? groupDashboardRows(props.rows) : props.rows))
const sorted = computed(() => sortDashboardRows(tableRows.value, sort.value, props.ppos))
const paged = computed(() => pageRows(sorted.value, page.value))
const unit = computed(() => (isGrouped.value ? "PPO" : "lot"))
const sortLabel = computed(() => COLUMNS.find((column) => column.key === sort.value.key)?.label)
const rangeText = computed(() => (sorted.value.length
	? `${formatQuantity(paged.value.start + 1)}–${formatQuantity(paged.value.start + paged.value.rows.length)} of ${plural(sorted.value.length, unit.value)}`
	: `No ${unit.value}s`))

watch(() => [props.rows, isGrouped.value], () => { page.value = 0 })

function columnTitle(column) {
	const title = column.key === "stitch"
		? `Pcs received from sewing Work Orders (${props.sewingProcesses.join(", ")}); each WO counted once`
		: column.title
	if (!title) return undefined
	return isGrouped.value && SUMMED_FIELDS.includes(column.key) ? `${title} · summed over the PPO's filtered lots` : title
}

function sortBy(key) {
	sort.value = { key, direction: sort.value.key === key ? -sort.value.direction : 1 }
	page.value = 0
}

const sortMark = (key) => (sort.value.key === key ? (sort.value.direction > 0 ? "▲" : "▼") : "↕")
const ariaSort = (key) => (sort.value.key === key ? (sort.value.direction > 0 ? "ascending" : "descending") : "none")

function ppoQuantityText(ppo) {
	const info = props.ppos[ppo] || {}
	return info.pieces ? formatQuantity(info.pieces) : formatQuantity(info.boxes, Number(info.boxes) % 1 !== 0)
}

function copy() {
	copyCsv(toast, dashboardCsv(sorted.value, isGrouped.value, props.ppos), sorted.value.length, unit.value)
}
</script>
