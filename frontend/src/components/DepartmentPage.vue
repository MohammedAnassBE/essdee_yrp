<template>
	<main
		class="department-page erp-page-shell"
		:class="{
			'department-page--flat': flat,
			'department-page--full-width': fullWidth,
			'department-page--inline-navigation': inlineNavigation,
		}"
		:style="{ '--accent': accent }"
	>
		<nav v-if="!inlineNavigation && !hideNavigation" class="department-page__nav erp-page-nav" :aria-label="`Back to ${backLabel}`">
			<RouterLink v-slot="{ navigate }" custom :to="backTo">
				<Button
					class="back-link"
					icon="pi pi-arrow-left"
					:label="backLabel"
					:aria-label="`Back to ${backLabel}`"
					severity="secondary"
					text
					@click="navigate"
				/>
			</RouterLink>
		</nav>
		<Card
			class="department-page__panel erp-page-surface"
			:class="{ 'department-page__panel--flat': flat }"
		>
			<template #content>
				<h1 v-if="showTitle">{{ title }}</h1>
				<div class="department-page__content" :class="{ 'department-page__content--inline-navigation': inlineNavigation }">
					<slot />
				</div>
			</template>
		</Card>
	</main>
</template>

<script setup>
import Button from "primevue/button"
import Card from "primevue/card"
import { RouterLink } from "vue-router"
import { computed, provide } from "vue"

import { pageNavigationKey } from "./navigation/pageNavigationContext.js"

const props = defineProps({
	accent: {
		type: String,
		required: true,
	},
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
})

provide(pageNavigationKey, {
	backTo: computed(() => props.backTo),
	backLabel: computed(() => props.backLabel),
	inline: computed(() => props.inlineNavigation),
})
</script>

<style scoped>
.department-page__content--inline-navigation {
	min-height: calc(100vh - var(--erp-shell-header-height) - 112px);
	min-height: calc(100dvh - var(--erp-shell-header-height) - 112px);
}
</style>
