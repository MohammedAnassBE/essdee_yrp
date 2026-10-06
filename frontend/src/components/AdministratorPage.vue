<template>
	<main class="administrator-page">
		<header class="administrator-page__header">
			<div class="administrator-page__intro">
				<p class="administrator-page__eyebrow">Operations command center</p>
				<h1>Good work starts here.</h1>
				<p class="administrator-page__description">
					Choose a department workspace to manage the day’s production, stock, and commercial flow.
				</p>
			</div>
			<p class="administrator-page__summary">
				<strong>{{ departments.length }}</strong> connected workspaces
			</p>
		</header>

		<section aria-labelledby="department-workspaces-title">
			<header class="administrator-page__section-header">
				<h2 id="department-workspaces-title">Department workspaces</h2>
			</header>
			<div class="department-grid">
				<DepartmentCard
					v-for="department in departments"
					:key="department.key"
					:department="department"
				/>
			</div>
		</section>
	</main>
</template>

<script setup>
import DepartmentCard from "./DepartmentCard.vue"
import { departments } from "../departments/registry.js"
</script>
