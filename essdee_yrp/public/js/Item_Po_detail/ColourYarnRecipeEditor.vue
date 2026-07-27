<template>
	<div ref="root" class="cyr-editor">
		<div class="cyr-help">
			{{ __("One card represents one finished cloth colour. Ratio % is that yarn's share of this colour's blend; this is the only yarn-ratio entry required, and each card must total exactly 100%.") }}
			{{ __("Maintain Dia and Colour conversions only in the Fabric Processes tab.") }}
		</div>

		<div v-if="!groups.length" class="cyr-empty">
			{{ __("No colour-wise yarn recipe maintained.") }}
		</div>

		<div v-for="(group, gi) in groups" :key="group.key" class="cyr-card">
			<div class="cyr-card-head">
				<div>
					<div class="cyr-label">{{ __("Finished Colour") }}</div>
					<div :class="`cyr-colour-${group.key}`" class="cyr-colour-control"></div>
				</div>
				<strong class="cyr-total" :class="{ invalid: !valid_total(group) }">
					{{ total(group) }}%
				</strong>
				<button
					v-if="!locked"
					type="button"
					class="btn btn-xs btn-default cyr-delete"
					:title="__('Remove finished-colour recipe')"
					@click="remove_group(gi)"
				>×</button>
			</div>

			<div class="cyr-yarn-head" aria-hidden="true">
				<span>{{ __("Yarn Item") }}</span>
				<span>{{ __("Blend Share %") }}</span>
				<span></span>
			</div>
			<div v-for="(yarn, yi) in group.yarns" :key="yarn.key" class="cyr-yarn-row">
				<div :class="`cyr-yarn-${yarn.key}`" class="cyr-yarn-control"></div>
				<input
					v-model.number="yarn.ratio"
					type="number"
					min="0"
					max="100"
					step="0.001"
					class="form-control cyr-ratio"
					:disabled="locked"
					@input="emit_change"
				/>
				<button
					v-if="!locked"
					type="button"
					class="btn btn-xs btn-default cyr-delete"
					:disabled="group.yarns.length === 1"
					@click="remove_yarn(gi, yi)"
				>×</button>
			</div>
			<button v-if="!locked" type="button" class="btn btn-xs btn-default cyr-add-yarn" @click="add_yarn(gi)">
				+ {{ __("Add Yarn") }}
			</button>
		</div>

		<button v-if="!locked" type="button" class="btn btn-sm btn-default cyr-add-colour" @click="add_group">
			+ {{ __("Add Finished Colour") }}
		</button>
		<div v-else class="cyr-locked">
			{{ __("This IPD is approved — colour-wise yarn recipes are read-only.") }}
		</div>
	</div>
</template>

<script setup>
import { nextTick, ref } from "vue";

const root = ref(null);
const groups = ref([]);
const locked = ref(false);
const cloth_item = ref("");
const sample_doc = ref({});
let key_counter = 0;
let on_change = null;

function load_data(data, change_cb) {
	on_change = change_cb || null;
	locked.value = !!data.locked;
	cloth_item.value = data.cloth_item || "";
	const by_colour = new Map();
	(data.rows || []).forEach((row) => {
		const colour = row.colour || "";
		if (!by_colour.has(colour)) {
			by_colour.set(colour, {
				key: ++key_counter,
				colour,
				yarns: [],
				routes: [],
				bulk_knitting_output_colour: "",
			});
		}
		by_colour.get(colour).yarns.push({
			key: ++key_counter,
			yarn_item: row.yarn_item || "",
			ratio: Number(row.ratio) || 0,
		});
	});
	(data.routes || []).forEach((row) => {
		const colour = row.finished_colour || "";
		if (!by_colour.has(colour)) return;
		by_colour.get(colour).routes.push({
			key: ++key_counter,
			finished_dia: row.finished_dia || "",
			knitting_output_dia: row.knitting_output_dia || "",
			knitting_output_colour: row.knitting_output_colour || "",
		});
	});
	by_colour.forEach((group) => {
		const colours = [...new Set(
			group.routes.map((route) => route.knitting_output_colour).filter(Boolean),
		)];
		group.bulk_knitting_output_colour = colours.length === 1 ? colours[0] : "";
	});
	groups.value = [...by_colour.values()];
	nextTick(mount_controls);
}

