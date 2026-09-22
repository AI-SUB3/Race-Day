# 賽事紀錄 — 進度交接摘要

> 貼到新對話開頭即可接續。最後更新：v3.53.0

---

## 專案基本資料

- **名稱**：賽事紀錄（英文品牌 My Race；介面英文名 Race Log）
- **Repo**：AI-SUB3/Race-Day → https://ai-sub3.github.io/Race-Day/
- **架構**：純前端，主體是單一 `index.html`（約 938 KB），無建置步驟
- **Firebase**：race-day-6da0b（Blaze），Google 登入 + Firestore
- **工作路徑**：`/home/claude/race-schema/index.html`

### 部署檔案（缺一不可）

```
repo 根目錄/
├── index.html
├── sw.js             ← v3.31.0 起，離線快取；必須跟 index.html 同層
├── icons/            ← v3.14.0 起必要，少傳圖示會空白
│   ├── manifest.webmanifest
│   ├── icon-192.png / icon-512.png
│   ├── apple-touch-icon.png
│   └── help-avatar.png
├── about/ · sitemap/ · glossary/ · functions/
├── functions-share/  ← v3.48.0，公開連結 OG 預覽（部署見其 README-DEPLOY.md；node_modules 不要進 repo）
├── README.md · USAGE.md · CHANGELOG.md · CHANGELOG-archive.md · LICENSE
├── test_suite.py     ← 回歸測試（不需部署，但請保存）
└── firestore.rules · robots.txt · sitemap.xml
```

---

## 工作方式（請沿用）

1. **每一輪流程**：先查證現況 → 改 → 寫 Playwright 測試驗證 → **實際截圖看畫面** → 跑全站回歸 → 版本號 +1 → 更新 CHANGELOG/USAGE/README → 交付檔案
2. **交付檔名一律 `index.html`**（GitHub Pages 需求）
3. **每次改完必跑**：
   - JS 語法檢查（把 `<script>` 內容丟進 `new Function`）
   - HTML 標籤平衡檢查
   - `/tmp/test_drawer_regression.py`（全站回歸）
4. **程式碼註解用繁體中文，寫「為什麼」不寫「做什麼」**
5. **提案不照單全收**：查證後不合理的部分要說明理由並提替代方案

### 測試套件

`test_suite.py`（180 項檢查，16 個群組；suite 變大後單次執行常超過工具的單指令時間上限，建議分批跑，例如 `python3 test_suite.py core drawers sport multisport sync`、`security mobile i18n`、`data`、`share`、`share_touch offline`、`climate publink pubview`、`paste`）取代原本散落的 219 支臨時腳本，
**請跟 index.html 一起保存並持續增補**。

```bash
pip install playwright && playwright install chromium

python3 test_suite.py                 # 全部（約 30 秒）
python3 test_suite.py security mobile # 指定群組
python3 test_suite.py --list          # 列出群組
APP=/path/to/index.html python3 test_suite.py
```

群組：`core` `drawers` `sport` `multisport` `sync` `security` `mobile` `i18n` `data` `share` `share_touch` `offline`（自起本機 http 伺服器，SW 不能在 file:// 跑）`climate`

離開碼：0 通過 / 1 有失敗 / 2 參數錯誤（可直接接 CI）。
已用「故意注入 XSS 漏洞」驗證過它真的抓得到回歸，不是只會印綠勾。

**新增檢查時的原則**：斷言「行為」不斷言實作細節（class 名稱、DOM 順序），
否則改版面就要跟著改測試，測試最後會被當成雜訊略過。

---

## 已完成（v3.x 重點）

