/* 找賽事清單的測試（v4.16.0）：node --test tools/race-feed/test.mjs
   用 fixtures/ 裡存好的真網頁樣本（2026-10-05 存的）檢查每個網站的解析、合併、失敗時沿用上次的資料。
   為什麼要測：網站改版是遲早的事，改 parse.mjs 的時候跑這支，就知道有沒有把其他網站弄壞。 */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseHTML } from 'linkedom';
import * as P from './parse.mjs';
import { parseRobots, robotsAllows, fixtureName, run } from './fetch.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FX = path.join(HERE, 'fixtures');
const doc = f => parseHTML(fs.readFileSync(path.join(FX, f), 'utf8')).document;
const TODAY = '2026-10-05';
const byId = (list, sid) => list.find(r => r.sid === sid);

test('日期：不存在的日期、只有月日時推年份', () => {
  assert.equal(P.ymd(2026, 2, 30), null);
  assert.equal(P.ymd(2026, 12, 31), '2026-12-31');
  assert.equal(P.yearBefore(12, 7, '2027-05-22'), '2026-12-07');   // 開報日在比賽之前
  assert.equal(P.yearBefore(3, 1, '2027-02-21'), '2026-03-01');
  assert.equal(P.yearFromToday(3, 28, TODAY), '2027-03-28');       // 一起報名的日期沒有年份
  assert.equal(P.yearFromToday(10, 17, TODAY), '2026-10-17');
});

test('報名期間：各網站的寫法', () => {
  const cases = [
    ['報名日期 2026年10月01日00時起至2026年12月31日22時', '2026-10-01', '2026-12-31'],
    ['報名時間 2026-06-02 12:00:00 ~ 2026-10-20 23:59:59', '2026-06-02', '2026-10-20'],
    ['報名時間 2026/09/17(四)~2026/10/29(四)', '2026-09-17', '2026-10-29'],
    ['活動日期 報名時間 2026年10月16日（星期五） 2026/09/14(一)~2026/10/5(一)', '2026-09-14', '2026-10-05'],
    ['報名期間：2026年12月20日 至 1月10日', '2026-12-20', '2027-01-10'],   // 跨年、後面沒寫年份
  ];
  for (const [s, a, b] of cases) assert.deepEqual(P.parseRegRange(s), { regOpen: a, regClose: b }, s);
  assert.equal(P.parseRegRange('活動日期 2026/10/16'), null);
  assert.equal(P.parseRegRange('報名時間 2026/10/29 ~ 2026/09/17'), null);   // 迄比起早：不收
});

test('縣市與地區', () => {
  assert.deepEqual(P.findCity('台中市西屯區中央球場'), { city: '臺中市', region: 'central' });
  assert.deepEqual(P.findCity('南庄鄉公有停車場（康濟吊橋下）'), { city: '苗栗縣', region: 'central' });
  assert.deepEqual(P.findCity('總統府/大佳河濱公園'), { city: '臺北市', region: 'north' });
  assert.deepEqual(P.findCity('金城田徑場'), { city: '金門縣', region: 'islands' });
  assert.deepEqual(P.findCity('', '2027沖繩馬拉松'), { city: '沖繩', region: 'overseas' });
  assert.deepEqual(P.findCity('大安森林公園'), { city: '', region: '' });    // 大安區臺北、臺中都有：不猜
  assert.deepEqual(P.findCity('國泰新社區'), { city: '', region: '' });      // 「社區」不是臺中新社區
  assert.equal(P.findCity('新竹縣竹北市').city, '新竹縣');
});

test('種類與距離', () => {
  assert.equal(P.detectType('2026 某某越野馬拉松'), 'trail_running');
  assert.equal(P.detectType('1919 單車公益活動-台北陪騎'), 'cycling');
  assert.equal(P.detectType('高雄 5000公尺挑戰賽(10/16)'), 'road_running');
  assert.equal(P.detectType('2026 ONWF 北歐式健走聯賽'), 'other');
  assert.equal(P.detectType('【傘耀十二】美濃馬拉松', '超級馬拉松'), 'ultra_marathon');   // 網站給的類型優先
  assert.deepEqual(P.parseDistances(['42.195K', '21KM半馬組', '45公里超馬組', '5.K', '約12.5KM', '5000公尺', '0.1K']), [45, 42.195, 21, 12.5, 5]);
  assert.deepEqual(P.parseDistances(['全馬', '半馬', '5KM']), [42.195, 21.098, 5]);
  assert.ok(P.NOT_RACE.test('跑步講座'));
});

