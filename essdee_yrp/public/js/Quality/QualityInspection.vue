<template>
	<div>
		<h3>{{ __("Colours") }}</h3>
		<button
			v-if="docstatus === 0"
			type="button"
			class="btn btn-xs btn-default"
			style="margin-bottom: 10px"
			@click="toggle_colours"
		>
			{{ all_colours_selected ? __("Unselect All Colours") : __("Select All Colours") }}
		</button>
		<div class="quality-option-grid">
			<label v-for="colour in colours" :key="colour.colour" class="quality-option">
				<input
					type="checkbox"
					v-model="colour.selected"
					:disabled="docstatus !== 0"
					@change="make_dirty"
				/>
				{{ colour.colour }}
			</label>
		</div>

		<h3 style="margin-top: 15px">{{ __("Sizes") }}</h3>
		<button
			v-if="docstatus === 0"
			type="button"
			class="btn btn-xs btn-default"
			style="margin-bottom: 10px"
			@click="toggle_sizes"
		>
			{{ all_sizes_selected ? __("Unselect All Sizes") : __("Select All Sizes") }}
		</button>
		<div class="quality-option-grid">
			<label v-for="size in sizes" :key="size.size" class="quality-option">
				<input
					type="checkbox"
					v-model="size.selected"
					:disabled="docstatus !== 0"
					@change="make_dirty"
				/>
				{{ size.size }}
			</label>
		</div>
	</div>
</template>

<script setup>
import { computed, ref } from "vue";

const colours = ref([]);
const sizes = ref([]);
const docstatus = ref(0);

const all_colours_selected = computed(
	() => colours.value.length > 0 && colours.value.every((row) => row.selected),
);
const all_sizes_selected = computed(
	() => sizes.value.length > 0 && sizes.value.every((row) => row.selected),
);

function make_dirty() {
	if (window.cur_frm && !window.cur_frm.is_dirty()) {
		window.cur_frm.dirty();
	}
}

function toggle_colours() {
	const selected = !all_colours_selected.value;
	colours.value.forEach((row) => {
		row.selected = selected;
	});
	make_dirty();
}

function toggle_sizes() {
	const selected = !all_sizes_selected.value;
	sizes.value.forEach((row) => {
		row.selected = selected;
	});
	make_dirty();
}

function load_data(data = {}, status = 0) {
	colours.value = JSON.parse(JSON.stringify(data.colours || []));
	sizes.value = JSON.parse(JSON.stringify(data.sizes || []));
	docstatus.value = Number(status || 0);
}

function get_data() {
	return JSON.parse(
		JSON.stringify({ colours: colours.value, sizes: sizes.value }),
	);
}

defineExpose({ get_data, load_data });
</script>

<style scoped>
.quality-option-grid {
	display: grid;
	grid-template-columns: repeat(2, minmax(0, 1fr));
	gap: 6px 16px;
	margin-bottom: 10px;
}

.quality-option {
	display: flex;
	align-items: center;
	gap: 6px;
	font-weight: 400;
}
</style>