### 架構
- **詳情頁順序：header → 區段導覽列 → 成績儀表板（完賽才有）→ 各區段**（v3.30.0 儀表板移出賽後區段；v3.34.0 導覽列提到儀表板上方）
- **詳情頁五個區段**（v3.42.0 合併、v3.43.0 對調順序）：基本資訊與時間／路線與氣象（子標題：官方路線、當日氣象）／裝備補給與戰略／預算與行程規劃／賽後紀錄與個人數據。`section-weather` 這個 id 已不存在；改區段順序時 `QUICK_NAV_SECTIONS` 要一起改，測試會比對兩者；空抽屜卡片帶 `is-empty`，由各卡片自行判斷
- **抽屜面板化**：13 個抽屜（equipment / results / review / basicInfo / schedule / weather / checkpoints / mediaLinks / nutritionPlan / trainingPlan / goals / route / logistics），詳情頁全部變成「摘要卡片 + 點開編輯」
- **雲端同步六種資料**：賽事、鞋款、補給品資料庫、個人資料、裝備範本、徽章解鎖。合併規則「本機優先」，不覆蓋本機已有值
- **同步診斷**：本機 vs 雲端對照表，數字不一致標警示色，另顯示儲存空間用量（>80% 轉紅）
- **儲存失敗一定跳警示**（七種資料全涵蓋）

### 功能
- **生涯回顧主卡**：長按 PB 數字 1.5 秒解鎖（或 Cmd+K → `wrap`），含軌跡畫廊（GPX→SVG 霓虹線條）、戰靴排行、能量補給統計
- **鐵人三項分項成績**：FIT session 解析，游泳／T1／自行車／T2／跑步各自的距離、時間、心率、配速（各用自己的單位）
- **賽事五維雷達圖**：距離／爬升／氣溫嚴苛／高心率／穩定度，Canvas 原生繪製
- **徽章 103 枚**，五大類
- **動態回顧輪播（Story Mode）入口在 Cmd+K**（v3.25.0 移除導覽列按鈕）。手機在搜尋框打 `>` 即可開指令面板（v3.29.0）

### 視覺／互動
- 獎牌牆 3D 傾斜與反光、懸浮按鈕磁性吸附、iOS 空間景深（彈窗時主畫面退後失焦）
- 畫面縮放鎖定只針對觸控（iOS 的 JS 手勢攔截、連點兩下）；桌機 Ctrl/⌘＋滾輪不攔（v3.33.0）
- 表格去 Excel 化，分段表固定高度內捲

### 運動別正確性（近期重點）
- **跑步步頻 ×2**（FIT 記單腳，區間 30–110 才換算，可安全重跑）
- **游泳用每 100m 配速**，不顯示步頻與總爬升
- **多項運動不顯示全場平均**配速／心率／步頻
- **分享圖同樣受上述規則管轄**。v3.28.0 起數據集中在 `shareStatsBadges()`／`shareDetailRows()`，方形與限動共用；改運動別規則改那兩個函式就好
- **社群用途的圖（分享圖、徽章、年度回顧）走 `shareOrDownloadImage()`**：觸控裝置進系統分享面板、桌機下載。列印用途（手環、作戰卡、應援指南）維持 `downloadBlob()`

---

## 目前卡在哪 / 待辦

### 需要你決定
1. **Repo 是否轉私有**：LICENSE 已改成「版權所有，保留一切權利」，但 **repo 公開就看得到原始碼**。真正不開源需付費方案（GitHub Pro）才能從私有 repo 部署 Pages

### 已知限制（已記錄，非錯誤）
- **超馬步頻誤判**：走路多的超馬若總步頻落在 100–110，會被誤乘成 200–220。需用配速輔助判斷才能解
- **Android 首次長按不震動**：Chrome 要求先點過畫面，touchstart 不算手勢。已自動降級為加強視覺回饋
- **CSP**：JS 全行內，有意義的 CSP 需先拆出獨立 .js，屬架構級改動

### 下一步候選
- 行為追蹤型徽章（連續鍵盤操作、停留時間等）需 session 級追蹤機制，獨立一輪
- 其他表格（賽事清單、系列比較、鞋款分析）尚未做高度處理

---

## 關鍵決策（不要推翻，除非有新理由）

