"""Batch-render BOL PDFs into searchable JPG page images.

Example:
    python batch_pdf_to_images.py "D:\\Incoming BOLs"
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pymupdf as fitz  # PyMuPDF 1.28+ has no 'fitz' module


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = PROJECT_ROOT / "BOL images"
UPLOAD_ROOT = OUTPUT_ROOT / "_AppData" / "uploads"
sys.path.insert(0, str(PROJECT_ROOT))
from app.services.storage_layout import PDFS, IMAGES, migrate_legacy_gallery, unique_folder


EMBEDDED_TEXT_MIN_CHARS = 30  # pages with at least this much real text skip OCR


def safe_name(value: str) -> str:
    """Create a Windows-safe readable file/folder name."""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", value)
    return re.sub(r"\s+", " ", cleaned).strip(" .") or "Unknown"


def pdf_sha256(pdf_path: Path) -> str:
    """Return a content fingerprint without loading the full PDF into memory."""
    digest = hashlib.sha256()
    with pdf_path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def processing_key(pdf_path: Path, source_sha256: str) -> str:
    """Keep same-named but different PDFs separate while retaining readable names."""
    return f"{safe_name(pdf_path.stem)} [{source_sha256[:12]}]"


def is_processable_source_pdf(pdf_path: Path) -> bool:
    """Ignore generated gallery PDFs, but accept browser uploads in _AppData."""
    resolved = pdf_path.resolve()
    output_root = OUTPUT_ROOT.resolve()
    upload_root = UPLOAD_ROOT.resolve()
    return output_root not in resolved.parents or upload_root in resolved.parents


def cleanup_completed_processing() -> int:
    """Remove old temporary folders only after their final output was completed."""
    removed = 0
    processing_root = OUTPUT_ROOT / "_Processing"
    if not processing_root.is_dir():
        return removed
    completed_hashes: set[str] = set()
    for manifest_path in OUTPUT_ROOT.rglob("ocr-results.json"):
        try:
            source_sha256 = str(json.loads(manifest_path.read_text(encoding="utf-8")).get("source_sha256", ""))
            if source_sha256:
                completed_hashes.add(source_sha256)
        except (OSError, json.JSONDecodeError):
            continue
    for state_path in processing_root.glob("*/processing-state.json"):
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        is_legacy_stale_cache = not state.get("status")
        if not is_legacy_stale_cache and state.get("status") != "complete" and str(state.get("source_sha256", "")) not in completed_hashes:
            continue
        try:
            shutil.rmtree(state_path.parent)
            removed += 1
        except OSError:
            continue
    return removed


def generate_gallery() -> None:
    """Build the lightweight gallery shell; the FastAPI API supplies live cards."""
    payload = "[]"
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    migrate_legacy_gallery()
    page = """<!doctype html><html lang=\"en\"><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>BOL Images</title>
