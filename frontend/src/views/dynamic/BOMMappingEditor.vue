<!--
  BOMMappingEditor — the "Item BOM based on attribute mapping" editor (R1b).

  PrimeVue port of apps/yrp/yrp/public/js/ItemBOM/EditBOMAttributeMapping.vue +
  the load/validate round-trip in item_bom_attribute_mapping.js. Drives the
  standalone (non-submittable) Item BOM Attribute Mapping doctype, which the IPD
  engine reads in "Mode B" to resolve per-variant BOM quantities.

  What this surface does
  ----------------------
  An Item BOM Attribute Mapping says: "for this Item, when producing a variant
  with item-side attribute values X, the BOM Item is consumed with bom-side
  attribute values Y at quantity Q." The editor renders the full cross-product
  of the ITEM attributes' values (one row per combination) and lets the user pick
  the matching BOM-side attribute value(s) + a quantity for each combination, or
  exclude combinations that don't apply.

  same_attribute collapsing (RISK FLAG 1)
  ----------------------------------------
  An attribute flagged `same_attribute` on BOTH the item_attributes AND
  bom_item_attributes child tables is a "passthrough": the BOM variant simply
  inherits that attribute's value from the produced variant (e.g. Colour stays
  Colour). The Desk editor's get_attributes() drops such attributes from BOTH the
  item cross-product AND the BOM columns, and get_final_output() never writes them
  into `values`. The engine (_lookup_mode_b / _get_same_mapping_attributes,
  ipd_engine.py:626-673) mirrors this exactly: it excludes same_attrs when
  matching the item side, never reads them from the bom-side `values` rows, and
  re-stamps them onto the resolved bom_attrs from the demanded variant itself.

  => CONSISTENCY CONTRACT: this editor must (a) compute sameAttrs as the
  intersection of item-side and bom-side same_attribute flags, (b) exclude them
  from both the grid's item columns and bom columns, (c) NEVER emit same_attr rows
  into `values`, and (d) preserve the item_attributes / bom_item_attributes child
  rows (with their same_attribute flags) untouched on save — the engine reads them
  to know which attributes are passthrough. Break any of these and Mode B BOM math
  silently mismatches.

  values shape written on save (mirrors get_final_output → frm.doc.values)
  ------------------------------------------------------------------------
  For every INCLUDED grid row (combination), and only if every required cell is
  filled and qty > 0, we emit:
    - one {index, type:'item', attribute, attribute_value, quantity} per item attr
    - one {index, type:'bom',  attribute, attribute_value, quantity} per bom attr
  `index` is the row's position in the generated cross-product (stable per the
  item-value ordering returned by get_attribute_values). This is exactly the shape
  _lookup_mode_b groups by `index` and reads (item-side for matching, bom-side for
  the resolved attrs, first non-zero quantity for qty_of_bom_item).

  APIs (reused over HTTP; we do NOT import the Desk bundle / cur_frm / make_control)
  ---------------------------------------------------------------------------------
  - yrp.yrp.doctype.item.item.get_attribute_values(item, attributes) → {attr:[vals]}
    Used twice: (item, itemAttrs) to build the cross-product, and
    (bom_item, bomAttrs) for the BOM-side dropdown options.
