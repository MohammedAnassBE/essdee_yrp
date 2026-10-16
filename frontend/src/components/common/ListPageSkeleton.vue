<template>
	<div class="erp-list-page-skeleton" aria-hidden="true">
		<div class="erp-list-page-skeleton__head">
			<div class="erp-list-page-skeleton__identity">
				<span class="erp-skeleton erp-skeleton--line" />
				<span class="erp-skeleton erp-skeleton--title" />
				<span class="erp-skeleton erp-skeleton--line" />
			</div>
			<div class="erp-list-page-skeleton__actions">
				<span class="erp-skeleton erp-skeleton--input erp-list-page-skeleton__search" />
				<span v-for="button in 3" :key="button" class="erp-skeleton erp-skeleton--input" />
			</div>
		</div>
		<div class="erp-list-page-skeleton__tabs">
			<span v-for="tab in 3" :key="tab" class="erp-skeleton erp-skeleton--line" />
		</div>
		<div class="erp-skeleton-table erp-skeleton-table--responsive">
			<div class="erp-skeleton-table__header">
				<span v-for="column in 4" :key="column" class="erp-skeleton erp-skeleton--line" />
			</div>
			<div v-for="row in 8" :key="row" class="erp-skeleton-table__row">
				<span v-for="column in 4" :key="column" class="erp-skeleton erp-skeleton--line" />
			</div>
		</div>
	</div>
</template>