<style>body{margin:0;background:#f7f9fc;color:#202124;font:14px Arial}header{padding:18px 28px;background:#fff;border-bottom:1px solid #ddd;display:flex;gap:16px;align-items:center;position:sticky;top:0;z-index:4;flex-wrap:wrap}h1{font-size:22px;margin:0}.filter-bar{display:flex;flex:1;min-width:420px;gap:8px;flex-wrap:wrap}.filter-slot{display:flex;flex-direction:column;gap:3px;min-width:125px}.filter-slot label{font-size:11px;font-weight:bold;color:#5f6368;text-transform:uppercase}.filter-slot input,.filter-slot select{width:100%;box-sizing:border-box;padding:9px 10px;border:1px solid #d8dce0;border-radius:8px;background:#fff;font:inherit}.filter-slot.search-slot{flex:1;min-width:260px;position:relative}.search-slot input{padding:11px 14px 11px 37px;border-radius:22px;background:#f1f3f4;border-color:#f1f3f4;font-size:15px}.search-slot input:focus{outline:0;background:#fff;border-color:#1a73e8;box-shadow:0 0 0 2px #e8f0fe}.search-slot:after{content:'⌕';position:absolute;left:13px;bottom:8px;color:#5f6368;font-size:21px;line-height:1}.tabs button,.view-select{border:1px solid #d8dce0;background:#fff;border-radius:18px;padding:8px 12px;cursor:pointer;font:inherit;color:#202124}.tabs .on{background:#e8f0fe;color:#1967d2}main{padding:24px 28px}.count{color:#5f6368;margin-bottom:15px}.back{border:0;background:none;color:#1967d2;cursor:pointer;padding:0 0 0 10px;font:inherit}.group-title{grid-column:1/-1;margin:10px 0 -5px;font-size:17px;font-weight:500}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:16px}.card,.pdf-card{background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 1px 4px #ccd0d5}.card{content-visibility:auto;contain-intrinsic-size:290px}.card img{width:100%;height:175px;object-fit:cover;background:#e9eef4}.pdf-card{min-height:145px;padding:20px;text-align:left;border:0;cursor:pointer}.pdf-card:hover{box-shadow:0 4px 12px #b9bec5}.pdf-icon{font-size:30px}.pdf-title{font-weight:bold;margin-top:10px;word-break:break-word}.pdf-meta{color:#5f6368;font-size:12px;margin-top:6px}.info{padding:11px}.name{font-weight:bold;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.meta,.ocr{margin-top:5px;color:#5f6368;font-size:12px}.actions{display:flex;gap:5px;float:right}.icon{display:grid;place-items:center;width:29px;height:29px;border:1px solid #d8dce0;border-radius:50%;background:#fff;color:#3c4043;text-decoration:none;font-size:15px;cursor:pointer}.icon:hover{background:#f1f3f4}.trash:hover{color:#c5221f}.pdf-link{display:inline-block;margin-top:8px;color:#1967d2;font-size:12px;font-weight:bold;text-decoration:none}.pdf-link:hover{text-decoration:underline}.ocr{color:#3c4043;white-space:pre-wrap;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}.ocr.open{display:block}.more{border:0;background:none;color:#1967d2;padding:5px 0 0;font-size:12px;cursor:pointer}mark{background:#fff475;color:inherit;border-radius:2px;padding:0}.empty{padding:45px;text-align:center;color:#5f6368}</style>
<header><h1><a href=\"/\" title=\"Refresh gallery\">BOL Images</a></h1><div class=\"filter-bar\"><div class=\"filter-slot search-slot\"><label for=\"q\">Search PDF filename or OCR text</label><input id=\"q\" placeholder=\"Search PDF filename or OCR text\"></div><div class=\"filter-slot\"><label for=\"pdfFilter\">PDF file</label><select id=\"pdfFilter\"><option value=\"\">All PDF files</option></select></div></div><div class=\"tabs\"><button class=\"on\" data-tab=\"main\">Photos</button><label class=\"group-filter\"><input id=\"groupByPdf\" type=\"checkbox\"> View by PDF</label><label class=\"group-filter\"><input id=\"groupByDate\" type=\"checkbox\"> View by date</label><button class=\"view-mode on\" id=\"viewAllButton\" type=\"button\" hidden>All photos</button><button class=\"view-mode\" id=\"viewPdfButton\" type=\"button\" hidden>View by PDF</button><button class=\"view-mode\" id=\"viewDateButton\" type=\"button\" hidden>View by date</button><select id=\"viewBy\" hidden><option value=\"all\">All photos</option><option value=\"pdf\">View by PDF</option><option value=\"date\">View by date</option></select><button data-tab=\"trash\">Trash</button><button id=\"processToggle\">Process panel</button></div></header><main><div class=\"count\" id=\"count\"></div><div class=\"grid\" id=\"grid\"></div></main>
<script>const data=__DATA__,q=document.querySelector('#q'),grid=document.querySelector('#grid'),count=document.querySelector('#count'),viewBy=document.querySelector('#viewBy'),key='bol-demo-trash',moved=new Set(JSON.parse(localStorage.getItem(key)||'[]'));let tab='main',selectedPdf=null;function trash(x){moved.add(x.image);localStorage.setItem(key,JSON.stringify([...moved]));render()}function restore(x){moved.delete(x.image);localStorage.setItem(key,JSON.stringify([...moved]));render()}function addText(e,t,s){let p=t.toString(),n=s.toLowerCase();if(!n){e.textContent=p;return}let z=0,l=p.toLowerCase();while(1){let k=l.indexOf(n,z);if(k<0){e.append(document.createTextNode(p.slice(z)));break}e.append(document.createTextNode(p.slice(z,k)));let m=document.createElement('mark');m.textContent=p.slice(k,k+n.length);e.append(m);z=k+n.length}}function makeCard(x,s){let c=document.createElement('article');c.className='card';let im=document.createElement('img');im.src=encodeURI(x.image);im.alt=x.name;im.loading='lazy';im.decoding='async';im.fetchPriority='low';let i=document.createElement('div');i.className='info';let actions=document.createElement('div');actions.className='actions';let dl=document.createElement('a');dl.className='icon';dl.href=encodeURI(x.image);dl.download=x.name;dl.title='Download image';dl.textContent='⇩';actions.append(dl);if(tab==='main'){let tr=document.createElement('button');tr.className='icon trash';tr.title='Move to Trash';tr.textContent='🗑';tr.onclick=()=>trash(x);actions.append(tr)}else{let rs=document.createElement('button');rs.className='icon';rs.title='Restore to Photos';rs.textContent='↶';rs.onclick=()=>restore(x);actions.append(rs)}i.append(actions);for(let [cl,t] of [['name',String(x.page).padStart(3,'0')+' '+x.pdf+' P#'+x.page+'.jpg']]){let d=document.createElement('div');d.className=cl;addText(d,t,s);i.append(d)}if(x.searchable_pdf){let l=document.createElement('a');l.className='pdf-link';l.href=encodeURI(x.searchable_pdf)+'#page='+x.page;l.target='_blank';l.textContent='PDF-P#'+x.page;i.append(l)}let o=document.createElement('div');o.className='ocr';addText(o,'OCR: '+(x.text||'No readable text'),s);i.append(o);if((x.text||'').length>120){let b=document.createElement('button');b.className='more';b.textContent='Show full OCR text';b.onclick=()=>{let open=o.classList.toggle('open');b.textContent=open?'Show less':'Show full OCR text'};i.append(b)}c.append(im,i);return c}function render(){let s=q.value.trim(),a=data.filter(x=>(x.trash||moved.has(x.image))===(tab==='trash')&&(!s||Object.values(x).join(' ').toLowerCase().includes(s.toLowerCase())));if(viewBy.value==='pdf'&&!selectedPdf){let groups={};a.forEach(x=>(groups[x.pdf]??=[]).push(x));count.textContent=Object.keys(groups).length+' PDF'+(Object.keys(groups).length===1?'':'s');grid.innerHTML=Object.keys(groups).length?'':'<div class=\"empty\">No PDFs found.</div>';Object.entries(groups).forEach(([pdf,items])=>{let b=document.createElement('button');b.className='pdf-card';b.innerHTML='<div class=\"pdf-icon\">📄</div>';let t=document.createElement('div');t.className='pdf-title';addText(t,pdf,s);b.append(t);let m=document.createElement('div');m.className='pdf-meta';m.textContent=items.length+' page image'+(items.length===1?'':'s')+' · '+items[0].company;b.append(m);b.onclick=()=>{selectedPdf=pdf;render()};grid.append(b)});return}if(selectedPdf){a=a.filter(x=>x.pdf===selectedPdf);count.textContent=a.length+' image'+(a.length===1?'':'s')+' in '+selectedPdf;let back=document.createElement('button');back.className='back';back.textContent='← Back to PDF list';back.onclick=()=>{selectedPdf=null;render()};count.append(back)}else count.textContent=a.length+' image'+(a.length===1?'':'s');if(!a.length){grid.innerHTML='<div class=\"empty\">No images found.</div>';return}grid.innerHTML='';let groups={};a.forEach(x=>{let g=viewBy.value==='date'?x.date:'All photos';(groups[g]??=[]).push(x)});Object.entries(groups).forEach(([g,items])=>{if(viewBy.value==='date'){let h=document.createElement('h2');h.className='group-title';h.textContent=g;grid.append(h)}let i=0,step=()=>{let e=Math.min(i+60,items.length),f=document.createDocumentFragment();for(;i<e;i++)f.append(makeCard(items[i],s));if(more.parentNode)more.before(f);else grid.append(f);if(i>=items.length)more.remove()},more=document.createElement('div');more.style.cssText='grid-column:1/-1;height:1px';grid.append(more);step();if(i<items.length){let io=new IntersectionObserver(en=>{if(en[0].isIntersecting){step();if(i>=items.length)io.disconnect()}},{rootMargin:'1500px'});io.observe(more)}})}q.oninput=render;viewBy.onchange=()=>{selectedPdf=null;render()};document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>{tab=b.dataset.tab;selectedPdf=null;document.querySelectorAll('[data-tab]').forEach(x=>x.classList.toggle('on',x===b));render()});render()</script>""".replace("__DATA__", payload)
    # Keep expanded OCR readable without allowing a long page transcription to
    # stretch the image card indefinitely.
    page = page.replace(
        ".ocr.open{display:block}",
        ".ocr.open{display:block;max-height:180px;overflow-y:auto;padding:8px;"
        "border:1px solid #d8dce0;border-radius:6px;background:#f8f9fa;"
        "box-sizing:border-box}",
        1,
    )
    # The FastAPI app serves media, forces downloads, and moves Trash files.
    # Cards show a small cached preview; the detail view still loads the full scan.
    page = page.replace("im.src=encodeURI(x.image)", "im.src='/api/thumb?file='+encodeURIComponent(x.image)")
    page = page.replace("</style>", ".card{content-visibility:auto;contain-intrinsic-size:auto 320px}</style>", 1)
    page = page.replace(
        "im.alt=x.name;",
        "im.alt=x.name;im.className='card-image';im.title='Open image details';"
        "im.onclick=()=>openProductView(x);",
        1,
    )
    page = page.replace("</style>", ".info{padding:12px 14px 14px;display:flex;flex-direction:column}.actions{order:5;float:none;justify-content:flex-end;margin:10px 0 0;padding-top:10px;border-top:1px solid #eceff1}.name{order:1;white-space:normal;overflow-wrap:anywhere;font-size:14px;line-height:1.3;color:#202124}.meta{order:2;margin-top:4px;font-size:12px;line-height:1.4}.pdf-link{order:3;align-self:flex-start;margin-top:8px;padding:2px 8px;border-radius:10px;background:#e8f0fe}.ocr{order:4;margin-top:8px;font-size:12px;line-height:1.45;color:#3c4043}.more{order:4;align-self:flex-start;font-weight:bold}</style>", 1)
    # Thumbnails are not fetched until the user presses the card's Load image button.
    page = page.replace("im.src='/api/thumb?file='+encodeURIComponent(x.image)", "im.dataset.src='/api/thumb?file='+encodeURIComponent(x.image)")
    page = page.replace(
        "c.append(im,i);return c}",
        "let lb=document.createElement('button');lb.className='load-image';lb.textContent='Load image';"
        "lb.onclick=()=>{im.src=im.dataset.src;lb.replaceWith(im)};c.append(lb,i);let lx=document.querySelector('#loadImages');if(lx&&lx.checked&&q.value.trim())lb.click();return c}",
        1,
    )
    page = page.replace("</style>", ".load-image{display:block;width:100%;height:175px;margin:0;padding:0;border:0;border-radius:0;background:#e9eef4;color:#1967d2;font:bold 14px Arial;cursor:pointer}.load-image:hover{background:#e8f0fe}</style>", 1)
    page = page.replace("l.href=encodeURI(x.searchable_pdf)+'#page='+x.page", "l.href='/media/'+encodeURI(x.searchable_pdf)+'#page='+x.page")
    page = page.replace("dl.href=encodeURI(x.image)", "dl.href='/api/download?file='+encodeURIComponent(x.image)")
    svg = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="%s" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">%s</svg>'
    icon_pdf = svg % ("#c5221f", '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/><path d="M12 11v6m-3-3 3 3 3-3"/>')
    icon_img = svg % ("#1967d2", '<rect x="2" y="3" width="15" height="15" rx="2"/><circle cx="7" cy="8" r="1.3"/><path d="m17 13-4-4L4 18"/><path d="M19 12v9m-3-3 3 3 3-3"/>')
    page = page.replace("let tab='main',", "const ICON_PDF='%s',ICON_IMG='%s';let tab='main'," % (icon_pdf, icon_img), 1)
    page = page.replace("dl.title='Download image';dl.textContent='⇩';", "dl.title='Download image';dl.innerHTML=ICON_IMG;")
    page = page.replace("const data=", "let data=", 1)
    page = page.replace(".empty{", ".pdf-unavailable{margin-top:8px;color:#8d6400;font-size:12px}.empty{", 1)
    page = page.replace("if(x.searchable_pdf){let l=document.createElement('a');l.className='pdf-link';l.href=encodeURI(x.searchable_pdf)+'#page='+x.page;l.target='_blank';l.textContent='PDF-P#'+x.page;i.append(l)}", "if(x.searchable_pdf){let l=document.createElement('a');l.className='pdf-link';l.href=encodeURI(x.searchable_pdf)+'#page='+x.page;l.target='_blank';l.textContent='PDF-P#'+x.page;i.append(l)}else{let u=document.createElement('div');u.className='pdf-unavailable';u.textContent='Searchable PDF unavailable';i.append(u)}", 1)
    page = page.replace("let s=q.value.trim(),a=data.filter(x=>(x.trash||moved.has(x.image))===(tab==='trash')&&(!s||Object.values(x).join(' ').toLowerCase().includes(s.toLowerCase())));", "let s=q.value.trim(),a=data.filter(x=>(x.trash||moved.has(x.image))===(tab==='trash')&&(viewBy.value==='pdf'||!x.processing)&&(!s||Object.values(x).join(' ').toLowerCase().includes(s.toLowerCase())));", 1)
    page = page.replace("m.textContent=items.length+' page image'+(items.length===1?'':'s')+' · '+items[0].company;b.append(m);b.onclick=()=>{selectedPdf=pdf;render()};", "m.textContent=items[0].processing?'Processing image scan · searchable PDF ready':items.length+' page image'+(items.length===1?'':'s')+' · '+items[0].company;b.append(m);b.disabled=!!items[0].processing;b.title=items[0].processing?'Image scan is still processing':'View page images';b.onclick=()=>{if(items[0].processing)return;selectedPdf=pdf;render()};", 1)
    page = page.replace("actions.append(dl);if(tab==='main')", "actions.append(dl);if(x.source_pdf||x.searchable_pdf){let p=x.searchable_pdf||x.source_pdf,pl=document.createElement('a');pl.className='icon';pl.href='/api/download?file='+encodeURIComponent(p);pl.download=p.split('/').pop();pl.title='Download searchable PDF';pl.innerHTML=ICON_PDF;actions.append(pl)}if(tab==='main')", 1)
    page = page.replace("b.className='pdf-card';", "b.className='pdf-open';", 1)
    page = page.replace("grid.append(b)});return", "let card=document.createElement('article');card.className='pdf-card';card.append(b);let searchable=items.find(item=>item.searchable_pdf)?.searchable_pdf;if(searchable){let download=document.createElement('a');download.className='pdf-download';download.href='/media/'+encodeURI(searchable);download.download=searchable.split('/').pop();download.title='Download searchable PDF';download.textContent='⇩ Download searchable PDF';card.append(download)}if(items[0].pdf_folder){let del=document.createElement('button');del.className='pdf-delete';del.textContent='Delete this PDF data';del.title='Permanently delete this PDF, its images, OCR files, and database record';del.onclick=()=>deletePdf(items[0].pdf_folder,pdf);card.append(del)}grid.append(card)});return", 1)
    page = page.replace(".pdf-card{min-height:145px;padding:20px;text-align:left;border:0;cursor:pointer}", ".pdf-card{min-height:145px;padding:0;text-align:left;border:0;cursor:pointer}.pdf-open{display:block;width:100%;min-height:120px;padding:20px;text-align:left;border:0;background:transparent;color:inherit;font:inherit;cursor:pointer}.pdf-download{display:inline-block;margin:0 20px 16px;color:#1967d2;font-size:12px;font-weight:bold;text-decoration:none}.pdf-download:hover{text-decoration:underline}.pdf-delete{display:inline-block;margin:0 20px 16px;padding:0;border:0;background:none;color:#c5221f;font-size:12px;font-weight:bold;cursor:pointer}", 1)
    page = page.replace("key='bol-demo-trash',moved=new Set(JSON.parse(localStorage.getItem(key)||'[]'));", "moved=new Set();")
    page = page.replace("function trash(x){moved.add(x.image);localStorage.setItem(key,JSON.stringify([...moved]));render()}", "async function trash(x){let r=await fetch('/api/trash?file='+encodeURIComponent(x.image),{method:'POST'});if(!r.ok){alert('Could not move this image to Trash.');return}location.reload()}")
    page = page.replace("function restore(x){moved.delete(x.image);localStorage.setItem(key,JSON.stringify([...moved]));render()}", "async function restore(x){let r=await fetch('/api/restore?file='+encodeURIComponent(x.image),{method:'POST'});if(!r.ok){alert('Could not restore this image.');return}location.reload()}")
    processor = """<aside class=\"processor\" id=\"processorPanel\"><div class=\"process-head\"><div><strong>Process PDFs & Images</strong><span>Each selected PDF is an independent job; up to 10 run at once.</span></div><button id=\"processClose\" class=\"close\" title=\"Hide processor\">×</button></div><span id=\"statusBadge\" class=\"status idle\">IDLE</span><fieldset class=\"source-options\"><legend>Choose one source type</legend><label><input id=\"folderOption\" name=\"sourceType\" type=\"radio\" checked> Folder containing PDFs</label><label><input id=\"pdfOption\" name=\"sourceType\" type=\"radio\"> PDF files</label><label><input id=\"imageOption\" name=\"sourceType\" type=\"radio\"> Images</label></fieldset><div id=\"folderSource\"><input id=\"sourcePath\" placeholder=\"Paste a folder path containing PDFs\"><button class=\"primary\" onclick=\"processPath()\">Start folder</button></div><div id=\"pdfSource\" hidden><input id=\"pdfUpload\" type=\"file\" accept=\".pdf,application/pdf\" multiple><button class=\"primary\" onclick=\"processUpload()\">PDFs: upload & start</button></div><div id=\"imageSource\" hidden><input id=\"imageUpload\" type=\"file\" accept=\".png,.jpg,.jpeg,.webp,.tif,.tiff,image/png,image/jpeg,image/webp,image/tiff\" multiple><button class=\"primary\" onclick=\"processImages()\">Images: OCR to PDF</button></div><div><button id=\"holdButton\" class=\"stop\" onclick=\"holdProcess()\">Hold current batch</button></div><div><button class=\"primary\" onclick=\"runDataValidate()\">DataValidate</button><button id=\"repairDataButton\" onclick=\"runDataRepair()\" disabled>Repair missing data</button></div><div id=\"validationStatus\">Data validation has not run.</div><div class=\"resume-row\"><select id=\"heldJobs\"><option value=\"\">No held batches</option></select><button id=\"resumeButton\" onclick=\"resumeProcess()\">Resume batch</button></div><div id=\"jobStatus\">Choose a source type, then start it.</div><pre id=\"jobLog\">No logs yet.</pre></aside>"""
    processor = processor.replace('Resume batch</button>', 'Resume batch</button><button id="deleteHeldButton" class="stop" onclick="deleteHeldProcess()" disabled>Delete held batch</button>', 1)
    processor = processor.replace('<fieldset', '<div><label for="slotChoice">Slots for next batch</label><select id="slotChoice" onchange="toggleCustomSlots()"><option value="1">1 slot</option><option value="custom">Custom</option></select><input id="customSlots" type="number" min="1" step="1" value="2" aria-label="Custom slot count" hidden><input id="slotPassword" type="password" placeholder="Password for custom slots" aria-label="Password for custom slots" autocomplete="off" hidden></div><fieldset', 1)
    processor = processor.replace('up to 10 run at once.', 'the selected slot limit controls how many run at once.')
    page = page.replace("<main>", "<main>" + processor, 1)
    page = page.replace("</style>", "[hidden]{display:none!important}.processor{position:fixed;z-index:5;top:88px;right:-470px;width:440px;max-width:calc(100vw - 24px);max-height:calc(100vh - 105px);overflow:auto;background:#fff;border:1px solid #d8dce0;border-radius:12px;padding:16px;box-shadow:0 10px 30px #7a808880;transition:right .22s ease}.processor.open{right:16px}.process-head{display:flex;justify-content:space-between;align-items:flex-start}.process-head strong{display:block;font-size:16px}.process-head span:not(.status){display:block;color:#5f6368;font-size:12px;margin-top:3px}.processor .close{border:0;background:none;font-size:24px;line-height:18px;cursor:pointer}.status{display:inline-block;margin-top:10px;padding:5px 9px;border-radius:12px;font-size:11px;font-weight:bold}.status.idle,.status.complete{background:#e6f4ea;color:#137333}.status.running,.status.queued{background:#e8f0fe;color:#1967d2}.status.held{background:#fef7e0;color:#8d6400}.status.failed{background:#fce8e6;color:#c5221f}.processor>div:not(.process-head){display:flex;gap:8px;margin-top:10px;align-items:center}.processor input[type=text],.processor input:not([type]),.processor select{flex:1;min-width:0}.processor input,.processor button,.processor select{padding:9px;border:1px solid #d8dce0;border-radius:7px;background:#fff}.processor button{cursor:pointer}.processor .primary{background:#1a73e8;color:white;border-color:#1a73e8}.processor .stop{background:#fff;color:#c5221f;border-color:#f28b82}.processor .stop:disabled,.processor button:disabled{opacity:.45;cursor:not-allowed}.processor #jobStatus{display:block;color:#5f6368;font-size:12px;white-space:pre-wrap;margin-top:10px}.processor pre{max-height:280px;overflow:auto;background:#202124;color:#d7e3fc;padding:11px;border-radius:7px;font:12px/1.45 Consolas,monospace;white-space:pre-wrap}</style>", 1)
    page = page.replace(".processor{", "h1 a{color:#202124;text-decoration:none;cursor:pointer}h1 a:hover{color:#1967d2;text-decoration:underline}.source-options{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0 0;padding:9px;border:1px solid #d8dce0;border-radius:7px}.source-options legend{font-size:12px;color:#5f6368;padding:0 4px}.source-options label{display:flex;gap:4px;align-items:center;white-space:nowrap}.processor{", 1)
    ui_script = """<script>const jobStatus=document.querySelector('#jobStatus'),jobLog=document.querySelector('#jobLog'),badge=document.querySelector('#statusBadge'),holdButton=document.querySelector('#holdButton'),heldJobs=document.querySelector('#heldJobs'),resumeButton=document.querySelector('#resumeButton');async function showJob(){let r=await fetch('/api/process/status'),j=await r.json(),state=(j.state||'idle').toLowerCase();jobStatus.textContent=state.toUpperCase()+(j.phase?' · '+j.phase.replace('_',' ').toUpperCase():'')+': '+(j.message||'');badge.textContent=state.toUpperCase();badge.className='status '+state;holdButton.disabled=!['running','queued'].includes(state);let prior=heldJobs.value;heldJobs.innerHTML='';for(let x of (j.held_jobs||[])){let o=document.createElement('option');o.value=x.id;o.textContent=x.source+' — '+x.phase.replace('_',' ')+' (held)';heldJobs.append(o)}if(!heldJobs.options.length)heldJobs.innerHTML='<option value="">No held jobs</option>';if([...heldJobs.options].some(o=>o.value===prior))heldJobs.value=prior;resumeButton.disabled=!heldJobs.value;jobLog.textContent=j.logs||'No logs yet.';jobLog.scrollTop=jobLog.scrollHeight}async function processPath(){let p=document.querySelector('#sourcePath').value.trim();if(!p)return alert('Paste a folder path first.');let r=await fetch('/api/process/path?source_path='+encodeURIComponent(p),{method:'POST'});if(!r.ok)return alert((await r.json()).detail||'Could not start processing.');showJob()}async function processUpload(){let f=document.querySelector('#pdfUpload').files;if(!f.length)return alert('Choose one or more PDF files first.');let d=new FormData;for(let x of f)if(x.name.toLowerCase().endsWith('.pdf'))d.append('files',x,x.name);let r=await fetch('/api/process/upload',{method:'POST',body:d}),body=await r.json();let duplicates=body.duplicates||(body.detail&&body.detail.duplicates)||[];let duplicateMessage=duplicates.length?'Duplicate PDF not uploaded:\\n'+duplicates.map(x=>x.uploaded+' is already uploaded as '+x.existing.join(', ')).join('\\n'):'';if(!r.ok)return alert(duplicateMessage||body.detail?.message||body.detail||'Could not upload PDFs.');if(duplicateMessage)alert(duplicateMessage);showJob()}async function processImages(){let f=document.querySelector('#imageUpload').files;if(!f.length)return alert('Choose one or more image files first.');let d=new FormData;for(let x of f)d.append('files',x,x.name);let r=await fetch('/api/process/images',{method:'POST',body:d});if(!r.ok)return alert((await r.json()).detail||'Could not create the image PDF.');showJob()}async function holdProcess(){if(!confirm('Hold the current job? Completed searchable PDFs and page work will remain saved.'))return;let r=await fetch('/api/process/hold',{method:'POST'});if(!r.ok)return alert((await r.json()).detail||'Could not hold processing.');showJob()}async function resumeProcess(){let id=heldJobs.value;if(!id)return;let r=await fetch('/api/process/resume?job_id='+encodeURIComponent(id),{method:'POST'});if(!r.ok)return alert((await r.json()).detail||'Could not resume processing.');showJob()}heldJobs.onchange=()=>resumeButton.disabled=!heldJobs.value;showJob();setInterval(showJob,1500)</script>"""
    ui_script = ui_script.replace(
        "async function showJob()",
        "function formatHeldDate(value){let date=new Date(value),months=['jan','feb','mar','apr','may','jun','jul','aug','sep','oct','nov','dec'];if(Number.isNaN(date.getTime()))return 'date unavailable';let hour=date.getHours(),minute=String(date.getMinutes()).padStart(2,'0'),period=hour>=12?'pm':'am';hour=hour%12||12;return String(date.getDate()).padStart(2,'0')+'-'+months[date.getMonth()]+'-'+String(date.getFullYear()).slice(-2)+' '+hour+':'+minute+' '+period}function formatHeldJob(job){let count=Math.max(0,Number(job.input_count)||0),type=String(job.input_type||'file').toLowerCase();if(count!==1&&!type.endsWith('s'))type+='s';return (job.held_by||'This PC')+' '+count+' '+type+' '+formatHeldDate(job.held_at||job.updated_at)}async function showJob()",
        1,
    )
    ui_script = ui_script.replace(
        "o.textContent=x.source+' — '+x.phase.replace('_',' ')+' (held)';",
        "o.textContent=formatHeldJob(x);",
        1,
    )
    dashboard_script = r"""
function renderBatchDashboard(j){
  if(!Array.isArray(j.active_slots))return 'Restart the server to enable the 10-slot dashboard.\n\n'+(j.logs||'');
  const active=[...j.active_slots].sort((a,b)=>String(a.created_at).localeCompare(String(b.created_at))||a.id.localeCompare(b.id)), queued=j.queued_jobs||[], slots=Math.max(active.length,j.slot_limit||10);
  const cell=(v,w)=>{let s=String(v).replace(/[\r\n\t]/g,' ');return (s.length>w?s.slice(0,w-3)+'...':s).padEnd(w)}, name=x=>String(x.source_path||'').split(/[\\/]/).pop();
  const line='+------+----------+------------------------------------------+-------------+----------+-----------+';
  let out=['BOL Images - Parallel PDF Processing','Refresh: every 1 second',`Workers: ${active.length} / ${slots} active slots | Queue: ${queued.length} waiting`,'Progress: estimated overall; searchable phase has no page percentage.', '',line,'| Slot | Status   | PDF file                                 | Phase       | Progress | Pages     |',line];
  for(let i=0;i<slots;i++){
    let x=active[i];
    if(!x){out.push(`| ${cell(i+1,4)} | EMPTY    | ${cell('-',40)} | ${cell('-',11)} | ${cell('-',8)} | ${cell('-',9)} |`);continue}
    let pages=x.page_total?`${Math.max(0,x.page_current-1)}/${x.page_total}`:'-',progress=x.phase==='searchable'?'Working':`${x.progress||0}% ~`;
    out.push(`| ${cell(i+1,4)} | RUNNING  | ${cell(name(x),40)} | ${cell(x.phase==='image_scan'?'Image OCR':x.phase,11)} | ${cell(progress,8)} | ${cell(pages,9)} |`);
  }
  out.push(line,'','Pages = completed / total.','', 'Queued PDFs', '+--------+----------------------------------------------------+----------+', '| Queue #| PDF file                                           | Progress |', '+--------+----------------------------------------------------+----------+');
  queued.forEach((x,i)=>out.push(`| ${cell(i+1,6)} | ${cell(name(x),50)} | ${cell((x.progress||0)+'%',8)} |`));
  if(!queued.length)out.push('| -      | No PDFs waiting                                    | -        |');
  out.push('+--------+----------------------------------------------------+----------+');
  if(j.batch_counts)out.push('',`Batch selected: ${j.batch_counts.total} PDFs | Completed: ${j.batch_counts.complete} | Failed: ${j.batch_counts.failed} | Held: ${j.batch_counts.held}`);
  return out.join('\n');
}
"""
    ui_script = ui_script.replace('<script>', '<script>'+dashboard_script, 1)
    ui_script = ui_script.replace('async function processPath()', "function toggleCustomSlots(){let custom=document.querySelector('#slotChoice').value==='custom';document.querySelector('#customSlots').hidden=!custom;let password=document.querySelector('#slotPassword');password.hidden=!custom;if(!custom)password.value=''}function slotHeaders(){return {'X-Slot-Password':document.querySelector('#slotChoice').value==='custom'?document.querySelector('#slotPassword').value:''}}function selectedSlots(){let choice=document.querySelector('#slotChoice').value,n=Number(choice==='custom'?document.querySelector('#customSlots').value:1);if(!Number.isSafeInteger(n)||n<1){alert('Enter a positive whole number of slots.');return null}if(choice==='custom'&&!document.querySelector('#slotPassword').value){alert('Enter the password for custom slots.');return null}return n}async function processPath()", 1)
    for action in ('processPath', 'processUpload', 'processImages'):
        ui_script = ui_script.replace('async function '+action+'(){', 'async function '+action+'(){let slots=selectedSlots();if(slots===null)return;', 1)
    ui_script = ui_script.replace("'/api/process/path?source_path='+encodeURIComponent(p)", "'/api/process/path?slots='+slots+'&source_path='+encodeURIComponent(p)")
    ui_script = ui_script.replace("fetch('/api/process/upload',", "fetch('/api/process/upload?slots='+slots,")
    ui_script = ui_script.replace("fetch('/api/process/images',", "fetch('/api/process/images?slots='+slots,")
    ui_script = ui_script.replace("{method:'POST'", "{method:'POST',headers:slotHeaders()")
    ui_script = ui_script.replace("jobLog.textContent=j.logs||'No logs yet.';jobLog.scrollTop=jobLog.scrollHeight", "jobLog.textContent=renderBatchDashboard(j);updateSlotView(j)")
    ui_script = ui_script.replace("fetch('/api/process/status')", "fetch('/api/process/status',{cache:'no-store',signal:AbortSignal.timeout(8000)})")
    ui_script = ui_script.replace('setInterval(showJob,1500)', "setInterval(()=>showJob().catch(()=>{let t=document.querySelector('#slotUpdated');if(t)t.textContent='Connection lost - retrying...'}),1000)")
    ui_script = ui_script.replace('setInterval(showJob,1500)', 'setInterval(showJob,1000)')
    page = page.replace('</style>', '.processor{width:1040px;right:-1100px;box-sizing:border-box}.processor #jobLog{white-space:pre;max-height:55vh;overflow:auto;font:12px/1.5 Consolas,monospace}.processor .resume-row{flex-wrap:wrap}.processor .resume-row select{min-width:180px}</style>', 1)
    ui_script = ui_script.replace("No held jobs</option>", "No held batches</option>", 1)
    ui_script = ui_script.replace("resumeButton.disabled=!heldJobs.value", "resumeButton.disabled=!heldJobs.value;document.querySelector('#deleteHeldButton').disabled=!heldJobs.value")
    ui_script = ui_script.replace("heldJobs.onchange=()=>", "heldJobs.onchange=()=>{").replace(";showJob();setInterval", "};showJob();setInterval")
    ui_script = ui_script.replace("async function resumeProcess()", "async function deleteHeldProcess(){let id=heldJobs.value;if(!id)return;let label=heldJobs.selectedOptions[0].textContent;if(!confirm('Delete held batch: '+label+'? This removes its saved queue entries. PDFs, images and OCR output are kept. You cannot resume deleted entries.'))return;try{let r=await fetch('/api/process/held?job_id='+encodeURIComponent(id),{method:'DELETE'});if(!r.ok){let e=await r.json();alert(e.detail||'Could not delete held batch.')}await showJob()}catch(e){alert('Could not delete held batch. Check the server connection.')}}async function resumeProcess()", 1)
    ui_script = ui_script.replace(
        "async function holdProcess(){if(!confirm('Hold the current job? Completed searchable PDFs and page work will remain saved.'))return;let r=await fetch('/api/process/hold',{method:'POST'});if(!r.ok)return alert((await r.json()).detail||'Could not hold processing.');showJob()}",
        "async function holdProcess(){if(!confirm('Hold the current job? Completed searchable PDFs and page work will remain saved.'))return;let heldBy=prompt('Enter your name for this held job. Leave blank to use this PC name.','');if(heldBy===null)return;let r=await fetch('/api/process/hold?held_by='+encodeURIComponent(heldBy.trim()),{method:'POST'});if(!r.ok)return alert((await r.json()).detail||'Could not hold processing.');showJob()}",
        1,
    )
    page += ui_script
    page += """<script>const validationStatus=document.querySelector('#validationStatus'),repairDataButton=document.querySelector('#repairDataButton');let repairPrompted=false;async function showValidation(){try{let j=await (await fetch('/api/integrity/status')).json();validationStatus.textContent=(j.state||'idle').toUpperCase()+': '+(j.message||'')+' ('+(j.checked||0)+'/'+(j.total||0)+')';repairDataButton.disabled=(j.state==='running'||!(j.needs_repair>0));if(j.state==='running')repairPrompted=false;if(j.state==='complete'&&j.needs_repair>0&&!repairPrompted){repairPrompted=true;if(confirm('Validation found '+j.needs_repair+' PDF record(s) needing repair. Start repair now?'))runDataRepair(true)}}catch(e){validationStatus.textContent='Validation service unavailable.'}}async function runDataValidate(){let r=await fetch('/api/integrity/validate',{method:'POST'});if(!r.ok)return alert('Could not start validation.');showValidation()}async function runDataRepair(confirmed=false){if(!confirmed&&!confirm('Repair only missing searchable PDFs, JPG pages, and OCR records? Existing valid files will not be redone.'))return;let r=await fetch('/api/integrity/repair',{method:'POST'});if(!r.ok)return alert('Could not start repair.');showValidation()}async function deletePdf(folder,name){if(!confirm('Permanently delete '+name+' and all of its searchable PDF, JPG images, OCR data, Trash files, and database record? This cannot be restored.'))return;let r=await fetch('/api/pdf/delete?folder='+encodeURIComponent(folder),{method:'POST'});if(!r.ok)return alert((await r.json()).detail||'Could not delete PDF data.');await loadLiveGallery()}showValidation();setInterval(showValidation,2000)</script>"""
    page += """<script>const processorPanel=document.querySelector('#processorPanel'),processToggle=document.querySelector('#processToggle'),processClose=document.querySelector('#processClose');processToggle.onclick=()=>processorPanel.classList.toggle('open');processClose.onclick=()=>processorPanel.classList.remove('open')</script>"""
    page += """<script>function syncSourceOptions(){for(const [option,section] of [['folderOption','folderSource'],['pdfOption','pdfSource'],['imageOption','imageSource']])document.querySelector('#'+section).hidden=!document.querySelector('#'+option).checked}function chooseSource(option){document.querySelector('#'+option).checked=true;syncSourceOptions()}document.querySelectorAll('.source-options input').forEach(input=>input.addEventListener('change',syncSourceOptions));document.querySelector('#pdfUpload').addEventListener('change',()=>chooseSource('pdfOption'));document.querySelector('#imageUpload').addEventListener('change',()=>chooseSource('imageOption'));syncSourceOptions()</script>"""
    page += """<script>let liveGalleryTimer,liveGalleryRequest=0,galleryPrimedTab=null,gallerySignature='';async function loadLiveGallery(){let request=++liveGalleryRequest,params=new URLSearchParams({trash:String(tab==='trash')});try{if(galleryPrimedTab!==tab){let first=await fetch('/api/gallery?'+new URLSearchParams({trash:String(tab==='trash'),limit:'120'}));if(first.ok){let firstCards=await first.json();if(request!==liveGalleryRequest)return;data=firstCards;render()}}let response=await fetch('/api/gallery?'+params);if(!response.ok)throw Error('Gallery request failed');let text=await response.text();if(request!==liveGalleryRequest)return;galleryPrimedTab=tab;let signature=tab+':'+text.length+':'+text.slice(0,200)+text.slice(-200);if(signature===gallerySignature&&data.length>120)return;gallerySignature=signature;data=JSON.parse(text);render()}catch(error){if(request===liveGalleryRequest){count.textContent='Could not refresh the live gallery.';grid.innerHTML='<div class=\"empty\">The gallery service is unavailable.</div>'}}}function refreshLiveGallery(){clearTimeout(liveGalleryTimer);liveGalleryTimer=setTimeout(loadLiveGallery,250)}q.oninput=refreshLiveGallery;viewBy.onchange=()=>{selectedPdf=null;render()};document.querySelectorAll('[data-tab]').forEach(button=>button.onclick=()=>{tab=button.dataset.tab;selectedPdf=null;document.querySelectorAll('[data-tab]').forEach(item=>item.classList.toggle('on',item===button));loadLiveGallery()});loadLiveGallery();setInterval(()=>loadLiveGallery(),30000)</script>"""
    page += """<script>const pdfFilter=document.querySelector('#pdfFilter');function fillFilter(select,values,label){let chosen=select.value,items=[...new Set(values.filter(Boolean))].sort((a,b)=>String(a).localeCompare(String(b)));select.innerHTML='<option value="">'+label+'</option>';for(let value of items){let option=document.createElement('option');option.value=value;option.textContent=value;select.append(option)}if(items.includes(chosen))select.value=chosen}function statusOf(card){return card.processing?'processing':card.searchable_pdf?'ready':'missing'}function newestFirst(a,b){return String(b.date||'').localeCompare(String(a.date||''))||(Date.parse(b.processed_at)||0)-(Date.parse(a.processed_at)||0)||String(b.pdf||'').localeCompare(String(a.pdf||''))||Number(a.page||0)-Number(b.page||0)}function applyFilters(cards){let text=q.value.trim().toLowerCase();return cards.filter(card=>(!pdfFilter.value||card.pdf===pdfFilter.value)&&(!text||[card.pdf,card.name,card.text].some(value=>String(value||'').toLowerCase().includes(text)))).sort(newestFirst)}const galleryRender=render;render=function(){let allCards=data;fillFilter(pdfFilter,allCards.map(card=>card.pdf),'All PDF files');data=applyFilters(allCards);galleryRender();data=allCards};function rerenderForFilter(){render()}for(let input of [pdfFilter])input.addEventListener('input',rerenderForFilter);q.oninput=rerenderForFilter;</script>"""
    page += """<style>.nested-pdf-title{grid-column:1/-1;margin:8px 0 -6px;padding-top:10px;border-top:1px solid #e3e6ea;font-size:14px;font-weight:bold;color:#3c4043}</style><script>
const viewModeButtons={all:document.querySelector('#viewAllButton'),pdf:document.querySelector('#viewPdfButton'),date:document.querySelector('#viewDateButton')};
let pdfViewSelected=false,dateViewSelected=false;
function currentViewMode(){
  return pdfViewSelected&&dateViewSelected?'date-pdf':pdfViewSelected?'pdf':dateViewSelected?'date':'all';
}
function updateViewButtons(){
  viewModeButtons.all.classList.toggle('on',!pdfViewSelected&&!dateViewSelected);
  viewModeButtons.pdf.classList.toggle('on',pdfViewSelected);
  viewModeButtons.date.classList.toggle('on',dateViewSelected);
}
function pdfKey(card){return card.pdf_folder||card.company+'/'+card.pdf;}
function makePdfBox(items){
  const first=items[0],box=document.createElement('article'),button=document.createElement('button');
  box.className='pdf-card';button.className='pdf-open';button.type='button';
  const icon=document.createElement('div');icon.className='pdf-icon';icon.textContent='📄';
  const title=document.createElement('div');title.className='pdf-title';addText(title,first.pdf,q.value.trim());
  const meta=document.createElement('div');meta.className='pdf-meta';
  const pages=items.filter(item=>!item.processing);
  const searching=Boolean(q.value.trim());
  meta.textContent=first.company+' · '+pages.length+(searching?' matching images':' page images')+(first.processing?' · Processing':'');
  const show=document.createElement('div');show.className='pdf-meta';show.style.cssText='color:#1967d2;font-weight:bold;margin-top:6px';show.textContent='Show images';
  button.append(icon,title,meta,show);button.disabled=!pages.length;
  button.onclick=()=>{selectedPdf=pdfKey(first);render();};box.append(button);
  const searchable=items.find(item=>item.searchable_pdf)?.searchable_pdf;
  if(searchable){
    const link=document.createElement('a');link.className='pdf-download';link.href='/api/download?file='+encodeURIComponent(searchable);
    link.download=searchable.split('/').pop();link.textContent='Download searchable PDF';box.append(link);
  }
  if(first.pdf_folder){
    const del=document.createElement('button');del.className='pdf-delete';
    del.textContent='Delete this PDF data';del.onclick=()=>deletePdf(first.pdf_folder,first.pdf);box.append(del);
  }
  return box;
}
function renderPdfBrowser(){
  const available=data.filter(card=>Boolean(card.trash)===(tab==='trash'));
  fillFilter(pdfFilter,available.map(card=>card.pdf),'All PDF files');
  const filtered=applyFilters(available);
  grid.replaceChildren();
  if(selectedPdf){
    const pages=filtered.filter(card=>pdfKey(card)===selectedPdf&&!card.processing).sort((a,b)=>Number(a.page)-Number(b.page));
    const source=available.find(card=>pdfKey(card)===selectedPdf);
    count.textContent=pages.length+' matching page images in '+(source?.pdf||'selected PDF');
    const back=document.createElement('button');back.className='back';back.textContent='← Back to PDFs';
    back.onclick=()=>{selectedPdf=null;render();};count.append(back);
    appendCardsInPages(pages,q.value.trim());
    if(!pages.length){const empty=document.createElement('div');empty.className='empty';empty.textContent='No matching images in this PDF. Clear or change the search.';grid.append(empty);}
    return;
  }
  const pdfs=new Map();
  for(const card of filtered){
    const key=pdfKey(card);if(!pdfs.has(key))pdfs.set(key,[]);pdfs.get(key).push(card);
  }
  count.textContent=pdfs.size+' PDFs'+(dateViewSelected?' grouped by date':'');
  let lastDate=null;
  for(const items of pdfs.values()){
    if(dateViewSelected){
      const date=items[0].date||'Unknown date';
      if(date!==lastDate){const heading=document.createElement('h2');heading.className='group-title';heading.textContent=date;grid.append(heading);lastDate=date;}
    }
    grid.append(makePdfBox(items));
  }
  if(!pdfs.size){const empty=document.createElement('div');empty.className='empty';empty.textContent='No PDFs found.';grid.append(empty);}
}
const standardGalleryRender=render;
render=function(){
  if(tab==='trash'){
    if(pdfViewSelected||dateViewSelected){renderPdfBrowser();return;}
    standardGalleryRender();return;
  }
  const loadBox=document.querySelector('#loadImages');
  if(loadBox&&loadBox.checked&&q.value.trim()&&!selectedPdf){
    const mode=viewBy.value;viewBy.value='all';
    try{standardGalleryRender();}finally{viewBy.value=mode;}
    return;
  }
  if(!pdfViewSelected&&!dateViewSelected&&!selectedPdf){
    const mode=viewBy.value;viewBy.value='all';
    try{standardGalleryRender();}finally{viewBy.value=mode;}
    return;
  }
  renderPdfBrowser();
};
function applyViewSelection(){
  viewBy.value=currentViewMode();selectedPdf=null;updateViewButtons();render();
}
const combinedOption=document.createElement('option');
combinedOption.value='date-pdf';combinedOption.textContent='View by date and PDF';viewBy.append(combinedOption);
viewModeButtons.all.onclick=()=>{pdfViewSelected=false;dateViewSelected=false;applyViewSelection();};
viewModeButtons.pdf.onclick=()=>{pdfViewSelected=!pdfViewSelected;applyViewSelection();};
viewModeButtons.date.onclick=()=>{dateViewSelected=!dateViewSelected;applyViewSelection();};
</script>"""
    page += """<style>.group-filter{display:flex;align-items:center;gap:5px;padding:8px 10px;border:1px solid #d8dce0;border-radius:18px;background:#fff;cursor:pointer;white-space:nowrap}.group-filter:has(input:checked){border-color:#1a73e8;background:#e8f0fe;color:#1967d2}.group-filter input{margin:0;accent-color:#1a73e8}</style>"""
    page += """<script>const groupByPdf=document.querySelector('#groupByPdf'),groupByDate=document.querySelector('#groupByDate');function syncGroupingCheckboxes(){pdfViewSelected=groupByPdf.checked;dateViewSelected=groupByDate.checked;applyViewSelection()}groupByPdf.onchange=syncGroupingCheckboxes;groupByDate.onchange=syncGroupingCheckboxes;const loadImagesLabel=document.createElement('label');loadImagesLabel.className='group-filter';loadImagesLabel.innerHTML='<input type="checkbox" id="loadImages"> Load images';groupByDate.parentElement.after(loadImagesLabel);document.querySelector('#loadImages').onchange=()=>{selectedPdf=null;render()};</script>"""
    page += """<style>.card-image{cursor:zoom-in}.product-overlay{position:fixed;inset:0;z-index:30;display:flex;align-items:center;justify-content:center;padding:20px;background:#20212499}.product-modal{width:min(940px,100%);max-height:calc(100vh - 40px);overflow:auto;background:#fff;border-radius:14px;box-shadow:0 14px 40px #0008}.product-head{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;padding:16px 20px;border-bottom:1px solid #d8dce0}.product-title{margin:0;font-size:18px;word-break:break-word}.product-subtitle{margin-top:4px;color:#5f6368;font-size:13px}.product-close{border:0;background:none;color:#3c4043;font-size:26px;line-height:1;cursor:pointer}.product-body{display:grid;grid-template-columns:minmax(270px,1fr) minmax(300px,1fr);gap:20px;padding:20px}.product-image{width:100%;max-height:570px;object-fit:contain;background:#edf2f8}.product-meta{display:grid;grid-template-columns:105px 1fr;gap:8px 12px;margin:0;font-size:14px}.product-meta dt{color:#5f6368}.product-meta dd{margin:0;overflow-wrap:anywhere}.product-pdf-link{color:#1967d2;font-size:13px;text-decoration:none}.product-pdf-link:hover{text-decoration:underline}.product-ocr-label{display:block;margin:16px 0 7px;font-weight:bold}.product-ocr{box-sizing:border-box;width:100%;height:180px;resize:vertical;border:1px solid #d8dce0;border-radius:7px;padding:9px;background:#f8f9fa;color:#202124;font:13px/1.45 Consolas,monospace;white-space:pre-wrap}.product-actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}.product-action{padding:9px 12px;border:1px solid #d8dce0;border-radius:7px;background:#fff;color:#202124;font:14px Arial;cursor:pointer;text-decoration:none}.product-action.primary{border-color:#1a73e8;background:#1a73e8;color:#fff}.product-copy-status{min-height:16px;margin-top:8px;color:#5f6368;font-size:12px}@media(max-width:650px){.product-overlay{padding:0;align-items:stretch}.product-modal{max-height:100vh;border-radius:0}.product-body{grid-template-columns:1fr;padding:14px}.product-image{max-height:370px}.product-head{padding:14px}.product-meta{grid-template-columns:92px 1fr}}</style><div id=\"productView\" class=\"product-overlay\" hidden><section class=\"product-modal\" role=\"dialog\" aria-modal=\"true\" aria-labelledby=\"productTitle\"><header class=\"product-head\"><div><h2 id=\"productTitle\" class=\"product-title\"></h2><div id=\"productSubtitle\" class=\"product-subtitle\"></div></div><button id=\"productClose\" class=\"product-close\" type=\"button\" aria-label=\"Close image details\">×</button></header><div class=\"product-body\"><img id=\"productImage\" class=\"product-image\" alt=\"\"><div><dl class=\"product-meta\"><dt>Company</dt><dd id=\"productCompany\"></dd><dt>Source PDF</dt><dd id=\"productPdf\"></dd><dt>Page</dt><dd id=\"productPage\"></dd><dt>Searchable PDF</dt><dd><span id=\"productSearchableName\"></span><br><a id=\"productPdfPage\" class=\"product-pdf-link\" target=\"_blank\" rel=\"noopener\">Open PDF at this page ↗</a></dd></dl><label class=\"product-ocr-label\" for=\"productOcr\">Full OCR text</label><textarea id=\"productOcr\" class=\"product-ocr\" readonly></textarea><div class=\"product-actions\"><button id=\"productCopy\" class=\"product-action primary\" type=\"button\">Copy OCR text</button><a id=\"productImageDownload\" class=\"product-action\">Download JPG</a><a id=\"productPdfDownload\" class=\"product-action\">Download PDF</a></div><div id=\"productCopyStatus\" class=\"product-copy-status\" aria-live=\"polite\"></div></div></div></section></div><script>const productView=document.querySelector('#productView'),productClose=document.querySelector('#productClose'),productImage=document.querySelector('#productImage'),productTitle=document.querySelector('#productTitle'),productSubtitle=document.querySelector('#productSubtitle'),productCompany=document.querySelector('#productCompany'),productPdf=document.querySelector('#productPdf'),productPage=document.querySelector('#productPage'),productSearchableName=document.querySelector('#productSearchableName'),productPdfPage=document.querySelector('#productPdfPage'),productOcr=document.querySelector('#productOcr'),productCopy=document.querySelector('#productCopy'),productImageDownload=document.querySelector('#productImageDownload'),productPdfDownload=document.querySelector('#productPdfDownload'),productCopyStatus=document.querySelector('#productCopyStatus');function productMedia(file){return '/media/'+encodeURI(file)}function productDownload(file){return '/api/download?file='+encodeURIComponent(file)}function closeProductView(){productView.hidden=true}function openProductView(item){let source=item.source_pdf||item.searchable_pdf||'',searchable=item.searchable_pdf||'';productTitle.textContent=item.name||'Image details';productSubtitle.textContent=(item.pdf||'Source PDF')+' · Page '+(item.page||'');productImage.src=productMedia(item.image);productImage.alt=item.name||'Document image';productCompany.textContent=item.company||'Unmatched company';productPdf.textContent=item.pdf||source.split('/').pop()||'Unavailable';productPage.textContent=item.page||'';productSearchableName.textContent=searchable?searchable.split('/').pop():'Unavailable';productPdfPage.hidden=!searchable;if(searchable)productPdfPage.href=productMedia(searchable)+'#page='+encodeURIComponent(item.page);productOcr.value=item.text||'No readable text';productCopyStatus.textContent='';productImageDownload.href=productDownload(item.image);productImageDownload.download=item.name||'image.jpg';productPdfDownload.hidden=!source;if(source){productPdfDownload.href=productMedia(source);productPdfDownload.download=source.split('/').pop()}productView.hidden=false;productClose.focus()}productClose.onclick=closeProductView;productView.addEventListener('click',event=>{if(event.target===productView)closeProductView()});document.addEventListener('keydown',event=>{if(event.key==='Escape'&&!productView.hidden)closeProductView()});productCopy.onclick=async()=>{productOcr.select();try{await navigator.clipboard.writeText(productOcr.value);productCopyStatus.textContent='OCR text copied.'}catch(error){document.execCommand('copy');productCopyStatus.textContent='OCR text selected — press Ctrl+C if it was not copied automatically.'}}</script>"""
    page = page.replace(
        '<img id="productImage" class="product-image" alt="">',
        '<div id="productImageViewport" class="product-image-viewport">'
        '<div id="productImageStage" class="product-image-stage"><img id="productImage" class="product-image" alt=""></div>'
        '<button id="productRotate" class="product-rotate" type="button" aria-label="Rotate image clockwise" title="Rotate clockwise">↻</button></div>',
        1,
    )
    page = page.replace(
        '<div class="product-actions"><button id="productZoomOut" class="product-action" type="button" aria-label="Zoom out">−</button><span id="productZoomLabel" class="product-zoom-label">100%</span><button id="productZoomIn" class="product-action" type="button" aria-label="Zoom in">+</button><button id="productZoomReset" class="product-action" type="button">Fit width</button><button id="productCopy" class="product-action primary" type="button">Copy OCR text</button>',
        '<div class="product-actions"><button id="productCopy" class="product-action primary" type="button">Copy OCR text</button>',
        1,
    )
    page = page.replace(
        "productCopyStatus=document.querySelector('#productCopyStatus');",
        "productCopyStatus=document.querySelector('#productCopyStatus'),productImageViewport=document.querySelector('#productImageViewport'),productImageStage=document.querySelector('#productImageStage'),productRotate=document.querySelector('#productRotate');"
        "let productZoom=1,productRotation=0;function updateProductImageLayout(){if(!productImage.naturalWidth)return;let width=productImageViewport.clientWidth*productZoom,height=width*productImage.naturalHeight/productImage.naturalWidth,sideways=productRotation%180!==0;productImageStage.style.width=(sideways?height:width)+'px';productImageStage.style.height=(sideways?width:height)+'px';productImage.style.width=width+'px';productImage.style.left=(sideways?(height-width)/2:0)+'px';productImage.style.top=(sideways?(width-height)/2:0)+'px';productImage.style.transform='rotate('+productRotation+'deg)'}function setProductZoom(value){productZoom=Math.max(.75,Math.min(5,value));updateProductImageLayout()}productImage.addEventListener('load',updateProductImageLayout);",
        1,
    )
    page = page.replace(
        "productCopyStatus.textContent='';productImageDownload.href=productDownload(item.image);",
        "productCopyStatus.textContent='';productRotation=0;productImageViewport.scrollTop=0;productImageViewport.scrollLeft=0;setProductZoom(1);"
        "productImageDownload.href=productDownload(item.image);",
        1,
    )
    page = page.replace(
        "productCopy.onclick=async()=>",
        "function zoomAtPointer(event){let bounds=productImageViewport.getBoundingClientRect(),pointerX=event.clientX-bounds.left,"
        "pointerY=event.clientY-bounds.top,contentX=pointerX+productImageViewport.scrollLeft,contentY=pointerY+productImageViewport.scrollTop,"
        "nextZoom=Math.max(.75,Math.min(5,productZoom+(event.deltaY<0?.25:-.25))),scale=nextZoom/productZoom;"
        "setProductZoom(nextZoom);productImageViewport.scrollLeft=contentX*scale-pointerX;productImageViewport.scrollTop=contentY*scale-pointerY}"
        "let productPan=null;productImageViewport.addEventListener('pointerdown',event=>{if(event.target===productRotate)return;event.preventDefault();productPan={x:event.clientX,y:event.clientY,left:productImageViewport.scrollLeft,top:productImageViewport.scrollTop};productImageViewport.classList.add('panning');productImageViewport.setPointerCapture(event.pointerId)});"
        "productImageViewport.addEventListener('pointermove',event=>{if(!productPan)return;event.preventDefault();productImageViewport.scrollLeft=productPan.left-(event.clientX-productPan.x)*1.5;productImageViewport.scrollTop=productPan.top-(event.clientY-productPan.y)*1.5});"
        "function endProductPan(){productPan=null;productImageViewport.classList.remove('panning')}productImageViewport.addEventListener('pointerup',endProductPan);productImageViewport.addEventListener('pointercancel',endProductPan);productRotate.onclick=event=>{event.stopPropagation();productRotation=(productRotation+90)%360;updateProductImageLayout()};"
        "productImageViewport.addEventListener('wheel',event=>{event.preventDefault();zoomAtPointer(event)},{passive:false});productCopy.onclick=async()=>",
        1,
    )
    page += """<style>.product-modal{width:min(1320px,100%)}.product-body{grid-template-columns:minmax(500px,2.1fr) minmax(280px,1fr)}.product-image-viewport{position:relative;height:calc(100vh - 180px);min-height:500px;overflow:auto;background:#edf2f8;cursor:grab;touch-action:none;scrollbar-width:none}.product-image-viewport::-webkit-scrollbar{display:none}.product-image-viewport.panning{cursor:grabbing}.product-image-stage{position:relative;margin:auto;min-width:100%;min-height:100%}.product-image{position:absolute;display:block;max-height:none;height:auto;object-fit:initial;user-select:none;-webkit-user-drag:none;transform-origin:center}.product-rotate{position:absolute;z-index:2;top:12px;right:12px;width:38px;height:38px;border:1px solid #d8dce0;border-radius:50%;background:#fff;color:#202124;font-size:22px;line-height:1;cursor:pointer;box-shadow:0 1px 4px #20212455}.product-rotate:hover{background:#f1f3f4}@media(max-width:650px){.product-image-viewport{height:55vh;min-height:320px}.product-body{grid-template-columns:1fr}}</style>"""
    page += """<style>#acc-panel-link{position:fixed;right:16px;top:16px;z-index:20;padding:12px 10px;border:1px solid #0b57d0;border-radius:10px;background:#1a73e8;color:#fff;font:600 14px Arial,sans-serif;text-decoration:none;box-shadow:0 3px 10px #20212455}#acc-panel-link:hover{background:#0b57d0}</style><a id=\"acc-panel-link\" href=\"http://192.168.2.14:8040/\" target=\"_blank\" rel=\"noopener noreferrer\" title=\"Open Acc Panel in a new tab\">Acc Panel</a>"""
    page += """<style>
body>header{z-index:4;flex-wrap:wrap;padding-right:115px}
main:has(>.processor.open){display:grid;grid-template-columns:minmax(0,1fr) 310px;grid-template-rows:auto 1fr;column-gap:20px;align-items:start}
main:has(>.processor.open)>#count{grid-column:1;grid-row:1}
main:has(>.processor.open)>#grid{grid-column:1;grid-row:2;min-width:0}
main>.processor{display:none;position:static;transition:none;box-sizing:border-box}
main>.processor.open{display:block;position:sticky;top:var(--panel-top,100px);left:auto;right:auto;width:310px;max-width:100%;max-height:calc(100dvh - var(--panel-top,100px) - 16px);grid-column:2;grid-row:1/3;margin:0;padding:14px;overflow:auto;box-shadow:0 1px 4px #ccd0d5;z-index:1}
.processor .process-head strong{font-size:15px}.processor .process-head span{line-height:1.45}
.processor>div:not(.process-head){flex-wrap:wrap}
.processor input,.processor select,.processor button{box-sizing:border-box;font-size:12px;max-width:100%}
.processor input[type=file]{width:100%;padding:8px 0;border:0}
.processor #slotChoice,.processor #customSlots,.processor #sourcePath{width:100%;flex-basis:100%}
.processor .source-options{display:flex;flex-direction:column;gap:9px}
.processor #folderSource,.processor #pdfSource,.processor #imageSource{flex-direction:column;align-items:stretch}
.processor #folderSource button,.processor #pdfSource button,.processor #imageSource button{width:100%}
.processor details{border-top:1px solid #e4e7ec;margin-top:14px;padding-top:12px}
.processor summary{cursor:pointer;font-size:13px;font-weight:600;padding:4px 0;color:#344054}
.processor details>div{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
.processor .resume-row select{flex-basis:100%;width:100%;min-width:0}
.processor #validationStatus{font-size:12px;line-height:1.4;display:block}
.processor #jobLog{max-height:320px;white-space:pre;overflow:auto;font:11px/1.5 Consolas,monospace}
.processor #jobStatus{line-height:1.5;overflow-wrap:anywhere}
.slot-item{border:1px solid #e4e7ec;border-radius:6px;padding:8px;margin:6px 0;font-size:12px;overflow-wrap:anywhere}.slot-item small{display:block;margin-top:5px;color:#5f6368}.slot-item progress{width:100%;height:8px}.slot-updated{display:block;font-size:11px;color:#5f6368;margin:8px 0}.slot-list{max-height:300px;overflow:auto}.slots-dialog{width:min(1100px,90vw);max-height:85dvh;border:1px solid #d8dce0;border-radius:12px;padding:18px}.slots-dialog::backdrop{background:#20212466}.slots-dialog pre{overflow:auto;max-height:65dvh;background:#202124;color:#d7e3fc;padding:14px;font:12px/1.5 Consolas,monospace;white-space:pre}
@media(max-width:760px){main{padding:14px}main:has(>.processor.open){display:block}main>.processor.open{position:static;width:100%;max-height:none;margin-bottom:18px}.grid{grid-template-columns:repeat(auto-fill,minmax(200px,1fr))}}
</style><script>
// Group secondary actions without changing their IDs or event handlers.
function panelSection(title,nodes,open=false){let section=document.createElement('details'),summary=document.createElement('summary');summary.textContent=title;section.open=open;section.append(summary);nodes[0].before(section);nodes.forEach(n=>section.append(n));return section}
panelSection('Saved batches',[document.querySelector('.resume-row')]);
panelSection('Data checks',[document.querySelector('#repairDataButton').parentElement,document.querySelector('#validationStatus')]);
const slotSection=panelSection('Live slots & queue',[document.querySelector('#jobLog')],true);
jobLog.hidden=true;
const slotUpdated=document.createElement('span');slotUpdated.id='slotUpdated';slotUpdated.className='slot-updated';slotUpdated.textContent='Connecting...';
const slotList=document.createElement('section');slotList.className='slot-list';
const expandSlots=document.createElement('button');expandSlots.type='button';expandSlots.textContent='Expand full table';
slotSection.append(slotUpdated,slotList,expandSlots);
const slotsDialog=document.createElement('dialog');slotsDialog.className='slots-dialog';slotsDialog.setAttribute('aria-label','Live processing slots and queue');
const closeSlots=document.createElement('button');closeSlots.textContent='Close table';closeSlots.onclick=()=>slotsDialog.close();
const fullSlots=document.createElement('pre');slotsDialog.append(closeSlots,fullSlots);document.body.append(slotsDialog);
expandSlots.onclick=()=>{fullSlots.textContent=jobLog.textContent;slotsDialog.showModal()};
function updateSlotView(j){
 fullSlots.textContent=jobLog.textContent;
 slotUpdated.textContent='Updated '+new Date().toLocaleTimeString()+' - '+(j.active_slots||[]).length+' running / '+(j.slot_limit||10)+' slots';
 slotList.replaceChildren();
 const active=j.active_slots||[],queued=j.queued_jobs||[];
 for(const [i,x] of active.entries()){
   let card=document.createElement('article');card.className='slot-item';
   card.textContent='Slot '+(i+1)+' - '+String(x.source_path||'').split(/[\\\\/]/).pop();
   let detail=document.createElement('small');detail.textContent=x.phase==='image_scan'?'Image OCR: '+Math.max(0,(x.page_current||1)-1)+' / '+(x.page_total||'?')+' pages completed': 'Creating searchable PDF...';card.append(detail);
   let bar=document.createElement('progress');bar.max=100;if(x.phase==='image_scan')bar.value=x.progress||0;card.append(bar);slotList.append(card);
 }
 let waiting=document.createElement('p');waiting.textContent=queued.length+' PDFs waiting'+(!active.length?' - no PDFs currently running':'');slotList.append(waiting);
 for(const x of queued){let name=document.createElement('div');name.className='slot-item';name.textContent=String(x.source_path||'').split(/[\\\\/]/).pop();slotList.append(name)}
}
const panelHeader=document.querySelector('body>header');
new ResizeObserver(()=>document.documentElement.style.setProperty('--panel-top',(panelHeader.getBoundingClientRect().height+16)+'px')).observe(panelHeader);
processToggle.setAttribute('aria-controls','processorPanel');
function syncPanelAccess(){processToggle.setAttribute('aria-expanded',String(processorPanel.classList.contains('open')))}
new MutationObserver(syncPanelAccess).observe(processorPanel,{attributes:true,attributeFilter:['class']});syncPanelAccess();
processClose.setAttribute('aria-label','Close process panel');setTimeout(()=>showJob().catch(()=>{slotUpdated.textContent='Connection lost - retrying...'}),0);
</script>"""
    page += """<style>
/* Gallery header: a calm search row and a separate, aligned view toolbar. */
body>header{
  display:grid;grid-template-columns:150px minmax(0,1fr);gap:16px 24px;
  padding:20px 132px 14px 28px;background:#fffefd;
  border-bottom:1px solid #e8e5df;box-shadow:0 2px 10px #29251f04;
  align-items:center;font-family:Arial,sans-serif;
}
body>header h1{font-size:21px;letter-spacing:-.5px;white-space:nowrap}
body>header h1 a{color:#292722}
body>header .filter-bar{
  display:grid;grid-template-columns:minmax(220px,1fr) minmax(170px,240px) minmax(155px,200px);
  gap:12px;min-width:0;width:100%;align-items:end;
}
body>header .filter-slot,body>header .filter-slot.search-slot{min-width:0;gap:6px}
body>header .filter-slot label{font-size:10px;font-weight:600;letter-spacing:.7px;color:#77736b}
body>header .filter-slot input,body>header .filter-slot select{
  height:42px;min-width:0;border:1px solid #e2dfd8;border-radius:10px;
  background:#fffefd;color:#36332e;font-size:13px;transition:border-color .15s,box-shadow .15s;
}
body>header .search-slot input{
  padding:10px 14px 10px 39px;background:#f5f3ef;border-color:#f5f3ef;font-size:14px;
}
body>header .search-slot input::placeholder{color:#8b877e}
body>header .search-slot:after{bottom:11px;left:15px;color:#817b70;pointer-events:none}
body>header .filter-slot input:focus-visible,body>header .filter-slot select:focus-visible{
  outline:0;border-color:#aa8068;background:#fff;box-shadow:0 0 0 3px #aa80681a;
}
body>header .tabs{
  grid-column:1/-1;display:flex;align-items:center;gap:8px;flex-wrap:wrap;
  padding-top:12px;border-top:1px solid #eeece7;min-width:0;
}
body>header .tabs button,body>header .group-filter{
  box-sizing:border-box;min-height:34px;border:1px solid #e4e0d8;border-radius:8px;
  padding:7px 12px;background:transparent;color:#656056;font-size:12px;
  font-weight:500;line-height:18px;white-space:nowrap;transition:background .15s,border-color .15s;
}
body>header .group-filter{display:inline-flex;gap:7px;align-items:center}
body>header .group-filter input{width:14px;height:14px;margin:0;accent-color:#9c6b50}
body>header .tabs button:hover,body>header .group-filter:hover{background:#f4f1eb;border-color:#cdc6ba}
body>header .tabs .on,body>header .group-filter:has(input:checked){
  color:#1967d2;background:#e8f0fe;border-color:#1a73e8;
}
body>header .tabs button:focus-visible,body>header .group-filter:focus-within{
  outline:2px solid #aa8068;outline-offset:2px;
}
body>header #processToggle{margin-left:auto;color:#37332c;background:#f5f3ef}
#acc-panel-link{
  top:42px;right:28px;padding:10px 14px;border:1px solid #0b57d0;border-radius:9px;
  background:#1a73e8;color:#fff;box-shadow:0 3px 10px #20212455;font:600 12px/20px Arial,sans-serif;
}
#acc-panel-link:hover{background:#0b57d0;color:#fff}
@media(max-width:1100px){
  body>header{grid-template-columns:1fr;padding:18px 24px 12px;gap:14px}
  body>header h1{padding-right:110px}
  body>header .filter-bar{grid-template-columns:minmax(220px,1fr) minmax(150px,210px) minmax(140px,180px)}
  #acc-panel-link{top:12px;right:24px}
}
@media(max-width:650px){
  body>header{padding:16px 16px 12px;gap:12px}
  body>header .filter-bar{grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:10px}
  body>header .search-slot{grid-column:1/-1}
  body>header .tabs{gap:6px;padding-top:10px}
  body>header .tabs button,body>header .group-filter{padding:6px 9px}
  body>header #processToggle{margin-left:0}
  #acc-panel-link{right:16px;top:10px}
}
</style>"""
    page += """<style>
/* Keep the search and gallery actions together in one horizontal toolbar. */
body>header{
  display:flex;flex-wrap:nowrap;gap:14px;padding:16px 132px 16px 24px;
}
body>header h1{flex:0 0 auto;font-size:20px}
body>header .filter-bar{
  display:flex;flex:1 1 480px;min-width:240px;width:auto;gap:10px;align-items:center;
}
body>header .filter-slot.search-slot{flex:1 1 280px;min-width:140px}
body>header .filter-slot:not(.search-slot){flex:0 1 180px;min-width:100px;max-width:180px}
body>header .filter-slot label{
  position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;
  clip:rect(0,0,0,0);white-space:nowrap;border:0;
}
body>header .tabs{
  flex:0 0 auto;flex-wrap:nowrap;gap:6px;padding:0;border:0;grid-column:auto;
}
body>header .tabs button,body>header .group-filter{
  min-height:38px;padding:8px 10px;
}
body>header #processToggle{margin-left:0}
#acc-panel-link{top:17px;right:20px}
@media(max-width:1200px){
  body>header{gap:10px;padding-left:16px}
  body>header h1{font-size:18px}
  body>header .filter-bar{min-width:190px}
  body>header .tabs button,body>header .group-filter{padding:8px 7px}
}
@media(max-width:980px){
  body>header{overflow-x:auto;padding:12px 16px;gap:12px}
  body>header h1{padding-right:0}
  body>header .filter-bar{flex:0 0 360px;min-width:360px}
  body>header .tabs{padding-right:105px}
  #acc-panel-link{top:13px;right:16px}
}
</style>"""
    # Encode path segments, not the whole URI: # and ? belong to filenames.
    page = page.replace("encodeURI(", "encodeGalleryPath(")
    page = page.replace("<script>", "<script>function encodeGalleryPath(path){return String(path).split('/').map(encodeURIComponent).join('/')}", 1)
    page += (Path(__file__).with_name("spreadsheet_gallery.html")).read_text(encoding="utf-8")
    page += (Path(__file__).with_name("process_extras.html")).read_text(encoding="utf-8")
    # Company fields are intentionally absent from the filename-based gallery.
    page = page.replace("x.company+' · '+x.pdf+' · page '+x.page", "x.pdf+' · page '+x.page")
    page = page.replace("items.length+' page image'+(items.length===1?'':'s')+' · '+items[0].company", "items.length+' page image'+(items.length===1?'':'s')")
    page = page.replace("card.pdf_folder||card.company+'/'+card.pdf", "card.pdf_folder||card.pdf")
    page = page.replace("first.company+' · '+pages.length+' page images'", "pages.length+' page images'")
    page = page.replace("<dt>Company</dt><dd id=\"productCompany\"></dd>", "")
    page = page.replace("productCompany.textContent=item.company||'Unmatched company';", "")
    (OUTPUT_ROOT / "index.html").write_text(page, encoding="utf-8")


