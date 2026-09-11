# 賽事紀錄（Race Day）

一個從報名到終點的個人賽事紀錄網站。純前端、單一 `index.html`，部署在 GitHub Pages，不需要自架後端伺服器。

**線上網址**：https://ai-sub3.github.io/Race-Day/
**版本**：v1.0.0（[CHANGELOG.md](./CHANGELOG.md)）
**詳細操作說明**：[USAGE.md](./USAGE.md)

## 這是什麼

給路跑／越野跑／三鐵愛好者用的個人賽事管理工具，用行事曆管理賽事的整個生命週期——從考慮報名、抽籤、備賽，到完賽後的成績與檢討，取代散落在 Excel、記事本、聊天記錄裡的資料。

## 主要功能

- **行事曆主畫面**：年/月導覽，手機自動切換成清單檢視；雙層篩選（全部／即將到來／歷史紀錄）＋搜尋；生涯數據總覽
- **完整賽事欄位**：基本資訊、地理路線（含海拔變化圖）、氣象、預算行程、裝備補給、賽後成績與分析——完整欄位設計見 [`race-document.schema.json`](./race-document.schema.json)
- **系列賽事比較**：同一場賽事跨年比較 PB 趨勢
- **裝備清單範本化**：內建路跑／越野／三鐵標配範本，可自訂另存
- **配速試算與手環產生器**：依目標時間與策略算出分段配速，可下載成圖片
- **鞋款里程追蹤**、**分段掉速分析**、**補給時程規劃（計畫 vs 實際）**
- **資料匯入**：Excel（自己的賽事規劃表）、GPX/TCX（Garmin／COROS／Strava 運動紀錄，自動抓距離/爬升/心率/分段/海拔）、貼上 JSON 快速填入（給 AI 讀完賽事網站/簡章/證書後使用）
- **行事曆提醒**：匯出 `.ics` 日曆檔（含倒數一個月／一週提醒），交給手機原生行事曆處理通知
- **推播通知（選用，需額外部署）**：Firebase Cloud Messaging + Cloud Functions 排程，賽事倒數一個月／一週直接推送到手機，見 [USAGE.md](./USAGE.md#5a-推播通知選用需要額外部署)
- **成績分享圖**：一鍵產生可下載的賽事成績卡片
- **多語系**：繁體中文／日本語／English，右上角可切換；使用者自行輸入的資料不受影響，維持原文
- **深色模式**、**PWA 加入主畫面**（含自訂圖示）
- **Firebase 雲端同步（選用）**：Google 登入後跨裝置同步，本機儲存永遠是主要資料來源，未設定完全不影響使用

## 技術架構

- 純靜態網頁：一個 `index.html`，內嵌 CSS 與 JavaScript，無建置流程、無框架
- 儲存：`localStorage`（獨立架站時）或 Claude 內建 artifact 儲存（預覽環境），Firebase Firestore 為選用的雲端同步層
- 外部函式庫皆透過 CDN 載入：SheetJS（Excel 解析）、Firebase JS SDK（選用）
- GPX/TCX 解析、海拔剖面、配速計算、分享圖／配速手環產生（Canvas）皆為純前端運算，資料不會上傳到任何第三方伺服器

## 部署方式（GitHub Pages）

1. Fork 或下載本 repo
2. 上傳 `index.html` 到你的 repo 根目錄（檔名須為 `index.html`）
3. repo 設定 → Pages → Source 選 `Deploy from a branch` → Branch 選 `main` / `/(root)`
4. 約 1 分鐘後即可在 `https://<你的帳號>.github.io/<repo 名稱>/` 存取

## 啟用雲端同步（選用）

預設完全不需要 Firebase 也能正常使用（資料存在瀏覽器本機）。若要跨裝置同步，需要：

1. 到 Firebase Console（console.firebase.google.com）建立專案，啟用 Authentication（Google 登入）與 Firestore Database
2. Firestore 安全性規則設定為僅允許使用者存取自己 UID 底下的資料：
   ```
   rules_version = '2';
   service cloud.firestore {
     match /databases/{database}/documents {
       match /users/{uid}/races/{raceId} {
         allow read, write: if request.auth != null && request.auth.uid == uid;
       }
     }
   }
   ```
3. 在 Firebase Console 註冊一個網頁應用程式，取得 `firebaseConfig`
4. 打開 `index.html`，搜尋 `YOUR_API_KEY`，把整組 `firebaseConfig` 換成你的設定值

`apiKey` 等設定值會出現在公開原始碼中，這是 Firebase 的正常設計（安全性來自 Firestore 規則與 Authorized Domains，不是靠隱藏設定值），GitHub 的 Secret Scanning 若跳出提示可放心標記為已處理。詳細步驟見 [USAGE.md](./USAGE.md#5-雲端同步選用)。

## 資料結構

賽事資料以巢狀 JSON 文件儲存，一筆賽事一份文件，欄位設計文件：

- [`race-document.schema.json`](./race-document.schema.json)：JSON Schema（對應本 app 實際使用的資料結構，也是 Firestore 文件的結構）
- [`schema.sql`](./schema.sql)：對應的關聯式資料庫版本（PostgreSQL／SQLite），供未來若改用其他後端參考

## 版本紀錄

見 [CHANGELOG.md](./CHANGELOG.md)。
