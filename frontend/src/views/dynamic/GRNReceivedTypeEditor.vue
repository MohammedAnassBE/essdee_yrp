<!--
  GRNReceivedTypeEditor — the GRN received-type-SPLIT pivot (R3b).

  PrimeVue port of apps/yrp/yrp/public/js/WorkOrder/GoodsReceivedNoteEditor.vue
  (the Desk's received-type split editor, used for GRN against Work Order /
  rework). DocDetail.vue routes a Goods Received Note whose `against === "Work
  Order"` to THIS editor instead of the generic StockItemGridEditor pivot; every
  other stock voucher (and GRN-against-Purchase-Order) keeps the generic pivot.

  WHAT IT IS — split vs. the generic pivot
  ----------------------------------------
  The generic pivot (StockItemGridEditor) gives each logical item ONE row with
  one received_type. A GRN against a Work Order needs to SPLIT one pending
  receivable across MULTIPLE received types (e.g. Accepted / Rejected / Rework),
  each clamped to the remaining receivable qty. So here:

    rows    = received-type SPLITS of a logical item (parent item + dims-minus-
              received_type + non-primary attributes); the first split rowspans
              the item's identity / pending / allowed / balance cells.
    columns = the primary-attribute values (sizes) — same as the generic pivot.
    cells   = qty per (split, size), clamped to max_receivable_quantity minus the
              sum of the SAME size's qty across the item's OTHER splits.

  `received_type` is a STOCK DIMENSION carried on each entry.dimensions. Adding a
  split clones a template entry within the group and stamps a new received_type
  (qtys zeroed); removing a split splices it out. We NEVER add a new parent item
  here (mirrors the Desk's allowCreate:false) and we NEVER write Stock Ledger
  Entries — the server's ungroup_items_from_ui resolves/creates variants on save.

  CONTRACT — identical grouped `item_details` JSON as R3a
  -------------------------------------------------------
  loadData(grouped) / getItems() exchange the SAME grouped structure
  group_items_for_ui produces / ungroup_items_from_ui consumes
  (save_stock_items.py). A "split" is just one more entry (per received_type) for
  one logical item inside its group. We store the PARENT item + attributes +
  dimensions (incl. received_type) per entry; the server resolves variants.

  PUBLIC API (defineExpose) — same surface DocDetail drives on StockItemGridEditor
  --------------------------------------------------------------------------------
  - loadData(grouped) → rebuild internal `groups` from a saved grouped payload
                        (array or JSON string). Tolerant of partial entries.
  - getItems()        → the grouped JSON array (deep clone) for buildPayload.
  - hasItems()        → whether any group carries items.

  APIs (reused over HTTP via callMethod — same as the Desk component)
  -------------------------------------------------------------------
  - yrp.stock.api.get_stock_dimensions_for_ui()
        → [ { fieldname, label, options, mandatory } ] (for dimension labels)
  - yrp.yrp.doctype.goods_received_note.goods_received_note.get_rework_output_received_types()
        → { received_types: [...], default_received_type } (for the "+RT" buttons)
-->
<template>
	<div class="grn-rt-editor">
		<div v-if="!logicalRows.length" class="grid-empty-state">
			No pending receivables{{ editable ? " — open this GRN in Desk to (re)load source items." : "." }}
		</div>

		<div
			v-for="(row, rowIndex) in logicalRows"
			:key="row.key"
			class="grn-group"
		>
			<DataTable :value="row.splits" class="esd-table grn-dt" :rowHover="false" dataKey="key" :tableStyle="{ tableLayout: 'fixed', minWidth: '780px' }">
				<!-- S.No (rowspan-style: only shown on the first split) -->
				<Column header="#" :style="{ width: '44px' }">
					<template #body="{ index }">
						<span v-if="index === 0">{{ rowIndex + 1 }}</span>
					</template>
				</Column>

				<!-- Item identity + meta (only on the first split row) -->
				<Column header="Item" :style="{ minWidth: '190px' }">
					<template #body="{ index }">
						<template v-if="index === 0">
							<div class="grn-item-title esd-mono">{{ row.name }}</div>
							<div v-if="rowMeta(row)" class="grn-item-meta">{{ rowMeta(row) }}</div>
							<div v-if="row.defaultUom" class="grn-item-uom">{{ row.defaultUom }}</div>
						</template>
					</template>
				</Column>

				<Column v-if="actualDiaEnabled" header="Actual Dia" :style="{ width: '150px' }">
					<template #body="{ index }">
						<div v-if="index === 0" class="grn-dia-cell">
							<Select
								:modelValue="row.attributes?.Dia || null"
								:options="diaOptions"
								:disabled="!editable"
								filter
								fluid
								placeholder="Select Dia"
								@update:modelValue="onDiaChange(row, $event)"
							/>
							<Button
								v-if="editable && canRemoveDia(row)"
								icon="pi pi-trash"
								text
								rounded
								severity="danger"
								size="small"
								v-tooltip.top="'Remove this Actual Dia row'"
								@click="removeDia(row)"
							/>
						</div>
					</template>
				</Column>

				<!-- Received Type + remove control -->
				<Column header="Received Type" :style="{ width: '150px' }">
					<template #body="{ data: split }">
						<span class="grn-rt-name">{{ split.receivedType || "Received" }}</span>
						<Button
							v-if="editable && canRemoveSplit(row, split)"
							icon="pi pi-times"
							text
							rounded
							severity="danger"
							size="small"
							class="grn-rt-remove"
							v-tooltip.top="'Remove this Received Type row'"
							@click="removeSplit(row, split)"
						/>
					</template>
				</Column>

				<!-- Size (primary-attribute value) qty cells -->
				<Column
					v-for="col in row.columns"
					:key="'c-' + col.key"
					:header="col.label"
					:style="{ width: '92px' }"
				>
					<template #body="{ data: split }">
						<InputNumber
							v-if="editable"
							:modelValue="qty(split.entry, col.key)"
							@update:modelValue="onQtyInput(row, split, col.key, $event)"
							:min="0"
							:max="canReceiveExcess ? undefined : maxQty(row, split, col.key)"
							:minFractionDigits="0"
							:maxFractionDigits="3"
							class="cell-num"
							inputClass="cell-num-input"
							fluid
						/>
						<span v-else class="cell-ro">{{ formatQty(qty(split.entry, col.key)) }}</span>
					</template>
				</Column>

				<!-- Per-split total -->
				<Column header="Total" :style="{ width: '70px' }">
					<template #body="{ data: split }">
						<span class="cell-ro">{{ formatQty(splitTotal(split, row.columns)) }}</span>
					</template>
				</Column>

				<!-- Each received-type split becomes its own GRN child row. -->
				<Column header="Comments" :style="{ minWidth: '210px' }">
					<template #body="{ data: split }">
						<InputText
							v-if="editable"
							:modelValue="split.entry.comments"
							@update:modelValue="setGrnSplitComment(split, $event)"
							class="line-comment-input"
							placeholder="Add row comment"
							fluid
						/>
						<span v-else class="line-comment-read">{{ split.entry.comments || "—" }}</span>
					</template>
				</Column>

				<!-- Pending / Allowed / Bal. (only on the first split row) -->
				<Column header="Pending" :style="{ width: '74px' }">
					<template #body="{ index }">
						<span v-if="index === 0" class="cell-ro">{{ formatQty(rowPending(row)) }}</span>
					</template>
				</Column>
				<Column header="Allowed" :style="{ width: '74px' }">
					<template #body="{ index }">
						<span v-if="index === 0" class="cell-ro">{{ formatQty(rowAllowed(row)) }}</span>
					</template>
				</Column>
				<Column header="Bal." :style="{ width: '74px' }">
					<template #body="{ index }">
						<span
							v-if="index === 0"
							class="cell-ro"
							:class="{ 'txt-danger': rowBalance(row) < 0 }"
						>{{ formatQty(rowBalance(row)) }}</span>
					</template>
				</Column>

				<!-- "+ Received Type" add controls under the table -->
				<template #footer v-if="editable && (unusedRTs(row).length || unusedDias(row).length)">
					<div class="grn-rt-add-row">
						<template v-if="unusedRTs(row).length">
							<span class="grn-rt-add-label">Add Received Type:</span>
							<Button
								v-for="rt in unusedRTs(row)"
								:key="'add-' + rt"
								:label="rt"
								icon="pi pi-plus"
								size="small"
								severity="secondary"
								outlined
								class="grn-rt-add"
								@click="addSplit(row, rt)"
							/>
						</template>
						<template v-if="unusedDias(row).length">
							<span class="grn-rt-add-label grn-dia-add-label">Add Actual Dia:</span>
							<Select
								v-model="diaSelections[row.key]"
								:options="unusedDias(row)"
								filter
								class="grn-dia-select"
								placeholder="Select Dia"
							/>
							<Button
								label="Add Dia"
								icon="pi pi-plus"
								size="small"
								:disabled="!diaSelections[row.key]"
								@click="addDia(row, diaSelections[row.key])"
							/>
						</template>
					</div>
				</template>
			</DataTable>
		</div>
	</div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch, nextTick } from "vue"
