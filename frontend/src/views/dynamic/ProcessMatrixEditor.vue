<!--
  ProcessMatrixEditor — the "process the combination" surface (R1a).

  PrimeVue port of apps/yrp/yrp/public/js/ProcessMatrix/EditProcessMatrix.vue +
  the Generate-Combinations / dependent-attribute-strip logic from
  ipd_process_matrix.js. Drives the IPD Process Matrix doctype.

  Modes
  -----
  - EXISTING (:id is a real matrix name): getDoc → rebuild `groups` from the
    doc's `combinations` + `combination_attributes` child arrays (same algorithm
    as EditProcessMatrix.load()). Submitted (docstatus 1/2) → read-only.
  - CREATE (:id === "new"): read `ipd` + `process` from the query, build a blank
    header, then auto-attempt generate_cross_product to pre-seed group 0 (no-op
    if no input/output attributes are defined yet). First Save creates the doc
    and we router.replace to its real name (→ remount in EXISTING mode).

  Dependent-attribute STRIP (RISK FLAG 2)
  ---------------------------------------
  We fetch the IPD's `dependent_attribute` (e.g. Stage) and exclude it from the
  editable Input/Output attribute COLUMNS. The engine re-stamps Stage onto each
  combination from the IPD Process in/out stage (ipd_engine). We never show it as
  a column and never write it as a combination attribute. The doctype's
  validate_attributes_belong_to_ipd() throws if Stage leaks into a matrix, so the
  strip is also what keeps Save from being rejected.

  Save round-trip
  ---------------
  serialize `groups` → flat `combinations` (group_index, group_name, side,
  combo_index, quantity, uom, wastage_pct) + `combination_attributes`
  (group_index, side, combo_index, attribute, attribute_value), mirroring
  EditProcessMatrix.syncBack(). Sent with the header + attribute children via the
  standard REST PUT/POST (useDoc). The doc's validate() runs server-side.

  reference_item_variant / input_item / output_item (RISK FLAG 3): editable header
  fields so a process can own a reference-specific matrix vs the generic pool.
  reference_item_variant uses a plain Item Variant AutoComplete filtered to the
  IPD's item (we avoid the Desk's @validate_and_sanitize_search_inputs query,
  which needs a positional searchfield/start/page_len signature awkward over HTTP).
