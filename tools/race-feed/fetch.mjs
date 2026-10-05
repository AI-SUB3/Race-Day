#!/usr/bin/env node
/* 找賽事清單：每天抓一次（v4.16.0）
   GitHub Actions 每天清晨跑這支（.github/workflows/race-feed.yml）：照 robots.txt 讀 4 個報名網站公開的賽事清單，
   整理成 race-feed.json，跟 App 放在同一個網站。App 的「找賽事」分頁只讀這個檔案。

   為什麼不讓 App 直接去讀那些網站：瀏覽器不准一個網站讀另一個網站的內容（CORS），我們也沒有自己的伺服器；
   由排程先抓好、放在同一個網站，是不用伺服器又最省事的做法。
   為什麼這麼客氣：同一個網站兩次之間至少隔 1.5 秒、每天只跑一次、賽事頁抓過的幾天內不重抓、robots.txt 不准的不抓，
   User-Agent 寫明是誰、附說明頁，對方要找我們找得到。

   用法：
     node tools/race-feed/fetch.mjs
         預設：寫 race-feed.json（repo 根目錄）、賽事頁快取存 tools/race-feed/cache.json
     node tools/race-feed/fetch.mjs --fixtures tools/race-feed/fixtures --today 2026-10-05 --out /tmp/feed.json
         不連網：用存好的網頁樣本跑一遍（測試用）
     node tools/race-feed/fetch.mjs --snapshot <資料夾>
         不連網：用在瀏覽器裡解析好的結果（<來源>.json：{records, details}）組清單。第一次上線時用這個做出初始的清單
   其他選項：--only irunner,ctrun　只跑某幾個來源；--max-detail 60　每個來源最多讀幾個賽事頁；
             --delay 1500　同一個網站兩次之間隔幾毫秒；--now <ISO 時間>　固定 updatedAt（測試用） */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseHTML } from 'linkedom';
import * as P from './parse.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..', '..');
const UA = 'RaceLogFeedBot/1.0 (+https://ai-sub3.github.io/Race-Day/about/)';
const BOT = 'RaceLogFeedBot';
const ORDER = ['irunner', 'ctrun', 'joinnow', 'sportsnet'];
const sleep = ms => new Promise(r => setTimeout(r, ms));
const days = (a, b) => Math.round((Date.parse(b + 'T00:00:00Z') - Date.parse(a + 'T00:00:00Z')) / 864e5);
// 台灣的日期：排程在 UTC 20:17 跑（台灣清晨 4:17），用 UTC 的日期會差一天
const todayTW = () => new Date(Date.now() + 8 * 3600e3).toISOString().slice(0, 10);

// ---------------- 參數 ----------------
function parseArgs(argv) {
  const a = { out: path.join(ROOT, 'race-feed.json'), cache: path.join(HERE, 'cache.json'), fixtures: null, snapshot: null,
    today: null, now: null, only: null, maxDetail: 60, delay: 1500, timeout: 20000, quiet: false };
  for (let i = 0; i < argv.length; i++) {
    const k = argv[i], v = argv[i + 1];
    const need = () => { if (v == null) throw new Error(k + ' 後面要接值'); i++; return v; };
    if (k === '--out') a.out = path.resolve(need());
    else if (k === '--cache') a.cache = path.resolve(need());
    else if (k === '--fixtures') a.fixtures = path.resolve(need());
    else if (k === '--snapshot') a.snapshot = path.resolve(need());
    else if (k === '--today') a.today = need();
    else if (k === '--now') a.now = need();
    else if (k === '--only') a.only = need().split(',').map(s => s.trim()).filter(Boolean);
    else if (k === '--max-detail') a.maxDetail = Math.max(0, +need() || 0);
    else if (k === '--delay') a.delay = Math.max(0, +need() || 0);
    else if (k === '--quiet') a.quiet = true;
    else throw new Error('不認得的參數：' + k);
  }
  if (a.today && !/^\d{4}-\d{2}-\d{2}$/.test(a.today)) throw new Error('--today 要寫成 YYYY-MM-DD');
  return a;
}

