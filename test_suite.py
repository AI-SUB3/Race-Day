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
import json
import math
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


# v3.97.0 起，完全沒有資料的新裝置預設是簡易版。其他群組測的都是完整版的
# 功能，而且都是「先開空白頁、再塞資料」，所以開頁前先把偏好設成完整版
# （已經設過的不動）；簡易版自己的預設行為在 Simple 群組用沒有預設的 context 測。
PRESET_FULL_MODE_JS = "try{ if(!localStorage.getItem('ui-mode-v1')) localStorage.setItem('ui-mode-v1','full'); }catch(e){}"


def full_mode_context(browser, **kw):
    ctx = browser.new_context(**kw)
    ctx.add_init_script(PRESET_FULL_MODE_JS)
    return ctx


class Group:
    """一組相關的檢查，共用一個分頁。"""
    preset_full_mode = True

    def __init__(self, name, viewport=None, touch=False):
        self.name = name
        self.viewport = viewport or DESKTOP
        self.touch = touch
        self.checks = {}
        self.errors = []

    def run(self, browser):
        ctx = browser.new_context(viewport=self.viewport, has_touch=self.touch,
                                  is_mobile=self.touch)
        if self.preset_full_mode:
            ctx.add_init_script(PRESET_FULL_MODE_JS)
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
            // v4.0 起生涯數據（含榮譽櫃）在首頁的「生涯數據」分頁
            state.homeTab='career';
            renderAll();
            selectRace(null); await new Promise(s=>setTimeout(s,300));
            const el=document.querySelector('.trophy-cabinet-summary');
            if(el) el.click();
            await new Promise(s=>setTimeout(s,250));
            const body=document.getElementById('trophy-cabinet-body');
            const ok=!!(body && body.innerHTML.length);
            state.homeTab='races'; renderAll();
            return ok;
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
        # ---- 預算與行程摘要卡 ----
        LOGI_FIXTURE = '''()=>{
            state.races=[];
            for(let i=0;i<4;i++){ const r=emptyRace('國內賽'+i,'road_running','completed','202'+(1+i)+'-05-01');
              r.location.country='臺灣'; state.races.push(r); }
            const jp=emptyRace('若狹路越野賽','trail_running','registered','2026-09-27');
            jp.schedule.startTime='07:30'; jp.location.country='日本'; jp.location.city='福井県';
            jp.budget={registrationFee:10500,currency:'JPY',paymentStatus:'paid',chipDeposit:2000};
            jp.accommodations=[{hotelName:'福井パレスホテル',checkIn:'2026-09-26T15:00',checkOut:'2026-09-28T10:00',cost:18000},
                               {hotelName:'大阪前一晚',checkIn:'2026-09-25T15:00',checkOut:'2026-09-26T10:00',cost:9000}];
            jp.transportation=[{direction:'outbound',mode:'flight',departureTime:'2026-09-25T09:20',pickupLocation:'桃園機場',cost:14000},
                               {direction:'return',mode:'flight',departureTime:'2026-09-28T18:00',pickupLocation:'關西機場',cost:0}];
            jp.companions=[{name:'米奇',role:'partner'},{name:'Jenny',role:'friend'},{name:'阿龍',role:'friend'}];
            state.races.push(jp);
            window.__logiRace=jp;
            return true;
        }'''
        page.evaluate(LOGI_FIXTURE)
        # 金額要加總（報名＋住宿＋交通），押金另計不進總額
        c['logistics_card_totals_all_costs'] = page.evaluate('''()=>{
            const tt=logisticsTotals(window.__logiRace);
            const d=document.createElement('div'); d.innerHTML=logisticsDashCardHtml(window.__logiRace);
            const sub=d.querySelector('.dash-card-sub').textContent;
            return tt.total===51500 && tt.deposit===2000
                && sub.includes('JPY 51,500') && sub.includes('報名 10,500')
                && sub.includes('住宿 27,000') && sub.includes('交通 14,000')
                && sub.includes('已繳清') && sub.includes('押金');
        }''')
        # 第二行要講內容（飯店名、班次時間、同行者），不是數量
        c['logistics_card_second_line_shows_content'] = page.evaluate('''()=>{
            const d=document.createElement('div'); d.innerHTML=logisticsDashCardHtml(window.__logiRace);
            const sub2=d.querySelector('.dash-card-sub2').textContent;
            return sub2.includes('福井パレスホテル') && sub2.includes('09-26')
                && sub2.includes('飛機') && sub2.includes('09:20') && sub2.includes('桃園機場')
                && sub2.includes('米奇') && !/住宿 2|交通 2/.test(sub2);
        }''')
        # 四種警示各自成立，而且只有警示那一段是警示色
        c['logistics_card_warnings'] = page.evaluate('''()=>{
            const clone=()=>JSON.parse(JSON.stringify(window.__logiRace));
            const warn=r=>logisticsWarnings(r).join('|');
            const ok=logisticsWarnings(window.__logiRace).length===0;
            const unpaid=clone(); unpaid.budget.paymentStatus='unpaid';
            const gap=clone(); gap.accommodations=[{hotelName:'只住前一晚',checkIn:'2026-09-25T15:00',checkOut:'2026-09-26T10:00'}];
            const late=clone(); late.transportation=[{direction:'outbound',mode:'flight',departureTime:'2026-09-27T09:20'}];
            const none=clone(); none.transportation=[];
            return ok && warn(unpaid).includes('報名費未付')
                && warn(gap).includes('住宿沒有涵蓋比賽當天')
                && warn(late).includes('去程交通晚於起跑時間')
                && warn(none).includes('海外賽事尚未安排交通');
        }''')
        c['logistics_warning_is_styled_separately'] = page.evaluate('''()=>{
            const r=JSON.parse(JSON.stringify(window.__logiRace));
            r.budget.paymentStatus='unpaid';
            const d=document.createElement('div'); d.innerHTML=logisticsDashCardHtml(r);
            const warn=d.querySelector('.dash-card-warn');
            const sub2=d.querySelector('.dash-card-sub2');
            // 行程內容不可以被包在警示色裡，否則整行看起來都像出問題
            return !!warn && warn.textContent.includes('報名費未付')
                && !warn.textContent.includes('福井パレスホテル')
                && sub2.textContent.includes('福井パレスホテル');
        }''')
        # 資料不全時不要亂報警示（寧可不報）
        c['logistics_warnings_stay_quiet_without_data'] = page.evaluate('''()=>{
            const bare=emptyRace('空','road_running','considering','2026-01-01');
            const d=document.createElement('div'); d.innerHTML=logisticsDashCardHtml(bare);
            return logisticsWarnings(bare).length===0
                && d.querySelector('.dash-card-sub').textContent.includes('尚未填寫')
                && !d.querySelector('.dash-card-warn');
        }''')
        # 交通多了 cost 欄位（3c 的前提）
        c['transportation_has_cost_field'] = page.evaluate('''()=>{
            const hasField=TRANSPORT_FIELDS.some(f=>f.path==='cost');
            const fresh=LIST_META.transportation.factory();
            return hasField && ('cost' in fresh) && fresh.cost===null;
        }''')
        # ---- 當日氣象：四種狀態都要說清楚，不可以靜默空白 ----
        c['weather_block_explains_every_state'] = page.evaluate('''()=>{
            const pts=[]; for(let i=0;i<50;i++) pts.push({lat:25+i*0.001,lon:121.5+i*0.001});
            const today=todayISO();
            const plus=d=>{ const x=new Date(today+'T00:00:00'); x.setDate(x.getDate()+d);
              return x.toISOString().slice(0,10); };
            const mk=(date,track)=>{ const r=emptyRace('x','road_running',
              date<today?'completed':'registered',date);
              if(track) r.route.trackPoints=pts; return r; };
            const txt=r=>{ const d=document.createElement('div'); d.innerHTML=raceDayWeatherBlockHtml(r);
              return d.textContent.replace(/\\s+/g,' ').trim(); };
            return txt(mk(plus(3),true)).includes('抓取即時預報')
                && txt(mk(plus(3),false)).includes('匯入 GPX/FIT')
                && txt(mk(plus(60),true)).includes('7 天')
                && txt(mk(plus(-30),true)).includes('歷史天氣')
                && txt(mk(plus(-30),false)).includes('無法自動查詢');
        }''')
        # 詳情頁裡要真的有「抓取即時預報」的入口（原本只在備戰釘選面板裡）
        c['weather_fetch_button_exists_in_detail'] = page.evaluate('''async()=>{
            const pts=[]; for(let i=0;i<50;i++) pts.push({lat:25+i*0.001,lon:121.5+i*0.001});
            const x=new Date(todayISO()+'T00:00:00'); x.setDate(x.getDate()+3);
            state.races=[];
            const r=emptyRace('近期賽事','road_running','registered',x.toISOString().slice(0,10));
            r.route.trackPoints=pts;
            state.races.push(r); selectRace(r.id,{scroll:false});
            await new Promise(s=>setTimeout(s,300));
            const sec=document.getElementById('section-route');
            if(sec&&!sec.open){ sec.querySelector('summary').click(); await new Promise(s=>setTimeout(s,450)); }
            const btn=document.querySelector('#section-route [data-action="fetch-live-weather"]');
            return !!btn && btn.dataset.id===r.id;
        }''')
        # 沒有軌跡的歷史賽事不可以什麼都不說
        c['weather_no_track_is_not_silent'] = page.evaluate('''async()=>{
            state.races=[];
            const r=emptyRace('舊賽事','road_running','completed','2022-03-20');
            state.races.push(r); selectRace(r.id,{scroll:false});
            await new Promise(s=>setTimeout(s,300));
            const sec=document.getElementById('section-route');
            if(sec&&!sec.open){ sec.querySelector('summary').click(); await new Promise(s=>setTimeout(s,450)); }
            const sub=[...document.querySelectorAll('#section-route .subsection')].pop();
            return sub.textContent.includes('無法自動查詢');
        }''')
        # ---- 即時預報要回填「預報類」欄位 ----
        c['live_forecast_autofills_forecast_fields'] = page.evaluate('''()=>{
            const r=emptyRace('近期賽事','road_running','registered','2026-10-01');
            r.schedule.startTime='06:30';
            r.liveForecast={fetchedAt:new Date().toISOString(),
              times:['2026-10-01T05:00','2026-10-01T06:00','2026-10-01T07:00'],
              temp:[20,21,22],feelsLike:[19,20,21],humidity:[80,78,75],
              precipProb:[40,51,60],windSpeed:[12.3,14.8,16.1],
              windDirection:[90,135,180],gust:[25,28.8,30]};
            const changed=applyLiveForecastAutofill(r);
            return changed===true
                && r.climateForecast.rainProbabilityPct===51
                && r.climateForecast.windSpeedKmh===14.8
                && r.climateForecast.windDirection==='東南風';
        }''')
        # 「實際體感溫度／當日濕度」是賽後才知道的值，預報不可以先佔位——
        # 佔了之後歷史天氣的回填（只填空欄位）就再也補不進真正的實測值
        c['live_forecast_leaves_actual_fields_for_history'] = page.evaluate('''()=>{
            const r=emptyRace('近期賽事','road_running','registered','2026-10-01');
            r.schedule.startTime='06:30';
            r.liveForecast={times:['2026-10-01T06:00'],temp:[21],feelsLike:[20],
              humidity:[78],precipProb:[51],windSpeed:[14.8],windDirection:[135],gust:[28.8]};
            applyLiveForecastAutofill(r);
            const stillEmpty=r.raceDayWeather.feelsLikeTempC==null&&r.raceDayWeather.humidityPct==null;
            // 賽後歷史天氣要補得進去
            r.historicalWeather={times:['2026-10-01T06:00'],feelsLike:[26.4],humidity:[88],
              windSpeed:[9.2],windDirection:[45],precip:[0]};
            applyHistoricalWeatherAutofill(r);
            return stillEmpty && r.raceDayWeather.feelsLikeTempC===26.4
                && r.raceDayWeather.humidityPct===88;
        }''')
        # 不覆蓋使用者自己填的值、重複執行不會重複改
        c['live_forecast_autofill_is_safe'] = page.evaluate('''()=>{
            const lf={times:['2026-10-01T06:00'],precipProb:[51],windSpeed:[14.8],windDirection:[135]};
            const manual=emptyRace('手動','road_running','registered','2026-10-01');
            manual.schedule.startTime='06:30';
            manual.climateForecast.rainProbabilityPct=10;
            manual.liveForecast=lf;
            applyLiveForecastAutofill(manual);
            const kept=manual.climateForecast.rainProbabilityPct===10;
            const second=applyLiveForecastAutofill(manual);
            // 舊版快取沒有風速風向欄位也不能爆
            const old=emptyRace('舊快取','road_running','registered','2026-10-01');
            old.schedule.startTime='06:30';
            old.liveForecast={times:['2026-10-01T06:00'],temp:[21],precipProb:[51],gust:[28.8]};
            applyLiveForecastAutofill(old);
            return kept && second===false && old.climateForecast.rainProbabilityPct===51
                && old.climateForecast.windSpeedKmh==null;
        }''')
        # 歷年平均對未來賽事也要抓（原本綁 raceIsHistorical，未來賽事永遠空）
        c['climate_average_fetch_not_gated_to_past'] = page.evaluate('''()=>{
            const src=String(renderDetail);
            // 只看實際的 if 條件那一行——註解裡本來就會提到 raceIsHistorical
            // （說明為什麼拿掉），用前後文字擷取會連註解一起算進去
            const line=src.split(String.fromCharCode(10)).find(l=>
              l.indexOf('historicalAverageFetchingRaceId')>=0 && l.trim().indexOf('if(')===0);
            return !!line && !/raceIsHistorical/.test(line) && /raceHasGpsTrack/.test(line);
        }''')
        # ---- 歷年平均：±3 天區間取樣、並標示樣本數 ----
        c['climate_average_uses_day_window'] = page.evaluate('''async()=>{
            const urls=[];
            const realFetch=window.fetch;
            window.fetch=async(u)=>{ urls.push(String(u)); throw new Error('blocked'); };
            state.races=[];
            const r=emptyRace('跨年測試','road_running','registered','2027-01-02');
            r.route.trackPoints=[{lat:25,lon:121.5}];
            state.races.push(r);
            if(historicalAverageAttempted.clear) historicalAverageAttempted.clear();
            await fetchHistoricalAverageWeatherForRace(r.id);
            window.fetch=realFetch;
            const ranges=urls.map(u=>{ const m=u.match(/start_date=([0-9-]+)&end_date=([0-9-]+)/);
              return m?m[1]+'~'+m[2]:''; });
            // 五年各一次查詢，每次都是前後 3 天；跨年要正確進位
            return urls.length===5
                && ranges[0]==='2025-12-30~2026-01-05'
                && ranges[4]==='2021-12-30~2022-01-05';
        }''')
        # 樣本數與年數要被記下來（某幾年查不到時畫面上看得出來）
        c['climate_average_shows_sample_basis'] = page.evaluate('''()=>{
            const mk=ha=>{ const r=emptyRace('x','road_running','registered','2026-12-20');
              r.route.trackPoints=[{lat:25,lon:121.5}]; r.historicalAverageWeather=ha; return r; };
            const txt=r=>{ const d=document.createElement('div');
              d.innerHTML=raceDayWeatherBlockHtml(r); return d.textContent.replace(/\\s+/g,' '); };
            const full=txt(mk({years:[2025,2024,2023,2022,2021],windowDays:3,sampleCount:35,avgTempC:22.4,avgHumidityPct:78}));
            const partial=txt(mk({years:[2024,2023],windowDays:3,sampleCount:14,avgTempC:21.9,avgHumidityPct:80}));
            const legacy=txt(mk({years:[2025,2024,2023],avgTempC:20.1,avgHumidityPct:75}));
            return full.includes('5 年') && full.includes('35 筆') && full.includes('22.4°C')
                && partial.includes('2 年') && partial.includes('14 筆')
                && legacy.includes('3 年');   // 舊快取沒有樣本數也要能顯示
        }''')
        # 2/29：非閏年整年跳過，不拿 2/28 來湊
        c['climate_average_skips_invalid_leap_day'] = page.evaluate('''async()=>{
            const urls=[];
            const realFetch=window.fetch;
            window.fetch=async(u)=>{ urls.push(String(u)); throw new Error('blocked'); };
            state.races=[];
            const r=emptyRace('閏日','road_running','registered','2028-02-29');
            r.route.trackPoints=[{lat:25,lon:121.5}];
            state.races.push(r);
            if(historicalAverageAttempted.clear) historicalAverageAttempted.clear();
            await fetchHistoricalAverageWeatherForRace(r.id);
            window.fetch=realFetch;
            // 2027~2023 只有 2024 是閏年，所以只該送出一次查詢
            return urls.length===1 && urls[0].includes('2024-02-26') && urls[0].includes('2024-03-03');
        }''')
        # ---- 意見回饋按鈕 ----
        # ---- 意見回饋按鈕 ----
        # 正式版（v3.92 起已設定使用者的表單）：按下去要開表單，版本／裝置／畫面都帶入
        c['feedback_opens_real_form_prefilled'] = page.evaluate('''async()=>{
            let url=null; const real=window.open; window.open=(u)=>{ url=u; return null; };
            document.getElementById('btn-feedback').click();
            await new Promise(s=>setTimeout(s,200));
            window.open=real;
            if(!url) return false;
            const u=new URL(url);
            return u.pathname==='/forms/d/e/1FAIpQLSfuxfXHORQ96fceVn1fPc6RfE6Z7wuquU2Loj4Hor_HKe4rsA/viewform'
                && u.searchParams.get('usp')==='pp_url' && u.searchParams.get('entry.1727311429')===APP_VERSION
                && !!u.searchParams.get('entry.1690470865') && !!u.searchParams.get('entry.1958998644');
        }''')
        # 沒設定表單網址時的保護：不可以是死按鈕，要說明（用清空網址的副本驗證）
        import pathlib as _pl, re as _re
        _src=_re.sub(r"const FEEDBACK_FORM_URL='[^']*';","const FEEDBACK_FORM_URL='';",_pl.Path(APP).read_text(encoding='utf-8'),count=1)
        _tmp=_pl.Path('/tmp/_feedback_unconfigured.html'); _tmp.write_text(_src,encoding='utf-8')
        _pg=page.context.new_page(); _pg.goto('file://'+str(_tmp)); _pg.wait_for_timeout(900)
        c['feedback_not_configured_shows_notice'] = _pg.evaluate('''async()=>{
            document.querySelectorAll('.foreground-toast').forEach(n=>n.remove());
            let opened=false; const real=window.open; window.open=()=>{opened=true;};
            document.getElementById('btn-feedback').click();
            await new Promise(s=>setTimeout(s,200));
            window.open=real;
            const toast=[...document.querySelectorAll('.foreground-toast')].map(n=>n.textContent).join('');
            return opened===false && toast.includes('準備中') && buildFeedbackUrl()==='';
        }''')
        _pg.close()
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
            // v3.99.0：順序是 區段導覽列（含返回鍵，放最上面）→ header → 儀表板 → 各區段
            // （v3.34.0 原本是 header → 導覽列 → 儀表板）
            const firstSection=document.querySelector('details.section');
            const order=hero&&nav&&header&&firstSection
                && (nav.compareDocumentPosition(header)&Node.DOCUMENT_POSITION_FOLLOWING)
                && (header.compareDocumentPosition(hero)&Node.DOCUMENT_POSITION_FOLLOWING)
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


# 依速度剖面產生 FIT（單一或多個 session），用來測二鐵分段推算。
FIT_PROFILE_GENERATOR_JS = r'''// 依速度剖面產生 FIT：每 2 秒一個點、直線前進。segments:[{sec,kmh,hr}]；
// sessions 不給＝整場單一 session（模擬手錶用「跑步」單一模式錄完）；
// 給了就依 [{sport, fromSeg, toSeg}] 寫多個 session（模擬多項運動模式）。
window.__makeFitProfile=function(opt){
  const FIT_EPOCH=Date.UTC(1989,11,31,0,0,0)/1000;
  const start=Math.round(opt.start.getTime()/1000)-FIT_EPOCH;
  const bytes=[]; const u8=v=>bytes.push(v&255); const u16=v=>{u8(v);u8(v>>8);}; const u32=v=>{u8(v);u8(v>>8);u8(v>>16);u8(v>>24);};
  // withDist：多寫 record 欄位 5（手錶記的累計距離）；segments[i].noise：座標加上
  // 左右亂跳的雜訊（公尺），模擬開放水域游泳時斷斷續續的 GPS——距離欄位不受影響
  // enhancedAlt：海拔只寫欄位 78（新款 Garmin 的寫法），不寫欄位 2
  // withTemp：寫欄位 13（溫度，sint8）；segments[i].temp 或 segments[i].tempFirst＋tempFirstSec（剛下水偏熱）
  const fields=[[253,4,0x86],[0,4,0x85],[1,4,0x85],opt.enhancedAlt?[78,4,0x86]:[2,2,0x84],[3,1,0x02]];
  if(opt.withDist) fields.push([5,4,0x86]);
  if(opt.withTemp) fields.push([13,1,0x01]);
  // device_info：hrSource 'strap'＝ANT+ 心率帶（source 1、type 120）；'wrist'＝內建光學（source 5、type 10）
  if(opt.hrSource){
    const strap=opt.hrSource==='strap';
    u8(0x42);u8(0);u8(0);u16(23);u8(3);
    [[0,1,0x02],[1,1,0x02],[25,1,0x00]].forEach(f=>{u8(f[0]);u8(f[1]);u8(f[2]);});
    u8(0x02); u8(strap?1:4); u8(strap?120:10); u8(strap?1:5);
  }
  u8(0x40);u8(0);u8(0);u16(20);u8(fields.length);
  fields.forEach(f=>{u8(f[0]);u8(f[1]);u8(f[2]);});
  let lat=24.98, lon=121.53, t=0, dist=0; const segBounds=[]; let seed=7;
  const rnd=()=>{ seed=(seed*9301+49297)%233280; return seed/233280-0.5; };
  const toSc=d=>Math.round(d*Math.pow(2,31)/180);
  opt.segments.forEach((sg,si)=>{
    const from={t,dist};
    for(let s=0;s<sg.sec;s+=2){
      const m=sg.kmh/3.6*2; dist+=m;
      const heading=(si%2?0.3:0.9);
      lat+=Math.cos(heading)*m/111320; lon+=Math.sin(heading)*m/(111320*Math.cos(lat*Math.PI/180));
      t+=2;
      const nz=sg.noise||0, jl=rnd()*nz/111320, jo=rnd()*nz/111320;
      const altRaw=Math.round(((sg.alt!=null?sg.alt:20)+(sg.climb?sg.climb*(s/sg.sec):0)+500)*5);
      u8(0x00); u32(start+t); u32(toSc(lat+jl)>>>0); u32(toSc(lon+jo)>>>0);
      if(opt.enhancedAlt) u32(altRaw); else u16(altRaw);
      u8(sg.hr||150);
      if(opt.withDist) u32(Math.round(dist*100));
      if(opt.withTemp){ const tv=(sg.tempFirstSec&&s<sg.tempFirstSec)?sg.tempFirst:(sg.temp!=null?sg.temp:25); u8(tv<0?256+tv:tv); }
    }
    segBounds.push({from,to:{t,dist}});
  });
  u8(0x41);u8(0);u8(0);u16(18);u8(7);
  [[2,4,0x86],[253,4,0x86],[5,1,0x00],[7,4,0x86],[9,4,0x86],[16,1,0x02],[22,2,0x84]].forEach(f=>{u8(f[0]);u8(f[1]);u8(f[2]);});
  const sessions=opt.sessions||[{sport:1,fromSeg:0,toSeg:opt.segments.length-1}];
  sessions.forEach(ss=>{
    const a=segBounds[ss.fromSeg].from, b=segBounds[ss.toSeg].to;
    u8(0x01); u32(start+a.t); u32(start+b.t); u8(ss.sport); u32((b.t-a.t)*1000); u32(Math.round((b.dist-a.dist)*100)); u8(150); u16(ss.ascent!=null?ss.ascent:0xFFFF);
  });
  const data=new Uint8Array(bytes); const out=new Uint8Array(14+data.length); const dv=new DataView(out.buffer);
  dv.setUint8(0,14); dv.setUint8(1,0x10); dv.setUint16(2,2093,true); dv.setUint32(4,data.length,true);
  out[8]=46;out[9]=70;out[10]=73;out[11]=84; out.set(data,14);
  return new File([out],opt.name||'profile.fit',{type:'application/octet-stream'});
};
window.__DUATHLON_SEGMENTS=[
  {sec:1224,kmh:14.7,hr:165},                    // 0 跑 5K
  {sec:20,kmh:10,hr:160},{sec:60,kmh:1,hr:150},{sec:26,kmh:9,hr:150},   // 1-3 T1：跑進來、換裝、牽車
  {sec:1800,kmh:33,hr:158},{sec:30,kmh:12,hr:150},{sec:1800,kmh:33,hr:158},{sec:30,kmh:12,hr:150},{sec:734,kmh:33,hr:158}, // 4-8 騎 40K（兩次折返）
  {sec:20,kmh:15,hr:150},{sec:46,kmh:1,hr:148},{sec:10,kmh:8,hr:150},   // 9-11 T2：滑進來、換鞋、起跑
  {sec:1276,kmh:14.1,hr:172},                    // 12 跑 5K
];
window.__TRIATHLON_SEGMENTS=[
  {sec:1800,kmh:3,hr:150},                               // 0 游泳 1.5K
  {sec:120,kmh:9,hr:160},{sec:90,kmh:1,hr:150},{sec:30,kmh:8,hr:150},   // 1-3 T1：上岸跑、換裝、牽車
  {sec:2400,kmh:33,hr:155},{sec:30,kmh:12,hr:145},{sec:1964,kmh:33,hr:155},   // 4-6 騎 40K
  {sec:20,kmh:15,hr:148},{sec:60,kmh:1,hr:146},{sec:10,kmh:8,hr:150},  // 7-9 T2
  {sec:2571,kmh:14,hr:170},                              // 10 跑 10K
];
'''

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

        # ---- 單一模式錄完的二鐵 FIT：依速度推算分段（v3.82.0） ----
        page.add_script_tag(content=FIT_PROFILE_GENERATOR_JS)
        c['duathlon_single_session_legs_inferred'] = page.evaluate('''async()=>{
            const s=await parseActivityFile(__makeFitProfile({start:new Date('2021-05-09T07:00:00'),segments:__DUATHLON_SEGMENTS}));
            const L=s.inferredLegs||[];
            const near=(v,truth,tol)=>Math.abs(v-truth)<=tol;
            return s.fitSessionCount===1 && (s.legs||[]).length===0 && L.length===5
                && L.map(l=>l.sport).join()==='running,transition,cycling,transition,running'
                && L.every(l=>l.inferred===true)
                && near(L[2].durationSeconds,4394,15)            // 騎車：真實 73:14
                && L[1].durationSeconds>=60 && L[1].durationSeconds<=120   // T1：真實 106 秒（只看得到換裝那段，會略短）
                && L[3].durationSeconds>=45 && L[3].durationSeconds<=100   // T2：真實 76 秒
                && near(L[0].distanceKm,5.0,0.2) && near(L[2].distanceKm,39.9,0.8) && near(L[4].distanceKm,5.0,0.2)
                && L[0].avgHr===165 && L[2].avgHr===158 && L[4].avgHr===172;   // 心率分到對的段
        }''')
        # 不該拆的不可以拆：路跑中途慢走、越野下坡衝刺、純騎車、騎車前後跑太短
        c['duathlon_inference_no_false_positives'] = page.evaluate('''async()=>{
            const st=new Date('2021-05-09T07:00:00');
            const inf=async segs=>(await parseActivityFile(__makeFitProfile({start:st,segments:segs}))).inferredLegs;
            return !(await inf([{sec:1500,kmh:14},{sec:40,kmh:4},{sec:1500,kmh:14},{sec:40,kmh:4},{sec:1200,kmh:14.5}]))
                && !(await inf([{sec:1800,kmh:8},{sec:180,kmh:22},{sec:1800,kmh:9}]))
                && !(await inf([{sec:3600,kmh:30}]))
                && !(await inf([{sec:60,kmh:14},{sec:3600,kmh:30},{sec:60,kmh:14}]));
        }''')
        # 用多項運動模式錄的檔案：照舊用手錶記的精確分段，不走推算
        c['duathlon_multisession_uses_watch_legs'] = page.evaluate('''async()=>{
            const s=await parseActivityFile(__makeFitProfile({start:new Date('2021-05-09T07:00:00'),segments:__DUATHLON_SEGMENTS,
              sessions:[{sport:1,fromSeg:0,toSeg:0},{sport:3,fromSeg:1,toSeg:3},{sport:2,fromSeg:4,toSeg:8},{sport:3,fromSeg:9,toSeg:11},{sport:1,fromSeg:12,toSeg:12}]}));
            return (s.legs||[]).length===5 && !s.inferredLegs && !s.legs.some(l=>l.inferred)
                && s.legs[1].durationSeconds===106 && s.legs[3].durationSeconds===76;
        }''')
        # 套用：鐵人兩項才套推算分段；其他種類只提示
        c['duathlon_inferred_legs_apply_only_to_duathlon'] = page.evaluate('''async()=>{
            const run=async sport=>{
              state.races=[];
              const r=emptyRace('tSt 新北微風鐵人賽',sport,'completed','2021-05-09'); state.races.push(r);
              selectRace(r.id,{scroll:false}); await new Promise(s=>setTimeout(s,250));
              document.querySelectorAll('.foreground-toast').forEach(n=>n.remove());
              await importActivityFile(__makeFitProfile({start:new Date('2021-05-09T07:00:00'),segments:__DUATHLON_SEGMENTS}));
              await new Promise(s=>setTimeout(s,500));
              const ok=document.querySelector('[data-action="confirm-gpx-import"]');
              if(ok){ ok.click(); await new Promise(s=>setTimeout(s,600)); }
              document.getElementById('section-post').open=true;
              await new Promise(s=>setTimeout(s,200));
              return {legs:(state.races[0].legs||[]).length,
                toast:[...document.querySelectorAll('.foreground-toast')].map(n=>n.textContent).join(' '),
                note:!!document.querySelector('.leg-inferred-note')};
            };
            const du=await run('duathlon'), road=await run('road_running');
            return du.legs===5 && du.note && du.toast.includes('依速度推算')
                && road.legs===0 && !road.note && road.toast.includes('改成「鐵人兩項」');
        }''')

        # ---- v3.83.0：每段各自的每公里分段、雷達圖依分段計算、三鐵推算 ----
        IMPORT = '''const importAs=async(sport,segs,sessions)=>{
            state.races=[]; const r=emptyRace('測試',sport,'completed','2021-05-09'); state.races.push(r);
            selectRace(r.id,{scroll:false}); await new Promise(s=>setTimeout(s,250));
            await importActivityFile(__makeFitProfile({start:new Date('2021-05-09T07:00:00'),segments:segs,sessions}));
            await new Promise(s=>setTimeout(s,450));
            const ok=document.querySelector('[data-action="confirm-gpx-import"]'); if(ok){ ok.click(); await new Promise(s=>setTimeout(s,550)); }
            return state.races[0];
        };'''
        c['legs_get_their_own_splits'] = page.evaluate('''async()=>{ %s
            const du=await importAs('duathlon',__DUATHLON_SEGMENTS);
            const cnt=du.legs.map(l=>(l.splits||[]).length);
            // 多 session 的三鐵檔：游泳與轉換區不算每公里分段
            const tri=await importAs('triathlon',__TRIATHLON_SEGMENTS,[{sport:5,fromSeg:0,toSeg:0},{sport:3,fromSeg:1,toSeg:3},
              {sport:2,fromSeg:4,toSeg:6},{sport:3,fromSeg:7,toSeg:9},{sport:1,fromSeg:10,toSeg:10}]);
            const tcnt=tri.legs.map(l=>l.sport[0]+(l.splits||[]).length).join(' ');
            // 跑步段 2571 秒×14 km/h＝9.998 km，不滿 10 公里，最後一段不足 1 公里不計 → 9 個；
            // 游泳 1.5 km 每 100 公尺一段（v3.84.0）→ 14 個（最後一段落在切點上，同樣不計）
            return cnt.join()==='5,0,39,0,5' && tcnt==='s14 t0 c40 t0 r9' && !tri.legs.some(l=>l.inferred);
        }''' % IMPORT)
        c['triathlon_single_session_legs_inferred'] = page.evaluate('''async()=>{ %s
            const r=await importAs('triathlon',__TRIATHLON_SEGMENTS);
            const L=r.legs||[];
            return L.map(l=>l.sport).join()==='swimming,transition,cycling,transition,running'
                && L.every(l=>l.inferred) && L[0].distanceKm===null            // 水裡 GPS 不可靠，不給游泳距離
                && Math.abs(L[0].durationSeconds-1800)<=20
                && L[1].durationSeconds>=200 && L[1].durationSeconds<=270   // T1 含上岸跑：真實 240 秒
                && Math.abs(L[2].durationSeconds-4394)<=15
                && Math.abs(L[4].distanceKm-10)<=0.3;
        }''' % IMPORT)
        c['splits_table_grouped_by_leg'] = page.evaluate('''async()=>{
            const race=state.races[0];   // 上一項的三鐵
            const d=document.createElement('div'); d.innerHTML=renderSplitsChart(race);
            const heads=[...d.querySelectorAll('.splits-leg-head')].map(x=>x.textContent);
            const bike=[...d.querySelectorAll('.leg-cycling .splits-gap-primary')].map(x=>x.textContent);
            const run=[...d.querySelectorAll('.leg-running')];
            const firstRunKm=run[0]&&run[0].querySelector('.splits-dist').textContent;
            return !!d.querySelector('.splits-by-leg') && heads.length===3
                && heads[0].includes('游泳') && !!d.querySelector('.splits-leg-note')
                && bike.length===40 && bike.every(x=>/km\\/h$/.test(x))
                && run.length===10 && firstRunKm==='1K';                    // 每段公里數從 1 重新算
        }''')
        c['old_legs_without_splits_fall_back_by_time'] = page.evaluate('''async()=>{ %s
            const du=await importAs('duathlon',__DUATHLON_SEGMENTS);
            const old=JSON.parse(JSON.stringify(du)); old.legs.forEach(l=>delete l.splits);
            const lg=legSplitGroups(old);
            const kept=lg.groups.reduce((a,g)=>a+g.splits.length,0);
            const d=document.createElement('div'); d.innerHTML=renderSplitsChart(old);
            // 跨越交界的那幾公里略過，其餘歸到正確的段；畫面上提示可以重新匯入
            return lg.precise===false && kept<old.splits.length && kept>=old.splits.length-4
                && lg.groups.find(g=>g.leg.sport==='cycling').splits.length>=37
                && !!d.querySelector('.splits-leg-approx');
        }''' % IMPORT)
        c['radar_stability_and_hr_per_leg'] = page.evaluate('''async()=>{ %s
            const du=await importAs('duathlon',__DUATHLON_SEGMENTS);
            const dims=computeRaceRadar(du);
            const st=dims.find(d=>d.key==='stability');
            // 跑步最大心率 190、騎車 175：同樣 158 bpm，騎車段的區間比較高
            const saved=userProfile&&userProfile.hr;
            userProfile.hr={running:{restingHr:50,maxHr:190},cycling:{restingHr:50,maxHr:175}};
            const zr=hrZoneInfoForRace(158,du,'running').zone, zc=hrZoneInfoForRace(158,du,'cycling').zone;
            userProfile.hr=saved;
            const cv=parseFloat(st.raw.replace('CV ',''));
            return cv<10 && st.raw.includes('分段') && st.value>0.6 && zc>zr;
        }''' % IMPORT)
        c['single_sport_splits_and_radar_unchanged'] = page.evaluate('''()=>{
            const solo=emptyRace('路跑','road_running','completed','2026-01-01');
            solo.splits=[1,2,3,4,5].map(i=>({distanceKm:1,splitTimeSeconds:300+i,avgPaceSecPerKm:300+i,avgHr:150}));
            const d=document.createElement('div'); d.innerHTML=renderSplitsChart(solo);
            const st=computeRaceRadar(solo).find(x=>x.key==='stability');
            return !d.querySelector('.splits-by-leg') && d.querySelectorAll('tbody tr').length===5
                && !st.raw.includes('分段');
        }''')
        # ---- 游泳每 100 公尺一個分段（v3.84.0） ----
        SWIM = '''const SES=[{sport:5,fromSeg:0,toSeg:0},{sport:3,fromSeg:1,toSeg:3},{sport:2,fromSeg:4,toSeg:6},{sport:3,fromSeg:7,toSeg:9},{sport:1,fromSeg:10,toSeg:10}];
            const noisy=__TRIATHLON_SEGMENTS.map((sg,i)=>i===0?Object.assign({},sg,{noise:25}):sg);
            const swimLeg=async o=>{ const s=await parseActivityFile(__makeFitProfile(Object.assign({start:new Date('2021-05-09T07:00:00'),sessions:SES},o)));
              const race=emptyRace('三鐵','triathlon','completed','2021-05-09'); race.legs=s.legs; race.splits=s.splits;
              return {race,leg:s.legs.find(l=>l.sport==='swimming')}; };'''
        # 手錶記的累計距離優先：座標加了雜訊，分段仍然正確（每 100 公尺 2 分鐘）
        c['swim_splits_every_100m_from_watch_distance'] = page.evaluate('''async()=>{ %s
            const {leg}=await swimLeg({segments:noisy,withDist:true});
            const sp=leg.splits||[];
            return sp.length>=14 && sp.every(x=>x.distanceKm===0.1 && x.splitTimeSeconds===120 && x.avgPaceSecPerKm===1200);
        }''' % SWIM)
        # 只有亂掉的 GPS：算出比世界紀錄還快的配速 → 整段不列，並說明原因
        c['swim_splits_rejected_when_gps_is_nonsense'] = page.evaluate('''async()=>{ %s
            const {race,leg}=await swimLeg({segments:noisy,withDist:false});
            const d=document.createElement('div'); d.innerHTML=renderSplitsChart(race);
            return (leg.splits||[]).length===0 && leg.swimGpsRejected===true
                && d.querySelector('.splits-leg-note').textContent.includes('世界紀錄');
        }''' % SWIM)
        c['swim_table_rows_per_100m'] = page.evaluate('''async()=>{ %s
            const {race}=await swimLeg({segments:noisy,withDist:true});
            const d=document.createElement('div'); d.innerHTML=renderSplitsChart(race);
            const rows=[...d.querySelectorAll('.leg-swimming')];
            return rows.length>=14 && rows[0].querySelector('.splits-dist').textContent==='100 m'
                && rows[1].querySelector('.splits-dist').textContent==='200 m'
                && rows[0].querySelector('.splits-gap-primary').textContent.includes('/100m');
        }''' % SWIM)
        # 推算的游泳段（跑步模式錄的）刻意不算，並說明
        c['inferred_swim_has_no_splits'] = page.evaluate('''async()=>{
            const s=await parseActivityFile(__makeFitProfile({start:new Date('2021-05-09T07:00:00'),segments:__TRIATHLON_SEGMENTS}));
            const race=emptyRace('三鐵','triathlon','completed','2021-05-09'); race.legs=s.inferredTriLegs; race.splits=s.splits;
            const d=document.createElement('div'); d.innerHTML=renderSplitsChart(race);
            const swim=race.legs.find(l=>l.sport==='swimming');
            return !(swim.splits&&swim.splits.length) && d.querySelector('.splits-leg-note').textContent.includes('跑步模式');
        }''')
        # 雷達不納入游泳：游泳段 GPS 再亂，穩定度都不變
        c['radar_excludes_swim'] = page.evaluate('''async()=>{ %s
            const a=await swimLeg({segments:__TRIATHLON_SEGMENTS,withDist:true});
            const b=await swimLeg({segments:__TRIATHLON_SEGMENTS.map((sg,i)=>i===0?Object.assign({},sg,{kmh:1.5}):sg),withDist:true});
            const st=r=>computeRaceRadar(r).find(x=>x.key==='stability').raw;
            // 游泳慢了一倍，穩定度照樣只看騎車與跑步
            return st(a.race)===st(b.race) && (a.leg.splits||[]).length>0;
        }''' % SWIM)



class Radar(Group):
    """多項運動雷達圖（v3.85 疊圖、v3.86 加入游泳）＋ FIT 海拔／水溫／心率來源。
    從 multisport 拆出來：那個群組每項都要產生並解析 FIT，已經接近 300 秒上限。"""

    def body(self, page):
        c = self.checks
        page.add_script_tag(content=FIT_PROFILE_GENERATOR_JS)
        page.evaluate('''()=>{ userProfile=userProfile||{};
            userProfile.hr={running:{restingHr:50,maxHr:190},cycling:{restingHr:50,maxHr:175},swimming:{restingHr:50,maxHr:170}}; }''')
        FIX = '''const SEGS=__TRIATHLON_SEGMENTS.map((sg,i)=>i===0?Object.assign({},sg,{temp:27,tempFirst:32,tempFirstSec:120}):sg);
            const SES=[{sport:5,fromSeg:0,toSeg:0},{sport:3,fromSeg:1,toSeg:3},{sport:2,fromSeg:4,toSeg:6,ascent:420},
                       {sport:3,fromSeg:7,toSeg:9},{sport:1,fromSeg:10,toSeg:10,ascent:35}];
            const fit=o=>__makeFitProfile(Object.assign({start:new Date('2025-04-26T06:30:00'),segments:SEGS,sessions:SES,
                          withDist:true,withTemp:true,enhancedAlt:true,hrSource:'wrist'},o||{}));
            const importAs=async(sport,o)=>{
              state.races=[]; const r=emptyRace('鐵人',sport,'completed','2025-04-26'); state.races.push(r);
              selectRace(r.id,{scroll:false}); await new Promise(s=>setTimeout(s,250));
              await importActivityFile(fit(o)); await new Promise(s=>setTimeout(s,450));
              const ok=document.querySelector('[data-action="confirm-gpx-import"]'); if(ok){ ok.click(); await new Promise(s=>setTimeout(s,550)); }
              return state.races[0]; };'''
        # ---- FIT 解析：這三項都是用使用者的真實檔案（Forerunner 945）才發現的 ----
        c['fit_enhanced_altitude_is_read'] = page.evaluate('''async()=>{ %s
            // 新款 Garmin 只寫欄位 78；原本只讀欄位 2，海拔剖面、GAP、爬升全部是空的
            const segs=SEGS.map((sg,i)=>i===4?Object.assign({},sg,{climb:300}):sg);
            const pts=parseFitPoints(await fit({segments:segs}).arrayBuffer());
            const s=await parseActivityFile(fit({segments:segs}));
            return pts.filter(p=>p.ele!=null).length>100 && s.elevationGainM>=250 && s.elevationGainM<=350;
        }''' % FIX)
        c['legs_get_watch_ascent_and_swim_water_temp'] = page.evaluate('''async()=>{ %s
            const s=await parseActivityFile(fit());
            const g=sp=>s.legs.find(l=>l.sport===sp);
            // 下水前 2 分鐘 32°C（手錶還帶著體溫），之後 27°C：略過前 3 分鐘取中位數 → 27
            return g('cycling').elevationGainM===420 && g('running').elevationGainM===35
                && g('swimming').elevationGainM===null && g('swimming').waterTempC===27
                && g('cycling').waterTempC===undefined;
        }''' % FIX)
        c['hr_source_strap_vs_wrist'] = page.evaluate('''async()=>{ %s
            const src=async h=>parseFitPoints(await fit({hrSource:h}).arrayBuffer()).hrSource;
            return (await src('strap'))==='strap' && (await src('wrist'))==='wrist';
        }''' % FIX)
        c['water_temp_harshness_follows_wetsuit_rules'] = page.evaluate('''()=>{
            const h=waterTempHarshness;
            return h(21)===0 && h(18)===0 && h(24)===0 && Math.abs(h(16)-2/6)<0.01 && h(12)===1
                && Math.abs(h(28)-4/5.5)<0.01 && h(29.5)===1 && h(null)===null;
        }''')
        # ---- 雷達圖：泳、騎、跑三個形狀 ----
        c['radar_three_series_with_swim'] = page.evaluate('''async()=>{ %s
            const r=await importAs('triathlon');
            const d=computeRaceRadarSeries(r);
            const se=sp=>d.series.find(x=>x.sport===sp);
            const dim=(sp,k)=>se(sp).dims.find(x=>x.key===k);
            // 游泳：距離依 3.8 km 滿分、沒有爬升、溫度用水溫；穩定度的區段長度依距離調整
            // （1.5 km＝14 個 100 m 分段 → 每 200 m 一段 → 7 段；3.8 km 以上 → 每 500 m）
            const swimSplits=r.legs.find(l=>l.sport==='swimming').splits;
            const bs=swimBlockSize(swimSplits.length);
            const blocks=[]; for(let i=0;i+bs<=swimSplits.length;i+=bs) blocks.push(1);
            return d.series.map(x=>x.sport).join()==='swimming,cycling,running'
                && Math.abs(dim('swimming','distance').value-1.5/3.8)<0.02
                && dim('swimming','elevation').value===null
                && dim('swimming','temp').raw==='水 27°C' && dim('swimming','temp').value===Math.min((27-24)/5.5,1)
                && dim('cycling','elevation').raw==='420 m'                    // 用手錶記錄的爬升
                && bs===2 && blocks.length===7 && swimBlockSize(38)===5 && swimBlockSize(3)===1
                && dim('swimming','stability').raw!=null
                && dim('cycling','temp').label==='溫度嚴苛';
        }''' % FIX)
        c['radar_single_sport_unchanged'] = page.evaluate('''()=>{
            const solo=emptyRace('路跑','road_running','completed','2026-01-01'); solo.route.distanceKm=42.195;
            solo.splits=[1,2,3,4,5].map(i=>({distanceKm:1,splitTimeSeconds:300+i,avgPaceSecPerKm:300+i,avgHr:150}));
            const d=document.createElement('div'); d.innerHTML=renderRaceRadarHtml(solo);
            return Array.isArray(radarDataForRace(solo)) && !d.querySelector('.is-overlay') && !d.querySelector('.race-radar-legend');
        }''')
        # 游泳用手腕心率時要說明來源；有胸帶就不說明
        c['radar_wrist_hr_note_only_for_wrist'] = page.evaluate('''async()=>{ %s
            const a=await importAs('triathlon',{hrSource:'wrist'});
            const da=document.createElement('div'); da.innerHTML=renderRaceRadarHtml(a);
            const b=await importAs('triathlon',{hrSource:'strap'});
            const db=document.createElement('div'); db.innerHTML=renderRaceRadarHtml(b);
            const legend=[...da.querySelectorAll('.race-radar-legend-item')].map(x=>x.textContent.trim()).join();
            return legend==='游泳,自行車,跑步' && da.textContent.includes('手腕光學心率') && !db.textContent.includes('手腕光學心率');
        }''' % FIX)
        # 推算出來的游泳段（單一模式錄的）沒有分段 → 不畫，並說明
        c['radar_inferred_swim_not_drawn'] = page.evaluate('''async()=>{ %s
            const r=await importAs('triathlon',{sessions:null});
            const d=computeRaceRadarSeries(r);
            const h=document.createElement('div'); h.innerHTML=renderRaceRadarHtml(r);
            return d.series.map(x=>x.sport).join()==='cycling,running' && h.textContent.includes('沒有分段資料');
        }''' % FIX)
        c['radar_overlay_hr_uses_leg_zones'] = page.evaluate('''()=>{
            const r=emptyRace('二鐵','duathlon','completed','2021-05-09');
            const mk=(sport,hr)=>({sport,distanceKm:10,durationSeconds:3000,startTime:'2021-05-09T07:00:00Z',endTime:'2021-05-09T08:00:00Z',
              splits:[1,2,3,4,5].map(()=>({distanceKm:1,splitTimeSeconds:300,avgPaceSecPerKm:300,avgHr:hr}))});
            r.legs=[mk('running',158),{sport:'transition',durationSeconds:60},mk('cycling',158),{sport:'transition',durationSeconds:60},mk('running',158)];
            const d=computeRaceRadarSeries(r);
            const hr=s=>d.series.find(x=>x.sport===s).dims.find(x=>x.key==='hr').value;
            return hr('cycling')===1 && hr('running')===0;
        }''')
        # ---- 版面：桌機數值標在各軸旁、手機改用表格；任何文字都不可以超出畫布 ----
        BOUNDS = '''const check=async()=>{
            const canvas=document.querySelector('canvas.is-overlay'); const wrap=canvas.closest('.race-radar');
            const W=canvas.clientWidth,H=canvas.clientHeight,calls=[];
            const proto=CanvasRenderingContext2D.prototype, orig=proto.fillText;
            proto.fillText=function(txt,x,y){ calls.push({x,y,w:this.measureText(String(txt)).width,align:this.textAlign}); return orig.apply(this,arguments); };
            try{ drawRadarData(canvas,radarDataForRace(state.races[0]),1); } finally{ proto.fillText=orig; }
            const out=calls.filter(c2=>{ const l=c2.align==='right'?c2.x-c2.w:(c2.align==='center'?c2.x-c2.w/2:c2.x); return l<0||l+c2.w>W||c2.y<0||c2.y>H; });
            const tw=wrap.querySelector('.race-radar-values-wrap');
            return {texts:calls.length,out:out.length,compact:wrap.classList.contains('is-compact'),
              table:getComputedStyle(tw).display!=='none',tableFits:tw.scrollWidth<=tw.clientWidth+1,W}; };'''
        c['radar_desktop_values_on_canvas'] = page.evaluate('''async()=>{ %s %s
            await importAs('triathlon'); document.getElementById('section-post').open=true;
            await new Promise(s=>setTimeout(s,400));
            const r=await check();
            return !r.compact && !r.table && r.texts>=15 && r.out===0;
        }''' % (FIX, BOUNDS))
        for w in (390, 360):
            page.set_viewport_size({'width':w,'height':900}); page.wait_for_timeout(250)
            c[f'radar_phone_{w}_compact_with_table'] = page.evaluate('''async()=>{ %s %s
                await importAs('triathlon'); document.getElementById('section-post').open=true;
                await new Promise(s=>setTimeout(s,400));
                const r=await check();
                // 圖上只標 5 個軸名、數值在表格，表格不可以被切掉
                return r.compact && r.table && r.tableFits && r.texts===5 && r.out===0 && r.W<360;
            }''' % (FIX, BOUNDS))
        # ---- 瀏覽器縮放（Ctrl＋）：雷達圖要重畫成新的解析度（v3.87.0） ----
        page.set_viewport_size({'width':1100,'height':900}); page.wait_for_timeout(200)
        page.evaluate('''async()=>{ state.races=[];
            const r=emptyRace('路跑','road_running','completed','2026-01-01'); r.route.distanceKm=42.195; r.route.elevationGainM=300;
            r.results.chipTimeSeconds=10774; r.raceDayWeather.feelsLikeTempC=24;
            r.splits=[1,2,3,4,5,6].map(i=>({distanceKm:1,splitTimeSeconds:300+i*3,avgPaceSecPerKm:300+i*3,avgHr:150+i}));
            state.races.push(r); selectRace(r.id,{scroll:false}); await new Promise(s=>setTimeout(s,300));
            document.getElementById('section-post').open=true; await new Promise(s=>setTimeout(s,1300)); }''')
        cdp = page.context.new_cdp_session(page)
        results = []
        for zoom in (1.25, 2):
            cdp.send('Emulation.setDeviceMetricsOverride',{'width':1100,'height':900,'deviceScaleFactor':zoom,'mobile':False})
            page.wait_for_timeout(500)
            results.append(page.evaluate('''()=>{ const c=document.querySelector('canvas[data-race-radar]');
                return c.width===Math.round(c.clientWidth*window.devicePixelRatio)
                    && c.height===Math.round(c.clientHeight*window.devicePixelRatio); }'''))
        cdp.send('Emulation.clearDeviceMetricsOverride')
        page.wait_for_timeout(300)
        c['radar_redraws_on_browser_zoom'] = all(results)
        # 桌機把視窗拉窄：不用重新整理，雷達圖就要切到精簡模式（圖上只標軸名＋表格）
        page.evaluate('''async()=>{ %s
            await importAs('triathlon'); document.getElementById('section-post').open=true;
            await new Promise(s=>setTimeout(s,500)); }''' % FIX)
        wide = page.evaluate("()=>document.querySelector('.race-radar').classList.contains('is-compact')")
        page.set_viewport_size({'width':380,'height':900}); page.wait_for_timeout(500)
        narrow = page.evaluate("()=>document.querySelector('.race-radar').classList.contains('is-compact')")
        page.set_viewport_size({'width':1100,'height':900}); page.wait_for_timeout(500)
        back = page.evaluate("()=>document.querySelector('.race-radar').classList.contains('is-compact')")
        c['radar_switches_layout_on_window_resize'] = (wide is False) and (narrow is True) and (back is False)

# 假的雲端：記錄每一次呼叫、模擬雲端上的賽事與訓練紀錄（測增量同步用）
FAKE_CLOUD_JS = r'''window.__makeFakeCloud=function(initialRaces,initialTrainings){
  const store={races:new Map((initialRaces||[]).map(r=>[r.id,JSON.parse(JSON.stringify(r))])),
               trainings:(initialTrainings||[]).map(x=>JSON.parse(JSON.stringify(x)))};
  const log=[];
  const fc={enabled:true,log,store,
    async fetchAll(uid){ log.push(['fetchAll']); return [...store.races.values()].map(r=>JSON.parse(JSON.stringify(r))); },
    pageCalls:[], failAt:null,
    async fetchRacesPage(uid,afterId,size){
      fc.pageCalls.push([afterId,size]);
      if(fc.failAt!=null&&fc.pageCalls.length-1===fc.failAt){ fc.failAt=null; throw new Error('模擬分頁崩潰'); }
      const all=[...store.races.values()].sort((a,b)=>a.id<b.id?-1:1);
      const start=afterId?all.findIndex(r=>r.id>afterId):0;
      const slice=start<0?[]:all.slice(start,start+size);
      log.push(['fetchRacesPage',afterId,size]);
      return {races:slice.map(r=>JSON.parse(JSON.stringify(r))),lastId:slice.length?slice[slice.length-1].id:afterId,done:slice.length<size};
    },
    async fetchChangedSince(uid,since){ log.push(['fetchChangedSince',since]); return [...store.races.values()].filter(r=>(r.updatedAt||'')>since).map(r=>JSON.parse(JSON.stringify(r))); },
    async upsertRaces(uid,races,del){ log.push(['upsertRaces',races.map(r=>r.id),del||[]]); (del||[]).forEach(id=>store.races.delete(id)); races.forEach(r=>store.races.set(r.id,JSON.parse(JSON.stringify(r)))); return {batches:1,oversized:[]}; },
    async replaceAll(){ log.push(['replaceAll']); return {batches:1,oversized:[]}; },
    async fetchGlobalLists(){ return null; },
    async syncGlobalLists(){ log.push(['syncGlobalLists']); },
    // 訓練紀錄照雲端的樣子存：一個月一份。upsertTrainingMonths 跟正式版一樣在「交易」裡
    // 先讀雲端那個月、用 merge 合併再寫回，並回傳寫回的內容。denyTrainings 模擬安全性規則沒開放
    denyTrainings:false,
    async fetchTrainings(){ log.push(['fetchTrainings']); if(fc.denyTrainings) throw Object.assign(new Error('Missing or insufficient permissions.'),{code:'permission-denied'});
      return store.trainings.map(x=>JSON.parse(JSON.stringify(x))); },
    async upsertTrainingMonths(uid,byMonth,merge){ log.push(['upsertTrainingMonths',Object.keys(byMonth).sort()]);
      if(fc.denyTrainings) throw Object.assign(new Error('Missing or insufficient permissions.'),{code:'permission-denied'});
      const mon=x=>(x.date||'').slice(0,7)||'unknown', clone=x=>JSON.parse(JSON.stringify(x)), out={};
      Object.keys(byMonth).forEach(m=>{ const cloudItems=store.trainings.filter(x=>mon(x)===m).map(clone);
        const items=(merge?merge(cloudItems,byMonth[m]):byMonth[m]).map(clone);
        store.trainings=store.trainings.filter(x=>mon(x)!==m).concat(items); out[m]=items.map(clone); });
      return out; },
    async replaceTrainings(){ log.push(['replaceTrainings']); },
    onAuthChange(){}, signIn(){}, signOut(){},
  };
  return fc;
};
'''

# 年度旅程的測試資料：接近使用者實際的組合（國內多場、日本多場、柏林、只有 GPX 沒填城市、場地欄位寫雜事）
YEAR_JOURNEY_SEED_JS = r'''window.__seedYear=async function(){
  const realFetch=window.__rf||(window.__rf=window.fetch);
  window.fetch=async(u,o)=>{ const s=String(u); if(s.includes('geocoding-api')){ const q=decodeURIComponent(s.split('name=')[1]);
    const db={'福井':{latitude:35.49,longitude:135.75,country:'日本'},'大阪':{latitude:34.69,longitude:135.50,country:'日本'},'名古屋':{latitude:35.18,longitude:136.91,country:'日本'},'柏林':{latitude:52.52,longitude:13.40,country:'德國'},'(繳費) 忘記龍哥給我錢':{latitude:31.2,longitude:112.0,country:'中國'}};
    return new Response(JSON.stringify({results:db[q]?[Object.assign({name:q},db[q])]:[]})); } return realFetch(u,o); };
  userProfile=userProfile||emptyUserProfile(); userProfile.homeCounty='新北市'; journeyGeoCache={}; await saveJson('journey-geo-v1',{});
  state.races=[];
  const track=(lat,lon,shape)=>[...Array(60)].map((_,i)=>({lat:lat+Math.sin(i/9*shape)*0.02+i*0.0008,lon:lon+Math.cos(i/7)*0.02+i*0.0006}));
  const mk=(name,city,venue,country,date,gps)=>{ const r=emptyRace(name,'road_running','completed',date); r.location.city=city; r.location.venueName=venue; r.location.country=country;
    r.route.distanceKm=42.195; r.results.chipTimeSeconds=12000; if(gps) r.route.trackPoints=track(gps[0],gps[1],gps[2]); state.races.push(r); };
  mk('新北市萬金石馬拉松','新北市','','台灣','2026-03-22',[25.2,121.6,1]);
  mk('日月潭環湖','南投','','台灣','2026-04-10',null);
  mk('2026 台東超級鐵人三項','台東','','台灣','2026-11-01',[22.75,121.15,2]);
  mk('花蓮太魯閣馬拉松','花蓮','','台灣','2026-11-08',[24.15,121.6,3]);
  mk('台中馬拉松','台中','','台灣','2026-12-06',null);
  mk('宜蘭國際馬拉松','宜蘭','','台灣','2026-10-18',[24.7,121.8,4]);
  mk('冬山河路跑','宜蘭','','台灣','2026-05-17',null);
  mk('高雄富邦馬拉松','高雄','','台灣','2026-02-15',[22.6,120.3,5]);
  mk('若狭路トレイルラン','福井','','日本','2026-09-27',null);
  mk('大阪マラソン 2026','大阪','','日本','2026-02-22',[34.69,135.50,6]);
  mk('名古屋ウィメンズ','名古屋','','日本','2026-03-08',null);
  mk('富士五湖ウルトラ','','','',"2026-04-19",[35.5,138.76,7]);
  mk('柏林馬拉松','柏林','','德國','2026-09-27',null);
  mk('某某路跑','','(繳費) 忘記龍哥給我錢','','2026-06-01',null);
};
'''

class Journey(Group):
    """賽事旅程卡片（v3.93.0）：從家到賽場的動畫地圖＋真實地圖按鈕。"""

    def body(self, page):
        c = self.checks
        SETUP = '''const wait=ms=>new Promise(s=>setTimeout(s,ms));
            const geoCalls=[]; if(!window.__realFetch) window.__realFetch=window.fetch;
            window.fetch=async(u,o)=>{ const s=String(u); if(s.includes('geocoding-api.open-meteo.com')){
                const q=decodeURIComponent(s.split('name=')[1]); geoCalls.push(q);
                const db={'大阪':{name:'大阪市',latitude:34.69,longitude:135.50,country:'日本'},'Berlin':{name:'柏林',latitude:52.52,longitude:13.40,country:'德國'}};
                return new Response(JSON.stringify({results:db[q]?[db[q]]:[]})); }
              return window.__realFetch(u,o); };
            const mk=(name,city,country,mode)=>{ const r=emptyRace(name,'road_running','registered','2026-11-01');
              r.location.city=city; r.location.country=country;
              if(mode) r.transportation=[{direction:'outbound',mode,departureTime:'',pickupLocation:'',cost:null,notes:''}];
              state.races.push(r); return r; };
            const view=async id=>{ selectRace(id,{scroll:false}); await wait(450); return document.querySelector('.journey-card'); };
            userProfile=userProfile||emptyUserProfile(); userProfile.homeCounty='新北市'; state.races=[];
            journeyGeoCache={}; await saveJson('journey-geo-v1',{});'''
        c['journey_county_matching'] = page.evaluate('''()=>{
            const n=x=>(twCountyFromText(x)||{}).name||null;
            return n('台東')==='臺東縣' && n('2026 台東超級鐵人三項')==='臺東縣' && n('新竹市')==='新竹市'
                && n('新竹縣竹北')==='新竹縣' && n('新北市萬金石馬拉松')==='新北市' && n('臺北馬拉松')==='臺北市' && n('Osaka')===null;
        }''')
        c['journey_needs_home_then_profile_sets_it'] = page.evaluate('''async()=>{ %s
            userProfile.homeCounty='';
            const r=mk('2026 台東超級鐵人三項','台東','台灣','train');
            let card=await view(r.id);
            const prompt=!!card.querySelector('[data-action="journey-set-home"]');
            card.querySelector('[data-action="journey-set-home"]').click(); await wait(200);
            const sel=document.querySelector('[data-profile-path="homeCounty"]');
            sel.value='新北市'; sel.dispatchEvent(new Event('change',{bubbles:true})); await wait(300);
            const btn=document.querySelector('[data-action="close-profile-modal"]'); if(btn) btn.click();
            card=await view(r.id);
            return prompt && userProfile.homeCounty==='新北市' && !!card.querySelector('svg.jr-map');
        }''' % SETUP)
        c['journey_domestic_uses_taiwan_map'] = page.evaluate('''async()=>{ %s
            const r=mk('2026 台東超級鐵人三項','台東','台灣','train');
            const card=await view(r.id);
            return card.querySelector('.jr-foot b').textContent==='253' && card.querySelector('.jr-mover-icon').textContent==='🚆'
                && !!card.querySelector('.jr-land') && !card.querySelector('.jr-land-far') && !!card.querySelector('[data-action="journey-open-map"]');
        }''' % SETUP)
        c['journey_overseas_geocodes_once'] = page.evaluate('''async()=>{ %s
            const r=mk('大阪マラソン 2027','大阪','日本','flight');
            await view(r.id); await wait(400);
            const card=await view(r.id);
            await view(r.id); await view(r.id);
            // 東亞地圖、飛機、只查詢一次；有一端在台灣時整個台灣都在範圍內
            const svg=card.querySelector('svg.jr-map');
            return !!card.querySelector('.jr-land-far') && card.querySelector('.jr-mover-icon').textContent==='✈️'
                && card.querySelector('.jr-foot b').textContent==='1,726' && geoCalls.filter(q=>q==='大阪').length===1;
        }''' % SETUP)
        # 查到的座標只存這台裝置，不寫進賽事（寫進去會讓每場都被判定有變更、重新上傳雲端）
        c['journey_geocode_not_written_to_race'] = page.evaluate('''async()=>{ %s
            const r=mk('大阪マラソン 2027','大阪','日本','flight'); const before=JSON.stringify(r);
            await view(r.id); await wait(400);
            const cache=await loadJson('journey-geo-v1',{});
            return JSON.stringify(state.races.find(x=>x.id===r.id))===before && cache[r.id] && cache[r.id].lat===34.69;
        }''' % SETUP)
        c['journey_far_race_uses_line'] = page.evaluate('''async()=>{ %s
            const r=mk('柏林馬拉松','Berlin','德國',null);
            await view(r.id); await wait(400); const card=await view(r.id);
            return !!card.querySelector('.jr-line') && card.querySelector('.jr-mover-icon').textContent==='✈️'
                && card.querySelector('.jr-chip.is-muted')!==null;
        }''' % SETUP)
        # 同一個縣市：不顯示「離家 1 公里」這種沒意義的距離
        c['journey_same_county_no_fake_distance'] = page.evaluate('''async()=>{ %s
            const r=mk('新北市萬金石馬拉松','新北市','台灣','bus');
            const card=await view(r.id);
            const txt=card.textContent;
            return txt.includes('同一個縣市') && !/\\d+\\s*公里/.test(txt) && !card.querySelector('svg.jr-map');
        }''' % SETUP)
        # 查不到的地點：顯示找不到，而且不可以一直重查（重畫卡片不會再觸發查詢）
        c['journey_not_found_no_loop'] = page.evaluate('''async()=>{ %s
            const r=mk('神秘山路跑','某個不存在的地方','某國',null);
            await view(r.id); await wait(500);
            // 數「查詢函式被呼叫幾次」而不是連網次數：迴圈時每一圈都會先在快取找到
            // 「查過了」，根本不會連網，只數連網次數抓不到
            let invoked=0; const real=window.geocodeJourneyRace;
            window.geocodeJourneyRace=function(){ invoked++; return real.apply(this,arguments); };
            const card=await view(r.id); await view(r.id); await wait(600);
            window.geocodeJourneyRace=real;
            return card.textContent.includes('找不到') && geoCalls.filter(q=>q==='某個不存在的地方').length===1 && invoked===0;
        }''' % SETUP)
        c['journey_animation_reaches_arrival'] = page.evaluate('''async()=>{ %s
            const r=mk('2026 台東超級鐵人三項','台東','台灣','train');
            const card=await view(r.id); const svg=card.querySelector('svg.jr-map');
            playJourney(svg); await wait(1200);
            const mid=svg.querySelector('.jr-trail').getAttribute('d').length>0 && !svg.classList.contains('is-arrived');
            await wait(1500);
            return mid && svg.classList.contains('is-arrived') && svg.querySelector('.jr-mover').style.display==='none';
        }''' % SETUP)
        page.emulate_media(reduced_motion='reduce')
        c['journey_reduced_motion_shows_arrival'] = page.evaluate('''async()=>{ %s
            const r=mk('2026 台東超級鐵人三項','台東','台灣','train');
            const card=await view(r.id); const svg=card.querySelector('svg.jr-map');
            playJourney(svg); await wait(50);
            return svg.classList.contains('is-arrived');
        }''' % SETUP)
        page.emulate_media(reduced_motion='no-preference')
        # 方案 B：真實地圖（測試環境連不到 unpkg，用假的 Leaflet 看它做了什麼）
        c['journey_real_map_button'] = page.evaluate('''async()=>{ %s
            const r=mk('2026 台東超級鐵人三項','台東','台灣','train');
            const card=await view(r.id);
            const calls=[]; const chain={addTo(){return chain;},bindTooltip(){return chain;}};
            const realL=window.L;
            window.L={map:()=>{calls.push('map');return {fitBounds:()=>calls.push('fit'),remove:()=>calls.push('remove')};},
              tileLayer:u=>{calls.push('tile');return chain;},polyline:p=>{calls.push('line'+p.length);return chain;},
              circleMarker:()=>{calls.push('pin');return chain;},latLngBounds:x=>x};
            card.querySelector('[data-action="journey-open-map"]').click(); await wait(250);
            const opened=!!document.getElementById('journey-map-overlay');
            document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape'})); await wait(80);
            window.L=realL;
            return opened && calls.join()==='map,tile,line65,pin,pin,fit,remove' && !document.getElementById('journey-map-overlay');
        }''' % SETUP)
        # 陸地與海面要分得出來：淺色模式至少 1.5 倍（v3.94 前 1.12）、深色模式至少 1.7 倍（v3.95 前 1.43）
        c['journey_land_contrast'] = page.evaluate('''async()=>{ %s
            const r=mk('2026 台東超級鐵人三項','台東','台灣','train'); await view(r.id);
            const lum=rgb=>{ const m=rgb.match(/\\d+/g).map(Number).slice(0,3).map(v=>{v/=255;return v<=0.03928?v/12.92:Math.pow((v+0.055)/1.055,2.4);}); return 0.2126*m[0]+0.7152*m[1]+0.0722*m[2]; };
            const ratio=()=>{ const a=lum(getComputedStyle(document.querySelector('.jr-sea')).fill), b=lum(getComputedStyle(document.querySelector('.jr-land')).fill);
              return (Math.max(a,b)+0.05)/(Math.min(a,b)+0.05); };
            const root=document.documentElement, prev=root.getAttribute('data-theme');
            root.setAttribute('data-theme','light'); const light=ratio();
            root.setAttribute('data-theme','dark'); const dark=ratio();   // v3.95 前只有 1.43
            root.setAttribute('data-theme',prev||'light');
            return light>=1.5 && dark>=1.7;
        }''' % SETUP)
        # ---- 年度回顧長圖：選擇性加入「今年的賽事旅程」（v3.95.0） ----
        c['year_review_journey_toggle'] = page.evaluate('''async()=>{ %s
            const r=mk('2026 台東超級鐵人三項','台東','台灣','train'); r.status='completed'; r.results.chipTimeSeconds=36000; r.schedule.raceDate='2026-03-01';
            localStorage.removeItem('year-review-journey-v1');
            const d=document.createElement('div');
            userProfile.homeCounty=''; d.innerHTML=yearInReviewPickerHtml();
            const disabledNoHome=d.querySelector('#year-in-review-journey').disabled;
            userProfile.homeCounty='新北市'; d.innerHTML=yearInReviewPickerHtml(); document.body.appendChild(d);
            const cb=d.querySelector('#year-in-review-journey'); const offByDefault=!cb.checked&&!cb.disabled;
            cb.checked=true; cb.dispatchEvent(new Event('change',{bubbles:true}));
            d.innerHTML=yearInReviewPickerHtml(); const remembered=d.querySelector('#year-in-review-journey').checked;
            d.remove(); localStorage.removeItem('year-review-journey-v1');
            return disabledNoHome && offByDefault && remembered;
        }''' % SETUP)
        c['year_review_journey_block'] = page.evaluate('''async()=>{ %s
            state.races=[];
            const done=(name,city,country,date)=>{ const r=mk(name,city,country,null); r.status='completed'; r.schedule.raceDate=date;
              r.route.distanceKm=42.195; r.results.chipTimeSeconds=12000; return r; };
            done('2026 台東超級鐵人三項','台東','台灣','2026-11-01'); done('大阪マラソン 2026','大阪','日本','2026-02-22');
            done('新北市萬金石馬拉松','新北市','台灣','2026-03-22'); done('柏林馬拉松','Berlin','德國','2026-09-27');
            done('神秘山路跑','某個不存在的地方','某國','2026-05-01');
            const jb=await yearJourneyData(state.races);
            const spy=[]; const proto=CanvasRenderingContext2D.prototype, orig=proto.fillText;
            proto.fillText=function(x){ spy.push(String(x)); return orig.apply(this,arguments); };
            try{ await buildYearInReviewCanvas('2026',{journey:true}); } finally{}
            const on=spy.splice(0); await buildYearInReviewCanvas('2026',{journey:false}); const off=spy.splice(0);
            proto.fillText=orig;
            // 往返直線：台東 253×2＋大阪 1,726×2＋柏林 8,955×2；萬金石同縣市不算距離；查不到的另外註明
            return jb.places===4 && Math.abs(jb.totalKm-2*(253+1726+8955))<30 && jb.far.name==='Berlin' && jb.unlocated===1
                && on.includes('今年的賽事旅程') && on.some(x=>x.includes('新北市')&&x.includes('出發')) && on.some(x=>x.includes('東亞以外')&&x.includes('無法定位'))
                && !off.includes('今年的賽事旅程');
        }''' % SETUP)
        # ---- v3.96.0：使用者回報「地圖擠在一起、原本的路線拼貼不見了」 ----
        page.add_script_tag(content=YEAR_JOURNEY_SEED_JS)
        # 旅程接在最下面、長圖加長；原本的版面（含路線拼貼）一個像素都不能變
        c['year_journey_appended_layout_untouched'] = page.evaluate('''async()=>{ await __seedYear();
            const on=await buildYearInReviewCanvas('2026',{journey:true}), off=await buildYearInReviewCanvas('2026',{journey:false});
            const a=on.getContext('2d').getImageData(0,0,1080,1780).data, b=off.getContext('2d').getImageData(0,0,1080,1780).data;
            let diff=0; for(let i=0;i<a.length;i+=4) if(a[i]!==b[i]||a[i+1]!==b[i+1]||a[i+2]!==b[i+2]) diff++;
            return off.height===1920 && on.height>2800 && diff===0;
        }''')
        # 地名：不像地名的文字不拿去查（原本查到中國某地、畫出錯的點）；沒填城市用賽事名稱，不用「賽場」；
        # 同縣市的 GPX 賽事算在地；同名又近的地點合併；台灣一律用縣市名稱
        c['year_journey_places_clean'] = page.evaluate('''async()=>{ await __seedYear();
            const jb=await yearJourneyData(state.races);
            const names=yearJourneyPlaces(jb).map(x=>x.name+(x.count>1?'×'+x.count:'')+(x.local?'(在地)':''));
            const junk=state.races.find(r=>r.location.venueName.startsWith('(繳費)'));
            return !names.some(n=>n.includes('繳費')||n.includes('賽場')) && journeyRaceGeo(junk)===null && jb.unlocated===1
                && names.includes('富士五湖ウルトラ') && names.includes('新北(在地)') && names.includes('宜蘭×2')
                && names.includes('臺東') && names.includes('臺中') && !names.includes('台東') && jb.far.name==='柏林';
        }''')
        # 國內、海外分成兩張地圖（同一張東亞地圖時台灣只佔一小塊，國內的點全疊在一起）
        c['year_journey_split_panels'] = page.evaluate('''async()=>{ await __seedYear();
            const spy=[]; const proto=CanvasRenderingContext2D.prototype, orig=proto.fillText;
            proto.fillText=function(x){ spy.push(String(x)); return orig.apply(this,arguments); };
            try{ await buildYearInReviewCanvas('2026',{journey:true}); } finally{ proto.fillText=orig; }
            return spy.includes('國內') && spy.includes('海外') && spy.some(x=>x.includes('從 新北市 出發'));
        }''')
        # iPhone 安全：旅程卡片與地圖視窗的樣式不可以有 filter／blend／backdrop
        import pathlib as _pl, re as _re
        _css=_re.search(r'<style[^>]*>(.*?)</style>',_pl.Path(APP).read_text(encoding='utf-8'),_re.S).group(1)
        _rules=[m.group(0) for m in _re.finditer(r'\.(?:jr-|journey-)[^{}]*\{[^{}]*\}',_css)]
        c['journey_css_ios_safe'] = len(_rules)>=15 and not any(_re.search(r'(?<![-\w])filter\s*:|backdrop-filter|mix-blend-mode',r) for r in _rules)
        page.evaluate("()=>{ if(window.__realFetch) window.fetch=window.__realFetch; }")

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
            // v3.89 起改走只上傳有變的 upsertRaces；要有一場「跟雲端版本不同」的賽事才會上傳
            const realKnown=cloudKnown, realRaces=state.races;
            window.__cloud={enabled:true,
              upsertRaces:async()=>({batches:1,oversized:[{race:{id:'big',name:'爆量賽事'},size:2000000}]}),
              syncGlobalLists:async()=>{}, logFeatureUse:async()=>{}};
            cloudKnown={since:'',races:{},trainings:{}};
            state.races=[Object.assign(emptyRace('爆量賽事','road_running','completed','2025-01-01'),{id:'big',updatedAt:'2026-01-01T00:00:00Z'})];
            document.querySelectorAll('.foreground-toast').forEach(n=>n.remove());
            try{ await cloudSyncAllRaces(); }finally{ window.__cloud=realCloud; state.user=realUser; cloudKnown=realKnown; state.races=realRaces; }
            await new Promise(s=>setTimeout(s,200));
            const txt=[...document.querySelectorAll('.foreground-toast')].map(n=>n.textContent).join(' ');
            return txt.includes('爆量賽事') && txt.includes('1');
        }''')
        # ---- 增量同步（v3.89.0：iPhone「登入就打不開」） ----
        page.add_script_tag(content=FAKE_CLOUD_JS)
        SETUP = '''const wait=ms=>new Promise(s=>setTimeout(s,ms));
            const mk=(id,t)=>Object.assign(emptyRace('賽事'+id,'road_running','completed','2025-01-01'),{id,updatedAt:t});
            const A=mk('a','2026-09-01T00:00:00.000Z'), B=mk('b','2026-09-02T00:00:00.000Z'), C=mk('c','2026-09-03T00:00:00.000Z');
            const fresh=async(local,cloudRaces,tr)=>{ await saveJson('cloud-sync-state-v1',null); cloudKnown=null; cloudPendingDeletes=[];
              state.races=local.map(r=>JSON.parse(JSON.stringify(r))); trainings=(tr||[]).map(x=>migrateTraining(JSON.parse(JSON.stringify(x))));
              const c=__makeFakeCloud(cloudRaces,tr||[]); window.__cloud=c; return c; };'''
        c['sync_first_sign_in_no_reupload'] = page.evaluate('''async()=>{ %s
            const cloud=await fresh([A,B,C],[A,B,C]);
            await handleAuthChange({uid:'u1'}); await wait(1200);
            const kinds=cloud.log.map(x=>x[0]);
            // 完整下載只做一輪（v3.91 起分批）；沒有 replaceAll（會再下載全部）、沒有上傳任何賽事
            const ok=kinds.includes('fetchRacesPage') && !kinds.includes('fetchAll') && !kinds.includes('replaceAll')
              && !kinds.includes('upsertRaces') && !kinds.includes('upsertTrainingMonths');
            window.__cloud=null; state.user=null; return ok;
        }''' % SETUP)
        c['sync_second_open_is_incremental'] = page.evaluate('''async()=>{ %s
            const cloud=await fresh([A,B,C],[A,B,C]);
            await handleAuthChange({uid:'u1'}); await wait(1200); cloud.log.length=0;
            cloudKnown=null; await handleAuthChange({uid:'u1'}); await wait(1200);
            const f=cloud.log.find(x=>x[0]==='fetchChangedSince');
            // 只抓最新版本往前一天之後的（容忍不同裝置的時鐘誤差）
            const ok=!!f && f[1].slice(0,10)==='2026-09-02' && !cloud.log.some(x=>x[0]==='fetchAll'||x[0]==='fetchRacesPage'||x[0]==='upsertRaces');
            window.__cloud=null; state.user=null; return ok;
        }''' % SETUP)
        c['sync_edit_uploads_only_that_race'] = page.evaluate('''async()=>{ %s
            const cloud=await fresh([A,B,C],[A,B,C]);
            await handleAuthChange({uid:'u1'}); await wait(1200); cloud.log.length=0;
            const b=state.races.find(r=>r.id==='b'); b.name='改名'; b.updatedAt=new Date().toISOString();
            await persist(); await wait(1300);
            const ok=JSON.stringify(cloud.log)===JSON.stringify([['upsertRaces',['b'],[]]]);
            window.__cloud=null; state.user=null; return ok;
        }''' % SETUP)
        c['sync_permanent_delete_only_that_race'] = page.evaluate('''async()=>{ %s
            const cloud=await fresh([A,B,C],[A,B,C]);
            await handleAuthChange({uid:'u1'}); await wait(1200); cloud.log.length=0;
            keepRaces(r=>r.id!=='c'); await persist(); await wait(1300);
            const ok=JSON.stringify(cloud.log)===JSON.stringify([['upsertRaces',[],['c']]])
              && [...cloud.store.races.keys()].sort().join()==='a,b' && cloudPendingDeletes.length===0;
            window.__cloud=null; state.user=null; return ok;
        }''' % SETUP)
        # 本機資料被清掉、同步紀錄還在：必須完整下載補回，絕對不可以刪雲端
        c['sync_wiped_local_never_deletes_cloud'] = page.evaluate('''async()=>{ %s
            const cloud=await fresh([A,B,C],[A,B,C]);
            await handleAuthChange({uid:'u1'}); await wait(1200); cloud.log.length=0;
            state.races=[]; cloudKnown=null;
            await handleAuthChange({uid:'u1'}); await wait(1300);
            const deletes=cloud.log.filter(x=>x[0]==='upsertRaces').flatMap(x=>x[2]);
            const ok=cloud.log.some(x=>x[0]==='fetchRacesPage') && deletes.length===0
              && state.races.map(r=>r.id).sort().join()==='a,b,c' && cloud.store.races.size===3;
            window.__cloud=null; state.user=null; return ok;
        }''' % SETUP)
        # 沒登入時永久刪除：登入後不可以被雲端那份「復活」，而且要從雲端刪掉
        c['sync_offline_delete_not_resurrected'] = page.evaluate('''async()=>{ %s
            await saveJson('cloud-sync-state-v1',null); cloudKnown=null; cloudPendingDeletes=[];
            state.user=null; state.races=[A,B,C].map(r=>JSON.parse(JSON.stringify(r)));
            keepRaces(r=>r.id!=='a');
            const cloud=__makeFakeCloud([A,B,C],[]); window.__cloud=cloud;
            await handleAuthChange({uid:'u1'}); await wait(1300);
            const ok=state.races.map(r=>r.id).sort().join()==='b,c' && [...cloud.store.races.keys()].sort().join()==='b,c';
            window.__cloud=null; state.user=null; return ok;
        }''' % SETUP)
        c['sync_local_only_race_pushed'] = page.evaluate('''async()=>{ %s
            const D=mk('d','2026-09-10T00:00:00.000Z');
            const cloud=await fresh([A,B,D],[A,B]);
            await handleAuthChange({uid:'u1'}); await wait(1300);
            const ok=JSON.stringify(cloud.log.filter(x=>x[0]==='upsertRaces'))===JSON.stringify([['upsertRaces',['d'],[]]]);
            window.__cloud=null; state.user=null; return ok;
        }''' % SETUP)
        c['sync_trainings_only_changed_month'] = page.evaluate('''async()=>{ %s
            const T=[{id:'t1',date:'2026-08-05',updatedAt:'2026-08-05T00:00:00.000Z'},{id:'t2',date:'2026-09-06',updatedAt:'2026-09-06T00:00:00.000Z'}];
            const cloud=await fresh([A],[A],T);
            await handleAuthChange({uid:'u1'}); await wait(1200);
            const noUploadOnOpen=!cloud.log.some(x=>x[0]==='upsertTrainingMonths'||x[0]==='replaceTrainings');
            cloud.log.length=0;
            const t2=trainings.find(x=>x.id==='t2'); t2.shoeId='s1'; t2.updatedAt=new Date().toISOString();
            await persistTrainings(); await wait(1400);
            const ok=noUploadOnOpen && JSON.stringify(cloud.log)===JSON.stringify([['upsertTrainingMonths',['2026-09']]]);
            window.__cloud=null; state.user=null; return ok;
        }''' % SETUP)
        # ---- 第一次完整下載分批、可續傳（v3.91.0：v3.90 實機登入仍然崩潰） ----
        PAGED = '''const wait=ms=>new Promise(s=>setTimeout(s,ms));
            const mkp=i=>Object.assign(emptyRace('賽事'+i,'road_running','completed','2025-01-01'),{id:'r'+String(i).padStart(2,'0'),updatedAt:'2026-09-'+String(1+i%28).padStart(2,'0')+'T00:00:00.000Z'});
            const R=[...Array(12)].map((_,i)=>mkp(i));
            const reset=async(local)=>{ await saveJson('cloud-sync-state-v1',null); localStorage.removeItem('sync-inflight-v1'); cloudKnown=null; cloudPendingDeletes=[];
              state.races=local.map(r=>JSON.parse(JSON.stringify(r))); trainings=[]; };
            const trace=c=>c.pageCalls.map(x=>(x[0]||'start')+'/'+x[1]).join(' ');'''
        c['sync_first_download_is_paged'] = page.evaluate('''async()=>{ %s
            await reset(R); const cloud=__makeFakeCloud(R,[]); window.__cloud=cloud;
            await handleAuthChange({uid:'u1'}); await wait(1200);
            const st=await loadJson('cloud-sync-state-v1',null);
            const ok=trace(cloud)==='start/5 r04/5 r09/5' && !cloud.log.some(x=>x[0]==='fetchAll'||x[0]==='upsertRaces')
              && !st.byUid.u1.fullSync && Object.keys(st.byUid.u1.races).length===12 && localStorage.getItem('sync-inflight-v1')===null;
            window.__cloud=null; state.user=null; hideSyncPill(); return ok;
        }''' % PAGED)
        # 中途崩潰（這裡用丟出錯誤模擬）：重新打開從中斷處接著抓，不從頭
        c['sync_resumes_after_crash'] = page.evaluate('''async()=>{ %s
            await reset(R); const cloud=__makeFakeCloud(R,[]); cloud.failAt=1; window.__cloud=cloud;
            await handleAuthChange({uid:'u1'}); await wait(600);
            const marker=JSON.parse(localStorage.getItem('sync-inflight-v1')||'null');
            cloud.pageCalls.length=0; cloudKnown=null;
            await handleAuthChange({uid:'u1'}); await wait(1200);
            const st=await loadJson('cloud-sync-state-v1',null);
            const ok=!!marker && marker.afterId==='r04' && trace(cloud)==='r04/5 r09/5'
              && !st.byUid.u1.fullSync && Object.keys(st.byUid.u1.races).length===12;
            window.__cloud=null; state.user=null; hideSyncPill(); return ok;
        }''' % PAGED)
        # 同一個位置崩潰兩次：那一批的 5 場逐筆下載，把特別大的那一場隔開
        c['sync_isolates_repeat_crash_point'] = page.evaluate('''async()=>{ %s
            await reset(R); const cloud=__makeFakeCloud(R,[]); window.__cloud=cloud;
            cloud.failAt=1; await handleAuthChange({uid:'u1'}); await wait(500);
            cloudKnown=null; cloud.pageCalls.length=0; cloud.failAt=0; await handleAuthChange({uid:'u1'}); await wait(500);
            cloudKnown=null; cloud.pageCalls.length=0; await handleAuthChange({uid:'u1'}); await wait(1500);
            const ok=trace(cloud)==='r04/1 r05/1 r06/1 r07/1 r08/1 r09/5';
            window.__cloud=null; state.user=null; hideSyncPill(); return ok;
        }''' % PAGED)
        # ?nosync=1：已登入也完全不碰雲端（一打開就崩潰、連登出都沒辦法時的出口）
        c['sync_nosync_escape_hatch'] = page.evaluate('''async()=>{ %s
            await reset(R); const cloud=__makeFakeCloud(R,[]); window.__cloud=cloud; sessionStorage.setItem('no-sync','1');
            await handleAuthChange({uid:'u1'}); await wait(500);
            const pill=(document.getElementById('sync-progress-pill')||{}).textContent||'';
            const ok=cloud.log.length===0 && cloud.pageCalls.length===0 && pill.includes('nosync');
            sessionStorage.removeItem('no-sync'); window.__cloud=null; state.user=null; hideSyncPill(); return ok;
        }''' % PAGED)
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
        # 右下角只剩「＋」一顆（v4.0）：說明、回饋收進頭像選單，不再有文字泡泡
        c['phone_only_new_race_fab_bottom_right'] = page.evaluate('''()=>{
            const nw=document.getElementById('btn-new-fab').getBoundingClientRect();
            const fixed=[...document.querySelectorAll('body *')].filter(el=>{
              const cs=getComputedStyle(el); if(cs.position!=='fixed'||cs.display==='none'||cs.visibility==='hidden') return false;
              const r=el.getBoundingClientRect(); return r.width>0&&r.height>0&&r.right>innerWidth-80&&r.bottom>innerHeight-160; });
            return nw.width>0 && Math.round(innerWidth-nw.right)===16 && Math.round(innerHeight-nw.bottom)===16
                && fixed.length===1 && fixed[0].id==='btn-new-fab'
                && !document.querySelector('.help-fab,.feedback-fab,#help-fab-caption,#feedback-fab-caption')
                && !!document.getElementById('btn-help').closest('#account-menu-panel')
                && !!document.getElementById('btn-feedback').closest('#account-menu-panel');
        }''')
        # ---- 字級切換（手機）：手機禁止雙指縮放，這是唯一放大字的方式 ----
        c['font_scale_changes_text_size'] = page.evaluate('''async()=>{
            state.races=[];
            const r=emptyRace('字級測試','road_running','completed','2025-04-27');
            r.route.distanceKm=21.0975; r.results.chipTimeSeconds=5185;
            r.budget={registrationFee:1200,currency:'TWD',paymentStatus:'paid'};
            state.races.push(r); selectRace(r.id,{scroll:false});
            await new Promise(s=>setTimeout(s,300));
            const size=async sc=>{ applyFontScale(sc); await new Promise(s=>setTimeout(s,150));
              return parseFloat(getComputedStyle(document.querySelector('.dash-card-sub')).fontSize); };
            const S=await size('small'), M=await size('medium'), L=await size('large');
            return Math.abs(M-13)<0.05 && Math.abs(S-11.7)<0.05 && Math.abs(L-14.95)<0.1;
        }''')
        # 30px 以上的大數字不縮放——放大會在手機上把完賽時間撐出螢幕
        c['font_scale_keeps_display_numbers'] = page.evaluate('''async()=>{
            const el=document.querySelector('.results-big-time');
            if(!el) return false;
            const at=async sc=>{ applyFontScale(sc); await new Promise(s=>setTimeout(s,150));
              return parseFloat(getComputedStyle(el).fontSize); };
            const S=await at('small'), L=await at('large');
            applyFontScale('medium');
            return S===L;
        }''')
        c['font_scale_large_no_horizontal_overflow_on_phone'] = page.evaluate('''async()=>{
            applyFontScale('large'); await new Promise(s=>setTimeout(s,300));
            const ok=document.documentElement.scrollWidth<=window.innerWidth+1;
            applyFontScale('medium');
            return ok;
        }''')
        # 360px 小螢幕（很多 Android 手機）：三種字級都不可以左右溢出；
        # 「大」字級時三個圖示按鈕可以整組換到下一行，但不能被拆散
        page.set_viewport_size({'width':360,'height':800})
        page.wait_for_timeout(250)
        c['phone_360_no_overflow_any_scale'] = page.evaluate('''async()=>{
            const out=[];
            for(const sc of ['small','medium','large']){
              applyFontScale(sc); await new Promise(s=>setTimeout(s,200));
              const tools=[...document.querySelectorAll('.cal-tools > button')].map(b=>Math.round(b.getBoundingClientRect().top));
              out.push(document.documentElement.scrollWidth<=window.innerWidth+1 && Math.max(...tools)-Math.min(...tools)<4);
            }
            applyFontScale('medium');
            return out.every(Boolean);
        }''')
        page.set_viewport_size({'width':390,'height':844})
        page.wait_for_timeout(250)
        # 訓練是首頁的第三個分頁（v4.0），手機上三個分頁平分寬度、都看得到字
        c['training_tab_visible_with_label_on_phone'] = page.evaluate('''()=>{
            selectRace(null);   // 上一個檢查停在賽事頁（賽事頁不顯示首頁分頁）
            const tr=document.getElementById('btn-training');
            const r=tr.getBoundingClientRect();
            const tabs=[...document.querySelectorAll('.home-tabs .home-tab')].map(b=>b.getBoundingClientRect());
            return !!tr.closest('.home-tabs') && !tr.closest('.topbar-actions') && r.width>0 && r.right<=window.innerWidth
                && tr.textContent.trim()==='訓練' && tabs.length===3 && tabs.every(x=>Math.abs(x.top-r.top)<1)
                && Math.max(...tabs.map(x=>x.width))-Math.min(...tabs.map(x=>x.width))<2;
        }''')
        # ---- iPhone 分頁崩潰（「重複發生問題」）：觸控裝置不可以有大面積合成效果（v3.88.0） ----
        br = page.context.browser
        PROBE = '''async()=>{
            state.races=[]; const r=emptyRace('若狹路','trail_running','registered',addDaysStr(todayISO(),5)); state.races.push(r);
            renderAll(); await new Promise(s=>setTimeout(s,400));
            const cs=(q,prop)=>{ const el=document.querySelector(q); return el?getComputedStyle(el)[prop]:null; };
            const bd=q=>cs(q,'backdropFilter')||cs(q,'webkitBackdropFilter');
            return {hoverNone:matchMedia('(hover:none)').matches, glow:cs('#ambient-glow','display'),
              topbar:bd('#topbar'), row2:bd('.topbar-row2'), blob:cs('.focus-mesh-blob','filter'), anim:cs('.focus-mesh-blob','animationName')};
        }'''
        tctx = full_mode_context(br, viewport={'width':390,'height':844}, is_mobile=True, has_touch=True)
        tp = tctx.new_page(); tp.goto('file://'+APP); tp.wait_for_timeout(900)
        touch = tp.evaluate(PROBE); tctx.close()
        dctx = full_mode_context(br, viewport={'width':1200,'height':900})
        dp = dctx.new_page(); dp.goto('file://'+APP); dp.wait_for_timeout(900)
        desk = dp.evaluate(PROBE); dctx.close()
        c['touch_devices_drop_large_compositing_effects'] = (touch['hoverNone'] is True and touch['glow']=='none'
            and touch['topbar']=='none' and touch['row2']=='none' and touch['blob']=='none' and touch['anim']=='none')
        # 桌機（有滑鼠）維持原本的效果
        c['desktop_keeps_visual_effects'] = (desk['hoverNone'] is False and desk['glow']!='none'
            and 'blur' in (desk['topbar'] or '') and 'blur' in (desk['blob'] or ''))
        # 安全模式：?safe=fx 開、重新整理仍有效、?safe=all 連圖片一起關、?safe=off 恢復
        sctx = full_mode_context(br, viewport={'width':390,'height':844}, is_mobile=True, has_touch=True)
        sp = sctx.new_page(); base='file://'+APP
        sp.goto(base+'?safe=fx'); sp.wait_for_timeout(700)
        a = sp.evaluate("()=>[document.documentElement.getAttribute('data-safe'),!!document.querySelector('.safe-mode-banner')]")
        sp.goto(base); sp.wait_for_timeout(700)
        b = sp.evaluate("()=>document.documentElement.getAttribute('data-safe')")
        sp.goto(base+'?safe=all'); sp.wait_for_timeout(700)
        c3 = sp.evaluate("()=>{const i=document.createElement('img');document.body.appendChild(i);const d=getComputedStyle(i).display;i.remove();return [document.documentElement.getAttribute('data-safe'),d];}")
        sp.goto(base+'?safe=off'); sp.wait_for_timeout(700)
        d = sp.evaluate("()=>[document.documentElement.getAttribute('data-safe'),!!document.querySelector('.safe-mode-banner')]")
        sctx.close()
        c['safe_mode_lifecycle'] = (a==['fx',True] and b=='fx' and c3==['fx img','none'] and d==[None,False])
        # 行事曆縮圖延遲載入：一百多場賽事時不要一次解碼全部
        import pathlib as _pl
        _src=_pl.Path(APP).read_text(encoding='utf-8')
        c['calendar_thumbs_lazy_load'] = ('class="cal-chip-thumb"' in _src and 'class="cal-list-thumb"' in _src
            and all('loading="lazy"' in seg.split('>')[0] for seg in _src.split('<img class="cal-')[1:3]))
        # ---- iPhone 狀態列：內容不可以被狀態列蓋住（v3.90.0，使用者截圖：標題被時間蓋住） ----
        c['content_clears_status_bar'] = page.evaluate('''async()=>{
            const root=document.documentElement;
            const measure=async()=>{ await new Promise(s=>setTimeout(s,150));
              const h1=document.querySelector('#topbar h1');
              openTrainingOverlay(); await new Promise(s=>setTimeout(s,150));
              const tr=document.querySelector('#training-overlay h2');
              const r={title:h1.getBoundingClientRect().top, training:tr.getBoundingClientRect().top};
              closeTrainingOverlay();
              const probe=cls=>{ const el=document.createElement('button'); el.className=cls; document.body.appendChild(el);
                const v=parseFloat(getComputedStyle(el).top); el.remove(); return v; };
              r.hofClose=probe('hof-close'); r.storyClose=probe('story-close-btn');
              return r; };
            const none=await measure();
            root.style.setProperty('--sat','47px');
            const bar=await measure();
            root.style.removeProperty('--sat');
            // 有狀態列時全部剛好往下讓出 47px；沒有時維持原位（桌機的 env() 是 0）
            const d=k=>Math.round(bar[k]-none[k]);
            return d('title')===47 && d('training')===47 && d('hofClose')===47 && d('storyClose')===47
                && none.hofClose===16 && none.storyClose===20;
        }''')
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
            const fab=document.getElementById('btn-new-fab');
            if(!fab.getBoundingClientRect().width) return false;
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
        # 語言選單在頭像選單裡（v4.0）：先打開選單再選
        for lang in ('zh', 'ja', 'en'):
            if lang != 'zh':
                if page.evaluate("()=>document.getElementById('account-menu-panel').hidden"):
                    page.click('#btn-account-menu')
                    page.wait_for_timeout(200)
                page.select_option('#lang-select', lang)
                page.wait_for_timeout(300)
                c[f'{lang}_menu_stays_open_after_language_change'] = page.evaluate(
                    "()=>!document.getElementById('account-menu-panel').hidden")
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
        # 牆在畫面下半部看不到時（矮視窗＋上面有「下一場」焦點卡）：切換後自動捲過去
        page.set_viewport_size({'width': 1100, 'height': 560})
        c['photo_wall_scrolls_into_view_on_toggle'] = page.evaluate('''async()=>{
            state.races=[];
            const up=emptyRace('下一場','road_running','registered',addDaysStr(todayISO(),6)); state.races.push(up);
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
            // 有捲動、牆在可視範圍內，而且沒被固定在上面的頂列、搜尋篩選列蓋住
            const row2=document.querySelector('.topbar-row2').getBoundingClientRect();
            return window.scrollY>0 && top>=row2.bottom-1 && top<window.innerHeight*0.6;
        }''')
        page.set_viewport_size(DESKTOP)
        page.wait_for_timeout(200)
        # v4.0：生涯數據、榮譽櫃搬到「生涯數據」分頁——賽事分頁的獎牌牆上面不再有它們
        c['photo_wall_not_under_career_summary'] = page.evaluate('''()=>{
            const wrap=document.querySelector('.photo-grid-wrap');
            return !!wrap && !document.querySelector('#calendar .career-summary-wrap')
                && !document.querySelector('#calendar .trophy-cabinet-summary');
        }''')
        # 已經看得到牆的時候不要捲（v4.0）：切換鈕就在牆的正上方
        c['photo_wall_toggle_does_not_scroll_when_visible'] = page.evaluate('''async()=>{
            state.races=state.races.filter(r=>r.status==='completed');
            state.viewMode='calendar'; renderAll(); window.scrollTo(0,0);
            await new Promise(s=>setTimeout(s,150));
            document.getElementById('cal-view-toggle').click();
            await new Promise(s=>setTimeout(s,700));
            const ok=window.scrollY===0 && !!document.querySelector('.photo-grid-wrap');
            state.viewMode='calendar'; renderAll();
            return ok;
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
        # ---- 征戰年數＝跨幾年，不是「有比賽的年份數」 ----
        c['career_years_is_span_not_active_count'] = page.evaluate('''()=>{
            const mk=y=>{ const r=emptyRace('賽事'+y,'road_running','completed',y+'-06-01');
              r.route.distanceKm=10; r.results.chipTimeSeconds=2400; state.races.push(r); };
            state.races=[];
            // 2012 跑第一場，中間空 2013–2016，2025 還在跑
            [2012,2017,2018,2019,2020,2021,2022,2023,2024,2025].forEach(mk);
            const d=computeHallOfFameData();
            return d.yearCount===14 && d.activeYearCount===10
                && d.firstRaceYear==='2012' && d.lastRaceYear==='2025';
        }''')
        # 只有一年、以及完全沒有完賽紀錄時不可以算錯
        c['career_years_edge_cases'] = page.evaluate('''()=>{
            state.races=[];
            const r=emptyRace('單場','road_running','completed','2024-06-01');
            r.route.distanceKm=10; r.results.chipTimeSeconds=2400; state.races.push(r);
            const one=computeHallOfFameData();
            state.races=[];
            const none=computeHallOfFameData();
            return one.yearCount===1 && one.activeYearCount===1 && none.yearCount===0;
        }''')
        # 畫面上要附區間說明，不然只看到 14 還是會想問為什麼
        c['career_years_tile_has_span_tooltip'] = page.evaluate('''async()=>{
            const mk=y=>{ const r=emptyRace('賽事'+y,'road_running','completed',y+'-06-01');
              r.route.distanceKm=10; r.results.chipTimeSeconds=2400; state.races.push(r); };
            state.races=[]; [2012,2020,2025].forEach(mk);
            renderCalendar(); openHallOfFame();
            await new Promise(s=>setTimeout(s,400));
            const tile=[...document.querySelectorAll('.hof-tile')].find(t=>
              t.querySelector('.hof-tile-label').textContent==='征戰年數');
            const ok=!!tile && tile.querySelector('.hof-tile-value').textContent==='14'
                  && tile.title.includes('2012') && tile.title.includes('2025')
                  && tile.title.includes('3');
            closeHallOfFame();
            return ok;
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
        # 視窗是從生涯回顧（z-index:210 的全螢幕圖層）打開的，必須疊在它上面，
        # 而且下載按鈕要真的按得到——被蓋住或被推到捲軸外都等於「按了沒反應」
        c['career_modal_sits_above_hall_of_fame'] = page.evaluate('''async()=>{
            state.races=[];
            for(let i=0;i<6;i++){ const r=emptyRace('賽事'+i,'road_running','completed','2025-0'+(1+i)+'-11');
              r.route.distanceKm=21.1; r.results.chipTimeSeconds=7200; state.races.push(r); }
            renderCalendar(); openHallOfFame();
            await new Promise(s=>setTimeout(s,300));
            document.querySelector('[data-action="open-career-share"]').click();
            await new Promise(s=>setTimeout(s,1200));
            const hofZ=parseInt(getComputedStyle(document.getElementById('hof-overlay')).zIndex,10);
            const modalZ=parseInt(getComputedStyle(document.getElementById('career-share-modal')).zIndex,10);
            const mid=document.elementFromPoint(window.innerWidth/2,window.innerHeight/2);
            return modalZ>hofZ && !!(mid&&mid.closest('#career-share-modal'));
        }''')
        c['career_download_button_is_reachable'] = page.evaluate('''()=>{
            const btn=document.querySelector('[data-action="confirm-career-share"]');
            if(!btn) return false;
            const b=btn.getBoundingClientRect();
            const hit=document.elementFromPoint(b.left+b.width/2,b.top+b.height/2);
            const ok=b.top>=0 && b.bottom<=window.innerHeight+1
                  && !!(hit&&hit.closest('[data-action="confirm-career-share"]'));
            closeCareerShareModal(); closeHallOfFame();
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
        ctx = full_mode_context(browser, viewport=self.viewport, service_workers='allow')
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
        # ---- 4a：sw.js 的預快取清單必須跟 index.html 載入的 CDN 網址一字不差 ----
        # index.html 用 SRI，快取回應內容一旦跟頁面要的版本對不上，套件整個不載入。
        # idb-keyval 是 <script src>；xlsx v4.5.0 起按「匯入 Excel」才載入，網址在 XLSX_SRC 常數
        html = open(APP, encoding='utf-8').read()
        sw_path = os.path.join(os.path.dirname(os.path.abspath(APP)), 'sw.js')
        sw = open(sw_path, encoding='utf-8').read() if os.path.exists(sw_path) else ''
        srcs = re.findall(r'<script src="(https://[^"]+)"', html) + re.findall(r"const XLSX_SRC='(https://[^']+)'", html)
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
        # ---- 有新版本的提醒要醒目：紅色箭頭從右上角指向「立即更新」（v3.77.0） ----
        page.goto(self.url, wait_until='domcontentloaded')
        page.wait_for_timeout(1200)
        c['update_banner_has_arrow_on_primary'] = page.evaluate('''async()=>{
            let posted=null;
            offerWorkerUpdate({waiting:{postMessage:m=>{ posted=m; }}});
            await new Promise(s=>setTimeout(s,100));
            const ban=document.querySelector('.app-banner.is-update');
            if(!ban) return false;
            const btns=[...ban.querySelectorAll('.app-banner-actions button')];
            const primary=ban.querySelector('button.primary');
            const arrow=ban.querySelector('.update-cta .update-arrow');
            const ok=btns[btns.length-1]===primary                 // 主要按鈕在最右邊
              && !!arrow && arrow.getAttribute('aria-hidden')==='true'
              && getComputedStyle(arrow).animationName==='update-arrow-poke';
            primary.click();
            return ok && posted && posted.type==='SKIP_WAITING' && swReloadRequested===true;
        }''')
        # 其他提示（安裝、儲存空間）不可以跟著長出箭頭
        c['other_banners_have_no_arrow'] = page.evaluate('''()=>{
            swReloadRequested=false;
            showAppBanner({text:'儲存空間快滿了',kind:'warn',actions:[{label:'清理',primary:true},{label:'稍後'}]});
            const ban=document.querySelector('.app-banner');
            const ok=!ban.classList.contains('is-update') && !ban.querySelector('.update-arrow')
              && ban.querySelector('.app-banner-actions button').classList.contains('primary');   // 原本的順序不變
            hideAppBanner();
            return ok;
        }''')
        # 360px 手機：箭頭不可以超出螢幕，也不可以蓋到提示文字（量字的實際範圍，不是量框）
        page.set_viewport_size({'width':360,'height':760})
        page.wait_for_timeout(200)
        c['update_arrow_fits_small_phone'] = page.evaluate('''async()=>{
            offerWorkerUpdate({waiting:{postMessage(){}}});
            await new Promise(s=>setTimeout(s,100));
            const ban=document.querySelector('.app-banner.is-update');
            const arrow=ban.querySelector('.update-arrow').getBoundingClientRect();
            const r=document.createRange(); r.selectNodeContents(ban.querySelector('.app-banner-text'));
            const g=r.getBoundingClientRect();
            const covers=!(g.right<=arrow.left||arrow.right<=g.left||g.bottom<=arrow.top||arrow.bottom<=g.top);
            hideAppBanner();
            return arrow.left>=0 && arrow.right<=window.innerWidth && !covers;
        }''')
        # 系統設定「減少動態效果」：箭頭還在，但不動
        page.emulate_media(reduced_motion='reduce')
        c['update_arrow_respects_reduced_motion'] = page.evaluate('''async()=>{
            offerWorkerUpdate({waiting:{postMessage(){}}});
            await new Promise(s=>setTimeout(s,100));
            const ban=document.querySelector('.app-banner.is-update');
            const a=ban.querySelector('.update-arrow');
            const ok=!!a && getComputedStyle(a).animationName==='none'
              && getComputedStyle(ban.querySelector('button.primary')).animationName==='none';
            hideAppBanner();
            return ok;
        }''')
        page.emulate_media(reduced_motion='no-preference')

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
        ctx=full_mode_context(browser, viewport=self.viewport)
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
        # ---- 「已存在的賽事」否決不可以擋掉：新增表單上的貼上、以及不同屆 ----
        c['paste_fills_open_create_form_even_if_name_exists'] = page.evaluate('''async()=>{
            state.races=[]; state.creating=false;
            state.races.push(emptyRace('臺北馬拉松','road_running','completed','2025-12-21'));
            startCreate();
            await new Promise(s=>setTimeout(s,350));
            const dt=new DataTransfer(); dt.setData('text','2026 臺北馬拉松\\n2026-12-20');
            document.dispatchEvent(new ClipboardEvent('paste',{clipboardData:dt,bubbles:true,cancelable:true}));
            await new Promise(s=>setTimeout(s,400));
            return document.getElementById('new-name').value==='2026 臺北馬拉松'
                && document.getElementById('new-date').value==='2026-12-20';
        }''')
        # 同系列的不同屆要能新增（名稱比對是子字串，去年那場會誤中）
        c['different_edition_still_counts_as_new_race'] = page.evaluate('''async()=>{
            state.races=[]; state.creating=false;
            state.races.push(emptyRace('臺北馬拉松','road_running','completed','2025-12-21'));
            renderAll(); await new Promise(s=>setTimeout(s,250));
            const dt=new DataTransfer(); dt.setData('text','2026 臺北馬拉松\\n2026-12-20');
            document.dispatchEvent(new ClipboardEvent('paste',{clipboardData:dt,bubbles:true,cancelable:true}));
            await new Promise(s=>setTimeout(s,400));
            const ok=state.creating===true && document.getElementById('new-name').value==='2026 臺北馬拉松';
            state.creating=false; renderAll();
            return ok;
        }''')
        # 但「同名又同一天」仍然不可以跳新增表單（那才是真的重複）
        c['same_name_same_date_does_not_offer_new_race'] = page.evaluate('''async()=>{
            state.races=[]; state.creating=false;
            const r=emptyRace('臺北馬拉松','road_running','completed','2025-12-21');
            state.races.push(r); selectRace(r.id,{scroll:false});
            await new Promise(s=>setTimeout(s,250));
            const dt=new DataTransfer(); dt.setData('text','臺北馬拉松\\n2025-12-21');
            document.dispatchEvent(new ClipboardEvent('paste',{clipboardData:dt,bubbles:true,cancelable:true}));
            await new Promise(s=>setTimeout(s,400));
            const ok=state.creating!==true;
            closePasteNoteModal();
            return ok;
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

class FeedbackConfigured(Group):
    """回饋按鈕在填好表單設定之後的行為（用原始碼替換常數的方式模擬）。"""
    def setup_page(self, page):
        import pathlib
        src=pathlib.Path(APP).read_text(encoding='utf-8')
        # 不管正式版填了什麼（v3.92 起已填入使用者的表單），都換成測試用的表單
        import re as _re
        src=_re.sub(r"const FEEDBACK_FORM_URL='[^']*';",
                    "const FEEDBACK_FORM_URL='https://docs.google.com/forms/d/e/TESTFORM/viewform';",src,count=1)
        src=_re.sub(r"const FEEDBACK_PREFILL=\{[^}]*\};",
                    "const FEEDBACK_PREFILL={version:'entry.111',device:'222',page:'entry.333'};",src,count=1)
        tmp=pathlib.Path('/tmp/_feedback_cfg.html'); tmp.write_text(src,encoding='utf-8')
        page.goto('file://'+str(tmp)); page.wait_for_timeout(900)

    def body(self, page):
        c = self.checks
        self.setup_page(page)
        # 使用說明、意見回饋（v4.0）：不再是右下角的懸浮鈕，收在頭像選單最後一組；
        # 選單打開時兩個都點得到（不被其他東西蓋住）
        c['help_and_feedback_in_avatar_menu'] = page.evaluate('''async()=>{
            const panel=document.getElementById('account-menu-panel');
            const fb=document.getElementById('btn-feedback'), help=document.getElementById('btn-help');
            const closedHidden=panel.hidden && !fb.getBoundingClientRect().width;
            document.getElementById('btn-account-menu').click(); await new Promise(s=>setTimeout(s,150));
            const hit=el=>{ const r=el.getBoundingClientRect(); const h=document.elementFromPoint(r.left+r.width/2,r.top+r.height/2); return !!(h&&h.closest('#'+el.id)); };
            const ok=closedHidden && !panel.hidden && hit(help) && hit(fb) && help.compareDocumentPosition(fb)&Node.DOCUMENT_POSITION_FOLLOWING
                && help.querySelector('img').getAttribute('src')==='icons/help-avatar.png'
                && !document.querySelector('.help-fab,.feedback-fab,.help-fab-wrap,.feedback-fab-wrap');
            document.getElementById('btn-account-menu').click();
            return ok && panel.hidden;
        }''')
        # ---- 字級、深色模式、語言（v4.0 收進頭像選單的「顯示」）：記憶、按下狀態 ----
        c['display_settings_in_avatar_menu'] = page.evaluate('''()=>{
            const panel=document.getElementById('account-menu-panel');
            const group=document.querySelector('.font-scale');
            const theme=document.getElementById('btn-theme-toggle');
            const lang=document.getElementById('lang-select');
            if(!group||!theme||!lang) return false;
            const labels=[...group.querySelectorAll('[data-font-scale]')].map(b=>b.textContent.trim()).join('');
            const inPanel=[group,theme,lang].every(el=>panel.contains(el));
            const order=group.compareDocumentPosition(theme)&Node.DOCUMENT_POSITION_FOLLOWING && theme.compareDocumentPosition(lang)&Node.DOCUMENT_POSITION_FOLLOWING;
            const topbarLoose=[...document.querySelectorAll('.topbar-actions > *')].every(el=>!el.matches('.font-scale,.lang-switcher,#btn-theme-toggle'));
            return inPanel && order && topbarLoose && labels==='小中大' && theme.getAttribute('role')==='switch'
                && group.querySelector('[data-font-scale="medium"]').getAttribute('aria-pressed')==='true';
        }''')
        c['font_scale_persists_and_syncs'] = page.evaluate('''async()=>{
            document.querySelector('[data-font-scale="large"]').click();
            await new Promise(s=>setTimeout(s,150));
            const saved=localStorage.getItem('font-scale-v1');
            const attr=document.documentElement.getAttribute('data-font');
            const pressed=[...document.querySelectorAll('[data-font-scale]')]
              .filter(b=>b.getAttribute('aria-pressed')==='true').map(b=>b.dataset.fontScale).join();
            document.querySelector('[data-font-scale="medium"]').click();
            await new Promise(s=>setTimeout(s,150));
            // 「中」是預設值：不留屬性、不留 localStorage
            return saved==='large' && attr==='large' && pressed==='large'
                && localStorage.getItem('font-scale-v1')===null
                && !document.documentElement.hasAttribute('data-font');
        }''')
        # 控制項本身不跟著縮放——否則切到大，頂端列自己也被撐大
        c['font_scale_control_itself_does_not_scale'] = page.evaluate('''async()=>{
            const btn=document.querySelector('[data-font-scale="medium"]');
            const before=getComputedStyle(btn).fontSize;
            applyFontScale('large'); await new Promise(s=>setTimeout(s,150));
            const after=getComputedStyle(btn).fontSize;
            applyFontScale('medium');
            return before===after;
        }''')
        # ---- 訓練是首頁的第三個分頁（v4.0；原本是頂列「＋ 新增賽事」下面的小按鈕） ----
        c['training_is_home_tab'] = page.evaluate('''()=>{
            const tr=document.getElementById('btn-training');
            const tabs=[...document.querySelectorAll('.home-tabs .home-tab')];
            return !!tr.closest('.home-tabs') && !tr.closest('#topbar') && tabs[tabs.length-1]===tr
                && tabs.every(b=>Math.abs(b.getBoundingClientRect().top-tr.getBoundingClientRect().top)<1);
        }''')
        # 頂列只剩三樣：簡易版、＋ 新增賽事、頭像——三種字級都排成一行、垂直置中對齊
        c['topbar_three_controls_aligned'] = page.evaluate('''async()=>{
            const out=[];
            for(const sc of ['small','medium','large']){
              applyFontScale(sc); await new Promise(s=>setTimeout(s,150));
              const shown=[...document.querySelectorAll('.topbar-actions > *')].filter(el=>el.getBoundingClientRect().width>0);
              const ids=shown.map(el=>el.id||el.className).join('|');
              const mid=el=>{const r=el.getBoundingClientRect(); return r.top+r.height/2;};
              const nb=document.getElementById('btn-new');
              const off=Math.max(...['#btn-mode-toggle','#btn-account-menu'].map(q=>Math.abs(mid(document.querySelector(q))-mid(nb))));
              out.push(ids==='btn-mode-toggle|btn-new|action-menu account-menu' && off<1.5
                && document.querySelector('header').getBoundingClientRect().height<110);
            }
            applyFontScale('medium');
            return out.every(Boolean);
        }''')
        c['training_button_opens_overlay'] = page.evaluate('''async()=>{
            document.getElementById('btn-training').click();
            await new Promise(s=>setTimeout(s,200));
            const open=!document.getElementById('training-overlay').hidden;
            closeTrainingOverlay();
            return open;
        }''')
        import pathlib as _pl
        _real=_pl.Path(APP).read_text(encoding='utf-8')
        c['feedback_form_configured'] = ("const FEEDBACK_FORM_URL='https://docs.google.com/forms/d/e/1FAIpQLSfuxfXHORQ96fceVn1fPc6RfE6Z7wuquU2Loj4Hor_HKe4rsA/viewform';" in _real
            and "const FEEDBACK_PREFILL={version:'entry.1727311429',device:'entry.1690470865',page:'entry.1958998644'};" in _real)
        c['feedback_prefill_builds_google_form_url'] = page.evaluate('''()=>{
            const u=new URL(buildFeedbackUrl());
            return u.pathname.endsWith('/viewform') && u.searchParams.get('usp')==='pp_url'
                && u.searchParams.get('entry.111')===APP_VERSION
                && !!u.searchParams.get('entry.222')          // 只寫數字也要自動補 entry. 前綴
                && u.searchParams.get('entry.333')==='首頁';
        }''')
        # 只帶版本／裝置／畫面，絕不夾帶賽事資料
        c['feedback_url_carries_no_race_data'] = page.evaluate('''async()=>{
            state.races=[];
            const r=emptyRace('私密賽事名稱XYZ','road_running','completed','2025-02-24');
            r.results.chipTimeSeconds=10774; r.bibNumber='003150';
            state.races.push(r); selectRace(r.id,{scroll:false});
            await new Promise(s=>setTimeout(s,300));
            const url=decodeURIComponent(buildFeedbackUrl());
            return !url.includes('私密賽事名稱XYZ') && !url.includes('003150')
                && !url.includes('2:59:34') && url.includes('賽事詳情');
        }''')
        # 從頭像選單按「意見回饋」：開表單，選單收起來
        c['feedback_menu_item_opens_form_and_closes_menu'] = page.evaluate('''async()=>{
            selectRace(null); await new Promise(s=>setTimeout(s,200));
            let args=null; const real=window.open; window.open=(...a)=>{ args=a; };
            document.getElementById('btn-account-menu').click(); await new Promise(s=>setTimeout(s,150));
            const opened=!document.getElementById('account-menu-panel').hidden;
            document.getElementById('btn-feedback').click();
            await new Promise(s=>setTimeout(s,150));
            window.open=real;
            return opened && !!args && args[0].includes('TESTFORM') && document.getElementById('account-menu-panel').hidden;
        }''')
        c['feedback_opens_new_tab'] = page.evaluate('''async()=>{
            let args=null; const real=window.open; window.open=(...a)=>{ args=a; };
            document.getElementById('btn-feedback').click();
            await new Promise(s=>setTimeout(s,150));
            window.open=real;
            return !!args && args[0].includes('TESTFORM') && args[1]==='_blank'
                && String(args[2]||'').includes('noopener');
        }''')

# 測試用 FIT 檔產生器（file header + session + record 訊息）。訓練匯入要走
# 真正的二進位解析路徑，不能用假的摘要物件代替。
FIT_GENERATOR_JS = r'''// 測試用 FIT 產生器：file header + session(18) + record(20) 訊息。小端序。
window.__makeFit=function(opt){
  const FIT_EPOCH=Date.UTC(1989,11,31,0,0,0)/1000;
  const start=Math.round(opt.start.getTime()/1000)-FIT_EPOCH;
  const bytes=[];
  const u8=v=>bytes.push(v&255);
  const u16=v=>{u8(v);u8(v>>8);};
  const u32=v=>{u8(v);u8(v>>8);u8(v>>16);u8(v>>24);};
  // record 定義（local 0）：253 timestamp u32、0 lat s32、1 lon s32、2 alt u16、3 hr u8
  u8(0x40);u8(0);u8(0);u16(20);u8(5);
  [[253,4,0x86],[0,4,0x85],[1,4,0x85],[2,2,0x84],[3,1,0x02]].forEach(f=>{u8(f[0]);u8(f[1]);u8(f[2]);});
  const n=opt.gps?opt.points:0;
  for(let i=0;i<n;i++){
    const a=i/(n-1)*Math.PI*2;
    const lat=opt.lat+Math.sin(a)*0.01, lon=opt.lon+Math.cos(a)*0.014+Math.sin(a*3)*0.002;
    u8(0x00); u32(start+i*Math.round(opt.seconds/n));
    const toSc=d=>Math.round(d*Math.pow(2,31)/180);
    const la=toSc(lat), lo=toSc(lon);
    u32(la>>>0); u32(lo>>>0); u16(Math.round((opt.alt+Math.sin(a*2)*15+500)*5)); u8(opt.hr);
  }
  // session 定義（local 1）：2 start u32、253 ts u32、5 sport enum、7 elapsed u32(ms)、9 dist u32(cm)、16 avgHr u8、22 ascent u16
  u8(0x41);u8(0);u8(0);u16(18);u8(7);
  [[2,4,0x86],[253,4,0x86],[5,1,0x00],[7,4,0x86],[9,4,0x86],[16,1,0x02],[22,2,0x84]].forEach(f=>{u8(f[0]);u8(f[1]);u8(f[2]);});
  u8(0x01); u32(start); u32(start+opt.seconds); u8(opt.sport); u32(opt.seconds*1000); u32(Math.round(opt.km*100000));
  u8(opt.hr); u16(opt.ascent);
  const data=new Uint8Array(bytes);
  const out=new Uint8Array(14+data.length);
  const dv=new DataView(out.buffer);
  dv.setUint8(0,14); dv.setUint8(1,0x10); dv.setUint16(2,2093,true); dv.setUint32(4,data.length,true);
  out[8]=46;out[9]=70;out[10]=73;out[11]=84;   // ".FIT"
  out.set(data,14);
  return new File([out],opt.name||'run.fit',{type:'application/octet-stream'});
};
'''

class Training(Group):
    """訓練紀錄（方案 B）：解析、匯入分類、鞋款里程、跟賽事的隔離、賽前訓練週期、同步合併。"""

    def body(self, page):
        c = self.checks
        # 靜態檢查：整份程式不可以出現「向後查找」正規表示式——iOS Safari 16.4
        # 以前不支援，一碰到就是語法錯誤，整個網站的程式都跑不起來
        import pathlib as _pl, re as _re
        _src=_pl.Path(APP).read_text(encoding='utf-8')
        c['no_regex_lookbehind_for_old_ios'] = len(_re.findall(r'\(\?<[!=]', _src))==0
        page.add_script_tag(content=FIT_GENERATOR_JS)
        page.evaluate('''()=>{ state.races=[]; trainings=[];
            shoes.length=0; shoes.push({id:'s1',name:'Pegasus 41',targetKm:700,isRetired:false,trainingKm:50}); }''')
        MK = '''const mk=(d,km,sec,name,o)=>__makeFit(Object.assign({name,start:new Date(d),gps:true,points:120,
            seconds:sec,km,hr:145,ascent:40,sport:1,lat:25.03,lon:121.56,alt:20},o||{}));'''

        # ---- 解析 ----
        c['fit_outdoor_uses_watch_totals'] = page.evaluate('''async()=>{ %s
            const r=await parseTrainingFile(mk('2026-09-14T06:10:00',12.3,3600,'o.fit',{points:300,hr:142,ascent:88}));
            return r.date==='2026-09-14' && r.startTime==='06:10' && r.sport==='run'
                && r.distanceKm===12.3 && r.durationSeconds===3600 && r.avgHr===142
                && r.elevationGainM===88                       // 手錶的爬升（氣壓計）優先於 GPS 重算
                && r.thumb.length===200 && r.fingerprint.length>=16;
        }''' % MK)
        # 跑步機沒有 GPS：賽事匯入會拒絕，訓練不可以
        c['fit_treadmill_without_gps_imports'] = page.evaluate('''async()=>{ %s
            const r=await parseTrainingFile(mk('2026-09-15T19:30:00',9,2700,'t.fit',{gps:false,hr:150,ascent:0}));
            return r.distanceKm===9 && r.durationSeconds===2700 && r.avgHr===150 && r.thumb===null;
        }''' % MK)
        c['gpx_reads_sport_and_name'] = page.evaluate('''async()=>{
            const pts=[]; for(let i=0;i<30;i++) pts.push(`<trkpt lat="${25+i*0.001}" lon="${121.5+i*0.001}"><ele>10</ele><time>2026-09-10T22:${String(i).padStart(2,'0')}:00Z</time></trkpt>`);
            const gpx=`<?xml version="1.0"?><gpx><trk><name>Evening Ride</name><type>cycling</type><trkseg>${pts.join('')}</trkseg></trk></gpx>`;
            const r=await parseTrainingFile(new File([gpx],'ride.gpx'));
            return r.sport==='ride' && r.name==='Evening Ride' && r.distanceKm>0 && !!r.thumb;
        }''')

        # ---- 匯入分類：新的／重複／比賽當天／讀不到 ----
        c['batch_import_classifies_files'] = page.evaluate('''async()=>{ %s
            state.races=[]; trainings=[];
            const race=emptyRace('大阪馬拉松','road_running','completed','2026-02-22');
            race.route.distanceKm=42.195; race.results.chipTimeSeconds=10774; race.performanceData.shoeId='s1';
            state.races.push(race);
            await startTrainingImport([mk('2026-01-10T06:00:00',15,4500,'a.fit'),mk('2026-01-17T06:00:00',30,9600,'b.fit'),
              mk('2026-02-08T06:00:00',12,3600,'c.fit'),mk('2026-02-22T08:00:00',42.4,10774,'race.fit'),
              new File([new Uint8Array([1,2,3])],'broken.fit'),new File(['x'],'note.txt')]);
            const st=trainingImportState;
            const ok=st.fresh.length===3 && st.raceDay.length===1 && st.raceDay[0]._race.name==='大阪馬拉松'
              && st.failed.length===1 && st.dupes.length===0;
            const sel=document.querySelector('[data-training-import-shoe]');
            sel.value='s1'; sel.dispatchEvent(new Event('change',{bubbles:true}));
            document.querySelector('[data-action="confirm-training-import"]').click();
            await new Promise(s=>setTimeout(s,300));
            return ok && liveTrainings().length===3 && liveTrainings().every(x=>x.shoeId==='s1');
        }''' % MK)
        c['reimport_and_cross_format_are_duplicates'] = page.evaluate('''async()=>{ %s
            await startTrainingImport([mk('2026-01-10T06:00:00',15,4500,'a.fit')]);   // 同一個檔
            const same=trainingImportState.dupes.length===1; closeTrainingImportModal();
            // 同一次運動另存成 GPX：檔案不同，但日期、開始時間、距離都一樣
            const rec=migrateTraining({date:'2026-01-10',startTime:'06:00',distanceKm:15.05,fingerprint:'other'});
            return same && !!findDuplicateTraining(rec);
        }''' % MK)
        c['race_day_file_can_be_opted_in'] = page.evaluate('''async()=>{ %s
            await startTrainingImport([mk('2026-02-22T08:00:00',42.4,10774,'race2.fit')]);
            const box=document.querySelector('[data-raceday="0"]');
            const disabledBefore=document.querySelector('[data-action="confirm-training-import"]').disabled;
            box.checked=true; box.dispatchEvent(new Event('change',{bubbles:true}));
            const enabledAfter=!document.querySelector('[data-action="confirm-training-import"]').disabled;
            closeTrainingImportModal();
            return disabledBefore && enabledAfter;
        }''' % MK)

        # ---- 鞋款里程：賽事＋手動補登＋匯入，比賽當天不重複算 ----
        c['shoe_km_adds_imported_training'] = page.evaluate('''()=>{
            const s=computeShoeStats('s1');
            return Math.abs(s.raceDistance-42.195)<0.01 && s.manualTrainingKm===50
                && Math.abs(s.importedTrainingKm-57)<0.01 && Math.abs(s.totalDistance-149.195)<0.01;
        }''')
        c['shoe_km_follows_edit_and_delete'] = page.evaluate('''async()=>{
            openTrainingOverlay(); trainingPeriod='all'; refreshTrainingOverlay();
            // v3.80 起「全部」依年月收合，預設只展開最新月份——要點的列得先展開才畫得出來
            trainingOpenYears=new Set(liveTrainings().map(x=>x.date.slice(0,4)));
            trainingOpenMonths=new Set(liveTrainings().map(x=>x.date.slice(0,7)));
            refreshTrainingOverlay();
            const id=liveTrainings().find(x=>x.distanceKm===30).id;
            document.querySelector(`[data-action="training-edit"][data-id="${id}"]`).click();
            const sel=document.querySelector(`[data-training-shoe="${id}"]`);
            sel.value=''; sel.dispatchEvent(new Event('change',{bubbles:true}));
            await new Promise(s=>setTimeout(s,200));
            const afterUnlink=computeShoeStats('s1').importedTrainingKm;
            const id2=liveTrainings().find(x=>x.distanceKm===12).id;
            document.querySelector(`[data-action="training-edit"][data-id="${id2}"]`).click();
            document.querySelector(`[data-action="training-delete"][data-id="${id2}"]`).click();
            await new Promise(s=>setTimeout(s,200));
            const afterDelete=computeShoeStats('s1').importedTrainingKm;
            const tomb=trainings.find(x=>x.id===id2);
            closeTrainingOverlay();
            return Math.abs(afterUnlink-27)<0.01 && Math.abs(afterDelete-15)<0.01
                && !!tomb.deletedAt && tomb.thumb===null;      // 軟刪除留墓碑，跨裝置才同步得到
        }''')

        # ---- 隔離：訓練不可以碰到任何賽事相關的東西 ----
        c['training_never_touches_race_data'] = page.evaluate('''async()=>{
            const before={races:state.races.length,
              career:JSON.stringify([computeHallOfFameData().totalCompleted,computeHallOfFameData().totalDistance]),
              chips:(renderCalendar(),document.querySelectorAll('.cal-chip').length)};
            trainings.push(migrateTraining({date:todayISO(),distanceKm:21,durationSeconds:6000,sport:'run',fingerprint:'iso'}));
            await persistTrainings();
            const after={races:state.races.length,
              career:JSON.stringify([computeHallOfFameData().totalCompleted,computeHallOfFameData().totalDistance]),
              chips:(renderCalendar(),document.querySelectorAll('.cal-chip').length)};
            const snap=JSON.stringify(buildPublicSnapshot(state.races[0]));
            return JSON.stringify(before)===JSON.stringify(after)
                && !/fingerprint|trainings/.test(snap);
        }''')

        # ---- 賽前訓練週期 ----
        c['buildup_weeks_align_to_race_day'] = page.evaluate('''()=>{
            trainings=[];
            const race=emptyRace('測試賽','road_running','completed','2026-03-01');   // 週日
            const add=(d,km,sport)=>trainings.push(migrateTraining({date:d,distanceKm:km,sport:sport||'run',fingerprint:d+km}));
            add('2026-02-28',5);   // 比賽前一天 → 賽前第 1 週
            add('2026-02-22',20);  // 比賽前 7 天 → 賽前第 1 週
            add('2026-02-21',30);  // 比賽前 8 天 → 賽前第 2 週
            add('2026-03-01',42);  // 比賽當天 → 不算
            add('2026-02-25',50,'ride');   // 路跑賽只算跑步
            const b=computeTrainingBuildup(race);
            const w=k=>b.weeks.find(x=>x.k===k);
            return w(1).km===25 && w(2).km===30 && b.longest===30
                && w(1).from==='2026-02-22' && w(1).to==='2026-02-28';
        }''')
        c['buildup_multisport_counts_all_sports'] = page.evaluate('''()=>{
            const tri=emptyRace('三鐵','triathlon','completed','2026-03-01');
            return computeTrainingBuildup(tri).weeks.find(x=>x.k===1).km===75;   // 5+20 跑＋50 騎
        }''')
        c['buildup_taper_waits_for_complete_weeks'] = page.evaluate('''()=>{
            trainings=[];
            const past=emptyRace('過去','road_running','completed','2026-03-01');
            for(let k=1;k<=5;k++){ const d=addDaysStr('2026-03-01',-7*k+1);
              trainings.push(migrateTraining({date:d,distanceKm:k<=2?30:60,sport:'run',fingerprint:'p'+k})); }
            const pastTaper=computeTrainingBuildup(past).taper;           // (30+30)/2 ÷ 60 −1 = −50%
            const soon=emptyRace('五天後','road_running','registered',addDaysStr(todayISO(),5));
            trainings.push(migrateTraining({date:todayISO(),distanceKm:5,sport:'run',fingerprint:'now'}));
            const b=computeTrainingBuildup(soon);
            const w1=b.weeks.find(x=>x.k===1);
            return pastTaper===-50 && w1.inProgress===true && b.taper===null;
        }''')
        c['buildup_card_hidden_until_feature_used'] = page.evaluate('''async()=>{
            state.races=[];
            const r=emptyRace('沒訓練資料','road_running','registered','2026-12-20');
            state.races.push(r);
            trainings=[];
            const none=trainingBuildupHtml(r);
            trainings.push(migrateTraining({date:'2020-01-01',distanceKm:5,sport:'run',fingerprint:'old'}));
            const empty=trainingBuildupHtml(r);
            return none==='' && empty.includes('沒有訓練紀錄');
        }''')
        c['buildup_week_drilldown_keeps_section_open'] = page.evaluate('''async()=>{
            trainings=[];
            state.races=[];
            const r=emptyRace('鑽取測試','road_running','completed','2026-03-01');
            state.races.push(r);
            trainings.push(migrateTraining({date:'2026-02-25',distanceKm:12,durationSeconds:3600,avgHr:140,sport:'run',fingerprint:'d1'}));
            selectRace(r.id,{scroll:false}); await new Promise(s=>setTimeout(s,250));
            const sec=document.getElementById('section-prep'); sec.open=true;
            document.querySelector('[data-action="buildup-week"][data-week="1"]').dispatchEvent(new MouseEvent('click',{bubbles:true}));
            await new Promise(s=>setTimeout(s,250));
            const drill=document.querySelector('.buildup-drill');
            return !!drill && drill.textContent.includes('12.0 km') && document.getElementById('section-prep').open;
        }''')

        # ---- 同步合併 ----
        c['merge_uses_updated_at_and_tombstones'] = page.evaluate('''()=>{
            trainings=[migrateTraining({id:'m1',date:'2026-01-01',distanceKm:10,updatedAt:'2026-01-02T00:00:00Z'}),
                       migrateTraining({id:'m2',date:'2026-01-03',distanceKm:8,updatedAt:'2026-01-05T00:00:00Z'})];
            mergeTrainings([
              {id:'m1',date:'2026-01-01',distanceKm:10,updatedAt:'2026-01-09T00:00:00Z',deletedAt:'2026-01-09T00:00:00Z'},  // 別台裝置刪了
              {id:'m2',date:'2026-01-03',distanceKm:99,updatedAt:'2026-01-04T00:00:00Z'},                                  // 雲端比較舊
              {id:'m3',date:'2026-01-07',distanceKm:6,updatedAt:'2026-01-07T00:00:00Z'}]);                                // 雲端才有
            const g=id=>trainings.find(x=>x.id===id);
            return !!g('m1').deletedAt && g('m2').distanceKm===8 && !!g('m3') && liveTrainings().length===2;
        }''')
        c['persist_schedules_cloud_push'] = page.evaluate('''async()=>{
            // v3.89 起只上傳有變的月份：雲端還一筆都沒有時，每個有訓練的月份都要上傳
            let pushed=null;
            const realCloud=window.__cloud, realUser=state.user, realKnown=cloudKnown;
            window.__cloud=Object.assign({},realCloud||{},{enabled:true,upsertTrainingMonths:async(uid,byMonth)=>{
              pushed={uid,months:Object.keys(byMonth).length,n:Object.values(byMonth).reduce((a,x)=>a+x.length,0)}; }});
            state.user={uid:'u1'}; cloudKnown={since:'',races:{},trainings:{}};
            await persistTrainings();
            await new Promise(s=>setTimeout(s,1300));
            window.__cloud=realCloud; state.user=realUser; cloudKnown=realKnown;
            const months=new Set(trainings.map(x=>(x.date||'').slice(0,7)||'unknown')).size;
            return !!pushed && pushed.uid==='u1' && pushed.n===trainings.length && pushed.months===months;
        }''')

        # ---- 依賽事建議準備週期與減量週數（v3.81.0） ----
        c['training_period_table_all_rows'] = page.evaluate('''()=>{
            const chk=(sport,km,prep,taper)=>{ const r=emptyRace('x',sport,'registered','2026-12-20');
              if(km!=null) r.route.distanceKm=km; const c2=classifyRaceForTraining(r);
              return !!c2 && c2.prep===prep && taperRangeText(c2)===taper; };
            return chk('road_running',5,4,'1') && chk('road_running',10,6,'1') && chk('road_running',21.0975,8,'1–2')
              && chk('road_running',42.195,16,'2–3') && chk('ultra_marathon',100,20,'2–3') && chk('road_running',60,20,'2–3')
              && chk('trail_running',15,8,'1') && chk('trail_running',25,14,'1–2') && chk('trail_running',43,20,'2–3')
              && chk('duathlon',30,8,'1') && chk('triathlon',51.5,12,'1') && chk('triathlon',113,16,'2–3')
              && chk('triathlon',226,24,'2–3');
        }''')
        # 距離沒填時從名稱判斷；表格沒有的運動不給建議、圖表維持 12 週
        c['training_period_infers_from_name_and_skips_unknown'] = page.evaluate('''()=>{
            const w=(name,sport,km)=>{ const r=emptyRace(name,sport,'registered','2026-12-20');
              if(km!=null) r.route.distanceKm=km; return effectivePrepWeeks(r); };
            const noSuggest=emptyRace('自行車賽','cycling','registered','2026-12-20'); noSuggest.route.distanceKm=100;
            return w('IRONMAN 70.3 Taiwan','triathlon',null)===16 && w('Challenge Taiwan 226','triathlon',null)===24
                && w('臺北全程馬拉松','road_running',null)===16 && w('萬金石半程馬拉松','road_running',null)===8
                && w('路跑（沒線索）','road_running',null)===12
                && classifyRaceForTraining(noSuggest)===null && effectivePrepWeeks(noSuggest)===12;
        }''')
        # 使用者填的優先；無效值退回建議；改距離時建議跟著變（建議值不寫進資料）
        c['training_period_user_value_wins_and_suggestion_is_live'] = page.evaluate('''()=>{
            const r=emptyRace('臺北馬拉松','road_running','registered','2026-12-20'); r.route.distanceKm=21.0975;
            const a=effectivePrepWeeks(r);
            r.route.distanceKm=42.195; const b=effectivePrepWeeks(r);
            r.trainingPlan.prepWeeks=18; r.trainingPlan.taperWeeks=2; const own=[effectivePrepWeeks(r),effectiveTaperWeeks(r)];
            r.trainingPlan.prepWeeks=0; r.trainingPlan.taperWeeks=-3; const bad=[effectivePrepWeeks(r),effectiveTaperWeeks(r)];
            return a===8 && b===16 && own.join()==='18,2' && bad.join()==='16,3'
                && r.trainingPlan.taperStartDate==='';      // 不自動填日期欄位（會讓減量期徽章自動成立）
        }''')
        # 長條圖依週數畫、減量週數標灰；超過 16 週只標偶數週與第 1 週
        c['buildup_uses_race_weeks'] = page.evaluate('''()=>{
            state.races=[]; trainings=[];
            const r=emptyRace('Challenge Taiwan 226','triathlon','completed','2026-03-01');
            state.races.push(r);
            trainings.push(migrateTraining({date:'2026-02-20',distanceKm:40,sport:'ride',fingerprint:'q1'}));
            trainings.push(migrateTraining({date:'2026-02-18',distanceKm:12,sport:'run',fingerprint:'q2'}));  // 路跑賽只算跑步
            const b=computeTrainingBuildup(r);
            const d=document.createElement('div'); d.innerHTML=trainingBuildupHtml(r);
            const bars=d.querySelectorAll('.buildup-bar'), taper=d.querySelectorAll('.buildup-bar.is-taper');
            const labels=[...d.querySelectorAll('.buildup-bar text')].map(x=>x.textContent);
            const sub=d.querySelector('.buildup-sub').textContent;
            // 馬拉松：16 根、最後 3 根是減量期
            const m=emptyRace('臺北馬拉松','road_running','completed','2026-03-01'); m.route.distanceKm=42.195;
            const dm=document.createElement('div'); dm.innerHTML=trainingBuildupHtml(m);
            return b.N===24 && bars.length===24 && taper.length===3 && sub.includes('24 週') && sub.includes('226K')
                && !labels.includes('23') && labels.includes('24') && labels.includes('1')
                && dm.querySelectorAll('.buildup-bar').length===16 && dm.querySelectorAll('.buildup-bar.is-taper').length===3;
        }''')
        c['training_plan_drawer_and_card_show_suggestion'] = page.evaluate('''async()=>{
            state.races=[];
            const r=emptyRace('臺北馬拉松','road_running','registered','2026-12-20'); r.route.distanceKm=42.195;
            state.races.push(r);
            const d=document.createElement('div'); d.innerHTML=trainingPlanDashCardHtml(r);
            const card=d.querySelector('.dash-card-sub').textContent, faint=!!d.querySelector('.dash-card.is-empty');
            r.trainingPlan.prepWeeks=18; d.innerHTML=trainingPlanDashCardHtml(r);
            const card2=d.querySelector('.dash-card-sub').textContent;
            r.trainingPlan.prepWeeks=null;
            selectRace(r.id,{scroll:false}); await new Promise(s=>setTimeout(s,250));
            openDrawer('trainingPlan'); await new Promise(s=>setTimeout(s,400));
            const ph=document.querySelector('[data-path="trainingPlan.prepWeeks"]').placeholder;
            const hint=(document.querySelector('.tp-hint')||{}).textContent||'';
            closeDrawer();
            return card==='準備 16 週・減量 2–3 週（建議）' && faint                 // 只有建議值時卡片仍是淡色
                && card2==='準備 18 週・減量 2–3 週（建議）'                          // 哪段是建議就標哪段
                && ph==='建議 16' && hint.includes('全程馬拉松');
        }''')
        # ---- 「全部」依年份、月份收合（v3.80.0） ----
        SEED700 = '''trainings=[]; let n=0; const t0=todayISO();
            for(let d=0;n<700;d+=3){ trainings.push(migrateTraining({id:'g'+n,date:addDaysStr(t0,-d),startTime:'06:15',
              sport:'run',distanceKm:+(5+((n*37)%15)+0.3).toFixed(1),durationSeconds:1800+((n*53)%3600),fingerprint:'g'+n})); n++; }'''
        c['all_tab_groups_by_year_and_month'] = page.evaluate('''()=>{ %s
            openTrainingOverlay(); trainingPeriod='all'; refreshTrainingOverlay();
            const ov=document.getElementById('training-overlay');
            const years=[...ov.querySelectorAll('[data-training-year]')];
            const curY=todayISO().slice(0,4), curM=todayISO().slice(0,7);
            const openYears=years.filter(b=>b.getAttribute('aria-expanded')==='true').map(b=>b.dataset.trainingYear);
            const openMonths=[...ov.querySelectorAll('[data-training-month][aria-expanded="true"]')].map(b=>b.dataset.trainingMonth);
            const rows=ov.querySelectorAll('.training-row').length;
            const expect=liveTrainings().filter(x=>x.date.slice(0,7)===curM).length;
            // 預設只展開最新的年份與月份；只畫出那個月的列（效能：700 筆不會一次全畫）
            return years[0].dataset.trainingYear===curY
                && JSON.stringify(openYears)===JSON.stringify([curY])
                && JSON.stringify(openMonths)===JSON.stringify([curM])
                && rows===expect && rows<60;
        }''' % SEED700)
        c['group_stats_add_up'] = page.evaluate('''()=>{
            // 某一年的次數＝那一年各月份次數加總
            const ov=document.getElementById('training-overlay');
            const y=String(Number(todayISO().slice(0,4))-1);
            ov.querySelector(`[data-training-year="${y}"]`).click();
            const num=s=>parseInt(s,10);
            const yCount=num(ov.querySelector(`[data-training-year="${y}"] .training-group-stats`).textContent);
            const mCounts=[...ov.querySelectorAll('[data-training-month]')].filter(b=>b.dataset.trainingMonth.startsWith(y))
              .map(b=>num(b.querySelector('.training-group-stats').textContent));
            const real=liveTrainings().filter(x=>x.date.startsWith(y)).length;
            return mCounts.length===12 && mCounts.reduce((a,b)=>a+b,0)===yCount && yCount===real;
        }''')
        c['group_toggles_render_only_open_months'] = page.evaluate('''()=>{
            const ov=document.getElementById('training-overlay');
            const y=String(Number(todayISO().slice(0,4))-1);
            const before=ov.querySelectorAll('.training-row').length;     // 去年展開了、但月份都還收著
            const m=y+'-06';
            ov.querySelector(`[data-training-month="${m}"]`).click();
            const afterOpen=ov.querySelectorAll('.training-row').length;
            const inJune=liveTrainings().filter(x=>x.date.slice(0,7)===m).length;
            ov.querySelector(`[data-training-year="${y}"]`).click();        // 收起整年
            const afterCollapse=ov.querySelectorAll('.training-row').length;
            return afterOpen===before+inJune && afterCollapse===before;
        }''')
        c['week_and_month_tabs_stay_flat_and_reopen_resets'] = page.evaluate('''()=>{
            const ov=document.getElementById('training-overlay');
            ov.querySelector('[data-training-period="week"]').click();
            const weekFlat=!ov.querySelector('[data-training-year]');
            ov.querySelector('[data-training-period="month"]').click();
            const monthFlat=!ov.querySelector('[data-training-year]');
            // 重新打開訓練頁：展開狀態回到預設
            trainingOpenYears.add('2021');
            closeTrainingOverlay(); openTrainingOverlay(); trainingPeriod='all'; refreshTrainingOverlay();
            const open=[...ov.querySelectorAll('[data-training-year][aria-expanded="true"]')].map(b=>b.dataset.trainingYear);
            closeTrainingOverlay();
            return weekFlat && monthFlat && JSON.stringify(open)===JSON.stringify([todayISO().slice(0,4)]);
        }''')
        # ---- 在訓練頁拖放檔案（v3.79.0：之前會卡在「放開以匯入檔案」畫面） ----
        DRAG = '''const drag=async(files,target)=>{
            const dt=new DataTransfer(); files.forEach(f=>dt.items.add(f));
            const fire=type=>target.dispatchEvent(new DragEvent(type,{bubbles:true,cancelable:true,dataTransfer:dt}));
            fire('dragenter'); fire('dragover'); await new Promise(s=>setTimeout(s,60));
            const text=document.querySelector('.global-dropzone-title').textContent;
            fire('drop'); await new Promise(s=>setTimeout(s,500));
            return {text,stuck:!document.getElementById('global-dropzone').hidden};
        };'''
        c['drop_on_training_page_imports_and_clears'] = page.evaluate('''async()=>{ %s %s
            trainings=[]; state.races=[];
            openTrainingOverlay();
            const r=await drag([mk('2026-09-01T06:00:00',12,3600,'a.fit'),mk('2026-09-03T06:00:00',8,2400,'b.fit')],
                               document.querySelector('#training-overlay .training-inner'));
            const btn=document.querySelector('[data-action="cancel-training-import"]');
            const b=btn&&btn.getBoundingClientRect();
            const hit=b&&document.elementFromPoint(b.left+b.width/2,b.top+b.height/2);
            const ok=r.text==='放開以匯入訓練紀錄' && r.stuck===false
              && trainingImportState && trainingImportState.fresh.length===2
              && !!(hit&&hit.closest('#training-import-modal'));      // 匯入視窗沒有被任何東西蓋住
            closeTrainingImportModal(); closeTrainingOverlay();
            return ok;
        }''' % (MK, DRAG))
        c['drop_elsewhere_still_imports_race'] = page.evaluate('''async()=>{ %s %s
            let routed=null; const real=window.routeDroppedFiles;
            window.routeDroppedFiles=async fs=>{ routed=fs.map(f=>f.name); };
            const r=await drag([mk('2026-09-01T06:00:00',12,3600,'race.fit')],document.getElementById('main-content'));
            window.routeDroppedFiles=real;
            return r.text==='放開以匯入檔案' && r.stuck===false
                && JSON.stringify(routed)==='["race.fit"]' && document.getElementById('training-import-modal').hidden;
        }''' % (MK, DRAG))
        # 保險：就算有元素在 drop 時 stopPropagation()，畫面也不能卡住（這次 bug 的成因）
        c['dropzone_never_sticks_even_if_drop_is_swallowed'] = page.evaluate('''async()=>{ %s %s
            const trap=document.createElement('div');
            trap.style.cssText='position:fixed;inset:0;z-index:1';
            trap.addEventListener('drop',e=>{ e.preventDefault(); e.stopPropagation(); });
            document.body.appendChild(trap);
            const r=await drag([mk('2026-09-01T06:00:00',5,1500,'x.fit')],trap);
            trap.remove();
            return r.stuck===false;
        }''' % (MK, DRAG))
        # ---- 畫面層級：匯入視窗一定要疊在訓練頁上面（v3.67 的教訓） ----
        c['import_modal_above_training_overlay'] = page.evaluate('''async()=>{ %s
            openTrainingOverlay();
            await startTrainingImport([mk('2025-05-05T06:00:00',8,2400,'z.fit')]);
            const oz=parseInt(getComputedStyle(document.getElementById('training-overlay')).zIndex,10);
            const mz=parseInt(getComputedStyle(document.getElementById('training-import-modal')).zIndex,10);
            const btn=document.querySelector('[data-action="confirm-training-import"]');
            const b=btn.getBoundingClientRect();
            const hit=document.elementFromPoint(b.left+b.width/2,b.top+b.height/2);
            const onTop=mz>oz && !!(hit&&hit.closest('#training-import-modal'));
            document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape'}));
            const modalClosed=document.getElementById('training-import-modal').hidden;
            const overlayStill=!document.getElementById('training-overlay').hidden;
            document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape'}));
            return onTop && modalClosed && overlayStill && document.getElementById('training-overlay').hidden;
        }''' % MK)


SIMPLE_SEED_JS = r"""window.__simpleSeed=async function(){
  const mk=(name,date)=>{ const r=emptyRace(name,'road_running','completed',date); r.route.distanceKm=42.195; r.results.chipTimeSeconds=12600; return r; };
  const rich=mk('2025 台北馬拉松','2025-12-21'); rich.id='rich';
  rich.alias='Taipei Marathon'; rich.series='台北馬'; rich.location.city='台北市'; rich.location.country='台灣';
  rich.route.elevationGainM=60;
  rich.route.elevationProfile=[{distanceKm:0,elevationM:10},{distanceKm:20,elevationM:32},{distanceKm:42,elevationM:12}];
  rich.checkpoints=[Object.assign(LIST_META.checkpoints.factory(),{name:'CP1',distanceKm:10}),Object.assign(LIST_META.checkpoints.factory(),{name:'CP2',distanceKm:25})];
  rich.splits=[...Array(42)].map((_,i)=>({distanceKm:1,splitTimeSeconds:295+(i%5),avgPaceSecPerKm:295+(i%5),avgHr:150+(i%10)}));
  rich.performanceData.avgHr=155; rich.results.overallRank=812; rich.budget.registrationFee=1500;
  rich.review.courseReview='後段起風'; rich.review.lessonsLearned='前半太快';
  const prev=mk('2024 台北馬拉松','2024-12-15'); prev.id='prev'; prev.series='台北馬';
  const bare=emptyRace('只填名字','road_running','registered','2026-12-20'); bare.id='bare';
  state.races=[rich,prev,bare]; await persist(); renderAll();
};
"""


class Simple(Group):
    """簡易版（v3.97.0）：右上角開關、新裝置預設、只收起不刪資料、抽屜常用欄位。
    這組刻意不預設完整版——要測的就是「沒有資料的新裝置」會進簡易版。"""
    preset_full_mode = False

    def body(self, page):
        c = self.checks
        mode = "()=>document.documentElement.getAttribute('data-mode')"
        c['new_device_without_data_defaults_simple'] = page.evaluate("""()=>
            document.documentElement.getAttribute('data-mode')==='simple'
            && localStorage.getItem('ui-mode-v1')==='simple' && localStorage.getItem('ui-mode-auto-v1')==='1'
            && document.getElementById('btn-mode-toggle').getAttribute('aria-checked')==='true'""")
        # 右上角：工具列第一顆、在畫面右半邊、跟「新增賽事」同一排
        c['switch_first_in_top_right_toolbar'] = page.evaluate("""()=>{
            const b=document.getElementById('btn-mode-toggle'), r=b.getBoundingClientRect(), n=document.getElementById('btn-new').getBoundingClientRect();
            const brand=document.querySelector('.topbar-brand').getBoundingClientRect();
            return b.parentElement.classList.contains('topbar-actions') && b.parentElement.firstElementChild===b
              && r.left>brand.right && r.right<=n.left && r.width>0 && Math.abs((r.top+r.bottom)/2-(n.top+n.bottom)/2)<4
              && b.getAttribute('role')==='switch'; }""")
        HIDDEN = "['#btn-training','#cal-table-toggle','#btn-export-csv','#btn-export-notebook']"
        c['simple_hides_static_entries_only'] = page.evaluate("""()=>{
            const d=q=>getComputedStyle(document.querySelector(q)).display;
            return %s.every(q=>d(q)==='none') && d('#btn-new')!=='none' && d('.font-scale')!=='none'
              && d('#btn-export')!=='none' && d('#btn-import')!=='none' && d('#cal-view-toggle')!=='none'
              && getComputedStyle(document.querySelector('.topbar-row1')).paddingBottom==='0px'; }""" % HIDDEN)
        page.add_script_tag(content=SIMPLE_SEED_JS)
        page.evaluate('async()=>{ await __simpleSeed(); selectRace("rich",{scroll:false}); }')
        page.wait_for_timeout(500)
        ADV = """()=>{ const q=s=>!!document.querySelector('#detail '+s);
            return {radar:q('.race-radar'),qnav:q('.quick-nav a'),logi:q('#section-logistics'),splitsChart:q('.splits-chart-block'),
              splitAna:q('.split-analysis'),elev:q('.elevation-profile'),series:!!document.querySelector('#detail > details.section:not([id])'),
              cp:q('[data-section="checkpoints"]'),weather:q('[data-section="weather"]'),nutri:q('[data-section="nutritionPlan"]'),
              tplan:q('[data-section="trainingPlan"]'),epp:q('.epp-section'),pacing:q('[data-action="open-pacing-modal"]'),
              spark:q('.spark'),fatigue:q('[data-action="open-fatigue-mode"]'),paste:q('[data-action="open-paste-modal"]'),
              aiPrompt:q('[data-action="copy-report-prompt"]'),shoe:[...document.querySelectorAll('#section-post h3')].some(h=>h.textContent.includes('鞋'))}; }"""
        adv = page.evaluate(ADV)
        c['simple_detail_does_not_render_advanced'] = not any(adv.values())
        c['simple_detail_keeps_core'] = page.evaluate("""()=>{ const q=s=>!!document.querySelector('#detail '+s);
            const sums=[...document.querySelectorAll('#detail details.section>summary')].map(x=>x.textContent.trim());
            return q('.results-big-time') && q('[data-action="generate-share-image"]') && q('#section-basic') && q('.journey-card')
              && ['basicInfo','schedule','route','goals','equipment','results','review','mediaLinks'].every(k=>q('[data-section="'+k+'"]'))
              && q('[data-action="open-gpx-picker"]') && q('[data-action="delete-race"]') && q('[data-action="duplicate-race"]')
              // v4.2 起已完賽的賽事「成績與心得」排第一
              && JSON.stringify(sums)===JSON.stringify(['成績與心得','基本資訊','路線與天氣','裝備與目標']); }""")
        # 頁尾提示只列這場真的有資料的進階區塊
        note = page.evaluate("()=>{ const n=document.querySelector('.simple-hidden-note'); return n?n.textContent:''; }")
        c['hidden_note_lists_filled_advanced_items'] = all(x in note for x in
            ['分段配速（42 段）', '賽事能力雷達', '系列賽比較', '海拔剖面', 'CP／補給站 2 筆', '預算與行程', '切換到完整版查看']) \
            and '訓練計畫' not in note and '補給設定' not in note and '氣象紀錄' not in note
        c['hidden_note_absent_when_nothing_hidden'] = page.evaluate("""async()=>{ selectRace('bare',{scroll:false});
            await new Promise(s=>setTimeout(s,200)); const none=!document.querySelector('.simple-hidden-note');
            selectRace('rich',{scroll:false}); await new Promise(s=>setTimeout(s,200)); return none; }""")
        # ---- 抽屜：只列常用欄位，可以就地展開 ----
        c['drawer_basic_common_fields_and_filled_count'] = page.evaluate("""async()=>{
            openDrawer('basicInfo'); await new Promise(s=>setTimeout(s,200));
            const paths=[...document.querySelectorAll('#drawer-content [data-path]')].map(x=>x.dataset.path);
            const btn=document.querySelector('#drawer-content .simple-fields-toggle');
            // 別名、系列有填；競賽形式是預設值「個人單人」，不算已填
            return JSON.stringify(paths)===JSON.stringify(['name','officialUrl','status','sportType','location.city','location.country'])
              && !!btn && btn.textContent==='顯示全部欄位（還有 5 項，其中 2 項已填）' && btn.getAttribute('aria-expanded')==='false'; }""")
        page.click('#drawer-content .simple-fields-toggle')
        page.wait_for_timeout(200)
        c['drawer_show_all_expands_in_place'] = page.evaluate("""()=>{
            const n=document.querySelectorAll('#drawer-content [data-path]').length;
            const btn=document.querySelector('#drawer-content .simple-fields-toggle');
            return n===11 && btn.textContent==='只顯示常用欄位' && btn.getAttribute('aria-expanded')==='true'
              && document.documentElement.getAttribute('data-mode')==='simple'; }""")
        page.fill('#drawer-content [data-path="alias"]', 'TPE')
        page.press('#drawer-content [data-path="alias"]', 'Tab')
        page.wait_for_timeout(400)
        c['drawer_edit_saves_and_reopen_resets'] = page.evaluate("""async()=>{
            const saved=state.races.find(r=>r.id==='rich').alias==='TPE';
            closeDrawer(); await new Promise(s=>setTimeout(s,300));
            openDrawer('basicInfo'); await new Promise(s=>setTimeout(s,200));
            const n=document.querySelectorAll('#drawer-content [data-path]').length;
            closeDrawer(); await new Promise(s=>setTimeout(s,300));
            return saved && n===6; }""")
        c['drawer_schedule_results_review_trimmed'] = page.evaluate("""async()=>{
            const get=async sec=>{ openDrawer(sec); await new Promise(s=>setTimeout(s,200));
              const p=[...document.querySelectorAll('#drawer-content [data-path]')].map(x=>x.dataset.path);
              closeDrawer(); await new Promise(s=>setTimeout(s,300)); return p; };
            const sc=await get('schedule'), rs=await get('results'), rv=await get('review');
            return JSON.stringify(sc)===JSON.stringify(['schedule.raceDate','schedule.startTime','bibNumber'])
              && JSON.stringify(rs)===JSON.stringify(['results.chipTimeSeconds','results.overallRank','results.overallParticipants','results.ageGroupRank','results.isPb'])
              && JSON.stringify(rv)===JSON.stringify(['review.courseReview']); }""")
        # ---- 切換：資料一個位元都不變 ----
        c['switching_never_changes_data'] = page.evaluate("""async()=>{
            const snap=async()=>JSON.stringify([state.races,await loadJson(STORAGE_KEY)]);
            const before=await snap(); const btn=document.getElementById('btn-mode-toggle');
            for(let i=0;i<4;i++){ btn.click(); await new Promise(s=>setTimeout(s,250)); }
            openDrawer('basicInfo'); await new Promise(s=>setTimeout(s,150));
            document.querySelector('#drawer-content .simple-fields-toggle').click(); await new Promise(s=>setTimeout(s,150));
            document.querySelector('#drawer-content .simple-fields-toggle').click(); await new Promise(s=>setTimeout(s,150));
            closeDrawer(); await new Promise(s=>setTimeout(s,400));
            return document.documentElement.getAttribute('data-mode')==='simple' && (await snap())===before; }""")
        # 頁尾按鈕 → 完整版：進階區塊全部回來、手動選過就清掉「自動」旗標
        # 選賽事時可能跳出「解鎖徽章」的動畫蓋住整頁，先收掉
        page.evaluate("()=>document.querySelectorAll('.badge-unbox-overlay').forEach(n=>n.remove())")
        page.click('.simple-hidden-note-btn')
        page.wait_for_timeout(400)
        adv_full = page.evaluate(ADV)
        c['note_button_switches_to_full_and_everything_returns'] = page.evaluate(mode) is None \
            and page.evaluate("()=>localStorage.getItem('ui-mode-v1')==='full'&&localStorage.getItem('ui-mode-auto-v1')===null&&document.getElementById('btn-mode-toggle').getAttribute('aria-checked')==='false'") \
            and all(adv_full[k] for k in ['radar', 'qnav', 'logi', 'splitsChart', 'elev', 'series', 'cp', 'weather',
                                          'nutri', 'tplan', 'pacing', 'fatigue', 'paste', 'aiPrompt', 'shoe'])
        c['full_mode_drawer_has_all_fields'] = page.evaluate("""async()=>{
            openDrawer('basicInfo'); await new Promise(s=>setTimeout(s,200));
            const n=document.querySelectorAll('#drawer-content [data-path]').length, b=!!document.querySelector('#drawer-content .simple-fields-toggle');
            closeDrawer(); await new Promise(s=>setTimeout(s,300)); return n===11 && !b; }""")
        # 簡易版沒有入口的抽屜開著時切換 → 收掉，不留孤兒抽屜
        c['switch_closes_drawer_without_entry'] = page.evaluate("""async()=>{
            openDrawer('logistics'); await new Promise(s=>setTimeout(s,200));
            const open=!document.getElementById('global-drawer').hidden;
            document.getElementById('btn-mode-toggle').click(); await new Promise(s=>setTimeout(s,400));
            return open && document.getElementById('global-drawer').hidden && document.documentElement.getAttribute('data-mode')==='simple'; }""")
        # 表格檢視：簡易版沒有那顆按鈕，不能卡在表格裡；切回完整版還是表格
        c['table_view_not_stuck_in_simple'] = page.evaluate("""async()=>{
            const btn=document.getElementById('btn-mode-toggle'); btn.click(); await new Promise(s=>setTimeout(s,300));
            document.getElementById('cal-table-toggle').click(); await new Promise(s=>setTimeout(s,200));
            const inTable=!!document.querySelector('#calendar .table-view-wrap');
            btn.click(); await new Promise(s=>setTimeout(s,300));
            const simpleNoTable=!document.querySelector('#calendar .table-view-wrap');
            btn.click(); await new Promise(s=>setTimeout(s,300));
            const back=!!document.querySelector('#calendar .table-view-wrap');
            document.getElementById('cal-table-toggle').click(); await new Promise(s=>setTimeout(s,200));
            return inTable && simpleNoTable && back && state.viewMode!=='table'; }""")
        # 首頁（五場以上才有生涯區）：簡易版收起榮譽櫃、氣溫與配速圖；留 PB 卡與年度回顧長圖卡
        c['home_trims_trophy_and_charts'] = page.evaluate("""async()=>{
            const extra=[1,2,3].map(i=>{ const r=emptyRace('馬拉松'+i,'road_running','completed','2023-0'+i+'-10'); r.route.distanceKm=42.195; r.results.chipTimeSeconds=13000+i; return r; });
            state.races.push(...extra); state.selectedId=null; state.homeTab='career'; renderAll(); await new Promise(s=>setTimeout(s,300));
            const q=s=>!!document.querySelector('#calendar '+s);
            const full=q('.trophy-cabinet-wrap') && q('.climate-chart-wrap') && q('.honor-card') && q('.year-in-review-row');
            document.getElementById('btn-mode-toggle').click(); await new Promise(s=>setTimeout(s,300));
            const simple=!q('.trophy-cabinet-wrap') && !q('.climate-chart-wrap') && q('.honor-card') && q('.year-in-review-row')
              && q('[data-action="open-hof"]');
            state.homeTab='races'; renderAll();
            return full && simple && document.documentElement.getAttribute('data-mode')==='simple'; }""")
        c['i18n_switch_and_section_labels'] = page.evaluate("""async()=>{
            selectRace('rich',{scroll:false}); await new Promise(s=>setTimeout(s,200));
            const lab=()=>document.querySelector('#btn-mode-toggle .mode-switch-label').textContent;
            const sum=()=>document.querySelector('#section-basic>summary').textContent.trim();
            setLang('ja'); const ja=[lab(),sum(),document.getElementById('btn-mode-toggle').title];
            setLang('en'); const en=[lab(),sum(),(document.querySelector('.simple-hidden-note')||{}).textContent||''];
            setLang('zh'); const zh=[lab(),sum()];
            return ja[0]==='シンプル' && ja[1]==='基本情報' && ja[2].includes('シンプル') && en[0]==='Simple' && en[1]==='Basics'
              && en[2].includes('splits (42)') && en[2].includes('View in full view') && zh[0]==='簡易版' && zh[1]==='基本資訊'; }""")
        # ---- 重新整理：偏好留著，而且在畫面出來前就套上（不會先閃完整版） ----
        # 記錄 #app 剛被解析出來那一刻的 data-mode（不能用 DOMContentLoaded：module
        # 腳本會拖慢它，init() 可能已經跑完）。那時主程式還沒讀完本機資料，
        # 只有 <head> 裡的早期腳本有機會先套上簡易版。
        page.add_init_script("new MutationObserver((ms,o)=>{ if(document.getElementById('app')){ window.__modeAtApp=document.documentElement.getAttribute('data-mode'); o.disconnect(); } }).observe(document,{childList:true,subtree:true});")
        page.reload()
        page.wait_for_timeout(900)
        c['simple_pref_applied_before_first_render'] = page.evaluate("()=>window.__modeAtApp==='simple' && document.documentElement.getAttribute('data-mode')==='simple' && document.getElementById('btn-mode-toggle').getAttribute('aria-checked')==='true'")
        # 已經有資料、還沒選過 → 完整版（更新後不會突然少一大半）
        page.evaluate("()=>{ localStorage.removeItem('ui-mode-v1'); localStorage.removeItem('ui-mode-auto-v1'); }")
        page.reload()
        page.wait_for_timeout(900)
        c['existing_data_defaults_full'] = page.evaluate("()=>window.__modeAtApp===null && document.documentElement.getAttribute('data-mode')===null && localStorage.getItem('ui-mode-v1')==='full' && localStorage.getItem('ui-mode-auto-v1')===null")
        # ---- 自動選的簡易版 + 第一次登入從雲端載回一堆賽事 → 其實是老使用者換新手機 ----
        page.add_script_tag(content=FAKE_CLOUD_JS)
        SETUP = """const wait=ms=>new Promise(s=>setTimeout(s,ms));
            const mk=(id)=>Object.assign(emptyRace('雲端'+id,'road_running','completed','2025-01-01'),{id,updatedAt:'2026-09-0'+id.length+'T00:00:00.000Z'});
            const setup=async(local,cloudRaces,pref,auto)=>{ await saveJson('cloud-sync-state-v1',null); cloudKnown=null; cloudPendingDeletes=[];
              state.races=local; trainings=[]; localStorage.setItem('ui-mode-v1',pref);
              if(auto) localStorage.setItem('ui-mode-auto-v1','1'); else localStorage.removeItem('ui-mode-auto-v1');
              applyUiModeAttr(pref); document.querySelectorAll('.foreground-toast,.toast').forEach(n=>n.remove());
              window.__cloud=__makeFakeCloud(cloudRaces,[]); };
            const done=()=>{ window.__cloud=null; state.user=null; };"""
        c['auto_simple_switches_full_after_cloud_restore'] = page.evaluate("""async()=>{ %s
            await setup([],[mk('a'),mk('bb'),mk('ccc')],'simple',true);
            await handleAuthChange({uid:'u1'}); await wait(1400);
            const txt=document.body.textContent;
            const ok=document.documentElement.getAttribute('data-mode')===null && localStorage.getItem('ui-mode-v1')==='full'
              && localStorage.getItem('ui-mode-auto-v1')===null && txt.includes('已從雲端載入 3 場賽事');
            done(); return ok; }""" % SETUP)
        c['explicit_simple_kept_after_cloud_restore'] = page.evaluate("""async()=>{ %s
            await setup([],[mk('a'),mk('bb')],'simple',false);
            await handleAuthChange({uid:'u1'}); await wait(1400);
            const ok=document.documentElement.getAttribute('data-mode')==='simple' && state.races.length===2;
            done(); return ok; }""" % SETUP)
        c['auto_simple_with_local_races_kept'] = page.evaluate("""async()=>{ %s
            await setup([mk('mine')],[mk('mine'),mk('a')],'simple',true);
            await handleAuthChange({uid:'u1'}); await wait(1400);
            const ok=document.documentElement.getAttribute('data-mode')==='simple' && localStorage.getItem('ui-mode-auto-v1')==='1';
            done(); return ok; }""" % SETUP)
        # 公開分享頁是給別人看的完整紀錄：不受這台裝置的簡易版影響（最後做，會換掉整個 body）
        c['public_view_ignores_simple_mode'] = page.evaluate("""async()=>{
            applyUiModeAttr('simple'); fetchPublicSnapshotAnyway=async()=>null;
            await bootPublicShareView('x'); return document.documentElement.getAttribute('data-mode')===null; }""")


class SimplePhone(Group):
    """手機頂列（v4.0 起只有一行）：標題｜簡易版開關｜頭像。開關緊貼在頭像左邊、
    跟標題同一行、不壓到標題、不撐出橫向捲軸；簡易版沒有「訓練」分頁。"""
    preset_full_mode = False

    def run(self, browser):
        for w in (360, 390):
            for m in ('simple', 'full'):
                ctx = browser.new_context(viewport={'width': w, 'height': 800}, is_mobile=True, has_touch=True)
                ctx.add_init_script("try{ localStorage.setItem('ui-mode-v1','%s'); }catch(e){}" % m)
                page = ctx.new_page()
                page.on('pageerror', lambda e: self.errors.append(str(e)))
                page.goto(APP_URL)
                page.wait_for_timeout(800)
                for lang in ('zh', 'en', 'ja'):
                    r = page.evaluate("""(lang)=>{ setLang(lang);
                        const b=document.getElementById('btn-mode-toggle').getBoundingClientRect();
                        const av=document.getElementById('btn-account-menu').getBoundingClientRect();
                        const h=document.querySelector('.app-title'); const rg=document.createRange(); rg.selectNodeContents(h);
                        const tr=rg.getBoundingClientRect();
                        return {right:innerWidth-av.right, avGap:av.left-b.right, top:b.top, titleBottom:tr.bottom, gap:b.left-tr.right, w:b.width,
                          avTop:av.top, scroll:document.documentElement.scrollWidth, vw:innerWidth,
                          newBtn:getComputedStyle(document.getElementById('btn-new')).display,
                          training:getComputedStyle(document.getElementById('btn-training')).display}; }""", lang)
                    ok = (r['w'] > 0 and 10 <= r['right'] <= 24 and 0 <= r['avGap'] <= 12 and r['top'] < r['titleBottom']
                          and r['avTop'] < r['titleBottom'] and r['gap'] >= 8 and r['newBtn'] == 'none'
                          and r['scroll'] <= r['vw'] and ((r['training'] == 'none') == (m == 'simple')))
                    self.checks[f'phone{w}_{m}_{lang}_one_row_topbar_no_overlap'] = ok
                    if not ok:
                        print(f'   ⚠ phone{w}_{m}_{lang}: {r}')
                ctx.close()
        return self.checks, self.errors



# 107 場、2015–2025，接近使用者實際的資料量（固定亂數種子，每次一樣）
UX_SEED_JS = r"""window.__seed107=async function(){
  const cities=['台北市','新北市','台中市','高雄市','花蓮縣','台東縣','宜蘭縣','南投縣','嘉義縣','大阪','東京','福井','柏林'];
  const kinds=[['road_running',42.195,'馬拉松'],['road_running',21.0975,'半程馬拉松'],['trail_running',35,'越野賽'],['triathlon',51.5,'鐵人三項'],['road_running',10,'10K 路跑'],['cycling',100,'單車挑戰']];
  let seed=11; const rnd=()=>{ seed=(seed*9301+49297)%233280; return seed/233280; };
  const out=[];
  for(let i=0;i<107;i++){
    const y=2015+Math.floor(i/10); const m=1+Math.floor(rnd()*12); const d=1+Math.floor(rnd()*27);
    const k=kinds[Math.floor(rnd()*kinds.length)]; const city=cities[Math.floor(rnd()*cities.length)];
    const date=`${y}-${String(m).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
    const st=rnd()<0.93?'completed':(rnd()<0.5?'dnf':'dns');
    const r=emptyRace(`${y} ${city}${k[2]}`,k[0],st,date);
    r.route.distanceKm=k[1]; r.location.city=city;
    if(st==='completed'){ r.results.chipTimeSeconds=Math.round(k[1]*300); r.results.overallRank=100+i; }
    out.push(r);
  }
  state.races=out; state.selectedId=null; state.filterStatus='all'; state.searchQuery='';
  document.getElementById('search-input').value='';
  state.calendarYear=2026; state.calendarMonth=8; state.viewMode='calendar';
  await persist(); renderAll();
};
"""


class UxFixes(Group):
    """v3.98.0 使用者體驗修正：跨月份搜尋／篩選、未定日期、空月份跳轉、
    編輯後不收起區段不跳走、頁首海拔小圖。"""

    def body(self, page):
        c = self.checks
        page.add_script_tag(content=UX_SEED_JS)
        page.add_style_tag(content='.badge-unbox-overlay,.foreground-toast{display:none!important}')
        page.evaluate('__seed107()')
        page.wait_for_timeout(400)
        # ---- 搜尋：列出所有月份，不是只找這個月 ----
        page.fill('#search-input', '大阪')
        page.wait_for_timeout(400)
        c['search_lists_matches_from_all_months'] = page.evaluate("""()=>{
            const n=state.races.filter(r=>r.location.city==='大阪').length;
            const rows=[...document.querySelectorAll('#calendar .cal-results .cal-list-item')];
            const res=document.querySelector('#calendar .cal-results');
            return n>=5 && rows.length===n && rows.every(b=>state.races.find(r=>r.id===b.dataset.id).location.city==='大阪')
              && document.querySelector('.cal-results-title').textContent==='搜尋「大阪」：'+n+' 場'
              && !document.querySelector('#calendar .cal-grid') && !document.querySelector('.career-summary-wrap')
              && res.getBoundingClientRect().top+scrollY<500 && document.querySelector('.cal-nav').classList.contains('is-results'); }""")
        c['search_results_grouped_by_year_newest_first'] = page.evaluate("""()=>{
            const years=[...document.querySelectorAll('.cal-results-group-title')].map(h=>h.childNodes[0].textContent.trim());
            const dates=[...document.querySelectorAll('.cal-results .cal-list-item')].map(b=>state.races.find(r=>r.id===b.dataset.id).schedule.raceDate);
            return years.length>1 && years.every((y,i)=>i===0||y<years[i-1]) && dates.every((d,i)=>i===0||d<=dates[i-1]); }""")
        page.click('.cal-results .cal-list-item')
        page.wait_for_timeout(500)
        c['result_row_opens_race'] = page.evaluate("()=>!!currentRace && currentRace.location.city==='大阪'")
        # v3.99 起賽事頁是獨立畫面：先返回結果清單，再清除
        page.click('#detail .qn-back')
        page.wait_for_timeout(500)
        page.evaluate('scrollTo(0,0)')
        page.click('[data-action="clear-cal-results"]')
        page.wait_for_timeout(300)
        c['clear_button_returns_to_month'] = page.evaluate("""()=>state.searchQuery==='' && document.getElementById('search-input').value===''
            && state.filterStatus==='all' && !!document.querySelector('#calendar .cal-grid') && !document.querySelector('.cal-results')
            && !document.querySelector('.cal-nav').classList.contains('is-results')""")
        # ---- 篩選：數字跟畫面一致 ----
        page.evaluate("()=>{ [...document.querySelectorAll('#filter-chips .chip')].find(b=>b.dataset.status==='history').click(); }")
        page.wait_for_timeout(300)
        c['filter_chip_count_matches_list'] = page.evaluate("""()=>{
            const chip=[...document.querySelectorAll('#filter-chips .chip')].find(b=>b.dataset.status==='history');
            const n=Number((chip.textContent.match(/\\((\\d+)\\)/)||[])[1]);
            return n===107 && document.querySelectorAll('.cal-results .cal-list-item').length===n
              && document.querySelector('.cal-results-title').textContent==='「歷史紀錄」：107 場'; }""")
        page.click('#cal-prev')
        page.wait_for_timeout(300)
        c['month_arrow_leaves_results_to_month'] = page.evaluate("""()=>!document.querySelector('.cal-results') && state.filterStatus==='all'
            && state.calendarMonth===7 && state.calendarYear===2026 && !!document.querySelector('#calendar .cal-grid')""")
        c['upcoming_group_ascending'] = page.evaluate("""async()=>{
            const a=emptyRace('遠的','road_running','registered','2027-03-01'), b=emptyRace('近的','road_running','registered','2026-11-01');
            state.races.push(a,b); await persist();
            [...document.querySelectorAll('#filter-chips .chip')].find(x=>x.dataset.status==='upcoming').click();
            await new Promise(s=>setTimeout(s,300));
            const g=document.querySelector('.cal-results-group'); const names=[...g.querySelectorAll('.cal-list-name')].map(x=>x.textContent);
            const title=g.querySelector('.cal-results-group-title').childNodes[0].textContent.trim();
            const dates=[...g.querySelectorAll('.cal-results-date')].map(x=>x.textContent);
            document.querySelector('[data-action="clear-cal-results"]').click();
            return title==='即將到來' && names.join()==='近的,遠的' && dates.join()==='2026-11-01,2027-03-01'; }""")
        # ---- 沒填日期的賽事 ----
        page.evaluate("()=>{ document.getElementById('btn-new').click(); }")
        page.wait_for_timeout(300)
        page.fill('#new-name', '想參加的超馬')
        page.click('[data-action="confirm-create"]')
        page.wait_for_timeout(500)
        c['undated_race_shown_under_month'] = page.evaluate("""async()=>{
            state.selectedId=null; renderAll(); await new Promise(s=>setTimeout(s,200));
            const u=document.querySelector('#calendar .cal-undated');
            return !!u && u.textContent.includes('未定日期') && u.textContent.includes('想參加的超馬')
              && !!u.querySelector('.cal-results-row.no-date'); }""")
        page.fill('#search-input', '超馬')
        page.wait_for_timeout(400)
        c['undated_race_found_by_search'] = page.evaluate("""()=>{
            const g=document.querySelector('.cal-results-group');
            const row=[...g.querySelectorAll('.cal-results-row')].find(x=>x.textContent.includes('想參加的超馬'));
            return g.querySelector('.cal-results-group-title').childNodes[0].textContent.trim()==='即將到來'
              && !!row && row.querySelector('.cal-results-date').textContent==='日期未定' && !document.querySelector('.cal-results .cal-undated'); }""")
        page.fill('#search-input', '')
        page.wait_for_timeout(300)
        c['undated_race_visible_in_simple_mode'] = page.evaluate("""async()=>{
            setUiMode('simple',{silent:true}); await new Promise(s=>setTimeout(s,200));
            const ok=!!document.querySelector('#calendar .cal-undated') && document.querySelector('#calendar .cal-undated').textContent.includes('想參加的超馬');
            setUiMode('full',{silent:true}); await new Promise(s=>setTimeout(s,200)); return ok; }""")
        # ---- 空月份：上一場／下一場直接跳過去 ----
        c['empty_month_offers_prev_next'] = page.evaluate("""async()=>{
            // 第一場之前的月份：只有「下一場」
            state.calendarYear=2014; state.calendarMonth=5; renderCalendar();
            const before=document.querySelector('#calendar .cal-month-empty');
            const onlyNext=!!before && !before.querySelector('.cal-jump-prev') && !!before.querySelector('.cal-jump-next');
            if(!onlyNext) return false;
            // 找一個 2016–2025 之間沒有比賽的月份（前後都有比賽）
            let y=2016,m=0,found=false;
            for(;y<=2025&&!found;y++) for(m=0;m<12;m++){ const k=`${y}-${String(m+1).padStart(2,'0')}`;
              if(!state.races.some(r=>(r.schedule.raceDate||'').startsWith(k))){ found=true; break; } }
            y--; state.calendarYear=y; state.calendarMonth=m; renderCalendar();
            const box=document.querySelector('#calendar .cal-month-empty');
            const prev=box&&box.querySelector('.cal-jump-prev'), next=box&&box.querySelector('.cal-jump-next');
            if(!found||!prev||!next) return false;
            const target=next.dataset.ym; next.click(); await new Promise(s=>setTimeout(s,200));
            const [ty,tm]=target.split('-').map(Number);
            return state.calendarYear===ty && state.calendarMonth===tm-1 && !document.querySelector('#calendar .cal-month-empty')
              && document.querySelectorAll('#calendar .cal-chip').length>0 && box.textContent.includes('這個月沒有賽事'); }""")
        # ---- 編輯後：區段不收起、畫面不跳、游標留在下一格 ----
        page.evaluate("""()=>{ const r=state.races.filter(x=>x.status==='completed').slice(-2)[0]; selectRace(r.id,{scroll:true}); }""")
        page.wait_for_timeout(700)
        page.evaluate("()=>document.querySelector('#section-post>summary').click()")
        page.wait_for_timeout(200)
        page.evaluate("""()=>{ const c=document.querySelector('#section-post [data-section="results"]'); scrollTo(0,c.getBoundingClientRect().top+scrollY-300); }""")
        page.wait_for_timeout(200)
        y0 = page.evaluate('Math.round(scrollY)')
        page.click('#section-post [data-section="results"]')
        page.wait_for_timeout(500)
        page.fill('#drawer-content [data-path="results.overallRank"]', '321')
        page.press('#drawer-content [data-path="results.overallRank"]', 'Tab')
        page.wait_for_timeout(500)
        c['drawer_edit_keeps_focus_on_next_field'] = page.evaluate("""()=>document.activeElement && document.activeElement.dataset.path==='results.overallParticipants'
            && currentRace.results.overallRank===321 && document.getElementById('section-post').open""")
        page.keyboard.press('Escape')
        page.wait_for_timeout(600)
        c['closing_drawer_keeps_section_and_scroll'] = page.evaluate("""(y0)=>document.getElementById('section-post').open
            && Math.abs(scrollY-y0)<=2 && document.getElementById('global-drawer').hidden
            && document.querySelector('.hero-results').textContent.includes('321')""", y0)
        c['simple_toggle_keeps_open_sections'] = page.evaluate("""async()=>{
            document.getElementById('btn-mode-toggle').click(); await new Promise(s=>setTimeout(s,250));
            const a=document.getElementById('section-post').open;
            document.getElementById('btn-mode-toggle').click(); await new Promise(s=>setTimeout(s,250));
            return a && document.getElementById('section-post').open; }""")
        c['switching_race_still_starts_collapsed'] = page.evaluate("""async()=>{
            const other=state.races.filter(x=>x.status==='completed').slice(-5)[0]; selectRace(other.id,{scroll:false});
            await new Promise(s=>setTimeout(s,300));
            return [...document.querySelectorAll('#detail details.section[id]')].every(d=>!d.open); }""")
        # ---- 頁首海拔小圖 ----
        c['header_spark_is_small_and_labelled'] = page.evaluate("""async()=>{
            document.getElementById('btn-sample-data').click(); await new Promise(s=>setTimeout(s,400));
            selectRace('example-alishan-trail',{scroll:false}); await new Promise(s=>setTimeout(s,300));
            const e=document.querySelector('#detail .detail-header .spark'); if(!e) return false;
            const b=e.getBoundingClientRect();
            return Math.round(b.width)===140 && Math.round(b.height)===22 && /^海拔 \\d+–\\d+ m$/.test(e.getAttribute('aria-label'))
              && e.closest('.dh-spark').textContent.trim()===e.getAttribute('aria-label'); }""")
        # ---- 語言 ----
        c['i18n_results_and_empty_month'] = page.evaluate("""async()=>{
            state.selectedId=null; renderAll();
            setLang('en'); state.searchQuery='大阪'; renderCalendar();
            const en=document.querySelector('.cal-results-title').textContent;
            setLang('ja'); renderCalendar(); const ja=document.querySelector('.cal-results-title').textContent;
            exitCalendarResults(); state.calendarYear=2030; state.calendarMonth=0; renderCalendar();
            const jaEmpty=document.querySelector('.cal-month-empty').textContent;
            setLang('zh'); state.calendarYear=2026; state.calendarMonth=8; renderCalendar();
            return /^“大阪”: \\d+ races$/.test(en) && /^「大阪」の検索結果：\\d+ 件$/.test(ja) && jaEmpty.includes('今月の大会はありません') && jaEmpty.includes('前の大会'); }""")
        # 獎牌牆、表格檢視本來就是跨月份的，搜尋時維持原本的畫面
        c['grid_and_table_views_unchanged_by_search'] = page.evaluate("""async()=>{
            state.searchQuery='大阪'; state.viewMode='grid'; renderCalendar(); const g=!document.querySelector('.cal-results');
            state.viewMode='table'; renderCalendar(); const tb=!document.querySelector('.cal-results') && !!document.querySelector('.table-view-wrap');
            state.viewMode='calendar'; state.searchQuery=''; renderCalendar(); return g && tb; }""")
        # ================= v3.99.0：賽事頁是獨立畫面、網址帶賽事 =================
        page.evaluate('async()=>{ await __seed107(); scrollTo(0,0); }')
        page.wait_for_timeout(300)
        page.fill('#search-input', '大阪')
        page.wait_for_timeout(400)
        page.evaluate("()=>{ const e=document.querySelectorAll('.cal-results .cal-list-item')[4]; scrollTo(0,e.getBoundingClientRect().top+scrollY-300); }")
        page.wait_for_timeout(200)
        y_list = page.evaluate('Math.round(scrollY)')
        page.evaluate("()=>document.querySelectorAll('.cal-results .cal-list-item')[4].click()")
        page.wait_for_timeout(600)
        rid = page.evaluate('state.selectedId')
        c['entering_race_sets_url_and_shows_only_detail'] = page.evaluate("""(id)=>{
            const hidden=s=>getComputedStyle(document.querySelector(s)).display==='none';
            const first=document.getElementById('detail').firstElementChild;
            return !!id && location.hash==='#race='+encodeURIComponent(id) && hidden('#calendar') && hidden('.topbar-row2')
              && hidden('.home-tabs') && hidden('#focus-panel-slot') && scrollY===0
              && first.classList.contains('quick-nav') && first.firstElementChild.classList.contains('qn-back')
              && first.querySelectorAll('a').length===5 && history.state && history.state.appNav===true; }""", rid)
        c['detail_nav_stays_reachable_when_scrolled'] = page.evaluate("""async()=>{
            const d=document.getElementById('section-post'); d.open=true; scrollTo(0,d.getBoundingClientRect().top+scrollY-60);
            await new Promise(s=>setTimeout(s,200));
            const n=document.querySelector('#detail .qn-back').getBoundingClientRect();
            const hit=document.elementFromPoint(n.left+n.width/2,n.top+n.height/2);
            return n.top>=0 && n.bottom<innerHeight/3 && !!(hit&&hit.closest('.qn-back')); }""")
        page.go_back()
        page.wait_for_timeout(600)
        c['browser_back_returns_to_list_at_same_place'] = page.evaluate("""(y)=>location.hash==='' && state.selectedId===null
            && !!document.querySelector('.cal-results') && state.searchQuery==='大阪' && Math.abs(scrollY-y)<=2
            && getComputedStyle(document.getElementById('calendar')).display!=='none'""", y_list)
        page.go_forward()
        page.wait_for_timeout(600)
        c['browser_forward_reopens_race'] = page.evaluate("(id)=>state.selectedId===id && scrollY===0", rid)
        page.reload()
        page.wait_for_function("()=>typeof state!=='undefined' && state.races.length>0 && document.body.classList.contains('viewing-detail')===!!(state.selectedId||state.creating)", timeout=30000)
        page.wait_for_timeout(300)
        page.add_style_tag(content='.badge-unbox-overlay,.foreground-toast{display:none!important}')
        c['reload_reopens_same_race'] = page.evaluate("""(id)=>state.selectedId===id && !!currentRace
            && getComputedStyle(document.getElementById('calendar')).display==='none'""", rid)
        c['back_button_goes_to_list'] = page.evaluate("""async()=>{
            document.querySelector('#detail .qn-back').click(); await new Promise(s=>setTimeout(s,500));
            return state.selectedId===null && location.hash==='' && getComputedStyle(document.getElementById('calendar')).display!=='none'; }""")
        c['drawer_back_closes_drawer_then_leaves'] = page.evaluate("""async(id)=>{
            const wait=ms=>new Promise(s=>setTimeout(s,ms));
            selectRace(id); await wait(300); openDrawer('basicInfo'); await wait(200);
            history.back(); await wait(400);
            const a=document.getElementById('global-drawer').hidden && state.selectedId===id && location.hash.startsWith('#race=');
            history.back(); await wait(400);
            return a && state.selectedId===null && location.hash===''; }""", rid)
        c['create_flow_routes'] = page.evaluate("""async()=>{
            const wait=ms=>new Promise(s=>setTimeout(s,ms));
            startCreate(); await wait(200); const h1=location.hash;
            const bar=!!document.querySelector('#detail .quick-nav.is-back-only .qn-back');
            document.querySelector('[data-action="cancel-create"]').click(); await wait(400); const h2=location.hash;
            startCreate(); await wait(200); document.getElementById('new-name').value='路由測試';
            document.querySelector('[data-action="confirm-create"]').click(); await wait(400);
            const id=state.selectedId, h3=location.hash;
            history.back(); await wait(400);
            return h1==='#new' && bar && h2==='' && !!id && h3==='#race='+encodeURIComponent(id)
              && location.hash==='' && !state.creating && state.selectedId===null; }""")
        c['delete_race_leaves_detail_and_url'] = page.evaluate("""async(id)=>{
            const wait=ms=>new Promise(s=>setTimeout(s,ms));
            const other=state.races.find(r=>r.id!==id&&!r.deletedAt&&r.status==='completed');
            selectRace(other.id); await wait(300);
            document.querySelector('[data-action="delete-race"]').click(); await wait(500);
            return state.selectedId===null && location.hash==='' && getComputedStyle(document.getElementById('calendar')).display!=='none'; }""", rid)
        c['simple_mode_detail_has_back_only'] = page.evaluate("""async(id)=>{
            setUiMode('simple',{silent:true}); selectRace(id); await new Promise(s=>setTimeout(s,300));
            const nav=document.querySelector('#detail .quick-nav');
            const ok=!!nav && nav.classList.contains('is-back-only') && !!nav.querySelector('.qn-back') && !nav.querySelector('a');
            setUiMode('full',{silent:true}); history.back(); await new Promise(s=>setTimeout(s,400)); return ok; }""", rid)
        # 網址指向本機還沒有的賽事（新裝置、等雲端）：先記著，資料來了再打開
        base = page.evaluate("location.href.split('#')[0]")
        page.goto(base + '#race=from-cloud')
        page.reload()   # 只改 # 的 goto 是同一份文件的跳轉；重新載入才會走到 init()
        page.wait_for_function("()=>typeof state!=='undefined' && state.races.length>0 && document.body.classList.contains('viewing-detail')===!!(state.selectedId||state.creating)", timeout=30000)
        page.wait_for_timeout(300)
        c['unknown_race_in_url_waits_for_cloud'] = page.evaluate("""async()=>{
            const waiting=pendingRouteRaceId==='from-cloud' && state.selectedId===null && location.hash==='#race=from-cloud';
            const r=Object.assign(emptyRace('雲端來的','road_running','completed','2024-05-05'),{id:'from-cloud'});
            state.races.push(r); resolvePendingRoute(); await new Promise(s=>setTimeout(s,300));
            return waiting && state.selectedId==='from-cloud' && location.hash==='#race=from-cloud' && pendingRouteRaceId===null; }""")
        # 直接開網址進來（沒有上一筆可以退）：按返回回到清單，不會離開網站
        page.goto(base + '#race=' + rid)
        page.reload()   # 只改 # 的 goto 是同一份文件的跳轉；重新載入才會走到 init()
        page.wait_for_function("()=>typeof state!=='undefined' && state.races.length>0 && document.body.classList.contains('viewing-detail')===!!(state.selectedId||state.creating)", timeout=30000)
        page.wait_for_timeout(300)
        page.add_style_tag(content='.badge-unbox-overlay,.foreground-toast{display:none!important}')
        opened = page.evaluate("(id)=>state.selectedId===id && !(history.state&&history.state.appNav)", rid)
        page.click('#detail .qn-back')
        page.wait_for_timeout(600)
        c['direct_url_back_button_stays_in_app'] = opened and page.evaluate("""()=>typeof state!=='undefined' && state.selectedId===null
            && location.hash==='' && getComputedStyle(document.getElementById('calendar')).display!=='none'""")
        # 選著的賽事被移除（同步刪掉、清空資料）：回到清單，網址也清掉
        c['stale_selection_returns_to_list'] = page.evaluate("""async(id)=>{
            selectRace(id); await new Promise(s=>setTimeout(s,300));
            state.races=state.races.filter(r=>r.id!==id); renderAll(); await new Promise(s=>setTimeout(s,400));
            return state.selectedId===null && !location.hash.includes(encodeURIComponent(id))
              && getComputedStyle(document.getElementById('calendar')).display!=='none'; }""", rid)
        # 手機：頂列捲下去會收合，返回清單時不能因此差了一截（v3.99.0 實測差 38px）
        pctx = full_mode_context(page.context.browser, viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True)
        pp = pctx.new_page()
        pp.goto(APP_URL)
        pp.wait_for_timeout(900)
        pp.add_script_tag(content=UX_SEED_JS)
        pp.add_style_tag(content='.badge-unbox-overlay,.foreground-toast{display:none!important}')
        pp.evaluate('__seed107()')
        pp.wait_for_timeout(300)
        pp.fill('#search-input', '大阪')
        pp.wait_for_timeout(400)
        pp.evaluate("()=>{ const e=document.querySelectorAll('.cal-results .cal-list-item')[4]; scrollTo(0,e.getBoundingClientRect().top+scrollY-420); }")
        pp.wait_for_timeout(500)
        before = pp.evaluate("()=>Math.round(document.querySelectorAll('.cal-results .cal-list-item')[4].getBoundingClientRect().top)")
        pp.evaluate("()=>document.querySelectorAll('.cal-results .cal-list-item')[4].click()")
        pp.wait_for_timeout(600)
        pp.go_back()
        pp.wait_for_timeout(800)
        after = pp.evaluate("()=>Math.round(document.querySelectorAll('.cal-results .cal-list-item')[4].getBoundingClientRect().top)")
        c['phone_back_puts_card_back_in_place'] = abs(before - after) <= 2
        pctx.close()


# v4.0：在 107 場之外補三場還沒比的、一場沒日期的（日期相對今天，每天跑都成立）
V4_EXTRA_JS = """async()=>{ await __seed107();
    const up=(n,st,d)=>{ const r=emptyRace(n,'road_running',st,addDaysStr(todayISO(),d)); r.route.distanceKm=42.195; r.location.city='台北市'; return r; };
    state.races.push(up('近的比賽','registered',9),up('遠的比賽','considering',120),up('抽籤的比賽','lottery_pending',45));
    state.races.push(emptyRace('沒日期的比賽','trail_running','considering',''));
    await persist(); renderAll(); window.scrollTo(0,0); }"""


class V4Layout(Group):
    """v4.0 版面：頂列只剩三樣、頭像選單（顯示／資料／說明）、首頁分頁（賽事／生涯數據／訓練）、
    手機預設清單、右下角只剩「＋」、賽事頁頁首精簡、第一次打開的歡迎卡、頁尾版本號。"""

    def body(self, page):
        c = self.checks
        page.add_script_tag(content=UX_SEED_JS)
        page.add_style_tag(content='.badge-unbox-overlay,.foreground-toast{display:none!important}')
        # ================= 第一次打開：還沒有任何賽事 =================
        c['first_run_shows_welcome_card'] = page.evaluate("""()=>{
            const card=document.querySelector('#calendar .welcome-card');
            const hidden=s=>getComputedStyle(document.querySelector(s)).display==='none';
            return state.races.length===0 && !!card && card.querySelectorAll('button').length===3
              && !!card.querySelector('.welcome-main[data-action="start-create"]')
              && !!card.querySelector('[data-action="welcome-import"]') && !!card.querySelector('[data-action="welcome-sample"]')
              && hidden('.topbar-row2') && document.getElementById('detail').children.length===0
              && !card.querySelector('.welcome-hint'); }""")   # 沒設定雲端同步：不提登入
        c['first_run_sign_in_hint_only_when_signed_out'] = page.evaluate("""()=>{
            const real=window.cloudEnabled; window.cloudEnabled=()=>true; state.user=null; renderCalendar();
            const a=!!document.querySelector('.welcome-card .welcome-hint');
            state.user={uid:'u',displayName:'Aaron'}; renderCalendar();
            const b=!document.querySelector('.welcome-card .welcome-hint');
            window.cloudEnabled=real; state.user=null; renderCalendar(); return a && b; }""")
        c['first_run_glow_only_on_welcome_button'] = page.evaluate("""()=>{
            try{ localStorage.removeItem(FIRST_USE_GLOW_KEY); }catch(e){}
            renderCalendar();
            return document.querySelector('.welcome-main').classList.contains('cta-glow')
              && !document.getElementById('btn-new').classList.contains('cta-glow'); }""")
        c['welcome_new_button_opens_create_form'] = page.evaluate("""async()=>{
            document.querySelector('.welcome-card .welcome-main').click(); await new Promise(s=>setTimeout(s,300));
            const ok=state.creating && !!document.querySelector('#detail .create-form') && location.hash==='#new';
            document.querySelector('[data-action="cancel-create"]').click(); await new Promise(s=>setTimeout(s,400));
            return ok && !state.creating && !!document.querySelector('.welcome-card'); }""")
        c['welcome_import_button_opens_file_picker'] = page.evaluate("""()=>{
            const inp=document.getElementById('import-file-input'); let clicked=false; const real=inp.click;
            inp.click=()=>{ clicked=true; };
            document.querySelector('[data-action="welcome-import"]').click(); inp.click=real; return clicked; }""")
        # 「先看範例資料」：載入範例、直接打開第一場（看得到一場完整的紀錄長什麼樣子）；
        # 返回首頁後歡迎卡就不見了，清掉範例又回來
        c['welcome_sample_loads_samples_then_card_goes_away'] = page.evaluate("""async()=>{
            document.querySelector('[data-action="welcome-sample"]').click(); await new Promise(s=>setTimeout(s,500));
            const loaded=state.races.filter(r=>EXAMPLE_RACE_IDS.includes(r.id)).length===5 && EXAMPLE_RACE_IDS.includes(state.selectedId);
            document.querySelector('#detail .qn-back').click(); await new Promise(s=>setTimeout(s,500));
            const gone=!state.selectedId && !document.querySelector('.welcome-card')
              && getComputedStyle(document.querySelector('.topbar-row2')).display!=='none' && !document.body.classList.contains('is-first-run');
            document.getElementById('btn-sample-data').click(); await new Promise(s=>setTimeout(s,500));
            return loaded && gone && !!document.querySelector('.welcome-card') && document.body.classList.contains('is-first-run'); }""")
        page.evaluate(V4_EXTRA_JS)
        page.wait_for_timeout(300)
        # ================= 頂列、頁尾 =================
        c['topbar_three_controls_no_row3'] = page.evaluate("""()=>{
            const shown=[...document.querySelectorAll('.topbar-actions > *')].filter(el=>el.getBoundingClientRect().width>0);
            return shown.map(el=>el.id||el.className).join('|')==='btn-mode-toggle|btn-new|action-menu account-menu'
              && !document.querySelector('.topbar-row3') && !document.getElementById('data-mgmt-menu')
              && document.querySelector('header').getBoundingClientRect().height<100; }""")
        c['footer_version_and_copyright_last_in_main'] = page.evaluate("""()=>{
            const main=document.getElementById('main-content'), f=main.querySelector(':scope > .app-footer');
            const v=document.getElementById('app-version'), cp=document.getElementById('app-copyright');
            return !!f && main.lastElementChild===f && f.contains(v) && f.contains(cp) && v.textContent.includes(APP_VERSION)
              && cp.textContent.includes('2026') && f.getBoundingClientRect().top>document.getElementById('calendar').getBoundingClientRect().bottom; }""")
        # ================= 首頁分頁 =================
        c['races_tab_default_order_no_career_strip'] = page.evaluate("""()=>{
            const kids=[...document.getElementById('main-content').children].map(e=>e.id||e.className.split(' ')[0]);
            const cur=document.querySelector('.home-tab[aria-current="page"]');
            return !!cur && cur.dataset.homeTab==='races' && state.homeTab==='races' && document.body.dataset.homeTab==='races'
              && kids.join()==='home-tabs,focus-panel-slot,topbar-row2,calendar,detail,app-footer'
              && !!document.querySelector('#focus-panel-slot .focus-panel') && !!document.querySelector('#calendar .cal-grid')
              && !document.querySelector('#calendar .career-summary-wrap')
              && document.querySelectorAll('.home-tab[aria-current]').length===1; }""")
        c['career_tab_has_stats_and_no_calendar_tools'] = page.evaluate("""async()=>{
            document.querySelector('.home-tab[data-home-tab="career"]').click(); await new Promise(s=>setTimeout(s,300));
            const hidden=s=>getComputedStyle(document.querySelector(s)).display==='none';
            return state.homeTab==='career' && document.body.dataset.homeTab==='career'
              && document.querySelector('.home-tab[aria-current="page"]').dataset.homeTab==='career'
              && !!document.querySelector('#calendar .career-summary-wrap .honor-card') && !!document.querySelector('#calendar .trophy-cabinet-wrap')
              && !document.querySelector('#calendar .cal-grid') && hidden('.topbar-row2') && hidden('#focus-panel-slot')
              && document.querySelector('#focus-panel-slot').innerHTML===''; }""")
        c['career_hof_button_opens_review_without_press_charge'] = page.evaluate("""async()=>{
            const b=document.querySelector('.honor-card [data-action="open-hof"]'); if(!b) return false;
            b.dispatchEvent(new MouseEvent('mousedown',{bubbles:true,button:0}));
            const charging=document.querySelector('.honor-card').classList.contains('pressing');
            document.dispatchEvent(new MouseEvent('mouseup',{bubbles:true}));
            b.click(); await new Promise(s=>setTimeout(s,200));
            const open=!document.getElementById('hof-overlay').hidden;
            closeHallOfFame(); return open && !charging; }""")
        c['career_hof_button_without_marathon_pb'] = page.evaluate("""()=>{
            const keep=state.races; state.races=keep.filter(r=>!(r.route.distanceKm>42&&r.route.distanceKm<42.3)); renderCalendar();
            const ok=!document.querySelector('#calendar .honor-card') && !!document.querySelector('#calendar .career-hof-row [data-action="open-hof"]');
            state.races=keep; renderCalendar(); return ok; }""")
        c['career_tab_empty_message_under_five'] = page.evaluate("""()=>{
            const keep=state.races; state.races=keep.slice(0,3); renderCalendar();
            const e=document.querySelector('#calendar .career-empty'); const ok=!!e && e.textContent.includes('目前 3 場');
            state.races=keep; renderCalendar(); return ok && !document.querySelector('#calendar .career-empty'); }""")
        c['career_tab_survives_race_round_trip'] = page.evaluate("""async()=>{
            const r=state.races.find(x=>x.status==='completed'); selectRace(r.id); await new Promise(s=>setTimeout(s,300));
            const tabsHidden=getComputedStyle(document.querySelector('.home-tabs')).display==='none';
            document.querySelector('#detail .qn-back').click(); await new Promise(s=>setTimeout(s,500));
            return tabsHidden && state.homeTab==='career' && !!document.querySelector('#calendar .career-summary-wrap')
              && getComputedStyle(document.querySelector('.home-tabs')).display!=='none'; }""")
        c['training_tab_opens_overlay_keeps_current_tab'] = page.evaluate("""async()=>{
            document.getElementById('btn-training').click(); await new Promise(s=>setTimeout(s,200));
            const open=!document.getElementById('training-overlay').hidden; closeTrainingOverlay();
            return open && state.homeTab==='career' && !document.getElementById('btn-training').hasAttribute('aria-current'); }""")
        c['races_tab_returns_calendar'] = page.evaluate("""async()=>{
            document.querySelector('.home-tab[data-home-tab="races"]').click(); await new Promise(s=>setTimeout(s,300));
            return state.homeTab==='races' && !!document.querySelector('#calendar .cal-grid')
              && !document.querySelector('#calendar .career-summary-wrap') && !!document.querySelector('#focus-panel-slot .focus-panel'); }""")
        # ================= 頭像選單 =================
        c['avatar_menu_holds_everything_in_order'] = page.evaluate("""()=>{
            const p=document.getElementById('account-menu-panel');
            const ids=['auth-area','btn-open-profile','lang-select','menu-group-import','btn-import','btn-import-json','menu-group-export',
              'btn-export','btn-export-csv','btn-export-notebook','btn-export-ics','btn-recovery','btn-sample-data','btn-help','btn-feedback','btn-clear','auth-signout'];
            const els=ids.map(id=>document.getElementById(id));
            return els.every(e=>e&&p.contains(e)) && els.every((e,i)=>i===0||els[i-1].compareDocumentPosition(e)&Node.DOCUMENT_POSITION_FOLLOWING)
              && p.lastElementChild===document.getElementById('auth-signout')
              && document.getElementById('btn-clear').previousElementSibling.classList.contains('action-menu-divider')
              && ['menu-group-import','menu-group-export'].every(id=>{ const d=document.getElementById(id); return d.tagName==='DETAILS' && !d.open; }); }""")
        page.click('#btn-account-menu')
        page.wait_for_timeout(200)
        c['menu_font_scale_keeps_menu_open_inside_viewport'] = page.evaluate("""async()=>{
            const p=document.getElementById('account-menu-panel');
            document.querySelector('[data-font-scale="large"]').click(); await new Promise(s=>setTimeout(s,200));
            const r=p.getBoundingClientRect();
            const ok=!p.hidden && document.documentElement.getAttribute('data-font')==='large' && r.right<=innerWidth-7 && r.left>=7;
            document.querySelector('[data-font-scale="medium"]').click(); await new Promise(s=>setTimeout(s,200));
            return ok && !p.hidden; }""")
        c['menu_dark_mode_switch'] = page.evaluate("""async()=>{
            const b=document.getElementById('btn-theme-toggle'), p=document.getElementById('account-menu-panel');
            b.click(); await new Promise(s=>setTimeout(s,150));
            const on=document.documentElement.getAttribute('data-theme')==='dark' && b.getAttribute('aria-checked')==='true' && !p.hidden
              && localStorage.getItem('theme-pref-v1')==='dark';
            b.click(); await new Promise(s=>setTimeout(s,150));
            return on && document.documentElement.getAttribute('data-theme')==='light' && b.getAttribute('aria-checked')==='false' && !p.hidden; }""")
        c['menu_export_group_expands_menu_stays'] = page.evaluate("""async()=>{
            const d=document.getElementById('menu-group-export'), p=document.getElementById('account-menu-panel');
            d.querySelector('summary').click(); await new Promise(s=>setTimeout(s,150));
            const ok=d.open && !p.hidden && document.getElementById('btn-export-ics').getBoundingClientRect().height>0;
            d.querySelector('summary').click(); await new Promise(s=>setTimeout(s,150));
            return ok && !d.open && !p.hidden; }""")
        c['menu_escape_closes_and_refocuses_avatar'] = page.evaluate("""async()=>{
            document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true})); await new Promise(s=>setTimeout(s,100));
            const t=document.getElementById('btn-account-menu');
            return document.getElementById('account-menu-panel').hidden && document.activeElement===t && t.getAttribute('aria-expanded')==='false'; }""")
        c['menu_help_opens_help_and_closes_menu'] = page.evaluate("""async()=>{
            document.getElementById('btn-account-menu').click(); await new Promise(s=>setTimeout(s,150));
            document.getElementById('btn-help').click(); await new Promise(s=>setTimeout(s,200));
            const ok=!document.getElementById('help-modal').hidden && document.getElementById('account-menu-panel').hidden
              && document.querySelector('#help-modal .help-body').textContent.includes('頭像選單')
              && !document.querySelector('#help-modal .help-body').textContent.includes('左下角');
            document.querySelector('#help-modal [data-action="close-help"]').click(); return ok; }""")
        c['menu_import_item_closes_menu'] = page.evaluate("""async()=>{
            const inp=document.getElementById('import-file-input'); let clicked=false; const real=inp.click; inp.click=()=>{ clicked=true; };
            document.getElementById('btn-account-menu').click(); await new Promise(s=>setTimeout(s,150));
            document.querySelector('#menu-group-import summary').click(); await new Promise(s=>setTimeout(s,100));
            document.getElementById('btn-import').click(); await new Promise(s=>setTimeout(s,100));
            inp.click=real; document.getElementById('menu-group-import').open=false;
            return clicked && document.getElementById('account-menu-panel').hidden; }""")
        c['signed_in_header_count_and_signout_last'] = page.evaluate("""()=>{
            const real=window.cloudEnabled; window.cloudEnabled=()=>true; state.user={uid:'u1',displayName:'Aaron',email:'',photoURL:''};
            renderAuthArea();
            const n=state.races.filter(r=>!r.deletedAt).length;
            const q=s=>document.querySelector('#auth-area '+s);
            const out=document.getElementById('auth-signout');
            const a=q('.auth-user-name').textContent==='Aaron' && q('.auth-initial').textContent==='A'
              && q('.auth-user-sub').textContent.includes(n+' 場') && !out.hidden && out.lastElementChild.id==='btn-signout'
              && !q('#btn-signout') && !!q('#btn-sync-diag');
            state.races.push(emptyRace('計數用','road_running','considering','')); renderAll();
            const b=q('.auth-user-sub').textContent.includes((n+1)+' 場');
            state.races.pop(); state.user=null; window.cloudEnabled=real; renderAuthArea(); renderAll();
            return a && b && document.getElementById('auth-signout').hidden && !document.getElementById('btn-signout'); }""")
        c['v4_strings_translated'] = page.evaluate("""()=>{
            const read=()=>[document.querySelector('.home-tab[data-home-tab="races"]').textContent,
              document.querySelector('.home-tab[data-home-tab="career"]').textContent,
              document.querySelector('[data-i18n="ui.menuDisplay"]').textContent,
              document.querySelector('.view-seg [data-phone-view="list"]').textContent,
              document.querySelector('[data-i18n="ui.menuExport"]').textContent];
            setLang('ja'); const ja=read(); const selJa=document.getElementById('lang-select').value;
            setLang('en'); const en=read(); setLang('zh'); const zh=read();
            return selJa==='ja' && document.getElementById('lang-select').value==='zh'
              && ja.slice(0,4).join('|')==='大会|キャリア|表示|リスト' && en.slice(0,4).join('|')==='Races|Career|Display|List'
              && zh.join('|')==='賽事|生涯數據|顯示|清單|匯出與備份（JSON／CSV／行事曆）'
              && document.querySelector('.home-tabs').getAttribute('aria-label')==='首頁'; }""")
        # ================= 賽事頁頁首 =================
        c['completed_header_compact'] = page.evaluate("""async()=>{
            const r=state.races.find(x=>x.status==='completed'&&x.location.city); selectRace(r.id); await new Promise(s=>setTimeout(s,300));
            const h=document.querySelector('#detail .detail-header');
            const btn=h.querySelector('.dh-status-btn');
            return !h.querySelector('.lifecycle-stepper') && !h.querySelector('.cover-upload') && !h.querySelector('.dh-gcal-quicklink')
              && h.querySelector('.dh-meta').textContent.trim()===r.schedule.raceDate+' ・ '+r.location.city
              && btn.getAttribute('aria-haspopup')==='true' && btn.textContent.trim()===statusLabel('completed'); }""")
        c['status_menu_six_states_current_checked_left_aligned'] = page.evaluate("""async()=>{
            document.querySelector('.dh-status-btn').click(); await new Promise(s=>setTimeout(s,150));
            const p=document.getElementById('dh-status-menu'); const items=[...p.querySelectorAll('[data-action="lc-set-status"]')];
            const checked=items.filter(i=>i.getAttribute('aria-checked')==='true').map(i=>i.dataset.status);
            const b=document.querySelector('.dh-status-btn').getBoundingClientRect(), pr=p.getBoundingClientRect();
            return !p.hidden && items.map(i=>i.dataset.status).join()==='considering,lottery_pending,registered,completed,dns,dnf'
              && checked.join()==='completed' && Math.abs(pr.left-Math.max(8,b.left))<2 && pr.top>=b.bottom; }""")
        c['status_menu_marks_dnf'] = page.evaluate("""async()=>{
            const id=state.selectedId;
            document.querySelector('#dh-status-menu [data-status="dnf"]').click(); await new Promise(s=>setTimeout(s,500));
            const r=state.races.find(x=>x.id===id);
            const ok=r.status==='dnf' && document.getElementById('dh-status-menu').hidden
              && document.querySelector('.dh-status-btn').classList.contains('status-dnf') && !document.querySelector('#detail .lifecycle-stepper');
            r.status='completed'; renderAll(); return ok; }""")
        c['upcoming_header_keeps_stepper_without_dns_row'] = page.evaluate("""async()=>{
            const r=state.races.find(x=>x.name==='近的比賽'); selectRace(r.id); await new Promise(s=>setTimeout(s,300));
            const h=document.querySelector('#detail .detail-header');
            return !!h.querySelector('.lifecycle-stepper') && !h.querySelector('.lc-exception-row') && !!h.querySelector('.progress-block')
              && h.querySelector('.dh-meta').textContent.trim()===r.schedule.raceDate+' ・ 台北市'; }""")
        c['cover_actions_in_more_menu'] = page.evaluate("""()=>{
            const m=()=>document.getElementById('dh-more-menu');
            const noCover=!!m().querySelector('[data-action="open-cover-picker"]') && !m().querySelector('[data-action="remove-cover"]');
            currentRace.coverImage='data:image/gif;base64,R0lGODlhAQABAAAAACw='; renderDetail();
            const withCover=['open-cover-picker','open-focal-point','remove-cover'].every(a=>!!m().querySelector('[data-action="'+a+'"]'))
              && !document.querySelector('#detail .detail-header .cover-upload');
            currentRace.coverImage=''; renderDetail(); return noCover && withCover; }""")
        page.evaluate("()=>{ document.querySelector('#detail .qn-back').click(); }")
        page.wait_for_timeout(400)

        # ================= 手機 =================
        pctx = full_mode_context(page.context.browser, viewport=PHONE, is_mobile=True, has_touch=True)
        pp = pctx.new_page()
        pp.on('pageerror', lambda e: self.errors.append(str(e)))
        pp.goto(APP_URL)
        pp.wait_for_timeout(900)
        pp.add_script_tag(content=UX_SEED_JS)
        pp.add_style_tag(content='.badge-unbox-overlay,.foreground-toast{display:none!important}')
        pp.evaluate(V4_EXTRA_JS)
        pp.wait_for_timeout(300)
        c['phone_topbar_one_row'] = pp.evaluate("""()=>{
            const r=q=>document.querySelector(q).getBoundingClientRect();
            const t=r('.app-title'), sw=r('#btn-mode-toggle'), av=r('#btn-account-menu');
            return sw.top<t.bottom && av.top<t.bottom && sw.right<=av.left && innerWidth-av.right<=24
              && r('#topbar').height<90 && getComputedStyle(document.getElementById('btn-new')).display==='none'
              && document.documentElement.scrollWidth<=innerWidth; }""")
        c['phone_default_list_view'] = pp.evaluate("""()=>{
            const seg=document.querySelector('.view-seg');
            const pressed=[...seg.querySelectorAll('[aria-pressed="true"]')].map(b=>b.dataset.phoneView);
            const hidden=s=>getComputedStyle(document.querySelector(s)).display==='none';
            const groups=[...document.querySelectorAll('#calendar .cal-phone-list > .cal-results-group')]
              .map(g=>g.querySelector('.cal-results-group-title').childNodes[0].textContent.trim());
            return getComputedStyle(seg).display!=='none' && pressed.join()==='list' && state.phoneView==='list'
              && hidden('.cal-month-nav') && hidden('.cal-tools')
              && groups.join()==='即將到來,最近的賽事' && !document.querySelector('#calendar .cal-grid'); }""")
        c['phone_list_upcoming_ascending_recent_five'] = pp.evaluate("""()=>{
            const gs=[...document.querySelectorAll('#calendar .cal-phone-list > .cal-results-group')];
            const dates=g=>[...g.querySelectorAll('.cal-list-item')].map(b=>state.races.find(r=>r.id===b.dataset.id).schedule.raceDate);
            const up=dates(gs[0]), recent=dates(gs[1]), today=todayISO();
            const past=state.races.filter(r=>!r.deletedAt&&r.schedule.raceDate&&r.schedule.raceDate<today).map(r=>r.schedule.raceDate).sort().reverse();
            const dated=up.slice(0,3), rowDates=[...gs[0].querySelectorAll('.cal-results-date')].map(x=>x.textContent);
            return up.length===4 && dated.every((d,i)=>d>=today&&(i===0||d>=dated[i-1])) && up[3]===''
              && rowDates[3]==='日期未定' && gs[0].lastElementChild.textContent.includes('沒日期的比賽')
              && recent.length===5 && recent.join()===past.slice(0,5).join(); }""")
        c['phone_focus_panel_kept_above_list'] = pp.evaluate("""()=>{
            const fp=document.querySelector('#focus-panel-slot .focus-panel'), seg=document.querySelector('.view-seg');
            return !!fp && fp.getBoundingClientRect().bottom<=seg.getBoundingClientRect().top
              && document.querySelector('.home-tabs').getBoundingClientRect().bottom<=fp.getBoundingClientRect().top; }""")
        c['phone_see_all_matches_history_chip'] = pp.evaluate("""async()=>{
            const btn=document.querySelector('[data-action="list-see-all-history"]');
            const chip=[...document.querySelectorAll('#filter-chips .chip')].find(b=>b.dataset.status==='history');
            const n=Number((chip.textContent.match(/\\((\\d+)\\)/)||[])[1]);
            const label=btn.textContent.includes(String(n));
            btn.click(); await new Promise(s=>setTimeout(s,300));
            const ok=label && state.filterStatus==='history' && document.querySelectorAll('.cal-results .cal-list-item').length===n;
            document.querySelector('[data-action="clear-cal-results"]').click(); await new Promise(s=>setTimeout(s,200));
            return ok && !!document.querySelector('#calendar .cal-phone-list'); }""")
        c['phone_list_row_opens_race_and_back_keeps_list'] = pp.evaluate("""async()=>{
            document.querySelector('#calendar .cal-phone-list .cal-list-item').click(); await new Promise(s=>setTimeout(s,400));
            const opened=!!state.selectedId;
            document.querySelector('#detail .qn-back').click(); await new Promise(s=>setTimeout(s,500));
            return opened && !state.selectedId && state.phoneView==='list' && !!document.querySelector('#calendar .cal-phone-list'); }""")
        c['phone_calendar_segment_has_month_nav'] = pp.evaluate("""async()=>{
            document.querySelector('.view-seg [data-phone-view="calendar"]').click(); await new Promise(s=>setTimeout(s,200));
            return state.phoneView==='calendar' && getComputedStyle(document.querySelector('.cal-month-nav')).display!=='none'
              && !!document.querySelector('#calendar .cal-list') && !document.querySelector('#calendar .cal-phone-list')
              && document.querySelector('.view-seg [aria-pressed="true"]').dataset.phoneView==='calendar'
              && document.documentElement.scrollWidth<=innerWidth; }""")
        c['phone_grid_segment_is_photo_wall'] = pp.evaluate("""async()=>{
            document.querySelector('.view-seg [data-phone-view="grid"]').click(); await new Promise(s=>setTimeout(s,200));
            const ok=state.phoneView==='grid' && !!document.querySelector('#calendar .photo-grid-wrap')
              && getComputedStyle(document.querySelector('.cal-month-nav')).display==='none' && state.viewMode==='calendar';
            document.querySelector('.view-seg [data-phone-view="list"]').click(); await new Promise(s=>setTimeout(s,200));
            return ok && !!document.querySelector('#calendar .cal-phone-list'); }""")
        c['phone_nav_swipe_ignored_outside_calendar'] = pp.evaluate("""()=>{
            const nav=document.querySelector('.cal-nav'), m0=state.calendarMonth;
            const mk=(type,x)=>{ const t=new Touch({identifier:1,target:nav,clientX:x,clientY:200});
              return new TouchEvent(type,{bubbles:true,cancelable:true,touches:type==='touchend'?[]:[t],changedTouches:[t]}); };
            nav.dispatchEvent(mk('touchstart',300)); nav.dispatchEvent(mk('touchmove',200)); nav.dispatchEvent(mk('touchend',120));
            return state.calendarMonth===m0 && !!document.querySelector('#calendar .cal-phone-list'); }""")
        pp.set_viewport_size({'width': 1100, 'height': 844})
        pp.wait_for_timeout(300)
        c['crossing_640_switches_to_desktop_views'] = pp.evaluate("""()=>!!document.querySelector('#calendar .cal-grid')
            && !document.querySelector('#calendar .cal-phone-list') && getComputedStyle(document.querySelector('.view-seg')).display==='none'
            && getComputedStyle(document.querySelector('.cal-tools')).display!=='none'""")
        pp.set_viewport_size(PHONE)
        pp.wait_for_timeout(300)
        c['crossing_back_to_phone_list'] = pp.evaluate("()=>!!document.querySelector('#calendar .cal-phone-list')")
        c['phone_only_plus_fab'] = pp.evaluate("""()=>{
            const nw=document.getElementById('btn-new-fab').getBoundingClientRect();
            return nw.width===52 && Math.round(innerWidth-nw.right)===16 && Math.round(innerHeight-nw.bottom)===16
              && !document.querySelector('.help-fab,.feedback-fab,#help-fab-caption,#feedback-fab-caption'); }""")
        pp.set_viewport_size({'width': 390, 'height': 600})
        pp.wait_for_timeout(200)
        pp.click('#btn-account-menu')
        pp.wait_for_timeout(200)
        pp.click('#menu-group-export > summary')
        pp.wait_for_timeout(250)
        c['phone_menu_wide_scrolls_and_sits_above_fab'] = pp.evaluate("""()=>{
            const p=document.getElementById('account-menu-panel'), r=p.getBoundingClientRect();
            const fab=document.getElementById('btn-new-fab').getBoundingClientRect();
            const hit=document.elementFromPoint(fab.left+fab.width/2,fab.top+fab.height/2);
            return !p.hidden && r.width>=innerWidth-25 && r.bottom<=innerHeight-7 && p.scrollHeight>p.clientHeight
              && !!(hit&&hit.closest('#account-menu-panel')); }""")
        c['phone_menu_scroll_kept_when_group_toggles'] = pp.evaluate("""async()=>{
            const p=document.getElementById('account-menu-panel'); p.scrollTop=p.scrollHeight;
            await new Promise(s=>setTimeout(s,50)); const before=p.scrollTop;
            document.querySelector('#menu-group-import > summary').click(); await new Promise(s=>setTimeout(s,200));
            return before>0 && p.scrollTop>0 && !p.hidden; }""")
        pp.keyboard.press('Escape')
        pp.set_viewport_size(PHONE)
        pp.wait_for_timeout(200)
        c['phone_completed_header_short'] = pp.evaluate("""async()=>{
            const r=state.races.find(x=>x.status==='completed'&&x.location.city); selectRace(r.id); await new Promise(s=>setTimeout(s,400));
            const h=document.querySelector('#detail .detail-header').getBoundingClientRect();
            return h.height<200 && !!document.querySelector('#detail .hero-results'); }""")
        pctx.close()
        # 新裝置（沒有任何資料、沒有預設完整版）：簡易版的歡迎卡，沒有「訓練」分頁
        sctx = page.context.browser.new_context(viewport=PHONE, is_mobile=True, has_touch=True)
        sp = sctx.new_page()
        sp.on('pageerror', lambda e: self.errors.append(str(e)))
        sp.goto(APP_URL)
        sp.wait_for_timeout(900)
        c['new_device_simple_welcome_without_training_tab'] = sp.evaluate("""()=>document.documentElement.getAttribute('data-mode')==='simple'
            && !!document.querySelector('#calendar .welcome-card') && getComputedStyle(document.getElementById('btn-training')).display==='none'
            && [...document.querySelectorAll('.home-tab')].filter(b=>getComputedStyle(b).display!=='none').length===2
            && getComputedStyle(document.querySelector('.topbar-row2')).display==='none'""")
        sctx.close()



# v4.1：對比計算（沿著父層把半透明底色疊上去，算出文字實際落在什麼顏色上）
CONTRAST_JS = r"""window.__contrast=function(el){
  const rgba=c=>{ const m=(c.match(/[\d.]+/g)||[]).map(Number); return [m[0]||0,m[1]||0,m[2]||0,m.length>3?m[3]:1]; };
  const layers=[]; let e=el;
  while(e&&e.nodeType===1){ const b=rgba(getComputedStyle(e).backgroundColor); if(b[3]>0) layers.push(b); if(b[3]>=1) break; e=e.parentElement; }
  let bg=[255,255,255];
  for(let i=layers.length-1;i>=0;i--){ const [r,g,b,a]=layers[i]; bg=[r*a+bg[0]*(1-a),g*a+bg[1]*(1-a),b*a+bg[2]*(1-a)]; }
  const fg=rgba(getComputedStyle(el).color);
  const lum=c=>{ const v=c.slice(0,3).map(x=>{ x/=255; return x<=0.03928?x/12.92:Math.pow((x+0.055)/1.055,2.4); }); return 0.2126*v[0]+0.7152*v[1]+0.0722*v[2]; };
  const a=lum(fg),b=lum(bg); return (Math.max(a,b)+0.05)/(Math.min(a,b)+0.05);
};
// 點擊範圍：在元素中心上下各 dy 的地方點下去，打到的還是不是它
window.__hitsAt=function(el,dx,dy){
  const r=el.getBoundingClientRect(); const x=r.left+r.width/2+dx, y=r.top+r.height/2+dy;
  const hit=document.elementFromPoint(x,y); return !!hit&&(hit===el||el.contains(hit));
};"""


class V41Fixes(Group):
    """v4.1.0 修正：返回鍵關最上面那一層、生涯數據分頁網址、篩選數字一致、表格／獎牌牆
    不顯示月份箭頭、次要文字與小字金色對比、圖表字、點擊範圍、重複資訊、範例資料日期。"""

    def body(self, page):
        c = self.checks
        page.add_script_tag(content=UX_SEED_JS)
        page.add_script_tag(content=CONTRAST_JS)
        page.add_style_tag(content='.badge-unbox-overlay,.foreground-toast{display:none!important}')
        page.evaluate(V4_EXTRA_JS)
        page.wait_for_timeout(400)
        wait = "const wait=ms=>new Promise(s=>setTimeout(s,ms));"
        # ================= 返回鍵 =================
        # 每一種疊在上面的層：打開 → 按返回 → 只關掉它，人還在原本的畫面
        c['back_closes_each_overlay_and_stays'] = page.evaluate("""async()=>{ """ + wait + """
            const done=state.races.find(r=>r.status==='completed'&&r.results.chipTimeSeconds!=null);
            done.results.isPb=true; selectRace(done.id); await wait(400);
            const hash=location.hash, out=[];
            const vis=id=>{ const el=document.getElementById(id); return !!el&&!el.hidden&&el.getClientRects().length>0; };
            const cases=[
              ['training-overlay',()=>openTrainingOverlay()],
              ['help-modal',()=>openHelpModal()],
              ['share-modal',()=>openShareModal(done)],
              ['profile-modal',()=>openProfileModal()],
              ['hof-overlay',()=>openHallOfFame()],
              ['recovery-modal',()=>openRecoveryModal()],
              ['account-menu-panel',()=>document.getElementById('btn-account-menu').click()],
              ['dh-more-menu',()=>document.querySelector('[data-menu-trigger="dh-more-menu"]').click()],
              ['global-drawer',()=>openDrawer('basicInfo')],
            ];
            for(const [id,open] of cases){
              open(); await wait(250); const opened=vis(id);
              history.back(); await wait(450);
              out.push(opened && !vis(id) && location.hash===hash && state.selectedId===done.id ? 'ok' : id);
            }
            return out.every(x=>x==='ok') || out.join(); }""") is True
        # 用 ✕ 關掉之後，返回鍵按一次就回到清單（不會有一次「按了沒反應」）
        c['closed_by_x_then_one_back_leaves_race'] = page.evaluate("""async()=>{ """ + wait + """
            const id=state.selectedId; openHelpModal(); await wait(250);
            document.querySelector('#help-modal [data-action^="close"]').click(); await wait(250);
            const closed=document.getElementById('help-modal').hidden;
            history.back(); await wait(500);
            return closed && state.selectedId===null && location.hash===''; }""")
        # 賽事頁上選單用 Esc 關掉、再按頁面上的「返回」：一次就回清單
        c['page_back_button_after_closed_menu'] = page.evaluate("""async()=>{ """ + wait + """
            const r=state.races.find(x=>x.status==='completed'); selectRace(r.id); await wait(400);
            document.querySelector('.dh-status-btn').click(); await wait(200);
            document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape'})); await wait(200);
            const menuClosed=document.getElementById('dh-status-menu').hidden;
            // 一次就跳回清單：中間不會先停在「防護」那一筆（換兩次畫面、捲動位置跳兩次）
            let pops=0; const count=()=>{ pops++; }; window.addEventListener('popstate',count);
            document.querySelector('#detail .qn-back').click(); await wait(500);
            window.removeEventListener('popstate',count);
            return menuClosed && pops===1 && state.selectedId===null && location.hash==='' && !history.state.backGuard; }""")
        # 從頭像選單點「使用說明」：選單換成說明，返回只關說明
        c['menu_to_help_back_closes_help_only'] = page.evaluate("""async()=>{ """ + wait + """
            document.getElementById('btn-account-menu').click(); await wait(200);
            document.getElementById('btn-help').click(); await wait(300);
            const a=!document.getElementById('help-modal').hidden && document.getElementById('account-menu-panel').hidden;
            history.back(); await wait(450);
            return a && document.getElementById('help-modal').hidden && location.hash==='' && state.selectedId===null; }""")
        # 兩層疊在一起（生涯回顧上面開「下載生涯回顧圖」）：返回一次關一層
        c['stacked_layers_close_one_per_back'] = page.evaluate("""async()=>{ """ + wait + """
            openHallOfFame(); await wait(250); openCareerShareModal(); await wait(300);
            const vis=id=>{ const el=document.getElementById(id); return !el.hidden&&el.getClientRects().length>0; };
            const both=vis('hof-overlay')&&vis('career-share-modal');
            history.back(); await wait(450); const one=vis('hof-overlay')&&!vis('career-share-modal');
            history.back(); await wait(450); const none=!vis('hof-overlay')&&!vis('career-share-modal');
            return both && one && none && location.hash===''; }""")
        # 只改 # 的跳轉（手動改網址）不是返回，開著的層不會被關掉
        c['hash_jump_is_not_back'] = page.evaluate("""async()=>{ """ + wait + """
            openHelpModal(); await wait(250); location.hash='#not-a-route'; await wait(300);
            const still=!document.getElementById('help-modal').hidden;
            const x=document.querySelector('#help-modal [data-action^="close"]'); if(x) x.click(); await wait(200);
            history.replaceState({},'',location.pathname+location.search); return still; }""")
        # ================= 生涯數據分頁的網址 =================
        c['career_tab_has_url_and_back_returns_to_races'] = page.evaluate("""async()=>{ """ + wait + """
            document.querySelector('.home-tab[data-home-tab="career"]').click(); await wait(300);
            const a=location.hash==='#career' && state.homeTab==='career' && !!document.querySelector('#calendar .career-summary-wrap');
            history.back(); await wait(450);
            return a && location.hash==='' && state.homeTab==='races' && !document.querySelector('#calendar .career-summary-wrap'); }""")
        # 點「賽事」分頁切回來＝退回原本那一筆（不是再推一筆）：返回鍵不會在兩個分頁之間來回
        c['races_tab_click_goes_back_not_forward'] = page.evaluate("""async()=>{ """ + wait + """
            history.replaceState(Object.assign({},history.state,{testMark:'home'}),'');
            document.querySelector('.home-tab[data-home-tab="career"]').click(); await wait(300);
            const onCareer=history.state.testMark!=='home';
            document.querySelector('.home-tab[data-home-tab="races"]').click(); await wait(450);
            return onCareer && history.state.testMark==='home' && location.hash==='' && state.homeTab==='races'; }""")
        c['race_from_career_returns_to_career'] = page.evaluate("""async()=>{ """ + wait + """
            document.querySelector('.home-tab[data-home-tab="career"]').click(); await wait(300);
            const r=state.races.find(x=>x.status==='completed'); selectRace(r.id); await wait(400);
            document.querySelector('#detail .qn-back').click(); await wait(500);
            const ok=state.selectedId===null && location.hash==='#career' && state.homeTab==='career'
              && !!document.querySelector('#calendar .career-summary-wrap');
            document.querySelector('.home-tab[data-home-tab="races"]').click(); await wait(450); return ok; }""")
        # 重新整理留在生涯數據：用本機 http 開（headless Chromium 在 file:// 下重新整理，
        # 偶爾會把整個 localStorage 弄丟——v4.0 一樣會，跟這裡要測的事無關；http 下 8/8 穩定）
        import http.server, socketserver, threading, functools
        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *a, **k):
                pass
        socketserver.TCPServer.allow_reuse_address = True
        srv = socketserver.TCPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=os.path.dirname(os.path.abspath(APP))))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        rctx = full_mode_context(page.context.browser, viewport=DESKTOP)
        rp = rctx.new_page()
        rp.on('pageerror', lambda e: self.errors.append(str(e)))
        rp.goto(f'http://127.0.0.1:{srv.server_address[1]}/' + os.path.basename(APP))
        rp.wait_for_timeout(900)
        rp.add_style_tag(content='.badge-unbox-overlay,.foreground-toast{display:none!important}')
        rp.evaluate("""async()=>{ for(let i=0;i<6;i++){ const r=emptyRace('重整測試 '+i,'road_running','completed','2024-0'+(i+1)+'-10');
            r.route.distanceKm=42.195; r.results.chipTimeSeconds=12600+i*60; state.races.push(r); }
            await persist(); renderAll(); document.querySelector('.home-tab[data-home-tab="career"]').click(); }""")
        rp.wait_for_timeout(800)
        rp.reload()
        rp.wait_for_function("()=>typeof state!=='undefined' && state.races.length>0", timeout=30000)
        rp.wait_for_timeout(500)
        c['reload_stays_on_career_tab'] = rp.evaluate("""()=>location.hash==='#career' && state.homeTab==='career'
            && document.querySelector('.home-tab[aria-current="page"]').dataset.homeTab==='career' && !!document.querySelector('#calendar .career-summary-wrap')""")
        rctx.close()
        srv.shutdown()
        # ================= 表格／獎牌牆不顯示月份箭頭 =================
        c['month_arrows_only_in_month_view'] = page.evaluate("""async()=>{ """ + wait + """
            const shown=()=>{ const n=document.querySelector('.cal-month-nav'); return getComputedStyle(n).display!=='none' && n.getBoundingClientRect().width>0; };
            const cal=shown();
            document.getElementById('cal-table-toggle').click(); await wait(300); const table=shown();
            document.getElementById('cal-table-toggle').click(); await wait(200);
            document.getElementById('cal-view-toggle').click(); await wait(300); const grid=shown();
            document.getElementById('cal-view-toggle').click(); await wait(300);
            return cal && !table && !grid && shown(); }""")
        # ================= 對比 =================
        c['secondary_text_meets_aa_light_and_dark'] = page.evaluate("""async()=>{ """ + wait + """
            const check=()=>{
              const els=[document.querySelector('.home-tab:not([aria-current])'), document.querySelector('.app-tagline'), document.getElementById('app-version')];
              return els.every(e=>e&&__contrast(e)>=4.5); };
            // 切主題有 0.8 秒的底色過場：量的時候先關掉過場，量的是最後的顏色
            const st=document.createElement('style'); st.textContent='*{transition:none!important}'; document.head.appendChild(st);
            const light=check(); applyTheme('dark'); await wait(150); const dark=check(); applyTheme('light'); await wait(150); st.remove();
            return light && dark; }""")
        c['pb_badge_and_focus_label_meet_aa'] = page.evaluate("""async()=>{ """ + wait + """
            const r=state.races.find(x=>x.status==='completed'&&x.results.chipTimeSeconds!=null); r.results.isPb=true; selectRace(r.id); await wait(400);
            const pb=document.querySelector('#detail .pb-badge'); const a=!!pb && __contrast(pb)>=4.5;
            goBackFromDetail(); await wait(400);
            const lab=document.querySelector('.focus-panel-label'); return a && !!lab && __contrast(lab)>=4.5; }""")
        # ================= 重複資訊 =================
        c['header_date_once_pb_once'] = page.evaluate("""async()=>{ """ + wait + """
            const up=state.races.find(x=>x.name==='近的比賽'); selectRace(up.id); await wait(400);
            const h=document.querySelector('#detail .detail-header').innerText;
            const once=(h.split(up.schedule.raceDate).length-1)===1;
            const done=state.races.find(x=>x.status==='completed'&&x.results.isPb&&x.results.chipTimeSeconds!=null); selectRace(done.id); await wait(400);
            const pbs=document.querySelectorAll('#detail .pb-badge').length;
            goBackFromDetail(); await wait(400); return once && pbs===1; }""")
        # ================= 範例資料的日期跟著今天走 =================
        # （版本號的檢查跟著最新的群組走，v4.2.0 起在 v42）
        c['sample_dates_follow_today'] = page.evaluate("""()=>{
            const ex=buildExampleRaces(), today=todayISO();
            const by=id=>ex.find(r=>r.id===id);
            const gap=(a,b)=>Math.round((new Date(b+'T00:00:00')-new Date(a+'T00:00:00'))/86400000);
            const a=by('example-alishan-trail'), t=by('example-taroko-marathon'), m=by('example-taipei-marathon');
            return a.schedule.raceDate===addDaysStr(today,10) && ex.every(r=>r.schedule.raceDate>=today)
              && gap(a.schedule.raceDate,t.schedule.raceDate)===42 && gap(a.schedule.raceDate,m.schedule.raceDate)===84
              && ex.every(r=>r.name.includes(r.schedule.raceDate.slice(0,4)))
              && m.accommodations[0].checkIn===addDaysStr(m.schedule.raceDate,-1)
              && t.schedule.lotteryResultDate<t.schedule.raceDate; }""")
        # ================= 手機 =================
        pctx = full_mode_context(page.context.browser, viewport=PHONE, is_mobile=True, has_touch=True)
        pp = pctx.new_page()
        pp.on('pageerror', lambda e: self.errors.append(str(e)))
        pp.goto(APP_URL)
        pp.wait_for_timeout(900)
        pp.add_script_tag(content=UX_SEED_JS)
        pp.add_script_tag(content=CONTRAST_JS)
        pp.add_style_tag(content='.badge-unbox-overlay,.foreground-toast{display:none!important}')
        pp.evaluate(V4_EXTRA_JS)
        pp.wait_for_timeout(400)
        c['phone_upcoming_chip_matches_list_group'] = pp.evaluate("""()=>{
            const chip=[...document.querySelectorAll('#filter-chips .chip')].find(b=>b.dataset.status==='upcoming');
            const n=Number((chip.textContent.match(/\\((\\d+)\\)/)||[])[1]);
            const g=document.querySelector('#calendar .cal-phone-list > .cal-results-group');
            const cnt=Number(g.querySelector('.cal-results-count').textContent);
            const rows=g.querySelectorAll('.cal-list-item').length;
            const last=g.querySelector('.cal-results-row:last-child');
            return n===4 && cnt===n && rows===n && last.textContent.includes('沒日期的比賽')
              && last.querySelector('.cal-results-date').textContent==='日期未定' && !document.querySelector('#calendar .cal-undated'); }""")
        c['phone_upcoming_filter_title_matches_group'] = pp.evaluate("""async()=>{
            [...document.querySelectorAll('#filter-chips .chip')].find(b=>b.dataset.status==='upcoming').click();
            await new Promise(s=>setTimeout(s,300));
            const n=Number(document.querySelector('.cal-results-title').textContent.match(/(\\d+) 場/)[1]);
            const g=document.querySelector('.cal-results-group'); const cnt=Number(g.querySelector('.cal-results-count').textContent);
            document.querySelector('[data-action="clear-cal-results"]').click(); await new Promise(s=>setTimeout(s,300));
            return n===4 && cnt===4; }""")
        c['phone_small_controls_have_44px_hit_area'] = pp.evaluate("""async()=>{ """ + wait + """
            const out=[];
            const h44=(el,name)=>{ if(!(el&&__hitsAt(el,0,-20)&&__hitsAt(el,0,20))) out.push(name); };
            h44(document.getElementById('btn-account-menu'),'avatar');
            h44(document.getElementById('btn-mode-toggle'),'mode');
            h44(document.querySelector('[data-action="dismiss-focus-panel"]'),'dismiss');
            [...document.querySelectorAll('.view-seg button')].forEach(b=>{ if(b.getBoundingClientRect().height<40) out.push('seg'); });
            const up=state.races.find(x=>x.name==='近的比賽'); selectRace(up.id); await wait(400);
            h44(document.querySelector('.dh-status-btn'),'stamp');
            [...document.querySelectorAll('.quick-nav a, .quick-nav .qn-back')].forEach(a=>{ if(a.getBoundingClientRect().height<40) out.push('qn'); });
            [...document.querySelectorAll('.lc-node')].forEach(n=>{ if(n.getBoundingClientRect().width<44) out.push('lc'); });
            return out.length===0 || out.join(); }""") is True
        c['phone_avatar_tap_at_edge_opens_menu'] = pp.evaluate("""async()=>{ """ + wait + """
            goBackFromDetail(); await wait(400);
            const b=document.getElementById('btn-account-menu').getBoundingClientRect();
            document.elementFromPoint(b.left+b.width/2, b.bottom+4).click(); await wait(250);
            const open=!document.getElementById('account-menu-panel').hidden;
            document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape'})); await wait(200); return open; }""")
        c['phone_gear_drawer_fits_and_checkboxes_20px'] = pp.evaluate("""async()=>{ """ + wait + """
            const r=state.races.find(x=>x.name==='近的比賽');
            r.equipmentChecklist=[{itemName:'跑鞋',category:'other',weightG:null,isConsumable:false,isMandatory:false,isPacked:false,location:'',notes:''}];
            // v4.2 起裝備清單預設是「打包」模式；範本選單與每件的「已打包」核取方塊在「編輯」
            selectRace(r.id); await wait(300); equipmentViewMode='list'; openDrawer('equipment'); await wait(400);
            const d=document.getElementById('global-drawer');
            const sel=d.querySelector('#template-select'); const box=d.querySelector('input[type="checkbox"][data-path$="isPacked"]');
            const ok=!!sel && sel.getBoundingClientRect().right<=innerWidth && !!box && box.getBoundingClientRect().width>=20
              && document.documentElement.scrollWidth<=innerWidth;
            closeDrawer(); await wait(300); goBackFromDetail(); await wait(400); return ok; }""")
        pp.evaluate("()=>document.querySelector('.home-tab[data-home-tab=\"career\"]').click()")
        pp.wait_for_timeout(700)
        c['phone_career_chart_labels_readable'] = pp.evaluate("""()=>{
            const vis=[...document.querySelectorAll('.yc-year,.yc-count,.et-year')].filter(e=>e.getClientRects().length);
            const sized=vis.every(e=>e.getBoundingClientRect().height>=11 && parseFloat(getComputedStyle(e).fontSize)>=12);
            // 標籤之間至少留 4px（貼在一起一樣讀不出來）
            const noOverlap=sel=>{ const rs=[...document.querySelectorAll(sel)].filter(e=>e.getClientRects().length).map(e=>e.getBoundingClientRect()).sort((a,b)=>a.left-b.left);
              return rs.every((r,i)=>i===0||r.left>=rs[i-1].right+4); };
            const yc=document.querySelectorAll('.yc-year').length, et=[...document.querySelectorAll('.et-year')].filter(e=>e.getClientRects().length).length;
            return yc===11 && et>=5 && sized && noOverlap('.yc-year') && noOverlap('.et-year')
              && !document.querySelector('.elevation-trend-svg text'); }""")
        # 年份很多（26 年）：年份標籤一樣不會疊在一起
        c['phone_career_labels_no_overlap_many_years'] = pp.evaluate("""async()=>{
            const extra=[]; for(let y=2000;y<2026;y++){ const r=emptyRace('多年 '+y,'trail_running','completed',y+'-06-15');
              r.route.distanceKm=30; r.route.elevationGainM=800+(y%5)*300; r.results.chipTimeSeconds=14000; extra.push(r); }
            state.races.push(...extra); renderCalendar(); await new Promise(s=>setTimeout(s,400));
            const shown=e=>e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden';
            const noOverlap=(sel,min)=>{ const rs=[...document.querySelectorAll(sel)].filter(shown).map(e=>e.getBoundingClientRect()).sort((a,b)=>a.left-b.left);
              return rs.length>=min && rs.every((r,i)=>i===0||r.left>=rs[i-1].right+4); };
            const latest=[...document.querySelectorAll('.yc-year')].pop();
            // 場次數字太擠時收起來（每一欄的提示文字裡還有），收起來也算沒有疊在一起
            const ok=noOverlap('.et-year',5) && noOverlap('.yc-year',5) && noOverlap('.yc-count',0) && shown(latest) && latest.textContent.includes('25');
            state.races=state.races.filter(r=>!extra.includes(r)); renderCalendar(); await new Promise(s=>setTimeout(s,300)); return ok; }""")
        c['phone_elevation_dots_are_round'] = pp.evaluate("""()=>{
            const d=[...document.querySelectorAll('.et-dot')]; return d.length>5 && d.every(x=>{ const r=x.getBoundingClientRect(); return Math.abs(r.width-r.height)<0.5; }); }""")
        # 從頭像選單點「範例資料」打開一場 → 返回回到首頁 → 再返回就離開（不會卡一下）
        pp.evaluate("()=>document.querySelector('.home-tab[data-home-tab=\"races\"]').click()")
        pp.wait_for_timeout(400)
        pp.goto(APP_URL)
        pp.wait_for_timeout(900)
        pp.add_style_tag(content='.badge-unbox-overlay,.foreground-toast{display:none!important}')
        pp.click('#btn-account-menu')
        pp.wait_for_timeout(250)
        pp.click('#btn-sample-data')
        pp.wait_for_timeout(600)
        opened = pp.evaluate("()=>EXAMPLE_RACE_IDS.includes(state.selectedId) && location.hash.startsWith('#race=')")
        pp.go_back()
        pp.wait_for_timeout(700)
        home = pp.evaluate("()=>state.selectedId===null && location.hash===''")
        first_url = pp.url
        pp.go_back()
        pp.wait_for_timeout(800)
        c['sample_from_menu_back_twice_leaves_cleanly'] = opened and home and pp.url != first_url
        pctx.close()



class V42Flows(Group):
    """v4.2.0：比完賽之後記錄成績、打包模式、賽前四格、已完賽「賽後」排第一、生涯數據可以點。"""

    def body(self, page):
        c = self.checks
        page.add_script_tag(content=UX_SEED_JS)
        page.add_style_tag(content='.badge-unbox-overlay{display:none!important}')
        page.evaluate(V4_EXTRA_JS)
        page.wait_for_timeout(400)
        W = "const wait=ms=>new Promise(s=>setTimeout(s,ms));"
        # 測試用的賽事：昨天比完還沒填（有 A 目標）、15 天前、今天、抽籤中昨天
        page.evaluate("""async()=>{
            const mk=(n,st,d)=>{ const r=emptyRace(n,'road_running',st,d!=null?addDaysStr(todayISO(),d):''); r.route.distanceKm=42.195; r.location.city='台中市'; state.races.push(r); return r; };
            const y=mk('昨天的馬拉松','registered',-1); y.goals[0].targetTimeSeconds=hmsToSec('3:30:00');
            mk('三天前的半馬','registered',-3).route.distanceKm=21.1;
            mk('十五天前的賽事','registered',-15); mk('今天的賽事','registered',0); mk('昨天沒抽中','lottery_pending',-1);
            await persist(); renderAll(); scrollTo(0,0); }""")
        page.wait_for_timeout(300)
        id_of = lambda n: page.evaluate("(n)=>state.races.find(r=>r.name===n).id", n)
        # ================= ① 記錄成績 =================
        c['prompt_day_after_registered_only'] = page.evaluate("""()=>{
            const card=document.querySelector('#focus-panel-slot .result-prompt');
            return !!card && card.querySelector('.result-prompt-title').textContent==='昨天的馬拉松'
              && card.querySelector('.result-prompt-meta').textContent.startsWith('昨天')
              && card.compareDocumentPosition(document.querySelector('#focus-panel-slot .focus-panel'))&Node.DOCUMENT_POSITION_FOLLOWING; }""")
        # 每一場所在的月份都翻過去看（v4.5.1 修測試）：原本只看畫面上那個月，月初的頭幾天「昨天」和
        # 「三天前」分在兩個月，只看得到其中一場，測試在每個月的 1–3 號會失敗
        c['list_tag_only_on_awaiting'] = page.evaluate("""()=>{
            const names=['昨天的馬拉松','三天前的半馬','十五天前的賽事','今天的賽事','昨天沒抽中'];
            const months=new Set(names.map(n=>state.races.find(r=>r.name===n).schedule.raceDate.slice(0,7)));
            const keep=[state.calendarYear,state.calendarMonth], tagged=new Set();
            months.forEach(ym=>{ state.calendarYear=Number(ym.slice(0,4)); state.calendarMonth=Number(ym.slice(5,7))-1; renderCalendar();
              document.querySelectorAll('#calendar .cal-list-item').forEach(b=>{ if(b.querySelector('.result-tag')) tagged.add(state.races.find(r=>r.id===b.dataset.id).name); }); });
            state.calendarYear=keep[0]; state.calendarMonth=keep[1]; renderCalendar();
            return JSON.stringify([...tagged].sort())===JSON.stringify(['三天前的半馬','昨天的馬拉松']); }""")
        c['record_opens_race_and_short_sheet'] = page.evaluate("""async()=>{ """ + W + """
            document.querySelector('.result-prompt [data-action="result-record"]').click(); await wait(500);
            const d=document.getElementById('global-drawer');
            const paths=[...d.querySelectorAll('#drawer-content [data-path]')].map(x=>x.dataset.path);
            return currentRace&&currentRace.name==='昨天的馬拉松' && location.hash.startsWith('#race=') && !d.hidden
              && document.getElementById('drawer-title').textContent==='記錄成績'
              && JSON.stringify(paths)===JSON.stringify(['results.chipTimeSeconds','results.overallRank','results.overallParticipants','results.ageGroupRank','results.ageGroupParticipants']); }""")
        page.fill('#drawer-content input[data-path="results.chipTimeSeconds"]', '3:21:27')
        page.keyboard.press('Tab')
        page.wait_for_timeout(600)
        c['goal_comparison_in_words'] = page.evaluate("""()=>{ const g=document.querySelector('#drawer-content .record-result-goal');
            return !!g && g.textContent==='比 A 目標（3:30:00）快 8 分 33 秒' && g.classList.contains('is-ahead'); }""")
        c['save_marks_completed_and_shows_result'] = page.evaluate("""async()=>{ """ + W + """
            document.querySelector('[data-action="record-result-save"]').click(); await wait(700);
            const r=state.races.find(x=>x.name==='昨天的馬拉松');
            return r.status==='completed' && r.results.chipTimeSeconds===12087 && document.getElementById('global-drawer').hidden
              && scrollY===0 && document.querySelector('#detail .results-big-time').textContent.includes('21')
              && document.querySelector('#detail .quick-nav a').dataset.target==='section-post'; }""")
        c['back_after_save_goes_home_and_card_moves_on'] = page.evaluate("""async()=>{ """ + W + """
            goBackFromDetail(); await wait(500);
            const card=document.querySelector('#focus-panel-slot .result-prompt');
            return state.selectedId===null && !!card && card.querySelector('.result-prompt-title').textContent==='三天前的半馬'; }""")
        c['dns_from_card_with_undo'] = page.evaluate("""async()=>{ """ + W + """
            document.querySelector('.result-prompt [data-action="result-set-status"][data-status="dns"]').click(); await wait(500);
            const r=state.races.find(x=>x.name==='三天前的半馬');
            const a=r.status==='dns' && !document.querySelector('#focus-panel-slot .result-prompt');
            const undo=[...document.querySelectorAll('.foreground-toast .race-undo-btn')].pop(); if(!undo) return false; undo.click(); await wait(500);
            return a && r.status==='registered' && !!document.querySelector('#focus-panel-slot .result-prompt'); }""")
        c['later_hides_card_keeps_tag_and_banner'] = page.evaluate("""async()=>{ """ + W + """
            document.querySelector('.result-prompt [data-action="result-later"]').click(); await wait(300);
            renderAll(); await wait(200);
            const id=state.races.find(x=>x.name==='三天前的半馬').id;
            const gone=!document.querySelector('#focus-panel-slot .result-prompt');
            const tag=!!document.querySelector('#calendar .cal-list-item[data-id="'+id+'"] .result-tag');
            selectRace(id); await wait(400);
            const banner=document.querySelector('#detail .result-banner');
            const ok=gone && tag && !!banner && banner.textContent.includes('比賽已經過了 3 天') && !document.querySelector('#detail .rw-tiles');
            goBackFromDetail(); await wait(400); return ok; }""")
        c['banner_any_age_and_dns_from_banner'] = page.evaluate("""async()=>{ """ + W + """
            const r=state.races.find(x=>x.name==='十五天前的賽事');
            const noTag=!document.querySelector('#calendar .cal-list-item[data-id="'+r.id+'"] .result-tag');
            selectRace(r.id); await wait(400);
            const has=!!document.querySelector('#detail .result-banner');
            const dnsBtn=document.querySelector('#detail .result-banner [data-action="lc-set-status"][data-status="dns"]');
            if(!dnsBtn){ goBackFromDetail(); await wait(400); return false; }
            dnsBtn.click(); await wait(500);
            const ok=noTag && has && r.status==='dns' && !document.querySelector('#detail .result-banner');
            goBackFromDetail(); await wait(400); return ok; }""")
        c['no_prompt_on_race_day_or_for_lottery'] = page.evaluate("""()=>{
            const today=state.races.find(x=>x.name==='今天的賽事'), lot=state.races.find(x=>x.name==='昨天沒抽中');
            return today.schedule.raceDate===todayISO() && !raceNeedsResult(today) && !isAwaitingResult(lot) && !raceNeedsResult(lot)
              && !document.querySelector('#calendar .cal-list-item[data-id="'+today.id+'"] .result-tag'); }""")
        c['save_without_time_still_completes'] = page.evaluate("""async()=>{ """ + W + """
            const r=emptyRace('沒記時間的賽事','road_running','registered',addDaysStr(todayISO(),-2)); state.races.push(r); await persist(); renderAll();
            openRecordResult(r.id); await wait(400);
            document.querySelector('[data-action="record-result-save"]').click(); await wait(600);
            const ok=r.status==='completed' && r.results.chipTimeSeconds==null && document.getElementById('global-drawer').hidden;
            goBackFromDetail(); await wait(400); return ok; }""")
        # 鐵人三項只填完賽時間（沒有匯入分項，記錄成績最常見的情況）：不顯示全場平均配速，分享圖也一樣
        c['triathlon_with_only_time_has_no_overall_pace'] = page.evaluate("""async()=>{ """ + W + """
            const r=emptyRace('只填時間的三鐵','triathlon','registered',addDaysStr(todayISO(),-1)); r.route.distanceKm=113; state.races.push(r); await persist(); renderAll();
            openRecordResult(r.id); await wait(400);
            const inp=document.querySelector('#drawer-content input[data-path="results.chipTimeSeconds"]'); inp.value='5:41:27'; inp.dispatchEvent(new Event('change',{bubbles:true})); await wait(300);
            document.querySelector('[data-action="record-result-save"]').click(); await wait(600);
            const labels=[...document.querySelectorAll('#detail .results-badge-label')].map(e=>e.textContent);
            const share=shareStatsBadges(r,SHARE_SHOW_DEFAULT).map(b=>b[0]);
            const ok=r.status==='completed' && r.results.chipTimeSeconds===20487 && labels.includes('距離')
              && !labels.some(l=>l.includes('配速')) && !share.some(l=>l.includes('配速'));
            goBackFromDetail(); await wait(400); return ok; }""")
        c['back_closes_record_sheet_first'] = page.evaluate("""async()=>{ """ + W + """
            const r=emptyRace('返回測試','road_running','registered',addDaysStr(todayISO(),-1)); state.races.push(r); await persist(); renderAll();
            openRecordResult(r.id); await wait(400);
            history.back(); await wait(500);
            const a=document.getElementById('global-drawer').hidden && state.selectedId===r.id;
            history.back(); await wait(500);
            return a && state.selectedId===null && location.hash===''; }""")
        # 有封面照的賽事頁首上的提示列：淺色、深色模式都要看得清楚（深色模式的封面頁首是深底淺字）
        page.add_script_tag(content=CONTRAST_JS)
        c['banner_on_cover_readable_light_and_dark'] = page.evaluate("""async()=>{ """ + W + """
            const r=emptyRace('有封面的賽事','road_running','registered',addDaysStr(todayISO(),-2));
            const cv=document.createElement('canvas'); cv.width=320; cv.height=180; const g=cv.getContext('2d');
            g.fillStyle='#d8c8a0'; g.fillRect(0,0,320,180); g.fillStyle='#334'; g.fillRect(0,110,320,70);
            r.coverImage=cv.toDataURL('image/jpeg',.8); r.coverImageAspect=320/180; state.races.push(r); await persist();
            selectRace(r.id); await wait(400);
            const st=document.createElement('style'); st.textContent='*{transition:none!important}'; document.head.appendChild(st);
            const read=()=>{ const b=document.querySelector('#detail .detail-header.has-cover .result-banner b'); return !!b && __contrast(b)>=4.5; };
            const light=read(); applyTheme('dark'); await wait(150); const dark=read(); applyTheme('light'); await wait(150); st.remove();
            goBackFromDetail(); await wait(400); return light && dark; }""")
        # ================= ③ 賽前四格、已完賽順序 =================
        c['tiles_for_registered_upcoming_only'] = page.evaluate("""async()=>{ """ + W + """
            const near=state.races.find(x=>x.name==='近的比賽'); near.bibNumber='B77'; near.schedule.startTime='06:30';
            near.equipmentChecklist=[{itemName:'跑鞋',isPacked:true},{itemName:'帽子',isPacked:false}].map(x=>Object.assign(LIST_META.equipmentChecklist.factory(),x));
            const gi=near.goals.findIndex(g=>g.tier==='A'); near.goals[gi].targetTimeSeconds=hmsToSec('3:15:00'); await persist();
            selectRace(near.id); await wait(400);
            const v=[...document.querySelectorAll('#detail .rw-tile')].map(b=>b.dataset.tile+':'+b.querySelector('.rw-tile-value').textContent);
            const far=state.races.find(x=>x.name==='遠的比賽'); selectRace(far.id); await wait(400);
            const none=!document.querySelector('#detail .rw-tiles');
            return JSON.stringify(v)===JSON.stringify(['bib:B77','start:06:30','pack:1/2','goal:3:15:00']) && none; }""")
        # 全部打包好：值寫「2/2」、勾勾在標籤上（「打包 ✓」），值本身不加勾，兩位數的清單才放得下
        c['all_packed_tile_marks_done'] = page.evaluate("""async()=>{ """ + W + """
            const near=state.races.find(x=>x.name==='近的比賽'); const keep=near.equipmentChecklist.map(i=>i.isPacked);
            near.equipmentChecklist.forEach(i=>{ i.isPacked=true; }); selectRace(near.id); await wait(400);
            const t=document.querySelector('#detail .rw-tile[data-tile="pack"]');
            const ok=t.querySelector('.rw-tile-value').textContent==='2/2' && t.querySelector('.rw-tile-label').textContent==='打包 ✓';
            near.equipmentChecklist.forEach((i,k)=>{ i.isPacked=keep[k]; }); await persist(); renderDetail(); await wait(100);
            return ok; }""")
        c['empty_tile_opens_drawer_and_focuses'] = page.evaluate("""async()=>{ """ + W + """
            const r=emptyRace('還沒填的','road_running','registered',addDaysStr(todayISO(),20)); state.races.push(r); await persist();
            selectRace(r.id); await wait(400);
            const t=document.querySelector('#detail .rw-tile[data-tile="bib"]');
            const empty=t.classList.contains('is-empty') && t.textContent.includes('＋ 填寫');
            t.click(); await wait(400);
            const ae=document.activeElement;
            const ok=empty && !document.getElementById('global-drawer').hidden && ae && ae.dataset.path==='bibNumber';
            ae.value='Z9'; ae.dispatchEvent(new Event('change',{bubbles:true})); await wait(400);
            closeDrawer(); await wait(300);
            return ok && document.querySelector('#detail .rw-tile[data-tile="bib"] .rw-tile-value').textContent==='Z9'; }""")
        c['pack_tile_opens_pack_mode'] = page.evaluate("""async()=>{ """ + W + """
            equipmentViewMode='list';
            const near=state.races.find(x=>x.name==='近的比賽'); selectRace(near.id); await wait(400);
            document.querySelector('#detail .rw-tile[data-tile="pack"]').click(); await wait(400);
            const ok=!document.getElementById('global-drawer').hidden && !!document.querySelector('#drawer-content .pack-row')
              && document.querySelector('[data-action="equipment-view"][aria-pressed="true"]').dataset.view==='pack';
            closeDrawer(); await wait(300); return ok; }""")
        c['completed_post_first_upcoming_basic_first'] = page.evaluate("""async()=>{ """ + W + """
            const order=()=>[...document.querySelectorAll('#detail details.section')].map(d=>d.id).join();
            const nav=()=>[...document.querySelectorAll('#detail .quick-nav a')].map(a=>a.dataset.target).join();
            const done=state.races.find(x=>x.status==='completed'&&x.results.chipTimeSeconds); selectRace(done.id); await wait(400);
            const a=order()==='section-post,section-basic,section-route,section-prep,section-logistics' && nav()==='section-post,section-basic,section-route,section-prep,section-logistics';
            const dnf=state.races.find(x=>x.status==='dnf'); selectRace(dnf.id); await wait(400); const b=order().startsWith('section-post');
            const up=state.races.find(x=>x.name==='近的比賽'); selectRace(up.id); await wait(400);
            const c2=order()==='section-basic,section-route,section-prep,section-logistics,section-post' && nav().startsWith('section-basic');
            goBackFromDetail(); await wait(400); return a && b && c2; }""")
        # ================= ② 打包模式 =================
        page.evaluate("""async()=>{ const r=state.races.find(x=>x.name==='近的比賽');
            r.equipmentChecklist=['跑鞋','號碼布','能量膠','鹽錠','帽子','手錶'].map((n,i)=>Object.assign(LIST_META.equipmentChecklist.factory(),{itemName:n,isPacked:i<2,isMandatory:i===1||i===3,location:i===2?'body':''}));
            await persist(); equipmentViewMode='pack'; packFilter='todo'; selectRace(r.id); await new Promise(s=>setTimeout(s,300)); openDrawer('equipment'); }""")
        page.wait_for_timeout(400)
        c['pack_mode_default_lists_unpacked_first'] = page.evaluate("""()=>{
            const dc=document.getElementById('drawer-content');
            const todo=[...dc.querySelectorAll('.pack-list > .pack-row')].map(b=>b.querySelector('.pack-name').textContent);
            const done=dc.querySelector('details.pack-done');
            return JSON.stringify(todo)===JSON.stringify(['能量膠','鹽錠','帽子','手錶']) && !!done && !done.open
              && done.querySelector('summary').textContent==='已打包 2 件' && dc.querySelector('.pack-progress b').textContent==='2 / 6'
              && !dc.querySelector('input[data-path$="itemName"]')
              && dc.querySelector('.pack-row .pack-where').textContent==='隨身攜帶'
              && [...dc.querySelectorAll('.pack-list > .pack-row')][1].querySelector('.pack-must').textContent==='強制'; }""")
        c['tap_row_packs_and_moves_to_done'] = page.evaluate("""async()=>{ """ + W + """
            document.querySelector('#drawer-content .pack-list > .pack-row').click(); await wait(400);
            const r=currentRace; const dc=document.getElementById('drawer-content');
            return r.equipmentChecklist[2].isPacked===true && dc.querySelector('.pack-progress b').textContent==='3 / 6'
              && dc.querySelector('details.pack-done summary').textContent==='已打包 3 件'
              && ![...dc.querySelectorAll('.pack-list > .pack-row')].some(b=>b.textContent.includes('能量膠')); }""")
        c['done_group_stays_open_and_unpacks'] = page.evaluate("""async()=>{ """ + W + """
            const d=document.querySelector('#drawer-content details.pack-done'); d.open=true; await wait(100);
            const row=[...d.querySelectorAll('.pack-row')].find(b=>b.textContent.includes('跑鞋')); row.click(); await wait(400);
            const d2=document.querySelector('#drawer-content details.pack-done');
            return currentRace.equipmentChecklist[0].isPacked===false && !!d2 && d2.open; }""")
        c['filters_all_and_must'] = page.evaluate("""async()=>{ """ + W + """
            document.querySelector('[data-action="pack-filter"][data-filter="must"]').click(); await wait(300);
            const must=[...document.querySelectorAll('#drawer-content .pack-row .pack-name')].map(x=>x.textContent);
            document.querySelector('[data-action="pack-filter"][data-filter="all"]').click(); await wait(300);
            const all=document.querySelectorAll('#drawer-content .pack-row').length;
            document.querySelector('[data-action="pack-filter"][data-filter="todo"]').click(); await wait(300);
            return JSON.stringify(must)===JSON.stringify(['號碼布','鹽錠']) && all===6; }""")
        page.click('#drawer-content .pack-add-input')
        page.keyboard.type('壓縮襪')
        page.keyboard.press('Enter')
        page.wait_for_timeout(400)
        page.keyboard.type('防曬乳')
        page.keyboard.press('Enter')
        page.wait_for_timeout(400)
        c['add_items_with_enter_back_to_back'] = page.evaluate("""()=>{ const l=currentRace.equipmentChecklist;
            return l.length===8 && l[6].itemName==='壓縮襪' && l[7].itemName==='防曬乳' && l[7].isPacked===false
              && document.activeElement && document.activeElement.classList.contains('pack-add-input') && document.activeElement.value===''; }""")
        # 注音／拼音／日文輸入法選字時按的 Enter 是「確定這個字」，不能被當成新增
        c['enter_while_composing_does_not_add'] = page.evaluate("""async()=>{ """ + W + """
            const inp=document.querySelector('#drawer-content .pack-add-input'); inp.value='選字中';
            inp.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',isComposing:true,bubbles:true,cancelable:true})); await wait(300);
            const ok=currentRace.equipmentChecklist.length===8;
            document.querySelector('#drawer-content .pack-add-input').value=''; return ok; }""")
        c['edit_and_kanban_views_still_work'] = page.evaluate("""async()=>{ """ + W + """
            document.querySelector('[data-action="equipment-view"][data-view="list"]').click(); await wait(300);
            const edit=document.querySelectorAll('#drawer-content input[data-path$=".itemName"]').length===8 && !!document.getElementById('template-select');
            document.querySelector('[data-action="equipment-view"][data-view="kanban"]').click(); await wait(300);
            const kb=!!document.querySelector('#drawer-content .kanban-card');
            document.querySelector('[data-action="equipment-view"][data-view="pack"]').click(); await wait(300);
            closeDrawer(); await wait(300); return edit && kb && !!document.querySelector('#detail .rw-tiles'); }""")
        c['empty_list_offers_templates_in_pack_mode'] = page.evaluate("""async()=>{ """ + W + """
            const r=emptyRace('空清單','trail_running','registered',addDaysStr(todayISO(),30)); state.races.push(r); await persist();
            selectRace(r.id); await wait(300); openDrawer('equipment'); await wait(300);
            const dc=document.getElementById('drawer-content');
            const ok=!!dc.querySelector('[data-action="apply-starter-template"]') && !!dc.querySelector('.pack-add-input');
            dc.querySelector('[data-action="apply-starter-template"]').click(); await wait(400);
            const filled=r.equipmentChecklist.length>0 && document.querySelectorAll('#drawer-content .pack-row').length===r.equipmentChecklist.length;
            closeDrawer(); await wait(300); goBackFromDetail(); await wait(400); return ok && filled; }""")
        c['focus_card_packing_opens_drawer'] = page.evaluate("""async()=>{ """ + W + """
            equipmentViewMode='list';
            // v4.3 起焦點卡的打包是一格（跟賽事頁的賽前四格同一套）
            const ring=document.querySelector('#focus-panel-slot .focus-panel [data-action="open-packing"]');
            const fr=computeFocusRace(); if(!ring) return false; ring.click(); await wait(500);
            // 焦點賽事可能還沒有清單（那時面板是範本與新增），所以看「打開的是打包模式」
            const on=document.querySelector('#drawer-content [data-action="equipment-view"][aria-pressed="true"]');
            const ok=!!fr && state.selectedId===fr.id && !document.getElementById('global-drawer').hidden && !!on && on.dataset.view==='pack';
            closeDrawer(); await wait(300); goBackFromDetail(); await wait(400); return ok; }""")
        # ================= ④ 生涯數據 =================
        # 上面幾項是賽事頁直接跳賽事頁（每一跳都是新的一頁，返回會回到上一場），
        # 先一路返回到首頁，生涯數據才是從首頁點進去的狀態
        page.evaluate("""async()=>{ for(let i=0;i<25&&(state.selectedId||state.creating);i++){ goBackFromDetail(); await new Promise(s=>setTimeout(s,350)); } }""")
        page.evaluate("()=>document.querySelector('.home-tab[data-home-tab=\"career\"]').click()")
        page.wait_for_timeout(600)
        c['year_bar_opens_that_years_races'] = page.evaluate("""async()=>{ """ + W + """
            const bar=document.querySelector('.yc-col[data-year="2019"]'); if(!bar) return false; const n=Number(bar.querySelector('.yc-count').textContent);
            bar.click(); await wait(400);
            const el=document.getElementById('career-sheet');
            const rows=[...el.querySelectorAll('.cal-list-item')].map(b=>state.races.find(r=>r.id===b.dataset.id));
            const dates=rows.map(r=>r.schedule.raceDate);
            return !el.hidden && el.querySelector('h2').textContent==='2019 年・完賽 '+n+' 場' && rows.length===n
              && rows.every(r=>r.status==='completed'&&r.schedule.raceDate.startsWith('2019')) && dates.every((d,i)=>i===0||d>=dates[i-1])
              && el.querySelector('.career-sheet-sum b').textContent===n+' 場'; }""")
        c['back_closes_sheet_first'] = page.evaluate("""async()=>{ """ + W + """
            history.back(); await wait(500);
            return document.getElementById('career-sheet').hidden && location.hash==='#career' && state.homeTab==='career'; }""")
        c['heatmap_cell_opens_month'] = page.evaluate("""async()=>{ """ + W + """
            const cell=document.querySelector('.heatmap-cell[data-action="career-month"]'); if(!cell) return false; const ym=cell.dataset.ym;
            cell.click(); await wait(400);
            const el=document.getElementById('career-sheet');
            const rows=[...el.querySelectorAll('.cal-list-item')].map(b=>state.races.find(r=>r.id===b.dataset.id));
            const n=state.races.filter(r=>!r.deletedAt&&r.status==='completed'&&r.schedule.raceDate.startsWith(ym)).length;
            const ok=!el.hidden && rows.length===n && n>0 && rows.every(r=>r.schedule.raceDate.startsWith(ym))
              && el.querySelector('h2').textContent.startsWith(ym.slice(0,4)+' 年 '+Number(ym.slice(5))+' 月');
            document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape'})); await wait(300);
            return ok && el.hidden; }""")
        c['total_races_opens_all_by_year'] = page.evaluate("""async()=>{ """ + W + """
            const all=document.querySelector('[data-action="career-all"]'); if(!all) return false; all.click(); await wait(400);
            const el=document.getElementById('career-sheet');
            const n=state.races.filter(r=>!r.deletedAt&&r.status==='completed').length;
            const years=[...el.querySelectorAll('.cal-results-group-title')].map(h=>h.childNodes[0].textContent.trim());
            return el.querySelectorAll('.cal-list-item').length===n && years.length>5 && years.every((y,i)=>i===0||y<years[i-1]); }""")
        c['sheet_row_opens_race_back_returns_to_career'] = page.evaluate("""async()=>{ """ + W + """
            const row=document.querySelector('#career-sheet .cal-list-item'); if(!row) return false; const id=row.dataset.id; row.click(); await wait(500);
            const a=state.selectedId===id && document.getElementById('career-sheet').hidden && location.hash.startsWith('#race=');
            history.back(); await wait(600);
            return a && state.selectedId===null && state.homeTab==='career' && location.hash==='#career'; }""")
        # PB 的時間：真的用滑鼠按。按住 0.8 秒才放開是想長按（還沒到 1.5 秒解鎖），
        # 不該跳走；很快點一下才打開那一場；鍵盤 Enter 也要能打開
        pb = page.locator('[data-action="career-pb"]')
        bb = None
        if pb.count() and pb.first.is_visible():
            pb.first.scroll_into_view_if_needed()
            bb = pb.first.bounding_box()
        if not bb:
            # 前面的項目壞掉、人已經不在生涯數據：記成這一項失敗，不要整組當掉
            bb = {'x': -100, 'y': -100, 'width': 0, 'height': 0}
        cx, cy = bb['x'] + bb['width'] / 2, bb['y'] + bb['height'] / 2
        page.mouse.move(max(cx, 0), max(cy, 0))
        page.mouse.down()
        page.wait_for_timeout(800)
        page.mouse.up()
        page.wait_for_timeout(300)
        held_stays = page.evaluate("()=>state.selectedId===null && document.getElementById('hof-overlay').hidden")
        page.mouse.click(cx, cy)
        page.wait_for_timeout(500)
        tap_opens = page.evaluate("()=>state.selectedId===marathonPbRace().id")
        page.evaluate("""async()=>{ goBackFromDetail(); await new Promise(s=>setTimeout(s,500)); }""")
        if page.locator('[data-action="career-pb"]').count():
            page.evaluate("()=>document.querySelector('[data-action=\"career-pb\"]').focus()")
            page.keyboard.press('Enter')
        page.wait_for_timeout(500)
        key_opens = page.evaluate("()=>state.selectedId===marathonPbRace().id")
        page.evaluate("""async()=>{ goBackFromDetail(); await new Promise(s=>setTimeout(s,500)); }""")
        c['pb_tap_opens_pb_race_long_press_does_not'] = held_stays and tap_opens and key_opens
        # （版本號的檢查跟著最新的群組走，v4.3.0 起在 v43）
        # ================= 手機：大小與英文 =================
        for w in (390, 360):
            pctx = full_mode_context(page.context.browser, viewport={'width': w, 'height': 800}, is_mobile=True, has_touch=True)
            pp = pctx.new_page()
            pp.on('pageerror', lambda e: self.errors.append(str(e)))
            pp.goto(APP_URL)
            pp.wait_for_timeout(900)
            pp.add_script_tag(content=UX_SEED_JS)
            pp.add_style_tag(content='.badge-unbox-overlay,.foreground-toast{display:none!important}')
            pp.evaluate(V4_EXTRA_JS)
            pp.wait_for_timeout(300)
            if w == 390:
                # 剛打開網站，從賽事頁的「裝備清單」卡片進去，預設就是打包模式
                c['fresh_page_gear_card_opens_pack_mode'] = pp.evaluate("""async()=>{ const wait=ms=>new Promise(s=>setTimeout(s,ms));
                    const r=state.races.find(x=>x.name==='近的比賽');
                    r.equipmentChecklist=['跑鞋','帽子'].map(n=>Object.assign(LIST_META.equipmentChecklist.factory(),{itemName:n}));
                    await persist(); selectRace(r.id); await wait(400);
                    document.querySelector('#detail .dash-card[data-section="equipment"]').click(); await wait(400);
                    const ok=document.querySelector('[data-action="equipment-view"][aria-pressed="true"]').dataset.view==='pack'
                      && document.querySelectorAll('#drawer-content .pack-list > .pack-row').length===2;
                    closeDrawer(); await wait(300); goBackFromDetail(); await wait(400); return ok; }""")
            # 四格在三種語言 × 三種字級 × 幾種最長的內容下：值不被截掉、標籤不超出格子。
            # 「12/12」全部打包好、A12345、11:50:00（超馬）是實際會出現的最寬的值
            c[f'phone{w}_tiles_and_pack_rows_fit'] = pp.evaluate("""async()=>{ const wait=ms=>new Promise(s=>setTimeout(s,ms));
                const r=state.races.find(x=>x.name==='近的比賽'); const gi=r.goals.findIndex(g=>g.tier==='A');
                const fill=(bib,st,n,packed,goal)=>{ r.bibNumber=bib; r.schedule.startTime=st; r.goals[gi].targetTimeSeconds=goal?hmsToSec(goal):null;
                  r.equipmentChecklist=Array.from({length:n},(_,i)=>Object.assign(LIST_META.equipmentChecklist.factory(),{itemName:'裝備 '+i,isPacked:i<packed})); };
                fill('T0231','06:30',12,7,'11:50:00'); await persist(); selectRace(r.id); await wait(400);
                const bad=[];
                for(const lang of ['zh','ja','en']){ setLang(lang); await wait(200);
                  for(const fs of ['small','medium','large']){ applyFontScale(fs);
                    for(const cs of [['T0231','06:30',12,7,'11:50:00'],['A12345','06:30',12,12,'3:30:00'],['','',0,0,'']]){
                      fill(...cs); renderDetail(); await wait(30);
                      const tiles=[...document.querySelectorAll('#detail .rw-tile')];
                      if(tiles.length!==4) bad.push(lang+fs+' tiles='+tiles.length);
                      tiles.forEach(t=>{ const st=getComputedStyle(t), inner=t.getBoundingClientRect().right-parseFloat(st.paddingRight);
                        const v=t.querySelector('.rw-tile-value'), rg=document.createRange(); rg.selectNodeContents(t.querySelector('.rw-tile-label'));
                        if(v.scrollWidth>v.clientWidth+1) bad.push(lang+' '+fs+' cut '+v.textContent);
                        if(rg.getBoundingClientRect().right>inner+0.5) bad.push(lang+' '+fs+' label '+t.querySelector('.rw-tile-label').textContent); });
                      if(document.documentElement.scrollWidth>innerWidth) bad.push(lang+' '+fs+' hscroll');
                    } } }
                setLang('zh'); applyFontScale('medium'); fill('T0231','06:30',12,7,'11:50:00'); await persist(); renderDetail(); await wait(200);
                if(bad.length) console.log('tiles:',bad.join(' | '));
                document.querySelector('#detail .rw-tile[data-tile="pack"]').click(); await wait(400);
                const rows=[...document.querySelectorAll('#drawer-content .pack-list > .pack-row')];
                return bad.length===0 && rows.length===5 && rows.every(b=>b.getBoundingClientRect().height>=44)
                  && document.documentElement.scrollWidth<=innerWidth; }""")
            pctx.close()
        ectx = full_mode_context(page.context.browser, viewport=PHONE, is_mobile=True, has_touch=True)
        ectx.add_init_script("try{localStorage.setItem('lang-pref-v1','en');}catch(e){}")
        ep = ectx.new_page()
        ep.on('pageerror', lambda e: self.errors.append(str(e)))
        ep.goto(APP_URL)
        ep.wait_for_timeout(900)
        ep.add_script_tag(content=UX_SEED_JS)
        ep.add_style_tag(content='.badge-unbox-overlay,.foreground-toast{display:none!important}')
        ep.evaluate(V4_EXTRA_JS)
        c['english_prompt_and_tiles'] = ep.evaluate("""async()=>{ const wait=ms=>new Promise(s=>setTimeout(s,ms));
            const r=emptyRace('Yesterday race','road_running','registered',addDaysStr(todayISO(),-1)); state.races.push(r); await persist(); renderAll(); await wait(300);
            const card=document.querySelector('.result-prompt');
            const a=card.querySelector('.result-prompt-label').textContent==='Did you finish?' && card.querySelector('.result-prompt-main').textContent==='Log result'
              && document.querySelector('.result-tag').textContent==='Result pending';
            const up=state.races.find(x=>x.name==='近的比賽'); selectRace(up.id); await wait(400);
            const labels=[...document.querySelectorAll('#detail .rw-tile-label')].map(x=>x.textContent).join('|');
            return a && labels==='Bib|Start|Packed|Goal A'; }""")
        # 英文單數：昨天的比賽不是「1 days ago」，只有一場的月份不是「1 races」
        c['english_singular_reads_naturally'] = ep.evaluate("""async()=>{ const wait=ms=>new Promise(s=>setTimeout(s,ms));
            const r=state.races.find(x=>x.name==='Yesterday race'); selectRace(r.id); await wait(400);
            const b=document.querySelector('#detail .result-banner b').textContent;
            goBackFromDetail(); await wait(400);
            const by={}; state.races.filter(x=>!x.deletedAt&&x.status==='completed'&&x.schedule.raceDate).forEach(x=>{ const k=x.schedule.raceDate.slice(0,7); by[k]=(by[k]||0)+1; });
            const ym=Object.keys(by).find(k=>by[k]===1); if(!ym) return false;
            openCareerSheet('month',ym); await wait(200);
            const h=document.querySelector('#career-sheet h2').textContent, n=document.querySelector('#career-sheet .career-sheet-sum b').textContent;
            closeCareerSheet();
            return b==='This race was yesterday — no result yet' && h.endsWith('· 1 finished') && n==='1'; }""")
        ectx.close()


class V43Flows(Group):
    """v4.3.0：精簡的「下一場」卡、獎牌牆（沒有封面照的畫成獎牌）、表格排序與各距離最佳、
    全馬 PB 只算跑步。"""

    def _ctx(self, browser, viewport, lang=None, touch=False):
        ctx = full_mode_context(browser, viewport=viewport, is_mobile=touch, has_touch=touch)
        if lang:
            ctx.add_init_script(f"try{{localStorage.setItem('lang-pref-v1','{lang}');}}catch(e){{}}")
        pg = ctx.new_page()
        pg.on('pageerror', lambda e: self.errors.append(str(e)))
        pg.on('console', self._echo)
        pg.goto(APP_URL)
        pg.wait_for_timeout(900)
        pg.add_script_tag(content=UX_SEED_JS)
        pg.add_style_tag(content='.badge-unbox-overlay,.foreground-toast{display:none!important}')
        pg.evaluate(V4_EXTRA_JS)
        pg.wait_for_timeout(300)
        return ctx, pg

    # 檢查失敗時頁面裡用 console.log 印出實際拿到的值，帶到測試輸出，不用重跑一次才知道差在哪
    ECHO = ('third:', 'fetch:', 'sorts:', 'prompt:', 'fit:', 'en:')

    def _echo(self, msg):
        if msg.text.startswith(self.ECHO):
            print('   ', msg.text[:300])

    def ev(self, pg, js):
        # 一項檢查在頁面裡拋出例外（例如某個元素不見了）：記成這一項失敗並印出原因，
        # 後面的檢查照跑——不要整組當掉、看不到其他項目的結果
        try:
            return pg.evaluate(js)
        except Exception as exc:                      # noqa: BLE001
            print('    ⚠', str(exc).split('\n')[0][:200])
            return False

    def body(self, page):
        c = self.checks
        page.on('console', self._echo)
        page.add_script_tag(content=UX_SEED_JS)
        page.add_script_tag(content=CONTRAST_JS)
        page.add_style_tag(content='.badge-unbox-overlay,.foreground-toast{display:none!important}')
        page.evaluate(V4_EXTRA_JS)
        page.wait_for_timeout(400)
        # 每一項都用得到的：等待、焦點賽事（9 天後的「近的比賽」）、它的 A 目標在第幾個
        W = ("const wait=ms=>new Promise(s=>setTimeout(s,ms));"
             "const near=state.races.find(x=>x.name==='近的比賽'); const gi=near.goals.findIndex(g=>g.tier==='A');"
             "const card=()=>document.querySelector('#focus-panel-slot .focus-panel');"
             "const tile=k=>document.querySelector('#focus-panel-slot .rw-tile[data-tile=\"'+k+'\"]');"
             "const tiles=()=>[...document.querySelectorAll('#focus-panel-slot .rw-tile')].map(t=>t.dataset.tile+':'+t.querySelector('.rw-tile-label').textContent+':'+t.querySelector('.rw-tile-value').textContent);"
             # 回到首頁：先關抽屜，再一層一層返回
             "const home=async()=>{ for(let i=0;i<12;i++){ if(!document.getElementById('global-drawer').hidden){ closeDrawer(); await wait(300); continue; } if(state.selectedId||state.creating){ goBackFromDetail(); await wait(350); continue; } break; } };")
        # ================= ① 「下一場」卡 =================
        c['laptop_card_is_one_compact_row'] = self.ev(page, """()=>{ const f=document.querySelector('#focus-panel-slot .focus-panel'); if(!f) return false;
            const head=f.querySelector('.nx-head').getBoundingClientRect(), tl=f.querySelector('.nx-tiles').getBoundingClientRect();
            // 一列：三格在倒數的右邊、上下範圍重疊；v4.2 的圓環、三張卡、「查看完整賽事」都不在了
            const oneRow=tl.left>=head.right-1 && tl.top<head.bottom && tl.bottom>head.top;
            const old=f.querySelector('.focus-panel-card,.focus-panel-grid,.focus-hero,.focus-panel-view-btn,.progress-ring-wrap,svg');
            // v4.7.0 起筆電上右邊有一張今日一句，兩張卡一樣高：句子長的那幾天卡片的框會被拉高（內容置中），
            // 所以量內容本身——原本「卡片 ≤150px」扣掉上下 14px 的內距
            const content=Math.max(head.bottom,tl.bottom)-Math.min(head.top,tl.top);
            return f.classList.contains('focus-panel-compact') && content<=122 && oneRow && !old
              && f.querySelectorAll('.rw-tile').length===3; }""")
        c['card_name_date_time_place_countdown'] = self.ev(page, """async()=>{ """ + W + """
            near.schedule.startTime='06:30'; await persist(); renderAll(); await wait(100);
            const f=card(); const d=near.schedule.raceDate; const wd='日一二三四五六'[new Date(d+'T00:00:00').getDay()];
            return f.dataset.id===near.id && f.querySelector('.nx-name').textContent==='近的比賽'
              && f.querySelector('.nx-meta').textContent===d.slice(5).replace('-','/')+'（'+wd+'） 06:30 ・ 台北市'
              && f.querySelector('.nx-count b').textContent==='9' && f.querySelector('.nx-count span').textContent==='天後'; }""")
        c['empty_tiles_invite_filling'] = self.ev(page, """()=>{ """ + W + """
            return JSON.stringify(tiles())===JSON.stringify(['pack:打包:＋ 清單','goal:A 目標:＋ 填寫','bib:號碼布:＋ 填寫'])
              && [...document.querySelectorAll('#focus-panel-slot .rw-tile')].every(t=>t.classList.contains('is-empty')&&t.type==='button'); }""")
        c['tiles_show_pack_goal_bib'] = self.ev(page, """async()=>{ """ + W + """
            near.equipmentChecklist=Array.from({length:12},(_,i)=>Object.assign(LIST_META.equipmentChecklist.factory(),{itemName:'裝備 '+i,isPacked:i<7}));
            near.goals[gi].targetTimeSeconds=hmsToSec('3:15:00'); near.bibNumber='B77'; await persist(); renderAll(); await wait(100);
            const a=JSON.stringify(tiles())===JSON.stringify(['pack:打包:7/12','goal:A 目標:3:15:00','bib:號碼布:B77']);
            near.equipmentChecklist.forEach(i=>{ i.isPacked=true; }); renderAll(); await wait(100);
            const p=tile('pack');
            const b=p.querySelector('.rw-tile-label').textContent==='打包 ✓' && p.querySelector('.rw-tile-value').textContent==='12/12' && p.classList.contains('is-done');
            near.equipmentChecklist.forEach((i,k)=>{ i.isPacked=k<7; }); await persist(); renderAll(); await wait(100);
            return a && b; }""")
        c['card_top_opens_race_back_returns'] = self.ev(page, """async()=>{ """ + W + """
            document.querySelector('#focus-panel-slot .nx-main').click(); await wait(500);
            const a=state.selectedId===near.id && location.hash.startsWith('#race=');
            history.back(); await wait(500);
            return a && state.selectedId===null && !!card(); }""")
        c['empty_goal_tile_opens_and_focuses_field'] = self.ev(page, """async()=>{ """ + W + """
            near.goals[gi].targetTimeSeconds=null; await persist(); renderAll(); await wait(100);
            tile('goal').click(); await wait(500);
            const ae=document.activeElement;
            const a=state.selectedId===near.id && !document.getElementById('global-drawer').hidden && !!ae && ae.dataset.path==='goals.'+gi+'.targetTimeSeconds';
            if(!a){ await home(); return false; }
            ae.value='3:20:00'; ae.dispatchEvent(new Event('change',{bubbles:true})); await wait(400);
            await home();
            const v=tile('goal');
            return near.goals[gi].targetTimeSeconds===12000 && !!v && v.querySelector('.rw-tile-value').textContent==='3:20:00'; }""")
        # 已經有值的格子：打開那一區，但不搶焦點（手機會跳出鍵盤蓋住畫面）
        c['filled_tile_opens_without_focus'] = self.ev(page, """async()=>{ """ + W + """
            tile('bib').click(); await wait(500);
            const inp=document.querySelector('#drawer-content [data-path="bibNumber"]');
            const ok=state.selectedId===near.id && !document.getElementById('global-drawer').hidden && !!inp && inp.value==='B77' && document.activeElement!==inp;
            await home(); return ok; }""")
        c['back_from_tile_closes_sheet_then_home'] = self.ev(page, """async()=>{ """ + W + """
            tile('bib').click(); await wait(500);
            history.back(); await wait(500);
            const a=document.getElementById('global-drawer').hidden && state.selectedId===near.id;
            history.back(); await wait(500);
            return a && state.selectedId===null && location.hash===''; }""")
        c['pack_tile_opens_pack_mode'] = self.ev(page, """async()=>{ """ + W + """
            equipmentViewMode='list';
            tile('pack').click(); await wait(500);
            const on=document.querySelector('#drawer-content [data-action="equipment-view"][aria-pressed="true"]');
            const ok=state.selectedId===near.id && !document.getElementById('global-drawer').hidden && !!on && on.dataset.view==='pack'
              && document.querySelectorAll('#drawer-content .pack-list > .pack-row').length===5;
            await home(); return ok; }""")
        # 第三格：有預報才放天氣（手填的、抓到的即時預報）；只有「歷年平均」自動帶進來的氣溫不算預報
        c['third_tile_weather_only_with_forecast'] = self.ev(page, """async()=>{ """ + W + """
            const third=()=>{ const t=document.querySelectorAll('#focus-panel-slot .rw-tile')[2]; return t?[t.dataset.tile,t.querySelector('.rw-tile-label').textContent,t.querySelector('.rw-tile-value').textContent,t.dataset.action||''].join(':'):''; };
            const HA={avgTempC:21.3,avgHumidityPct:70,years:[2021,2022,2023],sampleCount:21,windowDays:3,fetchedAt:new Date().toISOString()};
            const set=async(temp,rain,ha)=>{ near.climateForecast.avgTempC=temp; near.climateForecast.rainProbabilityPct=rain; near.historicalAverageWeather=ha; renderAll(); await wait(80); return third(); };
            const got=[await set(null,null,null), await set(24.4,30,null), await set(18,null,null), await set(21.3,null,HA), await set(21.3,40,HA)];
            const want=['bib:號碼布:B77:focus-tile','weather:降雨 30%:24°C:focus-view-race','weather:天氣:18°C:focus-view-race','bib:號碼布:B77:focus-tile','weather:降雨 40%:21°C:focus-view-race'];
            const ok=JSON.stringify(got)===JSON.stringify(want);
            if(!ok) console.log('third:',got.join(' | '));
            await set(24.4,30,null);
            document.querySelectorAll('#focus-panel-slot .rw-tile')[2].click(); await wait(500);
            const opened=state.selectedId===near.id && document.getElementById('global-drawer').hidden;
            await home(); await set(null,null,null); await persist();
            return ok && opened; }""")
        c['weather_tile_uses_live_forecast_at_start'] = self.ev(page, """async()=>{ """ + W + """
            const d=near.schedule.raceDate;
            near.liveForecast={fetchedAt:new Date().toISOString(),times:[d+'T05:00',d+'T06:00',d+'T07:00'],temp:[19.2,21.6,24.8],precipProb:[10,60,20],gust:[10,12,14]};
            renderAll(); await wait(80);
            const t=document.querySelectorAll('#focus-panel-slot .rw-tile')[2];
            const ok=t.dataset.tile==='weather' && t.querySelector('.rw-tile-label').textContent==='降雨 60%' && t.querySelector('.rw-tile-value').textContent==='22°C';
            near.liveForecast=null; await persist(); renderAll(); return ok; }""")
        # 7 天內、有軌跡、還沒抓：第三格是「抓取預報」，按下去真的抓（這裡把 Open-Meteo 換成假的回應）
        c['fetch_tile_within_7_days_with_track'] = self.ev(page, """async()=>{ """ + W + """
            const third=()=>document.querySelectorAll('#focus-panel-slot .rw-tile')[2];
            near.route.trackPoints=[{lat:25.03,lon:121.56,ele:10},{lat:25.04,lon:121.57,ele:12}];
            renderAll(); await wait(80);
            const far=third().dataset.tile==='bib';
            const keep=near.schedule.raceDate; near.schedule.raceDate=addDaysStr(todayISO(),5);
            near.climateForecast.rainProbabilityPct=50;
            renderAll(); await wait(80);
            const t=third();
            const offer=t.dataset.tile==='weather' && t.dataset.action==='fetch-live-weather' && t.querySelector('.rw-tile-label').textContent==='天氣'
              && t.querySelector('.rw-tile-value').textContent==='抓取預報';
            const calls=[]; const realFetch=window.fetch;
            window.fetch=async(u,o)=>{ const s=String(u); calls.push(s);
              if(s.includes('api.open-meteo.com/v1/forecast')){ await wait(200); const d=near.schedule.raceDate;
                return new Response(JSON.stringify({hourly:{time:[d+'T06:00',d+'T07:00'],temperature_2m:[26.4,27.9],apparent_temperature:[28,29],relative_humidity_2m:[80,78],precipitation_probability:[35,40],wind_speed_10m:[8,9],wind_direction_10m:[90,95],wind_gusts_10m:[15,18]}})); }
              return realFetch(u,o); };
            t.click(); await wait(80);
            const b=third(); const busy=b.disabled && b.querySelector('.rw-tile-value').textContent==='抓取中…';
            await wait(700); window.fetch=realFetch;
            const w=third();
            const got=w.dataset.tile==='weather' && w.dataset.action==='focus-view-race' && w.querySelector('.rw-tile-label').textContent==='降雨 35%'
              && w.querySelector('.rw-tile-value').textContent==='26°C' && calls.some(s=>s.includes('latitude=25.03')) && !!near.liveForecast;
            if(!(far&&offer&&busy&&got)) console.log('fetch:',far,offer,busy,got);
            near.schedule.raceDate=keep; near.route.trackPoints=[]; near.liveForecast=null;
            near.climateForecast=emptyRace('x','road_running','registered','').climateForecast; await persist(); renderAll();
            return far && offer && busy && got; }""")
        # 高度要量卡片自己的：v4.7.0 起筆電右邊有今日一句、兩張一樣高（v47 有測），句子長的那幾天卡片的框
        # 會被拉到 221px。原本直接量框，結果跟著「今天是哪一句」變——v4.10.0 回歸時（10/3）才第一次失敗，
        # 換回 v4.9.0 一樣失敗。這一項要看的是「封面照不會把卡片撐高」，所以量的時候先關掉今日一句
        c['cover_photo_is_card_background'] = self.ev(page, """async()=>{ """ + W + """
            const cv=document.createElement('canvas'); cv.width=320; cv.height=180; const g=cv.getContext('2d'); g.fillStyle='#fff'; g.fillRect(0,0,320,180);
            near.coverImage=cv.toDataURL('image/jpeg',.9); near.coverImageAspect=320/180; await persist();
            localStorage.setItem(DAILY_QUOTE_PREF_KEY,'off'); renderAll(); await wait(150);
            try{
              const f=card(); const bi=getComputedStyle(f.querySelector('.nx-head')).backgroundImage;
              return !document.querySelector('#focus-panel-slot .dq-card') && f.classList.contains('has-cover') && !f.querySelector('.focus-mesh') && bi.includes('url(') && bi.includes('data:image')
                && f.querySelectorAll('.rw-tile').length===3 && f.getBoundingClientRect().height<=170;
            }finally{ localStorage.removeItem(DAILY_QUOTE_PREF_KEY); renderAll(); await wait(150); } }""")
        # 最難讀的情況：封面照是一整片白（雪地、天空）。用頁首漸層算出每個字底下的顏色——淺色、深色模式都一樣
        COVER_READ = """()=>{ const head=document.querySelector('#focus-panel-slot .has-cover .nx-head'); if(!head) return ['no cover'];
            const bi=getComputedStyle(head).backgroundImage;
            const stops=[...bi.matchAll(/rgba?\\(([\\d.]+), ([\\d.]+), ([\\d.]+)(?:, ([\\d.]+))?\\)/g)].map(m=>[+m[1],+m[2],+m[3],m[4]==null?1:+m[4]]);
            if(stops.length<2) return ['no gradient'];
            const hb=head.getBoundingClientRect();
            const lum=c=>{ const v=c.map(x=>{ x/=255; return x<=0.03928?x/12.92:Math.pow((x+0.055)/1.055,2.4); }); return 0.2126*v[0]+0.7152*v[1]+0.0722*v[2]; };
            const over=(top,a,base)=>top.map((x,i)=>x*a+base[i]*(1-a));
            const bad=[]; let n=0;
            head.querySelectorAll('.focus-panel-label,.taper-badge,.nx-dismiss,.nx-name,.nx-meta,.nx-count b,.nx-count span').forEach(el=>{ n++;
              const b=el.getBoundingClientRect(); const p=Math.max(0,Math.min(1,(b.top-hb.top)/hb.height));
              const s0=stops[0], s1=stops[stops.length-1]; const a=s0[3]+(s1[3]-s0[3])*p; const col=s0.slice(0,3).map((x,i)=>x+(s1[i]-x)*p);
              let bg=over(col,a,[255,255,255]);
              const own=(getComputedStyle(el).backgroundColor.match(/[\\d.]+/g)||[]).map(Number); if(own.length===4&&own[3]>0) bg=over(own.slice(0,3),own[3],bg);
              const fm=getComputedStyle(el).color.match(/[\\d.]+/g).map(Number); const fg=fm.length===4?over(fm.slice(0,3),fm[3],bg):fm.slice(0,3);
              const L1=lum(fg),L2=lum(bg), cr=(Math.max(L1,L2)+.05)/(Math.min(L1,L2)+.05);
              const cs=getComputedStyle(el), fs=parseFloat(cs.fontSize), bold=parseInt(cs.fontWeight)>=700;
              if(cr<((fs>=24||(fs>=18.66&&bold))?3:4.5)) bad.push(el.className+' '+cr.toFixed(2)); });
            return n>=7?bad:['only '+n]; }"""
        page.evaluate("""async()=>{ """ + W + """ near.trainingPlan.taperStartDate=addDaysStr(todayISO(),-2); renderAll(); await wait(100); }""")
        light = self.ev(page, COVER_READ)
        light = ['error'] if light is False else light
        page.evaluate("()=>applyTheme('dark')")
        page.wait_for_timeout(200)
        dark = self.ev(page, COVER_READ)
        dark = ['error'] if dark is False else dark
        page.evaluate("()=>applyTheme('light')")
        page.wait_for_timeout(200)
        if light or dark:
            print('   cover contrast:', light, dark)
        c['cover_text_readable_on_white_photo'] = not light and not dark
        c['taper_badge_only_in_taper'] = self.ev(page, """async()=>{ """ + W + """
            near.coverImage=null; renderAll(); await wait(80);
            const b=document.querySelector('#focus-panel-slot .nx-top .taper-badge');
            const on=!!b && b.textContent==='進入減量期';
            near.trainingPlan.taperStartDate=addDaysStr(todayISO(),3); renderAll(); await wait(80);
            const off=!document.querySelector('#focus-panel-slot .taper-badge');
            near.trainingPlan.taperStartDate=''; await persist(); renderAll(); return on && off; }""")
        c['race_day_says_today'] = self.ev(page, """async()=>{ """ + W + """
            const keep=near.schedule.raceDate; near.schedule.raceDate=todayISO(); renderAll(); await wait(80);
            const b=document.querySelector('#focus-panel-slot .nx-count b');
            const ok=!!b && b.classList.contains('nx-today') && b.textContent==='今天' && !document.querySelector('#focus-panel-slot .nx-count span');
            near.schedule.raceDate=keep; await persist(); renderAll(); return ok; }""")
        c['dismiss_hides_card'] = self.ev(page, """async()=>{ """ + W + """
            document.querySelector('#focus-panel-slot [data-action="dismiss-focus-panel"]').click(); await wait(200);
            const gone=!card() && state.focusDismissedId===near.id; renderAll(); await wait(100);
            const stays=!card(); state.focusDismissedId=null; renderAll(); await wait(100);
            return gone && stays && !!card(); }""")
        # 筆電看不到手機那份「即將到來」清單：「比完了嗎？」和「下一場」兩張都放
        c['laptop_shows_prompt_and_card'] = self.ev(page, """async()=>{ """ + W + """
            const y=emptyRace('昨天的路跑','road_running','registered',addDaysStr(todayISO(),-1)); state.races.push(y); await persist(); renderAll(); await wait(150);
            const slot=document.getElementById('focus-panel-slot');
            const ok=!!slot.querySelector('.result-prompt') && !!slot.querySelector('.focus-panel');
            state.races=state.races.filter(r=>r!==y); await persist(); renderAll(); return ok; }""")
        # ================= ③ 獎牌牆 =================
        c['wall_has_every_finished_race_newest_first'] = self.ev(page, """async()=>{ """ + W + """
            scrollTo(0,0); document.getElementById('cal-view-toggle').click(); await wait(800);
            // v4.5.1 起每一年可以收起來、預設只展開今年：全部展開之後才數得到每一場
            const all=document.querySelector('#calendar [data-action="wall-toggle-all"]'); if(all&&all.dataset.open==='1'){ all.click(); await wait(200); }
            const done=state.races.filter(r=>!r.deletedAt&&r.status==='completed').sort((a,b)=>(b.schedule.raceDate||'').localeCompare(a.schedule.raceDate||''));
            const ids=[...document.querySelectorAll('#calendar .photo-card')].map(b=>b.dataset.id);
            return state.viewMode==='grid' && done.length>90 && JSON.stringify(ids)===JSON.stringify(done.map(r=>r.id))
              && document.querySelectorAll('#calendar .photo-card.bib-card').length===done.length; }""")
        # v4.4.0 獎牌牆改成號碼布牆：卡片上寫什麼、運動別顏色、PB 印章、拍立得、對比、各種寬度放不放得下，都改在 v44 群組檢查
        c['wall_card_opens_race_back_to_wall'] = self.ev(page, """async()=>{ """ + W + """
            const el=document.querySelector('#calendar .photo-card'); const id=el.dataset.id; el.click(); await wait(500);
            const ok=state.selectedId===id; await home(); return ok && state.selectedId===null && state.viewMode==='grid' && !!document.querySelector('#calendar .photo-card'); }""")
        c['empty_wall_and_no_best_strip'] = self.ev(page, """async()=>{ """ + W + """
            const keep=state.races; state.races=keep.filter(r=>r.status!=='completed'); renderCalendar(); await wait(100);
            const wrap=document.querySelector('#calendar .photo-grid-wrap');
            const ok=!!wrap && wrap.textContent.includes('還沒有已完賽的賽事') && !wrap.querySelector('.photo-card');
            state.viewMode='table'; renderCalendar(); await wait(100);
            const noBest=!!document.querySelector('#calendar .table-view') && !document.querySelector('#calendar .tv-best');
            state.races=keep; state.viewMode='grid'; renderCalendar(); return ok && noBest; }""")
        # ================= ④ 表格排序、各距離最佳 =================
        ROWS = "[...document.querySelectorAll('#calendar .table-view-row')]"
        TIMES = ROWS + ".map(r=>{ const t=r.cells[5].textContent.replace('PB','').trim(); return t==='—'?null:hmsToSec(t); })"
        c['table_headers_sortable_default_by_year'] = self.ev(page, """async()=>{ """ + W + """
            document.getElementById('cal-table-toggle').click(); await wait(500);
            const ths=[...document.querySelectorAll('.table-view thead th')];
            const sorts=ths.map(th=>th.getAttribute('aria-sort')||'-').join(',');
            return state.viewMode==='table' && sorts==='descending,none,-,none,none,none' && !!document.querySelector('.table-year-row') && !document.querySelector('.tv-sortbar')
              && ths.filter(th=>th.querySelector('button.tv-sort-btn')).length===5 && !ths[2].querySelector('button') && ths[2].textContent.trim()==='狀態'; }""")
        c['time_sort_flat_fastest_first_blank_last'] = self.ev(page, """async()=>{ """ + W + """
            document.querySelector('.tv-sort-btn[data-key="time"]').click(); await wait(300);
            const secs=""" + TIMES + """; const firstNull=secs.indexOf(null); const timed=secs.slice(0,firstNull<0?secs.length:firstNull);
            const th=document.querySelector('.tv-sort-btn[data-key="time"]').closest('th'); const bar=document.querySelector('.tv-sortbar');
            return !document.querySelector('.table-year-row') && secs.length===filteredRaces().length && timed.length>90 && firstNull>0
              && timed.every((v,i)=>i===0||v>=timed[i-1]) && secs.slice(firstNull).every(v=>v==null)
              && th.getAttribute('aria-sort')==='ascending' && th.querySelector('.tv-arrow').textContent==='▲'
              && !!bar && bar.querySelector('span').textContent==='依「完賽時間」排序（快 → 慢）・'+secs.length+' 場'; }""")
        c['click_again_reverses_blank_still_last'] = self.ev(page, """async()=>{ """ + W + """
            document.querySelector('.tv-sort-btn[data-key="time"]').click(); await wait(300);
            const secs=""" + TIMES + """; const firstNull=secs.indexOf(null); const timed=secs.slice(0,firstNull);
            const th=document.querySelector('.tv-sort-btn[data-key="time"]').closest('th');
            return firstNull>0 && timed.every((v,i)=>i===0||v<=timed[i-1]) && secs.slice(firstNull).every(v=>v==null) && th.getAttribute('aria-sort')==='descending'
              && th.querySelector('.tv-arrow').textContent==='▼' && document.querySelector('.tv-sortbar span').textContent.includes('（慢 → 快）'); }""")
        # 設計稿的情境：搜「半程」再點「完賽時間」，第一列就是最快的一場半馬
        c['search_then_sort_finds_fastest_half'] = self.ev(page, """async()=>{ """ + W + """
            const half=state.races.filter(r=>!r.deletedAt&&r.status==='completed'&&r.route.distanceKm===21.0975).sort((a,b)=>a.schedule.raceDate.localeCompare(b.schedule.raceDate))[0];
            half.results.chipTimeSeconds=hmsToSec('1:38:12'); await persist();
            document.querySelector('.tv-chip[data-action="table-sort-reset"]').click(); await wait(300);
            const s=document.getElementById('search-input'); s.value='半程'; s.dispatchEvent(new Event('input',{bubbles:true})); await wait(600);
            document.querySelector('.tv-sort-btn[data-key="time"]').click(); await wait(300);
            const rows=""" + ROWS + """;
            const ok=rows.length>5 && rows.every(r=>r.cells[1].textContent.includes('半程')) && rows[0].dataset.id===half.id && rows[0].cells[5].textContent.replace('PB','').trim()==='1:38:12';
            s.value=''; s.dispatchEvent(new Event('input',{bubbles:true})); await wait(600);
            return ok && document.querySelectorAll('#calendar .table-view-row').length===filteredRaces().length; }""")
        c['reset_chip_back_to_year_groups'] = self.ev(page, """async()=>{ """ + W + """
            const chip=document.querySelector('.tv-chip[data-action="table-sort-reset"]'); if(!chip) return false;
            const label=chip.textContent.trim(); chip.click(); await wait(300);
            return label==='回到依年份分組 ✕' && tableSort.key==='date' && tableSort.dir==='desc' && !!document.querySelector('.table-year-row') && !document.querySelector('.tv-sortbar'); }""")
        c['date_header_oldest_first_keeps_years'] = self.ev(page, """async()=>{ """ + W + """
            document.querySelector('.tv-sort-btn[data-key="date"]').click(); await wait(300);
            const years=[...document.querySelectorAll('.table-year-row')].map(r=>r.dataset.year);
            const chip=document.querySelector('.tv-chip');
            const ok=tableSort.dir==='asc' && years[0]==='2015' && years.every((y,i)=>i===0||y>=years[i-1]) && !!chip && chip.textContent.trim()==='回到新到舊 ✕'
              && document.querySelector('.tv-sort-btn[data-key="date"]').closest('th').getAttribute('aria-sort')==='ascending';
            chip.click(); await wait(300); return ok && tableSort.dir==='desc'; }""")
        c['name_distance_elevation_sort'] = self.ev(page, """async()=>{ """ + W + """
            const col=i=>""" + ROWS + """.map(r=>r.cells[i].textContent.trim());
            document.querySelector('.tv-sort-btn[data-key="name"]').click(); await wait(300);
            const names=col(1), want=filteredRaces().map(r=>r.name).sort((a,b)=>a.localeCompare(b,'zh-Hant'));
            const nameOk=JSON.stringify(names)===JSON.stringify(want);
            document.querySelector('.tv-sort-btn[data-key="distance"]').click(); await wait(300);
            const d=col(3).map(x=>x==='—'?null:Number(x)), dn=d.filter(x=>x!=null);
            const distOk=dn[0]===100 && dn.every((v,i)=>i===0||v<=dn[i-1]) && d.slice(dn.length).every(v=>v==null);
            const ev=state.races.filter(r=>!r.deletedAt&&r.status==='completed').slice(0,3); [1200,300,2500].forEach((m,i)=>{ ev[i].route.elevationGainM=m; }); await persist();
            document.querySelector('.tv-sort-btn[data-key="elevation"]').click(); await wait(300);
            const e=col(4); const elevOk=e.slice(0,3).join()==='2500,1200,300' && e.slice(3).every(x=>x==='—');
            tableSort={key:'date',dir:'desc'}; renderCalendar(); await wait(100);
            if(!(nameOk&&distOk&&elevOk)) console.log('sorts:',nameOk,distOk,elevOk);
            return nameOk && distOk && elevOk; }""")
        c['best_strip_per_distance_matches_career_pb'] = self.ev(page, """()=>{
            const cards=[...document.querySelectorAll('#calendar .tv-best-card')];
            const fm=cards.find(x=>x.dataset.best==='fm'), hm=cards.find(x=>x.dataset.best==='hm');
            const half=state.races.find(r=>r.results.chipTimeSeconds===hmsToSec('1:38:12'));
            const labels=cards.map(x=>x.querySelector('.tv-best-label').textContent).join('|');
            return cards.map(x=>x.dataset.best).join()==='fm,hm,10k,tri51' && labels==='全馬最佳|半馬最佳|10K 最佳|51.5K 鐵人最佳'
              && fm.querySelector('b').textContent===secToHMS(computeCareerStats().marathonPB) && fm.dataset.id===marathonPbRace().id
              && hm.dataset.id===half.id && hm.querySelector('b').textContent==='1:38:12' && hm.querySelector('.tv-best-race').textContent===half.name; }""")
        c['best_card_opens_race'] = self.ev(page, """async()=>{ """ + W + """
            const hm=document.querySelector('#calendar .tv-best-card[data-best="hm"]'); const id=hm.dataset.id; hm.click(); await wait(500);
            const ok=state.selectedId===id; await home(); return ok && state.selectedId===null && state.viewMode==='table' && !!document.querySelector('.tv-best'); }""")
        # 42 公里的自行車賽不是全馬：各距離最佳、生涯數據的全馬 PB、榮譽櫃都不算它；越野全馬算
        c['cycling_42k_is_not_marathon_pb'] = self.ev(page, """async()=>{ """ + W + """
            const before=computeCareerStats().marathonPB;
            const bike=emptyRace('42K 自行車繞圈賽','cycling','completed','2025-06-01'); bike.route.distanceKm=42.195; bike.results.chipTimeSeconds=hmsToSec('1:05:00');
            state.races.push(bike); await persist(); renderCalendar(); await wait(150);
            const fm=document.querySelector('#calendar .tv-best-card[data-best="fm"]');
            const a=computeCareerStats().marathonPB===before && marathonPbRace().id!==bike.id && fm.dataset.id!==bike.id && computeHallOfFameData().pbRace.id!==bike.id;
            const trail=emptyRace('越野全馬','trail_running','completed','2025-07-01'); trail.route.distanceKm=42.195; trail.results.chipTimeSeconds=hmsToSec('3:05:00');
            state.races.push(trail); await persist(); renderCalendar(); await wait(150);
            const fm2=document.querySelector('#calendar .tv-best-card[data-best="fm"]');
            const b=computeCareerStats().marathonPB===hmsToSec('3:05:00') && fm2.dataset.id===trail.id;
            state.races=state.races.filter(r=>r!==bike&&r!==trail); await persist(); renderCalendar();
            return a && b; }""")
        c['best_strip_only_in_table'] = self.ev(page, """async()=>{ """ + W + """
            state.viewMode='calendar'; renderAll(); await wait(150); const cal=!document.querySelector('.tv-best');
            state.viewMode='grid'; renderAll(); await wait(150); const grid=!document.querySelector('.tv-best');
            state.viewMode='table'; renderAll(); await wait(150); const table=!!document.querySelector('.tv-best');
            state.viewMode='calendar'; renderAll(); return cal && grid && table; }""")
        # （版本號的檢查跟著最新的群組走，v4.3.1 起在 v431）
        # ================= 手機 =================
        pctx, pp = self._ctx(page.context.browser, {'width': 390, 'height': 844}, touch=True)
        # 打開 App 的第一個畫面就看得到第一場賽事（v4.2 是 1,044px，在畫面外）。
        # 量的時候關掉今日一句：v4.7.0 起它在下一場卡上面，高度每天不同（中文版面 102–194px，原文是日文、
        # 英文的句子多兩行原文），56 句裡有 27 句會把第一場推到 844px 的下緣之外（只露出上緣；日文 0 句、
        # 英文 1 句）。原本直接量，結果跟著「今天是哪一句」變，v4.10.0 回歸時（10/3）才第一次失敗、
        # v4.9.0 一樣失敗。這一項守的是 v4.3.0 的「下一場卡夠精簡」；今日一句打開時的第一個畫面要不要
        # 調整，是 HANDOFF「待你回報」裡等決定的事，不在這裡用當天的句子碰運氣
        c['phone_first_race_on_first_screen'] = self.ev(pp, """async()=>{ """ + W + """
            near.schedule.startTime='06:30'; near.bibNumber='B77'; near.goals[gi].targetTimeSeconds=hmsToSec('3:15:00');
            near.equipmentChecklist=Array.from({length:12},(_,i)=>Object.assign(LIST_META.equipmentChecklist.factory(),{itemName:'裝備 '+i,isPacked:i<7}));
            await persist(); localStorage.setItem(DAILY_QUOTE_PREF_KEY,'off'); renderAll(); scrollTo(0,0); await wait(200);
            try{
              const f=card(), first=document.querySelector('#calendar .cal-list-item'); if(!f||!first) return false;
              const fb=f.getBoundingClientRect(), lb=first.getBoundingClientRect();
              return !document.querySelector('#focus-panel-slot .dq-card') && state.phoneView==='list' && fb.height<=200 && lb.top>fb.bottom && lb.bottom<=innerHeight && first.dataset.id===near.id;
            }finally{ localStorage.removeItem(DAILY_QUOTE_PREF_KEY); renderAll(); scrollTo(0,0); await wait(200); } }""")
        # 手機清單：「比完了嗎？」在的時候先不放「下一場」卡（它就在清單第一列）；月曆上兩張都放；按「之後再說」卡片回來
        c['phone_list_prompt_takes_card_place'] = self.ev(pp, """async()=>{ """ + W + """
            const y=emptyRace('昨天的路跑','road_running','registered',addDaysStr(todayISO(),-1)); state.races.push(y); await persist(); renderAll(); await wait(200);
            const slot=document.getElementById('focus-panel-slot');
            const list=!!slot.querySelector('.result-prompt') && !slot.querySelector('.focus-panel');
            const firstUp=document.querySelector('#calendar .cal-list-item').dataset.id===near.id;
            document.querySelector('.view-seg [data-phone-view="calendar"]').click(); await wait(300);
            const cal=!!slot.querySelector('.result-prompt') && !!slot.querySelector('.focus-panel');
            document.querySelector('.view-seg [data-phone-view="list"]').click(); await wait(300);
            const back=!!slot.querySelector('.result-prompt') && !slot.querySelector('.focus-panel');
            document.querySelector('.result-prompt [data-action="result-later"]').click(); await wait(300);
            const later=!slot.querySelector('.result-prompt') && !!slot.querySelector('.focus-panel');
            state.races=state.races.filter(r=>r!==y); await persist(); renderAll();
            if(!(list&&firstUp&&cal&&back&&later)) console.log('prompt:',list,firstUp,cal,back,later);
            return list && firstUp && cal && back && later; }""")
        pctx.close()
        # 三格在 360／390 × 三種語言 × 三種字級 × 最寬的內容：值不被截掉、標籤不超出格子、沒有橫向捲動。
        # 「12/12」「11:50:00」（超馬）「A12345」、降雨 100%、「Get forecast」「抓取中…」是實際會出現的最寬的字
        FIT = """async()=>{ """ + W + """
            const list=(n,p)=>Array.from({length:n},(_,i)=>Object.assign(LIST_META.equipmentChecklist.factory(),{itemName:'x'+i,isPacked:i<p}));
            const cases={
              full:()=>{ near.equipmentChecklist=list(12,12); near.goals[gi].targetTimeSeconds=hmsToSec('11:50:00'); near.bibNumber='A12345'; near.liveForecast=null; near.route.trackPoints=[]; near.schedule.raceDate=addDaysStr(todayISO(),9); },
              weather:()=>{ near.equipmentChecklist=list(12,7); near.goals[gi].targetTimeSeconds=hmsToSec('3:30:00'); near.liveForecast={fetchedAt:new Date().toISOString(),times:['2026-01-01T06:00'],temp:[-12.4],precipProb:[100],gust:[30]}; },
              empty:()=>{ near.equipmentChecklist=[]; near.goals[gi].targetTimeSeconds=null; near.bibNumber=''; near.liveForecast=null; near.route.trackPoints=[{lat:25,lon:121,ele:10}]; near.schedule.raceDate=addDaysStr(todayISO(),5); },
              busy:()=>{ weatherFetchingRaceId=near.id; } };
            const bad=[];
            for(const lang of ['zh','ja','en']){ setLang(lang); await wait(150);
              for(const fs of ['small','medium','large']){ applyFontScale(fs);
                for(const [k,fn] of Object.entries(cases)){ fn(); renderFocusPanel(); await wait(30);
                  const f=card(); if(!f){ bad.push(lang+fs+k+' nocard'); continue; } const cr=f.getBoundingClientRect();
                  const ts=[...f.querySelectorAll('.rw-tile')]; if(ts.length!==3) bad.push(lang+fs+k+' tiles='+ts.length);
                  ts.forEach(t=>{ const st=getComputedStyle(t), inner=t.getBoundingClientRect().right-parseFloat(st.paddingRight);
                    const v=t.querySelector('.rw-tile-value'), lb=t.querySelector('.rw-tile-label'), rg=document.createRange(); rg.selectNodeContents(lb);
                    if(v.scrollWidth>v.clientWidth+1) bad.push(lang+' '+fs+' '+k+' cut '+v.textContent);
                    if(rg.getBoundingClientRect().right>inner+0.5) bad.push(lang+' '+fs+' '+k+' label '+lb.textContent); });
                  f.querySelectorAll('.nx-name,.nx-meta,.nx-count,.nx-dismiss,.focus-panel-label').forEach(e=>{ const b=e.getBoundingClientRect(); if(b.right>cr.right+0.5||b.left<cr.left-0.5) bad.push(lang+' '+fs+' '+k+' out '+e.className); });
                  if(document.documentElement.scrollWidth>innerWidth) bad.push(lang+' '+fs+' '+k+' hscroll');
                }
                weatherFetchingRaceId=null; } }
            setLang('zh'); applyFontScale('medium'); renderFocusPanel();
            if(bad.length) console.log('fit:',bad.slice(0,12).join(' | '));
            return bad.length===0; }"""
        # 700：直拿的小平板、縮窄的視窗（筆電的一列排法要到 768px 才放得下）
        for w in (390, 360, 700):
            fctx, fp = self._ctx(page.context.browser, {'width': w, 'height': 800}, touch=w < 641)
            kind = 'phone' if w < 641 else 'tablet'
            c[f'{kind}{w}_card_tiles_fit'] = self.ev(fp, FIT)
            fctx.close()
        # ================= 英文、日文 =================
        ectx, ep = self._ctx(page.context.browser, DESKTOP, lang='en')
        c['english_card_and_table'] = self.ev(ep, """async()=>{ """ + W + """
            near.schedule.startTime='06:30'; await persist(); renderAll(); await wait(200);
            const f=card(); const unit=f.querySelector('.nx-count span').textContent, meta=f.querySelector('.nx-meta').textContent;
            const labels=[...f.querySelectorAll('.rw-tile-label')].map(x=>x.textContent).join('|');
            const keep=near.schedule.raceDate; near.schedule.raceDate=addDaysStr(todayISO(),1); renderAll(); await wait(100);
            const one=document.querySelector('#focus-panel-slot .nx-count span').textContent;
            near.schedule.raceDate=keep; await persist();
            state.viewMode='table'; tableSort={key:'date',dir:'desc'}; renderAll(); await wait(200);
            document.querySelector('.tv-sort-btn[data-key="time"]').click(); await wait(300);
            const n=document.querySelectorAll('#calendar .table-view-row').length;
            const bar=document.querySelector('.tv-sortbar span').textContent, chip=document.querySelector('.tv-chip').textContent.trim();
            const heads=[...document.querySelectorAll('.table-view thead th')].map(th=>th.textContent.replace(/[▲▼↕]/g,'').trim()).join('|');
            const best=[...document.querySelectorAll('.tv-best-label')].map(x=>x.textContent).join('|');
            const s=document.getElementById('search-input'); s.value='遠的比賽'; s.dispatchEvent(new Event('input',{bubbles:true})); await wait(600);
            const single=document.querySelector('.tv-sortbar span').textContent;
            s.value=''; s.dispatchEvent(new Event('input',{bubbles:true})); await wait(400);
            const want={unit:'days',one:'day',labels:'Packed|Goal A|Bib',bar:'Sorted by “Finish Time” (fastest first) · '+n+' races',chip:'Back to grouping by year ✕',
              heads:'Date|Race Name|Status|Distance(km)|Elevation(m)|Finish Time',best:'Best marathon|Best half|Best 10K|Best 51.5K triathlon',single:'Sorted by “Finish Time” (fastest first) · 1 race'};
            const got={unit,one,labels,bar,chip,heads,best,single};
            const bad=Object.keys(want).filter(k=>got[k]!==want[k]);
            const metaOk=/^\\d\\d\\/\\d\\d \\((Sun|Mon|Tue|Wed|Thu|Fri|Sat)\\) 06:30 · 台北市$/.test(meta);
            if(bad.length||!metaOk) console.log('en:',bad.map(k=>k+'='+got[k]).join(' | '),meta);
            return bad.length===0 && metaOk; }""")
        ectx.close()
        jctx, jp = self._ctx(page.context.browser, DESKTOP, lang='ja')
        c['japanese_table_sort_bar'] = self.ev(jp, """async()=>{ const wait=ms=>new Promise(s=>setTimeout(s,ms));
            state.viewMode='table'; renderAll(); await wait(200);
            document.querySelector('.tv-sort-btn[data-key="distance"]').click(); await wait(300);
            const n=document.querySelectorAll('#calendar .table-view-row').length;
            return document.querySelector('.tv-sortbar span').textContent==='「距離(km)」で並べ替え（長い順）・'+n+' レース'
              && document.querySelector('.tv-chip').textContent.trim()==='年ごとの表示に戻す ✕'
              && [...document.querySelectorAll('.tv-best-label')].map(x=>x.textContent).join('|')==='フル最速|ハーフ最速|10K 最速|51.5K トライアスロン最速'; }""")
        jctx.close()


TRAINING_SEED_JS = r"""window.__seedTrainings=async function(){
  const loop=[]; for(let i=0;i<=40;i++){ const a=i/40*Math.PI*2; loop.push(+(0.5+0.42*Math.cos(a)).toFixed(3),+(0.5+0.3*Math.sin(a*2)).toFixed(3)); }
  const t=todayISO();
  const mk=(d,st,sport,km,sec,hr,thumb,name)=>migrateTraining({date:d,startTime:st,sport,distanceKm:km,durationSeconds:sec,avgHr:hr,name:name||'',thumb,
    fingerprint:'fp'+d+st,source:'fit',importedAt:new Date().toISOString()});
  trainings=[mk(t,'06:10','run',10.2,3120,148,loop,'晨跑'),mk(addDaysStr(t,-1),'19:30','ride',32.5,4500,131,loop),mk(addDaysStr(t,-2),'07:00','run',5.0,1620,155,null,'跑步機'),
    mk(addDaysStr(t,-40),'06:00','run',21.1,6900,150,loop),mk(addDaysStr(t,-400),'06:00','swim',1.5,2400,140,null)];
  await saveJson(TRAININGS_KEY,trainings);
};"""


class V431Fixes(Group):
    """v4.3.1：訓練頁跟著淺色／深色模式、字看得清楚；訓練紀錄跨裝置同步（同一個月兩台都在寫
    不會互相洗掉、同一個檔在兩台各匯入一次只留一筆、雲端拒絕時看得到）；安全性規則涵蓋每個路徑。"""

    ECHO = ('trtheme:', 'trsync:')

    def _echo(self, msg):
        if msg.text.startswith(self.ECHO):
            print('   ', msg.text[:300])

    def ev(self, pg, js):
        # 一項檢查拋出例外：記成這一項失敗、印出原因，後面照跑
        try:
            return pg.evaluate(js)
        except Exception as exc:                      # noqa: BLE001
            print('    ⚠', str(exc).split('\n')[0][:200])
            return False

    def body(self, page):
        c = self.checks
        page.on('console', self._echo)
        page.add_script_tag(content=CONTRAST_JS)
        page.add_script_tag(content=TRAINING_SEED_JS)
        page.add_script_tag(content=FAKE_CLOUD_JS)
        page.add_style_tag(content='.badge-unbox-overlay,.foreground-toast{display:none!important}')
        page.evaluate("()=>__seedTrainings()")
        # ================= 訓練頁跟著主題 =================
        # 每一段字（含按鈕、日期、分組標題）都要達 4.5:1（大字 3:1）；頁面底色就是首頁的底色
        READ = """()=>{ const ov=document.getElementById('training-overlay'); const bad=[]; let n=0;
            ov.querySelectorAll('*').forEach(el=>{ const r=el.getBoundingClientRect(); if(!(r.width>0&&r.height>0)) return;
              if(![...el.childNodes].some(x=>x.nodeType===3&&x.textContent.trim())) return;
              if(el.closest('svg')) return;   // 縮圖裡的「≈」是裝飾
              n++; const cs=getComputedStyle(el), fs=parseFloat(cs.fontSize), bold=parseInt(cs.fontWeight)>=700;
              const cr=__contrast(el); if(cr<((fs>=24||(fs>=18.66&&bold))?3:4.5)) bad.push(el.tagName+'.'+(el.className||'')+' '+el.textContent.trim().slice(0,10)+' '+cr.toFixed(2)); });
            const pr=document.createElement('div'); pr.style.background='var(--paper)'; document.body.appendChild(pr); const paper=getComputedStyle(pr).backgroundColor; pr.remove();
            return {n,bad,bg:getComputedStyle(ov).backgroundColor,paper}; }"""
        THEME = """async(theme)=>{ const wait=ms=>new Promise(s=>setTimeout(s,ms));
            const st=document.createElement('style'); st.id='__nt'; st.textContent='*{transition:none!important}'; document.head.appendChild(st);
            applyTheme(theme); await wait(150); openTrainingOverlay(); await wait(150);
            const res=[]; for(const p of ['week','all']){ document.querySelector('[data-training-period="'+p+'"]').click(); await wait(120);
              if(p==='all'){ const m=document.querySelector('[data-training-month][aria-expanded="false"]'); if(m){ m.click(); await wait(80); } }
              res.push((""" + READ + """)()); }
            closeTrainingOverlay(); applyTheme('light'); await wait(150); st.remove();
            const bad=res.flatMap(r=>r.bad); if(bad.length) console.log('trtheme:',theme,bad.slice(0,8).join(' | '));
            return {bad:bad.length,n:res.reduce((a,r)=>a+r.n,0),bg:res[0].bg,paper:res[0].paper}; }"""
        light = self.ev(page, "()=>(" + THEME + ")('light')")
        dark = self.ev(page, "()=>(" + THEME + ")('dark')")
        c['training_page_follows_light_theme'] = bool(light) and light['bad'] == 0 and light['n'] > 20 and light['bg'] == light['paper'] and light['bg'] != 'rgb(15, 19, 22)'
        c['training_page_follows_dark_theme'] = bool(dark) and dark['bad'] == 0 and dark['n'] > 20 and dark['bg'] == dark['paper']
        if light and dark:
            print('    ', 'light', light['bg'], 'dark', dark['bg'])
        # 縮圖：淺色是淺底、深一點的金色線；深色是深底亮金線；線跟底至少 3:1
        c['training_thumb_follows_theme'] = self.ev(page, """async()=>{ const wait=ms=>new Promise(s=>setTimeout(s,ms));
            const lum=c=>{ const v=c.match(/[\\d.]+/g).slice(0,3).map(Number).map(x=>{ x/=255; return x<=0.03928?x/12.92:Math.pow((x+0.055)/1.055,2.4); }); return 0.2126*v[0]+0.7152*v[1]+0.0722*v[2]; };
            const read=()=>{ const th=document.querySelector('#training-overlay .training-thumb'); const line=th.querySelectorAll('path')[1];
              const bg=getComputedStyle(th).backgroundColor, fg=getComputedStyle(line).stroke; const a=lum(bg),b=lum(fg);
              return {bg,fg,cr:(Math.max(a,b)+.05)/(Math.min(a,b)+.05)}; };
            applyTheme('light'); openTrainingOverlay(); document.querySelector('[data-training-period="week"]').click(); await wait(100);
            const l=read(); applyTheme('dark'); await wait(100); const d=read(); applyTheme('light'); closeTrainingOverlay();
            const surf=getComputedStyle(document.documentElement).getPropertyValue('--surface').trim();
            if(!(l.cr>=3&&d.cr>=3&&l.bg!==d.bg&&l.fg!==d.fg)) console.log('trtheme: thumb',JSON.stringify(l),JSON.stringify(d));
            return l.cr>=3 && d.cr>=3 && l.bg!==d.bg && l.fg!==d.fg; }""")
        # 英文的月份：原本拿不存在的 state.lang 判斷語言，英文一直顯示「Month 9」
        c['training_month_names_in_english'] = self.ev(page, """async()=>{ const wait=ms=>new Promise(s=>setTimeout(s,ms));
            setLang('en'); await wait(150); openTrainingOverlay(); document.querySelector('[data-training-period="all"]').click(); await wait(120);
            const labels=[...document.querySelectorAll('#training-overlay [data-training-month] .training-group-label')].map(x=>x.textContent);
            const want=new Date(todayISO()+'T00:00:00').toLocaleString('en-US',{month:'long'});
            closeTrainingOverlay(); setLang('zh'); await wait(150);
            if(labels[0]!==want) console.log('trtheme: months',labels.join(','));
            return labels.length>0 && labels[0]===want && !labels.some(x=>/Month|月/.test(x)); }""")
        # ================= 安全性規則涵蓋 App 用到的每一個雲端路徑 =================
        # v3.76.0 新增了 users/{uid}/trainings，規則沒跟著加：讀寫全被擋，畫面上什麼都看不到
        import pathlib as _pl, re as _re
        src = _pl.Path(APP).read_text(encoding='utf-8')
        rules_path = _pl.Path(os.path.dirname(os.path.abspath(__file__))) / 'firestore.rules'
        rules = rules_path.read_text(encoding='utf-8') if rules_path.exists() else ''
        app_paths = set()
        for kind, args in _re.findall(r"\b(collection|doc)\(db,([^)]*)\)", src):
            segs = [a.strip() for a in args.split(',')]
            segs = [a[1:-1] if a[:1] in "'\"" else '*' for a in segs]
            if kind == 'collection':
                segs.append('*')          # 集合底下的每一份文件
            app_paths.add('/'.join(segs))
        rule_blocks = []
        for m in _re.finditer(r"match\s+/([^\s{][^\s]*)\s*\{", rules):
            path = m.group(1)
            if path.startswith('databases/'):
                continue
            body = rules[m.end():rules.find('}', rules.find('allow', m.end()))]
            rule_blocks.append(([('*' if s.startswith('{') else s) for s in path.split('/')], path, body))

        def covered(p):
            segs = p.split('/')
            for rsegs, rpath, body in rule_blocks:
                if len(rsegs) == len(segs) and all(r == '*' or r == s for r, s in zip(rsegs, segs)):
                    # 使用者自己的資料：一定要限定本人（request.auth.uid == uid）
                    if segs[0] == 'users' and 'request.auth.uid == uid' not in body:
                        return False
                    return True
            return False
        missing = sorted(p for p in app_paths if not covered(p))
        if missing:
            print('    rules missing:', missing)
        c['rules_cover_every_cloud_path'] = bool(rules) and len(app_paths) >= 6 and not missing and 'users/*/trainings/*' in app_paths
        # ================= 訓練紀錄跨裝置同步 =================
        SETUP = """const wait=ms=>new Promise(s=>setTimeout(s,ms)); const clone=x=>JSON.parse(JSON.stringify(x));
            const T=(id,d,o)=>Object.assign({id,date:d,startTime:'06:00',sport:'run',distanceKm:10,durationSeconds:3000,fingerprint:'fp-'+id,
              importedAt:d+'T08:00:00.000Z',updatedAt:d+'T08:00:00.000Z'},o||{});
            // 換一台裝置：本機沒有賽事、沒有訓練、沒有同步紀錄（雲端那份不動）
            const device=async(local)=>{ await saveJson('cloud-sync-state-v1',null); cloudKnown=null; cloudPendingDeletes=[]; state.user=null;
              state.races=[]; trainings=(local||[]).map(x=>migrateTraining(clone(x))); await saveJson(TRAININGS_KEY,trainings);
              hideAppBanner(); trainingDeniedNoticeShown=false; trainingSyncError=null; };
            const ids=list=>list.filter(x=>!x.deletedAt).map(x=>x.id).sort().join();"""
        c['trainings_follow_account_to_new_device'] = self.ev(page, """async()=>{ """ + SETUP + """
            const cloud=__makeFakeCloud([],[]); window.__cloud=cloud;
            await device([T('t1','2026-08-05'),T('t2','2026-09-06')]);              // 裝置 A：本機有訓練、雲端是空的
            await handleAuthChange({uid:'u1'}); await wait(1300);
            const upA=ids(cloud.store.trainings);
            await device([]);                                                          // 裝置 B：全新的瀏覽器
            await handleAuthChange({uid:'u1'}); await wait(1300);
            const gotB=ids(trainings), saved=ids(await loadJson(TRAININGS_KEY,[]));
            if(!(upA==='t1,t2'&&gotB==='t1,t2'&&saved==='t1,t2')) console.log('trsync: new device',upA,gotB,saved);
            return upA==='t1,t2' && gotB==='t1,t2' && saved==='t1,t2'; }""")
        # 同一個月兩台裝置都在寫：B 上傳九月時，不能把別台剛寫進雲端的九月那筆洗掉，B 也要補到那一筆
        c['two_devices_same_month_no_loss'] = self.ev(page, """async()=>{ """ + SETUP + """
            const cloud=window.__cloud; if(!cloud) return false;
            cloud.store.trainings.push(clone(T('t4','2026-09-20')));                    // 別台裝置剛寫進雲端
            trainings.push(migrateTraining(clone(T('t3','2026-09-12')))); await persistTrainings(); await wait(1500);
            const inCloud=ids(cloud.store.trainings), here=ids(trainings);
            if(!(inCloud==='t1,t2,t3,t4'&&here==='t1,t2,t3,t4')) console.log('trsync: same month',inCloud,here);
            return inCloud==='t1,t2,t3,t4' && here==='t1,t2,t3,t4'; }""")
        # 同一個檔在兩台各匯入一次（另一台看起來是空的就又匯入）：留最早匯入的那筆，鞋款搬過去，另一筆的刪除同步到雲端
        c['same_file_on_two_devices_kept_once'] = self.ev(page, """async()=>{ """ + SETUP + """
            const a1=T('a1','2026-09-10',{fingerprint:'SAME',importedAt:'2026-09-10T08:00:00.000Z'});
            const b1=T('b1','2026-09-10',{fingerprint:'SAME',importedAt:'2026-09-25T08:00:00.000Z',shoeId:'s1',updatedAt:'2026-09-25T08:00:00.000Z'});
            const cloud=__makeFakeCloud([],[a1]); window.__cloud=cloud;
            await device([b1]); await handleAuthChange({uid:'u1'}); await wait(1600);
            const live=trainings.filter(x=>!x.deletedAt&&x.fingerprint==='SAME');
            const ca=cloud.store.trainings.find(x=>x.id==='a1'), cb=cloud.store.trainings.find(x=>x.id==='b1');
            const ok=live.length===1 && live[0].id==='a1' && live[0].shoeId==='s1' && !!cb && !!cb.deletedAt && !!ca && !ca.deletedAt && ca.shoeId==='s1';
            if(!ok) console.log('trsync: dedupe',JSON.stringify(live.map(x=>[x.id,x.shoeId])),JSON.stringify(cloud.store.trainings.map(x=>[x.id,!!x.deletedAt,x.shoeId])));
            return ok; }""")
        # 雲端拒絕（安全性規則沒開放）：跳一次提示、本機資料還在、同步診斷寫出怎麼修
        c['denied_sync_is_visible_once'] = self.ev(page, """async()=>{ """ + SETUP + """
            const cloud=__makeFakeCloud([],[]); cloud.denyTrainings=true; window.__cloud=cloud;
            await device([T('t1','2026-08-05'),T('t2','2026-09-06')]);
            await handleAuthChange({uid:'u1'}); await wait(1300);
            const b=document.querySelector('.app-banner');
            const shown=!!b && b.classList.contains('is-warn') && b.textContent.includes('訓練紀錄沒有同步到雲端');
            const kept=ids(trainings)==='t1,t2' && ids(await loadJson(TRAININGS_KEY,[]))==='t1,t2';
            hideAppBanner();
            trainings[0].shoeId='s9'; trainings[0].updatedAt=new Date().toISOString(); await persistTrainings(); await wait(1400);
            const again=!document.querySelector('.app-banner');                     // 一次瀏覽只提示一次
            await handleAuthChange({uid:'u1'}); await wait(800);                     // 再登入一次也不會重複跳
            const again2=!document.querySelector('.app-banner');
            trainingDeniedNoticeShown=false; await handleAuthChange({uid:'u1'}); await wait(800);
            const how=document.querySelector('.app-banner [data-banner-action="0"]'); if(how) how.click(); await wait(300);
            const m=document.getElementById('sync-diag-modal'); const fix=m&&!m.hidden&&m.querySelector('.sync-diag-fix');
            const fixOk=!!fix && fix.textContent.includes('firestore.rules') && fix.textContent.includes('發布');
            if(m){ m.hidden=true; m.innerHTML=''; }
            if(!(shown&&kept&&again&&again2&&fixOk)) console.log('trsync: denied',shown,kept,again,again2,fixOk);
            return shown && kept && again && again2 && fixOk; }""")
        c['sync_diag_lists_trainings'] = self.ev(page, """async()=>{ """ + SETUP + """
            const row=()=>[...document.querySelectorAll('#sync-diag-modal .sync-diag-table tbody tr')].find(tr=>tr.textContent.includes('訓練紀錄'));
            const cloud=__makeFakeCloud([],[T('t1','2026-08-05'),T('t2','2026-09-06'),T('t3','2026-09-07',{deletedAt:'2026-09-08T00:00:00.000Z'})]); window.__cloud=cloud;
            await device([T('t1','2026-08-05'),T('t2','2026-09-06')]); await handleAuthChange({uid:'u1'}); await wait(1200);
            openSyncDiagModal(); await runSyncDiag(); await wait(100);
            const r1=row(); const ok1=!!r1 && r1.cells[1].textContent.trim()==='2' && r1.cells[2].textContent.trim()==='2' && !r1.classList.contains('sync-diag-mismatch')
              && !document.querySelector('#sync-diag-modal .sync-diag-fix');
            cloud.denyTrainings=true; await runSyncDiag(); await wait(100);
            const r2=row(); const ok2=!!r2 && r2.cells[2].textContent.trim()==='被拒絕' && r2.classList.contains('sync-diag-mismatch')
              && !!document.querySelector('#sync-diag-modal .sync-diag-fix');
            const m=document.getElementById('sync-diag-modal'); m.hidden=true; m.innerHTML='';
            window.__cloud=null; state.user=null; hideAppBanner();
            if(!(ok1&&ok2)) console.log('trsync: diag',ok1,ok2);
            return ok1 && ok2; }""")
        # （版本號的檢查跟著最新的群組走，v4.3.2 起在 v432）


# 各距離最佳用的賽事：名稱跟使用者截圖一樣不含年份；一場 226 公里的自行車賽比超級鐵人快，
# 用來確認它不會搶走「226K 超級鐵人最佳」那張
BEST_SEED_JS = r"""window.__mk=(n,sport,km,d,t,st)=>{ const r=emptyRace(n,sport,st||'completed',d); r.route.distanceKm=km; r.results.chipTimeSeconds=t==null?null:hmsToSec(t); return r; };
window.__seedBest=async function(opts){
  opts=opts||{};
  const list=[
    __mk('大阪馬拉松','road_running',42.195,'2024-02-25','3:28:41'),
    __mk('東京馬拉松','road_running',42.195,'2023-03-05','3:35:10'),
    __mk('萬金石馬拉松（半程）','road_running',21.0975,'2023-03-19','1:36:20'),
    __mk('大稻埕 10K 夜跑','road_running',10,'2022-08-20','0:44:10'),
    __mk('陽明山 5K 路跑','road_running',5,'2021-04-11','0:21:05'),
    __mk('臺東巴歌浪鐵人三項','triathlon',113,'2023-04-15','5:58:12'),
    __mk('澎湖超級鐵人三項','triathlon',226,'2025-10-05','12:41:09'),
    __mk('2019 墾丁 226 單車挑戰','cycling',226,'2019-11-02','8:10:00'),
  ];
  if(opts.tri51) list.push(__mk('2022 臺南標準鐵人三項 51.5K','triathlon',51.5,'2022-05-08','2:31:45'));
  state.races=list; state.selectedId=null; state.filterStatus='all'; state.searchQuery='';
  document.getElementById('search-input').value='';
  state.viewMode='table'; tableSort={key:'date',dir:'desc'}; await persist(); renderAll();
};
"""


class V432Best(Group):
    """v4.3.2：各距離最佳多一張「226K 超級鐵人最佳」、每張卡寫出那一場的年份；
    筆電上 6、7 張排成一排，標籤只在空白處換行、換行時同一排的時間還是對齊。"""

    ECHO = ('best:',)

    def _echo(self, msg):
        if msg.text.startswith(self.ECHO):
            print('   ', msg.text[:300])

    def ev(self, pg, js, arg=None):
        # 一項檢查拋出例外：記成這一項失敗、印出原因，後面照跑
        try:
            return pg.evaluate(js) if arg is None else pg.evaluate(js, arg)
        except Exception as exc:                      # noqa: BLE001
            print('    ⚠', str(exc).split('\n')[0][:200])
            return False

    def _ctx(self, browser, viewport, lang=None):
        ctx = full_mode_context(browser, viewport=viewport)
        if lang:
            ctx.add_init_script(f"try{{localStorage.setItem('lang-pref-v1','{lang}');}}catch(e){{}}")
        pg = ctx.new_page()
        pg.on('pageerror', lambda e: self.errors.append(str(e)))
        pg.on('console', self._echo)
        pg.goto(APP_URL)
        pg.wait_for_timeout(900)
        pg.add_script_tag(content=BEST_SEED_JS)
        pg.add_script_tag(content=CONTRAST_JS)
        pg.add_style_tag(content='.badge-unbox-overlay,.foreground-toast{display:none!important}')
        pg.evaluate("()=>__seedBest()")
        pg.wait_for_timeout(300)
        return ctx, pg

    def body(self, page):
        c = self.checks
        browser = page.context.browser
        W = ("const wait=ms=>new Promise(s=>setTimeout(s,ms));"
             "const card=k=>document.querySelector('#calendar .tv-best-card[data-best=\"'+k+'\"]');"
             "const line=k=>card(k)&&card(k).querySelector('.tv-best-race');"
             "const byName=n=>state.races.find(r=>r.name===n);"
             "const redraw=async()=>{ await persist(); renderCalendar(); await wait(120); };"
             "const rows=()=>new Set([...document.querySelectorAll('#calendar .tv-best-card')].map(x=>Math.round(x.getBoundingClientRect().top))).size;"
             "const cardW=()=>Math.round(document.querySelector('#calendar .tv-best-card').getBoundingClientRect().width);")
        # 筆電寬度（表格區 1,056px）
        lctx, lp = self._ctx(browser, {'width': 1280, 'height': 800})
        # ================= 226K 超級鐵人 =================
        c['best_226k_card_listed'] = self.ev(lp, """()=>{ """ + W + """
            const keys=[...document.querySelectorAll('#calendar .tv-best-card')].map(x=>x.dataset.best).join();
            const c226=card('tri226'), tri=byName('澎湖超級鐵人三項');
            const ok=keys==='fm,hm,10k,5k,tri113,tri226' && !!c226 && c226.querySelector('.tv-best-label').textContent==='226K 超級鐵人最佳'
              && c226.querySelector('b').textContent==='12:41:09' && c226.dataset.id===tri.id
              && card('tri113').dataset.id===byName('臺東巴歌浪鐵人三項').id;
            if(!ok) console.log('best: 226',keys,c226&&c226.textContent.replace(/\\s+/g,' '));
            return ok; }""")
        # 220–235 公里的鐵人三項才算：少 4 公里（游泳取消）、多幾公里（騎車段比較長）都算；
        # 219.9、235.1、雙倍超鐵 452 公里不算；沒完賽的不算（就算時間比較快）
        c['tri226_distance_window'] = self.ev(lp, """async()=>{ """ + W + """
            const keep=state.races.slice(); const time=()=>card('tri226').querySelector('b').textContent;
            const add=(n,km,t,st)=>{ const r=__mk(n,'triathlon',km,'2024-06-1'+state.races.length%10,t,st); state.races.push(r); return r; };
            add('短一點的鐵人',219.9,'10:00:00'); add('雙倍超級鐵人',452,'11:00:00'); add('長一點的鐵人',235.1,'11:30:00'); add('沒完賽的超鐵',226,'9:00:00','dnf');
            await redraw(); const out=time()==='12:41:09' && card('tri113').dataset.id===byName('臺東巴歌浪鐵人三項').id;
            const a=add('游泳取消的超鐵',222.2,'12:00:00'); await redraw(); const lo=card('tri226').dataset.id===a.id && time()==='12:00:00';
            const b=add('騎車段多 9 公里',235,'11:50:00'); await redraw(); const hi=card('tri226').dataset.id===b.id && time()==='11:50:00';
            const e=add('剛好 220',220,'11:40:00'); await redraw(); const edge=card('tri226').dataset.id===e.id;
            state.races=keep; await redraw();
            if(!(out&&lo&&hi&&edge)) console.log('best: window',out,lo,hi,edge);
            return out && lo && hi && edge && time()==='12:41:09'; }""")
        c['best_226k_card_opens_race'] = self.ev(lp, """async()=>{ """ + W + """
            const id=card('tri226').dataset.id; card('tri226').click(); await wait(500);
            const ok=state.selectedId===id && byName('澎湖超級鐵人三項').id===id;
            goBackFromDetail(); await wait(400);
            return ok && state.selectedId===null && !!card('tri226'); }""")
        # ================= 年份 =================
        # 名稱前面是那一場的年份，年份是這一行的第一個東西（名稱太長被截掉時年份還在）
        c['best_cards_show_race_year'] = self.ev(lp, """()=>{ """ + W + """
            const keys=['fm','hm','10k','5k','tri113','tri226'];
            const got=keys.map(k=>line(k).textContent);
            const want=['2024 大阪馬拉松','2023 萬金石馬拉松（半程）','2022 大稻埕 10K 夜跑','2021 陽明山 5K 路跑','2023 臺東巴歌浪鐵人三項','2025 澎湖超級鐵人三項'];
            const first=keys.every(k=>{ const l=line(k), y=l.firstChild; return !!y && y.nodeType===1 && y.classList.contains('tv-best-year') && y.textContent===l.textContent.slice(0,4); });
            const ok=JSON.stringify(got)===JSON.stringify(want) && first;
            if(!ok) console.log('best: year',got.join(' | '),first);
            return ok; }""")
        # 名稱本來就是這一年開頭：不再多寫一次；年份在名稱後面的照樣加在前面（後面可能被截掉）；
        # 「20240 公尺」開頭剛好是那四個數字但不是年份
        c['year_not_repeated_when_name_starts_with_it'] = self.ev(lp, """async()=>{ """ + W + """
            const r=byName('大阪馬拉松'), keep=r.name, res=[];
            for(const n of ['2024 大阪馬拉松','2024大阪馬拉松','大阪馬拉松 2024','20240 公尺大阪接力','  2024 大阪馬拉松']){
              r.name=n; await redraw(); const l=line('fm'), y=l.firstChild;
              res.push([l.textContent, !!y && y.nodeType===1 && y.classList.contains('tv-best-year') && y.textContent==='2024']); }
            r.name=keep; await redraw();
            const want=[['2024 大阪馬拉松',true],['2024大阪馬拉松',true],['2024 大阪馬拉松 2024',true],['2024 20240 公尺大阪接力',true],['2024 大阪馬拉松',true]];
            const ok=JSON.stringify(res)===JSON.stringify(want);
            if(!ok) console.log('best: dup',JSON.stringify(res));
            return ok; }""")
        c['year_stays_visible_when_name_cut'] = self.ev(lp, """async()=>{ """ + W + """
            const r=byName('澎湖超級鐵人三項'), keep=r.name;
            r.name='澎湖國際超級鐵人三項錦標賽暨全國鐵人三項系列賽總決賽'; await redraw();
            const c=card('tri226'), l=line('tri226'), y=l.querySelector('.tv-best-year');
            const cut=l.scrollWidth>l.clientWidth+1, lb=l.getBoundingClientRect(), yb=y?y.getBoundingClientRect():null;
            const seen=!!yb && yb.width>0 && yb.left>=lb.left-0.5 && yb.right<=lb.right+0.5;
            const title=c.getAttribute('title')==='2025-10-05 '+r.name;          // 滑鼠停著看得到完整的日期和賽名
            r.name=keep; await redraw();
            if(!(cut&&seen&&title)) console.log('best: cut',cut,seen,title,c.getAttribute('title'));
            return cut && seen && title; }""")
        c['unnamed_or_undated_race'] = self.ev(lp, """async()=>{ """ + W + """
            const r=byName('大阪馬拉松'), kn=r.name, kd=r.schedule.raceDate;
            r.name=''; await redraw(); const unnamed=line('fm').textContent;
            r.name=kn; r.schedule.raceDate=''; await redraw();
            const c=card('fm'), same=!!c && c.dataset.id===r.id;
            const nodate=same?line('fm').textContent:'', noTag=same && !c.querySelector('.tv-best-year'), title=same?c.getAttribute('title'):'';
            r.schedule.raceDate=kd; await redraw();
            const ok=unnamed==='2024 (未命名賽事)' && nodate==='大阪馬拉松' && noTag && title==='大阪馬拉松';
            if(!ok) console.log('best: blank',unnamed,nodate,noTag,title);
            return ok; }""")
        # 年份比賽名深一階、淺色深色都看得清楚（4.5:1 以上）
        c['best_card_text_readable_light_and_dark'] = self.ev(lp, """async()=>{ """ + W + """
            const st=document.createElement('style'); st.textContent='*{transition:none!important}'; document.head.appendChild(st);
            const res={};
            for(const th of ['light','dark']){ applyTheme(th); await wait(150);
              const cs=[...document.querySelectorAll('#calendar .tv-best-card')];
              const min=sel=>Math.min(...cs.map(x=>__contrast(x.querySelector(sel))));
              res[th]={label:min('.tv-best-label'),time:min('b'),year:min('.tv-best-year'),name:min('.tv-best-race')}; }
            applyTheme('light'); await wait(150); st.remove();
            const ok=['light','dark'].every(th=>{ const r=res[th]; return r.label>=4.5 && r.time>=4.5 && r.year>=4.5 && r.name>=4.5 && r.year>r.name+0.5; });
            console.log('best: contrast',JSON.stringify(res,(k,v)=>typeof v==='number'?+v.toFixed(2):v));
            return ok; }""")
        # ================= 筆電上一排放得下就排一排 =================
        # 6 張、7 張都是一排（原本一排 5 張，第 6 張會自己掉到第二排）；張數少時卡片維持原本的寬度，不會被撐開
        c['laptop_six_or_seven_cards_one_row'] = self.ev(lp, """async()=>{ """ + W + """
            const six=[rows(),cardW()];
            const t51=__mk('臺南標準鐵人三項','triathlon',51.5,'2022-05-08','2:31:45'); state.races.push(t51); await redraw();
            const seven=[rows(),cardW(),document.querySelectorAll('#calendar .tv-best-card').length];
            const keep=state.races.slice();
            state.races=keep.filter(r=>r!==t51&&r.name!=='澎湖超級鐵人三項'); await redraw(); const five=[rows(),cardW()];
            state.races=keep.filter(r=>r.sportType!=='triathlon'); await redraw(); const four=[rows(),cardW()];
            state.races=keep.filter(r=>r!==t51); await redraw();
            const ok=six[0]===1 && seven[0]===1 && seven[2]===7 && five[0]===1 && Math.abs(five[1]-203)<=2 && Math.abs(four[1]-203)<=2 && six[1]>=160;
            if(!ok) console.log('best: rows',JSON.stringify({six,seven,five,four}));
            return ok; }""")
        lctx.close()
        # ================= 各寬度 × 三種語言 × 三種字級 × 6／7 張 =================
        # 標籤、時間不超出卡片；年份看得到；標籤只在空白處換行（不會把最後一個「佳」「速」單獨擠到下一行）；
        # 同一排的時間對齊；沒有橫向捲動
        FIT = """()=>{ const bad=[]; const cards=[...document.querySelectorAll('#calendar .tv-best-card')]; const byRow={};
            cards.forEach(c=>{ const cb=c.getBoundingClientRect(), cs=getComputedStyle(c);
              const inL=cb.left+parseFloat(cs.paddingLeft)+parseFloat(cs.borderLeftWidth)-0.5, inR=cb.right-parseFloat(cs.paddingRight)-parseFloat(cs.borderRightWidth)+0.5;
              const lb=c.querySelector('.tv-best-label'), tm=c.querySelector('b'), ln=c.querySelector('.tv-best-race'), y=c.querySelector('.tv-best-year');
              [lb,tm].forEach(e=>{ const r=document.createRange(); r.selectNodeContents(e); const b=r.getBoundingClientRect(); if(b.left<inL||b.right>inR) bad.push(c.dataset.best+' out:'+e.textContent); });
              if(!y) bad.push(c.dataset.best+' noyear'); else if(y.getBoundingClientRect().right>ln.getBoundingClientRect().right+0.5) bad.push(c.dataset.best+' yearcut');
              const tn=lb.firstChild; if(tn&&tn.nodeType===3){ const s=tn.textContent; let top=null;
                for(let i=0;i<s.length;i++){ const r=document.createRange(); r.setStart(tn,i); r.setEnd(tn,i+1); const rc=r.getClientRects()[0]; if(!rc||rc.width===0) continue;
                  if(top!==null&&rc.top>top+2&&s[i-1]!==' ') bad.push(c.dataset.best+' break:'+s.slice(0,i)+'|'+s.slice(i)); top=rc.top; } }
              const k=Math.round(cb.top); (byRow[k]=byRow[k]||[]).push(tm.getBoundingClientRect().top); });
            Object.values(byRow).forEach(ts=>{ if(Math.max(...ts)-Math.min(...ts)>1) bad.push('times '+ts.map(Math.round).join('/')); });
            if(document.documentElement.scrollWidth>innerWidth) bad.push('hscroll');
            return bad; }"""
        bad = []
        labels = {}
        for lang in ('zh', 'ja', 'en'):
            fctx, fp = self._ctx(browser, {'width': 1280, 'height': 900}, lang=lang)
            # 英文、日文的標籤（含 226K）、年份一樣在名稱前面
            labels[lang] = self.ev(fp, """()=>[...document.querySelectorAll('#calendar .tv-best-label')].map(x=>x.textContent).join('|')
                +'#'+document.querySelector('#calendar .tv-best-card[data-best="fm"] .tv-best-race').textContent""")
            for w in (1280, 1100, 1000, 768, 641):
                fp.set_viewport_size({'width': w, 'height': 900})
                for tri51 in (False, True):
                    self.ev(fp, "(o)=>__seedBest(o)", {'tri51': tri51})
                    fp.wait_for_timeout(150)
                    for fs in ('small', 'medium', 'large'):
                        got = self.ev(fp, "async(fs)=>{ applyFontScale(fs); renderCalendar(); await new Promise(s=>setTimeout(s,60)); return (" + FIT + ")(); }", fs)
                        if got is False:
                            got = ['eval failed']
                        bad += [f'{lang} {w} {7 if tri51 else 6} {fs} {x}' for x in got]
            self.ev(fp, "()=>applyFontScale('medium')")
            fctx.close()
        if bad:
            print('    fit:', ' | '.join(bad[:10]))
        c['best_strip_fits_every_width_language_font'] = not bad
        c['english_japanese_labels_include_226'] = (
            labels.get('en') == 'Best marathon|Best half|Best 10K|Best 5K|Best 113K triathlon|Best 226K triathlon#2024 大阪馬拉松'
            and labels.get('ja') == 'フル最速|ハーフ最速|10K 最速|5K 最速|113K トライアスロン最速|226K トライアスロン最速#2024 大阪馬拉松')
        if not c['english_japanese_labels_include_226']:
            print('    labels:', labels)
        # ================= 使用說明（三種語言都寫到 226K 和年份） =================
        c['help_mentions_226k_and_year'] = self.ev(page, """async()=>{ const wait=ms=>new Promise(s=>setTimeout(s,ms)); const out={};
            for(const [lang,word] of [['zh','那一場的年份'],['ja','大会名の前にその年'],['en','year in front of each race name']]){ setLang(lang); await wait(150); openHelpModal(); await wait(200);
              const tx=document.querySelector('#help-modal .help-body').textContent; out[lang]=tx.includes('226K')&&tx.includes(word);
              document.querySelector('#help-modal [data-action="close-help"]').click(); await wait(200); }
            setLang('zh'); await wait(150);
            if(!(out.zh&&out.ja&&out.en)) console.log('best: help',JSON.stringify(out));
            return out.zh && out.ja && out.en; }""")
        # （版本號的檢查跟著最新的群組走，v4.3.3 起在 v433）


# 輸入框的框看不看得出來：border、box-shadow 畫的框（0 模糊）、outline、填色，取對「背後底色」最大的那個。
# color-mix() 算出來的顏色是 color(srgb 0.98 0.98 0.97 / 0.35)（0–1 的小數），要乘 255
FIELD_FRAME_JS = r"""
window.__rgba=c=>{ const m=(c.match(/[\d.]+/g)||[]).map(Number); const k=/^color\(srgb/.test(c)?255:1; return [(m[0]||0)*k,(m[1]||0)*k,(m[2]||0)*k,m.length>3?m[3]:1]; };
window.__over=(t,u)=>{ const a=t[3]; return [t[0]*a+u[0]*(1-a),t[1]*a+u[1]*(1-a),t[2]*a+u[2]*(1-a),1]; };
window.__lum=c=>{ const v=c.slice(0,3).map(x=>{ x/=255; return x<=0.03928?x/12.92:Math.pow((x+0.055)/1.055,2.4); }); return 0.2126*v[0]+0.7152*v[1]+0.0722*v[2]; };
window.__cr=(a,b)=>{ const x=__lum(a),y=__lum(b); return (Math.max(x,y)+.05)/(Math.min(x,y)+.05); };
window.__behind=el=>{ const layers=[]; let e=el.parentElement; while(e){ const b=__rgba(getComputedStyle(e).backgroundColor); if(b[3]>0) layers.push(b); if(b[3]>=1) break; e=e.parentElement; }
  let bg=[255,255,255,1]; for(let i=layers.length-1;i>=0;i--) bg=__over(layers[i],bg); return bg; };
window.__frame=el=>{ const cs=getComputedStyle(el), bg=__behind(el); let best=__cr(__over(__rgba(cs.backgroundColor),bg),bg);
  ['Top','Right','Bottom','Left'].forEach(s=>{ if(parseFloat(cs['border'+s+'Width'])>0) best=Math.max(best,__cr(__over(__rgba(cs['border'+s+'Color']),bg),bg)); });
  const parts=[]; let d=0,cur=''; for(const ch of cs.boxShadow){ if(ch==='(') d++; if(ch===')') d--; if(ch===','&&d===0){ parts.push(cur); cur=''; } else cur+=ch; } parts.push(cur);
  parts.forEach(sh=>{ if(!sh||sh.trim()==='none') return; const col=(sh.match(/(rgba?|color)\([^)]*\)/)||[''])[0]; const n=(sh.replace(col,'').match(/-?[\d.]+px/g)||[]).map(parseFloat).concat([0,0,0,0]);
    if(col&&n[2]===0&&(n[3]>=1||Math.abs(n[0])>=1||Math.abs(n[1])>=1)) best=Math.max(best,__cr(__over(__rgba(col),bg),bg)); });
  if(cs.outlineStyle!=='none'&&parseFloat(cs.outlineWidth)>0) best=Math.max(best,__cr(__over(__rgba(cs.outlineColor),bg),bg));
  return best; };
window.__visible=el=>{ const r=el.getBoundingClientRect(), cs=getComputedStyle(el); return r.width>0&&r.height>0&&cs.visibility!=='hidden'&&cs.display!=='none'&&!el.closest('[hidden]'); };
// 看得到的「可以打字的格子」；「新增一件」的框畫在外層 .pack-add
window.__fieldsIn=root=>[...root.querySelectorAll('input:not([type=hidden]):not([type=checkbox]):not([type=radio]):not([type=file]):not([type=range]):not([type=color]),select,textarea')]
  .filter(__visible).map(el=>el.classList.contains('pack-add-input')?el.closest('.pack-add'):el);
window.__placeholderCr=el=>{ const cs=getComputedStyle(el), bg=__behind(el), fill=__over(__rgba(cs.backgroundColor),bg); return __cr(__over(__rgba(getComputedStyle(el,'::placeholder').color),fill),fill); };
// 一場還沒比的（裝備兩件、各種清單各一列）＋一場已完賽的
window.__seedFields=async()=>{
  const r=emptyRace('2026 Xtrail 越野跑挑戰賽 - 福壽山站','trail_running','registered',addDaysStr(todayISO(),9));
  r.location.city='台中市';
  const it=(n,p,loc)=>Object.assign(LIST_META.equipmentChecklist.factory(),{itemName:n,isPacked:p,location:loc||''});
  r.equipmentChecklist=[it('222',false,'finish_bag'),it('頭燈',true)];
  ['checkpoints','mediaLinks','accommodations','transportation','companions'].forEach(k=>{ if(LIST_META[k]) r[k]=[LIST_META[k].factory()]; });
  const done=emptyRace('2025 臺北馬拉松','road_running','completed','2025-12-21'); done.results.chipTimeSeconds=hmsToSec('3:20:00');
  state.races=[r,done]; await persist(); window.__rid=r.id; window.__did=done.id; selectRace(r.id); };
"""


class V433Fields(Group):
    """v4.3.3：抽屜、彈窗裡的輸入框看得出框（淺色、深色、瀏覽器強制深色）；切換鈕、篩選膠囊、
    打包的勾選方塊、「新增一件」也是；提示字看得清楚；原生的下拉、日期、核取方塊跟著深色模式。"""

    ECHO = ('fields:',)

    def _echo(self, msg):
        if msg.text.startswith(self.ECHO):
            print('   ', msg.text[:300])

    def ev(self, pg, js, arg=None):
        # 一項檢查拋出例外：記成這一項失敗、印出原因，後面照跑
        try:
            return pg.evaluate(js) if arg is None else pg.evaluate(js, arg)
        except Exception as exc:                      # noqa: BLE001
            print('    ⚠', str(exc).split('\n')[0][:200])
            return False

    def _ctx(self, browser, theme, os_scheme='light', force_dark=False, dsf=1):
        ctx = full_mode_context(browser, viewport={'width': 1280, 'height': 860}, color_scheme=os_scheme, device_scale_factor=dsf)
        ctx.add_init_script(f"try{{localStorage.setItem('theme-pref-v1','{theme}');}}catch(e){{}}")
        pg = ctx.new_page()
        if force_dark:
            # 跟使用者的瀏覽器一樣打開「網頁強制深色」（Chrome／Edge 的 Auto Dark Mode）
            cdp = ctx.new_cdp_session(pg)
            cdp.send('Emulation.setAutoDarkModeOverride', {'enabled': True})
        pg.on('pageerror', lambda e: self.errors.append(str(e)))
        pg.on('console', self._echo)
        pg.goto(APP_URL)
        pg.wait_for_timeout(900)
        pg.add_script_tag(content=FIELD_FRAME_JS)
        # 量顏色前先關掉過場：框的顏色有 0.15 秒的過場，量到的是半途的顏色
        pg.add_style_tag(content='.badge-unbox-overlay,.foreground-toast{display:none!important} *{transition:none!important}')
        pg.evaluate("()=>__seedFields()")
        pg.wait_for_timeout(500)
        return ctx, pg

    @staticmethod
    def _lum(bgr):
        v = []
        for x in (bgr[2], bgr[1], bgr[0]):
            x = x / 255
            v.append(x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4)
        return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]

    def _edge(self, pg, sel, side='left'):
        """截圖後在元素左（或右）邊的框線位置取色：框外 8px 的底色，跟框附近最突出的那個像素比對比。
        強制深色是畫的時候才轉的，算出來的樣式看不到，只能量畫面"""
        box = pg.evaluate("(s)=>{ const e=document.querySelector(s); if(!e) return null; const r=e.getBoundingClientRect(); return [r.left,r.top,r.width,r.height]; }", sel)
        if not box:
            return None
        img = cv2.imdecode(np.frombuffer(pg.screenshot(), np.uint8), cv2.IMREAD_COLOR)
        k = img.shape[1] / 1280
        x, y, w, h = [v * k for v in box]
        cy = int(y + h / 2)
        if side == 'left':
            out_x, xs = int(x) - 8, range(int(x) - 2, int(x) + int(5 * k))
        else:
            out_x, xs = int(x + w) + 8, range(int(x + w) - int(5 * k), int(x + w) + 2)
        outside = self._lum(img[cy, out_x])
        best = max((max(self._lum(img[cy, xx]), outside) + .05) / (min(self._lum(img[cy, xx]), outside) + .05) for xx in xs)
        return round(float(best), 2)

    def body(self, page):
        c = self.checks
        browser = page.context.browser
        # ================= 抽屜裡的每一格：淺色、深色 =================
        DRAWERS = r"""async()=>{ const wait=ms=>new Promise(s=>setTimeout(s,ms));
            const secs=[['equipment','pack'],['equipment','list'],['equipment','kanban'],['basicInfo'],['schedule'],['weather'],['checkpoints'],['mediaLinks'],
              ['nutritionPlan'],['trainingPlan'],['goals'],['route'],['logistics'],['results','done'],['review','done'],['recordResult','done']];
            const bad=[], phBad=[]; let n=0, nPh=0, nCtl=0, minFill=99;
            for(const [key,arg] of secs){
              closeDrawer(); await wait(60);
              const id=arg==='done'?__did:__rid; if(state.selectedId!==id){ selectRace(id); await wait(200); }
              if(key==='equipment') equipmentViewMode=arg;
              openDrawer(key); await wait(220);
              const root=document.getElementById('drawer-content');
              __fieldsIn(root).forEach(el=>{ n++; const f=__frame(el); if(f<3) bad.push(key+(arg?':'+arg:'')+' '+(el.dataset.path||el.className||el.tagName)+' '+f.toFixed(2));
                const bg=__behind(el), fill=__cr(__over(__rgba(getComputedStyle(el).backgroundColor),bg),bg); minFill=Math.min(minFill,fill); });
              // 瀏覽器自己畫的核取方塊外面不能再多一圈框（.field input 的框不套到它身上）
              root.querySelectorAll('input[type=checkbox]').forEach(el=>{ if(__visible(el)&&getComputedStyle(el).boxShadow!=='none') bad.push(key+' checkbox ring'); });
              // 切換鈕（外框）、沒選的篩選膠囊、還沒打包的勾選方塊
              root.querySelectorAll('.equip-view-seg,.pack-filter:not([aria-pressed="true"]),.pack-row:not(.is-packed) .pack-box').forEach(el=>{ if(!__visible(el)) return; nCtl++; const f=__frame(el); if(f<3) bad.push(key+(arg?':'+arg:'')+' '+el.className+' '+f.toFixed(2)); });
              root.querySelectorAll('input[placeholder],textarea[placeholder]').forEach(el=>{ if(!el.placeholder||!__visible(el)) return; nPh++; const r=__placeholderCr(el); if(r<4.5) phBad.push(key+' '+(el.dataset.path||el.className)+' '+r.toFixed(2)); });
            }
            closeDrawer();
            return {n,nCtl,bad,nPh,phBad,minFill}; }"""
        # 抽屜以外：首頁搜尋框、新增賽事、個人資料、鞋款、補給品字典、配速、貼上、恢復
        MODALS = r"""async()=>{ const wait=ms=>new Promise(s=>setTimeout(s,ms)); const hide=()=>document.querySelectorAll('.modal-overlay').forEach(m=>m.hidden=true);
            const steps=[['home',()=>{ closeDrawer(); state.selectedId=null; renderAll(); }],['create',()=>startCreate()],
              ['profile',()=>{ hide(); state.creating=false; renderAll(); openProfileModal(); }],['shoes',()=>{ hide(); openShoeModal(); }],
              ['nutrition',()=>{ hide(); openNutritionDictModal(); }],['pacing',()=>{ hide(); selectRace(__rid); openPacingModal(); }],
              ['paste',()=>{ hide(); openPasteModal(); }],['recovery',()=>{ hide(); openRecoveryModal(); }]];
            const bad=[], phBad=[]; let n=0;
            for(const [name,fn] of steps){ fn(); await wait(350);
              __fieldsIn(document).forEach(el=>{ n++; const f=__frame(el); if(f<3) bad.push(name+' '+(el.id||el.className||el.tagName)+' '+f.toFixed(2)); });
              document.querySelectorAll('input[placeholder],textarea[placeholder]').forEach(el=>{ if(!el.placeholder||!__visible(el)) return; const r=__placeholderCr(el); if(r<4.5) phBad.push(name+' '+(el.id||el.className)+' '+r.toFixed(2)); }); }
            hide(); state.creating=false; renderAll();
            return {n,bad,phBad}; }"""
        res = {}
        for theme in ('light', 'dark'):
            ctx, pg = self._ctx(browser, theme)
            d = self.ev(pg, DRAWERS) or {'n': 0, 'nCtl': 0, 'bad': ['eval failed'], 'nPh': 0, 'phBad': ['eval failed'], 'minFill': 0}
            m = self.ev(pg, MODALS) or {'n': 0, 'bad': ['eval failed'], 'phBad': ['eval failed']}
            res[theme] = (d, m)
            print(f"    {theme}: drawer fields {d['n']}, controls {d['nCtl']}, placeholders {d['nPh']}; other inputs {m['n']}")
            if d['bad'] or d['phBad'] or m['bad'] or m['phBad']:
                print(f'    {theme}:', (d['bad'] + d['phBad'] + m['bad'] + m['phBad'])[:8])
            # 深色模式：瀏覽器自己畫的核取方塊、日期選擇器、下拉清單跟著換深色（原本是白色的方塊）
            if theme == 'dark':
                c['native_controls_follow_dark_mode'] = self.ev(pg, """async()=>{ const wait=ms=>new Promise(s=>setTimeout(s,ms));
                    selectRace(__rid); await wait(200); openDrawer('schedule'); await wait(250);
                    const cb=document.querySelector('#drawer-content input[type=checkbox]'), date=document.querySelector('#drawer-content input[type=date]');
                    const ok=getComputedStyle(document.documentElement).colorScheme==='dark' && getComputedStyle(cb).colorScheme==='dark' && getComputedStyle(date).colorScheme==='dark';
                    closeDrawer(); return ok; }""")
                pg.evaluate("async()=>{ openDrawer('schedule'); await new Promise(s=>setTimeout(s,250)); document.querySelector('#drawer-content input[type=checkbox]').scrollIntoView({block:'center'}); }")
                pg.wait_for_timeout(200)
                box = pg.evaluate("()=>{ const r=document.querySelector('#drawer-content input[type=checkbox]').getBoundingClientRect(); return [r.left+r.width/2, r.top+r.height/2]; }")
                img = cv2.imdecode(np.frombuffer(pg.screenshot(), np.uint8), cv2.IMREAD_COLOR)
                cb_light = self._lum(img[int(box[1]), int(box[0])])
                # 方塊中間是深色（原本 color-scheme 沒宣告時是白色 1.0）
                c['native_controls_follow_dark_mode'] = bool(c['native_controls_follow_dark_mode']) and cb_light < 0.2
                if cb_light >= 0.2:
                    print('    checkbox center luminance', round(cb_light, 3))
                pg.evaluate("()=>closeDrawer()")
            ctx.close()
        # 數量是「真的有量到」的下限：16 個抽屜畫面 129 格、抽屜以外 27 格
        for theme in ('light', 'dark'):
            d, m = res[theme]
            c[f'drawer_fields_framed_{theme}'] = d['n'] >= 120 and d['nCtl'] >= 5 and not d['bad']
            c[f'other_inputs_framed_{theme}'] = m['n'] >= 25 and not m['bad']
        # 深色模式的格子比抽屜深一階：不是只靠框，整格看得出來是「嵌進去」的（淺色是白格子，靠框）
        c['dark_fields_a_step_darker'] = res['dark'][0]['minFill'] >= 1.1
        if res['dark'][0]['minFill'] < 1.1:
            print('    dark field fill', res['dark'][0]['minFill'])
        c['placeholders_readable'] = all(res[t][0]['nPh'] >= 3 and not res[t][0]['phBad'] and not res[t][1]['phBad'] for t in ('light', 'dark'))
        # ================= 使用者的情況：淺色模式＋瀏覽器「網頁強制深色」 =================
        # 量畫面上的像素：框（輸入框、下拉、勾選方塊、「新增一件」、膠囊、切換鈕）對旁邊底色至少 3:1。
        # 原本：勾選方塊 1.94、「新增一件」1.0、切換鈕外框 1.28
        fctx, fp = self._ctx(browser, 'light', force_dark=True, dsf=2)
        got = {}
        fp.evaluate("async()=>{ equipmentViewMode='pack'; openDrawer('equipment'); await new Promise(s=>setTimeout(s,400)); }")
        fp.mouse.move(5, 5)
        got['pack-box'] = self._edge(fp, '#drawer-content .pack-row:not(.is-packed) .pack-box')
        got['pack-add'] = self._edge(fp, '#drawer-content .pack-add')
        got['chip'] = self._edge(fp, '#drawer-content .pack-filter:not([aria-pressed="true"])')
        got['seg'] = self._edge(fp, '#drawer-content .equip-view-seg', 'right')
        fp.evaluate("async()=>{ closeDrawer(); openDrawer('basicInfo'); await new Promise(s=>setTimeout(s,400)); }")
        got['text'] = self._edge(fp, '#drawer-content .field input[type=text]')
        got['select'] = self._edge(fp, '#drawer-content .field select')
        fp.evaluate("async()=>{ closeDrawer(); equipmentViewMode='list'; openDrawer('equipment'); await new Promise(s=>setTimeout(s,400)); }")
        got['template'] = self._edge(fp, '#drawer-content .template-bar select')
        fctx.close()
        c['forced_dark_frames_visible'] = all(v is not None and v >= 3 for v in got.values())
        print('    forced dark:', got)
        # App 自己的深色＋系統也是深色：瀏覽器不會再轉一次（選中的「打包」維持淺色底；原本會被反成 #282825）
        dctx, dp = self._ctx(browser, 'dark', os_scheme='dark', force_dark=True, dsf=1)
        dp.evaluate("async()=>{ equipmentViewMode='pack'; openDrawer('equipment'); await new Promise(s=>setTimeout(s,400)); }")
        dp.mouse.move(5, 5)
        sb = dp.evaluate("()=>{ const r=document.querySelector('#drawer-content .equip-view-seg button[aria-pressed=\"true\"]').getBoundingClientRect(); return [r.left+4, r.top+4]; }")
        img = cv2.imdecode(np.frombuffer(dp.screenshot(), np.uint8), cv2.IMREAD_COLOR)
        sel_lum = self._lum(img[int(sb[1]), int(sb[0])])
        c['app_dark_left_alone_by_forced_dark'] = sel_lum > 0.6
        if sel_lum <= 0.6:
            print('    selected segment luminance', round(sel_lum, 3))
        dctx.close()
        # ================= 對焦、錯誤、高對比模式 =================
        lctx, lp = self._ctx(browser, 'light')
        c['focus_ring_turns_green'] = self.ev(lp, """async()=>{ const wait=ms=>new Promise(s=>setTimeout(s,ms));
            const trail=getComputedStyle(document.documentElement).getPropertyValue('--trail').trim();
            const probe=document.createElement('i'); probe.style.color=trail; document.body.appendChild(probe); const g=getComputedStyle(probe).color; probe.remove();
            const bd=getComputedStyle(document.documentElement).getPropertyValue('--field-border').trim();
            const p2=document.createElement('i'); p2.style.color=bd; document.body.appendChild(p2); const b=getComputedStyle(p2).color; p2.remove();
            openDrawer('basicInfo'); await wait(250);
            const inp=document.querySelector('#drawer-content .field input[type=text]');
            const rest=getComputedStyle(inp).boxShadow.includes(b);
            inp.focus(); await wait(220); const foc=getComputedStyle(inp).boxShadow; const focOk=foc.includes(g)&&foc.split('px').length>6;
            inp.blur(); await wait(220); const back=getComputedStyle(inp).boxShadow.includes(b);
            closeDrawer(); equipmentViewMode='pack'; openDrawer('equipment'); await wait(250);
            const add=document.querySelector('#drawer-content .pack-add'); const addRest=getComputedStyle(add).boxShadow.includes(b);
            add.querySelector('input').focus(); await wait(220); const addFoc=getComputedStyle(add).boxShadow.includes(g);
            add.querySelector('input').blur(); closeDrawer();
            if(!(rest&&focOk&&back&&addRest&&addFoc)) console.log('fields: focus',rest,focOk,back,addRest,addFoc,foc);
            return rest && focOk && back && addRest && addFoc; }""")
        # 看不懂的時間格式：框變紅（原本用 border-color，框改成 box-shadow 之後要跟著改）
        c['invalid_duration_ring_is_red'] = self.ev(lp, """async()=>{ const wait=ms=>new Promise(s=>setTimeout(s,ms));
            const p=document.createElement('i'); p.style.color=getComputedStyle(document.documentElement).getPropertyValue('--flag').trim(); document.body.appendChild(p); const flag=getComputedStyle(p).color; p.remove();
            selectRace(__did); await wait(250); openDrawer('results'); await wait(250);
            const inp=document.querySelector('#drawer-content input[data-kind="duration"]'); if(!inp) return false;
            inp.focus(); inp.value='abc'; inp.dispatchEvent(new Event('input',{bubbles:true})); await wait(150);
            const bad=inp.getAttribute('aria-invalid')==='true' && getComputedStyle(inp).boxShadow.includes(flag);
            inp.value=''; inp.dispatchEvent(new Event('input',{bubbles:true})); inp.blur(); await wait(100); closeDrawer();
            return bad; }""")
        # Windows 高對比模式會拿掉 box-shadow：輸入框靠透明的 border 被畫成系統顏色、勾選方塊靠 outline
        lp.emulate_media(forced_colors='active')
        c['high_contrast_mode_keeps_frames'] = self.ev(lp, """async()=>{ const wait=ms=>new Promise(s=>setTimeout(s,ms));
            selectRace(__rid); await wait(250); openDrawer('basicInfo'); await wait(250);
            const inp=document.querySelector('#drawer-content .field input[type=text]'), cs=getComputedStyle(inp);
            const a=__rgba(cs.borderTopColor)[3]===1 && parseFloat(cs.borderTopWidth)>=1 && __cr(__rgba(cs.borderTopColor),__behind(inp))>=3;
            closeDrawer(); equipmentViewMode='pack'; openDrawer('equipment'); await wait(250);
            const box=document.querySelector('#drawer-content .pack-row:not(.is-packed) .pack-box'), bs=getComputedStyle(box);
            // 方塊的框可以是 outline 或 border，看得到就好
            const b=(bs.outlineStyle!=='none' && parseFloat(bs.outlineWidth)>0 && __rgba(bs.outlineColor)[3]===1 && __cr(__rgba(bs.outlineColor),__behind(box))>=3)
              || (parseFloat(bs.borderTopWidth)>0 && __rgba(bs.borderTopColor)[3]===1 && __cr(__rgba(bs.borderTopColor),__behind(box))>=3);
            const add=document.querySelector('#drawer-content .pack-add'), as=getComputedStyle(add);
            const d=__rgba(as.borderTopColor)[3]===1 && __cr(__rgba(as.borderTopColor),__behind(add))>=3;
            closeDrawer();
            if(!(a&&b&&d)) console.log('fields: hc',a,b,d,cs.borderTopColor,bs.outlineColor,as.borderTopColor);
            return a && b && d; }""")
        lp.emulate_media(forced_colors='none')
        lctx.close()
        # ================= 使用說明（三種語言：瀏覽器的強制深色、改用 App 的深色模式） =================
        c['help_explains_forced_dark'] = self.ev(page, """async()=>{ const wait=ms=>new Promise(s=>setTimeout(s,ms)); const out={};
            for(const [lang,word] of [['zh','網頁強制深色'],['ja','強制ダークモード'],['en','force dark mode for web contents']]){ setLang(lang); await wait(150); openHelpModal(); await wait(200);
              const tx=document.querySelector('#help-modal .help-body').textContent; out[lang]=tx.includes('Auto Dark Mode')&&tx.includes(word);
              document.querySelector('#help-modal [data-action="close-help"]').click(); await wait(200); }
            setLang('zh'); await wait(150);
            if(!(out.zh&&out.ja&&out.en)) console.log('fields: help',JSON.stringify(out));
            return out.zh && out.ja && out.en; }""")
        # （版本號的檢查跟著最新的群組走，v4.4.0 起在 v44）


# 號碼布牆用的賽事：各種號碼（短、長、英文字母、中文、一位數）、有封面照的、PB、沒距離、沒成績、
# 沒日期、很長的賽名；還有不該上牆的（還沒比、沒跑完、刪掉的）
WALL_SEED_JS = r"""window.__seedBibWall=async function(opts){ opts=opts||{};
  const cv=document.createElement('canvas'); cv.width=96; cv.height=72; const g=cv.getContext('2d');
  const gr=g.createLinearGradient(0,0,0,72); gr.addColorStop(0,'#F4C27A'); gr.addColorStop(1,'#1F4E79'); g.fillStyle=gr; g.fillRect(0,0,96,72);
  const cover=cv.toDataURL('image/jpeg',.8);
  const mk=o=>{ const r=emptyRace(o.n,o.s,o.st||'completed',o.d||''); r.route.distanceKm=o.km==null?null:o.km;
    r.results.chipTimeSeconds=o.t?hmsToSec(o.t):null; r.results.isPb=!!o.pb; r.bibNumber=o.bib||'';
    if(o.cover){ r.coverImage=cover; r.coverThumb=cover; } if(o.del) r.deletedAt=new Date().toISOString(); return r; };
  const L=[
    {n:'長號碼的馬拉松',s:'road_running',d:'2026-04-12',km:42.195,t:'3:15:20',bib:'M102345',pb:1},
    {n:'英文字母號碼',s:'trail_running',d:'2026-03-08',km:50,t:'7:02:11',bib:'WM-88421'},
    {n:'中文號碼',s:'duathlon',d:'2026-02-22',km:21.0975,t:'1:39:59',bib:'B區1234'},
    {n:'只有距離',s:'cycling',d:'2026-01-18',km:160.93},
    {n:'第三十八屆國際城市超級馬拉松暨全民健康路跑嘉年華',s:'ultra_marathon',d:'2026-01-04',km:246,t:'35:12:40',bib:'7',pb:1},
    {n:'澎湖超級鐵人三項',s:'triathlon',d:'2025-10-05',km:226,t:'12:41:09',pb:1,bib:'1088',cover:1},
    {n:'東京馬拉松',s:'road_running',d:'2025-03-02',km:42.195,t:'3:24:50',bib:'12345',cover:1},
    {n:'合歡山越野挑戰賽',s:'trail_running',d:'2024-11-17',km:25,t:'4:12:30',cover:1},
    {n:'神戶馬拉松',s:'road_running',d:'2024-11-10',km:42.195,t:'3:31:02',bib:'8821'},
    {n:'臺東巴歌浪鐵人三項',s:'triathlon',d:'2024-04-14',km:113,t:'5:58:12',pb:1,bib:'356'},
    {n:'大阪馬拉松',s:'road_running',d:'2024-02-25',km:42.195,t:'3:28:41',bib:'30412'},
    {n:'臺北馬拉松',s:'road_running',d:'2023-12-17',km:42.195,t:'3:38:15',bib:'A1520'},
    {n:'萬金石馬拉松（半程）',s:'road_running',d:'2023-03-19',km:21.0975,t:'1:36:20',pb:1,bib:'H3307'},
    {n:'手錶量的 10K',s:'road_running',d:'2023-01-08',km:9.97,t:'0:47:12'},
    {n:'臺南標準鐵人三項',s:'triathlon',d:'2022-05-08',km:51.5,t:'2:31:45',pb:1},
    {n:'日月潭泳渡',s:'swimming',d:'2022-03-13',km:3.3,t:'1:18:22'},
    {n:'東海岸超級馬拉松 100K',s:'ultra_marathon',d:'2019-10-27',km:100,t:'11:48:30',pb:1},
    {n:'斯巴達障礙跑 Sprint',s:'obstacle_race',d:'2019-04-14',km:5,t:'0:58:10'},
    {n:'公司運動會大隊接力',s:'other',d:'2019-03-10'},
    {n:'沒填日期的比賽',s:'road_running',d:'',km:10,t:'0:48:30',bib:'2077'},
    {n:'沒日期沒成績',s:'obstacle_race',d:''},
    {n:'報名了還沒比',s:'road_running',st:'registered',d:'2026-11-01',km:42.195},
    {n:'沒跑完',s:'trail_running',st:'dnf',d:'2025-06-01',km:50},
    {n:'刪掉的',s:'road_running',d:'2025-05-01',km:10,t:'0:50:00',del:1},
  ];
  state.races=L.concat(opts.extra||[]).map(mk).filter(opts.keep||(()=>true)); state.selectedId=null; state.filterStatus='all'; state.searchQuery='';
  const si=document.getElementById('search-input'); if(si) si.value='';
  state.viewMode='grid'; await persist(); setPhoneView('grid'); renderAll(); await new Promise(s=>setTimeout(s,250));
  // v4.5.1 起每一年可以收起來、預設只展開今年：要看每一張卡（v44 的版面、對比檢查）就先按「全部展開」
  if(opts.expand){ const b=document.querySelector('#calendar [data-action="wall-toggle-all"]'); if(b&&b.dataset.open==='1') b.click(); await new Promise(s=>setTimeout(s,150)); }
};
window.__card=n=>{ const r=state.races.find(x=>x.name===n); return r&&document.querySelector('#calendar .photo-card[data-id="'+r.id+'"]'); };
// 字底下真正的顏色：往上找第一層不透明的底；號碼布的紙是漸層，拿漸層裡的每一個顏色都比一次、取最差的
window.__under=el=>{ let e=el; const layers=[];
  while(e){ const cs=getComputedStyle(e);
    if(/gradient/.test(cs.backgroundImage)&&!e.classList.contains('bib-holes')){
      const cols=(cs.backgroundImage.match(/(rgba?|color)\([^)]*\)/g)||[]).map(__rgba).filter(c=>c[3]>=1);
      if(cols.length) return cols.map(c=>layers.reduceRight((bg,l)=>__over(l,bg),c)); }
    const b=__rgba(cs.backgroundColor); if(b[3]>0) layers.push(b); if(b[3]>=1) break; e=e.parentElement; }
  let bg=[255,255,255,1]; for(let i=layers.length-1;i>=0;i--) bg=__over(layers[i],bg); return [bg]; };
window.__textCr=el=>{ const fg=__rgba(getComputedStyle(el).color); return Math.min(...__under(el).map(bg=>__cr(__over(fg,bg),bg))); };
"""

# 號碼布牆的版面：每張號碼布的賽名帶、號碼、左下角的字、晶片條都在紙裡面；號碼沒被切掉、
# 每一個字的中心都不在 PB 印章底下、賽名帶的字不跑到印章底下；印章裡的字在內圈裡；
# 拍立得的距離在照片裡、日期和成績在卡片裡；沒有橫向捲動
BIB_FIT_JS = r"""()=>{ const bad=[];
  const st=document.createElement('style'); st.textContent='.photo-card{transform:none!important;transition:none!important}'; document.head.appendChild(st);
  const R=e=>e.getBoundingClientRect();
  const inside=(a,b,tol=0.5)=>a.left>=b.left-tol&&a.right<=b.right+tol&&a.top>=b.top-tol&&a.bottom<=b.bottom+tol;
  const cut=e=>e.scrollWidth>e.clientWidth+1;
  const name=c=>(c.title||'?').slice(0,8);
  document.querySelectorAll('#calendar .bib-card').forEach(c=>{ const cr=R(c);
    ['.bib-head','.bib-num','.bib-timing'].forEach(s=>{ const e=c.querySelector(s); if(e&&!inside(R(e),cr)) bad.push(name(c)+' out '+s); });
    const no=c.querySelector('.bib-no'); if(cut(no)) bad.push(name(c)+' number cut '+no.textContent);
    if(!inside(R(no),R(c.querySelector('.bib-num')),1)) bad.push(name(c)+' number spills');
    const tag=c.querySelector('.bib-tag'); if(cut(tag)) bad.push(name(c)+' tag cut '+tag.textContent);
    // v4.6.0：成績、均速、爬升在底部的計時帶裡，每一樣都在帶子裡、沒被切掉，號碼底下那一行在號碼下面
    const band=c.querySelector('.bib-timing');
    if(band) band.querySelectorAll('.bib-time,.bib-pace,.bib-elev').forEach(e=>{ if(!inside(R(e),R(band),0.5)) bad.push(name(c)+' band text out '+e.textContent); if(cut(e)) bad.push(name(c)+' band text cut '+e.textContent); });
    if(R(tag).top<R(no).bottom-2) bad.push(name(c)+' tag overlaps number');
    const race=c.querySelector('.bib-race'), fz=parseFloat(getComputedStyle(race).fontSize);
    if(race.clientWidth<Math.min(race.scrollWidth,4*fz)-1) bad.push(name(c)+' race name too narrow '+race.clientWidth);
    const sp=c.querySelector('.bib-stamp');
    // 印章自己轉了 -16°：外框比圓大，圓心用外框的中心、半徑用沒轉之前的寬度
    if(sp){ const s=R(sp), cx=s.left+s.width/2, cy=s.top+s.height/2, r=parseFloat(getComputedStyle(sp).width)/2;
      const tw=document.createTreeWalker(no,NodeFilter.SHOW_TEXT); let n;
      while((n=tw.nextNode())){ for(let i=0;i<n.length;i++){ const rg=document.createRange(); rg.setStart(n,i); rg.setEnd(n,i+1); const b=rg.getBoundingClientRect();
        if(b.width&&Math.hypot(b.left+b.width/2-cx,b.top+b.height/2-cy)<r) bad.push(name(c)+' stamp covers '+n.data[i]); } }
      const rr=R(race); if(Math.hypot(rr.right-cx,Math.min(rr.bottom,cy)-cy)<r-1) bad.push(name(c)+' stamp covers race name');
      if(cx-r<cr.left-1||cx+r>cr.right+1||cy-r<cr.top-1) bad.push(name(c)+' stamp off card');
    }
  });
  document.querySelectorAll('#calendar .pola-card').forEach(c=>{ const cr=R(c);
    const d=c.querySelector('.pola-dist'); if(d&&!inside(R(d),R(c.querySelector('.pola-photo')))) bad.push(name(c)+' dist out of photo');
    const cap=R(c.querySelector('.pola-cap'));
    c.querySelectorAll('.pola-meta span,.bib-timing .bib-time,.bib-timing .bib-pace,.bib-timing .bib-elev').forEach(e=>{ if(!inside(R(e),cap)) bad.push(name(c)+' meta out '+e.textContent); });
    if(!inside(R(c.querySelector('.pola-cap')),cr)) bad.push(name(c)+' caption out');
  });
  // 印章裡的字（SVG）：getBBox 的高度是字型的整個行高、不是墨水；橫向用 bbox（textLength 固定了寬度），
  // 直向用基線往上 0.9 個字級到往下 0.15 個字級，四個角都要在內圈（半徑 24）裡
  document.querySelectorAll('#calendar .bib-stamp').forEach(sv=>{ sv.querySelectorAll('text').forEach(t=>{ const b=t.getBBox(), fz=parseFloat(getComputedStyle(t).fontSize), y0=t.y.baseVal[0].value;
    const top=y0-0.9*fz, bot=y0+0.15*fz;
    if([[b.x,top],[b.x+b.width,top],[b.x,bot],[b.x+b.width,bot]].some(([x,y])=>Math.hypot(x-30,y-30)>24)) bad.push('stamp text out '+t.textContent); }); });
  if(document.documentElement.scrollWidth>innerWidth) bad.push('hscroll');
  if(!document.querySelector('#calendar .bib-card')) bad.push('no bibs');
  st.remove();
  return [...new Set(bad)]; }"""


class V44BibWall(Group):
    """v4.4.0：獎牌牆改成號碼布牆——依年份分段（場數、里程、PB 數）；沒有封面照的完賽是那一場的
    號碼布（賽名帶、號碼或距離、晶片條上的成績），有封面照的是拍立得，PB 蓋紅色印章。
    各種寬度、語言、字級都放得下；淺色、深色、瀏覽器強制深色都看得清楚。"""

    ECHO = ('wall:',)

    def _echo(self, msg):
        if msg.text.startswith(self.ECHO):
            print('   ', msg.text[:300])

    def ev(self, pg, js, arg=None):
        # 一項檢查拋出例外：記成這一項失敗、印出原因，後面照跑
        try:
            return pg.evaluate(js) if arg is None else pg.evaluate(js, arg)
        except Exception as exc:                      # noqa: BLE001
            print('    ⚠', str(exc).split('\n')[0][:200])
            return False

    def _ctx(self, browser, viewport, theme='light', touch=False, lang=None, force_dark=False, dsf=1):
        ctx = full_mode_context(browser, viewport=viewport, is_mobile=touch, has_touch=touch, color_scheme='light', device_scale_factor=dsf)
        init = f"localStorage.setItem('theme-pref-v1','{theme}');"
        if lang:
            init += f"localStorage.setItem('lang-pref-v1','{lang}');"
        ctx.add_init_script('try{' + init + '}catch(e){}')
        pg = ctx.new_page()
        if force_dark:
            cdp = ctx.new_cdp_session(pg)
            cdp.send('Emulation.setAutoDarkModeOverride', {'enabled': True})
        pg.on('pageerror', lambda e: self.errors.append(str(e)))
        pg.on('console', self._echo)
        pg.goto(APP_URL)
        pg.wait_for_timeout(900)
        pg.add_script_tag(content=FIELD_FRAME_JS)
        pg.add_script_tag(content=WALL_SEED_JS)
        pg.add_style_tag(content='.badge-unbox-overlay,.foreground-toast{display:none!important}')
        pg.evaluate("()=>__seedBibWall({expand:true})")
        pg.wait_for_timeout(300)
        return ctx, pg

    def body(self, page):
        c = self.checks
        browser = page.context.browser
        W = ("const wait=ms=>new Promise(s=>setTimeout(s,ms));"
             "const home=async()=>{ for(let i=0;i<12;i++){ if(!document.getElementById('global-drawer').hidden){ closeDrawer(); await wait(300); continue; } if(state.selectedId||state.creating){ goBackFromDetail(); await wait(350); continue; } break; } };")
        ctx, pg = self._ctx(browser, {'width': 1280, 'height': 900})
        # ================= 分段、順序、統計 =================
        c['wall_has_each_finished_race_once_newest_first'] = self.ev(pg, """()=>{
            const done=state.races.filter(r=>!r.deletedAt&&r.status==='completed').sort((a,b)=>(b.schedule.raceDate||'').localeCompare(a.schedule.raceDate||''));
            const ids=[...document.querySelectorAll('#calendar .photo-card')].map(b=>b.dataset.id);
            const ok=JSON.stringify(ids)===JSON.stringify(done.map(r=>r.id)) && done.length===21;
            if(!ok) console.log('wall: ids',ids.length,done.length);
            return ok; }""")
        c['sections_by_year_undated_last'] = self.ev(pg, """()=>{
            const heads=[...document.querySelectorAll('#calendar .bib-sec')].map(s=>s.querySelector('h3 .bib-ynum').textContent);
            const per=[...document.querySelectorAll('#calendar .bib-sec')].map(s=>[...s.querySelectorAll('.photo-card')].map(b=>{ const r=state.races.find(x=>x.id===b.dataset.id); return (r.schedule.raceDate||'').slice(0,4)||'—'; }));
            const ok=JSON.stringify(heads)===JSON.stringify(['2026','2025','2024','2023','2022','2019','未定日期'])
              && per.every((ys,i)=>ys.every(y=>y===(heads[i]==='未定日期'?'—':heads[i])));
            if(!ok) console.log('wall: heads',heads.join(','));
            return ok; }""")
        # 每一段的標題：場數、四捨五入的總里程、PB 數（沒有 PB 就不寫；沒有里程就不寫）
        c['year_header_counts_races_km_pb'] = self.ev(pg, """()=>{
            const got=[...document.querySelectorAll('#calendar .bib-ystats')].map(e=>e.textContent.replace(/\\s+/g,' ').trim());
            const want=['5 場 · 520 km · 2 PB','2 場 · 268 km · 1 PB','4 場 · 222 km · 1 PB','3 場 · 73 km · 1 PB','2 場 · 55 km · 1 PB','3 場 · 105 km · 1 PB','2 場 · 10 km'];
            if(JSON.stringify(got)!==JSON.stringify(want)) console.log('wall: stats',got.join(' | '));
            return JSON.stringify(got)===JSON.stringify(want) && !!document.querySelector('#calendar .bib-ystats b'); }""")
        # ================= 號碼布上寫什麼 =================
        # 大字：有號碼寫號碼；沒有號碼寫距離（斜體）；兩個都沒有畫運動別的圖示。左下角：大字是號碼時寫距離，
        # 否則寫運動別。右下角：有成績寫在晶片條上，沒有成績寫日期
        c['bib_number_else_distance_else_icon'] = self.ev(pg, """()=>{ const bad=[];
            // v4.6.0 起成績在底部的計時帶上（沒有成績寫日期），距離（或運動別）寫在號碼底下
            const read=n=>{ const c=__card(n); const no=c.querySelector('.bib-no'), right=c.querySelector('.bib-timing .bib-time');
              return [c.querySelector('.bib-race').textContent, no.querySelector('svg')?'[icon]':no.textContent.trim(), getComputedStyle(no).fontStyle,
                c.querySelector('.bib-num .bib-tag').textContent, right?(right.classList.contains('is-date')?'date:':'time:')+right.textContent.trim():'', (c.querySelector('.bib-year')||{}).textContent||''].join('|'); };
            const want={
              '神戶馬拉松':'神戶馬拉松|8821|normal|42.2 KM|time:3:31:02|2024',
              '臺南標準鐵人三項':'臺南標準鐵人三項|51.5K|italic|三鐵|time:2:31:45|2022',
              '只有距離':'只有距離|160.9K|italic|自行車|date:2026.01.18|2026',
              '公司運動會大隊接力':'公司運動會大隊接力|[icon]|normal|其他|date:2019.03.10|2019',
              '沒日期沒成績':'沒日期沒成績|[icon]|normal|障礙賽||',
              '中文號碼':'中文號碼|B區1234|normal|21.1 KM|time:1:39:59|2026' };
            Object.entries(want).forEach(([n,w])=>{ const g=read(n); if(g!==w) bad.push(g); });
            if(bad.length) console.log('wall: bib',bad.join(' || '));
            return bad.length===0; }""")
        # 手錶量到的距離（9.97、21.0975、160.93）：四捨五入到小數一位，整數不寫「.0」
        c['distance_rounds_to_one_decimal'] = self.ev(pg, """()=>{
            const got=['手錶量的 10K','萬金石馬拉松（半程）','只有距離','東海岸超級馬拉松 100K','日月潭泳渡'].map(n=>{ const c=__card(n); const num=c.querySelector('.bib-num');
              return num.classList.contains('is-dist')?num.querySelector('.bib-no').textContent.trim():c.querySelector('.bib-tag').textContent; }).join(',');
            // 游泳寫公尺（v4.6.0）
            if(got!=='10K,21.1 KM,160.9K,100K,3300M') console.log('wall: round',got);
            return got==='10K,21.1 KM,160.9K,100K,3300M'; }""")
        # 有封面照的是拍立得：照片、照片上的距離、賽名、日期和成績；沒有號碼布的東西
        c['cover_race_is_polaroid'] = self.ev(pg, """()=>{
            const r=state.races.find(x=>x.name==='東京馬拉松'), c=__card('東京馬拉松'); const img=c.querySelector('img');
            const meta=[...c.querySelectorAll('.pola-meta span')].map(s=>s.textContent);
            // v4.6.0：日期寫在賽名下面，成績、均速在下面那條計時帶上
            const band=c.querySelector('.bib-timing.is-pola');
            return !!img && img.getAttribute('src')===coverThumbOf(r) && c.querySelector('.pola-dist').textContent==='42.2K'
              && c.querySelector('.pola-name').textContent==='東京馬拉松' && JSON.stringify(meta)==='["2025.03.02"]'
              && !!band && band.querySelector('.bib-time').textContent==='3:24:50' && band.querySelector('.bib-pace').textContent==='4\\'51"/km'
              && !c.querySelector('.bib-num,.bib-head') && document.querySelectorAll('#calendar .pola-card').length===3; }""")
        # PB 才有印章（號碼布、拍立得都是），淺色、深色都一樣
        c['pb_stamp_only_on_pb_light_and_dark'] = self.ev(pg, """async()=>{ """ + W + """
            const check=()=>[...document.querySelectorAll('#calendar .photo-card')].every(b=>{ const r=state.races.find(x=>x.id===b.dataset.id);
              const sp=b.querySelector('.bib-stamp'); return r.results.isPb ? (!!sp && sp.getBoundingClientRect().width>30 && sp.textContent.includes('PB')) : !sp; });
            const light=check(); applyTheme('dark'); await wait(150); const dark=check(); applyTheme('light'); await wait(150);
            return light && dark && document.querySelectorAll('#calendar .bib-stamp').length===7; }""")
        # 賽名帶是運動別的顏色：每個運動別不一樣，白字至少 4.5:1；大字的距離用同一個顏色，紙上至少 3:1（大字）
        c['band_color_by_sport_and_readable'] = self.ev(pg, """async()=>{ """ + W + """
            const st=document.createElement('style'); st.textContent='*{transition:none!important}'; document.head.appendChild(st);
            const bands=[...document.querySelectorAll('#calendar .bib-card')].map(b=>[b.dataset.sport,getComputedStyle(b.querySelector('.bib-head')).backgroundColor]);
            const bySport={}; bands.forEach(([s,col])=>{ (bySport[s]=bySport[s]||new Set()).add(col); });
            const oneEach=Object.values(bySport).every(s=>s.size===1), distinct=new Set(Object.values(bySport).map(s=>[...s][0])).size===Object.keys(bySport).length;
            const read=()=>{ const bad=[];
              document.querySelectorAll('#calendar .bib-race').forEach(e=>{ const cr=__textCr(e); if(cr<4.5) bad.push(e.textContent.slice(0,6)+' '+cr.toFixed(2)); });
              document.querySelectorAll('#calendar .bib-num.is-dist .bib-no').forEach(e=>{ const cr=__textCr(e); if(cr<3) bad.push('dist '+e.textContent+' '+cr.toFixed(2)); });
              return bad; };
            const light=read(); applyTheme('dark'); await wait(150); const dark=read(); applyTheme('light'); await wait(150); st.remove();
            if(light.length||dark.length||!oneEach||!distinct) console.log('wall: band',oneEach,distinct,light.join(' | '),'/',dark.join(' | '));
            return oneEach && distinct && Object.keys(bySport).length>=8 && !light.length && !dark.length; }""")
        # 紙上、晶片條上、拍立得上、段落標題的字：淺色、深色都至少 4.5:1（大字的號碼 3:1）
        c['wall_text_readable_light_and_dark'] = self.ev(pg, """async()=>{ """ + W + """
            const st=document.createElement('style'); st.textContent='*{transition:none!important}'; document.head.appendChild(st);
            const read=()=>{ const bad=[];
              document.querySelectorAll('#calendar .bib-tag,#calendar .bib-time,#calendar .bib-pace,#calendar .bib-elev,#calendar .pola-name,#calendar .pola-meta span,#calendar .bib-ystats,#calendar .bib-ystats b,#calendar .bib-year')
                .forEach(e=>{ const cr=__textCr(e); if(cr<4.5) bad.push(e.className+' '+e.textContent.slice(0,8)+' '+cr.toFixed(2)); });
              document.querySelectorAll('#calendar .bib-num:not(.is-dist):not(.is-icon) .bib-no,#calendar .bib-ynum').forEach(e=>{ const cr=__textCr(e); if(cr<3) bad.push('big '+e.textContent+' '+cr.toFixed(2)); });
              return [...new Set(bad)]; };
            const light=read(); applyTheme('dark'); await wait(150); const dark=read(); applyTheme('light'); await wait(150); st.remove();
            if(light.length||dark.length) console.log('wall: contrast',light.slice(0,6).join(' | '),'/',dark.slice(0,6).join(' | '));
            return !light.length && !dark.length; }""")
        # 報讀的名稱是一句完整的話：賽名、日期、距離、成績、號碼、PB（卡片上的版面直接唸會沒頭沒尾）
        c['screen_reader_label_says_name_date_time_bib_pb'] = self.ev(pg, """()=>{
            const a=__card('臺東巴歌浪鐵人三項').getAttribute('aria-label'), b=__card('合歡山越野挑戰賽').getAttribute('aria-label');
            // v4.6.0：均速也唸出來（三鐵不寫均速）
            const ok=a==='臺東巴歌浪鐵人三項, 三鐵, 2024-04-14, 113 km, 5:58:12, 號碼布 356, 個人最佳 PB' && b==='合歡山越野挑戰賽, 越野跑, 2024-11-17, 25 km, 4:12:30, 均速 10\\'06"/km'
              && [...document.querySelectorAll('#calendar .photo-card')].every(x=>x.tagName==='BUTTON'&&x.getAttribute('aria-label'))
              && document.querySelectorAll('#calendar .bib-yhead').length===7 && document.querySelector('#calendar .bib-yhead').tagName==='H3';
            if(!ok) console.log('wall: label',a,'/',b);
            return ok; }""")
        # 每張卡的小角度每次畫都一樣（重畫、切檢視不會整面牆跳一下），而且不是每張都同一個角度
        c['card_tilt_stable_across_rerender'] = self.ev(pg, """async()=>{ """ + W + """
            const rots=()=>[...document.querySelectorAll('#calendar .photo-card')].map(b=>b.style.getPropertyValue('--rot'));
            const a=rots(); state.viewMode='calendar'; renderCalendar(); await wait(50); state.viewMode='grid'; renderCalendar(); await wait(50); const b=rots();
            return JSON.stringify(a)===JSON.stringify(b) && new Set(a).size>5 && a.every(x=>Math.abs(parseFloat(x))<=3); }""")
        # 滑鼠移上去：扶正、浮起來（不再跟著游標轉）
        pg.add_style_tag(content='*{transition:none!important}')
        box = pg.evaluate("""()=>{ const c=__card('神戶馬拉松'); c.scrollIntoView({block:'center'}); const r=c.getBoundingClientRect(); return [r.left+r.width/2,r.top+r.height/2,parseFloat(c.style.getPropertyValue('--rot'))]; }""")
        before = pg.evaluate("()=>getComputedStyle(__card('神戶馬拉松')).transform")
        pg.mouse.move(box[0], box[1]); pg.wait_for_timeout(100)
        pg.mouse.move(box[0] + 20, box[1] + 10); pg.wait_for_timeout(100)
        after = pg.evaluate("()=>[getComputedStyle(__card('神戶馬拉松')).transform,__card('神戶馬拉松').style.getPropertyValue('--tilt-x')]")
        pg.mouse.move(5, 5); pg.wait_for_timeout(50)
        m = [float(v) for v in re.findall(r'-?[\d.e]+', before)]
        rot_ok = len(m) == 6 and abs(math.degrees(math.atan2(m[1], m[0])) - box[2]) < 0.05 and abs(box[2]) > 0.01
        c['hover_straightens_and_lifts_card'] = rot_ok and after[0] == 'matrix(1, 0, 0, 1, 0, -3)' and after[1] == ''
        # 點一下打開那一場，返回回到牆上（號碼布、拍立得都是）；鍵盤：Tab 到卡片有看得到的框，Enter 打開
        c['click_opens_race_back_returns_to_wall'] = self.ev(pg, """async()=>{ """ + W + """
            let ok=true;
            for(const n of ['神戶馬拉松','東京馬拉松']){ const el=__card(n); const id=el.dataset.id; el.click(); await wait(500);
              ok=ok&&state.selectedId===id; await home(); ok=ok&&state.selectedId===null&&state.viewMode==='grid'&&!!__card(n); }
            return ok; }""")
        pg.keyboard.press('Tab')
        c['keyboard_focus_ring_and_enter_opens'] = self.ev(pg, """async()=>{ """ + W + """
            const el=__card('大阪馬拉松'); el.focus(); await wait(50); const cs=getComputedStyle(el);
            const ring=el.matches(':focus-visible') && cs.outlineStyle==='solid' && parseFloat(cs.outlineWidth)>=2 && __cr(__rgba(cs.outlineColor),__under(el.parentElement)[0])>=3;
            return { ring, id:el.dataset.id }; }""")
        ring = c['keyboard_focus_ring_and_enter_opens']
        if ring and ring.get('ring'):
            pg.keyboard.press('Enter'); pg.wait_for_timeout(500)
            opened = pg.evaluate("(id)=>state.selectedId===id", ring['id'])
            pg.evaluate("async()=>{ " + W + " await home(); }")
            c['keyboard_focus_ring_and_enter_opens'] = bool(opened)
        else:
            c['keyboard_focus_ring_and_enter_opens'] = False
        # ================= 字型 =================
        # 大字用 Barlow Condensed（號碼布、計時看板的窄體字），載不到時有系統內建的窄體字可以接
        c['display_font_requested_with_condensed_fallbacks'] = self.ev(pg, """()=>{
            const href=[...document.querySelectorAll('link[rel="stylesheet"]')].map(l=>l.href).find(h=>h.includes('fonts.googleapis.com'))||'';
            const ff=getComputedStyle(document.querySelector('#calendar .bib-no')).fontFamily;
            return /family=Barlow\\+Condensed:ital,wght@[^&]*0,900[^&]*1,900/.test(href) && /^"?Barlow Condensed"?,/.test(ff) && /Condensed.*sans-serif$/.test(ff) && ff.split(',').length>=4; }""")
        # ================= 三種語言 =================
        c['stamp_and_header_in_three_languages'] = self.ev(pg, """async()=>{ """ + W + """ const out={};
            for(const lang of ['zh','ja','en']){ setLang(lang); await wait(150);
              out[lang]=[document.querySelector('#calendar .bib-stamp-sub').textContent, document.querySelector('#calendar .bib-ystats').textContent.replace(/\\s+/g,' ').trim(),
                [...document.querySelectorAll('#calendar .bib-ynum')].pop().textContent, __card('臺南標準鐵人三項').querySelector('.bib-tag').textContent].join('|'); }
            setLang('zh'); await wait(150);
            const ok=out.zh==='個人最佳|5 場 · 520 km · 2 PB|未定日期|三鐵' && out.ja==='ベスト|5 レース · 520 km · 2 PB|日付未定|トライアスロン'
              && out.en==='BEST|5 races · 520 km · 2 PB|No date yet|Triathlon';
            if(!ok) console.log('wall: lang',JSON.stringify(out));
            return ok; }""")
        c['help_describes_bib_wall'] = self.ev(pg, """async()=>{ """ + W + """ const out={};
            for(const [lang,words] of [['zh',['號碼布','拍立得','紅色印章','號碼布編號']],['ja',['ゼッケン','ポラロイド','赤いスタンプ','ゼッケン番号']],['en',['bib','polaroid','red stamp','Bib Number']]]){
              setLang(lang); await wait(150); openHelpModal(); await wait(200);
              const tx=document.querySelector('#help-modal .help-body').textContent; out[lang]=words.every(w=>tx.includes(w)) && !/金框|金の枠|gold rim/.test(tx);
              document.querySelector('#help-modal [data-action="close-help"]').click(); await wait(200); }
            setLang('zh'); await wait(150);
            if(!(out.zh&&out.ja&&out.en)) console.log('wall: help',JSON.stringify(out));
            return out.zh && out.ja && out.en; }""")
        c['empty_wall_shows_message'] = self.ev(pg, """async()=>{ """ + W + """
            const keep=state.races; state.races=keep.filter(r=>r.status!=='completed'); renderCalendar(); await wait(100);
            const wrap=document.querySelector('#calendar .photo-grid-wrap');
            const ok=!!wrap && wrap.textContent.includes('還沒有已完賽的賽事') && !wrap.querySelector('.photo-card,.bib-sec');
            state.races=keep; renderCalendar(); return ok; }""")
        # （版本號的檢查跟著最新的群組走，v4.5.0 起在 v45）
        ctx.close()
        # ================= 各種寬度 × 語言 × 字級都放得下 =================
        # 沙盒連不到 Google Fonts：這裡量到的是備援字型（一般無襯線字，比 Barlow Condensed 寬很多），是最擠的情況
        FIT_ALL = """async()=>{ const wait=ms=>new Promise(s=>setTimeout(s,ms)); const fit=""" + BIB_FIT_JS + """; const bad=[];
            for(const lang of ['zh','ja','en']){ setLang(lang); await wait(120);
              for(const fs of ['small','medium','large']){ applyFontScale(fs); await wait(80); fit().forEach(b=>bad.push(lang+' '+fs+' '+b)); } }
            setLang('zh'); applyFontScale('medium');
            if(bad.length) console.log('wall: fit',bad.slice(0,10).join(' | '));
            return bad.length===0; }"""
        for w in (360, 390, 700, 1280):
            fctx, fp = self._ctx(browser, {'width': w, 'height': 900}, touch=w < 641)
            c[f'fits_{w}_all_languages_and_font_sizes'] = self.ev(fp, FIT_ALL)
            if w == 360:
                # 手機兩欄一樣寬（拍立得不換行的日期不會把那一欄撐寬）
                c['phone_two_equal_columns'] = self.ev(fp, """async()=>{ const r=state.races.find(x=>x.name==='東京馬拉松'); const keep=r.name;
                    r.name='東京馬拉松 Tokyo Marathon 2025 Elite Wave'; renderCalendar(); await new Promise(s=>setTimeout(s,80));
                    const ok=[...document.querySelectorAll('#calendar .bib-grid')].every(g=>{
                      const ws=[...g.children].map(x=>Math.round(x.offsetWidth)); return getComputedStyle(g).gridTemplateColumns.split(' ').length===2 && new Set(ws).size===1; });
                    r.name=keep; renderCalendar(); return ok; }""")
                # 長按號碼布：跳出快速動作，放開手指不會順便打開那一場
                c['long_press_bib_opens_context_sheet'] = self.ev(fp, """async()=>{ const wait=ms=>new Promise(s=>setTimeout(s,ms));
                    const card=__card('神戶馬拉松'); card.scrollIntoView({block:'center'}); await wait(100); const rect=card.getBoundingClientRect();
                    const opts={bubbles:true,pointerType:'touch',isPrimary:true,clientX:rect.x+rect.width/2,clientY:rect.y+rect.height/2,pointerId:1};
                    card.dispatchEvent(new PointerEvent('pointerdown',opts)); await wait(700);
                    card.dispatchEvent(new PointerEvent('pointerup',opts)); card.dispatchEvent(new MouseEvent('click',{bubbles:true,clientX:opts.clientX,clientY:opts.clientY}));
                    await wait(150); const sheet=document.getElementById('race-context-sheet');
                    const ok=!sheet.hidden && !!sheet.querySelector('[data-ctx="share"]') && state.selectedId===null;
                    closeRaceContextSheet(); return ok; }""")
            fctx.close()
        # ================= 瀏覽器的「網頁強制深色」 =================
        # 強制深色是畫的時候才轉的，算出來的樣式看不到，只能量畫面：PB 印章的圈跟旁邊的紙要看得出來
        # （設計稿的 mix-blend-mode:multiply 在轉成深色的紙上整個印章都不見了）
        for theme, force in (('light', True), ('light', False), ('dark', False)):
            sctx, sp = self._ctx(browser, {'width': 1280, 'height': 900}, theme=theme, force_dark=force, dsf=2)
            sp.add_style_tag(content='*{transition:none!important}')
            geo = sp.evaluate("""()=>{ const c=__card('臺東巴歌浪鐵人三項'); c.scrollIntoView({block:'center'}); const s=c.querySelector('.bib-stamp'), r=s.getBoundingClientRect();
                return [r.left+r.width/2, r.top+r.height/2, parseFloat(getComputedStyle(s).width)/2]; }""")
            sp.wait_for_timeout(200)
            img = cv2.imdecode(np.frombuffer(sp.screenshot(), np.uint8), cv2.IMREAD_COLOR)
            k = img.shape[1] / 1280
            cx, cy, r = geo[0] * k, geo[1] * k, geo[2] * k
            crs = []
            for deg in range(25, 160, 10):            # 下半圈：底下是紙，不是賽名帶
                a = math.radians(deg)
                best = 0
                for rr in (r * 0.93, r * 0.95, r * 0.97):
                    ring = img[int(cy + rr * math.sin(a)), int(cx + rr * math.cos(a))]
                    paper = img[int(cy + (r + 6 * k) * math.sin(a)), int(cx + (r + 6 * k) * math.cos(a))]
                    l1, l2 = V433Fields._lum(ring), V433Fields._lum(paper)
                    best = max(best, (max(l1, l2) + .05) / (min(l1, l2) + .05))
                crs.append(best)
            crs.sort()
            med = crs[len(crs) // 2]
            label = 'pb_stamp_visible_' + ('forced_dark' if force else theme)
            # 3:1 是 WCAG 對非文字圖形的要求；實測淺色 4.2、深色 3.7、強制深色 4.8，加回 multiply 的強制深色 1.08
            c[label] = med >= 3
            if med < 3:
                print(f'    wall: stamp {label} median contrast {med:.2f}')
            sctx.close()


# 沙盒連不到 jsDelivr：設 CDN_MIRROR=放著 xlsx.full.min.js（npm 原檔，SRI 雜湊一樣）的資料夾，
# Excel 那幾項就從那裡回應；沒設就照常走網路
CDN_MIRROR = os.environ.get('CDN_MIRROR', '')
XLSX_CDN_URL = 'https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js'
IPHONE_UA = ('Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 '
             '(KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1')


def tiny_xlsx(sheet, rows):
    """只用標準函式庫做一個最小的 .xlsx（一張工作表、字串用 inlineStr），測試不必多裝套件。"""
    import io, zipfile
    from xml.sax.saxutils import escape

    def col(i):
        s = ''
        i += 1
        while i:
            i, r = divmod(i - 1, 26)
            s = chr(65 + r) + s
        return s
    body = ''
    for ri, row in enumerate(rows, 1):
        cells = ''
        for ci, v in enumerate(row):
            ref = f'{col(ci)}{ri}'
            if isinstance(v, (int, float)):
                cells += f'<c r="{ref}"><v>{v}</v></c>'
            else:
                cells += f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(v))}</t></is></c>'
        body += f'<row r="{ri}">{cells}</row>'
    files = {
        '[Content_Types].xml': '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>',
        '_rels/.rels': '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        'xl/workbook.xml': '<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
            f'<sheet name="{escape(sheet)}" sheetId="1" r:id="rId1"/></sheets></workbook>',
        'xl/_rels/workbook.xml.rels': '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
        'xl/worksheets/sheet1.xml': '<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'<sheetData>{body}</sheetData></worksheet>',
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, text in files.items():
            z.writestr(name, text)
    return buf.getvalue()


# 七種資料各放一點：賽事（含一場在垃圾桶）、訓練（含一筆刪除墓碑）、鞋款、補給品、自訂範本、
# 個人資料（含居住縣市）、徽章
BACKUP_SEED_JS = r"""window.__seedSeven=async function(){
  const a=emptyRace('備份測試・全馬','road_running','completed','2025-03-01'); a.results.chipTimeSeconds=12000; a.route.distanceKm=42.195;
  const b=emptyRace('備份測試・越野','trail_running','registered','2027-05-01');
  const c=emptyRace('備份測試・垃圾桶','road_running','registered','2027-06-01'); c.deletedAt=new Date().toISOString();
  state.races.push(a,b,c); await persist();
  trainings.push(migrateTraining({id:'t1',date:'2025-02-01',sport:'run',name:'輕鬆跑',distanceKm:10,durationSeconds:3600,fingerprint:'fp1',importedAt:'2025-02-01T00:00:00Z'}));
  trainings.push(migrateTraining({id:'t2',date:'2025-02-03',sport:'ride',name:'騎車',distanceKm:40,durationSeconds:5400,fingerprint:'fp2',importedAt:'2025-02-03T00:00:00Z'}));
  trainings.push(migrateTraining({id:'t3',date:'2025-01-03',sport:'run',name:'刪掉的',distanceKm:5,durationSeconds:1800,fingerprint:'fp3',importedAt:'2025-01-03T00:00:00Z',deletedAt:'2025-01-04T00:00:00Z',updatedAt:'2025-01-04T00:00:00Z'}));
  await persistTrainings();
  shoes.push(migrateShoe({id:'s1',name:'Vaporfly 3',brand:'Nike'})); await persistShoes();
  nutritionDictionary.push(migrateNutritionDictItem({id:'n1',name:'Maurten Gel 100',carbGrams:25})); await persistNutritionDictionary();
  templates.push({id:'tpl-own',name:'我的越野包',items:[{itemName:'頭燈',category:'mandatory_gear',isMandatory:true}]}); await persistTemplates();
  userProfile=migrateUserProfile({weightKg:60,homeCounty:'台北市',hr:{running:{restingHr:50,maxHr:190}}}); await persistUserProfile();
  badgeUnlocks['first_finish']={unlockedAt:'2025-03-01T10:00:00Z',seen:true,triggerRaceId:a.id}; await persistBadgeUnlocks();
  renderAll();
};
// 沒登入的雲端：Firebase 回報「沒有登入」之前，跟一般打開網站一樣先不知道
window.__signedOutCloud=function(callNow){ const c=__makeFakeCloud([],[]); c.onAuthChange=cb=>{ window.__authCb=cb; if(callNow) cb(null); };
  window.__cloud=c; window.dispatchEvent(new Event('cloud-ready')); return c; };
window.__addLive=function(n){ for(let i=0;i<n;i++) state.races.push(emptyRace('提醒卡測試 '+i,'road_running','completed','2025-0'+(1+i%9)+'-01')); renderAll(); };
window.__card=()=>document.querySelector('#auth-area .backup-nudge');
window.__dot=()=>document.getElementById('btn-account-menu').classList.contains('has-alert');
"""

# 瀏覽器的 navigator.storage.persist() 換成會記次數的假函式（真的那個在無頭瀏覽器裡一律拒絕）
PERSIST_SPY_JS = """(()=>{ window.__persist={calls:0,granted:false,persisted:false};
  try{ const sm=navigator.storage;
    Object.defineProperty(sm,'persist',{configurable:true,value:async()=>{ window.__persist.calls++; return window.__persist.granted; }});
    Object.defineProperty(sm,'persisted',{configurable:true,value:async()=>window.__persist.persisted});
  }catch(e){} })();"""


class V45Backup(Group):
    """v4.5.0：完整備份（匯出七種資料、匯入合併還原、舊格式照收）；沒登入時的資料安全提醒（頭像選單的
    提醒卡、頭像的小紅點、持久保存、iPhone 加到主畫面的提示）；Excel 解析套件按「匯入 Excel」才載入；
    行事曆匯出不帶垃圾桶、沒東西可匯出時講一聲；生涯數據的 5 場門檻不算垃圾桶。"""

    ECHO = ('v45:',)

    def _echo(self, msg):
        if msg.text.startswith(self.ECHO):
            print('   ', msg.text[:300])

    def ev(self, pg, js, arg=None):
        try:
            return pg.evaluate(js) if arg is None else pg.evaluate(js, arg)
        except Exception as exc:                      # noqa: BLE001
            print('    ⚠', str(exc).split('\n')[0][:200])
            return False

    def _ctx(self, browser, viewport=None, touch=False, ua=None, init=(), lang=None, theme=None, spy=True):
        kw = dict(viewport=viewport or {'width': 1100, 'height': 900}, is_mobile=touch, has_touch=touch, accept_downloads=True)
        if ua:
            kw['user_agent'] = ua
        ctx = full_mode_context(browser, **kw)
        if spy:
            ctx.add_init_script(PERSIST_SPY_JS)
        pre = ''
        if lang:
            pre += f"localStorage.setItem('lang-pref-v1','{lang}');"
        if theme:
            pre += f"localStorage.setItem('theme-pref-v1','{theme}');"
        if pre:
            ctx.add_init_script('try{' + pre + '}catch(e){}')
        for s in init:
            ctx.add_init_script(s)
        pg = ctx.new_page()
        pg.on('pageerror', lambda e: self.errors.append(str(e)))
        pg.on('console', self._echo)
        return ctx, pg

    def _open(self, pg):
        pg.goto(APP_URL)
        pg.wait_for_timeout(900)
        pg.add_script_tag(content=FAKE_CLOUD_JS)
        pg.add_script_tag(content=BACKUP_SEED_JS)
        pg.add_script_tag(content=FIELD_FRAME_JS)

    def _import(self, pg, text, name='backup.json', wait=700):
        pg.set_input_files('#json-file-input', files=[{'name': name, 'mimeType': 'application/json', 'buffer': text.encode('utf-8')}])
        pg.wait_for_timeout(wait)

    def _toasts(self, pg):
        return pg.evaluate("()=>[...document.querySelectorAll('.foreground-toast')].map(e=>e.textContent).join(' || ')")

    def _clear_toasts(self, pg):
        pg.evaluate("()=>document.querySelectorAll('.foreground-toast').forEach(e=>e.remove())")

    def _serve_xlsx(self, route):
        path = os.path.join(CDN_MIRROR, 'xlsx.full.min.js') if CDN_MIRROR else ''
        if path and os.path.exists(path):
            route.fulfill(status=200, body=open(path, 'rb').read(),
                          headers={'Access-Control-Allow-Origin': '*', 'Content-Type': 'application/javascript; charset=utf-8'})
        else:
            route.continue_()

    def body(self, page):
        c = self.checks
        browser = page.context.browser
        W = "const wait=ms=>new Promise(s=>setTimeout(s,ms));"

        # ================= 完整備份：匯出 =================
        ctx, pg = self._ctx(browser)
        self._open(pg)
        pg.evaluate("()=>__seedSeven()")
        pg.wait_for_timeout(200)
        today = pg.evaluate("todayISO()")
        pg.click('#btn-account-menu')
        pg.wait_for_timeout(150)
        pg.click('#menu-group-export summary')
        pg.wait_for_timeout(150)
        with pg.expect_download() as dl:
            pg.click('#btn-export')
        d = dl.value
        raw = open(d.path(), 'rb').read()
        fname = d.suggested_filename
        try:
            data = json.loads(raw.decode('utf-8'))
        except Exception:                              # noqa: BLE001
            data = {}
        races = data.get('races') or []
        trs = data.get('trainings') or []
        prof = data.get('userProfile') or {}
        c['export_holds_all_seven_kinds'] = (
            data.get('format') == 'race-log-backup' and data.get('version') == 1
            and len(races) == 3 and any(r.get('deletedAt') for r in races)          # 垃圾桶裡的也帶
            and len(trs) == 3 and any(x.get('deletedAt') for x in trs)              # 刪除墓碑也帶
            and [s.get('id') for s in data.get('shoes') or []] == ['s1']
            and [n.get('id') for n in data.get('nutritionDictionary') or []] == ['n1']
            and any(t.get('id') == 'tpl-own' for t in data.get('templates') or [])
            and prof.get('weightKg') == 60 and prof.get('homeCounty') == '台北市'
            and ((prof.get('hr') or {}).get('running') or {}).get('maxHr') == 190
            and 'first_finish' in (data.get('badgeUnlocks') or {}))
        if not c['export_holds_all_seven_kinds']:
            print('    v45: export keys', {k: (len(v) if isinstance(v, (list, dict)) else v) for k, v in data.items()})
        c['export_file_named_with_date'] = fname == f'賽事紀錄備份-{today}.json'
        c['export_records_last_backup_time'] = self.ev(pg, "()=>{ const v=lastBackupAt(); return !!v && Date.now()-v<60000; }")
        # 其他入口也是完整備份：指令控制台、儲存空間快滿的提示
        c['command_palette_and_storage_banner_export_full_backup'] = self.ev(pg, """()=>{
            const a=CMDK_ACTIONS.find(x=>x.id==='export-json'); let n=0; const real=window.exportFullBackup; window.exportFullBackup=()=>{ n++; };
            try{ a.run(); showStorageWarning(0.9); document.querySelector('.app-banner [data-banner-action="0"]').click(); }
            finally{ window.exportFullBackup=real; hideAppBanner(); }
            return n===2 && t(a.labelKey,a.labelFallback)==='匯出完整備份（JSON）'; }""")
        ctx.close()

        # ================= 完整備份：在一台新裝置還原 =================
        ctx, pg = self._ctx(browser)
        self._open(pg)
        c['restore_on_new_device_brings_back_all_seven'] = False
        before = self.ev(pg, "()=>({tpl:templates.map(x=>x.name).sort().join('|')})")
        self._import(pg, raw.decode('utf-8'), fname)
        got = self.ev(pg, """()=>({races:state.races.length, live:state.races.filter(r=>!r.deletedAt).map(r=>r.name).sort().join('|'),
            tr:trainings.length, liveTr:liveTrainings().map(x=>x.name).sort().join('|'), shoes:shoes.map(s=>s.name).join('|'),
            nut:nutritionDictionary.map(n=>n.name).join('|'), tpl:templates.map(x=>x.name).sort().join('|'),
            w:userProfile.weightKg, county:userProfile.homeCounty, maxHr:userProfile.hr.running.maxHr, badge:!!badgeUnlocks.first_finish})""") or {}
        builtin = (before or {}).get('tpl', '')
        c['restore_on_new_device_brings_back_all_seven'] = (
            got.get('races') == 3 and got.get('live') == '備份測試・全馬|備份測試・越野'
            and got.get('tr') == 3 and got.get('liveTr') == '輕鬆跑|騎車'
            and got.get('shoes') == 'Vaporfly 3' and got.get('nut') == 'Maurten Gel 100'
            and got.get('w') == 60 and got.get('county') == '台北市' and got.get('maxHr') == 190 and got.get('badge') is True)
        if not c['restore_on_new_device_brings_back_all_seven']:
            print('    v45: restore', got)
        # 新裝置一打開就有一套內建範本（id 是新的）：還原時另一台那套一樣的不再多一份，自訂的照樣補進來
        c['restore_keeps_one_set_of_builtin_templates'] = got.get('tpl') == '|'.join(sorted(builtin.split('|') + ['我的越野包']))
        c['restore_is_saved'] = self.ev(pg, """async()=>{
            const r=await loadJson('races-v1',[]), t=await loadJson('trainings-v1',[]), s=await loadJson('shoes-v1',[]),
              n=await loadJson('nutrition-dictionary-v1',[]), tp=await loadJson('equipment-templates-v1',[]), p=await loadJson('user-profile-v1',null), b=await loadJson('badges-v1',{});
            return r.length===3 && t.length===3 && s.length===1 && n.length===1 && tp.some(x=>x.id==='tpl-own') && p&&p.weightKg===60 && !!b.first_finish; }""")
        toast = self._toasts(pg)
        c['restore_says_what_was_added'] = all(w in toast for w in ('備份匯入完成', '賽事 2 場', '訓練 2 筆', '鞋款 1 雙', '補給品 1 項', '裝備範本 1 個'))
        if not c['restore_says_what_was_added']:
            print('    v45: toast', toast[:200])
        self._clear_toasts(pg)
        self._import(pg, raw.decode('utf-8'), fname)
        toast2 = self._toasts(pg)
        c['restoring_twice_adds_nothing'] = ('沒有新增' in toast2) and self.ev(pg, "()=>state.races.length===3&&trainings.length===3&&shoes.length===1&&templates.filter(x=>x.id==='tpl-own').length===1")
        # 拖進來的檔案走同一條路
        self._clear_toasts(pg)
        c['dropped_backup_file_goes_to_restore'] = self.ev(pg, """async(txt)=>{ const keep=state.races.length;
            state.races=state.races.filter(r=>r.name!=='備份測試・越野'); renderAll();
            await routeDroppedFiles([new File([txt],'備份.json',{type:'application/json'})]); await new Promise(s=>setTimeout(s,300));
            return state.races.length===keep && state.races.some(r=>r.name==='備份測試・越野'); }""", raw.decode('utf-8'))
        ctx.close()

        # ================= 還原是合併，不會蓋掉這台比較新的 =================
        ctx, pg = self._ctx(browser)
        self._open(pg)
        conflict = self.ev(pg, """async()=>{
            const mk=(id,name,at)=>Object.assign(emptyRace(name,'road_running','registered','2027-01-01'),{id,updatedAt:at});
            state.races=[mk('shared-1','這台比較新','2026-09-01T00:00:00Z'), mk('shared-2','這台比較舊','2020-01-01T00:00:00Z')]; await persist();
            userProfile=migrateUserProfile({weightKg:70}); await persistUserProfile(); syncOverwrites=[];
            return JSON.stringify({format:'race-log-backup',version:1,races:[mk('shared-1','備份比較舊','2025-01-01T00:00:00Z'),mk('shared-2','備份比較新','2026-01-01T00:00:00Z')],
              userProfile:{weightKg:60,homeCounty:'台北市'}}); }""")
        if conflict:
            self._import(pg, conflict)
        c['restore_never_overwrites_newer_local'] = self.ev(pg, """()=>{
            const n=id=>state.races.find(r=>r.id===id).name, rec=syncOverwrites.map(x=>x.raceName).sort().join('|');
            const ok=n('shared-1')==='這台比較新' && n('shared-2')==='備份比較新' && rec==='備份比較舊|這台比較舊'
              && userProfile.weightKg===70 && userProfile.homeCounty==='台北市';
            if(!ok) console.log('v45: merge',n('shared-1'),n('shared-2'),rec,userProfile.weightKg,userProfile.homeCounty);
            return ok; }""")
        c['restore_toast_points_to_recovery_for_conflicts'] = '資料復原' in self._toasts(pg)
        self._clear_toasts(pg)
        # 壞掉／空的備份：講清楚、什麼都不動
        self._import(pg, json.dumps({'format': 'race-log-backup', 'version': 1}))
        c['empty_backup_says_so_and_changes_nothing'] = ('沒有資料' in self._toasts(pg)) and self.ev(pg, "()=>state.races.length===2")
        self._clear_toasts(pg)
        # 舊版（v4.4 以前）匯出的賽事陣列照樣能匯入
        old = self.ev(pg, "()=>JSON.stringify([emptyRace('舊格式匯出的賽事','road_running','completed','2024-11-03')])")
        if old:
            self._import(pg, old, 'races-export.json')
        c['old_race_array_export_still_imports'] = self.ev(pg, "()=>state.races.some(r=>r.name==='舊格式匯出的賽事') && state.races.length===3")
        # 訓練頁「匯出訓練紀錄」的檔案：進訓練、不會變成一堆空白賽事
        tr_export = json.dumps([
            {'id': 'tx1', 'date': '2025-05-01', 'startTime': None, 'sport': 'run', 'name': '匯出的訓練', 'distanceKm': 8, 'durationSeconds': 2700, 'elevationGainM': None,
             'avgHr': None, 'shoeId': None, 'thumb': None, 'fingerprint': 'fpx1', 'source': 'fit', 'importedAt': '2025-05-01T00:00:00Z', 'updatedAt': '2025-05-01T00:00:00Z', 'deletedAt': None}])
        self._clear_toasts(pg)
        self._import(pg, tr_export, '訓練紀錄-2025-05-02.json')
        c['training_export_file_imports_as_trainings'] = self.ev(pg, "()=>state.races.length===3 && liveTrainings().some(x=>x.name==='匯出的訓練')") and ('訓練紀錄匯入完成' in self._toasts(pg))
        # 開著一場賽事時貼上整份備份：還原，不是把七種資料塞進這一場
        self._clear_toasts(pg)
        c['pasting_backup_with_race_open_restores_instead_of_quickfill'] = self.ev(pg, """async(txt)=>{
            const r=state.races.find(x=>x.id==='shared-1'); selectRace(r.id); await new Promise(s=>setTimeout(s,200));
            const before=JSON.stringify(Object.keys(state.races.find(x=>x.id==='shared-1')).sort());
            const backup=JSON.parse(txt); backup.races.push(emptyRace('貼上的備份','road_running','registered','2027-02-02'));
            const dt=new DataTransfer(); dt.setData('text', JSON.stringify(backup));
            document.dispatchEvent(new ClipboardEvent('paste',{clipboardData:dt,bubbles:true,cancelable:true})); await new Promise(s=>setTimeout(s,400));
            const cur=state.races.find(x=>x.id==='shared-1');
            const ok=state.races.some(x=>x.name==='貼上的備份') && cur.name==='這台比較新' && !('format' in cur) && !('races' in cur)
              && JSON.stringify(Object.keys(cur).sort())===before;
            goBackFromDetail(); return ok; }""", conflict or '{}')
        ctx.close()

        # ================= 沒登入：頭像選單的提醒卡、頭像的紅點 =================
        ctx, pg = self._ctx(browser, viewport={'width': 390, 'height': 844}, touch=True)
        self._open(pg)
        pg.add_style_tag(content='.foreground-toast,.app-banner{display:none!important} *{transition:none!important}')
        # Firebase 還沒回報登入狀態之前（已登入的人也是這樣開始的）：不能先閃提醒卡和紅點
        c['nothing_flashes_before_login_state_is_known'] = self.ev(pg, """async()=>{ __addLive(3); __signedOutCloud(false); await new Promise(s=>setTimeout(s,150));
            return !__card() && !__dot() && !!document.querySelector('#auth-area #btn-signin'); }""")
        c['signed_out_with_races_shows_card'] = self.ev(pg, """async()=>{ window.__authCb(null); await new Promise(s=>setTimeout(s,200));
            const card=__card(); if(!card) return false;
            return card.querySelector('.backup-nudge-title').textContent==='資料只存在這台裝置' && !!card.querySelector('#btn-signin')
              && !!card.querySelector('[data-action="backup-export"]') && card.querySelector('.backup-nudge-last').textContent==='還沒備份過'
              && !card.querySelector('.backup-nudge-ios'); }""")
        c['dot_and_accessible_name_when_3_races_never_backed_up'] = self.ev(pg, """()=>{ const b=document.getElementById('btn-account-menu');
            return __dot() && b.getAttribute('aria-label')==='帳號與設定（資料還沒備份）' && getComputedStyle(b,'::before').content!=='none'; }""")
        c['dot_follows_race_count_and_backup_age'] = self.ev(pg, """async()=>{ const wait=ms=>new Promise(s=>setTimeout(s,ms));
            const live=()=>state.races.filter(r=>!r.deletedAt);
            const keep=state.races.slice(); state.races=live().slice(0,2); renderAll(); await wait(50);
            const two=__dot(); state.races=keep; renderAll(); await wait(50); const three=__dot();
            localStorage.setItem('last-backup-v1',JSON.stringify(Date.now()-3*86400000)); renderAuthArea();
            const recent=!__dot() && __card().querySelector('.backup-nudge-last').textContent==='上次備份：3 天前'
              && document.getElementById('btn-account-menu').getAttribute('aria-label')==='帳號與設定';
            localStorage.setItem('last-backup-v1',JSON.stringify(Date.now()-31*86400000)); renderAuthArea(); const stale=__dot();
            localStorage.removeItem('last-backup-v1'); renderAuthArea();
            if(!( !two && three && recent && stale )) console.log('v45: dot',two,three,recent,stale);
            return !two && three && recent && stale; }""")
        c['empty_device_gets_plain_signin_button'] = self.ev(pg, """async()=>{ const keep=state.races; state.races=keep.map(r=>Object.assign({},r,{deletedAt:new Date().toISOString()})); renderAll();
            await new Promise(s=>setTimeout(s,50)); const ok=!__card() && !__dot() && !!document.querySelector('#auth-area > #btn-signin');
            state.races=keep; renderAll(); return ok && !!__card(); }""")
        # 從提醒卡匯出：真的下載、選單留著、看得到「上次備份：今天」、紅點消失
        pg.click('#btn-account-menu')
        pg.wait_for_timeout(200)
        try:
            with pg.expect_download(timeout=4000) as dl2:
                pg.click('#auth-area [data-action="backup-export"]')
            got_dl = dl2.value.suggested_filename.endswith('.json')
        except Exception:                              # noqa: BLE001
            got_dl = False
        pg.wait_for_timeout(200)
        c['card_export_downloads_keeps_menu_and_clears_dot'] = got_dl and self.ev(pg, """()=>!document.getElementById('account-menu-panel').hidden
            && __card().querySelector('.backup-nudge-last').textContent==='上次備份：今天' && !__dot()""")
        pg.keyboard.press('Escape')
        # 選單比畫面高、在裡面捲動時，分隔線不能被擠到看不見
        c['menu_dividers_survive_scrolling_menu'] = self.ev(pg, """async()=>{ const wait=ms=>new Promise(s=>setTimeout(s,ms));
            localStorage.removeItem('last-backup-v1'); renderAuthArea();
            // 匯入、匯出兩組都展開：選單一定比手機畫面高，要在裡面捲動
            const groups=['menu-group-import','menu-group-export'].map(id=>document.getElementById(id)); groups.forEach(g=>g.open=true);
            document.getElementById('btn-account-menu').click(); await wait(200);
            const p=document.getElementById('account-menu-panel'); const scrolls=p.scrollHeight>p.clientHeight+20;
            const hs=[...p.querySelectorAll('.action-menu-divider')].map(d=>d.getBoundingClientRect().height);
            document.getElementById('btn-account-menu').click(); await wait(100); groups.forEach(g=>g.open=false);
            if(!(scrolls&&hs.every(h=>h>=1))) console.log('v45: dividers',scrolls,hs.join(','));
            return scrolls && hs.length>=4 && hs.every(h=>h>=1); }""")
        # 卡片上的字在淺色、深色都看得清楚（4.5:1）
        contrast = """()=>{ const card=__card(); const els=[...card.querySelectorAll('.backup-nudge-title,.backup-nudge-body,.backup-nudge-last,button')];
            const low=els.map(el=>{ const cs=getComputedStyle(el); const own=__rgba(cs.backgroundColor); const bg=own[3]>0?__over(own,__behind(el)):__behind(el);
              return [el.className||el.id, __cr(__over(__rgba(cs.color),bg),bg)]; }).filter(x=>x[1]<4.5);
            if(low.length) console.log('v45: contrast',JSON.stringify(low)); return els.length>=5 && low.length===0; }"""
        light_ok = self.ev(pg, contrast)
        pg.evaluate("()=>applyTheme('dark')")
        pg.wait_for_timeout(100)
        dark_ok = self.ev(pg, contrast)
        pg.evaluate("()=>applyTheme('light')")
        c['card_text_readable_light_and_dark'] = bool(light_ok and dark_ok)
        # 登入之後：提醒卡、紅點都不見；登出又回來
        c['signing_in_hides_card_and_dot'] = self.ev(pg, """async()=>{ const wait=ms=>new Promise(s=>setTimeout(s,ms));
            await handleAuthChange({uid:'u45',displayName:'測試者',email:'',photoURL:''}); await wait(200);
            const inOk=!__card() && !__dot() && !!document.querySelector('#auth-area .auth-user');
            await handleAuthChange(null); await wait(200);
            return inOk && !!__card(); }""")
        c['card_and_dot_translated'] = self.ev(pg, """async()=>{ const wait=ms=>new Promise(s=>setTimeout(s,ms)); const out={};
            for(const lang of ['ja','en']){ setLang(lang); await wait(150);
              out[lang]=[__card().querySelector('.backup-nudge-title').textContent, document.querySelector('#auth-area #btn-signin').textContent,
                document.querySelector('#auth-area [data-action="backup-export"]').textContent, document.getElementById('btn-account-menu').getAttribute('aria-label')].join('|'); }
            setLang('zh'); await wait(150);
            const ok=out.ja==='データはこの端末にしかありません|Google でログインしてバックアップ|バックアップを書き出す|アカウントと設定（データ未バックアップ）'
              && out.en==='Your data is only on this device|Sign in with Google to back up|Export backup file|Account & settings (data not backed up)';
            if(!ok) console.log('v45: lang',JSON.stringify(out)); return ok; }""")
        ctx.close()

        # iPhone 的 Safari（還沒加到主畫面）：提醒卡多講 7 天會被清；加到主畫面的提示也講資料
        ctx, pg = self._ctx(browser, viewport={'width': 390, 'height': 844}, touch=True, ua=IPHONE_UA)
        self._open(pg)
        c['iphone_card_mentions_7_day_clearing'] = self.ev(pg, """async()=>{ __addLive(1); __signedOutCloud(true); await new Promise(s=>setTimeout(s,200));
            const ios=__card()&&__card().querySelector('.backup-nudge-ios'); return !!ios && ios.textContent.includes('7 天') && ios.textContent.includes('加入主畫面'); }""")
        c['iphone_install_hint_mentions_data'] = self.ev(pg, """()=>{ localStorage.setItem('open-count-v1','3'); localStorage.removeItem('install-hint-v1'); hideAppBanner();
            maybeShowInstallHint(); const b=document.querySelector('.app-banner .app-banner-text'); const tx=b?b.textContent:''; hideAppBanner();
            return tx.includes('7 天') && tx.includes('Safari') && tx.includes('加入主畫面'); }""")
        ctx.close()

        # ================= 持久保存 =================
        ctx, pg = self._ctx(browser)
        self._open(pg)
        c['persist_not_requested_without_data'] = self.ev(pg, "()=>window.__persist.calls===0 && localStorage.getItem('persist-asked-v1')===null")
        c['persist_requested_once_when_first_race_saved'] = self.ev(pg, """async()=>{ const wait=ms=>new Promise(s=>setTimeout(s,ms));
            state.races.push(emptyRace('第一場','road_running','registered','2027-01-01')); await persist(); await wait(50);
            const one=window.__persist.calls; await persist(); await persist(); await wait(50);
            return one===1 && window.__persist.calls===1 && typeof JSON.parse(localStorage.getItem('persist-asked-v1'))==='number'; }""")
        race_json = self.ev(pg, "()=>JSON.stringify([emptyRace('已經有的賽事','road_running','registered','2027-01-01')])") or '[]'
        ctx.close()
        seed_races = "try{ localStorage.setItem('races-v1', %s); }catch(e){}" % json.dumps(race_json)
        res = []
        for label, extra in (('asked_yesterday', "localStorage.setItem('persist-asked-v1', String(Date.now()-86400000));"),
                             ('asked_8_days_ago', "localStorage.setItem('persist-asked-v1', String(Date.now()-8*86400000));"),
                             ('already_persisted', "window.__persist.persisted=true;")):
            ctx, pg = self._ctx(browser, init=(seed_races, 'try{' + extra + '}catch(e){}'))
            pg.goto(APP_URL)
            pg.wait_for_timeout(900)
            res.append(self.ev(pg, "()=>[state.races.length, window.__persist.calls]"))
            ctx.close()
        # 有資料時一打開就問；問過、沒拿到的 7 天內不再問；已經是持久的不用問
        c['persist_asked_at_startup_with_data_but_not_nagging'] = res == [[1, 0], [1, 1], [1, 0]]
        if not c['persist_asked_at_startup_with_data_but_not_nagging']:
            print('    v45: persist', res)
        # 加到主畫面的（standalone）：每次打開都問（那時候瀏覽器幾乎一定會給），一次瀏覽還是只問一次
        ctx, pg = self._ctx(browser, init=(seed_races, "try{ localStorage.setItem('persist-asked-v1', String(Date.now()-86400000));"
                                           " Object.defineProperty(navigator,'standalone',{configurable:true,get:()=>true}); }catch(e){}"))
        pg.goto(APP_URL)
        pg.wait_for_timeout(900)
        c['installed_app_asks_each_launch_once_per_session'] = self.ev(pg, """async()=>{ const atStart=window.__persist.calls;
            state.races.push(emptyRace('再一場','road_running','registered','2027-02-01')); await persist(); await persist(); await new Promise(s=>setTimeout(s,50));
            return atStart===1 && window.__persist.calls===1; }""")
        ctx.close()

        # ================= Excel 解析套件延後載入 =================
        ctx, pg = self._ctx(browser)
        reqs = []
        pg.on('request', lambda r: reqs.append(r.url))
        pending = []
        # 按下「匯入 Excel」之後的請求先扣著（模擬網路慢），之前的照常回應——萬一開頁就載入，
        # 頁面也開得起來、由下一項乾淨地失敗，不會整組卡在等頁面載入完
        hold = {'on': False}

        def held(route):
            if hold['on']:
                pending.append(route)
            else:
                self._serve_xlsx(route)
        pg.route(XLSX_CDN_URL, held)
        pg.goto(APP_URL)
        pg.wait_for_timeout(900)
        c['xlsx_not_loaded_at_startup'] = (not any('xlsx' in u for u in reqs)) and self.ev(pg, "()=>typeof XLSX==='undefined' && !document.querySelector('script[src*=\"xlsx\"]')")
        hold['on'] = True
        c['excel_button_starts_loading_with_sri'] = self.ev(pg, """async()=>{ const inp=document.getElementById('import-file-input'); const real=inp.click; let picked=false; inp.click=()=>{ picked=true; };
            document.getElementById('btn-import').click(); inp.click=real; await new Promise(s=>setTimeout(s,100));
            const s=[...document.querySelectorAll('script')].find(x=>x.src===XLSX_SRC);
            return picked && !!s && s.integrity===XLSX_SRI && s.getAttribute('crossorigin')==='anonymous' && /^sha384-/.test(s.integrity) && /@\\d+\\.\\d+\\.\\d+\\//.test(s.src); }""")
        pg.wait_for_timeout(200)
        c['xlsx_requested_only_after_click'] = any(u == XLSX_CDN_URL for u in reqs) and len(pending) == 1
        # 套件還在路上就選好了檔案：先出現「正在載入」，等到了再到選工作表
        xbytes = tiny_xlsx('2026', [['日期', '賽事名稱', '距離'], ['2026-11-01', '測試馬拉松', '42.195']])
        pg.set_input_files('#import-file-input', files=[{'name': '賽事.xlsx', 'mimeType': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'buffer': xbytes}])
        pg.wait_for_timeout(250)
        c['loading_message_while_parser_downloads'] = self.ev(pg, """()=>{ const m=document.getElementById('import-modal');
            return !m.hidden && m.textContent.includes('正在載入 Excel 解析工具') && !!m.querySelector('[data-action="close-import"]'); }""")
        if pending:
            self._serve_xlsx(pending[0])
        pg.wait_for_timeout(1500)
        c['excel_import_continues_once_parser_arrives'] = self.ev(pg, """()=>{ const m=document.getElementById('import-modal');
            const ok=typeof XLSX!=='undefined' && !m.hidden && m.querySelector('h2').textContent.includes('選擇工作表') && m.textContent.includes('2026');
            if(!ok) console.log('v45: excel',typeof XLSX, m.hidden, m.textContent.slice(0,80)); closeImportModal(); return ok; }""")
        ctx.close()
        # 載入失敗（離線、被擋）：選了檔案講清楚；網路好了再按一次就能用，不必重新整理
        ctx, pg = self._ctx(browser)
        mode = {'fail': True}

        def flaky(route):
            if mode['fail']:
                route.abort()
            else:
                self._serve_xlsx(route)
        pg.route(XLSX_CDN_URL, flaky)
        pg.goto(APP_URL)
        pg.wait_for_timeout(900)
        pg.evaluate("()=>{ const inp=document.getElementById('import-file-input'); inp.click=()=>{}; document.getElementById('btn-import').click(); }")
        pg.wait_for_timeout(300)
        pg.set_input_files('#import-file-input', files=[{'name': '賽事.xlsx', 'mimeType': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'buffer': xbytes}])
        pg.wait_for_timeout(500)
        c['parser_failure_explains_and_suggests_retry'] = self.ev(pg, """()=>{ const m=document.getElementById('import-modal');
            const ok=!m.hidden && m.textContent.includes('Excel 解析工具載入失敗') && m.textContent.includes('再按一次') && !document.querySelector('script[src*="xlsx"]');
            closeImportModal(); return ok; }""")
        mode['fail'] = False
        pg.evaluate("()=>document.getElementById('btn-import').click()")
        pg.wait_for_timeout(1500)
        pg.set_input_files('#import-file-input', files=[{'name': '賽事.xlsx', 'mimeType': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'buffer': xbytes}])
        pg.wait_for_timeout(600)
        c['retry_after_failure_works_without_reload'] = self.ev(pg, """()=>{ const m=document.getElementById('import-modal');
            const ok=typeof XLSX!=='undefined' && !m.hidden && m.querySelector('h2').textContent.includes('選擇工作表'); closeImportModal(); return ok; }""")
        ctx.close()
        # 等套件的時候按了「取消」：套件到了也不要自己再跳出來
        ctx, pg = self._ctx(browser)
        pending = []
        hold = {'on': False}

        def held2(route):
            if hold['on']:
                pending.append(route)
            else:
                self._serve_xlsx(route)
        pg.route(XLSX_CDN_URL, held2)
        pg.goto(APP_URL)
        pg.wait_for_timeout(900)
        hold['on'] = True
        pg.evaluate("()=>{ const inp=document.getElementById('import-file-input'); inp.click=()=>{}; document.getElementById('btn-import').click(); }")
        pg.wait_for_timeout(200)
        pg.set_input_files('#import-file-input', files=[{'name': '賽事.xlsx', 'mimeType': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'buffer': xbytes}])
        pg.wait_for_timeout(250)
        self.ev(pg, "()=>document.querySelector('#import-modal [data-action=\"close-import\"]').click()")
        if pending:
            self._serve_xlsx(pending[0])
        pg.wait_for_timeout(1200)
        c['cancel_while_loading_stays_closed'] = self.ev(pg, "()=>typeof XLSX!=='undefined' && document.getElementById('import-modal').hidden")
        ctx.close()

        # ================= 行事曆匯出、生涯數據門檻 =================
        ctx, pg = self._ctx(browser)
        self._open(pg)
        pg.evaluate("""()=>{ const a=emptyRace('還在的報名','road_running','registered',addDaysStr(todayISO(),30));
            const b=emptyRace('丟進垃圾桶的報名','road_running','registered',addDaysStr(todayISO(),40)); b.deletedAt=new Date().toISOString();
            state.races.push(a,b); renderAll(); }""")
        try:
            with pg.expect_download(timeout=4000) as dl3:
                pg.evaluate("()=>document.getElementById('btn-export-ics').click()")
            ics = open(dl3.value.path(), 'rb').read().decode('utf-8')
        except Exception:                              # noqa: BLE001
            ics = ''
        c['calendar_export_skips_trashed_races'] = ('還在的報名' in ics) and ('丟進垃圾桶的報名' not in ics)
        downloads = []
        pg.on('download', lambda d: downloads.append(d))
        self._clear_toasts(pg)
        pg.evaluate("()=>{ state.races=state.races.filter(r=>r.deletedAt||r.status==='completed'); renderAll(); document.getElementById('btn-export-ics').click(); }")
        pg.wait_for_timeout(600)
        c['calendar_export_with_nothing_upcoming_says_so'] = (not downloads) and ('沒有已排定日期' in self._toasts(pg))
        c['career_threshold_ignores_trash'] = self.ev(pg, """async()=>{ const wait=ms=>new Promise(s=>setTimeout(s,ms));
            state.races=[]; for(let i=0;i<4;i++) state.races.push(emptyRace('生涯 '+i,'road_running','completed','2025-0'+(i+1)+'-01'));
            for(let i=0;i<3;i++){ const r=emptyRace('垃圾桶 '+i,'road_running','completed','2024-0'+(i+1)+'-01'); r.deletedAt=new Date().toISOString(); state.races.push(r); }
            renderAll(); setHomeTab('career'); await wait(200);
            const four=!document.querySelector('#calendar .career-summary-wrap') && (document.querySelector('#calendar .career-empty')||{textContent:''}).textContent.includes('目前 4 場');
            state.races.push(emptyRace('第五場','road_running','completed','2025-06-01')); renderAll(); await wait(200);
            const five=!!document.querySelector('#calendar .career-summary-wrap');
            setHomeTab('races'); return four && five; }""")
        # ================= 說明、選單文字、版本 =================
        c['menu_says_full_backup_in_three_languages'] = self.ev(pg, """async()=>{ const wait=ms=>new Promise(s=>setTimeout(s,ms)); const out={};
            for(const lang of ['zh','ja','en']){ setLang(lang); await wait(100);
              out[lang]=document.getElementById('btn-export').textContent+'|'+document.getElementById('btn-import-json').textContent; }
            setLang('zh'); await wait(100);
            return out.zh==='匯出完整備份（JSON）|匯入備份（JSON）' && out.ja==='完全バックアップを書き出す（JSON）|バックアップを読み込む（JSON）'
              && out.en==='Export full backup (JSON)|Import backup (JSON)'; }""")
        c['help_explains_backup_and_signed_out_risk'] = self.ev(pg, """async()=>{ const wait=ms=>new Promise(s=>setTimeout(s,ms)); const out={};
            const words={zh:['匯出完整備份','七種','資料只存在這台裝置','7 天','匯入備份','持久保存'],
              ja:['完全バックアップを書き出す','7種類','データはこの端末にしかありません','7 日','バックアップを読み込む','永続'],
              en:['Export full backup','seven','Your data is only on this device','7 days','Import backup','persistent']};
            for(const lang of ['zh','ja','en']){ setLang(lang); await wait(120); openHelpModal(); await wait(200);
              const tx=document.querySelector('#help-modal .help-body').textContent; const miss=words[lang].filter(w=>!tx.includes(w));
              out[lang]=miss; document.querySelector('#help-modal [data-action="close-help"]').click(); await wait(150); }
            setLang('zh'); await wait(100);
            const ok=Object.values(out).every(m=>m.length===0); if(!ok) console.log('v45: help missing',JSON.stringify(out)); return ok; }""")
        # （版本號的檢查跟著最新的群組走，v4.5.1 起在 v451）
        ctx.close()

        # 雲端合併也不再複製內建範本（同一個合併函式）
        ctx, pg = self._ctx(browser)
        self._open(pg)
        c['cloud_merge_skips_identical_builtin_templates'] = self.ev(pg, """()=>{
            const n=templates.length; const copy=templates.map(x=>Object.assign({},x,{id:'other-device-'+x.id}));
            mergeGlobalListsIntoState({templates:copy.concat([{id:'cloud-own',name:'雲端自訂',items:[]}])});
            return templates.length===n+1 && templates.some(x=>x.id==='cloud-own'); }""")
        ctx.close()


# 獎牌牆年份折頁的小工具：每一段的狀態、展開了哪幾年、按一下某一年
FOLD_JS = r"""
window.__secs=()=>[...document.querySelectorAll('#calendar .bib-sec')].map(s=>{ const b=s.querySelector('.bib-ytoggle');
  return {key:b.dataset.wallYear, open:b.getAttribute('aria-expanded')==='true', cards:s.querySelectorAll('.photo-card').length,
    label:s.querySelector('.bib-ynum').textContent, stats:s.querySelector('.bib-ystats').textContent.replace(/\s+/g,' ').trim()}; });
window.__openKeys=()=>__secs().filter(x=>x.open).map(x=>x.key).join(',');
window.__toggle=k=>document.querySelector('#calendar [data-wall-year="'+k+'"]').click();
window.__ty=()=>String(new Date().getFullYear());
"""


class V451WallFold(Group):
    """v4.5.1：獎牌牆每一年可以收起來——年份標題就是開關，預設只展開今年（今年還沒有完賽就展開最新的
    一年）；收起來的年份只畫標題（場數、里程、PB 數）、不畫卡片；兩年以上有「全部展開／全部收合」；
    鍵盤、報讀；打開一場再返回、重畫、換語言，展開的年份都不變。"""

    ECHO = ('fold:',)

    def _echo(self, msg):
        if msg.text.startswith(self.ECHO):
            print('   ', msg.text[:300])

    def ev(self, pg, js, arg=None):
        try:
            return pg.evaluate(js) if arg is None else pg.evaluate(js, arg)
        except Exception as exc:                      # noqa: BLE001
            print('    ⚠', str(exc).split('\n')[0][:200])
            return False

    def _ctx(self, browser, viewport=None, touch=False, theme='light', lang=None, keep=None, extra=None, seed='wall'):
        ctx = full_mode_context(browser, viewport=viewport or {'width': 1280, 'height': 900}, is_mobile=touch, has_touch=touch)
        init = f"localStorage.setItem('theme-pref-v1','{theme}');"
        if lang:
            init += f"localStorage.setItem('lang-pref-v1','{lang}');"
        ctx.add_init_script('try{' + init + '}catch(e){}')
        pg = ctx.new_page()
        pg.on('pageerror', lambda e: self.errors.append(str(e)))
        pg.on('console', self._echo)
        pg.goto(APP_URL)
        pg.wait_for_timeout(900)
        pg.add_script_tag(content=FIELD_FRAME_JS)
        pg.add_script_tag(content=WALL_SEED_JS)
        pg.add_script_tag(content=FOLD_JS)
        pg.add_style_tag(content='.badge-unbox-overlay,.foreground-toast{display:none!important} *{transition:none!important}')
        if seed == 'wall':
            self.ev(pg, "(o)=>__seedBibWall({keep:o.keep?new Function('r','return ('+o.keep+')'):null, extra:o.extra||[]})", {'keep': keep, 'extra': extra or []})
        else:
            pg.add_script_tag(content=UX_SEED_JS)
            self.ev(pg, V4_EXTRA_JS)
            self.ev(pg, "()=>{ state.viewMode='grid'; setPhoneView('grid'); renderAll(); }")
        pg.wait_for_timeout(300)
        return ctx, pg

    def body(self, page):
        c = self.checks
        browser = page.context.browser
        W = "const wait=ms=>new Promise(s=>setTimeout(s,ms));"
        ctx, pg = self._ctx(browser)
        # ================= 預設：只展開今年 =================
        c['default_opens_only_this_year'] = self.ev(pg, """()=>{ const keys=__secs().map(x=>x.key); const ty=__ty();
            const want=keys.includes(ty)?ty:keys[0]; const ok=__openKeys()===want && keys.length===7;
            if(!ok) console.log('fold: default',__openKeys(),keys.join(',')); return ok; }""")
        c['collapsed_years_show_stats_but_no_cards'] = self.ev(pg, """()=>{ const secs=__secs();
            const want=['5 場 · 520 km · 2 PB','2 場 · 268 km · 1 PB','4 場 · 222 km · 1 PB','3 場 · 73 km · 1 PB','2 場 · 55 km · 1 PB','3 場 · 105 km · 1 PB','2 場 · 10 km'];
            const gridsOk=[...document.querySelectorAll('#calendar .bib-sec')].every(s=>{ const open=s.querySelector('.bib-ytoggle').getAttribute('aria-expanded')==='true';
              const g=s.querySelector('.bib-grid'); return open?(!g.hidden&&g.children.length>0):(g.hidden&&g.children.length===0&&g.getBoundingClientRect().height===0); });
            const ok=JSON.stringify(secs.map(x=>x.stats))===JSON.stringify(want) && secs.every(x=>x.open?x.cards>0:x.cards===0)
              && document.querySelectorAll('#calendar .photo-card').length===secs.filter(x=>x.open).reduce((n,x)=>n+x.cards,0) && gridsOk;
            if(!ok) console.log('fold: collapsed',JSON.stringify(secs)); return ok; }""")
        # 開關是 h3 裡的按鈕：報讀軟體照樣可以用標題跳，按鈕講得出展開了沒有、控制的是哪一片
        c['year_header_is_h3_button_with_state'] = self.ev(pg, """()=>[...document.querySelectorAll('#calendar .bib-sec')].every(s=>{
            const h=s.querySelector('h3'), b=h&&h.querySelector('button.bib-ytoggle'); if(!b) return false;
            const ctl=document.getElementById(b.getAttribute('aria-controls')||'');
            return b.type==='button' && ['true','false'].includes(b.getAttribute('aria-expanded')) && !!ctl && s.contains(ctl)
              && b.textContent.includes(s.querySelector('.bib-ynum').textContent) && b.getBoundingClientRect().height>=44; })""")
        c['clicking_a_year_opens_it_and_again_closes'] = self.ev(pg, """async()=>{ """ + W + """
            const sel='#calendar [data-wall-year="2024"]'; document.querySelector(sel).scrollIntoView({block:'center'}); await wait(100);
            const y0=document.querySelector(sel).getBoundingClientRect().top;
            __toggle('2024'); await wait(150);
            const s=__secs().find(x=>x.key==='2024'), y1=document.querySelector(sel).getBoundingClientRect().top;
            const opened=s.open && s.cards===4 && document.querySelector(sel).getAttribute('aria-expanded')==='true' && Math.abs(y1-y0)<2;
            __toggle('2024'); await wait(150);
            const t=__secs().find(x=>x.key==='2024');
            if(!(opened&&!t.open&&t.cards===0)) console.log('fold: click',JSON.stringify(s),y0,y1);
            return opened && !t.open && t.cards===0; }""")
        # 鍵盤：Enter／空白鍵開關，焦點留在同一顆按鈕上（看得到框）；Tab 進到那一年的第一張卡
        pg.focus('#calendar [data-wall-year="2023"]')
        pg.keyboard.press('Enter')
        pg.wait_for_timeout(150)
        k1 = self.ev(pg, """()=>{ const a=document.activeElement; return a.dataset.wallYear==='2023' && a.matches(':focus-visible') && a.getAttribute('aria-expanded')==='true'
            && __secs().find(x=>x.key==='2023').cards===3; }""")
        pg.keyboard.press('Tab')
        pg.wait_for_timeout(100)
        k2 = self.ev(pg, """()=>{ const a=document.activeElement; return a.classList.contains('photo-card') && a.closest('.bib-sec').querySelector('[data-wall-year]').dataset.wallYear==='2023'; }""")
        pg.keyboard.press('Shift+Tab')
        pg.keyboard.press('Space')
        pg.wait_for_timeout(150)
        k3 = self.ev(pg, "()=>{ const a=document.activeElement; return a.dataset.wallYear==='2023' && a.getAttribute('aria-expanded')==='false' && __secs().find(x=>x.key==='2023').cards===0; }")
        c['keyboard_toggles_and_keeps_focus'] = bool(k1 and k2 and k3)
        if not c['keyboard_toggles_and_keeps_focus']:
            print('    fold: keyboard', k1, k2, k3)
        # 全部展開／全部收合
        c['expand_all_then_collapse_all'] = self.ev(pg, """async()=>{ """ + W + """
            const btn=()=>document.querySelector('#calendar [data-action="wall-toggle-all"]');
            const a0=btn().textContent; btn().click(); await wait(150);
            const allOpen=__secs().every(x=>x.open) && document.querySelectorAll('#calendar .photo-card').length===21 && btn().textContent==='全部收合' && document.activeElement===btn();
            btn().click(); await wait(150);
            const allShut=__secs().every(x=>!x.open) && !document.querySelector('#calendar .photo-card') && btn().textContent==='全部展開';
            if(!(a0==='全部展開'&&allOpen&&allShut)) console.log('fold: all',a0,allOpen,allShut);
            return a0==='全部展開' && allOpen && allShut; }""")
        # 打開一場再返回：展開的年份不變，剛剛點的那張卡回到畫面上
        c['open_years_survive_opening_a_race_and_back'] = self.ev(pg, """async()=>{ """ + W + """
            __toggle('2026'); await wait(100); __toggle('2024'); await wait(150);
            const card=__card('神戶馬拉松'); card.scrollIntoView({block:'center'}); await wait(150); const id=card.dataset.id;
            card.click(); await wait(500); const inRace=state.selectedId===id;
            document.querySelector('#detail .qn-back').click(); await wait(600);
            const back=__card('神戶馬拉松'), r=back&&back.getBoundingClientRect();
            const ok=inRace && state.selectedId===null && __openKeys()==='2026,2024' && !!back && r.top>=0 && r.bottom<=innerHeight;
            if(!ok) console.log('fold: back',inRace,__openKeys(),r&&r.top);
            return ok; }""")
        c['open_years_survive_rerender_and_language'] = self.ev(pg, """async()=>{ """ + W + """
            const before=__openKeys(); renderAll(); await wait(100); const same=__openKeys()===before;
            const out={};
            for(const lang of ['ja','en']){ setLang(lang); await wait(150);
              out[lang]=[__openKeys()===before, document.querySelector('#calendar [data-action="wall-toggle-all"]').textContent, __secs().pop().label]; }
            setLang('zh'); await wait(150);
            const ok=same && out.ja[0] && out.en[0] && out.ja[1]==='すべて開く' && out.en[1]==='Expand all' && out.ja[2]==='日付未定' && out.en[2]==='No date yet' && __openKeys()===before;
            if(!ok) console.log('fold: lang',JSON.stringify(out)); return ok; }""")
        c['undated_group_opens'] = self.ev(pg, """async()=>{ """ + W + """
            __toggle('undated'); await wait(150); const u=__secs().find(x=>x.key==='undated');
            const ok=u.open && u.cards===2 && u.label==='未定日期'; __toggle('undated'); await wait(100); return ok; }""")
        # 收起來的那幾列在淺色、深色都看得清楚：年份（大字）3:1、場數里程 4.5:1、箭頭 3:1、「全部展開」4.5:1
        readable = """()=>{ const bad=[];
            document.querySelectorAll('#calendar .bib-sec.is-collapsed').forEach(s=>{
              const y=s.querySelector('.bib-ynum'), st=s.querySelector('.bib-ystats'), ch=s.querySelector('.bib-ychev');
              if(__textCr(y)<3) bad.push('year '+y.textContent); if(__textCr(st)<4.5) bad.push('stats '+st.textContent);
              const bg=__under(ch)[0]; if(__cr(__over(__rgba(getComputedStyle(ch).borderRightColor),bg),bg)<3) bad.push('chevron'); });
            const b=document.querySelector('#calendar [data-action="wall-toggle-all"]'); if(__textCr(b)<4.5) bad.push('expand-all');
            if(bad.length) console.log('fold: contrast',bad.join(' | ')); return bad.length===0 && !!document.querySelector('#calendar .bib-sec.is-collapsed'); }"""
        light = self.ev(pg, readable)
        self.ev(pg, "()=>applyTheme('dark')")
        pg.wait_for_timeout(100)
        dark = self.ev(pg, readable)
        self.ev(pg, "()=>applyTheme('light')")
        c['collapsed_rows_readable_light_and_dark'] = bool(light and dark)
        c['help_describes_year_folding'] = self.ev(pg, """async()=>{ """ + W + """ const out={};
            const words={zh:['預設只展開今年','全部展開'],ja:['今年だけ','すべて開く'],en:['only this year','Expand all']};
            for(const lang of ['zh','ja','en']){ setLang(lang); await wait(150); openHelpModal(); await wait(200);
              const tx=document.querySelector('#help-modal .help-body').textContent; out[lang]=words[lang].filter(w=>!tx.includes(w));
              document.querySelector('#help-modal [data-action="close-help"]').click(); await wait(150); }
            setLang('zh'); await wait(100);
            const ok=Object.values(out).every(m=>m.length===0); if(!ok) console.log('fold: help missing',JSON.stringify(out)); return ok; }""")
        # （版本號的檢查跟著最新的群組走，v4.6.0 起在 v46）
        ctx.close()

        # 今年跟更新的年份（日期填錯、或比完還沒改日期）都有：展開的是今年，不是最新的那一年
        ty = page.evaluate("()=>new Date().getFullYear()")
        ctx, pg = self._ctx(browser, extra=[{'n': '今年的賽事', 's': 'road_running', 'd': f'{ty}-01-02', 'km': 10, 't': '0:50:00'},
                                             {'n': '明年的賽事', 's': 'road_running', 'd': f'{ty + 1}-03-01', 'km': 21.0975, 't': '1:45:00'}])
        c['this_year_wins_over_a_newer_year'] = self.ev(pg, """()=>{ const keys=__secs().map(x=>x.key);
            const ok=keys[0]===String(Number(__ty())+1) && __openKeys()===__ty(); if(!ok) console.log('fold: newer',keys.join(','),__openKeys()); return ok; }""")
        ctx.close()
        # 今年還沒有完賽：展開最新的那一年（不會整面牆都收著）
        ctx, pg = self._ctx(browser, keep="!(r.schedule.raceDate||'').startsWith(String(new Date().getFullYear()))")
        c['no_race_this_year_opens_newest'] = self.ev(pg, """()=>{ const keys=__secs().map(x=>x.key);
            const ok=!keys.includes(__ty()) && __openKeys()===keys[0] && keys[0]!=='undated'; if(!ok) console.log('fold: newest',keys.join(','),__openKeys()); return ok; }""")
        ctx.close()
        # 只有一年：不需要「全部展開」；那一年照樣可以收起來
        ctx, pg = self._ctx(browser, keep="(r.schedule.raceDate||'').startsWith('2024')")
        c['single_year_has_no_expand_all'] = self.ev(pg, """async()=>{ """ + W + """
            const one=__secs().length===1 && __openKeys()==='2024' && !document.querySelector('#calendar [data-action="wall-toggle-all"]');
            __toggle('2024'); await wait(150); const shut=__openKeys()==='' && !document.querySelector('#calendar .photo-card');
            __toggle('2024'); await wait(150); return one && shut && __secs()[0].cards===4; }""")
        ctx.close()
        # 107 場的資料：只畫展開那一年的卡，其他年份只有標題
        ctx, pg = self._ctx(browser, seed='ux')
        c['big_wall_renders_only_open_year_cards'] = self.ev(pg, """()=>{ const secs=__secs(), done=state.races.filter(r=>!r.deletedAt&&r.status==='completed').length;
            const shown=document.querySelectorAll('#calendar .photo-card').length, open=secs.filter(x=>x.open);
            const ok=done>90 && secs.length>=8 && open.length===1 && shown===open[0].cards && shown<done/5;
            if(!ok) console.log('fold: big',done,secs.length,shown,__openKeys()); return ok; }""")
        ctx.close()

        # ================= 手機的標題列放得下 =================
        FIT = """async()=>{ const wait=ms=>new Promise(s=>setTimeout(s,ms)); const bad=[];
            for(const lang of ['zh','ja','en']){ setLang(lang); await wait(120);
              for(const fs of ['small','medium','large']){ applyFontScale(fs); await wait(80);
                document.querySelectorAll('#calendar .bib-ytoggle').forEach(b=>{ const r=b.getBoundingClientRect(), ch=b.querySelector('.bib-ychev').getBoundingClientRect();
                  const st=b.querySelector('.bib-ystats'), sr=st.getBoundingClientRect(), tag=lang+' '+fs+' '+b.dataset.wallYear;
                  if(r.left<0||r.right>innerWidth+0.5) bad.push(tag+' toggle out');
                  if(r.height<44) bad.push(tag+' short '+r.height);
                  if(ch.right>r.right+0.5||ch.left<sr.right-0.5&&ch.top<sr.bottom&&ch.bottom>sr.top) bad.push(tag+' chevron overlaps');
                  // 箭頭一直在這一列的最右邊（字多到換行時也是），不會掉到年份底下
                  if(ch.right<r.right-24) bad.push(tag+' chevron not at right end');
                  if(Math.abs((ch.top+ch.bottom)/2-(r.top+r.bottom)/2)>r.height/2) bad.push(tag+' chevron off');
                  if(sr.right>r.right+0.5) bad.push(tag+' stats out'); });
                const a=document.querySelector('#calendar [data-action="wall-toggle-all"]'); if(a){ const ar=a.getBoundingClientRect(); if(ar.right>innerWidth+0.5||ar.height<32) bad.push(lang+' '+fs+' expand-all'); }
                if(document.documentElement.scrollWidth>innerWidth) bad.push(lang+' '+fs+' hscroll'); } }
            setLang('zh'); applyFontScale('medium');
            if(bad.length) console.log('fold: fit',bad.slice(0,8).join(' | ')); return bad.length===0; }"""
        # 2021 年塞 12 場、10 個 PB：英文、字級「大」時「12 races · 1235 km · 10 PB」在 360 寬放不下一行，要換行
        heavy = [{'n': f'百公里 {i + 1}', 's': 'ultra_marathon', 'd': f'2021-{i + 1:02d}-15', 'km': 102.9, 't': '11:00:00', 'pb': 1 if i < 10 else 0} for i in range(12)]
        for w in (360, 390):
            fctx, fp = self._ctx(browser, viewport={'width': w, 'height': 800}, touch=True, extra=heavy)
            c[f'phone_{w}_year_headers_fit'] = self.ev(fp, FIT)
            fctx.close()



# v4.6.0 的種子：在號碼布牆的樣本上加幾場、填爬升／分段，涵蓋均速、爬升的每一條規則
V46_SEED_JS = r"""window.__seedV46=async function(o){ o=o||{};
  await __seedBibWall({expand:true, extra:[
    {n:'太魯閣登山自行車賽',s:'cycling',d:'2026-03-01',km:105,t:'4:28:10',bib:'1186'},
    {n:'游跑兩項',s:'other',d:'2026-02-01',km:6,t:'0:40:00',bib:'77'},
    {n:'平地場地賽',s:'road_running',d:'2026-02-15',km:5,t:'0:20:00',bib:'5'},
    {n:'沒成績的封面',s:'trail_running',d:'2026-01-10',km:21,cover:1},
    {n:'泳渡封面',s:'swimming',d:'2026-02-20',km:2.5,t:'0:58:00',cover:1},
  ]});
  const set=(n,f)=>{ const r=state.races.find(x=>x.name===n); f(r); };
  set('太魯閣登山自行車賽',r=>{ r.route.elevationGainM=3275; });
  set('中文號碼',r=>{ r.route.elevationGainM=180; });          // 二鐵：寫爬升、不寫均速
  set('臺東巴歌浪鐵人三項',r=>{ r.route.elevationGainM=1200; }); // 三鐵：兩個都不寫
  set('日月潭泳渡',r=>{ r.route.elevationGainM=531; });         // 游泳：GPS 假爬升不寫
  set('游跑兩項',r=>{ r.route.elevationGainM=50; r.legs=[{sport:'swimming',distanceKm:1,durationSeconds:1200},{sport:'running',distanceKm:5,durationSeconds:1200}]; });
  set('平地場地賽',r=>{ r.route.elevationGainM=0; });
  set('神戶馬拉松',r=>{ r.route.elevationGainM=1234.4; });
  set('只有距離',r=>{ r.route.elevationGainM=900; });
  set('東京馬拉松',r=>{ r.route.elevationGainM=45; });
  set('沒成績的封面',r=>{ r.route.elevationGainM=1000; });
  set('英文字母號碼',r=>{ r.route.elevationGainM=2450; });
  set('第三十八屆國際城市超級馬拉松暨全民健康路跑嘉年華',r=>{ r.route.elevationGainM=12345; });
  set('合歡山越野挑戰賽',r=>{ r.route.elevationGainM=1450; });
  await persist(); renderCalendar(); await new Promise(s=>setTimeout(s,200));
};
window.__band=n=>{ const c=__card(n); const b=c&&c.querySelector('.bib-timing'); if(!b) return null;
  const q=s=>{ const e=b.querySelector(s); return e?e.textContent.trim():''; };
  return [q('.bib-time'), b.querySelector('.bib-time.is-date')?'date':'', q('.bib-pace'), q('.bib-elev')].join('|'); };
"""


class V46FinisherWall(Group):
    """v4.6.0：獎牌牆改名「完賽牆」；號碼布底部一條黑色計時帶——成績、均速（跑步每公里配速、自行車時速、
    游泳每 100 公尺；三鐵、二鐵不寫）、爬升（游泳、三鐵不寫）；拍立得也有；游泳的距離在整個 App 都寫公尺
    （填也是填公尺，存的照樣是公里）；深色模式、瀏覽器強制深色時號碼布還是白紙。"""

    ECHO = ('v46:',)

    def _echo(self, msg):
        if msg.text.startswith(self.ECHO):
            print('   ', msg.text[:300])

    def ev(self, pg, js, arg=None):
        try:
            return pg.evaluate(js) if arg is None else pg.evaluate(js, arg)
        except Exception as exc:                      # noqa: BLE001
            print('    ⚠', str(exc).split('\n')[0][:200])
            return False

    def _ctx(self, browser, viewport=None, touch=False, theme='light', force_dark=False, dsf=1):
        # 強制深色：瀏覽器只在系統（或瀏覽器）是深色時才幫網頁轉深色——使用者把 App 設成淺色、手機是深色，
        # 才會看到 App 被轉黑。prefers-color-scheme 還是 light 時 Chrome 連 color-scheme:only light 都不理，
        # 那是模擬器才有的組合
        ctx = full_mode_context(browser, viewport=viewport or {'width': 1280, 'height': 900}, is_mobile=touch, has_touch=touch,
                                color_scheme='dark' if force_dark else 'light', device_scale_factor=dsf)
        ctx.add_init_script("try{localStorage.setItem('theme-pref-v1','%s');}catch(e){}" % theme)
        pg = ctx.new_page()
        if force_dark:
            cdp = ctx.new_cdp_session(pg)
            cdp.send('Emulation.setAutoDarkModeOverride', {'enabled': True})
        pg.on('pageerror', lambda e: self.errors.append(str(e)))
        pg.on('console', self._echo)
        pg.goto(APP_URL)
        pg.wait_for_timeout(900)
        pg.add_script_tag(content=FIELD_FRAME_JS)
        pg.add_script_tag(content=WALL_SEED_JS)
        pg.add_script_tag(content=V46_SEED_JS)
        pg.add_style_tag(content='.badge-unbox-overlay,.foreground-toast{display:none!important} *{transition:none!important}')
        self.ev(pg, "()=>__seedV46()")
        pg.wait_for_timeout(200)
        return ctx, pg

    def body(self, page):
        c = self.checks
        browser = page.context.browser
        W = ("const wait=ms=>new Promise(s=>setTimeout(s,ms));"
             "const home=async()=>{ for(let i=0;i<12;i++){ if(!document.getElementById('global-drawer').hidden){ closeDrawer(); await wait(300); continue; } if(state.selectedId||state.creating){ goBackFromDetail(); await wait(350); continue; } break; } };")
        ctx, pg = self._ctx(browser)
        # ================= 改名：完賽牆 =================
        c['renamed_finisher_wall_three_languages'] = self.ev(pg, """async()=>{ """ + W + """ const out={};
            const seg=()=>document.querySelector('.view-seg [data-phone-view="grid"]').textContent.trim();
            const tog=()=>{ const b=document.getElementById('cal-view-toggle'); return b.getAttribute('aria-label')+'|'+b.getAttribute('title'); };
            for(const lang of ['zh','ja','en']){ setLang(lang); await wait(150); out[lang]=seg()+'|'+tog(); }
            setLang('zh'); await wait(150);
            const ok=out.zh==='完賽牆|切換為完賽牆檢視|切換為完賽牆檢視' && out.ja==='完走ウォール|完走ウォール表示に切り替え|完走ウォール表示に切り替え'
              && out.en==='Finisher wall|Switch to finisher wall view|Switch to finisher wall view';
            if(!ok) console.log('v46: rename',JSON.stringify(out)); return ok; }""")
        # 畫面上、說明裡都不再出現舊名字（三種語言）
        c['old_name_gone_from_ui_and_help'] = self.ev(pg, """async()=>{ """ + W + """ const bad=[];
            const old={zh:/獎牌牆/,ja:/メダル棚/,en:/trophy wall/i};
            for(const lang of ['zh','ja','en']){ setLang(lang); await wait(150);
              const attrs=[...document.querySelectorAll('[aria-label],[title],[placeholder]')].map(e=>[e.getAttribute('aria-label'),e.getAttribute('title'),e.getAttribute('placeholder')].join(' ')).join(' ');
              // innerText：畫面上看得到的字（textContent 會把 <script> 裡的程式註解也算進去）
              if(old[lang].test(document.body.innerText+attrs)) bad.push(lang+' ui');
              openHelpModal(); await wait(200); const tx=document.querySelector('#help-modal .help-body').textContent;
              if(old[lang].test(tx)) bad.push(lang+' help');
              if(!tx.includes({zh:'完賽牆',ja:'完走ウォール',en:'Finisher wall'}[lang])) bad.push(lang+' help no new name');
              document.querySelector('#help-modal [data-action="close-help"]').click(); await wait(150); }
            setLang('zh'); await wait(150);
            if(bad.length) console.log('v46: old name',bad.join(',')); return bad.length===0; }""")
        # ================= 計時帶：成績｜均速｜爬升 =================
        # 成績|沒成績寫日期|均速|爬升。跑步類每公里配速、自行車時速、游泳每 100 公尺；多項運動（三鐵、二鐵、
        # 分段兩段以上）不寫均速；游泳、三鐵、分段有游泳的不寫爬升；0 與沒填不寫；千分位
        c['timing_band_pace_and_elevation_rules'] = self.ev(pg, """()=>{ const bad=[];
            const want={
              '臺北馬拉松':'3:38:15||5\\'10"/km|',
              '神戶馬拉松':'3:31:02||5\\'00"/km|+1,234 m',
              '太魯閣登山自行車賽':'4:28:10||23.5 km/h|+3,275 m',
              '日月潭泳渡':'1:18:22||2\\'22"/100m|',
              '臺東巴歌浪鐵人三項':'5:58:12|||',
              '臺南標準鐵人三項':'2:31:45|||',
              '中文號碼':'1:39:59|||+180 m',
              '游跑兩項':'0:40:00|||',
              '平地場地賽':'0:20:00||4\\'00"/km|',
              '只有距離':'2026.01.18|date||+900 m',
              '公司運動會大隊接力':'2019.03.10|date||',
              '第三十八屆國際城市超級馬拉松暨全民健康路跑嘉年華':'35:12:40||8\\'35"/km|+12,345 m' };
            Object.entries(want).forEach(([n,w])=>{ const g=__band(n); if(g!==w) bad.push(n+' → '+g); });
            // 沒成績也沒日期、沒均速沒爬升：不畫帶子
            if(__card('沒日期沒成績').querySelector('.bib-timing')) bad.push('empty band drawn');
            if(bad.length) console.log('v46: band',bad.join(' || ')); return bad.length===0; }""")
        # 拍立得：日期在賽名下面，帶子只寫成績、均速、爬升（沒成績時不再寫一次日期）；游泳的照片上寫公尺
        c['polaroid_band_and_swim_meters'] = self.ev(pg, """()=>{
            const meta=n=>[...__card(n).querySelectorAll('.pola-meta span')].map(s=>s.textContent).join(',');
            const got=[__band('東京馬拉松'),meta('東京馬拉松'),__band('沒成績的封面'),meta('沒成績的封面'),__band('泳渡封面'),__card('泳渡封面').querySelector('.pola-dist').textContent,__band('澎湖超級鐵人三項')];
            const want=['3:24:50||4\\'51"/km|+45 m','2025.03.02','|||+1,000 m','2026.01.10','0:58:00||2\\'19"/100m|','2500M','12:41:09|||'];
            const ok=JSON.stringify(got)===JSON.stringify(want); if(!ok) console.log('v46: pola',JSON.stringify(got)); return ok; }""")
        c['swim_bib_big_meters_and_tag'] = self.ev(pg, """async()=>{ """ + W + """
            const r=state.races.find(x=>x.name==='日月潭泳渡'); const c1=__card('日月潭泳渡');
            const a=[c1.querySelector('.bib-no').textContent, c1.querySelector('.bib-num .bib-tag').textContent];
            r.bibNumber='S88'; renderCalendar(); await wait(80);
            const b=[__card('日月潭泳渡').querySelector('.bib-no').textContent, __card('日月潭泳渡').querySelector('.bib-num .bib-tag').textContent];
            r.bibNumber=''; renderCalendar(); await wait(80);
            const ok=JSON.stringify(a)==='["3300M","游泳"]' && JSON.stringify(b)==='["S88","3300 M"]';
            if(!ok) console.log('v46: swim bib',JSON.stringify([a,b])); return ok; }""")
        c['screen_reader_label_has_pace_and_elevation'] = self.ev(pg, """async()=>{ """ + W + """ const out={};
            for(const lang of ['zh','en']){ setLang(lang); await wait(150);
              out[lang]=[__card('神戶馬拉松').getAttribute('aria-label'), __card('日月潭泳渡').getAttribute('aria-label')]; }
            setLang('zh'); await wait(150);
            const ok=out.zh[0]==='神戶馬拉松, 路跑, 2024-11-10, 42.2 km, 3:31:02, 均速 5\\'00"/km, 爬升 +1,234 m, 號碼布 8821'
              && out.zh[1]==='日月潭泳渡, 游泳, 2022-03-13, 3300 m, 1:18:22, 均速 2\\'22"/100m'
              && out.en[0].includes('avg 5\\'00"/km, elevation gain +1,234 m');
            if(!ok) console.log('v46: label',JSON.stringify(out)); return ok; }""")
        c['band_text_readable'] = self.ev(pg, """()=>{ const bad=[];
            document.querySelectorAll('#calendar .bib-time,#calendar .bib-pace,#calendar .bib-elev').forEach(e=>{ const cr=__textCr(e); if(cr<4.5) bad.push(e.textContent+' '+cr.toFixed(2)); });
            if(bad.length) console.log('v46: band contrast',bad.slice(0,5).join(' | ')); return bad.length===0 && document.querySelectorAll('#calendar .bib-elev').length>5; }""")
        # 年份標題的合計照樣是公里（游泳 3.3 km 加在裡面，不換成公尺）
        c['year_totals_stay_km'] = self.ev(pg, """()=>{ const s=[...document.querySelectorAll('#calendar .bib-sec')].find(x=>x.querySelector('.bib-ynum').textContent==='2022');
            return !!s && s.querySelector('.bib-ystats').textContent.replace(/\\s+/g,' ').trim()==='2 場 · 55 km · 1 PB'; }""")
        # ================= 深色模式：紙跟淺色一樣白 =================
        c['dark_mode_paper_same_as_light'] = self.ev(pg, """async()=>{ """ + W + """
            const read=()=>[getComputedStyle(__card('神戶馬拉松')).backgroundImage, getComputedStyle(__card('東京馬拉松')).backgroundColor];
            const light=read(); applyTheme('dark'); await wait(100); const dark=read(); applyTheme('light'); await wait(100);
            const ok=JSON.stringify(light)===JSON.stringify(dark) && /255, 255, 255/.test(light[0]) && light[1]==='rgb(253, 252, 248)';
            if(!ok) console.log('v46: dark paper',JSON.stringify([light,dark])); return ok; }""")
        c['cards_and_flag_opt_out_of_forced_dark'] = self.ev(pg, """()=>[...document.querySelectorAll('#calendar .photo-card,#calendar .bib-flag')].every(e=>{ const v=getComputedStyle(e).colorScheme; return /only/.test(v)&&/light/.test(v)&&!/dark/.test(v); })""")
        # ================= 游泳寫公尺：整個 App =================
        c['swim_meters_list_meta_table_and_labels'] = self.ev(pg, """async()=>{ """ + W + """
            const sw=state.races.find(x=>x.name==='日月潭泳渡'), road=state.races.find(x=>x.name==='神戶馬拉松');
            const meta=[raceTerrainMetaHtml(sw), raceTerrainMetaHtml(road)].map(h=>{ const d=document.createElement('div'); d.innerHTML=h; return d.textContent; });
            const lab=[raceDistLabel(sw),raceDistLabel(road)];
            const radar=computeRaceRadar(sw).find(d=>d.key==='distance').raw;
            // 表格：游泳寫「3300 m」（表頭是 km），照距離排序還是照公里數排
            state.viewMode='grid'; tableSort.key='distance'; tableSort.dir='asc'; state.viewMode='table'; renderCalendar(); await wait(100);
            const rows=[...document.querySelectorAll('#calendar .table-view-row')].map(tr=>tr.children[3].textContent.trim());
            const iSwim=rows.indexOf('3300 m'), i5=rows.indexOf('5.0');
            tableSort.key='date'; tableSort.dir='desc'; state.viewMode='grid'; renderCalendar(); await wait(100);
            const ok=meta[0]==='3300m · +531m' && meta[1]==='42.2K · +1234m' && lab[0]==='3300 m' && lab[1]==='42.2 km' && radar==='3300 m'
              && iSwim>=0 && i5>iSwim && rows.includes('42.2');
            if(!ok) console.log('v46: meters',JSON.stringify([meta,lab,radar,iSwim,i5,rows.slice(0,6)])); return ok; }""")
        c['swim_meters_race_page_share_and_public'] = self.ev(pg, """async()=>{ """ + W + """
            const sw=state.races.find(x=>x.name==='日月潭泳渡');
            selectRace(sw.id,{scroll:false}); await wait(400);
            const dash=(document.querySelector('#detail .results-dashboard')||{}).textContent||'';
            const route=(document.querySelector('[data-section="route"] .dash-card-sub')||{}).textContent||'';
            const share=shareStatsBadges(sw,SHARE_SHOW_DEFAULT).map(b=>b[1]);
            const ok=dash.includes('3300 公尺') && !dash.includes('3.3 公里') && route.includes('3300 m') && !route.includes('3.3 km')
              && share.includes('3300 公尺') && share.includes('2\\'22"/100m') && !share.some(v=>/公里/.test(v));
            if(!ok) console.log('v46: race page',JSON.stringify([dash.slice(0,120),route,share]));
            return ok; }""")
        # 賽事頁的總距離欄：游泳填公尺、右邊寫 m，存的是公里；換成別的運動別又變回公里
        c['swim_distance_field_in_meters_saves_km'] = self.ev(pg, """async()=>{ """ + W + """
            const sw=state.races.find(x=>x.name==='日月潭泳渡');
            openDrawer('route'); await wait(250);
            let el=document.querySelector('#drawer-content #f-route-distanceKm');
            const a=[el.value, el.closest('.field-input-wrap').querySelector('.field-unit').textContent];
            el.value='1500'; el.dispatchEvent(new Event('change',{bubbles:true})); await wait(300);
            const saved=sw.route.distanceKm; closeDrawer(); await wait(250);
            sw.sportType='road_running'; openDrawer('route'); await wait(250);
            el=document.querySelector('#drawer-content #f-route-distanceKm');
            const b=[el.value, el.closest('.field-input-wrap').querySelector('.field-unit').textContent];
            closeDrawer(); await wait(250); sw.sportType='swimming'; sw.route.distanceKm=3.3; await persist();
            const ok=JSON.stringify(a)==='["3300","m"]' && saved===1.5 && JSON.stringify(b)==='["1.5","km"]';
            if(!ok) console.log('v46: field',JSON.stringify([a,saved,b])); return ok; }""")
        c['swim_gpx_preview_and_denoise_in_meters'] = self.ev(pg, """()=>{
            const sw=state.races.find(x=>x.name==='日月潭泳渡');
            const strip=h=>{ const d=document.createElement('div'); d.innerHTML=h; return d.textContent.replace(/\\s+/g,' '); };
            const g=strip(gpxSummaryHtml({distanceKm:3.52,durationSeconds:4700,elevationGainM:null,avgHr:null,maxHr:null,avgCadence:null,splits:[]},'a.gpx'));
            const keep=[sw.route.trackPoints,sw.route.timedTrackPoints];
            sw.route.trackPoints=[[23.86,120.91],[23.87,120.92]]; sw.route.timedTrackPoints=[{lat:23.86,lon:120.91,t:0},{lat:23.87,lon:120.92,t:60}];
            gpsDenoisePreview={raceId:sw.id,oldDistanceKm:3.52,newDistanceKm:3.31,smoothedTimedPoints:[]};
            const d=strip(gpsDenoiseSectionHtml(sw));
            gpsDenoisePreview=null; sw.route.trackPoints=keep[0]; sw.route.timedTrackPoints=keep[1];
            const ok=g.includes('3520 公尺') && g.includes('會取代現有的 3300 公尺') && d.includes('3520 m') && d.includes('3310 m') && d.includes('套用並更新距離為 3310 m') && !/\\d km/.test(d);
            if(!ok) console.log('v46: gpx',g.slice(0,160),'/',d.slice(0,200)); return ok; }""")
        c['public_view_and_report_prompt_in_meters'] = self.ev(pg, """async()=>{
            const sw=state.races.find(x=>x.name==='日月潭泳渡');
            const prompt=buildRaceReportPrompt(sw);
            const snap=await buildPublicSnapshot(sw);
            return { snap, prompt }; }""")
        pub = c['public_view_and_report_prompt_in_meters']
        c['public_view_and_report_prompt_in_meters'] = False
        # ================= 新增賽事：選游泳就填公尺 =================
        c['create_form_swim_uses_meters'] = self.ev(pg, """async()=>{ """ + W + """
            await home(); startCreate(); await wait(300);
            const sel=document.getElementById('new-sport'), inp=document.getElementById('new-distance'), unit=()=>document.getElementById('new-distance-unit').textContent;
            const fire=()=>sel.dispatchEvent(new Event('change',{bubbles:true}));
            inp.value='3.3'; sel.value='swimming'; fire(); await wait(50);
            const a=[inp.value,unit(),inp.getAttribute('placeholder'),inp.hasAttribute('list')];
            sel.value='road_running'; fire(); await wait(50);
            const b=[inp.value,unit(),inp.hasAttribute('list')];
            sel.value='swimming'; fire(); await wait(50); inp.value='1500';
            document.getElementById('new-name').value='V46 新泳渡';
            document.querySelector('[data-action="confirm-create"]').click(); await wait(400);
            const r=state.races.find(x=>x.name==='V46 新泳渡');
            const ok=JSON.stringify(a)==='["3300","m","公尺，例如 1500",false]' && JSON.stringify(b)==='["3.3","km",true]' && !!r && r.route.distanceKm===1.5 && r.sportType==='swimming';
            if(!ok) console.log('v46: create',JSON.stringify([a,b,r&&r.route.distanceKm]));
            await home(); return ok; }""")
        c['paste_create_swim_fills_meters'] = self.ev(pg, """async()=>{ """ + W + """
            startCreateFromPaste({name:'貼上的泳渡',sportType:'swimming',distanceKm:3.3}); await wait(300);
            const inp=document.getElementById('new-distance');
            const ok=inp.value==='3300' && inp.dataset.unit==='m' && document.getElementById('new-distance-unit').textContent==='m';
            await home(); return ok; }""")
        c['help_describes_band_and_swim_meters'] = self.ev(pg, """async()=>{ """ + W + """ const out={};
            // 計時帶上有哪三樣要寫成一句（只看單字的話，說明裡別處也有「均速」「爬升」，拿掉這一句也照樣過）
            const words={zh:['計時帶印著完賽時間、均速和爬升','每 100 公尺','三鐵、二鐵只寫成績','游泳的距離寫公尺'],
              ja:['計測帯には完走タイム・平均・獲得標高','100m あたり','デュアスロンはタイムだけ','メートルで表示'],
              en:['timing strip along the bottom shows your finish time, average and elevation gain','per 100 m','triathlons and duathlons show just the time','meters everywhere']};
            for(const lang of ['zh','ja','en']){ setLang(lang); await wait(150); openHelpModal(); await wait(200);
              const tx=document.querySelector('#help-modal .help-body').textContent; out[lang]=words[lang].filter(w=>!tx.includes(w));
              document.querySelector('#help-modal [data-action="close-help"]').click(); await wait(150); }
            setLang('zh'); await wait(100);
            const ok=Object.values(out).every(m=>m.length===0); if(!ok) console.log('v46: help missing',JSON.stringify(out)); return ok; }""")
        # （版本號的檢查跟著最新的群組走，v4.7.0 起在 v47）
        # 公開頁會把整頁換掉：放在這個頁面的最後
        if pub and isinstance(pub, dict):
            c['public_view_and_report_prompt_in_meters'] = self.ev(pg, """(o)=>{ renderPublicShareView(o.snap); const tx=document.body.textContent;
                const ok=tx.includes('3300 公尺') && !tx.includes('3.3 公里') && (!o.prompt || (o.prompt.includes('3300 m') && !o.prompt.includes('3.3 km')));
                if(!ok) console.log('v46: public',tx.slice(0,200)); return ok; }""", pub)
        ctx.close()
        # ================= 手機清單：游泳寫公尺 =================
        pctx, pp = self._ctx(browser, viewport={'width': 390, 'height': 844}, touch=True)
        c['phone_list_search_shows_swim_meters'] = self.ev(pp, """async()=>{ const wait=ms=>new Promise(s=>setTimeout(s,ms));
            setPhoneView('list'); renderAll(); await wait(150);
            const si=document.getElementById('search-input'); si.value='日月潭'; si.dispatchEvent(new Event('input',{bubbles:true})); await wait(400);
            const m=[...document.querySelectorAll('#calendar .cal-list-meta')].map(e=>e.textContent.trim());
            si.value=''; si.dispatchEvent(new Event('input',{bubbles:true})); await wait(200);
            const ok=m.includes('3300m · +531m'); if(!ok) console.log('v46: list',JSON.stringify(m)); return ok; }""")
        pctx.close()
        # ================= 瀏覽器的「網頁強制深色」：號碼布、拍立得還是白紙，計時帶還是黑的 =================
        # 強制深色是畫的時候才轉的，算出來的樣式看不到，只能量畫面
        for w, touch in ((1280, False), (390, True)):
            sctx, sp = self._ctx(browser, viewport={'width': w, 'height': 900}, touch=touch, force_dark=True, dsf=1)
            geo = self.ev(sp, """()=>{ const b=__card('神戶馬拉松'); b.scrollIntoView({block:'center'}); const st=document.createElement('style'); st.textContent='.photo-card{transform:none!important}'; document.head.appendChild(st);
                const br=b.getBoundingClientRect(), nr=b.querySelector('.bib-num').getBoundingClientRect(), tr=b.querySelector('.bib-timing').getBoundingClientRect();
                return { paper:[br.left+5, nr.top+nr.height/2], band:[tr.left+4, tr.top+tr.height/2] }; }""")
            sp.wait_for_timeout(200)
            img = cv2.imdecode(np.frombuffer(sp.screenshot(), np.uint8), cv2.IMREAD_COLOR)
            ok = False
            if geo:
                paper = img[int(geo['paper'][1]), int(geo['paper'][0])]
                band = img[int(geo['band'][1]), int(geo['band'][0])]
                lp, lb = V433Fields._lum(paper), V433Fields._lum(band)
                ok = lp > 0.8 and lb < 0.05
                if not ok:
                    print(f'    v46: forced dark {w} paper {paper} band {band}')
            c[f'forced_dark_{w}_bib_paper_stays_white'] = ok
            # 拍立得的白框也一樣
            pg2 = self.ev(sp, """()=>{ const p=__card('東京馬拉松'); p.scrollIntoView({block:'center'}); const r=p.getBoundingClientRect(), ph=p.querySelector('.pola-photo').getBoundingClientRect(); return [r.left+3, (ph.top+ph.bottom)/2]; }""")
            sp.wait_for_timeout(150)
            img = cv2.imdecode(np.frombuffer(sp.screenshot(), np.uint8), cv2.IMREAD_COLOR)
            c[f'forced_dark_{w}_polaroid_frame_stays_white'] = bool(pg2) and V433Fields._lum(img[int(pg2[1]), int(pg2[0])]) > 0.8
            sctx.close()
        # ================= 版面：有爬升、各種寬度 × 語言 × 字級都放得下 =================
        FIT_ALL = """async()=>{ const wait=ms=>new Promise(s=>setTimeout(s,ms)); const fit=""" + BIB_FIT_JS + """; const bad=[];
            for(const lang of ['zh','ja','en']){ setLang(lang); await wait(120);
              for(const fs of ['small','medium','large']){ applyFontScale(fs); await wait(80); fit().forEach(b=>bad.push(lang+' '+fs+' '+b)); } }
            setLang('zh'); applyFontScale('medium');
            if(bad.length) console.log('v46: fit',bad.slice(0,10).join(' | '));
            return bad.length===0; }"""
        # 一般字級：成績和均速／爬升排在同一列（帶子沒有被擠成兩列）
        # 360 寬只看號碼布：拍立得的帶子在白框裡面窄 26px，游泳的「0:58:00」加「2'19"/100m」排不進一行，
        # 均速會整組換到成績下面（這是設計好的退路，不算擠壞）
        ONE_ROW = """(sel)=>{ const bad=[]; const st=document.createElement('style'); st.textContent='.photo-card{transform:none!important}'; document.head.appendChild(st);
            document.querySelectorAll(sel).forEach(b=>{ const t=b.querySelector('.bib-time'), p=b.querySelector('.bib-perf'); if(!t||!p) return;
              const tr=t.getBoundingClientRect(), pr=p.getBoundingClientRect(); if(pr.top>=tr.bottom-1) bad.push((b.closest('.photo-card').title||'').slice(0,8)); });
            st.remove(); if(bad.length) console.log('v46: two rows',bad.join(',')); return bad.length===0 && document.querySelectorAll('#calendar .bib-perf').length>8; }"""
        # V46_QUICK=1：反例驗證時跳過這一段（4 種寬度 × 9 種語言字級，佔這一組大半的時間）；
        # 針對版面的反例照樣跑完整的
        for w in (() if os.environ.get('V46_QUICK') else (360, 390, 700, 1280)):
            fctx, fp = self._ctx(browser, viewport={'width': w, 'height': 900}, touch=w < 641)
            c[f'band_fits_{w}_all_languages_and_font_sizes'] = self.ev(fp, FIT_ALL)
            if w in (360, 390):
                c[f'band_one_row_{w}'] = self.ev(fp, ONE_ROW, '#calendar .bib-card .bib-timing' if w == 360 else '#calendar .bib-timing')
            fctx.close()


# v4.7.0：假時鐘（開頁前裝好，App 裡所有 new Date()／Date.now() 都走它）。
# 時區用 Asia/Taipei：台北 10/3 00:30 是 UTC 10/2 16:30——用 UTC 算天數的寫法會在這裡露餡
V47_CLOCK_JS = r"""(()=>{ const _D=Date; let off=0;
  class D extends _D{ constructor(...a){ if(a.length===0) super(_D.now()+off); else super(...a); } static now(){ return _D.now()+off; } }
  window.Date=D; window.__RealDate=_D;
  window.__setNowMs=ms=>{ off=ms-_D.now(); };
  window.__setNow=iso=>{ window.__setNowMs(new _D(iso).getTime()); };
  window.__setNow('%s');
})();"""

V47_JS = r"""
window.__wait=ms=>new Promise(s=>setTimeout(s,ms));
window.__dq=()=>document.querySelector('#focus-panel-slot .dq-card');
// 第 i 天（2026/10/2 是第 0 天）早上 9 點
window.__dayMs=i=>new __RealDate(2026,9,2+i,9,0,0).getTime();
window.__showDay=async i=>{ __setNowMs(__dayMs(i)); renderFocusPanel(); await __wait(15); return __dq(); };
window.__qt=(s,l)=>l==='en'?'“'+s+'”':'「'+s+'」';
window.__cjk=/[぀-ヿ㐀-鿿＀-￯　-〿]/;
window.__sheet=()=>document.getElementById('daily-quote-sheet');
window.__openSheet=async i=>{ const c=await __showDay(i); c.click(); await __wait(60); return __sheet(); };
window.__closeSheet=async()=>{ const b=__sheet().querySelector('[data-action="close-daily-quote"]'); if(b) b.click(); await __wait(60); };
// 最長、最短的幾句（版面檢查用）
window.__dqHardDays=()=>{ const pick=f=>DAILY_QUOTES.map((q,i)=>[f(q),i]).sort((a,b)=>b[0]-a[0])[0][1];
  return [...new Set([pick(q=>q.text.zh.length+(q.lang!=='zh'?q.text[q.lang].length/2:0)), pick(q=>q.text.ja.length), pick(q=>q.text.en.length),
    pick(q=>q.role.zh.length), pick(q=>q.role.ja.length), pick(q=>q.role.en.length), pick(q=>q.who.en.length), pick(q=>-q.text.zh.length)])]; };
"""

# v4.7.1：模擬手機上載到的 Noto Sans TC／JP。沙盒連不到 Google Fonts，平常退回 DejaVu Sans（字比較寬、字框比較矮），
# 換行跟字落的高度都跟手機不一樣——v4.7.1 的副標題被切，在沙盒裡只差 1 個像素、幾乎看不出來。
# 本機的 Noto Sans CJK TC／JP 跟 Google 的 Noto Sans TC／JP 是同一套字，垂直度量一樣（hhea 1160/-288、沒開 USE_TYPO_METRICS，
# iOS 跟 Linux 的 Chromium 都用這組），拿來冒充
NOTO_AS_WEBFONT_CSS = ''.join(
    f"@font-face{{font-family:'Noto Sans {fam}';font-weight:{w};src:local('Noto Sans CJK {fam}{full}'),local('NotoSansCJK{fam.lower()}-{ps}');}}"
    for fam in ('TC', 'JP') for w, full, ps in (('400', '', 'Regular'), ('500', ' Medium', 'Medium'), ('700', ' Bold', 'Bold')))


class V47DailyQuote(Group):
    """v4.7.0：今日一句。「賽事」分頁最上面每天一句跑者說過的話——筆電放在「下一場」卡右邊（360px、
    一樣高），平板、手機放在它上面；一天一句（當地日期，過午夜換），中文版面＝中文翻譯＋原文，
    日文／英文版面只顯示那個語言；點開看說話者、情境、出處和連結；頭像選單可以關掉。"""

    ECHO = ('v47:',)

    def _echo(self, msg):
        if msg.text.startswith(self.ECHO):
            print('   ', msg.text[:300])

    def ev(self, pg, js, arg=None):
        try:
            return pg.evaluate(js) if arg is None else pg.evaluate(js, arg)
        except Exception as exc:                      # noqa: BLE001
            print('    ⚠', str(exc).split('\n')[0][:200])
            return False

    def _ctx(self, browser, viewport=None, touch=False, theme='light', lang='zh', now='2026-10-02T09:00:00',
             seed=True, force_dark=False, tz='Asia/Taipei', url=None):
        ctx = full_mode_context(browser, viewport=viewport or {'width': 1280, 'height': 900}, is_mobile=touch, has_touch=touch,
                                color_scheme='dark' if force_dark else 'light', timezone_id=tz)
        ctx.add_init_script(V47_CLOCK_JS % now)
        ctx.add_init_script("try{localStorage.setItem('theme-pref-v1','%s');localStorage.setItem('lang-pref-v1','%s');}catch(e){}" % (theme, lang))
        pg = ctx.new_page()
        if force_dark:
            cdp = ctx.new_cdp_session(pg)
            cdp.send('Emulation.setAutoDarkModeOverride', {'enabled': True})
        pg.on('pageerror', lambda e: self.errors.append(str(e)))
        pg.on('console', self._echo)
        pg.goto(url or APP_URL)
        pg.wait_for_timeout(900)
        pg.add_script_tag(content=FIELD_FRAME_JS)
        pg.add_script_tag(content=WALL_SEED_JS)
        pg.add_script_tag(content=V47_JS)
        pg.add_style_tag(content='.badge-unbox-overlay{display:none!important} *{transition:none!important;animation:none!important}')
        if seed:
            self.ev(pg, """async()=>{ if(!state.races.length){ state.races.push(...buildExampleRaces()); }
                state.selectedId=null; state.creating=false; await persist(); renderAll(); await __wait(200); window.scrollTo(0,0); }""")
        return ctx, pg

    def body(self, page):
        c = self.checks
        browser = page.context.browser
        ctx, pg = self._ctx(browser)
        # ================= 資料 =================
        c['quotes_data_complete'] = self.ev(pg, r"""()=>{ const bad=[], ids=new Set(), L=['zh','ja','en'];
            if(DAILY_QUOTES.length!==56) bad.push('count '+DAILY_QUOTES.length);
            DAILY_QUOTES.forEach(q=>{ if(ids.has(q.id)) bad.push('dup '+q.id); ids.add(q.id);
              if(!L.includes(q.lang)) bad.push(q.id+' lang');
              L.forEach(l=>{ if(!(q.text[l]||'').trim()) bad.push(q.id+' text.'+l);
                ['who','role','ctx'].forEach(k=>{ if(!((q[k]||{})[l]||'').trim()) bad.push(q.id+' '+k+'.'+l); });
                // 括號是畫面加的，資料裡不帶
                if(/^[「“"]/.test(q.text[l])) bad.push(q.id+' bracket '+l); });
              if(!/^https:\/\//.test(q.src.url)) bad.push(q.id+' url');
              if(!q.src.pub||!q.src.date) bad.push(q.id+' src');
              // 原文：text[原文語言] 就是原文；只有字跟顯示的不同（簡體原文）才另外帶 orig
              if(q.orig&&q.orig===q.text[q.lang]) bad.push(q.id+' orig redundant');
              // 英文的撇號、引號用彎的（直的 ' 在明體裡很突兀）
              if(/['"]/.test(q.text.en)) bad.push(q.id+' straight quote'); });
            L.forEach(l=>{ if(DAILY_QUOTES.filter(q=>q.lang===l).length<10) bad.push('few '+l); });
            if(bad.length) console.log('v47: data',bad.slice(0,8).join(' | ')); return bad.length===0; }""")
        # 輪播順序：同一個人兩週內不重複出現，不會連三天同一種原文語言（含輪完一圈接回開頭）
        c['rotation_spreads_speakers_and_languages'] = self.ev(pg, r"""()=>{ const n=DAILY_QUOTES.length, bad=[];
            for(let i=0;i<n;i++){ for(let k=1;k<14;k++){ const a=DAILY_QUOTES[i], b=DAILY_QUOTES[(i+k)%n]; if(a.who.en===b.who.en) bad.push(a.id+'~'+b.id); }
              const l=[0,1,2].map(k=>DAILY_QUOTES[(i+k)%n].lang); if(l[0]===l[1]&&l[1]===l[2]) bad.push('3x '+l[0]+' @'+i); }
            if(bad.length) console.log('v47: spread',bad.slice(0,6).join(' | ')); return bad.length===0; }""")
        # ================= 一天一句 =================
        c['one_quote_per_local_day_changes_at_midnight'] = self.ev(pg, r"""async()=>{
            const at=async iso=>{ __setNow(iso); renderFocusPanel(); await __wait(15); const d=__dq(); return d&&d.dataset.quoteId; };
            const Q=DAILY_QUOTES, n=Q.length;
            const r={ a:await at('2026-10-02T00:00:30'), b:await at('2026-10-02T23:59:30'), c:await at('2026-10-03T00:00:30'),
              d:await at('2026-11-27T09:00:00'), e:await at('2026-10-01T09:00:00'), f:await at('2027-03-15T12:00:00') };
            // 10/2 第 1 句、整天不變；台北 10/3 00:00 就換（UTC 這時還是 10/2）；+56 天回到第 1 句；錨點前一天是最後一句
            const f=Math.round((Date.UTC(2027,2,15)-Date.UTC(2026,9,2))/864e5)%n;
            const ok=r.a===Q[0].id && r.b===Q[0].id && r.c===Q[1].id && r.d===Q[0].id && r.e===Q[n-1].id && r.f===Q[f].id;
            __setNow('2026-10-02T09:00:00'); renderFocusPanel();
            if(!ok) console.log('v47: rotation',JSON.stringify(r)); return ok; }""")
        # 開著不動過了午夜：切回分頁就換成新的一句，只換那張卡（下一場卡不重畫）
        c['midnight_rollover_swaps_card_in_place'] = self.ev(pg, r"""async()=>{
            __setNow('2026-10-02T23:59:50'); renderFocusPanel(); await __wait(30);
            const fp=document.querySelector('#focus-panel-slot .focus-panel'), before=__dq().dataset.quoteId;
            __setNow('2026-10-03T00:00:20'); document.dispatchEvent(new Event('visibilitychange')); await __wait(30);
            const after=__dq().dataset.quoteId, same=!!fp&&fp===document.querySelector('#focus-panel-slot .focus-panel');
            const ok=before===DAILY_QUOTES[0].id && after===DAILY_QUOTES[1].id && same;
            __setNow('2026-10-02T09:00:00'); renderFocusPanel();
            if(!ok) console.log('v47: midnight',before,after,same); return ok; }""")
        # ================= 語言（使用者指定的規則），每一句都看 =================
        LANG_RULES = r"""async(lang)=>{ const bad=[], tag={zh:'zh-Hant',ja:'ja',en:'en'};
            setLang(lang); await __wait(60);
            for(let i=0;i<DAILY_QUOTES.length;i++){ const q=DAILY_QUOTES[i], card=await __showDay(i);
              if(!card||card.dataset.quoteId!==q.id){ bad.push(i+' wrong card'); continue; }
              const main=card.querySelector('.dq-quote'), orig=card.querySelector('.dq-orig');
              if(main.textContent!==__qt(q.text[lang],lang)) bad.push(q.id+' main');
              if(main.getAttribute('lang')!==tag[lang]) bad.push(q.id+' main lang');
              if(lang==='zh'&&q.lang!=='zh'){
                // 中文版面：先中文翻譯，下面附原文
                if(!orig||orig.textContent!==__qt(q.text[q.lang],q.lang)||orig.getAttribute('lang')!==tag[q.lang]) bad.push(q.id+' orig');
                else if(orig.getBoundingClientRect().top<main.getBoundingClientRect().bottom-1) bad.push(q.id+' orig not below'); }
              else if(orig) bad.push(q.id+' extra orig');
              if(card.querySelector('.dq-by b').textContent!==q.who[lang]) bad.push(q.id+' who');
              // 日文、英文版面只顯示那個語言：英文整張卡沒有中日文字；日文不出現原文
              if(lang==='en'&&__cjk.test(card.textContent)) bad.push(q.id+' has CJK');
              if(lang==='ja'&&q.lang!=='ja'&&(card.textContent.includes(q.text[q.lang])||(q.orig&&card.textContent.includes(q.orig)))) bad.push(q.id+' shows original'); }
            setLang('zh'); await __wait(60); __setNow('2026-10-02T09:00:00'); renderFocusPanel();
            if(bad.length) console.log('v47: lang '+lang,bad.slice(0,8).join(' | ')); return bad.length===0; }"""
        c['zh_ui_translation_then_original_below'] = self.ev(pg, LANG_RULES, 'zh')
        c['ja_ui_shows_only_japanese'] = self.ev(pg, LANG_RULES, 'ja')
        c['en_ui_shows_only_english'] = self.ev(pg, LANG_RULES, 'en')
        # 讀螢幕：日曆紙是裝飾，日期用一句看不見的話唸；接著是句子、原文、說話者
        c['screen_reader_text_date_quote_author'] = self.ev(pg, r"""async()=>{ const out={};
            for(const lang of ['zh','en']){ setLang(lang); await __wait(60); const card=await __showDay(0);
              out[lang]=[...card.querySelectorAll('.dq-body > *')].map(e=>e.textContent).join('').replace(/\s+/g,' ').trim();
              if(card.querySelector('.dq-page').getAttribute('aria-hidden')!=='true') out[lang]='page not hidden'; }
            setLang('zh'); await __wait(60); const q=DAILY_QUOTES[0];
            const ok=out.zh.startsWith('今日一句，10 月 2 日（週五）：'+__qt(q.text.zh,'zh')+__qt(q.text.en,'en')+q.who.zh+'，'+q.role.zh)
              && out.en.startsWith('Quote of the day, Fri, Oct 2: '+__qt(q.text.en,'en')+q.who.en+', '+q.role.en);
            if(!ok) console.log('v47: sr',JSON.stringify(out)); return ok; }""")
        c['calendar_page_date_three_languages'] = self.ev(pg, r"""async()=>{ const out={};
            for(const lang of ['zh','ja','en']){ setLang(lang); await __wait(60); const c=await __showDay(0);
              out[lang]=['.dq-month','.dq-day','.dq-wd'].map(s=>c.querySelector(s).textContent).join('|'); }
            setLang('zh'); await __wait(60);
            const ok=out.zh==='10 月|2|週五' && out.ja==='10月|2|金曜日' && out.en==='OCT|2|FRI'; if(!ok) console.log('v47: page',JSON.stringify(out)); return ok; }""")
        # ================= 筆電：下一場卡右邊、一樣高、360px；DOM 順序跟畫面一致 =================
        c['laptop_beside_next_race_same_height'] = self.ev(pg, r"""async()=>{ renderFocusPanel(); await __wait(40);
            const card=__dq(), fp=document.querySelector('#focus-panel-slot .focus-panel'); if(!card||!fp) return false;
            const a=fp.getBoundingClientRect(), b=card.getBoundingClientRect(), after=!!(fp.compareDocumentPosition(card)&Node.DOCUMENT_POSITION_FOLLOWING);
            const ok=b.left>=a.right+12 && Math.abs(a.top-b.top)<1 && Math.abs(a.height-b.height)<1.5 && Math.abs(b.width-360)<1 && after;
            if(!ok) console.log('v47: laptop',JSON.stringify([a,b,after])); return ok; }""")
        # 長句子讓今日一句比較高：下一場卡跟著一樣高，不會一長一短
        c['laptop_long_quote_next_race_matches_height'] = self.ev(pg, r"""async()=>{ const i=__dqHardDays()[0]; await __showDay(i);
            // 換了日期，範例賽事可能變成「比完了嗎？」：還沒比的移到新的今天之後 10 天，左邊只有下一場卡
            const moved=state.races.filter(r=>r.status==='registered').map(r=>[r,r.schedule.raceDate]); moved.forEach(([r])=>{ r.schedule.raceDate=addDaysStr(todayISO(),10); });
            renderFocusPanel(); await __wait(30);
            const card=__dq(), fp=document.querySelector('#focus-panel-slot .focus-panel'); const a=fp.getBoundingClientRect(), b=card.getBoundingClientRect();
            moved.forEach(([r,d])=>{ r.schedule.raceDate=d; }); __setNow('2026-10-02T09:00:00'); renderFocusPanel();
            const ok=Math.abs(a.height-b.height)<1.5 && b.height>a.height-1; if(!ok) console.log('v47: tall',a.height,b.height); return ok; }""")
        # 「比完了嗎？」和下一場卡疊在左邊：今日一句維持自己的高度、靠上
        c['laptop_with_result_prompt_keeps_own_height'] = self.ev(pg, r"""async()=>{
            const y=new Date(); y.setDate(y.getDate()-1); const ys=y.getFullYear()+'-'+String(y.getMonth()+1).padStart(2,'0')+'-'+String(y.getDate()).padStart(2,'0');
            const r=emptyRace('V47 昨天的比賽','road_running','registered',ys); state.races.push(r); renderAll(); await __wait(80);
            const card=__dq(), pr=document.querySelector('#focus-panel-slot .result-prompt'), fp=document.querySelector('#focus-panel-slot .focus-panel');
            const ok=!!(card&&pr&&fp) && (()=>{ const b=card.getBoundingClientRect(), p=pr.getBoundingClientRect(), f=fp.getBoundingClientRect();
              return Math.abs(b.top-p.top)<1 && b.left>p.right && b.height<f.bottom-p.top-40; })();
            state.races=state.races.filter(x=>x!==r); renderAll(); await __wait(60);
            if(!ok) console.log('v47: prompt'); return ok; }""")
        # 沒有下一場卡：單獨一張、整排寬
        c['no_next_race_card_full_width'] = self.ev(pg, r"""async()=>{ const fr=computeFocusRace(); state.focusDismissedId=fr&&fr.id; renderFocusPanel(); await __wait(40);
            const card=__dq(), slot=document.getElementById('focus-panel-slot'); const ok=!!card && !slot.querySelector('.focus-panel') && Math.abs(card.getBoundingClientRect().width-slot.getBoundingClientRect().width)<1;
            state.focusDismissedId=null; renderFocusPanel(); return ok; }""")
        # 用鍵盤：Tab 到卡片按 Enter 打開
        pg.focus('#focus-panel-slot .dq-card')
        pg.keyboard.press('Enter')
        pg.wait_for_timeout(150)
        c['keyboard_enter_opens_sheet'] = self.ev(pg, "()=>!__sheet().hidden && document.activeElement && document.activeElement.dataset.action==='close-daily-quote'")
        # ================= 詳細頁 =================
        c['sheet_dialog_semantics'] = self.ev(pg, r"""()=>{ const p=__sheet().querySelector('[role="dialog"]'); if(!p) return false;
            const lb=document.getElementById(p.getAttribute('aria-labelledby')); return p.getAttribute('aria-modal')==='true' && !!lb && lb.textContent.trim()==='今日一句'; }""")
        pg.keyboard.press('Escape')
        pg.wait_for_timeout(150)
        c['esc_closes_sheet_focus_back_on_card'] = self.ev(pg, "()=>__sheet().hidden && document.activeElement===__dq()")
        c['backdrop_and_back_button_close_sheet'] = self.ev(pg, r"""async()=>{ let sh=await __openSheet(0); const a=!sh.hidden;
            sh.dispatchEvent(new MouseEvent('click',{bubbles:true})); await __wait(80); const b=sh.hidden;
            sh=await __openSheet(0); await __wait(120); history.back(); await __wait(500); const c=sh.hidden;
            return a&&b&&c; }""")
        c['sheet_zh_every_quote_who_context_source'] = self.ev(pg, r"""async()=>{ const bad=[];
            for(let i=0;i<DAILY_QUOTES.length;i++){ const q=DAILY_QUOTES[i], sh=await __openSheet(i);
              if(sh.hidden){ bad.push(q.id+' not open'); continue; }
              const t=s=>{ const e=sh.querySelector(s); return e?e.textContent.trim():null; };
              if(t('.dq-sheet-main')!==__qt(q.text.zh,'zh')) bad.push(q.id+' main');
              const o=sh.querySelector('.dq-sheet-orig [lang]');
              if(q.lang!=='zh'){ if(!o||o.textContent!==__qt(q.text[q.lang],q.lang)) bad.push(q.id+' orig'); } else if(o) bad.push(q.id+' orig shown');
              const who=t('.dq-sheet-who')||''; if(!who.includes(q.who.zh)||!who.includes(q.role.zh)) bad.push(q.id+' who');
              if(t('.dq-sheet-ctx')!==q.ctx.zh) bad.push(q.id+' ctx');
              const pub=t('.dq-sheet-src-pub')||''; if(!pub.includes(q.src.pub)||!pub.includes(q.src.date.replace(/-/g,'/'))) bad.push(q.id+' pub');
              const a=sh.querySelector('a.dq-sheet-link'); if(!a||a.getAttribute('href')!==q.src.url||a.target!=='_blank'||!/noopener/.test(a.rel)) bad.push(q.id+' link');
              // 中文是翻譯的才註明
              const note=t('.dq-sheet-note'); if((note==='中文是本站翻譯的')!==(q.lang!=='zh')||(q.lang==='zh'&&note)) bad.push(q.id+' note');
              await __closeSheet(); }
            if(bad.length) console.log('v47: sheet zh',bad.slice(0,8).join(' | ')); return bad.length===0; }""")
        SHEET_ONLY = r"""async(lang)=>{ const bad=[]; setLang(lang); await __wait(60);
            const noteText={ja:'日本語訳はこのアプリによるものです',en:'English translation by this app'}[lang];
            for(let i=0;i<DAILY_QUOTES.length;i++){ const q=DAILY_QUOTES[i], sh=await __openSheet(i);
              const t=s=>{ const e=sh.querySelector(s); return e?e.textContent.trim():null; };
              if(t('.dq-sheet-main')!==__qt(q.text[lang],lang)) bad.push(q.id+' main');
              if(sh.querySelector('.dq-sheet-orig')) bad.push(q.id+' orig shown');
              const who=t('.dq-sheet-who')||''; if(!who.includes(q.who[lang])||!who.includes(q.role[lang])) bad.push(q.id+' who');
              if(t('.dq-sheet-ctx')!==q.ctx[lang]) bad.push(q.id+' ctx');
              const note=t('.dq-sheet-note'); if((note===noteText)!==(q.lang!==lang)) bad.push(q.id+' note');
              if(lang==='en'&&__cjk.test(sh.textContent)) bad.push(q.id+' CJK in sheet');
              if(lang==='ja'&&q.lang!=='ja'&&sh.textContent.includes(q.text[q.lang])) bad.push(q.id+' original shown');
              await __closeSheet(); }
            setLang('zh'); await __wait(60);
            if(bad.length) console.log('v47: sheet '+lang,bad.slice(0,8).join(' | ')); return bad.length===0; }"""
        c['sheet_ja_only_japanese'] = self.ev(pg, SHEET_ONLY, 'ja')
        c['sheet_en_only_english'] = self.ev(pg, SHEET_ONLY, 'en')
        # 英文的撇號不是全形：句子用拉丁明體；說話者那一行模擬正式站載入 Noto Sans TC（這裡用本機同一套 Noto Sans CJK TC）
        c['english_apostrophes_not_full_width'] = self.ev(pg, r"""async()=>{ setLang('en'); await __wait(60);
            const w=(el,ch)=>{ const walker=document.createTreeWalker(el,NodeFilter.SHOW_TEXT); let n; while((n=walker.nextNode())){ const k=n.textContent.indexOf(ch);
                if(k>=0){ const r=document.createRange(); r.setStart(n,k); r.setEnd(n,k+1); return r.getBoundingClientRect().width/parseFloat(getComputedStyle(el).fontSize); } } return null; };
            const keep=document.body.style.fontFamily; document.body.style.fontFamily="'Noto Sans CJK TC',sans-serif";
            const i=DAILY_QUOTES.findIndex(q=>q.text.en.includes('’')), j=DAILY_QUOTES.findIndex(q=>q.role.en.includes('’'));
            const a=w((await __showDay(i)).querySelector('.dq-quote'),'’'), b=w((await __showDay(j)).querySelector('.dq-role'),'’');
            const sh=await __openSheet(j); const d=w(sh.querySelector('.dq-sheet-who'),'’'); await __closeSheet();
            document.body.style.fontFamily=keep; setLang('zh'); await __wait(60); __setNow('2026-10-02T09:00:00'); renderFocusPanel();
            const ok=a!==null&&a<0.45&&b!==null&&b<0.45&&d!==null&&d<0.45; if(!ok) console.log('v47: apostrophe',a,b,d); return ok; }""")
        # ================= 對比：淺色、深色 =================
        c['card_text_contrast_light_dark'] = self.ev(pg, r"""async()=>{ const bad=[]; await __showDay(0);
            for(const th of ['light','dark']){ applyTheme(th); await __wait(80);
              ['.dq-quote','.dq-orig','.dq-by b','.dq-role','.dq-month','.dq-day','.dq-wd'].forEach(s=>{ const e=document.querySelector('#focus-panel-slot '+s);
                if(!e){ bad.push(th+' missing '+s); return; } const cr=__textCr(e); if(cr<4.5) bad.push(th+' '+s+' '+cr.toFixed(2)); }); }
            applyTheme('light'); if(bad.length) console.log('v47: contrast',bad.join(' | ')); return bad.length===0; }""")
        c['sheet_text_contrast_light_dark'] = self.ev(pg, r"""async()=>{ const bad=[];
            for(const th of ['light','dark']){ applyTheme(th); await __wait(80); const sh=await __openSheet(0);
              ['.dq-sheet-head h2','.dq-sheet-main','.dq-sheet-orig-label','.dq-sheet-orig [lang]','.dq-sheet-who b','.dq-sheet-who','.dq-sheet-ctx','.dq-sheet-src-label','.dq-sheet-src-pub','.dq-sheet-link','.dq-sheet-note','.dq-sheet-hide'].forEach(s=>{
                const e=sh.querySelector(s); if(!e){ bad.push(th+' missing '+s); return; } const cr=__textCr(e); if(cr<4.5) bad.push(th+' '+s+' '+cr.toFixed(2)); });
              await __closeSheet(); }
            applyTheme('light'); if(bad.length) console.log('v47: sheet contrast',bad.join(' | ')); return bad.length===0; }""")
        c['calendar_page_white_in_dark_mode'] = self.ev(pg, r"""async()=>{ const read=()=>{ const p=document.querySelector('#focus-panel-slot .dq-page'); return [getComputedStyle(p).backgroundColor,getComputedStyle(p).colorScheme,getComputedStyle(p.querySelector('.dq-day')).color]; };
            const light=read(); applyTheme('dark'); await __wait(80); const dark=read(); applyTheme('light'); await __wait(60);
            const ok=JSON.stringify(light)===JSON.stringify(dark) && light[0]==='rgb(255, 255, 255)' && /only/.test(light[1]) && /light/.test(light[1]) && !/dark/.test(light[1]);
            if(!ok) console.log('v47: page dark',JSON.stringify([light,dark])); return ok; }""")
        # ================= 字型 =================
        c['serif_fonts_per_language'] = self.ev(pg, r"""async()=>{ const href=[...document.querySelectorAll('link[rel="stylesheet"]')].map(l=>l.href).filter(h=>h.includes('fonts.googleapis.com')).join(' ');
            const out={}; for(const lang of ['zh','ja','en']){ setLang(lang); await __wait(60); out[lang]=getComputedStyle((await __showDay(0)).querySelector('.dq-quote')).fontFamily; }
            setLang('zh'); await __wait(60);
            const ok=/family=Noto\+Serif\+TC:wght@600/.test(href) && /family=Noto\+Serif\+JP:wght@600/.test(href)
              && /^"?Noto Serif TC"?,/.test(out.zh) && /^"?Noto Serif JP"?,/.test(out.ja) && /^Georgia,/.test(out.en) && /serif$/.test(out.zh) && /serif$/.test(out.en);
            if(!ok) console.log('v47: fonts',JSON.stringify(out)); return ok; }""")
        # ================= 說明、選單 =================
        c['help_describes_daily_quote'] = self.ev(pg, r"""async()=>{ const out={};
            const words={zh:['今日一句','過了午夜換下一句','下面附原文','頭像選單「顯示」裡的「今日一句」'],
              ja:['今日の名言','日付が変わると次の言葉','日本語だけを表示','「今日の名言」をオフ'],
              en:['Quote of the day','changes at midnight','In English you only see English','turn off “Quote of the day”']};
            for(const lang of ['zh','ja','en']){ setLang(lang); await __wait(120); openHelpModal(); await __wait(200);
              const tx=document.querySelector('#help-modal .help-body').textContent; out[lang]=words[lang].filter(w=>!tx.includes(w));
              document.querySelector('#help-modal [data-action="close-help"]').click(); await __wait(150); }
            setLang('zh'); await __wait(100);
            const ok=Object.values(out).every(m=>m.length===0); if(!ok) console.log('v47: help missing',JSON.stringify(out)); return ok; }""")
        c['menu_toggle_label_three_languages'] = self.ev(pg, r"""async()=>{ const out={};
            for(const lang of ['zh','ja','en']){ setLang(lang); await __wait(80); out[lang]=document.getElementById('daily-quote-row-label').textContent.trim(); }
            setLang('zh'); await __wait(80);
            return out.zh==='今日一句' && out.ja==='今日の名言' && out.en==='Quote of the day'; }""")
        # （版本號的檢查跟著最新的群組走，v4.7.1 起在 v471）
        # ================= 只在「賽事」首頁 =================
        c['hidden_on_search_career_and_race_page'] = self.ev(pg, r"""async()=>{ const vis=()=>{ const d=__dq(); return !!d && d.getClientRects().length>0; };
            const base=vis();
            const si=document.getElementById('search-input'); si.value='範例'; si.dispatchEvent(new Event('input',{bubbles:true})); await __wait(300); const search=vis();
            si.value=''; si.dispatchEvent(new Event('input',{bubbles:true})); await __wait(300); const back=vis();
            document.querySelector('.home-tab[data-home-tab="career"]').click(); await __wait(200); const career=vis();
            document.querySelector('.home-tab[data-home-tab="races"]').click(); await __wait(200);
            selectRace(state.races[0].id,{scroll:false}); await __wait(300); const detail=vis(); goBackFromDetail(); await __wait(350);
            const ok=base && !search && back && !career && !detail && vis(); if(!ok) console.log('v47: places',base,search,back,career,detail); return ok; }""")
        # ================= 開關 =================
        c['sheet_hide_turns_off_with_toast'] = self.ev(pg, r"""async()=>{ const sh=await __openSheet(0);
            sh.querySelector('[data-action="hide-daily-quote"]').click(); await __wait(150);
            const toast=[...document.querySelectorAll('.foreground-toast')].map(e=>e.textContent).join('|');
            const ok=sh.hidden && !__dq() && document.getElementById('btn-daily-quote-toggle').getAttribute('aria-checked')==='false' && toast.includes('頭像選單');
            if(!ok) console.log('v47: hide',sh.hidden,!!__dq(),toast); return ok; }""")
        ctx.close()
        # 頭像選單的開關、重新整理之後還是關的：用本機 http 開（headless Chromium 在 file:// 下重新整理，
        # 偶爾會把整個 localStorage 弄丟——v41 也是這樣做；反例驗證時這兩項在 file:// 下會隨機失敗）
        import http.server, socketserver, threading, functools

        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *a, **k):
                pass
        socketserver.TCPServer.allow_reuse_address = True
        srv = socketserver.TCPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=os.path.dirname(os.path.abspath(APP))))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        hctx, hp = self._ctx(browser, url=f'http://127.0.0.1:{srv.server_address[1]}/' + os.path.basename(APP))
        c['menu_toggle_turns_off_menu_stays_open'] = self.ev(hp, r"""async()=>{ const had=!!__dq();
            document.getElementById('btn-account-menu').click(); await __wait(150);
            document.getElementById('btn-daily-quote-toggle').click(); await __wait(150);
            return had && !__dq() && document.getElementById('btn-daily-quote-toggle').getAttribute('aria-checked')==='false' && !document.getElementById('account-menu-panel').hidden; }""")
        hp.reload()
        hp.wait_for_function("()=>typeof state!=='undefined' && state.races.length>0", timeout=30000)
        hp.wait_for_timeout(400)
        hp.add_script_tag(content=V47_JS)
        c['hidden_preference_survives_reload'] = self.ev(hp, "()=>!__dq() && document.getElementById('btn-daily-quote-toggle').getAttribute('aria-checked')==='false'")
        c['menu_toggle_turns_back_on'] = self.ev(hp, r"""async()=>{ document.getElementById('btn-account-menu').click(); await __wait(150);
            document.getElementById('btn-daily-quote-toggle').click(); await __wait(150);
            return !!__dq() && document.getElementById('btn-daily-quote-toggle').getAttribute('aria-checked')==='true' && !document.getElementById('account-menu-panel').hidden; }""")
        hctx.close()
        srv.shutdown()
        # 第一次使用（還沒有賽事）：只有歡迎卡
        fctx, fp = self._ctx(browser, seed=False)
        c['not_on_first_run_welcome'] = self.ev(fp, "()=>!__dq() && !!document.querySelector('#calendar .welcome-card')")
        fctx.close()
        # ================= 平板、手機：在下一場卡上面、一樣寬；換斷點會重排 =================
        for w, touch in ((1099, False), (390, True)):
            sctx, sp = self._ctx(browser, viewport={'width': w, 'height': 900}, touch=touch)
            c[f'stacked_{w}_above_next_race_same_width'] = self.ev(sp, r"""()=>{ const card=__dq(), fp=document.querySelector('#focus-panel-slot .focus-panel'); if(!card||!fp) return false;
                const a=fp.getBoundingClientRect(), b=card.getBoundingClientRect(), first=!!(card.compareDocumentPosition(fp)&Node.DOCUMENT_POSITION_FOLLOWING);
                const ok=b.bottom<=a.top-8 && Math.abs(a.left-b.left)<1 && Math.abs(a.right-b.right)<1 && first;
                if(!ok) console.log('v47: stacked',innerWidth,JSON.stringify([a,b,first])); return ok; }""")
            if w == 390:
                # 手機只寫名字（身分在詳細頁）
                c['phone_card_name_only'] = self.ev(sp, "()=>{ const r=__dq().querySelector('.dq-role'); return !!r && r.getClientRects().length===0 && __dq().querySelector('.dq-by b').getClientRects().length>0; }")
            sctx.close()
        rctx, rp = self._ctx(browser, viewport={'width': 1280, 'height': 900})
        side = lambda: self.ev(rp, r"""()=>{ const card=__dq(), fp=document.querySelector('#focus-panel-slot .focus-panel'); const a=fp.getBoundingClientRect(), b=card.getBoundingClientRect();
            return {side:b.left>=a.right, cardFirst:!!(card.compareDocumentPosition(fp)&Node.DOCUMENT_POSITION_FOLLOWING)}; }""")
        s1 = side()
        rp.set_viewport_size({'width': 1000, 'height': 900}); rp.wait_for_timeout(300)
        s2 = side()
        rp.set_viewport_size({'width': 1280, 'height': 900}); rp.wait_for_timeout(300)
        s3 = side()
        c['resize_across_1100_reorders'] = bool(s1 and s2 and s3 and s1['side'] and not s1['cardFirst'] and not s2['side'] and s2['cardFirst'] and s3['side'] and not s3['cardFirst'])
        rctx.close()
        # ================= 瀏覽器強制深色：日曆紙還是白的 =================
        dctx, dp = self._ctx(browser, viewport={'width': 1280, 'height': 900}, force_dark=True)
        geo = self.ev(dp, "()=>{ const p=__dq().querySelector('.dq-page').getBoundingClientRect(); return [p.left+4, p.top+p.height*0.62]; }")
        dp.wait_for_timeout(200)
        ok = False
        if geo:
            img = cv2.imdecode(np.frombuffer(dp.screenshot(), np.uint8), cv2.IMREAD_COLOR)
            px = img[int(geo[1]), int(geo[0])]
            ok = V433Fields._lum(px) > 0.8
            if not ok:
                print('    v47: forced dark page', px)
        c['forced_dark_calendar_page_stays_white'] = ok
        dctx.close()
        # ================= 版面：各種寬度 × 語言 × 字級都放得下 =================
        FIT = r"""async(o)=>{ const bad=[]; const days=o.all?DAILY_QUOTES.map((q,i)=>i):__dqHardDays();
            for(const lang of ['zh','ja','en']){ setLang(lang); await __wait(60);
              for(const fs of o.fs){ applyFontScale(fs); await __wait(30);
                for(const i of days){ const card=await __showDay(i); if(!card){ bad.push('no card'); continue; }
                  const cr=card.getBoundingClientRect(), tag=lang+' '+fs+' '+DAILY_QUOTES[i].id;
                  if(cr.left<-0.5||cr.right>innerWidth+0.5) bad.push(tag+' card out');
                  card.querySelectorAll('.dq-page,.dq-quote,.dq-orig,.dq-by').forEach(e=>{ const r=e.getBoundingClientRect(); if(!r.width) return;
                    if(r.left<cr.left-0.5||r.right>cr.right+0.5||r.bottom>cr.bottom+0.5) bad.push(tag+' '+e.className+' out'); });
                  // 每一行字都在卡片裡（中日文行尾的「。」」會壓成半形擠進最後一格，字框可能伸進右邊內距幾 px，
                  // 那是全形標點空白的半邊；超出卡片才算擠壞）
                  card.querySelectorAll('.dq-quote,.dq-orig,.dq-by').forEach(e=>{ const rg=document.createRange(); rg.selectNodeContents(e);
                    if([...rg.getClientRects()].some(r=>r.width&&(r.right>cr.right-2||r.left<cr.left+2))) bad.push(tag+' '+e.className+' line out'); });
                  ['.dq-month','.dq-wd','.dq-day'].forEach(s=>{ const e=card.querySelector(s); if(e.scrollWidth>e.clientWidth+1) bad.push(tag+' '+s+' clipped'); });
                  if(document.documentElement.scrollWidth>innerWidth) bad.push(tag+' hscroll');
                  if(o.tiles) document.querySelectorAll('#focus-panel-slot .rw-tile-value').forEach(v=>{ if(v.scrollWidth>v.clientWidth+1) bad.push(tag+' tile '+v.textContent); }); } } }
            setLang('zh'); applyFontScale('medium'); __setNow('2026-10-02T09:00:00'); renderFocusPanel();
            if(bad.length) console.log('v47: fit '+innerWidth,bad.slice(0,8).join(' | ')); return bad.length===0; }"""
        for w in (320, 360, 390):
            jctx, jp = self._ctx(browser, viewport={'width': w, 'height': 900}, touch=True, lang='ja')
            c[f'ja_phone_{w}_prompt_and_view_switch_no_sideways_scroll'] = self.ev(jp, r"""async()=>{ const bad=[];
                const y=new Date(); y.setDate(y.getDate()-1); const ys=y.getFullYear()+'-'+String(y.getMonth()+1).padStart(2,'0')+'-'+String(y.getDate()).padStart(2,'0');
                state.races.push(emptyRace('V47 昨日の大会','road_running','registered',ys)); renderAll(); await __wait(100);
                for(const fs of ['small','medium','large']){ applyFontScale(fs); await __wait(60);
                  const pr=document.querySelector('#focus-panel-slot .result-prompt'); if(!pr){ bad.push(fs+' no prompt'); continue; }
                  pr.querySelectorAll('.result-prompt-alt .btn-ghost').forEach(b=>{ const r=b.getBoundingClientRect(); if(b.scrollWidth>b.clientWidth+1||r.right>innerWidth) bad.push(fs+' '+b.textContent.trim()+' spills'); if(r.height<44) bad.push(fs+' short'); });
                  const seg=document.querySelector('.view-seg'); if(seg.getBoundingClientRect().right>innerWidth+0.5) bad.push(fs+' view switch out');
                  if(document.documentElement.scrollWidth>innerWidth) bad.push(fs+' hscroll '+document.documentElement.scrollWidth); }
                applyFontScale('medium'); if(bad.length) console.log('v47: ja phone '+innerWidth,bad.join(' | ')); return bad.length===0; }""")
            jctx.close()
        # V47_QUICK=1：反例驗證時跳過這一段（7 種寬度 × 中日英 × 三種字級，佔這一組一半以上的時間）；針對版面的反例照樣跑完整的
        for w in (() if os.environ.get('V47_QUICK') else (320, 360, 390, 700, 1099, 1100, 1280)):
            touch = w < 641
            fctx, fpg = self._ctx(browser, viewport={'width': w, 'height': 900}, touch=touch)
            every = w in (320, 1100)
            c[f'fits_{w}_languages_font_sizes'] = self.ev(fpg, FIT, {'fs': ['small', 'medium', 'large'], 'all': False, 'tiles': w >= 1100})
            if every:
                c[f'fits_{w}_every_quote'] = self.ev(fpg, FIT, {'fs': ['large'], 'all': True, 'tiles': w >= 1100})
            fctx.close()


class V471TaglineFit(V47DailyQuote):
    """v4.7.1：手機頂列的副標題，字級「大」時下半截被切掉（收合動畫的 max-height 寫死 20px，一行字 25.8px）。
    改成跟著字級走；放不下一行時換行，不再截成「…」。往下捲時照樣收起來。"""

    ECHO = ('v471:',)

    def body(self, page):
        c = self.checks
        browser = page.context.browser
        # 每一種寬度 × 中日英 × 三種字級：副標題整句都看得到（沒被切、沒有「…」），最多兩行，在頂列裡、
        # 不壓到首頁分頁；標題那一行照樣是一行（簡易版、頭像跟標題同一行）；沒有橫向捲動
        FIT = r"""async()=>{ const bad=[];
            for(const lang of ['zh','ja','en']){ setLang(lang); await __wait(80); await document.fonts.ready;
              for(const fs of ['small','medium','large']){ applyFontScale(fs); window.scrollTo(0,0); await __wait(120);
                const e=document.querySelector('.app-tagline'), tag=lang+' '+fs, cs=getComputedStyle(e), lh=parseFloat(cs.lineHeight);
                const r=e.getBoundingClientRect(), tb=document.getElementById('topbar').getBoundingClientRect(), tabs=document.querySelector('.home-tabs').getBoundingClientRect();
                if(e.scrollHeight>e.clientHeight+1) bad.push(tag+' cut '+e.scrollHeight+'>'+e.clientHeight);
                if(e.scrollWidth>e.clientWidth+1) bad.push(tag+' ellipsis');
                if(r.height>lh*2+1) bad.push(tag+' >2 lines');
                if(r.height<lh-1) bad.push(tag+' squashed '+r.height.toFixed(1));
                if(r.bottom>tb.bottom+0.5||r.top<tb.top) bad.push(tag+' outside topbar');
                if(tabs.top<tb.bottom-0.5) bad.push(tag+' overlaps tabs');
                const t=document.querySelector('.app-title').getBoundingClientRect(), sw=document.getElementById('btn-mode-toggle').getBoundingClientRect(), av=document.getElementById('btn-account-menu').getBoundingClientRect();
                if(innerWidth<=860&&(sw.top>=t.bottom||av.top>=t.bottom||sw.right>av.left)) bad.push(tag+' title row breaks');
                if(document.documentElement.scrollWidth>innerWidth) bad.push(tag+' hscroll'); } }
            setLang('zh'); applyFontScale('medium');
            if(bad.length) console.log('v471: tagline '+innerWidth,bad.slice(0,8).join(' | ')); return bad.length===0; }"""
        for w in (320, 360, 390, 430, 700, 860, 1100):
            touch = w < 641
            fctx, fp = self._ctx(browser, viewport={'width': w, 'height': 844}, touch=touch)
            c[f'tagline_whole_{w}_all_languages_font_sizes'] = self.ev(fp, FIT)
            fctx.close()
        # 手機寬度再用手機上的字型度量跑一次（NOTO_AS_WEBFONT_CSS）：字框高度、字落的位置、英文要換幾行都跟手機一樣
        for w in (320, 360, 390):
            fctx, fp = self._ctx(browser, viewport={'width': w, 'height': 844}, touch=True)
            fp.add_style_tag(content=NOTO_AS_WEBFONT_CSS)
            c[f'tagline_whole_{w}_with_phone_font_metrics'] = self.ev(fp, r"""async()=>{ await document.fonts.ready; await __wait(100);
                const e=document.querySelector('.app-tagline'), rg=document.createRange(); rg.selectNodeContents(e);
                const h=rg.getClientRects()[0].height/parseFloat(getComputedStyle(e).fontSize);
                if(h<1.3){ console.log('v471: phone font metrics not applied, glyph box '+h.toFixed(2)+'em'); return false; }
                return (""" + FIT + """)(); }""")
            fctx.close()
        # 往下捲：副標題收起來（頂列變矮）；捲回最上面：整句回來、沒被切
        sctx, sp = self._ctx(browser, viewport={'width': 390, 'height': 844}, touch=True)
        c['tagline_collapses_on_scroll_and_comes_back'] = self.ev(sp, r"""async()=>{ applyFontScale('large'); await __wait(100);
            const e=document.querySelector('.app-tagline'), tb=document.getElementById('topbar');
            window.scrollTo(0,0); window.dispatchEvent(new Event('scroll')); await __wait(200); const h0=e.getBoundingClientRect().height, b0=tb.getBoundingClientRect().height;
            window.scrollTo(0,600); window.dispatchEvent(new Event('scroll')); await __wait(300);
            const compact=tb.classList.contains('topbar-compact'), h1=e.getBoundingClientRect().height, b1=tb.getBoundingClientRect().height;
            window.scrollTo(0,0); window.dispatchEvent(new Event('scroll')); await __wait(300);
            const h2=e.getBoundingClientRect().height, cut=e.scrollHeight>e.clientHeight+1;
            applyFontScale('medium');
            const back=!tb.classList.contains('topbar-compact');
            const ok=compact && h1<1 && b1<b0-20 && Math.abs(h2-h0)<1 && h0>25 && !cut && back;
            if(!ok) console.log('v471: scroll',h0,b0,compact,h1,b1,h2,cut,back,document.documentElement.scrollHeight); return ok; }""")
        # （版本號的檢查跟著最新的群組走，v4.8.0 起在 v48）
        sctx.close()


# v4.8.0：Spotify 的嵌入播放器在沙盒裡連不到——用一個灰色的替身頁面代替，順便數播放器被載入了幾次
EMBED_STUB_HTML = ('<!doctype html><meta charset="utf-8"><body style="margin:0;height:100vh;display:flex;align-items:center;'
                   'justify-content:center;background:#C9CCC6;color:#2B2F2C;font:13px sans-serif">Spotify 播放器（測試替身）</body>')

V48_JS = r"""
// 22 碼的 Spotify ID（格式對就好，替身頁不管是哪一首）
window.__SP={ track:'4uLU6hMCjMI75M1A2tKUQC', track2:'7ouMYWpwJ422jRcDASZB7P', album:'1DFixLWuPkv3KT3TnV35m3',
  playlist:'37i9dQZF1DXcBWIGoYBM5M', episode:'512ojhOuo1ktJprKbVcKyQ', show:'5CfCWKI5pZ28U0uOzXkDHe', artist:'0OdUWJ0sBjDrqHygGUXeCF' };
window.__bgmRace=()=>state.races.find(x=>x.id==='example-alishan-trail');
window.__setLinks=async(links,r)=>{ r=r||__bgmRace(); r.mediaLinks=links.map(l=>Object.assign({type:'other',url:'',notes:''},l));
  r.updatedAt=new Date().toISOString(); await persist(); return r; };
window.__open=async r=>{ r=r||__bgmRace(); if(state.selectedId===r.id&&currentRace&&currentRace.id===r.id) renderDetail(); else selectRace(r.id,{scroll:false});
  await __wait(250); return document.querySelector('.detail-header'); };
window.__bgm=()=>document.querySelector('.detail-header .dh-bgm');
window.__frame=()=>document.querySelector('.detail-header iframe.dh-bgm-frame');
window.__pasteText=async txt=>{ const dt=new DataTransfer(); dt.setData('text',txt);
  document.dispatchEvent(new ClipboardEvent('paste',{clipboardData:dt,bubbles:true,cancelable:true})); await __wait(300);
  return document.getElementById('paste-note-modal'); };
window.__setField=async(id,val)=>{ const e=document.getElementById(id); e.value=val; e.dispatchEvent(new Event('change',{bubbles:true})); await __wait(350); return e; };
"""


class V48RaceBgm(V47DailyQuote):
    """v4.8.0：賽事 BGM。多媒體與連結裡的 Spotify 連結（類型「賽事 BGM」的優先），在賽事名稱、日期地點下面
    放 Spotify 官方的嵌入播放器：網址各種寫法都認得（intl-ja、embed、舊式 user、spotify: URI），播放器網址自己組；
    改欄位重畫頁首時不重新載入（支援 moveBefore 的瀏覽器）；深淺色跟著 App；離線、短網址、其他音樂平台放連結；
    貼上或填 Spotify 連結自動歸成「賽事 BGM」；相簿不重複列；手機各寬度、三種語言、三種字級放得下。"""

    ECHO = ('v48:',)

    def _bgm_ctx(self, browser, viewport=None, touch=False, **kw):
        ctx, pg = self._ctx(browser, viewport=viewport, touch=touch, **kw)
        self.embeds = []

        def embed(route):
            self.embeds.append(route.request.url)
            route.fulfill(status=200, body=EMBED_STUB_HTML, headers={'content-type': 'text/html; charset=utf-8'})
        ctx.route('https://open.spotify.com/embed/**', embed)
        pg.add_script_tag(content=V48_JS)
        return ctx, pg

    def body(self, page):
        c = self.checks
        browser = page.context.browser
        ctx, pg = self._bgm_ctx(browser, viewport={'width': 390, 'height': 844}, touch=True)
        # ================= 認得哪些連結 =================
        # 各種寫法的 Spotify 連結都變成播放器：網址由類型＋ID 自己組（?si= 那些追蹤參數不帶過去），放在頁首、日期地點下面
        c['spotify_link_forms_become_player_under_race_name'] = self.ev(pg, r"""async()=>{ const S=__SP, bad=[];
            const cases=[
              ['https://open.spotify.com/track/'+S.track+'?si=1a2b3c4d','track/'+S.track],
              ['https://open.spotify.com/intl-ja/track/'+S.track,'track/'+S.track],
              ['https://open.spotify.com/intl-zh-tw/album/'+S.album+'?si=x','album/'+S.album],
              ['https://open.spotify.com/embed/playlist/'+S.playlist+'?utm_source=generator','playlist/'+S.playlist],
              ['https://open.spotify.com/user/spotify/playlist/'+S.playlist,'playlist/'+S.playlist],
              ['spotify:episode:'+S.episode,'episode/'+S.episode],
              ['https://open.spotify.com/show/'+S.show,'show/'+S.show],
              ['https://open.spotify.com/artist/'+S.artist,'artist/'+S.artist],
              ['http://open.spotify.com/track/'+S.track,'track/'+S.track]];
            for(const [url,want] of cases){ await __setLinks([{type:'music',url}]); const h=await __open(), f=__frame(), box=__bgm();
              if(!f){ bad.push('no player '+url); continue; }
              if(f.src!=='https://open.spotify.com/embed/'+want+'?utm_source=generator') bad.push(url+' -> '+f.src);
              const after=(a,b)=>!!(a.compareDocumentPosition(b)&Node.DOCUMENT_POSITION_FOLLOWING);
              if(!h.contains(box)||!after(h.querySelector('h1'),box)||!after(h.querySelector('.dh-meta'),box)) bad.push('position '+url); }
            if(bad.length) console.log('v48: forms',bad.slice(0,6).join(' | ')); return bad.length===0; }""")
        # 畫面上：日期地點那一行正下方，倒數和賽前四格在它下面
        c['player_sits_between_meta_line_and_countdown'] = self.ev(pg, r"""async()=>{
            await __setLinks([{type:'music',url:'https://open.spotify.com/track/'+__SP.track}]); const h=await __open(); window.scrollTo(0,0); await __wait(60);
            const m=h.querySelector('.dh-meta').getBoundingClientRect(), b=__bgm().getBoundingClientRect(), tiles=h.querySelector('.rw-tiles'), prog=h.querySelector('.progress-block,.countdown,.dh-progress');
            const below=b.top>=m.bottom-0.5&&b.top-m.bottom<24, above=(!tiles||tiles.getBoundingClientRect().top>=b.bottom)&&(!prog||prog.getBoundingClientRect().top>=b.bottom);
            if(!(below&&above)) console.log('v48: geometry',m.bottom,b.top,b.bottom,tiles&&tiles.getBoundingClientRect().top); return below&&above; }""")
        # 不是 Spotify、ID 不對、危險的網址：不放播放器，也不會變成 javascript:／data: 連結或插進 HTML
        c['non_spotify_or_unsafe_links_never_become_player'] = self.ev(pg, r"""async()=>{ const S=__SP, bad=[];
            const cases=['https://evil.example/open.spotify.com/track/'+S.track,'https://open.spotify.com.evil.example/track/'+S.track,
              'https://open.spotify.com/track/abc','javascript:alert(1)//open.spotify.com/track/'+S.track,
              'https://open.spotify.com/track/'+S.track+'"><img src=x onerror=alert(1)>','data:text/html,<script>alert(1)</script>'];
            for(const url of cases){ await __setLinks([{type:'music',url}]); const h=await __open();
              if(__frame()) bad.push('player '+url);
              if(h.querySelector('a[href^="javascript:"],a[href^="data:"],img[src="x"],script')) bad.push('unsafe '+url); }
            if(bad.length) console.log('v48: unsafe',bad.join(' | ')); return bad.length===0; }""")
        # 頁首放類型是「賽事 BGM」的那一筆；其他連結（包括別的 Spotify）留在賽後紀錄的相簿，放在頁首的不重複列
        c['bgm_typed_link_wins_and_others_stay_in_gallery'] = self.ev(pg, r"""async()=>{ const S=__SP, bad=[];
            const A='https://open.spotify.com/track/'+S.track, B='https://open.spotify.com/track/'+S.track2;
            await __setLinks([{type:'other',url:A},{type:'photo_album',url:'https://photos.example.org/album'},{type:'music',url:B,notes:'終點那首'}]);
            const h=await __open(), f=__frame();
            if(!f||!f.src.includes(S.track2)) bad.push('header not the BGM one '+(f&&f.src));
            if(h.querySelector('.dh-bgm-cap').textContent.trim()!=='終點那首') bad.push('caption');
            const hrefs=[...document.querySelectorAll('#section-post .media-gallery-card')].map(a=>a.href);
            if(hrefs.some(x=>x.includes(S.track2))) bad.push('BGM repeated in gallery');
            if(!hrefs.some(x=>x.includes(S.track))||!hrefs.some(x=>x.includes('photos.example.org'))) bad.push('others missing '+hrefs.join(','));
            // 沒有「賽事 BGM」類型的：第一筆 Spotify 連結上頁首
            await __setLinks([{type:'photo_album',url:'https://photos.example.org/album'},{type:'other',url:A}]); await __open();
            if(!__frame()||!__frame().src.includes(S.track)) bad.push('first spotify link');
            if(bad.length) console.log('v48: pick',bad.join(' | ')); return bad.length===0; }""")
        # 沒有音樂連結的賽事：頁首完全沒有這一塊
        c['no_music_link_no_block'] = self.ev(pg, r"""async()=>{
            await __setLinks([{type:'photo_album',url:'https://photos.example.org/a'},{type:'official_site',url:'https://race.example.org/'}]); await __open();
            return !__bgm(); }""")
        # 播放器本身：延後載入、有讀螢幕唸的標題、官方的權限（加密媒體、全螢幕）、官方精簡尺寸 152px
        c['player_lazy_titled_official_size'] = self.ev(pg, r"""async()=>{
            await __setLinks([{type:'music',url:'https://open.spotify.com/track/'+__SP.track}]); await __open(); const f=__frame(); if(!f) return false;
            const ok=f.loading==='lazy'&&(f.getAttribute('allow')||'').includes('encrypted-media')&&f.hasAttribute('allowfullscreen')
              &&Math.round(f.getBoundingClientRect().height)===152&&f.title.trim().length>0;
            if(!ok) console.log('v48: attrs',f.outerHTML.slice(0,300)); return ok; }""")
        # 小字（備註，沒寫就是「賽事 BGM」）、播放器的標題跟著語言；換語言不重新載入播放器
        c['caption_and_title_follow_language_without_reload'] = self.ev(pg, r"""async()=>{ const bad=[];
            const want={zh:['賽事 BGM','賽事 BGM（Spotify 播放器）'],ja:['レースBGM','レースBGM（Spotifyプレーヤー）'],en:['Race BGM','Race BGM (Spotify player)']};
            await __setLinks([{type:'music',url:'https://open.spotify.com/track/'+__SP.track}]); await __open(); const first=__frame();
            for(const l of ['zh','ja','en']){ setLang(l); await __wait(150); const f=__frame(), cap=__bgm()&&__bgm().querySelector('.dh-bgm-cap').textContent.trim();
              if(cap!==want[l][0]) bad.push(l+' caption '+cap); if(!f||f.title!==want[l][1]) bad.push(l+' title '+(f&&f.title));
              if(f!==first) bad.push(l+' reloaded'); }
            setLang('zh'); await __wait(100);
            if(bad.length) console.log('v48: lang',bad.join(' | ')); return bad.length===0; }""")
        # 深色模式用 Spotify 的深色款（theme=0），淺色不帶；切換時跟著換
        c['player_theme_follows_app'] = self.ev(pg, r"""async()=>{ const bad=[];
            await __setLinks([{type:'music',url:'https://open.spotify.com/track/'+__SP.track}]); await __open();
            const light=__frame().src; applyTheme('dark'); await __wait(150); const dark=__frame().src; applyTheme('light'); await __wait(150); const back=__frame().src;
            if(light.includes('theme=')) bad.push('light '+light); if(!dark.includes('theme=0')) bad.push('dark '+dark); if(back.includes('theme=')) bad.push('back '+back);
            if(bad.length) console.log('v48: theme',bad.join(' | ')); return bad.length===0; }""")
        # ================= 改別的欄位，播放器不重新載入 =================
        self.ev(pg, r"""async()=>{ await __setLinks([{type:'music',url:'https://open.spotify.com/track/'+__SP.track}]); await __open(); await __wait(200); }""")
        n0 = len(self.embeds)
        kept = self.ev(pg, r"""async()=>{ const bad=[], f0=__frame(); if(!f0) return false;   // 沒有播放器就不算「沒被換掉」
            // 只重畫頁首的欄位（抽屜裡改起跑時間）、整頁重畫的欄位（改名字會帶出系列，整頁重畫）、直接整頁重畫
            openDrawer('schedule'); await __wait(250); await __setField('f-schedule-startTime','06:15');
            if(__frame()!==f0) bad.push('header redraw');
            closeDrawer(); await __wait(150); openDrawer('basicInfo'); await __wait(250);
            await __setField('f-name','2026 阿里山森林越野賽'); if(__frame()!==f0) bad.push('name change');
            closeDrawer(); await __wait(150); renderDetail(); await __wait(150); if(__frame()!==f0) bad.push('renderDetail');
            const keeper=document.getElementById('bgm-keeper'); if(keeper&&keeper.children.length) bad.push('left in keeper');
            if(bad.length) console.log('v48: keep',bad.join(' | ')); return bad.length===0; }""")
        c['editing_other_fields_keeps_player_loaded'] = bool(kept) and len(self.embeds) == n0
        # 不支援 moveBefore 的瀏覽器（Safari）：重新載入，但播放器照樣在、暫存處沒有留下東西
        n1 = len(self.embeds)
        c['without_moveBefore_player_reloads_cleanly'] = self.ev(pg, r"""async()=>{ const f0=__frame(), mb=Element.prototype.moveBefore; delete Element.prototype.moveBefore;
            try{ updateDetailHeaderBits(); await __wait(200); renderDetail(); await __wait(200); const f1=__frame(), keeper=document.getElementById('bgm-keeper');
              return !!f1&&f1!==f0&&!(keeper&&keeper.children.length); }
            finally{ Element.prototype.moveBefore=mb; } }""") and len(self.embeds) == n1 + 2
        # ================= 在抽屜裡改、清掉、新增 =================
        c['changing_or_clearing_bgm_link_updates_header'] = self.ev(pg, r"""async()=>{ const S=__SP, bad=[];
            await __setLinks([{type:'music',url:'https://open.spotify.com/track/'+S.track}]); await __open(); openDrawer('mediaLinks'); await __wait(250);
            await __setField('f-mediaLinks-0-url','https://open.spotify.com/album/'+S.album);
            if(!__frame()||!__frame().src.includes('/album/'+S.album)) bad.push('not updated '+(__frame()&&__frame().src));
            await __setField('f-mediaLinks-0-url','');
            if(__bgm()) bad.push('still shown after clearing');
            closeDrawer(); await __wait(120);
            // 兩筆 Spotify：把「賽事 BGM」那筆改成「其他」，頁首換成第一筆，相簿也跟著換（不重複、不漏）
            await __setLinks([{type:'other',url:'https://open.spotify.com/track/'+S.track},{type:'music',url:'https://open.spotify.com/track/'+S.track2}]); await __open();
            openDrawer('mediaLinks'); await __wait(250); await __setField('f-mediaLinks-1-type','other'); closeDrawer(); await __wait(150);
            const hrefs=[...document.querySelectorAll('#section-post .media-gallery-card')].map(a=>a.href);
            if(!__frame()||!__frame().src.includes(S.track+'?')) bad.push('header after type change '+(__frame()&&__frame().src));
            if(hrefs.some(x=>x.includes(S.track+''))&&!hrefs.some(x=>x.includes(S.track2))) bad.push('gallery stale '+hrefs.join(','));
            if(bad.length) console.log('v48: edit',bad.join(' | ')); return bad.length===0; }""")
        # 新增一筆、填 Spotify 網址：類型還是預設的「其他」就自動改成「賽事 BGM」（有提示動畫）；
        # 不是音樂的網址、使用者自己選了別的類型，都不動
        c['typing_music_url_sets_type_to_bgm'] = self.ev(pg, r"""async()=>{ const S=__SP, bad=[]; const r=await __setLinks([]); await __open();
            openDrawer('mediaLinks'); await __wait(250);
            const add=async()=>{ drawerEl.querySelector('[data-action="add-item"][data-list="mediaLinks"]').click(); await __wait(250); return r.mediaLinks.length-1; };
            let n=await add(); await __setField('f-mediaLinks-'+n+'-url','https://open.spotify.com/intl-ja/playlist/'+S.playlist+'?si=z');
            const sel=document.getElementById('f-mediaLinks-'+n+'-type');
            if(r.mediaLinks[n].type!=='music'||!sel||sel.value!=='music') bad.push('type '+r.mediaLinks[n].type);
            if(!sel||!sel.closest('.field-smart-filled')) bad.push('no highlight');
            if(!__frame()) bad.push('no player');
            n=await add(); await __setField('f-mediaLinks-'+n+'-url','https://results.example.org/2026');
            if(r.mediaLinks[n].type!=='other') bad.push('non-music changed '+r.mediaLinks[n].type);
            n=await add(); await __setField('f-mediaLinks-'+n+'-type','photo_album'); await __setField('f-mediaLinks-'+n+'-url','https://open.spotify.com/track/'+S.track);
            if(r.mediaLinks[n].type!=='photo_album') bad.push('user choice overridden '+r.mediaLinks[n].type);
            closeDrawer(); await __wait(120);
            if(bad.length) console.log('v48: smart',bad.join(' | ')); return bad.length===0; }""")
        # ================= 組不出播放器的：放連結 =================
        c['short_link_shows_open_link_with_hint'] = self.ev(pg, r"""async()=>{ const bad=[];
            await __setLinks([{type:'music',url:'https://spotify.link/AbCdEf1234'}]); await __open();
            const a=__bgm()&&__bgm().querySelector('a.dh-bgm-link');
            if(__frame()) bad.push('player');
            if(!a||a.getAttribute('href')!=='https://spotify.link/AbCdEf1234'||a.target!=='_blank'||!/noopener/.test(a.rel)) bad.push('link');
            if(!a||!a.textContent.includes('在 Spotify 開啟')||!a.textContent.includes('短網址')) bad.push('zh '+(a&&a.textContent.trim()));
            setLang('en'); await __wait(150); const a2=__bgm().querySelector('a.dh-bgm-link');
            if(!a2.textContent.includes('Open in Spotify')||!a2.textContent.includes('Short links')||__cjk.test(a2.textContent)) bad.push('en '+a2.textContent.trim());
            setLang('zh'); await __wait(100);
            if(bad.length) console.log('v48: short',bad.join(' | ')); return bad.length===0; }""")
        c['other_music_services_show_open_link'] = self.ev(pg, r"""async()=>{ const bad=[];
            const cases=[['https://music.apple.com/tw/album/run/1440841363','Apple Music'],['https://music.youtube.com/watch?v=abc123','YouTube Music'],
              ['https://www.kkbox.com/tw/tc/song/abc','KKBOX'],['https://music.example.org/song/1','music.example.org']];
            for(const [url,name] of cases){ await __setLinks([{type:'music',url}]); await __open(); const a=__bgm()&&__bgm().querySelector('a.dh-bgm-link');
              if(__frame()||!a||a.getAttribute('href')!==url||!a.textContent.includes('在 '+name+' 開啟')) bad.push(name+' '+(a&&a.textContent.trim())); }
            if(bad.length) console.log('v48: services',bad.join(' | ')); return bad.length===0; }""")
        # 離線：放連結、寫明連上網路就有播放器；連上網路自己換回播放器
        self.ev(pg, r"""async()=>{ await __setLinks([{type:'music',url:'https://open.spotify.com/intl-ja/track/'+__SP.track+'?si=q'}]); }""")
        # 已經在播的時候斷線：改別的欄位，播放器留著（緩衝好的還能播），不換成連結
        self.ev(pg, r"""async()=>{ await __open(); await __wait(200); window.__f0=__frame(); }""")
        pg.context.set_offline(True)
        c['going_offline_keeps_loaded_player'] = self.ev(pg, r"""async()=>{ await __wait(100); updateDetailHeaderBits(); await __wait(150);
            const ok=!!__f0&&__frame()===__f0&&__bgm().dataset.bgmState==='player'; if(!ok) console.log('v48: offline keep',navigator.onLine); return ok; }""")
        # 離線時打開（新的播放器）：放連結
        self.ev(pg, r"""async()=>{ goBackFromDetail&&goBackFromDetail(); await __wait(200); }""")
        c['offline_shows_link_instead_of_player'] = self.ev(pg, r"""async()=>{ await __wait(100); await __open(); const b=__bgm(), a=b&&b.querySelector('a.dh-bgm-link');
            const ok=!!b&&b.dataset.bgmState==='offline'&&!__frame()&&!!a&&a.getAttribute('href')==='https://open.spotify.com/track/'+__SP.track&&b.textContent.includes('離線中');
            if(!ok) console.log('v48: offline',navigator.onLine,b&&b.outerHTML.slice(0,200)); return ok; }""")
        pg.context.set_offline(False)
        c['back_online_brings_player_back'] = self.ev(pg, r"""async()=>{ await __wait(400); const ok=!!__frame()&&__bgm().dataset.bgmState==='player';
            if(!ok) console.log('v48: online',navigator.onLine,__bgm()&&__bgm().dataset.bgmState); return ok; }""")
        # ================= 貼上 =================
        c['url_classifier_files_music_sources_as_bgm'] = self.ev(pg, r"""()=>{ const got=k=>{ const r=classifyPastedUrl(k); return r?r.type:null; };
            const ok=got('https://open.spotify.com/track/'+__SP.track)==='music' && got('https://spotify.link/x1')==='music'
              && got('https://music.apple.com/tw/album/a/1')==='music' && got('https://music.youtube.com/watch?v=a')==='music'
              && got('https://www.kkbox.com/tw/tc/song/a')==='music'
              && got('https://www.youtube.com/watch?v=a')==='other'                 // 一般 YouTube 照舊
              && got('https://developer.spotify.com/documentation/embeds')!=='music' // 說明文件不是歌
              && got('spotify:track:'+__SP.track)==='music' && classifyPastedUrl('spotify:track:short')===null;
            if(!ok) console.log('v48: classify'); return ok; }""")
        # 在賽事頁貼上 Spotify 連結：確認視窗預設「賽事 BGM」、說明播放器會出現在哪；存了之後頁首就有播放器。
        # 電腦版的 spotify: URI 換成網址；短網址先講清楚只會是連結
        c['paste_spotify_link_saved_as_bgm_player'] = self.ev(pg, r"""async()=>{ const S=__SP, bad=[]; await __setLinks([]); await __open();
            let el=await __pasteText('https://open.spotify.com/intl-ja/track/'+S.track+'?si=abc');
            if(el.hidden||pasteNoteState.kind!=='url') bad.push('modal');
            if(el.querySelector('[data-paste-url-field="type"]').value!=='music') bad.push('type '+el.querySelector('[data-paste-url-field="type"]').value);
            const hint=el.querySelector('.paste-url-bgm'); if(!hint||!hint.textContent.includes('賽事名稱下面')) bad.push('hint');
            el.querySelector('[data-action="confirm-paste-url"]').click(); await __wait(450);
            const ml=__bgmRace().mediaLinks; if(ml.length!==1||ml[0].type!=='music') bad.push('saved '+JSON.stringify(ml));
            if(!__frame()||!__frame().src.includes('/track/'+S.track)) bad.push('no player after paste');
            el=await __pasteText('spotify:album:'+S.album);
            if(el.hidden||!el.querySelector('.paste-url-preview').textContent.includes('https://open.spotify.com/album/'+S.album)) bad.push('uri');
            el.querySelector('[data-action="close-paste-note"]').click(); await __wait(120);
            el=await __pasteText('https://spotify.link/AbCdEf1234'); const h2=el.querySelector('.paste-url-bgm');
            if(!h2||!h2.textContent.includes('短網址')) bad.push('short hint');
            el.querySelector('[data-action="close-paste-note"]').click(); await __wait(120);
            if(bad.length) console.log('v48: paste',bad.join(' | ')); return bad.length===0; }""")
        # ================= 其他 =================
        c['media_type_option_translated'] = self.ev(pg, r"""async()=>{ const bad=[], want={zh:'賽事 BGM',ja:'レースBGM',en:'Race BGM'};
            await __setLinks([{type:'music',url:'https://open.spotify.com/track/'+__SP.track}]); await __open();
            for(const l of ['zh','ja','en']){ setLang(l); await __wait(120); openDrawer('mediaLinks'); await __wait(220);
              const sel=document.getElementById('f-mediaLinks-0-type'), o=sel&&sel.querySelector('option[value="music"]');
              if(!o||o.textContent.trim()!==want[l]||sel.value!=='music') bad.push(l+' '+(o&&o.textContent));
              closeDrawer(); await __wait(120); }
            setLang('zh'); await __wait(100);
            if(bad.length) console.log('v48: option',bad.join(' | ')); return bad.length===0; }""")
        c['caption_and_link_text_contrast_light_dark'] = self.ev(pg, r"""async()=>{ const bad=[];
            // 播放器那一款只有小字；短網址那一款小字＋連結的兩行。少了哪一個也算失敗
            for(const [v,sels] of [[[{type:'music',url:'https://open.spotify.com/track/'+__SP.track,notes:'終點那首'}],['.dh-bgm-cap span']],
                                   [[{type:'music',url:'https://spotify.link/AbCdEf1234'}],['.dh-bgm-cap span','.dh-bgm-link-main','.dh-bgm-link-sub']]]){
              await __setLinks(v); await __open();
              for(const th of ['light','dark']){ applyTheme(th); await __wait(120);
                sels.forEach(s=>{ const e=document.querySelector('.detail-header '+s); if(!e){ bad.push(th+' missing '+s); return; }
                  const cr=__textCr(e); if(cr<4.5) bad.push(th+' '+s+' '+cr.toFixed(2)); }); } }
            applyTheme('light'); await __wait(80);
            if(bad.length) console.log('v48: contrast',bad.join(' | ')); return bad.length===0; }""")
        c['simple_mode_also_shows_player'] = self.ev(pg, r"""async()=>{
            await __setLinks([{type:'music',url:'https://open.spotify.com/track/'+__SP.track}]); setUiMode('simple'); await __wait(150); await __open();
            const ok=isSimpleMode()&&!!__frame(); setUiMode('full'); await __wait(150); return ok; }""")
        # 比完的賽事：播放器在頁首（成績總覽在頁首下面），不是在賽後紀錄裡
        c['finished_race_player_in_header_above_results'] = self.ev(pg, r"""async()=>{ const r=state.races.find(x=>x.id==='example-sunmoonlake-half');
            r.status='completed'; r.schedule.raceDate='2026-09-20'; r.results.chipTimeSeconds=5400; r.results.gunTimeSeconds=5460;
            await __setLinks([{type:'music',url:'https://open.spotify.com/track/'+__SP.track}],r); await __open(r);
            const h=document.querySelector('.detail-header'), hero=document.querySelector('.hero-results');
            const ok=!!__frame()&&h.contains(__frame())&&!document.querySelector('#section-post iframe')&&(!hero||!!(h.compareDocumentPosition(hero)&Node.DOCUMENT_POSITION_FOLLOWING));
            if(!ok) console.log('v48: finished',!!__frame(),!!hero); return ok; }""")
        # 公開分享頁的快照是白名單：BGM 這次沒有加進去
        c['public_snapshot_leaves_bgm_out'] = self.ev(pg, r"""async()=>{ const r=await __setLinks([{type:'music',url:'https://open.spotify.com/track/'+__SP.track}]);
            const snap=JSON.stringify(await buildPublicSnapshot(r)); return !snap.includes(__SP.track)&&!snap.includes('mediaLinks'); }""")
        c['help_mentions_bgm_three_languages'] = self.ev(pg, r"""async()=>{ const bad=[], key={zh:'賽事 BGM',ja:'レースBGM',en:'Race BGM'};
            for(const l of ['zh','ja','en']){ setLang(l); await __wait(100); openHelpModal(); await __wait(200);
              const txt=document.getElementById('help-modal').innerText;
              if(!txt.includes(key[l])||!txt.includes('Spotify')||!txt.includes('30')||!txt.includes('intl-ja')) bad.push(l);
              document.querySelector('#help-modal [data-action="close-help"]').click(); await __wait(100); }
            setLang('zh'); await __wait(80); if(bad.length) console.log('v48: help',bad.join(' | ')); return bad.length===0; }""")
        # 版本號的檢查跟著最新的群組走，v4.9.0 起在 v49
        ctx.close()
        # ================= 手機各寬度 × 中日英 × 三種字級 =================
        FIT = r"""async()=>{ const S=__SP, bad=[];
            const variants=[[{type:'music',url:'https://open.spotify.com/track/'+S.track,notes:'終點線前最後一公里，腦中一直循環的那首歌 the final kilometre song'}],
                            [{type:'music',url:'https://spotify.link/AbCdEf1234'}]];
            for(const lang of ['zh','ja','en']){ setLang(lang); await __wait(80);
              for(const fs of ['small','medium','large']){ applyFontScale(fs);
                for(const v of variants){ await __setLinks(v); await __open(); window.scrollTo(0,0); await __wait(60);
                  const h=document.querySelector('.detail-header'), b=__bgm(), tag=lang+' '+fs+' '+(v[0].url.includes('spotify.link')?'short':'player');
                  if(!b){ bad.push(tag+' missing'); continue; }
                  const hr=h.getBoundingClientRect(), br=b.getBoundingClientRect();
                  if(br.left<hr.left-0.5||br.right>hr.right+0.5) bad.push(tag+' outside header');
                  b.querySelectorAll('.dh-bgm-cap,.dh-bgm-cap span,.dh-bgm-link,.dh-bgm-link-main,.dh-bgm-link-sub').forEach(e=>{ if(e.scrollWidth>e.clientWidth+1) bad.push(tag+' overflow '+e.className); });
                  if(document.documentElement.scrollWidth>innerWidth) bad.push(tag+' hscroll'); } } }
            setLang('zh'); applyFontScale('medium');
            if(bad.length) console.log('v48: fit '+innerWidth,bad.slice(0,8).join(' | ')); return bad.length===0; }"""
        STEPPER = r"""async()=>{ const bad=[];
            for(const lang of ['en','ja','zh']){ setLang(lang); await __wait(60);
              for(const fs of ['small','medium','large']){ applyFontScale(fs);
                for(const st of ['considering','lottery_pending','registered']){ const r=__bgmRace(); r.status=st; await __setLinks([]); await __open(); await __wait(40);
                  const tr=document.querySelector('.detail-header .lc-track'), tag=lang+' '+fs+' '+st; if(!tr){ bad.push(tag+' no track'); continue; }
                  const t=tr.getBoundingClientRect(), labs=[...tr.querySelectorAll('.lc-node-label')].map(l=>{ const g=document.createRange(); g.selectNodeContents(l); return [...g.getClientRects()]; });
                  if(document.documentElement.scrollWidth>innerWidth) bad.push(tag+' hscroll');
                  labs.flat().forEach(q=>{ if(q.left<t.left-0.5||q.right>t.right+0.5) bad.push(tag+' label outside'); });
                  for(let i=0;i<labs.length-1;i++){ if(Math.max(...labs[i].map(q=>q.right))>Math.min(...labs[i+1].map(q=>q.left))-2) bad.push(tag+' labels touch '+i); }
                  tr.querySelectorAll('.lc-node').forEach(n=>{ if(n.getBoundingClientRect().width<43.5) bad.push(tag+' node <44px'); }); } } }
            __bgmRace().status='registered'; await persist(); setLang('zh'); applyFontScale('medium');
            if(bad.length) console.log('v48: stepper '+innerWidth,bad.slice(0,8).join(' | ')); return bad.length===0; }"""
        for w in (320, 360, 390):
            fctx, fp = self._bgm_ctx(browser, viewport={'width': w, 'height': 844}, touch=True)
            c[f'fits_{w}_all_languages_font_sizes'] = self.ev(fp, FIT)
            # 賽事頁頁首的狀態條：英文加大字級在 320px 原本比軌道寬、整頁左右滑（v4.8.0 量到的舊問題）
            if w == 320:
                c['status_track_fits_320_every_language_font_size'] = self.ev(fp, STEPPER)
            fctx.close()
        # 電腦：不拉滿整欄（520px 以內），跟日期地點那一行左邊對齊
        lctx, lp = self._bgm_ctx(browser, viewport={'width': 1280, 'height': 900})
        c['laptop_player_aligned_not_full_width'] = self.ev(lp, r"""async()=>{
            await __setLinks([{type:'music',url:'https://open.spotify.com/track/'+__SP.track}]); await __open();
            const fr=__frame().getBoundingClientRect(), mr=document.querySelector('.detail-header .dh-meta').getBoundingClientRect();
            const ok=fr.width<=520.5&&fr.width>=300&&Math.abs(fr.left-mr.left)<=1; if(!ok) console.log('v48: laptop',fr.width,fr.left,mr.left); return ok; }""")
        lctx.close()


# ---------------------------------------------------------------------------
# v4.9.0：隱私權政策與使用條款
# ---------------------------------------------------------------------------
PRIVACY_PATH = os.path.join(os.path.dirname(os.path.abspath(APP)), 'privacy', 'index.html')
PRIVACY_URL = 'file://' + PRIVACY_PATH

# App 會連到的外部服務（字型、程式庫、地圖、天氣、播放器、雲端）。index.html 多了一個這裡沒有的網域，
# 測試就會失敗——提醒先把它寫進隱私權政策第 2 節，再加到這張表
PRIVACY_SERVICE_OF_HOST = (
    ('fonts.googleapis.com', 'Google Fonts'), ('fonts.gstatic.com', 'Google Fonts'),
    ('cdn.jsdelivr.net', 'jsDelivr'), ('unpkg.com', 'unpkg'),
    ('www.gstatic.com', 'Firebase'), ('firestore.googleapis.com', 'Firebase'),
    ('tile.openstreetmap.org', 'OpenStreetMap'), ('tile.opentopomap.org', 'OpenTopoMap'),
    ('open-meteo.com', 'Open-Meteo'), ('open.spotify.com', 'Spotify'),
)


def app_request_hosts(html):
    """index.html 自己會發出請求的網域。只算載入程式、樣式、字型、圖磚、API、播放器這些；
    使用者點了才離開的連結（官網、名言出處、Google 表單）不算，那些不是我們送出的資料。"""
    pats = [r'<script src="(https://[^"]+)"', r'<link href="(https://[^"]+)"',
            r"(?:script\.src|cssLink\.href)='(https://[^']+)'", r"const XLSX_SRC='(https://[^']+)'",
            r'from "(https://[^"]+)"', r"L\.tileLayer\(\s*'(https://[^']+)'",
            r"fetch\('(https://[^']+)'", r"const url=`(https://[^`$]+)", r"`(https://open\.spotify\.com/embed/)"]
    hosts = set()
    for pat in pats:
        for u in re.findall(pat, html):
            hosts.add(re.sub(r'^https://', '', u).split('/')[0].lower())
    return hosts


PRIVACY_PAGE_JS = r"""
window.__visible=()=>document.body.innerText;
window.__shown=sel=>[...document.querySelectorAll(sel)].filter(e=>getComputedStyle(e).display!=='none'&&e.getClientRects().length);
window.__pick=async l=>{ document.querySelector('[data-set-lang="'+l+'"]').click(); await new Promise(r=>setTimeout(r,30)); };
"""


class V49Privacy(V48RaceBgm):
    """v4.9.0：隱私權政策與使用條款。獨立頁面 privacy/：中日英、沿用 App 的深淺色與字級、不載入任何外部資源、
    內容涵蓋 Spotify 嵌入條款 V.5–V.6 要求的每一項，也跟程式實際連到的服務、保存天數對得上。App 裡頭像選單、
    登入按鈕下、Spotify 播放器下、使用說明、公開連結頁都連過去，網址帶目前的語言；Service Worker 不再把
    同一個網站底下的其他頁面存成 App 的離線快取。"""

    ECHO = ('v49:',)

    def _priv(self, browser, url=PRIVACY_URL, viewport=None, locale='en-US', color_scheme='light', init=None):
        ctx = browser.new_context(viewport=viewport or {'width': 390, 'height': 844}, locale=locale,
                                  color_scheme=color_scheme, is_mobile=True, has_touch=True)
        if init:
            ctx.add_init_script(init)
        pg = ctx.new_page()
        pg.on('pageerror', lambda e: self.errors.append('privacy: ' + str(e)))
        pg.on('console', self._echo)
        self.priv_requests = []
        pg.on('request', lambda r: self.priv_requests.append(r.url))
        pg.goto(url)
        pg.wait_for_timeout(250)
        pg.add_script_tag(content=FIELD_FRAME_JS + WALL_SEED_JS + PRIVACY_PAGE_JS)
        return ctx, pg

    def _sw_check(self, browser):
        """開過 privacy/ 之後，離線開 App 還是 App（v4.8.0 以前會變成政策頁）。
        SW 不能在 file:// 註冊：起一個本機伺服器，「離線」就是把伺服器關掉——Playwright 的
        set_offline 攔不到 Service Worker 自己送出的請求，用它測不出這個問題。"""
        import http.server, socketserver, threading, functools
        directory = os.path.dirname(os.path.abspath(APP))

        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *a, **k):
                pass
        socketserver.TCPServer.allow_reuse_address = True
        srv = socketserver.TCPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=directory))
        base = f'http://127.0.0.1:{srv.server_address[1]}/'
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        ok = False
        ctx = full_mode_context(browser, viewport={'width': 390, 'height': 844}, service_workers='allow')
        try:
            pg = ctx.new_page()
            pg.on('pageerror', lambda e: self.errors.append('sw: ' + str(e)))
            pg.goto(base + 'index.html')
            pg.wait_for_timeout(800)
            pg.evaluate("async()=>{ await navigator.serviceWorker.ready; await new Promise(r=>setTimeout(r,1500)); }")
            pg.reload()
            pg.wait_for_timeout(800)
            controlled = pg.evaluate('!!navigator.serviceWorker.controller')
            pg.goto(base + 'privacy/?lang=en')
            pg.wait_for_timeout(500)
            on_privacy = pg.title().startswith('Privacy Policy')
            cached_app = pg.evaluate(r"""async()=>{ const key=new URL('/index.html',location.origin).href;
                for(const n of await caches.keys()){ const r=await (await caches.open(n)).match(key);
                  if(r) return /<title>賽事紀錄<\/title>/.test(await r.text()); } return null; }""")
            srv.shutdown()
            srv.server_close()
            srv = None
            pg.goto(base + 'index.html')
            pg.wait_for_timeout(1500)
            offline_app = pg.evaluate("()=>typeof APP_VERSION!=='undefined'&&!!document.getElementById('app-version')")
            ok = bool(controlled and on_privacy and cached_app and offline_app)
            if not ok:
                print('    v49: sw', controlled, on_privacy, cached_app, offline_app)
        except Exception as exc:                      # noqa: BLE001
            print('    v49: sw ⚠', str(exc).split('\n')[0][:200])
        finally:
            ctx.close()
            if srv:
                srv.shutdown()
                srv.server_close()
        return ok

    def body(self, page):
        c = self.checks
        browser = page.context.browser
        app_html = open(APP, encoding='utf-8').read()
        priv = open(PRIVACY_PATH, encoding='utf-8').read() if os.path.exists(PRIVACY_PATH) else ''
        # ================= 政策頁本身 =================
        c['privacy_page_deployed_next_to_app'] = bool(priv)
        # 講隱私權的頁面本身不再把訪客送去第三方：沒有外部字型、樣式、程式、圖片（<a> 連結、canonical 不算）
        c['privacy_page_source_has_no_external_resources'] = bool(priv) and not re.search(
            r'<(?:script|img|iframe|link)\b[^>]*\b(?:src|href)="https?://(?!ai-sub3\.github\.io/Race-Day/privacy/")|@import|url\(\s*["\']?https?:', priv)
        # 聯絡管道：App 裡的意見回饋表單，同一個網址（表單換了，兩邊要一起換）
        fb = re.search(r"const FEEDBACK_FORM_URL='([^']+)'", app_html)
        fb_links = re.findall(r'class="js-feedback" href="([^"]+)"', priv)
        c['privacy_contact_is_the_app_feedback_form'] = bool(fb) and len(fb_links) >= 9 and all(u == fb.group(1) for u in fb_links)
        names, unknown = [], []
        for h in sorted(app_request_hosts(app_html)):
            n = next((name for suf, name in PRIVACY_SERVICE_OF_HOST if h == suf or h.endswith('.' + suf)), None)
            (names.append(n) if n else unknown.append(h))
        if unknown:
            print('    v49: 政策裡沒寫到的外部網域', unknown)
        trash = re.search(r'const TRASH_RETENTION_DAYS=(\d+)', app_html)
        cover = re.search(r'function processCoverImage[\s\S]{0,900}?const maxDim=(\d+)', app_html)

        ctx, pg = self._priv(browser, PRIVACY_URL + '?lang=zh')
        c['privacy_page_requests_nothing_external'] = bool(self.priv_requests) and all(u.startswith('file://') for u in self.priv_requests)
        if not c['privacy_page_requests_nothing_external']:
            print('    v49: external', [u for u in self.priv_requests if not u.startswith('file://')][:5])
        # 三種語言一一對應：每一節都有中日英三份，小標、條列、服務、連結的數目一樣（少翻一段就抓得到）
        c['privacy_three_languages_same_structure'] = self.ev(pg, r"""()=>{ const bad=[];
            for(const id of ['summary','privacy','cookies','terms','contact']){ const sec=document.getElementById(id);
              if(!sec){ bad.push('no '+id); continue; }
              const blocks=[...sec.children].filter(e=>e.classList.contains('l10n'));
              const langs=blocks.map(b=>b.getAttribute('lang')).sort().join(',');
              if(langs!=='en,ja,zh-Hant') bad.push(id+' langs '+langs);
              const sig=b=>['h3','li','dt','a'].map(t=>b.querySelectorAll(t).length).join('/');
              if(new Set(blocks.map(sig)).size!==1) bad.push(id+' '+blocks.map(b=>b.lang+':'+sig(b)).join(' ')); }
            if(bad.length) console.log('v49: structure',bad.join(' | ')); return bad.length===0; }""")
        # Spotify 嵌入條款 V.5–V.6 要的每一項，三種語言都寫到：依政策處理、蒐集什麼、怎麼用與分享、
        # 自己有沒有用 Cookie、允許第三方設 Cookie 蒐集瀏覽活動、怎麼管理 Cookie；還有使用者條款
        c['privacy_covers_spotify_widget_terms_each_language'] = self.ev(pg, r"""async()=>{ const bad=[];
            const need={zh:['依照本政策','我們蒐集的資料','使用目的','誰會接觸到你的資料','本服務自己不設定 Cookie','我們允許下列第三方在你的瀏覽器設定 Cookie','瀏覽活動','管理 Cookie 的方式','Google Analytics','使用條款'],
              ja:['本ポリシーに従います','収集するデータ','利用目的','データにアクセスできる人','Cookie を設定しません','第三者があなたのブラウザに Cookie を設定','閲覧活動','Cookie の管理方法','Google アナリティクス','利用規約'],
              en:['in accordance with this policy','Data we collect','How we use data','Who can access your data',"doesn't set cookies",'We allow the third parties below to place cookies','browsing activity','Managing cookies','Google Analytics','Terms of Use']};
            for(const l of ['zh','ja','en']){ await __pick(l); const txt=__visible(); need[l].forEach(k=>{ if(!txt.includes(k)) bad.push(l+' '+k); }); }
            if(bad.length) console.log('v49: widget terms',bad.join(' | ')); return bad.length===0; }""")
        # 跟程式對得上：App 會連到的每個外部服務都寫到（三種語言）；保存天數、封面縮小的像素跟程式一樣
        c['privacy_lists_every_service_the_app_calls'] = (not unknown) and bool(names) and self.ev(pg, r"""async(names)=>{ const bad=[];
            for(const l of ['zh','ja','en']){ await __pick(l); const txt=__visible(); names.forEach(n=>{ if(!txt.includes(n)) bad.push(l+' '+n); }); }
            if(bad.length) console.log('v49: services',bad.join(' | ')); return bad.length===0; }""", sorted(set(names)))
        c['privacy_numbers_match_app_code'] = bool(trash and cover) and self.ev(pg, r"""async(nums)=>{ const bad=[];
            for(const l of ['zh','ja','en']){ await __pick(l); const txt=__visible(); nums.forEach(n=>{ if(!txt.includes(n)) bad.push(l+' '+n); }); }
            if(bad.length) console.log('v49: numbers',bad.join(' | ')); return bad.length===0; }""", [trash.group(1), cover.group(1)] if trash and cover else [])
        # 切語言：只換這一頁，網址的 ?lang= 跟著改（#錨點留著），App 的語言設定不動
        c['privacy_switcher_changes_this_page_only'] = self.ev(pg, r"""async()=>{
            localStorage.setItem('lang-pref-v1','zh'); location.hash='#cookies'; await new Promise(r=>setTimeout(r,30));
            await __pick('en');
            const d=document.documentElement, pressed=[...document.querySelectorAll('[data-set-lang]')].map(b=>b.dataset.setLang+':'+b.getAttribute('aria-pressed')).join(',');
            const ok=d.dataset.lang==='en'&&d.lang==='en'&&/[?&]lang=en(&|$)/.test(location.search)&&!/lang=zh/.test(location.search)&&location.hash==='#cookies'
              &&pressed==='zh:false,ja:false,en:true'&&localStorage.getItem('lang-pref-v1')==='zh'&&document.title.startsWith('Privacy Policy')
              &&__shown('.l10n[lang="zh-Hant"]').length===0&&__shown('.l10n[lang="en"]').length>10;
            if(!ok) console.log('v49: switch',d.dataset.lang,location.search,location.hash,pressed,localStorage.getItem('lang-pref-v1'),document.title); return ok; }""")
        ctx.close()
        # 用哪種語言打開：網址的 ?lang=（App 的連結都會帶）→ App 存的語言 → 瀏覽器語言（中日以外用英文）
        lang_ok = []
        clear = "try{localStorage.removeItem('lang-pref-v1')}catch(e){}"
        for url, locale, init, want in (
                (PRIVACY_URL + '?lang=ja', 'en-US', None, 'ja'),
                (PRIVACY_URL + '?lang=en', 'zh-TW', None, 'en'),
                (PRIVACY_URL, 'en-US', "try{localStorage.setItem('lang-pref-v1','ja')}catch(e){}", 'ja'),
                (PRIVACY_URL, 'ja-JP', clear, 'ja'),
                (PRIVACY_URL, 'zh-TW', clear, 'zh'),
                (PRIVACY_URL, 'de-DE', clear, 'en'),
                (PRIVACY_URL + '?lang=xx', 'zh-TW', clear, 'zh')):
            lctx, lp = self._priv(browser, url, locale=locale, init=init)
            got = self.ev(lp, """()=>{ const d=document.documentElement, map={zh:'zh-Hant',ja:'ja',en:'en'};
                return [d.dataset.lang, d.lang, document.title, __shown('.l10n').every(e=>e.lang===map[d.dataset.lang])]; }""")
            ok = bool(got) and got[0] == want and got[1] == {'zh': 'zh-Hant', 'ja': 'ja', 'en': 'en'}[want] and got[3]
            if not ok:
                print('    v49: lang', url.split('/')[-1], locale, got)
            lang_ok.append(ok)
            lctx.close()
        c['privacy_language_from_link_then_app_then_browser'] = all(lang_ok)
        # 深淺色、字級沿用 App 的設定（App 選了淺色，系統深色也維持淺色）；沒設定就跟系統
        th_ok = []
        for scheme, init, want_theme, want_font, want_px in (
                ('light', "localStorage.setItem('theme-pref-v1','dark');localStorage.setItem('font-scale-v1','large');", 'dark', 'large', '18.4px'),
                ('dark', "localStorage.setItem('theme-pref-v1','light');", 'light', None, '16px'),
                ('dark', "localStorage.removeItem('theme-pref-v1');", 'dark', None, '16px'),
                ('light', "localStorage.setItem('font-scale-v1','small');", 'light', 'small', '14.4px')):
            tctx, tp = self._priv(browser, PRIVACY_URL + '?lang=zh', color_scheme=scheme, init='try{' + init + '}catch(e){}')
            got = self.ev(tp, """()=>[document.documentElement.dataset.theme, document.documentElement.dataset.font||null,
                getComputedStyle(document.body).backgroundColor, getComputedStyle(document.body).fontSize]""")
            bg = 'rgb(13, 16, 19)' if want_theme == 'dark' else 'rgb(230, 233, 230)'
            ok = bool(got) and got[0] == want_theme and got[1] == want_font and got[2] == bg and got[3] == want_px
            if not ok:
                print('    v49: theme', scheme, init, got)
            th_ok.append(ok)
            tctx.close()
        c['privacy_follows_app_theme_and_font_size'] = all(th_ok)
        for w in (320, 390):
            fctx, fp = self._priv(browser, PRIVACY_URL + '?lang=zh', viewport={'width': w, 'height': 760})
            c[f'privacy_fits_{w}_every_language_theme_font'] = self.ev(fp, r"""async()=>{ const bad=[], d=document.documentElement;
                for(const th of ['light','dark']) for(const fs of ['small',null,'large']) for(const l of ['zh','ja','en']){
                  d.dataset.theme=th; if(fs) d.dataset.font=fs; else delete d.dataset.font; await __pick(l);
                  const tag=l+' '+th+' '+(fs||'medium');
                  if(d.scrollWidth>d.clientWidth) bad.push(tag+' hscroll '+d.scrollWidth);
                  const br=document.querySelector('.brand').getBoundingClientRect(), lr=document.querySelector('.lang').getBoundingClientRect();
                  if(br.right>lr.left+0.5) bad.push(tag+' brand under switcher');
                  if(lr.right>d.clientWidth+0.5) bad.push(tag+' switcher off screen');
                  const vis=document.querySelector('.brand>span'); if(vis&&vis.getBoundingClientRect().width>1&&vis.scrollWidth>vis.clientWidth+1) bad.push(tag+' brand cut');
                  document.querySelectorAll('.lang button').forEach(b=>{ if(b.getBoundingClientRect().height<31.5) bad.push(tag+' small button'); });
                  document.querySelectorAll('.card').forEach(e=>{ if(e.scrollWidth>e.clientWidth+1) bad.push(tag+' card overflow '+e.id); }); }
                d.dataset.theme='light'; delete d.dataset.font;
                if(bad.length) console.log('v49: fit '+innerWidth,bad.slice(0,8).join(' | ')); return bad.length===0; }""")
            if w == 390:
                c['privacy_text_contrast_light_dark'] = self.ev(fp, r"""async()=>{ const bad=[], d=document.documentElement; await __pick('zh');
                  for(const th of ['light','dark']){ d.dataset.theme=th; await new Promise(r=>setTimeout(r,20));
                    ['h1 .l10n[lang="zh-Hant"]','.updated .l10n[lang="zh-Hant"]','#privacy p','#privacy .note','#cookies .svc dd','#cookies .refs a',
                     '#summary a','.toc a','.lang button[aria-pressed="true"]','.lang button[aria-pressed="false"]','footer a','footer .wrap>span'].forEach(s=>{
                      const e=document.querySelector(s); if(!e){ bad.push(th+' missing '+s); return; }
                      const cr=__textCr(e); if(cr<4.5) bad.push(th+' '+s+' '+cr.toFixed(2)); }); }
                  d.dataset.theme='light';
                  if(bad.length) console.log('v49: contrast',bad.join(' | ')); return bad.length===0; }""")
                # 播放器下那行說明連到 #cookies：跳過去不會被固定在上面的頁首蓋住
                c['privacy_anchor_not_hidden_under_header'] = self.ev(fp, r"""async()=>{
                  location.hash=''; window.scrollTo(0,0); await new Promise(r=>setTimeout(r,30));
                  location.hash='#cookies'; await new Promise(r=>setTimeout(r,150));
                  const top=document.getElementById('cookies').getBoundingClientRect().top, hb=document.querySelector('.top').getBoundingClientRect().bottom;
                  const ok=top>=hb-1&&top<=hb+40; if(!ok) console.log('v49: anchor',top,hb); return ok; }""")
            fctx.close()

        # ================= App 裡的入口 =================
        ctx, pg = self._bgm_ctx(browser, viewport={'width': 390, 'height': 844}, touch=True)
        c['menu_link_below_feedback_follows_language'] = self.ev(pg, r"""async()=>{ const bad=[], want={zh:'隱私權政策與使用條款',ja:'プライバシーポリシーと利用規約',en:'Privacy Policy & Terms'};
            for(const l of ['zh','ja','en','zh']){ setLang(l); await __wait(60); const a=document.getElementById('btn-privacy');
              if(!a||a.tagName!=='A'){ bad.push('not a link'); break; }
              if(a.getAttribute('href')!=='privacy/?lang='+l) bad.push(l+' href '+a.getAttribute('href'));
              if(a.textContent.trim()!==want[l]) bad.push(l+' text '+a.textContent.trim());
              if(a.target!=='_blank'||!/noopener/.test(a.rel)) bad.push('target/rel');
              if(!a.closest('#account-menu-panel')) bad.push('not in menu'); }
            const fbk=document.getElementById('btn-feedback'), a=document.getElementById('btn-privacy');
            if(!a||!(fbk.compareDocumentPosition(a)&Node.DOCUMENT_POSITION_FOLLOWING)) bad.push('not below feedback');
            if(bad.length) console.log('v49: menu',bad.join(' | ')); return bad.length===0; }""")
        # 登入之前看得到同意的是什麼：一般的登入按鈕、有資料時的提醒卡，兩種下面都有那行小字；登入後就不再顯示
        c['sign_in_note_under_both_sign_in_entries'] = self.ev(pg, r"""async()=>{ const bad=[], prev={cloud:window.__cloud,user:state.user,known:authKnown};
            window.__cloud=Object.assign({},prev.cloud||{},{enabled:true}); state.user=null;
            const look=tag=>{ renderAuthArea(); const area=document.getElementById('auth-area'), btn=area.querySelector('#btn-signin'), note=area.querySelector('.auth-legal');
              if(!btn){ bad.push(tag+' no sign-in button'); return; }
              if(!note){ bad.push(tag+' no note'); return; }
              if(!(btn.compareDocumentPosition(note)&Node.DOCUMENT_POSITION_FOLLOWING)) bad.push(tag+' note above button');
              const a=note.querySelector('a'); if(!a||a.getAttribute('href')!=='privacy/?lang=zh'||a.target!=='_blank') bad.push(tag+' link '+(a&&a.getAttribute('href'))); };
            authKnown=true; look('nudge'); if(!document.querySelector('#auth-area .backup-nudge')) bad.push('nudge not shown');
            authKnown=false; look('button');
            state.user={uid:'u1',displayName:'Aaron'}; renderAuthArea();
            if(document.querySelector('#auth-area .auth-legal')) bad.push('still shown when signed in');
            window.__cloud=prev.cloud; state.user=prev.user; authKnown=prev.known; renderAuthArea();
            if(bad.length) console.log('v49: signin',bad.join(' | ')); return bad.length===0; }""")
        c['sign_in_note_translated'] = self.ev(pg, r"""async()=>{ const bad=[], prev={cloud:window.__cloud,user:state.user,known:authKnown};
            window.__cloud=Object.assign({},prev.cloud||{},{enabled:true}); state.user=null; authKnown=false;
            const want={zh:'登入即表示你同意使用條款與隱私權政策。',ja:'ログインすると、利用規約とプライバシーポリシーに同意したものとみなされます。',en:'By signing in, you agree to the Terms of Use and Privacy Policy.'};
            for(const l of ['ja','en','zh']){ setLang(l); await __wait(60); const n=document.querySelector('#auth-area .auth-legal');
              if(!n||n.textContent.trim()!==want[l]) bad.push(l+' '+(n&&n.textContent.trim()));
              else if(n.querySelector('a').getAttribute('href')!=='privacy/?lang='+l) bad.push(l+' href'); }
            window.__cloud=prev.cloud; state.user=prev.user; authKnown=prev.known; renderAuthArea();
            if(bad.length) console.log('v49: signin lang',bad.join(' | ')); return bad.length===0; }""")
        # 播放器一載入 Spotify 就會設 Cookie：說明放在播放器正下方，連到政策的 Cookie 那一節
        c['player_has_cookie_note_linking_cookies_section'] = self.ev(pg, r"""async()=>{
            await __setLinks([{type:'music',url:'https://open.spotify.com/track/'+__SP.track}]); await __open(); await __wait(150);
            const box=__bgm(), f=__frame(), n=box&&box.querySelector('.dh-bgm-legal'), a=n&&n.querySelector('a');
            const ok=!!(box&&f&&n&&a)&&box.dataset.bgmState==='player'&&!!(f.compareDocumentPosition(n)&Node.DOCUMENT_POSITION_FOLLOWING)
              &&a.getAttribute('href')==='privacy/?lang=zh#cookies'&&a.target==='_blank'&&/noopener/.test(a.rel)
              &&n.textContent.includes('Spotify')&&n.textContent.includes('Cookie')&&box.querySelectorAll('.dh-bgm-legal').length===1;
            if(!ok) console.log('v49: note',box&&box.outerHTML.slice(0,300)); return ok; }""")
        # 播放器照 Spotify 給的樣子顯示（嵌入條款）：說明寫在外面、不蓋到播放器，播放器的高度、寬度不變
        c['cookie_note_outside_player_unaltered'] = self.ev(pg, r"""async()=>{
            await __setLinks([{type:'music',url:'https://open.spotify.com/track/'+__SP.track}]); await __open(); await __wait(150);
            const f=__frame(), b=__bgm(), n=b&&b.querySelector('.dh-bgm-legal'); if(!f||!n) return false;
            const fr=f.getBoundingClientRect(), nr=n.getBoundingClientRect(), br=b.getBoundingClientRect();
            const ok=n.parentElement===b&&nr.top>=fr.bottom-0.5&&Math.round(fr.height)===152&&Math.abs(fr.width-br.width)<=1;
            if(!ok) console.log('v49: unaltered',fr.height,fr.width,br.width,nr.top,fr.bottom); return ok; }""")
        # 只有真的載入播放器才需要說明：其他音樂平台、短網址、離線都只放連結，不會載入 Spotify；連上網路後播放器和說明一起回來
        no_note = self.ev(pg, r"""async()=>{ const bad=[];
            for(const url of ['https://music.apple.com/tw/album/run/1234567890','https://spotify.link/AbCdEf1234']){
              await __setLinks([{type:'music',url}]); await __open(); await __wait(120); const b=__bgm();
              if(!b||b.dataset.bgmState!=='link') bad.push('state '+url+' '+(b&&b.dataset.bgmState));
              else if(b.querySelector('.dh-bgm-legal')) bad.push('note on link card '+url); }
            await __setLinks([{type:'music',url:'https://open.spotify.com/track/'+__SP.track2}]);
            if(bad.length) console.log('v49: link cards',bad.join(' | ')); return bad.length===0; }""")
        ctx.set_offline(True)
        offline = self.ev(pg, r"""async()=>{ await __wait(100); await __open(); await __wait(150); const b=__bgm();
            const ok=!!b&&b.dataset.bgmState==='offline'&&!b.querySelector('.dh-bgm-legal'); if(!ok) console.log('v49: offline',b&&b.dataset.bgmState); return ok; }""")
        ctx.set_offline(False)
        back = self.ev(pg, r"""async()=>{ await __wait(300); const b=__bgm(); const ok=!!b&&b.dataset.bgmState==='player'&&!!b.querySelector('.dh-bgm-legal');
            if(!ok) console.log('v49: back online',b&&b.dataset.bgmState); return ok; }""")
        c['cookie_note_only_when_player_loads'] = bool(no_note and offline and back)
        # 改欄位、整頁重畫：說明還在、只有一行，播放器沒被重新載入（支援 moveBefore 的瀏覽器）
        c['cookie_note_survives_header_redraws'] = self.ev(pg, r"""async()=>{
            await __setLinks([{type:'music',url:'https://open.spotify.com/track/'+__SP.track}]); await __open(); await __wait(150);
            const before=__frame(); updateDetailHeaderBits(); await __wait(60); renderDetail(); await __wait(120);
            const b=__bgm(), n=b?b.querySelectorAll('.dh-bgm-legal'):[], f=__frame();
            const kept=typeof Element.prototype.moveBefore!=='function'||f===before;
            const ok=!!b&&n.length===1&&!!f&&!!(f.compareDocumentPosition(n[0])&Node.DOCUMENT_POSITION_FOLLOWING)&&kept;
            if(!ok) console.log('v49: redraw',n.length,!!f,kept); return ok; }""")
        c['cookie_note_translated'] = self.ev(pg, r"""async()=>{ const bad=[], want={zh:['播放器由 Spotify 提供','隱私權政策'],ja:['プレーヤーは Spotify が提供','プライバシーポリシー'],en:['This player is provided by Spotify','Privacy Policy']};
            await __setLinks([{type:'music',url:'https://open.spotify.com/track/'+__SP.track}]);
            for(const l of ['ja','en','zh']){ setLang(l); await __wait(80); await __open(); await __wait(120); const n=__bgm()&&__bgm().querySelector('.dh-bgm-legal'), a=n&&n.querySelector('a');
              if(!a||!n.textContent.includes(want[l][0])||a.textContent!==want[l][1]||a.getAttribute('href')!=='privacy/?lang='+l+'#cookies') bad.push(l+' '+(n&&n.textContent)); }
            if(bad.length) console.log('v49: note lang',bad.join(' | ')); return bad.length===0; }""")
        c['cookie_note_contrast_light_dark'] = self.ev(pg, r"""async()=>{ const bad=[];
            await __setLinks([{type:'music',url:'https://open.spotify.com/track/'+__SP.track}]); await __open();
            for(const th of ['light','dark']){ applyTheme(th); await __wait(150);
              for(const s of ['.dh-bgm-legal','.dh-bgm-legal a']){ const e=document.querySelector('.detail-header '+s); if(!e){ bad.push(th+' missing '+s); continue; }
                const cr=__textCr(e); if(cr<4.5) bad.push(th+' '+s+' '+cr.toFixed(2)); } }
            applyTheme('light'); await __wait(80);
            if(bad.length) console.log('v49: note contrast',bad.join(' | ')); return bad.length===0; }""")
        c['help_links_policy_three_languages'] = self.ev(pg, r"""async()=>{ const bad=[], want={zh:'隱私權政策與使用條款',ja:'プライバシーポリシーと利用規約',en:'Privacy Policy & Terms of Use'};
            for(const l of ['zh','ja','en']){ setLang(l); await __wait(80); openHelpModal(); await __wait(200);
              const a=[...document.querySelectorAll('#help-modal a')].find(x=>x.getAttribute('href')==='privacy/?lang='+l);
              if(!a||a.textContent.trim()!==want[l]||a.target!=='_blank'||!/noopener/.test(a.rel)) bad.push(l+' '+(a&&a.textContent));
              document.querySelector('#help-modal [data-action="close-help"]').click(); await __wait(100); }
            setLang('zh'); await __wait(60); if(bad.length) console.log('v49: help',bad.join(' | ')); return bad.length===0; }""")
        # 版本號的檢查跟著最新的群組走，v4.10.0 起在 v410
        # 公開連結頁（看的人多半沒有帳號）：頁尾也有政策的連結
        c['public_page_footer_links_policy'] = self.ev(pg, r"""async()=>{ setLang('en'); await __wait(60);
            renderPublicShareView({v:1,name:'Test',raceDate:'2026-03-01',startTime:'06:30',sportType:'trail_running',city:'Chiayi',country:'Taiwan',
              results:{chipTimeSeconds:16000,isPb:false,overallRank:null,ageGroupRank:null},route:{distanceKm:42,elevationGainM:2300,track:[]},performance:{avgHr:null},
              shoeName:null,fuel:[],coverThumb:null,photos:[],og:null});
            await __wait(60); const a=[...document.querySelectorAll('.pubview-foot a')].find(x=>x.getAttribute('href')==='privacy/?lang=en');
            const ok=!!a&&a.textContent==='Privacy Policy & Terms'&&a.target==='_blank';
            if(!ok) console.log('v49: pubview',(document.querySelector('.pubview-foot')||{}).innerHTML); return ok; }""")
        ctx.close()
        # 手機最窄的 320px：選單裡的連結、登入小字、播放器下的說明，三種語言、三種字級都放得下
        mctx, mp = self._bgm_ctx(browser, viewport={'width': 320, 'height': 700}, touch=True)
        c['menu_and_notes_fit_320_every_language_font_size'] = self.ev(mp, r"""async()=>{ const bad=[], prev={cloud:window.__cloud,user:state.user,known:authKnown};
            window.__cloud=Object.assign({},prev.cloud||{},{enabled:true}); state.user=null; authKnown=false;
            await __setLinks([{type:'music',url:'https://open.spotify.com/track/'+__SP.track}]);
            for(const l of ['zh','ja','en']){ setLang(l); await __wait(60);
              for(const fs of ['small','medium','large']){ applyFontScale(fs); await __wait(40); const tag=l+' '+fs;
                await __open(); window.scrollTo(0,0); await __wait(80);
                const h=document.querySelector('.detail-header').getBoundingClientRect(), n=document.querySelector('.dh-bgm-legal');
                if(!n) bad.push(tag+' no note'); else { const r=n.getBoundingClientRect(); if(r.left<h.left-0.5||r.right>h.right+0.5) bad.push(tag+' note outside'); if(n.scrollWidth>n.clientWidth+1) bad.push(tag+' note overflow'); }
                if(document.documentElement.scrollWidth>innerWidth) bad.push(tag+' hscroll');
                document.getElementById('btn-account-menu').click(); await __wait(150);
                const panel=document.getElementById('account-menu-panel');
                if(panel.hidden){ bad.push(tag+' menu closed'); continue; }
                const pr=panel.getBoundingClientRect();
                for(const e of [document.getElementById('btn-privacy'),panel.querySelector('.auth-legal')]){ if(!e){ bad.push(tag+' missing'); continue; }
                  const r=e.getBoundingClientRect(); if(r.left<pr.left-0.5||r.right>pr.right+0.5) bad.push(tag+' outside '+(e.id||e.className));
                  if(e.scrollWidth>e.clientWidth+1) bad.push(tag+' overflow '+(e.id||e.className)); }
                if(pr.right>innerWidth+0.5||pr.left<-0.5) bad.push(tag+' panel off screen');
                document.getElementById('btn-account-menu').click(); await __wait(100); } }
            window.__cloud=prev.cloud; state.user=prev.user; authKnown=prev.known; setLang('zh'); applyFontScale('medium');
            if(bad.length) console.log('v49: fit320',bad.slice(0,8).join(' | ')); return bad.length===0; }""")
        mctx.close()
        # ================= Service Worker =================
        c['sw_other_pages_do_not_replace_offline_app'] = self._sw_check(browser)


# ---------------------------------------------------------------------------
# v4.10.0：訓練頁改版（設計稿 A＋D 的備戰卡）
# ---------------------------------------------------------------------------
# 範例：今天 2026-10-03（六），12/13 有一場已報名的全馬（週跑量目標 56 km）；本週 49.6 km、上週 47.9 km
TR410_SEED_JS = r"""
// v4.10.0 畫面檢查用的範例：今天 2026-10-03（六），12/13 有一場已報名的全馬（週跑量目標 56 km）
window.__seed410=async function(opts){ opts=opts||{};
  const loop=(n,rx,ry,wob)=>{ const a=[]; for(let i=0;i<100;i++){ const t=i/100*Math.PI*2; a.push(+(0.5+rx*Math.cos(t)+wob*Math.sin(3*t)).toFixed(3),+(0.5+ry*Math.sin(t)+wob*Math.cos(2*t)).toFixed(3)); } return a; };
  shoes.length=0;
  shoes.push({id:'sA',name:'Trainer A',targetKm:600,isRetired:false,trainingKm:0},{id:'sB',name:'Racer B',targetKm:400,isRetired:false,trainingKm:0});
  const T=[]; let n=0;
  const add=(date,time,km,sec,hr,elev,name,shoe,sport)=>T.push(migrateTraining({id:'t'+(n++),date,startTime:time,sport:sport||'run',name:name||'',
    distanceKm:km,durationSeconds:sec,elevationGainM:elev,avgHr:hr,shoeId:shoe===undefined?'sA':shoe,thumb:loop(n,0.32+((n*7)%5)/50,0.22+((n*3)%5)/40,0.05),fingerprint:'fp'+n}));
  // 本週
  add('2026-10-03','06:12',21.4,7447,147,312,'週六長跑');
  add('2026-10-01','06:20',7.2,2592,131,40,'恢復跑');
  add('2026-09-30','18:40',12.6,3667,163,65,'節奏跑','sB');
  add('2026-09-29','06:05',8.4,2948,138,30,'輕鬆跑');
  // 上週（47.9 km）
  add('2026-09-26','06:10',19.5,6922,149,280,'週六長跑');
  add('2026-09-24','06:15',6.8,2462,132,35,'恢復跑');
  add('2026-09-23','18:30',12.0,3540,161,60,'');
  add('2026-09-22','06:00',9.6,3360,140,42,'');
  // 再往前 10 週：每週 4 次，週末長跑
  const weekly=[41.2,38.0,44.6,74.7,52.0,45.1,33.6,49.3,47.0,30.2];   // 新到舊
  weekly.forEach((tot,i)=>{ const mon=addDaysStr('2026-09-21',-7*(i+1));
    const long=Math.round(tot*0.42*10)/10, a=Math.round(tot*0.22*10)/10, b=Math.round(tot*0.2*10)/10, c=+(tot-long-a-b).toFixed(1);
    add(addDaysStr(mon,1),'06:05',a,Math.round(a*350),140,40,'');
    add(addDaysStr(mon,2),'18:40',b,Math.round(b*300),158,50,'');
    add(addDaysStr(mon,3),'06:20',c,Math.round(c*360),132,30,'');
    add(addDaysStr(mon,5),'06:10',long,Math.round(long*345),148,250,''); });
  if(opts.ride) add('2026-10-02','07:00',42.0,5400,128,380,'週五騎車',null,'ride');
  trainings=T; await persistTrainings();
  const r=emptyRace('範例全程馬拉松','road_running','registered','2026-12-13');
  r.id='prep-full'; r.schedule.startTime='06:30'; r.route.distanceKm=42.195; r.location.city='台北市';
  r.goals=[{tier:'A',targetTimeSeconds:14100},{tier:'B',targetTimeSeconds:14340},{tier:'C',targetTimeSeconds:null}];
  if(opts.goal!==false) r.trainingPlan.weeklyMileageTargetKm=56;
  state.races=state.races.filter(x=>x.id!=='prep-full'); if(opts.race!==false) state.races.push(r);
  await persist(); renderAll();
};
"""
TR410_JS = r"""
window.__ov=()=>document.getElementById('training-overlay');
window.__q=s=>__ov().querySelector(s);
window.__qa=s=>[...__ov().querySelectorAll(s)];
window.__open410=async(o)=>{ await __seed410(o); openTrainingOverlay(); await __wait(120); };
window.__tab=async v=>{ __q('[data-training-period="'+v+'"]').click(); await __wait(80); };
window.__sport=async v=>{ __q('[data-training-sport="'+v+'"]').click(); await __wait(80); };
window.__px=e=>parseFloat(getComputedStyle(e).fontSize);
"""


class V410Training(V49Privacy):
    """v4.10.0：訓練頁改版。「本週」：備戰中的賽事卡（已報名／抽籤中、已進入準備期的最近一場；倒數、A／B 目標、
    賽前第幾週、準備期／減量期）、本週卡（大數字、比上週同期、週目標＝賽事訓練計畫的週跑量、每天的長條）、三格小卡、
    本週解讀、近 12 週里程；「本月」：每天的長條與近 12 個月；「全部」維持年月收合。兩種以上的運動時可以篩選，
    不同運動的公里數不相加。字級照設計稿（16／17／24／15，圖表至少 13，都乘 --fs），點擊範圍至少 44px。"""

    ECHO = ('v410:',)

    def _tr(self, browser, viewport=None, touch=True, lang='zh', theme='light', now='2026-10-03T09:00:00'):
        ctx, pg = self._ctx(browser, viewport=viewport or {'width': 390, 'height': 844}, touch=touch, lang=lang, theme=theme, now=now, seed=False)
        pg.add_script_tag(content=TR410_SEED_JS + TR410_JS)
        return ctx, pg

    def body(self, page):
        c = self.checks
        browser = page.context.browser
        c['seed_available'] = bool(TR410_SEED_JS)
        ctx, pg = self._tr(browser)
        # ================= 備戰中的賽事卡 =================
        c['prep_card_shows_nearest_race_in_prep_window'] = self.ev(pg, r"""async()=>{ await __open410();
            const card=__q('.trp-card'); if(!card) return false;
            const txt=card.innerText.replace(/\s+/g,' ');
            const segs=card.querySelectorAll('.trp-seg'), taper=card.querySelectorAll('.trp-seg.is-taper'), now=card.querySelectorAll('.trp-seg.is-now');
            const past=card.querySelectorAll('.trp-seg.is-past');
            // 10/3 → 12/13 是 71 天；全馬準備 16 週、減量 3 週；賽前第 11 週＝備戰第 6 週
            const ok=txt.includes('範例全程馬拉松')&&/\b71\b/.test(card.querySelector('.trp-days').innerText)&&txt.includes('A 3:55:00')&&txt.includes('B 3:59:00')
              &&txt.includes('賽前第 11 週')&&txt.includes('備戰第 6 週 / 共 16 週')&&txt.includes('12/13（日）06:30 起跑')&&txt.includes('42.2 km')
              &&segs.length===16&&taper.length===3&&now.length===1&&past.length===5&&[...segs].indexOf(now[0])===5
              &&card.compareDocumentPosition(__q('.trw-card'))&Node.DOCUMENT_POSITION_FOLLOWING;
            if(!ok) console.log('v410: prep',txt.slice(0,200),segs.length,taper.length,past.length); return !!ok; }""")
        c['prep_card_only_for_committed_races_in_window'] = self.ev(pg, r"""async()=>{ const bad=[], r=state.races.find(x=>x.id==='prep-full');
            const look=async()=>{ refreshTrainingOverlay(); await __wait(40); return __q('.trp-card'); };
            r.status='considering'; if(await look()) bad.push('considering shown');
            r.status='lottery_pending'; let c1=await look(); if(!c1||!c1.innerText.includes(labelFor(STATUS_OPTIONS,'lottery_pending','status'))) bad.push('lottery chip');
            r.status='registered'; r.schedule.raceDate='2027-03-01'; if(await look()) bad.push('outside 16-week window shown');
            // 最近那場還沒進準備期（10K 準備 6 週），下一場進了：放下一場
            r.schedule.raceDate='2026-12-13';
            const tenk=emptyRace('十公里','road_running','registered','2026-11-29'); tenk.id='tenk'; tenk.route.distanceKm=10; state.races.push(tenk);
            let c2=await look(); if(!c2||!c2.innerText.includes('範例全程馬拉松')) bad.push('should skip race not yet in window');
            tenk.schedule.raceDate='2026-11-08';   // 5 週後、10K 準備 6 週：進了，而且比較近
            let c3=await look(); if(!c3||!c3.innerText.includes('十公里')) bad.push('nearest in window');
            state.races=state.races.filter(x=>x.id!=='tenk'); r.deletedAt=new Date().toISOString(); if(await look()) bad.push('deleted shown');
            r.deletedAt=null; refreshTrainingOverlay(); await __wait(40);
            if(bad.length) console.log('v410: prep filter',bad.join(' | ')); return bad.length===0; }""")
        c['prep_card_opens_race_page'] = self.ev(pg, r"""async()=>{ __q('.trp-card').click(); await __wait(200);
            const ok=__ov().hidden&&state.selectedId==='prep-full'&&!!currentRace&&currentRace.id==='prep-full';
            openTrainingOverlay(); await __wait(80); return ok; }""")
        # ================= 本週卡 =================
        c['week_card_total_and_vs_same_days_last_week'] = self.ev(pg, r"""async()=>{
            const card=__q('.trw-card'), km=card.querySelector('.trw-km b').textContent, chip=card.querySelector('.tr-chip');
            // 本週一到今天（週六）49.6；上週一到上週六 47.9 → +3.5% 四捨五入 4%
            const ok=km==='49.6'&&!!chip&&chip.textContent.includes('4%')&&chip.textContent.includes('↑')&&chip.textContent.includes('上週同期')
              &&card.querySelector('.trw-range').textContent==='9/28 – 10/4';
            if(!ok) console.log('v410: week',km,chip&&chip.textContent); return ok; }""")
        c['week_days_today_rest_future'] = self.ev(pg, r"""async()=>{
            const days=__qa('.trw-day'), vals=days.map(d=>d.querySelector('.trw-day-val').textContent), names=days.map(d=>d.querySelector('.trw-day-name').textContent);
            const today=days.findIndex(d=>d.classList.contains('is-today'));
            const ok=days.length===7&&JSON.stringify(names)===JSON.stringify(['一','二','三','四','五','六','日'])
              &&JSON.stringify(vals)===JSON.stringify(['休','8.4','12.6','7.2','休','21.4','—'])&&today===5&&days[6].classList.contains('is-future');
            if(!ok) console.log('v410: days',vals.join(','),today); return ok; }""")
        c['week_goal_from_race_training_plan'] = self.ev(pg, r"""async()=>{
            const g=__q('.trw-goal'); if(!g) return false; const txt=g.innerText.replace(/\s+/g,' ');
            const bar=g.querySelector('[role="progressbar"]');
            const ok=txt.includes('週目標 56 km')&&txt.includes('89%')&&txt.includes('再 6.4 km 達標')&&txt.includes('範例全程馬拉松')&&bar.getAttribute('aria-valuenow')==='89';
            if(!ok) console.log('v410: goal',txt); return ok; }""")
        c['week_goal_reached_and_missing'] = self.ev(pg, r"""async()=>{ const bad=[], r=state.races.find(x=>x.id==='prep-full');
            r.trainingPlan.weeklyMileageTargetKm=40; refreshTrainingOverlay(); await __wait(40);
            let t1=__q('.trw-goal').innerText; if(!t1.includes('已達標，多跑了 9.6 km')||!t1.includes('124%')) bad.push('over '+t1);
            r.trainingPlan.weeklyMileageTargetKm=null; refreshTrainingOverlay(); await __wait(40);
            if(__q('.trw-goal')) bad.push('goal without target');
            const link=__q('[data-action="training-set-goal"]'); if(!link) bad.push('no set-goal link');
            else{ link.click(); await __wait(250);
              const field=[...document.querySelectorAll('#drawer-content [data-path]')].find(x=>x.dataset.path==='trainingPlan.weeklyMileageTargetKm');
              if(!(__ov().hidden&&currentRace&&currentRace.id==='prep-full'&&drawerOpenSection==='trainingPlan'&&field&&document.activeElement===field)) bad.push('link target');
              closeDrawer(); }
            r.trainingPlan.weeklyMileageTargetKm=56; openTrainingOverlay(); await __wait(80);
            if(bad.length) console.log('v410: goal states',bad.join(' | ')); return bad.length===0; }""")
        c['tiles_count_time_climb'] = self.ev(pg, r"""async()=>{
            const tiles=__qa('.trw-card + .tr-tiles .tr-tile b').map(b=>b.textContent);
            const items=trainingsInRange('2026-09-28','2026-10-03',['run']);
            const want=[String(items.length),fmtTrainingHM(trSumSec(items)),Math.round(trSumElev(items)).toLocaleString('en-US')];
            const ok=JSON.stringify(tiles)===JSON.stringify(want)&&tiles[0]==='4';
            if(!ok) console.log('v410: tiles',tiles.join(','),want.join(',')); return ok; }""")
        c['hours_never_show_60_minutes'] = self.ev(pg, r"""()=>fmtTrainingHM(14399)==='4:00'&&fmtTrainingHM(3570)==='1:00'&&fmtTrainingHM(0)==='0:00'
            &&trainingGroupStatsHtml([{distanceKm:10,durationSeconds:14380}]).endsWith('4:00')""")
        c['week_read_above_average_and_longest'] = self.ev(pg, r"""async()=>{
            const p=__q('.tr-read p'); if(!p) return false; const txt=p.textContent;
            // 本週之前 4 週：41.2、47.9、38.0（不含本週）… 平均用程式算出來比對
            const had=trainingsInRange('2026-08-31','2026-09-27',['run']), avg=trSumKm(had)/4, pct=Math.round((49.6/avg-1)*100);
            const ok=txt.includes('目前 49.6 km')&&txt.includes('（'+trFmtKm(avg)+' km）')&&txt.includes('多 '+pct+'%')&&txt.includes('最長一次是週六的 21.4 km，佔本週的 43%');
            if(!ok) console.log('v410: read',txt,avg); return ok; }""")
        c['twelve_week_chart_average_line_and_labels'] = self.ev(pg, r"""async()=>{
            const card=__q('.trc-card'); if(!card) return false;
            const cols=[...card.querySelectorAll('.trc-col')], vals=[...card.querySelectorAll('.trc-val')].map(v=>v.textContent);
            const area=card.querySelector('.trc-area').getBoundingClientRect(), line=card.querySelector('.trc-avg').getBoundingClientRect();
            const kms=cols.map(c=>{ const m=c.title.match(/([\d.]+) km$/); return m?Number(m[1]):NaN; });
            const avg=(kms[7]+kms[8]+kms[9]+kms[10])/4, max=Math.max(avg,...kms);
            const expectY=area.bottom-avg/max*area.height;   // 虛線畫在框的上緣，框的底邊就是平均值的位置
            const lastBar=cols[11].querySelector('.trc-bar').getBoundingClientRect(), peakBar=cols[kms.indexOf(Math.max(...kms.slice(0,11)))].querySelector('.trc-bar').getBoundingClientRect();
            const ok=cols.length===12&&cols[11].classList.contains('is-cur')&&kms[11]===49.6&&Math.abs(line.bottom-expectY)<=1.5
              &&vals.includes('74.7')&&vals.includes('49.6')&&vals.length===2&&Math.abs(peakBar.height-area.height)<=1.5
              &&card.querySelector('.trc-legend').textContent.includes(trFmtKm(avg))&&card.querySelector('.trc-x-cur').textContent==='本週'
              // x 軸的字都在同一排（指定欄位又重疊時，後面那個會被擠到下一排）
              &&new Set([...card.querySelectorAll('.trc-x span')].map(e=>Math.round(e.getBoundingClientRect().top))).size===1;
            if(!ok) console.log('v410: chart',kms.join(','),line.top,expectY,vals.join(',')); return ok; }""")
        c['week_list_this_and_last_week'] = self.ev(pg, r"""async()=>{
            const heads=__qa('.training-list-head'), rows=__qa('.training-group:first-child .training-row').length;
            const ok=heads.length===2&&heads[0].innerText.startsWith('本週')&&heads[0].innerText.includes('4 次')&&heads[1].innerText.startsWith('上週')
              &&rows===4&&__qa('.training-row').length===8;
            if(!ok) console.log('v410: list',heads.map(h=>h.innerText).join(' / ')); return ok; }""")
        # ================= 週還沒過完、週一、週日 =================
        ctx.close()
        mctx, mp = self._tr(browser, now='2026-09-28T07:00:00')   # 週一早上，這週還沒跑
        c['monday_morning_no_misleading_minus_100'] = self.ev(mp, r"""async()=>{ await __open410();
            const card=__q('.trw-card'), chip=card.querySelector('.tr-chip'), read=__q('.tr-read p');
            // 上週同期（上週一）沒有訓練：不放比較；不說「少 100%」；解讀說還沒有訓練
            const ok=card.querySelector('.trw-km b').textContent==='0.0'&&!chip&&!!read&&read.textContent.includes('本週還沒有訓練')&&!/少/.test(read.textContent)
              &&__qa('.training-group')[0].innerText.includes('本週還沒有訓練');
            if(!ok) console.log('v410: monday',chip&&chip.textContent,read&&read.textContent); return ok; }""")
        mctx.close()
        tctx, tp = self._tr(browser, now='2026-10-01T21:00:00')   # 週四晚上：49.6 的前半段，還沒到平均
        c['midweek_below_average_says_gap_not_less'] = self.ev(tp, r"""async()=>{ await __open410();
            const txt=__q('.tr-read p').textContent;
            const ok=/近 4 週平均 [\d.]+ km，還差 [\d.]+ km。/.test(txt)&&!/少 \d+%/.test(txt);
            if(!ok) console.log('v410: midweek',txt); return ok; }""")
        tctx.close()
        sctx, sp = self._tr(browser, now='2026-09-27T20:00:00')   # 週日：週過完了，少就說少
        c['sunday_week_done_can_say_less'] = self.ev(sp, r"""async()=>{ await __open410();
            const txt=__q('.tr-read p').textContent; const ok=/比近 4 週平均（[\d.]+ km）(多|少) \d+%|差不多/.test(txt);
            if(!ok) console.log('v410: sunday',txt); return ok; }""")
        sctx.close()
        # ================= 運動篩選 =================
        rctx, rp = self._tr(browser)
        c['sport_filter_defaults_to_race_sport'] = self.ev(rp, r"""async()=>{ await __open410({ride:true});
            const btns=__qa('[data-training-sport]').map(b=>b.dataset.trainingSport+':'+b.getAttribute('aria-pressed'));
            const km=__q('.trw-km b').textContent, rows=__qa('.training-row').length;
            const ok=JSON.stringify(btns)===JSON.stringify(['run:true','ride:false','all:false'])&&km==='49.6'&&rows===8
              &&!__q('.tr-mix')&&__q('.trw-goal')&&!__qa('.training-title').some(e=>e.textContent==='週五騎車');
            if(!ok) console.log('v410: sport default',btns.join(','),km,rows); return ok; }""")
        c['sport_filter_all_sums_and_explains'] = self.ev(rp, r"""async()=>{ await __sport('all');
            const km=__q('.trw-km b').textContent, mix=__q('.tr-mix'), goal=__q('.trw-goal');
            const ok=km==='91.6'&&!!mix&&mix.textContent.includes('跑步 49.6')&&mix.textContent.includes('騎車 42.0')
              &&!!goal&&goal.innerText.includes('（跑步）')&&goal.innerText.includes('89%')&&__qa('.training-row').length===9;
            if(!ok) console.log('v410: sport all',km,mix&&mix.textContent,goal&&goal.innerText); return ok; }""")
        c['sport_filter_other_sport_hides_run_goal'] = self.ev(rp, r"""async()=>{ await __sport('ride');
            const ok=__q('.trw-km b').textContent==='42.0'&&!__q('.trw-goal')&&!__q('[data-action="training-set-goal"]')&&__qa('.training-row').length===1
              &&__q('.training-title').textContent==='週五騎車'; await __sport('run'); return ok; }""")
        c['sport_filter_without_race_uses_most_sessions'] = self.ev(rp, r"""async()=>{
            state.races=state.races.filter(x=>x.id!=='prep-full'); closeTrainingOverlay(); openTrainingOverlay(); await __wait(80);
            const on=__q('[data-training-sport][aria-pressed="true"]');
            const ok=!!on&&on.dataset.trainingSport==='run'&&!__q('.trp-card'); return ok; }""")
        c['single_sport_has_no_filter_row'] = self.ev(rp, r"""async()=>{ await __open410(); return !__q('.training-sports')&&__q('.trw-km b').textContent==='49.6'; }""")
        # ================= 本月、全部 =================
        c['month_tab_card_strip_and_twelve_months'] = self.ev(rp, r"""async()=>{ await __open410(); await __tab('month');
            const card=__q('.trw-card'), strip=card.querySelectorAll('.trm-day'), cols=__qa('.trc-col');
            const items=trainingsInRange('2026-10-01','2026-10-03',['run']);
            const chip=card.querySelector('.tr-chip');
            const prev=trSumKm(trainingsInRange('2026-09-01','2026-09-03',['run'])), pct=Math.round((trSumKm(items)/prev-1)*100);
            const ok=card.querySelector('.trw-km b').textContent===trFmtKm(trSumKm(items))&&strip.length===31&&card.querySelector('.trm-day.is-today')===strip[2]
              &&cols.length===12&&__q('.trc-x-cur').textContent==='本月'&&(!prev||(chip&&chip.textContent.includes(Math.abs(pct)+'%')))
              &&__qa('.training-row').length===items.length&&!__q('[data-training-year]');
            if(!ok) console.log('v410: month',strip.length,cols.length,chip&&chip.textContent); return ok; }""")
        c['all_tab_totals_and_groups'] = self.ev(rp, r"""async()=>{ await __tab('all');
            const all=liveTrainings(), km=Math.round(trSumKm(all)).toLocaleString('en-US');
            const ok=__q('.trw-card .trw-km b').textContent===km&&__qa('.tr-tile b')[0].textContent===String(all.length)&&!!__q('[data-training-year]');
            await __tab('week'); return ok; }""")
        # ================= 字級與點擊範圍 =================
        c['type_scale_matches_design_times_font_setting'] = self.ev(rp, r"""async()=>{ const bad=[];
            for(const [fs,k] of [['small',0.9],['medium',1],['large',1.15]]){ applyFontScale(fs); refreshTrainingOverlay(); await __wait(60);
              const near=(e,px)=>e&&Math.abs(__px(e)-px*k)<0.3;
              if(!near(__q('.training-inner'),16)) bad.push(fs+' body');
              if(!near(__q('.training-title'),17)) bad.push(fs+' title');
              if(!near(__q('.training-dist b'),24)) bad.push(fs+' distance');
              if(!near(__q('.training-stats'),15)) bad.push(fs+' stats');
              if(!near(__q('.training-date'),15)) bad.push(fs+' date');
              // 畫面上所有看得到的字至少 13px（乘上字級）
              const tiny=__qa('*').filter(e=>e.childNodes.length&&[...e.childNodes].some(n=>n.nodeType===3&&n.textContent.trim())&&e.getClientRects().length&&__px(e)<13*k-0.3);
              if(tiny.length) bad.push(fs+' tiny: '+tiny.slice(0,3).map(e=>e.className+' '+__px(e)).join(';')); }
            applyFontScale('medium'); refreshTrainingOverlay(); await __wait(40);
            if(bad.length) console.log('v410: type',bad.join(' | ')); return bad.length===0; }""")
        c['tap_targets_at_least_44px'] = self.ev(rp, r"""async()=>{ const bad=[];
            __qa('button,select,a').filter(e=>e.getClientRects().length&&!e.classList.contains('training-shoe')&&!e.classList.contains('trp-card')).forEach(e=>{
              const r=e.getBoundingClientRect(); if(r.height<43.5) bad.push((e.dataset.action||e.dataset.trainingPeriod||e.className)+' '+r.height.toFixed(0)); });
            // 鞋款膠囊看起來 32px，上下各 6px 也點得到
            const chip=__q('.training-shoe'); chip.scrollIntoView({block:'center'}); await __wait(50); const r=chip.getBoundingClientRect();
            const hit=y=>{ const e=document.elementFromPoint(r.left+r.width/2,y); return !!(e&&e.closest('.training-shoe')===chip); };
            if(!(hit(r.top-5.5)&&hit(r.bottom+5.5))) bad.push('shoe chip hit area');
            if(bad.length) console.log('v410: taps',bad.slice(0,6).join(' | ')); return bad.length===0; }""")
        c['shoe_chip_still_edits_and_deletes'] = self.ev(rp, r"""async()=>{
            const row=__q('.training-row'), id=row.dataset.trainingId; row.querySelector('[data-action="training-edit"]').click(); await __wait(60);
            const sel=__q('[data-training-shoe="'+id+'"]'); if(!sel) return false;
            sel.value='sB'; sel.dispatchEvent(new Event('change',{bubbles:true})); await __wait(150);
            const changed=trainings.find(x=>x.id===id).shoeId==='sB'&&__q('[data-training-id="'+id+'"] .training-shoe').textContent.trim()==='Racer B';
            __q('[data-training-id="'+id+'"] [data-action="training-edit"]').click(); await __wait(60);
            __q('[data-action="training-delete"][data-id="'+id+'"]').click(); await __wait(150);
            const gone=!!trainings.find(x=>x.id===id).deletedAt&&!__q('[data-training-id="'+id+'"]');
            await __open410(); return changed&&gone; }""")
        rctx.close()
        # ================= 三種語言：沒有漏翻 =================
        lang_bad = []
        for lang in ('ja', 'en'):
            lctx, lp = self._tr(browser, lang=lang)
            got = self.ev(lp, r"""async(lang)=>{ await __open410({ride:true}); const out=[]; let seen=0;
                const scan=()=>{ // 使用者資料（賽事名稱、訓練名稱、鞋款）不算
                  const skip=new Set([...__qa('.trp-name,.training-title,.training-shoe,.trw-goal-src')]);
                  const walk=document.createTreeWalker(__ov(),NodeFilter.SHOW_TEXT); let n; const txt=[];
                  while((n=walk.nextNode())){ const el=n.parentElement; if([...skip].some(s=>s.contains(el))) continue; if(el.getClientRects().length) txt.push(n.textContent); }
                  return txt.join(' '); };
                for(const tab of ['week','month','all']){ await __tab(tab); await __sport('all');
                  const t=scan(); seen+=t.length;
                  if(lang==='en'){ const han=t.match(/[一-鿿]+/g); if(han) out.push(tab+': '+[...new Set(han)].slice(0,6).join(',')); }
                  else{ ['本週','本月','跑步','騎車','次訓練','總時數','週目標','備戰','減量期','近 12','上週','爬升'].forEach(w=>{ if(t.includes(w)) out.push(tab+': '+w); }); } }
                // 什麼都沒掃到（頁面沒畫出來）不算通過
                if(seen<300) out.push('page did not render ('+seen+' chars)');
                return out; }""", lang)
            if not isinstance(got, list):
                lang_bad.append(lang + ' crashed')
            elif got:
                lang_bad.append(lang + ' ' + '; '.join(got))
            lctx.close()
        if lang_bad:
            print('    v410: untranslated', lang_bad)
        c['ja_en_fully_translated'] = not lang_bad
        # ================= 手機各寬度 × 三語 × 三種字級：不左右滑、字不被擠出去 =================
        FIT = r"""async()=>{ const bad=[];
            for(const lang of ['zh','ja','en']){ setLang(lang); await __wait(60);
              for(const fs of ['small','medium','large']){ applyFontScale(fs); await __open410({ride:true});
                // 標題列：標題一定一行（放不下時按鈕換到上面一排，不是把標題擠成「トレーニング記／録」）、
                // 關閉鈕在右上角；中文放得下，標題跟按鈕要在同一排（不能為了日文讓每種語言都變兩排）
                { const top=__q('.training-top'), h=top.querySelector('h2'), x=top.querySelector('.training-close');
                  const g=document.createRange(); g.selectNodeContents(h); const lines=new Set([...g.getClientRects()].map(q=>Math.round(q.top))).size;
                  const tb=top.getBoundingClientRect(), hb=h.getBoundingClientRect(), xb=x.getBoundingClientRect();
                  if(lines!==1) bad.push(lang+' '+fs+' title lines '+lines);
                  if(Math.abs(xb.right-tb.right)>1||xb.top>hb.top+1) bad.push(lang+' '+fs+' close not top-right');
                  if(lang==='zh'&&!(xb.top<hb.bottom&&xb.bottom>hb.top)) bad.push(lang+' '+fs+' zh header not one row'); }
                for(const tab of ['week','month','all']){ await __tab(tab); for(const s of ['run','all']){ await __sport(s); const tag=lang+' '+fs+' '+tab+' '+s;
                  const ov=__ov(); if(ov.scrollWidth>ov.clientWidth) bad.push(tag+' hscroll '+ov.scrollWidth);
                  __qa('.tr-tile b,.trw-day-val,.training-dist,.trp-goal,.trw-km b,.trp-days-num,.training-sport,.training-tab').forEach(e=>{ if(e.scrollWidth>e.clientWidth+1) bad.push(tag+' overflow '+e.className); });
                  // 運動按鈕整顆都在畫面裡（橫向捲動時最後一顆被切一半，看不出還有）
                  __qa('.training-sport').forEach(e=>{ const q=e.getBoundingClientRect(); if(q.right>ov.clientWidth+0.5||q.left<-0.5) bad.push(tag+' sport chip cut'); });
                  const cards=__qa('.tr-card'); cards.forEach(cd=>{ const r=cd.getBoundingClientRect(); [...cd.querySelectorAll('*')].forEach(x=>{ if(!x.getClientRects().length||x.closest('.trc-val')) return; const q=x.getBoundingClientRect(); if(q.width&&(q.right>r.right+1||q.left<r.left-1)) bad.push(tag+' outside card '+x.className); }); });
                  // x 軸的字不疊在一起
                  __qa('.trc-x').forEach(x=>{ const sp=[...x.children].map(s=>{ const g=document.createRange(); g.selectNodeContents(s); return g.getBoundingClientRect(); }).filter(q=>q.width);
                    for(let i=0;i<sp.length;i++) for(let j=i+1;j<sp.length;j++) if(sp[i].right>sp[j].left+0.5&&sp[j].right>sp[i].left+0.5&&Math.abs(sp[i].top-sp[j].top)<4) bad.push(tag+' x labels overlap'); });
                  // 每天的數字不擠在一起
                  const dv=__qa('.trw-day-val').map(v=>{ const g=document.createRange(); g.selectNodeContents(v); return g.getBoundingClientRect(); });
                  for(let i=0;i<dv.length-1;i++) if(dv[i].right>dv[i+1].left-2) bad.push(tag+' day values touch '+i); } } } }
            setLang('zh'); applyFontScale('medium');
            if(bad.length) console.log('v410: fit '+innerWidth,[...new Set(bad)].slice(0,8).join(' | ')); return bad.length===0; }"""
        for w in (320, 360, 390):
            fctx, fp = self._tr(browser, viewport={'width': w, 'height': 800})
            c[f'fits_{w}_three_languages_three_font_sizes'] = self.ev(fp, FIT)
            fctx.close()
        # ================= 深淺色的對比 =================
        cctx, cp = self._tr(browser)
        c['contrast_light_dark'] = self.ev(cp, r"""async()=>{ const bad=[]; await __open410({ride:true});
            const sels=['.trp-chip','.trp-meta','.trp-when','.trp-week','.trp-phases span','.trw-range','.tr-chip','.trw-goal-row','.trw-goal-foot','.trw-goal-src',
              '.trw-day-name','.trw-day-val','.tr-tile span','.tr-read p','.trc-legend','.trc-val','.trc-x span','.training-date','.training-stats','.training-shoe span','.training-group-stats','.training-sport'];
            for(const th of ['light','dark']){ applyTheme(th); await __wait(120);
              sels.forEach(s=>{ const e=__q(s); if(!e){ bad.push(th+' missing '+s); return; } const cr=__textCr(e); if(cr<4.5) bad.push(th+' '+s+' '+cr.toFixed(2)); }); }
            applyTheme('light'); await __wait(60);
            if(bad.length) console.log('v410: contrast',bad.join(' | ')); return bad.length===0; }""")
        # 說明頁頂端本來就印著版本號，只找「v4.10.0」少了這一段也會過：找這一段特有的句子（備戰卡、不同運動不相加）
        c['help_mentions_training_page_three_languages'] = self.ev(cp, r"""async()=>{ const bad=[], key={zh:'不同運動的公里數不會加在一起',ja:'種目の違う距離は合計しません',en:'distances from different sports are never added together'};
            closeTrainingOverlay();
            for(const l of ['zh','ja','en']){ setLang(l); await __wait(80); openHelpModal(); await __wait(150);
              const txt=document.getElementById('help-modal').innerText; if(!txt.includes(key[l])) bad.push(l);
              document.querySelector('#help-modal [data-action="close-help"]').click(); await __wait(80); }
            setLang('zh'); await __wait(60); if(bad.length) console.log('v410: help',bad.join(' | ')); return bad.length===0; }""")
        c['version_is_v4_10_0'] = self.ev(cp, "()=>APP_VERSION==='v4.10.0'")
        cctx.close()


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
    'feedback':   lambda: FeedbackConfigured('feedback'),
    'training':   lambda: Training('training'),
    'radar':      lambda: Radar('radar'),
    'journey':    lambda: Journey('journey'),
    'simple':     lambda: Simple('simple'),
    'simple_phone': lambda: SimplePhone('simple_phone'),
    'ux':         lambda: UxFixes('ux'),
    'v4':         lambda: V4Layout('v4'),
    'v41':        lambda: V41Fixes('v41'),
    'v42':        lambda: V42Flows('v42'),
    'v43':        lambda: V43Flows('v43'),
    'v431':       lambda: V431Fixes('v431'),
    'v432':       lambda: V432Best('v432'),
    'v433':       lambda: V433Fields('v433'),
    'v44':        lambda: V44BibWall('v44'),
    'v45':        lambda: V45Backup('v45'),
    'v451':       lambda: V451WallFold('v451'),
    'v46':        lambda: V46FinisherWall('v46'),
    'v47':        lambda: V47DailyQuote('v47'),
    'v471':       lambda: V471TaglineFit('v471'),
    'v48':        lambda: V48RaceBgm('v48'),
    'v49':        lambda: V49Privacy('v49'),
    'v410':       lambda: V410Training('v410'),
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