-->
<template>
	<div class="matrix-editor">
		<!-- Breadcrumb -->
		<nav class="crumbs">
			<a @click="goHome">Home</a>
			<span class="sep">/</span>
			<a v-if="header.ipd" @click="goIpd">{{ ipdLabel }}</a>
			<a v-else @click="goMatrixList">IPD Process Matrix</a>
			<span class="sep">/</span>
			<span class="crumb-cur esd-mono">{{ isCreate ? "New Matrix" : id }}</span>
		</nav>

		<!-- Header (Q2: human descriptor is the hero; the matrix code is a chip). -->
		<div class="detail-head">
			<div class="id-block">
				<div class="doc-hero">
					{{ header.process_name || (isCreate ? "New Process Matrix" : "Process Matrix") }}
				</div>
				<div class="doc-sub">
					Process the combination<span v-if="ipdLabel"> · {{ ipdLabel }}</span>
				</div>
				<div v-if="!isCreate" class="doc-id esd-mono">{{ id }}</div>
			</div>
			<Tag
				v-if="readonly"
				class="head-status"
				:value="isSubmitted ? 'Read-only (submitted)' : 'Read-only'"
				severity="secondary"
				rounded
			/>
			<div class="head-actions">
				<Button
					v-if="!readonly"
					label="Generate Combinations"
					icon="pi pi-bolt"
					size="small"
					severity="secondary"
					outlined
					:loading="generating"
					@click="generateCombinations"
				/>
				<Button
					v-if="!readonly"
					label="Add Group"
					icon="pi pi-plus"
					size="small"
					severity="secondary"
					outlined
					@click="addGroup"
				/>
				<Button
					v-if="!readonly"
					:label="isCreate ? 'Create' : 'Save'"
					icon="pi pi-check"
					size="small"
					:loading="saving"
					@click="onSave"
				/>
				<a
					v-if="!isCreate && (isAdmin || hasRole('System Manager'))"
					class="desk-link"
					:href="deskUrl"
					target="_blank"
					rel="noopener"
				>
					<i class="pi pi-external-link" /> Open in Desk
				</a>
			</div>
		</div>

		<!-- Loading -->
		<div v-if="loading" class="state-block">
			<i class="pi pi-spin pi-spinner" style="font-size: 1.5rem" />
			<span>Loading…</span>
		</div>

		<Message v-else-if="loadError" severity="error" :closable="false">{{ loadError }}</Message>

		<template v-else>
			<!-- ── Header fields ── -->
			<section class="panel">
				<div class="panel-head"><h3>Matrix</h3></div>
				<div class="hdr-grid">
					<div class="fld-wrap">
						<label>IPD <span class="req">*</span></label>
						<AutoComplete
							v-model="header.ipd"
							:suggestions="ipdSuggestions"
							@complete="searchIpd"
							:disabled="readonly || !isCreate"
							placeholder="Item Production Detail"
							dropdown
							completeOnFocus
							fluid
							@item-select="onIpdChanged"
							@change="onIpdMaybeCleared"
						/>
					</div>
					<div class="fld-wrap">
						<label>Process <span class="req">*</span></label>
						<AutoComplete
							v-model="header.process_name"
							:suggestions="processSuggestions"
							@complete="searchProcess"
							:disabled="readonly"
							placeholder="Process"
							dropdown
							completeOnFocus
							fluid
						/>
					</div>
					<div class="fld-wrap">
						<label>Reference Item Variant</label>
						<LinkField
							v-model="header.reference_item_variant"
							target-doctype="Item Variant"
							:search-handler="searchVariantHandler"
							:disabled="readonly"
							placeholder="Generic (leave blank)"
						/>
						<small class="fld-hint">Blank = generic matrix for the whole process pool.</small>
					</div>
					<div class="fld-wrap">
						<label>Input Item</label>
						<LinkField
							v-model="header.input_item"
							target-doctype="Item"
							:disabled="readonly"
							placeholder="IPD item (leave blank)"
							@item-select="onInputItemChanged"
							@change="onInputItemMaybeCleared"
						/>
						<small class="fld-hint">Source consumed (e.g. fabric for Cutting). Blank = IPD's item.</small>
					</div>
					<div class="fld-wrap">
						<label>Output Item</label>
						<LinkField
							v-model="header.output_item"
							target-doctype="Item"
							:disabled="readonly"
							placeholder="IPD item (leave blank)"
							@item-select="onOutputItemChanged"
							@change="onOutputItemChanged"
						/>
						<small class="fld-hint">Item produced. Blank = IPD's item.</small>
					</div>
				</div>
			</section>

			<!-- ── Attribute pickers (IPD Matrix Attribute children) ── -->
			<section class="panel">
				<div class="panel-head">
					<h3>Combination Attributes</h3>
					<span class="panel-meta">
						The IPD's dependent attribute<span v-if="dependentAttribute"> ({{ dependentAttribute }})</span>
						is excluded — the engine stamps it from the process in/out stage.
					</span>
				</div>
				<div class="attr-pickers">
					<div class="attr-col input-col">
						<div class="attr-col-head">
							<span>Input Attributes</span>
							<AutoComplete
								v-if="!readonly"
								v-model="newInputAttr"
								:suggestions="attrSuggestions"
								@complete="searchAttribute"
								@item-select="addInputAttr"
								placeholder="+ add attribute"
								dropdown
								class="attr-add"
							/>
						</div>
						<div class="attr-chips">
							<Tag
								v-for="a in inputAttributes"
								:key="'ia-' + a"
								:value="a"
								severity="primary"
								rounded
							>
								<span>{{ a }}</span>
								<i v-if="!readonly" class="pi pi-times chip-x" @click="removeInputAttr(a)" />
							</Tag>
							<span v-if="!inputAttributes.length" class="muted-dash">No input attributes.</span>
						</div>
					</div>
					<div class="attr-col output-col">
						<div class="attr-col-head">
							<span>Output Attributes</span>
							<AutoComplete
								v-if="!readonly"
								v-model="newOutputAttr"
								:suggestions="attrSuggestions"
								@complete="searchAttribute"
								@item-select="addOutputAttr"
								placeholder="+ add attribute"
								dropdown
								class="attr-add"
							/>
						</div>
						<div class="attr-chips">
							<Tag
								v-for="a in outputAttributes"
								:key="'oa-' + a"
								:value="a"
								severity="secondary"
								rounded
							>
								<span>{{ a }}</span>
								<i v-if="!readonly" class="pi pi-times chip-x" @click="removeOutputAttr(a)" />
							</Tag>
							<span v-if="!outputAttributes.length" class="muted-dash">No output attributes.</span>
						</div>
					</div>
				</div>
			</section>

			<!-- ── Groups ── -->
			<div class="groups-meta">
				{{ groups.length }} group(s) · {{ totalCombos }} combination(s)
			</div>

			<section v-for="(group, gi) in groups" :key="group.group_index" class="panel group-panel">
				<div class="group-head">
					<span class="group-tag">Group {{ group.group_index }}</span>
					<InputText
						v-model="group.group_name"
						:disabled="readonly"
						placeholder="Group name (optional)"
						class="group-name"
					/>
					<Button
						v-if="!readonly"
						icon="pi pi-trash"
						text
						rounded
						severity="danger"
						size="small"
						@click="deleteGroup(gi)"
						v-tooltip.left="'Delete group'"
					/>
				</div>

				<!-- Inputs -->
				<div class="side-block input-side">
					<div class="side-heading">
						<span>Inputs</span>
						<Button
							v-if="!readonly"
							label="Add Input"
							icon="pi pi-plus"
							size="small"
							text
							@click="addRow(group, 'Input')"
						/>
					</div>
					<DataTable :value="group.inputs" class="esd-table combo-dt" :rowHover="false">
						<Column v-for="a in inputAttributes" :key="'i-c-' + a" :header="a">
							<template #body="{ data }">
								<Select
									v-model="data.attrs[a]"
									:options="attributeValuesInput[a] || []"
									:disabled="readonly"
									showClear
									placeholder="—"
									class="cell-select"
									fluid
								/>
							</template>
						</Column>
						<Column header="Qty" :style="{ width: '110px' }">
							<template #body="{ data }">
								<InputNumber
									v-model="data.qty"
									:disabled="readonly"
									:minFractionDigits="0"
									:maxFractionDigits="6"
									class="cell-num"
									fluid
								/>
							</template>
						</Column>
						<Column header="UOM" :style="{ width: '120px' }">
							<template #body="{ data }">
								<InputText v-model="data.uom" :disabled="readonly" placeholder="UOM" class="cell-text" fluid />
							</template>
						</Column>
						<Column :style="{ width: '52px' }">
							<template #body="{ index }">
								<Button v-if="!readonly" icon="pi pi-times" text rounded severity="danger" size="small" @click="deleteRow(group, 'inputs', index)" />
							</template>
						</Column>
						<template #empty>
							<div class="esd-empty">
								<i class="pi pi-table" />
								<p class="esd-empty__text">No input rows.</p>
							</div>
						</template>
					</DataTable>
				</div>

				<!-- Outputs -->
				<div class="side-block output-side">
					<div class="side-heading">
						<span>Outputs</span>
						<Button
							v-if="!readonly"
							label="Add Output"
							icon="pi pi-plus"
							size="small"
							text
							@click="addRow(group, 'Output')"
						/>
					</div>
					<DataTable :value="group.outputs" class="esd-table combo-dt" :rowHover="false">
						<Column v-for="a in outputAttributes" :key="'o-c-' + a" :header="a">
							<template #body="{ data }">
								<Select
									v-model="data.attrs[a]"
									:options="attributeValuesOutput[a] || []"
									:disabled="readonly"
									showClear
									placeholder="—"
									class="cell-select"
									fluid
								/>
							</template>
						</Column>
						<Column header="Qty" :style="{ width: '110px' }">
							<template #body="{ data }">
								<InputNumber
									v-model="data.qty"
									:disabled="readonly"
									:minFractionDigits="0"
									:maxFractionDigits="6"
									class="cell-num"
									fluid
								/>
							</template>
						</Column>
						<Column header="UOM" :style="{ width: '120px' }">
							<template #body="{ data }">
								<InputText v-model="data.uom" :disabled="readonly" placeholder="UOM" class="cell-text" fluid />
							</template>
						</Column>
						<Column :style="{ width: '52px' }">
							<template #body="{ index }">
								<Button v-if="!readonly" icon="pi pi-times" text rounded severity="danger" size="small" @click="deleteRow(group, 'outputs', index)" />
							</template>
						</Column>
						<template #empty>
							<div class="esd-empty">
								<i class="pi pi-table" />
								<p class="esd-empty__text">No output rows.</p>
							</div>
						</template>
					</DataTable>
				</div>
			</section>

			<div v-if="!groups.length" class="esd-empty">
				<i class="pi pi-sitemap" />
				<p class="esd-empty__text">
					No groups yet. Add a group, or use
					<strong>Generate Combinations</strong> to seed from the attribute cross-product.
				</p>
				<Button
					v-if="!readonly"
					label="Add Group"
					icon="pi pi-plus"
					size="small"
					severity="secondary"
					outlined
					@click="addGroup"
				/>
			</div>
		</template>
	</div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted, onBeforeUnmount, nextTick } from "vue"