test('運動筆記：清單', () => {
  const list = P.parseIrunnerList(doc('irunner-list.html'));
  assert.ok(list.length >= 15, '列數 ' + list.length);
  assert.ok(list.every(r => r.url.startsWith('https://irunner.biji.co/') && r.urlKind === 'register'));
  assert.ok(!list.some(r => P.NOT_RACE.test(r.name)), '講座不放進來');
  const khm = byId(list, '2027KHM');
  assert.equal(khm.date, null); assert.equal(khm.month, '2027-01'); assert.equal(khm.regClose, '2026-10-23'); assert.equal(khm.siteState, 'open');
  const op = byId(list, 'TTTESSSTTTT-2027ONEPIECERUN-KHH');
  assert.equal(op.regOpen, '2026-12-07'); assert.equal(op.siteState, null); assert.equal(op.city, '高雄市');
  assert.equal(byId(list, '2026RaveNightRun').siteState, 'cancelled');
  assert.equal(byId(list, 'CIMarathon2026').siteState, 'full');
  assert.equal(byId(list, '2026RotaryRUNWITHYOU').siteState, 'closed');
  assert.equal(byId(list, '2027OkinawaRUN').region, 'overseas');
  assert.ok(list.every(r => !/<br/i.test(r.name)));
});

test('運動筆記：賽事頁', () => {
  assert.deepEqual(P.parseIrunnerDetail(doc('irunner-detail-2026jiaoxihotspring.html')),
    { date: '2026-12-12', venue: '宜蘭縣礁溪國小', regOpen: '2026-06-02', regClose: '2026-10-20' });
  // 「詳細內容請洽內文」不是地點
  assert.equal(P.applyDetail({ name: 'x', date: '2027-03-27', venue: '', city: '', region: '' }, { venue: '詳細內容請洽內文' }).venue, '');
  const k = P.parseIrunnerDetail(doc('irunner-detail-2027KHM.html'));
  assert.equal(k.date, undefined); assert.equal(k.venue, '高雄國家體育場'); assert.equal(k.regOpen, '2026-09-21');
});

test('全統：首頁與賽事頁', () => {
  const list = P.parseCtrunHome(doc('ctrun-home.html'));
  assert.equal(new Set(list.map(r => r.sid)).size, list.length, '同一場不重複');
  assert.equal(byId(list, '362').siteState, 'open');      // 搶先報名
  assert.equal(byId(list, '366').siteState, 'open');
  assert.equal(byId(list, '337').siteState, 'closed');    // 報名截止
  assert.equal(byId(list, '320').siteState, 'full');      // 徽章「已額滿」
  assert.equal(byId(list, '330').siteState, 'closed');    // 已經比完：沒有報名按鈕
  assert.equal(byId(list, '362').date, '2027-01-17');
  assert.equal(byId(list, '362').city, '臺中市');
  assert.deepEqual(P.parseCtrunDetail(doc('ctrun-detail-362.html')), { regOpen: '2026-09-17', regClose: '2026-10-29', venue: '台中市西屯區中央球場' });
  const d361 = P.parseCtrunDetail(doc('ctrun-detail-361.html'));
  assert.equal(d361.regOpen, '2026-09-14'); assert.equal(d361.regClose, '2026-10-05');
});

test('一起報名：首頁與簡章', () => {
  const list = P.parseJoinnowIndex(doc('joinnow-index.html'), TODAY);
  assert.ok(!list.some(r => r.sid === '132' || r.sid === '113'), '活動已結束的不收');
  assert.equal(byId(list, '151').date, '2027-03-28');
  assert.equal(byId(list, '152').date, '2026-12-26');
  assert.equal(byId(list, '150').date, '2027-01-16');
  assert.equal(byId(list, '151').siteState, 'open');
  assert.equal(byId(list, '137').siteState, 'closed');
  assert.equal(byId(list, '137').type, 'ultra_marathon');
  assert.equal(byId(list, '151').city, '高雄市');
  assert.equal(byId(list, '151').detailUrl, 'https://www.joinnow.com.tw/about.php?cnt_id=151&type=1');
  const d = P.parseJoinnowDetail(doc('joinnow-about-151.html'));
  assert.deepEqual(d, { regOpen: '2026-10-01', regClose: '2026-12-31', date: '2027-03-28' });
  // 資訊卡格式：只有截止日
  assert.deepEqual(P.parseJoinnowDetail(doc('joinnow-about-152.html')), { regClose: '2026-10-31', date: '2026-12-26', venue: '棧貳庫廣場' });
  // 舊版版面：字直接寫在內文
  const old = parseHTML('<html><body><div>活動日期2026/12/13(日) 報名期限 2026/05/31 截止 額滿提前截止 活動地點高雄美濃區龍肚小學</div></body></html>').document;
  assert.deepEqual(P.parseJoinnowDetail(old), { date: '2026-12-13', regClose: '2026-05-31' });
});