function get_data() {
	const rows = [];
	const routes = [];
	groups.value.forEach((group) => {
		group.yarns.forEach((yarn) => {
			rows.push({
				cloth_item: cloth_item.value,
				colour: group.colour || "",
				yarn_item: yarn.yarn_item || "",
				ratio: Number(yarn.ratio) || 0,
			});
		});
		group.routes.forEach((route) => {
			routes.push({
				finished_colour: group.colour || "",
				finished_dia: route.finished_dia || "",
				knitting_output_dia: route.knitting_output_dia || "",
				knitting_output_colour: route.knitting_output_colour || "",
			});
		});
	});
	return { rows, routes };
}

function emit_change() {
	if (on_change) on_change(get_data());
}

function total(group) {
	return Math.round(group.yarns.reduce((sum, row) => sum + (Number(row.ratio) || 0), 0) * 1000) / 1000;
}

function valid_total(group) {
	return Math.abs(total(group) - 100) <= 0.001;
}

function route_direct(group, route) {
	return Boolean(
		group.colour &&
		route.finished_dia &&
		route.knitting_output_colour === group.colour &&
		route.knitting_output_dia === route.finished_dia
	);
}

function route_label(group, route) {
	if (!group.colour || !route.finished_dia || !route.knitting_output_colour || !route.knitting_output_dia) {
		return __("Complete route");
	}
	if (route_direct(group, route)) return __("Direct to finished");
	const changes = [];
	if (route.knitting_output_colour !== group.colour) changes.push(__("Colour process"));
	if (route.knitting_output_dia !== route.finished_dia) changes.push(__("Dia process"));
	return changes.join(" + ");
}

function add_group() {
	if (groups.value.some((group) => !group.colour)) {
		frappe.show_alert({ message: __("Complete the blank finished-colour card first."), indicator: "orange" });
		return;
	}
	groups.value.push({
		key: ++key_counter,
		colour: "",
		yarns: [{ key: ++key_counter, yarn_item: "", ratio: 100 }],
		routes: [],
		bulk_knitting_output_colour: "",
	});
	nextTick(mount_controls);
}

function remove_group(index) {
	groups.value.splice(index, 1);
	emit_change();
}

function add_yarn(group_index) {
	const group = groups.value[group_index];
	const first = group.yarns[0];
	const split_evenly = group.yarns.length === 1 && Number(first.ratio) === 100;
	if (split_evenly) first.ratio = 50;
	group.yarns.push({
		key: ++key_counter,
		yarn_item: "",
		ratio: split_evenly ? 50 : 0,
	});
	emit_change();
	nextTick(mount_controls);
}

function remove_yarn(group_index, yarn_index) {
	const group = groups.value[group_index];
	if (group.yarns.length === 1) return;
	group.yarns.splice(yarn_index, 1);
	emit_change();
}

function add_route(group_index) {
	const group = groups.value[group_index];
	group.routes.push({
		key: ++key_counter,
		finished_dia: "",
		knitting_output_dia: "",
		knitting_output_colour: group.bulk_knitting_output_colour || group.colour || "",
	});
	nextTick(mount_controls);
}

function remove_route(group_index, route_index) {
	groups.value[group_index].routes.splice(route_index, 1);
	emit_change();
}

function apply_bulk_output_colour(group, value) {
	group.bulk_knitting_output_colour = value || "";
	if (!value) return;
	group.routes.forEach((route) => {
		route.knitting_output_colour = value;
		$(root.value).find(`.cyr-knit-colour-${route.key}`).empty();
	});
	$(root.value).find(`.cyr-bulk-colour-${group.key}`).empty();
	emit_change();
	nextTick(mount_controls);
}

function use_finished_colour(group) {
	if (group.colour) apply_bulk_output_colour(group, group.colour);
}

function make_link(parent_selector, value, options, filters, placeholder, change_cb) {
	const parent = $(root.value).find(parent_selector);
	if (!parent.length || parent.children().length) return;
	const control = frappe.ui.form.make_control({
		parent,
		df: {
			fieldtype: "Link",
			options,
			fieldname: parent_selector.replace(/\W/g, "_"),
			placeholder,
			get_query: () => ({ filters: filters || {} }),
		},
		doc: sample_doc.value,
		render_input: true,
		only_input: true,
	});
	Promise.resolve(control.set_value(value)).then(() => {
		if (locked.value) {
			control.df.read_only = 1;
			control.refresh();
			return;
		}
		control.df.onchange = () => change_cb(control.get_value());
	});
}

function mount_controls() {
	groups.value.forEach((group) => {
		make_link(
			`.cyr-colour-${group.key}`,
			group.colour,
			"Item Attribute Value",
			{ attribute_name: "Colour" },
			__("Select finished colour"),
			(value) => {
				group.colour = value || "";
				emit_change();
			},
		);
		group.yarns.forEach((yarn) => {
			make_link(
				`.cyr-yarn-${yarn.key}`,
				yarn.yarn_item,
				"Item",
				{ disabled: 0 },
				__("Select yarn item"),
				(value) => {
					yarn.yarn_item = value || "";
					emit_change();
				},
			);
		});
	});
}