-->
<template>
	<div class="bom-mapping-editor">
		<!-- Breadcrumb -->
		<nav class="crumbs">
			<a @click="goHome">Home</a>
			<span class="sep">/</span>
			<a v-if="ipdName" @click="goIpd">{{ ipdLabel }}</a>
			<a v-else @click="goMappingList">Item BOM Attribute Mapping</a>
			<span class="sep">/</span>
			<span class="crumb-cur esd-mono">{{ id }}</span>
		</nav>

		<!-- Header (Q2: produced item is the hero; the mapping code is a chip). -->
		<div class="detail-head">
			<div class="id-block">
				<div class="doc-hero">
					Item BOM Mapping<span v-if="itemLabel"> · {{ itemLabel }}</span>
				</div>
				<div class="doc-sub">Item BOM based on attribute mapping</div>
				<div class="doc-id esd-mono">{{ id }}</div>
			</div>
			<div class="head-actions">
				<Button
					label="Save"
					icon="pi pi-check"
					size="small"
					:loading="saving"
					:disabled="loading || !!loadError"
					@click="onSave"
				/>
				<a
					v-if="isAdmin || hasRole('System Manager')"
					class="desk-link"
					:href="deskUrl"
					target="_blank"
					rel="noopener"
				>
					<i class="pi pi-external-link" /> Open in Desk
				</a>
			</div>
		</div>

		<!-- Loading / error -->
		<div v-if="loading" class="state-block">
			<i class="pi pi-spin pi-spinner" style="font-size: 1.5rem" />
			<span>Loading…</span>
		</div>

		<Message v-else-if="loadError" severity="error" :closable="false">{{ loadError }}</Message>

		<template v-else>
			<!-- ── Context (read-only Item / BOM Item) ── -->
			<section class="panel">
				<div class="panel-head"><h3>Mapping</h3></div>
				<div class="ctx-grid">
					<div class="ctx-fld">
						<label>Item</label>
						<a class="ctx-val esd-mono" @click="navItem(item)">{{ item || "—" }}</a>
						<small class="ctx-hint">Produced item (drives the item-side cross-product).</small>
					</div>
					<div class="ctx-fld">
						<label>BOM Item</label>
						<a class="ctx-val esd-mono" @click="navItem(bomItem)">{{ bomItem || "—" }}</a>
						<small class="ctx-hint">Consumed item (its attribute values fill the BOM columns).</small>
					</div>
				</div>
				<div v-if="sameAttrs.length" class="same-note">
					<i class="pi pi-link" />
					<span>
						Passthrough attribute<span v-if="sameAttrs.length > 1">s</span>
						(<strong>{{ sameAttrs.join(", ") }}</strong>): the BOM variant inherits
						{{ sameAttrs.length > 1 ? "these values" : "this value" }} from the produced
						variant, so {{ sameAttrs.length > 1 ? "they are" : "it is" }} not shown as a
						column and not stored per-row.
					</span>
				</div>
			</section>

			<!-- ── Attribute selectors (mirror the Desk item_attributes /
			     bom_item_attributes grids), side by side: Item Attributes on the
			     left, BOM Item Attributes on the right. Editing either rebuilds
			     the cross-product grid below. ── -->
			<div class="attr-panels-row">
			<section class="panel attr-panel">
				<div class="panel-head">
					<h3>Item Attributes</h3>
					<span class="panel-meta">produced item — drives the cross-product rows</span>
				</div>
				<div class="attr-body">
					<div v-if="!itemAttrRows.length" class="attr-empty">
						No item-side attributes selected.
					</div>
					<ul v-else class="attr-list">
						<li v-for="(r, i) in itemAttrRows" :key="'ia-' + r.attribute" class="attr-row">
							<span class="attr-name">{{ r.attribute }}</span>
							<label class="same-toggle" v-tooltip.top="sameTip">
								<Checkbox
									:modelValue="!!r.same_attribute"
									:binary="true"
									@update:modelValue="setItemSame(i, $event)"
								/>
								<span>same</span>
							</label>
							<Button
								icon="pi pi-times"
								size="small"
								text
								rounded
								severity="danger"
								v-tooltip.left="'Remove attribute'"
								@click="removeItemAttr(i)"
							/>
						</li>
					</ul>
					<div class="attr-add">
						<Select
							v-model="addItemAttrSel"
							:options="availableItemAttrs"
							:disabled="!availableItemAttrs.length"
							:placeholder="availableItemAttrs.length ? 'Add an item attribute…' : 'All item attributes added'"
							showClear
							class="attr-add-select"
						/>
						<Button
							label="Add"
							icon="pi pi-plus"
							size="small"
							severity="secondary"
							outlined
							:disabled="!addItemAttrSel"
							@click="addItemAttr"
						/>
					</div>
				</div>
			</section>

			<section class="panel attr-panel">
				<div class="panel-head">
					<h3>BOM Item Attributes</h3>
					<span class="panel-meta">consumed item — its values fill the BOM columns</span>
				</div>
				<div class="attr-body">
					<div v-if="!bomAttrRows.length" class="attr-empty">
						No BOM-side attributes selected.
					</div>
					<ul v-else class="attr-list">
						<li v-for="(r, i) in bomAttrRows" :key="'ba-' + r.attribute" class="attr-row">
							<span class="attr-name">{{ r.attribute }}</span>
							<label class="same-toggle" v-tooltip.top="sameTip">
								<Checkbox
									:modelValue="!!r.same_attribute"
									:binary="true"
									@update:modelValue="setBomSame(i, $event)"
								/>
								<span>same</span>
							</label>
							<Button
								icon="pi pi-times"
								size="small"
								text
								rounded
								severity="danger"
								v-tooltip.left="'Remove attribute'"
								@click="removeBomAttr(i)"
							/>
						</li>
					</ul>
					<div class="attr-add">
						<Select
							v-model="addBomAttrSel"
							:options="availableBomAttrs"
							:disabled="!availableBomAttrs.length"
							:placeholder="availableBomAttrs.length ? 'Add a BOM item attribute…' : 'All BOM attributes added'"
							showClear
							class="attr-add-select"
						/>
						<Button
							label="Add"
							icon="pi pi-plus"
							size="small"
							severity="secondary"
							outlined
							:disabled="!addBomAttrSel"
							@click="addBomAttr"
						/>
					</div>
				</div>
			</section>
			</div>

			<!-- ── Empty hint (no attributes yet) ── -->
			<section v-if="!attributes.length" class="panel empty-config">
				<div class="empty-config-body">
					<i class="pi pi-table empty-icon" />
					<div class="empty-text">
						<h3>No attribute columns yet</h3>
						<p>
							Add at least one <strong>item-side</strong> and one
							<strong>BOM-side</strong> attribute above to build the cross-product
							grid — or auto-fill from the owning IPD (item side = the IPD's
							primary attribute, BOM side = every attribute on
							<strong>{{ bomItem || "the BOM item" }}</strong>).
						</p>
					</div>
				</div>
				<div class="empty-config-actions">
					<Button
						label="Configure columns from IPD"
						icon="pi pi-sparkles"
						size="small"
						:loading="configuring"
						@click="configureColumns"
					/>
					<a v-if="item" class="inline-link" @click="navItem(item)">Open produced Item</a>
					<span v-if="item && bomItem" class="dot-sep">·</span>
					<a v-if="bomItem" class="inline-link" @click="navItem(bomItem)">Open BOM Item</a>
				</div>
			</section>

			<template v-else>
				<!-- Grid toolbar: combination count + Enable/Disable all, right
				     above the grid (mirrors the Desk EditBOMAttributeMapping
				     component, whose Disable/Enable buttons sit with the table —
				     the page-header pair scrolls out of view on a long grid). -->
				<div class="grid-toolbar">
					<div class="grid-meta">
						<Tag
							:value="`${includedCount} of ${data.length} included`"
							severity="primary"
							rounded
						/>
						<span v-if="bomAttrs.length === 0" class="grid-warn">
							This mapping has no BOM-side attribute columns — nothing to map.
						</span>
					</div>
					<div class="grid-toolbar-actions">
						<Button
							label="Enable all"
							icon="pi pi-check-circle"
							size="small"
							:disabled="!data.length"
							v-tooltip.top="'Include every combination'"
							@click="enableRows"
						/>
						<Button
							label="Disable incomplete"
							icon="pi pi-ban"
							size="small"
							severity="secondary"
							outlined
							:disabled="!data.length"
							v-tooltip.top="'Exclude included rows that have a blank BOM value'"
							@click="disableRows"
						/>
					</div>
				</div>

				<!-- ── Cross-product grid ── -->
				<section class="panel grid-panel">
					<DataTable :value="data" class="esd-table bom-dt" :rowHover="false" dataKey="__row_id">
						<!-- S.No -->
						<Column header="#" :style="{ width: '48px' }">
							<template #body="{ index }">{{ index + 1 }}</template>
						</Column>

						<!-- include / exclude toggle -->
						<Column header="" :style="{ width: '56px' }">
							<template #body="{ data: row, index }">
								<Button
									v-if="row.included"
									icon="pi pi-times-circle"
									text
									rounded
									severity="danger"
									size="small"
									v-tooltip.right="'Exclude this combination'"
									@click="toggleRow(index, false)"
								/>
								<Button
									v-else
									icon="pi pi-plus-circle"
									text
									rounded
									severity="success"
									size="small"
									v-tooltip.right="'Include this combination'"
									@click="toggleRow(index, true)"
								/>
							</template>
						</Column>

						<!-- item attribute columns (read-only chips) -->
						<Column v-for="attr in itemAttrs" :key="'i-' + attr" :header="attr">
							<template #body="{ data: row }">
								<Tag :value="row[itemKey(attr)] || '—'" severity="secondary" rounded class="item-chip" />
							</template>
						</Column>

						<!-- bom attribute columns (editable Select) -->
						<Column v-for="attr in bomAttrs" :key="'b-' + attr">
							<template #header>
								<div class="col-head">
									<span>{{ attr }}</span>
									<div class="col-fill">
										<Select
											v-model="fillBom[attr]"
											:options="bomAttrValues[attr] || []"
											showClear
											placeholder="—"
											class="fill-select"
										/>
										<Button
											label="Fill"
											size="small"
											severity="secondary"
											text
											v-tooltip.top="'Broadcast this value down the column (included rows)'"
											@click="fillColumn(attr)"
										/>
									</div>
								</div>
							</template>
							<template #body="{ data: row }">
								<Select
									v-model="row[bomKey(attr)]"
									:options="bomAttrValues[attr] || []"
									:disabled="!row.included"
									showClear
									placeholder="—"
									class="cell-select"
									:class="{ 'cell-missing': row.included && !row[bomKey(attr)] }"
									fluid
								/>
							</template>
						</Column>

						<!-- quantity column -->
						<Column v-if="bomAttrs.length > 0">
							<template #header>
								<div class="col-head">
									<span>Quantity</span>
									<div class="col-fill">
										<InputNumber
											v-model="fillQty"
											:minFractionDigits="0"
											:maxFractionDigits="6"
											placeholder="0"
											class="fill-num"
										/>
										<Button
											label="Fill"
											size="small"
											severity="secondary"
											text
											v-tooltip.top="'Broadcast this quantity down the column (included rows)'"
											@click="fillQuantity"
										/>
									</div>
								</div>
							</template>
							<template #body="{ data: row }">
								<InputNumber
									v-model="row.__qty"
									:disabled="!row.included"
									:minFractionDigits="0"
									:maxFractionDigits="6"
									class="cell-num"
									:class="{ 'cell-missing': row.included && !row.__qty }"
									fluid
								/>
							</template>
						</Column>

						<template #empty>
							<div class="esd-empty">
							<i class="pi pi-table" />
							<p class="esd-empty__text">No combinations.</p>
						</div>
						</template>
					</DataTable>
				</section>
			</template>
		</template>
	</div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted, onBeforeUnmount, nextTick } from "vue"