import { useRouter, useRoute, onBeforeRouteLeave } from "vue-router"
import DataTable from "primevue/datatable"
import Column from "primevue/column"
import Button from "primevue/button"
import Tag from "primevue/tag"
import Message from "primevue/message"
import InputText from "primevue/inputtext"
import InputNumber from "primevue/inputnumber"
import Select from "primevue/select"
import AutoComplete from "primevue/autocomplete"
import Tooltip from "primevue/tooltip"
import LinkField from "@/components/LinkField.vue"
import { callMethod, getDoc, searchLink } from "@/api/client"
import { useDoc } from "@/composables/useDoc"
import { useAppToast } from "@/composables/useToast"
import { useAppConfirm } from "@/composables/useConfirm"
import { usePermissions } from "@/composables/usePermissions"

const vTooltip = Tooltip

const props = defineProps({
	id: { type: String, required: true },
})

const router = useRouter()
const route = useRoute()
const toast = useAppToast()
const confirm = useAppConfirm()
const { isAdmin, hasRole } = usePermissions()

const DOCTYPE = "IPD Process Matrix"
const docState = useDoc(DOCTYPE)

const isCreate = computed(() => props.id === "new")

// ── reactive model ──
const header = reactive({
	ipd: "",
	process_name: "",
	reference_item_variant: "",
	input_item: "",
	output_item: "",
})
const inputAttributes = ref([])   // [attrName] (dependent attr already stripped)
const outputAttributes = ref([])
const attributeValuesInput = reactive({})   // { attr: [values] }
const attributeValuesOutput = reactive({})
const groups = ref([])            // [{ group_index, group_name, inputs:[row], outputs:[row] }]
const dependentAttribute = ref(null)
// Q3: the owning IPD's produced item (IPD is hash-autonamed with no title_field,
// so its human identity is the `item` data field — fetched in fetchDependentAttribute).
const ipdItem = ref("")
const docstatus = ref(0)
// Default UOMs for new input/output rows — the consumed/produced item's default
// UOM (input rows ← input_item ‖ IPD item, output rows ← output_item ‖ IPD item).
const inputUom = ref("")
const outputUom = ref("")

