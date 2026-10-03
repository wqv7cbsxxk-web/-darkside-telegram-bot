const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const data=JSON.parse(fs.readFileSync('docs/articles.json','utf8'));
const catalog=JSON.parse(fs.readFileSync('docs/artists.json','utf8'));
const html=fs.readFileSync('docs/index.html','utf8');
const script=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)][0][1];
for(const tag of html.matchAll(/<script\b[^>]*\bsrc=[^>]*>/g))assert.match(tag[0],/\b(?:async|defer)\b/,'a stalled script download must not block parsing or the inline news app');
const profiles=JSON.parse(fs.readFileSync('docs/artist_profiles.json','utf8'));
const seedJson=fs.readFileSync('docs/index.html','utf8').match(/<script id="articlesSeed" type="application\/json">([\s\S]*?)<\/script>/)[1];
const storage=new Map();
async function boot(article=null,initialSearch='',fetchImpl=null,telegram=null,storageUnavailable=false){
 const nodes=new Map();
 function element(){return {textContent:'',style:{},children:[],dataset:{},events:{},classList:{add(){},remove(){},toggle(){}},setAttribute(k,v){this[k]=v},removeAttribute(k){delete this[k]},addEventListener(k,v){this.events[k]=v},append(...els){this.children.push(...els)},replaceChildren(...els){this.children=[...els]},get lastChild(){return this.children.at(-1)}};}
 const sections=['news','tour','where','members','about'].map(name=>Object.assign(element(),{dataset:{bandSection:name}}));
 const document={documentElement:{style:{setProperty(){}}},getElementById(id){if(!nodes.has(id)){const el=element();if(id==='articlesSeed')el.textContent=seedJson;nodes.set(id,el)}return nodes.get(id)},createElement:element,querySelectorAll(selector){return selector==='[data-band-section]'?sections:[]},querySelector(){return element()}};
 document.head=element();
 const window={addEventListener(){},Telegram:telegram?{WebApp:telegram}:undefined};const context={document,window,location:{search:article?'?id='+article.id:initialSearch,pathname:'/'},URLSearchParams,Date,String,console,history:{back(){},replaceState(){}},localStorage:{getItem(k){if(storageUnavailable)throw Error('Storage denied');return storage.get(k)},setItem(k,v){if(storageUnavailable)throw Error('Storage denied');storage.set(k,v)}},setTimeout(){throw Error('No retry expected')},fetch:fetchImpl||async function(url){return {ok:true,json:async()=>url.startsWith('articles.json')?data:url.startsWith('artists.json')?catalog:profiles}}};
 vm.runInNewContext(script,context);await new Promise(resolve=>setImmediate(resolve));return {nodes,app:window.MetalNews,sections};
}
(async()=>{
 for(const a of [data.articles.find(a=>a.original_url.endsWith('/184168/')),data.articles.find(a=>a.original_url.includes('tom-morellos-power'))]){
  const {nodes}=await boot(a);assert.deepEqual(nodes.get('article').children.map(p=>p.textContent),a.paragraphs);
  assert.equal(nodes.get('title').textContent,a.title);
 }
 storage.delete('metal-news.articles.v1');
 const sdkUnavailable=await boot(null,'',()=>new Promise(()=>{}));assert.ok(sdkUnavailable.nodes.get('list').children.length,'cold startup must display bundled news while Telegram SDK and feed requests are unavailable');
 const sdkBroken=await boot(null,'',()=>new Promise(()=>{}),{ready(){throw Error('SDK unavailable')},expand(){throw Error('WebView unsupported')}});assert.ok(sdkBroken.nodes.get('list').children.length,'Telegram bridge errors must not abort app startup');
 const noStorage=await boot(null,'',()=>new Promise(()=>{}),null,true);assert.ok(noStorage.nodes.get('list').children.length,'denied local storage must not hide the bundled news feed');
 storage.set('metal-news.articles.v1','invalid cached JSON');const corruptCache=await boot(null,'',()=>new Promise(()=>{}));assert.ok(corruptCache.nodes.get('list').children.length,'a corrupt cache must not prevent use of the bundled news feed');
 const legacy=await boot(null,'?view=bands');assert.equal(legacy.nodes.get('viewTitle').textContent,'Твоя музыкальная лента');
 const {app,nodes,sections}=await boot();assert.ok(nodes.get('list').children.length);
 app.toggleFavorite('wolves-in-the-throne-room');
 let mine=app.selectArticles(data.articles,{view:'mine'});
 assert.equal(mine.length,1);assert.ok(mine[0].paragraphs[6].startsWith('6. Wretched Spirits'));
 const restarted=await boot();assert.ok(restarted.app.preferences.favorites.includes('wolves-in-the-throne-room'));
 const offline=await boot(null,'',()=>new Promise(()=>{}));assert.ok(offline.nodes.get('list').children.length,'cached feed must render before the network responds');
 storage.set('metal-news.articles.v1',JSON.stringify({articles:[data.articles.at(-1)],cachedAt:1}));const refreshedSeed=await boot(null,'',()=>new Promise(()=>{}));assert.ok(refreshedSeed.nodes.get('list').children.length>1,'new embedded feed must replace an older local cache when offline');
 storage.delete('metal-news.articles.v1');const optionalDataOffline=await boot(null,'',async url=>url.startsWith('articles.json')?new Promise(()=>{}):new Promise(()=>{}));assert.ok(optionalDataOffline.nodes.get('list').children.length,'bundled news seed must render even when the WebView cannot finish network requests');
 storage.delete('metal-news.articles.v1');const notYetPublished=await boot(null,'?id=not-yet-published',()=>new Promise(()=>{}));assert.ok(notYetPublished.nodes.get('list').children.length,'an article link missing from the bundled snapshot must still open the feed instead of leaving the spinner');
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
 app.toggleBlocked('wolves-in-the-throne-room');assert.equal(app.selectArticles(data.articles).some(a=>a.original_url.endsWith('/184168/')),false);assert.equal(app.preferences.favorites.includes('wolves-in-the-throne-room'),false);const blockedRestart=await boot();assert.ok(blockedRestart.app.preferences.blocked.includes('wolves-in-the-throne-room'));app.toggleFavorite('wolves-in-the-throne-room');assert.equal(app.preferences.blocked.includes('wolves-in-the-throne-room'),false);
 console.log('Mini App: full articles, immediate cached startup, favorites persistence, band pages and event filters verified.');
})().catch(e=>{console.error(e);process.exitCode=1});
