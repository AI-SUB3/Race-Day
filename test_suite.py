#!/usr/bin/env python3
"""
賽事紀錄 — 回歸測試套件
=======================

用法：
    python3 test_suite.py                  # 跑全部
    python3 test_suite.py core drawers     # 只跑指定群組
    python3 test_suite.py --list           # 列出所有群組
    APP=/path/to/index.html python3 test_suite.py

需求：pip install playwright && playwright install chromium

設計原則
--------
1. 每個 check 回傳布林值，命名直接說明「應該成立的事」，
   失敗時看名字就知道壞了什麼，不用回頭讀程式碼。
2. 只斷言「行為」，不斷言實作細節（class 名稱、DOM 結構順序），
   否則每次改版面都要跟著改測試，測試就會被當成雜訊而略過。
3. 每個群組獨立開分頁，避免前一組污染 state。
4. 任何 pageerror 都算失敗——JS 例外不該被容忍。
"""

import os
import sys
from playwright.sync_api import sync_playwright

APP = os.environ.get('APP', '/home/claude/race-schema/index.html')
APP_URL = APP if APP.startswith('http') else 'file://' + os.path.abspath(APP)

PHONE = {'width': 390, 'height': 844}
DESKTOP = {'width': 1100, 'height': 900}

# ---------------------------------------------------------------- helpers

SEED = """
async (n) => {
  // 建立 n 場已完賽、帶分段與心率的賽事，供各群組共用
  for (let i = 0; i < n; i++) {
    const r = emptyRace('Race ' + i, 'road_running', 'completed',
                        '2025-' + String(1 + (i % 12)).padStart(2, '0') + '-01');
    r.route.distanceKm = 42.195;
    r.results.chipTimeSeconds = 10771 + i * 60;
    r.performanceData.avgHr = 160; r.performanceData.maxHr = 190;
    r.splits = [];
    for (let j = 0; j < 42; j++)
      r.splits.push({distanceKm:1, avgPaceSecPerKm:255+j, avgHr:150+(j%20),
                     splitTimeSeconds:255, elevationGainM:3, notes:''});
    state.races.push(r);
  }
  renderAll();
  await new Promise(s => setTimeout(s, 300));
  return state.races.length;
}
"""


class Group:
    """一組相關的檢查，共用一個分頁。"""

    def __init__(self, name, viewport=None, touch=False):
        self.name = name
        self.viewport = viewport or DESKTOP
        self.touch = touch
        self.checks = {}
        self.errors = []

    def run(self, browser):
        ctx = browser.new_context(viewport=self.viewport, has_touch=self.touch,
                                  is_mobile=self.touch)
        page = ctx.new_page()
        page.on('pageerror', lambda e: self.errors.append(str(e)))
        page.goto(APP_URL)
        page.wait_for_timeout(800)
        try:
            self.body(page)
        except Exception as exc:                      # noqa: BLE001
            self.checks['GROUP_CRASHED'] = False
            self.errors.append(f'{type(exc).__name__}: {exc}')
        ctx.close()
        return self.checks, self.errors

    def body(self, page):
        raise NotImplementedError


# ---------------------------------------------------------------- groups

class Core(Group):
    """載入、範例資料、指令控制台、榮譽櫃 — 最基本的活著檢查。"""

    def body(self, page):
        c = self.checks
        c['app_boots'] = page.evaluate(
            'typeof state!=="undefined" && Array.isArray(state.races)')
        # 範例資料按鈕在帳號選單裡（v3.6.0 起）
        page.click('#btn-account-menu')
        page.wait_for_timeout(200)
        page.click('#btn-sample-data')
        page.wait_for_timeout(400)
        c['sample_data_imports_5'] = page.evaluate(
            'state.races.filter(r=>EXAMPLE_RACE_IDS.includes(r.id)).length') == 5
        c['sample_button_becomes_clear'] = page.evaluate(
            '''()=>document.getElementById('btn-sample-data').textContent.trim()
                 !== t('ui.sampleData','範例資料')''')
        c['sample_data_clears_again'] = page.evaluate('''async()=>{
            document.getElementById('btn-sample-data').click();
            await new Promise(s=>setTimeout(s,400));
            return state.races.filter(r=>EXAMPLE_RACE_IDS.includes(r.id)).length===0;
        }''')
        c['command_palette_opens'] = page.evaluate(
            '''()=>{cmdkOpen();const ok=!document.getElementById('command-palette').hidden;
                    cmdkClose();return ok;}''')
        c['trophy_cabinet_renders'] = page.evaluate('''async()=>{
            // 榮譽櫃在「生涯總覽」裡，而生涯總覽要有 5 場以上的賽事才會渲染
            // （renderCareerSummary 開頭就 return ''）。上面剛把範例資料清掉，
            // 所以這裡要補滿 5 場，否則測到的是「賽事不夠」而不是「榮譽櫃壞了」。
            for(let i=0;i<5;i++){
                const r=emptyRace('TrophySeed '+i,'road_running','completed',
                                  '2025-0'+(i+1)+'-01');
                r.route.distanceKm=42.195; r.results.chipTimeSeconds=10771+i*60;
                state.races.push(r);
            }
            renderAll();
            selectRace(null); await new Promise(s=>setTimeout(s,300));
            const el=document.querySelector('.trophy-cabinet-summary');
            if(el) el.click();
            await new Promise(s=>setTimeout(s,250));
            const body=document.getElementById('trophy-cabinet-body');
            return !!(body && body.innerHTML.length);
        }''')
        c['badge_definitions_unique'] = page.evaluate(
            '''()=>new Set(BADGE_DEFINITIONS.map(b=>b.id)).size===BADGE_DEFINITIONS.length''')