def ocr_page(image_path: Path, provider: str, model: str) -> str:
    if provider == "pymupdf":
        return ""  # Text is collected directly from the PDF before rendering.
    if provider == "rapidocr":
        from app.services.ocr import extract_rapidocr_text
        return extract_rapidocr_text(image_path)
    from app.services.ocr import extract_page_text
    return extract_page_text(image_path, provider, model)


def create_searchable_pdf(source_pdf: Path, output_pdf: Path, page_lines: dict[int, list] | None = None, dpi: int = 200) -> None:
    """Make a separate searchable PDF from RapidOCR text; never change the source PDF."""
    from app.services.ocr import build_searchable_pdf
    build_searchable_pdf(source_pdf, output_pdf, page_lines, dpi)


def repair_searchable_pdfs() -> tuple[int, int]:
    """Create missing searchable PDFs for already processed gallery folders."""
    repaired = failed = 0
    for manifest_path in OUTPUT_ROOT.rglob("ocr-results.json"):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        folder = manifest_path.parent
        source_pdf = folder / Path(str(manifest.get("source_pdf", ""))).name
        preferred_name = str(manifest.get("searchable_pdf") or f"{safe_name(source_pdf.stem)} Searchable.pdf")
        searchable_pdf = folder / preferred_name
        existing = sorted(path for path in folder.glob("* Searchable.pdf") if path.is_file())
        if existing:
            if manifest.get("searchable_pdf") != existing[0].name:
                manifest["searchable_pdf"] = existing[0].name
                manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
            continue
        if not source_pdf.is_file():
            failed += 1
            print(f"Missing source PDF: {source_pdf}", file=sys.stderr, flush=True)
            continue
        try:
            print(f"Creating searchable PDF: {source_pdf.name}", flush=True)
            create_searchable_pdf(source_pdf, searchable_pdf)
            manifest["searchable_pdf"] = searchable_pdf.name
            manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
            repaired += 1
        except Exception as error:
            failed += 1
            print(f"Could not create searchable PDF for {source_pdf.name}: {error}", file=sys.stderr, flush=True)
    return repaired, failed


