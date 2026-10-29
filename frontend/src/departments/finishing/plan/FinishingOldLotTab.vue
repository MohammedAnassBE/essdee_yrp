<template>
	<div class="finishing-stack">
		<section v-for="matrix in transferMatrices" :key="matrix.key" class="finishing-section" :aria-label="matrix.title">
			<h3 class="finishing-section__title">{{ matrix.title }}</h3>
			<div class="finishing-scroll" role="region" tabindex="0" :aria-label="matrix.title">
				<table class="finishing-table">
					<thead>
						<tr>
							<th class="finishing-table__index">#</th>
							<th>{{ matrix.counterpart }}</th>
							<th>Colour</th>
							<th>Part</th>
							<th>Bucket</th>
							<th v-for="size in matrix.sizes" :key="size" class="erp-number">{{ size }}</th>
							<th class="erp-number">Total</th>
							<th>Lot Transfers</th>
						</tr>
					</thead>
					<tbody v-for="(group, index) in matrix.groups" :key="`${group.fp}-${group.colour}-${group.part}`">
						<tr v-for="(bucket, bucketIndex) in buckets(group)" :key="bucket.key">
							<template v-if="bucketIndex === 0">
								<td :rowspan="buckets(group).length" class="finishing-table__index">{{ index + 1 }}</td>
								<td :rowspan="buckets(group).length"><strong><DocumentLink doctype="SD YRP Finishing Plan" :name="group.fp" :label="group.fp" /></strong><small class="old-lot__sub"><DocumentLink doctype="SD YRP Lot" :name="group.lot" :label="group.lot" /></small></td>
								<td :rowspan="buckets(group).length">{{ group.colour }}</td>
								<td :rowspan="buckets(group).length">{{ group.part || "—" }}</td>
							</template>
							<td><span class="old-lot__bucket" :class="`old-lot__bucket--${bucket.key}`">{{ bucket.label }}</span></td>
							<td v-for="size in matrix.sizes" :key="size" class="erp-number">{{ bucket.values[size] ? formatQuantity(bucket.values[size]) : "—" }}</td>
							<td class="erp-number finishing-table__row-total">{{ formatQuantity(bucket.total) }}</td>
							<td v-if="bucketIndex === 0" :rowspan="buckets(group).length">
								<span v-for="transfer in group.lts || []" :key="transfer" class="old-lot__transfer">{{ transfer }}</span>
							</td>
						</tr>
					</tbody>
				</table>
			</div>
		</section>

		<p v-if="!transferMatrices.length && !data.available" class="finishing-empty">No old lot transfers for this Finishing Plan.</p>
		<section v-if="data.available" class="finishing-section" aria-label="Available loose pieces">
			<div class="old-lot__toolbar">
				<h3 class="finishing-section__title">Available in Other Finishing Plans</h3>
				<div v-if="canTransfer" class="old-lot__actions">
					<Button label="Fetch Items" icon="pi pi-refresh" severity="secondary" outlined :disabled="busy" @click="emit('fetch')" />
					<Button label="Lot Transfer" icon="pi pi-arrow-right-arrow-left" :disabled="busy || !availableRows.length" @click="submitTransfer" />
				</div>
			</div>
			<p v-if="!availableRows.length" class="finishing-empty">No transferable loose pieces found in other Finishing Plans for this item.</p>
			<div v-for="row in availableRows" :key="`${row.source_fp}-${row.lot}-${row.warehouse}`" class="finishing-section">
				<h4 class="old-lot__lot"><DocumentLink doctype="SD YRP Lot" :name="row.lot" :label="row.lot" /> <small><DocumentLink doctype="SD YRP Finishing Plan" :name="row.source_fp" :label="row.source_fp" /> · {{ row.warehouse_name }}</small></h4>
				<div class="finishing-scroll" role="region" tabindex="0" :aria-label="`Available loose pieces in ${row.lot}`">
					<table v-entry-table="{ fixed: false }" class="finishing-table">
						<thead>
							<tr>
								<th class="finishing-table__index">#</th>
								<th>Colour</th>
								<th v-if="canTransfer">Set Colour</th>
								<th v-if="row.is_set_item">{{ row.set_attr }}</th>
								<th>Bucket</th>
								<th v-for="size in row.primary_values" :key="size" class="erp-number">{{ size }}</th>
								<th class="erp-number">Total</th>
							</tr>
						</thead>
						<tbody v-for="(colour, index) in availableColours(row)" :key="colour">
							<tr v-for="(bucket, bucketIndex) in availableBuckets(row, colour)" :key="bucket.key">
								<template v-if="bucketIndex === 0">
									<td :rowspan="availableBuckets(row, colour).length" class="finishing-table__index">{{ index + 1 }}</td>
									<td :rowspan="availableBuckets(row, colour).length">{{ colour }}</td>
									<td v-if="canTransfer" :rowspan="availableBuckets(row, colour).length"><Select v-model="transfers[lotTransferKey(row)][colour].set_combination" :options="data.available.colours || []" placeholder="Select" :aria-label="`${row.source_fp} ${colour} set colour`" :disabled="busy" /></td>
									<td v-if="row.is_set_item" :rowspan="availableBuckets(row, colour).length">{{ row.old_lot_inward.data[colour].part || "—" }}</td>
								</template>
								<td><span class="old-lot__bucket" :class="`old-lot__bucket--${bucket.key}`">{{ bucket.label }}</span></td>
								<td v-for="size in row.primary_values" :key="size" class="erp-number">
									<template v-if="bucket.values[size]">
										<span class="old-lot__balance">{{ formatQuantity(bucket.values[size]) }}</span>
										<input v-if="canTransfer" v-model="transfers[lotTransferKey(row)][colour].sizes[size][bucket.field]" type="number" min="0" :max="bucket.values[size]" class="finishing-entry-input" :aria-label="`Transfer ${bucket.label} ${row.source_fp} ${colour} ${size}`" :disabled="busy" />
									</template>
									<span v-else>—</span>
								</td>
								<td class="erp-number finishing-table__row-total">
									<span class="old-lot__balance">{{ formatQuantity(bucket.total) }}</span>
									<span v-if="canTransfer">{{ formatQuantity(transferTotal(row, colour, bucket.field)) }}</span>
								</td>
							</tr>
						</tbody>
						<tfoot>
							<tr v-for="bucket in bucketTotals(row)" :key="bucket.key" class="finishing-table__total-row">
								<th :colspan="2 + (canTransfer ? 1 : 0) + (row.is_set_item ? 1 : 0)" scope="row">Total</th>
								<td><span class="old-lot__bucket" :class="`old-lot__bucket--${bucket.key}`">{{ bucket.label }}</span></td>
								<td v-for="size in row.primary_values" :key="size" class="erp-number">
									<span class="old-lot__balance">{{ formatQuantity(bucket.totals.balance.sizes[size]) }}</span>
									<span v-if="canTransfer">{{ formatQuantity(bucket.totals.transfer.sizes[size]) }}</span>
								</td>
								<td class="erp-number finishing-table__row-total">
									<span class="old-lot__balance">{{ formatQuantity(bucket.totals.balance.total) }}</span>
									<span v-if="canTransfer">{{ formatQuantity(bucket.totals.transfer.total) }}</span>
								</td>
							</tr>
						</tfoot>
					</table>
				</div>
			</div>
		</section>
		<DocumentErrorDialog :message="transferError" title="Check the lot transfer" @dismiss="transferError = ''" />
	</div>
