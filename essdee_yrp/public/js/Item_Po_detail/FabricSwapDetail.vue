<template>
	<div ref="root" class="fabric-swap-detail" :style="locked ? 'pointer-events:none;opacity:0.7' : ''">
		<div v-for="(group, gi) in groups" :key="group.key" class="fsw-card">
			<div class="fsw-card-head">
				<span class="fsw-card-title">
					{{ group.pin ? `${config.pin_label}: ${group.pin}` : `All ${config.pin_label}s` }}
				</span>
				<button v-if="!locked" class="btn btn-xs fsw-del" @click="remove_group(gi)">&times;</button>
			</div>
			<div v-for="(pair, pi) in group.pairs" :key="pair.key" class="fsw-pair">
				<div :class="input_class(pair.key, 'from')" class="fsw-input"></div>
				<span class="fsw-arrow">&rarr;</span>
				<div :class="input_class(pair.key, 'to')" class="fsw-input"></div>
				<button v-if="!locked" class="btn btn-xs fsw-del" @click="remove_pair(gi, pi)">&times;</button>
			</div>
			<button v-if="!locked" class="btn btn-xs btn-default fsw-add-pair" @click="add_pair(gi)">
				+ {{ __("Add mapping") }}
			</button>
		</div>
		<div v-if="!locked" class="fsw-add-row">
			<div class="fsw-add-pin"></div>
			<button v-if="!has_wildcard" class="btn btn-xs btn-default" @click="add_group('')">
				+ {{ __("All") }} {{ config.pin_label }}s
			</button>
		</div>
	</div>
</template>

<script setup>
import { ref, computed, nextTick } from "vue";

const root = ref(null);
const groups = ref([]);
const config = ref({ pin_label: "", value_label: "", pin_attribute: "", value_attribute: "" });
const locked = ref(false);
const sample_doc = ref({});
let on_change = null;
let key_counter = 0;
let add_pin_control = null;

const has_wildcard = computed(() => groups.value.some((g) => g.pin === ""));

function load_data(data, change_cb) {
	on_change = change_cb || null;
	config.value = {
		pin_label: data.pin_label,
		value_label: data.value_label,
		pin_attribute: data.pin_attribute,
		value_attribute: data.value_attribute,
	};
	locked.value = !!data.locked;
	groups.value = (data.groups || []).map((g) => ({
		pin: g.pin || "",
		key: ++key_counter,
		pairs: (g.pairs || []).map((p) => ({ from: p.from || "", to: p.to || "", key: ++key_counter })),
	}));
	if (!groups.value.length) {
		groups.value.push({ pin: "", key: ++key_counter, pairs: [{ from: "", to: "", key: ++key_counter }] });
	}
	nextTick(() => {
		mount_pair_inputs();
		mount_add_pin_control();
	});
}

function get_data() {
	const rows = [];
	groups.value.forEach((group) => {
		group.pairs.forEach((pair) => {
			if (!pair.from && !pair.to) return;
			rows.push({ pin: group.pin || null, from: pair.from || null, to: pair.to || null });
		});
	});
	return rows;
}

function emit_change() {
	if (on_change) on_change(get_data());
}

function input_class(pair_key, side) {
	return `fsw-slot-${pair_key}-${side}`;
}

function last_used_from() {
	for (let gi = groups.value.length - 1; gi >= 0; gi--) {
		const pairs = groups.value[gi].pairs;
		for (let pi = pairs.length - 1; pi >= 0; pi--) {
			if (pairs[pi].from) return pairs[pi].from;
		}
	}
	return "";
}

function add_pair(gi) {
	// Fast entry: repeat the widget's last used from-value as the default.
	const from = last_used_from();
	groups.value[gi].pairs.push({ from, to: "", key: ++key_counter });
	nextTick(() => {
		mount_pair_inputs();
		if (from) emit_change();
	});
}

function remove_pair(gi, pi) {
	const removed = groups.value[gi].pairs.splice(pi, 1)[0];
	// Removing an empty pair changes nothing stored — don't dirty the form.
	if (removed && (removed.from || removed.to)) emit_change();
}