import DataTable from "primevue/datatable"
import Column from "primevue/column"
import Button from "primevue/button"
import InputNumber from "primevue/inputnumber"
import InputText from "primevue/inputtext"
import Select from "primevue/select"
import Tooltip from "primevue/tooltip"
import { callMethod } from "@/api/client"
import {
	addGrnActualDia,
	addGrnReceivedType,
	buildGrnLogicalRows,
	compactGrnRouteSplits,
	grnSplitReferenceKey,
	normalizeGrnReceiptQuantity,
	removeGrnRow,
	removeGrnSplit,
	setGrnRowDia,
	setGrnSplitComment,
	setGrnSplitQuantity,
} from "@/engine/stock/grnRouteRows"

const vTooltip = Tooltip

const props = defineProps({
	// false → read-only render (e.g. embedded in a view context). DocDetail only
	// mounts this in edit/create, so default true.
	editable: { type: Boolean, default: true },
	workOrder: { type: String, default: "" },
	actualDiaDisabled: { type: Boolean, default: false },
	allowExcess: { type: Boolean, default: false },
})

// Q6: emit `change` on genuine user edits so DocDetail's dirty guard sees grid
// edits (this editor's state lives here, not in the parent `form`). Armed after
// loadData/mount so the programmatic seed never false-fires.
const emit = defineEmits(["change"])
const changeArmed = ref(false)

