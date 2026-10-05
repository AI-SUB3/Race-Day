/* 找賽事清單：解析與整理（v4.16.0；v4.18.0 加跑者廣場、超馬協會、JTB、MSPO 和國家別）
   這支檔案只放純函式：給它網頁的 document，回傳整理好的賽事。不連網、不讀寫檔案。
   為什麼拆成純函式：同一份程式碼在 GitHub Actions（Node＋linkedom）和瀏覽器（DOMParser）都能跑。
   網站改版時，可以直接在那個網站的分頁裡貼上這支檔案試解析，不必等每天的排程跑完才知道壞了沒。
   每個網站的欄位位置是 2026-10-05 用真的網頁對過的，樣本在 fixtures/。 */

// ---------------- 共用：文字、日期 ----------------
const txt = el => (el ? String(el.textContent || '') : '').replace(/<br\s*\/?>/gi, ' ').replace(/\s+/g, ' ').trim();
const pad = n => String(n).padStart(2, '0');
function ymd(y, m, d) {
  y = +y; m = +m; d = +d;
  if (!(y >= 2000 && y <= 2100 && m >= 1 && m <= 12 && d >= 1 && d <= 31)) return null;
  const t = new Date(Date.UTC(y, m - 1, d));
  if (t.getUTCMonth() !== m - 1) return null;   // 2/30 這種不存在的日期
  return `${y}-${pad(m)}-${pad(d)}`;
}
const addDays = (iso, n) => { const t = new Date(iso + 'T00:00:00Z'); t.setUTCDate(t.getUTCDate() + n); return t.toISOString().slice(0, 10); };
// 只有月日、沒有年份：取「不晚於 anchor、而且在 anchor 前一年內」的那一個（報名日期一定在比賽之前）
function yearBefore(m, d, anchor) {
  if (!anchor) return null;
  const y = +anchor.slice(0, 4);
  for (const yy of [y, y - 1]) { const v = ymd(yy, m, d); if (v && v <= anchor) return v; }
  return null;
}
// 只有月日的比賽日期：還沒結束的活動，取今天以後最近的那一個
function yearFromToday(m, d, today) {
  const y = +today.slice(0, 4);
  for (const yy of [y, y + 1]) { const v = ymd(yy, m, d); if (v && v >= today) return v; }
  return null;
}
const FULL_DATE = /(\d{4})\s*[年/.\-]\s*(\d{1,2})\s*[月/.\-]\s*(\d{1,2})/;
function parseFullDate(s) { const m = String(s || '').match(FULL_DATE); return m ? ymd(m[1], m[2], m[3]) : null; }
/* 報名期間：「報名時間／日期／期間」後面最近的一組「日期 ~ 日期」。各網站寫法都不一樣：
   2026/09/17(四)~2026/10/29(四)、2026/09/29(二) ~ 2026/10/29(四)、2026年10月01日00時起至2026年12月31日22時、
   表頭一列「活動日期｜報名時間」、下一列才是值（中間先遇到比賽日期，要跳過）。後面那個日期可以省略年份。
   第一個日期後面可能接時間（00時、12:00、23:59:59），時間裡的數字不能被當成第二個日期。 */
const D1 = '(\\d{4})\\s*[年/.\\-]\\s*(\\d{1,2})\\s*[月/.\\-]\\s*(\\d{1,2})';
const D2 = '(?:(\\d{4})\\s*[年/.\\-]\\s*)?(\\d{1,2})\\s*[月/.\\-]\\s*(\\d{1,2})';
const GAP = '(?:[^~～至到\\-－—\\d]|\\d{1,2}(?::\\d{2}){1,2}|\\d{1,2}\\s*[時點](?:\\s*\\d{1,2}\\s*分)?){0,24}';
const REG_RANGE = /* @__PURE__ */ new RegExp('報名(?:時間|日期|期間)[\\s\\S]{0,80}?' + D1 + GAP + '(?:[~～至到\\-－—]+|起至|起迄)\\s*' + D2);
function parseRegRange(text) {
  const m = String(text || '').replace(/\s+/g, ' ').match(REG_RANGE);
  if (!m) return null;
  const open = ymd(m[1], m[2], m[3]);
  let close = ymd(m[4] || m[1], m[5], m[6]);
  if (open && close && close < open && !m[4]) close = ymd(+m[1] + 1, m[5], m[6]);   // 12/20~1/10 跨年、後面沒寫年份
  return open && close && close >= open ? { regOpen: open, regClose: close } : null;
}

// ---------------- 縣市、地區 ----------------
const COUNTIES = ['臺北市', '新北市', '基隆市', '桃園市', '新竹市', '新竹縣', '宜蘭縣', '苗栗縣', '臺中市', '彰化縣', '南投縣', '雲林縣',
  '嘉義市', '嘉義縣', '臺南市', '高雄市', '屏東縣', '花蓮縣', '臺東縣', '澎湖縣', '金門縣', '連江縣'];
const REGION_OF = {
  north: ['臺北市', '新北市', '基隆市', '桃園市', '新竹市', '新竹縣', '宜蘭縣', '新竹'],
  central: ['苗栗縣', '臺中市', '彰化縣', '南投縣', '雲林縣'],
  south: ['嘉義市', '嘉義縣', '臺南市', '高雄市', '屏東縣', '嘉義'],
  east: ['花蓮縣', '臺東縣'],
  islands: ['澎湖縣', '金門縣', '連江縣'],
};
// 沒寫「市」「縣」的簡稱；新竹、嘉義分不出是市還是縣，照寫簡稱（地區一樣）
const SHORT = { 臺北: '臺北市', 新北: '新北市', 基隆: '基隆市', 桃園: '桃園市', 宜蘭: '宜蘭縣', 苗栗: '苗栗縣', 臺中: '臺中市', 彰化: '彰化縣',
  南投: '南投縣', 雲林: '雲林縣', 臺南: '臺南市', 高雄: '高雄市', 屏東: '屏東縣', 花蓮: '花蓮縣', 臺東: '臺東縣', 澎湖: '澎湖縣', 金門: '金門縣',
  馬祖: '連江縣', 連江: '連江縣', 新竹: '新竹', 嘉義: '嘉義' };
/* 鄉鎮市區（要帶「鄉鎮市區」字尾才算）：地點常常只寫到鄉鎮，例如「南庄鄉公有停車場」。
   跨縣市重複的（中正區、中山區、信義區、大安區、東區、西區、南區、北區、中區）不收；
   會撞到一般用語的也不收：新社區、大社區（社區）、林園區（森林園區）。 */