</template>

<script setup>
import DocumentLink from "../../../components/common/DocumentLink.vue"
import { vEntryTable } from "../../../components/common/childGrid/entryTable.js"
import Button from "primevue/button"
import Select from "primevue/select"
import { computed, ref, watch } from "vue"

import DocumentErrorDialog from "../../../components/documents/DocumentErrorDialog.vue"
import { lotTransferErrors, lotTransferKey, lotTransferPayload } from "../finishingEntries.js"
import { lotTransferTotals } from "../finishingEntryTotals.js"
import { formatQuantity } from "../finishingViews.js"

const props = defineProps({
	data: { type: Object, required: true },
	canTransfer: { type: Boolean, default: false },
	busy: { type: Boolean, default: false },
})
const emit = defineEmits(["fetch", "transfer"])
const transfers = ref({})
const transferError = ref("")
const transferMatrices = computed(() => [
	{ key: "received", title: "Received from Other Finishing Plans", counterpart: "Source FP / Lot", source: props.data.received },
	{ key: "given", title: "Given to Other Finishing Plans", counterpart: "Destination FP / Lot", source: props.data.given },
].filter((matrix) => matrix.source?.groups?.length).map((matrix) => ({ ...matrix, sizes: matrix.source.primary_values || [], groups: matrix.source.groups })))
const availableRows = computed(() => props.data.available?.data || [])