// ── grouped state (== save_stock_items.py shape; same as the Desk's `items`) ──
const groups = ref([])

watch(
	groups,
	() => { if (changeArmed.value) emit("change") },
	{ deep: true },
)

// ── dimension labels (for the row meta) ──
const dimensions = ref([])
// ── available received types for the "+RT" add buttons ──
const availableRTs = ref([])
const actualDiaEnabled = ref(false)
const canReceiveExcess = computed(() => props.allowExcess)
const diaOptions = ref([])
const diaSelections = reactive({})
let actualDiaRequest = 0
const defaultReceivedType = ref("")
const receivedTypesReady = ref(false)

onMounted(async () => {
	try {
		const dims = await callMethod("yrp.stock.api.get_stock_dimensions_for_ui")
		dimensions.value = Array.isArray(dims) ? dims : []
	} catch (_) {
		dimensions.value = []
	}
	try {
		const r = await callMethod(
			"yrp.yrp.doctype.goods_received_note.goods_received_note.get_rework_output_received_types",
		)
		availableRTs.value = (r && Array.isArray(r.received_types)) ? r.received_types : []
		defaultReceivedType.value = r?.default_received_type || ""
	} catch (_) {
		availableRTs.value = []
		defaultReceivedType.value = ""
	}
	receivedTypesReady.value = true
	compactLoadedSplits()
	await loadActualDiaContext()
	// Arm change-emit after initial state settles (a later external loadData re-arms).
	nextTick(() => { changeArmed.value = true })
})

watch(
	() => [props.workOrder, props.actualDiaDisabled],
	loadActualDiaContext,
)

