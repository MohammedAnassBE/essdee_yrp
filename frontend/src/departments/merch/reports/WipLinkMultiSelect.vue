<template>
	<div ref="root" class="wip-links">
		<LinkField v-model="selected" :doctype="doctype" :label="label" :invalid="invalid" :show-open-button="false" :reset-version="resetVersion" @select="add" />
		<div v-if="modelValue.length" class="wip-links__chips" :aria-label="`Selected ${label}`">
			<span v-for="(name, index) in summary.visible" :key="name" class="wip-links__chip">
				<span class="wip-links__name" :title="name">{{ name }}</span>
				<button v-if="ordered && index" type="button" :aria-label="`Move ${name} earlier`" @click="move(index)">←</button>
				<button type="button" :aria-label="`Remove ${name}`" @click="remove(name)">×</button>
			</span>
		</div>
		<div v-if="modelValue.length" class="wip-links__summary">
			<span role="status">{{ countLabel }}</span>
			<button v-if="summary.hiddenCount" type="button" aria-haspopup="dialog" :aria-label="`Show all ${countLabel}`" @click="allVisible = true">+{{ summary.hiddenCount }} more</button>
			<button type="button" :aria-label="`Clear ${label}`" @click="clear">Clear</button>
		</div>
		<div ref="measurements" class="wip-links__measurements" aria-hidden="true" inert>
			<span v-for="(name, index) in modelValue.slice(0, 6)" :key="name" class="wip-links__chip">
				<span class="wip-links__name">{{ name }}</span>
				<span v-if="ordered && index" class="wip-links__measure-control">←</span>
				<span class="wip-links__measure-control">×</span>
			</span>
		</div>
		<Dialog v-model:visible="allVisible" modal :header="`Selected ${label} (${modelValue.length})`" :style="{ width: '32rem', maxWidth: 'calc(100vw - 24px)' }">
			<p class="wip-links__dialog-count">{{ countLabel }}</p>
			<ul class="wip-links__all">
				<li v-for="(name, index) in modelValue" :key="name">
					<span class="wip-links__full-name">{{ name }}</span>
					<Button v-if="ordered && index" type="button" icon="pi pi-arrow-up" :aria-label="`Move ${name} earlier`" severity="secondary" text @click="move(index)" />
					<Button type="button" icon="pi pi-times" :aria-label="`Remove ${name}`" severity="secondary" text @click="remove(name)" />
				</li>
			</ul>
			<template #footer>
				<Button type="button" label="Clear" :aria-label="`Clear ${label}`" severity="secondary" outlined @click="clear" />
				<Button type="button" label="Done" @click="allVisible = false" />
			</template>
		</Dialog>
	</div>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue"
import LinkField from "../../../components/common/LinkField.vue"
import { selectionSummary } from "./wipSelectionSummary.js"

const props = defineProps({
	modelValue: { type: Array, default: () => [] },
	doctype: { type: String, required: true },
	label: { type: String, required: true },
	invalid: { type: Boolean, default: false },
	ordered: { type: Boolean, default: false },
})
const emit = defineEmits(["update:modelValue"])
const selected = ref("")
const resetVersion = ref(0)
const root = ref(null)
const measurements = ref(null)
const chipWidths = ref([])
const availableWidth = ref(0)
const allVisible = ref(false)
const summary = computed(() => selectionSummary(props.modelValue, chipWidths.value, availableWidth.value))
const countLabel = computed(() => {
	const noun = props.label === "Processes" ? "process" : props.label.toLowerCase()
	return `${props.modelValue.length} ${noun}${props.modelValue.length === 1 ? "" : noun === "process" ? "es" : "s"}`
})
let resizeObserver
function measure() {
	availableWidth.value = root.value?.clientWidth || 0
	chipWidths.value = Array.from(measurements.value?.children || [], (chip) => chip.getBoundingClientRect().width)
}
onMounted(() => {
	resizeObserver = new ResizeObserver(measure)
	resizeObserver.observe(root.value)
	measure()
})
onBeforeUnmount(() => resizeObserver?.disconnect())
watch(() => props.modelValue, () => {
	if (!props.modelValue.length) allVisible.value = false
	measure()
}, { deep: true, flush: "post" })
function clear() { emit("update:modelValue", []); allVisible.value = false }
async function add({ name }) {
	emit("update:modelValue", [...new Set([...props.modelValue, name])])
	await nextTick()
	selected.value = ""
	resetVersion.value += 1
}
function remove(name) { emit("update:modelValue", props.modelValue.filter((value) => value !== name)) }
function move(index) {
	const values = [...props.modelValue]
	;[values[index - 1], values[index]] = [values[index], values[index - 1]]
	emit("update:modelValue", values)
}
</script>

<style scoped>
.wip-links { position: relative; min-width: 0; }
.wip-links__chips { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 6px; }
.wip-links__chip { box-sizing: border-box; display: inline-flex; align-items: center; gap: 5px; min-width: 0; max-width: 100%; padding: 3px 6px; background: var(--erp-surface-soft); border: 1px solid var(--erp-border); border-radius: 5px; font-size: var(--erp-font-size-caption); }
.wip-links__name { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.wip-links__chip button, .wip-links__measure-control { box-sizing: border-box; display: inline-flex; align-items: center; justify-content: center; flex: 0 0 24px; width: 24px; min-height: 28px; padding: 0; border: 0; background: transparent; color: inherit; font: inherit; }
.wip-links button { cursor: pointer; }
.wip-links__summary { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 10px; margin-top: 4px; font-size: var(--erp-font-size-caption); color: var(--erp-text-muted); }
.wip-links__summary button { min-height: 28px; padding: 0; border: 0; background: transparent; color: var(--erp-accent); font: inherit; text-decoration: underline; }
.wip-links__measurements { position: absolute; inset: 0 0 auto; height: 0; overflow: hidden; visibility: hidden; display: flex; flex-direction: column; align-items: flex-start; pointer-events: none; }
.wip-links__dialog-count { margin: 0 0 8px; color: var(--erp-text-muted); }
.wip-links__all { max-height: 55dvh; overflow-y: auto; overscroll-behavior: contain; list-style: none; margin: 0; padding: 0; }
.wip-links__all li { display: flex; align-items: center; gap: 5px; padding: 4px 0; border-bottom: 1px solid var(--erp-border); }
.wip-links__full-name { flex: 1; min-width: 0; overflow-wrap: anywhere; }
.wip-links__all :deep(.p-button) { flex-shrink: 0; }
</style>
