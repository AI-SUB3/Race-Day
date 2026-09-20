/* 賽事紀錄 — 離線 Service Worker
   目的只有一個：山上沒訊號時，網站還打得開、疲勞模式還能用。
   資料本來就全在本機（IndexedDB），缺的只是「頁面本身」——一個 index.html
   加兩個 CDN 套件。所以這支 SW 只快取這幾樣東西，其他（Firebase、天氣
   API）一律直接放行，不快取、不攔截。

   快取版本綁在註冊時的 ?v=APP_VERSION：index.html 版號一變，這支檔案的
   URL 就變，瀏覽器視為新的 SW、走 install → 建新快取 → activate 刪舊快取。
   不用另外維護一個版本常數，也不會出現「index.html 更新了、快取還是舊的」。 */
const VERSION=new URL(self.location.href).searchParams.get('v')||'dev';
const CACHE='race-log-'+VERSION;
const FONT_CACHE='race-log-fonts';   // 字型跨版本共用，不必每版重抓
const PRECACHE=[
  './',
  './index.html',
  './icons/manifest.webmanifest',
  './icons/icon-192.png',
  './icons/icon-512.png',
  './icons/apple-touch-icon.png',
  './icons/help-avatar.png',
  // 這兩行必須跟 index.html 的 <script src> 一模一樣（含版號）——
  // index.html 用 SRI 驗證內容，快取的回應若不是 CORS 模式取得的
  // （opaque），SRI 會判定失敗、套件整個不載入。test_suite 有檢查。
  'https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js',
  'https://cdn.jsdelivr.net/npm/idb-keyval@6.3.0/dist/umd.js',
];
const NAV_TIMEOUT_MS=3500;

function corsRequest(url){
  return new Request(url,{mode:'cors',credentials:'omit'});
}
function isCdn(url){ return url.hostname==='cdn.jsdelivr.net'; }
function isFont(url){ return url.hostname==='fonts.googleapis.com'||url.hostname==='fonts.gstatic.com'; }

self.addEventListener('install',event=>{
  event.waitUntil((async()=>{
    const cache=await caches.open(CACHE);
    // 逐一 add、個別容錯：少一張圖示不該讓整個 install 失敗、離線功能全沒。
    await Promise.all(PRECACHE.map(async u=>{
      try{ await cache.add(/^https?:/.test(u)?corsRequest(u):u); }
      catch(err){ /* 單一資源失敗，其餘照常 */ }
    }));
    // 不自動 skipWaiting：新版要等使用者按「更新」才切換，避免正在填表單
    // 時頁面突然重新載入。
  })());
});

self.addEventListener('activate',event=>{
  event.waitUntil((async()=>{
    const names=await caches.keys();
    await Promise.all(names.filter(n=>n.startsWith('race-log-')&&n!==CACHE&&n!==FONT_CACHE).map(n=>caches.delete(n)));
    await self.clients.claim();
  })());
});

self.addEventListener('message',event=>{
  if(event.data&&event.data.type==='SKIP_WAITING') self.skipWaiting();
});

/* 導覽請求（開網站）：先試網路、逾時或失敗才用快取。
   為什麼不是快取優先：那樣每次都拿到舊版，更新要靠 SW 換版才生效，
   使用者會看到「明明推了新版怎麼還是舊的」。網路優先＋短逾時，
   有訊號時永遠最新，沒訊號時 3.5 秒內退回快取。 */
async function handleNavigation(request){
  const cache=await caches.open(CACHE);
  try{
    const controller=new AbortController();
    const timer=setTimeout(()=>controller.abort(),NAV_TIMEOUT_MS);
    const res=await fetch(request,{signal:controller.signal});
    clearTimeout(timer);
    if(res&&res.ok){ cache.put('./index.html',res.clone()); }
    return res;
  }catch(err){
    const cached=await cache.match('./index.html')||await cache.match('./');
    if(cached) return cached;
    throw err;
  }
}

/* CDN 套件：快取優先。版號鎖死＋SRI，內容永遠不會變，沒有理由每次都問網路。 */
async function handleCdn(request){
  const cache=await caches.open(CACHE);
  const hit=await cache.match(request.url);
  if(hit) return hit;
  const res=await fetch(corsRequest(request.url));
  if(res&&res.ok) cache.put(request.url,res.clone());
  return res;
}

/* 字型：先給快取、背景更新。字型缺了頁面也能用（有備援字型），
   所以這裡寧可先出畫面。 */
async function handleFont(request){
  const cache=await caches.open(FONT_CACHE);
  const hit=await cache.match(request);
  const refresh=fetch(request).then(res=>{ if(res&&res.ok) cache.put(request,res.clone()); return res; }).catch(()=>null);
  return hit||(await refresh)||Response.error();
}

self.addEventListener('fetch',event=>{
  const req=event.request;
  if(req.method!=='GET') return;
  const url=new URL(req.url);
  if(req.mode==='navigate'){ event.respondWith(handleNavigation(req)); return; }
  if(isCdn(url)){ event.respondWith(handleCdn(req)); return; }
  if(isFont(url)){ event.respondWith(handleFont(req)); return; }
  if(url.origin===self.location.origin){
    // 同源靜態檔（圖示、manifest）：快取優先，沒有才抓
    event.respondWith((async()=>{
      const cache=await caches.open(CACHE);
      const hit=await cache.match(req,{ignoreSearch:true});
      if(hit) return hit;
      const res=await fetch(req);
      if(res&&res.ok) cache.put(req,res.clone());
      return res;
    })());
  }
  // 其他（Firebase、天氣 API、Google 登入）：不攔，直接走網路
});