async function loadActualDiaContext() {
	const request = ++actualDiaRequest
	actualDiaEnabled.value = false
	diaOptions.value = []
	if (!props.workOrder || props.actualDiaDisabled) return
	try {
		const result = await callMethod("essdee_yrp.fabric_grn.get_actual_dia_context", {
			work_order: props.workOrder,
		})
		if (request !== actualDiaRequest) return
		actualDiaEnabled.value = !!result?.enabled
		diaOptions.value = result?.dia_options || []
	} catch (_) {
		if (request !== actualDiaRequest) return
		actualDiaEnabled.value = false
	}
}

const dimensionLabels = computed(() => {
	const out = {}
	for (const dim of dimensions.value || []) out[dim.fieldname] = dim.label
	return out
})

// ════════════════ LOGICAL ROWS (mirror the Desk's logicalRows) ════════════════
// Collapse the grouped entries into logical rows keyed by parent item +
// dimensions-minus-received_type + non-primary attributes + size columns. Each
// distinct received_type for that key becomes one SPLIT row.
const logicalRows = computed(() => buildGrnLogicalRows(groups.value))

function dimensionLabel(fieldname) {
	if (dimensionLabels.value[fieldname]) return dimensionLabels.value[fieldname]
	return fieldname.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
}

function rowMeta(row) {
	const parts = []
	for (const fn of row.dimensionFields || []) {
		const v = row.dimensions[fn]
		if (v) parts.push(`${dimensionLabel(fn)}: ${v}`)
	}
	for (const fn of row.attributeFields || []) {
		const v = row.attributes[fn]
		if (v) parts.push(v)
	}
	const setColour = row.setCombination?.major_colour
	const setPart = row.setCombination?.major_part
	if (setColour || setPart) {
		parts.push(`Set: ${[setColour, setPart].filter(Boolean).join(" / ")}`)
	}
	return parts.join(" | ")
}

// ════════════════ QTY / CLAMP (mirror the Desk math) ════════════════
function valueDetail(entry, key) {
	if (!entry.values) entry.values = {}
	if (!entry.values[key]) entry.values[key] = { qty: 0 }
	return entry.values[key]
}

function toNumber(value) {
	const n = Number(value || 0)
	return Number.isFinite(n) ? n : 0
}

function qty(entry, key) {
	return toNumber(valueDetail(entry, key).qty)
}

// Pending / Allowed are stored per size-cell on the entries (any split carries
// them — they are properties of the receivable, not the split). Read the first
// non-empty across splits, exactly like the Desk.
function pendingQty(row, key) {
	for (const split of row.splits) {
		const p = valueDetail(split.entry, key).pending_quantity
		if (p !== undefined && p !== null && p !== "") return toNumber(p)
	}
	return 0
}

function allowedQty(row, key) {
	for (const split of row.splits) {
		const a = valueDetail(split.entry, key).max_receivable_quantity
		if (a !== undefined && a !== null && a !== "") return Math.max(toNumber(a), 0)
	}
	return Math.max(pendingQty(row, key), 0)
}

function otherSplitQty(row, currentSplit, key) {
	const reference = grnSplitReferenceKey(currentSplit, key)
	if (actualDiaEnabled.value && reference) {
		let total = 0
		for (const candidateRow of logicalRows.value) {
			for (const candidate of candidateRow.splits) {
				for (const column of candidateRow.columns) {
					if (
						candidateRow.key === row.key
						&& candidate.receivedType === currentSplit?.receivedType
						&& column.key === key
					) continue
					if (grnSplitReferenceKey(candidate, column.key) === reference) {
						total += qty(candidate.entry, column.key)
					}
				}
			}
		}
		return total
	}
	let total = 0
	for (const split of row.splits) {
		// PrimeVue passes a proxied body-row object, so object identity is not
		// stable here. Received Type is unique within a logical item row.
		if (split.receivedType === currentSplit?.receivedType) continue
		total += qty(split.entry, key)
	}
	return total
}

function rowReference(row) {
	for (const split of row.splits || []) {
		for (const column of row.columns || []) {
			const reference = grnSplitReferenceKey(split, column.key)
			if (reference) return reference
		}
	}
	return ""
}

function rowsForReference(row) {
	const reference = rowReference(row)
	if (!reference) return [row]
	return logicalRows.value.filter((candidate) => rowReference(candidate) === reference)
}

