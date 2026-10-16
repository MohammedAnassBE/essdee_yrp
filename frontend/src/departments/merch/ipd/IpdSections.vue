<template>
	<div ref="root" class="ipd-layout">
		<IpdTabs :tabs="tabs" :doc="doc" :is-new="isNew" :readonly="readonly" :model-value="active" @before-change="finishCellEdit" @update:model-value="select">
			<template #before><slot name="before" /></template>
			<template #default="{ section }">
				<component v-for="part in section.parts" :is="sectionComponent(part.component)" :key="`${part.component}-${part.variant}`" :section-key="part.sectionKey" :part="part.variant" :readonly="readonly" />
			</template>
		</IpdTabs>
	</div>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { preserveListNavigationState } from '../../../router/listDocumentNavigation.js'
import { preloadSectionComponents, sectionComponent } from './ipdSectionRegistry.js'
import { preloadSectionKeys, resolveTab, visibleTabs } from './ipdTabs.js'
import IpdTabs from './IpdTabs.vue'

const props = defineProps({
	tabs: { type: Array, required: true },
	doc: { type: Object, required: true },
	isNew: Boolean,
	readonly: Boolean,
})
const emit = defineEmits(['leave-first-section'])
const route = useRoute()
const router = useRouter()
const root = ref(null)
const available = computed(() => visibleTabs(props.tabs, props.doc, { isNew: props.isNew }))
const active = computed(() => resolveTab(available.value, route.hash.slice(1)))
watch(() => preloadSectionKeys(props.tabs, props.doc), (keys) => { preloadSectionComponents(keys) }, { immediate: true })

function finishCellEdit() {
	const panel = root.value?.querySelector('[role="tabpanel"]')
	if (panel?.contains(document.activeElement)) document.activeElement.blur()
	for (const grid of panel?.querySelectorAll('[role="grid"]') || []) grid.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
}
async function jumpTo(key, { focus = true } = {}) {
	const target = resolveTab(available.value, key)
	if (target !== active.value) finishCellEdit()
	if (route.hash !== `#${target}`) await router.replace({ query: route.query, hash: `#${target}`, state: preserveListNavigationState() })
	const tab = available.value.find((entry) => entry.fieldname === target)
	const parts = (tab?.sections || []).filter((section) => !section.visible || section.visible(props.doc, { isNew: props.isNew })).flatMap((section) => section.parts)
	await Promise.all(parts.map((part) => sectionComponent(part.component).__asyncLoader?.()))
	await nextTick()
	await nextTick()
	if (focus) focusPanel()
}
async function select(key) {
	const leavingFirst = props.isNew && active.value === available.value[0]?.fieldname
	await jumpTo(key, { focus: false })
	root.value?.querySelector('[role="tab"][aria-selected="true"]')?.focus({ preventScroll: true })
	if (leavingFirst) emit('leave-first-section')
}
function focusPanel() {
	root.value?.querySelector('[role="tabpanel"]')?.focus({ preventScroll: true })
}
function focusFirstControl() {
	const panel = root.value?.querySelector('[role="tabpanel"]')
	for (const target of panel?.querySelectorAll('input:not(:disabled), select:not(:disabled), button:not(:disabled), td[data-row][data-col], [id^="ipd-edit-"][tabindex]') || []) {
		target.focus({ preventScroll: true })
		if (document.activeElement !== target) continue
		target.scrollIntoView({ block: 'nearest', inline: 'nearest' })
		return true
	}
	return false
}
watch(active, (key, previous) => { if (key !== previous) finishCellEdit() })
watch(() => [active.value, route.hash], () => {
	if (route.hash !== `#${active.value}`) router.replace({ query: route.query, hash: `#${active.value}`, state: preserveListNavigationState() })
}, { immediate: true })
defineExpose({ jumpTo, focusPanel, focusFirstControl })
</script>
