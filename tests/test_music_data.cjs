const assert=require('node:assert/strict');
const m=require('../docs/music-data.js');
assert.equal(m.ageAt({text:'1967-07-12',precision:11},null,new Date('2026-07-11T10:00:00Z')),58);
assert.equal(m.ageAt({text:'1967-07-12',precision:11},null,new Date('2026-07-12T10:00:00Z')),59);
assert.equal(m.ageAt({text:'1941-06-09',precision:11},{text:'2012-07-16',precision:11}),71);
assert.equal(m.ageAt({text:'1967',precision:9}),null);
assert.equal(m.dateValue({time:'+1985-00-00T00:00:00Z',precision:9}).text,'1985');
assert.equal(m.span({text:'1985'},null),'1985 → окончание не указано');
const claim=value=>({mainsnak:{datavalue:{value}}});
const member={...claim({id:'Q2'}),qualifiers:{P580:[{datavalue:{value:{time:'+1985-00-00T00:00:00Z',precision:9}}}],P582:[{datavalue:{value:{time:'+2010-00-00T00:00:00Z',precision:9}}}]}};
const result=m.members({id:'Q1',claims:{P527:[member,{...member,rank:'deprecated'}]}},{Q2:{id:'Q2',labels:{en:{value:'Drummer'}},claims:{P1303:[claim({id:'Q3'})]}},Q3:{labels:{en:{value:'drums'}}}});
assert.equal(result.length,1);assert.equal(result[0].end.text,'2010');assert.equal(result[0].role,'');assert.equal(result[0].instruments,'drums');
console.log('Music data: exact birthday age, deceased age, partial dates, periods and scoped instruments verified.');
// Python URL encoding escapes '*'; URLSearchParams keeps it literal.
// The bundled cache must satisfy the same query without a network request.
const fs=require('node:fs');const bundled=JSON.parse(fs.readFileSync('docs/music_cache.json','utf8'));
for(const response of Object.values(bundled))response._retrieved_at=new Date().toISOString();
m.seed(bundled);global.fetch=async()=>{throw Error('Unexpected HTTP request for cached albums')};
m.albums('Q162586').then(rows=>{assert.ok(rows.some(a=>a.name==='Images and Words'));console.log('Bundled album cache survives URL encoding differences.');}).catch(e=>{console.error(e);process.exitCode=1});
