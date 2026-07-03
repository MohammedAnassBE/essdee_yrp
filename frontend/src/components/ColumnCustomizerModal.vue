<!--
  ColumnCustomizerModal — per-user list columns (#2). Lets the user pick which
  columns show + reorder them; persists to the `User Listview` doctype (base yrp)
  via save_user_listview / reset_user_listview. Sort + saved filters are deferred.
-->
<template>
	<Dialog
		:visible="visible"
		modal
		header="Customize Columns"
		:style="{ width: '460px' }"
		@update:visible="$emit('update:visible', $event)"
	>
		<p class="cc-hint">Tick the columns to show; use the arrows to reorder them.</p>
		<div class="cc-list">
			<div v-for="(col, i) in localCols" :key="col.fieldname" class="cc-row">
				<Checkbox v-model="col.enabled" :binary="true" :inputId="'cc-' + col.fieldname" />
				<label :for="'cc-' + col.fieldname" class="cc-label">{{ col.label }}</label>
				<span class="cc-type">{{ col.fieldtype }}</span>
				<div class="cc-move">
					<Button
						icon="pi pi-chevron-up"
						text
						rounded
						size="small"
						:disabled="i === 0"
						@click="move(i, -1)"
					/>
					<Button
						icon="pi pi-chevron-down"
						text
						rounded
						size="small"
						:disabled="i === localCols.length - 1"
						@click="move(i, 1)"
					/>
				</div>
			</div>
			<div v-if="!localCols.length" class="cc-empty">No customizable columns.</div>
		</div>
		<template #footer>
			<Button
				label="Reset to Default"
				severity="secondary"
				outlined
				size="small"
				:loading="saving"
				@click="resetColumns"
			/>
			<Button label="Save" icon="pi pi-check" size="small" :loading="saving" @click="saveColumns" />
		</template>
	</Dialog>
</template>

<script setup>
import { ref, watch } from "vue"
import Dialog from "primevue/dialog"
import Button from "primevue/button"
import Checkbox from "primevue/checkbox"
import { callMethod } from "@/api/client"
import { useAppToast } from "@/composables/useToast"

const props = defineProps({
	visible: { type: Boolean, default: false },
	doctype: { type: String, required: true },
	// [{ fieldname, label, fieldtype, enabled }] — every eligible field, ordered.
	columns: { type: Array, default: () => [] },
})
const emit = defineEmits(["update:visible", "saved"])
const toast = useAppToast()

const localCols = ref([])
const saving = ref(false)

// Rebuild the editable copy each time the modal opens.
watch(
	() => props.visible,
	(open) => {
		if (open) {
			localCols.value = props.columns.map((c) => ({
				fieldname: c.fieldname,
				label: c.label,
				fieldtype: c.fieldtype,
				enabled: !!c.enabled,
			}))
		}
	},
)

function move(i, dir) {
	const j = i + dir
	if (j < 0 || j >= localCols.value.length) return
	const arr = localCols.value
	const [item] = arr.splice(i, 1)
	arr.splice(j, 0, item)
}

async function saveColumns() {
	if (!props.doctype) return
	saving.value = true
	try {
		const columns = localCols.value.map((c) => ({
			fieldname: c.fieldname,
			enabled: c.enabled ? 1 : 0,
		}))
		await callMethod("yrp.yrp.doctype.user_listview.user_listview.save_user_listview", {
			doctype_name: props.doctype,
			columns: JSON.stringify(columns),
		})
		toast.success("Columns saved", "Your column layout was updated.")
		emit("update:visible", false)
		emit("saved")
	} catch (e) {
		toast.error("Save failed", e.message)
	} finally {
		saving.value = false
	}
}

async function resetColumns() {
	if (!props.doctype) return
	saving.value = true
	try {
		await callMethod("yrp.yrp.doctype.user_listview.user_listview.reset_user_listview", {
			doctype_name: props.doctype,
		})
		toast.success("Columns reset", "Reverted to the default columns.")
		emit("update:visible", false)
		emit("saved")
	} catch (e) {
		toast.error("Reset failed", e.message)
	} finally {
		saving.value = false
	}
}
</script>

<style scoped>
.cc-hint {
	font-size: 12px;
	color: var(--esd-muted);
	margin: 0 0 10px;
}
.cc-list {
	display: flex;
	flex-direction: column;
	gap: 2px;
	max-height: 420px;
	overflow-y: auto;
}
.cc-row {
	display: flex;
	align-items: center;
	gap: 10px;
	padding: 6px 8px;
	border-radius: var(--radius-sm);
}
.cc-row:hover {
	background: var(--esd-slate-50);
}
.cc-label {
	flex: 1;
	font-size: 13px;
	color: var(--esd-ink);
	cursor: pointer;
}
.cc-type {
	font-size: 10.5px;
	font-weight: 600;
	text-transform: uppercase;
	letter-spacing: 0.03em;
	color: var(--esd-muted);
	background: var(--esd-slate-50);
	padding: 1px 6px;
	border-radius: 6px;
}
.cc-move {
	display: flex;
}
.cc-empty {
	padding: 16px;
	text-align: center;
	color: var(--esd-muted);
	font-size: 13px;
}
</style>
