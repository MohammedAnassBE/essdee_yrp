<template>
	<div class="ipd-tabs">
		<div ref="bar" class="ipd-tabs__bar" role="tablist" :aria-label="label">
			<button
				v-for="tab in available" :id="tabId(tab.fieldname)" :key="tab.fieldname" type="button" role="tab"
				:aria-selected="active === tab.fieldname" :aria-controls="panelId(tab.fieldname)"
				:tabindex="focused === tab.fieldname ? 0 : -1" class="ipd-tabs__tab" :class="{ 'is-active': active === tab.fieldname }"
				@focus="focused = tab.fieldname" @click="select(tab.fieldname)" @keydown="onKeydown($event, tab.fieldname)"
			>{{ tab.label }}</button>
		</div>
		<slot name="before" />
		<KeepAlive>
			<IpdTabPanel v-if="current" :key="current.fieldname" :tab="current" :doc="doc" :is-new="isNew" :readonly="readonly" :panel-id="panelId(active)" :labelledby="tabId(active)">
				<template #default="scope"><slot v-bind="scope" /></template>
			</IpdTabPanel>
		</KeepAlive>
	</div>
</template>

<script setup>
import { computed, nextTick, ref, useId, watch } from 'vue'
import IpdTabPanel from './IpdTabPanel.vue'
import { resolveTab, visibleTabs } from './ipdTabs.js'

const props = defineProps({
	tabs: { type: Array, required: true },
	doc: { type: Object, required: true },
	isNew: Boolean,
	readonly: Boolean,
	modelValue: { type: String, default: '' },
	label: { type: String, default: 'Tabs' },
})
const emit = defineEmits(['update:modelValue', 'before-change'])
const id = useId()
const bar = ref(null)
const available = computed(() => visibleTabs(props.tabs, props.doc, { isNew: props.isNew }))
const active = computed(() => resolveTab(available.value, props.modelValue))
const current = computed(() => available.value.find((tab) => tab.fieldname === active.value))
const focused = ref(active.value)
const tabId = (key) => `${id}-tab-${key}`
const panelId = (key) => `${id}-panel-${key}`
function select(key) {
	if (key === active.value) return
	emit('before-change')
	emit('update:modelValue', key)
}
function onKeydown(event, key) {
	const keys = available.value.map((tab) => tab.fieldname)
	const index = keys.indexOf(key)
	let target
	if (event.key === 'ArrowRight') target = keys[(index + 1) % keys.length]
	else if (event.key === 'ArrowLeft') target = keys[(index - 1 + keys.length) % keys.length]
	else if (event.key === 'Home') target = keys[0]
	else if (event.key === 'End') target = keys.at(-1)
	else if (['Enter', ' '].includes(event.key)) { event.preventDefault(); select(key); return }
	else return
	event.preventDefault()
	focused.value = target
	document.getElementById(tabId(target))?.focus()
}
watch(active, async (key) => {
	focused.value = key
	await nextTick()
	const element = document.getElementById(tabId(key))
	if (element && bar.value) {
		const bounds = element.getBoundingClientRect()
		const viewport = bar.value.getBoundingClientRect()
		if (bounds.left < viewport.left) bar.value.scrollLeft += bounds.left - viewport.left
		else if (bounds.right > viewport.right) bar.value.scrollLeft += bounds.right - viewport.right
	}
}, { immediate: true })
</script>
