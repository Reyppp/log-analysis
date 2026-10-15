// Run with Node.js: node tools/test_frontend.cjs
const {readFileSync}=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const html=readFileSync(require('node:path').join(__dirname,'../index.html'),'utf8');
const start=html.indexOf('function thicknessSummary('),end=html.indexOf('function renderOverview(',start);
const filter=html.slice(html.indexOf('function filteredLayerRows('),html.indexOf('function filteredMachineSegments('));
const context=vm.createContext({});
vm.runInContext(`let payload,viewState={scope:'monitor'};const inputs={'layer-min':{value:1},'layer-max':{value:5}}, choices={material:['H','L'],method:['Optical','Time']};const $=id=>inputs[id],num=Number,checked=name=>choices[name];${html.slice(start,end)}${filter}`,context);
vm.runInContext(`
const records=[{layer:1,material:'H',method:'Optical',phy_thick:10.125},{layer:2,material:'L',method:'Time',phy_thick:20.125},{layer:3,material:'H',method:'Optical',phy_thick:null},{layer:4,material:'L',method:'Time',phy_thick:0},{layer:5,material:'H',method:'Optical',phy_thick:5,layer_end:null}];
payload={summary:records,monitor_summary:records};
globalThis.result=thicknessSummary(rows());
globalThis.card=thicknessCard(rows());
choices.material=['H'];inputs['layer-min'].value=3;
globalThis.hOnly=thicknessSummary(rows());
viewState.scope='combined';globalThis.combined=thicknessSummary(rows());
choices.method=['Time'];globalThis.empty=rows().length;
globalThis.missing=thicknessSummary([{phy_thick:null},{},{phy_thick:''},{phy_thick:NaN},{phy_thick:Infinity}]);
`,context);
assert.equal(context.result.total,35.25);
assert.equal(context.result.valid,4);
assert.match(context.card,/H 15.13 nm（不完整）/);
assert.match(context.card,/L 20.13 nm/);
assert.match(context.card,/有效 4\/5 层/);
assert.equal(context.hOnly.total,5);
assert.equal(context.hOnly.valid,1);
assert.equal(context.combined.total,5);
assert.equal(context.empty,0);
assert.equal(context.missing.total,null);
assert.equal((html.match(/\$\{thicknessCard\(r\)\}/g)||[]).length,2);
new vm.Script(html.match(/<script>([\s\S]*?)<\/script>/)[1]);
console.log('Frontend thickness: totals, H/L, incomplete, pending layer, filters, modes, empty and syntax passed.');

// Presentation changes must preserve every record and leave analysis values untouched.
const ui=vm.createContext({});
const declarations=html.slice(html.indexOf('const $=id=>'),html.indexOf('const fmtSec='));
const tables=html.slice(html.indexOf('const TABLE_PAGE_SIZE='),html.indexOf('function toggleChartFocus('));
const validation=html.slice(html.indexOf('function layerRangeError('),html.indexOf('function updateFilterSummary('));
const format=html.slice(html.indexOf('function formatValue('),html.indexOf('class ApiError'));
vm.runInContext(`const FIELD_META={robust_z:{label:'稳健 Z 分数',digits:2}};
const viewState={scope:'monitor',active:'anomaly'},document={getElementById:()=>null};
${declarations}${format}${tables}${validation}`,ui);
vm.runInContext(`
const records=Array.from({length:546},(_,i)=>({layer:i+1,material:'H',robust_z:i}));
const before=JSON.stringify(records);
globalThis.everyPage=Array.from({length:5},(_,page)=>tablePage(records,page));
globalThis.last=tablePage(records,999);
globalThis.first=tablePage(records,-1);
globalThis.unchanged=before===JSON.stringify(records);
const anomalies=[{layer:3,material:'H',method:'OMS',metric:'power_mean',value:4,robust_z:4,level:'关注'},
 {layer:3,material:'H',method:'OMS',metric:'power_mean',value:4,robust_z:6,level:'重点复核'},
 {layer:3,material:'H',method:'OMS',metric:'current_mean',value:2,robust_z:3.8,level:'关注'},
 {layer:7,material:'L',method:'Timer',metric:'power_mean',value:3,robust_z:4,level:'关注'}];
const originals=JSON.stringify(anomalies);
globalThis.groups=groupAnomalyRows(anomalies);
globalThis.groupsUnchanged=originals===JSON.stringify(anomalies);
globalThis.tableMarkup=table(records,['layer','material','robust_z']);
globalThis.escaped=table([{layer:1,material:'<script>bad()</script>',robust_z:5.69564615374007e13}],['layer','material','robust_z']);
globalThis.hugeZ=formatValue('robust_z',5.69564615374007e13);
globalThis.regularZ=formatValue('robust_z',3.75);
globalThis.noLayer=table([{layer:null,material:'H'}],['layer','material']);
globalThis.errors=[layerRangeError(null,10,1,243),layerRangeError(1.5,10,1,243),
 layerRangeError(10,1,1,243),layerRangeError(1,244,1,243),layerRangeError(1,243,1,243)];
`,ui);
assert.deepEqual(Array.from(ui.everyPage,page=>page.records.length),[120,120,120,120,66]);
assert.equal(new Set(Array.from(ui.everyPage).flatMap(page=>Array.from(page.records,row=>row.layer))).size,546);
assert.equal(ui.last.current,4);
assert.equal(ui.first.current,0);
assert.equal(ui.unchanged,true);
assert.equal(ui.groups.length,2);
assert.equal(ui.groups[0].review_count,3);
assert.equal(ui.groups[0].review_metrics.length,2);
assert.equal(ui.groups[0].level,'重点复核');
assert.equal(ui.groups[0].value,4);
assert.equal(ui.groupsUnchanged,true);
assert.match(ui.tableMarkup,/共 546 条 · 当前 1–120 条 · 第 1\/5 页/);
assert.match(ui.tableMarkup,/data-open-layer="120"/);
assert.doesNotMatch(ui.tableMarkup,/data-open-layer="121"/);
assert.match(ui.escaped,/&lt;script&gt;bad\(\)&lt;\/script&gt;/);
assert.match(ui.escaped,/title="原始 Z 分数：56956461537400.7"/);
assert.equal(ui.hugeZ,'5.70e+13');
assert.equal(ui.regularZ,'3.75');
assert.doesNotMatch(ui.noLayer,/data-open-layer=/);
assert.ok(Array.from(ui.errors).slice(0,4).every(Boolean));
assert.equal(ui.errors[4],'');
console.log('Frontend UI: complete pagination, nonmutating layer groups, safe cells, raw Z values and layer validation passed.');
