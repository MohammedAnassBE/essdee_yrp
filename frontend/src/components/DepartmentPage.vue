<template>
	<main
		class="department-page"
		:class="{
			'department-page--flat': flat,
			'department-page--full-width': fullWidth,
		}"
		:style="{ '--accent': accent }"
	>
		<RouterLink v-slot="{ navigate }" custom :to="backTo">
			<Button
				class="back-link"
				icon="pi pi-arrow-left"
				:label="backLabel"
				severity="secondary"
				text
				@click="navigate"
			/>
		</RouterLink>
		<Card
			class="department-page__panel"
			:class="{ 'department-page__panel--flat': flat }"
		>
			<template #content>
				<h1 v-if="showTitle">{{ title }}</h1>
				<div class="department-page__content">
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

defineProps({
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
		default: "Administrator",
	},
})
</script>