class Drawers(Group):
    """13 個抽屜：能開、欄位自動儲存、關閉後摘要卡片更新。"""

    def body(self, page):
        c = self.checks
        page.evaluate(SEED, 3)
        c['all_sections_registered'] = page.evaluate(
            '''()=>Object.keys(DRAWER_SECTIONS).length>=13''')
        c['every_drawer_opens'] = page.evaluate('''async()=>{
            const r=emptyRace('DrawerT','trail_running','completed','2026-06-01');
            r.route.distanceKm=43; r.results.chipTimeSeconds=10000;
            state.races.push(r); selectRace(r.id,{scroll:false});
            await new Promise(s=>setTimeout(s,250));
            for (const key of Object.keys(DRAWER_SECTIONS)) {
                openDrawer(key);
                await new Promise(s=>setTimeout(s,90));
                const open = !document.getElementById('global-drawer').hidden;
                const filled = document.getElementById('drawer-content').innerHTML.length>0;
                closeDrawer();
                await new Promise(s=>setTimeout(s,90));
                if(!open || !filled) return 'FAILED at '+key;
            }
            return true;
        }''') is True
        c['drawer_field_autosaves'] = page.evaluate('''async()=>{
            const r=state.races.find(x=>x.name==='DrawerT');
            selectRace(r.id,{scroll:false}); await new Promise(s=>setTimeout(s,200));
            openDrawer('route'); await new Promise(s=>setTimeout(s,250));
            const el=document.querySelector('#drawer-content #f-route-distanceKm');
            if(!el) return false;
            el.value='55.5'; el.dispatchEvent(new Event('change',{bubbles:true}));
            await new Promise(s=>setTimeout(s,300));
            const ok=state.races.find(x=>x.id===r.id).route.distanceKm===55.5;
            closeDrawer(); await new Promise(s=>setTimeout(s,250));
            return ok;
        }''')
        c['summary_card_reflects_edit'] = page.evaluate('''()=>{
            const el=document.querySelector('[data-section="route"] .dash-card-sub');
            return !!(el && el.textContent.includes('55.5'));
        }''')
        c['closing_drawer_restores_scroll'] = page.evaluate(
            "()=>document.body.style.overflow===''")


def share_spy(setup_js):
    """產生一段「攔 fillText、畫一張分享圖、回傳畫了哪些字」的 evaluate 原始碼。

    斷言「畫了什麼字」而不是比對像素——比對像素會把字型與抗鋸齒的差異
    也算成失敗，那種測試壞得比程式還頻繁。setup_js 是一段回傳 race 的
    JS 運算式，直接內嵌（page.evaluate 沒辦法收函式當參數）。
    """
    return """async () => {
  const proto = CanvasRenderingContext2D.prototype;
  const orig = proto.fillText;
  const drawn = [];
  proto.fillText = function(txt, ...rest){ drawn.push(String(txt)); return orig.call(this, txt, ...rest); };
  try {
    const race = (%s)();
    const canvas = await buildShareCanvas(race);
    const ctx = canvas.getContext('2d');
    return { drawn, w: canvas.width, h: canvas.height,
             pixels: [...ctx.getImageData(0, canvas.height*0.6, canvas.width, canvas.height*0.35).data] };
  } finally {
    proto.fillText = orig;
  }
}""" % setup_js


