<template>
	<div v-if="embedded" class="department-page-embedded"><slot /><DocumentActivity v-if="activityDoctype" :doctype="activityDoctype" :name="activityName" :record="activityRecord" /></div>
	<main
		v-else
		class="department-page erp-page-shell"
		:class="{
			'department-page--flat': flat,
			'department-page--full-width': fullWidth,
			'department-page--inline-navigation': isInline,
		}"
	>
		<nav v-if="!isInline && !hideNavigation && !isLockedExit(backTo)" class="department-page__nav erp-page-nav" :aria-label="`Back to ${backLabel}`">
			<BackLink :to="backTo" :label="backLabel" />
		</nav>
		<Card
			class="department-page__panel erp-page-surface"
			:class="{ 'department-page__panel--flat': flat }"
		>
			<template #content>
				<h1 v-if="showTitle">{{ title }}</h1>
				<div class="department-page__content" :class="{ 'department-page__content--inline-navigation': isInline }">
					<slot />
					<DocumentActivity v-if="activityDoctype" :doctype="activityDoctype" :name="activityName" :record="activityRecord" />
				</div>
			</template>
		</Card>
	</main>
</template>

<script setup>
import Card from "primevue/card"
import { computed, provide, ref } from "vue"

import DocumentActivity from "./documents/DocumentActivity.vue"
import BackLink from "./navigation/BackLink.vue"
import { pageNavigationKey } from "./navigation/pageNavigationContext.js"
import { isLockedExit } from "../router/departmentLock.js"

const props = defineProps({
	title: {
		type: String,
		required: true,
	},
	showTitle: {
		type: Boolean,
		default: true,
	},
	flat: {
		type: Boolean,
		default: false,
	},
	fullWidth: {
		type: Boolean,
		default: false,
	},
	backTo: {
		type: String,
		default: "/",
	},
	backLabel: {
		type: String,
		default: "Workspaces",
	},
	inlineNavigation: {
		type: Boolean,
		default: false,
	},
	hideNavigation: {
		type: Boolean,
		default: false,
	},
	embedded: { type: Boolean, default: false },
	activityDoctype: { type: String, default: "" },
	activityName: { type: String, default: "" },
	activityRecord: { type: Object, default: null },
})

// Pages whose content renders InlinePageNavigation (list and form title rows) get the back button beside their title.
const inlineClaims = ref(0)
const isInline = computed(() => !props.embedded && (props.inlineNavigation || (inlineClaims.value > 0 && !props.hideNavigation)))

provide(pageNavigationKey, {
	backTo: computed(() => props.backTo),
	backLabel: computed(() => props.backLabel),
	inline: isInline,
	claimInline: () => {
		inlineClaims.value += 1
		return () => { inlineClaims.value -= 1 }
	},
})
</script>

<style scoped>
.department-page-embedded { min-width: 0; }

.department-page__content--inline-navigation {
	min-height: calc(100vh - var(--erp-shell-header-height) - 112px);
	min-height: calc(100dvh - var(--erp-shell-header-height) - 112px);
}
</style>