const loading = ref(false)
const loadError = ref(null)
const saving = computed(() => docState.saving.value)
const generating = ref(false)

// B2: editing the matrix is System-Manager-only. Every other user gets a
// READ-ONLY view (fields disabled, no Add Input/Output, no delete/edit, no Save).
// This gate is scoped to matrix EDITING only — viewing the IPD and saving/creating
// Item Production Detail records is unaffected (that lives in IPDConfigView /
// DocDetail, not here; IPDs are auto-created and every user must still save them).
const canEditMatrix = computed(() => isAdmin.value || hasRole("System Manager"))
// Submitted/cancelled matrices are engine-owned → read-only regardless of role.
const isSubmitted = computed(() => docstatus.value === 1 || docstatus.value === 2)
const readonly = computed(() => isSubmitted.value || !canEditMatrix.value)

// Q6: unsaved-changes guard. A deep watch flags the editable model dirty once
// armed (after load + any create-mode auto-generate settle, so programmatic
// seeding doesn't count). resetDirty()/armDirty() bracket load(); onSave clears it.
const isDirty = ref(false)
const dirtyArmed = ref(false)
watch(
	[header, groups, inputAttributes, outputAttributes, attributeValuesInput, attributeValuesOutput],
	() => { if (dirtyArmed.value) isDirty.value = true },
	{ deep: true },
)
async function armDirty() {
	await nextTick()
	dirtyArmed.value = true
}
function beforeUnloadGuard(e) {
	if (isDirty.value && !readonly.value) {
		e.preventDefault()
		e.returnValue = ""
	}
}

// Q2/Q3: the owning IPD's produced item names the breadcrumb + hero (the IPD's
// own name is a meaningless hash). Falls back to the IPD code until item resolves.
const ipdLabel = computed(() => (header.ipd ? (ipdItem.value || header.ipd) : ""))

const totalCombos = computed(() => {
	let n = 0
	for (const g of groups.value) n += g.inputs.length + g.outputs.length
	return n
})

const deskUrl = computed(
	() => `/app/ipd-process-matrix/${encodeURIComponent(props.id)}`,
)

// ── autocomplete buffers ──
const ipdSuggestions = ref([])
const processSuggestions = ref([])
const attrSuggestions = ref([])
const newInputAttr = ref(null)
const newOutputAttr = ref(null)

// ════════════════ LOAD ════════════════
async function load() {
	loading.value = true
	loadError.value = null
	dirtyArmed.value = false
	isDirty.value = false
	try {
		if (isCreate.value) {
			// Seed header from query (?ipd=&process=).
			header.ipd = route.query.ipd || ""
			header.process_name = route.query.process || ""
			header.reference_item_variant = ""
			header.input_item = ""
			header.output_item = ""
			inputAttributes.value = []
			outputAttributes.value = []
			groups.value = []
			docstatus.value = 0
			if (header.ipd) {
				await fetchDependentAttribute()
				await refreshSideUoms()
				// Pre-seed: only fires if attributes already exist on the IPD's
				// item AND we add attribute rows — a brand-new matrix has none,
				// so this is typically a graceful no-op (mirrors Desk: Generate
				// requires attributes). Kept per the synthesized-flow spec.
				await generateCombinations({ silent: true })
			}
		} else {
			const doc = await getDoc(DOCTYPE, props.id)
			header.ipd = doc.ipd || ""
			header.process_name = doc.process_name || ""
			header.reference_item_variant = doc.reference_item_variant || ""
			header.input_item = doc.input_item || ""
			header.output_item = doc.output_item || ""
			docstatus.value = Number(doc.docstatus) || 0

			await fetchDependentAttribute()
			// Strip dependent attr from the editable columns (RISK FLAG 2).
			inputAttributes.value = stripDependent(
				(doc.input_attributes || []).map((r) => r.attribute).filter(Boolean),
			)
			outputAttributes.value = stripDependent(
				(doc.output_attributes || []).map((r) => r.attribute).filter(Boolean),
			)

			await reloadAttributeValues()
			rebuildGroups(doc.combinations || [], doc.combination_attributes || [])
			await refreshSideUoms()
		}
	} catch (e) {
		loadError.value = e.message || "Failed to load"
	} finally {
		loading.value = false
	}
	// Q3: resolve the owning IPD's human title for the breadcrumb/hero.
	// Q6: arm dirty tracking only after load + auto-generate settle.
	armDirty()
}

async function fetchDependentAttribute() {
	dependentAttribute.value = null
	ipdItem.value = ""
	if (!header.ipd) return
	try {
		const r = await callMethod("frappe.client.get_value", {
			doctype: "Item Production Detail",
			filters: { name: header.ipd },
			fieldname: ["dependent_attribute", "item"],
		})
		dependentAttribute.value = r?.dependent_attribute || null
		ipdItem.value = r?.item || ""
	} catch (_) {
		dependentAttribute.value = null
	}
}