// Clamp = max_receivable_quantity for the size minus the qty of the SAME size in
// this item's OTHER splits.
function maxQty(row, split, key) {
	return Math.max(allowedQty(row, key) - otherSplitQty(row, split, key), 0)
}

function onQtyInput(row, split, key, value) {
	// Resolve the current computed row/split before applying the clamp. DataTable
	// can retain a stale/proxied slot object after another split changes.
	const currentRow = logicalRows.value.find((candidate) => candidate.key === row.key) || row
	const currentSplit = currentRow.splits.find(
		(candidate) => candidate.receivedType === split.receivedType,
	) || split
	const next = normalizeGrnReceiptQuantity(
		value,
		allowedQty(currentRow, key),
		otherSplitQty(currentRow, currentSplit, key),
		canReceiveExcess.value,
	)
	setGrnSplitQuantity(currentSplit, key, next)
}

function splitTotal(split, columns) {
	return columns.reduce((t, c) => t + qty(split.entry, c.key), 0)
}
function rowReceived(row) {
	return row.splits.reduce((t, s) => t + splitTotal(s, row.columns), 0)
}
function rowPending(row) {
	return row.columns.reduce((t, c) => t + pendingQty(row, c.key), 0)
}
function rowAllowed(row) {
	return row.columns.reduce((t, c) => t + allowedQty(row, c.key), 0)
}
function rowBalance(row) {
	row = logicalRows.value.find((candidate) => candidate.key === row?.key) || row
	if (actualDiaEnabled.value && rowReference(row)) {
		return rowAllowed(row) - rowsForReference(row).reduce(
			(total, candidate) => total + rowReceived(candidate),
			0,
		)
	}
	return rowAllowed(row) - rowReceived(row)
}

// ════════════════ ADD / REMOVE SPLIT (mirror addSplit/removeSplit) ════════════════
function unusedRTs(row) {
	if (!availableRTs.value || !availableRTs.value.length) return []
	const used = new Set(row.splits.map((s) => s.receivedType || ""))
	return availableRTs.value.filter((rt) => !used.has(rt))
}

function unusedDias(row) {
	if (!actualDiaEnabled.value) return []
	const used = new Set(
		rowsForReference(row).map((candidate) => candidate.attributes?.Dia).filter(Boolean),
	)
	return diaOptions.value.filter((dia) => !used.has(dia))
}

function onDiaChange(row, dia) {
	if (!dia || !actualDiaEnabled.value) return
	const duplicate = rowsForReference(row).some(
		(candidate) => candidate !== row && candidate.attributes?.Dia === dia,
	)
	if (duplicate) return
	setGrnRowDia(row, dia)
}

function addDia(row, dia) {
	if (!dia || !actualDiaEnabled.value || !row.splits?.length) return
	addGrnActualDia(groups.value, row, dia)
	diaSelections[row.key] = null
}

function canRemoveDia(row) {
	return rowsForReference(row).length > 1
		&& row.splits.every((split) => splitTotal(split, row.columns) === 0)
}

function removeDia(row) {
	if (!canRemoveDia(row)) return
	removeGrnRow(groups.value, row)
}

function canRemoveSplit(row, split) {
	// Keep at least one split per row; only allow removing an empty (zero-qty) one.
	if (!row.splits || row.splits.length <= 1) return false
	return splitTotal(split, row.columns) === 0
}

// Clone a template entry within the matching group, stamp the new received_type,
// zero the qtys (value_fields preserved so they round-trip).
function addSplit(row, rt) {
	addGrnReceivedType(groups.value, row, rt)
}

function removeSplit(row, split) {
	removeGrnSplit(groups.value, split)
}

function formatQty(value) {
	const n = toNumber(value)
	if (Number.isInteger(n)) return String(n)
	return n.toFixed(3).replace(/\.?0+$/, "")
}

// The defaults API pads each receivable with every configured Received Type.
// Keep the configured default plus any split that already carries a quantity;
// operators can add the remaining types from the table footer when needed.
function compactGroups(data) {
	return compactGrnRouteSplits(data, defaultReceivedType.value)
}