import { useRouter, onBeforeRouteLeave } from "vue-router"
import DataTable from "primevue/datatable"
import Column from "primevue/column"
import Button from "primevue/button"
import Tag from "primevue/tag"
import Message from "primevue/message"
import Select from "primevue/select"
import InputNumber from "primevue/inputnumber"
import Checkbox from "primevue/checkbox"
import Tooltip from "primevue/tooltip"
import { callMethod, getDoc } from "@/api/client"
import { useDoc } from "@/composables/useDoc"
import { useAppToast } from "@/composables/useToast"
import { useAppConfirm } from "@/composables/useConfirm"
import { usePermissions } from "@/composables/usePermissions"

const vTooltip = Tooltip

const props = defineProps({
	id: { type: String, required: true },
})

const router = useRouter()
const toast = useAppToast()
const confirm = useAppConfirm()
const { isAdmin, hasRole } = usePermissions()

const DOCTYPE = "Item BOM Attribute Mapping"
const docState = useDoc(DOCTYPE)

// ── reactive model ──
const item = ref("")
const bomItem = ref("")
// item_attributes / bom_item_attributes child rows as loaded — preserved verbatim
// on save (the engine reads their same_attribute flags). [{attribute, same_attribute}]
const itemAttrRows = ref([])
const bomAttrRows = ref([])
// sameAttrs: attributes flagged same_attribute on BOTH sides (passthrough) — the
// intersection ipd_engine._get_same_mapping_attributes computes. Excluded from the
// grid columns and never written into `values`.
const sameAttrs = ref([])
// Grid columns (same_attribute attrs already stripped).
const itemAttrs = ref([])   // item-side columns (read-only chips)
const bomAttrs = ref([])    // bom-side columns (editable)
// editor `attributes` list (mirrors get_attributes output): for reference/debug.
const attributes = ref([])  // [{type:'item'|'bom', attribute, attribute_values?}]
const itemAttrValues = reactive({}) // {attr: [vals]} — builds the cross-product
const bomAttrValues = reactive({})  // {attr: [vals]} — bom dropdown options
const data = ref([])        // generated cross-product rows
const ipdName = ref(null)   // owning IPD (for the breadcrumb), best-effort
// saved `values` from the last load — re-reconciled whenever the attribute
// selection changes so already-saved combinations survive a rebuild.
const savedValues = ref([])