function add_group(pin) {
	if (groups.value.some((g) => g.pin === pin)) {
		frappe.show_alert(__("A card for {0} already exists", [pin || __("All")]));
		return;
	}
	const from = last_used_from();
	groups.value.push({ pin, key: ++key_counter, pairs: [{ from, to: "", key: ++key_counter }] });
	nextTick(() => {
		mount_pair_inputs();
		if (from) emit_change();
	});
}

function remove_group(gi) {
	const removed = groups.value.splice(gi, 1)[0];
	// Removing a card with no stored values changes nothing — don't dirty.
	if (removed && removed.pairs.some((p) => p.from || p.to)) emit_change();
}

function make_link(parent_sel, value, attribute, placeholder, change_cb) {
	const parent = $(root.value).find(parent_sel);
	if (!parent.length || parent.children().length) return null;
	const input = frappe.ui.form.make_control({
		parent,
		df: {
			fieldtype: "Link",
			options: "Item Attribute Value",
			fieldname: parent_sel.replace(/\W/g, "_"),
			placeholder,
			get_query: () => ({ filters: { attribute_name: attribute } }),
		},
		doc: sample_doc.value,
		render_input: true,
		only_input: true,
	});
	// Wire the change handler only AFTER the initial (async, for Link) set
	// settles, so loading pre-existing values never marks the form dirty.
	// Locked widgets stay display-only: no change wiring at all.
	Promise.resolve(input.set_value(value)).then(() => {
		if (!locked.value) input.df.onchange = () => change_cb(input.get_value());
	});
	return input;
}

function mount_pair_inputs() {
	groups.value.forEach((group) => {
		group.pairs.forEach((pair) => {
			make_link(`.${input_class(pair.key, "from")}`, pair.from, config.value.value_attribute,
				`${__("From")} ${config.value.value_label}`, (value) => {
					pair.from = value || "";
					emit_change();
				});
			make_link(`.${input_class(pair.key, "to")}`, pair.to, config.value.value_attribute,
				`${__("To")} ${config.value.value_label}`, (value) => {
					pair.to = value || "";
					emit_change();
				});
		});
	});
}

function mount_add_pin_control() {
	const parent = $(root.value).find(".fsw-add-pin");
	if (!parent.length || parent.children().length) return;
	add_pin_control = frappe.ui.form.make_control({
		parent,
		df: {
			fieldtype: "Link",
			options: "Item Attribute Value",
			fieldname: "fsw_add_pin",
			placeholder: `${__("Add")} ${config.value.pin_label}...`,
			get_query: () => ({ filters: { attribute_name: config.value.pin_attribute } }),
			onchange: () => {
				const pin = add_pin_control.get_value();
				if (!pin) return;
				add_group(pin);
				add_pin_control.set_value("");
			},
		},
		doc: sample_doc.value,
		render_input: true,
		only_input: true,
	});
}

defineExpose({
	load_data,
	get_data,
});
</script>

<style scoped>
.fsw-card {
	border: 1px solid var(--border-color);
	border-radius: var(--border-radius-md, 8px);
	padding: 10px 12px;
	margin: 8px 0;
	background: var(--card-bg, var(--fg-color));
}
.fsw-card-head {
	display: flex;
	justify-content: space-between;
	align-items: center;
	margin-bottom: 6px;
}
.fsw-card-title {
	font-weight: 600;
}
.fsw-pair {
	display: flex;
	align-items: center;
	gap: 8px;
	margin: 4px 0;
}
.fsw-input {
	width: 180px;
}
.fsw-arrow {
	color: var(--text-muted);
}
.fsw-add-pair {
	margin-top: 4px;
}
.fsw-add-row {
	display: flex;
	align-items: center;
	gap: 8px;
	margin-top: 8px;
}
.fsw-add-pin {
	width: 180px;
}
.fsw-del {
	color: var(--text-muted);
}
</style>
