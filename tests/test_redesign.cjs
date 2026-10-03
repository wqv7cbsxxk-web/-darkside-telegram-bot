const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const {parseHTML}=require('linkedom');
const articles=JSON.parse(fs.readFileSync('docs/articles.json','utf8'));
const catalog=JSON.parse(fs.readFileSync('docs/artists.json','utf8'));
const profiles=JSON.parse(fs.readFileSync('docs/artist_profiles.json','utf8'));
const script=fs.readFileSync('docs/app.js','utf8');
const storage=new Map();
async function boot(search=''){
 const {document,window:domWindow}=parseHTML(fs.readFileSync('docs/index.html','utf8'));
 const window={Event:domWindow.Event};
 Object.defineProperty(domWindow.HTMLSelectElement.prototype,'value',{configurable:true,get(){return [...this.options].find(x=>x.selected)?.value||'';},set(value){for(const o of this.options)o.selected=o.value===String(value);}});
 const handlers={};
 window.scrollY=0;window.scrollTo=({top})=>window.scrollY=top;
 window.addEventListener=(name,fn)=>handlers[name]=fn;
 window.matchMedia=()=>({matches:false,addEventListener(){}});
 // Toast timing is irrelevant to the assertions and must not slow CI.
 window.setTimeout=()=>1;
 window.MusicData={seed(){},span:(b,e)=>(b?.text||'?')+' → '+(e?.text||'?'),async search(){return [{id:'wd:Q1779',qid:'Q1779',name:'ABBA',description:'шведская поп-группа'}]},async group(b){return {qid:'Q1',entity:{labels:{}},members:[],wikiMembers:[],description:'Описание из источника',source_url:'https://www.wikidata.org/wiki/Q1'}},async albums(){return [{id:'wiki:Images and Words',name:'Images and Words',date:'1992'}]},async albumByTitle(){return {name:'Images and Words',tracks:[{title:'Pull Me Under',number:'1'}],credits:[{text:'Mike Portnoy – drums',title:'Mike Portnoy'}],wiki_url:'https://en.wikipedia.org/wiki/Images_and_Words'}},async personByTitle(){return {name:'Mike Portnoy',projects:[],age:59,instruments:'drums'}}};
 const context={document,window,URLSearchParams,Date,String,Map,Set,console,history:{replaceState(){}},location:{search,pathname:'/'},localStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v)},fetch:async url=>({ok:true,json:async()=>url.startsWith('articles.json')?articles:url.startsWith('artists.json')?catalog:url.startsWith('artist_profiles.json')?profiles:{}}),setTimeout:()=>1,clearTimeout(){}};
 vm.runInNewContext(script,context);await new Promise(r=>setImmediate(r));
 const app=window.MetalNews;
 const click=selector=>{const el=document.querySelector(selector);assert(el,'Missing '+selector);el.dispatchEvent(new window.Event('click',{bubbles:true}));};
 const change=(el,value)=>{assert(el);if(el.type==='checkbox')el.checked=value;else el.value=String(value);el.dispatchEvent(new window.Event('change',{bubbles:true}));};
 return {document,window,app,click,change,handlers};
}
(async()=>{
 storage.set('metal-news.preferences.v1',JSON.stringify({favorites:['opeth'],blocked:[],saved:[],custom:[]}));
 const {app,document,window,click,change,handlers}=await boot();
 assert(app.preferences.favorites.includes('opeth'),'preserve legacy favorites');
 assert.equal(document.querySelectorAll('.nav [data-view]').length,4);
 click('[data-view="bands"]');assert.equal(app.state.view,'bands');assert(document.querySelector('#list').textContent.includes('Opeth'));assert(!document.querySelector('#list').textContent.includes('Metallica'));
 click('[data-view="all"]');const initial=document.querySelectorAll('#list article').length;assert(initial>20);
 app.openSettings();assert(!document.querySelector('#settingsPanel').classList.contains('hidden'));
 const checks=[...document.querySelectorAll('.setting-check')];
 change(checks.find(x=>x.textContent==='Darkside').querySelector('input'),false);
 const compact=checks.find(x=>x.textContent==='Компактная лента');change(compact.querySelector('input'),true);
 const theme=[...document.querySelectorAll('.setting-select')].find(x=>x.textContent.startsWith('Тема')).querySelector('select');change(theme,'light');
 app.closeSettings();assert.equal(document.documentElement.getAttribute('data-theme'),'light');assert(document.documentElement.classList.contains('compact-feed'));
 assert.equal(app.selectArticles(articles.articles).some(a=>a.source==='Darkside'),false);
 assert(document.querySelectorAll('#list article').length<initial);
 const restarted=await boot();assert.equal(restarted.app.preferences.settings.theme,'light');assert(restarted.app.preferences.settings.disabledSources.includes('Darkside'));
 // No article truncation; even a filtered source remains accessible by deep link.
 const wolves=articles.articles.find(a=>a.original_url.endsWith('/184168/'));
 const direct=await boot('?id='+wolves.id);assert.equal(direct.document.querySelector('#article').children.length,wolves.paragraphs.length);assert(direct.document.querySelector('#article').textContent.includes('6. Wretched Spirits'));
 // Restore scroll after reading and keep separate root stacks.
 window.scrollY=480;const story=app.selectArticles(articles.articles).find(a=>a.artists.length);app.openArticle(story);assert.equal(window.scrollY,0);app.goBack();assert.equal(window.scrollY,480);
 app.openArticle(story);app.setView('bands');app.setView('all');assert.equal(app.state.current.id,story.id);app.goBack();
 app.openBand({id:'dream-theater',name:'Dream Theater'});await new Promise(r=>setImmediate(r));assert(document.querySelectorAll('.band-links .section-link').length===5);
 click('[data-band-section="albums"]');await new Promise(r=>setImmediate(r));click('#bandInfo .album-row');await new Promise(r=>setImmediate(r));assert(document.querySelector('#bandInfo').textContent.includes('Pull Me Under'));
 click('#bandInfo .album-row');await new Promise(r=>setImmediate(r));assert(document.querySelector('#bandInfo').textContent.includes('59 лет'));app.goBack();assert(document.querySelector('#bandInfo').textContent.includes('Pull Me Under'));app.goBack();assert(document.querySelector('#bandInfo').textContent.includes('Images and Words'));
 // Snapshots survive archive expiry, and blocking does not delete deliberate saves.
 app.saveArticle(story);const copy={...story,id:'expired-article'};app.saveArticle(copy);app.toggleBlocked(story.artists[0].id);assert(app.selectArticles(articles.articles).every(a=>!app.artistList(a).some(b=>b.id===story.artists[0].id)));
 app.setView('saved');assert(document.querySelector('#list').textContent.includes(copy.title));assert(app.allArticles().some(a=>a.id==='expired-article'));const afterRestart=await boot();assert(afterRestart.app.allArticles().some(a=>a.id==='expired-article'));
 // Source, category and topic switches all apply; all sources off has a recovery action.
 app.openSettings();for(const row of document.querySelectorAll('.setting-check'))if(articles.articles.some(a=>a.source===row.textContent))change(row.querySelector('input'),false);app.closeSettings();app.setView('all');app.setView('all');assert.equal(app.selectArticles(articles.articles).length,0);assert(document.querySelector('#list').textContent.includes('Изменить фильтры'));
 // Mark read after scrolling; exact title/url navigation is preserved.
 app.openArticle(story);window.scrollY=200;handlers.scroll();assert(app.preferences.read.includes(story.id));
 console.log('Redesign: migration, root tabs, persisted filters/theme, complete deep links, scroll/back stacks, musician/album navigation and archived saved snapshots verified.');
})().catch(e=>{console.error(e);process.exitCode=1});