// Q6: unsaved-changes guard — a deep watch flags the editable model dirty once
// armed (after load + grid rebuild settle). resetDirty brackets load(); persist
// re-loads (which re-arms clean).
const isDirty = ref(false)
const dirtyArmed = ref(false)
watch(
	[item, bomItem, data, itemAttrs, bomAttrs],
	() => { if (dirtyArmed.value) isDirty.value = true },
	{ deep: true },
)
async function armDirty() {
	await nextTick()
	dirtyArmed.value = true
}
function beforeUnloadGuard(e) {
	if (isDirty.value) { e.preventDefault(); e.returnValue = "" }
}
// Q2/Q3: human labels. The produced item's name IS human (Item is autonamed from
// name1), so itemLabel is just item.value. The owning IPD is hash-autonamed with
// no title_field, so its breadcrumb label is the IPD's `item` (fetched in
// fetchOwningIpd), falling back to the IPD code until it resolves.
const ipdItem = ref("")
const ipdLabel = computed(() => (ipdName.value ? (ipdItem.value || ipdName.value) : ""))
const itemLabel = computed(() => item.value || "")

// ── attribute selectors (mirror the Desk item_attributes / bom_item_attributes
//    grids). The full attribute pool per side comes from get_attributes(item);
//    the Add picker offers the pool minus the already-selected rows. ──
const itemAttrPool = ref([]) // all attributes on the produced item
const bomAttrPool = ref([])  // all attributes on the bom item
const addItemAttrSel = ref(null)
const addBomAttrSel = ref(null)
const sameTip =
	"Passthrough: when the SAME attribute is flagged on both sides, the BOM variant inherits its value from the produced variant (no column, not stored per-row)."
// rebuild sequence guard — a later rebuild invalidates an in-flight earlier one.
let rebuildSeq = 0

const availableItemAttrs = computed(() => {
	const taken = new Set(itemAttrRows.value.map((r) => r.attribute))
	return itemAttrPool.value.filter((a) => !taken.has(a))
})
const availableBomAttrs = computed(() => {
	const taken = new Set(bomAttrRows.value.map((r) => r.attribute))
	return bomAttrPool.value.filter((a) => !taken.has(a))
})

// per-column Fill buffers
const fillBom = reactive({})
const fillQty = ref(null)

const loading = ref(false)
const loadError = ref(null)
const configuring = ref(false)
const saving = computed(() => docState.saving.value)

const deskUrl = computed(
	() => `/app/item-bom-attribute-mapping/${encodeURIComponent(props.id)}`,
)

const includedCount = computed(() => data.value.filter((r) => r.included).length)

// Column key helpers (mirror get_attribute_name: type_attribute), namespaced to
// avoid colliding with the row's own bookkeeping keys.
function itemKey(attr) {
	return "item__" + attr
}
function bomKey(attr) {
	return "bom__" + attr
}

// ════════════════ LOAD ════════════════
async function load() {
	// Creating a new mapping is a master-data task the generic /web form doesn't
	// model, and our explicit route also captures `/item-bom-attribute-mapping/new`
	// — send that to the Desk new-form rather than crashing on getDoc("…", "new").
	// (Mirrors IPDConfigView's `new` handling.)
	if (props.id === "new") {
		// Should never arrive here — IPDConfigView's openMapping pre-creates
		// the mapping (so it has the IPD + bom_item context) and routes to
		// the resulting name. Surface a clear error rather than the old
		// silent Desk redirect, which broke the strict no-Desk rule.
		loadError.value =
			"Open this editor from an IPD's BOM row — it can't be created in isolation."
		return
	}
	loading.value = true
	loadError.value = null
	dirtyArmed.value = false
	isDirty.value = false
	try {
		const doc = await getDoc(DOCTYPE, props.id)
		item.value = doc.item || ""
		bomItem.value = doc.bom_item || ""
		itemAttrRows.value = (doc.item_attributes || []).map((r) => ({
			attribute: r.attribute,
			same_attribute: r.same_attribute ? 1 : 0,
		}))
		bomAttrRows.value = (doc.bom_item_attributes || []).map((r) => ({
			attribute: r.attribute,
			same_attribute: r.same_attribute ? 1 : 0,
		}))
		savedValues.value = doc.values || []

		// The pickers need every attribute the produced / bom item carries.
		await loadAttrPools()
		await rebuildGrid()

		// Best-effort: find an IPD that links this mapping (for the breadcrumb).
		fetchOwningIpd()
	} catch (e) {
		loadError.value = e.message || "Failed to load"
	} finally {
		loading.value = false
	}
	// Q6: arm dirty tracking after load + grid rebuild settle.
	armDirty()
}

// Full attribute pool per side (mirror the Desk set_query → get_item_attributes
// filtered by item). Feeds the Add pickers.
async function loadAttrPools() {
	try {
		const [ip, bp] = await Promise.all([
			item.value
				? callMethod("yrp.yrp.doctype.item.item.get_attributes", { item: item.value })
				: Promise.resolve([]),
			bomItem.value
				? callMethod("yrp.yrp.doctype.item.item.get_attributes", { item: bomItem.value })
				: Promise.resolve([]),
		])
		itemAttrPool.value = ip || []
		bomAttrPool.value = bp || []
	} catch (e) {
		toast.warn("Attribute list", e.message)
	}
}

// Recompute the derived grid columns from the editable itemAttrRows / bomAttrRows.
// sameAttrs = item-side same ∩ bom-side same (passthrough — mirrors
// _get_same_mapping_attributes); those are dropped from BOTH column lists.
function recomputeColumns() {
	const itemSame = new Set(
		itemAttrRows.value.filter((r) => r.same_attribute).map((r) => r.attribute),
	)
	sameAttrs.value = bomAttrRows.value
		.filter((r) => r.same_attribute && itemSame.has(r.attribute))
		.map((r) => r.attribute)
	const sameSet = new Set(sameAttrs.value)
	itemAttrs.value = itemAttrRows.value.map((r) => r.attribute).filter((a) => !sameSet.has(a))
	bomAttrs.value = bomAttrRows.value.map((r) => r.attribute).filter((a) => !sameSet.has(a))
}

function buildAttributesList() {
	const attrList = []
	for (const attr of bomAttrs.value) attrList.push({ type: "bom", attribute: attr })
	for (const attr of itemAttrs.value) {
		attrList.push({ type: "item", attribute: attr, attribute_values: itemAttrValues[attr] || [] })
	}
	attributes.value = attrList
}

