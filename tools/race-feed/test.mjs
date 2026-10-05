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
import { parseRobots, robotsAllows, robotsDelay, fixtureName, run } from './fetch.mjs';

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
  // v4.18.0：體能挑戰、鐵人的寫法、日文、「路跑X健走」算路跑
  assert.equal(P.detectType('2026 Spartan Race 台北站'), 'obstacle_race');
  assert.equal(P.detectType('台北101垂直馬拉松'), 'obstacle_race');
  assert.equal(P.detectType('2026 臺東巴歌浪超鐵 Taitung Super 3'), 'triathlon');
  assert.equal(P.detectType('2027 tSt 新北微風鐵人賽'), 'triathlon');
  assert.equal(P.detectType('2026 鐵人兩項挑戰賽'), 'duathlon');
  assert.equal(P.detectType('2026 跑若飛天公盃路跑X健走大賽'), 'road_running');
  assert.equal(P.detectType('某某公開賽', null, ['0.75K+20K+5K']), 'triathlon');
  assert.equal(P.detectType('第19回川崎港トライアスロン'), 'triathlon');
  assert.equal(P.detectType('信越五岳トレイルランニングレース'), 'trail_running');
  assert.equal(P.detectType('明石海峡大橋海上ウォーク'), 'other');
  assert.equal(P.detectType('第44回いぶすき菜の花マラソン'), 'road_running');
  assert.deepEqual(P.parseDistances(['1.9K+90K+21.1K', '0.75K+20K+5K']), [113, 25.75]);   // 鐵人三段加起來
  assert.deepEqual(P.parseDistances(['100英里 / 100K夜']), [160.934, 100]);
  assert.deepEqual(P.parseDistances(['フルマラソン', 'ハーフ']), [42.195, 21.098]);
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

test('跑者廣場：全國賽會', () => {
  const list = P.parseRunPlaza(doc('runplaza-contest.html'), TODAY);
  assert.equal(list.length, 9);
  const zw = list.find(r => r.name.includes('五指山'));
  assert.equal(zw.date, '2026-10-18'); assert.equal(zw.regClose, '2026-10-18'); assert.equal(zw.regOpen, null); assert.equal(zw.city, '新竹縣');
  const pt = list.find(r => r.name.includes('屏東風域'));
  assert.equal(pt.date, '2027-01-01', '月份變小就是跨年');
  assert.equal(pt.regOpen, '2026-08-14'); assert.equal(pt.regClose, '2026-11-21');
  assert.deepEqual(pt.distances, [21, 10, 4]);
  assert.equal(list.find(r => r.name.includes('龜山朝日')).siteState, 'closed');
  const im = list.find(r => r.name.includes('IRONMAN'));
  assert.equal(im.type, 'triathlon'); assert.deepEqual(im.distances, [113]);
  assert.equal(list.find(r => r.name.includes('tSt')).date, '2027-05-09');
  assert.equal(list.find(r => r.name.includes('飆5K')).urlKind, 'site', '不是報名網站的連結當官網');
  assert.ok(list.every(r => r.source === 'runplaza' && /^\d{4}-\d{2}-\d{2}-[0-9a-z]+$/.test(r.sid)));
  assert.equal(P.parseRunPlaza(doc('runplaza-contest.html'), TODAY)[3].sid, zw.sid, '編號每次一樣');
  // 真網頁上看到的兩種寫法：只寫開始報名「6月22日 ~」、名稱前後加 * 裝飾
  const row = (name, d, reg, cat = '42.195K') => `<tr><td></td><td><a href="https://bao-ming.com/eb/content/1">${name}</a></td><td></td><td>${d}</td><td>臺北市政府</td><td><button>${cat}</button></td><td></td><td>${reg}</td></tr>`;
  const extra = P.parseRunPlaza(parseHTML(`<table id="GridView1">${row('2026 臺北馬拉松', '12/20 日 06:30', '6月22日 ~')}${row('*2026 新竹市快樂路跑*', '12/27 日', '~ 12月01日 (最後一週)')}` +
    `${row('2027 六堆客庄巡禮走相逐', '01/10 日', '', '21K')}${row('2027 制霸小島', '01/17 日', '', '101K')}${row('2027 古道健行', '01/24 日', '', '8K')}</table>`).document, TODAY);
  assert.equal(extra[0].regOpen, '2026-06-22'); assert.equal(extra[0].regClose, null);
  assert.equal(extra[1].name, '2026 新竹市快樂路跑'); assert.equal(extra[1].regClose, '2026-12-01');
  assert.deepEqual(extra.slice(2).map(r => r.type), ['road_running', 'ultra_marathon', 'other'], '跑步行事曆：看不出項目的照公里數猜；健行照樣算其他');
  assert.equal(P.detectType('2026 淡蘭古道越野', null, []), 'trail_running');
  assert.equal(P.detectType('2027 山城健走', null, ['8K']), 'other');
  assert.equal(P.detectType('旱溪水岸慢跑健走嘉年華', null, []), 'road_running');
  assert.equal(P.detectType('2026 臺灣動感亞洲50', null, []), 'trail_running');
  assert.equal(P.detectType('TAKANAWA GATEWAY CITY SWIM & RUN FESTA 2026', null, []), 'duathlon', '游泳＋跑步是二項，不是游泳');
});