class SportUnits(Group):
    """各運動別用自己的單位——這裡錯了數字就會誤導。"""

    def body(self, page):
        c = self.checks
        N = 'normalizeRunningCadence'
        c['run_cadence_doubled'] = page.evaluate(f"()=>{N}(86,'trail_running')===172")
        c['run_cadence_already_total_untouched'] = page.evaluate(
            f"()=>{N}(172,'road_running')===172")
        c['cycling_cadence_untouched'] = page.evaluate(f"()=>{N}(86,'cycling')===86")
        c['swim_cadence_untouched'] = page.evaluate(f"()=>{N}(44,'swimming')===44")
        c['cadence_idempotent'] = page.evaluate(
            f"()=>{N}({N}(86,'road_running'),'road_running')===172")
        c['swim_pace_per_100m'] = page.evaluate(
            """()=>formatSwimPace(536).includes('/100m')""")
        # 分享圖是最容易被轉傳出去的畫面，詳情頁修好了但分享圖沿用舊算法，
        # 就會把「泳渡配速 89'25"/km、爬升 531 公尺」散佈出去。
        swim_share = page.evaluate(share_spy('''()=>{
            const r=emptyRace('泳渡','swimming','completed','2026-09-20');
            r.route.distanceKm=2.51; r.results.chipTimeSeconds=13465;
            r.route.elevationGainM=531;
            return r;
        }'''))['drawn']
        c['share_image_respects_swim_units'] = (
            any('/100m' in x for x in swim_share)
            and not any('/km' in x for x in swim_share)
            and not any('531' in x for x in swim_share))
        c['swim_hides_cadence_and_elevation'] = page.evaluate('''async()=>{
            const r=emptyRace('Swim','swimming','completed','2026-09-01');
            r.route.distanceKm=2.5; r.results.chipTimeSeconds=5626;
            r.performanceData.avgCadence=23; r.performanceData.avgHr=132;
            r.performanceData.maxHr=190; r.route.elevationGainM=531;
            state.races.push(r); selectRace(r.id,{scroll:false});
            document.getElementById('section-post').open=true;
            await new Promise(s=>setTimeout(s,400));
            const labels=[...document.querySelectorAll('.results-badge-label')]
                          .map(e=>e.textContent);
            const vals=[...document.querySelectorAll('.results-badge-value')]
                          .map(e=>e.textContent);
            return !labels.some(l=>l.includes('步頻'))
                && !labels.some(l=>l.includes('爬升'))
                && vals.some(v=>v.includes('/100m'));
        }''')
        c['running_race_keeps_cadence_and_km'] = page.evaluate('''async()=>{
            const r=emptyRace('Run','road_running','completed','2026-01-01');
            r.route.distanceKm=42.195; r.results.chipTimeSeconds=10771;
            r.performanceData.avgCadence=172; r.performanceData.avgHr=162;
            r.performanceData.maxHr=190;
            state.races.push(r); selectRace(r.id,{scroll:false});
            document.getElementById('section-post').open=true;
            await new Promise(s=>setTimeout(s,400));
            const labels=[...document.querySelectorAll('.results-badge-label')]
                          .map(e=>e.textContent);
            const vals=[...document.querySelectorAll('.results-badge-value')]
                          .map(e=>e.textContent);
            return labels.some(l=>l.includes('步頻')) && vals.some(v=>v.includes('/km'));
        }''')


class Multisport(Group):
    """鐵人三項分項成績：FIT session → legs，各段用自己的單位。"""

    def body(self, page):
        c = self.checks
        c['legs_render_with_T1_T2'] = page.evaluate('''async()=>{
            const r=emptyRace('Tri','triathlon','completed','2026-10-18');
            r.results.chipTimeSeconds=52710;
            r.legs=[{sport:'swimming',durationSeconds:6218,distanceKm:3.8,avgHr:141},
                    {sport:'transition',durationSeconds:1690,distanceKm:0,avgHr:132},
                    {sport:'cycling',durationSeconds:24184,distanceKm:180,avgHr:148},
                    {sport:'transition',durationSeconds:1081,distanceKm:0,avgHr:140},
                    {sport:'running',durationSeconds:19539,distanceKm:42.2,avgHr:156}];
            state.races.push(r); selectRace(r.id,{scroll:false});
            document.getElementById('section-post').open=true;
            await new Promise(s=>setTimeout(s,400));
            const names=[...document.querySelectorAll('.leg-name')].map(e=>e.textContent.trim());
            return names.length===5
                && names.some(n=>n.startsWith('T1'))
                && names.some(n=>n.startsWith('T2'));
        }''')
        c['each_leg_uses_own_unit'] = page.evaluate('''()=>{
            const swim=legPaceLabel({sport:'swimming',distanceKm:3.8,durationSeconds:6218});
            const bike=legPaceLabel({sport:'cycling',distanceKm:180,durationSeconds:24184});
            const run =legPaceLabel({sport:'running',distanceKm:42.2,durationSeconds:19539});
            const t   =legPaceLabel({sport:'transition',distanceKm:0,durationSeconds:100});
            return swim.includes('/100m') && bike.includes('km/h')
                && run.includes('/km') && t===null;
        }''')
        c['multisport_hides_whole_race_averages'] = page.evaluate('''async()=>{
            const r=state.races.find(x=>x.name==='Tri');
            selectRace(r.id,{scroll:false});
            document.getElementById('section-post').open=true;
            await new Promise(s=>setTimeout(s,350));
            const labels=[...document.querySelectorAll('.results-badge-label')]
                          .map(e=>e.textContent);
            return !labels.some(l=>l.includes('配速'));
        }''')
        c['single_sport_has_no_leg_section'] = page.evaluate('''async()=>{
            const r=emptyRace('Solo','road_running','completed','2026-02-01');
            r.route.distanceKm=42.195; r.results.chipTimeSeconds=10771;
            state.races.push(r); selectRace(r.id,{scroll:false});
            document.getElementById('section-post').open=true;
            await new Promise(s=>setTimeout(s,350));
            return !document.querySelector('.leg-breakdown');
        }''')


