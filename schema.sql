-- ============================================================================
-- 賽事紀錄網站 資料庫結構（關聯式版本）
-- 目標引擎：PostgreSQL 14+（主要語法）
-- SQLite 相容性調整（見文末「SQLite 對應調整」說明）：
--   1. SERIAL           -> INTEGER PRIMARY KEY AUTOINCREMENT
--   2. TIMESTAMPTZ      -> TEXT（存 ISO8601，如 '2026-03-15T06:00:00+08:00'）
--   3. BOOLEAN           SQLite 原生支援 0/1，語法可直接沿用
--   4. CHECK 約束（取代 ENUM）兩邊皆可直接使用，故本檔一律用 CHECK 而非原生 ENUM
--
-- 設計原則：
--   - 所有「時間長度」欄位（完賽時間、目標時間、關門時間）一律存成 INTEGER 秒數，
--     方便排序 / 比較 / 計算配速，顯示時再由前端轉成 HH:MM:SS
--   - 倒數天數不落地儲存，查詢時用 race_date - CURRENT_DATE 動態計算（見文末範例）
--   - 1:1 關係（如成績、體能數據、賽後心得）拆成獨立表而非塞進 races 主表，
--     原因：這些欄位是「賽後才會有值」，拆表可避免主表大量 NULL，也方便未來擴充
--   - 1:N 關係（住宿、交通、裝備、CP、分段配速…）皆用 race_id 外鍵 + ON DELETE CASCADE
-- ============================================================================