test('超馬協會：國內賽事行事曆', () => {
  const list = P.parseCtau(doc('ctau-calendar.html'), TODAY);
  assert.deepEqual(list.map(r => r.name).slice(0, 6), ['2026第14屆 開廣飛跑盃 超級馬拉松', '2026宜蘭冬山河 超級馬拉松', '2026東吳國際 超級馬拉松',
    '2026北宜公路 超級馬拉松', '2027 陽明山 超級馬拉松', '2027 臺北超級馬拉松']);
  assert.ok(!list.some(r => /志工|研習/.test(r.name)), '研習、志工不收');
  const ds = list.find(r => r.name.includes('冬山河'));
  assert.equal(ds.date, '2026-11-20'); assert.equal(ds.dateEnd, '2026-11-21'); assert.equal(ds.regClose, '2026-10-19');
  assert.equal(ds.url, 'https://bao-ming.com/eb/content/7003#reg'); assert.equal(ds.siteState, 'open'); assert.equal(ds.city, '宜蘭縣');
  assert.ok(ds.distances.includes(160.934), '100 英里');
  const ym = list.find(r => r.name === '2027 陽明山 超級馬拉松');
  assert.equal(ym.date, '2027-01-23'); assert.equal(ym.regClose, '2026-12-22');
  const tp = list.find(r => r.name === '2027 臺北超級馬拉松');
  assert.equal(tp.date, '2027-02-19'); assert.equal(tp.url, '', '沒有報名連結時不用舊新聞的連結');
  assert.equal(list.find(r => r.name === '2026 陽明山 超級馬拉松').date, '2026-01-17', '下面那張表看「2026年」');
  assert.equal(list.find(r => r.name === '2026長明賞').type, 'ultra_marathon');
  // 下面的舊行事曆（<h1>2025年</h1>、表格包在好幾層 div 裡）整張不看，不會變成明年的比賽
  assert.ok(!list.some(r => /2025宜蘭|2019/.test(r.name)), '舊年份的表格不收');
  // 年份跟日期黏在一起的寫法
  const one = P.parseCtau(parseHTML('<table><tr><td>活動名稱</td><td>日期</td><td>地點</td><td>里程</td></tr><tr><td>2028 測試 超級馬拉松</td><td>2028.03/06(六)</td><td>至善國中</td><td>50K</td></tr></table>').document, TODAY);
  assert.equal(one[0].date, '2028-03-06', '寫了年份就照寫，不是今天推的 2027');
  // 選拔賽的附註「2027 IAU 24H」不是名稱；場地只寫「新莊 田徑場」也認得縣市
  assert.equal(P.ctauName(['2026 CTAU超馬系列賽', '最終站', '臺北 超級馬拉松', '2027 IAU 24H', '世界錦標賽', '國家隊選拔賽之一']), '2026 臺北 超級馬拉松');
  assert.equal(P.findCity('新莊 田徑場起跑').city, '新北市');
});

test('JTB：清單與賽事頁', () => {
  const list = P.parseJtbList(doc('jtb-list-1.html'));
  assert.deepEqual(list.map(r => r.sid), ['ib79m', '7zc33', 'nlwil'], '高爾夫、志工招募、幼兒滑步車（ストライダー）不收');
  assert.ok(list.every(r => r.country === 'jp'));
  const ib = list[0];
  assert.equal(ib.date, '2027-01-10'); assert.equal(ib.city, '鹿児島県'); assert.equal(ib.region, 'kyushu-okinawa');
  assert.equal(list.find(r => r.sid === '7zc33').city, '大阪府');
  assert.equal(list.find(r => r.sid === 'nlwil').type, 'other', '海上ウォーク是健走');
  // 海外的（認不出都道府縣、寫了外國地名）算其他國家
  const pal = P.parseJtbList(parseHTML('<ul><li><a href="/detail/qws2i"></a><div class="title">パラオライド</div><span data-event-type="cycling"></span><div class="c-eventlist__contents__date">開催日：2026年11月22日(日) 開催場所：パラオ共和国コロール島</div></li></ul>').document);
  assert.equal(pal[0].country, 'other');
  assert.equal(list.find(r => r.sid === 'nlwil').dateEnd, '2026-11-29');
  assert.equal(P.jtbMaxPage(doc('jtb-list-1.html')), 7);
  const d = P.parseJtbDetail(doc('jtb-detail-ib79m.html'));
  assert.equal(d.regOpen, '2026-08-01'); assert.equal(d.regClose, '2026-10-25', '各組別最晚的截止');
  assert.deepEqual(d.cats, ['フルマラソン', '10km']);
  // 【】裡是梯次、年齡的：只認標題裡的距離（全形、㎞ 也認得）
  const d2 = P.parseJtbDetail(parseHTML('<table><tr><th>受付期間</th><td><table><tr><th>【一次】個人:500m ※一般</th><td>2026年02月09日(月)～2026年09月18日(金)</td></tr><tr><th>【第1部】１０㎞ 男子</th><td>2026年02月09日(月)～2026年10月09日(金)</td></tr><tr><th>【大人】</th><td>2026年02月09日(月)～2026年10月08日(木)</td></tr></table></td></tr></table>').document);
  assert.deepEqual(d2.cats, ['500m', '10km']); assert.equal(d2.regClose, '2026-10-09');
  assert.deepEqual(P.applyDetail(ib, d).distances, [42.195, 10]);
});