class Sync(Group):
    """雲端合併規則：本機優先，永不覆蓋本機已有值。"""

    def body(self, page):
        c = self.checks
        c['new_device_pulls_everything'] = page.evaluate('''()=>{
            userProfile=emptyUserProfile(); templates=[]; badgeUnlocks={};
            shoes.length=0; nutritionDictionary.length=0;
            mergeGlobalListsIntoState({
                shoes:[{id:'s1',name:'CloudShoe'}],
                nutritionDictionary:[{id:'n1',name:'CloudGel'}],
                templates:[{id:'t1',name:'CloudTpl',items:[]}],
                badgeUnlocks:{b1:{unlockedAt:'2025-01-01T00:00:00Z'}},
                userProfile:{weightKg:62,hr:{running:{restingHr:45,maxHr:190}}},
            });
            return shoes.length===1 && templates.length===1
                && Object.keys(badgeUnlocks).length===1
                && userProfile.weightKg===62
                && userProfile.hr.running.maxHr===190;
        }''')
        c['local_values_never_overwritten'] = page.evaluate('''()=>{
            userProfile=emptyUserProfile();
            userProfile.weightKg=58;
            userProfile.hr.running.maxHr=195;
            mergeGlobalListsIntoState({userProfile:{
                weightKg:99, heightCm:180, hr:{running:{restingHr:40,maxHr:170}}}});
            return userProfile.weightKg===58          // 本機值保留
                && userProfile.hr.running.maxHr===195 // 本機值保留
                && userProfile.heightCm===180         // 空欄位從雲端補上
                && userProfile.hr.running.restingHr===40;
        }''')
        c['badge_keeps_earliest_unlock'] = page.evaluate('''()=>{
            badgeUnlocks={a:{unlockedAt:'2026-01-01T00:00:00Z',seen:true}};
            mergeGlobalListsIntoState({badgeUnlocks:{
                a:{unlockedAt:'2023-05-05T00:00:00Z',seen:false}}});
            return badgeUnlocks.a.unlockedAt==='2023-05-05T00:00:00Z'
                && badgeUnlocks.a.seen===true;   // 已讀狀態保留
        }''')
        c['malformed_cloud_payload_safe'] = page.evaluate('''()=>{
            try{
                mergeGlobalListsIntoState(null);
                mergeGlobalListsIntoState({});
                mergeGlobalListsIntoState({templates:'nope',badgeUnlocks:5,userProfile:'x'});
                return true;
            }catch(e){ return false; }
        }''')
        c['storage_failure_is_surfaced'] = page.evaluate('''async()=>{
            const orig=window.saveJson;
            let shown=0;
            const origShow=window.showStorageError;
            window.showStorageError=()=>{shown++;};
            window.saveJson=async()=>{throw new Error('QuotaExceededError');};
            await persist(); await persistShoes(); await persistUserProfile();
            window.saveJson=orig; window.showStorageError=origShow;
            return shown>=3;
        }''')


