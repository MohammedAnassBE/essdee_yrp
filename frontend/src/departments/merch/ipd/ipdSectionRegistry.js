import { defineAsyncComponent, markRaw } from "vue"

import IpdSectionPlaceholder from "./IpdSectionPlaceholder.vue"

export const SECTION_FILES = {
	item: "./sections/IpdItemSection.vue",
	attributes: "./sections/IpdAttributesSection.vue",
	packing: "./sections/IpdPackingSection.vue",
	set_item: "./sections/IpdSetItemSection.vue",
	stitching: "./sections/IpdStitchingSection.vue",
	cutting: "./sections/IpdCuttingSection.vue",
	accessories: "./sections/IpdAccessoriesSection.vue",
	processes: "./sections/IpdProcessesSection.vue",
	settings: "./sections/IpdSettingsSection.vue",
	yarn_ratio: "./cloth/IpdYarnRatioSection.vue",
	fabric_routes: "./cloth/IpdFabricRoutesSection.vue",
	fabric_processes: "./cloth/IpdFabricProcessesSection.vue",
	compacting: "./cloth/IpdCompactingSection.vue",
}

const loaders = import.meta.glob(["./sections/Ipd*Section.vue", "./cloth/Ipd*Section.vue"])
const cache = new Map()

export function sectionComponent(sectionKey) {
	if (!cache.has(sectionKey)) {
		const loader = loaders[SECTION_FILES[sectionKey]]
		cache.set(sectionKey, markRaw(loader ? defineAsyncComponent(loader) : IpdSectionPlaceholder))
	}
	return cache.get(sectionKey)
}

export function preloadSectionComponents(sectionKeys) {
	return Promise.allSettled([...new Set(sectionKeys)].map((key) => sectionComponent(key).__asyncLoader?.()))
}
