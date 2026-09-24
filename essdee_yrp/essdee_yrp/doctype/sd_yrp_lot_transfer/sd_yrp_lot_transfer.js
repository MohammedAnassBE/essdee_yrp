frappe.ui.form.on('SD YRP Lot Transfer',{
 refresh(frm){
  frm.lotTransferApp?.unmount();
  frm.fields_dict.item_html.$wrapper.empty();
  frm.set_df_property('items','hidden',1);
  const {app,editor}=essdee_yrp.mount_lot_transfer(frm.fields_dict.item_html.wrapper,frm);
  frm.lotTransferApp=app;frm.lotTransferEditor=editor;
  editor.load(frm.doc.__onload?.item_details || []);
 },
 validate(frm){
  if(!frm.lotTransferEditor)return;
  frm.doc.item_details = JSON.stringify(frm.lotTransferEditor.get_items());
 }
});