| 決策 | 理由 |
|---|---|
| 配色沿用既有土色系 | 金=PB／達成、綠=進行中焦點、橘紅=警示。加高彩度色會讓語彙失效 |
| 圖表網格不用 `--rule` | 那是分隔線色，深色模式下跟底色只差一階。網格用 `--ink-soft` 配透明度（外圈 0.75／內圈 0.42／軸線 0.36） |
| 不做時間分段輸入框 | 時間欄位共用解析邏輯，改動牽動全站；三格在手機上更難用 |
| 匯入紀錄檔一律覆蓋（含成績時間） | v3.24.0 依使用者要求推翻 v3.22.0 的「時間不覆蓋」。程式不替使用者保留，改成套用前逐欄標出「會取代現有的 ⋯」，不想覆蓋就取消。檔案沒有的欄位仍不清空 |
| 缺資料回傳 null 不是 0 | 0 在雷達圖上看起來像「很輕鬆」，跟「沒資料」是兩回事 |
| 鞋子里程只算跑步段 | 三鐵的 `route.distanceKm` 是全程（含游泳騎車）。一律走 `shoeDistanceOfRace()`；多項賽事沒有 `legs` 時回 0，寧可少算 |
| 分項成績用 FIT session 而非配速猜測 | 猜測遇到爬坡慢騎或轉換區小跑會判斷錯 |
| 範例資料真刪除不進垃圾桶 | 隨時可一鍵重匯，留垃圾桶會洗掉真正要救的賽事 |
| 徽章只做資料算得出來的 | 行為追蹤是另一套機制，需獨立驗證 |
| 氣候圖用個人距離曲線、EPP 維持經典距離 | 圖是給人看趨勢的，多收資料值得；EPP 係數拿去預測完賽時間，不混估計值。`computeClimatePerformancePoints()` 不帶參數 = 嚴格版 |
| 縮圖 480px 上限（v3.26.0） | 卡片實測需要 490～510 裝置像素。再往上到 640px 要 69KB，跟 760px 原圖的 80KB 幾乎一樣，等於存第二份原圖；而直接用原圖渲染會從 75ms 變 152ms（base64 串進 innerHTML 的字串成本） |
| 貼上網址只存網址，不抓網頁 | 跨網域抓網頁會被 CORS 擋、要後端。OG 解析對住宿只給得到飯店名，給不到日期與金額，增益小於現有的貼文字方案 |
| 翻譯佔位符只有 `{n}`（`tf`）與 `{a}`/`{b}`（`tf2`） | 寫成 `{s}` 不會被置換、會原樣顯示。守門測試 `paste_modals_leave_no_placeholder` |
| 貼上住宿／交通要扛得住「網頁選字複製」的雜訊 | 麵包屑、星等評論、按鈕字樣、「平均每晚」參考價都是真實會遇到的雜訊。找名稱／費用前先過濾雜訊行；費用優先找「總金額」標籤，不用第一個看起來像錢的數字；「酒店」等常見命名要在關鍵字清單裡，不是只有「飯店」 |
| 貼上票券：方向與工具是猜的，視窗裡可直接改 | 去程／回程標記切段、無標記依賽事日期猜方向；「車次」高鐵台鐵共用要看抬頭；訂位代號先抽掉再找班次 |
| 貼上住宿一律新增不覆蓋 | 判斷錯只是多一筆可刪的紀錄；欄位預設全勾（訂房信是結構化的），但只有日期時時間留空不猜 |
| 貼上心得只判斷、不直接寫 | 全域貼上是很吵的路徑，誤判＝把別人的剪貼簿塞進資料。計分制 ≥5 分才攔，數字一律預設不勾並附原文片段 |
| 公開快照白名單制 | `buildPublicSnapshot()` 只放明列欄位；`/public/{id}` 一包 JSON 字串；撤銷＝刪文件。改 firestore.rules 見 functions-share/README-DEPLOY.md |
| QR 自己產不用套件 | 單檔＋離線＋SRI 的成本高於一個 200 行的編碼器。正確性用 OpenCV 編碼器逐格比對、解碼器實掃驗證 |
| 外部套件走 jsDelivr 的 npm 路徑並鎖死版號 | SRI 雜湊要驗得出來才敢用。jsDelivr 逐位元組轉送 npm 原檔，雜湊能從官方 tarball 算出並比對；cdnjs 自行重新打包無從驗證。浮動版號（`@6`）配 SRI 則是定時炸彈，上游一發版就整包被擋 |
| 破壞性操作用兩段式確認 | 沿用既有模式，5 秒自動解除，狀態各自獨立 |

