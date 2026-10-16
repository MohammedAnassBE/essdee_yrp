<template>
	<div ref="root" class="ipd-layout">
		<IpdTabs :tabs="tabs" :doc="doc" :is-new="isNew" :readonly="readonly" :model-value="active" @before-change="finishCellEdit" @update:model-value="select">
			<template #before><slot name="before" /></template>
			<template #default="{ section }">
				<component v-for="part in section.parts" :is="sectionComponent(part.component)" :key="`${part.component}-${part.variant}`" :section-key="part.sectionKey" :part="part.variant" :data-ipd-part="part.variant" :readonly="readonly" />
			</template>
		</IpdTabs>
	</div>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { useToast } from 'primevue/usetoast'
import { useRoute, useRouter } from 'vue-router'
import { preserveListNavigationState } from '../../../router/listDocumentNavigation.js'
import { preloadSectionComponents, sectionComponent } from './ipdSectionRegistry.js'
import { preloadSectionKeys, problemNavigation as navigationForProblem, resolveTab, visibleTabs } from './ipdTabs.js'
import { focusElement, GRID_FOCUS_PART } from './ipdFocus.js'
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
const toast = useToast()
const root = ref(null)
const available = computed(() => visibleTabs(props.tabs, props.doc, { isNew: props.isNew }))
const active = computed(() => resolveTab(available.value, route.hash.slice(1)))
watch(() => preloadSectionKeys(props.tabs, props.doc), (keys) => { preloadSectionComponents(keys) }, { immediate: true })

function finishCellEdit() {
	const panel = root.value?.querySelector('[role="tabpanel"]')
	for (const grid of panel?.querySelectorAll('[role="grid"]') || []) grid.dispatchEvent(new Event('entry-grid-finish-edit'))
	if (panel?.contains(document.activeElement)) document.activeElement.blur()
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
function problemNavigation(problem) {
	return navigationForProblem(problem, props.tabs, props.doc, { isNew: props.isNew })
}
function reportProblem(message) {
	if (message) toast.add({ severity: 'warn', summary: 'Go to cell', detail: message, life: 6000 })
}
function focusProblemHeading(problem) {
	const panel = root.value?.querySelector('[role="tabpanel"]')
	const part = GRID_FOCUS_PART[problem.field]
	const section = [...(panel?.querySelectorAll('[data-ipd-section]') || [])]
		.find((element) => element.dataset.ipdSection === problem.section && (!part || element.dataset.ipdPart === part))
	return focusElement(section?.closest('.ipd-tab-section')?.querySelector('h2') || panel)
}
watch(active, (key, previous) => { if (key !== previous) finishCellEdit() })
watch(() => [active.value, route.hash], () => {
	if (route.hash !== `#${active.value}`) router.replace({ query: route.query, hash: `#${active.value}`, state: preserveListNavigationState() })
}, { immediate: true })
defineExpose({ jumpTo, focusPanel, problemNavigation, reportProblem, focusProblemHeading })
</script>
