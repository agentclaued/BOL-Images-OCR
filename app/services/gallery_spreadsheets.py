"""Spreadsheet controls and table browser added to the generated gallery shell."""


def add_spreadsheet_ui(page: str) -> str:
    page = page.replace("Search PDF filename or OCR text", "Search filename, OCR or cells")
    page = page.replace('>View by PDF</label>', '>View by file</label>')
    page = page.replace('>PDF file</label>', '>File</label>')
    # Existing IDs stay stable for the PDF page browser.
    page = page.replace("All PDF files", "All files")
    page = page.replace('<div class="tabs">', '<div class="filter-slot"><label for="fileType">File type</label><select id="fileType" aria-label="File type"><option value="">All types</option><option value="pdf">PDF / images</option><option value="excel">Excel</option><option value="csv">CSV</option></select></div><div class="tabs">', 1)
    page = page.replace('let cards=await response.json();', "let cards=await response.json();if(tab!=='trash'){let sheetsResponse=await fetch('/api/spreadsheets?query='+encodeURIComponent(q.value.trim()));if(!sheetsResponse.ok)throw Error('Spreadsheet service unavailable');cards=cards.concat(await sheetsResponse.json())}", 1)
    page = page.replace('meta.textContent=first.company', 'meta.textContent=first.company', 1)
    page += '''<style>
body>header> .filter-slot{min-width:95px;max-width:115px;flex:0 0 105px}
.sheet-upload{border-top:1px solid #e4e7ec;margin-top:14px;padding-top:12px}
.sheet-upload summary{cursor:pointer;font-weight:600}.sheet-upload input{width:100%;margin:12px 0}
.sheet-upload-status{white-space:pre-wrap;font-size:12px;line-height:1.5;margin-top:8px}
.sheet-browser{grid-column:1/-1;min-width:0;background:#fff;border:1px solid #e4e7ec;border-radius:10px;padding:16px}
.sheet-toolbar{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:12px}
.sheet-toolbar select,.sheet-toolbar button{padding:8px;border:1px solid #ddd;border-radius:6px;background:#fff;font:inherit}
.sheet-scroll{overflow:auto;max-height:65vh;border:1px solid #e4e7ec}
.sheet-table{border-collapse:separate;border-spacing:0;font-size:13px;width:100%}
.sheet-table th,.sheet-table td{padding:9px 12px;min-width:110px;border-bottom:1px solid #eee;border-right:1px solid #eee;text-align:left;vertical-align:top}
.sheet-table th{position:sticky;top:0;background:#f5f3ef;z-index:1}
.sheet-table td{max-width:340px;overflow-wrap:anywhere;white-space:pre-wrap}.sheet-table small{display:block;color:#898277;font-size:10px;margin-bottom:4px}
.sheet-notes{color:#756343;font-size:12px;margin:8px 0}.sheet-file-icon{color:#34734d;font-size:22px;font-weight:600}
</style><script>
const fileType=document.querySelector('#fileType');
let openedSheet=null,sheetChoice='',sheetOffset=0,sheetRequest=0,sheetListSearch='';
const uploadSection=document.createElement('details');uploadSection.className='sheet-upload';
const uploadHeading=document.createElement('summary');uploadHeading.textContent='Upload Excel / CSV';
const sheetUpload=document.createElement('input');sheetUpload.type='file';sheetUpload.multiple=true;sheetUpload.accept='.xls,.xlsx,.csv';sheetUpload.setAttribute('aria-label','Choose Excel or CSV files');
const uploadButton=document.createElement('button');uploadButton.type='button';uploadButton.textContent='Upload and index';
const uploadStatus=document.createElement('div');uploadStatus.className='sheet-upload-status';uploadStatus.setAttribute('role','status');
uploadSection.append(uploadHeading,sheetUpload,uploadButton,uploadStatus);processorPanel.append(uploadSection);
uploadButton.onclick=async()=>{
  if(!sheetUpload.files.length){uploadStatus.textContent='Choose XLS, XLSX or CSV files first.';return;}
  uploadButton.disabled=true;uploadStatus.textContent='Reading and indexing spreadsheets...';
  try{
    const messages=[];
    for(const file of sheetUpload.files){
      if(file.size>50*1024*1024){messages.push(file.name+': exceeds 50 MB.');continue;}
      const form=new FormData();form.append('files',file,file.name);
      const response=await fetch('/api/spreadsheets/upload',{method:'POST',body:form});
      if(!response.ok)throw Error('Upload failed. Restart the updated app if this feature is unavailable.');
      const result=await response.json();
      for(const item of result.files)messages.push(item.name+': indexed '+item.cells+' cells.'+(item.warnings.length?' '+item.warnings.join(' '):''));
      for(const item of result.errors)messages.push(item.name+': '+item.error);
      uploadStatus.textContent=messages.join('\n');
    }
    openedSheet=null;selectedPdf=null;q.value='';fileType.value='';tab='main';
    document.querySelectorAll('[data-tab]').forEach(b=>b.classList.toggle('on',b.dataset.tab==='main'));
    groupByPdf.checked=true;syncGroupingCheckboxes();await loadLiveGallery();
  }catch(error){uploadStatus.textContent=error.message;}finally{uploadButton.disabled=false;}
};
function sheetBox(item){
  const box=document.createElement('article');box.className='pdf-card';
  const button=document.createElement('button');button.type='button';button.className='pdf-open';
  const icon=document.createElement('div');icon.className='sheet-file-icon';icon.textContent=item.file_type.toUpperCase();
  const title=document.createElement('div');title.className='pdf-title';addText(title,item.name,q.value.trim());
  const meta=document.createElement('div');meta.className='pdf-meta';meta.textContent=item.sheet_count+' sheet(s)'+(item.text?' · Cell matches found':'');
  button.append(icon,title,meta);button.onclick=()=>{sheetListSearch=q.value;openedSheet=item;sheetChoice='';sheetOffset=0;q.value=item.name.toLowerCase().includes(q.value.trim().toLowerCase())?'':q.value;render();};
  const download=document.createElement('a');download.className='pdf-download';download.href='/api/spreadsheets/'+item.file_id+'/download';download.textContent='Download original';
  box.append(button,download);return box;
}
const pdfBoxOnly=makePdfBox;
makePdfBox=function(items){return items[0].file_type?sheetBox(items[0]):pdfBoxOnly(items);};
function matchesFileType(card){return !fileType.value||(fileType.value==='pdf'?!card.file_type:fileType.value==='excel'?['xls','xlsx'].includes(card.file_type):card.file_type==='csv');}
function closeSheet(){openedSheet=null;sheetRequest++;q.value=sheetListSearch;refreshLiveGallery();}
function columnLabel(n){let out='';while(n){n--;out=String.fromCharCode(65+n%26)+out;n=Math.floor(n/26);}return out;}
async function renderSheet(){
  const item=openedSheet,request=++sheetRequest;
  const params=new URLSearchParams({query:q.value.trim(),offset:String(sheetOffset)});if(sheetChoice!=='')params.set('sheet',sheetChoice);
  count.textContent='Loading '+item.name+'...';grid.replaceChildren();
  try{
    const response=await fetch('/api/spreadsheets/'+item.file_id+'/rows?'+params);
    if(!response.ok)throw Error('Could not read spreadsheet rows.');
    const result=await response.json();if(request!==sheetRequest||openedSheet!==item)return;
    count.textContent=result.total+' matching rows in '+result.name;
    const panel=document.createElement('section');panel.className='sheet-browser';
    const toolbar=document.createElement('div');toolbar.className='sheet-toolbar';
    const back=document.createElement('button');back.textContent='← Back to files';back.onclick=closeSheet;
    const select=document.createElement('select');select.setAttribute('aria-label','Worksheet');
    const all=document.createElement('option');all.value='';all.textContent='All sheets';select.append(all);
    for(const sheet of result.sheets){const option=document.createElement('option');option.value=sheet.idx;option.textContent=sheet.name;select.append(option);}
    select.value=sheetChoice;select.onchange=()=>{sheetChoice=select.value;sheetOffset=0;renderSheet();};
    const download=document.createElement('a');download.href='/api/spreadsheets/'+item.file_id+'/download';download.textContent='Download original';
    toolbar.append(back,select,download);panel.append(toolbar);
    if(result.warnings.length){const note=document.createElement('p');note.className='sheet-notes';note.textContent=result.warnings.join(' ');panel.append(note);}
    const scroll=document.createElement('div');scroll.className='sheet-scroll';
    const table=document.createElement('table');table.className='sheet-table';
    const columns=[...new Set(result.rows.flatMap(row=>row.cells.map(cell=>cell.column)))].sort((a,b)=>a-b);
    const head=document.createElement('thead'),header=document.createElement('tr');
    for(const label of ['Sheet','Row',...columns.map(columnLabel)]){const th=document.createElement('th');th.textContent=label;header.append(th);}head.append(header);table.append(head);
    const body=document.createElement('tbody');
    for(const row of result.rows){
      const tr=document.createElement('tr');
      for(const label of [row.sheet,String(row.row)]){const td=document.createElement('td');td.textContent=label;tr.append(td);}
      const byColumn=new Map(row.cells.map(cell=>[cell.column,cell]));
      for(const column of columns){
        const td=document.createElement('td'),cell=byColumn.get(column);
        if(cell){const ref=document.createElement('small');ref.textContent=cell.address;td.append(ref);addText(td,cell.value,q.value.trim());if(cell.formula){const formula=document.createElement('small');addText(formula,cell.formula,q.value.trim());td.append(formula);}}
        tr.append(td);
      }
      body.append(tr);
    }
    table.append(body);scroll.append(table);panel.append(scroll);
    const pages=document.createElement('div');pages.className='sheet-toolbar';
    const prev=document.createElement('button');prev.textContent='Previous';prev.disabled=sheetOffset===0;prev.onclick=()=>{sheetOffset=Math.max(0,sheetOffset-100);renderSheet();};
    const next=document.createElement('button');next.textContent='Next';next.disabled=sheetOffset+100>=result.total;next.onclick=()=>{sheetOffset+=100;renderSheet();};
    const label=document.createElement('span');label.textContent=result.total?'Rows '+(sheetOffset+1)+'–'+Math.min(sheetOffset+100,result.total)+' of '+result.total:'No matching rows. Change the search or sheet.';
    pages.append(prev,label,next);panel.append(pages);grid.append(panel);
  }catch(error){if(request!==sheetRequest)return;count.textContent=error.message;const back=document.createElement('button');back.textContent='Back to files';back.onclick=closeSheet;grid.append(back);}
}
const filesBaseRender=render;
render=function(){
  if(openedSheet){renderSheet();return;}
  const original=data;data=original.filter(matchesFileType);
  try{
    if(!pdfViewSelected&&!dateViewSelected){const sheets=applyFilters(data).filter(card=>card.file_type);data=data.filter(card=>!card.file_type);filesBaseRender();sheets.forEach(item=>grid.append(sheetBox(item)));if(sheets.length){grid.querySelector('.empty')?.remove();count.textContent=data.length+' page images · '+sheets.length+' spreadsheets';}}
    else{filesBaseRender();if(!selectedPdf)count.textContent=count.textContent.replace('PDFs','files');}
  }finally{data=original;}
};
q.oninput=()=>{sheetOffset=0;if(openedSheet)renderSheet();else refreshLiveGallery();};
fileType.onchange=()=>{openedSheet=null;selectedPdf=null;render();};
document.querySelectorAll('[data-tab]').forEach(button=>button.addEventListener('click',()=>{openedSheet=null;sheetRequest++;}));
groupByPdf.addEventListener('change',()=>{openedSheet=null;sheetRequest++;render();});
groupByDate.addEventListener('change',()=>{openedSheet=null;sheetRequest++;render();});
</script>'''
    return page
