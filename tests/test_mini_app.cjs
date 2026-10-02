// Execute the existing Mini App script against a small DOM adapter. No UI edits.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const data = JSON.parse(fs.readFileSync('docs/articles.json', 'utf8'));
function checkArticle(article, expectedCount) {
const nodes = new Map();
function element() {
  return { textContent: '', innerHTML: '', style: {}, children: [],
    classList: { add() {}, remove() {} }, addEventListener() {},
    appendChild(child) { this.children.push(child); } };
}
const document = {
  documentElement: { style: { setProperty() {} } },
  getElementById(id) {
    if (!nodes.has(id)) nodes.set(id, element());
    return nodes.get(id);
  },
  createElement: element,
};
let fetchCount = 0;
const context = {
  document, window: {}, location: { search: '?id=' + article.id },
  URLSearchParams, Date, String, console, history: { back() {} },
  setTimeout() { throw new Error('Article must load without retry'); },
  async fetch(url, options) {
    fetchCount++;
    assert.ok(url.startsWith('articles.json?t='));
    assert.equal(options.cache, 'no-store');
    return { ok: true, async json() { return data; } };
  },
};
const html = fs.readFileSync('docs/index.html', 'utf8');
const script = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)][0][1];
vm.runInNewContext(script, context);
return new Promise(resolve => setImmediate(() => {
  assert.equal(fetchCount, 1);
  const rendered = nodes.get('article').children.map(p => p.textContent);
  assert.deepEqual(rendered, article.paragraphs);
  assert.equal(rendered.length, expectedCount);
  if (expectedCount === 7) {
    assert.match(rendered[6], /^6\. Wretched Spirits, Land of the Light 06:14$/);
  } else {
    assert.match(nodes.get('title').textContent, /Фестиваль Тома Морелло/);
    assert.match(rendered[0], /Фестиваль/);
    assert.ok(!rendered.join(' ').includes('A post shared by'));
  }
  resolve();
}));
}

Promise.all([
  checkArticle(data.articles.find(a => a.original_url.endsWith('/184168/')), 7),
  checkArticle(data.articles.find(a => a.original_url.includes('tom-morellos-power')), 4),
]).then(() => console.log('Mini App: full Darkside tracklist and translated ThePRP article rendered.'));