const TOWNS = {
  臺北市: '大同區 松山區 萬華區 士林區 北投區 內湖區 南港區 文山區',
  新北市: '板橋區 三重區 中和區 永和區 新莊區 新店區 樹林區 鶯歌區 三峽區 淡水區 汐止區 瑞芳區 土城區 蘆洲區 五股區 泰山區 林口區 深坑區 石碇區 坪林區 三芝區 石門區 八里區 平溪區 雙溪區 貢寮區 金山區 萬里區 烏來區',
  基隆市: '仁愛區 安樂區 暖暖區 七堵區',
  桃園市: '桃園區 中壢區 平鎮區 八德區 楊梅區 蘆竹區 大溪區 龍潭區 龜山區 大園區 觀音區 新屋區 復興區',
  新竹市: '香山區',
  新竹縣: '竹北市 竹東鎮 新埔鎮 關西鎮 湖口鄉 新豐鄉 芎林鄉 橫山鄉 北埔鄉 寶山鄉 峨眉鄉 尖石鄉 五峰鄉',
  苗栗縣: '苗栗市 頭份市 竹南鎮 後龍鎮 通霄鎮 苑裡鎮 卓蘭鎮 造橋鄉 西湖鄉 頭屋鄉 公館鄉 銅鑼鄉 三義鄉 大湖鄉 獅潭鄉 三灣鄉 南庄鄉 泰安鄉',
  臺中市: '北屯區 西屯區 南屯區 太平區 大里區 霧峰區 烏日區 豐原區 后里區 石岡區 東勢區 和平區 潭子區 大雅區 神岡區 大肚區 沙鹿區 龍井區 梧棲區 清水區 大甲區 外埔區',
  彰化縣: '彰化市 員林市 鹿港鎮 和美鎮 北斗鎮 溪湖鎮 田中鎮 二林鎮 線西鄉 伸港鄉 福興鄉 秀水鄉 花壇鄉 芬園鄉 大村鄉 埔鹽鄉 埔心鄉 永靖鄉 社頭鄉 二水鄉 田尾鄉 埤頭鄉 芳苑鄉 大城鄉 竹塘鄉 溪州鄉',
  南投縣: '南投市 埔里鎮 草屯鎮 竹山鎮 集集鎮 名間鄉 鹿谷鄉 中寮鄉 魚池鄉 國姓鄉 水里鄉 信義鄉 仁愛鄉',
  雲林縣: '斗六市 斗南鎮 虎尾鎮 西螺鎮 土庫鎮 北港鎮 古坑鄉 大埤鄉 莿桐鄉 林內鄉 二崙鄉 崙背鄉 麥寮鄉 東勢鄉 褒忠鄉 臺西鄉 元長鄉 四湖鄉 口湖鄉 水林鄉',
  嘉義縣: '太保市 朴子市 布袋鎮 大林鎮 民雄鄉 溪口鄉 新港鄉 六腳鄉 東石鄉 義竹鄉 鹿草鄉 水上鄉 中埔鄉 竹崎鄉 梅山鄉 番路鄉 大埔鄉 阿里山鄉',
  臺南市: '中西區 安平區 安南區 永康區 歸仁區 新化區 左鎮區 玉井區 楠西區 南化區 仁德區 關廟區 龍崎區 官田區 麻豆區 佳里區 西港區 七股區 將軍區 學甲區 北門區 新營區 後壁區 白河區 東山區 六甲區 下營區 柳營區 鹽水區 善化區 大內區 山上區 新市區 安定區',
  高雄市: '新興區 前金區 苓雅區 鹽埕區 鼓山區 旗津區 前鎮區 三民區 楠梓區 小港區 左營區 仁武區 岡山區 路竹區 阿蓮區 田寮區 燕巢區 橋頭區 梓官區 彌陀區 永安區 湖內區 鳳山區 大寮區 鳥松區 大樹區 旗山區 美濃區 六龜區 內門區 杉林區 甲仙區 桃源區 那瑪夏區 茂林區 茄萣區',
  屏東縣: '屏東市 潮州鎮 東港鎮 恆春鎮 萬丹鄉 長治鄉 麟洛鄉 九如鄉 里港鄉 鹽埔鄉 高樹鄉 萬巒鄉 內埔鄉 竹田鄉 新埤鄉 枋寮鄉 新園鄉 崁頂鄉 林邊鄉 南州鄉 佳冬鄉 琉球鄉 車城鄉 滿州鄉 枋山鄉 三地門鄉 霧臺鄉 瑪家鄉 泰武鄉 來義鄉 春日鄉 獅子鄉 牡丹鄉',
  宜蘭縣: '宜蘭市 羅東鎮 蘇澳鎮 頭城鎮 礁溪鄉 壯圍鄉 員山鄉 冬山鄉 五結鄉 三星鄉 大同鄉 南澳鄉',
  花蓮縣: '花蓮市 鳳林鎮 玉里鎮 新城鄉 吉安鄉 壽豐鄉 光復鄉 豐濱鄉 瑞穗鄉 富里鄉 秀林鄉 萬榮鄉 卓溪鄉',
  臺東縣: '臺東市 成功鎮 關山鎮 卑南鄉 鹿野鄉 池上鄉 東河鄉 長濱鄉 太麻里鄉 大武鄉 綠島鄉 海端鄉 延平鄉 金峰鄉 達仁鄉 蘭嶼鄉',
  澎湖縣: '馬公市 湖西鄉 白沙鄉 西嶼鄉 望安鄉 七美鄉',
  金門縣: '金城鎮 金湖鎮 金沙鎮 金寧鄉 烈嶼鄉 烏坵鄉',
  連江縣: '南竿鄉 北竿鄉 莒光鄉 東引鄉',
};
const TOWN_OF = /* @__PURE__ */ Object.entries(TOWNS).flatMap(([c, list]) => list.split(' ').map(t => [t, c]));
// 地點只寫地標的（路協的表常見）：只收很確定的幾個
const LANDMARK = { 總統府: '臺北市', 凱達格蘭: '臺北市', 大佳河濱: '臺北市', 陽明山: '臺北市', 臺北101: '臺北市', 美堤河濱: '臺北市',
  夢時代: '高雄市', 駁二: '高雄市', 溪頭: '南投縣', 日月潭: '南投縣', 阿里山: '嘉義縣', 墾丁: '屏東縣', 太魯閣: '花蓮縣', 金城: '金門縣',
  // 超馬協會每年固定的場地（v4.18.0）：地點只寫「新莊 田徑場」「東吳大學 外雙溪校區」「55K 新店國小」
  東吳大學: '臺北市', 新莊田徑場: '新北市', 新店國小: '新北市' };
const OVERSEAS = /日本|韓國|不丹|泰國|越南|柬埔寨|馬來西亞|新加坡|香港|澳門|中國|美國|加拿大|英國|法國|德國|義大利|澳洲|紐西蘭|海外|沖繩|東京|大阪|京都|名古屋|北海道|福岡|首爾|釜山|曼谷|清邁|吳哥|峴港|雪梨|柏林|倫敦|波士頓|芝加哥|紐約|巴黎/;
const toTai = s => String(s || '').replace(/台/g, '臺');
function regionOf(city) {
  for (const [r, list] of Object.entries(REGION_OF)) if (list.includes(city)) return r;
  return '';
}
// 依序看每一段文字（地點、名稱…），第一個認得出縣市的就用它
function findCity(...texts) {
  for (const raw of texts) {
    const s = toTai(raw);
    if (!s) continue;
    let best = null;
    for (const c of COUNTIES) { const i = s.indexOf(c); if (i >= 0 && (!best || i < best.i)) best = { i, c }; }
    if (best) return { city: best.c, region: regionOf(best.c) };
    for (const [k, c] of TOWN_OF) { const i = s.indexOf(k); if (i >= 0 && (!best || i < best.i)) best = { i, c }; }
    if (best) return { city: best.c, region: regionOf(best.c) };
    for (const [k, c] of Object.entries(SHORT)) { const i = s.indexOf(k); if (i >= 0 && (!best || i < best.i)) best = { i, c }; }
    if (best) return { city: best.c, region: regionOf(best.c) };
    const flat = s.replace(/\s+/g, '');   // 「新莊 田徑場」這種中間斷行的也認得
    for (const [k, c] of Object.entries(LANDMARK)) if (flat.includes(k)) return { city: c, region: regionOf(c) };
  }
  for (const raw of texts) { const m = String(raw || '').match(OVERSEAS); if (m) return { city: m[0] === '海外' ? '' : m[0], region: 'overseas' }; }
  return { city: '', region: '' };
}

// ---------------- 日本：都道府縣、地區（v4.18.0） ----------------
const JP_PREFS = ['北海道', '青森県', '岩手県', '宮城県', '秋田県', '山形県', '福島県', '茨城県', '栃木県', '群馬県', '埼玉県', '千葉県', '東京都', '神奈川県',
  '新潟県', '富山県', '石川県', '福井県', '山梨県', '長野県', '岐阜県', '静岡県', '愛知県', '三重県', '滋賀県', '京都府', '大阪府', '兵庫県', '奈良県', '和歌山県',
  '鳥取県', '島根県', '岡山県', '広島県', '山口県', '徳島県', '香川県', '愛媛県', '高知県', '福岡県', '佐賀県', '長崎県', '熊本県', '大分県', '宮崎県', '鹿児島県', '沖縄県'];
// 地區：北海道・東北／關東／中部（北陸、甲信越、東海）／近畿（含三重）／中國・四國／九州・沖繩
const JP_REGION_AT = [[0, 'hokkaido-tohoku'], [7, 'kanto'], [14, 'chubu'], [23, 'kinki'], [30, 'chugoku-shikoku'], [39, 'kyushu-okinawa']];
function jpRegionOf(pref) {
  const i = JP_PREFS.indexOf(pref);
  if (i < 0) return '';
  let r = '';
  for (const [start, id] of JP_REGION_AT) if (i >= start) r = id;
  return r;
}
// 地點只寫市名的（「(指宿市)」「那覇」）：政令指定都市和常辦比賽的幾個；台灣寫法的「沖繩」也認
const JP_CITY = { 札幌: '北海道', 仙台: '宮城県', さいたま: '埼玉県', 千葉市: '千葉県', 横浜: '神奈川県', 川崎: '神奈川県', 相模原: '神奈川県', 新潟市: '新潟県',
  静岡市: '静岡県', 浜松: '静岡県', 名古屋: '愛知県', 京都市: '京都府', 大阪市: '大阪府', 堺: '大阪府', 神戸: '兵庫県', 岡山市: '岡山県', 広島市: '広島県',
  北九州: '福岡県', 福岡市: '福岡県', 熊本市: '熊本県', 那覇: '沖縄県', 沖繩: '沖縄県', 指宿: '鹿児島県', 富士吉田: '山梨県', 河口湖: '山梨県', 青梅: '東京都',
  // 每年固定的大會、清單上只寫地名的（v4.18.0 實際資料看到的）：しまなみ海道（今治）、日田、新城、那珂總合公園（那珂川市在福岡，所以寫全名）
  しまなみ: '愛媛県', 日田: '大分県', 新城市: '愛知県', 那珂総合公園: '茨城県' };
