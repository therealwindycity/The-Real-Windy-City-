/* lock.js — password gate + in-browser decryption of the Atlas dataset
 *
 * Two layers live here:
 *   1. the dataset is ciphertext (AES-256-GCM, key derived from the passphrase
 *      with PBKDF2-HMAC-SHA256) — see tools/lock_atlas.py;
 *   2. this module turns that ciphertext back into data in the browser, in
 *      memory only. Nothing is written anywhere, and the passphrase itself is
 *      never stored — with "remember this tab" we keep the *derived key* in
 *      sessionStorage, which dies with the tab.
 *
 * If atlas/enc/manifest.json is not present the app runs in plain mode against
 * atlas/data/ (local development). Append ?plain=1 to force plain mode.
 */
'use strict';

const Lock = {
  active: false,        // encrypted dataset detected
  unlocked: false,
  key: null,            // CryptoKey (AES-GCM)
  toc: null,            // { files: {logical: blob}, exports: [...], sha256: {...} }
  manifest: null,
  cache: new Map(),     // logical name -> text
  _pending: null,       // resolves the boot promise once unlocked

  SESSION_KEY: 'paradox-atlas-key',

  /* ------------------------------------------------------------ detection */
  async probe() {
    const forcedPlain = /[?&]plain=1\b/.test(location.search);
    try {
      const res = await fetch('enc/manifest.json', { cache: 'no-cache' });
      if (res.ok) {
        this.manifest = await res.json();
        this.active = !forcedPlain;
        if (forcedPlain) this.active = false;
      }
    } catch { /* no manifest → plain dataset */ }
    if (!this.active) return false;
    // A key remembered for this tab is reused without prompting.
    if (await this._restoreSessionKey()) {
      this.unlocked = true;
      return true;
    }
    return true; // active but still locked
  },

  /* ------------------------------------------------------------ key handling */
  _b64(buf) {
    return btoa(String.fromCharCode(...new Uint8Array(buf)));
  },
  _unb64(str) {
    return Uint8Array.from(atob(str), (c) => c.charCodeAt(0));
  },
  async _deriveKey(password, salt) {
    if (!(window.crypto && crypto.subtle)) {
      throw new Error('This browser has no WebCrypto here. Open the Atlas over https:// or http://localhost — '
        + 'browsers only expose crypto.subtle in a secure context.');
    }
    const base = await crypto.subtle.importKey('raw', new TextEncoder().encode(password), 'PBKDF2', false, ['deriveKey']);
    return crypto.subtle.deriveKey(
      { name: 'PBKDF2', salt, iterations: (this.manifest?.kdf?.iterations) || 600000, hash: 'SHA-256' },
      base, { name: 'AES-GCM', length: 256 }, true, ['decrypt']);
  },
  async _restoreSessionKey() {
    try {
      const raw = sessionStorage.getItem(this.SESSION_KEY);
      if (!raw) return false;
      const saved = JSON.parse(raw);
      if (saved.salt !== this.manifest.kdf.salt) return false;
      this.key = await crypto.subtle.importKey('raw', this._unb64(saved.key), 'AES-GCM', true, ['decrypt']);
      await this._loadToc();
      return true;
    } catch {
      sessionStorage.removeItem(this.SESSION_KEY);
      return false;
    }
  },
  async _rememberSessionKey() {
    try {
      const raw = await crypto.subtle.exportKey('raw', this.key);
      sessionStorage.setItem(this.SESSION_KEY, JSON.stringify({ salt: this.manifest.kdf.salt, key: this._b64(raw) }));
    } catch { /* export can fail on some browsers; the key still works for this page */ }
  },
  forget() {
    try { sessionStorage.removeItem(this.SESSION_KEY); } catch {}
    this.key = null;
    this.toc = null;
    this.unlocked = false;
    this.cache.clear();
  },
  async _loadToc() {
    const headName = this.manifest.head || 'blobs/head.bin';
    const res = await fetch('enc/' + headName, { cache: 'force-cache' });
    if (!res.ok) throw new Error('encrypted index missing (' + res.status + ')');
    const blob = new Uint8Array(await res.arrayBuffer());
    const plain = await this._decryptBytes('head', blob);
    this.toc = JSON.parse(new TextDecoder().decode(plain));
  },

  /* ------------------------------------------------------------ decryption */
  async _decryptBytes(name, blob) {
    const nonce = blob.subarray(0, 12);
    const body = blob.subarray(12);
    const plain = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: nonce, additionalData: new TextEncoder().encode(name) }, this.key, body);
    const view = new DataView(plain);
    const size = view.getUint32(0, false);
    return new Uint8Array(plain, 4, size);
  },

  async unlock(password, remember = false) {
    const salt = this._unb64(this.manifest.kdf.salt);
    this.key = await this._deriveKey(password, salt);
    await this._loadToc();               // throws if the passphrase is wrong
    this.unlocked = true;
    if (remember) await this._rememberSessionKey();
    return true;
  },

  /* ------------------------------------------------------------ data access */
  async text(logical) {
    if (this.cache.has(logical)) return this.cache.get(logical);
    let out;
    if (!this.active) {
      const res = await fetch('data/' + logical, { cache: 'no-cache' });
      if (!res.ok) throw new Error(logical + ' ' + res.status);
      out = await res.text();
    } else {
      if (!this.unlocked) throw new Error('locked');
      const blobName = this.toc?.files?.[logical];
      if (!blobName) throw new Error('not in the encrypted index: ' + logical);
      const res = await fetch('enc/blobs/' + blobName, { cache: 'force-cache' });
      if (!res.ok) throw new Error(blobName + ' ' + res.status);
      const plain = await this._decryptBytes(logical, new Uint8Array(await res.arrayBuffer()));
      out = new TextDecoder().decode(plain);
    }
    this.cache.set(logical, out);
    return out;
  },
  async json(logical) {
    return JSON.parse(await this.text(logical));
  },
  async unlockedThreadIds() {
    if (!this.active || !this.toc) return null;
    return Object.keys(this.toc.files).filter((n) => n.startsWith('threads/')).map((n) => n.slice(8, -5));
  },
  exportsIndex() {
    return (this.toc?.exports || []).slice().sort((a, b) => a.name.localeCompare(b.name));
  },
  async downloadExport(name, suggested) {
    const text = await this.text('exports/' + name);
    download(suggested || name, text, name.endsWith('.json') ? 'application/json' : 'text/plain');
  },

  /* ------------------------------------------------------------ lock screen */
  ensureScreen() {
    let host = document.getElementById('lockscreen');
    if (host) return host;
    host = document.createElement('div');
    host.id = 'lockscreen';
    host.innerHTML = `
      <form class="lockbox" id="lockform" autocomplete="off">
        <div class="lockglyph">🔒</div>
        <h1>Paradox Atlas is encrypted</h1>
        <p class="muted">${this.manifest?.files ?? ''} files · AES-256-GCM · PBKDF2-SHA256 ${((this.manifest?.kdf?.iterations || 0) / 1000).toFixed(0)}k
          ${this.manifest?.created ? ' · locked ' + this.manifest.created.slice(0, 10) : ''}</p>
        <input id="lockpass" type="password" placeholder="Passphrase" autocomplete="current-password" spellcheck="false">
        <label class="lockrow"><input type="checkbox" id="lockremember" checked> keep me unlocked in this tab only</label>
        <button class="btn primary" id="lockgo" type="submit">Unlock</button>
        <div class="lockerr" id="lockerr"></div>
        <p class="locknote">Decryption happens in your browser. The passphrase is never sent anywhere and never stored —
          everything you see exists only in this page's memory.</p>
      </form>`;
    document.body.append(host);
    const form = host.querySelector('#lockform');
    const input = host.querySelector('#lockpass');
    const err = host.querySelector('#lockerr');
    const go = host.querySelector('#lockgo');
    setTimeout(() => input.focus(), 30);
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      if (!input.value) return;
      go.disabled = true;
      go.textContent = 'Decrypting…';
      err.textContent = '';
      try {
        await this.unlock(input.value, host.querySelector('#lockremember').checked);
        host.remove();
        document.documentElement.classList.remove('locking');
        if (this._pending) { const r = this._pending; this._pending = null; r(true); }
        // Unlocking after a re-lock (or after a failed first boot) still has to
        // rebuild the views — the dataset is loaded fresh into memory.
        if (typeof Atlas !== 'undefined' && Atlas && !Atlas.data && typeof reloadData === 'function') {
          await reloadData();
        }
      } catch (ex) {
        // A wrong key surfaces as a DOMException named OperationError whose
        // message is deliberately vague ("operation-specific reason") — say
        // something useful instead of relaying that.
        const bad = /OperationError|Operation failed|decrypt/i.test(`${ex.name || ''} ${ex.message || ''}`);
        err.textContent = bad
          ? 'That passphrase did not decrypt the archive. Check it (the words are joined with hyphens) and try again.'
          : (ex.message || 'Unlock failed.');
        input.select();
      } finally {
        go.disabled = false;
        go.textContent = 'Unlock';
      }
    });
    return host;
  },

  /* Called from boot: resolves true once the dataset is available. */
  prompt() {
    if (this.unlocked) return Promise.resolve(true);
    this.ensureScreen();
    return new Promise((resolve) => { this._pending = resolve; });
  },

  /* Re-lock without reloading: every decrypted byte is dropped — the dataset, the
     transcript cache, any built packet and every rendered passage. */
  lockNow() {
    this.forget();
    document.documentElement.classList.add('locking');
    try {
      Atlas.data = null;
      Atlas.threadCache.clear();
      if (typeof Handoff !== 'undefined') { Handoff.last = null; Handoff.previewText = ''; }
      const draw = document.getElementById('drawer');
      if (draw) draw.classList.remove('open');
      for (const id of ['drawerBody', 'storyBody', 'tlBody', 'ledgerTable', 'coverageBody', 'hoFiles', 'hoPreview', 'queue', 'legend', 'inspector', 'storyInspector']) {
        const node = document.getElementById(id);
        if (node) node.innerHTML = '';
      }
    } catch { /* a partially booted page still locks */ }
    this.prompt();
  },
};