---

## 近期修過的坑（避免重蹈）

- **`e.target.closest()` 未防呆**：事件派送到 document 時 `e.target` 非元素節點會拋例外
- **`filter`/`transform` 會破壞 `position:fixed` 子孫**：套在 `#main-content`（FAB 在 `</main>` 之外）才安全
- **manifest 路徑相對於 manifest 自身**，不是相對於網頁
- **翻譯鍵有動態組合**（`'ui.leg_'+sport`），不能只靠搜尋判斷是否無用
- **`saveJson`/`loadJson` 必須往外拋**，包 try/catch 會讓儲存警示永遠不觸發
- **iOS Safari 不能對大元素套 `filter`**：`filter:blur()` 會把整棵子樹點陣化成單一 GPU 圖層，`#main-content` 這種整頁的元素會直接把分頁撐爆（白畫面＋不斷重整＋「重複發生問題」）。`transform` 沒事（會分塊）。彈窗景深的模糊只給 `(hover:hover) and (pointer:fine)`（v3.46.0）
- **SW 出問題時的脫困方式：網址加 `?nosw=1`**，會註銷 worker、清快取、這個分頁不再註冊。連續三次啟動失敗也會自動做（`boot-fails-v1`，`init()` 成功時歸零）
- **SW 裡不要把 `{signal}` 傳給 navigate 模式的 Request**：瀏覽器處理不一致，丟錯就會永遠只吃快取。逾時用 `Promise.race`
- **清 SW 的順序：先 unregister 再刪 caches**，否則還活著的 worker 會把快取建回來
- **升級 CDN 套件時 `sw.js` 的預快取清單要同步改**（URL 一字不差），否則 SRI 對不上、套件不載入。測試 `sw_precaches_exact_cdn_urls` 會抓
- **`firebase-messaging-sw.js` 註冊在 `/` 根路徑**，GitHub Pages 專案站台下這個路徑是 404（除非自訂網域）；離線 SW 註冊在 `./`，scope 更具體、會控制頁面，兩者不衝突，但推播是否真的能用要在實機確認
- **照片匯入有三道各自獨立的關卡**：檔案選擇器的 `accept`、全域拖曳的副檔名白名單、EXIF 有沒有拍攝時間。任何一道擋掉都是「照片加不進去」，改的時候三道都要看（v3.38.0）
- **EXIF 內嵌縮圖沒有方向標籤**：拿來顯示前要用主圖的 Orientation 轉正（`orientThumbnail()`），解碼時 `imageOrientation:'none'` 避免瀏覽器再轉一次
- **容器沒有下內距時，最後一個子元素的 margin 會穿出去**（margin collapsing）：`details.section` 為此加了 `padding-bottom` 並把 `>*:last-child` 的 margin 歸零（v3.41.0）
- **Canvas 不會跟著 CSS 變數換色**：新增用 canvas 畫的東西，要掛進 `redrawThemeDependentCanvases()`，否則切主題後顏色停在舊的
- **抽屜（`drawerEl`）不在 `#detail` 底下**：掛在 `detailEl` 的事件監聽抽屜收不到，要兩邊都掛（v3.29.0 時間驗證踩到）
- **看不懂的輸入不能存成 null**：那是把使用者的值清掉。留在欄位、標紅、不寫入
- **CHANGELOG 版本號曾重複**，新增前先確認號碼未被使用
- **升級 xlsx / idb-keyval 時必須同時換 `integrity` 雜湊**，只改版號會被瀏覽器擋掉。作法：`npm pack <套件>@<版本>` 解開後 `openssl dgst -sha384 -binary <檔案> | openssl base64 -A`

---

## 待你回報

- 手機上獎牌牆與搜尋的實際流暢度。v3.26.0 把縮圖從 320px 提到 480px 換畫質，沙盒量到首屏 75ms→100ms，**實機是否還順要你回報**；太卡的話把 `COVER_THUMB_PX` 調回 420 或 360 就好，重產是自動的