function findPref(...texts) {
  for (const raw of texts) {
    const s = String(raw || '');
    if (!s) continue;
    let best = null;
    for (const p of JP_PREFS) { const i = s.indexOf(p); if (i >= 0 && (!best || i < best.i)) best = { i, p }; }
    if (best) return { city: best.p, region: jpRegionOf(best.p) };
    // 沒寫「県」「府」「都」：先比「東京都」再比「京都」，免得東京被認成京都
    for (const p of JP_PREFS) { const bare = p === '北海道' ? p : p.slice(0, -1); const i = s.indexOf(bare); if (bare.length >= 2 && i >= 0 && (!best || i < best.i)) best = { i, p }; }
    if (best) return { city: best.p, region: jpRegionOf(best.p) };
    for (const [k, p] of Object.entries(JP_CITY)) if (s.includes(k)) return { city: p, region: jpRegionOf(p) };
  }
  return { city: '', region: '' };
}
// 國家：台灣的網站寫在「海外」的，認得出是日本就算日本（沖繩馬拉松、東京馬拉松），其他算其他國家
const JP_WORDS = /日本|沖繩|沖縄|東京|大阪|京都|名古屋|北海道|福岡|札幌|神戸|横浜|橫濱|那覇|富士山|仙台/;
function countryOf(r) {
  if (r.country) return r.country;
  if (r.region !== 'overseas') return 'tw';
  return JP_WORDS.test([r.city, r.venue, r.name].join(' ')) || findPref(r.city, r.venue).city ? 'jp' : 'other';
}

// ---------------- 種類、距離 ----------------
// App 的 sportType；順序有關係：「越野馬拉松」是越野、「垂直馬拉松」是體能挑戰、「泳渡…路跑」看網站給的類型。
// v4.18.0：體能挑戰（障礙賽、HYROX、垂直馬拉松）排最前面；日文的寫法（JTB、MSPO）；「超鐵」「小鐵人」「鐵人賽」是三鐵
const TYPE_RULES = [
  ['obstacle_race', /障礙賽|obstacle|spartan|斯巴達|hyrox|\bdeka\b|垂直馬拉松|登高賽|爬樓梯|tough\s*mudder|スパルタン|オブスタクル|障害物/i],
  ['triathlon', /鐵人三項|三鐵|超鐵|超級鐵人|小鐵人|triathlon|ironman|\b226\b|\b113\b|51\.5|70\.3|トライアスロン/i],
  ['duathlon', /鐵人兩項|鐵人二項|二鐵|duathlon|aquathlon|デュアスロン|アクアスロン|バイク\s*[＆&]\s*ラン|swim\s*[＆&]\s*run|スイム\s*[＆&]\s*ラン/i],   // 「SWIM & RUN」是游泳＋跑步的二項
  ['triathlon', /鐵人/],   // 「鐵人賽」沒寫幾項的算三鐵（二鐵上面先認了）
  ['cycling', /自行車|單車|騎行|陪騎|公路車|登山車|自由車|gravel|cycling|bicycle|\bbike\b|\bmtb\b|サイクリング|ヒルクライム|エンデューロ|グランフォンド|自転車|ライド/i],
  ['swimming', /游泳|泳渡|公開水域|open\s*water|\bswim|オープンウォーター|スイム|遠泳|水泳/i],
  /* 健走、登山算其他，而且要排在越野前面：「古道健行」是爬山不是越野跑；
     但名稱裡也有跑步的（「路跑X健走大賽」「慢跑健走嘉年華」「古道越野」）照跑步算 */
  ['other', /^(?!.*(?:跑|馬拉松|越野|run|marathon|マラソン|トレラン)).*(?:健走|健行|步道|登山|walk|hiking|ウォーク|ウォーキング|ハイキング)/i],
  ['trail_running', /越野|山徑|trail|古道|天梯|動感亞洲|action\s*asia|トレイル|トレラン/i],   // 動感亞洲辦的都是越野賽
  ['ultra_marathon', /超馬|超級馬拉松|ultra|ウルトラ/i],
  ['road_running', /馬拉松|路跑|夜跑|慢跑|跑|run|marathon|\d{3,5}\s*公尺|マラソン|ラン|駅伝|ジョギング/i],   // 「5000公尺挑戰賽」也是跑步
];
const WALK_RE = TYPE_RULES.find(([t]) => t === 'other')[1];
const SITE_TYPE = { 路跑: 'road_running', 馬拉松: 'road_running', 超級馬拉松: 'ultra_marathon', 越野: 'trail_running', 越野跑: 'trail_running',
  自行車: 'cycling', 單車: 'cycling', 健行: 'other', 健走: 'other', 鐵人三項: 'triathlon', 鐵人兩項: 'duathlon', 游泳: 'swimming' };
function detectType(name, siteType, cats) {
  if (siteType && SITE_TYPE[siteType.trim()]) return SITE_TYPE[siteType.trim()];
  for (const [t, re] of TYPE_RULES) if (re.test(name || '')) return t;
  // 名稱看不出來、組別寫成「1.5K+40K+10K」：三段是三鐵、兩段是二鐵（v4.18.0，跑者廣場的鐵人賽常常這樣）
  const legs = Math.max(0, ...(cats || []).map(c => (String(c).match(/[+＋]/g) || []).length + 1));
  if (legs >= 3) return 'triathlon';
  if (legs === 2) return 'duathlon';
  return 'other';
}
// 不是比賽的活動（講座、訓練營、志工、試乘…）不放進清單；
// JTB 上的「ストライダー」是 2～5 歲幼兒的滑步車賽，一個月好幾場，會把日本的單車塞滿（v4.18.0）
const NOT_RACE = /講座|訓練營|志工|招募|試乘|籃球|說明會|課程|研習|座談|工作坊|講習|分享會|ボランティア|講習会|説明会|セミナー|ストライダー|STRIDER/i;
// 賽事頁的地點欄常常只寫「詳見簡章」「詳細內容請洽內文」：這種不算地點
const NOT_VENUE = /簡章|內文|請洽|洽詢|詳見|待公[布告]|另行公告|未定/;
/* 組別文字裡的距離（公里）：42.195K、21KM半馬組、45公里超馬組、5.K（網站打錯）、約12.5KM、5000公尺；
   沒寫數字的「全馬」「半馬」照標準距離。不到 0.5 公里的不算（公勝盃的 0.1K 是趣味組）。 */
function parseDistances(texts) {
  const out = [];
  for (const raw of texts || []) {
    let s = String(raw || '');
    let found = false;
    // 鐵人的「1.5K+40K+10K」是一組三段，加起來 51.5K 才是這一組的距離（v4.18.0）
    s = s.replace(/\d+(?:\.\d+)?\s*(?:k(?:m)?|公里)?(?:\s*[+＋]\s*\d+(?:\.\d+)?\s*(?:k(?:m)?|公里)?)+/gi, chain => {
      out.push((chain.match(/\d+(?:\.\d+)?/g) || []).reduce((a, b) => a + +b, 0)); found = true; return ' ';
    });
    for (const m of s.matchAll(/(\d+(?:\.\d+)?)\s*(?:英里|miles?)(?![a-z])/gi)) { out.push(+m[1] * 1.609344); found = true; }   // 超馬的 100 英里
    for (const m of s.matchAll(/(\d+(?:\.\d+)?)\s*\.?\s*(?:k(?:m)?|公里)(?![a-z])/gi)) { out.push(+m[1]); found = true; }
    for (const m of s.matchAll(/(\d{3,5})\s*(?:公尺|m)(?![a-z])/gi)) { out.push(+m[1] / 1000); found = true; }
    if (!found) {
      if (/全馬|全程馬拉松|全程組|フルマラソン|^フル$/.test(s)) out.push(42.195);
      if (/半馬|半程馬拉松|半程組|ハーフマラソン|^ハーフ$/.test(s)) out.push(21.0975);
    }
  }
  return [...new Set(out.filter(x => x >= 0.5 && x <= 1000).map(x => Math.round(x * 1000) / 1000))].sort((a, b) => b - a);
}
const cleanName = s => String(s || '').replace(/<br\s*\/?>/gi, ' ').replace(/\s+/g, ' ').trim();
// 一格裡用 <br> 分開的每一行（超馬協會的表格一格塞了系列名、標語、名稱好幾行）
function linesOf(el) {
  if (!el) return [];
  const c = el.cloneNode(true);
  for (const br of [...c.querySelectorAll('br')]) br.parentNode.replaceChild(el.ownerDocument.createTextNode('\n'), br);
  return String(c.textContent || '').replace(/\u00a0/g, ' ').split('\n').map(s => s.replace(/\s+/g, ' ').trim()).filter(Boolean);
}
// 網站沒有編號的（跑者廣場、超馬協會）：用日期＋名稱算一個短碼，名稱和日期不變就一樣
function h32(s) { let h = 0x811c9dc5; for (const ch of String(s)) { h ^= ch.codePointAt(0); h = Math.imul(h, 0x01000193) >>> 0; } return h.toString(36); }
const REG_HOSTS = /bao-ming\.com|lohasnet\.tw|sportaiwan\.com|irunner\.biji\.co|joinnow\.com\.tw|ctrun\.com\.tw|eventpal|focusline|beclass\.com|accupass|kktix|ironman\.com|actionasiaevents|ezsignup|soonnet/i;
const CANCELLED = /[(（]\s*(停賽|停辦|取消|延期)\s*[)）]/;

// ---------------- 運動筆記（irunner.biji.co/list） ----------------
/* 一個月一塊 .month-wrap，每一列 .competition-list-row：data-year、data-month（202705）、
   .competition-date「05-22 (週六)」或「見簡章」、.competition-place、.competition-name a（相對網址）、
   .competition-event .event-item（距離，多半是空的）、.competition-status「12-07 開報」「10-31 截止」「已截止報名」「已額滿」「延期辦理」 */
