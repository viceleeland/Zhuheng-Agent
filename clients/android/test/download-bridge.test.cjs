const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../assets/download-bridge.js'), 'utf8');

function setup(bytes = new Uint8Array([80, 75, 3, 4])) {
  const listeners = new Map();
  const packets = [], alerts = [], requests = [], tracks = [], sockets = [];
  class Anchor {
    constructor(href, name = '成果.docx') { this.href = href; this.download = name; }
    hasAttribute(key) { return key === 'download'; }
    click() { throw new Error('Native anchor navigation should be intercepted'); }
  }
  class Socket {
    static OPEN = 1;
    constructor(url) { this.url = url; this.closed = false; sockets.push(this); }
    addEventListener() {}
    close() { this.closed = true; }
  }
  const window = {
    WebSocket: Socket,
    addEventListener: (type, fn) => listeners.set(type, fn),
    removeEventListener: type => listeners.delete(type)
  };
  const document = { addEventListener() {} };
  const navigator = { mediaDevices: { getUserMedia: async () => {
    const track = { stopped: false, stop() { this.stopped = true; }, addEventListener() {} };
    tracks.push(track);
    return { getTracks: () => [track] };
  } } };
  const port = { postMessage: raw => {
    packets.push(JSON.parse(raw));
    queueMicrotask(() => port.onmessage({ data: '{"ok":true}' }));
  } };
  const context = {
    window, document, navigator, HTMLAnchorElement: Anchor, location: new URL('https://cw.test/changwei'),
    URL, Uint8Array, Set, JSON, Promise, String, Error, setTimeout, clearTimeout,
    btoa: value => Buffer.from(value, 'binary').toString('base64'),
    alert: value => alerts.push(value),
    localStorage: { getItem: () => 'test-only-token' },
    fetch: async (url, options) => { requests.push({ url, options }); return { ok: true, blob: async () => new Blob([bytes], { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' }) }; }
  };
  vm.runInNewContext(source.replace('__NATIVE_MARKER__', '"test-marker"'), context);
  function connect() { listeners.get('message')({ data: 'test-marker', ports: [port] }); }
  return { window, navigator, listeners, port, packets, alerts, requests, tracks, sockets, Anchor, connect };
}

test('blob DOCX is transferred losslessly in acknowledged chunks and never sends JWT', async () => {
  const bytes = Uint8Array.from({ length: 120000 }, (_, i) => i % 251);
  const env = setup(bytes);
  env.connect();
  await env.window.__cwDownload('blob:https://cw.test/id', '监理日志.docx');
  assert.equal(env.alerts.length, 0);
  assert.equal(env.packets[0].size, 120000);
  assert.equal(env.packets[0].name, '监理日志.docx');
  const chunks = env.packets.filter(p => p.type === 'chunk');
  assert.equal(chunks.length, 3);
  assert.deepEqual(Buffer.concat(chunks.map(p => Buffer.from(p.data, 'base64'))), Buffer.from(bytes));
  assert.equal(env.packets.at(-1).type, 'finish');
  assert.equal(env.requests[0].options.headers.Authorization, undefined);
  assert.ok(!JSON.stringify(env.packets).includes('test-only-token'));
});

test('programmatic anchor.click is intercepted without navigating to revoked blob', async () => {
  const env = setup();
  env.connect();
  new env.Anchor('blob:https://cw.test/result').click();
  for (let i = 0; i < 30; i++) await Promise.resolve();
  assert.equal(env.packets.at(-1).type, 'finish');
});

test('cross-origin, foreign blob, HTTP and file URLs cannot reach native download', async () => {
  const env = setup();
  env.connect();
  for (const url of ['https://evil.test/file', 'blob:https://evil.test/id', 'http://cw.test/file', 'file:///etc/passwd']) await env.window.__cwDownload(url, 'x');
  assert.equal(env.alerts.length, 4);
  assert.equal(env.requests.length, 0);
  assert.equal(env.packets.length, 0);
});

test('same-origin authenticated HTTP attachment keeps the token inside page fetch', async () => {
  const env = setup();
  env.connect();
  await env.window.__cwDownload('https://cw.test/api/changwei/artifacts/a/download', 'a.docx');
  assert.equal(env.requests[0].options.headers.Authorization, 'Bearer test-only-token');
  assert.ok(!JSON.stringify(env.packets).includes('test-only-token'));
});

test('background cleanup stops capture and closes ASR websocket; future capture resumes explicitly', async () => {
  const env = setup();
  await env.navigator.mediaDevices.getUserMedia({ audio: true });
  const socket = new env.window.WebSocket('wss://cw.test/api/changwei/tasks/t/modules/0/transcribe');
  env.window.__cwStopCapture();
  assert.ok(env.tracks[0].stopped);
  assert.ok(socket.closed);
  await assert.rejects(env.navigator.mediaDevices.getUserMedia({ audio: true }), /后台/);
  assert.ok(env.tracks[1].stopped);
  env.window.__cwResumeCapture();
  await env.navigator.mediaDevices.getUserMedia({ audio: true });
  assert.ok(!env.tracks[2].stopped);
});

test('wrong handshake marker does not attach native port', async () => {
  const env = setup();
  env.listeners.get('message')({ data: 'wrong-marker', ports: [env.port] });
  await env.window.__cwDownload('blob:https://cw.test/id', 'x');
  assert.equal(env.packets.length, 0);
  assert.equal(env.alerts.length, 1);
});