// Recompute columns → refetch values → rebuild grid → reconcile saved values.
// Called on load AND whenever the attribute selection changes. A sequence guard
// drops a stale in-flight rebuild if the user edits again before it resolves —
// the same `seq` is threaded into the value loaders so a superseded fetch neither
// clears nor writes the shared value maps (which feed the live BOM dropdowns).
// `notify` shows a "rebuilt — review & Save" toast for user-initiated edits.
async function rebuildGrid({ notify = false } = {}) {
	const seq = ++rebuildSeq
	recomputeColumns()
	await Promise.all([loadItemValues(seq), loadBomValues(seq)])
	if (seq !== rebuildSeq) return // superseded by a newer edit
	buildAttributesList()
	buildGrid()
	reconcile(savedValues.value || [])
	if (notify && attributes.value.length) {
		toast.info("Grid rebuilt", "Attribute columns changed — review the BOM values and click Save.")
	}
}

// ── attribute-selector actions (item side) ──
function addItemAttr() {
	const a = addItemAttrSel.value
	if (!a || itemAttrRows.value.some((r) => r.attribute === a)) return
	itemAttrRows.value.push({ attribute: a, same_attribute: 0 })
	addItemAttrSel.value = null
	rebuildGrid({ notify: true })
}
function removeItemAttr(i) {
	itemAttrRows.value.splice(i, 1)
	rebuildGrid({ notify: true })
}
function setItemSame(i, val) {
	itemAttrRows.value[i].same_attribute = val ? 1 : 0
	rebuildGrid({ notify: true })
}
// ── attribute-selector actions (bom side) ──
function addBomAttr() {
	const a = addBomAttrSel.value
	if (!a || bomAttrRows.value.some((r) => r.attribute === a)) return
	bomAttrRows.value.push({ attribute: a, same_attribute: 0 })
	addBomAttrSel.value = null
	rebuildGrid({ notify: true })
}
function removeBomAttr(i) {
	bomAttrRows.value.splice(i, 1)
	rebuildGrid({ notify: true })
}
function setBomSame(i, val) {
	bomAttrRows.value[i].same_attribute = val ? 1 : 0
	rebuildGrid({ notify: true })
}

// Clear + write the shared value map atomically AFTER the fetch resolves, and
// only if this rebuild is still current — so an out-of-order older fetch can't
// clobber a newer rebuild's options (TOCTOU on the live dropdown options).
async function loadItemValues(seq) {
	if (!item.value || !itemAttrs.value.length) {
		for (const k of Object.keys(itemAttrValues)) delete itemAttrValues[k]
		return
	}
	try {
		const r = await callMethod("yrp.yrp.doctype.item.item.get_attribute_values", {
			item: item.value,
			attributes: itemAttrs.value,
		})
		if (seq !== undefined && seq !== rebuildSeq) return // superseded
		for (const k of Object.keys(itemAttrValues)) delete itemAttrValues[k]
		for (const [k, v] of Object.entries(r || {})) itemAttrValues[k] = v || []
	} catch (e) {
		toast.warn("Item attribute values", e.message)
	}
}

async function loadBomValues(seq) {
	if (!bomItem.value || !bomAttrs.value.length) {
		for (const k of Object.keys(bomAttrValues)) delete bomAttrValues[k]
		return
	}
	try {
		const r = await callMethod("yrp.yrp.doctype.item.item.get_attribute_values", {
			item: bomItem.value,
			attributes: bomAttrs.value,
		})
		if (seq !== undefined && seq !== rebuildSeq) return // superseded
		for (const k of Object.keys(bomAttrValues)) delete bomAttrValues[k]
		for (const [k, v] of Object.entries(r || {})) bomAttrValues[k] = v || []
	} catch (e) {
		toast.warn("BOM attribute values", e.message)
	}
}

// Best-effort breadcrumb: which IPD owns this mapping (item_bom.attribute_mapping).
async function fetchOwningIpd() {
	ipdName.value = null
	try {
		const rows = await callMethod("frappe.client.get_list", {
			doctype: "Item BOM",
			filters: { attribute_mapping: props.id },
			fields: ["parent", "parenttype"],
			limit_page_length: 1,
		})
		const row = (rows || [])[0]
		if (row && row.parenttype === "Item Production Detail") {
			ipdName.value = row.parent
			// Q3: the IPD is hash-named — fetch its produced item so the breadcrumb
			// shows a human name instead of the hash.
			try {
				const ipd = await callMethod("frappe.client.get_value", {
					doctype: "Item Production Detail",
					filters: { name: ipdName.value },
					fieldname: "item",
				})
				ipdItem.value = ipd?.item || ""
			} catch (_) {
				ipdItem.value = ""
			}
		}
	} catch (_) {
		ipdName.value = null
	}
}

// ════════════════ CROSS-PRODUCT (mirror set_attributes) ════════════════
// One row per combination of the ITEM attributes' values. bom cells start null,
// qty starts 0, every row included by default. Row order follows the value order
// returned by get_attribute_values → this position IS the saved `index`.
function buildGrid() {
	const rows = [{}]
	for (const attr of itemAttrs.value) {
		const values = itemAttrValues[attr] || []
		const next = []
		for (const combo of rows) {
			for (const val of values) {
				const nc = { ...combo }
				nc[itemKey(attr)] = val
				next.push(nc)
			}
		}
		rows.length = 0
		rows.push(...next)
	}
	// If there are item attrs but one has zero values the cross-product collapses
	// to nothing — guard so we don't render a single empty row.
	let combos = rows
	if (itemAttrs.value.length && combos.length === 1 && Object.keys(combos[0]).length === 0) {
		combos = []
	}
	combos.forEach((combo, i) => {
		combo.__row_id = i
		combo.included = true
		combo.__qty = 0
		for (const attr of bomAttrs.value) combo[bomKey(attr)] = null
	})
	data.value = combos
}

// find_index: locate the generated row matching a saved combo's item-side values.
function findIndex(itemValues) {
	for (let i = 0; i < data.value.length; i++) {
		const row = data.value[i]
		let ok = true
		for (const attr of itemAttrs.value) {
			if (itemValues[attr] !== row[itemKey(attr)]) {
				ok = false
				break
			}
		}
		if (ok) return i
	}
	return -1
}

