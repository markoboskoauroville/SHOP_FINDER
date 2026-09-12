// functions/_middleware.js: the pages.dev side of the Shop & Pool Finder.
//
// Cloudflare serves the app itself (public/index.html) as a static file, so the page opens even
// while the machine sleeps. Two addresses are relayed to the Oracle machine, through Caddy, with the
// door key only this function knows (the Pages secrets ORIGIN and DOOR_KEY, set by deploy.sh):
//     /pools.json   the hours update_pools.py wrote on the machine
//     /update       start the updater (it answers at once; the page polls /health)
//     /health       when pools.json was written, and whether a run is going
// and /config.js carries the Google key (the secret GOOGLE_MAPS_KEY) for the paid map option.
// When the machine does not answer in time the page gets {ok:false, asleep:true} and shows the
// pools with live Google hours instead. Everything else falls through to the static files.

const RELAY = { '/pools.json': 12000, '/update': 20000, '/health': 12000 };  // path -> the time we wait, ms
const MACHINE_PREFIX = '/shopfinder';

function json(obj, status) {
  return new Response(JSON.stringify(obj), {
    status, headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' },
  });
}

export async function onRequest({ request, env, next }) {
  const url = new URL(request.url);
  if (url.pathname === '/config.js') {   // the paid option's key, from the Pages secret GOOGLE_MAPS_KEY
    return new Response('window.SF_CONFIG = ' + JSON.stringify({ googleMapsKey: env.GOOGLE_MAPS_KEY || '' }) + ';',
      { headers: { 'Content-Type': 'application/javascript; charset=utf-8', 'Cache-Control': 'no-store' } });
  }
  const wait = RELAY[url.pathname];
  if (wait === undefined) return next();
  if (request.method !== 'GET') return json({ ok: false, error: 'GET only' }, 405);
  if (!env.ORIGIN || !env.DOOR_KEY) return json({ ok: false, error: 'the door has no ORIGIN and DOOR_KEY secrets yet (deploy.sh secrets)' }, 503);
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), wait);
  try {
    const r = await fetch(env.ORIGIN + MACHINE_PREFIX + url.pathname, {
      headers: { 'X-Door-Key': env.DOOR_KEY, 'Accept': 'application/json' },
      signal: ctl.signal,
      cf: { cacheTtl: 0 },
    });
    if (r.status === 502 || r.status === 503 || r.status === 504) {
      return json({ ok: false, asleep: true, error: 'the machine answered ' + r.status }, 503);
    }
    const headers = new Headers({ 'Cache-Control': 'no-store' });
    headers.set('Content-Type', r.headers.get('Content-Type') || 'application/json; charset=utf-8');
    return new Response(r.body, { status: r.status, headers });
  } catch (e) {
    return json({ ok: false, asleep: true, error: 'the machine did not answer (asleep?)' }, 503);
  } finally {
    clearTimeout(timer);
  }
}