function parseIrunnerList(doc, base = 'https://irunner.biji.co/') {
  const out = [];
  for (const r of doc.querySelectorAll('#competition-inner .competition-list-row')) {
    const a = r.querySelector('.competition-name a');
    if (!a || !a.getAttribute('href')) continue;
    const name = cleanName(txt(a));
    if (!name || NOT_RACE.test(name)) continue;
    const ym = String(r.getAttribute('data-month') || '');
    const year = +ym.slice(0, 4) || +r.getAttribute('data-year');
    const dm = txt(r.querySelector('.competition-date')).match(/(\d{1,2})-(\d{1,2})/);
    const date = dm && year ? ymd(year, dm[1], dm[2]) : null;
    const month = /^\d{6}$/.test(ym) ? ym.slice(0, 4) + '-' + ym.slice(4) : (date ? date.slice(0, 7) : null);
    const place = txt(r.querySelector('.competition-place'));
    const cats = [...r.querySelectorAll('.competition-event .event-item')].map(txt).filter(Boolean);
    const status = txt(r.querySelector('.competition-status'));
    const anchor = date || (month ? month + '-28' : null);
    let regOpen = null, regClose = null, siteState = null;
    let m = status.match(/(\d{1,2})-(\d{1,2})\s*開報/); if (m) regOpen = yearBefore(m[1], m[2], anchor);
    m = status.match(/(\d{1,2})-(\d{1,2})\s*截止/); if (m) regClose = yearBefore(m[1], m[2], anchor);
    if (/額滿/.test(status)) siteState = 'full';
    else if (/已截止/.test(status)) siteState = 'closed';
    else if (regClose) siteState = 'open';                 // 「10-31 截止」：網站上現在報得到，10/31 截止
    if (/延期|停辦|停賽|取消/.test(status) || CANCELLED.test(name)) siteState = 'cancelled';
    const slug = a.getAttribute('href').trim();
    const url = new URL(slug, base).href;
    const loc = findCity(/簡章|依活動/.test(place) ? '' : place, name);
    out.push({ source: 'irunner', sid: slug, name, date, dateEnd: null, month, city: loc.city, region: loc.region, venue: '',
      type: detectType(name), distances: parseDistances(cats), cats, regOpen, regClose, siteState, url, urlKind: 'register', detailUrl: url });
  }
  return out;
}
// 賽事頁：.detail-item（日曆圖示＝日期、地圖圖示＝地點）、報名時間的「起」「迄」
function parseIrunnerDetail(doc) {
  const out = {};
  for (const it of doc.querySelectorAll('.detail-item')) {
    const i = it.querySelector('i'); const cls = i ? String(i.getAttribute('class') || '') : '';
    const v = txt(it);
    if (/fa-calendar/.test(cls)) { const d = parseFullDate(v); if (d) out.date = d; }
    if (/fa-map-marker/.test(cls) && v && !NOT_VENUE.test(v)) out.venue = v;
  }
  for (const li of doc.querySelectorAll('li.stack-column-item')) {
    if (!/報名時間/.test(txt(li.querySelector('.data-title')))) continue;
    for (const g of li.querySelectorAll('.itags')) {
      const tags = [...g.querySelectorAll('.itag')].map(txt);
      const d = parseFullDate(tags.join(' '));
      if (!d) continue;
      if (/起/.test(tags[0] || '')) out.regOpen = d;
      if (/迄/.test(tags[0] || '')) out.regClose = d;
    }
  }
  return out;
}

// ---------------- 全統（ctrun.com.tw 首頁） ----------------
/* 每一場 .pri_table_list：.pic a（/Activity?EventMain_ID=366）、h6＋h4 是名稱的前後兩段、
   li 用圖示分：fa-calendar 日期「2027年1月10日 (星期日)」、fa-flag 距離徽章、fa-map-marker-alt 地點；
   按鈕「搶先報名」「我要報名」「報名截止」；已結束的沒有按鈕、改成「活動照片」。徽章「已額滿」。 */
function parseCtrunHome(doc, base = 'https://www.ctrun.com.tw/') {
  const out = [], seen = new Set();
  for (const x of doc.querySelectorAll('.pri_table_list')) {
    const a = x.querySelector('.pic a[href*="EventMain_ID"]');
    const id = a && (String(a.getAttribute('href')).match(/EventMain_ID=(\d+)/) || [])[1];
    if (!id || seen.has(id)) continue;
    seen.add(id);
    const h6 = cleanName(txt(x.querySelector('h6'))), h4 = cleanName(txt(x.querySelector('h4')));
    const name = [h6, h4].filter(Boolean).join(' ');
    if (!name || NOT_RACE.test(name)) continue;
    const li = cls => [...x.querySelectorAll('li')].find(l => l.querySelector('.' + cls));
    const date = parseFullDate(txt(li('fa-calendar')));
    const flag = li('fa-flag');
    const cats = flag ? [...flag.querySelectorAll('.badge')].map(txt).filter(Boolean) : [];
    const venue = txt(li('fa-map-marker-alt'));
    const btn = x.querySelector('button.eventBtnReg');
    const btnText = btn ? (btn.getAttribute('title') || txt(btn)) : '';
    const badge = txt(x.querySelector('.easy-block-v1-badge'));
    let siteState = null;
    if (!btn) siteState = 'closed';                       // 活動照片、成績查詢：已經比完
    else if (/截止/.test(btnText)) siteState = 'closed';
    else if (!btn.hasAttribute('disabled') && /報名/.test(btnText)) siteState = 'open';   // 「我要報名」「搶先報名」都按得下去
    if (/^已額滿$/.test(badge)) siteState = 'full';       // 「3K健走組已額滿」只是某一組
    if (CANCELLED.test(name)) siteState = 'cancelled';
    const url = new URL('/Activity?EventMain_ID=' + id, base).href;
    const loc = findCity(venue, name);
    out.push({ source: 'ctrun', sid: id, name, date, dateEnd: null, month: date ? date.slice(0, 7) : null, city: loc.city, region: loc.region, venue,
      type: detectType(name), distances: parseDistances(cats), cats, regOpen: null, regClose: null, siteState, url, urlKind: 'register', detailUrl: url });
  }
  return out;
}
// 賽事頁的簡章是編輯器打的表格，格式每場不一樣：看整頁文字找「報名時間」後面的日期區間；地點找「活動地點」那一格
function cellAfter(doc, label) {
  for (const el of doc.querySelectorAll('td, th')) {
    if (txt(el) !== label) continue;
    const n = el.nextElementSibling;
    if (n && txt(n)) return txt(n);
  }
  return '';
}
function parseCtrunDetail(doc) {
  const out = {};
  const r = parseRegRange(txt(doc.body || doc.documentElement));
  if (r) Object.assign(out, r);
  const v = cellAfter(doc, '活動地點'); if (v) out.venue = v;
  return out;
}

// ---------------- 一起報名（joinnow.com.tw） ----------------
/* 首頁的表格 tr[data-id]：.td-date「03/28(日)」（沒有年份）、.td-type 類型、第一個 .td-site 縣市、.td-title 名稱、
   第二個 .td-site 地點、.td-item span 組別、.td-state「報名中」「報名截止」「活動已結束」。
   報名頁 run-step1.php?cnt_id=、簡章 about.php?cnt_id=&type=1（報名日期在簡章裡）。 */
function parseJoinnowIndex(doc, today, base = 'https://www.joinnow.com.tw/') {
  const out = [], seen = new Set();
  for (const r of doc.querySelectorAll('table tr[data-id]')) {
    const id = String(r.getAttribute('data-id') || '').trim();
    if (!/^\d+$/.test(id) || seen.has(id)) continue;
    seen.add(id);
    const state = txt(r.querySelector('.td-state')).replace(/查看/g, '').trim();
    if (/已結束/.test(state)) continue;
    const name = cleanName(txt(r.querySelector('.td-title')));
    if (!name || NOT_RACE.test(name)) continue;
    const dm = txt(r.querySelector('.td-date')).match(/(\d{1,2})\s*\/\s*(\d{1,2})/);
    let date = dm ? yearFromToday(dm[1], dm[2], today) : null;
    const ty = name.match(/(20\d\d)/);                      // 名稱寫了年份而且對得上，就照名稱（跨年的時候比較準）
    if (dm && ty && Math.abs(+ty[1] - +(date || today).slice(0, 4)) === 1) { const alt = ymd(ty[1], dm[1], dm[2]); if (alt && alt >= today) date = alt; }
    const sites = [...r.querySelectorAll('.td-site')].map(txt);
    const cats = [...r.querySelectorAll('.td-item span')].map(txt).filter(Boolean);
    let siteState = null;
    if (/報名中/.test(state)) siteState = 'open';
    if (/截止/.test(state)) siteState = 'closed';
    if (/額滿/.test(state)) siteState = 'full';
    if (CANCELLED.test(name)) siteState = 'cancelled';
    const loc = findCity(sites[0], sites[1], name);
    out.push({ source: 'joinnow', sid: id, name, date, dateEnd: null, month: date ? date.slice(0, 7) : null, city: loc.city, region: loc.region, venue: sites[1] || '',
      type: detectType(name, txt(r.querySelector('.td-type'))), distances: parseDistances(cats), cats, regOpen: null, regClose: null, siteState,
      url: new URL('run-step1.php?cnt_id=' + id, base).href, urlKind: 'register', detailUrl: new URL('about.php?cnt_id=' + id + '&type=1', base).href });
  }
  return out;
}
/* 簡章頁：多數場次上方有一排資訊卡 ul.m0820-info（.lb 標籤、.val 值）：活動日期「2026/12/26 (六)」、報名期限「2026/10/31 截止」、活動地點。
   報名期限只有截止日；有些場次在內文另外寫了完整的「報名日期 起至」，有的話用完整的。 */
