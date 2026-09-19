(function () {
  'use strict';
  const marker = __NATIVE_MARKER__;
  const maxBytes = 30 * 1024 * 1024;
  const streams = new Set();
  const speechSockets = new Set();
  let captureAllowed = true;
  if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
    const capture = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
    navigator.mediaDevices.getUserMedia = async function (constraints) {
      const stream = await capture(constraints);
      if (!captureAllowed) {
        stream.getTracks().forEach(track => track.stop());
        throw new Error('应用已进入后台，请返回后重新启用麦克风。');
      }
      streams.add(stream);
      stream.getTracks().forEach(track => track.addEventListener('ended', () => streams.delete(stream)));
      return stream;
    };
  }
  const NativeSocket = window.WebSocket;
  window.WebSocket = class extends NativeSocket {
    constructor(url, protocols) {
      if (protocols === undefined) super(url); else super(url, protocols);
      const target = new URL(url, location.href);
      if (target.pathname.startsWith('/api/changwei/') && target.pathname.endsWith('/transcribe')) {
        speechSockets.add(this);
        this.addEventListener('close', () => speechSockets.delete(this));
      }
    }
  };
  window.__cwStopCapture = function () {
    captureAllowed = false;
    streams.forEach(stream => stream.getTracks().forEach(track => track.stop()));
    streams.clear();
    speechSockets.forEach(socket => socket.close());
    speechSockets.clear();
  };
  window.__cwResumeCapture = function () { captureAllowed = true; };
  let port = null;
  let running = false;
  let waiting = null;
  let waitTimer = null;
  function exchange(packet) {
    return new Promise((resolve, reject) => {
      if (!port) { reject(new Error('下载通道尚未就绪，请稍后重试。')); return; }
      waiting = { resolve, reject };
      waitTimer = setTimeout(() => { waiting = null; reject(new Error('下载传输超时。')); }, 15000);
      port.postMessage(JSON.stringify(packet));
    });
  }
  function respond(event) {
    let message;
    try { message = JSON.parse(event.data); } catch (_) { return; }
    if (!waiting) return;
    const next = waiting;
    waiting = null;
    clearTimeout(waitTimer);
    if (message.ok) next.resolve();
    else next.reject(new Error(message.error || '无法保存文件。'));
  }
  async function download(url, filename) {
    if (running) { alert('请先完成当前文件的保存。'); return; }
    if (!port) { alert('下载通道尚未就绪，请稍后重试。'); return; }
    const target = new URL(url, location.href);
    if (target.origin !== location.origin || !['blob:', 'https:'].includes(target.protocol)) {
      alert('只能下载当前工程服务的文件。'); return;
    }
    running = true;
    try {
      const headers = {};
      // JWT 始终留在当前 WebView 的同源页面中，原生代码不读取或保存它。
      if (target.protocol === 'https:') {
        const token = localStorage.getItem('user_token');
        if (token) headers.Authorization = 'Bearer ' + token;
      }
      const response = await fetch(target.href, { credentials: 'same-origin', headers });
      if (!response.ok) throw new Error('下载请求未成功，请重新登录后重试。');
      const blob = await response.blob();
      if (blob.size === 0 || blob.size > maxBytes) throw new Error('支持保存 1 字节至 30 MB 的成果文件。');
      await exchange({ type: 'start', name: filename || '工程成果.docx', mime: blob.type, size: blob.size });
      // 逐块确认，避免 JavaScript 一次发完后让原生队列持有整份 base64。
      for (let offset = 0; offset < blob.size; offset += 49152) {
        const bytes = new Uint8Array(await blob.slice(offset, offset + 49152).arrayBuffer());
        let binary = '';
        for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
        await exchange({ type: 'chunk', data: btoa(binary) });
      }
      await exchange({ type: 'finish' });
    } catch (error) {
      if (port) port.postMessage(JSON.stringify({ type: 'cancel' }));
      alert(error.message || '保存失败，请重试。');
    } finally {
      running = false;
    }
  }
  window.addEventListener('message', function connect(event) {
    if (event.data !== marker || event.ports.length !== 1) return;
    port = event.ports[0];
    port.onmessage = respond;
    window.removeEventListener('message', connect);
  });
  // 捕捉程序调用 anchor.click()，其中也包括 Vue 的 blob 下载按钮。
  const originalClick = HTMLAnchorElement.prototype.click;
  HTMLAnchorElement.prototype.click = function () {
    if (this.href.startsWith('blob:') || this.hasAttribute('download')) {
      void download(this.href, this.download);
      return;
    }
    return originalClick.call(this);
  };
  document.addEventListener('click', event => {
    const anchor = event.target.closest && event.target.closest('a');
    if (anchor && (anchor.href.startsWith('blob:') || anchor.hasAttribute('download'))) {
      event.preventDefault();
      void download(anchor.href, anchor.download);
    }
  }, true);
  // 仅供 WebView DownloadListener 回调调用，不暴露任何原生文件系统能力。
  window.__cwDownload = download;
}());
