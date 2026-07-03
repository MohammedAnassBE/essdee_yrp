<!--
  ItemDependentAttributeEditor — /web port of the Desk Vue component
  apps/yrp/yrp/public/js/components/DependentAttribute.vue.

  When an Item has a `dependent_attribute` (e.g. Stage), this editor lets
  the user configure, per dependent-attribute VALUE (Cut / Piece / Pack):
    • UOM            (Link → UOM, one per stage)
    • Display Name   (Data,        one per stage)
    • Which of the item's OTHER attributes apply at this stage
                     (one Check per non-dependent attribute column)

  Data shape (server-side, exposed via __onload.dependent_attribute):
    { attribute: "Stage",
      attr_list: {
        "Cut":   { uom, name, attributes: ["Panel","Colour","Size"] },
        "Piece": { uom, name, attributes: ["Part","Colour","Size"] },
        "Pack":  { uom, name, attributes: ["Size"] },
      } }

  Save calls yrp.yrp.doctype.item.item.update_dependent_attribute_details
  with the FULL matrix; the server replaces the linked
  Item Dependent Attribute Mapping row by row.

  View mode: read-only table with ✅ markers in the attribute columns.
  Edit mode: UOM = LinkField, Display Name = InputText, attribute columns
             = ToggleSwitch.
-->
<template>
	<div class="item-dep-editor">
		<div v-if="loading" class="state-block sm">
			<i class="pi pi-spin pi-spinner" /> <span>Loading…</span>
		</div>
		<div v-else-if="!hasMatrix" class="empty-inline">
			This item has no dependent attribute configured yet.
		</div>
		<template v-else>
			<div class="dep-head">
				<div class="dep-title">
					Dependent attribute: <b>{{ dependentAttribute }}</b>
				</div>
				<div class="dep-actions">
					<Button
						v-if="!editMode && editable"
						label="Edit"
						icon="pi pi-pencil"
						size="small"
						outlined
						@click="enterEdit"
					/>
					<Button
						v-if="editMode"
						label="Discard"
						icon="pi pi-times"
						size="small"
						severity="secondary"
						outlined
						:disabled="saving"
						@click="discardEdit"
					/>
					<Button
						v-if="editMode"
						label="Save"
						icon="pi pi-check"
						size="small"
						:loading="saving"
						@click="onSave"
					/>
				</div>
			</div>

			<DataTable :value="rows" class="esd-table dep-dt" :rowHover="false" dataKey="value">
				<Column header="" :style="{ width: '120px' }">
					<template #body="{ data }">
						<strong>{{ data.value }}</strong>
					</template>
				</Column>
				<Column header="UOM" :style="{ minWidth: '180px' }">
					<template #body="{ data }">
						<LinkField
							v-if="editMode"
							:model-value="data.uom"
							@update:model-value="data.uom = $event"
							target-doctype="UOM"
						/>
						<span v-else>{{ data.uom || "—" }}</span>
					</template>
				</Column>
				<Column header="Display Name" :style="{ minWidth: '160px' }">
					<template #body="{ data }">
						<InputText
							v-if="editMode"
							v-model="data.name"
							class="fld"
						/>
						<span v-else>{{ data.name || "—" }}</span>
					</template>
				</Column>
				<Column
					v-for="attr in otherAttributes"
					:key="'col-' + attr"
					:header="attr"
					:style="{ width: '120px' }"
					bodyStyle="text-align:center"
				>
					<template #body="{ data }">
						<ToggleSwitch
							v-if="editMode"
							:modelValue="data.attributeSet.has(attr)"
							@update:modelValue="toggleAttribute(data, attr, $event)"
						/>
						<span v-else>
							<i v-if="data.attributeSet.has(attr)" class="pi pi-check txt-good" />
							<span v-else class="muted">—</span>
						</span>
					</template>
				</Column>
			</DataTable>
		</template>
	</div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from "vue"
import DataTable from "primevue/datatable"
import Column from "primevue/column"
import Button from "primevue/button"
import InputText from "primevue/inputtext"
import ToggleSwitch from "primevue/toggleswitch"
import { callMethod, getDocWithOnload } from "@/api/client"
import { useAppToast } from "@/composables/useToast"
import LinkField from "@/components/LinkField.vue"

const props = defineProps({
	itemName: { type: String, required: true },
	editable: { type: Boolean, default: false },
})
const emit = defineEmits(["saved"])

const toast = useAppToast()

// ── server snapshot ──
const loading = ref(false)
const saving = ref(false)
const dependentAttribute = ref("")
const dependentMapping = ref("")
const defaultUom = ref("")
// dependentAttrValues = ordered values of the dependent attribute (e.g. Cut/Piece/Pack)
const dependentAttrValues = ref([])
// otherAttributes = all attribute names except the dependent one
const otherAttributes = ref([])
// rows = reactive matrix rows; built on load + on edit-enter
const rows = ref([])
const editMode = ref(false)
// last persisted matrix kept as JSON for Discard.
let baseline = "[]"

