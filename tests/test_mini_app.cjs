const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const data=JSON.parse(fs.readFileSync('docs/articles.json','utf8'));
const catalog=JSON.parse(fs.readFileSync('docs/artists.json','utf8'));
const script=[...fs.readFileSync('docs/index.html','utf8').matchAll(/<script>([\s\S]*?)<\/script>/g)][0][1];
const profiles=JSON.parse(fs.readFileSync('docs/artist_profiles.json','utf8'));
const storage=new Map();
async function boot(article=null){
 const nodes=new Map();
 function element(){return {textContent:'',style:{},children:[],dataset:{},events:{},classList:{add(){},remove(){},toggle(){}},setAttribute(k,v){this[k]=v},removeAttribute(k){delete this[k]},addEventListener(k,v){this.events[k]=v},append(...els){this.children.push(...els)},replaceChildren(...els){this.children=[...els]},get lastChild(){return this.children.at(-1)}};}
 const sections=['news','tour','where','members','about'].map(name=>Object.assign(element(),{dataset:{bandSection:name}}));
 const document={documentElement:{style:{setProperty(){}}},getElementById(id){if(!nodes.has(id))nodes.set(id,element());return nodes.get(id)},createElement:element,querySelectorAll(selector){return selector==='[data-band-section]'?sections:[]},querySelector(){return element()}};
 const window={};const context={document,window,location:{search:article?'?id='+article.id:'',pathname:'/'},URLSearchParams,Date,String,console,history:{back(){},replaceState(){}},localStorage:{getItem(k){return storage.get(k)},setItem(k,v){storage.set(k,v)}},setTimeout(){throw Error('No retry expected')},async fetch(url){return {ok:true,json:async()=>url.startsWith('articles.json')?data:url.startsWith('artists.json')?catalog:profiles}}};
 vm.runInNewContext(script,context);await new Promise(resolve=>setImmediate(resolve));return {nodes,app:window.MetalNews,sections};
}
(async()=>{
 for(const a of [data.articles.find(a=>a.original_url.endsWith('/184168/')),data.articles.find(a=>a.original_url.includes('tom-morellos-power'))]){
  const {nodes}=await boot(a);assert.deepEqual(nodes.get('article').children.map(p=>p.textContent),a.paragraphs);
  assert.equal(nodes.get('title').textContent,a.title);
 }
 const {app,nodes,sections}=await boot();assert.ok(nodes.get('list').children.length);
 app.toggleFavorite('wolves-in-the-throne-room');
 let mine=app.selectArticles(data.articles,{view:'mine'});
 assert.equal(mine.length,1);assert.ok(mine[0].paragraphs[6].startsWith('6. Wretched Spirits'));
 const restarted=await boot();assert.ok(restarted.app.preferences.favorites.includes('wolves-in-the-throne-room'));
 assert.equal(restarted.app.selectArticles(data.articles,{view:'mine',topic:'releases'}).length,1);
 assert.equal(restarted.app.selectArticles(data.articles,{view:'mine',topic:'live'}).length,0);
 assert.equal(app.selectArticles(data.articles,{band:{id:'iron-maiden'}}).length,1);
 assert.equal(app.mention('Anthrax announced a show','Anthrax'),true);
 assert.equal(app.mention('toolbox','Tool'),false);
 app.toggleFavorite('wolves-in-the-throne-room');assert.equal(app.selectArticles(data.articles,{view:'mine'}).length,0);
 const events=app.upcomingEvents({events:[{date:'2026-10-01',city:'Past'},{date:'2026-10-03',city:'Future'}]},new Date('2026-10-02T02:00:00Z'));assert.equal(events.length,1);assert.equal(events[0].city,'Future');
 assert.ok(app.profileFor({id:'opeth'}).members.length);
 app.openBand({id:'opeth',name:'Opeth'});sections.find(s=>s.dataset.bandSection==='members').events.click();assert.ok(nodes.get('bandInfo').children.some(c=>c.children?.some(v=>v.textContent==='Mikael Åkerfeldt')));
 app.openBand({id:'deep-purple',name:'Deep Purple'});sections.find(s=>s.dataset.bandSection==='tour').events.click();assert.ok(nodes.get('bandInfo').children.length>10);
 sections.find(s=>s.dataset.bandSection==='where').events.click();assert.ok(nodes.get('bandInfo').children.some(c=>String(c.textContent).includes('Фактическое местоположение')));
 console.log('Mini App: full articles, favorites persistence, band pages, event filters and empty feed verified.');
})().catch(e=>{console.error(e);process.exitCode=1});