test('MSPO：清單與大會頁', () => {
  const list = P.parseMspoList(doc('mspo-triathlon.html'));
  assert.equal(list.length, 5);
  const z = list.find(r => r.sid === '67414');
  assert.equal(z.type, 'duathlon'); assert.equal(z.city, '神奈川県'); assert.equal(z.region, 'kanto'); assert.equal(z.siteState, 'closed');
  assert.equal(list.find(r => r.sid === '67897').siteState, 'open');
  assert.equal(list.find(r => r.sid === '67557').region, 'kyushu-okinawa');
  assert.equal(P.mspoMaxPage(doc('mspo-triathlon.html')), 2);
  assert.deepEqual(P.parseMspoDetail(doc('mspo-event-67414.html')), { regOpen: '2026-06-08', regClose: '2026-09-09' });
});

test('國家、日本的地區', () => {
  assert.deepEqual(P.findPref('東京臨海広域防災公園'), { city: '東京都', region: 'kanto' });
  assert.deepEqual(P.findPref('京都府京都市'), { city: '京都府', region: 'kinki' });
  assert.equal(P.findPref('東京都江東区').city, '東京都', '東京都不是京都');
  assert.equal(P.findPref('三重県四日市').region, 'kinki');
  assert.equal(P.countryOf({ region: 'north', city: '臺北市', name: 'x', venue: '' }), 'tw');
  assert.equal(P.countryOf({ region: 'overseas', city: '沖繩', name: '2027沖繩馬拉松', venue: '' }), 'jp');
  assert.equal(P.countryOf({ region: 'overseas', city: '馬來西亞', name: '檳城馬拉松', venue: '' }), 'other');
  const r = P.buildRaces([{ source: 'irunner', sid: 'oki', name: '2027沖繩馬拉松', date: '2027-02-21', dateEnd: null, month: '2027-02', city: '沖繩', region: 'overseas', venue: '',
    type: 'road_running', distances: [], cats: [], regOpen: null, regClose: null, siteState: null, url: 'https://irunner.biji.co/oki', urlKind: 'register' }], TODAY);
  assert.equal(r[0].country, 'jp'); assert.equal(r[0].region, 'kyushu-okinawa', '海外的日本賽事換成日本的地區');
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
  // v4.18.0：報名網址一樣也算同一場（跑者廣場連到運動筆記的那一頁、名稱寫得不太一樣）
  const rp = { ...base, source: 'runplaza', sid: 'r1', name: '臺北城市馬拉松 全馬組', date: '2026-12-20', url: 'http://irunner.biji.co/x/', urlKind: 'register', venue: '市政府廣場' };
  const m2 = P.mergeRaces([rp, a]);
  assert.equal(m2.length, 1); assert.equal(m2[0].source, 'irunner'); assert.equal(m2[0].venue, '市政府廣場');
  // 報名網站只有月份、行事曆有日期：合併後用行事曆的日期
  const m3 = P.mergeRaces([{ ...rp, date: '2027-02-21', month: '2027-02' }, { ...a, date: null, month: '2027-02' }]);
  assert.equal(m3.length, 1); assert.equal(m3[0].source, 'irunner'); assert.equal(m3[0].date, '2027-02-21');
});

