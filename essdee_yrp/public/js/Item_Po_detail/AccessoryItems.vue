<template>
    <div ref='root'>
        <table v-if="Object.keys(items).length > 0" class='table table-sm table-bordered'>
            <thead>
                <tr>
                    <th v-if="!read_only" style="width: 32px">
                        <input type="checkbox" data-row-select :checked="selection.isAllSelected.value" :indeterminate="selection.isPartlySelected.value" @change="selection.toggleAll($event.target.checked)">
                    </th>
                    <th>Acceesory</th>
                    <th v-if="is_set_item">Part</th>
                </tr>
            </thead>
            <tbody>
                <tr v-for="(item,val) in items" :key='val'>
                    <td v-if="!read_only">
                        <input type="checkbox" data-row-select tabindex="-1" :checked="selection.isSelected(val)" @change="selection.toggle(val, $event.target.checked)">
                    </td>
                    <td>{{val}}</td>
                    <td v-if="is_set_item">{{item}}</td>
                </tr>
            </tbody>
        </table>
        <SelectionFooter :count="selection.selected.value.length" @delete="selection.removeSelected(delete_item, () => !read_only)" />
        <div class="row" v-enter-submits="add_item">
            <div class="accessory-item col-md-5"></div>
            <div class="part-item col-md-5"></div>
        </div>
        <button class="btn btn-success" v-if="show_button2" @click="add_item()">Add Item</button>
        <span v-if="show_button2" class="pr-3"></span>
        <button class="btn btn-success" v-if="show_button2" @click="close()">Close</button>
        <button class="btn btn-success" v-if="show_button1" @click="create_inputs()">Add Accessory Item</button>
        <div class="pb-5"></div>
    </div>
</template>

<script setup>
import {ref, onMounted} from 'vue';
import { SelectionFooter, useRowSelection, vEnterSubmits } from "yrp/public/js/utils/entryGrid.js";
let root = ref(null)
let items = ref({})
let sample_doc = ref({})
let accessoy_item = null
let part = null
let cloth_types = null
let show_button1 = ref(true)
let show_button2 = ref(false)
let is_set_item = cur_frm.doc.is_set_item
const read_only = cur_frm.doc.docstatus > 0 || !cur_frm.has_perm("write") || (!cur_frm.is_new() && cur_frm.doc.approval_status === "Approved")
const selection = useRowSelection(() => read_only ? [] : Object.keys(items.value))

function create_inputs(){
    let el = root.value
    $(el).find(".accessory-item").html("")
    accessoy_item = frappe.ui.form.make_control({
        parent:$(el).find(".accessory-item"),
        df: {
            fieldname:'cloth_accessory',
            fieldtype:"Data",
            label:"Accessory",
            reqd:true,
        },
        doc: sample_doc.value,
        render_input: true,
    })
    show_button1.value = false
    show_button2.value = true
    if(is_set_item){
        $(el).find(".part-item").html("")
        part = frappe.ui.form.make_control({
            parent:$(el).find(".part-item"),
            df: {
                fieldname:'part',
				fieldtype:"Autocomplete",
				label:"Part",
				reqd:true,
				get_query(){
					return {
						query:'essdee_yrp.ipd_ui.search_attribute_detail_values',
						params: {
							'mapping': cur_frm.set_item_attr_map_value,
                        }
                    }
                }
            },
            doc: sample_doc.value,
            render_input: true,
        })
    }
}

function close(){
    let el = root.value
    $(el).find(".cloth-type").html("")
    $(el).find(".accessory-item").html("")
    $(el).find(".part-item").html("")
    accessoy_item.set_value(null)
    if(is_set_item){
        part.set_value(null)
    }
    show_button1.value = true
    show_button2.value = false
}

function delete_item(key){
    cur_frm.dirty()
    delete items.value[key]
}

function add_item(){
    let el = root.value
    let val = null
    if(is_set_item){
        val = part.get_value()
        if(val == null || val == "" || !val){
            frappe.msgprint(`Enter the ${cur_frm.doc.set_item_attribute} Value`)
            return
        }
        part.set_value(null)
    }
    let acc_name = accessoy_item.get_value()
    if(!acc_name || acc_name == "" || acc_name == null){
        frappe.msgprint("Enter the Value for Accessory")
        return
    }
    items.value[acc_name] = val
    accessoy_item.set_value(null)
    $(el).find(".cloth-type").html("")
    $(el).find(".accessory-item").html("")
    $(el).find(".part-item").html("")
    show_button1.value = true
    show_button2.value = false
    cur_frm.dirty()
}

function load_data(item){
    items.value = item
}

function get_items(){
    return items.value
}

onMounted(()=> {
    let attr_list = []
    for(let i = 0; i < cur_frm.doc.cloth_detail.length; i++){
        attr_list.push(cur_frm.doc.cloth_detail[i]['name1'])
    }
    cloth_types = attr_list
})

defineExpose({
    load_data,
    get_items,
})
</script>
