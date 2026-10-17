<template>
	<div :id="panelId" class="ipd-tab-panel" role="tabpanel" :aria-labelledby="labelledby" tabindex="0">
		<template v-for="(section, index) in tab.sections" :key="index">
			<section v-if="!section.visible || section.visible(doc, { isNew })" class="ipd-tab-section" :aria-labelledby="section.heading ? `${panelId}-${index}` : undefined">
				<h2 v-if="section.heading" :id="`${panelId}-${index}`" class="ipd-tab-heading">{{ section.heading }}</h2>
				<div v-nonempty-section>
					<div><slot :section="section" :readonly="readonly" /></div>
					<p hidden style="display: none" class="erp-help-text">No details to display.</p>
				</div>
			</section>
		</template>
	</div>
</template>

<script setup>
// Children can finish loading or change their rows without updating this panel.
// Observe their rendered content so every visible section retains an empty state.
const observers = new WeakMap()
const vNonemptySection = {
	mounted(element) {
		const refresh = () => {
			const content = element.firstElementChild
			const empty = element.lastElementChild
			const hasContent = Boolean((content.innerText ?? content.textContent).trim() || content.querySelector('input, button, select, textarea, table'))
			empty.hidden = hasContent
			// The shared help-text class sets display:block, overriding native hidden.
			empty.style.display = hasContent ? 'none' : ''
		}
		refresh()
		const observer = new MutationObserver(refresh)
		observer.observe(element.firstElementChild, { childList: true, characterData: true, subtree: true })
		observers.set(element, observer)
	},
	unmounted(element) { observers.get(element)?.disconnect(); observers.delete(element) },
}

defineProps({
	tab: { type: Object, required: true },
	doc: { type: Object, required: true },
	isNew: Boolean,
	readonly: Boolean,
	panelId: { type: String, required: true },
	labelledby: { type: String, required: true },
})
</script>