function stripDependent(list) {
	const dep = dependentAttribute.value
	if (!dep) return list
	return list.filter((a) => a !== dep)
}

// Rebuild `groups` from the flat child arrays — same algorithm as
// EditProcessMatrix.load().
function rebuildGroups(combos, attrs) {
	const attrLookup = {}
	for (const a of attrs) {
		const k = a.group_index + "|" + a.side + "|" + a.combo_index
		if (!attrLookup[k]) attrLookup[k] = {}
		attrLookup[k][a.attribute] = a.attribute_value
	}

	const grouped = {}
	for (const c of combos) {
		if (!grouped[c.group_index]) {
			grouped[c.group_index] = {
				group_index: c.group_index,
				group_name: c.group_name || "",
				inputs: [],
				outputs: [],
			}
		} else if (c.group_name && !grouped[c.group_index].group_name) {
			grouped[c.group_index].group_name = c.group_name
		}
		const k = c.group_index + "|" + c.side + "|" + c.combo_index
		const attrSet = attrLookup[k] || {}
		const list = c.side === "Input" ? inputAttributes.value : outputAttributes.value
		const rowAttrs = {}
		// Only surface attrs we still show as columns (dependent attr excluded).
		for (const a of list) rowAttrs[a] = attrSet[a] || null
		const row = { qty: c.quantity, uom: c.uom || "", wastage_pct: c.wastage_pct || 0, attrs: rowAttrs }
		if (c.side === "Input") grouped[c.group_index].inputs.push(row)
		else grouped[c.group_index].outputs.push(row)
	}
	groups.value = Object.values(grouped).sort((a, b) => a.group_index - b.group_index)
}

// B1: load the FULL value list for every attribute, UNFILTERED by the item's
// variants. The matrix is now auto-generated from the IPD, so the old
// item-variant constraint (yrp.yrp.api.matrix.get_matrix_attribute_values, which
// resolved values off the IPD item's attribute mappings and rendered empty "—"
// selects) is obsolete. "Item Attribute Value" is a standalone doctype keyed by
// `attribute_name`; we list every value of each attribute in play, both sides.
async function reloadAttributeValues() {
	// Clear existing keys.
	for (const k of Object.keys(attributeValuesInput)) delete attributeValuesInput[k]
	for (const k of Object.keys(attributeValuesOutput)) delete attributeValuesOutput[k]
	const attrs = Array.from(new Set([...inputAttributes.value, ...outputAttributes.value]))
	if (!attrs.length) return
	try {
		const rows = await callMethod("frappe.client.get_list", {
			doctype: "Item Attribute Value",
			filters: { attribute_name: ["in", attrs] },
			fields: ["attribute_name", "attribute_value"],
			limit_page_length: 0,
			order_by: "attribute_value asc",
		})
		const byAttr = {}
		for (const row of rows || []) {
			if (!row?.attribute_name) continue
			if (!byAttr[row.attribute_name]) byAttr[row.attribute_name] = []
			byAttr[row.attribute_name].push(row.attribute_value)
		}
		for (const a of inputAttributes.value) attributeValuesInput[a] = byAttr[a] || []
		for (const a of outputAttributes.value) attributeValuesOutput[a] = byAttr[a] || []
	} catch (e) {
		toast.warn("Attribute values", e.message)
	}
}

onMounted(load)

// Q6: unsaved-changes guards — native browser-close + SPA route-leave.
// Ctrl/Cmd+S → Save (mirror the Desk + DocDetail shortcut the specialized editors
// were missing). preventDefault stops the browser's "save page" dialog.
function onKeydown(e) {
	const key = (e.key || "").toLowerCase()
	if ((e.ctrlKey || e.metaKey) && key === "s") {
		e.preventDefault()
		if (readonly.value || saving.value || loading.value) return
		onSave()
	}
}
onMounted(() => {
	window.addEventListener("beforeunload", beforeUnloadGuard)
	window.addEventListener("keydown", onKeydown)
})
onBeforeUnmount(() => {
	window.removeEventListener("beforeunload", beforeUnloadGuard)
	window.removeEventListener("keydown", onKeydown)
})
onBeforeRouteLeave((to, from, next) => {
	if (isDirty.value && !readonly.value) {
		confirm.require({
			header: "Discard unsaved changes?",
			message: "You have unsaved changes to this matrix. Leave without saving?",
			icon: "pi pi-exclamation-triangle",
			acceptLabel: "Leave",
			acceptClass: "p-button-danger",
			rejectLabel: "Stay",
			accept: () => { isDirty.value = false; next() },
			reject: () => next(false),
		})
	} else next()
})

// React to query changes in create mode (router keys on path, so ?ipd= changes
// do NOT remount — re-seed when they change while still on /new).
watch(
	() => [route.query.ipd, route.query.process],
	() => {
		if (isCreate.value) load()
	},
)

