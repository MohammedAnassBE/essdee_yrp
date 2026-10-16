<template>
	<Dialog
		:visible="visible"
		modal
		class="erp-entity-dialog erp-dialog--md ipd-copy-dialog"
		header="New version from an existing IPD"
		:closable="!copying"
		:dismissable-mask="false"
		@show="onShow"
		@update:visible="emit('update:visible', $event)"
	>
		<form class="ipd-copy-dialog__body" @submit.prevent="submit">
			<div class="erp-field-grid">
				<LinkField
					v-model="sourceName"
					input-id="ipd-copy-source"
					label="Copy from *"
					doctype="YRP Item Production Detail"
					:show-open-button="false"
					:disabled="copying"
					:help-text="sourceHelp"
				/>
				<LinkField
					v-model="item"
					input-id="ipd-copy-item"
					label="For item *"
					doctype="Item"
					:filters="itemFilters"
					:show-open-button="false"
					:disabled="copying || !options"
					:help-text="item && options && item !== options.source.item ? 'The copy will be the first version for this item.' : ''"
				/>
				<div class="ipd-copy-dialog__field">
					<label class="erp-field-label" for="ipd-copy-tech-pack">Tech Pack Version<span class="erp-required-mark" aria-hidden="true">*</span></label>
					<InputText id="ipd-copy-tech-pack" v-model="techPack" fluid :invalid="attempted && !techPack.trim()" :disabled="copying" aria-required="true" />
					<small v-if="options" class="erp-help-text">Source: {{ options.source.tech_pack_version || "—" }}</small>
				</div>
				<div class="ipd-copy-dialog__field">
					<label class="erp-field-label" for="ipd-copy-pattern">Pattern Version<span class="erp-required-mark" aria-hidden="true">*</span></label>
					<InputText id="ipd-copy-pattern" v-model="pattern" fluid :invalid="attempted && !pattern.trim()" :disabled="copying" aria-required="true" />
					<small v-if="options" class="erp-help-text">Source: {{ options.source.pattern_version || "—" }}</small>
				</div>
			</div>
			<div v-if="loading" class="ipd-copy-dialog__loading" aria-label="Loading copy options">
				<Skeleton v-for="row in 4" :key="row" height="2.5rem" />
			</div>
			<fieldset v-else-if="options" class="ipd-copy-dialog__sections">
				<legend class="erp-field-label">Sections to copy</legend>
				<label v-for="section in options.sections" :key="section.key" class="ipd-copy-dialog__option" :class="{ 'is-locked': section.locked }">
					<Checkbox :model-value="selected.includes(section.key)" binary :disabled="section.locked || copying" :input-id="`ipd-copy-${section.key}`" @update:model-value="toggle(section.key, $event)" />
					<span>{{ tabLabel({ section: section.key }) }}<small v-if="section.locked"> · always copied</small></span>
					<small class="ipd-copy-dialog__meta">{{ selected.includes(section.key) ? section.meta : "start empty" }}</small>
				</label>
			</fieldset>
			<Message v-if="error || missingMessage" severity="error" size="small" :closable="false">{{ error || missingMessage }}</Message>
		</form>
		<template #footer>
			<Button label="Cancel" severity="secondary" text :disabled="copying" @click="emit('update:visible', false)" />
			<Button :label="createLabel" icon="pi pi-copy" :loading="copying" :disabled="!options || loading" @click="submit" />
		</template>
	</Dialog>
</template>

<script setup>
import Button from "primevue/button"
import Checkbox from "primevue/checkbox"
import Dialog from "primevue/dialog"
import InputText from "primevue/inputtext"
import Message from "primevue/message"
import Skeleton from "primevue/skeleton"
import { computed, ref, watch } from "vue"

import { copyIpd, getIpdCopyOptions, getIpdItemGroups } from "../../../api/merch.js"
import LinkField from "../../../components/common/LinkField.vue"
import { tabLabel } from "./ipdTabs.js"
import { copyDefaults, toggleCopySection } from "./ipdEditor.js"
import "./ipd.css"

const props = defineProps({
	visible: { type: Boolean, default: false },
	source: { type: String, default: "" },
})
const emit = defineEmits(["update:visible", "copied"])
const sourceName = ref("")
const item = ref("")
const techPack = ref("")
const pattern = ref("")
const options = ref(null)
const selected = ref([])
const itemGroups = ref([])
const loading = ref(false)
const copying = ref(false)
const attempted = ref(false)
const error = ref("")
let optionsSequence = 0

const itemFilters = computed(() => ({ has_variants: 1, disabled: 0, ...(itemGroups.value.length ? { item_group: ["in", itemGroups.value] } : {}) }))
const sourceHelp = computed(() => {
	const source = options.value?.source
	if (!source) return ""
	const lots = source.lot_count ? ` · used by ${source.lot_count} ${source.lot_count === 1 ? "lot" : "lots"}` : ""
	return `${source.approval_status || "Not Approved"} · version ${source.version}${lots}`
})
const missingMessage = computed(() => attempted.value && (!techPack.value.trim() || !pattern.value.trim() || !item.value) ? "Enter the item, Tech Pack Version and Pattern Version." : "")
const createLabel = computed(() => !options.value || (item.value && item.value !== options.value.source.item) ? "Create copy" : `Create version ${options.value.next_version}`)

function onShow() {
	attempted.value = false
	error.value = ""
	techPack.value = ""
	pattern.value = ""
	if (sourceName.value === props.source) loadOptions(props.source)
	sourceName.value = props.source
	if (!itemGroups.value.length) getIpdItemGroups().then((groups) => { itemGroups.value = groups || [] }).catch(() => {})
}
async function loadOptions(source) {
	const sequence = ++optionsSequence
	options.value = null
	if (!source) return
	loading.value = true
	error.value = ""
	try {
		const result = await getIpdCopyOptions(source)
		if (sequence !== optionsSequence) return
		options.value = result
		item.value = result.source.item
		selected.value = copyDefaults(result.sections)
	} catch (reason) {
		if (sequence === optionsSequence) error.value = reason?.message || "Unable to load this IPD."
	} finally {
		if (sequence === optionsSequence) loading.value = false
	}
}
function toggle(key, checked) {
	selected.value = toggleCopySection(selected.value, key, checked, options.value.sections)
}
async function submit() {
	attempted.value = true
	if (!options.value || copying.value) return
	if (missingMessage.value) return
	copying.value = true
	error.value = ""
	try {
		const result = await copyIpd(sourceName.value, {
			techPackVersion: techPack.value.trim(), patternVersion: pattern.value.trim(), sections: selected.value,
			item: item.value !== options.value.source.item ? item.value : null,
		})
		emit("copied", result.name)
		emit("update:visible", false)
	} catch (reason) {
		error.value = reason?.message || "Unable to copy this IPD."
	} finally {
		copying.value = false
	}
}

watch(sourceName, (source) => { if (props.visible) loadOptions(source) })
</script>
