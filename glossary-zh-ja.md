# 中日名詞對照表（賽事紀錄 App）

此檔案由 `index.html` 裡的翻譯字典自動整理產生，供快速查閱、翻譯校對或未來新增語言時參考。

**維護方式**：真正的翻譯內容以 `index.html` 裡的 `JA` / `EN` 字典為準；這份對照表是衍生檔案，字典異動後重新整理即可，不用手動同步兩處。

## 賽事欄位 (Race Data Fields)

| 欄位 Key | 繁體中文 | 日本語 |
|---|---|---|
| `field.accommodations.address` | 地址 | 住所 |
| `field.accommodations.bookingStatus` | 訂房狀態 | 予約状況 |
| `field.accommodations.checkIn` | 入住時間 | チェックイン |
| `field.accommodations.checkOut` | 退房時間 | チェックアウト |
| `field.accommodations.cost` | 費用 | 費用 |
| `field.accommodations.distanceToStartKm` | 距起點距離 | スタート地点までの距離 |
| `field.accommodations.hotelName` | 飯店名稱 | 宿泊先名 |
| `field.accommodations.notes` | 備註 | 備考 |
| `field.basic.alias` | 別名 / 英文名稱 | 別名／英語名 |
| `field.basic.location.city` | 縣市 | 都市／県 |
| `field.basic.location.country` | 國家 | 国 |
| `field.basic.location.venueName` | 起終點名稱 | スタート／ゴール地点 |
| `field.basic.lottery.applicants` | 抽籤申請人數 | 抽選応募者数 |
| `field.basic.lottery.wasSelected` | 本次是否抽中 | 今回当選したか |
| `field.basic.lottery.winRatePct` | 中籤率 | 当選率 |
| `field.basic.lottery.winners` | 抽籤名額 / 中籤人數 | 抽選当選枠／当選者数 |
| `field.basic.name` | 賽事名稱 | 大会名 |
| `field.basic.raceFormat` | 競賽形式 | 形式 |
| `field.basic.schedule.lotteryResultDate` | 抽籤結果公佈日 | 抽選結果発表日 |
| `field.basic.schedule.raceDate` | 比賽日期 | レース日 |
| `field.basic.schedule.registrationCloseDate` | 報名截止日期 | エントリー締切日 |
| `field.basic.schedule.registrationOpenDate` | 報名開始日期 | エントリー開始日 |
| `field.basic.schedule.startTime` | 起跑時間 | スタート時刻 |
| `field.basic.series` | 賽事系列（跨年比較用，同系列請填一致名稱） | シリーズ名（年別比較用、同じシリーズは同じ名前で） |
| `field.basic.sportType` | 主要運動種類 | 主な種目 |
| `field.basic.status` | 狀態 | ステータス |
| `field.checkpoints.cutoffTimeSeconds` | 關門時間 | 関門時刻 |
| `field.checkpoints.distanceKm` | 距離 | 距離 |
| `field.checkpoints.elevationM` | 海拔 | 標高 |
| `field.checkpoints.hasDropBag` | 可寄放裝備 | ドロップバッグ可 |
| `field.checkpoints.hasFood` | 提供食物 | 給食あり |
| `field.checkpoints.hasWater` | 提供飲水 | 給水あり |
| `field.checkpoints.name` | 名稱 | 名称 |
| `field.checkpoints.notes` | 備註 | 備考 |
| `field.companions.contactInfo` | 聯絡方式 | 連絡先 |
| `field.companions.name` | 姓名 | 氏名 |
| `field.companions.notes` | 備註 | 備考 |
| `field.companions.role` | 角色 | 役割 |
| `field.equipmentChecklist.category` | 分類 | カテゴリー |
| `field.equipmentChecklist.isMandatory` | 強制裝備 | 必携装備 |
| `field.equipmentChecklist.isPacked` | 已打包 | 準備済み |
| `field.equipmentChecklist.itemName` | 項目名稱 | アイテム名 |
| `field.equipmentChecklist.notes` | 備註 | 備考 |
| `field.logistics.budget.chipDeposit` | 晶片押金 | 計測チップ保証金 |
| `field.logistics.budget.currency` | 幣別 | 通貨 |
| `field.logistics.budget.paymentStatus` | 繳費狀態 | 支払い状況 |
| `field.logistics.budget.registrationFee` | 報名費用 | エントリー費 |
| `field.mediaLinks.notes` | 備註 | 備考 |
| `field.mediaLinks.type` | 類型 | 種類 |
| `field.mediaLinks.url` | 連結 | リンク |
| `field.nutritionSchedule.consumed` | 賽後：已補給 | レース後：摂取済み |
| `field.nutritionSchedule.distanceKm` | 距離／CP | 距離／CP |
| `field.nutritionSchedule.item` | 補給項目 | 補給内容 |
| `field.nutritionSchedule.notes` | 備註 | 備考 |
| `field.nutritionSchedule.plannedAmount` | 預計份量 | 予定量 |
| `field.post.performanceData.avgCadence` | 平均步頻 | 平均ケイデンス |
| `field.post.performanceData.avgHr` | 平均心率 | 平均心拍数 |
| `field.post.performanceData.avgPowerWatts` | 平均功率 | 平均パワー |
| `field.post.performanceData.dataSource` | 資料來源 | データ元 |
| `field.post.performanceData.maxHr` | 最大心率 | 最大心拍数 |
| `field.post.results.ageGroupParticipants` | 分組人數 | 年代別エントリー数 |
| `field.post.results.ageGroupRank` | 分組名次 | 年代別順位 |
| `field.post.results.chipTimeSeconds` | 晶片時間 (Chip Time) | ネットタイム（Chip Time） |
| `field.post.results.firstHalfSeconds` | 前半程時間 | 前半タイム |
| `field.post.results.gunTimeSeconds` | 大會時間 (Gun Time) | グロスタイム（Gun Time） |
| `field.post.results.isPb` | 個人最佳 (PB) | 自己ベスト (PB) |
| `field.post.results.overallParticipants` | 總參賽人數 | 総エントリー数 |
| `field.post.results.overallRank` | 總排名次 | 総合順位 |
| `field.post.results.secondHalfSeconds` | 後半程時間 | 後半タイム |
| `field.post.review.cons` | 缺點評價 | 改善点 |
| `field.post.review.courseReview` | 路線心得 | コースの感想 |
| `field.post.review.hitTheWallNotes` | 撞牆期紀錄 | 壁にぶつかった記録 |
| `field.post.review.lessonsLearned` | 檢討筆記 | 振り返りメモ |
| `field.post.review.pros` | 優點評價 | 良かった点 |
| `field.prep.nutritionPlan.electrolyteTabletCount` | 電解質 / 鹽錠數量 | 塩分タブレット数 |
| `field.prep.nutritionPlan.gelCount` | 能量膠數量 | エナジージェル数 |
| `field.prep.nutritionPlan.hydrationCapacityMl` | 水袋容量預估 | 水分携行量（想定） |
| `field.prep.nutritionPlan.notes` | 補給備註 | 補給メモ |
| `field.prep.trainingPlan.externalPlanUrl` | 外部訓練計畫連結 | 外部練習計画リンク |
| `field.prep.trainingPlan.keyWorkoutNotes` | 關鍵課表備註 | 重要練習メモ |
| `field.prep.trainingPlan.notes` | 訓練備註 | 練習メモ |
| `field.prep.trainingPlan.planEndDate` | 訓練計畫結束日 | 練習計画終了日 |
| `field.prep.trainingPlan.planStartDate` | 訓練計畫開始日 | 練習計画開始日 |
| `field.prep.trainingPlan.taperStartDate` | 減量期開始日 | テーパリング開始日 |
| `field.prep.trainingPlan.weeklyMileageTargetKm` | 週跑量目標 | 週間走行距離目標 |
| `field.route.route.checkpointCount` | CP / 補給站數量 | CP／エイド数 |
| `field.route.route.cutoffTimeSeconds` | 全程關門時間 | 制限時間 |
| `field.route.route.distanceKm` | 總距離 | 総距離 |
| `field.route.route.elevationGainM` | 總爬升 | 累積標高（上り） |
| `field.route.route.elevationLossM` | 總下降 | 累積標高（下り） |
| `field.route.route.itraPoints` | ITRA / UTMB 點數（官方公告值，非自動計算） | ITRA／UTMBポイント（公式発表値、自動計算ではありません） |
| `field.route.route.maxAltitudeM` | 最高海拔 | 最高標高 |
| `field.route.route.minAltitudeM` | 最低海拔 | 最低標高 |
| `field.route.route.startAltitudeM` | 起點海拔 | スタート標高 |
| `field.route.route.surface.pavedPct` | 柏油路比例 | 舗装路の割合 |
| `field.route.route.surface.stairsPct` | 階梯比例 | 階段の割合 |
| `field.route.route.surface.trailPct` | 土路比例 | 未舗装路の割合 |
| `field.route.route.terrainNotes` | 賽道陡升段說明 | コース・急登に関する備考 |
| `field.splits.avgHr` | 平均心率 | 平均心拍数 |
| `field.splits.avgPaceSecPerKm` | 平均配速 | 平均ペース |
| `field.splits.distanceKm` | 距離 | 距離 |
| `field.splits.elevationGainM` | 爬升 | 上り |
| `field.splits.notes` | 備註 | 備考 |
| `field.splits.splitTimeSeconds` | 分段時間 | スプリットタイム |
| `field.transportation.departureTime` | 發車 / 出發時間 | 出発時刻 |
| `field.transportation.direction` | 方向 | 往復 |
| `field.transportation.mode` | 交通工具 | 交通手段 |
| `field.transportation.notes` | 備註 | 備考 |
| `field.transportation.pickupLocation` | 接駁點位置 | 集合場所 |
| `field.weather.climateForecast.avgHumidityPct` | 歷年平均濕度 | 例年の平均湿度 |
| `field.weather.climateForecast.avgTempC` | 歷年平均氣溫 | 例年の平均気温 |
| `field.weather.climateForecast.rainProbabilityPct` | 降雨機率 | 降水確率 |
| `field.weather.climateForecast.windDirection` | 風向 | 風向き |
| `field.weather.climateForecast.windSpeedKmh` | 風速 | 風速 |
| `field.weather.raceDayWeather.condition` | 當日氣候狀況 | 当日の天候 |
| `field.weather.raceDayWeather.feelsLikeTempC` | 實際體感溫度 | 体感温度（実績） |
| `field.weather.raceDayWeather.humidityPct` | 當日濕度 | 当日の湿度 |
| `field.weather.raceDayWeather.notes` | 天氣備註 | 天候メモ |
## 清單標題 (Repeatable List Titles)

