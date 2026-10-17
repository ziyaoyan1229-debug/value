// 價值台股推播後端（Cloudflare Worker，免費方案）：收手機的推播訂閱，盤後更新時把通知推到 iPhone／Android／電腦。
// 由 .github/workflows/push.yml 自動部署；KV（SUBS）存訂閱與 VAPID 金鑰（第一次用到時自動產生），PUSH_KEY 是發送用密鑰（部署時設定）。
// 加密與 VAPID 的做法和 coin-app 的 worker/push.js 相同。
//   GET  /vapid                          → { key }：給網站訂閱用的公鑰
//   POST /sub   { sub, codes, types }    → 登記或更新一台裝置（codes＝要追蹤的股票代號，types＝{ buy, over, move, limit, limitdn } 要收的通知）
//   POST /unsub { endpoint }             → 取消
//   POST /send  Authorization: Bearer <PUSH_KEY>  { items: [{ code, kind, title, body, url, tag }] }
//               → 推給有追蹤該股票、有開該類通知的裝置；回 { sent, gone, failed, subs }
//   GET  /stats Authorization: Bearer <PUSH_KEY>  → { subs }
//   GET  /rt?c=2330,2454                 → 盤中即時價（轉送證交所基本市況報導 mis.twse.com.tw，不存任何資料，同一台機器 15 秒內共用結果）
//   GET  /k5?c=2330                      → 最近一個交易日的 5 分 K（轉送 Yahoo Finance，60 秒內共用結果）
const SITE = 'https://ziyaoyan1229-debug.github.io/value/';
const enc = new TextEncoder();
const b64u = buf => { let s = ''; for (const b of new Uint8Array(buf)) s += String.fromCharCode(b); return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, ''); };
const ub64 = s => { s = s.replace(/-/g, '+').replace(/_/g, '/'); s += '='.repeat((4 - s.length % 4) % 4); return Uint8Array.from(atob(s), c => c.charCodeAt(0)); };
const cat = (...a) => { const n = a.reduce((x, y) => x + y.length, 0), o = new Uint8Array(n); let i = 0; for (const x of a) { o.set(x, i); i += x.length; } return o; };
const json = (d, st = 200) => new Response(JSON.stringify(d), { status: st, headers: { 'content-type': 'application/json; charset=utf-8', 'access-control-allow-origin': '*' } });
const S = crypto.subtle;