// ---------------- robots.txt ----------------
// 照 RFC 9309：找寫了自己名字的那組規則，沒有就用 *；最長的規則勝出，一樣長時 Allow 勝出；* 是萬用字元、$ 是結尾
function parseRobots(text) {
  const groups = []; let cur = null, lastAgent = false;
  for (let line of String(text || '').split(/\r?\n/)) {
    line = line.replace(/#.*/, '').trim();
    const m = line.match(/^([A-Za-z-]+)\s*:\s*(.*)$/);
    if (!m) continue;
    const k = m[1].toLowerCase(), v = m[2].trim();
    if (k === 'user-agent') {
      if (!cur || !lastAgent) { cur = { agents: [], rules: [] }; groups.push(cur); }
      cur.agents.push(v.toLowerCase()); lastAgent = true;
    } else {
      lastAgent = false;
      if (cur && (k === 'allow' || k === 'disallow') && v) cur.rules.push({ allow: k === 'allow', path: v });
    }
  }
  return groups;
}
function ruleMatches(rule, p) {
  let r = rule; const end = r.endsWith('$'); if (end) r = r.slice(0, -1);
  const re = new RegExp('^' + r.split('*').map(x => x.replace(/[.+?^${}()|[\]\\]/g, '\\$&')).join('.*') + (end ? '$' : ''));
  return re.test(p);
}
function robotsAllows(groups, agent, p) {
  const a = agent.toLowerCase();
  let g = groups.filter(x => x.agents.some(n => n !== '*' && a.includes(n)));
  if (!g.length) g = groups.filter(x => x.agents.includes('*'));
  let best = null;
  for (const r of g.flatMap(x => x.rules)) {
    if (!ruleMatches(r.path, p)) continue;
    if (!best || r.path.length > best.path.length || (r.path.length === best.path.length && r.allow)) best = r;
  }
  return !best || best.allow;
}

// ---------------- 讀網頁 ----------------
function decode(buf, ctype) {
  let cs = (String(ctype || '').match(/charset=["']?([\w-]+)/i) || [])[1];
  if (!cs) cs = (buf.subarray(0, 4096).toString('latin1').match(/<meta[^>]+charset=["']?([\w-]+)/i) || [])[1];
  try { return new TextDecoder((cs || 'utf-8').toLowerCase()).decode(buf); } catch { return new TextDecoder('utf-8').decode(buf); }
}
function liveGetter(opt) {
  const last = new Map(), robots = new Map();
  let requests = 0;
  async function once(url) {
    const host = new URL(url).host;
    const wait = (last.get(host) || 0) + opt.delay - Date.now();
    if (wait > 0) await sleep(wait);
    last.set(host, Date.now());
    requests++;
    const ctl = new AbortController(); const t = setTimeout(() => ctl.abort(), opt.timeout);
    try {
      const res = await fetch(url, { redirect: 'follow', signal: ctl.signal, headers: { 'User-Agent': UA,
        Accept: 'text/html,application/xhtml+xml;q=0.9,*/*;q=0.8', 'Accept-Language': 'zh-TW,zh;q=0.9,en;q=0.5' } });
      const buf = Buffer.from(await res.arrayBuffer());
      if (buf.length > 6e6) throw new Error('網頁太大');
      return { status: res.status, text: decode(buf, res.headers.get('content-type')) };
    } finally { clearTimeout(t); last.set(host, Date.now()); }
  }
  // 網路斷掉或對方忙（5xx、429）：等 5 秒再試一次就好，不連續猛試
  async function retry(url) {
    try { const r = await once(url); if (r.status >= 500 || r.status === 429) { await sleep(5000); return await once(url); } return r; }
    catch { await sleep(5000); return await once(url); }
  }
  function robotsFor(origin) {
    if (!robots.has(origin)) robots.set(origin, (async () => {
      try {
        const r = await retry(origin + '/robots.txt');
        if (r.status >= 200 && r.status < 300) return parseRobots(r.text);
        if (r.status >= 400 && r.status < 500) return [];   // 沒有 robots.txt＝沒有限制（RFC 9309）
        return null;                                         // 5xx：照規範先當作全部不准，今天不抓
      } catch { return null; }
    })());
    return robots.get(origin);
  }
  const get = async url => {
    const u = new URL(url);
    const groups = await robotsFor(u.origin);
    if (groups === null) throw new Error('讀不到 robots.txt，今天先不抓');
    if (!robotsAllows(groups, BOT, u.pathname + u.search)) throw new Error('robots.txt 不允許 ' + u.pathname);
    const r = await retry(url);
    if (r.status !== 200) throw new Error('HTTP ' + r.status);
    return r.text;
  };
  get.count = () => requests;
  return get;
}
// 網頁樣本：網址對到 fixtures/ 裡的檔名
function fixtureName(url) {
  const u = new URL(url);
  if (u.host === 'irunner.biji.co') return u.pathname === '/list' ? 'irunner-list.html' : 'irunner-detail-' + decodeURIComponent(u.pathname.slice(1)) + '.html';
  if (u.host === 'www.ctrun.com.tw') { const id = u.searchParams.get('EventMain_ID'); return id ? `ctrun-detail-${id}.html` : 'ctrun-home.html'; }
  if (u.host === 'www.joinnow.com.tw') { const id = u.searchParams.get('cnt_id'); return id ? `joinnow-about-${id}.html` : 'joinnow-index.html'; }
  if (u.host === 'www.sportsnet.org.tw') return `sportsnet-${u.searchParams.get('schedule_year') || 'x'}.html`;
  return null;
}
function fixtureGetter(dir) {
  let requests = 0;
  const get = async url => {
    requests++;
    const f = fixtureName(url), p = f && path.join(dir, f);
    if (!p || !fs.existsSync(p)) throw new Error('HTTP 404（樣本裡沒有）');
    return fs.readFileSync(p, 'utf8');
  };
  get.count = () => requests;
  return get;
}
const toDoc = html => parseHTML(html).document;

// ---------------- 每個來源：清單頁 ----------------
const LIST = {
  irunner: async (get) => P.parseIrunnerList(toDoc(await get(P.SOURCES.irunner.home))),
  ctrun: async (get) => P.parseCtrunHome(toDoc(await get(P.SOURCES.ctrun.home))),
  joinnow: async (get, today) => P.parseJoinnowIndex(toDoc(await get(P.SOURCES.joinnow.home)), today),
  // 路協：今年和明年的行事曆。明年的還沒公布時，網站回空表格、年份選單也不會選到明年，就當作還沒有
  sportsnet: async (get, today) => {
    const y = +today.slice(0, 4), out = [];
    for (const yy of [y, y + 1]) {
      let d;
      try { d = toDoc(await get(`https://www.sportsnet.org.tw/schedule.php?schedule_year=${yy}`)); }
      catch (e) { if (yy === y) throw e; continue; }
      if (P.sportsnetYear(d) !== yy) { if (yy === y) throw new Error(`年份選單沒有選到 ${yy}（網站可能改版）`); continue; }
      out.push(...P.parseSportsnet(d, yy));
    }
    return out;
  },
};
const DETAIL = { irunner: P.parseIrunnerDetail, ctrun: P.parseCtrunDetail, joinnow: P.parseJoinnowDetail, sportsnet: null };

// 還沒結束、一年多以內的才需要（跟 buildRaces 留下來的範圍一樣）
function upcoming(r, today) {
  const d = r.date || (r.month ? r.month + '-28' : null);
  return !!d && (r.dateEnd || d) >= today && d <= P.addDays(today, 430);
}
// 賽事頁多久重抓一次：報名快開始或快截止的 2 天，其他 7 天
function maxAge(r, today) {
  const soon = (d, n) => d && d >= today && d <= P.addDays(today, n);
  return soon(r.regClose, 21) || soon(r.regOpen, 14) ? 2 : 7;
}

async function withDetails(src, recs, ctx) {
  const parse = DETAIL[src];
  const stat = { fetched: 0, cached: 0, failed: 0, skipped: 0 };
  if (!parse) return { recs, stat };
  const order = recs.map((r, i) => ({ r, i })).filter(x => x.r.detailUrl && upcoming(x.r, ctx.today))
    .sort((a, b) => (a.r.date || a.r.month + '-28').localeCompare(b.r.date || b.r.month + '-28'));   // 最近的比賽先抓
  const out = recs.slice();
  for (const { r, i } of order) {
    const url = r.detailUrl;
    const hit = ctx.cache.details[url];
    const withCache = hit ? P.applyDetail(r, hit.d) : r;
    if (hit) hit.seen = ctx.today;
    const snap = ctx.snapshot && ctx.snapshot[src] && ctx.snapshot[src].details ? ctx.snapshot[src].details[url] : undefined;
    if (snap !== undefined) {   // 瀏覽器裡已經解析好的
      if (snap) { ctx.cache.details[url] = { at: ctx.today, seen: ctx.today, d: snap }; out[i] = P.applyDetail(r, snap); stat.fetched++; }
      else { out[i] = withCache; stat.failed++; }
      continue;
    }
    if (hit && days(hit.at, ctx.today) < maxAge(withCache, ctx.today)) { out[i] = withCache; stat.cached++; continue; }
    if (ctx.snapshot || stat.fetched + stat.failed >= ctx.opt.maxDetail) { out[i] = withCache; stat.skipped++; continue; }
    try {
      const d = parse(toDoc(await ctx.get(url)));
      ctx.cache.details[url] = { at: ctx.today, seen: ctx.today, d };
      out[i] = P.applyDetail(r, d); stat.fetched++;
    } catch (e) {
      out[i] = withCache; stat.failed++;   // 賽事頁讀不到不算整個來源失敗：清單上的資料照用
      ctx.log(`  ${src} 賽事頁讀不到：${url}（${e.message}）`);
    }
  }
  return { recs: out, stat };
}

// 上一次的資料轉回原始格式：某個來源今天抓不到時，先用上次的
function fromPrevFeed(prev, src) {
  return (prev && Array.isArray(prev.races) ? prev.races : []).filter(r => r.source === src).map(r => ({
    source: r.source, sid: String(r.id || '').split(':').slice(1).join(':'), name: r.name, date: r.date, dateEnd: r.dateEnd || null, month: r.month,
    city: r.city || '', region: r.region || '', venue: r.venue || '', type: r.type || 'other', distances: r.distances || [], cats: r.cats || [],
    regOpen: r.regOpen || null, regClose: r.regClose || null, siteState: r.siteState || null, url: r.url || '', urlKind: r.urlKind || 'register', detailUrl: null,
  }));
}

function readJson(p) { try { return JSON.parse(fs.readFileSync(p, 'utf8')); } catch { return null; } }
// 一場一行：每天的差異在 git 上一眼看得出是哪幾場變了
function stringify(feed) {
  return '{"v":' + feed.v + ',"updatedAt":' + JSON.stringify(feed.updatedAt) + ',\n"sources":[\n' + feed.sources.map(s => JSON.stringify(s)).join(',\n') +
    '\n],\n"races":[\n' + feed.races.map(r => JSON.stringify(r)).join(',\n') + '\n]}\n';
}

async function run(opt) {
  const today = opt.today || todayTW();
  const log = opt.quiet ? () => {} : (...a) => console.log(...a);
  const get = opt.fixtures ? fixtureGetter(opt.fixtures) : liveGetter(opt);
  const prev = readJson(opt.out);
  const cache = readJson(opt.cache) || {};
  if (!cache.details || typeof cache.details !== 'object') cache.details = {};
  if (!cache.lastGood || typeof cache.lastGood !== 'object') cache.lastGood = {};
  let snapshot = null;
  if (opt.snapshot) { snapshot = {}; for (const s of ORDER) { const j = readJson(path.join(opt.snapshot, s + '.json')); if (j) snapshot[s] = j; } }
  const ctx = { opt, today, get, cache, snapshot, log };
  const prevSrc = Object.fromEntries((prev && Array.isArray(prev.sources) ? prev.sources : []).map(s => [s.id, s]));

  const all = [], sources = [];
  for (const src of ORDER) {
    const meta = { id: src, name: P.SOURCES[src].name, url: P.SOURCES[src].home };
    if (opt.only && !opt.only.includes(src)) {   // 這次沒跑的來源：沿用上次的
      const keep = fromPrevFeed(prev, src); all.push(...keep);
      if (prevSrc[src]) sources.push(prevSrc[src]); else sources.push({ ...meta, ok: false, count: 0, error: '這次沒有抓', stale: true });
      continue;
    }
    let recs = null, error = null;
    try {
      if (snapshot) {
        if (!snapshot[src]) throw new Error('沒有這個來源的解析結果');
        recs = snapshot[src].records;
        if (!Array.isArray(recs)) throw new Error('解析結果格式不對');
      } else recs = await LIST[src](get, today);
      const n = recs.filter(r => upcoming(r, today)).length;
      const before = prevSrc[src] && prevSrc[src].ok ? prevSrc[src].count : 0;
      // 網站改版時常常是「抓得到網頁、但一筆都解析不出來」：筆數突然歸零或掉到三成以下，當作失敗、先用上次的
      if (n === 0 && before >= 3) throw new Error(`解析到 0 筆（上次 ${before} 筆），網站可能改版`);
      if (before >= 10 && n < before * 0.3) throw new Error(`筆數從 ${before} 掉到 ${n}，網站可能改版`);
    } catch (e) { error = e.message || String(e); recs = null; }

    if (recs) {
      const { recs: full, stat } = await withDetails(src, recs, ctx);
      const up = full.filter(r => upcoming(r, today));
      all.push(...up);
      cache.lastGood[src] = { at: today, records: up };
      sources.push({ ...meta, ok: true, count: up.length, error: null, stale: false });
      log(`${src}：${up.length} 場（清單 ${recs.length} 列；賽事頁 新抓 ${stat.fetched}、快取 ${stat.cached}、失敗 ${stat.failed}、留到下次 ${stat.skipped}）`);
    } else {
      // 先用快取裡最後一次成功的原始資料，沒有再用上一份 race-feed.json
      const lg = cache.lastGood[src];
      const keep = (lg && Array.isArray(lg.records) ? lg.records : fromPrevFeed(prev, src)).filter(r => upcoming(r, today));
      all.push(...keep);
      sources.push({ ...meta, ok: false, count: keep.length, error, stale: keep.length > 0, since: (lg && lg.at) || (prevSrc[src] && prevSrc[src].since) || null });
      log(`${src}：失敗（${error}），先用上次的 ${keep.length} 場`);
      if (process.env.GITHUB_ACTIONS) console.log(`::warning title=找賽事清單::${meta.name}：${error}（先用上次的資料）`);
    }
  }

  const races = P.buildRaces(all, today);
  const feed = { v: 1, updatedAt: null, sources, races };
  // 內容沒變就沿用上次的時間：檔案一個字都不變，排程就不會每天產生空的提交
  const same = prev && JSON.stringify(prev.sources) === JSON.stringify(sources) && JSON.stringify(prev.races) === JSON.stringify(races);
  feed.updatedAt = same && prev.updatedAt ? prev.updatedAt : (opt.now || new Date().toISOString());
  fs.writeFileSync(opt.out, stringify(feed));

  // 快取：30 天沒用到的賽事頁丟掉，免得越存越大
  for (const [k, v] of Object.entries(cache.details)) if (!v || !v.seen || days(v.seen, today) > 30) delete cache.details[k];
  fs.mkdirSync(path.dirname(opt.cache), { recursive: true });
  fs.writeFileSync(opt.cache, JSON.stringify(cache));

  const okCount = sources.filter(s => s.ok).length;
  log(`共 ${races.length} 場，${okCount}/${sources.length} 個來源成功，連線 ${get.count()} 次，${same ? '內容沒變' : '內容有更新'} → ${opt.out}`);
  if (process.env.GITHUB_STEP_SUMMARY) {
    const rows = sources.map(s => `| ${s.name} | ${s.ok ? '✅' : '⚠️'} | ${s.count} | ${s.error || ''} |`).join('\n');
    fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY, `### 找賽事清單\n共 ${races.length} 場，${same ? '內容沒變' : '內容有更新'}\n\n| 來源 | 狀態 | 場數 | 問題 |\n|---|---|---|---|\n${rows}\n`);
  }
  return { feed, same, okCount };
}

export { parseRobots, robotsAllows, fixtureName, upcoming, maxAge, stringify, run, parseArgs };

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  let opt;
  try { opt = parseArgs(process.argv.slice(2)); } catch (e) { console.error(e.message); process.exit(2); }
  run(opt).then(({ okCount, feed }) => {
    // 全部來源都失敗、手上也沒有任何資料：讓排程顯示失敗（GitHub 會寄信通知）
    if (okCount === 0 && feed.races.length === 0) process.exit(1);
  }).catch(e => { console.error(e && e.stack || e); process.exit(1); });
}
