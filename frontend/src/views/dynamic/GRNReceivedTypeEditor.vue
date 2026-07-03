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
			<DataTable :value="row.splits" class="esd-table grn-dt" :rowHover="false" dataKey="key" :tableStyle="{ tableLayout: 'fixed', minWidth: '100%' }">
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

				<!-- Received Type + remove control -->
				<Column header="Received Type" :style="{ minWidth: '130px' }">
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
							:max="maxQty(row, split, col.key)"
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
				<template #footer v-if="editable && unusedRTs(row).length">
					<div class="grn-rt-add-row">
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
					</div>
				</template>
			</DataTable>
		</div>
	</div>
</template>

<script setup>
import { ref, computed, onMounted, watch, nextTick } from "vue"
import DataTable from "primevue/datatable"
import Column from "primevue/column"
import Button from "primevue/button"
import InputNumber from "primevue/inputnumber"
import Tooltip from "primevue/tooltip"
import { callMethod } from "@/api/client"

const vTooltip = Tooltip

const props = defineProps({
	// false → read-only render (e.g. embedded in a view context). DocDetail only
	// mounts this in edit/create, so default true.
	editable: { type: Boolean, default: true },
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
	} catch (_) {
		availableRTs.value = []
	}
	// Arm change-emit after initial state settles (a later external loadData re-arms).
	nextTick(() => { changeArmed.value = true })
})

const dimensionLabels = computed(() => {
	const out = {}
	for (const dim of dimensions.value || []) out[dim.fieldname] = dim.label
	return out
})

// ════════════════ LOGICAL ROWS (mirror the Desk's logicalRows) ════════════════
// Collapse the grouped entries into logical rows keyed by parent item +
// dimensions-minus-received_type + non-primary attributes + size columns. Each
// distinct received_type for that key becomes one SPLIT row.
const logicalRows = computed(() => {
	const rows = []
	const byKey = new Map()
	for (const group of groups.value || []) {
		for (const entry of group.items || []) {
			const dimsNoType = stripReceivedType(entry.dimensions || {})
			const attributes = entry.attributes || {}
			const columns = getColumns(group, entry)
			const key = stableKey({
				name: entry.name,
				dimensions: dimsNoType,
				attributes,
				columns: columns.map((c) => c.key),
			})
			if (!byKey.has(key)) {
				const row = {
					key,
					name: entry.name,
					dimensions: dimsNoType,
					dimensionFields: Object.keys(dimsNoType).filter((fn) => dimsNoType[fn]),
					attributes,
					attributeFields: Object.keys(attributes).filter((fn) => attributes[fn]),
					columns,
					defaultUom: entry.default_uom || "",
					splits: [],
				}
				byKey.set(key, row)
				rows.push(row)
			}
			byKey.get(key).splits.push({
				key: `${key}::${receivedType(entry)}`,
				receivedType: receivedType(entry),
				entry,
			})
		}
	}
	for (const row of rows) {
		row.splits.sort((a, b) => (a.receivedType || "").localeCompare(b.receivedType || ""))
	}
	return rows
})

function stripReceivedType(dimsIn) {
	const out = {}
	for (const [fn, v] of Object.entries(dimsIn || {})) {
		if (fn !== "received_type") out[fn] = v
	}
	return out
}

function receivedType(entry) {
	return (entry.dimensions || {}).received_type || ""
}

function getColumns(group, entry) {
	const values = entry.values || {}
	const primaryValues = group.primary_attribute_values || []
	if (primaryValues.length && !Object.prototype.hasOwnProperty.call(values, "default")) {
		return primaryValues.map((v) => ({ key: v, label: v }))
	}
	return [{ key: "default", label: "Qty" }]
}

function stableKey(value) {
	return JSON.stringify(sortObject(value))
}
function sortObject(value) {
	if (Array.isArray(value)) return value.map((i) => sortObject(i))
	if (!value || typeof value !== "object") return value
	const out = {}
	for (const k of Object.keys(value).sort()) out[k] = sortObject(value[k])
	return out
}

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
	let total = 0
	for (const split of row.splits) {
		if (split === currentSplit) continue
		total += qty(split.entry, key)
	}
	return total
}

// Clamp = max_receivable_quantity for the size minus the qty of the SAME size in
// this item's OTHER splits.
function maxQty(row, split, key) {
	return Math.max(allowedQty(row, key) - otherSplitQty(row, split, key), 0)
}

function onQtyInput(row, split, key, value) {
	const detail = valueDetail(split.entry, key)
	let next = toNumber(value)
	if (next < 0) next = 0
	const maxValue = maxQty(row, split, key)
	if (maxValue !== null && next > maxValue) next = maxValue
	detail.qty = next
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
	return rowAllowed(row) - rowReceived(row)
}

// ════════════════ ADD / REMOVE SPLIT (mirror addSplit/removeSplit) ════════════════
function unusedRTs(row) {
	if (!availableRTs.value || !availableRTs.value.length) return []
	const used = new Set(row.splits.map((s) => s.receivedType || ""))
	return availableRTs.value.filter((rt) => !used.has(rt))
}

function canRemoveSplit(row, split) {
	// Keep at least one split per row; only allow removing an empty (zero-qty) one.
	if (!row.splits || row.splits.length <= 1) return false
	return splitTotal(split, row.columns) === 0
}

// Clone a template entry within the matching group, stamp the new received_type,
// zero the qtys (value_fields preserved so they round-trip).
function addSplit(row, rt) {
	for (const group of groups.value || []) {
		for (const entry of group.items || []) {
			const stripped = stripReceivedType(entry.dimensions || {})
			const k = stableKey({
				name: entry.name,
				dimensions: stripped,
				attributes: entry.attributes || {},
				columns: getColumns(group, entry).map((c) => c.key),
			})
			if (k !== row.key) continue
			const clone = JSON.parse(JSON.stringify(entry))
			clone.dimensions = { ...stripped, received_type: rt }
			clone.values = {}
			for (const col of getColumns(group, entry)) {
				const src = (entry.values || {})[col.key] || {}
				clone.values[col.key] = { ...src, qty: 0 }
			}
			group.items.push(clone)
			return
		}
	}
}

function removeSplit(row, split) {
	for (const group of groups.value || []) {
		const idx = (group.items || []).indexOf(split.entry)
		if (idx !== -1) {
			group.items.splice(idx, 1)
			return
		}
	}
}

function formatQty(value) {
	const n = toNumber(value)
	if (Number.isInteger(n)) return String(n)
	return n.toFixed(3).replace(/\.?0+$/, "")
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
		groups.value = JSON.parse(JSON.stringify(data))
	}
	nextTick(() => { changeArmed.value = true })
}

// Deep-cloned grouped JSON for buildPayload. Strips empty groups defensively
// (mirrors StockItemGridEditor.getItems so DocDetail's edit-mode "empty grid"
// safety stays meaningful). Zero-qty split entries are kept — the server's
// ungroup_items_from_ui skips zero-qty rows on save.
function getItems() {
	return JSON.parse(
		JSON.stringify((groups.value || []).filter((g) => (g.items || []).length > 0)),
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
	overflow: hidden;
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