function parseJoinnowDetail(doc) {
  const out = {};
  const all = txt(doc.body || doc.documentElement);
  const r = parseRegRange(all);
  if (r) Object.assign(out, r);
  for (const li of doc.querySelectorAll('.m0820-info li')) {
    const lb = txt(li.querySelector('.lb')), val = txt(li.querySelector('.val'));
    const d = parseFullDate(val);
    if (lb === '報名期限' && d && !out.regClose) out.regClose = d;
    if (lb === '活動日期' && d) out.date = d;
    if (lb === '活動地點' && val) out.venue = val;
  }
  // 舊版版面沒有資訊卡，同樣的字直接寫在內文：「活動日期2026/12/13(日) 報名期限 2026/05/31 截止」
  const DATE = '(\\d{4}\\s*[/年.\\-]\\s*\\d{1,2}\\s*[/月.\\-]\\s*\\d{1,2})';
  if (!out.date) { const m = all.match(new RegExp('活動日期\\s*[:：]?\\s*' + DATE)); if (m) { const d = parseFullDate(m[1]); if (d) out.date = d; } }
  if (!out.regClose) { const m = all.match(new RegExp('報名期限\\s*[:：]?\\s*' + DATE + '\\s*(?:\\([^)]*\\)\\s*)?截止')); if (m) { const d = parseFullDate(m[1]); if (d) out.regClose = d; } }
  return out;
}

// ---------------- 中華民國路跑協會（sportsnet.org.tw/schedule.php） ----------------
/* table.races：一列一場，td 依序是圖示、場次、日期「01/11(日)」「1/24~25(六~日)」、名稱（連到賽事網站）、地點、項目。
   年份不在表上，看抓的是 schedule_year 哪一年。沒有報名期間、也不是報名頁，連結當「賽事官網」。 */
