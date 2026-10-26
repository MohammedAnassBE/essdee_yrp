<template>
    <div ref="root">
        <table v-if="items && Object.keys(items).length > 0" class="table table-sm table-bordered">
            <tr>
                <th> Process </th>
                <th> {{ stiching_attr }}</th>
                <th v-if="!panels_only"></th>
            </tr>
            <tr v-for="item in Object.keys(items)" :key="item">
                <td>{{item}}</td>
                <td>
                   <label style="display: flex; gap: 6px; align-items: center; margin: 0;" v-for="panel in row_panels(item)" :key="panel">
                        <input type="checkbox" :checked="items[item].includes(panel)" @change="toggle_panel(item, panel, $event.target.checked)">
                        <span>{{panel}}</span>
                   </label>
                </td>
                <td v-if="!panels_only">
                    <div class="cursor-pointer" @click="delete_item(item)"
					v-html="frappe.utils.icon('delete', 'md', 'mr-1')"></div>
                </td>
            </tr>
        </table>
        <div class="process-name col-md-5"></div>
        <div class="panel-checks row p-4" style="display: flex; gap: 10px"></div>
        <button v-if="show_button1 && !panels_only" class="btn btn-success" @click="create_inputs()"> Add Process</button>
        <button v-if="show_button2" class="btn btn-success" @click="add_process()">Add</button>
    </div>
</template>
<script setup>
import {ref, onMounted} from 'vue';

let show_button1 = ref(true)
let panels_only = ref(false)
let show_button2 = ref(false)
let root = ref(null)
let sample_doc = ref({})
let panels = ref([])
let stiching_attr = cur_frm.doc.stiching_attribute
let process = null
let selected_panels = ref([])
let items = ref({})
let panel_values = []

onMounted(()=> {
    if(cur_frm.stiching_attribute_mapping){
        frappe.call({
            method:"essdee_yrp.ipd_ui.get_attr_mapping_details",
            args : {
                mapping:cur_frm.stiching_attribute_mapping,
            },
            callback:function(r){
                panels.value = r.message
            }
        })
    }
})

function create_inputs(){
    show_button1.value = false
    show_button2.value = true
    let el = root.value
    $(el).find('.process-name').html("")
    process = frappe.ui.form.make_control({
        parent : $(el).find('.process-name'),
        df: {
            fieldtype: "Link",
            fieldname: "process_name",
            label: "Process",
            options: "YRP Process",
            onchange:()=>{
                let selected = process.get_value()
                if(selected && selected !== "" && selected !== null){
                    create_checks()
                }
                else{
                    $(el).find(".panel-checks").html("")
                }
            }
        },
        doc:sample_doc.value,
        render_input: true,
    })
}
function create_checks(){
    panel_values = []
    let el = root.value
    $(el).find(".panel-checks").html("")
    let keys = Object.keys(items.value)
    for(let i = 0 ; i < panels.value.length ; i++){
        let name = process.get_value()+""+panels.value[i]+""+i+""+new Date().getTime()
        name = name.replaceAll(" ","_")
        panel_values[i] = frappe.ui.form.make_control({
            parent:$(el).find(".panel-checks"),
            df: {
                fieldname: name,
                fieldtype: "Check",
                label:panels.value[i],
                onchange: ()=> {
                    let value = panel_values[i].get_value()
                    if(value){
                        let y = selected_panels.value.indexOf(panels.value[i])
                        if(y == -1){
                            selected_panels.value.push(panels.value[i])
                        }
                    }
                    else{
                        let idx = selected_panels.value.indexOf(panels.value[i])
                        let p = selected_panels.value
                        p.splice(idx,1)
                        selected_panels.value = p
                    }
                }
            },
            doc: sample_doc.value,
            render_input:true,
        })
        panel_values[i].set_value(1)
    }
}

function add_process(){
    cur_frm.dirty()
    let process_value = process.get_value()
    if(!process_value || process_value == "" || process_value == null){
        frappe.msgprint("Enter the process")
        return
    }
    if(!items.value){
        items.value = {}
    }
    items.value[process_value] = selected_panels.value
    show_button2.value = false
    show_button1.value = true
    process.set_value(null)
    let el = root.value
    $(el).find(".panel-checks").html("")
    $(el).find(".process-name").html("")
    selected_panels.value = []
    panel_values = []
}

function row_panels(item){
    const stored = (items.value[item] || []).filter((panel) => !panels.value.includes(panel))
    return [...panels.value, ...stored]
}

function toggle_panel(item, panel, checked){
    const current = items.value[item] || []
    items.value[item] = checked ? [...current, panel] : current.filter((value) => value !== panel)
    cur_frm.dirty()
}

function set_panels_only(value){
    panels_only.value = Boolean(value)
}

function get_items(){
    return items.value
}

function delete_item(process){
    let x = items.value
    delete x[process]
    items.value = x
}
function load_items(item){
    items.value = JSON.parse(item)
}
defineExpose({
    get_items,
    load_items,
    set_panels_only,
})
</script>