class Security(Group):
    """XSS：使用者可控欄位必須無法執行程式碼；外部套件必須驗證完整性。"""

    def body(self, page):
        c = self.checks
        # CDN 被入侵或被中間人換包時，SRI 是唯一會擋下來的機制；
        # 少一個 integrity 或少一個 crossorigin（沒有它瀏覽器拿不到內容也就無從比對）都等於沒防。
        c['external_scripts_have_sri'] = page.evaluate('''()=>
            [...document.querySelectorAll('script[src^="http"]')].every(s=>
                (s.getAttribute('integrity')||'').startsWith('sha384-')
             && s.getAttribute('crossorigin')==='anonymous')
        ''')
        # 版本寫成 @6 這類浮動範圍時，上游一發新版雜湊就對不上、套件被整個擋掉。
        # SRI 與浮動版本不能並存，所以這裡強制路徑上出現完整三段版號。
        c['external_scripts_pinned_to_exact_version'] = page.evaluate('''()=>
            [...document.querySelectorAll('script[src^="http"]')].every(s=>
                /@\\d+\\.\\d+\\.\\d+\\//.test(s.getAttribute('src')))
        ''')
        c['safe_url_blocks_dangerous_schemes'] = page.evaluate('''()=>
            safeUrl('javascript:alert(1)')===''
         && safeUrl('JaVaScRiPt:alert(1)')===''
         && safeUrl('data:text/html,<script>alert(1)</script>')===''
         && safeUrl('data:image/svg+xml,<svg onload=alert(1)>')===''
         && safeUrl('vbscript:msgbox(1)')===''
         && safeUrl('x" onerror="alert(1)')===''
        ''')
        c['safe_url_allows_legitimate'] = page.evaluate('''()=>
            safeUrl('https://strava.com/x')==='https://strava.com/x'
         && safeUrl('data:image/png;base64,iVBORw0KGgo=').startsWith('data:image/png')
         && safeUrl('data:image/jpeg;base64,/9j/4AAQ').startsWith('data:image/jpeg')
        ''')
        c['race_name_payload_does_not_execute'] = page.evaluate('''async()=>{
            window.__xss=[];
            const r=emptyRace('<img src=x onerror="window.__xss.push(1)">',
                              'road_running','completed','2026-03-01');
            state.races.push(r); selectRace(r.id,{scroll:false});
            await new Promise(s=>setTimeout(s,350));
            return window.__xss.length===0;
        }''')
        c['cover_image_payload_does_not_execute'] = page.evaluate('''async()=>{
            window.__xss=[];
            const r=emptyRace('Cover','road_running','completed','2026-04-01');
            r.coverImage='x" onerror="window.__xss.push(1)" data-x="';
            r.results.chipTimeSeconds=3600; r.route.distanceKm=10;
            state.races.push(r);
            state.viewMode='grid'; renderCalendar();
            await new Promise(s=>setTimeout(s,400));
            return window.__xss.length===0;
        }''')
        c['media_link_js_scheme_neutralised'] = page.evaluate('''async()=>{
            const r=emptyRace('Link','road_running','completed','2026-02-01');
            r.mediaLinks=[{type:'link',url:'javascript:alert(1)',notes:'x'}];
            state.races.push(r); selectRace(r.id,{scroll:false});
            document.getElementById('section-post').open=true;
            await new Promise(s=>setTimeout(s,350));
            const a=document.querySelector('.media-gallery-link');
            return !a || !a.getAttribute('href').startsWith('javascript:');
        }''')


class Mobile(Group):
    """手機專屬：縮放鎖定、觸控手勢、表格高度。"""

    def __init__(self):
        super().__init__('mobile', viewport=PHONE, touch=True)

    def body(self, page):
        c = self.checks
        c['pinch_zoom_blocked'] = page.evaluate('''()=>{
            const e=new Event('gesturestart',{cancelable:true,bubbles:true});
            document.dispatchEvent(e);
            return e.defaultPrevented;
        }''')
        c['normal_scroll_not_blocked'] = page.evaluate('''()=>{
            const e=new WheelEvent('wheel',{cancelable:true,bubbles:true});
            document.dispatchEvent(e);
            return !e.defaultPrevented;
        }''')
        c['inputs_at_least_16px'] = page.evaluate('''async()=>{
            const r=emptyRace('M','trail_running','registered','2026-12-01');
            state.races.push(r); selectRace(r.id,{scroll:false});
            await new Promise(s=>setTimeout(s,250));
            openDrawer('basicInfo'); await new Promise(s=>setTimeout(s,300));
            const inp=document.querySelector('#drawer-content input');
            const size=inp?parseFloat(getComputedStyle(inp).fontSize):0;
            closeDrawer();
            return size>=16;   // 小於 16px 會觸發 iOS 對焦自動放大
        }''')
        c['splits_table_height_capped'] = page.evaluate('''async()=>{
            const r=emptyRace('S','road_running','completed','2026-01-01');
            r.route.distanceKm=42.195; r.results.chipTimeSeconds=10771;
            r.performanceData.maxHr=190;
            r.splits=[];
            for(let i=0;i<42;i++) r.splits.push({distanceKm:1,avgPaceSecPerKm:255+i,
                avgHr:150,splitTimeSeconds:255,elevationGainM:3,notes:''});
            state.races.push(r); selectRace(r.id,{scroll:false});
            document.getElementById('section-post').open=true;
            await new Promise(s=>setTimeout(s,450));
            const w=document.querySelector('.splits-chart-wrap');
            if(!w) return false;
            return w.getBoundingClientRect().height<=420 && w.scrollHeight>w.clientHeight;
        }''')
        c['overlay_depth_toggles_and_clears'] = page.evaluate('''async()=>{
            openShoeModal(); await new Promise(s=>setTimeout(s,200));
            const on=document.body.classList.contains('overlay-open');
            document.getElementById('shoe-modal').hidden=true;
            await new Promise(s=>setTimeout(s,250));
            const off=!document.body.classList.contains('overlay-open');
            return on && off;
        }''')
        c['fab_stays_fixed_during_overlay'] = page.evaluate('''async()=>{
            const fab=document.getElementById('btn-help');
            const before=fab.getBoundingClientRect();
            openShoeModal(); await new Promise(s=>setTimeout(s,250));
            const during=fab.getBoundingClientRect();
            document.getElementById('shoe-modal').hidden=true;
            return Math.abs(during.top-before.top)<1
                && Math.abs(during.left-before.left)<1;
        }''')


