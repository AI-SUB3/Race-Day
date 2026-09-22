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
import base64
import cv2
import numpy as np
import re
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
        # ---- 1b：空抽屜淡化，填了的維持原樣 ----
        # 區段最後一張卡片不能黏在區段下緣（左右有 20px，下面卻 0）
        # 路線與氣象合併成一個區段，底下兩個子標題；導覽列少一格
        # 區段順序：裝備（賽前準備）排在預算之前，導覽列順序要一致
        c['prep_section_before_logistics_and_nav_matches'] = page.evaluate('''async()=>{
            const r=emptyRace('順序','trail_running','registered','2026-09-06');
            state.races.push(r); selectRace(r.id,{scroll:false});
            await new Promise(s=>setTimeout(s,300));
            const ids=[...document.querySelectorAll('details.section')].map(e=>e.id);
            const navTargets=[...document.querySelectorAll('.quick-nav a')].map(a=>a.dataset.target);
            return ids.join(',')==='section-basic,section-route,section-prep,section-logistics,section-post'
                && navTargets.join(',')===ids.join(',');
        }''')
        c['route_and_weather_merged_into_one_section'] = page.evaluate('''async()=>{
            const r=emptyRace('合併','trail_running','registered','2026-09-06');
            state.races.push(r); selectRace(r.id,{scroll:false});
            await new Promise(s=>setTimeout(s,300));
            const sec=document.getElementById('section-route');
            if(!sec) return false;
            if(!sec.open){ sec.querySelector('summary').click(); await new Promise(s=>setTimeout(s,350)); }
            const live=document.getElementById('section-route');
            const heads=[...live.querySelectorAll(':scope > .subsection > .subsection-head h3')].map(e=>e.textContent.trim());
            const navTargets=[...document.querySelectorAll('.quick-nav a')].map(a=>a.dataset.target);
            return !document.getElementById('section-weather')
                && heads.join(',')==='官方路線,當日氣象'
                && !navTargets.includes('section-weather')
                && navTargets.length===5;
        }''')
        c['section_last_card_has_bottom_breathing_room'] = page.evaluate('''async()=>{
            const r=emptyRace('間距','trail_running','registered','2026-09-06');
            r.budget.totalTwd=2500; r.checkpoints=[{name:'CP1',distanceKm:8}];
            state.races.push(r); selectRace(r.id,{scroll:false});
            await new Promise(s=>setTimeout(s,300));
            const out=[];
            for(const id of ['section-basic','section-logistics','section-prep','section-route']){
              const sec=document.getElementById(id); if(!sec) continue;
              if(!sec.open){ sec.querySelector('summary').click(); await new Promise(s=>setTimeout(s,350)); }
              const live=document.getElementById(id);
              const kids=[...live.children].filter(e=>e.tagName!=='SUMMARY');
              const last=kids[kids.length-1]; if(!last) continue;
              const sb=live.getBoundingClientRect(), lb=last.getBoundingClientRect();
              out.push({id,bottom:sb.bottom-lb.bottom,left:lb.left-sb.left});
            }
            // 下緣間距要存在，而且跟左右內距同一個量級（不是 0、也不是兩倍）
            return out.length>=3 && out.every(x=>x.bottom>=12 && x.bottom<=x.left+4);
        }''')
        # ---- 行事曆：運動別底圖與放大的名稱 ----
        c['calendar_chip_tint_per_sport'] = page.evaluate('''async()=>{
            state.races=[];
            const add=(name,sport,day)=>state.races.push(emptyRace(name,sport,'registered','2026-12-'+String(day).padStart(2,'0')));
            add('路跑','road_running',3); add('越野','trail_running',5); add('超馬','ultra_marathon',7);
            add('二鐵','duathlon',9); add('三鐵','triathlon',11); add('自行車','cycling',13);
            add('游泳','swimming',15); add('障礙','obstacle_race',17);
            state.calendarYear=2026; state.calendarMonth=11; renderCalendar();
            await new Promise(s=>setTimeout(s,300));
            const chips=[...document.querySelectorAll('.cal-chip')];
            if(chips.length<8) return false;
            // 每一種運動別都要帶到自己的底圖變數，而且實際算出來的背景色互不相同
            const tints=chips.map(ch=>ch.style.getPropertyValue('--chip-tint'));
            const resolved=chips.map(ch=>getComputedStyle(ch).backgroundColor);
            const uniqueResolved=new Set(resolved);
            return tints.every(t=>/--sport-bg-/.test(t))
                && tints.some(t=>t.includes('road_running')) && tints.some(t=>t.includes('triathlon'))
                && uniqueResolved.size>=7
                && resolved.every(v=>v!=='rgba(0, 0, 0, 0)');
        }''')
        c['calendar_chip_text_is_larger_and_wraps'] = page.evaluate('''()=>{
            const chip=document.querySelector('.cal-chip');
            const text=chip.querySelector('.cal-chip-text');
            const size=parseFloat(getComputedStyle(chip).fontSize);
            const cs=getComputedStyle(text);
            return size>=15 && cs.webkitLineClamp==='2' && cs.overflow==='hidden';
        }''')
        # 選取狀態的底色要蓋過運動別底圖（行內變數很容易贏過 class）
        c['calendar_selected_chip_overrides_tint'] = page.evaluate('''async()=>{
            const first=state.races[0];
            selectRace(first.id,{scroll:false});
            await new Promise(s=>setTimeout(s,300));
            const sel=document.querySelector('.cal-chip.selected');
            if(!sel) return false;
            const bg=getComputedStyle(sel).backgroundColor;
            const ink=getComputedStyle(document.documentElement).getPropertyValue('--ink').trim();
            // --ink 是 hex，換算成 rgb 來比
            const toRgb=h=>{const v=parseInt(h.slice(1),16);return `rgb(${(v>>16)&255}, ${(v>>8)&255}, ${v&255})`;};
            return bg===toRgb(ink);
        }''')
        # 同一天多場賽事不可以撐出格子
        c['calendar_multiple_chips_stay_in_cell'] = page.evaluate('''async()=>{
            state.races=[];
            ['road_running','trail_running','swimming'].forEach((sp,i)=>
              state.races.push(emptyRace('賽事'+i,sp,'registered','2026-12-19')));
            state.calendarYear=2026; state.calendarMonth=11; renderCalendar();
            await new Promise(s=>setTimeout(s,300));
            const cell=[...document.querySelectorAll('.cal-cell,.cal-day')].find(c2=>c2.querySelector('.cal-chip'));
            const chips=cell.querySelectorAll('.cal-chip');
            const cb=cell.getBoundingClientRect();
            const last=chips[chips.length-1].getBoundingClientRect();
            return chips.length>=1 && last.bottom<=cb.bottom+1;
        }''')
        c['empty_drawer_cards_muted_filled_cards_not'] = page.evaluate('''async()=>{
            const r=emptyRace('卡片','road_running','registered','2026-11-01');
            r.location.city='臺北市'; r.route.distanceKm=42.195;
            state.races.push(r); selectRace(r.id,{scroll:false});
            await new Promise(s=>setTimeout(s,300));
            const cls=sec=>document.querySelector('.dash-card[data-section="'+sec+'"]').classList.contains('is-empty');
            return cls('basicInfo')===false && cls('route')===false
                && cls('goals')===true && cls('review')===true && cls('equipment')===true;
        }''')
        c['empty_card_is_shorter_than_filled_card'] = page.evaluate('''()=>{
            const filled=document.querySelector('.dash-card[data-section="basicInfo"]').getBoundingClientRect().height;
            const empty=document.querySelector('.dash-card[data-section="goals"]').getBoundingClientRect().height;
            return empty<filled;
        }''')
        # ---- 1c：完賽賽事的成績儀表板貼在 header 下方、區段列之前，且只出現一次 ----
        c['completed_race_nav_then_hero_then_sections'] = page.evaluate('''async()=>{
            const r=emptyRace('完賽','road_running','completed','2026-05-01');
            r.results.chipTimeSeconds=10771; r.route.distanceKm=42.195;
            state.races.push(r); selectRace(r.id,{scroll:false});
            await new Promise(s=>setTimeout(s,300));
            const hero=document.querySelector('.hero-results'), nav=document.querySelector('.quick-nav');
            const header=document.querySelector('.detail-header');
            // v3.34.0：順序是 header → 區段導覽列 → 儀表板 → 各區段
            const firstSection=document.querySelector('details.section');
            const order=hero&&nav&&header&&firstSection
                && (header.compareDocumentPosition(nav)&Node.DOCUMENT_POSITION_FOLLOWING)
                && (nav.compareDocumentPosition(hero)&Node.DOCUMENT_POSITION_FOLLOWING)
                && (hero.compareDocumentPosition(firstSection)&Node.DOCUMENT_POSITION_FOLLOWING);
            return !!order && document.querySelectorAll('.results-dashboard').length===1
                && !document.querySelector('#section-post .results-dashboard');
        }''')
        # 雷達圖是 canvas，切主題不會自動換色——切到深色後必須重畫成亮字
        c['radar_redraws_with_light_text_in_dark_mode'] = page.evaluate('''async()=>{
            document.documentElement.setAttribute('data-theme','light'); applyTheme('light');
            const r=emptyRace('雷達','trail_running','completed','2026-05-01');
            r.results.chipTimeSeconds=12000; r.route.distanceKm=23.9; r.route.elevationGainM=824;
            r.performanceData.avgHr=150; r.performanceData.maxHr=180; r.raceDayWeather.feelsLikeTempC=29.2;
            r.splits=Array.from({length:23},(_,i)=>({distanceKm:1,avgPaceSecPerKm:480+i*3,elevationGainM:30}));
            state.races.push(r); selectRace(r.id,{scroll:false});
            await new Promise(s=>setTimeout(s,1300));   // 等生長動畫畫完
            const cv=document.querySelector('canvas[data-race-radar]'); if(!cv) return false;
            const bright=()=>{
              const ctx=cv.getContext('2d'); const d=ctx.getImageData(0,0,cv.width,Math.round(cv.height*0.14)).data;
              let n=0; for(let i=0;i<d.length;i+=4){ if(d[i+3]>0 && (d[i]+d[i+1]+d[i+2])/3>200) n++; } return n; };
            const lightModeBright=bright();          // 淺色模式：深字，亮像素應該很少
            applyTheme('dark');
            await new Promise(s=>setTimeout(s,100));
            const darkModeBright=bright();           // 深色模式重畫後：亮字
            applyTheme('light');
            return darkModeBright>lightModeBright*3 && darkModeBright>50;
        }''')
        # 網格線在深色模式要看得見：灰階、中等亮度的像素要夠多（--rule 幾乎跟底色同色時不會過）
        c['radar_grid_visible_in_dark_mode'] = page.evaluate('''async()=>{
            applyTheme('dark'); await new Promise(s=>setTimeout(s,150));
            const cv=document.querySelector('canvas[data-race-radar]'); if(!cv) return false;
            const d=cv.getContext('2d').getImageData(0,0,cv.width,cv.height).data;
            let grid=0;
            for(let i=0;i<d.length;i+=4){
              const r=d[i],g=d[i+1],b=d[i+2],a=d[i+3];
              if(a<40) continue;
              const lum=(r+g+b)/3;
              if(Math.abs(r-g)<22 && Math.abs(g-b)<28 && lum>=70 && lum<=200) grid++;
            }
            applyTheme('light');
            return grid>800;
        }''')
        # ---- 成績儀表板顯示距離 ----
        c['results_dashboard_shows_distance_first'] = page.evaluate('''()=>{
            const r=emptyRace('半馬','road_running','completed','2026-05-01');
            r.route.distanceKm=21.0975; r.results.chipTimeSeconds=5185; r.results.overallRank=65;
            const d=document.createElement('div'); d.innerHTML=renderResultsDashboard(r);
            const rows=[...d.querySelectorAll('.results-badge')].map(b=>
              b.querySelector('.results-badge-label').textContent+'='+b.querySelector('.results-badge-value').textContent.trim());
            return rows[0]==='距離=21.0975 公里' && rows.some(x=>x.startsWith('配速='));
        }''')
        # 距離不能被四捨五入掉，整數也不要拖尾零
        c['results_distance_formats_precisely'] = page.evaluate('''()=>{
            const val=km=>{ const r=emptyRace('x','road_running','completed','2026-05-01');
              r.route.distanceKm=km; r.results.chipTimeSeconds=5185;
              const d=document.createElement('div'); d.innerHTML=renderResultsDashboard(r);
              return d.querySelector('.results-badge-value').textContent.trim(); };
            return val(21.0975)==='21.0975 公里' && val(42.195)==='42.195 公里'
                && val(10)==='10 公里' && val(23.400000000000002)==='23.4 公里';
        }''')
        # 多項運動與游泳不顯示配速，但距離照樣要有
        c['results_distance_shown_for_multisport_and_swim'] = page.evaluate('''()=>{
            const tri=emptyRace('三鐵','triathlon','completed','2026-05-01');
            tri.route.distanceKm=113; tri.results.chipTimeSeconds=19000;
            tri.legs=[{order:1,sport:'swimming',distanceKm:1.9,durationSeconds:2000},
                      {order:2,sport:'cycling',distanceKm:90,durationSeconds:11000}];
            const swim=emptyRace('泳渡','swimming','completed','2026-05-01');
            swim.route.distanceKm=2.5; swim.results.chipTimeSeconds=4200;
            const rows=r=>{ const d=document.createElement('div'); d.innerHTML=renderResultsDashboard(r);
              return [...d.querySelectorAll('.results-badge')].map(b=>b.querySelector('.results-badge-label').textContent); };
            const triRows=rows(tri), swimRows=rows(swim);
            return triRows[0]==='距離' && !triRows.includes('配速')
                && swimRows[0]==='距離' && swimRows.includes('配速');
        }''')
        # 沒填距離就不要出現這一格
        c['results_distance_absent_when_unset'] = page.evaluate('''()=>{
            const r=emptyRace('沒距離','road_running','completed','2026-05-01');
            r.results.chipTimeSeconds=5185;
            const d=document.createElement('div'); d.innerHTML=renderResultsDashboard(r);
            return [...d.querySelectorAll('.results-badge-label')].every(x=>x.textContent!=='距離');
        }''')
        c['uncompleted_race_has_no_hero_dashboard'] = page.evaluate('''async()=>{
            const r=emptyRace('未完賽','road_running','registered','2026-12-01');
            r.route.distanceKm=10;
            state.races.push(r); selectRace(r.id,{scroll:false});
            await new Promise(s=>setTimeout(s,300));
            return !document.querySelector('.hero-results') && !document.querySelector('.results-dashboard');
        }''')


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
        # ---- Firestore 分批同步（原本全部塞一個 batch，超過 11MB 整批失敗）----
        c['sync_chunks_by_byte_budget'] = page.evaluate('''()=>{
            // 每場約 900KB（在單一文件上限之內），8 場共 7.2MB > 單批 5MB 預算
            const big='x'.repeat(900000);
            const races=Array.from({length:8},(_,i)=>({id:'r'+i,name:'賽事'+i,coverImage:big}));
            const {chunks,oversized}=chunkRacesForSync(races);
            const total=chunks.reduce((s,c2)=>s+c2.length,0);
            const sizes=chunks.map(c2=>c2.reduce((s,r)=>s+JSON.stringify(r).length,0));
            return chunks.length>=2 && total===8 && oversized.length===0
                && sizes.every(v=>v<=FS_BATCH_BYTES+950000);   // 每批都在預算附近，不會整包擠在一批
        }''')
        c['sync_chunks_by_operation_count'] = page.evaluate('''()=>{
            const races=Array.from({length:1000},(_,i)=>({id:'r'+i,name:'x'}));
            const {chunks}=chunkRacesForSync(races);
            return chunks.length>=3 && chunks.every(c2=>c2.length<=FS_BATCH_OPS)
                && chunks.reduce((s,c2)=>s+c2.length,0)===1000;
        }''')
        # 單一場超過文件上限 → 跳過它，其餘照常同步（不能因為一場壞掉全部不上去）
        c['sync_skips_oversized_race_but_keeps_rest'] = page.evaluate('''()=>{
            const huge={id:'huge',name:'爆量賽事',coverImage:'y'.repeat(1200000)};
            const ok1={id:'a',name:'正常一'}, ok2={id:'b',name:'正常二'};
            const {chunks,oversized}=chunkRacesForSync([ok1,huge,ok2]);
            const ids=chunks.flat().map(r=>r.id);
            return oversized.length===1 && oversized[0].race.id==='huge'
                && ids.join(',')==='a,b';
        }''')
        c['sync_empty_input_is_safe'] = page.evaluate('''()=>{
            const a=chunkRacesForSync([]), b=chunkRacesForSync(null);
            return a.chunks.length===0 && a.oversized.length===0
                && b.chunks.length===0 && b.oversized.length===0;
        }''')
        # replaceAll 要真的送出多個 batch，而不是一個
        # 有賽事被跳過時，呼叫端一定要跳出提示——不能默默少同步幾場
        c['sync_reports_skipped_races_to_user'] = page.evaluate('''async()=>{
            const realCloud=window.__cloud, realUser=state.user;
            state.user={uid:'u1'};
            window.__cloud={enabled:true,
              replaceAll:async()=>({batches:1,oversized:[{race:{name:'爆量賽事'},size:2000000}]}),
              syncGlobalLists:async()=>{}, logFeatureUse:async()=>{}};
            document.querySelectorAll('.foreground-toast').forEach(n=>n.remove());
            try{ await cloudSyncAllRaces(); }finally{ window.__cloud=realCloud; state.user=realUser; }
            await new Promise(s=>setTimeout(s,200));
            const txt=[...document.querySelectorAll('.foreground-toast')].map(n=>n.textContent).join(' ');
            return txt.includes('爆量賽事') && txt.includes('1');
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
        # 桌機的 Ctrl/⌘＋滾輪是瀏覽器縮放（無障礙），不能被攔（v3.33.0 拿掉攔截）
        # 觸控裝置上開彈窗不能對整個主內容套 filter:blur——iOS 會因為圖層太大把分頁殺掉
        c['overlay_open_does_not_blur_main_on_touch'] = page.evaluate('''()=>{
            document.body.classList.add('overlay-open');
            const cs=getComputedStyle(document.getElementById('main-content'));
            const filter=cs.filter, transform=cs.transform;
            document.body.classList.remove('overlay-open');
            return filter==='none' && transform!=='none';   // 縮放景深保留，模糊拿掉
        }''')
        c['ctrl_wheel_zoom_not_blocked'] = page.evaluate('''()=>{
            const a=new WheelEvent('wheel',{cancelable:true,bubbles:true,ctrlKey:true});
            const b=new WheelEvent('wheel',{cancelable:true,bubbles:true,metaKey:true});
            document.dispatchEvent(a); document.dispatchEvent(b);
            return !a.defaultPrevented && !b.defaultPrevented;
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
        # ---- 3a：搜尋框打 > 直接變指令面板 ----
        c['search_gt_opens_command_palette_with_text'] = page.evaluate('''async()=>{
            const s=document.getElementById('search-input');
            s.value='>回顧'; s.dispatchEvent(new Event('input',{bubbles:true}));
            await new Promise(r=>setTimeout(r,200));
            const palette=document.getElementById('command-palette');
            const ci=document.getElementById('cmdk-input');
            const rows=[...document.querySelectorAll('.cmdk-row-label')].map(e=>e.textContent);
            const ok=!palette.hidden && ci.value==='>回顧' && s.value==='' && rows.length>0;
            cmdkClose(); return ok;
        }''')
        # ---- 3c：長按卡片彈出快速動作，放開手指不會順便開詳情頁 ----
        c['long_press_card_opens_context_sheet'] = page.evaluate('''async()=>{
            state.races=[]; state.selectedId=null; currentRace=null;
            const r=emptyRace('長按我','road_running','completed','2026-03-01');
            r.results.chipTimeSeconds=3600; r.route.distanceKm=10;
            state.races.push(r); state.viewMode='calendar';
            state.calendarYear=2026; state.calendarMonth=2; renderAll();
            await new Promise(s=>setTimeout(s,300));
            const card=document.querySelector('.cal-list-item[data-id="'+r.id+'"], .cal-chip[data-id="'+r.id+'"]');
            if(!card) return false;
            const rect=card.getBoundingClientRect();
            const opts={bubbles:true,pointerType:'touch',isPrimary:true,clientX:rect.x+20,clientY:rect.y+10,pointerId:1};
            card.dispatchEvent(new PointerEvent('pointerdown',opts));
            await new Promise(s=>setTimeout(s,700));
            card.dispatchEvent(new PointerEvent('pointerup',opts));
            card.dispatchEvent(new MouseEvent('click',{bubbles:true,clientX:opts.clientX,clientY:opts.clientY}));
            await new Promise(s=>setTimeout(s,150));
            const sheet=document.getElementById('race-context-sheet');
            const opened=!sheet.hidden && !!sheet.querySelector('[data-ctx="duplicate"]') && !!sheet.querySelector('[data-ctx="share"]');
            const notNavigated=state.selectedId!==r.id;
            return opened && notNavigated;
        }''')
        c['context_sheet_duplicate_and_delete_work'] = page.evaluate('''async()=>{
            const before=state.races.filter(x=>!x.deletedAt).length;
            document.querySelector('#race-context-sheet [data-ctx="duplicate"]').click();
            await new Promise(s=>setTimeout(s,300));
            const afterDup=state.races.filter(x=>!x.deletedAt).length;
            const copy=state.races.find(x=>x.id===state.selectedId);
            openRaceContextSheet(copy.id); await new Promise(s=>setTimeout(s,100));
            document.querySelector('#race-context-sheet [data-ctx="delete"]').click();
            await new Promise(s=>setTimeout(s,300));
            const afterDel=state.races.filter(x=>!x.deletedAt).length;
            const soft=!!state.races.find(x=>x.id===copy.id&&x.deletedAt);
            return afterDup===before+1 && afterDel===before && soft;
        }''')
        # 短按（未達 550ms）不能觸發
        c['short_tap_does_not_open_context_sheet'] = page.evaluate('''async()=>{
            const r=state.races.find(x=>!x.deletedAt); state.selectedId=null; currentRace=null;
            state.calendarYear=2026; state.calendarMonth=2; renderAll();
            await new Promise(s=>setTimeout(s,200));
            const card=document.querySelector('.cal-list-item[data-id="'+r.id+'"], .cal-chip[data-id="'+r.id+'"]');
            if(!card) return false;
            const rect=card.getBoundingClientRect();
            const opts={bubbles:true,pointerType:'touch',isPrimary:true,clientX:rect.x+20,clientY:rect.y+10,pointerId:1};
            card.dispatchEvent(new PointerEvent('pointerdown',opts));
            await new Promise(s=>setTimeout(s,150));
            card.dispatchEvent(new PointerEvent('pointerup',opts));
            await new Promise(s=>setTimeout(s,600));
            return document.getElementById('race-context-sheet').hidden;
        }''')
        # ---- 3b：詳情頁左右滑切換區段 ----
        c['section_swipe_moves_to_next_section'] = page.evaluate('''async()=>{
            const r=state.races.find(x=>!x.deletedAt);
            selectRace(r.id,{scroll:false}); await new Promise(s=>setTimeout(s,400));
            navigateToSection('section-basic'); await new Promise(s=>setTimeout(s,500));
            const before=currentSectionIndex();
            const el=document.getElementById('detail');
            const mk=(type,x,y)=>{
              const touch=new Touch({identifier:1,target:el,clientX:x,clientY:y});
              return new TouchEvent(type,{bubbles:true,cancelable:true,touches:type==='touchend'?[]:[touch],changedTouches:[touch]});
            };
            const target=document.querySelector('#section-basic')||el;
            target.dispatchEvent(mk('touchstart',300,400));
            target.dispatchEvent(mk('touchmove',260,404));
            target.dispatchEvent(mk('touchmove',150,410));
            target.dispatchEvent(mk('touchend',140,412));
            await new Promise(s=>setTimeout(s,700));
            const active=document.querySelector('.quick-nav a.active');
            return before===0 && !!active && active.dataset.target==='section-route';
        }''')
        c['section_swipe_ignores_vertical_scroll'] = page.evaluate('''async()=>{
            navigateToSection('section-basic'); await new Promise(s=>setTimeout(s,500));
            const el=document.getElementById('detail');
            const mk=(type,x,y)=>{
              const touch=new Touch({identifier:1,target:el,clientX:x,clientY:y});
              return new TouchEvent(type,{bubbles:true,cancelable:true,touches:type==='touchend'?[]:[touch],changedTouches:[touch]});
            };
            const target=document.querySelector('#section-basic')||el;
            target.dispatchEvent(mk('touchstart',300,400));
            target.dispatchEvent(mk('touchmove',280,470));
            target.dispatchEvent(mk('touchmove',150,600));
            target.dispatchEvent(mk('touchend',140,620));
            await new Promise(s=>setTimeout(s,400));
            const active=document.querySelector('.quick-nav a.active');
            return !!active && active.dataset.target==='section-basic';
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
        # ---- 5a：時間欄位驗證 ----
        c['duration_parser_accepts_human_formats'] = page.evaluate('''()=>
            hmsToSec('3:44:25')===13465 && hmsToSec('44:25')===2665 && hmsToSec('3.44.25')===13465
         && hmsToSec('3 44 25')===13465 && hmsToSec('3h44m25s')===13465 && hmsToSec('3時44分25秒')===13465
         && hmsToSec("4'15\\"")===255 && hmsToSec('３：４４：２５'.replace(/[０-９]/g,d=>String.fromCharCode(d.charCodeAt(0)-0xFEE0)))===13465
         && hmsToSec('1:30:25.6')===5426 && hmsToSec('')===null && hmsToSec('abc')===null
         && hmsToSec('3:xx:25')===null && hmsToSec('1:2:3:4')===null
        ''')
        c['invalid_duration_keeps_stored_value_and_shows_hint'] = page.evaluate('''async()=>{
            const r=emptyRace('驗證','road_running','completed','2026-04-01');
            r.results.chipTimeSeconds=13465; r.route.distanceKm=42.195;
            state.races.push(r); selectRace(r.id,{scroll:false});
            await new Promise(s=>setTimeout(s,300));
            openDrawer('results'); await new Promise(s=>setTimeout(s,300));
            const inp=document.querySelector('input[data-path="results.chipTimeSeconds"]');
            if(!inp) return false;
            inp.value='三小時'; inp.dispatchEvent(new Event('input',{bubbles:true}));
            inp.dispatchEvent(new Event('change',{bubbles:true}));
            await new Promise(s=>setTimeout(s,200));
            const hint=inp.closest('.field').querySelector('.field-hint-live');
            return r.results.chipTimeSeconds===13465 && inp.getAttribute('aria-invalid')==='true'
                && !!hint && hint.classList.contains('is-error');
        }''')
        c['ambiguous_duration_shows_normalised_value'] = page.evaluate('''async()=>{
            const inp=document.querySelector('input[data-path="results.chipTimeSeconds"]');
            inp.value='44:25'; inp.dispatchEvent(new Event('input',{bubbles:true}));
            await new Promise(s=>setTimeout(s,100));
            const hint=inp.closest('.field').querySelector('.field-hint-live');
            const shows=!!hint && hint.textContent.includes('0:44:25') && !hint.classList.contains('is-error');
            inp.dispatchEvent(new Event('change',{bubbles:true}));
            await new Promise(s=>setTimeout(s,200));
            return shows && currentRace.results.chipTimeSeconds===2665 && inp.value==='0:44:25';
        }''')
        # ---- 5b：匯入預覽逐欄標示 ----
        c['import_preview_flags_every_overwritten_field'] = page.evaluate('''()=>{
            currentRace.route.elevationGainM=180; currentRace.performanceData.avgHr=150;
            currentRace.performanceData.maxHr=175; currentRace.performanceData.avgCadence=170;
            currentRace.splits=[{},{},{}];
            const html=gpxSummaryHtml({distanceKm:42.2,elevationGainM:220,durationSeconds:10771,
                                       avgHr:160,maxHr:182,avgCadence:88,splits:[{},{}]},'x.fit');
            const notes=(html.match(/gpx-overwrite-note/g)||[]).length;
            return notes>=7 && html.includes('180 公尺') && html.includes('150 bpm')
                && html.includes('175 bpm') && html.includes('170 spm') && html.includes('3 段');
        }''')
        c['import_preview_silent_when_nothing_changes'] = page.evaluate('''()=>{
            const html=gpxSummaryHtml({distanceKm:currentRace.route.distanceKm,elevationGainM:180,
                durationSeconds:currentRace.results.chipTimeSeconds,avgHr:150,maxHr:175,avgCadence:null,splits:[]},'x.gpx');
            return !html.includes('gpx-overwrite-note');
        }''')
        # ---- 照片縮圖依 EXIF 方向轉正 ----
        # 做一張 40×20、左上角一塊紅的縮圖，各方向碼轉完後紅塊該在哪個角、
        # 畫布寬高該不該對調，逐一驗。3＝倒著拍（使用者回報的那種）。
        c['thumbnail_orientation_matrix_correct'] = page.evaluate('''async()=>{
            const src=document.createElement('canvas'); src.width=40; src.height=20;
            const x=src.getContext('2d'); x.fillStyle='#fff'; x.fillRect(0,0,40,20); x.fillStyle='#f00'; x.fillRect(0,0,8,8);
            const blob=await new Promise(r=>src.toBlob(r,'image/png'));
            const cornerOf=(url)=>new Promise(res=>{ const img=new Image(); img.onload=()=>{
                const c=document.createElement('canvas'); c.width=img.width; c.height=img.height;
                const g=c.getContext('2d'); g.drawImage(img,0,0);
                const red=(px,py)=>{ const d=g.getImageData(px,py,1,1).data; return d[0]>200&&d[1]<80&&d[2]<80; };
                const W=img.width,H=img.height;
                res({W,H,tl:red(2,2),tr:red(W-3,2),bl:red(2,H-3),br:red(W-3,H-3)}); }; img.src=url; });
            const o1=await cornerOf(await orientThumbnail(blob,1));
            const o3=await cornerOf(await orientThumbnail(blob,3));
            const o6=await cornerOf(await orientThumbnail(blob,6));
            const o8=await cornerOf(await orientThumbnail(blob,8));
            return o1.W===40&&o1.tl
                && o3.W===40&&o3.br&&!o3.tl            // 180°：左上 → 右下
                && o6.W===20&&o6.H===40&&o6.tr         // 90° CW：寬高對調，左上 → 右上
                && o8.W===20&&o8.H===40&&o8.bl;        // 270° CW：左上 → 左下
        }''')
        # exifr 可能給數字也可能給翻譯字串，兩種都要對
        c['exif_orientation_string_and_number_both_parsed'] = page.evaluate('''async()=>{
            const keep=window.exifr; window.exifr={};   // 沒有 orientation()，逼它走 tags 路徑
            try{
                const a=await readExifOrientation(null,{Orientation:3});
                const b=await readExifOrientation(null,{Orientation:'Rotate 90 CW'});
                const c2=await readExifOrientation(null,{Orientation:'Rotate 180'});
                const d=await readExifOrientation(null,{Orientation:'Horizontal (normal)'});
                const e=await readExifOrientation(null,{Orientation:'garbage'});
                return a===3&&b===6&&c2===3&&d===1&&e===1;
            } finally { window.exifr=keep; }
        }''')
        # ---- 照片加入失敗要說明原因，不是靜默略過 ----
        c['photo_without_capture_time_is_reported'] = page.evaluate('''async()=>{
            const r=emptyRace('照片','trail_running','completed','2026-05-01');
            const t0=Date.parse('2026-05-01T08:00:00Z');
            r.route.timedTrackPoints=Array.from({length:60},(_,i)=>({lat:25+i*0.001,lon:121+i*0.001,timeMs:t0+i*60000,elevationM:100+i,hr:150}));
            state.races.push(r); selectRace(r.id,{scroll:false});
            await new Promise(s=>setTimeout(s,200));
            const keep=window.exifr;
            window.exifr={ parse:async f=>f.name==='screenshot.png'?{}:{DateTimeOriginal:new Date(t0+600000)},
                           thumbnail:async()=>null };
            const mk=n=>new File([new Uint8Array([1,2,3])],n,{type:'image/png'});
            try{ await processPhotoFiles(r,[mk('good.jpg'),mk('screenshot.png')]); }
            finally{ window.exifr=keep; }
            const skipped=photoSkipReport.map(x=>x.fileName+':'+x.reason).join(',');
            return r.geoPhotos.length===1 && r.geoPhotos[0].fileName==='good.jpg'
                && skipped==='screenshot.png:noTime';
        }''')
        c['skip_report_rendered_and_dismissable'] = page.evaluate('''async()=>{
            renderDetail(); await new Promise(s=>setTimeout(s,150));
            const box=document.querySelector('.geo-photo-skipped');
            const shown=!!box && box.textContent.includes('screenshot.png');
            document.querySelector('[data-action="dismiss-photo-skip"]').click();
            await new Promise(s=>setTimeout(s,150));
            return shown && photoSkipReport.length===0 && !document.querySelector('.geo-photo-skipped');
        }''')
        # 沒有內嵌縮圖時自己產生一張，而不是留空
        c['thumbnail_falls_back_to_decoding_the_file'] = page.evaluate('''async()=>{
            const src=document.createElement('canvas'); src.width=800; src.height=600;
            const x=src.getContext('2d'); x.fillStyle='#4a7'; x.fillRect(0,0,800,600);
            const blob=await new Promise(r=>src.toBlob(r,'image/png'));
            const file=new File([blob],'nothumb.png',{type:'image/png'});
            const url=await thumbnailFromFullImage(file);
            if(!url||!url.startsWith('data:image/jpeg')) return false;
            const dims=await new Promise(res=>{const i=new Image(); i.onload=()=>res([i.width,i.height]); i.src=url;});
            return dims[0]===320 && dims[1]===240;   // 解碼階段就縮到 320 寬
        }''')
        # 選擇器與拖曳都要放行 HEIC
        c['heic_accepted_by_picker_and_drop'] = page.evaluate('''()=>{
            const input=document.getElementById('geo-photo-input');
            const accept=input?input.getAttribute('accept'):'';
            return /heic/i.test(accept) && /image\\/\\*/.test(accept);
        }''')
        # ---- 表格檢視依年份收合 ----
        c['table_groups_by_year_default_current_open'] = page.evaluate('''async()=>{
            tableExpandedYears=null;
            state.races=[]; state.selectedId=null; currentRace=null;
            const mk=(name,date,st,km)=>{ const r=emptyRace(name,'road_running',st,date);
                if(km) r.route.distanceKm=km; if(st==='completed') r.results.chipTimeSeconds=3600;
                state.races.push(r); return r; };
            mk('今年A','2026-03-01','completed',10); mk('今年B','2026-10-01','registered',21.1);
            mk('去年','2025-05-01','completed',42.195); mk('明年','2027-01-31','registered',42.2);
            state.viewMode='table'; renderCalendar();
            await new Promise(s=>setTimeout(s,200));
            const headers=[...document.querySelectorAll('.table-year-row')].map(e=>e.dataset.year+(e.classList.contains('open')?':open':':closed'));
            const visibleRows=document.querySelectorAll('.table-view-row').length;
            return headers.join(',')==='2027:closed,2026:open,2025:closed' && visibleRows===2;
        }''')
        c['table_year_header_shows_summary_and_toggles'] = page.evaluate('''async()=>{
            const h2025=document.querySelector('.table-year-row[data-year="2025"]');
            const summaryOk=h2025.textContent.includes('1 場')&&h2025.textContent.includes('完賽 1')&&h2025.textContent.includes('42.2 km');
            h2025.click(); await new Promise(s=>setTimeout(s,200));
            const opened=document.querySelectorAll('.table-view-row').length===3;
            document.querySelector('.table-year-row[data-year="2026"]').click();
            await new Promise(s=>setTimeout(s,200));
            const closed=[...document.querySelectorAll('.table-view-row')].every(r=>r.querySelector('td').textContent.startsWith('2025'));
            return summaryOk && opened && closed;
        }''')
        c['selected_race_year_forced_open'] = page.evaluate('''async()=>{
            const r2027=state.races.find(r=>r.schedule.raceDate==='2027-01-31');
            state.selectedId=r2027.id; renderCalendar();
            await new Promise(s=>setTimeout(s,200));
            const h=document.querySelector('.table-year-row[data-year="2027"]');
            const row=document.querySelector('.table-view-row.selected');
            return h.classList.contains('open') && !!row && row.dataset.id===r2027.id;
        }''')
        # 地圖照片卡片要整個放得進地圖裡（直立照最容易超出）
        c['geo_photo_popup_fits_inside_map'] = page.evaluate('''async()=>{
            const portrait=document.createElement('canvas'); portrait.width=600; portrait.height=800;
            const g=portrait.getContext('2d'); g.fillStyle='#567'; g.fillRect(0,0,600,800);
            const probe=document.createElement('div');
            probe.className='route-map';
            probe.style.cssText='position:absolute;left:-9999px;top:0;';
            probe.innerHTML='<div class="leaflet-popup-content-wrapper"><div class="leaflet-popup-content">'
              +geoPhotoPopupHtml({thumbnailDataUrl:portrait.toDataURL('image/png'),
                  rawCapturedAt:new Date().toISOString(),elevationM:240,hr:175,paceSecPerKm:253})
              +'</div></div>';
            document.body.appendChild(probe);
            const img=probe.querySelector('.geo-photo-popup-img');
            await new Promise(res=>{ if(img.complete) res(); else img.onload=res; });
            const cardH=probe.querySelector('.leaflet-popup-content-wrapper').getBoundingClientRect().height;
            const imgBox=img.getBoundingClientRect();
            const statsLines=probe.querySelectorAll('.geo-photo-popup-stats div').length;
            probe.remove();
            // 地圖高 280px，卡片還要留箭頭與上下邊距，抓 240px 當上限
            return cardH<=240 && imgBox.height<=150 && imgBox.width<imgBox.height && statsLines===3;
        }''')
        # ---- 三鐵只有跑步段算進鞋子里程 ----
        c['shoe_mileage_counts_run_leg_only'] = page.evaluate('''()=>{
            shoes.push({id:'sh-tri',name:'測試鞋',targetKm:600,isRetired:false,trainingKm:0});
            state.races=[];
            const tri=emptyRace('CT226','triathlon','completed','2025-04-26');
            tri.route.distanceKm=226; tri.results.chipTimeSeconds=52710; tri.performanceData.shoeId='sh-tri';
            tri.legs=[{order:1,sport:'swimming',distanceKm:3.8,durationSeconds:4500},
                      {order:2,sport:'transition',distanceKm:0,durationSeconds:300},
                      {order:3,sport:'cycling',distanceKm:180,durationSeconds:25000},
                      {order:4,sport:'running',distanceKm:42.195,durationSeconds:22670}];
            state.races.push(tri);
            const run=emptyRace('台北馬','road_running','completed','2025-12-21');
            run.route.distanceKm=42.195; run.results.chipTimeSeconds=12600; run.performanceData.shoeId='sh-tri';
            state.races.push(run);
            const st=computeShoeStats('sh-tri');
            return Math.abs(shoeDistanceOfRace(tri)-42.195)<0.001
                && Math.abs(shoeDistanceOfRace(run)-42.195)<0.001
                && Math.abs(st.raceDistance-84.39)<0.01;
        }''')
        # 多項賽事沒有分項資料時寧可算 0，不要把游泳騎車灌進去
        c['multisport_without_legs_adds_zero_shoe_km'] = page.evaluate('''()=>{
            const tri2=emptyRace('113 無分項','triathlon','completed','2025-06-01');
            tri2.route.distanceKm=113; tri2.results.chipTimeSeconds=21000; tri2.performanceData.shoeId='sh-tri';
            state.races.push(tri2);
            const st=computeShoeStats('sh-tri');
            return shoeDistanceOfRace(tri2)===0 && Math.abs(st.raceDistance-84.39)<0.01;
        }''')
        # 平均配速也要用跑步段，沒有分項資料的多項賽事跳過
        c['shoe_avg_pace_uses_run_leg'] = page.evaluate('''()=>{
            const perf=computeShoePerformanceStats('sh-tri');
            const expect=(22670/42.195+12600/42.195)/2;
            return Math.abs(perf.avgPaceSecPerKm-expect)<0.5;
        }''')
        # ---- 依縣市／行政區自動判別國家 ----
        c['country_guess_taiwan_and_japan'] = page.evaluate('''()=>{
            state.races=[];
            const tw=['宜蘭縣','宜蘭縣礁溪鄉','桃園市','臺北市','台北','新北市板橋區','花蓮縣秀林鄉','金門縣'];
            const jp=['福井県','東京都','北海道','神戸市','沖縄県那覇市','軽井沢町','大阪府大阪市中央区'];
            return tw.every(x=>guessCountryFromCity(x)==='臺灣')
                && jp.every(x=>guessCountryFromCity(x)==='日本');
        }''')
        # 用臺灣字寫的日本地名要判成日本（地名清單優先於後綴規則）
        c['country_name_list_beats_suffix_rule'] = page.evaluate('''()=>{
            state.races=[];
            return guessCountryFromCity('福井縣若狹')==='日本'
                && guessCountryFromCity('宜蘭縣')==='臺灣';
        }''')
        c['country_guess_international'] = page.evaluate('''()=>{
            state.races=[];
            const pairs=[['首爾','韓國'],['서울','韓國'],['香港','香港'],['新加坡','新加坡'],
                         ['Chamonix','法國'],['Boston','美國'],['Sydney','澳洲'],['Tokyo','日本'],
                         ['Kuala Lumpur','馬來西亞'],['北京市','中國'],['廣東省','中國']];
            return pairs.every(([city,want])=>guessCountryFromCity(city)===want);
        }''')
        c['country_guess_returns_null_when_unknown'] = page.evaluate('''()=>{
            state.races=[];
            return guessCountryFromCity('')===null && guessCountryFromCity('未知地名XYZ')===null
                && guessCountryFromCity(null)===null;
        }''')
        # 沿用使用者自己的寫法：他寫「台灣」就不要塞「臺灣」進去
        c['country_reuses_user_spelling'] = page.evaluate('''()=>{
            state.races=[{id:'x',location:{city:'台北市',country:'台灣'},schedule:{}}];
            const a=guessCountryFromCity('桃園市');
            state.races=[{id:'x',location:{city:'Tokyo',country:'Japan'},schedule:{}}];
            const b=guessCountryFromCity('大阪府');
            state.races=[];
            return a==='台灣' && b==='Japan' && guessCountryFromCity('桃園市')==='臺灣';
        }''')
        # 只在國家欄位空著時填，且只由縣市欄位觸發
        c['country_fills_only_when_empty_and_on_city_change'] = page.evaluate('''()=>{
            state.races=[];
            const filled=emptyRace('a','road_running','registered','2026-01-01');
            filled.location.city='福井県'; filled.location.country='日本國';
            const f1=applySmartDefaults(filled,'location.city');
            const empty=emptyRace('b','road_running','registered','2026-01-01');
            empty.location.city='宜蘭縣礁溪鄉';
            const f2=applySmartDefaults(empty,'location.city');
            const other=emptyRace('c','road_running','registered','2026-01-01');
            other.location.city='東京都';
            const f3=applySmartDefaults(other,'name');
            return filled.location.country==='日本國' && !f1.includes('location.country')
                && empty.location.country==='臺灣' && f2.includes('location.country')
                && !(other.location.country||'') && !f3.includes('location.country');
        }''')
        # 實際在表單輸入縣市，國家欄位要跟著出現
        c['country_autofills_through_the_form'] = page.evaluate('''async()=>{
            state.races=[];
            const r=emptyRace('若狹路越野賽','trail_running','registered','2026-09-27');
            state.races.push(r); selectRace(r.id,{scroll:false});
            await new Promise(s=>setTimeout(s,300));
            openDrawer('basicInfo');
            await new Promise(s=>setTimeout(s,500));
            const input=document.querySelector('[data-path="location.city"]');
            input.value='福井県';
            input.dispatchEvent(new Event('change',{bubbles:true}));
            await new Promise(s=>setTimeout(s,800));
            const country=document.querySelector('[data-path="location.country"]');
            return currentRace.location.country==='日本' && country && country.value==='日本';
        }''')
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


class Share(Group):
    """分享圖：設定視窗、兩種版面、勾選項目、分享面板／下載的分流。"""

    SEED = """()=>{
        const pts=[]; for(let i=0;i<120;i++){ const a=i/119*Math.PI*2;
            pts.push({lat:25.04+Math.sin(a)*0.012, lon:121.56+Math.cos(a)*0.016}); }
        shoes.push({id:'sh-share',name:'Alphafly 3',targetKm:600,isRetired:false,trainingKm:0});
        const r=emptyRace('分享測試','road_running','completed','2026-12-20');
        r.route.distanceKm=42.195; r.results.chipTimeSeconds=10771;
        r.performanceData.avgHr=162; r.performanceData.shoeId='sh-share';
        r.nutritionSchedule=[{item:'能量膠',qty:4,consumed:true}];
        r.route.trackPoints=pts;
        state.races.push(r); selectRace(r.id,{scroll:false});
        try{ localStorage.removeItem('share-prefs-v1'); }catch(e){}
        return r.id;
    }"""

    def body(self, page):
        c = self.checks
        page.evaluate(self.SEED)
        c['share_modal_opens_with_format_and_options'] = page.evaluate('''async()=>{
            document.querySelector('[data-action="generate-share-image"]').click();
            await new Promise(s=>setTimeout(s,900));
            const m=document.getElementById('share-modal');
            const opts=[...m.querySelectorAll('[data-share-opt]')].map(i=>i.dataset.shareOpt).sort().join(',');
            const preview=m.querySelector('#share-preview-img');
            return !m.hidden
                && m.querySelectorAll('[data-share-format]').length===2
                && opts==='fuel,hr,qr,shoe,track'   // QR 不依賴賽事資料，永遠在
                && !!preview && preview.src.startsWith('data:image/png');
        }''')
        # 切到限動：預覽要重畫成直式，設定要被記住
        c['share_story_format_switches_preview_and_persists'] = page.evaluate('''async()=>{
            document.querySelector('[data-share-format="story"]').click();
            await new Promise(s=>setTimeout(s,900));
            const img=document.getElementById('share-preview-img');
            const dims=await new Promise(res=>{const i=new Image(); i.onload=()=>res([i.width,i.height]); i.src=img.src;});
            const saved=JSON.parse(localStorage.getItem('share-prefs-v1')||'{}');
            return dims[0]===1080 && dims[1]===1920 && saved.format==='story';
        }''')
        # 關掉軌跡：下半段不能再有金色像素
        c['share_toggle_removes_track'] = page.evaluate('''async()=>{
            const before=await buildShareCanvas(currentRace,{format:'square',show:{track:true}});
            const after =await buildShareCanvas(currentRace,{format:'square',show:{track:false}});
            const gold=cv=>{const d=cv.getContext('2d').getImageData(0,cv.height*0.6,cv.width,cv.height*0.35).data;
                let n=0; for(let i=0;i<d.length;i+=4){ if(d[i]>150&&d[i+1]>130&&d[i]-d[i+2]>40) n++; } return n;};
            return gold(before)>500 && gold(after)<50;
        }''')
        # 沒資料的項目不給勾：一顆永遠沒作用的開關比沒有開關更誤導
        c['share_options_hide_when_data_absent'] = page.evaluate('''async()=>{
            closeShareModal();
            const r=emptyRace('空的','cycling','completed','2026-01-01');
            r.route.distanceKm=90; r.results.chipTimeSeconds=9000;
            state.races.push(r); selectRace(r.id,{scroll:false});
            openShareModal(r); await new Promise(s=>setTimeout(s,700));
            const keys=[...document.querySelectorAll('#share-modal [data-share-opt]')].map(i=>i.dataset.shareOpt);
            closeShareModal();
            return keys.join(',')==='qr';   // 這場什麼都沒有，只剩不挑資料的 QR
        }''')
        # 桌機：一律下載，不走分享面板（就算 navigator.share 存在）
        # ---- 分享圖上的 QR：要真的掃得出來 ----
        c['share_qr_encodes_site_url'] = page.evaluate('''()=>{
            const m=qrMatrix(shareSiteUrl());
            return !!m && m.length>=21 && m.length%4===1;   // 版本 n 的邊長是 17+4n
        }''')
        for fmt in ('square', 'story'):
            data_url = page.evaluate(
                "async(f)=>{const c=await buildShareCanvas(currentRace,{format:f,show:{qr:true}});"
                "return c.toDataURL('image/png');}", fmt)
            raw = base64.b64decode(data_url.split(',')[1])
            img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_GRAYSCALE)
            decoded, _, _ = cv2.QRCodeDetector().detectAndDecode(img)
            c[f'share_qr_scannable_{fmt}'] = decoded.startswith('http')
            # IG 實際送出的解析度大約 640–1080，縮到 640 還要掃得到
            small = cv2.resize(img, (640, int(img.shape[0] * 640 / img.shape[1])),
                               interpolation=cv2.INTER_AREA)
            decoded_small, _, _ = cv2.QRCodeDetector().detectAndDecode(small)
            c[f'share_qr_survives_downscale_{fmt}'] = decoded_small == decoded
        # 關掉 QR 就不該出現任何 QR
        no_qr = page.evaluate(
            "async()=>{const c=await buildShareCanvas(currentRace,{format:'square',show:{qr:false}});"
            "return c.toDataURL('image/png');}")
        img = cv2.imdecode(np.frombuffer(base64.b64decode(no_qr.split(',')[1]), np.uint8),
                           cv2.IMREAD_GRAYSCALE)
        decoded, _, _ = cv2.QRCodeDetector().detectAndDecode(img)
        c['share_qr_toggle_removes_it'] = decoded == ''
        # ---- 文案 ----
        c['share_caption_has_name_time_tags_and_url'] = page.evaluate('''()=>{
            const txt=shareCaptionText(currentRace);
            return txt.includes(currentRace.name)
                && txt.includes(secToHMS(currentRace.results.chipTimeSeconds))
                && /#/.test(txt) && txt.includes(shareSiteUrl())
                && txt.split('\\n').filter(Boolean).length<=6;   // 不要長到被 IG 收起來
        }''')
        c['share_caption_copies_to_clipboard'] = page.evaluate('''async()=>{
            let copied=null;
            const orig=document.execCommand;
            document.execCommand=function(cmd){ if(cmd==='copy'){ copied=document.activeElement&&document.activeElement.value; return true; } return false; };
            const ok=await copyTextToClipboard('測試文案 ABC');
            document.execCommand=orig;
            return ok===true && (copied==='測試文案 ABC' || copied===null);
        }''')
        # ---- 資料不足的分享選項要灰掉並說明原因，不是整個消失 ----
        c['share_unavailable_options_show_reason'] = page.evaluate('''async()=>{
            state.races=[];
            const r=emptyRace('只有成績','road_running','completed','2022-03-20');
            r.route.distanceKm=42.195; r.results.chipTimeSeconds=12317;
            state.races.push(r); selectRace(r.id,{scroll:false});
            await new Promise(s=>setTimeout(s,250));
            openShareModal(r); await new Promise(s=>setTimeout(s,700));
            const el=document.getElementById('share-modal');
            const greyed=[...el.querySelectorAll('.share-opt-unavailable')];
            const txt=el.innerText;
            const enabled=[...el.querySelectorAll('[data-share-opt]')].map(i=>i.dataset.shareOpt);
            closeShareModal();
            return greyed.length===4                      // 心率／戰靴／補給／軌跡都還在畫面上
                && greyed.every(l=>l.querySelector('input').disabled)
                && txt.includes('這場沒綁定鞋款') && txt.includes('沒有 GPX 軌跡')
                && enabled.join(',')==='qr';              // 只有 QR 可以勾
        }''')
        # 資料齊全時四個選項都是可勾的，不會出現「原因」字樣
        c['share_available_options_have_no_reason_text'] = page.evaluate('''async()=>{
            shoes.push({id:'s-opt',name:'測試鞋',targetKm:600,isRetired:false,trainingKm:0});
            const pts=[]; for(let i=0;i<50;i++) pts.push({lat:25+i*0.001,lon:121+i*0.001});
            const r=emptyRace('齊全','road_running','completed','2026-03-20');
            r.route.distanceKm=42.195; r.results.chipTimeSeconds=12317;
            r.performanceData.avgHr=162; r.performanceData.shoeId='s-opt';
            r.route.trackPoints=pts;
            r.nutritionSchedule=[{item:'能量膠',qty:4,consumed:true}];
            state.races.push(r); selectRace(r.id,{scroll:false});
            await new Promise(s=>setTimeout(s,250));
            openShareModal(r); await new Promise(s=>setTimeout(s,700));
            const el=document.getElementById('share-modal');
            const greyed=el.querySelectorAll('.share-opt-unavailable').length;
            const opts=[...el.querySelectorAll('[data-share-opt]')].map(i=>i.dataset.shareOpt).sort().join(',');
            closeShareModal();
            return greyed===0 && opts==='fuel,hr,qr,shoe,track';
        }''')
        # 多項運動的戰靴要說「這個運動種類不顯示」，不是「沒綁鞋款」
        c['share_shoe_reason_differs_for_non_running'] = page.evaluate('''async()=>{
            const tri=emptyRace('三鐵','triathlon','completed','2026-05-01');
            tri.route.distanceKm=113; tri.results.chipTimeSeconds=19000;
            state.races.push(tri); selectRace(tri.id,{scroll:false});
            await new Promise(s=>setTimeout(s,250));
            openShareModal(tri); await new Promise(s=>setTimeout(s,700));
            const txt=document.getElementById('share-modal').innerText;
            closeShareModal();
            return txt.includes('這個運動種類不顯示戰靴') && !txt.includes('這場沒綁定鞋款');
        }''')
        # ---- 生涯回顧下載圖 ----
        CAREER_SEED = '''()=>{
            shoes.push({id:'s1',name:'Nike Alphafly 3',targetKm:600,isRetired:false,trainingKm:120});
            nutritionDictionary.push({id:'n1',name:'GU 能量膠',carbG:22,sodiumMg:60,caffeineMg:20});
            state.races=[];
            const pts=[]; for(let i=0;i<160;i++){const a=i/159*Math.PI*2;
              pts.push({lat:25+Math.sin(a)*0.01,lon:121.5+Math.cos(a)*0.014});}
            const mk=(name,date,km,sec,pb,track)=>{ const r=emptyRace(name,'road_running','completed',date);
              r.route.distanceKm=km; r.results.chipTimeSeconds=sec; r.route.elevationGainM=100;
              if(pb) r.results.isPb=true; if(track) r.route.trackPoints=pts;
              r.performanceData.shoeId='s1';
              r.nutritionSchedule=[{item:'GU 能量膠',qty:4,consumed:true,nutritionId:'n1'}];
              state.races.push(r); };
            mk('大阪馬拉松','2025-02-24',42.195,10774,true,true);
            for(let i=0;i<6;i++) mk('賽事'+i,'202'+(1+i%5)+'-05-11',21.1,7200,false,i<2);
            renderCalendar(); return true;
        }'''
        page.evaluate(CAREER_SEED)
        # 高畫質：輸出寬度是版面寬度的兩倍（2160），不是螢幕解析度
        c['career_canvas_is_high_resolution'] = page.evaluate('''async()=>{
            const c2=await buildCareerCanvas({show:{hero:true,tiles:true,tracks:true,shoes:true,fuel:true,qr:true}});
            return c2.width===2160 && c2.height>1000;
        }''')
        # 每個勾選都要真的改變輸出（高度會變）
        c['career_sections_change_output'] = page.evaluate('''async()=>{
            const h=async show=>(await buildCareerCanvas({show})).height;
            const all=await h({hero:true,tiles:true,tracks:true,shoes:true,fuel:true,qr:true});
            const noTracks=await h({hero:true,tiles:true,tracks:false,shoes:true,fuel:true,qr:true});
            const noHero=await h({hero:false,tiles:true,tracks:true,shoes:true,fuel:true,qr:true});
            const tilesOnly=await h({hero:false,tiles:true,tracks:false,shoes:false,fuel:false,qr:false});
            return noTracks<all && noHero<all && tilesOnly<noTracks && tilesOnly>400;
        }''')
        # PB 時間不可以把 HTML 標籤畫到圖上（secToHMSDenoised 回傳的是 HTML）
        c['career_pb_time_is_plain_text'] = page.evaluate('''async()=>{
            const spy=[];
            const proto=CanvasRenderingContext2D.prototype;
            const orig=proto.fillText;
            proto.fillText=function(txt,...rest){ spy.push(String(txt)); return orig.call(this,txt,...rest); };
            try{ await buildCareerCanvas({show:{hero:true,tiles:true,tracks:false,shoes:false,fuel:false,qr:false}}); }
            finally{ proto.fillText=orig; }
            return spy.includes('2:59:34') && spy.every(x=>!/[<>]/.test(x));
        }''')
        # 資料不足的區塊要灰掉並說明原因，不是整個消失
        c['career_unavailable_sections_show_reason'] = page.evaluate('''async()=>{
            state.races=[];
            const r=emptyRace('只有成績','road_running','completed','2025-05-01');
            r.route.distanceKm=10; r.results.chipTimeSeconds=2400;
            state.races.push(r); renderCalendar();
            openCareerShareModal();
            await new Promise(s=>setTimeout(s,400));
            const el=document.getElementById('career-share-modal');
            const greyed=[...el.querySelectorAll('.share-opt-unavailable')].map(l=>l.textContent);
            const enabled=[...el.querySelectorAll('[data-career-opt]')].map(i=>i.dataset.careerOpt).sort().join(',');
            closeCareerShareModal();
            return greyed.length>=3 && enabled==='qr,tiles'
                && greyed.join(' ').includes('沒有匯入過 GPS 軌跡');
        }''')
        # 勾選狀態要記住（下一次打開沿用）
        c['career_prefs_persist'] = page.evaluate('''async()=>{
            page_dummy=null;
            careerSharePrefs.tracks=true;
            openCareerShareModal();
            await new Promise(s=>setTimeout(s,300));
            const box=document.querySelector('[data-career-opt="qr"]');
            box.checked=false; box.dispatchEvent(new Event('change',{bubbles:true}));
            await new Promise(s=>setTimeout(s,200));
            closeCareerShareModal();
            const saved=JSON.parse(localStorage.getItem('career-share-prefs-v1')||'{}');
            const ok=saved.qr===false && careerSharePrefs.qr===false;
            careerSharePrefs.qr=true;
            try{ localStorage.setItem('career-share-prefs-v1',JSON.stringify(careerSharePrefs)); }catch(e){}
            return ok;
        }''')
        c['share_desktop_downloads_not_share_sheet'] = page.evaluate('''async()=>{
            let shared=0, downloaded=0;
            const origShare=navigator.share, origCan=navigator.canShare, origDl=window.downloadBlob;
            navigator.share=async()=>{shared++;}; navigator.canShare=()=>true;
            window.downloadBlob=()=>{downloaded++;};
            try{ await shareOrDownloadImage(new Blob(['x'],{type:'image/png'}),'t.png'); }
            finally{ navigator.share=origShare; navigator.canShare=origCan; window.downloadBlob=origDl; }
            return shared===0 && downloaded===1;
        }''')


class ShareTouch(Group):
    """觸控裝置上的分享分流：優先系統分享面板，取消不算失敗，失敗退回下載。"""

    def __init__(self):
        super().__init__('share_touch', viewport=PHONE, touch=True)

    STUB = '''(mode)=>{
        window.__dl=0; window.__sh=0;
        window.__orig={share:navigator.share,can:navigator.canShare,dl:window.downloadBlob};
        navigator.canShare=()=>true;
        window.downloadBlob=()=>{window.__dl++;};
        navigator.share=async()=>{
            if(mode==='cancel'){ const e=new Error('cancel'); e.name='AbortError'; throw e; }
            if(mode==='fail') throw new Error('boom');
            window.__sh++;
        };
    }'''
    RESTORE = '''()=>{ navigator.share=window.__orig.share; navigator.canShare=window.__orig.can; window.downloadBlob=window.__orig.dl; }'''
    CALL = '''async()=>shareOrDownloadImage(new Blob(['x'],{type:'image/png'}),'t.png')'''

    def body(self, page):
        c = self.checks
        c['touch_reports_coarse_pointer'] = page.evaluate(
            "()=>window.matchMedia('(pointer: coarse)').matches")
        page.evaluate(self.STUB, 'ok')
        r = page.evaluate(self.CALL)
        c['share_touch_prefers_share_sheet'] = (r == 'shared') and page.evaluate("()=>window.__sh===1&&window.__dl===0")
        page.evaluate(self.RESTORE)
        page.evaluate(self.STUB, 'cancel')
        r = page.evaluate(self.CALL)
        c['share_touch_cancel_is_not_failure'] = (r == 'cancelled') and page.evaluate("()=>window.__dl===0")
        page.evaluate(self.RESTORE)
        page.evaluate(self.STUB, 'fail')
        r = page.evaluate(self.CALL)
        c['share_touch_error_falls_back_to_download'] = (r == 'downloaded') and page.evaluate("()=>window.__dl===1")
        page.evaluate(self.RESTORE)
        c['share_modal_button_says_share_on_touch'] = page.evaluate('''async()=>{
            const o={share:navigator.share,can:navigator.canShare};
            navigator.share=async()=>{}; navigator.canShare=()=>true;
            const r=emptyRace('觸控','road_running','completed','2026-01-01');
            r.route.distanceKm=10; r.results.chipTimeSeconds=2400;
            state.races.push(r); selectRace(r.id,{scroll:false});
            openShareModal(r); await new Promise(s=>setTimeout(s,600));
            const label=document.querySelector('#share-modal [data-action="confirm-share"]').textContent.trim();
            closeShareModal(); navigator.share=o.share; navigator.canShare=o.can;
            return label===t('ui.shareNow','分享');
        }''')


class Offline(Group):
    """離線與可靠性：Service Worker 真的能讓網站離線打開；安裝提示；儲存空間警示。

    SW 不能在 file:// 註冊，所以這組自己起一個本機 http 伺服器，指到
    index.html 所在的資料夾（sw.js 必須跟它同層）。跑完關掉。
    """

    def __init__(self):
        super().__init__('offline')
        self.server = None

    def run(self, browser):
        import http.server, socketserver, threading, functools
        directory = os.path.dirname(os.path.abspath(APP))
        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *a, **k):   # 少一張圖示的 404 不用洗到測試輸出裡
                pass
        handler = functools.partial(Quiet, directory=directory)
        socketserver.TCPServer.allow_reuse_address = True
        self.server = socketserver.TCPServer(('127.0.0.1', 0), handler)
        port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f'http://127.0.0.1:{port}/index.html'
        ctx = browser.new_context(viewport=self.viewport, service_workers='allow')
        page = ctx.new_page()
        page.on('pageerror', lambda e: self.errors.append(str(e)))
        page.goto(self.url)
        page.wait_for_timeout(800)
        try:
            self.body(page, ctx)
        except Exception as exc:                      # noqa: BLE001
            self.checks['GROUP_CRASHED'] = False
            self.errors.append(f'{type(exc).__name__}: {exc}')
        ctx.close()
        self.server.shutdown(); self.server.server_close()
        return self.checks, self.errors

    def body(self, page, ctx):
        c = self.checks
        # ---- 4a：sw.js 的預快取清單必須跟 index.html 的 <script src> 一字不差 ----
        # index.html 用 SRI，快取回應內容一旦跟頁面要的版本對不上，套件整個不載入。
        html = open(APP, encoding='utf-8').read()
        sw_path = os.path.join(os.path.dirname(os.path.abspath(APP)), 'sw.js')
        sw = open(sw_path, encoding='utf-8').read() if os.path.exists(sw_path) else ''
        srcs = re.findall(r'<script src="(https://[^"]+)"', html)
        c['sw_precaches_exact_cdn_urls'] = bool(sw) and len(srcs) == 2 and all(f"'{u}'" in sw for u in srcs)
        c['sw_registered_with_app_version'] = "register('./sw.js?v='+encodeURIComponent(APP_VERSION))" in html
        # 真的註冊起來、進入 active
        c['sw_becomes_active'] = page.evaluate('''async()=>{
            if(!('serviceWorker' in navigator)) return false;
            const reg=await navigator.serviceWorker.ready;
            await new Promise(r=>setTimeout(r,800));   // 等 precache 完成
            return !!reg.active;
        }''')
        # ---- 離線重新載入：頁面要活著、版本號要在 ----
        ver = page.evaluate('APP_VERSION')
        page.reload(); page.wait_for_timeout(800)      # 讓 SW 接管這個分頁
        ctx.set_offline(True)
        try:
            page.reload(); page.wait_for_timeout(1500)
            c['page_loads_while_offline'] = page.evaluate(
                "()=>typeof state!=='undefined' && document.getElementById('app-version').textContent") == ver
            c['fatigue_mode_reachable_offline'] = page.evaluate("()=>typeof fatigueVibrate==='function'")
        finally:
            ctx.set_offline(False)
        page.reload(); page.wait_for_timeout(800)
        # ---- 4b：第三次開啟才問；稍後 30 天 ----
        c['install_hint_waits_for_third_open'] = page.evaluate('''()=>{
            localStorage.setItem('open-count-v1','2'); localStorage.removeItem('install-hint-v1');
            hideAppBanner();
            const ev=new Event('beforeinstallprompt'); ev.prompt=()=>{}; ev.userChoice=Promise.resolve({outcome:'dismissed'});
            window.dispatchEvent(ev);
            const shownAt2=!!document.querySelector('.app-banner');
            localStorage.setItem('open-count-v1','3');
            window.dispatchEvent(ev);
            const shownAt3=!!document.querySelector('.app-banner');
            return !shownAt2 && shownAt3;
        }''')
        c['install_hint_snooze_persists'] = page.evaluate('''()=>{
            const later=[...document.querySelectorAll('.app-banner button')].find(b=>b.textContent.trim()===t('ui.later','稍後'));
            later.click();
            const st=JSON.parse(localStorage.getItem('install-hint-v1')||'{}');
            const ev=new Event('beforeinstallprompt'); ev.prompt=()=>{}; ev.userChoice=Promise.resolve({outcome:'dismissed'});
            window.dispatchEvent(ev);
            return !document.querySelector('.app-banner') && st.snoozedUntil>Date.now()+29*86400000;
        }''')
        # ---- 4c：儲存空間 ≥80% 主動提示；清理封面兩段式；低於門檻不提示 ----
        c['storage_warning_appears_at_80_percent'] = page.evaluate('''async()=>{
            localStorage.removeItem('storage-warn-v1'); hideAppBanner();
            const orig=navigator.storage.estimate;
            navigator.storage.estimate=async()=>({usage:850,quota:1000});
            try{ await checkStorageHeadroom(true); }finally{ navigator.storage.estimate=orig; }
            const b=document.querySelector('.app-banner.is-warn');
            return !!b && b.textContent.includes('85%');
        }''')
        c['storage_warning_silent_below_threshold'] = page.evaluate('''async()=>{
            hideAppBanner();
            const orig=navigator.storage.estimate;
            navigator.storage.estimate=async()=>({usage:400,quota:1000});
            try{ await checkStorageHeadroom(true); }finally{ navigator.storage.estimate=orig; }
            return !document.querySelector('.app-banner');
        }''')
        c['cover_cleanup_lists_largest_first_and_removes_on_confirm'] = page.evaluate('''async()=>{
            state.races=[];
            const mk=(name,px)=>{ const r=emptyRace(name,'road_running','completed','2026-06-0'+(1+state.races.length));
                const cv=document.createElement('canvas'); cv.width=px; cv.height=px;
                const x=cv.getContext('2d'); for(let i=0;i<300;i++){ x.fillStyle='rgb('+(i*7%255)+','+(i*13%255)+','+(i*29%255)+')'; x.fillRect(Math.random()*px,Math.random()*px,9,9); }
                r.coverImage=cv.toDataURL('image/jpeg',0.9); r.coverThumb=r.coverImage; state.races.push(r); return r; };
            const small=mk('小',120), big=mk('大',600);
            openStorageCleanup(); await new Promise(s=>setTimeout(s,150));
            const rows=[...document.querySelectorAll('.storage-cleanup-row')].map(e=>e.dataset.id);
            const order=rows[0]===big.id && rows[1]===small.id;
            const btn=document.querySelector('.storage-cleanup-row[data-id="'+big.id+'"] [data-action="cleanup-remove-cover"]');
            btn.click(); await new Promise(s=>setTimeout(s,50));
            const stillThere=!!big.coverImage && btn.classList.contains('is-confirming');
            btn.click(); await new Promise(s=>setTimeout(s,300));
            const removed=!big.coverImage && !!small.coverImage;
            closeStorageCleanup();
            return order && stillThere && removed;
        }''')
        # ---- 救援閘門（放最後：它會註銷 SW、清掉快取）----
        # 正常的連續重新整理不可以被誤判（init 成功會把計數歸零）
        c['normal_refresh_not_treated_as_loop'] = page.evaluate(
            "()=>sessionStorage.getItem('boot-fails-v1')==='0' && !window.__swDisabled")
        # 連續三次「載入但沒啟動完成」→ 這一次停用離線快取並清掉 worker
        page.evaluate("()=>{sessionStorage.setItem('boot-fails-v1','2'); sessionStorage.removeItem('sw-wiped-v1');}")
        page.goto(self.url, wait_until='domcontentloaded')
        page.wait_for_timeout(2200)
        c['repeated_boot_failure_disables_sw'] = page.evaluate("()=>window.__swDisabled===true")
        c['repeated_boot_failure_unregisters_worker'] = page.evaluate(
            "async()=>(await navigator.serviceWorker.getRegistrations()).length===0")
        c['wipe_explains_itself_to_the_user'] = page.evaluate(
            "()=>{const b=document.querySelector('.app-banner');"
            "return !!b && b.textContent.indexOf('離線快取')>=0;}")
        c['app_still_works_after_wipe'] = page.evaluate(
            "()=>typeof state!=='undefined' && !!document.getElementById('app-version').textContent")
        # 手動救援：?nosw=1 清乾淨、回到沒有參數的網址，且這個分頁不再註冊
        page.goto(self.url, wait_until='domcontentloaded')
        page.wait_for_timeout(1500)
        page.goto(self.url + '?nosw=1', wait_until='domcontentloaded')
        page.wait_for_timeout(2500)
        c['nosw_param_lands_on_clean_url'] = page.evaluate("()=>location.search===''")
        c['nosw_param_keeps_sw_off_for_this_session'] = page.evaluate(
            "async()=>window.__swDisabled===true && sessionStorage.getItem('sw-off-v1')==='1'"
            " && (await navigator.serviceWorker.getRegistrations()).length===0")

class Climate(Group):
    """氣候與表現：個人距離曲線、溫度估計值退回、越野校正開關。"""

    SEED = """()=>{
        state.races=[];
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

class PublicLink(Group):
    """公開連結：快照白名單、發佈／撤銷、唯讀頁、XSS。"""

    def body(self, page):
        c = self.checks
        SEED='''async()=>{
            state.user={uid:'u1'};
            window.__published={};
            window.__cloud={enabled:true,
              publishSnapshot:async(uid,id,json)=>{ window.__published[id]={uid,json}; },
              deleteSnapshot:async(id)=>{ delete window.__published[id]; },
            };
            shoes.push({id:'s1',name:'Alphafly 3',targetKm:600,isRetired:false,trainingKm:0});
            const pts=[]; for(let i=0;i<3000;i++){ const a=i/2999*Math.PI*2; pts.push({lat:25+Math.sin(a)*0.01,lon:121.5+Math.cos(a)*0.014,elevationM:50}); }
            const r=emptyRace('公開<b>測試</b>','road_running','completed','2026-12-20');
            r.results.chipTimeSeconds=10771; r.results.isPb=true; r.route.distanceKm=42.195; r.route.elevationGainM=180;
            r.performanceData.avgHr=162; r.performanceData.shoeId='s1';
            r.route.trackPoints=pts;
            r.budget={totalTwd:9999,notes:'秘密預算'}; r.notes='私人筆記';
            r.nutritionSchedule=[{item:'能量膠',qty:4,consumed:true},{item:'BCAA',qty:2,consumed:false}];
            const cv=document.createElement('canvas'); cv.width=200; cv.height=150;
            cv.getContext('2d').fillStyle='#345'; cv.getContext('2d').fillRect(0,0,200,150);
            const thumb=cv.toDataURL('image/jpeg',0.8);
            r.coverThumb=thumb;
            r.geoPhotos=Array.from({length:6},(_,i)=>({thumbnailDataUrl:thumb,rawCapturedAt:'2026-12-20T0'+i+':00:00Z',lat:25.01,lon:121.51,aligned:true}));
            state.races.push(r); selectRace(r.id,{scroll:false});
            return true;
        }'''
        page.evaluate(SEED); page.wait_for_timeout(300)
        # 白名單：該有的有、不該有的整包 JSON 裡連字串都找不到
        c['snapshot_is_whitelist_only'] = page.evaluate('''async()=>{
            const snap=await buildPublicSnapshot(currentRace);
            // og 與縮圖是 base64，任何數字串都可能剛好出現在裡面——檢查
            // 「不該外洩的字樣」要先把影像欄位拿掉再比對
            const json=JSON.stringify(Object.assign({},snap,{og:null,coverThumb:null,photos:[]}));
            return snap.name.includes('公開') && snap.results.chipTimeSeconds===10771
                && snap.shoeName==='Alphafly 3'
                && snap.fuel.length===1 && snap.fuel[0].item==='能量膠'   // 只有已補給的
                && snap.photos.length===6 && snap.route.track.length<=401 && snap.route.track.length>=200
                // 數字別拿來當洩漏標記：軌跡座標取五位小數，'9999' 這種
                // 數字串隨時會出現在 25.00999 裡。結構檢查＋文字標記才可靠。
                && snap.budget===undefined && snap.notes===undefined
                && !json.includes('秘密預算') && !json.includes('私人筆記')
                && !json.includes('BCAA') && !json.includes('shoeId') && !json.includes('"budget"');
        }''')
        c['snapshot_respects_byte_budget'] = page.evaluate('''async()=>{
            const big=document.createElement('canvas'); big.width=900; big.height=900;
            const g=big.getContext('2d');
            for(let i=0;i<3000;i++){ g.fillStyle='rgb('+(i*7%255)+','+(i*13%255)+','+(i*31%255)+')'; g.fillRect(Math.random()*900,Math.random()*900,14,14); }
            const noisy=big.toDataURL('image/jpeg',0.95);
            currentRace.geoPhotos=Array.from({length:40},()=>({thumbnailDataUrl:noisy,rawCapturedAt:'2026-12-20T05:00:00Z',lat:25.01,lon:121.51,aligned:true}));
            const snap=await buildPublicSnapshot(currentRace);
            return JSON.stringify(snap).length<=900000 && snap.photos.length<40;
        }''')
        c['publish_writes_doc_and_revoke_deletes'] = page.evaluate('''async()=>{
            currentRace.geoPhotos=currentRace.geoPhotos.slice(0,2);
            const id=await publishRaceLink(currentRace);
            const stored=window.__published[id];
            const okPublish=currentRace.publicShareId===id && stored && stored.uid==='u1'
                && JSON.parse(stored.json).name===currentRace.name;
            await revokeRaceLink(currentRace);
            return okPublish && !currentRace.publicShareId && !window.__published[id];
        }''')
        c['caption_uses_public_link_when_present'] = page.evaluate('''async()=>{
            const id=await publishRaceLink(currentRace);
            const withLink=shareCaptionText(currentRace).includes('?s='+id);
            await revokeRaceLink(currentRace);
            const without=!shareCaptionText(currentRace).includes('?s=');
            return withLink && without;
        }''')

class PublicView(Group):
    """?s= 唯讀頁：獨立群組，因為要用 ?s= 參數重新載入頁面。"""

    def run(self, browser):
        ctx=browser.new_context(viewport=self.viewport)
        page=ctx.new_page()
        page.on('pageerror', lambda e: self.errors.append(str(e)))
        snap_js='''{
          v:1,name:'惡意<img src=x onerror="window.__xss=1">名稱',raceDate:'2026-12-20',startTime:'06:30',
          sportType:'road_running',city:'臺北',country:'臺灣',
          results:{chipTimeSeconds:10771,isPb:true,overallRank:128,ageGroupRank:12},
          route:{distanceKm:42.195,elevationGainM:180,track:Array.from({length:120},(_,i)=>{const a=i/119*Math.PI*2;return [25+Math.sin(a)*0.01,121.5+Math.cos(a)*0.014];})},
          performance:{avgHr:162},shoeName:'Alphafly 3',fuel:[{item:'能量膠',qty:4}],
          coverThumb:null,photos:[],og:null
        }'''
        page.add_init_script(f"window.__cloudOverride={{fetchPublicSnapshot:async()=>({snap_js})}};")
        page.goto(APP_URL+'?s=testid123')
        page.wait_for_timeout(1500)
        c=self.checks
        try:
            c['public_view_renders_readonly'] = page.evaluate('''()=>{
                const hasTime=document.querySelector('.pubview-time')&&document.querySelector('.pubview-time').textContent.includes('2:59:31');
                const noApp=!document.getElementById('main-content')||!document.getElementById('main-content').isConnected;
                const noInputsToEdit=document.querySelectorAll('input:not([readonly]),textarea,select').length===0;
                return !!hasTime && noApp && noInputsToEdit;
            }''')
            c['public_view_escapes_hostile_name'] = page.evaluate(
                "()=>window.__xss!==1 && document.querySelector('.pubview h1').textContent.includes('惡意')")
            c['public_view_draws_track_svg'] = page.evaluate(
                "()=>{const p=document.querySelector('.pubview-track polyline');return !!p && p.getAttribute('points').split(' ').length>=100;}")
            c['public_view_local_data_untouched'] = page.evaluate(
                "()=>typeof state==='undefined' || !state.races || state.races.length===0")
        except Exception as exc:                      # noqa: BLE001
            self.checks['GROUP_CRASHED']=False; self.errors.append(str(exc))
        # 失效連結
        page2=ctx.new_page()
        page2.add_init_script("window.__cloudOverride={fetchPublicSnapshot:async()=>null};")
        page2.goto(APP_URL+'?s=deadlink')
        page2.wait_for_timeout(1200)
        c['public_view_dead_link_message'] = page2.evaluate(
            "()=>document.body.textContent.includes('已失效')")
        ctx.close()
        return self.checks, self.errors

class PasteReport(Group):
    """貼上完賽心得：分類器、預覽視窗、填入行為。"""

    REPORT = ('今天的臺北馬拉松跑得比預期好。前半段配速控制在 4:20，補給站每站都有喝水。'
              '30 公里之後開始有點撞牆，但靠著鹽錠撐過去了。最後衝線 2:59:31，總算破 3 小時，'
              '是個人最佳，總排名 128 名。')

    def body(self, page):
        c = self.checks
        page.evaluate('''()=>{
            state.races=[];
            const a=emptyRace('2026 臺北馬拉松','road_running','completed','2026-12-20');
            const b=emptyRace('2026 萬金石','road_running','completed','2026-03-15');
            b.review.lessonsLearned='舊的檢討內容';
            state.races.push(a,b); selectRace(a.id,{scroll:false});
        }''')
        page.wait_for_timeout(300)
        # 分類器：心得要中、雜訊不能中
        c['classifier_accepts_report_rejects_noise'] = page.evaluate('''(report)=>{
            const ok=classifyPastedText(report).isReport===true;
            const noise=['今天很累','https://example.com/x',
                         'const x=1;\\nfunction go(){ return x+1; }',
                         'name,date,km\\nA,2026-01-01,10\\nB,2026-02-02,21',
                         '<?xml version="1.0"?><gpx><trk></trk></gpx>'];
            return ok && noise.every(n=>classifyPastedText(n).isReport===false);
        }''', self.REPORT)
        # 焦點防護：在輸入框裡貼上不可以被攔截
        c['paste_in_input_is_not_hijacked'] = page.evaluate('''(report)=>{
            const input=document.createElement('textarea');
            document.body.appendChild(input); input.focus();
            const dt=new DataTransfer(); dt.setData('text', report);
            const ev=new ClipboardEvent('paste',{clipboardData:dt,bubbles:true,cancelable:true});
            input.dispatchEvent(ev);
            const hijacked=ev.defaultPrevented||!document.getElementById('paste-note-modal').hidden;
            input.remove();
            return !hijacked;
        }''', self.REPORT)
        # 空白處貼上 → 開預覽視窗，預設是目前開啟的賽事、數字預設不勾
        c['paste_on_blank_opens_preview'] = page.evaluate('''async(report)=>{
            const dt=new DataTransfer(); dt.setData('text', report);
            document.dispatchEvent(new ClipboardEvent('paste',{clipboardData:dt,bubbles:true,cancelable:true}));
            await new Promise(s=>setTimeout(s,250));
            const el=document.getElementById('paste-note-modal');
            const sel=el.querySelector('[data-paste-field="raceId"]');
            const boxes=[...el.querySelectorAll('[data-paste-fact]')];
            return !el.hidden && sel.value===currentRace.id
                && boxes.length>=2 && boxes.every(b=>!b.checked);
        }''', self.REPORT)
        c['extracted_facts_include_time_and_rank'] = page.evaluate('''(report)=>{
            const keys=extractRaceFacts(report).map(f=>f.key);
            const facts=extractRaceFacts(report);
            const time=facts.find(f=>f.key==='results.chipTimeSeconds');
            return keys.includes('results.chipTimeSeconds') && keys.includes('results.overallRank')
                && time.value===10771 && !!time.snippet;
        }''', self.REPORT)
        # 確認填入：文字進檢討筆記，未勾的數字不動
        c['confirm_fills_text_only_by_default'] = page.evaluate('''async()=>{
            document.querySelector('#paste-note-modal [data-action="confirm-paste-note"]').click();
            await new Promise(s=>setTimeout(s,400));
            const r=state.races.find(x=>x.name==='2026 臺北馬拉松');
            return r.review.lessonsLearned.includes('撞牆')
                && r.results.chipTimeSeconds==null && r.results.overallRank==null
                && document.getElementById('paste-note-modal').hidden;
        }''')
        # 勾選數字才會填，且已有內容的欄位預設是「接在後面」
        c['checked_facts_fill_and_append_preserves_existing'] = page.evaluate('''async(report)=>{
            const other=state.races.find(x=>x.name==='2026 萬金石');
            const dt=new DataTransfer(); dt.setData('text', report);
            document.dispatchEvent(new ClipboardEvent('paste',{clipboardData:dt,bubbles:true,cancelable:true}));
            await new Promise(s=>setTimeout(s,250));
            const el=document.getElementById('paste-note-modal');
            const sel=el.querySelector('[data-paste-field="raceId"]');
            sel.value=other.id; sel.dispatchEvent(new Event('change',{bubbles:true}));
            await new Promise(s=>setTimeout(s,200));
            const mode=el.querySelector('[data-paste-field="mode"]');
            const defaultAppend=mode && mode.value==='append';
            const box=el.querySelector('[data-paste-fact="0"]');
            box.checked=true; box.dispatchEvent(new Event('change',{bubbles:true}));
            el.querySelector('[data-action="confirm-paste-note"]').click();
            await new Promise(s=>setTimeout(s,400));
            const r=state.races.find(x=>x.name==='2026 萬金石');
            return defaultAppend && r.review.lessonsLearned.startsWith('舊的檢討內容')
                && r.review.lessonsLearned.includes('撞牆')
                && r.results.chipTimeSeconds===10771;
        }''', self.REPORT)
        # ---- 住宿資訊 ----
        ZH = ('訂房確認通知\n飯店名稱：礁溪老爺酒店\n地址：宜蘭縣礁溪鄉大忠路58號\n'
              '入住：2026-12-19 15:00\n退房：2026-12-21 11:00\n訂房編號：AB123456\n'
              '總金額：NT$8,400\n狀態：已付款')
        EN = ('Booking confirmation\nHotel: Hotel Metropolitan Tokyo\nAddress: 1-1-1 Shibuya, Tokyo\n'
              'Check-in: 2027/01/30 15:00\nCheck-out: 2027/02/01 10:00\nTotal: JPY 32,000\nBooking confirmed')
        c['accommodation_extracts_zh_booking'] = page.evaluate('''(txt)=>{
            const f=extractAccommodation(txt);
            return f.hotelName==='礁溪老爺酒店' && f.checkIn==='2026-12-19T15:00'
                && f.checkOut==='2026-12-21T11:00' && f.cost===8400
                && f.bookingStatus==='paid' && f.address.includes('大忠路');
        }''', ZH)
        c['accommodation_extracts_en_booking'] = page.evaluate('''(txt)=>{
            const f=extractAccommodation(txt);
            return f.hotelName==='Hotel Metropolitan Tokyo' && f.checkIn==='2027-01-30T15:00'
                && f.checkOut==='2027-02-01T10:00' && f.cost===32000 && f.bookingStatus==='booked';
        }''', EN)
        # 標題行不能被當成飯店名
        c['accommodation_skips_header_line_as_name'] = page.evaluate('''()=>{
            const f=extractAccommodation('民宿訂房\\n山中民宿\\n2026-09-05 ~ 2026-09-06\\n已預訂');
            return f.hotelName==='山中民宿' && f.checkIn==='2026-09-05' && f.checkOut==='2026-09-06';
        }''')
        # 只有日期沒有時間 → 時間留空，不要猜一個 00:00
        c['accommodation_leaves_time_blank_when_absent'] = page.evaluate('''()=>{
            const f=extractAccommodation('山中民宿\\n入住 2026-09-05\\n退房 2026-09-06\\n訂房編號 X1');
            return f.checkIn==='2026-09-05' && !f.checkIn.includes('T');
        }''')
        # 分流：訂房信走住宿、心得走心得、提到飯店的心得不能被搶走
        c['accommodation_and_report_routing'] = page.evaluate('''(args)=>{
            const [zh]=args;
            const report='今天配速控制得不錯，補給站都有停，最後衝線 2:59:31。我覺得這場表現很好。';
            const reportWithHotel='2026-12-20 這場賽前一晚住在市區的飯店，睡得還不錯。今天跑得比預期好，最後 2:59:31 完賽，是個人最佳，我很滿意。';
            return classifyAccommodationText(zh).isAccommodation===true
                && classifyAccommodationText(report).isAccommodation===false
                && classifyAccommodationText(reportWithHotel).isAccommodation===false
                && classifyPastedText(reportWithHotel).isReport===true;
        }''', [ZH])
        # 貼上 → 視窗 → 新增一筆，既有住宿不動
        c['accommodation_paste_adds_new_entry'] = page.evaluate('''async(txt)=>{
            const r=state.races.find(x=>x.name==='2026 臺北馬拉松');
            selectRace(r.id,{scroll:false});
            await new Promise(s=>setTimeout(s,200));
            r.accommodations=[{hotelName:'原本就有的飯店',address:'',checkIn:'',checkOut:'',
                               distanceToStartKm:null,bookingStatus:'booked',cost:null,notes:''}];
            const dt=new DataTransfer(); dt.setData('text', txt);
            document.dispatchEvent(new ClipboardEvent('paste',{clipboardData:dt,bubbles:true,cancelable:true}));
            await new Promise(s=>setTimeout(s,300));
            const el=document.getElementById('paste-note-modal');
            const opened=!el.hidden && el.textContent.includes('礁溪老爺酒店');
            const allChecked=[...el.querySelectorAll('[data-paste-accom]')].every(b=>b.checked);
            el.querySelector('[data-action="confirm-paste-accom"]').click();
            await new Promise(s=>setTimeout(s,400));
            const list=state.races.find(x=>x.name==='2026 臺北馬拉松').accommodations;
            return opened && allChecked && list.length===2
                && list[0].hotelName==='原本就有的飯店'
                && list[1].hotelName==='礁溪老爺酒店' && list[1].cost===8400;
        }''', ZH)
        # ---- 交通票券 ----
        FLIGHT = ('長榮航空 電子機票\n訂位代號：ABC123\n航班 BR189\n台北(TPE) → 東京成田(NRT)\n'
                  '2027/01/29 09:20 起飛\n13:35 抵達\n座位 32A')
        HSR_RT = ('台灣高鐵 訂位代號 12345678\n去程 車次 0613 2026-12-19 08:31 台北 → 左營 5車 12E\n'
                  '回程 車次 0842 2026-12-21 16:10 左營 → 台北 7車 3A')
        c['transport_classifier_covers_all_modes'] = page.evaluate('''(args)=>{
            const [flight,hsr]=args;
            const samples=[flight,hsr,
              '台鐵 自強號 123 車次\\n2026-09-05 07:10 台北 → 宜蘭',
              '國光客運 1815\\n台北轉運站 → 金山\\n2026-11-07 06:30 發車',
              '臺馬之星 船班\\n2026-11-06 22:00 基隆港 → 南竿\\n訂票代號 MZ2211',
              'のぞみ 15号 東京 → 新大阪\\n2027/01/30 08:00発 10:30着\\n予約番号 XY889',
              '捷運 淡水信義線 台北車站 → 淡水\\n2026-10-11 05:40 出發'];
            const modes=samples.map(s=>extractTransport(s,'2026-12-20')[0].mode);
            return samples.every(s=>classifyTransportText(s).isTransport)
                && modes.join(',')==='flight,hsr,train,bus,ferry,hsr,metro';
        }''', [FLIGHT, HSR_RT])
        c['transport_flight_fields_and_notes'] = page.evaluate('''(txt)=>{
            const e=extractTransport(txt,'2027-01-31')[0];
            return e.direction==='outbound' && e.mode==='flight' && e.departureTime==='2027-01-29T09:20'
                && e.pickupLocation==='台北(TPE)'
                && e.notes.split(' ・ ')[1]==='BR189'   // 班機號要是 BR189，不是訂位代號裡的 BC123
                && e.notes.includes('32A') && e.notes.includes('13:35') && e.notes.includes('#ABC123');
        }''', FLIGHT)
        c['transport_round_trip_splits_into_two_legs'] = page.evaluate('''(txt)=>{
            const legs=extractTransport(txt,'2026-12-20');
            return legs.length===2 && legs[0].direction==='outbound' && legs[1].direction==='return'
                && legs.every(l=>l.mode==='hsr')   // 抬頭寫高鐵，段落裡的「車次」不能把它判成火車
                && legs[0].departureTime==='2026-12-19T08:31' && legs[1].departureTime==='2026-12-21T16:10'
                && legs[0].notes.includes('0613') && legs[1].notes.includes('7車 3A');
        }''', HSR_RT)
        # 方向沒有標記時依賽事日期猜：比賽前去程、之後回程
        c['transport_direction_inferred_from_race_date'] = page.evaluate('''()=>{
            const txt='台鐵 自強號 123 車次\\n2026-09-07 07:10 宜蘭 → 台北';
            return extractTransport(txt,'2026-09-06')[0].direction==='return'
                && extractTransport(txt,'2026-09-08')[0].direction==='outbound';
        }''')
        # 分流：訂房信裡的「機場接送」不能變成交通票；機票不能變成住宿
        c['transport_vs_accommodation_routing'] = page.evaluate('''(flight)=>{
            const booking='訂房確認通知\\n飯店名稱：礁溪老爺酒店\\n入住：2026-12-19 15:00\\n退房：2026-12-21 11:00\\n機場接送：有';
            return classifyTransportText(booking).isTransport===false
                && classifyAccommodationText(booking).isAccommodation===true
                && classifyTransportText(flight).isTransport===true
                && classifyAccommodationText(flight).isAccommodation===false;
        }''', FLIGHT)
        # 貼上 → 視窗兩段 → 改第二段的工具 → 確認 → 兩筆進 transportation，既有的不動
        c['transport_paste_adds_legs_with_edits'] = page.evaluate('''async(txt)=>{
            const r=state.races.find(x=>x.name==='2026 臺北馬拉松');
            selectRace(r.id,{scroll:false}); await new Promise(s=>setTimeout(s,200));
            r.transportation=[{direction:'outbound',mode:'self_drive',departureTime:'',pickupLocation:'原本的',notes:''}];
            const dt=new DataTransfer(); dt.setData('text', txt);
            document.dispatchEvent(new ClipboardEvent('paste',{clipboardData:dt,bubbles:true,cancelable:true}));
            await new Promise(s=>setTimeout(s,300));
            const el=document.getElementById('paste-note-modal');
            const legs=el.querySelectorAll('.paste-transport-entry').length;
            const sel=el.querySelector('[data-paste-trip-field="1:mode"]');
            sel.value='train'; sel.dispatchEvent(new Event('change',{bubbles:true}));
            el.querySelector('[data-action="confirm-paste-transport"]').click();
            await new Promise(s=>setTimeout(s,400));
            const list=state.races.find(x=>x.name==='2026 臺北馬拉松').transportation;
            return legs===2 && list.length===3 && list[0].pickupLocation==='原本的'
                && list[1].mode==='hsr' && list[2].mode==='train' && list[2].direction==='return'
                && list[1].departureTime==='2026-12-19T08:31';
        }''', HSR_RT)
        # ---- 訂房／訂票「網頁選字複製」的雜訊（麵包屑、評論、參考價、按鈕字樣） ----
        AGODA_NOISY = ('首頁 › 台灣 › 宜蘭 › 礁溪\n礁溪老爺酒店\n4.6 分 (2,341 則評論)\n'
                       '免費取消・訂今付訂金\n立即預訂\n熱門房型剩 3 間\n平均每晚 NT$3,200 起\n'
                       '入住：2026-12-19\n退房：2026-12-21\n訂房保證最優惠價格\n總金額：NT$8,400\n'
                       '查看地圖　分享　收藏')
        THSR_NOISY = ('台灣高鐵 訂票系統\n首頁 › 訂票 › 查詢結果\n熱門優惠　立即比價\n'
                      '去程　2026-12-19（六）\n車次 0613　太魚快　08:31　台北 → 09:56　左營\n'
                      '剩餘座位：42\n標準車廂　5車 12E\n回程　2026-12-21（一）\n'
                      '車次 0842　08:31　左營 → 16:10　台北\n7車 3A\n訂位代號 12345678\n'
                      '更多班次　查看座位表')
        # 麵包屑不能變成飯店名，「酒店」這種常見命名要抓得到（原本規則只有「飯店」）
        c['accommodation_skips_breadcrumb_and_recognizes_jiudian'] = page.evaluate('''(txt)=>{
            const f=extractAccommodation(txt);
            return f.hotelName==='礁溪老爺酒店' && !f.hotelName.includes('首頁');
        }''', AGODA_NOISY)
        # 費用要抓「總金額」不是「平均每晚」的搜尋結果參考價
        c['accommodation_cost_prefers_total_over_teaser_price'] = page.evaluate('''(txt)=>{
            return extractAccommodation(txt).cost===8400;
        }''', AGODA_NOISY)
        # 星等評論、按鈕字樣不能污染分類或抽取（維持一定能判斷成住宿）
        c['accommodation_classify_robust_to_ui_noise'] = page.evaluate('''(txt)=>{
            return classifyAccommodationText(txt).isAccommodation===true;
        }''', AGODA_NOISY)
        # 日期與時刻分兩行（網頁常見排版）也要抓得到出發時間，不是只抓到日期
        c['transport_time_crosses_linebreak'] = page.evaluate('''(txt)=>{
            const legs=extractTransport(txt,'2026-12-20');
            return legs[0].departureTime==='2026-12-19T08:31' && legs[1].departureTime==='2026-12-21T08:31';
        }''', THSR_NOISY)
        # 「08:31 台北 → 09:56 左營」時間夾在站名中間，不能把時間當成站名
        c['transport_route_ignores_embedded_time'] = page.evaluate('''(txt)=>{
            const legs=extractTransport(txt,'2026-12-20');
            return legs[0].pickupLocation==='台北' && legs[0].notes.startsWith('台北 → 左營')
                && legs[1].pickupLocation==='左營' && legs[1].notes.startsWith('左營 → 台北');
        }''', THSR_NOISY)
        # 訂位代號只出現一次（在最後），但兩段行程都要對得上
        c['transport_shared_confirmation_applies_to_both_legs'] = page.evaluate('''(txt)=>{
            const legs=extractTransport(txt,'2026-12-20');
            return legs[0].notes.includes('#12345678') && legs[1].notes.includes('#12345678');
        }''', THSR_NOISY)
        # 「更多班次」「查看座位表」這類介面字樣不能被判成一個地名
        c['transport_ui_phrases_not_mistaken_for_location'] = page.evaluate('''(txt)=>{
            const legs=extractTransport(txt,'2026-12-20');
            return legs.every(l=>!/更多|查看|訂票|比價/.test(l.pickupLocation));
        }''', THSR_NOISY)
        # ---- 貼上純網址 → 存成媒體連結 ----
        c['url_classifier_recognises_sources'] = page.evaluate('''()=>{
            const got=k=>{const r=classifyPastedUrl(k);return r?r.type:null;};
            return got('https://www.instagram.com/p/Cxyz123/')==='photo_album'
                && got('https://www.strava.com/activities/123456')==='gpx_track'
                && got('https://connect.garmin.com/modern/activity/999')==='gpx_track'
                && got('https://example.org/files/a.pdf')==='brochure_pdf'
                && got('https://example.org/race/2026')==='official_site';  // 認不出來給官網
        }''')
        # 只收「整段就是一個 http(s) 網址」——夾在句子裡的、危險 scheme 的都不攔
        c['url_classifier_rejects_non_bare_and_unsafe'] = page.evaluate('''()=>{
            return classifyPastedUrl('看看這個 https://example.org/x')===null
                && classifyPastedUrl('javascript:alert(1)')===null
                && classifyPastedUrl('data:text/html,<script>1</script>')===null
                && classifyPastedUrl('今天天氣很好')===null
                && classifyPastedUrl('')===null;
        }''')
        # 貼上網址 → 開確認視窗（不是心得那個視窗），預設選中目前賽事
        c['url_paste_opens_link_modal'] = page.evaluate('''async()=>{
            const r=state.races.find(x=>x.name==='2026 臺北馬拉松');
            selectRace(r.id,{scroll:false}); await new Promise(s=>setTimeout(s,200));
            const dt=new DataTransfer(); dt.setData('text','https://www.strava.com/activities/123456');
            document.dispatchEvent(new ClipboardEvent('paste',{clipboardData:dt,bubbles:true,cancelable:true}));
            await new Promise(s=>setTimeout(s,300));
            const el=document.getElementById('paste-note-modal');
            return !el.hidden && pasteNoteState.kind==='url'
                && el.querySelector('[data-paste-field="raceId"]').value===r.id
                && el.querySelector('[data-paste-url-field="type"]').value==='gpx_track';
        }''')
        # 改類型與備註後儲存，進 mediaLinks，既有連結不動
        c['url_paste_saves_media_link'] = page.evaluate('''async()=>{
            const r=state.races.find(x=>x.name==='2026 臺北馬拉松');
            r.mediaLinks=[{type:'official_site',url:'https://old.example.org/',notes:'原本的'}];
            const el=document.getElementById('paste-note-modal');
            const sel=el.querySelector('[data-paste-url-field="type"]');
            sel.value='photo_album'; sel.dispatchEvent(new Event('change',{bubbles:true}));
            const notes=el.querySelector('[data-paste-url-field="notes"]');
            notes.value='賽後紀錄'; notes.dispatchEvent(new Event('change',{bubbles:true}));
            el.querySelector('[data-action="confirm-paste-url"]').click();
            await new Promise(s=>setTimeout(s,400));
            const list=state.races.find(x=>x.name==='2026 臺北馬拉松').mediaLinks;
            return list.length===2 && list[0].notes==='原本的'
                && list[1].url==='https://www.strava.com/activities/123456'
                && list[1].type==='photo_album' && list[1].notes==='賽後紀錄'
                && document.getElementById('paste-note-modal').hidden;
        }''')
        # 已經有一模一樣的連結時要出現提醒（但仍允許存）
        c['url_paste_warns_on_duplicate'] = page.evaluate('''async()=>{
            const dt=new DataTransfer(); dt.setData('text','https://www.strava.com/activities/123456');
            document.dispatchEvent(new ClipboardEvent('paste',{clipboardData:dt,bubbles:true,cancelable:true}));
            await new Promise(s=>setTimeout(s,300));
            const el=document.getElementById('paste-note-modal');
            const warned=!!el.querySelector('.paste-url-dup');
            el.querySelector('[data-action="close-paste-note"]').click();
            return warned;
        }''')
        # 網址不可以把心得／住宿／交通那三條路搶走（它們都是整段文字）
        c['url_route_does_not_steal_other_kinds'] = page.evaluate('''()=>{
            const report='今天配速控制得不錯，補給站都有停，最後衝線 2:59:31。我覺得這場表現很好。';
            const booking='訂房確認通知\\n飯店名稱：礁溪老爺酒店\\n入住：2026-12-19 15:00\\n退房：2026-12-21 11:00';
            return classifyPastedUrl(report)===null && classifyPastedUrl(booking)===null;
        }''')
        # 佔位符要真的被置換掉——tf() 只認 {n}，寫成 {s} 會原樣顯示在畫面上
        c['paste_modals_leave_no_placeholder'] = page.evaluate('''async()=>{
            const seen=[];
            const fire=txt=>{ const dt=new DataTransfer(); dt.setData('text',txt);
              document.dispatchEvent(new ClipboardEvent('paste',{clipboardData:dt,bubbles:true,cancelable:true})); };
            const samples=['https://www.strava.com/activities/123456',
              '訂房確認通知\\n飯店名稱：礁溪老爺酒店\\n入住：2026-12-19 15:00\\n退房：2026-12-21 11:00',
              '台灣高鐵 訂位代號 12345678\\n去程 車次 0613 2026-12-19 08:31 台北 → 左營 5車 12E\\n回程 車次 0842 2026-12-21 16:10 左營 → 台北 7車 3A',
              '今天配速控制得不錯，補給站都有停，最後衝線 2:59:31。我覺得這場表現很好。'];
            for(const sample of samples){
              fire(sample);
              await new Promise(s=>setTimeout(s,250));
              const el=document.getElementById('paste-note-modal');
              if(!el.hidden){
                // 只看介面文字，不看使用者貼進來的原文預覽
                const chrome=[...el.querySelectorAll('h2,.modal-hint,.paste-note-facts-hint')]
                  .map(n=>n.textContent).join(' ');
                seen.push(/\\{[a-z]\\}/.test(chrome));
                el.querySelector('[data-action="close-paste-note"]').click();
                await new Promise(s=>setTimeout(s,150));
              }
            }
            return seen.length>=3 && seen.every(bad=>bad===false);
        }''')
        # 里程碑不是賽事距離：「30 公里之後撞牆」不能被當成 distanceKm
        c['distance_needs_explicit_marker'] = page.evaluate('''()=>{
            const milestone=extractRaceFacts('最後衝線 2:59:31。30 公里之後開始撞牆。').map(f=>f.key);
            const explicit=extractRaceFacts('全程 42.195 公里，3:15:20 完賽。').find(f=>f.key==='route.distanceKm');
            return !milestone.includes('route.distanceKm') && explicit && explicit.value===42.195;
        }''')
        c['fact_labels_resolve_across_sections'] = page.evaluate('''async()=>{
            const dt=new DataTransfer(); dt.setData('text','全程 42.195 公里的賽事，最後 2:59:31 完賽，總排名 128 名。整體配速穩定，補給站都有停，我自己覺得表現不錯。');
            document.dispatchEvent(new ClipboardEvent('paste',{clipboardData:dt,bubbles:true,cancelable:true}));
            await new Promise(s=>setTimeout(s,250));
            const el=document.getElementById('paste-note-modal');
            const txt=el.textContent;
            el.querySelector('[data-action="close-paste-note"]').click();
            return !txt.includes('route.distanceKm') && !txt.includes('results.chipTimeSeconds');
        }''')
        # ---- 成績查詢頁 ----
        RESULT = ('財政部113年統一發票盃路跑活動\n2024-09-22 (日)\n劉恩龍\n010685\n'
                  '半馬組(21km) 男丁組 男\n大會成績\nOfficial Time\n01:51:53\n'
                  '個人成績\nNet Time\n01:51:36\n總排名\nOverall Ranking\n287/3000\n'
                  '性別排名\nGender Ranking\n259/2251\n分組排名\nDiv Ranking\n57/368')
        c['result_extracts_times_and_ranks'] = page.evaluate('''(txt)=>{
            const f=extractRaceResults(txt);
            return f['results.gunTimeSeconds']===6713 && f['results.chipTimeSeconds']===6696
                && f['results.overallRank']===287 && f['results.overallParticipants']===3000
                && f['results.ageGroupRank']===57 && f['results.ageGroupParticipants']===368;
        }''', RESULT)
        # 標籤與數值被排版拆到不同行也要對得上（這正是原本失效的原因）
        c['result_labels_match_across_lines'] = page.evaluate('''(txt)=>{
            const c2=classifyResultText(txt);
            return c2.isResult===true && c2.score>=5;
        }''', RESULT)
        # 成績頁通常也有賽事名稱與日期，不可以被「新增賽事」那條先吃掉
        c['result_beats_new_race_when_race_exists'] = page.evaluate('''async(txt)=>{
            state.races=[];
            const r=emptyRace('財政部統一發票盃路跑','road_running','completed','2024-09-22');
            state.races.push(r); selectRace(r.id,{scroll:false});
            await new Promise(s=>setTimeout(s,250));
            const dt=new DataTransfer(); dt.setData('text',txt);
            document.dispatchEvent(new ClipboardEvent('paste',{clipboardData:dt,bubbles:true,cancelable:true}));
            await new Promise(s=>setTimeout(s,400));
            return pasteNoteState && pasteNoteState.kind==='result' && state.creating!==true;
        }''', RESULT)
        c['result_fills_all_six_fields'] = page.evaluate('''async()=>{
            document.querySelector('[data-action="confirm-paste-result"]').click();
            await new Promise(s=>setTimeout(s,500));
            const r=state.races[0];
            return r.results.gunTimeSeconds===6713 && r.results.chipTimeSeconds===6696
                && r.results.overallRank===287 && r.results.overallParticipants===3000
                && r.results.ageGroupRank===57 && r.results.ageGroupParticipants===368;
        }''')
        # 沒有成績時間就不算成績頁
        c['result_needs_a_finish_time'] = page.evaluate('''()=>{
            return classifyResultText('總排名 287/3000\\n分組排名 57/368').isResult===false
                && classifyResultText('').isResult===false;
        }''')
        # 只有名稱＋日期（沒有成績）時，仍然走「新增賽事」
        c['new_race_still_wins_without_results'] = page.evaluate('''()=>{
            const txt='2026 臺北馬拉松\\n比賽日期：2026-12-20\\n距離：42.195 公里';
            return classifyResultText(txt).isResult===false
                && classifyNewRaceText(txt).isNewRace===true;
        }''')
        # 沒有排名區塊的成績頁也要抓得到（兩個獨立的完賽時間就是夠強的訊號）
        c['result_without_ranking_is_detected'] = page.evaluate('''()=>{
            const txt='2024 Panasonic 台北城市路跑賽\\n2024-09-08 (日)\\n劉恩龍\\n004514\\n'
                    + '12.5KM 男子組 TW 男\\n大會成績\\nOfficial Time\\n01:13:30\\n個人成績\\nNet Time\\n01:12:11';
            const c2=classifyResultText(txt);
            return c2.isResult===true
                && c2.fields['results.gunTimeSeconds']===4410
                && c2.fields['results.chipTimeSeconds']===4331
                && c2.fields['bibNumber']==='004514'
                && c2.fields['results.overallRank']==null;   // 沒有排名就不要亂填
        }''')
        # 放寬之後不可以把心得搶走
        c['result_loosening_does_not_steal_reports'] = page.evaluate('''()=>{
            const withTime='今天配速控制得不錯，補給站都有停，大會成績 3:25:17。我覺得這場表現很好。';
            const plain='今天配速控制得不錯，補給站都有停，最後衝線 2:59:31。我覺得這場表現很好。';
            return classifyResultText(withTime).isResult===false && classifyPastedText(withTime).isReport===true
                && classifyResultText(plain).isResult===false && classifyPastedText(plain).isReport===true
                && classifyResultText('晶片時間 03:25:17').isResult===false;  // 單一時間還是不夠
        }''')
        # ---- 標籤同義詞擴大 ----
        c['result_synonyms_zh_en_ja'] = page.evaluate('''()=>{
            const f=t=>extractRaceResults(t);
            const zh=f('大會紀錄 03:25:17\\n淨時間 03:24:50\\n綜合排名 120/2000');
            const en=f('Gross Time 03:25:17\\nNet Time 03:24:50\\nOverall Place 120/2000\\nGender Rank 45/900\\nDivision Rank 12/150');
            const ja=f('グロスタイム 03:25:17\\nネットタイム 03:24:50\\n総合順位 120/2000\\n男女別順位 45/900\\n種目別順位 12/150');
            return zh['results.gunTimeSeconds']===12317 && zh['results.chipTimeSeconds']===12290
                && zh['results.overallRank']===120
                && en['results.genderRank']===45 && en['results.ageGroupRank']===12
                && ja['results.genderRank']===45 && ja['results.ageGroupRank']===12
                && ja['results.gunTimeSeconds']===12317;
        }''')
        # 性別排名與分組名次是兩個欄位，不可以互相覆蓋
        c['gender_rank_kept_separate_from_age_group'] = page.evaluate('''()=>{
            const f=extractRaceResults('大會時間 01:51:53\\n個人時間 01:51:36\\n'
              +'總名次 287/3000\\n性別排名 259/2251\\n分組名次 57/368');
            return f['results.overallRank']===287 && f['results.overallParticipants']===3000
                && f['results.genderRank']===259 && f['results.genderParticipants']===2251
                && f['results.ageGroupRank']===57 && f['results.ageGroupParticipants']===368;
        }''')
        # 總排名不可以把分組／性別的數字吃走（裸的「排名」兩個字會誤中）
        c['overall_rank_does_not_swallow_subgroup_ranks'] = page.evaluate('''()=>{
            const a=extractRaceResults('晶片時間 03:25:17\\n分組排名 12/150');
            const b=extractRaceResults('晶片時間 03:25:17\\n性別排名 45/900');
            const c2=extractRaceResults('晶片時間 03:25:17\\n分組排名 12/150\\n總排名 120/2000');
            return a['results.overallRank']==null && a['results.ageGroupRank']===12
                && b['results.overallRank']==null && b['results.genderRank']===45
                && c2['results.overallRank']===120 && c2['results.ageGroupRank']===12;
        }''')
        # 前後半程與號碼布同義詞
        c['result_half_splits_and_bib_synonyms'] = page.evaluate('''()=>{
            const h=extractRaceResults('晶片時間 03:25:17\\n前半 1:40:00\\n後半 1:45:17\\n總排名 120/2000');
            const b=extractRaceResults('參賽編號 A1234\\n晶片成績 03:25:17\\n全場排名 88/900');
            return h['results.firstHalfSeconds']===6000 && h['results.secondHalfSeconds']===6317
                && b['bibNumber']==='A1234' && b['results.overallRank']===88;
        }''')
        # 性別排名要出現在成績儀表板上
        c['gender_rank_shows_in_dashboard'] = page.evaluate('''()=>{
            const r=emptyRace('x','road_running','completed','2026-05-01');
            r.route.distanceKm=21.0975; r.results.chipTimeSeconds=5185;
            r.results.genderRank=259; r.results.genderParticipants=2251;
            const d=document.createElement('div'); d.innerHTML=renderResultsDashboard(r);
            return [...d.querySelectorAll('.results-badge')].some(b=>
              b.querySelector('.results-badge-label').textContent==='性別排名'
              && b.querySelector('.results-badge-value').textContent.includes('259'));
        }''')
        # ---- 貼上的文字提到清單裡已存在的賽事時，該怎麼分流 ----
        c['paste_routing_matrix_with_existing_race'] = page.evaluate('''async()=>{
            state.races=[];
            const r=emptyRace('Panasonic 台北城市路跑賽','road_running','completed','2024-09-08');
            state.races.push(r); selectRace(r.id,{scroll:false});
            await new Promise(s=>setTimeout(s,200));
            const route=txt=>{
              if(classifyResultText(txt).isResult) return '成績';
              if(classifyNewRaceText(txt).isNewRace) return '新增賽事';
              if(classifyPastedText(txt).isReport) return '心得';
              return '無';
            };
            const cases=[
              ['Panasonic 台北城市路跑賽\\n01:12:11','成績'],                          // 最精簡：名稱＋時間
              ['2024 Panasonic 台北城市路跑賽\\n01:12:11','成績'],                     // 名稱多一個年份也要對得上
              ['Panasonic 台北城市路跑賽\\n2024-09-08\\n01:12:11','成績'],             // 已存在 → 不可以跳新增表單
              ['2027 田中馬拉松\\n比賽日期：2027-11-14\\n全程馬拉松','新增賽事'],        // 沒見過的才是新增
              ['今天的 Panasonic 台北城市路跑賽 跑得比預期好。前半段配速控制得不錯，補給站都有停，最後 1:12:11 完賽，我覺得這場表現很好，下次要更早開始補鹽。','心得'],
              ['01:12:11','無'],                                                      // 只有時間太曖昧
              ['某個沒建立過的賽事\\n01:12:11','無'],
            ];
            return cases.every(([txt,want])=>route(txt)===want);
        }''')
        # 名稱比對本身：太短的名稱不比對，避免泛稱亂中
        c['race_name_match_ignores_short_names'] = page.evaluate('''()=>{
            state.races=[];
            state.races.push(emptyRace('路跑','road_running','completed','2024-09-08'));
            const short=matchRaceByPastedName('今天去路跑 01:12:11');
            state.races.push(emptyRace('Panasonic 台北城市路跑賽','road_running','completed','2024-09-08'));
            const long=matchRaceByPastedName('2024 Panasonic 台北城市路跑賽 01:12:11');
            return short===null && !!long && long.name==='Panasonic 台北城市路跑賽';
        }''')
        # ---- 號碼布編號 ----
        c['bib_extracted_from_standalone_digits'] = page.evaluate('''()=>{
            const a=extractRaceResults('劉恩龍\\n003150\\n半馬挑戰組\\n大會成績\\n01:51:53\\n總排名\\n287/3000');
            const b=extractRaceResults('活動\\n2024-09-22\\n劉恩龍\\n010685\\n大會成績\\n01:51:53\\n總排名\\n287/3000\\n分組排名\\n57/368');
            return a['bibNumber']==='003150' && b['bibNumber']==='010685';
        }''')
        # 有標籤時要吃得下帶字母／連字號的號碼布
        c['bib_labelled_accepts_alphanumeric'] = page.evaluate('''()=>{
            const f=t=>extractRaceResults(t)['bibNumber'];
            return f('號碼布：A1234\\n晶片時間 03:25:17')==='A1234'
                && f('Bib No. R-045\\nChip Time 03:25:17')==='R-045'
                && f('ゼッケン 7821\\nネットタイム 03:25:17')==='7821';
        }''')
        # 不可以把人數、年份、三位數誤認成號碼布
        c['bib_ignores_participants_year_and_short_numbers'] = page.evaluate('''()=>{
            const f=t=>extractRaceResults(t)['bibNumber'];
            return f('晶片時間 03:25:17\\n總排名\\n287/3000\\n分組排名\\n57/3680')==null
                && f('2024\\n晶片時間 03:25:17\\n總排名 287/3000')==null
                && f('123\\n晶片時間 03:25:17')==null;
        }''')
        # 前導零不受年份規則限制（02024 不可能是年份）
        c['bib_leading_zero_beats_year_rule'] = page.evaluate('''()=>{
            return extractRaceResults('02024\\n晶片時間 03:25:17')['bibNumber']==='02024';
        }''')
        # 視窗標籤要跨區段解析（號碼布在基本資訊，不在賽後）
        c['bib_label_resolves_across_sections'] = page.evaluate('''async()=>{
            state.races=[];
            const r=emptyRace('統一發票盃','road_running','completed','2024-09-22');
            state.races.push(r); selectRace(r.id,{scroll:false});
            await new Promise(s=>setTimeout(s,250));
            const dt=new DataTransfer();
            dt.setData('text','劉恩龍\\n003150\\n大會成績\\n01:51:53\\n總排名\\n287/3000');
            document.dispatchEvent(new ClipboardEvent('paste',{clipboardData:dt,bubbles:true,cancelable:true}));
            await new Promise(s=>setTimeout(s,400));
            const el=document.getElementById('paste-note-modal');
            const txt=el.innerText;
            el.querySelector('[data-action="confirm-paste-result"]').click();
            await new Promise(s=>setTimeout(s,500));
            return txt.includes('號碼布編號') && !txt.includes('bibNumber')
                && state.races[0].bibNumber==='003150';
        }''')
        # ---- 貼上「賽事名稱＋日期」→ 開新增表單並帶入 ----
        c['new_race_extracts_name_date_distance'] = page.evaluate('''()=>{
            const r=classifyNewRaceText('2026 臺北馬拉松\\n比賽日期：2026-12-20\\n距離：42.195 公里\\nhttps://www.taipeimarathon.org.tw/');
            return r.isNewRace && r.info.name==='2026 臺北馬拉松' && r.info.raceDate==='2026-12-20'
                && r.info.distanceKm===42.195 && r.info.officialUrl.includes('taipeimarathon');
        }''')
        # 有標籤的比賽日期要贏過排在前面的報名日期
        c['new_race_prefers_labelled_race_date'] = page.evaluate('''()=>{
            const r=classifyNewRaceText('賽事名稱：2027 田中馬拉松\\n報名日期：2026-08-01\\n比賽日期：2027-11-14\\n全程馬拉松');
            return r.isNewRace && r.info.raceDate==='2027-11-14' && r.info.name==='2027 田中馬拉松';
        }''')
        # 名稱尾巴的距離／組別要切掉，但不能把名稱本體的「馬拉松」吃掉
        c['new_race_name_strips_trailing_noise'] = page.evaluate('''()=>{
            const a=classifyNewRaceText('萬金石馬拉松 2026/03/15 半程馬拉松');
            const b=classifyNewRaceText('2025 渣打公益馬拉松 2025-02-09 10 公里');
            return a.info.name==='萬金石馬拉松' && a.info.distanceKm===21.0975
                && b.info.name==='2025 渣打公益馬拉松' && b.info.distanceKm===10;
        }''')
        c['new_race_needs_both_name_and_date'] = page.evaluate('''()=>{
            return classifyNewRaceText('2026-12-20').isNewRace===false
                && classifyNewRaceText('臺北馬拉松').isNewRace===false
                && classifyNewRaceText('').isNewRace===false;
        }''')
        # 不可以搶走訂房、車票、心得
        c['new_race_yields_to_other_paste_kinds'] = page.evaluate('''()=>{
            const booking='訂房確認通知\\n飯店名稱：礁溪老爺酒店\\n入住：2026-12-19 15:00\\n退房：2026-12-21 11:00';
            const ticket='台灣高鐵 訂位代號 12345678\\n去程 車次 0613 2026-12-19 08:31 台北 → 左營 5車 12E\\n回程 車次 0842 2026-12-21 16:10 左營 → 台北 7車 3A';
            const report='今天配速控制得不錯，補給站都有停，最後衝線 2:59:31。我覺得這場表現很好。';
            return [booking,ticket,report].every(x=>classifyNewRaceText(x).isNewRace===false);
        }''')
        # 清單是空的時候也要能用——這正是最可能貼賽事資訊的時機
        c['new_race_paste_works_with_no_existing_races'] = page.evaluate('''async()=>{
            state.races=[]; state.creating=false;
            const dt=new DataTransfer();
            dt.setData('text','2025 渣打公益馬拉松\\n比賽日期：2025-02-09\\n距離：10 公里');
            document.dispatchEvent(new ClipboardEvent('paste',{clipboardData:dt,bubbles:true,cancelable:true}));
            await new Promise(s=>setTimeout(s,500));
            return state.creating===true
                && document.getElementById('new-name').value==='2025 渣打公益馬拉松'
                && document.getElementById('new-date').value==='2025-02-09'
                && document.getElementById('new-distance').value==='10';
        }''')
        # 日期早於今天 → 狀態自動帶「已完賽」，按下建立後真的存成 completed
        c['past_date_becomes_completed_on_create'] = page.evaluate('''async()=>{
            const statusPrefilled=document.getElementById('new-status').value==='completed';
            document.querySelector('[data-action="confirm-create"]').click();
            await new Promise(s=>setTimeout(s,600));
            const r=state.races[state.races.length-1];
            return statusPrefilled && r.status==='completed'
                && r.schedule.raceDate==='2025-02-09' && r.route.distanceKm===10;
        }''')
        # 未來日期不可以被改成已完賽
        c['future_date_keeps_default_status'] = page.evaluate('''async()=>{
            state.races=[]; state.creating=false;
            const dt=new DataTransfer();
            dt.setData('text','2030 未來馬拉松\\n比賽日期：2030-05-01\\n距離：21.0975 公里');
            document.dispatchEvent(new ClipboardEvent('paste',{clipboardData:dt,bubbles:true,cancelable:true}));
            await new Promise(s=>setTimeout(s,500));
            const prefilled=document.getElementById('new-status').value;
            document.querySelector('[data-action="confirm-create"]').click();
            await new Promise(s=>setTimeout(s,600));
            const r=state.races[state.races.length-1];
            return prefilled==='considering' && r.status==='considering';
        }''')
        # 新增表單要有距離欄位與常見距離的快捷清單
        c['create_form_has_distance_with_presets'] = page.evaluate('''async()=>{
            state.races=[]; startCreate();
            await new Promise(s=>setTimeout(s,400));
            const input=document.getElementById('new-distance');
            const list=document.getElementById('distance-presets');
            const vals=list?[...list.options].map(o=>o.value):[];
            const grid=document.querySelector('.create-grid');
            return !!input && !!grid && vals.includes('21.0975') && vals.includes('42.195')
                && vals.includes('5') && vals.includes('10') && vals.includes('30');
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
    'share':      lambda: Share('share'),
    'share_touch':lambda: ShareTouch(),
    'offline':    lambda: Offline(),
    'climate':    lambda: Climate('climate'),
    'publink':    lambda: PublicLink('publink'),
    'pubview':    lambda: PublicView('pubview'),
    'paste':      lambda: PasteReport('paste'),
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