function compactLoadedSplits() {
	if (!receivedTypesReady.value || !(groups.value || []).length) return
	changeArmed.value = false
	groups.value = compactGroups(groups.value)
	nextTick(() => { changeArmed.value = true })
}

// ════════════════ PUBLIC API (same surface DocDetail drives) ════════════════
// Rebuild internal `groups` from a saved grouped payload (array or JSON string).
function loadData(grouped) {
	changeArmed.value = false // programmatic load — don't emit change
	let data = grouped
	if (typeof data === "string") {
		try {
			data = JSON.parse(data || "[]")
		} catch (_) {
			data = []
		}
	}
	if (!Array.isArray(data)) {
		groups.value = []
	} else {
		// Deep clone so edits don't mutate the caller's onload object.
		groups.value = receivedTypesReady.value
			? compactGroups(data)
			: JSON.parse(JSON.stringify(data))
	}
	nextTick(() => { changeArmed.value = true })
}

// Deep-cloned grouped JSON for buildPayload. Strips empty groups defensively
// (mirrors StockItemGridEditor.getItems so DocDetail's edit-mode "empty grid"
// safety stays meaningful). Zero-qty split entries are kept — the server's
// ungroup_items_from_ui skips zero-qty rows on save.
function getItems() {
	return JSON.parse(
		JSON.stringify(
			compactGroups(groups.value).filter((g) => (g.items || []).length > 0),
		),
	)
}

function hasItems() {
	for (const g of groups.value || []) {
		if ((g.items || []).length) return true
	}
	return false
}

defineExpose({ loadData, getItems, hasItems })
</script>

<style scoped>
.grn-rt-editor {
	display: flex;
	flex-direction: column;
	gap: 12px;
}

.grn-group {
	border: 1px solid var(--esd-line);
	border-radius: var(--radius-sm);
	overflow-x: auto;
	overflow-y: hidden;
}

.grn-dt {
	font-size: 13px;
}
:deep(.grn-dt .p-datatable-thead > tr > th) {
	background: var(--esd-slate-50);
	font-size: 11.5px;
	letter-spacing: 0.03em;
	text-transform: uppercase;
	color: var(--esd-muted);
	padding: 6px 8px;
	white-space: nowrap;
}
:deep(.grn-dt .p-datatable-tbody > tr > td) {
	padding: 5px 8px;
	vertical-align: middle;
}

.grn-item-title {
	font-weight: 500;
}
.grn-item-meta {
	font-size: 11.5px;
	color: var(--esd-muted);
	line-height: 1.35;
}
.grn-item-uom {
	font-size: 11px;
	color: var(--esd-muted-2);
}

.grn-rt-name {
	font-weight: 500;
}
.grn-rt-remove {
	margin-left: 4px;
}
.grn-dia-cell {
	display: flex;
	align-items: center;
	gap: 4px;
}

.cell-num {
	width: 100%;
}
:deep(.cell-num-input) {
	/* fill the cell — PrimeVue's fluid sets the inner input to width:1% which
	   collapses to ~26px on our block-display host; force full width. */
	width: 100%;
	text-align: right;
}
.cell-ro {
	display: block;
	text-align: right;
	color: var(--esd-ink-2);
}
.line-comment-input {
	width: 100%;
}
.line-comment-read {
	display: block;
	white-space: pre-wrap;
	overflow-wrap: anywhere;
	color: var(--esd-ink-2);
}
.txt-danger {
	color: var(--esd-danger);
}

.grn-rt-add-row {
	display: flex;
	align-items: center;
	flex-wrap: wrap;
	gap: 6px;
	padding: 4px 2px;
}
.grn-rt-add-label {
	font-size: 11.5px;
	letter-spacing: 0.03em;
	text-transform: uppercase;
	color: var(--esd-muted);
	font-weight: 600;
	margin-right: 4px;
}
.grn-dia-add-label {
	margin-left: 12px;
}
.grn-dia-select {
	min-width: 150px;
}

.grid-empty-state {
	padding: 22px;
	border: 1px dashed var(--esd-line);
	border-radius: var(--radius-sm);
	background: var(--esd-card);
	text-align: center;
	color: var(--esd-muted);
	font-size: 13px;
}
</style>