defineExpose({
	load_data,
	get_data,
});
</script>

<style scoped>
.cyr-help {
	margin-bottom: 10px;
	padding: 9px 11px;
	border: 1px solid var(--border-color);
	border-radius: var(--border-radius-md, 8px);
	color: var(--text-muted);
	background: var(--subtle-fg);
	font-size: 12px;
	line-height: 1.45;
}
.cyr-card {
	margin: 9px 0;
	padding: 11px 12px;
	border: 1px solid var(--border-color);
	border-radius: var(--border-radius-md, 8px);
	background: var(--card-bg, var(--fg-color));
}
.cyr-card-head {
	display: grid;
	grid-template-columns: minmax(210px, 1fr) auto auto;
	gap: 10px;
	align-items: end;
	margin-bottom: 9px;
}
.cyr-label,
.cyr-yarn-head {
	color: var(--text-muted);
	font-size: 11px;
	font-weight: 600;
}
.cyr-total {
	align-self: center;
	color: var(--primary);
}
.cyr-route-count {
	align-self: center;
	padding: 4px 8px;
	border-radius: 999px;
	background: var(--subtle-fg);
	color: var(--text-muted);
	font-size: 11px;
	white-space: nowrap;
}
.cyr-total.invalid {
	color: var(--red-500);
}
.cyr-yarn-head,
.cyr-yarn-row {
	display: grid;
	grid-template-columns: minmax(220px, 1fr) 130px 32px;
	gap: 8px;
	align-items: center;
}
.cyr-yarn-head {
	padding: 0 2px 4px;
}
.cyr-yarn-row + .cyr-yarn-row {
	margin-top: 7px;
}
.cyr-ratio {
	height: 34px;
}
.cyr-delete {
	color: var(--text-muted);
}
.cyr-add-yarn,
.cyr-add-colour,
.cyr-add-route {
	margin-top: 8px;
}
.cyr-routes {
	margin-top: 12px;
	padding-top: 10px;
	border-top: 1px solid var(--border-color);
}
.cyr-bulk-output {
	display: grid;
	grid-template-columns: minmax(220px, 1fr) auto;
	gap: 8px;
	align-items: end;
	margin-bottom: 10px;
	padding: 9px;
	border-radius: var(--border-radius-sm, 6px);
	background: var(--subtle-fg);
}
.cyr-route-title {
	display: flex;
	align-items: baseline;
	justify-content: space-between;
	gap: 8px;
	margin-bottom: 7px;
}
.cyr-route-title span,
.cyr-route-empty {
	color: var(--text-muted);
	font-size: 11px;
}
.cyr-route-head,
.cyr-route-row {
	display: grid;
	grid-template-columns: minmax(135px, 0.8fr) minmax(145px, 0.9fr) minmax(180px, 1fr) minmax(110px, auto) 32px;
	gap: 8px;
	align-items: center;
}
.cyr-route-head {
	padding: 0 2px 4px;
	color: var(--text-muted);
	font-size: 11px;
	font-weight: 600;
}
.cyr-route-row + .cyr-route-row {
	margin-top: 7px;
}
.cyr-route-state {
	padding: 5px 7px;
	border-radius: 999px;
	background: var(--yellow-100);
	color: var(--yellow-700);
	font-size: 11px;
	text-align: center;
}
.cyr-route-state.direct {
	background: var(--green-100);
	color: var(--green-700);
}
.cyr-empty,
.cyr-locked {
	padding: 10px 2px;
	color: var(--text-muted);
	font-size: 12px;
}
@media (max-width: 700px) {
	.cyr-card-head {
		grid-template-columns: 1fr;
	}
	.cyr-total {
		justify-self: start;
	}
	.cyr-route-head {
		display: none;
	}
	.cyr-route-row {
		grid-template-columns: 1fr 1fr;
		padding: 8px;
		border: 1px solid var(--border-color);
		border-radius: var(--border-radius-sm, 6px);
	}
	.cyr-route-state {
		text-align: left;
	}
}
@media (max-width: 480px) {
	.cyr-yarn-head {
		display: none;
	}
	.cyr-yarn-row {
		grid-template-columns: minmax(0, 1fr) 88px 30px;
		gap: 4px;
	}
	.cyr-route-row {
		grid-template-columns: 1fr;
	}
}
</style>
