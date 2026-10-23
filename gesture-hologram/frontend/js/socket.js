/** WebSocket client with exponential-backoff reconnect. Emits one event per message `type`. */
export class BackendSocket extends EventTarget {
  #url; #ws = null; #retry = 0; #timer = null; #closed = false;

  constructor(path = '/ws') {
    super();
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    this.#url = `${proto}//${location.host}${path}`;
  }

  get connected() { return this.#ws?.readyState === WebSocket.OPEN; }

  connect() {
    this.#closed = false;
    const ws = new WebSocket(this.#url);
    this.#ws = ws;
    ws.addEventListener('open', () => { this.#retry = 0; this.dispatchEvent(new Event('open')); });
    ws.addEventListener('message', (e) => {
      let msg;
      try { msg = JSON.parse(e.data); } catch { return; }
      if (msg && typeof msg.type === 'string') this.dispatchEvent(new CustomEvent(msg.type, { detail: msg }));
    });
    ws.addEventListener('close', () => {
      this.dispatchEvent(new Event('close'));
      if (this.#closed) return;
      const delay = Math.min(5000, 400 * 2 ** this.#retry++);
      this.#timer = setTimeout(() => this.connect(), delay);
    });
    ws.addEventListener('error', () => ws.close());
  }

  send(payload) {
    if (this.connected) this.#ws.send(JSON.stringify(payload));
  }

  close() {
    this.#closed = true;
    clearTimeout(this.#timer);
    this.#ws?.close();
  }
}
