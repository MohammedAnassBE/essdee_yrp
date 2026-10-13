<template>
	<DepartmentPage title="Sales" :show-title="false" flat inline-navigation>
		<SalesLauncher />
	</DepartmentPage>
</template>

<script setup>
import DepartmentPage from "../components/DepartmentPage.vue"
import SalesLauncher from "./sales/SalesLauncher.vue"
</script>
