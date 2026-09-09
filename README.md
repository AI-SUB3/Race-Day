# 賽事紀錄網站 — 資料庫欄位架構設計

本設計提供兩套對應同一份資料模型的 schema，對應你提到的三種地端儲存方式：

| 檔案 | 適用儲存 | 設計邏輯 |
|---|---|---|
| `schema.sql` | PostgreSQL / SQLite | 正規化，拆成 17 張表，1:1 關係獨立成表、1:N 關係用外鍵 |
| `race-document.schema.json` | JSON 檔案 / MongoDB | 單一賽事一份文件，子資料以巢狀物件或陣列嵌入 |

兩者欄位名稱一一對應（`snake_case` vs `camelCase`），選一種儲存方式即可，未來若要換引擎，欄位對照表可直接照抄。

---

## 設計取捨

**為什麼關聯式版本要拆 17 張表，而不是全部塞進 `races` 一張表？**
你列的欄位裡，「賽前」（目標、裝備、補給、訓練計畫）和「賽後」（成績、體能數據、心得）是兩個時間點才會有值的資料。全塞一張表會讓「還沒比」的賽事有大量 NULL 欄位，也不利於之後個別擴充（例如成績要加上分組完賽率，不用動到主表）。拆表後，`races` 主表只保留「不管賽前賽後都存在」的基本資訊與路線資料。

**為什麼 JSON 版本反而全部嵌在一份文件裡？**
文件式資料庫的優勢是「一次讀取就拿到一場賽事的完整內容」，不需要 join。既然這些子資料的筆數都不多（住宿頂多幾筆、裝備清單頂多幾十筆），嵌入不會造成文件過度膨脹，也更符合前端「開一場賽事頁面」的讀取模式。

**時間長度一律存秒數（INTEGER `*Seconds`）**
`gunTime`、`chipTime`、`targetTime`、`cutoffTime` 都存成秒數，而非 `"03:45:00"` 字串。這樣可以直接做數學運算（配速換算、PB 比較、排序），顯示時再由前端格式化成 `HH:MM:SS`。

**倒數天數不落地儲存**
`countdownDays` 是 `raceDate` 的衍生值，每次查詢當下算最準，存起來反而要處理「每天要更新」的問題。SQL 範例見 `schema.sql` 文末。

**CP 與分段配速拆出獨立表/陣列（`checkpoints`、`race_splits` / `splits`）**
你原本的欄位是「CP / 補給站數量」這種彙總數字。考量到越野賽的關門時間通常是逐站分別限制，我把它展開成可逐點紀錄的結構——這樣「賽道分析」不只是一個數字，而是能真的畫出補給站分佈圖、標出哪一站最容易被關門。`race_splits` 則是分段配速，格式設計成可以直接對應你既有的 Strava 同步流程（[[recent-work]] 提到的 Python + Excel 匯出），未來要把訓練資料自動寫入這張表會比較順。

---

## 欄位分類對照（17 張表 / 對應 JSON 子物件）

| 分類 | SQL 表名 | JSON 子物件 | 關係 |
|---|---|---|---|
| 基本資訊與狀態、時間、地理路線 | `races` | 頂層欄位 + `schedule` / `location` / `route` | 主表 |
| CP / 補給站明細 | `checkpoints` | `checkpoints[]` | 1:N |
| 歷年氣候預測 | `race_climate_forecast` | `climateForecast` | 1:1 |
| 當日實際天氣 | `race_day_weather` | `raceDayWeather` | 1:1 |
| 報名費用 | `race_budget` | `budget` | 1:1 |
| 住宿 | `accommodations` | `accommodations[]` | 1:N |
| 交通 | `transportation` | `transportation[]` | 1:N |
| 隨行人員 | `companions` | `companions[]` | 1:N |
| 賽前目標 A/B/C | `race_goals` | `goals[]` | 1:N |
| 裝備清單 | `equipment_checklist` | `equipmentChecklist[]` | 1:N |
| 補給策略 | `nutrition_plan` | `nutritionPlan` | 1:1 |
| 訓練計畫 | `training_plan` | `trainingPlan` | 1:1 |
| 個人成績 | `race_results` | `results` | 1:1 |
| 體能數據 | `performance_data` | `performanceData` | 1:1 |
| 分段配速 | `race_splits` | `splits[]` | 1:N |
| 賽後心得與檢討 | `race_review` | `review` | 1:1 |
| 多媒體與連結 | `media_links` | `mediaLinks[]` | 1:N |

---

## Enum 值字典（兩套 schema 共用）

| 欄位 | 可選值 |
|---|---|
| `status` | `registered`(已報名) / `lottery_pending`(抽籤中) / `considering`(考慮中) / `completed`(已完賽) / `dns`(未起跑) / `dnf`(未完賽) |
| `sportType` | `road_running`(路跑) / `trail_running`(越野跑) / `ultra_marathon`(超馬) / `duathlon`(二鐵) / `triathlon`(三鐵) / `cycling`(自行車) / `obstacle_race`(斯巴達障礙賽) / `other` |
| `raceFormat` | `solo`(個人) / `pair`(雙人組) / `relay`(多人接力) / `loop`(繞圈賽) / `age_group`(分齡賽) |
| `paymentStatus` | `unpaid` / `paid` / `refunding` |
| `bookingStatus` | `considering` / `booked` / `paid` / `cancelled` |
| `condition`（天氣） | `sunny` / `cloudy` / `rainy` / `foggy` / `other` |
| `role`（隨行人員） | `partner` / `cheer_squad` / `emergency_contact` / `pacer` / `other` |
| `goalTier` | `A` / `B` / `C` |
| `category`（裝備） | `shoes` / `apparel` / `vest` / `headlamp` / `nutrition` / `mandatory_gear` / `other` |
| `linkType`（多媒體） | `official_site` / `brochure_pdf` / `gpx_track` / `photo_album` / `certificate` / `medal_photo` / `other` |

---

## JSON 版本範例文件（節錄）

```json
{
  "name": "2026 臺北馬拉松",
  "alias": "Taipei Marathon",
  "status": "registered",
  "sportType": "road_running",
  "raceFormat": "solo",
  "schedule": {
    "raceDate": "2026-12-20",
    "startTime": "06:30",
    "registrationCloseDate": "2026-09-30"
  },
  "location": { "venueName": "臺北市政府", "city": "臺北市", "country": "臺灣" },
  "route": {
    "distanceKm": 42.195,
    "elevationGainM": 180,
    "surface": { "pavedPct": 100, "trailPct": 0, "stairsPct": 0 },
    "cutoffTimeSeconds": 21600
  },
  "goals": [
    { "tier": "A", "targetTimeSeconds": 12600, "paceStrategy": "均速配速，前半程稍慢 5%" }
  ],
  "nutritionPlan": { "gelCount": 6, "electrolyteTabletCount": 2, "hydrationCapacityMl": 500 }
}
```

（完整欄位結構見 `race-document.schema.json`；關聯式版本的等效 DDL 見 `schema.sql`）

---

## 後續可擴充方向

- **多年份重複賽事比較**：若同一場賽事每年都參加（如年度臺北馬），可以加一個 `event_series`（賽事系列）主表，`races` 改成掛在 `event_series_id` 下，方便跨年比較 PB 趨勢。
- **抽籤機率追蹤**：`race_goals` 旁可加一張 `lottery_history` 記錄每年抽籤中籤率，作為隔年報名決策參考。
- **裝備清單可模板化**：`equipment_checklist` 可以先建一份「路跑標配」「越野標配」模板，新賽事建立時自動帶入預設項目，再依賽事調整。