| 欄位 Key | 繁體中文 | 日本語 |
|---|---|---|
| `list.accommodations` | 住宿 | 宿泊 |
| `list.checkpoints` | CP / 補給站明細 | CP／エイドステーション |
| `list.companions` | 隨行人員 | 同行者 |
| `list.equipmentChecklist` | 裝備清單 | 装備リスト |
| `list.mediaLinks` | 多媒體與連結 | 関連リンク |
| `list.nutritionSchedule` | 補給時程規劃 | 補給計画 |
| `list.splits` | 分段配速 | スプリット |
| `list.transportation` | 交通 | 交通 |
## 選項清單 (Dropdown Options)

| 欄位 Key | 繁體中文 | 日本語 |
|---|---|---|
| `opt.booking.booked` | 已預訂 | 予約済み |
| `opt.booking.cancelled` | 已取消 | キャンセル |
| `opt.booking.considering` | 考慮中 | 検討中 |
| `opt.booking.paid` | 已付款 | 支払済み |
| `opt.direction.outbound` | 去程 | 往路 |
| `opt.direction.return` | 回程 | 復路 |
| `opt.equipcat.apparel` | 服裝 | ウェア |
| `opt.equipcat.headlamp` | 頭燈 | ヘッドライト |
| `opt.equipcat.mandatory_gear` | 強制裝備 | 必携装備 |
| `opt.equipcat.nutrition` | 補給品 | 補給食 |
| `opt.equipcat.other` | 其他 | その他 |
| `opt.equipcat.shoes` | 跑鞋/戰靴 | シューズ |
| `opt.equipcat.vest` | 背心 | ベスト |
| `opt.format.age_group` | 分齡賽 | 年代別 |
| `opt.format.loop` | 繞圈賽 | 周回 |
| `opt.format.pair` | 雙人組 | ペア |
| `opt.format.relay` | 多人接力賽 | リレー |
| `opt.format.solo` | 個人單人 | 個人 |
| `opt.mediatype.brochure_pdf` | 賽事簡章 PDF | 要項PDF |
| `opt.mediatype.certificate` | 證書照片 | 完走証 |
| `opt.mediatype.gpx_track` | GPX 軌跡 | GPXトラック |
| `opt.mediatype.medal_photo` | 獎牌照片 | メダル写真 |
| `opt.mediatype.official_site` | 官方網站 | 公式サイト |
| `opt.mediatype.other` | 其他 | その他 |
| `opt.mediatype.photo_album` | 個人相簿 | アルバム |
| `opt.payment.paid` | 已繳清 | 支払済み |
| `opt.payment.refunding` | 退款中 | 返金手続き中 |
| `opt.payment.unpaid` | 未繳費 | 未払い |
| `opt.role.cheer_squad` | 加油團 | 応援団 |
| `opt.role.emergency_contact` | 緊急聯絡人 | 緊急連絡先 |
| `opt.role.other` | 其他 | その他 |
| `opt.role.pacer` | 配速員 | ペーサー |
| `opt.role.partner` | 同行夥伴 | 同行者 |
| `opt.sport.cycling` | 自行車 | サイクリング |
| `opt.sport.duathlon` | 二鐵 | デュアスロン |
| `opt.sport.obstacle_race` | 障礙賽 | 障害物レース |
| `opt.sport.other` | 其他 | その他 |
| `opt.sport.road_running` | 路跑 | ロード |
| `opt.sport.trail_running` | 越野跑 | トレイルラン |
| `opt.sport.triathlon` | 三鐵 | トライアスロン |
| `opt.sport.ultra_marathon` | 超級馬拉松 | ウルトラマラソン |
| `opt.status.completed` | 已完賽 | 完走 |
| `opt.status.considering` | 考慮中 | 検討中 |
| `opt.status.dnf` | 未完賽 (DNF) | 途中棄権 (DNF) |
| `opt.status.dns` | 未起跑 (DNS) | 未出走 (DNS) |
| `opt.status.lottery_pending` | 抽籤中 | 抽選待ち |
| `opt.status.registered` | 已報名 | エントリー済み |
| `opt.transportmode.flight` | 飛機 | 飛行機 |
| `opt.transportmode.hsr` | 高鐵 | 新幹線／高鉄 |
| `opt.transportmode.other` | 其他 | その他 |
| `opt.transportmode.self_drive` | 自駕 | 自家用車 |
| `opt.transportmode.shuttle` | 接駁車 | シャトルバス |
| `opt.weather.cloudy` | 陰 | 曇り |
| `opt.weather.foggy` | 霧 | 霧 |
| `opt.weather.other` | 其他 | その他 |
| `opt.weather.rainy` | 雨 | 雨 |
| `opt.weather.sunny` | 晴 | 晴れ |
## 介面與操作文字 (UI Labels & Actions)