class I18n(Group):
    """三語言：動態組出來的翻譯鍵不能漏出原始鍵名。"""

    def body(self, page):
        c = self.checks
        for lang in ('zh', 'ja', 'en'):
            if lang != 'zh':
                page.select_option('#lang-select', lang)
                page.wait_for_timeout(300)
            leaked = page.evaluate('''()=>{
                const legs=['swimming','cycling','running','transition']
                    .map(s=>legSportLabel({sport:s}));
                const cats=['explore','terrain','speed','crossover','gear']
                    .map(k=>t('ui.trophyCat_'+k,k));
                const days=weekdayLabels();
                return [...legs,...cats,...days].some(x=>String(x).startsWith('ui.'));
            }''')
            c[f'{lang}_no_raw_translation_keys'] = not leaked


class Data(Group):
    """資料完整性：刪除、復原、垃圾桶、縮圖。"""

    def body(self, page):
        c = self.checks
        c['delete_is_soft_and_restorable'] = page.evaluate('''async()=>{
            const r=emptyRace('Trash','road_running','completed','2026-01-01');
            state.races.push(r);
            r.deletedAt=new Date().toISOString();
            const inTrash=state.races.some(x=>x.id===r.id && x.deletedAt);
            restoreDeletedRace(r.id);
            await new Promise(s=>setTimeout(s,200));
            return inTrash && !state.races.find(x=>x.id===r.id).deletedAt;
        }''')
        c['purge_all_only_removes_trashed'] = page.evaluate('''async()=>{
            state.races=[];
            for(let i=0;i<3;i++){
                const a=emptyRace('Active '+i,'road_running','completed','2025-0'+(i+1)+'-01');
                state.races.push(a);
            }
            for(let i=0;i<2;i++){
                const d=emptyRace('Dead '+i,'road_running','completed','2025-0'+(i+5)+'-01');
                d.deletedAt=new Date().toISOString(); state.races.push(d);
            }
            openRecoveryModal(); await new Promise(s=>setTimeout(s,200));
            const btn=()=>document.querySelector('[data-action="purge-all-races"]');
            btn().click(); await new Promise(s=>setTimeout(s,200));   // 第一次只解除保險
            const stillThere=state.races.filter(x=>x.deletedAt).length===2;
            btn().click(); await new Promise(s=>setTimeout(s,300));   // 第二次才真的刪
            const gone=state.races.filter(x=>x.deletedAt).length===0;
            const activeKept=state.races.filter(x=>!x.deletedAt).length===3;
            closeRecoveryModal();
            return stillThere && gone && activeKept;
        }''')
        c['cover_thumb_capped_at_target_px'] = page.evaluate('''async()=>{
            // 斷言真正的契約是「最長邊縮到 COVER_THUMB_PX」，不是位元組大小——
            // 合成的棋盤格是高頻雜訊、壓縮率很差，用檔案大小當門檻會
            // 量到圖片內容而不是縮圖邏輯。尺寸讀常數而不寫死數字，
            // 之後再調解析度時這項不用跟著改。
            const c=document.createElement('canvas');
            c.width=1200; c.height=800;
            const ctx=c.getContext('2d');
            ctx.fillStyle='#c85'; ctx.fillRect(0,0,1200,800);
            const thumb=makeCoverThumb(c,1200,800);
            const dims=await new Promise(res=>{
                const i=new Image();
                i.onload=()=>res([i.width,i.height]);
                i.src=thumb;
            });
            return Math.max(...dims)===COVER_THUMB_PX && thumb.length < c.toDataURL('image/jpeg',0.92).length;
        }''')
        c['thumb_falls_back_to_full_when_missing'] = page.evaluate('''()=>{
            const r=emptyRace('NoThumb','road_running','completed','2026-01-01');
            r.coverImage='data:image/png;base64,AAAA'; r.coverThumb='';
            return coverThumbOf(r)===r.coverImage;
        }''')
        # 舊的 320px 縮圖要能被重產成現在的解析度；而原圖本來就比目標小的
        # 不能重產——否則每次啟動都白做一輪、還會觸發一次存檔與雲端同步。
        # 分享圖下半部：跑步賽事要帶鞋款、補給要列實際吃掉的、軌跡要是金色的。
        run_share = page.evaluate(share_spy('''()=>{
            shoes.push({id:'t-shoe',name:'Alphafly 3',targetKm:600,isRetired:false,trainingKm:0});
            const r=emptyRace('馬拉松','road_running','completed','2026-12-20');
            r.route.distanceKm=42.195; r.results.chipTimeSeconds=10771;
            r.performanceData.shoeId='t-shoe';
            r.nutritionSchedule=[{item:'能量膠',qty:4,consumed:true},
                                 {item:'鹽錠',qty:6,consumed:true},
                                 {item:'沒吃到的東西',qty:9,consumed:false}];
            const pts=[];
            for(let i=0;i<120;i++){ const a=i/119*Math.PI*2;
                pts.push({lat:25.04+Math.sin(a)*0.012, lon:121.56+Math.cos(a)*0.016}); }
            r.route.trackPoints=pts;
            return r;
        }'''))
        drawn = run_share['drawn']
        c['share_image_shows_shoe_and_consumed_fuel'] = (
            any('Alphafly 3' in x for x in drawn)
            and any('能量膠 ×4' in x for x in drawn)
            and not any('沒吃到的東西' in x for x in drawn))
        # 軌跡是金色的：下三分之一要找得到夠亮、紅綠明顯高於藍的像素。
        # 只數「有沒有畫線」不夠——畫成白色或綠色都會通過。
        px = run_share['pixels']
        gold = 0
        for i in range(0, len(px), 4):
            r_, g_, b_ = px[i], px[i+1], px[i+2]
            if r_ > 150 and g_ > 130 and r_ - b_ > 40:
                gold += 1
        c['share_image_track_glows_gold'] = gold > 500
        # 沒有軌跡的賽事不能因此壞掉，也不該留下半張圖
        c['share_image_survives_missing_track'] = page.evaluate(share_spy('''()=>{
            const r=emptyRace('無軌跡','road_running','completed','2026-03-01');
            r.route.distanceKm=10; r.results.chipTimeSeconds=2400;
            return r;
        }'''))['w'] == 1080
        c['undersized_thumbs_regenerate_once_only'] = page.evaluate('''async()=>{
            const mk=(px,q)=>{const c=document.createElement('canvas');
                c.width=px;c.height=Math.round(px*0.75);
                const x=c.getContext('2d');
                const g=x.createLinearGradient(0,0,px,px*0.75);
                g.addColorStop(0,'#c85'); g.addColorStop(1,'#345');
                x.fillStyle=g; x.fillRect(0,0,c.width,c.height);
                return c.toDataURL('image/jpeg',q);};
            state.races=[];
            const old=emptyRace('舊縮圖','road_running','completed','2026-01-15');
            old.coverImage=mk(760,0.78); old.coverThumb=mk(320,0.72); state.races.push(old);
            const small=emptyRace('小原圖','road_running','completed','2026-02-15');
            small.coverImage=mk(240,0.78); small.coverThumb=mk(240,0.72); state.races.push(small);
            let persists=0; const origPersist=window.persist;
            window.persist=async()=>{persists++;};
            await backfillCoverThumbs();
            const firstRound=persists;
            await backfillCoverThumbs();
            const secondRound=persists-firstRound;
            window.persist=origPersist;
            const size=async d=>{const i=new Image();i.src=d;await i.decode();
                                 return Math.max(i.width,i.height);};
            return await size(old.coverThumb)===COVER_THUMB_PX
                && await size(small.coverThumb)===240
                && firstRound===1 && secondRound===0;
        }''')
        c['photo_wall_scrolls_into_view_on_toggle'] = page.evaluate('''async()=>{
            state.races=[];
            for(let i=0;i<6;i++){
                const r=emptyRace('Wall '+i,'road_running','completed','2026-0'+(i+1)+'-15');
                r.results.chipTimeSeconds=10771; r.route.distanceKm=42.195;
                const cv=document.createElement('canvas'); cv.width=64; cv.height=64;
                cv.getContext('2d').fillRect(0,0,64,64);
                r.coverImage=cv.toDataURL('image/jpeg',0.7); r.coverThumb=r.coverImage;
                state.races.push(r);
            }
            state.viewMode='calendar'; renderAll();
            window.scrollTo(0,0);
            await new Promise(s=>setTimeout(s,150));
            document.getElementById('cal-view-toggle').click();
            await new Promise(s=>setTimeout(s,900));   // 等平滑捲動結束
            const wrap=document.querySelector('.photo-grid-wrap');
            if(!wrap) return false;
            const top=wrap.getBoundingClientRect().top;
            // 牆進到可視範圍內（不再是捲動前的一個半螢幕之外）
            return window.scrollY>0 && top>-40 && top<window.innerHeight*0.6;
        }''')
        # 牆的位置沒有被搬到榮譽櫃上方——只是捲過去，版面順序不變
        c['photo_wall_stays_below_trophy_cabinet'] = page.evaluate('''()=>{
            const wrap=document.querySelector('.photo-grid-wrap');
            const cabinet=document.querySelector('.trophy-cabinet-summary');
            if(!wrap||!cabinet) return false;
            return cabinet.compareDocumentPosition(wrap)&Node.DOCUMENT_POSITION_FOLLOWING;
        }''')
        # 匯入紀錄檔一律覆蓋，成績時間是最容易被偷偷保留的那一格：
        # 一旦又加回「已有值就不覆蓋」的保護，使用者會再次遇到
        # 「匯入的時間跟畫面對不上」而完全查不出原因。
        c['activity_import_overwrites_existing_time'] = page.evaluate('''()=>{
            const r=emptyRace('Overwrite','road_running','completed','2026-05-01');
            r.results.chipTimeSeconds=13465; r.route.distanceKm=3.3;
            r.performanceData.dataSource='手動輸入';
            applyActivitySummaryToRace(r,{durationSeconds:5626,distanceKm:2.51,
                                          elevationGainM:120,avgHr:150,maxHr:170});
            return r.results.chipTimeSeconds===5626
                && r.route.distanceKm===2.51
                && r.performanceData.dataSource!=='手動輸入';
        }''')
        # 檔案沒有的欄位不能被 null 清空——「一律覆蓋」指的是有值才蓋，
        # 不是拿空白把使用者手填的資料洗掉。
        c['activity_import_keeps_fields_absent_from_file'] = page.evaluate('''()=>{
            const r=emptyRace('Partial','road_running','completed','2026-06-01');
            r.results.chipTimeSeconds=10771; r.performanceData.avgHr=148;
            applyActivitySummaryToRace(r,{distanceKm:42.195});
            return r.results.chipTimeSeconds===10771 && r.performanceData.avgHr===148;
        }''')