function buckets(group) {
	return [
		{ key: "lp", label: "Loose Piece", values: group.lp || {}, total: Number(group.lp_total || 0) },
		{ key: "lps", label: "Loose Piece Set", values: group.lps || {}, total: Number(group.lps_total || 0) },
	].filter((bucket) => bucket.total > 0)
}

function availableColours(row) {
	return Object.keys(row.old_lot_inward?.data || {}).filter((colour) => availableBuckets(row, colour).length)
}

function availableBuckets(row, colour) {
	const entry = row.old_lot_inward.data[colour]
	const values = (field) => Object.fromEntries(Object.entries(entry.values || {}).map(([size, value]) => [size, Number(value[field] || 0)]))
	return [
		{ key: "lp", label: "Loose Piece", field: "loose_piece", values: values("balance_loose_piece"), total: Number(entry.colour_total?.balance_loose_piece || 0) },
		{ key: "lps", label: "Loose Piece Set", field: "loose_piece_set", values: values("balance_loose_piece_set"), total: Number(entry.colour_total?.balance_loose_piece_set || 0) },
	].filter((bucket) => bucket.total > 0)
}

function bucketTotals(row) {
	return [
		{ key: "lp", label: "Loose Piece", field: "loose_piece", balanceField: "balance_loose_piece" },
		{ key: "lps", label: "Loose Piece Set", field: "loose_piece_set", balanceField: "balance_loose_piece_set" },
	].map((bucket) => ({ ...bucket, totals: lotTransferTotals(row, transfers.value[lotTransferKey(row)], bucket.field, bucket.balanceField) }))
		.filter((bucket) => bucket.totals.balance.total > 0)
}

function initialTransfers(rows) {
	return Object.fromEntries(rows.map((row) => [lotTransferKey(row), Object.fromEntries(Object.entries(row.old_lot_inward?.data || {}).map(([colour, entry]) => [
		colour,
		{ set_combination: entry.set_combination || "", sizes: Object.fromEntries(row.primary_values.map((size) => [size, { loose_piece: 0, loose_piece_set: 0 }])) },
	]))]))
}

function transferTotal(row, colour, field) {
	return Object.values(transfers.value[lotTransferKey(row)][colour].sizes).reduce((sum, cell) => sum + (Number(cell[field]) || 0), 0)
}

function submitTransfer() {
	const errors = lotTransferErrors(availableRows.value, transfers.value)
	if (errors.length) {
		transferError.value = errors[0]
		return
	}
	emit("transfer", lotTransferPayload(availableRows.value, transfers.value))
}

watch(availableRows, (rows) => { transfers.value = initialTransfers(rows) }, { immediate: true })
</script>

<style scoped>
.old-lot__toolbar { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: var(--erp-space-2); }
.old-lot__actions { display: flex; flex-wrap: wrap; gap: var(--erp-space-2); }
.old-lot__balance { display: block; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); }
.old-lot__sub { display: block; color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 500; }
.old-lot__transfer { display: block; color: var(--erp-text-secondary); }
.old-lot__lot { margin: 0; color: var(--erp-text); font-size: var(--erp-font-size-body); font-weight: 700; }
.old-lot__lot small { margin-left: 6px; color: var(--erp-text-muted); font-weight: 500; }
.old-lot__bucket { display: inline-block; padding: 1px 7px; border-radius: 6px; font-size: var(--erp-font-size-min); font-weight: 700; text-transform: uppercase; letter-spacing: 0.03em; }
.old-lot__bucket--lp { color: #92400e; background: #fef3c7; }
.old-lot__bucket--lps { color: #166534; background: #dcfce7; }
</style>
