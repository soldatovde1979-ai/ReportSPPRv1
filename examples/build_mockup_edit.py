# ----------------------------------------------------------------------
# build_mockup_edit.py — копия макета для правки мышью (examples/mockup_report_v2.html → страница claude.ai)
# ЧТО: из готового макета делает страницу-артефакт: блоки перетаскиваются за ручку ⠿, ширина — на всю строку /
#      половина / треть, «в подвал» и обратно, перенос на другой слайд, комментарий к любому номеру. Правки хранятся
#      в базе страницы (capability db: edits/e-<номер>, layout/moves) — Claude читает их и вносит в настоящий макет.
#      Номера — постоянные номера макета (element_ids.json), по ним правка находит элемент.
# ПОЧЕМУ: my-FT Т-119 — «копия макета, где все элементы можно передвигать мышкой и оставлять комментарии, чтобы потом
#         ты посмотрел и внёс в настоящий макет»; ширина — выбор из трёх (рацпредложение, «ок»)
# Запуск (Linux / Bash):  python3 examples/build_mockup_edit.py [выходной.html]
# Публикация — инструментом Artifact с capabilities {db: {}, user: {}} (делает Claude).
# ----------------------------------------------------------------------
VERSION = "1.0"
SRC_FILE = "examples/mockup_report_v2.html"     # макет, из которого делается копия (собирает build_mockup_v2.py)
OUT_FILE = "examples/mockup_edit.html"          # по умолчанию; в git не кладётся (.gitignore)

import os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
out = sys.argv[1] if len(sys.argv) > 1 else OUT_FILE

src = open(SRC_FILE, encoding="utf-8").read()
head = re.search(r"<head>(.*?)</head>", src, re.S).group(1)
body = re.search(r"<body>(.*)</body>", src, re.S).group(1)
head = re.sub(r"<meta[^>]*>|<title>.*?</title>", "", head, flags=re.S)       # charset и viewport даёт оболочка страницы

EDIT_CSS = r"""<style>
/* ===== копия для правки (build_mockup_edit.py) ===== */
#tk-save,.tk-msg,.tk-form{display:none!important}
body.ed .enum{pointer-events:auto;cursor:pointer;opacity:1}
body.ed .enum.has-c{background:#C2255C;border-color:#C2255C;color:#fff}
.ed-bar{position:absolute;top:-12px;right:8px;z-index:4;display:none;gap:2px;padding:2px;border:1px solid var(--rule);border-radius:8px;background:var(--paper);box-shadow:0 2px 8px rgba(0,0,0,.15)}
.ed-u:hover>.ed-bar,.ed-u:focus-within>.ed-bar{display:flex}
.ed-bar button,.ed-bar select{font:12px var(--text);color:var(--ink2);background:transparent;border:0;border-radius:5px;padding:3px 6px;cursor:pointer}
.ed-bar button:hover{background:var(--wash);color:var(--ink)}.ed-bar .on{background:var(--t-blue);color:var(--c-blue)}
.ed-bar select{border:1px solid var(--rule);background:var(--paper);max-width:120px}
.ed-h{cursor:grab}.ed-drag{opacity:.45}
.ed-before{box-shadow:0 -4px 0 0 var(--c-blue)!important}.ed-after{box-shadow:0 4px 0 0 var(--c-blue)!important}
.ed-u[data-w="half"]{display:inline-block;vertical-align:top;width:calc(50% - 10px);margin-right:10px}
.ed-u[data-w="third"]{display:inline-block;vertical-align:top;width:calc(33.3% - 10px);margin-right:10px}
.ed-pop{position:fixed;z-index:20;width:min(420px,92vw);padding:12px;border-radius:10px;background:var(--paper);color:var(--ink);border:1px solid var(--rule);box-shadow:0 12px 40px rgba(0,0,0,.3)}
.ed-pop h4{font-size:13px;margin-bottom:6px}.ed-pop textarea{width:100%;min-height:96px;font:14px var(--text);padding:8px;border:1px solid var(--rule);border-radius:6px;background:var(--paper);color:var(--ink)}
.ed-pop .row{display:flex;gap:8px;justify-content:flex-end;margin-top:8px}
.ed-pop button,.ed-dock button{font:600 13px var(--text);padding:6px 12px;border-radius:6px;border:1px solid var(--rule);background:var(--wash);color:var(--ink);cursor:pointer}
.ed-pop button.pri,.ed-dock button.pri{background:var(--c-blue);border-color:var(--c-blue);color:#fff}
.ed-dock{position:fixed;right:max(16px,env(safe-area-inset-right,0px));bottom:calc(16px + env(safe-area-inset-bottom,0px));z-index:15;display:flex;gap:8px;align-items:center;
  padding:8px 10px;border-radius:10px;background:var(--paper);border:1px solid var(--rule);box-shadow:0 6px 24px rgba(0,0,0,.18);font-size:13px;color:var(--ink2)}
.ed-st{white-space:nowrap}.ed-st.ok{color:var(--c-ok)}.ed-st.err{color:var(--c-bad)}
.ed-help{position:fixed;right:max(16px,env(safe-area-inset-right,0px));bottom:calc(70px + env(safe-area-inset-bottom,0px));z-index:16;width:min(460px,92vw);max-height:70vh;overflow:auto;
  padding:14px 16px;border-radius:10px;background:var(--paper);color:var(--ink);border:1px solid var(--rule);box-shadow:0 12px 40px rgba(0,0,0,.25);font-size:13.5px}
.ed-help h3{font-size:15px;margin-bottom:8px}.ed-help ol{padding-left:18px;display:grid;gap:5px}.ed-help li b{color:var(--ink)}
.ed-help table{font-size:12.5px;margin-top:6px}.ed-help td{padding:4px 6px 4px 0}
@media (max-width:760px){.ed-u[data-w]{display:block;width:auto;margin-right:0}}
</style>"""