test('路協：行事曆', () => {
  const d26 = doc('sportsnet-2026.html'), d27 = doc('sportsnet-2027.html');
  assert.equal(P.sportsnetYear(d26), 2026); assert.equal(P.sportsnetYear(d27), 2027);
  const a = P.parseSportsnet(d26, 2026), b = P.parseSportsnet(d27, 2027);
  const km = byId(a, '2026-2');
  assert.equal(km.date, '2026-01-24'); assert.equal(km.dateEnd, '2026-01-25');
  assert.equal(km.city, '金門縣');
  assert.equal(byId(b, '2027-1').date, '2027-01-10');
  assert.ok([...a, ...b].every(r => r.urlKind === 'site' && (r.url === '' || /^https?:\/\//.test(r.url))));
  assert.deepEqual(byId(a, '2026-16').distances, [42.195, 21.098]);
});

test('合併：同一天、名稱相近才算同一場', () => {
  const base = { dateEnd: null, month: '2026-12', city: '', region: '', venue: '', type: 'road_running', distances: [], cats: [], regOpen: null, regClose: null, siteState: null, urlKind: 'register' };
  const a = { ...base, source: 'irunner', sid: 'x', name: '2026臺北馬拉松', date: '2026-12-20', url: 'https://irunner.biji.co/x' };
  const b = { ...base, source: 'sportsnet', sid: '2026-16', name: '2026臺北馬拉松 TAIPEI MARATHON', date: '2026-12-20', url: 'http://www.taipeicitymarathon.com', urlKind: 'site', city: '臺北市', region: 'north', distances: [42.195], cats: ['42.195KM'] };
  const c = { ...base, source: 'ctrun', sid: '9', name: '2026臺北馬拉松', date: '2026-12-21', url: 'https://www.ctrun.com.tw/Activity?EventMain_ID=9' };
  assert.ok(P.sameRace(a, b)); assert.ok(!P.sameRace(a, c));
  const m = P.mergeRaces([b, a, c]);
  assert.equal(m.length, 2);
  const tpe = m.find(r => r.date === '2026-12-20');
  assert.equal(tpe.source, 'irunner', '報名平台排前面');
  assert.equal(tpe.city, '臺北市', '缺的欄位用另一個來源補');
  assert.deepEqual(tpe.distances, [42.195]);
  assert.deepEqual(tpe.also, [{ source: 'sportsnet', url: 'http://www.taipeicitymarathon.com', urlKind: 'site' }]);
  // 同一個網站的兩頁（同一場分組報名）不合併
  const g1 = { ...base, source: 'irunner', sid: 'a3k', name: '統一發票盃路跑臺北場-休閒組(3km)', date: '2026-11-08', url: 'https://irunner.biji.co/a3k', siteState: 'full' };
  const g2 = { ...base, source: 'irunner', sid: 'a21k', name: '統一發票盃路跑臺北場-競賽組(21km)', date: '2026-11-08', url: 'https://irunner.biji.co/a21k', siteState: 'closed' };
  assert.equal(P.mergeRaces([g1, g2]).length, 2);
});

test('整理：只留還沒比、一年多以內的，依日期排', () => {
  const base = { dateEnd: null, city: '', region: '', venue: '', type: 'other', distances: [], cats: [], regOpen: null, regClose: null, siteState: null, url: '', urlKind: 'register', source: 'irunner' };
  const r = P.buildRaces([
    { ...base, sid: 'old', name: '已經比完', date: '2026-10-04', month: '2026-10' },
    { ...base, sid: 'far', name: '太遠', date: '2028-01-01', month: '2028-01' },
    { ...base, sid: 'b', name: '乙', date: '2026-11-01', month: '2026-11' },
    { ...base, sid: 'nodate', name: '見簡章', date: null, month: '2026-11' },
    { ...base, sid: 'a', name: '甲', date: '2026-10-05', month: '2026-10' },
  ], TODAY);
  assert.deepEqual(r.map(x => x.id), ['irunner:a', 'irunner:b', 'irunner:nodate']);
});

test('robots.txt：照規則判斷', () => {
  const g = parseRobots('User-agent: *\nDisallow: /admin/\nDisallow: /track/*/record/\nAllow: /track/*/record/public$\n\nUser-agent: BadBot\nDisallow: /\n');
  assert.ok(robotsAllows(g, 'RaceLogFeedBot', '/list'));
  assert.ok(robotsAllows(g, 'RaceLogFeedBot', '/2027KHM'));
  assert.ok(!robotsAllows(g, 'RaceLogFeedBot', '/admin/x'));
  assert.ok(!robotsAllows(g, 'RaceLogFeedBot', '/track/12/record/'));
  assert.ok(robotsAllows(g, 'RaceLogFeedBot', '/track/12/record/public'));
  assert.ok(!robotsAllows(g, 'BadBot/2.0', '/list'));
  assert.ok(robotsAllows(parseRobots(''), 'RaceLogFeedBot', '/anything'));
  assert.ok(!robotsAllows(parseRobots('User-agent: RaceLogFeedBot\nDisallow: /'), 'RaceLogFeedBot', '/list'));
  assert.equal(fixtureName('https://www.ctrun.com.tw/Activity?EventMain_ID=362'), 'ctrun-detail-362.html');
  assert.equal(fixtureName('https://www.sportsnet.org.tw/schedule.php?schedule_year=2027'), 'sportsnet-2027.html');
});

test('整段跑一次（用樣本）：內容沒變就不改時間、某個來源失敗先用上次的', async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'race-feed-'));
  const out = path.join(tmp, 'feed.json'), cache = path.join(tmp, 'cache.json');
  const opt = { out, cache, fixtures: FX, snapshot: null, today: TODAY, now: '2026-10-05T04:17:00Z', only: null, maxDetail: 60, delay: 0, timeout: 1000, quiet: true };
  const r1 = await run(opt);
  assert.equal(r1.okCount, 4);
  const f1 = JSON.parse(fs.readFileSync(out, 'utf8'));
  assert.equal(f1.v, 1);
  assert.ok(f1.races.length >= 30);
  assert.ok(f1.races.every(r => r.date === null || r.date >= TODAY), '沒有已經比完的');
  const j151 = f1.races.find(r => r.id === 'joinnow:151');
  assert.equal(j151.regOpen, '2026-10-01', '簡章裡的報名日期有補上');
  const jx = f1.races.find(r => r.id === 'irunner:2026jiaoxihotspring');
  assert.equal(jx.venue, '宜蘭縣礁溪國小');
  const text1 = fs.readFileSync(out, 'utf8');

  // 第二次：內容一樣 → 檔案一個字都不變（排程就不會產生空的提交）
  const r2 = await run({ ...opt, now: '2026-10-06T04:17:00Z' });
  assert.equal(r2.same, true);
  assert.equal(fs.readFileSync(out, 'utf8'), text1);
  const c2 = JSON.parse(fs.readFileSync(cache, 'utf8'));
  assert.ok(Object.keys(c2.details).length >= 5, '賽事頁有存快取');

  // 第三次：全統的首頁抓不到 → 全統標成 stale、先用上次的資料，其他來源照常
  const fx2 = path.join(tmp, 'fx2'); fs.mkdirSync(fx2);
  for (const f of fs.readdirSync(FX)) if (f !== 'ctrun-home.html') fs.copyFileSync(path.join(FX, f), path.join(fx2, f));
  const r3 = await run({ ...opt, fixtures: fx2, now: '2026-10-07T04:17:00Z' });
  const f3 = JSON.parse(fs.readFileSync(out, 'utf8'));
  const s3 = f3.sources.find(s => s.id === 'ctrun');
  assert.equal(s3.ok, false); assert.equal(s3.stale, true); assert.match(s3.error, /404/);
  assert.equal(f3.races.filter(r => r.source === 'ctrun').length, f1.races.filter(r => r.source === 'ctrun').length);
  assert.equal(r3.okCount, 3);

  // 第四次：一起報名的網頁變成解析不出東西（改版）→ 當作失敗，不會把清單清空
  const fx3 = path.join(tmp, 'fx3'); fs.mkdirSync(fx3);
  for (const f of fs.readdirSync(FX)) fs.copyFileSync(path.join(FX, f), path.join(fx3, f));
  fs.writeFileSync(path.join(fx3, 'joinnow-index.html'), '<html><body><div class="new-layout">改版了</div></body></html>');
  await run({ ...opt, fixtures: fx3, now: '2026-10-08T04:17:00Z' });
  const f4 = JSON.parse(fs.readFileSync(out, 'utf8'));
  const s4 = f4.sources.find(s => s.id === 'joinnow');
  assert.equal(s4.ok, false); assert.match(s4.error, /改版/);
  assert.ok(f4.races.some(r => r.source === 'joinnow'));
  fs.rmSync(tmp, { recursive: true, force: true });
});