test('同一天、名稱只有一段一樣：拿掉大家都有的字以後還有 3 個字一樣才算同一場', () => {
  const r = (name, date = '2026-11-15') => ({ name, date, dateEnd: null });
  assert.ok(P.sameRace(r('2026 國聚慵懶跑者聚樂部'), r('2026慵懶跑者聚樂部 COZY RUNNER CLUB')));
  assert.ok(P.sameRace(r('2026 南投馬11th-草鞋墩馬拉松'), r('2026 草鞋墩馬拉松 前進鳥嘴潭、奔向九九峰')));
  assert.ok(!P.sameRace(r('2027 府城英雄馬拉松'), r('2027沖繩馬拉松')));
  assert.ok(!P.sameRace(r('2026 虎馬第八屆全國烤雞馬拉松'), r('2026龍崎文衡殿 第三屆赤兔馬全國馬拉松')));
  assert.ok(!P.sameRace(r('2027 臺南古都國際半程馬拉松'), r('2027 高雄港都國際半程馬拉松')), '只有「國際半程馬拉松」一樣');
  assert.ok(!P.sameRace(r('2027 古都國際半程馬拉松'), r('2027 港都國際半程馬拉松')), '沒寫縣市：整段比有八成像，拿掉通用字只剩「古都」「港都」');
  assert.ok(!P.sameRace(r('2026 新北市耶誕馬拉松接力賽'), r('2026 新北市河濱公益路跑')), '只有縣市名一樣');
  assert.ok(!P.sameRace(r('2026 ZEPRO RUN全國半程馬拉松 新竹場'), r('2026 ZEPRO RUN全國半程馬拉松 台南場')), '同系列不同縣市');
  assert.ok(!P.sameRace(r('2026 國聚慵懶跑者聚樂部'), r('2026慵懶跑者聚樂部', '2026-11-22')), '不同天');
  assert.ok(P.sameRace(r('2027 臺中 MIZUNO 都會國際半程馬拉松'), r('2027 台中都會國際半程馬拉松')), '多了贊助商名稱');
  assert.ok(!P.sameRace({ ...r('第32回水郷ひたチャレンジウォーク'), country: 'jp' }, { ...r('紅葉チャレンジトライアスロン・デュアスロンフェスティバル'), country: 'jp' }), '片假名一樣不算');
  assert.ok(!P.sameRace({ ...r('TAKANAWA CITY SWIM & RUN'), country: 'jp' }, { ...r('2026 CITY SWIM & RUN'), region: 'north' }), '臺灣和日本不比');
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
  // v4.18.0：Crawl-delay
  assert.equal(robotsDelay(parseRobots('User-agent: *\nDisallow: /servers/frontend/\n\nCrawl-delay: 10\n'), 'RaceLogFeedBot'), 10);
  assert.equal(robotsDelay(parseRobots(''), 'RaceLogFeedBot'), 0);
  assert.equal(robotsDelay(parseRobots('User-agent: *\nCrawl-delay: 9999'), 'RaceLogFeedBot'), 60);
  assert.equal(fixtureName('https://jtbsports.jp/list.php?orderby=3&accepting=0&keyword=&pageno=2'), 'jtb-list-2.html');
  assert.equal(fixtureName('https://www.mspo.jp/athletic/triathlon?ss=1&paged=2&athletic=triathlon'), 'mspo-triathlon-2.html');
  assert.equal(fixtureName('https://www.mspo.jp/events/67414'), 'mspo-event-67414.html');
});

test('整段跑一次（用樣本）：內容沒變就不改時間、某個來源失敗先用上次的', async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'race-feed-'));
  const out = path.join(tmp, 'feed.json'), cache = path.join(tmp, 'cache.json');
  const opt = { out, cache, fixtures: FX, snapshot: null, today: TODAY, now: '2026-10-05T04:17:00Z', only: null, maxDetail: 60, delay: 0, timeout: 1000, quiet: true };
  const r1 = await run(opt);
  assert.equal(r1.okCount, 8);
  const f1 = JSON.parse(fs.readFileSync(out, 'utf8'));
  assert.equal(f1.v, 1);
  assert.ok(f1.races.length >= 30);
  assert.ok(f1.races.every(r => r.date === null || r.date >= TODAY), '沒有已經比完的');
  const j151 = f1.races.find(r => r.id === 'joinnow:151');
  assert.equal(j151.regOpen, '2026-10-01', '簡章裡的報名日期有補上');
  const jx = f1.races.find(r => r.id === 'irunner:2026jiaoxihotspring');
  assert.equal(jx.venue, '宜蘭縣礁溪國小');
  // v4.18.0：新的四個來源；每一場都有國家；JTB 的賽事頁補上報名期間
  for (const src of ['runplaza', 'ctau', 'jtb', 'mspo']) assert.ok(f1.races.some(r => r.source === src || (r.also || []).some(a => a.source === src)), src);
  assert.ok(f1.races.every(r => ['tw', 'jp', 'other'].includes(r.country)));
  assert.equal(f1.races.find(r => r.id === 'jtb:ib79m').regClose, '2026-10-25');
  assert.equal(f1.races.find(r => r.id === 'irunner:2027OkinawaRUN').country, 'jp');
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
  assert.equal(r3.okCount, 7);

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