async function hkdf(salt, ikm, info, len) {
  const k = await S.importKey('raw', ikm, 'HKDF', false, ['deriveBits']);
  return new Uint8Array(await S.deriveBits({ name: 'HKDF', hash: 'SHA-256', salt, info }, k, len * 8));
}
// RFC 8291（aes128gcm）加密推播內容
export async function encrypt(sub, text) {
  const uaPub = ub64(sub.keys.p256dh), auth = ub64(sub.keys.auth);
  const as = await S.generateKey({ name: 'ECDH', namedCurve: 'P-256' }, true, ['deriveBits']);
  const asPub = new Uint8Array(await S.exportKey('raw', as.publicKey));
  const uaKey = await S.importKey('raw', uaPub, { name: 'ECDH', namedCurve: 'P-256' }, false, []);
  const secret = new Uint8Array(await S.deriveBits({ name: 'ECDH', public: uaKey }, as.privateKey, 256));
  const ikm = await hkdf(auth, secret, cat(enc.encode('WebPush: info\0'), uaPub, asPub), 32);
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const cek = await hkdf(salt, ikm, enc.encode('Content-Encoding: aes128gcm\0'), 16);
  const nonce = await hkdf(salt, ikm, enc.encode('Content-Encoding: nonce\0'), 12);
  const key = await S.importKey('raw', cek, 'AES-GCM', false, ['encrypt']);
  const ct = new Uint8Array(await S.encrypt({ name: 'AES-GCM', iv: nonce }, key, cat(enc.encode(text), new Uint8Array([2]))));
  return cat(salt, new Uint8Array([0, 0, 16, 0]), new Uint8Array([asPub.length]), asPub, ct);
}
// VAPID：第一次用到時產生 P-256 金鑰，存在 KV（換金鑰會讓所有裝置要重新訂閱，所以只產生一次）
export async function vapid(env) {
  const v = await env.SUBS.get('vapid', 'json');
  if (v) return v;
  const k = await S.generateKey({ name: 'ECDSA', namedCurve: 'P-256' }, true, ['sign', 'verify']);
  const n = { pub: b64u(await S.exportKey('raw', k.publicKey)), jwk: await S.exportKey('jwk', k.privateKey) };
  await env.SUBS.put('vapid', JSON.stringify(n));
  return n;
}
export async function vapidHeader(v, endpoint) {
  const h = b64u(enc.encode(JSON.stringify({ typ: 'JWT', alg: 'ES256' })));
  const c = b64u(enc.encode(JSON.stringify({ aud: new URL(endpoint).origin, exp: Math.floor(Date.now() / 1000) + 12 * 3600, sub: SITE })));
  const key = await S.importKey('jwk', v.jwk, { name: 'ECDSA', namedCurve: 'P-256' }, false, ['sign']);
  const sig = await S.sign({ name: 'ECDSA', hash: 'SHA-256' }, key, enc.encode(h + '.' + c));
  return `vapid t=${h}.${c}.${b64u(sig)}, k=${v.pub}`;
}
export async function pushOne(v, sub, msg) {
  const body = await encrypt(sub, JSON.stringify(msg));
  return fetch(sub.endpoint, { method: 'POST', body, headers: { Authorization: await vapidHeader(v, sub.endpoint), 'Content-Encoding': 'aes128gcm', 'Content-Type': 'application/octet-stream', TTL: '86400', Urgency: 'high' } });
}
const idOf = async ep => 'sub:' + b64u(await S.digest('SHA-256', enc.encode(ep))).slice(0, 32);
const authed = (req, env) => env.PUSH_KEY && req.headers.get('authorization') === 'Bearer ' + env.PUSH_KEY;
async function allSubs(env) {
  const out = []; let cursor;
  do { const r = await env.SUBS.list({ prefix: 'sub:', cursor }); for (const k of r.keys) { const v = await env.SUBS.get(k.name, 'json'); if (v) out.push([k.name, v]); } cursor = r.list_complete ? null : r.cursor; } while (cursor);
  return out;
}
const KINDS = ['buy', 'over', 'move', 'limit', 'limitdn'];
// 證交所和 Yahoo 都不讓網頁直接抓，所以這裡轉一手；只放在記憶體裡短暫共用，不寫 KV
const MEMO = new Map();
async function memo(key, ttl, fn) {
  const m = MEMO.get(key); if (m && Date.now() - m.at < ttl) return m.v;
  const v = await fn(); MEMO.set(key, { at: Date.now(), v }); if (MEMO.size > 300) MEMO.delete(MEMO.keys().next().value);
  return v;
}
const UA = { 'user-agent': 'Mozilla/5.0 (value-taiwan-stock)', accept: 'application/json' };
const nz = x => { const n = parseFloat(x); return isFinite(n) && n > 0 ? n : null; };
const codesOf = u => [...new Set((u.searchParams.get('c') || '').split(',').filter(c => /^\d{4,6}[A-Z]?$/.test(c)))].slice(0, 30).sort();
async function realtime(codes) {
  const r = await fetch('https://mis.twse.com.tw/stock/api/getStockInfo.jsp?json=1&delay=0&ex_ch=' + codes.map(c => `tse_${c}.tw`).join('|'), { headers: UA });
  if (!r.ok) throw new Error('mis ' + r.status);
  const j = await r.json(), items = {};
  for (const m of j.msgArray || []) {
    const bid = nz(String(m.b || '').split('_')[0]), last = nz(m.z), y = nz(m.y);
    const d = String(m.d || ''), date = d.length === 8 ? `${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6)}` : null;
    items[m.c] = { price: last || bid, last: !!last, prev: y, open: nz(m.o), high: nz(m.h), low: nz(m.l), volumeLots: nz(m.v), date, time: m.t || null };
  }
  return { at: new Date().toISOString(), source: '臺灣證券交易所 基本市況報導', items };
}
async function k5(code) {
  const r = await fetch(`https://query1.finance.yahoo.com/v8/finance/chart/${code}.TW?interval=5m&range=1d`, { headers: UA });
  if (!r.ok) throw new Error('yahoo ' + r.status);
  const res = (await r.json()).chart?.result?.[0]; if (!res) throw new Error('yahoo empty');
  const q = res.indicators?.quote?.[0] || {}, ts = res.timestamp || [], bars = [];
  ts.forEach((t, i) => { if (q.open?.[i] != null && q.close?.[i] != null) bars.push([t, q.open[i], q.high[i], q.low[i], q.close[i], q.volume?.[i] || 0]); });
  return { at: new Date().toISOString(), source: 'Yahoo Finance', prev: res.meta?.chartPreviousClose ?? res.meta?.previousClose ?? null, bars };
}

