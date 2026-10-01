# 賽事紀錄 — 進度交接摘要

> 貼到新對話開頭即可接續。最後更新：v4.3.0

---

## 專案基本資料

- **名稱**：賽事紀錄（英文品牌 My Race；介面英文名 Race Log）
- **Repo**：AI-SUB3/Race-Day → https://ai-sub3.github.io/Race-Day/
- **架構**：純前端，主體是單一 `index.html`（約 1.5 MB），無建置步驟
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

`test_suite.py`（609 項檢查，27 個群組；suite 變大後單次執行常超過工具的單指令時間上限，建議分批跑，例如 `python3 test_suite.py core drawers sport sync`、`security mobile i18n data`、`share share_touch offline climate publink`、`pubview paste feedback training`、`multisport`、`radar`、`journey simple simple_phone`、`ux v4 v41`、`v42`、`v43`）取代原本散落的 219 支臨時腳本，
**請跟 index.html 一起保存並持續增補**。

```bash
pip install playwright && playwright install chromium

python3 test_suite.py                 # 全部（約 30 秒）
python3 test_suite.py security mobile # 指定群組
python3 test_suite.py --list          # 列出群組
APP=/path/to/index.html python3 test_suite.py
```

群組：`core` `drawers` `sport` `multisport` `sync` `security` `mobile` `i18n` `data` `share` `share_touch` `offline`（自起本機 http 伺服器，SW 不能在 file:// 跑）`climate` `publink` `pubview` `paste` `feedback` `training` `radar` `journey` `simple`（不預設完整版，測新裝置的預設）`simple_phone`（360／390 × 簡易／完整 × 中英日，一行頂列）`ux`（v3.98 起的使用者體驗修正，107 場固定種子資料）`v4`（v4.0 版面：歡迎卡、頂列三樣、頭像選單、首頁分頁、手機清單、賽事頁頁首）`v41`（v4.1 修正：返回鍵關最上面那一層、生涯數據網址、即將到來數字、月份箭頭、對比、圖表字、點擊範圍、範例資料日期；重新整理那一項自起本機 http）`v42`（v4.2：比完賽之後記錄成績、打包模式、賽前四格與區段順序、生涯數據可以點；手機那兩項要跑中日英 × 三種字級，最好單獨一批）`v43`（v4.3：精簡的「下一場」卡、獎牌牆、表格排序與各距離最佳、全馬只算跑步、版本號；fit 三項跑 360／390／700 × 中日英 × 三種字級）

離開碼：0 通過 / 1 有失敗 / 2 參數錯誤（可直接接 CI）。
已用「故意注入 XSS 漏洞」驗證過它真的抓得到回歸，不是只會印綠勾。

**新增檢查時的原則**：斷言「行為」不斷言實作細節（class 名稱、DOM 順序），
否則改版面就要跟著改測試，測試最後會被當成雜訊略過。

---

## 已完成（v3.x 重點）

### 架構
- **詳情頁順序：區段導覽列（最前面是「‹ 返回」）→ header → 成績儀表板（完賽才有）→ 各區段**（v3.30.0 儀表板移出賽後區段；v3.34.0 導覽列提到儀表板上方；v3.99.0 導覽列移到最上面、加返回鍵）
- **賽事頁是獨立畫面（v3.99.0）**：`body.viewing-detail` 時首頁分頁列、月曆、搜尋篩選列、焦點卡都 `display:none`。網址 `#race=<id>`／`#new`，由 `renderAll()` 開頭的 `syncRouteWithState()` 統一處理
- **v4.0 版面**：`#main-content` 依序是 `.home-tabs` → `#focus-panel-slot` → `.topbar-row2` → `#calendar` → `#detail` → `.app-footer`（版本號、版權）。頂列只有 `#btn-mode-toggle`、`#btn-new`（手機藏起來，用右下角 `#btn-new-fab`）、頭像選單；字體、深色模式（`#btn-theme-toggle` 是 role=switch）、語言、匯入匯出（兩組 `<details>`）、`#btn-help`、`#btn-feedback`、清除全部資料（`#btn-clear`，v4.1 起移到最下面自己一區）、登出（`#auth-signout`，選單最底下）都在 `#account-menu-panel` 裡。原本的 `.topbar-row3`、`#data-mgmt-menu`、說明與回饋懸浮鈕都拿掉了
- **詳情頁五個區段**（v3.42.0 合併、v3.43.0 對調順序）：基本資訊與時間／路線與氣象（子標題：官方路線、當日氣象）／裝備補給與戰略／預算與行程規劃／賽後紀錄與個人數據。`section-weather` 這個 id 已不存在；改區段順序時 `QUICK_NAV_SECTIONS` 要一起改，測試會比對兩者；空抽屜卡片帶 `is-empty`，由各卡片自行判斷
- **抽屜面板化**：13 個抽屜（equipment / results / review / basicInfo / schedule / weather / checkpoints / mediaLinks / nutritionPlan / trainingPlan / goals / route / logistics），詳情頁全部變成「摘要卡片 + 點開編輯」
- **雲端同步六種資料**：賽事、鞋款、補給品資料庫、個人資料、裝備範本、徽章解鎖。合併規則「本機優先」，不覆蓋本機已有值
- **同步診斷**：本機 vs 雲端對照表，數字不一致標警示色，另顯示儲存空間用量（>80% 轉紅）
- **儲存失敗一定跳警示**（七種資料全涵蓋）