// ════════════════ RECONCILE (mirror load_data) ════════════════
// Group saved values by index → {item:{attr:val}, bom:{attr:val}, qty}. Map each
// saved group's item-side combo back onto a generated row via findIndex and
// repopulate its bom cells + qty. Rows with no matching saved data are excluded.
function reconcile(values) {
	if (!data.value.length) return

	// No saved values yet (fresh / just-configured mapping) → leave every row
	// INCLUDED (buildGrid's default), exactly like the Desk's set_attributes,
	// which generates all combinations with included=true so the user can fill
	// them immediately. Only an existing mapping WITH saved values runs the
	// include-only-the-saved-rows reconciliation below (mirrors load_data, which
	// only toggles rows off when there is saved g_data to compare against).
	if (!values || !values.length) return

	// Group by saved index (same_attr rows never exist in `values`, so nothing to
	// strip here — but guard defensively in case legacy data carries them).
	const sameSet = new Set(sameAttrs.value)
	const byIndex = {}
	for (const v of values) {
		if (sameSet.has(v.attribute)) continue
		if (!byIndex[v.index]) byIndex[v.index] = { item: {}, bom: {}, qty: 0 }
		const g = byIndex[v.index]
		if (v.type === "item") g.item[v.attribute] = v.attribute_value
		else if (v.type === "bom") g.bom[v.attribute] = v.attribute_value
		if (v.quantity) g.qty = v.quantity
	}

	const matched = new Set()
	for (const idx of Object.keys(byIndex)) {
		const g = byIndex[idx]
		// Build the item-side combo as a plain {attr: value} map for findIndex.
		const itemValues = {}
		for (const attr of itemAttrs.value) itemValues[attr] = g.item[attr]
		const target = findIndex(itemValues)
		if (target < 0) continue
		const row = data.value[target]
		for (const attr of bomAttrs.value) {
			row[bomKey(attr)] = g.bom[attr] != null ? g.bom[attr] : null
		}
		if (bomAttrs.value.length > 0) row.__qty = g.qty || 0
		matched.add(target)
	}

	// Rows present in saved data → included; the rest → excluded (mirrors the
	// load_data tail that toggles every non-saved row off).
	data.value.forEach((row, i) => {
		row.included = matched.has(i)
	})
}

// ════════════════ ROW / COLUMN ACTIONS ════════════════
// Exclude clears the row's bom cells + qty (mirror toggle_row clearing inputs);
// include leaves them blank for the user to fill.
function toggleRow(index, included) {
	const row = data.value[index]
	row.included = included
	if (!included) {
		for (const attr of bomAttrs.value) row[bomKey(attr)] = null
		row.__qty = 0
	}
}

function fillColumn(attr) {
	const val = fillBom[attr]
	if (val == null || val === "") return
	for (const row of data.value) {
		if (!row.included) continue
		row[bomKey(attr)] = val
	}
}

function fillQuantity() {
	const q = fillQty.value
	if (q == null) return
	for (const row of data.value) {
		if (!row.included) continue
		row.__qty = q
	}
}

function disableRows() {
	// Exclude included rows that are incomplete (any blank bom cell, or no bom
	// columns at all) — mirrors disable_rows().
	for (let i = 0; i < data.value.length; i++) {
		const row = data.value[i]
		if (!row.included) continue
		let incomplete = bomAttrs.value.length === 0
		for (const attr of bomAttrs.value) {
			if (!row[bomKey(attr)]) {
				incomplete = true
				break
			}
		}
		if (incomplete) toggleRow(i, false)
	}
}

function enableRows() {
	for (let i = 0; i < data.value.length; i++) {
		if (!data.value[i].included) toggleRow(i, true)
	}
}

// ════════════════ SAVE (mirror get_final_output → frm.doc.values) ════════════════
// Emit item + bom value rows per included, complete combination. Validation
// mirrors get_final_output: every item cell present, every bom cell present, qty
// truthy. same_attrs are absent from itemAttrs/bomAttrs so they're never emitted.
function buildValues() {
	const output = []
	for (let i = 0; i < data.value.length; i++) {
		const row = data.value[i]
		if (!row.included) continue
		const qty = row.__qty

		// item-side rows
		for (const attr of itemAttrs.value) {
			const value = row[itemKey(attr)]
			if (!value) return { error: `Combination ${i + 1}: missing item value for ${attr}.` }
			output.push({
				index: i,
				type: "item",
				attribute: attr,
				attribute_value: value,
				quantity: qty || 0,
			})
		}
		// bom-side rows
		for (const attr of bomAttrs.value) {
			const value = row[bomKey(attr)]
			if (!value) return { error: `Combination ${i + 1}: choose a BOM value for ${attr} (or exclude the row).` }
			if (!qty || qty === 0) {
				return { error: `Combination ${i + 1}: quantity must be greater than 0 (or exclude the row).` }
			}
			output.push({
				index: i,
				type: "bom",
				attribute: attr,
				attribute_value: value,
				quantity: qty,
			})
		}
	}
	return { output }
}

async function onSave() {
	// No item attributes at all → engine treats as an empty mapping; allow a
	// cleared save (mirrors the validate() branch that empties values).
	if (!attributes.value.length) {
		await persist([])
		return
	}
	const built = buildValues()
	if (built.error) {
		toast.warn("Incomplete mapping", built.error)
		return
	}
	if (!built.output.length) {
		toast.warn("Nothing to save", "Include at least one complete combination, or there is nothing to map.")
		return
	}
	await persist(built.output)
}

