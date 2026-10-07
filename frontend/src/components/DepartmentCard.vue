<template>
	<RouterLink class="department-card-link" :to="department.path">
		<Card class="department-card">
			<template #content>
				<div class="department-card__layout">
					<span class="department-card__mark" aria-hidden="true">{{ department.shortLabel }}</span>
					<span class="department-card__content">
						<strong>{{ department.label }}</strong>
					</span>
					<i class="pi pi-arrow-right department-card__arrow" aria-hidden="true"></i>
				</div>
			</template>
		</Card>
	</RouterLink>
</template>

<script setup>
import Card from "primevue/card"
import { RouterLink } from "vue-router"

defineProps({
	department: {
		type: Object,
		required: true,
	},
})
</script>