-- ----------------------------------------------------------------------------
-- 1. races：賽事主表（基本資訊、時間、地理、路線）
-- ----------------------------------------------------------------------------
CREATE TABLE races (
    id                      SERIAL PRIMARY KEY,

    -- 基本資訊與狀態
    name                    TEXT NOT NULL,                      -- 賽事名稱，如「2026 臺北馬拉松」
    alias                   TEXT,                                -- 別名/英文名，如「Taipei Marathon」
    status                  TEXT NOT NULL DEFAULT 'considering'
        CHECK (status IN ('registered','lottery_pending','considering','completed','dns','dnf')),
        -- registered=已報名 / lottery_pending=抽籤中 / considering=考慮中
        -- completed=已完賽 / dns=未起跑 / dnf=未完賽
    sport_type              TEXT NOT NULL
        CHECK (sport_type IN ('road_running','trail_running','ultra_marathon',
                               'duathlon','triathlon','cycling','obstacle_race','other')),
        -- 路跑/越野跑/超馬/二鐵/三鐵/自行車/斯巴達障礙賽/其他
    race_format             TEXT DEFAULT 'solo'
        CHECK (race_format IN ('solo','pair','relay','loop','age_group')),
        -- 個人單人/雙人組/多人接力賽/繞圈賽/分齡賽

    -- 時間
    race_date               DATE NOT NULL,
    start_time              TIME,
    registration_open_date  DATE,
    registration_close_date DATE,
    lottery_result_date     DATE,

    -- 地理與地點
    venue_name               TEXT,                               -- 起終點名稱
    city                      TEXT,
    country                   TEXT,

    -- 路線數據
    distance_km              NUMERIC(6,2),
    elevation_gain_m         INTEGER,
    elevation_loss_m         INTEGER,
    min_altitude_m            INTEGER,
    max_altitude_m            INTEGER,
    start_altitude_m          INTEGER,

    -- 賽道分析與地形
    surface_paved_pct        NUMERIC(5,2),                       -- 柏油路 %
    surface_trail_pct        NUMERIC(5,2),                       -- 土路 %
    surface_stairs_pct       NUMERIC(5,2),                       -- 階梯 %
    checkpoint_count         INTEGER,                             -- CP/補給站數量（總覽用；細節見 checkpoints 表）
    cutoff_time_seconds      INTEGER,                             -- 全程關門時間（秒）
    terrain_notes             TEXT,                               -- 陡升段說明

    -- 多媒體與連結（賽事層級，非賽後才有）
    official_website_url     TEXT,
    brochure_pdf_url         TEXT,
    gpx_url                   TEXT,

    created_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_races_race_date ON races(race_date);
CREATE INDEX idx_races_status    ON races(status);
CREATE INDEX idx_races_sport     ON races(sport_type);


-- ----------------------------------------------------------------------------
-- 2. race_climate_forecast：歷年氣候預測（1:1，賽前參考用）
-- ----------------------------------------------------------------------------
CREATE TABLE race_climate_forecast (
    race_id               INTEGER PRIMARY KEY REFERENCES races(id) ON DELETE CASCADE,
    avg_temp_c            NUMERIC(4,1),
    avg_humidity_pct      NUMERIC(5,2),
    wind_direction         TEXT,
    wind_speed_kmh         NUMERIC(5,2),
    rain_probability_pct   NUMERIC(5,2)
);


-- ----------------------------------------------------------------------------
-- 3. race_day_weather：比賽當日實際天氣（1:1，完賽後填寫）
-- ----------------------------------------------------------------------------
CREATE TABLE race_day_weather (
    race_id                    INTEGER PRIMARY KEY REFERENCES races(id) ON DELETE CASCADE,
    actual_feels_like_temp_c   NUMERIC(4,1),
    condition                   TEXT CHECK (condition IN ('sunny','cloudy','rainy','foggy','other')),
        -- 晴/陰/雨/霧/其他
    actual_humidity_pct         NUMERIC(5,2),
    notes                        TEXT
);


-- ----------------------------------------------------------------------------
-- 4. race_budget：報名費用與繳款狀態（1:1）
-- ----------------------------------------------------------------------------
CREATE TABLE race_budget (
    race_id             INTEGER PRIMARY KEY REFERENCES races(id) ON DELETE CASCADE,
    registration_fee    NUMERIC(10,2),
    currency             TEXT DEFAULT 'TWD',
    payment_status       TEXT DEFAULT 'unpaid'
        CHECK (payment_status IN ('unpaid','paid','refunding')),
        -- 未繳費/已繳清/退款中
    chip_deposit         NUMERIC(10,2)
);


-- ----------------------------------------------------------------------------
-- 5. accommodations：住宿資訊（1:N，可能不只一間飯店）
-- ----------------------------------------------------------------------------
CREATE TABLE accommodations (
    id                       SERIAL PRIMARY KEY,
    race_id                  INTEGER NOT NULL REFERENCES races(id) ON DELETE CASCADE,
    hotel_name                TEXT,
    address                    TEXT,
    check_in_datetime          TIMESTAMPTZ,
    check_out_datetime         TIMESTAMPTZ,
    distance_to_start_km       NUMERIC(5,2),
    booking_status              TEXT DEFAULT 'considering'
        CHECK (booking_status IN ('considering','booked','paid','cancelled')),
    cost                         NUMERIC(10,2),
    notes                        TEXT
);
CREATE INDEX idx_accommodations_race ON accommodations(race_id);


-- ----------------------------------------------------------------------------
-- 6. transportation：交通規劃（1:N，去程/回程各一筆或多筆）
-- ----------------------------------------------------------------------------
CREATE TABLE transportation (
    id                  SERIAL PRIMARY KEY,
    race_id             INTEGER NOT NULL REFERENCES races(id) ON DELETE CASCADE,
    direction            TEXT NOT NULL CHECK (direction IN ('outbound','return')),  -- 去程/回程
    mode                  TEXT CHECK (mode IN ('hsr','shuttle','self_drive','flight','other')),
        -- 高鐵/接駁車/自駕/飛機/其他
    departure_time         TIMESTAMPTZ,
    pickup_location         TEXT,
    notes                    TEXT
);
CREATE INDEX idx_transportation_race ON transportation(race_id);


-- ----------------------------------------------------------------------------
-- 7. companions：隨行人員（1:N）
-- ----------------------------------------------------------------------------
CREATE TABLE companions (
    id             SERIAL PRIMARY KEY,
    race_id        INTEGER NOT NULL REFERENCES races(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    role             TEXT CHECK (role IN ('partner','cheer_squad','emergency_contact','pacer','other')),
        -- 同行夥伴/加油團/緊急聯絡人/配速員/其他
    contact_info     TEXT,
    notes            TEXT
);
CREATE INDEX idx_companions_race ON companions(race_id);


-- ----------------------------------------------------------------------------
-- 8. race_goals：賽前目標（1:N，A/B/C 三個目標各一筆）
-- ----------------------------------------------------------------------------
CREATE TABLE race_goals (
    id                  SERIAL PRIMARY KEY,
    race_id             INTEGER NOT NULL REFERENCES races(id) ON DELETE CASCADE,
    goal_tier            TEXT NOT NULL CHECK (goal_tier IN ('A','B','C')),
    target_time_seconds   INTEGER,
    pace_strategy          TEXT,
    UNIQUE (race_id, goal_tier)
);


-- ----------------------------------------------------------------------------
-- 9. equipment_checklist：裝備清單（1:N）
-- ----------------------------------------------------------------------------
CREATE TABLE equipment_checklist (
    id             SERIAL PRIMARY KEY,
    race_id        INTEGER NOT NULL REFERENCES races(id) ON DELETE CASCADE,
    item_name       TEXT NOT NULL,
    category         TEXT CHECK (category IN ('shoes','apparel','vest','headlamp',
                                                'nutrition','mandatory_gear','other')),
        -- 跑鞋/跑衣/背心/頭燈/補給品/強制裝備/其他
    is_mandatory      BOOLEAN NOT NULL DEFAULT FALSE,   -- 是否為強制裝備檢查表項目
    is_packed          BOOLEAN NOT NULL DEFAULT FALSE,   -- 是否已打包
    notes               TEXT
);
CREATE INDEX idx_equipment_race ON equipment_checklist(race_id);


-- ----------------------------------------------------------------------------
-- 10. nutrition_plan：補給策略（1:1）
-- ----------------------------------------------------------------------------
CREATE TABLE nutrition_plan (
    race_id                    INTEGER PRIMARY KEY REFERENCES races(id) ON DELETE CASCADE,
    gel_count                   INTEGER,        -- 能量膠數量
    electrolyte_tablet_count     INTEGER,        -- 電解質/鹽錠數量
    hydration_capacity_ml        INTEGER,        -- 水袋容量預估
    notes                         TEXT
);


-- ----------------------------------------------------------------------------
-- 11. checkpoints：CP / 補給站明細（1:N，選配進階表 —— 讓「CP數量」可展開為逐點紀錄）
-- ----------------------------------------------------------------------------
CREATE TABLE checkpoints (
    id                    SERIAL PRIMARY KEY,
    race_id               INTEGER NOT NULL REFERENCES races(id) ON DELETE CASCADE,
    cp_index               INTEGER NOT NULL,           -- 第幾個 CP（順序）
    name                    TEXT,
    distance_km             NUMERIC(6,2),
    cutoff_time_seconds      INTEGER,                   -- 該 CP 關門時間（可為相對起跑的秒數）
    has_water                BOOLEAN DEFAULT TRUE,
    has_food                 BOOLEAN DEFAULT TRUE,
    has_drop_bag              BOOLEAN DEFAULT FALSE,
    elevation_m               INTEGER,
    notes                      TEXT,
    UNIQUE (race_id, cp_index)
);
CREATE INDEX idx_checkpoints_race ON checkpoints(race_id);


-- ----------------------------------------------------------------------------
-- 12. training_plan：訓練計畫（1:1，賽前準備 —— 你提到但清單未列細項，此為建議欄位）
-- ----------------------------------------------------------------------------
CREATE TABLE training_plan (
    race_id                     INTEGER PRIMARY KEY REFERENCES races(id) ON DELETE CASCADE,
    plan_start_date              DATE,
    plan_end_date                 DATE,
    taper_start_date               DATE,               -- 減量期開始日
    weekly_mileage_target_km        NUMERIC(6,2),
    key_workout_notes                TEXT,             -- 關鍵課表備註（間歇、長跑、爬升訓練等）
    external_plan_url                 TEXT,             -- 若使用外部訓練計畫工具/文件的連結
    notes                              TEXT
);


-- ----------------------------------------------------------------------------
-- 13. race_results：個人成績 / PB（1:1，完賽後填寫）
-- ----------------------------------------------------------------------------
CREATE TABLE race_results (
    race_id                    INTEGER PRIMARY KEY REFERENCES races(id) ON DELETE CASCADE,
    gun_time_seconds            INTEGER,        -- 大會時間
    chip_time_seconds            INTEGER,        -- 晶片時間
    overall_rank                  INTEGER,
    overall_participants           INTEGER,
    age_group_rank                  INTEGER,
    age_group_participants           INTEGER,
    is_pb                              BOOLEAN DEFAULT FALSE
);


-- ----------------------------------------------------------------------------
-- 14. performance_data：體能數據（1:1，可由 Strava/COROS 匯入）
-- ----------------------------------------------------------------------------
CREATE TABLE performance_data (
    race_id             INTEGER PRIMARY KEY REFERENCES races(id) ON DELETE CASCADE,
    avg_hr               INTEGER,
    max_hr                INTEGER,
    avg_cadence            INTEGER,
    avg_power_watts         INTEGER,
    data_source              TEXT,   -- 如 'strava' / 'coros_manual'，方便標示資料來源
    notes                     TEXT
);


-- ----------------------------------------------------------------------------
-- 15. race_splits：分段配速（1:N，可由既有 Strava 同步流程直接匯入）
-- ----------------------------------------------------------------------------
CREATE TABLE race_splits (
    id                       SERIAL PRIMARY KEY,
    race_id                  INTEGER NOT NULL REFERENCES races(id) ON DELETE CASCADE,
    split_index                INTEGER NOT NULL,       -- 第幾公里/第幾段
    distance_km                 NUMERIC(6,2),
    split_time_seconds            INTEGER,
    avg_hr                          INTEGER,
    avg_pace_seconds_per_km          INTEGER,
    elevation_gain_m                  INTEGER,
    notes                               TEXT,
    UNIQUE (race_id, split_index)
);
CREATE INDEX idx_splits_race ON race_splits(race_id);


-- ----------------------------------------------------------------------------
-- 16. race_review：賽後心得與檢討（1:1）
-- ----------------------------------------------------------------------------
CREATE TABLE race_review (
    race_id                 INTEGER PRIMARY KEY REFERENCES races(id) ON DELETE CASCADE,
    hit_the_wall_notes        TEXT,   -- 撞牆期紀錄
    course_review               TEXT,   -- 路線心得
    pros                          TEXT,   -- 優點評價
    cons                            TEXT,   -- 缺點評價
    lessons_learned                   TEXT   -- 檢討筆記
);


-- ----------------------------------------------------------------------------
-- 17. media_links：多媒體與連結（1:N，賽後補充的相簿/證書等）
-- ----------------------------------------------------------------------------
CREATE TABLE media_links (
    id             SERIAL PRIMARY KEY,
    race_id        INTEGER NOT NULL REFERENCES races(id) ON DELETE CASCADE,
    link_type       TEXT CHECK (link_type IN ('official_site','brochure_pdf','gpx_track',
                                                'photo_album','certificate','medal_photo','other')),
    url              TEXT NOT NULL,
    notes             TEXT
);
CREATE INDEX idx_media_race ON media_links(race_id);


-- ============================================================================
-- 查詢範例
-- ============================================================================

-- 倒數天數（動態計算，不落地儲存）：
--   PostgreSQL: SELECT id, name, race_date, (race_date - CURRENT_DATE) AS countdown_days FROM races;
--   SQLite:     SELECT id, name, race_date, julianday(race_date) - julianday('now') AS countdown_days FROM races;

-- 賽事總覽（含成績與體能數據 join）：
-- SELECT r.name, r.race_date, r.status, res.chip_time_seconds, p.avg_hr
-- FROM races r
-- LEFT JOIN race_results res ON res.race_id = r.id
-- LEFT JOIN performance_data p ON p.race_id = r.id
-- ORDER BY r.race_date DESC;


-- ============================================================================
-- SQLite 對應調整（若改用 SQLite，將本檔做以下替換即可）
-- ============================================================================
-- 1. 所有 `SERIAL PRIMARY KEY`        -> `INTEGER PRIMARY KEY AUTOINCREMENT`
-- 2. 所有 `TIMESTAMPTZ`               -> `TEXT`（存 ISO8601 字串，如 datetime('now')）
-- 3. `now()`                          -> `datetime('now')` 或 `CURRENT_TIMESTAMP`
-- 4. `BOOLEAN` / `CHECK (... IN (...))` / `UNIQUE` / `INDEX`：SQLite 全部原生支援，無需更動
-- 5. `NUMERIC(p,s)` 在 SQLite 中無強制精度（動態型別），可直接沿用不影響功能