// ════════════════ ATTRIBUTE EDITING ════════════════
function addInputAttr(e) {
	const v = e?.value || newInputAttr.value
	newInputAttr.value = null
	if (!v) return
	if (dependentAttribute.value && v === dependentAttribute.value) {
		toast.warn("Not allowed", `${v} is the IPD's dependent attribute — the engine stamps it; it can't be a matrix column.`)
		return
	}
	if (inputAttributes.value.includes(v)) return
	inputAttributes.value.push(v)
	// Add the new attr key to every existing input row.
	for (const g of groups.value) for (const row of g.inputs) row.attrs[v] = row.attrs[v] || null
	reloadAttributeValues()
}
function removeInputAttr(a) {
	inputAttributes.value = inputAttributes.value.filter((x) => x !== a)
	for (const g of groups.value) for (const row of g.inputs) delete row.attrs[a]
	delete attributeValuesInput[a]
}
function addOutputAttr(e) {
	const v = e?.value || newOutputAttr.value
	newOutputAttr.value = null
	if (!v) return
	if (dependentAttribute.value && v === dependentAttribute.value) {
		toast.warn("Not allowed", `${v} is the IPD's dependent attribute — the engine stamps it; it can't be a matrix column.`)
		return
	}
	if (outputAttributes.value.includes(v)) return
	outputAttributes.value.push(v)
	for (const g of groups.value) for (const row of g.outputs) row.attrs[v] = row.attrs[v] || null
	reloadAttributeValues()
}
function removeOutputAttr(a) {
	outputAttributes.value = outputAttributes.value.filter((x) => x !== a)
	for (const g of groups.value) for (const row of g.outputs) delete row.attrs[a]
	delete attributeValuesOutput[a]
}

// ════════════════ GROUPS / ROWS ════════════════
function addGroup() {
	const next = groups.value.reduce((m, g) => Math.max(m, g.group_index), 0) + 1
	groups.value.push({ group_index: next, group_name: "", inputs: [], outputs: [] })
}
function deleteGroup(gi) {
	groups.value.splice(gi, 1)
}
function addRow(group, side) {
	const arr = side === "Input" ? group.inputs : group.outputs
	const list = side === "Input" ? inputAttributes.value : outputAttributes.value
	const attrs = {}
	for (const a of list) attrs[a] = null
	const uom = (side === "Input" ? inputUom.value : outputUom.value) || ""
	arr.push({ qty: 0, uom, wastage_pct: 0, attrs })
}
function deleteRow(group, key, index) {
	group[key].splice(index, 1)
}

// ════════════════ GENERATE COMBINATIONS ════════════════
async function generateCombinations(opts = {}) {
	const silent = opts?.silent === true
	if (!header.ipd) {
		if (!silent) toast.warn("Set IPD first", "Pick an Item Production Detail before generating.")
		return
	}
	if (!inputAttributes.value.length && !outputAttributes.value.length) {
		if (!silent) toast.warn("Add attributes", "Add at least one input or output attribute to generate combinations.")
		return
	}
	generating.value = true
	try {
		const r = await callMethod("yrp.yrp.api.matrix.generate_cross_product", {
			ipd: header.ipd,
			input_attributes: inputAttributes.value,
			output_attributes: outputAttributes.value,
			input_item: header.input_item || null,
		})
		if (!r) return
		// Seed into group 0 (matches ipd_process_matrix.js generate path), creating
		// it if absent. New rows append to whatever's already there.
		let g0 = groups.value.find((g) => g.group_index === 0)
		if (!g0) {
			g0 = { group_index: 0, group_name: "", inputs: [], outputs: [] }
			groups.value.unshift(g0)
		}
		;(r.input || []).forEach((combo) => {
			const attrs = {}
			for (const a of inputAttributes.value) attrs[a] = null
			combo.attrs.forEach((a) => {
				if (a.attribute in attrs) attrs[a.attribute] = a.attribute_value
			})
			g0.inputs.push({ qty: 0, uom: inputUom.value || "", wastage_pct: 0, attrs })
		})
		;(r.output || []).forEach((combo) => {
			const attrs = {}
			for (const a of outputAttributes.value) attrs[a] = null
			combo.attrs.forEach((a) => {
				if (a.attribute in attrs) attrs[a.attribute] = a.attribute_value
			})
			g0.outputs.push({ qty: 0, uom: outputUom.value || "", wastage_pct: 0, attrs })
		})
		groups.value.sort((a, b) => a.group_index - b.group_index)
		await reloadAttributeValues()
		if (!silent) {
			toast.success("Combinations generated", "Set quantities and assign group indices, then Save.")
		}
	} catch (e) {
		if (!silent) toast.error("Generate failed", e.message)
	} finally {
		generating.value = false
	}
}

// ════════════════ SAVE ════════════════
// Serialize groups → flat combinations + combination_attributes, mirroring
// EditProcessMatrix.syncBack(). The dependent attr is never in row.attrs (we
// stripped it from the columns), so it never reaches combination_attributes.
function serializeChildren() {
	const combinations = []
	const combination_attributes = []
	for (const g of groups.value) {
		const sides = [["Input", g.inputs], ["Output", g.outputs]]
		for (const [side, arr] of sides) {
			arr.forEach((row, idx) => {
				const ci = idx + 1
				combinations.push({
					group_index: g.group_index,
					group_name: g.group_name || null,
					side,
					combo_index: ci,
					quantity: row.qty || 0,
					uom: row.uom || null,
					wastage_pct: row.wastage_pct || 0,
				})
				for (const [attr, val] of Object.entries(row.attrs || {})) {
					if (!val) continue
					combination_attributes.push({
						group_index: g.group_index,
						side,
						combo_index: ci,
						attribute: attr,
						attribute_value: val,
					})
				}
			})
		}
	}
	return { combinations, combination_attributes }
}