export default {
  async fetch(req, env) {
    const u = new URL(req.url), p = u.pathname.replace(/\/+$/, '');
    if (req.method === 'OPTIONS') return new Response(null, { headers: { 'access-control-allow-origin': '*', 'access-control-allow-methods': 'GET,POST,OPTIONS', 'access-control-allow-headers': 'content-type,authorization', 'access-control-max-age': '86400' } });
    try {
      if (p === '/vapid') return json({ key: (await vapid(env)).pub });
      if (p === '/sub' && req.method === 'POST') {
        const d = await req.json(), s = d && d.sub;
        if (!s || typeof s.endpoint !== 'string' || !/^https:\/\//.test(s.endpoint) || !s.keys || !s.keys.p256dh || !s.keys.auth) return json({ error: 'bad subscription' }, 400);
        const codes = (Array.isArray(d.codes) ? d.codes : []).filter(c => /^\d{4,6}[A-Z]?$/.test(c)).slice(0, 200);
        const types = {}; for (const k of KINDS) types[k] = !!(d.types && d.types[k]);
        const rec = { sub: { endpoint: s.endpoint, keys: { p256dh: s.keys.p256dh, auth: s.keys.auth } }, codes, types, at: Date.now() };
        await env.SUBS.put(await idOf(s.endpoint), JSON.stringify(rec));
        return json({ ok: true, codes: codes.length });
      }
      if (p === '/rt' && req.method === 'GET') {
        const codes = codesOf(u); if (!codes.length) return json({ error: 'no codes' }, 400);
        return json(await memo('rt:' + codes.join(','), 15000, () => realtime(codes)));
      }
      if (p === '/k5' && req.method === 'GET') {
        const c = codesOf(u)[0]; if (!c) return json({ error: 'no code' }, 400);
        return json(await memo('k5:' + c, 60000, () => k5(c)));
      }
      if (p === '/unsub' && req.method === 'POST') { const d = await req.json(); if (d && d.endpoint) await env.SUBS.delete(await idOf(d.endpoint)); return json({ ok: true }); }
      if (p === '/send' && req.method === 'POST') {
        if (!authed(req, env)) return json({ error: 'unauthorized' }, 401);
        // 免費方案每次呼叫的 CPU 時間有限，一次只處理一批裝置；notify.yml 用 start 往下一批，直到 next 為 null
        const d = await req.json(), items = (d.items || []).slice(0, 50);
        const start = Math.max(0, +d.start || 0), size = Math.min(50, Math.max(1, +d.size || 25));
        const v = await vapid(env), all = await allSubs(env), subs = all.slice(start, start + size);
        let sent = 0, gone = 0, failed = 0;
        for (const [k, r] of subs) {
          const mine = items.filter(m => (!m.code || (r.codes || []).includes(m.code)) && (!m.kind || (r.types || {})[m.kind])).slice(0, 10);
          for (const m of mine) {
            try {
              const res = await pushOne(v, r.sub, { title: String(m.title || '價值台股').slice(0, 120), body: String(m.body || '').slice(0, 1000), url: m.url || './', tag: m.tag || undefined });
              if (res.status === 404 || res.status === 410) { await env.SUBS.delete(k); gone++; break; }
              if (res.ok) sent++; else failed++;
            } catch (e) { failed++; }
          }
        }
        return json({ sent, gone, failed, subs: all.length, next: start + size < all.length ? start + size - gone : null });
      }
      if (p === '/stats') { if (!authed(req, env)) return json({ error: 'unauthorized' }, 401); return json({ subs: (await allSubs(env)).length }); }
      return json({ name: 'Value push', ok: true });
    } catch (e) { return json({ error: String(e && e.message || e) }, 500); }
  }
};
