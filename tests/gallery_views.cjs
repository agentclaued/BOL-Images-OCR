// Execute the generated gallery's real view handlers with a small DOM fixture.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
class Element {
  constructor(tag='div') { this.tag=tag; this.children=[]; this._value=''; this.checked=false; this.textContent=''; this.classList={toggle(){}}; }
  set innerHTML(value) { this.children=[]; this._value=''; }
  get value() { return this._value; }
  set value(value) { this._value=this.tag==='select'&&!this.children.some(c=>c.value===value)?'':value; }
  append(...items) { this.children.push(...items); }
  replaceChildren(...items) { this.children=items; }
  addEventListener() {}
}
const elements=new Map();
const document={
  querySelector(id){ if(!elements.has(id))elements.set(id,new Element(['#viewBy','#pdfFilter','#statusFilter'].includes(id)?'select':'div'));return elements.get(id); },
  querySelectorAll(){return [];},
  createElement(tag){return new Element(tag);},
  createTextNode(text){return {textContent:text};}
};
for(const value of ['all','pdf','date']){const option=new Element('option');option.value=value;document.querySelector('#viewBy').append(option);}
document.querySelector('#viewBy').value='all';
const html=fs.readFileSync('BOL images/index.html','utf8');
const scripts=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m=>m[1]);
scripts.forEach(code=>new vm.Script(code));
const context=vm.createContext({document,console});
for(const index of [0,6,7,8])vm.runInContext(scripts[index],context);
assert.equal(vm.runInContext("encodeGalleryPath('Company #1/File 50%/A&B #2.jpg')",context),'Company%20%231/File%2050%25/A%26B%20%232.jpg');
const specialCard=vm.runInContext("makeCard({image:'Company #1/A&B #2.jpg',name:'sample',company:'Company #1',pdf:'test.pdf',page:1,text:'',searchable_pdf:'Company #1/Searchable #2.pdf'},'')",context);
assert.equal(specialCard.children[0].src,'/media/Company%20%231/A%26B%20%232.jpg');
assert.equal(specialCard.children[1].children.find(c=>c.className==='pdf-link').href,'/media/Company%20%231/Searchable%20%232.pdf#page=1');
vm.runInContext(`data=[
 {name:'old',image:'old.jpg',pdf:'Old.pdf',company:'A',date:'2026-09-01',page:1,text:'sample',trash:false},
 {name:'new',image:'new.jpg',pdf:'New.pdf',company:'A',date:'2026-09-10',page:1,text:'sample',trash:false}
];`,context);
const pdf=document.querySelector('#groupByPdf'),date=document.querySelector('#groupByDate');
function select(p,d){pdf.checked=p;date.checked=d;pdf.onchange();}
select(false,false);
assert.equal(document.querySelector('#count').textContent,'2 images');
select(true,false);
assert.equal(document.querySelector('#count').textContent,'2 PDFs');
select(false,true);
assert.equal(document.querySelector('#grid').children[0].textContent,'2026-09-10');
select(true,true);
assert.equal(document.querySelector('#viewBy').value,'date-pdf');
assert.equal(document.querySelector('#count').textContent,'2 PDFs grouped by date');
assert.equal(document.querySelector('#grid').children[0].textContent,'2026-09-10');
assert.equal(pdf.checked&&date.checked,true);
// Refreshing data/render must retain the combined state.
vm.runInContext('render()',context);
assert.equal(document.querySelector('#count').textContent,'2 PDFs grouped by date');
// Only PDF boxes appear until one is clicked; search stays inside that PDF.
const grid=document.querySelector('#grid'),q=document.querySelector('#q');
assert.equal(grid.children.filter(c=>c.className==='card').length,0);
q.value='NEW.PDF';q.oninput();
assert.equal(document.querySelector('#count').textContent,'1 PDFs grouped by date');
const box=grid.children.find(c=>c.className==='pdf-card');
box.children[0].onclick();
assert.equal(document.querySelector('#count').textContent,'1 matching page images in New.pdf');
assert.equal(grid.children.filter(c=>c.className==='card').length,1);
// The filename search opens its pages; replacing it with OCR text stays scoped.
q.value='absent';q.oninput();
assert.equal(document.querySelector('#count').textContent,'0 matching page images in New.pdf');
q.value='sample';q.oninput();
assert.equal(document.querySelector('#count').textContent,'1 matching page images in New.pdf');
vm.runInContext('render()',context);
assert.equal(document.querySelector('#count').textContent,'1 matching page images in New.pdf');
document.querySelector('#count').children.at(-1).onclick();
assert.equal(document.querySelector('#count').textContent,'2 PDFs grouped by date');
q.value='';
select(true,false);
assert.equal(document.querySelector('#count').textContent,'2 PDFs');
select(false,false);
assert.equal(document.querySelector('#count').textContent,'2 images');
// Date headings stay intact; same-date boxes follow time rather than filename.
vm.runInContext(`data=[
 {pdf:'Z-3pm.pdf',company:'A',date:'2026-09-10',processed_at:'2026-09-10T15:00:00Z',page:1,trash:false},
 {pdf:'A-5pm.pdf',company:'A',date:'2026-09-10',processed_at:'2026-09-10T17:00:00Z',page:1,trash:false},
 {pdf:'B-4pm.pdf',company:'A',date:'2026-09-10',processed_at:'2026-09-10T16:00:00Z',page:1,trash:false}
];`,context);
select(true,true);
assert.deepEqual(grid.children.filter(c=>c.className==='pdf-card').map(c=>c.children[0].children[1].textContent),['A-5pm.pdf','B-4pm.pdf','Z-3pm.pdf']);
assert.equal(grid.children.filter(c=>c.className==='group-title').length,1);
console.log('PASS: view states, navigation, search, and date groups with PDF boxes ordered 5pm, 4pm, 3pm.');
// Exercise the real file dropdown wiring and type predicates independently.
const sheetAsset=fs.readFileSync('app/services/spreadsheet_gallery.html','utf8');
Element.prototype.setAttribute=function(name,value){this[name]=value;};
const fileContext=vm.createContext({document, sheetElement:(tag,text)=>Object.assign(new Element(tag),{textContent:text}),
  groupByPdf:{checked:false,parentElement:{before(){},style:{}}},
  pdfFilter:{value:'previous.pdf'},applyFilters:cards=>cards,
  syncGroupingCheckboxes(){fileContext.syncCalls++;},syncCalls:0});
vm.runInContext(sheetAsset.slice(sheetAsset.indexOf('const fileType='),sheetAsset.indexOf('q.placeholder=')),fileContext);
vm.runInContext(`testCards=[{pdf:'a.pdf'},{file_id:'1',file_type:'xls'},{file_id:'2',file_type:'xlsx'},{file_id:'3',file_type:'csv'}]`,fileContext);
assert.deepEqual(Array.from(vm.runInContext('fileType.children.map(option=>option.textContent)',fileContext)),['View by file','View by PDF','View by XLS/CSV']);
for(const [value,expected] of [['',4],['pdf',1],['spreadsheet',3]]){
  vm.runInContext(`fileType.value=${JSON.stringify(value)};fileType.onchange()`,fileContext);
  assert.equal(vm.runInContext('applyFilters(testCards).length',fileContext),expected);
  assert.equal(fileContext.groupByPdf.checked,true);
  assert.equal(fileContext.pdfFilter.value,'');
}
assert.equal(fileContext.syncCalls,3);
console.log('PASS: file dropdown choices, combined XLS/XLSX/CSV filtering, and grouping synchronization.');