function buildPayload() {
	const { combinations, combination_attributes } = serializeChildren()
	return {
		ipd: header.ipd || null,
		process_name: header.process_name || null,
		reference_item_variant: header.reference_item_variant || null,
		input_item: header.input_item || null,
		output_item: header.output_item || null,
		// IPD Matrix Attribute children — flat {attribute} rows.
		input_attributes: inputAttributes.value.map((a) => ({ attribute: a })),
		output_attributes: outputAttributes.value.map((a) => ({ attribute: a })),
		combinations,
		combination_attributes,
	}
}

async function onSave() {
	if (!header.ipd) {
		toast.warn("Missing IPD", "IPD is required.")
		return
	}
	if (!header.process_name) {
		toast.warn("Missing Process", "Process is required.")
		return
	}
	const payload = buildPayload()
	try {
		if (isCreate.value) {
			const result = await docState.save(payload)
			const newName = result?.name
			isDirty.value = false // clear before navigating so the leave-guard stays silent
			toast.success("Created", newName ? `Matrix ${newName} created` : "Matrix created")
			if (newName) {
				// Different path → AppLayout remounts → loads saved doc cleanly.
				router.replace(`/ipd-process-matrix/${encodeURIComponent(newName)}`)
			}
		} else {
			await docState.save(payload, props.id)
			toast.success("Saved", `${props.id} updated`)
			await load()
		}
	} catch (e) {
		toast.error("Save failed", e.message)
	}
}

// ════════════════ AUTOCOMPLETE QUERIES ════════════════
async function searchIpd(e) {
	ipdSuggestions.value = await searchNames("Item Production Detail", e.query)
}
async function searchProcess(e) {
	processSuggestions.value = await searchNames("Process", e.query)
}
async function searchAttribute(e) {
	let names = await searchNames("Item Attribute", e.query)
	// Hide the dependent attribute from the picker entirely (RISK FLAG 2).
	if (dependentAttribute.value) names = names.filter((n) => n !== dependentAttribute.value)
	attrSuggestions.value = names
}
// Item Variant search filtered to the IPD's item (the reference variant must
// belong to the matrix's IPD item). Returns rows for LinkField's searchHandler
// (signature: async (query) => Array<{name}>).
async function searchVariantHandler(query) {
	try {
		let filters = {}
		if (header.ipd) {
			const r = await callMethod("frappe.client.get_value", {
				doctype: "Item Production Detail",
				filters: { name: header.ipd },
				fieldname: "item",
			})
			if (r?.item) filters = { item: r.item }
		}
		const rows = await callMethod("frappe.client.get_list", {
			doctype: "Item Variant",
			filters: { ...filters, name: ["like", `%${query || ""}%`] },
			fields: ["name"],
			limit_page_length: 20,
			order_by: "name asc",
		})
		return rows || []
	} catch (_) {
		return []
	}
}

async function searchNames(doctype, txt) {
	try {
		const rows = await searchLink(doctype, txt || "")
		return rows.map((r) => r.name)
	} catch (_) {
		return []
	}
}

// ── header reactions ──
async function onIpdChanged() {
	await fetchDependentAttribute()
	// Re-strip in case the dependent attr is already in the lists.
	inputAttributes.value = stripDependent(inputAttributes.value)
	outputAttributes.value = stripDependent(outputAttributes.value)
	await reloadAttributeValues()
	await refreshSideUoms()
}
function onIpdMaybeCleared(e) {
	// AutoComplete @change fires on free-text/clear. If emptied, reset dep attr.
	if (!header.ipd) dependentAttribute.value = null
}
// ── UOM auto-fill (input rows ← input_item ‖ IPD item; output rows ← output_item
//    ‖ IPD item). Mirrors the IPD Item BOM row, where uom = item.default_unit_of_measure.
async function fetchItemUom(itemName) {
	if (!itemName) return ""
	try {
		const r = await callMethod("frappe.client.get_value", {
			doctype: "Item",
			filters: { name: itemName },
			fieldname: "default_unit_of_measure",
		})
		return r?.default_unit_of_measure || ""
	} catch (_) {
		return ""
	}
}
async function ipdItemName() {
	if (!header.ipd) return ""
	try {
		const r = await callMethod("frappe.client.get_value", {
			doctype: "Item Production Detail",
			filters: { name: header.ipd },
			fieldname: "item",
		})
		return r?.item || ""
	} catch (_) {
		return ""
	}
}
// Resolve the default UOMs and backfill any EMPTY uom cells (never clobber a
// value the user typed). Called on load + whenever the IPD / input / output item changes.
async function refreshSideUoms() {
	const ipdIt = await ipdItemName()
	const [iu, ou] = await Promise.all([
		fetchItemUom(header.input_item || ipdIt),
		fetchItemUom(header.output_item || ipdIt),
	])
	inputUom.value = iu
	outputUom.value = ou
	for (const g of groups.value) {
		for (const row of g.inputs) if (!row.uom) row.uom = inputUom.value
		for (const row of g.outputs) if (!row.uom) row.uom = outputUom.value
	}
}
async function onInputItemChanged() {
	await reloadAttributeValues()
	await refreshSideUoms()
}
async function onOutputItemChanged() {
	await refreshSideUoms()
}
function onInputItemMaybeCleared() {
	onInputItemChanged()
}

