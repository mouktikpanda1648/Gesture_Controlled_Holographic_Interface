/** Operator console: status, gesture feedback, hand skeleton and activity log. */
const $ = (id) => document.getElementById(id);

const CONNECTIONS = [
  [0,1],[1,2],[2,3],[3,4],[0,5],[5,6],[6,7],[7,8],[5,9],[9,10],[10,11],[11,12],
  [9,13],[13,14],[14,15],[15,16],[13,17],[17,18],[18,19],[19,20],[0,17],
];

const GESTURE_LABEL = {
  NONE: 'NO HAND', UNKNOWN: 'UNRECOGNISED', FIST: 'FIST (idle)',
  POINT: 'POINT', THUMBS_UP: 'THUMBS UP', OPEN_PALM: 'OPEN PALM',
};

function setText(el, text) { if (el.textContent !== text) el.textContent = text; }
function setDot(el, s) { if (el.dataset.s !== s) el.dataset.s = s; }

export class Hud {
  #ctx = $('hand').getContext('2d');
  #live = $('live');
  #lastAnnounce = '';

  setBackend(online) {
    setDot($('dot-backend'), online ? 'ok' : 'bad');
    setText($('val-backend'), online ? 'online' : 'offline');
  }

  setHello({ version, simulate, inject }) {
    setText($('version'), `v${version}`);
    $('sim-badge').hidden = !simulate;
    document.body.dataset.inject = String(Boolean(inject));
  }

  render(state) {
    const { camera, link, hand } = state;

    const camOk = camera.status === 'ok' || camera.status === 'off';
    setDot($('dot-camera'), camera.status === 'ok' ? 'ok' : camera.status === 'off' ? 'warn' : camera.status === 'error' ? 'bad' : 'warn');
    setText($('val-camera'), camera.status === 'ok' ? `${camera.fps.toFixed(0)} fps` : camera.status === 'off' ? 'simulated' : camera.status);
    void camOk;

    setDot($('dot-link'), link.status === 'connected' ? 'ok' : link.status === 'degraded' || link.status === 'connecting' ? 'warn' : 'bad');
    setText($('val-link'), link.status === 'connected' ? `${link.port ?? ''}${link.firmware ? ` · FW ${link.firmware}` : ''}`.trim() : link.status);

    setDot($('dot-led'), link.led === 'on' ? 'on' : link.led === 'off' ? 'ok' : 'warn');
    setText($('val-led'), link.pending ? 'sending…' : link.led.toUpperCase());

    setText($('gesture-name'), GESTURE_LABEL[hand.gesture] ?? hand.gesture);
    const bar = $('gesture-bar');
    bar.style.setProperty('--p', String(hand.progress));
    bar.setAttribute('aria-valuenow', String(Math.round(hand.progress * 100)));
    for (const li of $('guide').children) {
      const active = li.dataset.g === hand.gesture;
      if (li.dataset.active !== String(active)) li.dataset.active = String(active);
    }
    this.#drawHand(hand.landmarks);

    const announce = `LED ${link.led}`;
    if (announce !== this.#lastAnnounce) { this.#lastAnnounce = announce; this.#live.textContent = announce; }
  }

  #drawHand(lms) {
    const ctx = this.#ctx, { width: w, height: h } = ctx.canvas;
    ctx.clearRect(0, 0, w, h);
    if (!lms) {
      ctx.fillStyle = 'rgba(127,154,166,.7)';
      ctx.font = '13px system-ui, sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('no hand detected', w / 2, h / 2);
      return;
    }
    ctx.lineWidth = 2;
    ctx.strokeStyle = 'rgba(77,232,255,.85)';
    ctx.lineCap = 'round';
    ctx.beginPath();
    for (const [a, b] of CONNECTIONS) {
      ctx.moveTo(lms[a][0] * w, lms[a][1] * h);
      ctx.lineTo(lms[b][0] * w, lms[b][1] * h);
    }
    ctx.stroke();
    ctx.fillStyle = '#fff';
    for (const [x, y] of lms) {
      ctx.beginPath(); ctx.arc(x * w, y * h, 3, 0, Math.PI * 2); ctx.fill();
    }
  }

  log({ level, msg, t }) {
    const list = $('log');
    const li = document.createElement('li');
    li.dataset.l = level;
    const time = document.createElement('time');
    time.textContent = new Date(t * 1000).toLocaleTimeString([], { hour12: false });
    const span = document.createElement('span');
    span.textContent = msg;
    li.append(time, span);
    list.append(li);
    while (list.children.length > 60) list.firstChild.remove();
    list.scrollTop = list.scrollHeight;
  }
}