EDIT_JS = r"""<script>
// копия макета для правки (build_mockup_edit.py 1.0): правки — в базе страницы, номер элемента — постоянный (data-n)
document.addEventListener('DOMContentLoaded',()=>{
document.body.classList.add('ed');
const $=(s,r=document)=>r.querySelector(s),$$=(s,r=document)=>[...r.querySelectorAll(s)];
const slideOf=el=>el.closest('.slide'),units=()=>$$('.slide [data-n]').filter(el=>el.matches('.panel,.gbox,.kpi,.itile,.tc'));
const byN=n=>$('.slide [data-n="'+CSS.escape(n)+'"]');
const label=el=>((el.querySelector('h3,h4,span:not(.enum)')||{}).textContent||'').replace(/\s+/g,' ').trim().slice(0,80);
const SLIDES=$$('.slide').map(s=>[s.id,(s.querySelector('.sh h2')||{}).textContent||s.id]);
let db=null,moves=[],edits={},busy=0;
// ---- панель внизу справа: состояние сохранения, правки, инструкция
const dock=document.createElement('div');dock.className='ed-dock';
dock.innerHTML='<span class="ed-st">загрузка правок…</span><button type="button" data-a="list">Мои правки <b>0</b></button><button type="button" class="pri" data-a="help">Как отдать правки</button>';
document.body.appendChild(dock);const st=$('.ed-st',dock);
const say=(t,c)=>{st.textContent=t;st.className='ed-st '+(c||'')};
const help=document.createElement('div');help.className='ed-help';help.hidden=true;document.body.appendChild(help);
function count(){const n=Object.values(edits).filter(e=>e.comment||e.width||e.cellar||e.slide).length+moves.length;$('[data-a=list] b',dock).textContent=n;return n}
function showHelp(list){help.hidden=false;
 const rows=Object.values(edits).filter(e=>e.comment||e.width||e.cellar||e.slide).sort((a,b)=>a.n.localeCompare(b.n,'ru',{numeric:true}))
  .map(e=>'<tr><td><b>'+e.n+'</b></td><td>'+[e.width&&('ширина: '+({full:'вся строка',half:'половина',third:'треть'})[e.width]),e.cellar&&'в подвал',e.slide&&('на слайд '+e.slide),e.comment&&('«'+esc(e.comment)+'»')].filter(Boolean).join('; ')+'</td></tr>').join('')
  +moves.map(m=>'<tr><td><b>'+m.n+'</b></td><td>'+(m.pos==='before'?'перед ':'после ')+m.target+'</td></tr>').join('');
 help.innerHTML=(list?'<h3>Мои правки</h3>'+(rows?'<table><tbody>'+rows+'</tbody></table>':'<p>Правок пока нет.</p>'):
 '<h3>Как отдать правки Claude</h3><ol>'+
 '<li><b>Двигать.</b> Наведите на блок — справа сверху появится панель. Тяните за <b>⠿</b> выше или ниже другого блока этого слайда; синяя черта — куда встанет. На другой слайд — список «→ слайд».</li>'+
 '<li><b>Ширина.</b> ▭ — на всю строку, ½ — половина, ⅓ — треть.</li>'+
 '<li><b>Подвал.</b> ⤓ — убрать в подвал слайда, ⤒ — вернуть.</li>'+
 '<li><b>Комментарий.</b> Клик по номеру элемента (кружок в углу) или 💬 на панели; пишите, что изменить. Номер не меняется — по нему я найду элемент. Номера с комментарием — малиновые.</li>'+
 '<li><b>Сохранение — само</b>, после каждой правки («сохранено» внизу). Можно закрыть страницу и продолжить потом.</li>'+
 '<li><b>Готово?</b> Напишите мне в чате: «правки в макете готовы». Я прочитаю их здесь, пришлю план и внесу в настоящий макет. После этого правки отсюда уберу.</li></ol>'+
 '<p class="mut" style="margin-top:8px">Тексты внутри блоков мышью не правятся — только комментарием. Это копия: отчёт и макет в репозитории от неё не меняются.</p>')+
 '<div class="row" style="display:flex;justify-content:flex-end;margin-top:10px"><button type="button" data-a="close">Закрыть</button></div>'}
dock.addEventListener('click',e=>{const a=e.target.closest('[data-a]');if(!a)return;if(a.dataset.a==='help')showHelp(false);if(a.dataset.a==='list')showHelp(true)});
help.addEventListener('click',e=>{if(e.target.closest('[data-a=close]'))help.hidden=true});
const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'})[c]);
// ---- запись
async function save(fn){busy++;say('сохраняю…');try{if(db)await fn();say(db?'сохранено ✓':'не сохраняется: нет доступа к базе',db?'ok':'err')}
 catch(err){say('не сохранено: '+(err&&err.code||err),'err')}finally{busy--;count()}}
const editDoc=n=>db.collection('edits').doc('e-'+n);
function setEdit(n,patch){const el=byN(n);const e=Object.assign(edits[n]||{n,label:el?label(el):'',slide0:el&&slideOf(el)?slideOf(el).id:''},patch,{ts:Date.now()});
 edits[n]=e;return save(()=>editDoc(n).set(JSON.parse(JSON.stringify(e))))}
const saveMoves=()=>save(()=>db.doc('layout/moves').set({list:moves}));
// ---- применение правок к странице
function cellar(s){let d=s.querySelector('details.cellar');if(!d){d=document.createElement('details');d.className='cellar';d.innerHTML='<summary>Подвал слайда (правка)</summary>';s.appendChild(d)}return d}
function applyMove(m){const a=byN(m.n),b=byN(m.target);if(!a||!b||a.contains(b))return;b.parentNode.insertBefore(a,m.pos==='before'?b:b.nextSibling)}
function applyEdit(e){const el=byN(e.n);if(!el)return;
 if(e.width&&e.width!=='full')el.dataset.w=e.width;else delete el.dataset.w;
 if(e.slide){const s=document.getElementById(e.slide);if(s&&slideOf(el)!==s)s.appendChild(el)}
 if(e.cellar){const s=slideOf(el);if(s&&!el.closest('details.cellar'))cellar(s).appendChild(el)}
 const b=el.querySelector(':scope>.enum')||(el.previousElementSibling&&el.previousElementSibling.querySelector('.enum'));if(b)b.classList.toggle('has-c',!!e.comment);
 bar(el)}
// ---- панель над блоком
function bar(el){let b=el.querySelector(':scope>.ed-bar');if(!b){b=document.createElement('div');b.className='ed-bar';el.prepend(b);el.classList.add('ed-u')}
 const e=edits[el.dataset.n]||{},w=e.width||'full',inC=!!el.closest('details.cellar');
 b.innerHTML='<button type="button" class="ed-h" draggable="true" title="Перетащить">⠿</button>'+
  [['full','▭','На всю строку'],['half','½','Половина'],['third','⅓','Треть']].map(([k,t,h])=>'<button type="button" data-w="'+k+'" title="'+h+'"'+(w===k?' class="on"':'')+'>'+t+'</button>').join('')+
  '<button type="button" data-c="'+(inC?'out':'in')+'" title="'+(inC?'Вернуть из подвала':'Убрать в подвал')+'">'+(inC?'⤒':'⤓')+'</button>'+
  '<select title="Перенести на слайд"><option value="">→ слайд</option>'+SLIDES.map(([k,t])=>'<option value="'+k+'">'+esc(t.slice(0,40))+'</option>').join('')+'</select>'+
  '<button type="button" data-k title="Комментарий">💬</button>'}
// ---- комментарий
const pop=document.createElement('div');pop.className='ed-pop';pop.hidden=true;document.body.appendChild(pop);
function comment(el,x,y){const n=el.dataset.n,e=edits[n]||{};pop.hidden=false;
 pop.style.left=Math.min(x,innerWidth-440)+'px';pop.style.top=Math.min(y,innerHeight-220)+'px';
 pop.innerHTML='<h4>'+n+' · '+esc(label(el)||'элемент')+'</h4><textarea id="ed-txt" placeholder="Что изменить в этом элементе"></textarea>'+
  '<div class="row">'+(e.comment?'<button type="button" data-p="del">Удалить</button>':'')+'<button type="button" data-p="x">Отмена</button><button type="button" class="pri" data-p="ok">Сохранить</button></div>';
 const t=$('#ed-txt',pop);t.value=e.comment||'';t.focus();pop.dataset.n=n}
pop.addEventListener('click',e=>{const a=e.target.closest('[data-p]');if(!a)return;const n=pop.dataset.n;
 if(a.dataset.p==='ok')setEdit(n,{comment:$('#ed-txt',pop).value.trim()}).then(()=>applyEdit(edits[n]));
 if(a.dataset.p==='del')setEdit(n,{comment:''}).then(()=>applyEdit(edits[n]));pop.hidden=true});
document.addEventListener('click',e=>{
 const en=e.target.closest('.enum');if(en){const el=en.closest('[data-n]')||(en.closest('.enum-w')&&en.closest('.enum-w').nextElementSibling);if(el)comment(el,e.clientX,e.clientY);return}
 const b=e.target.closest('.ed-bar button');if(!b)return;const el=b.closest('[data-n]'),n=el.dataset.n;
 if(b.dataset.w)setEdit(n,{width:b.dataset.w==='full'?'':b.dataset.w}).then(()=>applyEdit(edits[n]));
 if(b.dataset.c==='in')setEdit(n,{cellar:true}).then(()=>applyEdit(edits[n]));
 if(b.dataset.c==='out'){const s=slideOf(el);const main=s.querySelector('details.cellar');if(main)main.before(el);setEdit(n,{cellar:false}).then(()=>applyEdit(edits[n]))}
 if(b.hasAttribute('data-k'))comment(el,e.clientX,e.clientY)});
document.addEventListener('change',e=>{const s=e.target.closest('.ed-bar select');if(!s||!s.value)return;const el=s.closest('[data-n]');
 setEdit(el.dataset.n,{slide:s.value,cellar:false}).then(()=>applyEdit(edits[el.dataset.n]))});
// ---- перетаскивание
let drag=null,mark=null;const clr=()=>{if(mark)mark.classList.remove('ed-before','ed-after');mark=null};
document.addEventListener('dragstart',e=>{const h=e.target.closest&&e.target.closest('.ed-h');if(!h)return;drag=h.closest('[data-n]');drag.classList.add('ed-drag');e.dataTransfer.effectAllowed='move';e.dataTransfer.setData('text/plain',drag.dataset.n)});
document.addEventListener('dragover',e=>{if(!drag)return;const t=e.target.closest&&e.target.closest('.ed-u');if(!t||t===drag||drag.contains(t)||t.contains(drag)||slideOf(t)!==slideOf(drag)){clr();return}
 e.preventDefault();const r=t.getBoundingClientRect(),pos=e.clientY<r.top+r.height/2?'ed-before':'ed-after';if(mark!==t)clr();mark=t;t.classList.remove('ed-before','ed-after');t.classList.add(pos)});
document.addEventListener('drop',e=>{if(!drag||!mark)return;e.preventDefault();const m={n:drag.dataset.n,target:mark.dataset.n,pos:mark.classList.contains('ed-before')?'before':'after',ts:Date.now()};
 clr();applyMove(m);moves.push(m);saveMoves()});
document.addEventListener('dragend',()=>{if(drag)drag.classList.remove('ed-drag');drag=null;clr()});
// ---- старт: панели на блоки, затем правки из базы
units().forEach(bar);
(async()=>{try{db=await claude.use('db')}catch(err){db=null}
 if(!db){say('правки не сохраняются: база недоступна в этом окне','err');count();return}
 try{const m=await db.doc('layout/moves').get();moves=m.exists?(m.data().list||[]).slice():[];moves.forEach(applyMove);
  const q=await db.collection('edits').get();q.docs.forEach(d=>{const v=d.data();edits[v.n]=Object.assign({},v)});Object.values(edits).forEach(applyEdit);
  say('правки загружены ✓','ok')}catch(err){say('правки не загружены: '+(err&&err.code||err),'err')}count()})();
});
</script>"""

page = ("<title>Макет для правки ReportSPPR</title>\n" + head + EDIT_CSS +
        body.replace('<div class="mock">', '<div class="mock"><b>Копия для правки мышью.</b> Наведите на блок, чтобы двигать; инструкция — кнопка внизу справа. ', 1)
        + EDIT_JS)
open(out, "w", encoding="utf-8").write(page)
print(f"Записана копия для правки {out}: {len(page) // 1024} КБ (из {SRC_FILE})")