| 欄位 Key | 繁體中文 | 日本語 |
|---|---|---|
| `ui.addItem` | + 新增 | + 追加 |
| `ui.appTitle` | 賽事紀錄 | レース記録 |
| `ui.apply` | 套用 | 適用 |
| `ui.applyTemplate` | 套用範本 | テンプレートを適用 |
| `ui.authFailed` | 登入失敗： | ログイン失敗： |
| `ui.authPopupBlocked` | 瀏覽器擋掉了登入視窗，請允許彈出視窗後再試一次 | ブラウザがポップアップをブロックしました。ポップアップを許可して再試行してください |
| `ui.authPopupClosed` | 登入視窗被關閉了，請再試一次 | ログインウィンドウが閉じられました。もう一度お試しください |
| `ui.authUnauthorizedDomain` | 這個網域還沒被 Firebase 授權，請到 Authentication → Settings → Authorized domains 新增此網域 | このドメインはまだFirebaseで許可されていません。Authentication → Settings → Authorized domainsに追加してください |
| `ui.cancel` | 取消 | キャンセル |
| `ui.clearAll` | 清除全部資料 | すべてのデータを削除 |
| `ui.clearAllConfirm` | 確定清除？再按一次 | 本当に削除しますか？もう一度押してください |
| `ui.close` | 關閉 | 閉じる |
| `ui.countdownDays` | 倒數 ${d} 天 | あと {n} 日 |
| `ui.createRace` | 新增賽事 | 大会を作成 |
| `ui.dateNotSet` | 尚未設定日期 | 日付未設定 |
| `ui.daysLeft` | 還有 ${d} 天 | 残り {n} 日 |
| `ui.delete` | 刪除 | 削除 |
| `ui.deleteConfirm` | 確定刪除？再按一次 | 本当に削除しますか？もう一度 |
| `ui.deleteRace` | 刪除賽事 | 大会を削除 |
| `ui.deleteTemplate` | 刪除範本 | テンプレートを削除 |
| `ui.deleteTemplateConfirm` | 確定刪除？再按一次 | 本当に削除？もう一度 |
| `ui.downloadWristband` | 下載配速手環圖片 | リストバンド画像をダウンロード |
| `ui.errCannotParseFile` | 檔案格式無法解析，請確認是有效的 GPX 或 TCX 檔 | ファイル形式を解析できません。有効な GPX または TCX ファイルか確認してください |
| `ui.errNotEnoughPoints` | 檔案中沒有足夠的座標點 | ファイル内に十分な座標点がありません |
| `ui.errPasteNotObject` | 請貼上一個 JSON 物件（用 { } 包起來） | JSONオブジェクト（{ } で囲まれたもの）を貼り付けてください |
| `ui.excelBackToSheets` | ‹ 重新選擇工作表 | ‹ シート選択に戻る |
| `ui.excelColDate` | 日期 | 日付 |
| `ui.excelColDistance` | 距離 | 距離 |
| `ui.excelColName` | 賽事名稱 | 大会名 |
| `ui.excelColSource` | 來源分頁 | 元シート |
| `ui.excelColStatus` | 狀態 | ステータス |
| `ui.excelColVenue` | 地點 | 場所 |
| `ui.excelImport` | 匯入所選賽事 | 選択したレースを読み込む |
| `ui.excelParse` | 解析並預覽 | 解析してプレビュー |
| `ui.excelStep1Hint` | 已勾選看起來像「年度賽事清單」的工作表，可自行調整要匯入哪些分頁。 | 「年度別レース一覧」らしきシートには自動でチェックが入っています。必要に応じて調整してください。 |
| `ui.excelStep1Title` | 匯入 Excel — 選擇工作表 | Excelを読み込む — シートを選択 |
| `ui.excelStep2Title` | 匯入 Excel — 確認賽事清單 | Excelを読み込む — レース一覧の確認 |
| `ui.exportRaceIcs` | 加入行事曆提醒 | カレンダーに追加 |
| `ui.generateShareImage` | 產生分享圖 | シェア画像を作成 |
| `ui.goalPaceStrategy` | 配速策略 | ペース戦略 |
| `ui.goalTargetTime` | 目標時間 | 目標タイム |
| `ui.goalsTitle` | 賽前目標 | 目標タイム |
| `ui.gpxApply` | 套用到此賽事 | このレースに適用 |
| `ui.gpxAvgHr` | 平均心率 | 平均心拍数 |
| `ui.gpxDistance` | 距離 | 距離 |
| `ui.gpxElevGain` | 總爬升 | 累積標高 |
| `ui.gpxHintFull` | 從 ${fileEsc} 讀到以下數據，確認後套用到「${raceName}」（已有官方成績的欄位不會被覆蓋）： | {file} から以下のデータを読み取りました。確認後「{race}」に適用します（すでに公式記録が入力されている項目は上書きしません）： |
| `ui.gpxImportBtn` | 匯入運動紀錄檔（GPX / TCX） | アクティビティファイルを読み込む（GPX / TCX） |
| `ui.gpxImportHint` | 支援 Garmin / COROS / Strava 匯出的檔案，自動抓距離、爬升、時間、心率、分段配速 | Garmin / COROS / Strava から書き出したファイルに対応。距離・標高・タイム・心拍数・スプリットを自動取得します。 |
| `ui.gpxMaxHr` | 最大心率 | 最大心拍数 |
| `ui.gpxModalTitle` | 匯入運動紀錄檔 | アクティビティファイルの読み込み |
| `ui.gpxSplits` | 分段配速 | スプリット数 |
| `ui.gpxTime` | 時間 | タイム |
| `ui.helpTitle` | 使用說明 | 使い方 |
| `ui.helpVersionLine` | 版本 ${APP_VERSION} ・ 更完整的說明與雲端同步／推播通知部署步驟請見 repo 裡的 USAGE.md | バージョン {n} ・ より詳しい使い方やクラウド同期／プッシュ通知の設定手順はリポジトリの USAGE.md をご覧ください |
| `ui.justToday` | 就是今天 | 本日です |
| `ui.loading` | 載入中… | 読み込み中… |
| `ui.monthsLeft` | 還有約 ${Math.round(d/30)} 個月 | 残り約 {n} ヶ月 |
| `ui.newRace` | + 新增賽事 | + 大会を追加 |
| `ui.newRaceDate` | 比賽日期 | レース日 |
| `ui.newRaceName` | 賽事名稱 | 大会名 |
| `ui.newRaceNamePlaceholder` | 如：2026 臺北馬拉松 | 例：2026 台北マラソン |
| `ui.newRaceSport` | 主要運動種類 | 主な種目 |
| `ui.newRaceStatus` | 狀態 | ステータス |
| `ui.notYetAdded` | 尚未新增 | まだ追加されていません |
| `ui.notifFailed` | 推播設定失敗： | 通知の設定に失敗： |
| `ui.pacingCalc` | 試算 | 計算 |
| `ui.pacingCalcTitle` | 配速試算與手環產生器 | ペース計算＆リストバンド作成 |
| `ui.pacingDistance` | 總距離（公里） | 距離（km） |
| `ui.pacingDistanceCol` | 距離 | 距離 |
| `ui.pacingEven` | 勻速 | イーブンペース |
| `ui.pacingEvery1` | 每 1 公里 | 1kmごと |
| `ui.pacingEvery10` | 每 10 公里 | 10kmごと |
| `ui.pacingEvery5` | 每 5 公里 | 5kmごと |
| `ui.pacingHint` | 輸入目標時間與距離，選擇配速策略，算出每個分段的預計通過時間，也可以下載成手環圖片。 | 目標タイムと距離、ペース戦略を入力すると、区間ごとの通過予定タイムを計算します。 |
| `ui.pacingInterval` | 分段間隔 | 区間 |
| `ui.pacingInvalid` | 請輸入有效的目標時間與距離 | 有効な目標タイムと距離を入力してください |
| `ui.pacingNegative` | 負分段（後段加速） | ネガティブスプリット（後半加速） |
| `ui.pacingPositive` | 正分段（後段保守） | ポジティブスプリット（後半抑えめ） |
| `ui.pacingStrategy` | 配速策略 | ペース戦略 |
| `ui.pacingTargetTime` | 目標時間 | 目標タイム |
| `ui.pacingTimeCol` | 預計通過時間 | 通過予定タイム |
| `ui.pastDaysAgo` | 已過 ${Math.abs(d)} 天 | {n} 日前に終了 |
| `ui.pasteHintFull` | 把賽事網站、簡章 PDF 或證書內容請 Claude 整理成 JSON（欄位名稱對照 race-document.schema.json），貼在下面就會套用到「${raceName}」。只會更新你貼的欄位，其他資料不會被覆蓋。 | 大会サイト、要項PDF、完走証の内容をAIに race-document.schema.json の形式のJSONに整理してもらい、ここに貼り付けると「{race}」に反映されます。貼り付けた項目だけが更新され、他のデータは変更されません。 |
| `ui.pasteJsonError` | JSON 格式錯誤： | JSON形式エラー： |
| `ui.pasteModalTitle` | 貼上資料快速填入 | データを貼り付けて入力 |
| `ui.pasteQuickFill` | 貼上資料快速填入 | データを貼り付けて入力 |
| `ui.pbBadge` | 個人最佳 PB | 自己ベスト PB |
| `ui.raceShoe` | 本場穿著鞋款 | 着用シューズ |
| `ui.resultAvgHr` | 平均心率 | 平均心拍数 |
| `ui.resultElevGain` | 總爬升 | 累積標高 |
| `ui.resultOverallRank` | 總排名次 | 総合順位 |
| `ui.resultPace` | 配速 | ペース |
| `ui.saveAsTemplate` | 另存為範本 | テンプレートとして保存 |
| `ui.saveTemplate` | 儲存範本 | 保存 |
| `ui.sectionBasic` | 基本資訊與時間 | 基本情報と日程 |
| `ui.sectionLogistics` | 預算與行程規劃 | 予算と旅程 |
| `ui.sectionPost` | 賽後紀錄與個人數據 | レース後の記録とデータ |
| `ui.sectionPrep` | 裝備、補給與戰略（賽前準備） | 装備・補給・戦略（レース前の準備） |
| `ui.sectionRoute` | 地理與路線 | コースと地形 |
| `ui.sectionWeather` | 氣象 | 気象 |
| `ui.selectAll` | 全選 | すべて選択 |
| `ui.selectNone` | 全不選 | 選択解除 |
| `ui.selectRaceHint` | 點選上方行事曆中的賽事查看詳細紀錄，或建立一場新賽事。 | 上のカレンダーから大会を選ぶか、新しい大会を作成してください。 |
| `ui.seriesBest` | 系列最佳晶片時間 | シリーズ最高記録 |
| `ui.seriesComparison` | 系列賽事比較（跨年） | シリーズ大会の比較（年別） |
| `ui.seriesThisRace` | （本場） | （このレース） |
| `ui.seriesYear` | 年份 | 年 |
| `ui.shareImageSuffix` | -分享圖.png | -シェア画像.png |
| `ui.shoeAdd` | 新增 | 追加 |
| `ui.shoeHint` | 記錄比賽穿的鞋款，累積比賽里程幫助評估退役時機（僅計算本 app 記錄的比賽距離，不含訓練里程）。 | レースで履いたシューズを記録し、完走レースの累計距離から交換時期の目安にできます（本アプリに記録されたレース距離のみ集計、練習分は含みません）。 |
| `ui.shoeManage` | 管理鞋款 | シューズを管理 |
| `ui.shoeManageTitle` | 比賽鞋款 | シューズ管理 |
| `ui.shoeNamePlaceholder` | 鞋款名稱，如「ASICS Metaspeed」 | シューズ名（例：ASICS Metaspeed） |
| `ui.shoeNoneYet` | 尚未新增鞋款 | まだシューズが登録されていません |
| `ui.startToday` | 今天出發 | 本日スタート |
| `ui.templateNamePlaceholder` | 範本名稱，如「路跑標配」「越野標配」 | テンプレート名（例：ロード標準装備） |
| `ui.templateSelectEmpty` | 尚無已存範本 | テンプレートなし |
| `ui.unknownError` | 未知錯誤 | 不明なエラー |
| `ui.unnamedRace` | (未命名賽事) | （無題の大会） |
| `ui.weeksLeft` | 還有 ${Math.round(d/7)} 週 | 残り {n} 週間 |
| `ui.wristbandFilename` | 配速手環.png | ペース手帳.png |
| `ui.wristbandTitle` | 配速手環 | ペースリストバンド |

（另有 45 個內部/長文字段落型 key 未列入逐條對照表，例如說明頁的整段內容；請直接參考 `index.html` 裡的 `JA`/`EN`/程式碼中對應的中文原文。）