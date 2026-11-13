/* Phone notifications (web push) for the admin app */
const PUSH = { reg: null, config: null };
const pushSupported = () => 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
const isIOS = () => /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
const isStandalone = () => navigator.standalone === true || window.matchMedia('(display-mode: standalone)').matches;

function pushDeviceName() {
  const ua = navigator.userAgent;
  const dev = /iPhone/.test(ua) ? 'iPhone' : isIOS() ? 'iPad' : /Android/.test(ua) ? 'Android' : /Mac/.test(ua) ? 'Mac' : /Windows/.test(ua) ? 'Windows PC' : 'Device';
  const br = /Edg\//.test(ua) ? 'Edge' : /Chrome\//.test(ua) ? 'Chrome' : /Firefox\//.test(ua) ? 'Firefox' : /Safari\//.test(ua) ? 'Safari' : '';
  return isStandalone() ? `${dev} · home screen app` : (br ? `${dev} · ${br}` : dev);
}
function pushBlockedHelp() { return isIOS() ? 'Notifications are blocked for this app. Allow them in the iPhone\'s Settings → Notifications → LUZ EMS, then reopen the app.' : 'Notifications are blocked for this site. Allow them in the browser\'s site settings (the icon next to the address), then reload.'; }
function b64ToBytes(s) { const p = s.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - s.length % 4) % 4); return Uint8Array.from(atob(p), c => c.charCodeAt(0)); }
function bytesToB64(buf) { return btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, ''); }

async function pushRegister() {
  if (!pushSupported()) return null;
  if (!PUSH.reg) {
    PUSH.reg = await navigator.serviceWorker.register('/sw.js', { scope: '/' });
    navigator.serviceWorker.addEventListener('message', (e) => {
      if (e.data && e.data.type === 'navigate') { const h = (e.data.url.split('#')[1] || '').trim(); if (h) go(h); }
    });
  }
  return PUSH.reg;
}
async function pushCurrent() { const reg = await pushRegister(); return reg ? reg.pushManager.getSubscription() : null; }
async function pushSave(sub) {
  const j = sub.toJSON();
  return api('POST', '/push/subscribe', { endpoint: j.endpoint, p256dh: j.keys.p256dh, auth: j.keys.auth, device: pushDeviceName(), origin: location.origin });
}

/* Called after sign-in: keeps the server copy of this device's subscription fresh. */
async function pushSync() {
  try {
    if (!pushSupported() || Notification.permission !== 'granted') { await pushRegister().catch(() => {}); return; }
    const sub = await pushCurrent(); if (!sub) return;
    const cfg = await api('GET', '/push/config');
    const key = sub.options && sub.options.applicationServerKey ? bytesToB64(sub.options.applicationServerKey) : null;
    if (cfg.public_key && key && key !== cfg.public_key) {   // the server's key changed: subscribe again
      await sub.unsubscribe();
      const fresh = await PUSH.reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64ToBytes(cfg.public_key) });
      await pushSave(fresh);
    } else { await pushSave(sub); }
  } catch (e) { console.warn('push sync', e); }
}

async function enablePush() {
  // Ask first, straight from the tap: iPhone only shows the prompt in direct response to a touch.
  let perm;
  try { perm = await Notification.requestPermission(); } catch (e) { perm = 'denied'; }
  guard(async () => {
    if (perm !== 'granted') throw new Error(perm === 'denied' ? pushBlockedHelp() : 'Notifications were not allowed');
    const reg = await pushRegister(); await navigator.serviceWorker.ready;
    const cfg = await api('GET', '/push/config');
    if (!cfg.available || !cfg.public_key) throw new Error('Push is not available on this server yet');
    let sub = await reg.pushManager.getSubscription();
    if (!sub) sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64ToBytes(cfg.public_key) });
    await pushSave(sub);
    try { await api('POST', '/push/test', { endpoint: sub.endpoint }); toast('Notifications are on for this device. A test is on its way.'); }
    catch (e) { toast('This device is registered, but the test could not be sent: ' + e.message, true); }
    renderPushCard();
  });
}
async function disablePush() { guard(async () => { const sub = await pushCurrent(); if (sub) { await api('POST', '/push/unsubscribe', { endpoint: sub.endpoint }); await sub.unsubscribe(); } toast('Notifications turned off for this device'); renderPushCard(); }); }
async function testPush(all) { guard(async () => { const sub = all ? null : await pushCurrent(); const r = await api('POST', '/push/test', sub ? { endpoint: sub.endpoint } : {}); toast(`Test sent to ${r.sent} device${r.sent === 1 ? '' : 's'}`); renderPushCard(); }); }
async function removePushDevice(id) { guard(async () => { await api('DELETE', `/push/devices/${id}`); toast('Device removed'); renderPushCard(); }); }

async function renderPushCard() {
  const box = $('push-status'); if (!box) return;
  let html = '';
  const cfg = await api('GET', '/push/config').catch(() => null);
  const sub = pushSupported() ? await pushCurrent().catch(() => null) : null;
  const mine = sub && cfg ? cfg.devices.find(d => d.endpoint === sub.endpoint) : null;
  if (!cfg || !cfg.available) {
    html = `<div class="push-note warn">Notifications are not available on this server yet. Ask your developer to install the server update.</div>`;
  } else if (isIOS() && !isStandalone()) {
    html = `<div class="push-note"><strong>On iPhone, notifications only work from the home screen app.</strong>
      <ol><li>In Safari, tap the Share button, then <em>Add to Home Screen</em>. If you added the icon before this update, remove it and add it again.</li>
      <li>Open LUZ EMS from the new icon and sign in.</li><li>Come back to Settings and tap <em>Turn on notifications</em>.</li></ol></div>`;
  } else if (!pushSupported()) {
    html = `<div class="push-note warn">This browser does not support notifications. On iPhone, update to iOS 16.4 or later and open the app from its home screen icon.</div>`;
  } else if (Notification.permission === 'denied') {
    html = `<div class="push-note warn">${pushBlockedHelp()}</div>`;
  } else if (mine) {
    html = `<div class="push-note ok"><strong>On for this device.</strong> Alerts arrive on the lock screen even when the app is closed.</div>
      <div class="actions"><button class="btn btn-secondary btn-sm" onclick="testPush()">Send a test</button><button class="btn btn-ghost btn-sm" onclick="disablePush()">Turn off on this device</button></div>`;
  } else {
    html = `<div class="push-note">Get booking alerts on this device's lock screen, even when the app is closed.</div>
      <div class="actions"><button class="btn btn-primary" onclick="enablePush()">Turn on notifications</button></div>`;
  }
  if (cfg && cfg.devices.length) {
    html += `<div class="push-devices"><div class="tiny muted" style="margin:14px 0 6px">Devices receiving alerts</div>${cfg.devices.map(d => `
      <div class="push-device"><div><strong>${esc(d.device)}</strong>${mine && d.id === mine.id ? ' <span class="muted">(this one)</span>' : ''}
        <div class="tiny ${d.last_error ? '' : 'muted'}" ${d.last_error ? 'style="color:var(--bad)"' : ''}>${d.last_error ? 'Last send failed: ' + esc(d.last_error) : (d.last_success_at ? 'Last delivered ' + fmtDT(d.last_success_at) : 'Added ' + fmtDT(d.created_at))}</div></div>
        <button class="btn btn-ghost btn-xs" onclick="removePushDevice(${d.id})">Remove</button></div>`).join('')}</div>`;
  }
  box.innerHTML = html;
}
