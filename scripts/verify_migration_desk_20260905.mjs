// Read-only record-aware checks for the 2026-09-05 migration rehearsal.
// Credentials are read locally; no saves, submissions or business writes.
import {createRequire} from 'node:module';
import {readFileSync,writeFileSync} from 'node:fs';
const require=createRequire('/home/anas/.claude/playwright/package.json');
const {chromium}=require('playwright');
const base='http://erp_now.site:8003';
const [usr,pwd]=readFileSync('/home/anas/.frappe-debug-creds-mrp3','utf8').trim().split('\n').map(x=>x.trim());
const browser=await chromium.launch();
const ctx=await browser.newContext({viewport:{width:1440,height:1000},deviceScaleFactor:1});
const errors=[];
const results=[];const requests=[];
try{
 const login=await ctx.request.post(base+'/api/method/login',{form:{usr,pwd}});
 if(!login.ok())throw Error('Login failed: HTTP '+login.status());
 const page=await ctx.newPage();
 page.on('response',async r=>{if(r.status()>=400){let error;try{const body=await r.json();error=body.exc_type+': '+(body.exception||'')}catch{}requests.push({status:r.status(),path:new URL(r.url()).pathname,error})}});
 page.on('pageerror',e=>errors.push(e.message));
 page.on('console',m=>{if(m.type()==='error')errors.push(m.text())});
 await page.goto(base+'/desk',{waitUntil:'domcontentloaded'});
 await page.waitForFunction(()=>window.frappe&&frappe.set_route,null,{timeout:60000});
 const records=[
  ['YRP Purchase Invoice','MPI-2627-00965','po-invoice'],
  ['YRP Purchase Invoice','MPI-2526-01765-1','wo-invoice'],
  ['YRP Bin','00753hkq3a','bin'],
  ['YRP Stock Reservation Entry','MRP-SRE-2026-122693','reservation'],
  ['YRP Supplier','PRIYA TAPES','supplier'],
  ['Address','PRIYA TAPES-Billing','address'],
  ['SD YRP MRP Data Migration','MRP-MIG-2026-00001','migration-status']
 ];
 for(const [doctype,name,slug] of records){
  await page.evaluate(([dt,n])=>frappe.set_route('Form',dt,n),[doctype,name]);
  await page.waitForFunction(([dt,n])=>window.cur_frm&&cur_frm.doctype===dt&&cur_frm.doc.name===n&&!cur_frm.__isloading,[doctype,name],{timeout:60000});
  await page.waitForTimeout(2500);
  const result=await page.evaluate(()=>{
   const f=cur_frm,d=f.doc;
   const r={doctype:f.doctype,name:d.name,dirty:Boolean(f.is_dirty())};
   if(f.doctype==='YRP Purchase Invoice'){
    Object.assign(r,{items:d.items?.length,essdee_items:d.essdee_items?.length,
      physical_types:[...new Set(d.items?.map(x=>x.doctype))],
      grouped_types:[...new Set(d.essdee_items?.map(x=>x.doctype))],
      physical_visible:f.fields_dict.items.$wrapper.is(':visible'),
      grouped_visible:f.fields_dict.essdee_items.$wrapper.is(':visible')});
    f.fields_dict.essdee_items.$wrapper[0].scrollIntoView({block:'center'});
   }else if(f.doctype==='YRP Bin'){
    Object.assign(r,{reserved_qty:d.reserved_qty,reserved_field_exists:Boolean(f.fields_dict.reserved_qty),reserved_field_hidden:f.fields_dict.reserved_qty.df.hidden});
   }else if(f.doctype==='Address'){
    r.link_doctypes=d.links.map(x=>x.link_doctype);
   }else if(f.doctype==='SD YRP MRP Data Migration'){
    r.status=d.status;
    const field=f.fields_dict.retired_source_rows_json;
    const display=field.disp_area[0]||field.disp_area;
    const literal='<style>@import url(/files/not-a-real-request.css)</style><img src=x onerror=alert(1)><script>alert(2)</script>';
    const formatted=frappe.format(literal,{fieldtype:'JSON'});
    Object.assign(r,{
      archive_markup_nodes:display.querySelectorAll('style,link,script,img,iframe').length,
      archive_text_exact:display.textContent===d.retired_source_rows_json,
      archive_css_reference_preserved:d.retired_source_rows_json.includes('ppo-dashboard-viewer-fullscreen-live-20260806.css'),
      json_formatter_registered:typeof frappe.form.formatters.JSON==='function',
      synthetic_markup_escaped:!/<(?:style|script|img|link)\b/i.test(formatted)&&formatted.includes('&lt;style&gt;'),
      session_defaults_ready:Array.isArray(frappe.boot.session_defaults)
    });
   }
   return r;
  });
  if(doctype==='YRP Purchase Invoice'&&(!result.items||!result.essdee_items||result.physical_visible||!result.grouped_visible))throw Error('Invoice dual-table/UI mismatch: '+JSON.stringify(result));
  if(doctype==='Address'&&!result.link_doctypes.includes('YRP Supplier'))throw Error('Address namespace missing');
  if(doctype==='SD YRP MRP Data Migration'&&(result.archive_markup_nodes||!result.archive_text_exact||!result.synthetic_markup_escaped||!result.session_defaults_ready))throw Error('Inert archive display failed: '+JSON.stringify(result));
  if(result.dirty)throw Error('Record became dirty on read: '+doctype+' '+name);
  const shot='/home/anas/frappe-16/screenshots/migration-final-20260905-'+slug+'.png';
  await page.screenshot({path:shot});
  results.push({...result,screenshot:shot});
 }
 const route=page.url();
 await page.waitForTimeout(5000);
 if(page.url()!==route||route.includes('setup-wizard'))throw Error('Desk route is unstable');
 const evidence={checked_on:new Date().toISOString(),site:base,records:results,console_errors:errors,failed_requests:requests,route_stable:true};
 writeFileSync('/home/anas/frappe-16/docs/production-api-desk-verification-20260905.json',JSON.stringify(evidence,null,2)+'\n');
 console.log(JSON.stringify(evidence,null,2));
 if(requests.length)throw Error('Failed HTTP requests occurred');
 if(errors.length)throw Error('Console errors occurred');
}finally{await ctx.close();await browser.close()}