GROUPS = {
    'core':       lambda: Core('core'),
    'drawers':    lambda: Drawers('drawers'),
    'sport':      lambda: SportUnits('sport'),
    'multisport': lambda: Multisport('multisport'),
    'sync':       lambda: Sync('sync'),
    'security':   lambda: Security('security'),
    'mobile':     lambda: Mobile(),
    'i18n':       lambda: I18n('i18n'),
    'data':       lambda: Data('data'),
}


# ---------------------------------------------------------------- runner

def main():
    args = [a for a in sys.argv[1:] if not a.startswith('-')]
    if '--list' in sys.argv:
        print('可用群組：', ' '.join(GROUPS))
        return 0

    selected = args or list(GROUPS)
    unknown = [g for g in selected if g not in GROUPS]
    if unknown:
        print('未知群組：', ' '.join(unknown))
        print('可用群組：', ' '.join(GROUPS))
        return 2

    print(f'測試目標：{APP_URL}\n')
    total = passed = 0
    failures = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        for name in selected:
            group = GROUPS[name]()
            checks, errors = group.run(browser)
            print(f'── {name} ' + '─' * max(0, 46 - len(name)))
            for label, ok in checks.items():
                total += 1
                if ok:
                    passed += 1
                    print(f'   ✅ {label}')
                else:
                    failures.append(f'{name}.{label}')
                    print(f'   ❌ {label}')
            if errors:
                # JS 例外一律視為失敗：它代表某處真的炸了，只是畫面上剛好看不出來
                for e in errors:
                    failures.append(f'{name}.pageerror: {e[:90]}')
                    print(f'   ❌ pageerror: {e[:90]}')
                    total += 1
            print()
        browser.close()

    print('=' * 52)
    print(f'結果：{passed}/{total} 通過')
    if failures:
        print('\n失敗項目：')
        for f in failures:
            print('  •', f)
        return 1
    print('全部通過 ✅')
    return 0


if __name__ == '__main__':
    sys.exit(main())
