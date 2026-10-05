# 暫時拿掉的功能

> **v4.19.0 拿掉**：使用者說這幾個功能現在用的人不多、也不太好用，先收起來，之後要改再拿回來。
> 這份檔案留著拿掉時的**完整原始碼**（從 v4.18.2 原封不動搬過來）、翻譯、使用說明的句子和測試。照第 4 節「怎麼拿回來」貼回去，就會恢復成 v4.18.2 的樣子，再從那裡改。
>
> **資料沒有動**：賽事裡的目標（A／B／C）、當日氣象、氣候平均溫、分段、海拔剖面、CP 都還在。這三個功能本來就只是「讀」這些資料來算，拿回來就會照樣算出來。瀏覽器裡「含越野」的開關（localStorage `climate-include-trail-v1`）也還留著。

## 目錄

1. [環境折損預測（EPP）](#1-環境折損預測epp)
2. [氣候與表現散佈圖](#2-氣候與表現散佈圖)
3. [配速試算與手環產生器](#3-配速試算與手環產生器)
4. [怎麼拿回來](#4-怎麼拿回來)
5. [原始碼](#5-原始碼)
6. [翻譯（日文、英文）](#6-翻譯日文英文)
7. [使用說明的句子](#7-使用說明的句子)
8. [測試](#8-測試)

---

## 1. 環境折損預測（EPP）

- **在哪**：賽事頁「裝備、補給與戰略（賽前準備）」→「賽前目標」卡的下面，只有完整版有。
- **做什麼**：從過去的完賽紀錄算兩個係數：
  - **高溫折損**：體感 15°C 以上的路跑賽事，「配速比同距離 PB 慢幾 %」對溫度做線性迴歸（至少 4 場）。
  - **爬升折損**：同一場賽事自己的分段，「配速比這場平均慢幾 %」對坡度做迴歸（至少 2 場、6 個分段）。

  再拿全馬＞半馬＞10K 的 PB 配速當基準，套到這一場的距離、爬升、氣溫：有海拔剖面就逐段算（15 公里以下每 1 公里一段，更長的每 3 公里），7 天內有逐時預報就照「預估跑到那裡的時刻」查溫度。結果畫成瀑布圖（基準／爬升／高溫／其他因素／實際完賽或 AI 預測），給一個「AI 預測完賽時間」，可以「採用為 A／B／C 目標」，也可以展開逐公里預測表（區間、淨爬升、預測配速、預估抵達時刻）。
- **為什麼拿掉**：使用者說用的人不多、不好用。從截圖看得到的問題（一場 16.84 km 的越野賽）：
  - 高溫係數 R²=0.08、爬升係數 R²=0.01：兩條迴歸線幾乎解釋不了配速的差異，卻還是拿來算出一個精確到秒的「AI 預測完賽時間」。
  - 基準是路跑的 PB 配速，拿來套越野賽本來就不準。截圖裡「其他因素」那一根比基準還高，表示大部分的時間模型都解釋不了。
  - 瀑布圖的字太小（11px 的字縮在 180px 高的圖裡），看不出每一根是幾分幾秒。
  - 叫「AI 預測」，其實是線性迴歸，名字讓人期待太高。
- **之後可以怎麼改**（想法，還沒驗證）：
  - R² 太低就不給單一時間，改給一個區間（例如 1:10–1:25），或直接寫「資料還不夠」。
  - 越野另外一套基準：等效距離（例如每爬升 100 m 算 1 km），或拿自己越野賽的成績當基準，不用路跑 PB。
  - 瀑布圖每一根上面直接寫「+6:12」，圖至少 240px 高；或乾脆不畫圖，改成一句話：「這場最大的敵人是爬升，大約 +6 分鐘」。
  - 名字改成「預估完賽時間」。
  - 逐公里預測跟第 3 點的配速手環合併成一個東西。

## 2. 氣候與表現散佈圖

- **在哪**：首頁「生涯數據」分頁，在累積爬升趨勢圖和每月熱力圖中間，只有完整版有。
- **做什麼**：每一場完賽的路跑畫一個點。X 軸是體感溫度，Y 軸是「配速比個人距離曲線慢幾 %」。距離曲線用 Riegel 公式 T = e^a × D^k，k 用自己各距離的最佳成績擬合，資料不夠就用 1.06。圖例：金點是該距離最佳，空心的是只有氣候平均溫（估計值），三角形是越野（勾了「含越野」才收，用 EPP 的爬升係數校正回平地）。另外畫趨勢線（R² < 0.4 時畫成淡的虛線）和甜蜜點（效率 98% 以上那幾場的溫度範圍），圖下面寫斜率、R²、場數、最佳作戰溫度帶、效率基準。
- **為什麼拿掉**：使用者說用的人不多、不好用。從截圖看得到的問題：
  - R²=0.14（41 場）：氣溫只解釋一成多的差異，趨勢線沒有參考價值，圖下面還得掛一段「R² 偏低…」的警語。
  - 「最佳作戰溫度帶 -2~19°C（依 2 場）」：只有 2 場、範圍跨 21 度，等於沒說。
  - Y 軸被兩三個 -60% 以下的點拉到 -69%，其他點全擠在最上面一小條。
  - 圖例的字疊在一起（「各距離最佳」「氣候平均溫」）。
- **之後可以怎麼改**：
  - 改成「依溫度分段的中位數」長條圖：10°C 以下、10–15、15–20、20–25、25°C 以上各一根，寫上場數。比散佈圖加趨勢線好讀。
  - 離群值先排除（DNF 邊緣、走完的那幾場），或 Y 軸截在 -30%，超出去的點畫在邊上。
  - 甜蜜點至少 5 場才顯示。
  - 不一定要常駐在生涯數據，也可以放進年度回顧。

## 3. 配速試算與手環產生器

- **在哪**：賽事頁「裝備、補給與戰略」裡的一顆按鈕，按了開一個彈窗，只有完整版有。
- **做什麼**：輸入目標時間（預填 A 目標）、總距離（預填這場的距離）、配速策略（勻速；負分段、正分段是前後段配速各差 4%）、分段間隔（每 5、10、1 公里），算出每個點的預計通過時間。可以下載成手環圖片：寬 360px、深綠底，最上面是賽事名稱（只取前 16 個字）。
- **為什麼拿掉**：使用者說用的人不多、不好用。從截圖（下載的手環圖）看得到的問題：
  - 越野賽一樣把時間平均分配，沒看爬升。一場 16.84 km 的越野賽，每 5 公里的時間沒有參考價值。
  - 只有累計時間，沒有每一段的配速。
  - 賽事名稱在第 16 個字被切掉。
  - 360px 的圖印出來多大、怎麼貼在手上，沒有說明。
- **之後可以怎麼改**：
  - 用海拔剖面調整每一段的時間（可以跟 EPP 的逐段引擎合併），至少用 GAP（坡度校正配速）。
  - CP 站直接當分段點，跟應援指南卡用同一份時間。
  - 手環圖照實際尺寸輸出（例如 2.5 cm × 20 cm、300 dpi），名稱太長自動縮小字級，不要截斷。
- **沒有拿掉的**：`pacingTimeAtDistance()`（配速插值公式）。應援指南卡算 CP 預計通過時間在用；原本兩邊共用，拿回來時繼續共用這一個，不要各寫一份。

---

## 4. 怎麼拿回來

位置都用前後的程式碼找（搜尋那一行），不要用行號，行號每一版都會變。全部貼回去就是 v4.18.2 的樣子；只要拿回其中一個功能，就只貼那個功能的段落（第 5 節每一段都寫了屬於哪個功能）。

**注意相依**：氣候散佈圖的「含越野」要用 EPP 的爬升係數（`computeGravityCoefficient`），兩個都在 5-4 那一大段裡。只拿回散佈圖也要貼整段 5-4（裡面的 EPP 畫面函式不呼叫就不會出現）。

1. **CSS**（5-1）：照每一段寫的位置貼回 `<style>` 裡。
2. **HTML**（5-2）：配速試算的彈窗容器，貼在 `<div id="help-modal" …>` 的前一行。
3. **JS**：
   - 5-4（氣候資料層＋EPP 模型＋EPP 畫面）：貼在 `function formatPace(secPerKm){…}` 後面、`function computeCareerStats(){` 前面。
   - 5-5（氣候散佈圖）：貼在 `function heatmapHtml(){` 前面。
   - 5-6（配速試算）：把 `pacingTimeAtDistance` 上面那段註解換回 5-6 的原文，再把其餘的函式貼在 `pacingTimeAtDistance` 後面。
4. **呼叫的地方、按鈕的處理**（5-3）：
   - 生涯數據：`${simpleHome?'':elevationTrendChartSvg()}` 下一行加回散佈圖。
   - 賽事頁：`${goalsDashCardHtml(race)}` 下一行加回 EPP 和配速試算的按鈕。
   - 點擊處理：`toggle-epp-segments` 貼在 `toggle-fatigue-contrast` 那一段前面；`epp-adopt-goal` 貼在 `trigger-geo-photo-input` 那一段前面；`open-pacing-modal` 貼在 `open-profile-modal` 那一行後面。
   - 返回鍵、Esc 的清單加回 `'pacing-modal'`（`BACK_LAYER_IDS` 放在 `'sync-diag-modal'` 後面、Esc 的 `modalIds` 放在 `'shoe-modal'` 後面）。
5. **翻譯**（第 6 節）：62 個 key 貼回 `JA`、`EN` 字典（只貼要拿回的功能的那幾個也可以，前綴是 `ui.epp`、`ui.climate`、`ui.pacing`、`ui.wristband`、`ui.downloadWristband`）。
6. **使用說明**（第 7 節）：配速試算那一句貼回「裝備補給與戰略」那一條（中、日、英）。
7. **測試**（第 8 節）：`Climate` 群組貼回 `test_suite.py`、`GROUPS` 加回 `'climate'`；簡易版那兩項照第 8 節改回來；`v419` 群組裡確認「拿掉了」的檢查要跟著刪掉或改掉。
8. **版本、文件**：版本號 +1，CHANGELOG、README、USAGE、HANDOFF、App 內的使用說明照平常的流程更新；這份檔案裡拿回去的那一段刪掉。

---

## 5. 原始碼

### 5-1. CSS

**EPP、氣候散佈圖**（原本在 `.heatmap-wrap{` 那一行前面）：
```css
  .climate-chart-wrap{max-width:100%;}
  .climate-chart-svg{width:100%;height:220px;display:block;}
  .climate-chart-axis-label{font-size:calc(10px*var(--fs,1));fill:var(--stone);}
  .climate-chart-axis-title{font-size:calc(10px*var(--fs,1));fill:var(--ink-soft);font-weight:600;}
  .climate-chart-sweetspot-label{font-size:calc(9px*var(--fs,1));fill:var(--trail);font-weight:600;}
  .climate-chart-legend-label{font-size:calc(10px*var(--fs,1));fill:var(--ink-soft);}
  .climate-chart-slope{color:var(--flag);margin-top:8px;}
  .climate-chart-weak-note{margin-top:4px;}
  .climate-chart-sweetspot{color:var(--trail);margin-top:2px;}
  .epp-section{margin-top:16px;padding-top:16px;border-top:1px solid var(--rule);}
  .epp-coefficient-block p{color:var(--ink-soft);margin-bottom:4px;}
  .epp-waterfall-svg{width:100%;height:180px;display:block;margin:12px 0;}
  .epp-waterfall-label{font-size:calc(11px*var(--fs,1));fill:var(--ink);font-weight:600;}
  .epp-waterfall-axis-label{font-size:calc(11px*var(--fs,1));fill:var(--stone);text-anchor:middle;}
  .epp-predicted-row{display:flex;align-items:baseline;gap:10px;padding:10px 12px;border:1px solid var(--rule);border-radius:5px;background:var(--paper);margin-bottom:8px;}
  .epp-predicted-value{font-size:calc(20px*var(--fs,1));font-weight:700;color:var(--gold);}
  .epp-adopt-row{display:flex;gap:10px;flex-wrap:wrap;}
  .epp-segment-toggle-row{margin-top:10px;}
  .epp-segment-table-wrap{max-height:320px;overflow-y:auto;margin-top:10px;border:1px solid var(--rule);border-radius:6px;}
  .epp-segment-table{width:100%;border-collapse:collapse;font-size:calc(13px*var(--fs,1));}
  .epp-segment-table th{position:sticky;top:0;background:var(--surface);text-align:left;padding:7px 10px;border-bottom:1px solid var(--rule);color:var(--ink-soft);font-weight:600;}
  .epp-segment-table td{padding:6px 10px;border-bottom:1px solid var(--rule);}
  .epp-segment-table tr:last-child td{border-bottom:none;}
```

**氣候散佈圖：效率基準那一行**（原本在 `.share-opt-why{` 那一行後面）：
```css
  .climate-chart-curve{color:var(--stone);margin-top:4px;}
```

**氣候散佈圖：含越野的開關**（原本在 `.pubview-loading{` 那一行後面）：
```css
  .climate-trail-toggle{display:flex;align-items:center;gap:8px;flex-wrap:wrap;color:var(--stone);margin-top:8px;cursor:pointer;}
  .climate-trail-toggle input{accent-color:var(--trail);}
  .climate-trail-notready{color:var(--flag);}
```

**配速試算**（原本在 `/* ---- 訓練紀錄（v3.76.0） ---- */` 前面，跟上一段隔一個空行）：
```css
  /* ---------- Pacing calculator ---------- */
  .pacing-inputs{display:flex;flex-wrap:wrap;gap:14px;margin-bottom:6px;}
  .pacing-inputs .field{flex:1 1 150px;}
```

**EPP 逐公里表跟其他表格共用的三條規則**（只拿掉了 `.epp-segment-table` 這個選擇器，規則本身還在）：

```text
.table-view td,.series-table td,.shoe-analysis-table td,.import-table td,.sync-diag-table td{
  → 改回 .table-view td,.series-table td,.shoe-analysis-table td,.epp-segment-table td,.import-table td,.sync-diag-table td{

  .shoe-analysis-table tbody tr:hover td,
  → 下一行加回   .epp-segment-table tbody tr:hover td,

.series-table th,.import-table th{
  → 改回 .series-table th,.import-table th,.epp-segment-table th{
```

### 5-2. HTML

配速試算的彈窗容器（原本在 `<div id="report-prompt-fallback-modal" …>` 和 `<div id="help-modal" …>` 中間）：
```html
<div id="pacing-modal" class="modal-overlay" hidden></div>
```

### 5-3. 呼叫的地方、按鈕的處理

**生涯數據**（`renderCareerSummary` 裡；原本在 `${simpleHome?'':elevationTrendChartSvg()}` 和 `${simpleHome?'':heatmapHtml()}` 中間）：
```text
    ${simpleHome?'':climatePerformanceChartSvg()}
```

**賽事頁「裝備、補給與戰略」**（原本在 `${goalsDashCardHtml(race)}` 和 `${equipmentDashCardHtml(race)}` 中間）：
```text
      ${S?'':eppSectionHtml(race)}
      ${S?'':`<div class="subsection">
        <div class="subsection-head"><h3></h3><button type="button" class="btn-ghost" data-action="open-pacing-modal">${t('ui.pacingCalcTitle','配速試算與手環產生器')}</button></div>
      </div>`}
```

**點擊處理**（都在同一個 `document.addEventListener('click',e=>{…})` 裡；`toggle-epp-segments` 原本在 `toggle-fatigue-contrast` 那一段前面，`epp-adopt-goal` 在 `trigger-geo-photo-input` 那一段前面）：
```js
  if(e.target.closest('[data-action="toggle-epp-segments"]')){
    eppShowSegments=!eppShowSegments;
    renderDetail();
  }
  if(e.target.closest('[data-action="epp-adopt-goal"]')&&currentRace){
    const btn=e.target.closest('[data-action="epp-adopt-goal"]');
    const tier=btn.dataset.tier,seconds=Number(btn.dataset.seconds);
    const goal=currentRace.goals.find(g=>g.tier===tier);
    if(goal&&seconds){
      goal.targetTimeSeconds=seconds;
      currentRace.updatedAt=new Date().toISOString();
      persist();
      renderDetail();
      logFeatureUse('epp_adopt_goal');
    }
  }
```

`open-pacing-modal`（另一個點擊處理，原本在 `open-profile-modal` 那一行後面）：
```js
  if(e.target.closest('[data-action="open-pacing-modal"]')){ openPacingModal(); logFeatureUse('tool_pacing_calculator'); }
```

**返回鍵、Esc 關最上面那一層的清單**（原文；現在少了 `'pacing-modal'`）：

```text
'gpx-modal','paste-modal','paste-note-modal','shoe-modal','nutrition-dict-modal','sync-diag-modal','pacing-modal',
const modalIds=['import-modal','gpx-modal','paste-modal','shoe-modal','pacing-modal','help-modal',…
```

### 5-4. 氣候資料層＋EPP 模型＋EPP 畫面（JS）

原本在 `function formatPace(secPerKm){…}` 後面、`function computeCareerStats(){` 前面。裡面依序是：經典距離分類、個人距離曲線（Riegel）、`computeClimatePerformancePoints`（散佈圖和 EPP 共用的資料層）、`linearRegression`、甜蜜點、EPP 的兩個係數、基準配速、海拔內插、逐段預測引擎、瀑布圖、係數說明、逐公里表、EPP 整段畫面。
```js
/* ============================================================
   氣候與表現散佈圖矩陣：把不同距離的賽事，透過「相對於自己在同一種
   經典距離下的 PB 配速差多少 %」正規化到同一個尺度上，才能把 10K、
   半馬、全馬的表現放進同一張圖比較，不會因為距離不同、配速基數本來
   就不一樣而失真。只收路跑（sportType==='road_running'）且已完賽的
   資料——越野賽爬升造成的配速雜訊，會蓋過氣溫對配速的影響，混進來
   會讓「氣溫每上升 1°C 配速掉多少 %」這個統計失去意義。
   ============================================================ */
const CLASSIC_DISTANCES=[
  {key:'10k',label:'10K',min:8.5,max:11.5},
  {key:'half',label:'半馬',min:20,max:22.5},
  {key:'full',label:'全馬',min:41,max:43.5}, // 跟 computeCareerStats 的全馬 PB 判定範圍保持一致
];
function classifyClassicDistance(distanceKm){
  if(distanceKm==null) return null;
  const match=CLASSIC_DISTANCES.find(d=>distanceKm>=d.min&&distanceKm<=d.max);
  return match?match.key:null;
}
/* ============================================================
   個人距離曲線（Riegel）：T = exp(a) × D^k。
   原本效率基準是「10K／半馬／全馬三個分類各自的 PB」，三個桶以外的距離
   （5K、15K、30K、超馬路跑）沒有同伴可比，整場直接丟掉——氣候圖上
   「依 6 場推算」多半就是這樣來的。改成一條連續曲線之後，任何距離都
   能算出「這個距離我的理論最佳」，效率 = 理論／實際。
   k 從你自己各距離的最佳成績擬合（log-log 迴歸），資料不夠就用一般
   跑者的 1.06；截距取「包絡」——把曲線壓到最緊的那一場之下，讓所有
   實際成績的效率都 ≤100%，語意跟以前的「PB 是 100%」一致。
   ============================================================ */
const RIEGEL_DEFAULT_K=1.06;
function computePersonalDistanceCurve(){
  const runs=state.races.filter(r=>!r.deletedAt&&r.status==='completed'&&r.sportType==='road_running'
    &&r.route.distanceKm>0&&r.results.chipTimeSeconds>0);
  if(!runs.length) return null;
  // 每 0.5 km 一桶取最佳，只用前緣點擬合——不然同距離跑差的場次會把曲線往上拉
  const buckets=new Map();
  runs.forEach(r=>{ const key=Math.round(r.route.distanceKm*2)/2; const cur=buckets.get(key);
    if(!cur||r.results.chipTimeSeconds<cur.results.chipTimeSeconds) buckets.set(key,r); });
  const frontier=[...buckets.values()];
  const distinct=new Set(frontier.map(r=>Math.round(r.route.distanceKm)));
  let k=RIEGEL_DEFAULT_K,fitted=false,r2=null;
  if(distinct.size>=2){
    const reg=linearRegression(frontier.map(r=>({x:Math.log(r.route.distanceKm),y:Math.log(r.results.chipTimeSeconds)})));
    if(reg&&Number.isFinite(reg.slope)){ k=Math.min(1.25,Math.max(1.0,reg.slope)); fitted=true; r2=reg.r2; }
  }
  const resid=r=>Math.log(r.results.chipTimeSeconds)-k*Math.log(r.route.distanceKm);
  const a=Math.min(...frontier.map(resid));
  const anchorRace=frontier.find(r=>Math.abs(resid(r)-a)<1e-9)||frontier[0];
  const frontierIds=new Set(frontier.map(r=>r.id));
  return {k,a,fitted,r2,frontierCount:frontier.length,distinctDistances:distinct.size,anchorRace,frontierIds,
    predictSeconds:d=>Math.exp(a+k*Math.log(d))};
}
/* computeClimatePerformancePoints(opts)：氣候圖與 EPP 共用的資料層。
   opts.allDistances   用距離曲線當基準（否則只收三個經典距離、各自 PB 當基準）
   opts.allowEstimatedTemp 沒有體感溫度時退回歷史氣候平均溫，點會標成估計值
   opts.includeTrail   越野跑用爬升折損係數校正回平地等價，係數沒準備好就不收
   EPP 沿用最嚴格的那一組（三個參數全關），它的係數要拿去預測完賽時間，
   寧可少幾場也不要混進估計值。 */
function computeClimatePerformancePoints(opts){
  opts=opts||{};
  const curve=opts.allDistances?computePersonalDistanceCurve():null;
  const gravity=opts.includeTrail?computeGravityCoefficient():null;
  const trailOk=!!(gravity&&gravity.ready);
  const completed=state.races.filter(r=>!r.deletedAt&&r.status==='completed'
    &&r.route.distanceKm>0&&r.results.chipTimeSeconds>0
    &&(r.sportType==='road_running'||(opts.includeTrail&&trailOk&&(r.sportType==='trail_running'||r.sportType==='ultra_marathon')&&r.route.elevationGainM!=null)));
  const withTemp=completed.map(r=>{
    const measured=r.raceDayWeather&&r.raceDayWeather.feelsLikeTempC;
    const est=r.climateForecast&&r.climateForecast.avgTempC;
    if(measured!=null) return {r,tempC:measured,tempEstimated:false};
    if(opts.allowEstimatedTemp&&est!=null) return {r,tempC:est,tempEstimated:true};
    return null;
  }).filter(Boolean);
  // 越野：整場平均坡度 × 爬升係數，把配速校正回平地等價。粗，但跟係數
  // 本身的定義一致（每 1% 坡度慢幾 %）；不校正的話越野點會全部躺在最下面。
  const effectiveSeconds=r=>{
    if(r.sportType==='road_running'||!trailOk) return r.results.chipTimeSeconds;
    const gradePct=r.route.elevationGainM/(r.route.distanceKm*10);
    const factor=1+gravity.pctPerGradePoint*gradePct/100;
    return factor>0.3?r.results.chipTimeSeconds/factor:r.results.chipTimeSeconds;
  };
  const points=[];
  if(curve){
    withTemp.forEach(({r,tempC,tempEstimated})=>{
      const secs=effectiveSeconds(r);
      const efficiencyPct=Math.min(100,curve.predictSeconds(r.route.distanceKm)/secs*100);
      points.push({race:r,category:classifyClassicDistance(r.route.distanceKm),tempC,tempEstimated,
        isTrail:r.sportType!=='road_running',efficiencyPct,degradationPct:efficiencyPct-100,
        isPb:curve.frontierIds.has(r.id)});
    });
    points.curve=curve; points.gravity=gravity;
    return points;
  }
  const byCategory={};
  withTemp.forEach(item=>{ const cat=classifyClassicDistance(item.r.route.distanceKm); if(!cat) return; (byCategory[cat]=byCategory[cat]||[]).push(item); });
  Object.keys(byCategory).forEach(cat=>{
    const items=byCategory[cat];
    const paces=items.map(({r})=>effectiveSeconds(r)/r.route.distanceKm);
    const pbPace=Math.min(...paces);
    items.forEach(({r,tempC,tempEstimated},i)=>{
      const efficiencyPct=(pbPace/paces[i])*100;
      points.push({race:r,category:cat,tempC,tempEstimated,isTrail:r.sportType!=='road_running',
        efficiencyPct,degradationPct:efficiencyPct-100,isPb:paces[i]<=pbPace});
    });
  });
  return points;
}
// 最小平方法線性迴歸，x=體感溫度、y=配速衰退百分比（<=0）。資料點的
// 溫度如果全部一樣（分母為 0）就沒有斜率可以算，回傳 null。同時算出
// R²（判定係數），讓呼叫端知道這條迴歸線解釋了多少變異——R² 低代表
// 資料點很散、這條線不太可信，不是只看斜率數字本身好不好看。
function linearRegression(pts){
  const n=pts.length;
  if(n<2) return null;
  let sumX=0,sumY=0,sumXY=0,sumX2=0;
  pts.forEach(p=>{ sumX+=p.x; sumY+=p.y; sumXY+=p.x*p.y; sumX2+=p.x*p.x; });
  const denom=n*sumX2-sumX*sumX;
  if(denom===0) return null;
  const slope=(n*sumXY-sumX*sumY)/denom;
  const intercept=(sumY-slope*sumX)/n;
  const meanY=sumY/n;
  let ssTot=0,ssRes=0;
  pts.forEach(p=>{
    const predicted=slope*p.x+intercept;
    ssTot+=(p.y-meanY)*(p.y-meanY);
    ssRes+=(p.y-predicted)*(p.y-predicted);
  });
  const r2=ssTot===0?null:1-(ssRes/ssTot);
  return {slope,intercept,r2,n};
}
// 最佳作戰溫度帶：抓「PB 本身」或「效率 98% 以上」的賽事，取這些賽事
// 體感溫度的最小～最大範圍。只有一筆符合條件時，補一點寬度讓色塊看
// 得出來，不會變成一條細線。
function computeSweetSpotBand(points){
  // 只看效率 ≥98%：距離曲線之下「每個距離的最佳」（金點）不一定是高效率
  // ——一個人跑過六種距離，六場都是該距離最佳，但相對曲線可能只有 96%。
  // 甜蜜點要的是「那天狀態真的好」，不是「那個距離只跑過一次」。
  // 舊的分類制裡 PB 本身就是 100%，所以這條規則對舊資料層等價。
  const highEff=points.filter(p=>p.efficiencyPct>=98);
  if(!highEff.length) return null;
  const temps=highEff.map(p=>p.tempC);
  let min=Math.min(...temps),max=Math.max(...temps);
  if(max-min<1){ min-=1; max+=1; }
  return {min,max,count:highEff.length};
}

/* ============================================================
   環境折損與等價配速預測模型（EPP）：從過去的完賽紀錄，統計出這個人
   自己的「高溫折損係數」跟「爬升折損係數」，再用這兩個係數把一場賽事
   的完賽時間拆解成「基準時間＋爬升折損＋高溫折損＋其他因素」幾段，用
   瀑布圖呈現「這場比賽最大的敵人到底是山還是太陽」。

   刻意加了這幾層保守設計，都是先想清楚統計上的陷阱才決定的，不是
   隨便找個公式就上：
   - 業餘跑者的比賽紀錄通常只有個位數到十幾筆，用最小平方法硬算出來
     的係數很容易被單一一場「那天狀況特別差／特別好」的比賽整個帶偏，
     卻還是會吐出一個看起來很精確的數字（例如「每上升1°C配速衰退
     1.2%」）——精確不等於可信。所以每個係數旁邊都會顯示 R²（這條
     迴歸線解釋了多少變異）跟資料筆數，資料不夠或 R² 太低時，直接不
     顯示係數、改顯示「還需要更多資料」，不會給一個沒有根據的假精確
     數字。
   - 爬升折損係數刻意不是拿「不同賽事的總配速」互相比較（那樣會把
     「這場是全馬、那場是超馬」這種純粹因為距離不同造成的配速差異，
     錯誤地也算進爬升的帳上）。改成只在同一場賽事「自己的分段」之間
     比較——同一天、同一個人、同一個體能狀態，只有坡度在變，這樣量
     出來的爬升效應才乾淨，不會把「距離造成的配速差異」跟「坡度造成
     的配速差異」混在一起算成同一個係數。
   - 高溫折損係數沿用既有氣候矩陣（v2.59.0）的做法：同一個經典距離
     分類（10K／半馬／全馬）裡各自拿自己的 PB 當 100% 基準再比較，
     不會拿 10K 的配速去跟全馬比。
   - 「AI 預測完賽時間」只會顯示在瀑布圖跟一個獨立標示的預測欄位，
     不會自動寫進「賽前目標」——模型算出來的數字如果剛好是錯的，
     直接被當成配速計畫在比賽當天執行，後果比模型不準本身嚴重得多
     （例如高估體感耐熱能力導致前段衝太快、後段撞牆）。要採用這個
     預測當目標，是使用者自己主動的選擇，不是系統幫他決定的。
   ============================================================ */
const EPP_MIN_THERMAL_RACES=4;
const EPP_MIN_GRAVITY_RACES=2;
const EPP_MIN_GRAVITY_SPLITS=6;
// 高溫折損係數：沿用氣候矩陣的「同分類拿自己 PB 當基準」邏輯，只取
// 體感溫度 >= 15°C 的賽事做迴歸（低於這個門檻的degradation跟溫度
// 關聯性通常很弱，混進來只會稀釋斜率、讓係數更不準）。
function computeThermalCoefficient(){
  const points=computeClimatePerformancePoints().filter(p=>p.tempC>=15);
  if(points.length<EPP_MIN_THERMAL_RACES) return {ready:false,n:points.length,needed:EPP_MIN_THERMAL_RACES};
  const reg=linearRegression(points.map(p=>({x:p.tempC,y:p.degradationPct})));
  if(!reg) return {ready:false,n:points.length,needed:EPP_MIN_THERMAL_RACES};
  // slope 是「degradationPct 對 tempC」的斜率（degradationPct<=0），
  // 轉成正值的「每上升1°C衰退幾%」比較符合使用者的直覺說法。
  return {ready:true,pctPerDegree:Math.max(0,-reg.slope),r2:reg.r2,n:points.length};
}
// 爬升折損係數：只在同一場賽事「自己的分段」之間比較，把每段配速換算
// 成「相對這場賽事自己平均配速的比例」，再拿這個比例對坡度做迴歸，
// 這樣才不會把「距離造成的配速差異」也算進爬升的帳上。
function computeGravityCoefficient(){
  const completed=state.races.filter(r=>!r.deletedAt&&r.status==='completed'&&Array.isArray(r.splits)&&r.splits.length>=2);
  const pts=[];
  let contributingRaces=0;
  completed.forEach(r=>{
    const validSplits=r.splits.filter(s=>s.avgPaceSecPerKm!=null&&s.elevationGainM!=null&&s.distanceKm);
    if(validSplits.length<2) return;
    const raceMeanPace=validSplits.reduce((s,sp)=>s+sp.avgPaceSecPerKm,0)/validSplits.length;
    if(raceMeanPace<=0) return;
    let used=false;
    validSplits.forEach(sp=>{
      const grade=splitGradePct(sp);
      if(grade==null) return;
      pts.push({x:grade,y:(sp.avgPaceSecPerKm/raceMeanPace-1)*100});
      used=true;
    });
    if(used) contributingRaces++;
  });
  if(contributingRaces<EPP_MIN_GRAVITY_RACES||pts.length<EPP_MIN_GRAVITY_SPLITS){
    return {ready:false,n:pts.length,raceCount:contributingRaces,needed:EPP_MIN_GRAVITY_SPLITS};
  }
  const reg=linearRegression(pts);
  if(!reg) return {ready:false,n:pts.length,raceCount:contributingRaces,needed:EPP_MIN_GRAVITY_SPLITS};
  // slope 是「每 1% 坡度，配速比自己平均慢幾 %」；換算成「每 100m
  // 爬升、在 1 公里內大約多花幾秒」方便跟使用者熟悉的 GAP 概念對照。
  return {ready:true,pctPerGradePoint:reg.slope,r2:reg.r2,n:pts.length,raceCount:contributingRaces};
}
// 基準配速：從「經典距離」裡挑一個使用者最能代表「最佳有氧巡航配速」
// 的類別（全馬>半馬>10K，越長距離越接近長距離耐力賽事的能量系統），
// 取該分類目前的 PB 配速——PB 是已經證實做到過的能力上限，比隨便挑
// 一場單一賽事當基準更站得住腳。
function computeEppBaselinePace(){
  const points=computeClimatePerformancePoints();
  for(const cat of ['full','half','10k']){
    const inCat=points.filter(p=>p.category===cat);
    if(!inCat.length) continue;
    const pbPoint=inCat.find(p=>p.isPb)||inCat.reduce((best,p)=>(!best||p.race.results.chipTimeSeconds/p.race.route.distanceKm<best.race.results.chipTimeSeconds/best.race.route.distanceKm)?p:best,null);
    if(pbPoint){
      return {paceSecPerKm:pbPoint.race.results.chipTimeSeconds/pbPoint.race.route.distanceKm,category:cat,sourceRace:pbPoint.race};
    }
  }
  return null;
}
// 把三個係數套到某一場賽事（不分是已完賽用來回顧、還是未完賽用來
// 預測）身上，拆解成瀑布圖需要的幾段：基準時間／爬升折損／高溫折損／
// 其他（已完賽時是「實際時間 - 前三段加總」，未完賽時這段不存在，因為
// 還沒有實際時間可以拿來對比）。
// 用線性插值，從海拔剖面（route.elevationProfile，通常是降採樣到 50 點
// 的 {distanceKm,elevationM} 陣列）算出「某個公里數當下」的海拔——
// 逐公里切片預測要知道每一段的起訖點海拔，但剖面本身不會剛好在整數
// 公里處取樣，需要在兩個最近的已知點之間內插。
function elevationAtDistance(elevationProfile,km){
  if(!elevationProfile||elevationProfile.length<2) return null;
  if(km<=elevationProfile[0].distanceKm) return elevationProfile[0].elevationM;
  const last=elevationProfile[elevationProfile.length-1];
  if(km>=last.distanceKm) return last.elevationM;
  for(let i=1;i<elevationProfile.length;i++){
    if(elevationProfile[i].distanceKm>=km){
      const p0=elevationProfile[i-1],p1=elevationProfile[i];
      const span=p1.distanceKm-p0.distanceKm;
      const frac=span>0?(km-p0.distanceKm)/span:0;
      return p0.elevationM+(p1.elevationM-p0.elevationM)*frac;
    }
  }
  return last.elevationM;
}
/* ============================================================
   EPP 逐公里切片預測引擎：把整場賽事切成固定長度的區段（預設 1 公里，
   長距離賽事自動放寬到 3 公里，避免表格長到失去意義），每一段各自套
   用坡度折損／高溫折損，而不是像 computeRaceWaterfall() 原本那樣把
   全場總爬升攤平成一個平均坡度——這樣做出來的預測，才會真的反映出
   「第 4 段有一段連續陡坡，這段特別慢；第 9 段是長下坡，這段比基準
   還快」這種賽道實際的起伏樣貌，而不是整場均勻地慢一點點。

   坡度用「這一段起訖點的淨海拔變化」而不是「只算爬升的正值總和」，
   是為了跟爬升折損係數本身的算法保持一致——那個係數是拿 splits 資料
   裡 splitGradePct()（也是用淨爬升，下坡是負值）去迴歸出來的，如果
   這裡改用「只算上坡」的算法，套用同一個係數就會邏輯不一致。這也是
   為什麼下坡段的折損算出來可以是負值（=比基準快）：係數本身就是從
   這位使用者自己「上坡變慢多少、下坡變快多少」的真實資料迴歸出來
   的，不是只把上坡的效應複製一份、下坡直接歸零。

   氣溫則是「動態」的：如果這場賽事有抓到即時逐時預報（liveForecast，
   只有賽事日期在 7 天內才會有），會依照模擬跑到這一段時的「預估時
   鐘時間」去查對應時段的預報溫度，而不是整場都套同一個溫度——長距
   離賽事清晨出發、中午還在賽道上，體感溫度本來就會隨時間爬升，這裡
   把這個效應也模擬進去。查不到逐時預報、或模擬時間跨到隔天（逐時
   預報只涵蓋單一天）時，退回整場統一套用同一個溫度，跟原本 computeRaceWaterfall()
   的做法一樣。
   ============================================================ */
function pickSegmentLengthKm(distanceKm){
  return distanceKm>15?3:1;
}
function computeSegmentPredictions(race,segmentKmOverride){
  const baseline=computeEppBaselinePace();
  const thermal=computeThermalCoefficient();
  const gravity=computeGravityCoefficient();
  if(!baseline||!thermal.ready||!gravity.ready) return null;
  const distanceKm=race.route.distanceKm;
  if(!distanceKm) return null;
  const elevationProfile=race.route.elevationProfile;
  const hasProfile=elevationProfile&&elevationProfile.length>=2;
  if(!hasProfile) return null; // 沒有海拔剖面就沒辦法逐段算坡度，讓呼叫端退回用 elevationGainM 的簡化版，不要在這裡假裝算過、實際上每段坡度都是 0
  const segmentKm=segmentKmOverride||pickSegmentLengthKm(distanceKm);
  const live=race.liveForecast;
  const fallbackTempC=race.raceDayWeather.feelsLikeTempC!=null?race.raceDayWeather.feelsLikeTempC:race.climateForecast.avgTempC;
  const segments=[];
  let cumulativeSec=0;
  let startKm=0;
  while(startKm<distanceKm-1e-6){
    const endKm=Math.min(startKm+segmentKm,distanceKm);
    const segLenKm=endKm-startKm;
    let elevationChangeM=0;
    if(hasProfile){
      const e0=elevationAtDistance(elevationProfile,startKm);
      const e1=elevationAtDistance(elevationProfile,endKm);
      if(e0!=null&&e1!=null) elevationChangeM=e1-e0;
    }
    const avgGradePct=segLenKm>0?(elevationChangeM/(segLenKm*1000))*100:0;
    const gravityExtraPct=gravity.pctPerGradePoint*avgGradePct; // 刻意不夾在 >=0，下坡段允許算出負值（比基準快）
    const baselineSegSec=baseline.paceSecPerKm*segLenKm;
    const gravitySegSec=baselineSegSec*(gravityExtraPct/100);
    let tempC=fallbackTempC;
    if(live&&live.times&&live.times.length&&race.schedule.startTime){
      const arrival=formatClockTimeOffset(race.schedule.startTime,cumulativeSec);
      if(arrival&&arrival.dayOffset===0){
        const idx=findClosestHourIndex(live.times,arrival.label);
        if(live.temp&&live.temp[idx]!=null) tempC=live.temp[idx];
      }
    }
    const thermalExtraPct=(tempC!=null&&tempC>15)?thermal.pctPerDegree*(tempC-15):0;
    const thermalSegSec=baselineSegSec*(thermalExtraPct/100);
    const predictedSegSec=Math.max(0,baselineSegSec+gravitySegSec+thermalSegSec);
    cumulativeSec+=predictedSegSec;
    segments.push({
      startKm:+startKm.toFixed(2),endKm:+endKm.toFixed(2),segLenKm,
      elevationChangeM:Math.round(elevationChangeM),avgGradePct,
      tempC,gravitySegSec,thermalSegSec,predictedSegSec,
      cumulativeSec,paceSecPerKm:predictedSegSec/segLenKm,
    });
    startKm=endKm;
  }
  if(!segments.length) return null;
  return {
    segments,segmentKm,
    totalGravitySec:segments.reduce((s,x)=>s+x.gravitySegSec,0),
    totalThermalSec:segments.reduce((s,x)=>s+x.thermalSegSec,0),
    totalPredictedSec:cumulativeSec,
    baseline,thermal,gravity,
  };
}
function computeRaceWaterfall(race){
  const baseline=computeEppBaselinePace();
  const thermal=computeThermalCoefficient();
  const gravity=computeGravityCoefficient();
  if(!baseline||!thermal.ready||!gravity.ready) return null;
  const distanceKm=race.route.distanceKm;
  const elevationGainM=race.route.elevationGainM;
  if(!distanceKm) return null;
  const baselineSec=baseline.paceSecPerKm*distanceKm;
  // 優先用逐公里切片引擎算出來的加總——比下面「把全場爬升攤平成一個
  // 平均坡度」的簡化版準確得多，因為爬升折損跟高溫折損都會依照賽道
  // 實際的起伏跟模擬時鐘時間分段套用，不是整場均勻地打一個折。只有
  // 賽事沒有海拔剖面資料（例如手動填距離、沒匯入 GPX）時才會退回
  // 簡化版，保證這個功能在資料不足時依然能給出一個粗估值，而不是
  // 整段消失。
  const segmentResult=computeSegmentPredictions(race);
  let gravitySec,thermalSec,predictedSec,tempC,avgGradePct;
  if(segmentResult){
    gravitySec=segmentResult.totalGravitySec;
    thermalSec=segmentResult.totalThermalSec;
    predictedSec=segmentResult.totalPredictedSec;
    avgGradePct=elevationGainM!=null?(elevationGainM/(distanceKm*1000))*100:0;
    tempC=race.raceDayWeather.feelsLikeTempC!=null?race.raceDayWeather.feelsLikeTempC:race.climateForecast.avgTempC;
  }else{
    const fallbackAvgGradePct=elevationGainM!=null?(elevationGainM/(distanceKm*1000))*100:0;
    const gravityExtraPct=Math.max(0,gravity.pctPerGradePoint*fallbackAvgGradePct);
    gravitySec=baselineSec*(gravityExtraPct/100);
    tempC=race.raceDayWeather.feelsLikeTempC!=null?race.raceDayWeather.feelsLikeTempC:race.climateForecast.avgTempC;
    const thermalExtraPct=tempC!=null&&tempC>15?thermal.pctPerDegree*(tempC-15):0;
    thermalSec=baselineSec*(thermalExtraPct/100);
    predictedSec=baselineSec+gravitySec+thermalSec;
    avgGradePct=fallbackAvgGradePct;
  }
  const actualSec=race.results.chipTimeSeconds;
  const otherSec=actualSec!=null?actualSec-predictedSec:null;
  return {baseline,thermal,gravity,baselineSec,gravitySec,thermalSec,predictedSec,actualSec,otherSec,tempC,avgGradePct,segmentResult};
}
// 帶正負號的時間差顯示，用在瀑布圖的「+15分」「-8分」這種階梯標籤，
// 跟 secToHMS 分開是因為那個函式假設輸入一定是非負秒數。
function signedDurationLabel(sec){
  const sign=sec>=0?'+':'-';
  const abs=Math.round(Math.abs(sec));
  const h=Math.floor(abs/3600),m=Math.floor((abs%3600)/60),s=abs%60;
  if(h>0) return `${sign}${h}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
  return `${sign}${m}:${String(s).padStart(2,'0')}`;
}
// 折損瀑布圖：基準時間開始，每加一段折損／優勢就往上或往下疊一階，
// 最後一根柱子是全部疊起來的總結果（有實際成績就用實際成績，還沒有
// 就用模型預測值）。配色沿用氣候散佈圖那組既有色票，不是另外自創。
function eppWaterfallChartSvg(wf){
  const steps=[
    {label:t('ui.eppBarBaseline','基準'),delta:wf.baselineSec,cumStart:0,cumEnd:wf.baselineSec,color:'var(--contour)',isBase:true},
    {label:t('ui.eppBarGravity','爬升'),delta:wf.gravitySec,cumStart:wf.baselineSec,cumEnd:wf.baselineSec+wf.gravitySec,color:'#B8451F'},
    {label:t('ui.eppBarThermal','高溫'),delta:wf.thermalSec,cumStart:wf.baselineSec+wf.gravitySec,cumEnd:wf.predictedSec,color:'#D98A3D'},
  ];
  if(wf.otherSec!=null){
    steps.push({
      label:t('ui.eppBarOther','其他因素'),delta:wf.otherSec,
      cumStart:wf.predictedSec,cumEnd:wf.predictedSec+wf.otherSec,
      color:wf.otherSec<0?'#4C9A72':'#B8451F',
    });
  }
  const finalSec=wf.actualSec!=null?wf.actualSec:wf.predictedSec;
  steps.push({
    label:wf.actualSec!=null?t('ui.eppBarActual','實際完賽'):t('ui.eppBarPredicted','AI 預測'),
    delta:finalSec,cumStart:0,cumEnd:finalSec,color:'var(--gold)',isFinal:true,
  });

  const maxSec=Math.max(...steps.map(s=>Math.max(s.cumStart,s.cumEnd)))*1.08;
  const w=600,h=280,padL=54,padR=16,padTop=24,padBottom=54;
  const plotW=w-padL-padR,plotH=h-padTop-padBottom;
  const cols=steps.length;
  const gap=10;
  const barW=(plotW-gap*(cols-1))/cols;
  const sy=sec=>padTop+plotH-((sec/maxSec)*plotH);

  const bars=steps.map((s,i)=>{
    const x=padL+i*(barW+gap);
    const yTop=sy(Math.max(s.cumStart,s.cumEnd));
    const yBottom=sy(Math.min(s.cumStart,s.cumEnd));
    const barH=Math.max(1,yBottom-yTop);
    const connector=i>0&&!s.isFinal
      ?`<line x1="${(x-gap).toFixed(1)}" y1="${sy(s.cumStart).toFixed(1)}" x2="${x.toFixed(1)}" y2="${sy(s.cumStart).toFixed(1)}" stroke="var(--rule)" stroke-width="1" stroke-dasharray="3 3"/>`
      :'';
    const deltaLabel=s.isBase||s.isFinal?secToHMS(s.cumEnd):signedDurationLabel(s.delta);
    const tip=`${s.label}：${deltaLabel}`;
    return `${connector}<rect x="${x.toFixed(1)}" y="${yTop.toFixed(1)}" width="${barW.toFixed(1)}" height="${barH.toFixed(1)}" fill="${s.color}" opacity="${s.isFinal?1:0.85}" rx="2"><title>${escapeHtml(tip)}</title></rect>
      <text x="${(x+barW/2).toFixed(1)}" y="${(yTop-6).toFixed(1)}" text-anchor="middle" class="epp-waterfall-label mono">${escapeHtml(deltaLabel)}</text>
      <text x="${(x+barW/2).toFixed(1)}" y="${h-padBottom+20}" text-anchor="middle" class="epp-waterfall-axis-label">${escapeHtml(s.label)}</text>`;
  }).join('');

  return `<svg viewBox="0 0 ${w} ${h}" class="epp-waterfall-svg" preserveAspectRatio="xMidYMid meet">${bars}</svg>`;
}
function eppCoefficientBlockHtml(){
  const thermal=computeThermalCoefficient();
  const gravity=computeGravityCoefficient();
  const thermalLine=thermal.ready
    ?tv('ui.eppThermalReady','高溫折損：每升高 1°C，配速衰退約 {pct}%（R²={r2}，依 {n} 場賽事推算）',
      {pct:thermal.pctPerDegree.toFixed(2),r2:thermal.r2!=null?thermal.r2.toFixed(2):'—',n:thermal.n})
    :tv('ui.eppThermalPending','高溫折損：資料還不夠（目前 {n} 場體感溫度 ≥15°C 的路跑賽事，至少需要 {needed} 場）',{n:thermal.n,needed:thermal.needed});
  const gravityLine=gravity.ready
    ?tv('ui.eppGravityReady','爬升折損：每 1% 坡度，配速比自己平均慢約 {pct}%（R²={r2}，依 {n} 場賽事、{count} 個分段推算）',
      {pct:gravity.pctPerGradePoint.toFixed(2),r2:gravity.r2!=null?gravity.r2.toFixed(2):'—',n:gravity.raceCount,count:gravity.n})
    :tv('ui.eppGravityPending','爬升折損：資料還不夠（目前 {n} 個有效分段，至少需要 {needed} 個、來自至少 2 場賽事）',{n:gravity.n,needed:gravity.needed});
  return `<div class="epp-coefficient-block">
    <p class="small">${thermalLine}</p>
    <p class="small">${gravityLine}</p>
  </div>`;
}
// 逐公里預測表格預設收合，避免每次打開賽事詳情頁都跳出一大串清單；
// 是否展開只是畫面上的暫時狀態，不需要記住，重新整理就會收合回去。
let eppShowSegments=false;
function eppSegmentTableHtml(segmentResult,race){
  if(!segmentResult) return '';
  const rows=segmentResult.segments.map(s=>{
    const arrival=race.schedule.startTime?formatClockTimeOffset(race.schedule.startTime,s.cumulativeSec):null;
    const eleSign=s.elevationChangeM>0?'+':'';
    return `<tr>
      <td class="mono">${s.startKm}–${s.endKm}km</td>
      <td class="mono">${eleSign}${s.elevationChangeM}m</td>
      <td class="mono">${formatPace(s.paceSecPerKm)||'—'}/km</td>
      <td class="mono">${arrival?arrival.label+(arrival.dayOffset>0?' +'+arrival.dayOffset+'d':''):'—'}</td>
    </tr>`;
  }).join('');
  return `<div class="epp-segment-table-wrap">
    <table class="epp-segment-table">
      <thead><tr>
        <th>${t('ui.eppSegRange','區間')}</th>
        <th>${t('ui.eppSegElevation','淨爬升')}</th>
        <th>${t('ui.eppSegPace','預測配速')}</th>
        <th>${t('ui.eppSegArrival','預估抵達時刻')}</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>
  </div>`;
}
function eppSectionHtml(race){
  const wf=computeRaceWaterfall(race);
  const coeffBlock=eppCoefficientBlockHtml();
  if(!wf){
    return `<div class="epp-section">
      <div class="subsection-head"><span class="small">${t('ui.eppTitle','環境折損預測（EPP）')}</span></div>
      ${coeffBlock}
      <p class="empty-hint small">${t('ui.eppNotReadyHint','兩個係數都準備好、且這場賽事填了距離之後，這裡會顯示折損瀑布圖跟 AI 預測完賽時間。')}</p>
    </div>`;
  }
  const adoptButtons=['A','B','C'].map(tier=>
    `<button type="button" class="btn-text-small" data-action="epp-adopt-goal" data-tier="${tier}" data-seconds="${Math.round(wf.predictedSec)}">${t('ui.eppAdoptGoal','採用為 {tier} 目標').replace('{tier}',tier)}</button>`
  ).join('');
  const segmentToggle=wf.segmentResult
    ?`<div class="epp-segment-toggle-row">
        <button type="button" class="btn-text-small" data-action="toggle-epp-segments">${eppShowSegments?t('ui.eppHideSegments','隱藏逐公里預測'):t('ui.eppShowSegments','顯示逐公里預測（每 {km} 公里）').replace('{km}',wf.segmentResult.segmentKm)}</button>
      </div>
      ${eppShowSegments?eppSegmentTableHtml(wf.segmentResult,race):''}`
    :`<p class="empty-hint small">${t('ui.eppSegmentsNeedProfile','這場賽事還沒有海拔剖面資料（匯入 GPX/TCX/FIT 或手動填海拔變化圖才會有），目前用的是全場爬升攤平成平均坡度的簡化估計。')}</p>`;
  return `<div class="epp-section">
    <div class="subsection-head"><span class="small">${t('ui.eppTitle','環境折損預測（EPP）')}</span></div>
    ${coeffBlock}
    ${eppWaterfallChartSvg(wf)}
    <div class="epp-predicted-row">
      <span class="small">${t('ui.eppPredictedLabel','AI 預測完賽時間')}</span>
      <span class="epp-predicted-value mono">${secToHMS(wf.predictedSec)}</span>
    </div>
    <p class="empty-hint small">${t('ui.eppDisclaimer','這是根據你過去賽事統計出來的估計值，不是保證會發生的事，也不會自動變成你的賽前目標——要採用的話請自己按下面的按鈕。')}</p>
    <div class="epp-adopt-row">${adoptButtons}</div>
    ${segmentToggle}
  </div>`;
}
```

### 5-5. 氣候與表現散佈圖（JS）

原本在 `function heatmapHtml(){` 前面（`computeMonthlyHeatmapData` 後面）。包含畫圖的函式和「含越野」開關的 change 處理。
```js
// 氣候與表現散佈圖：門檻從原本 3 場提高到 4 場，跟 EPP 模型的高溫折損
// 係數用一樣的最低樣本數（同樣是「溫度 vs 表現」的迴歸，沒有理由套用
// 不同的可信度標準）。R²／樣本數這次改成一定會顯示在圖表文字裡，不是
// 拿到才選擇性顯示——3、4 筆資料畫出來的趨勢線，視覺上看起來會跟資料
// 齊全時一樣「確定」，但統計上完全不是一回事，把 R² 藏起來等於讓使用者
// 沒辦法自己判斷這條線值不值得信。R² 偏低（<0.4，代表這條線解釋不到
// 4 成的變異）時，趨勢線改用更淡、更稀疏的虛線呈現，用視覺本身傳達
// 「這條線沒有很篤定」，不是只在文字裡加一句警語、圖案本身還是畫得
// 信心滿滿。
const CLIMATE_CHART_MIN_POINTS=4;
const CLIMATE_CHART_WEAK_R2=0.4;
const CLIMATE_TRAIL_PREF_KEY='climate-include-trail-v1';
function climateIncludeTrail(){ try{ return localStorage.getItem(CLIMATE_TRAIL_PREF_KEY)==='1'; }catch(e){ return false; } }
function climatePerformanceChartSvg(){
  const includeTrail=climateIncludeTrail();
  const points=computeClimatePerformancePoints({allDistances:true,allowEstimatedTemp:true,includeTrail});
  const gravityReady=!!(points.gravity&&points.gravity.ready);
  // 越野開關永遠畫出來（就算資料不足也要讓人知道有這個選項），圖本身要夠點才畫
  const trailToggle=`<label class="climate-trail-toggle small">
      <input type="checkbox" data-action="climate-toggle-trail"${includeTrail?' checked':''}${includeTrail&&!gravityReady?' data-not-ready="1"':''}>
      ${t('ui.climateIncludeTrail','含越野（用爬升折損係數校正）')}${includeTrail&&!gravityReady?`<span class="climate-trail-notready">${t('ui.climateTrailNotReady','爬升係數資料還不夠，越野暫不納入')}</span>`:''}
    </label>`;
  if(points.length<CLIMATE_CHART_MIN_POINTS) return `<div class="climate-chart-wrap">${trailToggle}</div>`;

  const sweetSpot=computeSweetSpotBand(points);
  const reg=linearRegression(points.map(p=>({x:p.tempC,y:p.degradationPct})));
  const regIsWeak=reg&&reg.r2!=null&&reg.r2<CLIMATE_CHART_WEAK_R2;

  const temps=points.map(p=>p.tempC);
  let minTemp=Math.min(...temps),maxTemp=Math.max(...temps);
  if(sweetSpot){ minTemp=Math.min(minTemp,sweetSpot.min); maxTemp=Math.max(maxTemp,sweetSpot.max); }
  if(maxTemp-minTemp<2){ minTemp-=1; maxTemp+=1; }
  const tempPad=(maxTemp-minTemp)*0.08;
  minTemp-=tempPad; maxTemp+=tempPad;
  const tempRange=maxTemp-minTemp;

  const degs=points.map(p=>p.degradationPct);
  let minDeg=Math.min(...degs,0);
  if(reg){
    minDeg=Math.min(minDeg,reg.intercept+reg.slope*minTemp,reg.intercept+reg.slope*maxTemp);
  }
  if(minDeg>=0) minDeg=-1;
  const degRange=(0-minDeg)||1;

  const w=560,h=272,padL=54,padR=20,padTop=34,padBottom=48;
  const plotW=w-padL-padR,plotH=h-padTop-padBottom;
  const sx=temp=>padL+((temp-minTemp)/tempRange)*plotW;
  const sy=deg=>padTop+((0-deg)/degRange)*plotH;

  const sweetSpotRect=sweetSpot
    ?`<rect x="${sx(sweetSpot.min).toFixed(1)}" y="${padTop}" width="${(sx(sweetSpot.max)-sx(sweetSpot.min)).toFixed(1)}" height="${plotH}" fill="var(--trail)" opacity="0.14"/>
      <text x="${((sx(sweetSpot.min)+sx(sweetSpot.max))/2).toFixed(1)}" y="${padTop+14}" text-anchor="middle" class="climate-chart-sweetspot-label">${t('ui.climateChartSweetSpotLabel','甜蜜點')}</text>`
    :'';
  const zeroY=sy(0).toFixed(1);
  const zeroLine=`<line x1="${padL}" y1="${zeroY}" x2="${w-padR}" y2="${zeroY}" stroke="var(--rule)" stroke-width="1"/>`;
  // 中間再補一條淡淡的 Y 軸刻度線，原本只有 0% 跟最低值兩個端點，中間
  // 完全沒有參考線，這次補一條在視覺上抓比例會更容易。
  const midDeg=minDeg/2;
  const midY=sy(midDeg).toFixed(1);
  const midGridLine=`<line x1="${padL}" y1="${midY}" x2="${w-padR}" y2="${midY}" stroke="var(--rule)" stroke-width="0.5" stroke-dasharray="2 3" opacity="0.6"/>`;
  const trendLine=reg
    ?`<line x1="${padL}" y1="${sy(reg.intercept+reg.slope*minTemp).toFixed(1)}" x2="${w-padR}" y2="${sy(reg.intercept+reg.slope*maxTemp).toFixed(1)}" stroke="var(--flag)" stroke-width="${regIsWeak?1:1.5}" stroke-dasharray="${regIsWeak?'3 5':'5 4'}" opacity="${regIsWeak?0.5:1}"/>`
    :'';
  const dots=points.map(p=>{
    const cx=+sx(p.tempC).toFixed(1),cy=+sy(p.degradationPct).toFixed(1);
    // 金點＝該距離最佳，但效率照樣寫出來：距離曲線之下它可能只有 97%，
    // 標成「PB」會讓人以為那場是 100%。
    const degLabel=p.degradationPct.toFixed(1)+'%'+(p.isPb?t('ui.climateFrontierTip','（該距離最佳）'):'');
    const tempLabel=p.tempC.toFixed(1)+'°C'+(p.tempEstimated?t('ui.climateTempEstimatedTip','（氣候平均，估計）'):'');
    const trailLabel=p.isTrail?t('ui.climateTrailTip','／越野・已校正'):'';
    const tipText=`${p.race.name||t('ui.unnamedRace','(未命名賽事)')}/  ${tempLabel}/  ${degLabel}${trailLabel}`;
    const color=p.isPb?'var(--gold)':'var(--contour)';
    const r=p.isPb?5:4;
    // 空心＝溫度是估計值；三角＝越野（已用爬升係數校正）。形狀與實心分開表達
    // 兩件事，才不會出現「空心三角」讀不出來是哪一種。
    const shape=p.isTrail
      ?`<path d="M${cx} ${cy-r-1} L${cx+r+1} ${cy+r} L${cx-r-1} ${cy+r} Z" fill="${p.tempEstimated?'none':color}" stroke="${color}" stroke-width="1.6" opacity="0.85">`
      :`<circle cx="${cx}" cy="${cy}" r="${r}" fill="${p.tempEstimated?'none':color}" stroke="${color}" stroke-width="1.6" opacity="0.85">`;
    return shape+`<title>${escapeHtml(tipText)}</title>`+(p.isTrail?'</path>':'</circle>');
  }).join('');
  const estimatedCount=points.filter(p=>p.tempEstimated).length;
  const trailCount=points.filter(p=>p.isTrail).length;
  const axisLabels=`
    <text x="${padL}" y="${h-padBottom+20}" text-anchor="start" class="climate-chart-axis-label mono">${minTemp.toFixed(0)}°C</text>
    <text x="${w-padR}" y="${h-padBottom+20}" text-anchor="end" class="climate-chart-axis-label mono">${maxTemp.toFixed(0)}°C</text>
    <text x="${((padL+w-padR)/2).toFixed(1)}" y="${h-padBottom+20}" text-anchor="middle" class="climate-chart-axis-label mono">${t('ui.climateChartXAxis','體感溫度')}</text>
    <text x="${padL-6}" y="${padTop+4}" text-anchor="end" class="climate-chart-axis-label mono">0%</text>
    <text x="${padL-6}" y="${(padTop+plotH).toFixed(1)}" text-anchor="end" class="climate-chart-axis-label mono">${minDeg.toFixed(0)}%</text>
    <text x="${padL}" y="16" text-anchor="start" class="climate-chart-axis-title">${t('ui.climateChartYAxisCurve','配速衰退（相對個人距離曲線）')}</text>`;
  // 圖例排成兩欄兩列：標籤從「PB」改成「各距離最佳」之後變長，原本
  // 一列橫排會疊到隔壁。
  const lx1=w-250,lx2=w-130;
  const legend=`
    <g class="climate-chart-legend">
      <circle cx="${lx1}" cy="16" r="4" fill="var(--gold)"/>
      <text x="${lx1+9}" y="19" class="climate-chart-legend-label">${t('ui.climateChartLegendPb','各距離最佳')}</text>
      <circle cx="${lx2}" cy="16" r="4" fill="var(--contour)"/>
      <text x="${lx2+9}" y="19" class="climate-chart-legend-label">${t('ui.climateChartLegendOther','其他賽事')}</text>
      ${estimatedCount?`<circle cx="${lx1}" cy="30" r="4" fill="none" stroke="var(--contour)" stroke-width="1.6"/>
      <text x="${lx1+9}" y="33" class="climate-chart-legend-label">${t('ui.climateChartLegendEstimated','氣候平均溫')}</text>`:''}
      ${trailCount?`<path d="M${lx2} 25 L${lx2+5} 34 L${lx2-5} 34 Z" fill="var(--contour)"/>
      <text x="${lx2+9}" y="33" class="climate-chart-legend-label">${t('ui.climateChartLegendTrail','越野')}</text>`:''}
    </g>`;

  const countDetail=[
    estimatedCount?tf('ui.climateCountEstimated','其中 {n} 場用氣候平均溫',estimatedCount):'',
    trailCount?tf('ui.climateCountTrail','{n} 場越野已校正',trailCount):'',
  ].filter(Boolean).join('、');
  const slopeNote=reg
    ?`<div class="climate-chart-slope small">${tv('ui.climateChartSlope','氣溫每升高 1°C，配速平均衰退約 {n} 個百分點（R²={r2}，依 {count} 場賽事推算）',
        {n:Math.abs(reg.slope).toFixed(2),r2:reg.r2!=null?reg.r2.toFixed(2):'—',count:reg.n})}${countDetail?`（${countDetail}）`:''}</div>`
    :'';
  const curve=points.curve;
  const curveNote=curve
    ?`<div class="climate-chart-curve small">${curve.fitted
        ?tf2('ui.climateCurveFitted','效率基準：個人距離曲線 k={a}（依 {b} 個距離的最佳成績擬合）',curve.k.toFixed(2),curve.distinctDistances)
        :tf('ui.climateCurveDefault','效率基準：個人距離曲線 k={n}（不同距離的成績還不夠擬合，先用一般跑者的預設值）',RIEGEL_DEFAULT_K.toFixed(2))}</div>`
    :'';
  const weakR2Note=regIsWeak
    ?`<p class="climate-chart-weak-note empty-hint small">${t('ui.climateChartWeakR2','R² 偏低，代表氣溫沒辦法解釋大部分的配速差異，這條線僅供參考，不是穩定的規律——資料點再多一些，這個估計會更可信。')}</p>`
    :'';
  const sweetSpotNote=sweetSpot
    ?`<div class="climate-chart-sweetspot small">${tv('ui.climateChartSweetSpot','最佳作戰溫度帶：{range}（依 {n} 場高效率賽事推算）',{range:sweetSpot.min.toFixed(0)+'~'+sweetSpot.max.toFixed(0)+'°C',n:sweetSpot.count})}</div>`
    :'';

  return `<div class="climate-chart-wrap">
    <div class="yearly-chart-title small">${t('ui.climateChartTitle','氣候與表現散佈圖')}</div>
    <svg viewBox="0 0 ${w} ${h}" class="climate-chart-svg" preserveAspectRatio="xMidYMid meet">
      ${sweetSpotRect}${midGridLine}${zeroLine}${trendLine}${dots}${axisLabels}${legend}
    </svg>
    ${slopeNote}
    ${weakR2Note}
    ${sweetSpotNote}
    ${curveNote}
    ${trailToggle}
  </div>`;
}
document.addEventListener('change',e=>{
  const cb=e.target.closest('[data-action="climate-toggle-trail"]'); if(!cb) return;
  try{ localStorage.setItem(CLIMATE_TRAIL_PREF_KEY,cb.checked?'1':'0'); }catch(err){}
  renderCalendar();
  logFeatureUse('climate_toggle_trail');
});
```

### 5-6. 配速試算與手環產生器（JS）

`pacingTimeAtDistance` 上面原本的註解（現在改寫成「應援指南卡用」）：
```js
/* ============================================================
   配速試算與手環產生器
   ============================================================ */
// 抽出單點距離的配速時間計算，讓「配速試算表」（固定間隔）跟「應援指南
// 卡」（CP 站實際距離，不是固定間隔）可以共用同一套配速插值公式，不用
// 各自寫一份容易兜不起來的重複邏輯。
```

其餘的函式，原本接在 `pacingTimeAtDistance` 後面：
```js
function computePacingRows(targetSeconds,distanceKm,strategy,intervalKm){
  if(!targetSeconds||!distanceKm||!intervalKm) return [];
  const rows=[];
  let d=intervalKm;
  while(d<distanceKm-0.05){
    rows.push({distanceKm:+d.toFixed(1),cumulativeSeconds:Math.round(pacingTimeAtDistance(targetSeconds,distanceKm,strategy,d))});
    d+=intervalKm;
  }
  rows.push({distanceKm:+distanceKm.toFixed(2),cumulativeSeconds:Math.round(targetSeconds)});
  return rows;
}
function pacingTableHtml(rows){
  return `<table class="series-table"><thead><tr><th class="num">${t('ui.pacingDistanceCol','距離')}</th><th class="num">${t('ui.pacingTimeCol','預計通過時間')}</th></tr></thead>
    <tbody>${rows.map(r=>`<tr><td class="mono num">${r.distanceKm} km</td><td class="mono num">${secToHMS(r.cumulativeSeconds)}</td></tr>`).join('')}</tbody></table>`;
}
function pacingModalHtml(prefillTarget,prefillDistance,rows){
  return `<div class="modal-panel modal-panel-wide">
    <h2>${t('ui.pacingCalcTitle','配速試算與手環產生器')}</h2>
    <p class="modal-hint">${t('ui.pacingHint','輸入目標時間與距離，選擇配速策略，算出每個分段的預計通過時間，也可以下載成手環圖片。')}</p>
    <div class="pacing-inputs">
      <label class="field" for="pacing-target"><span>${t('ui.pacingTargetTime','目標時間')}</span><input type="text" id="pacing-target" placeholder="H:MM:SS" value="${escapeHtml(prefillTarget||'')}"></label>
      <label class="field" for="pacing-distance"><span>${t('ui.pacingDistance','總距離（公里）')}</span><input type="number" step="any" id="pacing-distance" value="${prefillDistance||''}"></label>
      <label class="field" for="pacing-strategy"><span>${t('ui.pacingStrategy','配速策略')}</span><select id="pacing-strategy">
        <option value="even">${t('ui.pacingEven','勻速')}</option>
        <option value="negative">${t('ui.pacingNegative','負分段（後段加速）')}</option>
        <option value="positive">${t('ui.pacingPositive','正分段（後段保守）')}</option>
      </select></label>
      <label class="field" for="pacing-interval"><span>${t('ui.pacingInterval','分段間隔')}</span><select id="pacing-interval">
        <option value="5">${t('ui.pacingEvery5','每 5 公里')}</option>
        <option value="10">${t('ui.pacingEvery10','每 10 公里')}</option>
        <option value="1">${t('ui.pacingEvery1','每 1 公里')}</option>
      </select></label>
    </div>
    <div class="modal-actions modal-actions-top">
      <button class="btn-primary" data-action="calc-pacing">${t('ui.pacingCalc','試算')}</button>
    </div>
    <div id="pacing-results">${rows&&rows.length?pacingTableHtml(rows):''}</div>
    <div class="modal-actions">
      ${rows&&rows.length?`<button class="btn-ghost" data-action="download-wristband">${t('ui.downloadWristband','下載配速手環圖片')}</button>`:''}
      <button class="btn-ghost" data-action="close-pacing">${t('ui.close','關閉')}</button>
    </div>
  </div>`;
}
let pacingModalRows=[];
const pacingModalEl_getter=()=>document.getElementById('pacing-modal');
function openPacingModal(){
  if(!currentRace) return;
  const goalA=currentRace.goals.find(g=>g.tier==='A');
  const prefillTarget=goalA&&goalA.targetTimeSeconds!=null?secToHMS(goalA.targetTimeSeconds):'';
  const prefillDistance=currentRace.route.distanceKm||'';
  pacingModalRows=[];
  pacingModalEl_getter().innerHTML=pacingModalHtml(prefillTarget,prefillDistance,null);
  pacingModalEl_getter().hidden=false;
}
pacingModalEl_getter().addEventListener('click',e=>{
  if(e.target.closest('[data-action="close-pacing"]')){
    pacingModalEl_getter().hidden=true;pacingModalEl_getter().innerHTML='';return;
  }
  if(e.target.closest('[data-action="calc-pacing"]')){
    const targetStr=document.getElementById('pacing-target').value;
    const distance=parseFloat(document.getElementById('pacing-distance').value);
    const strategy=document.getElementById('pacing-strategy').value;
    const interval=parseFloat(document.getElementById('pacing-interval').value);
    const targetSeconds=hmsToSec(targetStr);
    if(!targetSeconds||!distance){
      document.getElementById('pacing-results').innerHTML=`<p class="paste-error">${t('ui.pacingInvalid','請輸入有效的目標時間與距離')}</p>`;
      return;
    }
    pacingModalRows=computePacingRows(targetSeconds,distance,strategy,interval);
    pacingModalEl_getter().innerHTML=pacingModalHtml(targetStr,distance,pacingModalRows);
    return;
  }
  if(e.target.closest('[data-action="download-wristband"]')){
    runAsyncAction(downloadWristbandImage(pacingModalRows,currentRace),'配速手環');
    return;
  }
});
async function buildWristbandCanvas(rows,race){
  try{ await document.fonts.ready; }catch(e){}
  const W=360,H=120+rows.length*70;
  const canvas=document.createElement('canvas');
  canvas.width=W;canvas.height=H;
  const ctx=canvas.getContext('2d');
  ctx.fillStyle='#16231C';ctx.fillRect(0,0,W,H);
  ctx.fillStyle='#9BA3A0';
  ctx.font=`20px ${canvasFontFamily()}`;
  ctx.fillText(race&&race.name?Array.from(race.name).slice(0,16).join(''):t('ui.wristbandTitle','配速手環'),24,50);
  let y=100;
  rows.forEach(r=>{
    ctx.fillStyle='#EDEEE9';
    ctx.font='bold 28px "IBM Plex Mono",monospace';
    ctx.textAlign='left';
    ctx.fillText(String(r.distanceKm)+' km',24,y);
    ctx.fillStyle='#4C9A72';
    ctx.font='bold 32px "IBM Plex Mono",monospace';
    ctx.textAlign='right';
    ctx.fillText(secToHMS(r.cumulativeSeconds),W-24,y);
    ctx.textAlign='left';
    ctx.strokeStyle='#2A3038';ctx.lineWidth=1;
    ctx.beginPath();ctx.moveTo(24,y+20);ctx.lineTo(W-24,y+20);ctx.stroke();
    y+=70;
  });
  return canvas;
}
async function downloadWristbandImage(rows,race){
  if(!rows||!rows.length) return;
  const canvas=await buildWristbandCanvas(rows,race);
  canvas.toBlob(blob=>{
    if(!blob) return;
    downloadBlob(blob,t('ui.wristbandFilename','配速手環.png'));
  },'image/png');
}
```

---

## 6. 翻譯（日文、英文）

62 個只有這三個功能用的 key（`ui.climateChartYAxis` 是散佈圖舊版的 Y 軸，v4.18.2 時就已經沒用到，一起收在這裡）。中文是程式裡 `t('key','中文')` 的預設字，在第 5 節的原始碼裡。

```js
// 日文：貼回 index.html 的 const JA={…} 裡（放哪一行都可以，建議放在 'ui.elevationTrendTitle' 後面）
const JA_PARKED={
  'ui.climateChartLegendEstimated':'気候平均気温',
  'ui.climateChartLegendOther':'その他のレース',
  'ui.climateChartLegendPb':'距離別ベスト',
  'ui.climateChartLegendTrail':'トレイル',
  'ui.climateChartSlope':'気温が1°C上がるごとに、ペースは平均で約 {n} ポイント低下します（R²={r2}、{count}件のレースから算出）',
  'ui.climateChartSweetSpot':'最適な気温帯：{range}（高効率レース {n} 件から算出）',
  'ui.climateChartSweetSpotLabel':'スイートスポット',
  'ui.climateChartTitle':'気候とパフォーマンスの散布図',
  'ui.climateChartWeakR2':'R²が低いため、気温だけでは配速の差の大部分を説明できていません。この線はあくまで参考値で、まだ安定した傾向とは言えません——データが増えるほど信頼性が上がります。',
  'ui.climateChartXAxis':'体感温度',
  'ui.climateChartYAxisCurve':'ペース低下（自分の距離カーブ比）',
  'ui.climateCountEstimated':'うち {n} レースは気候平均気温',
  'ui.climateCountTrail':'トレイル {n} レースは補正済',
  'ui.climateCurveDefault':'効率の基準：自分の距離カーブ k={n}（距離の種類が足りないため一般的な既定値）',
  'ui.climateCurveFitted':'効率の基準：自分の距離カーブ k={a}（{b} 種の距離のベストから推定）',
  'ui.climateFrontierTip':'（この距離のベスト）',
  'ui.climateIncludeTrail':'トレイルを含める（登坂係数で補正）',
  'ui.climateTempEstimatedTip':'（気候平均・推定）',
  'ui.climateTrailNotReady':'登坂係数のデータ不足のため、トレイルは未反映',
  'ui.climateTrailTip':'／トレイル・補正済',
  'ui.downloadWristband':'リストバンド画像をダウンロード',
  'ui.eppAdoptGoal':'{tier}目標として採用',
  'ui.eppBarActual':'実際完走',
  'ui.eppBarBaseline':'基準',
  'ui.eppBarGravity':'登坂',
  'ui.eppBarOther':'その他要因',
  'ui.eppBarPredicted':'AI予測',
  'ui.eppBarThermal':'暑熱',
  'ui.eppDisclaimer':'これは過去のレースから統計的に算出した推定値であり、必ず実現する保証ではありません。自動的に目標にはなりません——採用する場合は下のボタンを押してください。',
  'ui.eppGravityPending':'登坂ペナルティ：データがまだ足りません（有効な区間が現在{n}個、最低{needed}個・2件以上のレースが必要）',
  'ui.eppGravityReady':'登坂ペナルティ：勾配1%ごとに自己平均ペースより約{pct}%遅い（R²={r2}、{n}件のレース・{count}区間から算出）',
  'ui.eppHideSegments':'区間別予測を隠す',
  'ui.eppNotReadyHint':'2つの係数が揃い、このレースに距離が入力されると、ここにペナルティ・ウォーターフォール図とAI予測タイムが表示されます。',
  'ui.eppPredictedLabel':'AI予測完走タイム',
  'ui.eppSegArrival':'到着予測時刻',
  'ui.eppSegElevation':'正味の標高変化',
  'ui.eppSegPace':'予測ペース',
  'ui.eppSegRange':'区間',
  'ui.eppSegmentsNeedProfile':'このレースにはまだ標高プロファイルのデータがありません（GPX/TCX/FITをインポートするか、標高変化グラフを手動入力すると使えます）。現在は総獲得標高を全体に均等に割り振った簡易推定を使用しています。',
  'ui.eppShowSegments':'区間別予測を表示（{km}kmごと）',
  'ui.eppThermalPending':'暑熱ペナルティ：データがまだ足りません（体感温度15°C以上のロードレースが現在{n}件、最低{needed}件必要）',
  'ui.eppThermalReady':'暑熱ペナルティ：気温が1°C上がるごとにペース低下 約{pct}%（R²={r2}、{n}件のレースから算出）',
  'ui.eppTitle':'環境ペナルティ予測（EPP）',
  'ui.pacingCalc':'計算',
  'ui.pacingCalcTitle':'ペース計算＆リストバンド作成',
  'ui.pacingDistance':'距離（km）',
  'ui.pacingDistanceCol':'距離',
  'ui.pacingEven':'イーブンペース',
  'ui.pacingEvery1':'1kmごと',
  'ui.pacingEvery10':'10kmごと',
  'ui.pacingEvery5':'5kmごと',
  'ui.pacingHint':'目標タイムと距離、ペース戦略を入力すると、区間ごとの通過予定タイムを計算します。',
  'ui.pacingInterval':'区間',
  'ui.pacingInvalid':'有効な目標タイムと距離を入力してください',
  'ui.pacingNegative':'ネガティブスプリット（後半加速）',
  'ui.pacingPositive':'ポジティブスプリット（後半抑えめ）',
  'ui.pacingStrategy':'ペース戦略',
  'ui.pacingTargetTime':'目標タイム',
  'ui.pacingTimeCol':'通過予定タイム',
  'ui.wristbandFilename':'ペース手帳.png',
  'ui.wristbandTitle':'ペースリストバンド',
  'ui.climateChartYAxis':'ペース低下（自己PB比）',
};
```

```js
// 英文：貼回 index.html 的 const EN={…} 裡（放哪一行都可以，建議放在 'ui.elevationTrendTitle' 後面）
const EN_PARKED={
  'ui.climateChartLegendEstimated':'Climate avg temp',
  'ui.climateChartLegendOther':'Other Races',
  'ui.climateChartLegendPb':'Best per distance',
  'ui.climateChartLegendTrail':'Trail',
  'ui.climateChartSlope':'For every 1°C rise in temperature, pace slows by about {n} percentage points on average (R²={r2}, based on {count} {count:race|races})',
  'ui.climateChartSweetSpot':'Sweet spot temperature range: {range} (based on {n} high-efficiency {n:race|races})',
  'ui.climateChartSweetSpotLabel':'Sweet Spot',
  'ui.climateChartTitle':'Climate vs. Performance',
  'ui.climateChartWeakR2':'R\u00b2 is low, meaning temperature alone doesn\u2019t explain most of the variation in pace. This line is only a rough reference, not yet a reliable pattern \u2014 it\u2019ll get more trustworthy with more data points.',
  'ui.climateChartXAxis':'Feels-Like Temperature',
  'ui.climateChartYAxisCurve':'Pace loss (vs. your distance curve)',
  'ui.climateCountEstimated':'{n} using climate avg temp',
  'ui.climateCountTrail':'{n} trail {n:race|races} corrected',
  'ui.climateCurveDefault':'Baseline: personal distance curve k={n} (not enough distinct distances to fit; using the common default)',
  'ui.climateCurveFitted':'Baseline: personal distance curve k={a} (fitted from bests at {b} {b:distance|distances})',
  'ui.climateFrontierTip':' (best at this distance)',
  'ui.climateIncludeTrail':'Include trail (corrected with your climb coefficient)',
  'ui.climateTempEstimatedTip':' (climate avg, estimated)',
  'ui.climateTrailNotReady':'Not enough climb-coefficient data yet; trail races left out',
  'ui.climateTrailTip':' / trail, corrected',
  'ui.downloadWristband':'Download wristband image',
  'ui.eppAdoptGoal':'Adopt as Tier {tier}',
  'ui.eppBarActual':'Actual finish',
  'ui.eppBarBaseline':'Baseline',
  'ui.eppBarGravity':'Gravity',
  'ui.eppBarOther':'Other factors',
  'ui.eppBarPredicted':'AI predicted',
  'ui.eppBarThermal':'Thermal',
  'ui.eppDisclaimer':'This is a statistical estimate from your past races, not a guarantee. It never becomes a goal automatically — use the buttons below if you want to adopt it.',
  'ui.eppGravityPending':'Gravity penalty: not enough data yet ({n} valid {n:segment|segments} so far, need at least {needed} from 2+ races)',
  'ui.eppGravityReady':'Gravity penalty: pace runs about {pct}% slower than your own average per 1% grade (R²={r2}, based on {n} {n:race|races}, {count} {count:segment|segments})',
  'ui.eppHideSegments':'Hide Per-Segment Prediction',
  'ui.eppNotReadyHint':'Once both coefficients are ready and this race has a distance filled in, a penalty waterfall chart and AI predicted time will appear here.',
  'ui.eppPredictedLabel':'AI Predicted Finish Time',
  'ui.eppSegArrival':'Est. Arrival Time',
  'ui.eppSegElevation':'Net Elevation',
  'ui.eppSegPace':'Predicted Pace',
  'ui.eppSegRange':'Segment',
  'ui.eppSegmentsNeedProfile':'This race doesn\u2019t have elevation profile data yet (import a GPX/TCX/FIT file, or fill in the elevation chart manually, to unlock this). Currently using a simplified estimate that spreads total elevation gain evenly across the whole distance.',
  'ui.eppShowSegments':'Show Per-Segment Prediction (every {km}km)',
  'ui.eppThermalPending':'Thermal penalty: not enough data yet ({n} road {n:race|races} with feels-like ≥15°C so far, need at least {needed})',
  'ui.eppThermalReady':'Thermal penalty: pace degrades about {pct}% per 1°C rise (R²={r2}, based on {n} {n:race|races})',
  'ui.eppTitle':'Environmental Pace Penalty (EPP)',
  'ui.pacingCalc':'Calculate',
  'ui.pacingCalcTitle':'Pace Calculator & Wristband Generator',
  'ui.pacingDistance':'Distance (km)',
  'ui.pacingDistanceCol':'Distance',
  'ui.pacingEven':'Even split',
  'ui.pacingEvery1':'Every 1 km',
  'ui.pacingEvery10':'Every 10 km',
  'ui.pacingEvery5':'Every 5 km',
  'ui.pacingHint':'Enter a target time, distance and pacing strategy to calculate your expected split times.',
  'ui.pacingInterval':'Interval',
  'ui.pacingInvalid':'Please enter a valid target time and distance',
  'ui.pacingNegative':'Negative split (faster second half)',
  'ui.pacingPositive':'Positive split (conservative second half)',
  'ui.pacingStrategy':'Pacing strategy',
  'ui.pacingTargetTime':'Target time',
  'ui.pacingTimeCol':'Expected split time',
  'ui.wristbandFilename':'pace-wristband.png',
  'ui.wristbandTitle':'Pace Wristband',
  'ui.climateChartYAxis':'Pace Degradation (vs. own PB)',
};
```

---

## 7. 使用說明的句子

App 內「使用說明」→「裝備補給與戰略」那一條（中、日、英）拿掉的部分：

```text
中文：補給時程規劃、配速試算與手環產生器。  （現在：補給時程規劃。）
日文：補給計画、ペース計算＆リストバンド作成。  （現在：補給計画。）
英文：…starter templates), a nutrition schedule, and a pace calculator with wristband generator.
      （現在：…starter templates) and a nutrition schedule.）
```

EPP 和氣候散佈圖原本就沒有寫進使用說明。USAGE.md、README.md 裡的段落（舊版本的紀錄）還在，標了「v4.19.0 暫時拿掉」。

---

## 8. 測試

### `Climate` 群組（9 項，原本在 `class PublicLink(Group):` 前面；`GROUPS` 裡是 `'climate':    lambda: Climate('climate'),`，放在 `'offline'` 和 `'publink'` 中間）

個人距離曲線、溫度估計值退回、越野校正開關、甜蜜點、EPP 沿用最嚴格的資料層。
```python
class Climate(Group):
    """氣候與表現：個人距離曲線、溫度估計值退回、越野校正開關。"""

    SEED = """()=>{
        state.races=[];
        state.homeTab='career';   // v4.0：氣候與表現圖在「生涯數據」分頁
        const add=(name,sport,km,sec,feels,avg,elev,splits)=>{
          const r=emptyRace(name,sport,'completed','2026-0'+(1+state.races.length%9)+'-1'+(state.races.length%9));
          r.route.distanceKm=km; r.results.chipTimeSeconds=sec;
          if(feels!=null) r.raceDayWeather.feelsLikeTempC=feels; if(avg!=null) r.climateForecast.avgTempC=avg;
          if(elev!=null) r.route.elevationGainM=elev; if(splits) r.splits=splits; state.races.push(r); return r; };
        add('5K','road_running',5,1230,12,null); add('10K','road_running',10,2580,15,null);
        add('15K','road_running',15,4020,null,22); add('半馬','road_running',21.1,5700,18,null);
        add('30K','road_running',30,8700,null,26); add('全馬','road_running',42.195,12400,20,null);
        add('全馬熱','road_running',42.195,13300,31,null);
        add('沒溫度','road_running',10,2700,null,null);
        const sp=(n,base)=>Array.from({length:n},(_,i)=>({distanceKm:1,avgPaceSecPerKm:base+i*40,elevationGainM:20+i*25,elevationLossM:5}));
        add('越野A','trail_running',25,9500,24,null,1200,sp(8,330)); add('越野B','trail_running',30,11800,28,null,1500,sp(8,360)); add('越野C','trail_running',20,7300,16,null,900,sp(8,300));
        try{ localStorage.removeItem('climate-include-trail-v1'); }catch(e){}
        return true;
    }"""

    def body(self, page):
        c = self.checks
        page.evaluate(self.SEED)
        # 舊規則只有三個經典距離 4 場；新規則 5K/15K/30K 都進來，沒溫度的仍然排除
        c['all_road_distances_now_count'] = page.evaluate('''()=>{
            const old=computeClimatePerformancePoints().length;
            const p=computeClimatePerformancePoints({allDistances:true,allowEstimatedTemp:true});
            const names=p.map(x=>x.race.name);
            return old===4 && p.length===7 && names.includes('5K') && names.includes('30K') && !names.includes('沒溫度');
        }''')
        # 曲線：k 從六個距離擬合、落在合理範圍；包絡讓所有效率 ≤100 且剛好一場是 100
        c['distance_curve_fitted_and_enveloped'] = page.evaluate('''()=>{
            const p=computeClimatePerformancePoints({allDistances:true,allowEstimatedTemp:true});
            const cv=p.curve;
            const effs=p.map(x=>x.efficiencyPct);
            return cv.fitted && cv.k>1.0 && cv.k<1.25 && cv.distinctDistances===6
                && effs.every(e=>e<=100.0001) && effs.filter(e=>e>99.999).length===1;
        }''')
        c['default_k_when_single_distance'] = page.evaluate('''()=>{
            const keep=state.races; state.races=keep.filter(r=>r.route.distanceKm===42.195);
            const cv=computePersonalDistanceCurve(); state.races=keep;
            return cv && !cv.fitted && Math.abs(cv.k-RIEGEL_DEFAULT_K)<1e-9;
        }''')
        # 溫度退回：兩場只有氣候平均溫的被標成估計值，圖上畫成空心
        c['estimated_temp_flagged_and_hollow'] = page.evaluate('''()=>{
            const p=computeClimatePerformancePoints({allDistances:true,allowEstimatedTemp:true});
            const est=p.filter(x=>x.tempEstimated).map(x=>x.race.name).sort().join(',');
            renderCalendar();
            const hollow=document.querySelectorAll('.climate-chart-svg circle[fill="none"]').length;
            return est==='15K,30K' && hollow>=2;
        }''')
        # 越野：預設關；開了且爬升係數就緒才進來，畫成三角，且效率已校正（比未校正高）
        c['trail_off_by_default_on_when_toggled'] = page.evaluate('''()=>{
            const off=computeClimatePerformancePoints({allDistances:true,allowEstimatedTemp:true,includeTrail:false});
            const on =computeClimatePerformancePoints({allDistances:true,allowEstimatedTemp:true,includeTrail:true});
            const trail=on.filter(x=>x.isTrail);
            const raw=state.races.find(r=>r.name==='越野A');
            const uncorrected=on.curve.predictSeconds(raw.route.distanceKm)/raw.results.chipTimeSeconds*100;
            return off.filter(x=>x.isTrail).length===0 && trail.length===3 && trail[0].efficiencyPct>uncorrected;
        }''')
        c['trail_toggle_rerenders_with_triangles'] = page.evaluate('''async()=>{
            const cb=document.querySelector('[data-action="climate-toggle-trail"]');
            cb.checked=true; cb.dispatchEvent(new Event('change',{bubbles:true}));
            await new Promise(s=>setTimeout(s,300));
            const tri=document.querySelectorAll('.climate-chart-svg path[d^="M"]').length;
            const text=document.querySelector('.climate-chart-wrap').innerText;
            return localStorage.getItem('climate-include-trail-v1')==='1' && tri>=3 && /10 場賽事推算/.test(text) && /3 場越野已校正/.test(text);
        }''')
        c['trail_excluded_when_gravity_not_ready'] = page.evaluate('''()=>{
            state.races.forEach(r=>{ if(r.sportType==='trail_running') r.splits=[]; });
            const on=computeClimatePerformancePoints({allDistances:true,allowEstimatedTemp:true,includeTrail:true});
            renderCalendar();
            const note=!!document.querySelector('.climate-trail-notready');
            return on.filter(x=>x.isTrail).length===0 && note;
        }''')
        # 甜蜜點只看效率 ≥98，不是「每個距離的最佳」都算
        c['sweet_spot_uses_efficiency_not_frontier'] = page.evaluate('''()=>{
            const p=computeClimatePerformancePoints({allDistances:true,allowEstimatedTemp:true});
            const band=computeSweetSpotBand(p);
            const frontier=p.filter(x=>x.isPb).length;
            return band && band.count<frontier && band.count===p.filter(x=>x.efficiencyPct>=98).length;
        }''')
        # EPP 沒有跟著放寬：不傳參數 = 舊規則
        c['epp_still_strict'] = page.evaluate('''()=>{
            const p=computeClimatePerformancePoints();
            return p.length===4 && p.every(x=>!x.tempEstimated && !x.isTrail && x.category);
        }''')
```

### 簡易版（`simple` 群組）改過的三項

**`simple_detail_does_not_render_advanced`**：原本也檢查 EPP 和配速試算的按鈕在簡易版不出現。拿回來時把這兩個加回 `ADV` 那一串：

```text
原本：tplan:q('[data-section="trainingPlan"]'),epp:q('.epp-section'),pacing:q('[data-action="open-pacing-modal"]'),
現在：tplan:q('[data-section="trainingPlan"]'),
```

**`note_button_switches_to_full_and_everything_returns`**：切回完整版之後「全部回來」的清單原本有配速試算，拿回來時加回 `'pacing'`：

```text
原本：'nutri', 'tplan', 'pacing', 'fatigue', 'paste', 'aiPrompt', 'shoe'])
```

**`home_trims_trophy_and_charts`**：原本拿氣候散佈圖當「完整版才有、簡易版收起來」的例子，現在改用熱力圖（`.heatmap-wrap`），兩種都對，拿回來時不用改：

```text
原本：const full=q('.trophy-cabinet-wrap') && q('.climate-chart-wrap') && q('.honor-card') && q('.year-in-review-row');
原本：const simple=!q('.trophy-cabinet-wrap') && !q('.climate-chart-wrap') && q('.honor-card') && q('.year-in-review-row')
```

### `v433` 群組（彈窗輸入框的框線）改過的兩處

`MODALS` 那一串原本也打開配速試算的彈窗；它有 4 格，所以門檻從 25 改成 21。拿回來時兩處都改回去：

```text
原本：['nutrition',()=>{ hide(); openNutritionDictModal(); }],['pacing',()=>{ hide(); selectRace(__rid); openPacingModal(); }],
原本：c[f'other_inputs_framed_{theme}'] = m['n'] >= 25 and not m['bad']
```

### `v419` 群組

v4.19.0 新增，檢查這三個功能確實拿掉、旁邊的東西照常（目標卡、熱力圖、榮譽櫃、應援指南卡的預計時間、返回鍵和 Esc）、這份檔案完整。拿回哪個功能，就把 `v419` 裡檢查「沒有那個功能」的部分刪掉。