### 功能
- **生涯回顧主卡**：長按 PB 卡 1.5 秒解鎖（或 Cmd+K → `wrap`、PB 卡上的「打開生涯回顧 ›」），含軌跡畫廊（GPX→SVG 霓虹線條）、戰靴排行、能量補給統計。v4.2 起很快點一下 PB 的時間是打開締造 PB 的那一場
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
- **多項運動不顯示全場平均**配速／心率／步頻。判斷一律用 `isMultisportRace()`（有分項，或運動種類是三鐵／二鐵）；v4.2 以前只看有沒有 `legs`，手動填時間的鐵人三項會算出 3'01"/km
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
- 筆電首頁預設仍是月曆（v4.3 設計稿②你選了照舊）。之後若覺得空月份太多，設計稿的方案 A（筆電也預設清單）、C（這個月沒比賽就跳到下一場的月份）可以再拿出來
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
| 功能因缺資料而不出現時，要說原因 | 「選項消失」跟「功能壞掉」在畫面上一樣。分享選項灰掉＋標原因（v3.61）、照片略過清單（v3.38）、氣象沒軌跡的說明（v3.71）都是同一條 |
| 預報不可以佔用「實際值」欄位 | 回填一律只填空欄位。預報先填了 `raceDayWeather.feelsLikeTempC`，賽後歷史天氣就補不進真正的實測值。預報只填 `climateForecast.*` |
| 多項運動分段推算只是退路 | FIT 有多個 session 一律用 `buildRaceLegs()`（手錶記的、精確）；只有 1 個 session 才推算：二鐵 `inferRunBikeRunLegs()`、三鐵 `inferSwimBikeRunLegs()`，共用 `analyzeSpeedProfile()`，依 `sportType` 選用。推算的分段標 `inferred:true`；推算的游泳距離一律 null |
| 貼齊畫面頂端的東西要讓出狀態列 | 用 `var(--sat)`（`env(safe-area-inset-top)`）。新增全螢幕視窗或固定在頂端的按鈕都要加；覆寫位置的規則放樣式表最後，不然會被原本的規則蓋掉 |
| 年度回顧長圖的版面不能被新區塊擠掉 | 選擇性區塊一律接在最下面、長圖加長（`drawYearJourneySection` 從 y=1880 開始），不要塞進中間。有逐像素測試 |
| 賽事旅程的地名 | `looksLikePlace()`：有括號或超過 20 字不拿去查（使用者的場地欄位會寫備註）。同縣市一律在地（`journeyRaceCounty`）。沒有地名用賽事名稱，不用「賽場」 |
| 賽事旅程的地點快取不能寫進賽事 | `journey-geo-v1`（IndexedDB，這台裝置自己的）。寫進 race 會讓每場都被判定有變更、重新上傳雲端。地圖輪廓是 Natural Earth 簡化後內建的 `JOURNEY_TW`／`JOURNEY_EA`（整數編碼，×1000／×100）；要加範圍就重新產生，不要直接放原始 GeoJSON |
| 意見回饋表單 | 填寫網址與三個 entry ID 在 `FEEDBACK_FORM_URL`／`FEEDBACK_PREFILL`（版本 1727311429、裝置 1690470865、當下畫面 1958998644），有測試鎖住。表單編輯頁：https://docs.google.com/forms/d/13QA_csP1fQNmuX2cyGZwLEt1xnXFepBm8bekPHKNNHw/edit；回覆試算表：https://docs.google.com/spreadsheets/d/1IN94KHlkWqfNdJOLSNtn_ogsD7qv2iWQr5rIzv6XiEo/edit（兩者都要表單擁有者的帳號才能開）。改了表單欄位要重新取得預先填入連結、更新 entry ID 與測試 |
| 簡易版只改顯示、不碰資料（v3.97.0） | `isSimpleMode()`（`<html data-mode="simple">`）。賽事頁、首頁的進階區塊在 JS 產生畫面時就直接不產生（`renderDetail` 裡的 `S?'':…`），**不要**改成產生了再用 CSS 藏：手機少畫很多東西，公開分享頁也不會被誤傷。CSS 只藏固定在頁面上的入口（訓練、表格檢視、匯出 CSV／ipynb）。新增一個進階區塊時，記得在 `renderDetail` 加 `S?'':`，有資料的話也加進 `simpleHiddenItems()` 讓頁尾提示列得出來 |
| 簡易版的偏好與預設 | `ui-mode-v1`（`simple`／`full`，這台裝置、不上雲端）＋ `ui-mode-auto-v1`（自動選的）。沒選過時 `resolveInitialUiMode()` 在第一次 `renderAll` 前決定：沒有賽事也沒有訓練 → 簡易，其他 → 完整（也寫進去，之後刪光也不會被當新使用者）。自動選的簡易版在「登入前本機 0 場、雲端載回賽事」時換成完整版（`maybeLeaveAutoSimple`）；使用者自己切過就清掉自動旗標 |
| 簡易版抽屜的常用欄位 | `SIMPLE_FIELD_PATHS`（基本 6、時間 3、成績 5、心得 1），經 `drawerFieldsHtml()`。「已填」計數用 `fieldHasValue()`，跟 `emptyRace()` 預設值一樣的不算 |
| 搜尋與篩選一律跨月份（v3.98.0） | 行事曆檢視下只要有搜尋字或篩選不是「全部」（`calendarResultsMode()`），就改畫 `calendarResultsHtml()`：即將到來／各年份／未定日期，不畫生涯數據與焦點卡。**不要**再讓搜尋只作用在當月——那會讓人以為資料不見。沒日期的賽事一定要有地方出現（`calendarUndatedHtml()`），新增表單的日期是選填的 |
| 同一場賽事重畫要保留區段與捲動（v3.98.0） | `renderDetail()` 用 `detailEl.dataset.raceId` 判斷是不是同一場；是的話換完 innerHTML **立刻**把 `details.section` 打開回去，再讀版面、最後補回 `scrollY`。從抽屜 change 觸發的完整重畫延到 `setTimeout(0)`，游標才已經移到下一格、可以放回去 |
| 賽事頁的網址與返回（v3.99.0） | 不要在各個入口自己 pushState（v4.1 起推、取代都經 `pushRoute()`／`replaceRoute()`，退一步經 `appHistoryBack()`）：`renderAll()` 一開頭 `syncRouteWithState()` 比對「狀態該有的網址」與現在的網址——清單→賽事、賽事→賽事用 push（先把目前這筆 replace 成帶 `scrollY`）；`#new`→賽事用 replace；離開賽事頁時，這筆是從清單推進來的就 `history.back()`，否則 replace。`popstate` 用 `applyRouteFromLocation()` 反推狀態，期間 `routeSyncPaused` 避免又推一筆。抽屜在 v4.1 起改走「返回鍵關最上面那一層」。捲動位置 App 自己管（`scrollRestoration='manual'`），回清單用 `restoreScrollY()`（手機頂列收合動畫跑完要再補一次） |
| 首頁分頁（v4.0） | `state.homeTab`（`races`／`career`）；v4.1 起生涯數據有網址 `#career`（`routeOfState()`、`isHomeRoute()`，`setHomeTab()` 會 `syncRouteWithState()`：切過去推一筆 `fromTab`，切回來是 `appHistoryBack()`）。`renderCalendar()` 開頭 `syncHomeChrome()` 同步分頁列、`body[data-home-tab]`、`is-first-run`、手機檢視切換鈕。生涯數據（`renderCareerSummary()`）**只**畫在 career 分頁，賽事分頁的月曆／獎牌牆／表格上面都不再有它。「訓練」分頁其實是 `#btn-training`，點了開訓練全螢幕頁、不切換 `homeTab` |
| 手機檢視與電腦檢視分開記（v4.0） | 手機（`isPhoneLayout()`＝≤640px）看 `state.phoneView`（`list` 預設／`calendar`／`grid`），電腦看 `state.viewMode`（`calendar`／`grid`／`table`），實際畫哪一種統一問 `currentCalendarView()`。清單是 `phoneListHtml()`：即將到來（`upcomingGroupRaces()`：有日期的由近到遠＋沒日期的計畫排最後，跟篩選鈕的 `isUpcomingRace` 數字一致）、最近 `PHONE_LIST_RECENT` 場、「看全部」（數字用 `isHistoryRace`，跟篩選鈕一致）、未定日期（`calendarUndatedHtml(races,inResults,skipPlans)`，清單與結果清單只列沒日期的過去賽事）。跨過 640px 由 `PHONE_LAYOUT_MQ` 的 change 重畫 |
| 下拉選單（v4.0 補強） | `positionActionMenuPanel()`：觸發按鈕帶 `data-menu-align="start"` 就靠左對齊（賽事頁的狀態章）；上下都放不下時設 `max-height` 在選單內捲動，重新對齊時保留選單自己的捲動位置。`data-keep-menu-open` 的列點了之後會重新對齊一次（字體變大、展開一組）。Esc 先收開著的選單。頭像選單長在頂列裡，所以 `#topbar` 的 z-index（45）要高過右下角的「＋」（41） |
| 賽事頁頁首（v4.0） | 狀態章是 `detailStatusMenuHtml()`（`#dh-status-menu`，六個狀態，走既有的 `lc-set-status`）；完賽／DNS／DNF 不畫狀態條，還沒比的畫、但 `noExceptionLinks`。封面照片的操作在「更多操作」（`coverMenuItemsHtml()`）；日期行是 `detailMetaLine()`（日期 ・ 地點） |
| 返回鍵關最上面那一層（v4.1） | 疊在上面的層（`BACK_LAYER_IDS` 列的彈窗、`.action-menu-panel`、`.badge-unbox-overlay`）由 MutationObserver 偵測打開，打開時推一筆「返回鍵防護」（網址不變、state 複製底下那一筆＋`backGuard:true`）；`popstate` 離開防護時關掉 `backLayerStack` 最上面那一層（`closeBackLayer()`，有自己關閉函式的列在 `BACK_LAYER_CLOSERS`，其他按 `[data-action^="close"]`）。**用 ✕／Esc 關掉時不要 `history.back()`**（非同步，同一個點擊裡接著換頁會把新網址退掉）：防護留著，之後返回離開它時發現沒東西就再退一格。程式要「退一步」一律用 `appHistoryBack()`（防護還在就 `go(-2)`）；`pushRoute()`／`replaceRoute()` 會處理防護的記號。只改 # 的跳轉 state 是 null，不算返回。新增全螢幕彈窗時把 id 加進 `BACK_LAYER_IDS` |
| 文字顏色與點擊範圍（v4.1） | 次要文字用 `--stone`（淺色 #676860、深色 #838A92，都 ≥4.5:1）；金色小字（PB 標章、「備戰釘選」、鞋款標籤）用 `--gold-ink`，`--gold` 只拿來當底色、線條、大數字。外觀要小、手指要點得到的控制項用透明 `::after` 撐到 44px（頭像、簡易版開關、狀態章、「暫時隱藏」）；放在 `overflow` 容器裡的（賽事頁導覽列）不能用 `::after`，直接加高 |
| 生涯圖表的字（v4.1） | 「歷年完賽場次」是 HTML 長條（`.yearly-chart`），「累積爬升趨勢」SVG 只畫線和面積（`preserveAspectRatio="none"`＋`non-scaling-stroke`），圓點與年份是 HTML 疊上去。**不要把文字放進會被拉伸的 SVG**：字會跟著縮放或壓扁。年份多時 `.is-dense` 改兩位數；趨勢圖的年份位置不平均（有比賽的季度才有點），`keep()` 依距離挑要標的年份（兩端一定標、窄螢幕隔 9%、寬螢幕 3.5%，第一個／最後一個標籤不是置中要算半個寬），沒挑到的加 `.is-minor`／`.is-minor-lg`；歷年長條超過 11 年手機上隔幾個標一個 |
| 範例資料的日期（v4.1） | `buildExampleRaces()` 裡寫的是以 2026-09-17 為今天排的日期，`shiftExampleRaceDates()` 依今天整組平移（阿里山永遠 10 天後），`createdAt` 這類不動，賽名年份跟著改。改範例內容時日期照舊寫在那組基準上就好 |
| 比完賽之後記錄成績（v4.2） | `raceNeedsResult()`＝已報名＋比賽日早於今天；`isAwaitingResult()` 再加「14 天內」（`RESULT_PROMPT_DAYS`）。首頁卡 `resultPromptHtml()` 取最近一場、扣掉這台裝置按過「之後再說」的（`result-prompt-later-v1`，最多記 50 筆），放在 `#focus-panel-slot` 的焦點卡前面；清單標籤 `resultTagHtml()`（14 天內）；賽事頁提示列 `resultBannerHtml()`（不限天數，取代四格）。**只問 `registered`**：抽籤中、考慮中的日期過了多半是沒抽中或沒去。記錄面板是抽屜 `recordResult`（`DRAWER_SECTIONS`），欄位用 `renderField()`＋`SECTION_POST` 的定義，所以照舊改完就存、時間驗證照舊；「儲存」只做 `quickSetRaceStatus(race,'completed')`，沒有另一條寫資料的路。首頁卡的 DNS／DNF 走 `setRaceStatusWithUndo()`（6 秒復原） |
| 打包模式（v4.2） | `equipmentViewMode`（`pack` 預設／`list` 編輯／`kanban` 佈署，記在記憶體、每次開網站從打包開始）、`packFilter`、`packDoneOpen`。`equipmentPackHtml()` 的每一列是 `button.pack-row[data-action="pack-toggle"]`，`data-index` 是在 `equipmentChecklist` 裡的位置（不是篩選後的位置）。「已打包 N 件」是 `<details>`：收起來的列還在 DOM 裡，量畫面上的列要用 `.pack-list > .pack-row`。`.pack-add-input` 的 Enter 要略過 `isComposing`（輸入法選字）。從四格、「下一場」卡的打包格（v4.2 是焦點卡圓環）進來一律經 `openRacePacking(id)`（重設成打包＋「還沒打包」） |
| 賽前四格與區段順序（v4.2） | `raceWeekTilesHtml()` 只在 `registered` 且還沒過比賽日。欄寬 `1fr .9fr 1fr 1.3fr`、≤380px 值縮到 14px、字級「大」在 ≤420px 排兩排兩格——這是用 360／375／390／414 × 小中大 × 中日英 × 最寬的值（12/12、A12345、11:50:00、日文空格子「＋ 作成」）量出來的，改欄寬或文字前先跑 `v42` 手機那兩項；全部打包好時勾勾放標籤上（`is-done`），值本身不加，兩位數才放得下；格子是 `open-drawer`＋`data-focus-path`，`detailEl` 的點擊處理在欄位**是空的**時才 focus（有值還搶焦點，手機會跳鍵盤蓋住畫面）。`renderDetail()` 把五個區段放進物件，依 `isDoneStatus`（completed／dns／dnf）決定順序；導覽列 `quickNavHtml({postFirst})` 跟著調。`simple` 與 `v42` 兩邊都鎖住順序 |
| 生涯數據可以點（v4.2） | `.yc-col`、熱力圖格子、「總完賽場次」「今年累計里程」都是 `<button>`，經 `openCareerSheet(kind,key)`（`year`／`month`／`all`）畫進 `#career-sheet`；統計一律 `completedRacesFor()`（只算已完賽，跟長條一致）。`#career-sheet` 登記在 `BACK_LAYER_IDS`／`BACK_LAYER_CLOSERS`／Esc 的 `modalIds`，返回鍵先關它。列表直接用清單的 `.cal-list-item`：點了先 `closeCareerSheet()` 再 `selectRace()`，網址從 `#career` 推一筆 `#race=`，返回回到 `#career`。PB 時間：`pointerdown` 記下按下的時間，`click` 的 `detail>0` 且按住超過 450ms 就不跳（那是想長按）；鍵盤的 click（`detail` 是 0）一律打開——v4.2 開發時抓到「上一次按住留下的時間讓鍵盤怎麼按都打不開」 |
| 「下一場」卡（v4.3） | `focusPanelHtml()`：`.focus-panel-compact`，上半部 `.nx-head`（`button.nx-main` 是 `focus-view-race`），下半部 `.nx-tiles` 三格用跟賽事頁四格同一組 `rwTileHtml()`／`rwPackTileHtml()`／`rwGoalTileHtml()`／`rwBibTileHtml()`。首頁卡的格子是 `data-action="focus-tile"`（先 `selectRace()` 再 `openDrawer()`，欄位是空的才 `focusDrawerFieldIfEmpty()`），賽事頁是 `open-drawer`（`detailEl` 接）。第三格 `focusThirdTileHtml()`：7 天內有軌跡、還沒抓過 → 「抓取預報」；`focusWeatherNow()` 有值 → 天氣（只有歷年平均自動帶進 `climateForecast.avgTempC` 的不算）；都沒有 → 號碼布。`renderFocusPanel()`：手機清單上有「比完了嗎？」就不放卡片（`currentCalendarView()==='list'`）。筆電一列從 768px 起（641–767 排兩欄每格只剩 73px）；字級「大」≤420px 排兩欄、第三格整列。改格子文字或欄寬先跑 `v43` 的 fit 三項。封面照頁首的漸層最上面 .58：`v43` 用「全白的照片」算每一行字的對比，調淡會被抓到 |
| 獎牌牆（v4.3） | `renderPhotoGrid()` 是全部已完賽、新到舊；`photoCardHtml()` 有封面照 → 照片卡，沒有 → `.is-medal`（`.medal-face` 的 `--medal`／`--medal-bg` 用 `sportColorVar()`／`sportBgVar()`；PB 加 `.is-pb`：金框、4px、`.medal-pb`——路跑本來就是金色，只換顏色分不出來）。最大的那行 `.medal-main`：距離 → 沒距離用成績 → 都沒有用年份，**不放運動別名稱**（日英放不進圓）；超過 6 個字加 `.is-long` 縮字。`.medal-disc` 的 `line-height:1.2` 不能拿掉：沿用 body 的 1.6，字級「大」時 PB 標記會超出圓（`v43` 量四個角都在圓裡） |
| 表格排序與各距離最佳（v4.3） | `tableSort`（記憶體）、`TABLE_SORT_FIRST_DIR`、`sortTableRaces()`（空值不論方向都在最後、同值新的在前）。照日期以外的欄位排時不分年份（`byDate`）。表格上面那行是整句的字典 `ui.tableSortBar`（`{a}` 欄位、`{b}` 方向、`{c}` 場數）——**不要拆成幾段拼**：英文要半形括號和「·」。場數用 `tableRaceCount()`（英文單數）。`BEST_DISTANCES`／`bestByDistance()`：跑步距離要 `isRunningSportType()`，全馬用 `isMarathonDistance()`——跟 `computeCareerStats()`、`marathonPbRace()`、`computeHallOfFameData()` 同一個判斷，v4.3 起只算跑步類（原本 42 公里的自行車賽會變成全馬 PB） |
| **第一次完整下載一定要分批** | `fullSyncRacesInPages()`：一次 5 場、每批存游標、可續傳；同處崩潰兩次改逐筆。一次抓全部（`fetchAll`）在 iPhone 會撐爆分頁，只留給「同步診斷」這種使用者主動按的功能 |
| 已登入就崩潰時的出口 | `?nosync=1`（本分頁不同步）、`?nosync=0` 恢復 |
| **雲端同步是增量的，不要改回整份** | `cloudKnown`（雲端每場的 updatedAt，存 IndexedDB `cloud-sync-state-v1`）。上傳只傳版本不同的（`upsertRaces`），打開網站只抓 `updatedAt > since－1天`（`fetchChangedSince`）。**`replaceAll` 已經不用**：它會先下載全部再整份上傳，iPhone 會崩潰 |
| **永久刪除一律走 `keepRaces()`** | 它會記下要從雲端刪的 id。直接寫 `state.races=state.races.filter(...)` 的話，雲端那份不會被刪、下次登入還會復活。雲端刪除絕不用「本機沒有」去推測 |
| **觸控裝置不可以有大面積合成效果** | `mix-blend-mode`、大半徑 `filter:blur`、`backdrop-filter` 在 iOS Safari 都要先把大片內容合成成一張圖，會撐爆分頁（「重複發生問題」）。一律放在 `@media (hover:hover) and (pointer:fine)` 或用 `@media (hover:none),(pointer:coarse)` 關掉。v3.88 全部列過一次 |
| iPhone 打不開時用安全模式找原因 | `?safe=fx`（關特效）→ `?safe=img`（關圖片）→ `?safe=all`，可與 `?nosw=1` 併用。存在 sessionStorage |
| canvas 要跟著縮放重畫 | 雷達圖是唯一的 canvas。`watchCanvasResolution()` 監聽像素比例與視窗大小，呼叫 `redrawThemeDependentCanvases()`。背板尺寸用 `Math.round(css×dpr)`。之後新增任何 canvas 都要掛進這個重畫流程 |
| **FIT 海拔要讀欄位 2 或 78** | 新款 Garmin 只寫 78（enhanced_altitude）。只讀 2 的話海拔剖面、GAP、爬升全空。真實檔案才發現——模擬檔都寫欄位 2 |
| 能拿到真實檔案就用真實檔案驗 | v3.86 用使用者的 Forerunner 945 檔案一次抓到三件模擬檔抓不到的事：海拔欄位、下水前幾分鐘水溫偏熱、心率來源。真實檔案含個人 GPS 軌跡，**不要放進公開 repo**；把學到的特徵寫進測試產生器 |
| 游泳水溫略過前 3 分鐘、心率來源看 device_info | 剛下水手錶帶著體溫。ANT+／120＝胸帶、內建／10＝手腕光學 |
| 多項運動雷達＝游泳、騎車、跑步疊圖 | `computeRaceRadarSeries()`；距離滿分依運動（`RADAR_LEG_FULL_KM`）；游泳不畫。繪製一律走 `radarDataForRace()`＋`drawRadarData()`，不要直接呼叫 `drawRaceRadar(computeRaceRadar())`。疊圖的數值要寫短，手機才放得下（有畫布文字邊界測試） |
| `multisport`、`radar` 群組都要單獨跑 | 每項都要產生並解析 FIT，各自接近 300 秒上限。雷達相關測試已拆到 `radar`；再加就再拆 |
| 游泳分段每 100 公尺、距離用手錶的 | `computeSwimSplitsFromPoints()` 優先用 record 欄位 5（`p.dist`）。中位數快於 50 秒／100m 視為 GPS 亂跳、整段不列（`leg.swimGpsRejected`）。推算的游泳段不算分段。雷達不納入游泳 |
| 多項運動的分段表與雷達一律依分段算 | `leg.splits`（匯入時每段各自算）；舊資料用 `legSplitGroups()` 依時間歸組、跨交界的略過。心率區間用 `hrZoneInfoForRace(hr,race,legSport)`，不要用整場的運動種類 |
| **不可以用正規表示式向後查找** | iOS Safari 16.4 以前不支援，整支程式直接語法錯誤、網站打不開。有靜態檢查 `no_regex_lookbehind_for_old_ios` |
| 準備週期／減量週數：建議值即時算、不寫進資料 | `effectivePrepWeeks()`／`effectiveTaperWeeks()`：使用者填的 > `TRAINING_PERIOD_TABLE` > 12 週。不要自動填 `taperStartDate`（徽章會自動成立） |
| 訓練頁「全部」只畫展開中的月份 | `trainingOpenYears`／`trainingOpenMonths`（記憶體，開頁與匯入後重置）。寫測試要點某一列前，先把那個月份展開 |
| 檔案拖放只有一個入口：全域的 window 監聽 | 不要在子元素自己接 `drop` 又 `stopPropagation()`——「放開以匯入檔案」畫面（z-index 500）會收不掉、把一切蓋住。要分情境就在全域 `drop` 裡判斷（例：訓練頁開著 → `startTrainingImport`）。捕獲階段另有一道保險重置 |
| 頂端列「＋ 新增賽事」下方的訓練鈕是往下掛的 | 桌機 `position:absolute` 掛在新增賽事下面、`.topbar-row1` 補 36px 底部留白。改回一般堆疊的話，其他控制項會對齊兩顆按鈕的中間而變低 |
| 測試批次不要塞太多群組 | 單一指令上限 300 秒；超時被砍會噴 Playwright EPIPE，看起來像錯誤其實不是。一批 2～4 組 |
| `showAppBanner()` 是共用的 | 更新、安裝提示、儲存空間警告都用它。要改其中一種的外觀就加 `kind`，不要改共用樣式 |
| 量「有沒有蓋到文字」要量字，不是量框 | `flex:1` 的 `<span>` 會撐滿整行。用 `document.createRange().selectNodeContents()` 量實際字的範圍 |
| `offline` 群組會起本機 HTTP 伺服器 | 用 `APP=/tmp/...` 做反例驗證時這組跑不起來，改用獨立 Playwright 腳本直接對反例檔跑同一個判斷式 |
| 訓練紀錄跟賽事完全分開 | 獨立陣列 `trainings`、儲存鍵 `trainings-v1`、雲端 `users/{uid}/trainings/{YYYY-MM}`。**絕對不要把訓練放進 `state.races`**——所有賽事統計都是靠「資料不在那裡」來隔離的，不是靠過濾 |
| 比賽當天的 FIT 不當訓練 | 賽事已經把距離算進鞋款，重複匯入會算兩次。`matchRaceForTraining()`：同日期＋距離差 20% 以內 |
| 匯入的鞋款里程動態加總 | `importedTrainingKmForShoe()`，不寫回 `shoe.trainingKm`（那個欄位是手動補登）。寫回的話刪除／換鞋要反向扣，容易錯 |
| 賽前訓練週期：週對齊比賽日、減量等整週結束 | 不用日曆週。還沒過完的那週不列入平均與減量 |
| `renderDetail()` 會收起所有區段 | 整頁重建、沒有記住展開狀態。局部更新優先（只換那張卡）；非整頁重畫不可時用 `renderDetailKeepOpen()` |
| 版面測試至少要測 360px | 390px 過了不代表 360px 過（很多 Android 是 360）。行事曆工具列在 360px＋大字級會換行（圖示按鈕整組換） |
| 新增 CSS 的 font-size 要乘 `--fs` | 字級切換靠 `calc(Npx*var(--fs,1))`。**之後新加的樣式也要這樣寫**，不然那一塊不會跟著縮放。例外：30px 以上的大數字、字級控制項本身 |
| manifest 的相對路徑是相對於 manifest 自己 | `icons/manifest.webmanifest` 裡寫 `"start_url":"."` 會解析成 `/Race-Day/icons/` → 安裝後的 PWA 一開就 404，但瀏覽器直接開完全正常。`start_url`／`scope`／`id` 一律寫絕對路徑 `/Race-Day/`。改完要**先移除已安裝的 App** 再重裝，舊安裝不會自動更新 start_url |
| 回饋表單只帶版本／裝置／畫面 | 公開收件匣，使用者按之前看不到會送什麼。絕不夾帶賽事資料，有測試鎖住 |
| 歷年平均跟比賽有沒有結束無關 | 那是地點×日期的多年平均，賽前最需要。不要綁 `raceIsHistorical()`。取樣＝往前 5 年 × 同月同日 ±3 天（`CLIMATE_AVG_YEARS`／`CLIMATE_AVG_WINDOW`），樣本數要顯示在畫面上 |
| 天氣自動查詢的前提是有 GPS 軌跡 | 需要座標。沒軌跡就查不了，但一定要在畫面上講出來，並保留手動填寫的路 |
| 從全螢幕圖層開的彈窗要拉 z-index | 生涯回顧是 210，一般 `.modal-overlay` 只有 50，不拉就被蓋住＝「按了沒反應」。驗收要測「看得到」「按得到」，不是只測「有沒有打開」 |
| 警示只染警示那一段 | 整行轉警示色會讓正常內容也看起來像出問題。`dashCardHtml` 的 `warnText` 獨立成一個 span |
| 摘要卡講內容不講數量 | 「住宿 4」對使用者沒有資訊量，他要的是哪一間、幾點。列最近一筆＋「+N」 |
| canvas 不能吃 HTML | `secToHMSDenoised()` 回傳帶 `<span>` 的字串，畫到 canvas 會顯示標籤原文。產圖一律用 `secToHMS()`。守門測試：攔 `fillText` 檢查沒有角括號 |
| 內容量會變的圖：量兩趟 | 生涯卡高度依區塊多寡而定。同一段排版程式跑兩次（measure/draw），不要各寫一份 |
| 性別排名 ≠ 分組名次 | 成績頁常常同時出現且數字不同（259/2251 vs 57/368），必須是兩個欄位。總排名的同義詞不可以收裸的「排名」，會把分組／性別的數字吃走 |
| 貼上內容提到已存在的賽事＝強證據 | 成績加 3 分。新增賽事的否決要加兩個條件（v3.68.0）：使用者已開著新增表單時不否決、日期不同視為不同屆。名稱是子字串比對，否則每年同一場都會被擋 |
| 計分制門檻要拿真實樣本校準 | 已經發生兩次「差一分所以完全沒反應」（v3.58 成績頁、v3.63 無排名成績頁）。加新的判斷類型時，一定要拿使用者實際會貼的內容跑分數，不要只看規則寫起來合不合理 |
| 成績頁是表格不是散文 | 心得的計分制（長度／句子／第一人稱）對成績表永遠差一點分數，會變成「完全沒反應」。表格類內容要自己的判斷規則，不要調鬆心得的門檻 |
| 貼上分流順序：成績 → 新增賽事 | 成績頁通常也有賽事名稱與日期，順序反了會變成「已經有這場卻跳新增表單」 |
| 運動別顏色有兩組變數 | `--sport-*` 是實色（色條、圓點），`--sport-bg-*` 是行事曆底圖（低透明度）。不用 `color-mix()`：Safari 16.2 以下不支援 |
| 行事曆名稱折兩行而不是加大字級了事 | 字放大會讓單行塞更少字、截斷更嚴重，跟「看清楚名稱」相反。`-webkit-line-clamp:2` |
| 距離是距離，不是運動種類 | 不把半馬／全馬做成 `sportType` 子項：`road_running` 被鞋子里程、氣候曲線、EPP、徽章大量依賴，拆開要全部跟著改，而距離本來就存在 `route.distanceKm`。改用距離快捷清單 |
| 貼上新增賽事不受「已有賽事」守門限制 | 清單空的時候正是最可能貼賽事資訊的時機；其他幾種貼上要填進某一場才需要那道守門 |
| 國家推論：地名清單優先於後綴規則 | 「福井縣若狹」是臺灣字寫的日本地名，只靠後綴會判錯。日文「区」≠ 中文「區」是可靠的判別依據。填入時沿用使用者既有的臺／台寫法，避免資料分叉 |
| Firestore 寫入一定要分批 | 單次請求 ≤11MB、單 batch ≤500 操作、單一文件 ≤1MB。全部塞一批會在封面照變多後整批失敗（全有全無）。走 `chunkRacesForSync()`；單場超標要跳過並回報，不要拖垮整批 |
| IG 貼文內文拿不到 | oEmbed 已無 token 需求、也沒被 CORS 擋，但回傳 HTML 不含 caption（只有 `View this post on Instagram`），`thumbnail_url` 也已移除。這條路實測過，不要再試 |
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
- **測試一律先設成完整版**（v3.97.0）：新裝置沒有資料會進簡易版，而大部分群組是「先開空白頁、再塞資料」。`Group.run` 與其他自建的 context 都加了 `PRESET_FULL_MODE_JS`；只有 `simple`／`simple_phone` 不加（`preset_full_mode = False`）。自己新增 context 時用 `full_mode_context()`
- **「畫面出來前」不能用 DOMContentLoaded 驗**：module 腳本會拖慢它，`init()` 可能已經跑完。`simple` 群組改用 MutationObserver 記錄 `#app` 剛被解析出來那一刻的 `data-mode`
- **沙盒裡 idb-keyval 的 CDN 連不到，`saveJson` 退回同步的 localStorage**：`await persist()` 之後的程式在同一個微任務就跑了，時序跟正式環境（IndexedDB，真正非同步）不一樣。v3.98 的「Tab 後游標消失」就是這樣才在測試裡重現；修的時候兩種時序都要成立
- **Playwright 的 `goto` 只改 `#` 是同一份文件的跳轉**，不會重新跑 `init()`；要測「直接開網址」得再 `reload()`（v3.99 的反例驗證抓到的）
- **分批平行跑測試時，`ux` 重新整理後的等待設 30 秒**：跟 `multisport`／`radar` 同時跑，Chromium 重新載入偶爾超過 15 秒，整組會被記成 GROUP_CRASHED（v4.0 遇到一次，單獨重跑通過）
- **headless Chromium 在 file:// 下重新整理，偶爾會整個 localStorage 不見**（v4.0 也一樣，http 下 8/8 穩定）：要測「重新整理之後」的事，開本機 http 伺服器（`v41` 的重新整理那一項、`offline` 群組的做法）
- **測試裡量顏色前先關掉過場**：`body` 換主題有 0.8 秒的底色過場，量到的是半途的顏色（`v41` 用 `*{transition:none!important}`）
- **賽事頁直接跳賽事頁，每一跳都是新的一頁**（v3.99 起）：測試連續 `selectRace()` 好幾場之後，`goBackFromDetail()` 一次只回到上一場，不是回首頁。要回首頁就一路退到 `state.selectedId` 是 null（`v42` 生涯數據那段開頭的寫法），不然點分頁時網址還是 `#race=`
- **收起來的 `<details>` 裡的元素還在 DOM**：`querySelectorAll` 會數到、高度是 0。量「畫面上看得到的列」要限定直屬的容器（`v42` 手機那項原本把收起來的「已打包」7 列也算進去）
- **測「按住」和「點一下」要用真的滑鼠**：`el.click()` 的 `detail` 是 0，跟鍵盤一樣，測不到按住多久。`page.mouse.down()`、等、`page.mouse.up()`
- **`d ? 加天數 : ''` 會把 0 天（今天）當成沒有日期**：`v42` 的反例驗證抓到「比賽當天不問」那一項原本是空測（今天的賽事根本沒有日期）。天數參數一律 `d!=null`
- **一項檢查在頁面裡拋例外，整組會當掉**：`page.evaluate` 丟出例外 → `GROUP_CRASHED`，後面的項目全部沒跑，反例驗證也看不出是哪一項抓到的。`v43` 用 `self.ev()` 包起來（例外＝這一項失敗、印出原因、後面照跑），新群組照這樣寫
- **歷年平均會自動寫進預報欄位**：打開有軌跡的賽事，背景查到的歷年平均會填進 `climateForecast.avgTempC`。拿 `climateForecast` 判斷「有沒有預報」要先排除這種情況（`focusWeatherNow()` 比對 `historicalAverageWeather.avgTempC`）
- **卡片做成 `<button>` 時一定要寫 `color`**：不寫就是瀏覽器預設的黑字，深色模式下看不到。獎牌牆的照片卡一直有這個問題，v4.3 每一場完賽都上牆才看出來（`v43` 的 wall_text_readable 量淺色、深色的對比）。新增按鈕式的卡片照這樣寫
- **641–767px 是筆電版面，但很窄**：直拿的平板、縮窄的視窗。兩欄排法最容易在這裡擠爆；版面測試除了 360／390 也量一個 700px（`v43` 的 tablet700）
- **選賽事可能跳出徽章解鎖動畫蓋住整頁**（`.badge-unbox-overlay`），測試要點頁面上的按鈕前先收掉
- **升級 xlsx / idb-keyval 時必須同時換 `integrity` 雜湊**，只改版號會被瀏覽器擋掉。作法：`npm pack <套件>@<版本>` 解開後 `openssl dgst -sha384 -binary <檔案> | openssl base64 -A`

---

## 待你回報

- 手機上獎牌牆與搜尋的實際流暢度。v3.26.0 把縮圖從 320px 提到 480px 換畫質，沙盒量到首屏 75ms→100ms，**實機是否還順要你回報**；太卡的話把 `COVER_THUMB_PX` 調回 420 或 360 就好，重產是自動的
