<template>
	<main class="administrator-page">
		<header class="administrator-page__header">
			<h1>Administrator</h1>
		</header>

		<section class="department-grid" aria-label="Department workspaces">
			<DepartmentCard
				v-for="department in departments"
				:key="department.key"
				:department="department"
			/>
		</section>
	</main>
</template>

<script setup>
import DepartmentCard from "./DepartmentCard.vue"
import { departments } from "../departments/registry.js"
</script>