// ── navigation ──
function goHome() {
	router.push("/home")
}
function goIpd() {
	if (header.ipd) router.push(`/item-production-detail/${encodeURIComponent(header.ipd)}`)
}
function goMatrixList() {
	// IPD Process Matrix has no /web list (it's opened from an IPD's process row).
	// Strict no-Desk rule: don't redirect to /app/ipd-process-matrix — surface a
	// toast instead (mirrors BOMMappingEditor.goMappingList).
	toast.warn(
		"No /web list",
		"Process Matrices are opened from an IPD's process — use “Configure combinations” there.",
	)
}
</script>

<style scoped>
.matrix-editor {
	display: flex;
	flex-direction: column;
	gap: 14px;
}

/* Breadcrumb + header (mirror DocDetail) */
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
/* Q2: hero is the human descriptor; the matrix code drops to a small mono chip. */
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
.head-status {
	align-self: center;
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
/* Explanatory sub-label reads as lighter text on the band (it's prose, not a count). */
.panel-meta {
	margin-left: auto;
	max-width: 60%;
	font-size: 11.5px;
	color: var(--esd-muted);
	text-align: right;
}

/* Header grid */
.hdr-grid {
	display: grid;
	grid-template-columns: repeat(3, minmax(0, 1fr));
	gap: 16px 24px;
	padding: 16px;
}
@media (max-width: 800px) {
	.hdr-grid {
		grid-template-columns: 1fr;
	}
}
.fld-wrap {
	display: flex;
	flex-direction: column;
	gap: 5px;
	min-width: 0;
}
.fld-wrap label {
	font-size: 11.5px;
	letter-spacing: 0.04em;
	text-transform: uppercase;
	color: var(--esd-muted);
	font-weight: 600;
}
.fld-wrap .req {
	color: var(--esd-danger);
}
.fld-hint {
	font-size: 12px;
	color: var(--esd-muted);
}

/* Attribute pickers */
.attr-pickers {
	display: grid;
	grid-template-columns: 1fr 1fr;
	gap: 1px;
	background: var(--esd-line);
}
@media (max-width: 800px) {
	.attr-pickers {
		grid-template-columns: 1fr;
	}
}
.attr-col {
	background: var(--esd-card);
	padding: 14px 16px;
	display: flex;
	flex-direction: column;
	gap: 10px;
}
.input-col {
	border-top: 2px solid var(--esd-accent);
}
.output-col {
	border-top: 2px solid var(--esd-accent-700);
}
.attr-col-head {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: 10px;
	font-weight: 600;
	font-size: 13px;
	color: var(--esd-ink);
}
.attr-add {
	width: 170px;
}
.attr-chips {
	display: flex;
	flex-wrap: wrap;
	gap: 6px;
}
.chip-x {
	margin-left: 6px;
	cursor: pointer;
	font-size: 10px;
	opacity: 0.7;
}
.chip-x:hover {
	opacity: 1;
}
.muted-dash {
	color: var(--esd-muted-2);
	font-size: 12.5px;
}

/* Groups */
.groups-meta {
	font-size: 12.5px;
	color: var(--esd-muted);
	padding: 0 2px;
}
.group-panel {
	padding: 14px 16px;
}
.group-head {
	display: flex;
	align-items: center;
	gap: 12px;
	margin-bottom: 10px;
}
.group-tag {
	font-weight: 600;
	font-size: 13px;
	color: var(--esd-ink);
	background: var(--esd-slate-50);
	padding: 3px 10px;
	border-radius: 999px;
}
.group-name {
	flex: 1;
	max-width: 300px;
}
.side-block {
	margin-top: 10px;
	padding-left: 10px;
}
.input-side {
	border-left: 3px solid var(--esd-accent);
}
.output-side {
	border-left: 3px solid var(--esd-accent-700);
}
.side-heading {
	display: flex;
	align-items: center;
	justify-content: space-between;
	margin-bottom: 4px;
	font-weight: 600;
	font-size: 13px;
	color: var(--esd-ink-2);
}
.combo-dt {
	font-size: 13px;
}
.cell-select,
.cell-num,
.cell-text {
	width: 100%;
}
/* Table headers inherit the PART 1c slate band; only refine the type here. */
:deep(.combo-dt .p-datatable-thead > tr > th) {
	font-size: 11.5px;
	letter-spacing: 0.03em;
	text-transform: uppercase;
	padding: 6px 8px;
}
:deep(.combo-dt .p-datatable-tbody > tr > td) {
	padding: 5px 8px;
}
</style>
