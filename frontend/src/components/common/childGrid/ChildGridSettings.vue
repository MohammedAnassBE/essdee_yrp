<template>
	<Button icon="pi pi-cog" text rounded severity="secondary" size="small" class="child-grid-settings__trigger" :aria-label="`Configure ${title} columns`" :title="`Configure ${title} columns`" @mousedown.prevent @click="open" />
	<Dialog v-model:visible="visible" modal :header="`Configure Columns · ${title}`" class="erp-dialog--sm child-grid-settings">
		<Message v-if="error" severity="error" :closable="false">{{ error }}</Message>
		<p class="child-grid-settings__hint">Choose the columns to show, their order and their share of the table width. The last column takes the rest. Mandatory columns stay visible. Saved for you, also in Desk.</p>
		<ol class="child-grid-settings__list">
			<li v-for="(column, index) in draft" :key="column.key" :class="{ 'is-hidden': !column.visible }">
				<Checkbox v-model="column.visible" binary :input-id="`${idPrefix}-${column.key}`" :disabled="column.locked" />
				<label :for="`${idPrefix}-${column.key}`">{{ column.label }}<span v-if="column.locked" class="erp-required-mark" aria-hidden="true">*</span></label>
				<span v-if="column.key === widths.lastKey" class="child-grid-settings__auto" :aria-label="`${column.label} width, automatic`" title="The last column takes the remaining width">{{ widths.lastPercent }}% auto</span>
				<InputNumber v-else-if="column.visible" v-model="column.percent" @input="column.percent = $event.value" :min="MIN_PERCENT" :max="100" suffix="%" :use-grouping="false" :max-fraction-digits="0" :aria-label="`${column.label} width`" input-class="child-grid-settings__width" />
				<span v-else class="child-grid-settings__auto" aria-hidden="true">—</span>
				<Button icon="pi pi-arrow-up" text rounded size="small" severity="secondary" :disabled="index === 0" :aria-label="`Move ${column.label} up`" @click="move(index, -1)" />
				<Button icon="pi pi-arrow-down" text rounded size="small" severity="secondary" :disabled="index === draft.length - 1" :aria-label="`Move ${column.label} down`" @click="move(index, 1)" />
			</li>
		</ol>
		<p class="child-grid-settings__total" :class="{ 'is-error': widths.error }" role="status">
			<span>Total: {{ widths.error ? widths.others : 100 }}%</span>
			<Button label="Distribute evenly" text size="small" severity="secondary" @click="draft = distributeEvenly(draft)" />
		</p>
		<Message v-if="widths.error" severity="warn" :closable="false">{{ widths.error }}</Message>
		<template #footer>
			<Button label="Reset to Default" severity="secondary" outlined :loading="busy === 'reset'" :disabled="Boolean(busy)" @click="run('reset')" />
			<Button label="Cancel" severity="secondary" text :disabled="Boolean(busy)" @click="visible = false" />
			<Button label="Save Columns" icon="pi pi-check" :loading="busy === 'save'" :disabled="Boolean(busy) || Boolean(widths.error)" @click="run('save')" />
		</template>
	</Dialog>
</template>

<script setup>
import Button from "primevue/button"
import Checkbox from "primevue/checkbox"
import Dialog from "primevue/dialog"
import InputNumber from "primevue/inputnumber"
import Message from "primevue/message"
import { computed, ref, useId } from "vue"

import { MIN_PERCENT, columnDraft, distributeEvenly, draftPercents } from "./childGridColumns.js"

const props = defineProps({
	title: { type: String, default: "table" },
	columns: { type: Array, required: true },
	visibleColumns: { type: Array, required: true },
	save: { type: Function, required: true },
	reset: { type: Function, required: true },
})

const idPrefix = `grid-column-${useId()}`
const visible = ref(false)
const draft = ref([])
const busy = ref("")
const error = ref("")
const widths = computed(() => draftPercents(draft.value))

function open() {
	draft.value = columnDraft(props.columns, props.visibleColumns)
	error.value = ""
	visible.value = true
}

function move(index, step) {
	const next = [...draft.value]
	const [column] = next.splice(index, 1)
	next.splice(index + step, 0, column)
	draft.value = next
}

async function run(action) {
	busy.value = action
	error.value = ""
	try {
		await (action === "save" ? props.save(draft.value) : props.reset())
		visible.value = false
	} catch (reason) {
		error.value = reason.message || "Unable to save column settings."
	} finally {
		busy.value = ""
	}
}
</script>

<style scoped>
.child-grid-settings__hint { margin: 0 0 var(--erp-space-3); color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); }
.child-grid-settings__list { display: grid; gap: 4px; margin: 0; padding: 0; list-style: none; }
.child-grid-settings__list li { display: grid; grid-template-columns: auto minmax(0, 1fr) 110px auto auto; align-items: center; gap: 8px; padding: 4px 6px; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); background: var(--erp-surface); }
.child-grid-settings__list li.is-hidden label { color: var(--erp-text-muted); }
.child-grid-settings__list label { overflow: hidden; color: var(--erp-text); font-size: var(--erp-font-size-table); white-space: nowrap; text-overflow: ellipsis; }
.child-grid-settings__list :deep(.child-grid-settings__width) { width: 100%; height: var(--erp-control-height-compact); }
.child-grid-settings__auto { color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); text-align: right; }
.child-grid-settings__total { display: flex; align-items: center; justify-content: space-between; margin: var(--erp-space-3) 0 0; color: var(--erp-text); font-size: var(--erp-font-size-table); font-weight: 600; }
.child-grid-settings__total.is-error { color: var(--erp-danger); }
</style>
