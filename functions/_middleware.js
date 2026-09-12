// functions/_middleware.js: the pages.dev side of the Shop & Pool Finder. NO SECRETS HERE.
//
// Cloudflare serves the app itself (public/index.html) as a static file, so the page opens even
// while the machine sleeps. The page's data addresses are relayed to the machine's own server,
// reached by its public name (not a secret; Caddy lets /shopfinder through without the door key,
// the app is public). The machine holds the keys and makes the Google calls itself:
//     /pools.json   the hours update_pools.py wrote on the machine
//     /update       start the updater (it answers at once; the page polls /health)
//     /health       when pools.json was written, and whether a run is going
//     /config.js    whether the paid option exists on the machine (never a key)
//     /places       a Google Places search, made on the machine
//     /gtile/...    Google's map tiles, fetched by the machine
// When the machine does not answer in time the page gets {ok:false, asleep:true} (config.js gets
// a valid script saying so) and shows the free option. Everything else is a static file.

const ORIGIN = 'https://130-61-181-83.sslip.io/shopfinder';
const WAIT = { '/pools.json': 12000, '/update': 20000, '/health': 12000, '/config.js': 8000, '/places': 25000 };
const TILE_WAIT = 15000;

function json(obj, status) {
  return new Response(JSON.stringify(obj), {
    status, headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' },
  });
}

export async function onRequest({ request, next }) {
  const url = new URL(request.url);
  const isTile = url.pathname.startsWith('/gtile/');
  const wait = isTile ? TILE_WAIT : WAIT[url.pathname];
  if (wait === undefined) return next();
  if (request.method !== 'GET') return json({ ok: false, error: 'GET only' }, 405);
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), wait);
  try {
    const r = await fetch(ORIGIN + url.pathname + url.search, {
      headers: { 'Accept': isTile ? 'image/*' : 'application/json, application/javascript',
                 'X-Client-IP': request.headers.get('CF-Connecting-IP') || '' },
      signal: ctl.signal,
      cf: isTile ? { cacheTtl: 1800, cacheEverything: true } : { cacheTtl: 0 },
    });
    if (!isTile && url.pathname !== '/places' && (r.status === 502 || r.status === 503 || r.status === 504)) {
      return asleep(url.pathname, 'the machine answered ' + r.status);
    }
    const headers = new Headers({ 'Cache-Control': isTile ? 'private, max-age=1800' : 'no-store' });
    headers.set('Content-Type', r.headers.get('Content-Type') || 'application/json; charset=utf-8');
    return new Response(r.body, { status: r.status, headers });
  } catch (e) {
    return asleep(url.pathname, 'the machine did not answer (asleep?)');
  } finally {
    clearTimeout(timer);
  }
}

function asleep(path, why) {
  if (path === '/config.js') {
    return new Response('window.SF_CONFIG = { google: false, googleTiles: false, asleep: true };',
      { status: 200, headers: { 'Content-Type': 'application/javascript; charset=utf-8', 'Cache-Control': 'no-store' } });
  }
  return json({ ok: false, asleep: true, error: why }, 503);
}