const hasMatrix = computed(() => !!dependentAttribute.value && dependentAttrValues.value.length > 0)

onMounted(load)
watch(() => props.itemName, load)

async function load() {
	if (!props.itemName) return
	loading.value = true
	editMode.value = false
	try {
		const doc = await getDocWithOnload("Item", props.itemName)
		if (!doc) {
			dependentAttribute.value = ""
			dependentAttrValues.value = []
			rows.value = []
			return
		}
		dependentAttribute.value = doc.dependent_attribute || ""
		dependentMapping.value = doc.dependent_attribute_mapping || ""
		defaultUom.value = doc.default_unit_of_measure || ""

		const onload = doc.__onload || {}
		const attrList = Array.isArray(onload.attr_list) ? onload.attr_list : []
		const dep = onload.dependent_attribute || {}
		const dataMap = (dep && dep.attr_list) || {}

		// Other-attribute column order: every attr_list entry whose name isn't
		// the dependent one (mirrors the Desk `attributes` computed).
		const others = []
		let depValues = []
		for (const a of attrList) {
			if (a.attr_name === dependentAttribute.value) {
				depValues = (a.attr_values || []).map((v) => v.attribute_value)
			} else {
				others.push(a.attr_name)
			}
		}
		otherAttributes.value = others
		dependentAttrValues.value = depValues

		// Build rows: one per dependent-attribute value. Missing entries get
		// defaults (uom = item default_unit_of_measure, name = "", no attrs) —
		// matches the Desk's "create on the fly when the user opens the editor".
		rows.value = depValues.map((v) => {
			const e = dataMap[v] || {}
			return {
				value: v,
				uom: e.uom || defaultUom.value || "",
				name: e.name || "",
				attributeSet: new Set(Array.isArray(e.attributes) ? e.attributes : []),
			}
		})
		baseline = serializeRows(rows.value)
	} catch (e) {
		toast.error("Could not load dependent attribute", e.message)
	} finally {
		loading.value = false
	}
}

function serializeRows(arr) {
	return JSON.stringify(
		arr.map((r) => ({
			value: r.value,
			uom: r.uom,
			name: r.name,
			attributes: [...r.attributeSet].sort(),
		})),
	)
}

function enterEdit() {
	if (!props.editable) return
	baseline = serializeRows(rows.value)
	editMode.value = true
}

function discardEdit() {
	// Re-hydrate rows from the baseline snapshot.
	const snap = JSON.parse(baseline || "[]")
	rows.value = snap.map((r) => ({
		value: r.value,
		uom: r.uom,
		name: r.name,
		attributeSet: new Set(Array.isArray(r.attributes) ? r.attributes : []),
	}))
	editMode.value = false
}

function toggleAttribute(row, attr, on) {
	if (on) row.attributeSet.add(attr)
	else row.attributeSet.delete(attr)
}

async function onSave() {
	if (!dependentMapping.value) {
		toast.error(
			"No mapping doc",
			"Save the item once after setting Dependent Attribute so the mapping exists.",
		)
		return
	}
	// Build the payload shape the server expects:
	//   { attribute, attr_list: { <value>: { uom, name, attributes: [...] } } }
	const attrListOut = {}
	for (const r of rows.value) {
		attrListOut[r.value] = {
			uom: r.uom || "",
			name: r.name || "",
			attributes: [...r.attributeSet],
		}
	}
	const detail = {
		attribute: dependentAttribute.value,
		attr_list: attrListOut,
	}
	saving.value = true
	try {
		await callMethod("yrp.yrp.doctype.item.item.update_dependent_attribute_details", {
			dependent_attribute_mapping: dependentMapping.value,
			detail,
		})
		toast.success("Saved", "Dependent attribute details updated")
		editMode.value = false
		baseline = serializeRows(rows.value)
		emit("saved")
	} catch (e) {
		toast.error("Save failed", e.message)
	} finally {
		saving.value = false
	}
}

defineExpose({ reload: load })
</script>

<style scoped>
.item-dep-editor {
	display: flex;
	flex-direction: column;
	gap: 14px;
}
.dep-head {
	display: flex;
	align-items: center;
	gap: 12px;
}
.dep-title {
	font-size: 13px;
	color: var(--esd-ink);
}
.dep-actions {
	margin-left: auto;
	display: flex;
	gap: 8px;
}
.dep-dt {
	border: 1px solid var(--esd-line);
	border-radius: var(--radius-sm);
	overflow: hidden;
}
.dep-dt :deep(.p-datatable-tbody > tr > td) {
	padding: 8px 10px;
	vertical-align: middle;
}
.fld {
	width: 100%;
}
.txt-good {
	color: var(--esd-success);
}
.muted {
	color: var(--esd-muted-2);
}
.state-block.sm {
	display: flex;
	align-items: center;
	gap: 8px;
	font-size: 13px;
	color: var(--esd-muted);
	padding: 18px 0;
}
.empty-inline {
	color: var(--esd-muted);
	font-size: 13px;
	padding: 18px 2px;
}
</style>