function parseSportsnet(doc, year) {
  const out = [];
  for (const tr of doc.querySelectorAll('table.races tr')) {
    const c = [...tr.querySelectorAll('td')];
    if (c.length < 6) continue;
    const a = c[3].querySelector('a');
    const name = cleanName(txt(c[3]));
    if (!name || NOT_RACE.test(name)) continue;
    const dm = txt(c[2]).match(/(\d{1,2})\s*\/\s*(\d{1,2})(?:\s*[~～\-]\s*(?:(\d{1,2})\s*\/\s*)?(\d{1,2}))?/);
    const date = dm ? ymd(year, dm[1], dm[2]) : null;
    let dateEnd = dm && dm[4] ? ymd(year, dm[3] || dm[1], dm[4]) : null;
    if (date && dateEnd && dateEnd < date) dateEnd = ymd(year + 1, dm[3] || dm[1], dm[4]);
    const catText = txt(c[5]);
    const cats = catText.split(/\s*\/\s*/).filter(Boolean);
    const loc = findCity(txt(c[4]), name);
    const href = a ? String(a.getAttribute('href') || '').trim() : '';
    out.push({ source: 'sportsnet', sid: String(year) + '-' + txt(c[1]), name, date, dateEnd, month: date ? date.slice(0, 7) : null, city: loc.city, region: loc.region,
      venue: txt(c[4]), type: detectType(name), distances: parseDistances(cats), cats, regOpen: null, regClose: null, siteState: null,
      url: /^https?:\/\//i.test(href) ? href : '', urlKind: 'site', detailUrl: null });
  }
  return out;
}

// 年度下拉選單選到哪一年。網址的年份還沒有行事曆時，網站不會選任何一年、表格是空的；
// 要是哪天改成「沒有就顯示今年」，年份就會標錯，所以一定要對得上才收（對不上就當作那年還沒公布）
function sportsnetYear(doc) {
  const o = doc.querySelector('#yearBox option[selected]');
  const m = o && String(o.getAttribute('value') || '').match(/schedule_year=(\d{4})/);
  return m ? +m[1] : null;
}

// ---------------- 跑者廣場（taipeimarathon.org.tw/contest.aspx「全國賽會」） ----------------
/* 一頁的表格 #GridView1，從這個月列到明年 5 月左右，一列一場：td[0] 每個月第一列有「10月」、td[1] 名稱（連到各報名網站：跑寶島、樂活、
   運動筆記…）、td[3]「10/03 六 05:30」、td[4] 地點、td[5] 每個組別一顆按鈕（「42.195K」「1.5K+40K+10K」）、td[6] 承辦單位、
   td[7] 報名日期「8月14日 ~ 11月21日」「~ 1月29日」「已截止」。日期沒有年份：從今年開始，月份變小就是跨年了。
   我們只讀這一頁，不碰它連過去的網站（跑寶島的條款禁止機器人，連結照樣可以給使用者點）。 */
function parseRunPlaza(doc, today) {
  const out = [];
  const t = doc.querySelector('#GridView1');
  if (!t) return out;
  const tm = +today.slice(5, 7);
  let y = +today.slice(0, 4), prevM = null;
  for (const tr of t.querySelectorAll('tr')) {
    const c = [...tr.querySelectorAll('td')];
    if (c.length < 8) continue;
    const dm = txt(c[3]).match(/(\d{1,2})\s*\/\s*(\d{1,2})(?:\s*[-~～]\s*(?:(\d{1,2})\s*\/\s*)?(\d{1,2}))?/);
    if (!dm) continue;
    const m = +dm[1];
    if (prevM === null) { if (m < tm - 6) y++; } else if (m < prevM) y++;
    prevM = m;
    // 有些名稱前後加了 * 當裝飾（「*2026 新竹市…快樂路跑*」），留著會跟別的網站對不上
    const name = cleanName(txt(c[1])).replace(/^[*＊\s]+|[*＊\s]+$/g, '');
    if (!name || NOT_RACE.test(name)) continue;
    const date = ymd(y, dm[1], dm[2]);
    if (!date) continue;
    let dateEnd = dm[4] ? ymd(y, dm[3] || dm[1], dm[4]) : null;
    if (dateEnd && dateEnd < date) dateEnd = ymd(y + 1, dm[3] || dm[1], dm[4]);
    const cats = [...c[5].querySelectorAll('button')].map(txt).filter(Boolean);
    const regText = txt(c[7]);
    let regOpen = null, regClose = null, siteState = null;
    const rr = regText.match(/(\d{1,2})\s*月\s*(\d{1,2})\s*日\s*[~～]\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日/);
    if (rr) {
      regClose = yearBefore(rr[3], rr[4], date);
      regOpen = regClose ? yearBefore(rr[1], rr[2], regClose) : null;
    } else {
      const rc = regText.match(/[~～]\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日/);
      if (rc) regClose = yearBefore(rc[1], rc[2], date);
      else {
        // 「6月22日 ~」：只寫了開始報名、還沒公布截止日（臺北馬拉松這種），開始日要在比賽之前
        const ro = regText.match(/(\d{1,2})\s*月\s*(\d{1,2})\s*日\s*[~～]\s*(?:$|[(（])/);
        if (ro) regOpen = yearBefore(ro[1], ro[2], date);
      }
    }
    if (/已截止|截止/.test(regText)) siteState = 'closed';
    if (/額滿/.test(regText)) siteState = 'full';
    if (/停辦|延期|取消|停賽/.test(regText) || CANCELLED.test(name)) siteState = 'cancelled';
    const a = c[1].querySelector('a');
    const href = a ? String(a.getAttribute('href') || '').trim() : '';
    const url = /^https?:\/\//i.test(href) ? href : '';
    const venue = txt(c[4]);
    const loc = findCity(venue, name);
    /* 跑者廣場是跑步的賽事行事曆：名稱看不出項目（「六堆客庄巡禮走相逐」、被截斷的「…公益路」）但有公里數的，當路跑，超過全馬當超馬；
       名稱是健走、登山的照樣算其他。猜錯的機會比放在「其他」裡找不到小。 */
    const distances = parseDistances(cats);
    let type = detectType(name, null, cats);
    if (type === 'other' && distances.length && !WALK_RE.test(name)) type = Math.max(...distances) > 42.2 ? 'ultra_marathon' : 'road_running';
    out.push({ source: 'runplaza', sid: date + '-' + h32(name), name, date, dateEnd, month: date.slice(0, 7), city: loc.city, region: loc.region, venue,
      type, distances, cats, regOpen, regClose, siteState,
      url, urlKind: !url || REG_HOSTS.test(url) ? 'register' : 'site', detailUrl: null });
  }
  return out;
}

// ---------------- 中華民國超級馬拉松運動協會（ctau.org.tw 國內賽事行事曆） ----------------
/* 同一頁好幾張表：最上面一張是今年下半年到明年，下面每張前面一段「2026年」「2025年」。一列一場，四格：活動名稱、日期、地點、里程／限時。
   名稱那一格是編輯器打的：「2026 CTAU超馬系列賽」「第二站」「跑馬就是這麼簡單（標語）」「2026第14屆 開廣飛跑盃 超級馬拉松」好幾行，
   名稱從第一個寫了年份的那一行開始；「主辦單位」之後是主辦和備註。日期格「10/10 (六) 09/09前 報名去」：截止日、報名連結都在這格。
   新聞連結的網址也有日期，但有幾列連到舊的新聞（2027 臺北超馬連到 2025 年的），所以不用。
   研習、志工、裁判講習、「組隊參加」的國外錦標賽不是一般人能報的比賽，不收。 */
const CTAU_NOISE = /CTAU\s*超馬系列賽|^第[一二三四五六七八九十\d]+站$|^(?:終極|最終|越野)站$|國家隊|選拔賽|錦標賽|^World|Championships|^Asia|Oceania|^(?:20\d\d\s*)?IAU\b/i;   // 「2027 IAU 24H」是選拔賽的附註
function ctauName(lines) {
  const ls = []; let seriesYear = '';
  for (const raw of lines) {
    const l = raw.replace(/\s+/g, ' ').trim();
    if (/^主辦單位/.test(l)) break;
    if (CTAU_NOISE.test(l)) { const y = l.match(/20\d\d/); if (y && !seriesYear) seriesYear = y[0]; continue; }
    ls.push(l);
  }
  const k = ls.findIndex(l => /20\d\d/.test(l));
  let name = (k >= 0 ? ls.slice(k) : ls).join(' ').replace(/\s*\d版$/, '').replace(/[(（]認證[)）]/g, '').replace(/\s+/g, ' ').trim();
  if (name && !/20\d\d/.test(name) && seriesYear) name = seriesYear + ' ' + name;
  return name;
}
function ctauVenue(lines) {
  const token = /\d+(?:\.\d+)?\s*(?:K|英里|公里|H)\b|\d{1,2}:\d{2}|起跑|終點|限時/i;
  const keep = lines.filter(l => !token.test(l)).slice(0, 3).join(' ');
  if (keep) return keep;
  return (lines[0] || '').replace(/\d+(?:\.\d+)?\s*(?:K|英里|公里)/gi, '').replace(/\s+/g, ' ').trim();
}
function parseCtau(doc, today) {
  const out = [];
  const tm = +today.slice(5, 7);
  /* 年份標題：同一頁下面還有 2011～2025 年的舊行事曆，標題是 <h1>2024年</h1>，而且很多表格跟標題不是兄弟（包在好幾層 div 裡）。
     所以照網頁順序往下看：遇到只寫「20xx年」的元素就記下來，表格用它前面最近的那一個。
     最上面那張沒有標題的是「今年下半年到明年」，月份往回跳就是跨年；標題是今年以前的整張不看（不然舊賽事會被當成明年的）。 */
  const yearOf = new Map(); let cur = null;
  for (const el of doc.querySelectorAll('h1,h2,h3,h4,h5,h6,p,div,strong,b,span,table')) {
    if (el.tagName === 'TABLE') { if (!yearOf.has(el)) yearOf.set(el, cur); continue; }
    if (el.querySelector('table')) continue;
    const m = txt(el).match(/^(20\d\d)\s*年$/);
    if (m) cur = +m[1];
  }
  for (const table of doc.querySelectorAll('table')) {
    if (!/活動名稱/.test(txt(table.querySelector('tr')))) continue;
    let y = yearOf.has(table) ? yearOf.get(table) : null;
    if (y !== null && y < +today.slice(0, 4)) continue;
    const fixedYear = y !== null;
    if (!fixedYear) y = +today.slice(0, 4);
    let prevM = null;
    for (const tr of table.querySelectorAll('tr')) {
      const c = [...tr.querySelectorAll('td')];
      if (c.length < 4 || /活動名稱/.test(txt(c[0]))) continue;
      const lines = linesOf(c[0]);
      const dtext = linesOf(c[1]).join(' ');
      if (NOT_RACE.test(lines.join(' ')) || /參賽|組隊參加/.test(lines.join(' ') + ' ' + dtext)) continue;
      // 年份有時跟日期寫在一起：「2027 01/23」「2019.01/13」「2017-1/14」
      const dm = dtext.match(/(?:(20\d\d)\s*[.\-/]?\s*)?(\d{1,2})\s*\/\s*(\d{1,2})(?:\s*[-~～]\s*(?:(\d{1,2})\s*\/\s*)?(\d{1,2}))?/);
      if (!dm) continue;
      const m = +dm[2];
      if (dm[1]) y = +dm[1];
      else if (!fixedYear) { if (prevM !== null && m < prevM) y++; else if (prevM === null && m < tm - 6) y++; }
      prevM = m;
      const date = ymd(y, dm[2], dm[3]);
      if (!date) continue;
      let dateEnd = dm[5] ? ymd(y, dm[4] || dm[2], dm[5]) : null;
      if (dateEnd && dateEnd < date) dateEnd = ymd(y + 1, dm[4] || dm[2], dm[5]);
      const name = ctauName(lines);
      if (!name) continue;
      const dl = dtext.match(/(\d{1,2})\s*\/\s*(\d{1,2})\s*前/);
      const regClose = dl ? yearBefore(dl[1], dl[2], date) : null;
      const reg = [...c[1].querySelectorAll('a')].find(a => /報名/.test(txt(a)));
      // 沒有報名連結的不用新聞連結：有幾列連到舊的新聞（2027 臺北超馬連到 2025 年的），App 會改給「看超馬協會」的行事曆
      const href = reg ? reg.getAttribute('href') : '';
      const url = /^https?:\/\//i.test(String(href || '')) ? String(href).trim() : '';
      const catLines = linesOf(c[3]).filter(l => /\d/.test(l)).slice(0, 8);
      const distances = parseDistances(catLines);
      let type = detectType(name);
      if ((type === 'road_running' || type === 'other') && distances.some(d => d > 42.2)) type = 'ultra_marathon';
      const venue = ctauVenue(linesOf(c[2]));
      const loc = findCity(venue, name);
      out.push({ source: 'ctau', sid: date + '-' + h32(name), name, date, dateEnd, month: date.slice(0, 7), city: loc.city, region: loc.region, venue,
        type, distances, cats: catLines.slice(0, 6), regOpen: null, regClose, siteState: reg && regClose ? 'open' : null,
        url, urlKind: reg ? 'register' : 'site', detailUrl: null });
    }
  }
  return out;
}

// ---------------- JTB Sports Station（jtbsports.jp，日本） ----------------
/* 清單 list.php 一頁 20 場（li > a[href^=/detail/]），翻頁是 &pageno=2（頁數在 select[name=pageno] 的 data-maxpage）。
   每場：.title 名稱、「開催日：2027年01月16日(土) - 2027年01月16日(土)」「開催場所：…」、[data-event-type] 種類
   （running、trail_running、cycling、triathlon、swimming、walking、other；golf、tour、winter_sports 不收）。
   報名期間在賽事頁 /detail/xxxx：「受付期間」裡每個組別一列「2026年08月01日(土) 00時00分～2026年10月18日(日) 23時59分」。 */
const JTB_TYPE = { running: 'road_running', trail_running: 'trail_running', cycling: 'cycling', triathlon: 'triathlon', swimming: 'swimming', walking: 'other', other: 'other' };
const JP_DATE = /(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日/g;
const jpDates = s => [...String(s || '').matchAll(JP_DATE)].map(m => ymd(m[1], m[2], m[3])).filter(Boolean);
// 日文名稱裡寫了「トレイル」「ウルトラ」「デュアスロン」的，比網站分的大類準
function jpType(name, fallback) {
  for (const [t, re] of TYPE_RULES) {
    if (t === 'road_running' || t === 'other') continue;
    if (re.test(name || '')) return t;
  }
  return fallback;
}
function cleanJpVenue(s) {
  let v = String(s || '').replace(/\s*[(（]?〒[\d-]+/, ' ').replace(/TEL[\d-]+/gi, '').replace(/\s+/g, ' ').trim();
  if (/[)）]$/.test(v) && !/[(（]/.test(v)) v = v.slice(0, -1).trim();   // 郵遞區號那段的括號拿掉了，剩下右括號
  return v.slice(0, 80);
}
const JP_ABROAD = /共和国|海外|ハワイ|ホノルル|グアム|サイパン|パラオ|台湾|台北|韓国|ソウル|タイ|バンコク|ベトナム|シンガポール|マレーシア|オーストラリア|アメリカ|ニューヨーク|ボストン|シカゴ|ロンドン|パリ|ベルリン|フランス|イタリア|ドイツ|スペイン/;
function parseJtbList(doc, base = 'https://jtbsports.jp/') {
  const out = [];
  for (const li of doc.querySelectorAll('li')) {
    const a = [...li.children].find(x => x.tagName === 'A' && /^\/detail\//.test(String(x.getAttribute('href') || '')));
    if (!a) continue;
    const name = cleanName(txt(li.querySelector('.title')) || txt(a));
    if (!name || NOT_RACE.test(name)) continue;
    const types = [...li.querySelectorAll('[data-event-type]')].map(x => String(x.getAttribute('data-event-type')));
    const t0 = types.find(t => JTB_TYPE[t]);
    if (!t0) continue;                                     // 高爾夫、旅遊、冬季運動
    const box = li.querySelector('.c-eventlist__contents__date');
    const ds = jpDates(txt(box));
    const date = ds[0] || null;
    const dateEnd = ds[1] && ds[1] !== date ? ds[1] : null;
    const place = (txt(box).match(/開催場所\s*[:：]\s*(.+)$/) || [])[1] || '';
    const pref = findPref(place, name);
    const href = new URL(a.getAttribute('href'), base).href;
    // JTB 也賣海外的（「パラオ共和国コロール島」）：認不出都道府縣、又寫了外國地名的算其他國家
    const country = !pref.city && JP_ABROAD.test(place + ' ' + name) ? 'other' : 'jp';
    out.push({ source: 'jtb', sid: href.split('/').filter(Boolean).pop(), name, date, dateEnd, month: date ? date.slice(0, 7) : null,
      city: pref.city, region: pref.region, country, venue: cleanJpVenue(place), type: jpType(name, JTB_TYPE[t0]),
      distances: parseDistances([name]), cats: [], regOpen: null, regClose: null, siteState: null, url: href, urlKind: 'register', detailUrl: href });
  }
  return out;
}
function jtbMaxPage(doc) {
  const s = doc.querySelector('select[name="pageno"]');
  return s ? Math.max(1, Math.min(10, +s.getAttribute('data-maxpage') || 1)) : 1;
}
function parseJtbDetail(doc) {
  const out = {};
  const cell = label => { for (const th of doc.querySelectorAll('th')) if (txt(th) === label && th.nextElementSibling) return th.nextElementSibling; return null; };
  const place = txt(cell('開催地'));
  if (place) out.venue = cleanJpVenue(place);
  const reg = cell('受付期間');
  if (reg) {
    const rows = [...reg.querySelectorAll('td')].map(td => jpDates(txt(td))).filter(d => d.length >= 2);
    if (!rows.length) { const d = jpDates(txt(reg)); if (d.length >= 2) rows.push(d); }
    if (rows.length) {
      out.regOpen = rows.map(d => d[0]).sort()[0];
      out.regClose = rows.map(d => d[1]).sort().pop();
    }
    /* 組別：每一列標題裡的距離（「01【フルマラソン】男子30歳未満」「【10kmマラソン】」「A:約31km【大人】」「【一次】個人:500m」）。
       【】裡常常是「一次」「2班」「大人」這種梯次、年齡，不是組別，所以只認距離；㎞、全形數字先換成半形 */
    const tok = [];
    for (const th of reg.querySelectorAll('th')) {
      const s = txt(th).normalize('NFKC');
      for (const m of s.matchAll(/(?:約)?\d+(?:\.\d+)?\s*km(?![a-z])|\d{3,5}\s*m(?![a-z])|フルマラソン|ハーフマラソン/gi)) tok.push(m[0].replace(/\s+/g, '').replace(/^約/, '').toLowerCase());
    }
    const cats = [...new Set(tok)];
    if (cats.length) out.cats = cats.slice(0, 8);
  }
  const d = jpDates(txt(cell('開催日')));
  if (d[0]) out.date = d[0];
  return out;
}

// ---------------- MSPO ENTRY（mspo.jp，日本） ----------------
/* 五個種類的清單頁 /athletic/triathlon、running、swimming、cycling、others，預設列這個月以後的；一頁 20 場、翻頁 ?ss=1&paged=2&athletic=…。
   表格一列一場：td.date「2026/10/03 (土)」、td.syumoku 種目（可能好幾個）、td.title a（/events/67414）、td.kaisaiti 都道府縣、
   td.entry「受付終了」或 a.entry_button「エントリー」。報名期間在大會頁的「申込受付期間」。同一場會出現在好幾個種類的清單裡，用編號去重複。 */
const MSPO_CATS = ['triathlon', 'running', 'swimming', 'cycling', 'others'];
const MSPO_TYPE = [[/トライアスロン/, 'triathlon'], [/デュアスロン|アクアスロン/, 'duathlon'], [/トレイル/, 'trail_running'], [/ウルトラ/, 'ultra_marathon'],
  [/オープンウォーター|スイム|スイミング|水泳/, 'swimming'], [/サイクリング|ロードレース|ヒルクライム|エンデューロ|自転車/, 'cycling'],
  [/マラソン|ランニング|駅伝|リレー|耐久/, 'road_running']];
function parseMspoList(doc) {
  const out = [];
  for (const tr of doc.querySelectorAll('tr')) {
    const td = tr.querySelector('td.date'), a = tr.querySelector('td.title a');
    if (!td || !a) continue;
    const name = cleanName(txt(a));
    if (!name || NOT_RACE.test(name)) continue;
    const dm = txt(td).match(/(\d{4})\s*\/\s*(\d{1,2})\s*\/\s*(\d{1,2})/);
    const date = dm ? ymd(dm[1], dm[2], dm[3]) : null;
    const types = [...tr.querySelectorAll('td.syumoku a')].map(txt).filter(Boolean);
    const prefText = txt(tr.querySelector('td.kaisaiti'));
    const overseas = /海外/.test(prefText);
    const pref = overseas ? { city: '', region: '' } : findPref(prefText, name);
    const entry = tr.querySelector('td.entry a');
    const et = txt(entry), cls = entry ? String(entry.getAttribute('class') || '') : '';
    let siteState = null;
    if (/受付終了|締切|終了/.test(et)) siteState = 'closed';
    else if (/定員/.test(et)) siteState = 'full';
    else if (/entry_button/.test(cls) || /エントリー/.test(et)) siteState = 'open';
    const id = (String(a.getAttribute('href') || '').match(/events\/(\d+)/) || [])[1];
    if (!id) continue;
    let fb = 'other';
    for (const [re, t] of MSPO_TYPE) if (types.some(x => re.test(x))) { fb = t; break; }
    const page = 'https://www.mspo.jp/events/' + id;
    out.push({ source: 'mspo', sid: id, name, date, dateEnd: null, month: date ? date.slice(0, 7) : null, city: pref.city, region: pref.region,
      country: overseas ? 'other' : 'jp', venue: '', type: jpType(name, fb), distances: parseDistances([name]), cats: [], regOpen: null, regClose: null,
      siteState, url: page, urlKind: 'register', detailUrl: page });
  }
  return out;
}
function mspoMaxPage(doc) {
  let n = 1;
  for (const a of doc.querySelectorAll('a[href*="paged="]')) { const m = String(a.getAttribute('href')).match(/paged=(\d+)/); if (m && /athletic=/.test(a.getAttribute('href'))) n = Math.max(n, +m[1]); }
  return Math.min(5, n);
}
function parseMspoDetail(doc) {
  const out = {};
  for (const th of doc.querySelectorAll('th')) {
    if (txt(th) !== '申込受付期間' || !th.nextElementSibling) continue;
    const d = jpDates(txt(th.nextElementSibling));
    if (d[0]) out.regOpen = d[0];
    if (d[1]) out.regClose = d[1];
  }
  return out;
}

// ---------------- 整理：補上賽事頁的資料、合併、排序 ----------------
function applyDetail(rec, d) {
  if (!d) return rec;
  const r = Object.assign({}, rec);
  if (!r.date && d.date) { r.date = d.date; r.month = d.date.slice(0, 7); }
  if (d.venue && !r.venue && !NOT_VENUE.test(d.venue)) r.venue = d.venue;
  /* 清單每天都是新的，賽事頁可能是幾天前存的：清單上已經有的報名日期以清單為準（延長報名時清單會先變）。
     只有月日相同的時候才換成賽事頁的（賽事頁有寫年份，清單的年份是推的）。 */
  for (const k of ['regOpen', 'regClose']) if (d[k] && (!r[k] || r[k].slice(5) === d[k].slice(5))) r[k] = d[k];
  if (!r.city && d.venue && !NOT_VENUE.test(d.venue)) { const loc = r.country === 'jp' ? findPref(d.venue) : findCity(d.venue); if (loc.city) { r.city = loc.city; r.region = loc.region; } }
  if (Array.isArray(d.cats) && d.cats.length && !(r.cats || []).length) { r.cats = d.cats; const ds = parseDistances(d.cats); if (ds.length) r.distances = ds; }
  return r;
}
// 名稱比對用的關鍵字：拿掉年份、屆數、標點、空白，英文小寫
function nameKey(s) {
  return toTai(s).toLowerCase().replace(/20\d\d年?|1\d\d年|第\s*[一二三四五六七八九十百\d]+\s*屆/g, '')
    .replace(/[\s\p{P}\p{S}]/gu, '');
}
function bigrams(s) { const a = []; for (let i = 0; i < s.length - 1; i++) a.push(s.slice(i, i + 2)); return a; }
/* 名稱只有一段一樣的（v4.18.0，跑者廣場加進來以後看到的）：「國聚慵懶跑者聚樂部」和「慵懶跑者聚樂部 COZY RUNNER CLUB」、
   「南投馬11th-草鞋墩馬拉松」和「草鞋墩馬拉松 前進鳥嘴潭、奔向九九峰」。
   先把大家都有的字（國際、半程、馬拉松、縣市名…）換成分隔記號，剩下的還有連續 3 個字一樣才算；
   不然同一天的「○○國際半程馬拉松」「新北市○○路跑」都會被當成同一場。兩邊寫了不同縣市（「新竹場」「台南場」）的一定不是同一場。 */
const PLACE_WORDS = ['臺北', '新北', '基隆', '桃園', '新竹', '宜蘭', '苗栗', '臺中', '彰化', '南投', '雲林', '嘉義', '臺南', '高雄', '屏東', '花蓮', '臺東', '澎湖', '金門', '連江', '馬祖'];
const GENERIC_WORDS = new RegExp('(?:' + PLACE_WORDS.join('|') + ')[市縣]?|國際|全國|半程|全程|馬拉松|路跑|超級|公益|嘉年華|接力|親子|健走|越野|鐵人|三項|兩項|自行車|單車|挑戰|城市|[盃杯賽場市縣]|run|marathon|race|trail|マラソン|大会|ハーフ|リレー|駅伝', 'g');
function longestCommon(a, b) {
  let best = 0; const prev = new Array(b.length + 1).fill(0);
  for (let i = 1; i <= a.length; i++) {
    let diag = 0;
    for (let j = 1; j <= b.length; j++) {
      const keep = prev[j];
      prev[j] = a[i - 1] === b[j - 1] && a[i - 1] !== '|' ? diag + 1 : 0;
      if (prev[j] > best) best = prev[j];
      diag = keep;
    }
  }
  return best;
}
function placesIn(k) { return PLACE_WORDS.filter(w => k.includes(w)); }
function sameRace(a, b) {
  if (!a.date || !b.date) return false;
  const near = a.date === b.date || (a.dateEnd && b.date >= a.date && b.date <= a.dateEnd) || (b.dateEnd && a.date >= b.date && a.date <= b.dateEnd);
  if (!near) return false;
  if (countryOf(a) !== countryOf(b)) return false;      // 臺灣的和日本的不會是同一場（同一天、名稱都有 RUN 也一樣）
  const x = nameKey(a.name), y = nameKey(b.name);
  if (!x || !y) return false;
  const px = placesIn(x), py = placesIn(y);
  if (px.length && py.length && !px.some(w => py.includes(w))) return false;
  if (x.length >= 4 && y.length >= 4 && (x.includes(y) || y.includes(x))) return true;
  /* 其他的比法都用拿掉通用字以後的名稱：「臺南古都國際半程馬拉松」「高雄港都國際半程馬拉松」整段比有七成像，其實只差在「古都」「港都」。
     ① 一邊是另一邊的一部分（「臺中都會…」和「臺中 MIZUNO 都會…」剩「都會」和「mizuno都會」）
     ② 剩下的字有六成像　③ 有連續 3 個漢字一樣（片假名、英文不算：「チャレンジ」「city」太常見） */
  const gx = x.replace(GENERIC_WORDS, '|'), gy = y.replace(GENERIC_WORDS, '|');
  const cx = gx.replace(/\|/g, ''), cy = gy.replace(/\|/g, '');
  if (cx.length >= 2 && cy.length >= 2 && (cx.includes(cy) || cy.includes(cx))) return true;
  const bx = bigrams(cx), by = new Set(bigrams(cy));
  const hit = bx.filter(g => by.has(g)).length;
  if (bx.length && by.size && (2 * hit) / (bx.length + by.size) >= 0.6) return true;
  const han = s => s.replace(/[^\p{Script=Han}]/gu, '|');
  return longestCommon(han(gx), han(gy)) >= 3;
}
// 報名平台優先（有報名狀態）；路協、跑者廣場、超馬協會是行事曆，排後面、合併時補欄位和連結
const RANK = { irunner: 1, ctrun: 1, joinnow: 1, jtb: 1, mspo: 1, sportsnet: 2, runplaza: 2, ctau: 2 };
// 報名網址一樣就是同一場（跑者廣場、超馬協會連到運動筆記、一起報名的那一頁）：網址比對不分 http/https、www、結尾斜線
const urlKey = u => String(u || '').trim().toLowerCase().replace(/^https?:\/\/(www\.)?/, '').replace(/#.*$/, '').replace(/\/+$/, '');
function mergeRaces(list) {
  const out = [];
  for (const r of [...list].sort((a, b) => (RANK[a.source] || 9) - (RANK[b.source] || 9))) {
    // 同一個網站上的兩頁不合併：常是同一場的不同組分開報名（例如 3K 已額滿、半馬已截止），各自的狀態不一樣
    const hit = out.find(x => x.source !== r.source && (sameRace(x, r) || (r.url && urlKey(x.url) === urlKey(r.url) && (!x.date || !r.date || Math.abs(Date.parse(x.date) - Date.parse(r.date)) <= 864e5))));
    if (!hit) { out.push(Object.assign({}, r, { also: [] })); continue; }
    if (r.url) hit.also.push({ source: r.source, url: r.url, urlKind: r.urlKind });
    // 報名網站只寫了月份（「2027富邦人壽高雄馬拉松」）、行事曆有確切日期：用行事曆的
    if (!hit.date && r.date) { hit.date = r.date; hit.month = r.month; }
    for (const k of ['city', 'region', 'venue', 'regOpen', 'regClose', 'dateEnd', 'country']) if (!hit[k] && r[k]) hit[k] = r[k];
    if (!hit.distances.length && r.distances.length) { hit.distances = r.distances; hit.cats = r.cats; }
  }
  return out;
}
// 台灣的網站列在「海外」的日本賽事（沖繩馬拉松）：地區換成日本的地區，篩「九州・沖繩」也找得到
function jpFix(r) {
  if (r.region !== 'overseas' || countryOf(r) !== 'jp') return r.region;
  return findPref(r.city, r.venue, r.name).region || '';
}
// 最後的清單：只留今天以後、一年多以內的；依日期排，沒有日期的排在那個月最後
function buildRaces(records, today) {
  const horizon = addDays(today, 430);
  const keep = records.filter(r => {
    const d = r.date || (r.month ? r.month + '-28' : null);
    if (!d) return false;
    if ((r.dateEnd || r.date || r.month + '-28') < today) return false;
    return d <= horizon;
  });
  const merged = mergeRaces(keep);
  merged.sort((a, b) => ((a.date || a.month + '-99') < (b.date || b.month + '-99') ? -1 : (a.date || a.month + '-99') > (b.date || b.month + '-99') ? 1 : a.name.localeCompare(b.name, 'zh-Hant')));
  return merged.map(r => ({
    id: r.source + ':' + r.sid, name: r.name, date: r.date, dateEnd: r.dateEnd || null, month: r.month, country: countryOf(r), city: r.city, region: jpFix(r), venue: r.venue,
    type: r.type, distances: r.distances, cats: r.cats.slice(0, 8), regOpen: r.regOpen, regClose: r.regClose, siteState: r.siteState,
    url: r.url, urlKind: r.urlKind, source: r.source, also: r.also,
  }));
}

const SOURCES = {
  irunner: { name: '運動筆記', home: 'https://irunner.biji.co/list' },
  ctrun: { name: '全統運動報名網', home: 'https://www.ctrun.com.tw/' },
  joinnow: { name: '一起報名', home: 'https://www.joinnow.com.tw/index.php' },
  sportsnet: { name: '中華民國路跑協會', home: 'https://www.sportsnet.org.tw/schedule.php' },
  runplaza: { name: '跑者廣場（全國賽會）', home: 'http://www.taipeimarathon.org.tw/contest.aspx' },
  ctau: { name: '中華民國超級馬拉松運動協會', home: 'https://www.ctau.org.tw/%E8%B3%BD%E4%BA%8B%E8%88%87%E8%A8%93%E7%B7%B4/%E8%B3%BD%E4%BA%8B%E8%A1%8C%E4%BA%8B%E6%9B%86/%E5%9C%8B%E5%85%A7%E8%B3%BD%E4%BA%8B%E8%A1%8C%E4%BA%8B%E6%9B%86/' },
  jtb: { name: 'JTBスポーツステーション', home: 'https://jtbsports.jp/list.php?orderby=3&accepting=0&keyword=' },
  mspo: { name: 'MSPO ENTRY', home: 'https://www.mspo.jp/athletic/triathlon' },
};

export {
  ymd, addDays, yearBefore, yearFromToday, parseFullDate, parseRegRange, findCity, regionOf, detectType, parseDistances, nameKey, sameRace,
  parseIrunnerList, parseIrunnerDetail, parseCtrunHome, parseCtrunDetail, parseJoinnowIndex, parseJoinnowDetail, parseSportsnet, sportsnetYear,
  parseRunPlaza, parseCtau, ctauName, parseJtbList, jtbMaxPage, parseJtbDetail, parseMspoList, mspoMaxPage, parseMspoDetail, MSPO_CATS,
  findPref, jpRegionOf, countryOf, applyDetail, mergeRaces, buildRaces, SOURCES, NOT_RACE,
};
