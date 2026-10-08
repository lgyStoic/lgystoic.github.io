/* Same-origin, versioned visit cache. No accounts, uploads, or remote scripts. */
const CACHE='shexian-e4ee02e41f32',CORE=["./","assets/index-CxljCGM-.js","assets/index-D9qrUcMn.css"],root=new URL('./',self.location.href);
self.addEventListener('install',event=>event.waitUntil((async()=>{
 const cache=await caches.open(CACHE);
 await Promise.all(CORE.map(async path=>{const request=new Request(new URL(path,root),{cache:'reload',priority:'low'}),response=await fetch(request);if(!response.ok)throw new Error('Core cache unavailable');await cache.put(request,response);}));
 await self.skipWaiting();
})()));
self.addEventListener('activate',event=>event.waitUntil((async()=>{
 for(const key of await caches.keys())if(key.startsWith('shexian-')&&key!==CACHE)await caches.delete(key);
 await self.clients.claim();
})()));
self.addEventListener('fetch',event=>{
 const request=event.request,url=new URL(request.url);if(request.method!=='GET'||url.origin!==root.origin||!url.pathname.startsWith(root.pathname)||url.pathname.endsWith('/sw.js'))return;
 const navigation=request.mode==='navigate';
 event.respondWith((async()=>{
  const cache=await caches.open(CACHE),key=navigation?new Request(root):request,cached=await cache.match(key,{ignoreSearch:navigation});
  if(!navigation&&cached)return cached;
  const fresh=fetch(request).then(async response=>{if(response.ok&&response.type==='basic')await cache.put(key,response.clone());return response;});
  event.waitUntil(fresh.catch(()=>{}));
  if(!cached)return fresh;
  // Revisit can use the local page if Pages does not respond promptly.
  const response=await Promise.race([fresh.catch(()=>cached),new Promise(resolve=>setTimeout(()=>resolve(cached),800))]);return response;
 })());
});
