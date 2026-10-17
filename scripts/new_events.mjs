// 比對前後兩版 live.json，輸出這次新增的通知（給 notify.yml 送到推播後端）
import fs from 'node:fs';
const read = p => { try { return JSON.parse(fs.readFileSync(p, 'utf8')); } catch (e) { return {}; } };
const [oldF, newF] = process.argv.slice(2);
const seen = new Set((read(oldF).events || []).map(e => e.id));
const items = (read(newF).events || []).filter(e => !seen.has(e.id))
  .map(e => ({ code: e.code, kind: e.kind, title: e.title, body: e.body, url: e.url, tag: e.id }));
process.stdout.write(JSON.stringify({ items }));