async function persist(values) {
	// Preserve the item_attributes / bom_item_attributes child rows verbatim — the
	// engine reads their same_attribute flags (RISK FLAG 1). Only `values` changes.
	const payload = {
		item: item.value || null,
		bom_item: bomItem.value || null,
		item_attributes: itemAttrRows.value.map((r) => ({
			attribute: r.attribute,
			same_attribute: r.same_attribute ? 1 : 0,
		})),
		bom_item_attributes: bomAttrRows.value.map((r) => ({
			attribute: r.attribute,
			same_attribute: r.same_attribute ? 1 : 0,
		})),
		values,
	}
	try {
		await docState.save(payload, props.id)
		toast.success("Saved", `${props.id} updated`)
		await load()
	} catch (e) {
		toast.error("Save failed", e.message)
	}
}

// Heal a mapping with empty attribute columns: derive item-side = owning IPD's
// primary attribute, bom-side = all BOM item attributes (server-side, mirrors
// production_api). Then reload so the grid renders. Used for legacy mappings
// created before openMapping seeded columns at creation time.
async function configureColumns() {
	configuring.value = true
	try {
		const res = await callMethod(
			"essdee_yrp.api.bom_mapping.configure_columns",
			{ mapping: props.id },
		)
		if (res && res.changed === false) {
			toast.info("Already configured", "This mapping already has attribute columns.")
		} else {
			toast.success("Columns configured", "Attribute columns set from the owning IPD.")
		}
		await load()
	} catch (e) {
		toast.error("Could not configure columns", e.message)
	} finally {
		configuring.value = false
	}
}

// Ctrl/Cmd+S → Save (mirror the Frappe Desk shortcut). preventDefault stops the
// browser's "save page" dialog. Guarded so it doesn't fire while loading, errored,
// or already saving.
function onKeydown(e) {
	const key = (e.key || "").toLowerCase()
	if ((e.ctrlKey || e.metaKey) && key === "s") {
		e.preventDefault()
		if (loading.value || loadError.value || saving.value) return
		onSave()
	}
}

onMounted(() => {
	load()
	window.addEventListener("keydown", onKeydown)
	window.addEventListener("beforeunload", beforeUnloadGuard)
})
onBeforeUnmount(() => {
	window.removeEventListener("keydown", onKeydown)
	window.removeEventListener("beforeunload", beforeUnloadGuard)
})

// Q6: confirm before leaving with unsaved mapping edits.
onBeforeRouteLeave((to, from, next) => {
	if (isDirty.value) {
		confirm.require({
			header: "Discard unsaved changes?",
			message: "You have unsaved changes to this BOM mapping. Leave without saving?",
			icon: "pi pi-exclamation-triangle",
			acceptLabel: "Leave",
			acceptClass: "p-button-danger",
			rejectLabel: "Stay",
			accept: () => { isDirty.value = false; next() },
			reject: () => next(false),
		})
	} else next()
})

// ── navigation ──
function goHome() {
	router.push("/home")
}
function goIpd() {
	if (ipdName.value) router.push(`/item-production-detail/${encodeURIComponent(ipdName.value)}`)
}
function goMappingList() {
	// No /web list page for Item BOM Attribute Mapping (open it only from the
	// owning IPD's BOM row). Strict no-Desk rule: do NOT redirect to
	// /app/item-bom-attribute-mapping. Surface a friendly toast instead.
	toast.warn(
		"No /web list",
		"Item BOM Attribute Mappings are opened from an IPD's BOM row.",
	)
}
function navItem(name) {
	if (name) router.push(`/item/${encodeURIComponent(name)}`)
}
</script>

<style scoped>
.bom-mapping-editor {
	display: flex;
	flex-direction: column;
	gap: 14px;
}
.inline-link {
	color: var(--esd-accent-700);
	cursor: pointer;
	text-decoration: underline;
}
.inline-link:hover {
	color: var(--esd-accent);
}

/* Empty-columns state with the auto-configure CTA */
.empty-config {
	padding: 20px;
	display: flex;
	flex-direction: column;
	gap: 16px;
}
.empty-config-body {
	display: flex;
	gap: 14px;
	align-items: flex-start;
}
.empty-icon {
	font-size: 26px;
	color: var(--esd-accent-700);
	margin-top: 2px;
}
.empty-text h3 {
	margin: 0 0 4px;
	font-size: 15px;
	font-weight: 600;
	color: var(--esd-ink);
}
.empty-text p {
	margin: 0;
	font-size: 13px;
	line-height: 1.5;
	color: var(--esd-muted);
}
.empty-config-actions {
	display: flex;
	align-items: center;
	gap: 12px;
	flex-wrap: wrap;
}
.dot-sep {
	color: var(--esd-muted-2);
}

/* Attribute selector panels (mirror Desk item_attributes / bom_item_attributes) —
   side by side: Item Attributes left, BOM Item Attributes right. */
.attr-panels-row {
	display: grid;
	grid-template-columns: 1fr 1fr;
	gap: 14px;
	align-items: start;
}
@media (max-width: 760px) {
	.attr-panels-row {
		grid-template-columns: 1fr;
	}
}
.attr-panel .panel-head {
	gap: 6px 10px;
	flex-wrap: wrap;
}
.attr-panel .panel-meta {
	font-size: 11.5px;
}
.attr-body {
	padding: 12px 16px;
	display: flex;
	flex-direction: column;
	gap: 10px;
}
.attr-empty {
	font-size: 12.5px;
	color: var(--esd-muted-2);
	font-style: italic;
}
.attr-list {
	list-style: none;
	margin: 0;
	padding: 0;
	display: flex;
	flex-direction: column;
	gap: 6px;
}
.attr-row {
	display: flex;
	align-items: center;
	gap: 12px;
	padding: 6px 10px;
	background: var(--esd-slate-50);
	border: 1px solid var(--esd-line);
	border-radius: var(--radius-sm);
}
.attr-name {
	font-weight: 600;
	font-size: 13px;
	color: var(--esd-ink);
	min-width: 120px;
}
.same-toggle {
	display: inline-flex;
	align-items: center;
	gap: 6px;
	font-size: 12px;
	color: var(--esd-muted);
	cursor: pointer;
	margin-left: auto;
}
.attr-add {
	display: flex;
	align-items: center;
	gap: 8px;
}
.attr-add-select {
	min-width: 240px;
}