def prepare_searchable_pdf(pdf_path: Path, source_sha256: str | None = None) -> bool:
    """Create the work-folder searchable PDF before any JPG/OCR processing."""
    source_sha256 = source_sha256 or pdf_sha256(pdf_path)
    pdf_name = safe_name(pdf_path.stem)
    work_dir = OUTPUT_ROOT / "_Processing" / processing_key(pdf_path, source_sha256)
    pages_dir = work_dir / "pages"
    state_path = work_dir / "processing-state.json"
    work_dir.mkdir(parents=True, exist_ok=True)
    pages_dir.mkdir(exist_ok=True)
    try:
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else {}
    except json.JSONDecodeError:
        state = {}
    searchable_pdf = work_dir / f"{pdf_name} Searchable.pdf"
    state.update(source_pdf=pdf_path.name, source_path=str(pdf_path.resolve()), source_sha256=source_sha256, pages=state.get("pages", []), status="preparing_searchable")
    state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    # The searchable PDF is built from the page OCR results in process_pdf,
    # so every page is OCR'd only once. This phase only prepares the work folder.
    state.update(status="searchable_ready", searchable_pdf=searchable_pdf.name if searchable_pdf.is_file() else None)
    state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    return True


def process_pdf(pdf_path: Path, provider: str, model: str, dpi: int, source_sha256: str | None = None) -> None:
    pdf_name = safe_name(pdf_path.stem)
    source_sha256 = source_sha256 or pdf_sha256(pdf_path)
    document = fitz.open(pdf_path)
    try:
        # Save every completed page immediately. If the process is stopped, the
        # next run loads this state and continues with the first unfinished page.
        work_dir = OUTPUT_ROOT / "_Processing" / processing_key(pdf_path, source_sha256)
        pages_dir = work_dir / "pages"
        state_path = work_dir / "processing-state.json"
        work_dir.mkdir(parents=True, exist_ok=True)
        pages_dir.mkdir(exist_ok=True)
        if state_path.is_file():
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                state = {"source_pdf": pdf_path.name, "source_sha256": source_sha256, "pages": []}
        else:
            state = {"source_pdf": pdf_path.name, "source_sha256": source_sha256, "pages": []}
        work_searchable_pdf = work_dir / f"{pdf_name} Searchable.pdf"
        state.update(source_pdf=pdf_path.name, source_path=str(pdf_path.resolve()), source_sha256=source_sha256, status="processing")
        state["searchable_pdf"] = work_searchable_pdf.name if work_searchable_pdf.is_file() else None
        state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
        saved_pages = {int(item["page"]): item for item in state.get("pages", [])}
        matrix = fitz.Matrix(dpi / 72, dpi / 72)
        total_pages = len(document)
        for page_number, page in enumerate(document, start=1):
            if page_number in saved_pages and (pages_dir / f"page-{page_number:03d}.jpg").is_file():
                print(f"  Page {page_number}/{total_pages}: already complete — resuming next page.", flush=True)
                continue
            print(f"  Page {page_number}/{total_pages}: rendering and reading OCR...", flush=True)
            work_image = pages_dir / f"page-{page_number:03d}.jpg"
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            pixmap.save(work_image, output="jpeg", jpg_quality=90)
            embedded_text = page.get_text().strip()
            if len(embedded_text) >= EMBEDDED_TEXT_MIN_CHARS:
                # Born-digital page: the PDF already has real text, so skip OCR.
                lines, raw_ocr = [], ""
            elif provider == "rapidocr":
                from app.services.ocr import extract_rapidocr_lines
                lines = extract_rapidocr_lines(work_image)
                raw_ocr = "\n".join(line[4] for line in lines)
            else:
                lines, raw_ocr = None, ocr_page(work_image, provider, model)
            saved_pages[page_number] = {"page": page_number, "raw_ocr": raw_ocr, "pdf_text": page.get_text().strip(), "lines": lines}
            state["pages"] = [saved_pages[number] for number in sorted(saved_pages)]
            state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")

        draft_pages = [saved_pages[number] for number in sorted(saved_pages)]
        if not work_searchable_pdf.is_file():
            print("  Building searchable PDF from OCR results...", flush=True)
            try:
                create_searchable_pdf(pdf_path, work_searchable_pdf, {int(item["page"]): item["lines"] for item in draft_pages if item.get("lines") is not None}, dpi)
            except Exception as error:
                print(f"  Warning: searchable PDF was not created: {error}", file=sys.stderr, flush=True)
            state["searchable_pdf"] = work_searchable_pdf.name if work_searchable_pdf.is_file() else None
        job_dir = unique_folder(PDFS, pdf_name, source_sha256)
        existing_manifest = job_dir / "ocr-results.json"
        if existing_manifest.is_file():
            try:
                existing_hash = str(json.loads(existing_manifest.read_text(encoding="utf-8")).get("source_sha256", ""))
            except (OSError, json.JSONDecodeError):
                existing_hash = ""
            if existing_hash != source_sha256:
                job_dir = unique_folder(PDFS, processing_key(pdf_path, source_sha256), source_sha256)
        image_dir = job_dir / "Images"
        trash_dir = image_dir / "Trash"
        job_dir.mkdir(parents=True, exist_ok=True)
        image_dir.mkdir(parents=True, exist_ok=True)
        trash_dir.mkdir(exist_ok=True)
        target_pdf = job_dir / pdf_path.name
        if pdf_path.resolve() != target_pdf.resolve():
            shutil.copy2(pdf_path, target_pdf)
        searchable_pdf = job_dir / f"{pdf_name} Searchable.pdf"
        if work_searchable_pdf.is_file() and not searchable_pdf.is_file():
            shutil.copy2(work_searchable_pdf, searchable_pdf)
        elif not searchable_pdf.is_file():
            print("  Creating searchable PDF as a fallback...", flush=True)
            try:
                create_searchable_pdf(target_pdf, searchable_pdf, dpi=dpi)
            except Exception as error:
                print(f"  Warning: searchable PDF was not created: {error}", file=sys.stderr, flush=True)

        pages: list[dict[str, object]] = []
        for item in draft_pages:
            page_number = int(item["page"])
            image_name = f"{page_number:03d} {pdf_name}.jpg"
            shutil.copy2(pages_dir / f"page-{page_number:03d}.jpg", image_dir / image_name)
            raw_ocr = str(item["raw_ocr"])
            page_text = str(item["pdf_text"])
            searchable_text = raw_ocr or page_text
            pages.append({"page": page_number, "image": image_name, "raw_ocr": raw_ocr, "pdf_text": page_text, "searchable_text": searchable_text})

        manifest = {
            "source_pdf": pdf_path.name,
            "source_sha256": source_sha256,
            "images_folder": image_dir.relative_to(OUTPUT_ROOT).as_posix(),
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "ocr_provider": provider,
            "searchable_pdf": searchable_pdf.name if searchable_pdf.is_file() else None,
            "pages": pages,
        }
        manifest_path = job_dir / "ocr-results.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        # Lightweight registry update for newly completed PDFs. The optional
        # manual DataValidate action performs the full repair audit later.
        from app.services.integrity import record_manifest
        record_manifest(manifest_path)
        state["status"] = "complete"
        state["completed_at"] = datetime.now(timezone.utc).isoformat()
        state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Done: {pdf_path.name} -> {job_dir}")
        # Final JPGs, OCR manifest, original, and searchable PDF are safely in
        # the filename-based folders now. Keep _Processing only for unfinished/held
        # work; completed jobs do not need a second copy.
        try:
            shutil.rmtree(work_dir)
        except OSError as error:
            # The final result is valid even if Windows temporarily locks a
            # temporary file; the next cleanup pass can remove this cache.
            print(f"  Note: completed temporary work will be cleaned later: {error}", flush=True)
    finally:
        document.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert all BOL PDFs to JPG pages and OCR records.")
    parser.add_argument("source", type=Path, nargs="?", default=None, help="Folder containing PDFs (subfolders are scanned). If omitted, the script asks for it.")
    parser.add_argument("--pdf-file", type=Path, help="Process exactly this one PDF as an independent queue job.")
    parser.add_argument("--ocr-provider", choices=["rapidocr", "pymupdf", "openai", "anthropic", "gemini", "compatible"], default="rapidocr")
    parser.add_argument("--model", default="", help="Optional model override for cloud OCR providers.")
    parser.add_argument("--dpi", type=int, default=200, help="JPG resolution; 200 is a good OCR balance.")
    parser.add_argument("--repair-searchable", action="store_true", help="Create searchable PDFs missing from existing gallery folders.")
    parser.add_argument("--searchable-only", action="store_true", help="Create searchable PDFs for every source PDF, without rendering JPGs.")
    parser.add_argument("--images-only", action="store_true", help="Render JPGs and OCR pages after the searchable-PDF phase.")
    args = parser.parse_args()
    if args.searchable_only and args.images_only:
        parser.error("Choose either --searchable-only or --images-only, not both.")
    if args.repair_searchable:
        repaired, failed = repair_searchable_pdfs()
        generate_gallery()
        print(f"Searchable PDF repair complete: {repaired} created, {failed} failed.")
        return 0 if not failed else 1
    if args.pdf_file is not None:
        args.pdf_file = args.pdf_file.resolve()
        if not args.pdf_file.is_file() or args.pdf_file.suffix.casefold() != ".pdf":
            parser.error("--pdf-file must name an existing PDF.")
        args.source = args.pdf_file.parent
    elif args.source is None:
        supplied_path = input("Paste the folder path containing your PDF files: ").strip().strip('"')
        if not supplied_path:
            parser.error("A PDF folder path is required.")
        args.source = Path(supplied_path)
    if not args.source.is_dir():
        parser.error(f"Source folder does not exist: {args.source}")
    migrate_legacy_gallery()
    cleaned = cleanup_completed_processing()
    if cleaned:
        print(f"Removed {cleaned} completed temporary processing folder(s).", flush=True)
    pdfs = [args.pdf_file] if args.pdf_file is not None else [path for path in args.source.rglob("*.pdf") if is_processable_source_pdf(path)]
    if not pdfs:
        print("No PDFs found.")
        return 1
    processed_hashes: set[str] = set()
    for manifest_path in OUTPUT_ROOT.rglob("ocr-results.json"):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            source_sha256 = str(manifest.get("source_sha256", ""))
            # Upgrade older output records once, using their preserved original
            # PDF. This avoids filename-only duplicate decisions after update.
            if not source_sha256:
                original = manifest_path.parent / Path(str(manifest.get("source_pdf", ""))).name
                if original.is_file():
                    source_sha256 = pdf_sha256(original)
                    manifest["source_sha256"] = source_sha256
                    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
            if source_sha256:
                processed_hashes.add(source_sha256)
        except (OSError, json.JSONDecodeError):
            continue
    print(f"Found {len(pdfs)} PDF file(s). OCR provider: {args.ocr_provider}.", flush=True)
    if args.searchable_only:
        failures = 0
        for index, pdf in enumerate(pdfs, start=1):
            source_sha256 = pdf_sha256(pdf)
            if source_sha256 in processed_hashes:
                print(f"[{index}/{len(pdfs)}] Skipped (identical PDF already processed): {pdf.name}", flush=True)
                continue
            print(f"[{index}/{len(pdfs)}] Preparing searchable PDF: {pdf.name}", flush=True)
            failures += not prepare_searchable_pdf(pdf, source_sha256)
        generate_gallery()
        return 0 if not failures else 1
    for index, pdf in enumerate(pdfs, start=1):
        source_sha256 = pdf_sha256(pdf)
        if source_sha256 in processed_hashes:
            print(f"[{index}/{len(pdfs)}] Skipped (identical PDF already processed): {pdf.name}", flush=True)
            continue
        try:
            print(f"[{index}/{len(pdfs)}] Processing: {pdf.name}", flush=True)
            process_pdf(pdf, args.ocr_provider, args.model, args.dpi, source_sha256)
            processed_hashes.add(source_sha256)
        except Exception as error:
            print(f"FAILED: {pdf} — {error}", file=sys.stderr)
    generate_gallery()
    print(f"Gallery created: {OUTPUT_ROOT / 'index.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())





