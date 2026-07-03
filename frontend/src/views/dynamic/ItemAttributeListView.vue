<!--
  ItemAttributeListView — clean chip-based card grid + inline editor.

  /web port of Desk apps/yrp/yrp/public/js/components/AttributeList.vue,
  re-skinned per user feedback 2026-05-29:
    • Values render as accent-tinted rounded chips (no bullet list, no
      dashed dividers).
    • Per-card pencil → INLINE edit mode in the same card (no modal).
    • Edit mode: chips become removable (× per chip) and an input + Add
      button creates new values; Save / Cancel at the bottom of the card.
    • Save flow (no Desk redirect):
        1) ensure each new value has an `Item Attribute Value` doc
           (callMethod("frappe.client.insert") — duplicates are no-ops),
        2) update the `Item Item Attribute Mapping`'s `values` table via
           callMethod("frappe.client.save").
    • Strict harness rule: no /app/* link — restricted users must stay in
      /web (see conventions.md 2026-05-29).

  Data source: __onload.attr_list, populated by Item.onload server-side
  (Item._load_attribute_list). Each entry:
    { attr_name, attr_values: [{ attribute_value }, …], doctype,
      attr_values_link }   — attr_values_link is the mapping doc name.
-->
<template>
	<div class="item-attr-list">
		<div v-if="loading" class="state-block sm">
			<i class="pi pi-spin pi-spinner" /> <span>Loading…</span>
		</div>
		<div v-else-if="!attrList.length" class="empty-inline">
			No attributes configured yet.
		</div>
		<div v-else class="attr-grid">
			<div
				v-for="(attr, idx) in attrList"
				:key="attr.attr_name"
				class="attr-card"
				:class="{ editing: editingIdx === idx }"
			>
				<div class="attr-head">
					<span class="attr-title">{{ attr.attr_name }}</span>
					<Button
						v-if="editingIdx !== idx && attr.attr_values_link"
						icon="pi pi-pencil"
						text
						rounded
						size="small"
						class="attr-edit-btn"
						v-tooltip.top="'Edit values'"
						@click="enterEdit(idx, attr)"
					/>
				</div>

				<!-- VIEW: chips -->
				<div v-if="editingIdx !== idx" class="chip-row">
					<span
						v-for="v in attr.attr_values || []"
						:key="v.attribute_value"
						class="attr-chip"
					>{{ v.attribute_value }}</span>
					<span v-if="!(attr.attr_values || []).length" class="empty-inline sm">
						No values
					</span>
				</div>

				<!-- EDIT: removable chips + add new -->
				<template v-else>
					<div class="chip-row editing">
						<span
							v-for="(v, i) in draftValues"
							:key="'d-' + i"
							class="attr-chip removable"
						>
							{{ v }}
							<button
								class="chip-x"
								type="button"
								v-tooltip.top="'Remove'"
								@click="removeAt(i)"
							>×</button>
						</span>
						<span v-if="!draftValues.length" class="empty-inline sm">
							No values — add one below.
						</span>
					</div>
					<div class="add-row">
						<AutoComplete
							v-model="newValue"
							:suggestions="newValueSuggestions"
							@complete="onNewValueComplete(attr, $event)"
							@item-select="addValue"
							@keydown.enter="addValue"
							placeholder="Pick or type new value…"
							dropdown
							completeOnFocus
							class="add-input"
							fluid
						/>
						<Button
							label="Add"
							icon="pi pi-plus"
							size="small"
							severity="secondary"
							outlined
							:disabled="!String(newValue || '').trim()"
							@click="addValue"
						/>
					</div>
					<div class="edit-actions">
						<Button
							label="Cancel"
							icon="pi pi-times"
							size="small"
							severity="secondary"
							outlined
							:disabled="saving"
							@click="cancelEdit"
						/>
						<Button
							label="Save"
							icon="pi pi-check"
							size="small"
							:loading="saving"
							@click="onSave(attr)"
						/>
					</div>
				</template>
			</div>
		</div>
	</div>
</template>

<script setup>
import { ref, onMounted, watch } from "vue"
import Button from "primevue/button"
import InputText from "primevue/inputtext"
import AutoComplete from "primevue/autocomplete"
import Tooltip from "primevue/tooltip"
import { callMethod, getDocWithOnload, searchLink } from "@/api/client"
import { useAppToast } from "@/composables/useToast"

const vTooltip = Tooltip

const props = defineProps({
	itemName: { type: String, required: true },
	// Host DocType whose __onload.attr_list we read and whose mappings we write.
	// "Item" by default; "Item Master Template" shares the identical attr_list
	// onload contract, so the same editor serves both.
	doctype: { type: String, default: "Item" },
})

const toast = useAppToast()
const loading = ref(false)
const saving = ref(false)
const attrList = ref([])

// ── inline edit state (one card at a time) ──
const editingIdx = ref(-1)
const draftValues = ref([])
const newValue = ref("")
// AutoComplete suggestion buffer for the "New value" picker.
const newValueSuggestions = ref([])

// Filtered list of existing Item Attribute Values for this attribute, minus
// the ones already in the draft list. Free-text entry is still allowed —
// the AutoComplete leaves v-model = typed string when nothing matches.
async function onNewValueComplete(attr, e) {
	const q = e?.query || ""
	try {
		const rows = await searchLink("Item Attribute Value", q, {
			attribute_name: attr.attr_name,
		})
		newValueSuggestions.value = (rows || [])
			.map((r) => r.name)
			.filter((n) => !draftValues.value.includes(n))
	} catch (_) {
		newValueSuggestions.value = []
	}
}

onMounted(load)
watch(() => props.itemName, load)

async function load() {
	if (!props.itemName) return
	loading.value = true
	editingIdx.value = -1
	draftValues.value = []
	try {
		const doc = await getDocWithOnload(props.doctype, props.itemName)
		const arr = doc?.__onload?.attr_list
		attrList.value = Array.isArray(arr) ? arr : []
	} catch (e) {
		toast.error("Could not load attributes", e.message)
		attrList.value = []
	} finally {
		loading.value = false
	}
}

function enterEdit(idx, attr) {
	editingIdx.value = idx
	draftValues.value = (attr.attr_values || []).map((v) => v.attribute_value)
	newValue.value = ""
}

function cancelEdit() {
	editingIdx.value = -1
	draftValues.value = []
	newValue.value = ""
}

function addValue() {
	// `newValue` may be a string (typed) or — after AutoComplete @item-select
	// — a plain string of the picked name (PrimeVue auto-sets v-model). Coerce
	// defensively in case a future suggestions array changes shape to objects.
	const raw = newValue.value
	const v = (typeof raw === "string" ? raw : raw?.name || "").trim()
	if (!v) return
	if (draftValues.value.includes(v)) {
		toast.warn("Duplicate", `"${v}" already in the list.`)
		newValue.value = ""
		return
	}
	draftValues.value.push(v)
	newValue.value = ""
	newValueSuggestions.value = []
}

function removeAt(i) {
	draftValues.value.splice(i, 1)
}

async function onSave(attr) {
	if (!attr.attr_values_link) {
		toast.error("No mapping doc", "Cannot save — the attribute mapping is missing.")
		return
	}
	saving.value = true
	try {
		// Single server-side call: creates missing Item Attribute Value docs +
		// rewrites the mapping's child rows in one transaction. Avoids the
		// timestamp-race a multi-call frontend flow used to hit (each new
		// Attribute Value insert was bumping the parent's `modified` between
		// the last insert and the parent save).
		await callMethod("essdee_yrp.api.item_attribute.update_mapping_values", {
			mapping: attr.attr_values_link,
			attribute_name: attr.attr_name,
			values: draftValues.value,
		})
		toast.success("Saved", `${attr.attr_name} values updated`)
		await load()
	} catch (e) {
		toast.error("Save failed", e.message)
	} finally {
		saving.value = false
	}
}

defineExpose({ reload: load })
</script>

<style scoped>
.item-attr-list {
	display: flex;
	flex-direction: column;
	gap: 8px;
}
.attr-grid {
	display: grid;
	grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
	gap: 12px;
}
.attr-card {
	background: var(--esd-card);
	border: 1px solid var(--esd-line);
	border-radius: var(--radius);
	padding: 12px 14px;
	display: flex;
	flex-direction: column;
	gap: 10px;
	min-width: 0;
	transition: border-color 0.12s, box-shadow 0.12s;
}
.attr-card:hover {
	border-color: var(--esd-accent-50);
}
.attr-card.editing {
	border-color: var(--esd-accent);
	box-shadow: 0 0 0 3px var(--esd-accent-50);
}
.attr-head {
	display: flex;
	align-items: center;
	gap: 8px;
}
.attr-title {
	font-size: 11.5px;
	letter-spacing: 0.06em;
	text-transform: uppercase;
	color: var(--esd-muted);
	font-weight: 600;
	flex: 1;
	min-width: 0;
}
.attr-edit-btn {
	flex-shrink: 0;
	color: var(--esd-muted-2);
}
.attr-edit-btn:hover {
	color: var(--esd-accent-700);
}

/* Chips */
.chip-row {
	display: flex;
	flex-wrap: wrap;
	gap: 6px;
	align-items: center;
}
.attr-chip {
	display: inline-flex;
	align-items: center;
	gap: 4px;
	background: var(--esd-accent-50);
	color: var(--esd-accent-700);
	border-radius: 999px;
	font-size: 12.5px;
	font-weight: 500;
	padding: 4px 12px;
	line-height: 1.3;
	white-space: nowrap;
}
.attr-chip.removable {
	padding-right: 6px;
}
.chip-x {
	background: transparent;
	border: 0;
	color: var(--esd-accent-700);
	cursor: pointer;
	font-size: 15px;
	line-height: 1;
	padding: 0 4px;
	border-radius: 999px;
	opacity: 0.7;
}
.chip-x:hover {
	opacity: 1;
	background: var(--esd-accent);
	color: white;
}

/* Edit add-row */
.add-row {
	display: flex;
	gap: 6px;
	align-items: center;
}
.add-input {
	flex: 1;
	min-width: 0;
}

/* Edit actions */
.edit-actions {
	display: flex;
	gap: 8px;
	justify-content: flex-end;
}

.state-block.sm,
.empty-inline,
.empty-inline.sm {
	color: var(--esd-muted);
	font-size: 13px;
	padding: 6px 0;
}
.empty-inline.sm {
	padding: 2px 0;
	font-size: 12px;
}
</style>