/* Breadcrumb + header (mirror ProcessMatrixEditor / DocDetail) */
.crumbs {
	display: flex;
	align-items: center;
	gap: 7px;
	font-size: 12.5px;
	color: var(--esd-muted);
}
.crumbs a {
	cursor: pointer;
	color: var(--esd-muted);
}
.crumbs a:hover {
	color: var(--esd-accent-700);
}
.crumbs .sep {
	color: var(--esd-muted-2);
}
.detail-head {
	display: flex;
	align-items: flex-start;
	gap: 14px;
}
.id-block {
	display: flex;
	flex-direction: column;
	gap: 3px;
}
/* Q2: hero is the produced item; the mapping code drops to a small mono chip. */
.doc-hero {
	font-size: 20px;
	font-weight: 700;
	letter-spacing: -0.01em;
	color: var(--esd-ink);
	line-height: 1.2;
}
.doc-sub {
	font-size: 13px;
	color: var(--esd-muted);
}
.doc-id {
	font-size: 12px;
	color: var(--esd-muted);
}
.doc-title {
	font-size: 13px;
	color: var(--esd-muted);
}
.head-actions {
	margin-left: auto;
	display: flex;
	gap: 8px;
	align-items: center;
	flex-wrap: wrap;
	justify-content: flex-end;
}
.desk-link {
	display: inline-flex;
	align-items: center;
	gap: 6px;
	font-size: 12.5px;
	color: var(--esd-accent-700);
	padding: 6px 10px;
	border: 1px solid var(--esd-line);
	border-radius: var(--radius-sm);
}
.desk-link:hover {
	background: var(--esd-accent-50);
}

.state-block {
	display: flex;
	flex-direction: column;
	align-items: center;
	gap: 10px;
	padding: 40px 0;
	color: var(--esd-muted);
}

/* Panels */
.panel {
	background: var(--esd-card);
	border: 1px solid var(--esd-line);
	border-radius: var(--radius);
	overflow: hidden;
}
/* Section heads share the Bright Workshop band (light tint; mirrors .esd-card__head). */
.panel-head {
	display: flex;
	align-items: center;
	gap: var(--space-2);
	padding: 10px 16px;
	background: var(--esd-accent-50); border-bottom: 1px solid var(--esd-line);
}
.panel-head::before {
	content: "";
	width: 6px;
	height: 6px;
	border-radius: 999px;
	background: var(--esd-accent-ink);
	opacity: 0.85;
	flex: 0 0 auto;
}
.panel-head h3 {
	margin: 0;
	font-size: 13px;
	font-weight: 700;
	letter-spacing: 0.02em;
	text-transform: uppercase;
	color: var(--esd-accent-ink);
}
/* The panel-meta sub-label on the attr heads reads as a right-aligned count pill. */
.panel-head .panel-meta {
	margin-left: auto;
	background: #fff;
	color: var(--esd-accent-ink);
	font-size: 11px;
	font-weight: 600;
	padding: 1px 8px;
	border-radius: 999px;
}

/* Context grid */
.ctx-grid {
	display: grid;
	grid-template-columns: repeat(2, minmax(0, 1fr));
	gap: 16px 24px;
	padding: 16px;
}
@media (max-width: 700px) {
	.ctx-grid {
		grid-template-columns: 1fr;
	}
}
.ctx-fld {
	display: flex;
	flex-direction: column;
	gap: 4px;
	min-width: 0;
}
.ctx-fld label {
	font-size: 11.5px;
	letter-spacing: 0.04em;
	text-transform: uppercase;
	color: var(--esd-muted);
	font-weight: 600;
}
.ctx-val {
	font-size: 14px;
	color: var(--esd-accent-700);
	cursor: pointer;
}
.ctx-val:hover {
	text-decoration: underline;
}
.ctx-hint {
	font-size: 11px;
	color: var(--esd-muted-2);
}
.same-note {
	display: flex;
	align-items: flex-start;
	gap: 8px;
	margin: 0 16px 16px;
	padding: 10px 12px;
	font-size: 12.5px;
	color: var(--esd-ink-2);
	background: var(--esd-accent-50);
	border: 1px solid var(--esd-line);
	border-radius: var(--radius-sm);
}
.same-note .pi {
	color: var(--esd-accent-700);
	margin-top: 2px;
}

/* Grid meta */
.grid-toolbar {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: 12px;
	flex-wrap: wrap;
}
.grid-toolbar-actions {
	display: flex;
	gap: 8px;
}
.grid-meta {
	display: flex;
	align-items: center;
	gap: var(--space-2);
	font-size: 12.5px;
	color: var(--esd-muted);
	padding: 0 2px;
}
.grid-warn {
	color: var(--esd-warn);
}

/* Grid */
.grid-panel {
	padding: 0;
}
.bom-dt {
	font-size: 13px;
}
.col-head {
	display: flex;
	flex-direction: column;
	gap: 6px;
	align-items: stretch;
}
.col-fill {
	display: flex;
	align-items: center;
	gap: 4px;
}
.fill-select,
.fill-num {
	flex: 1;
	min-width: 0;
}
.item-chip {
	font-weight: 500;
}
/* Constrain the repeated per-row inputs so rows stop wasting horizontal space. */
.cell-select,
.cell-num {
	width: 100%;
	max-width: 160px;
}
.cell-missing :deep(.p-select),
.cell-missing :deep(.p-inputnumber-input) {
	border-color: var(--esd-warn);
}
.cell-missing.cell-num :deep(.p-inputnumber-input) {
	border-color: var(--esd-warn);
}

:deep(.bom-dt .p-datatable-thead > tr > th) {
	font-size: 11.5px;
	letter-spacing: 0.03em;
	padding: 8px;
	vertical-align: top;
}
/* Zebra striping + taller rows for a long (15-row) grid's scannability. */
:deep(.bom-dt .p-datatable-tbody > tr:nth-child(even)) {
	background: var(--esd-bg);
}
:deep(.bom-dt .p-datatable-tbody > tr > td) {
	padding: 9px 10px;
	vertical-align: middle;
}
</style>
