#!/usr/bin/env python3
"""Polite, bounded, read-only public city mirror. Python standard library only.

Never publishes upstream HTML/scripts: pages are extracted and escaped into
independent archive templates. State survives via a GitHub Actions cache.
"""
from __future__ import annotations
import argparse
from collections import deque
from datetime import datetime, timezone
import hashlib
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse as urlparse
import urllib.request
import urllib.robotparser
import xml.etree.ElementTree as ET


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temp.replace(path)


def key(url):
    return hashlib.sha256(url.encode()).hexdigest()[:24]


def fresh_state():
    return {'records': {}, 'changes': []}


class PageParser(HTMLParser):
    """Extract readable text and links, never active markup or form controls."""
    blocked = {'script', 'style', 'noscript', 'iframe', 'svg', 'form', 'template'}
    blocks = {'p', 'div', 'section', 'article', 'main', 'header', 'footer', 'li',
              'h1', 'h2', 'h3', 'h4', 'tr', 'br', 'nav'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.suppressed = []
        self.parts = []
        self.title_parts = []
        self.in_title = False
        self.links = []
        self.link = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in self.blocked:
            self.suppressed.append(tag)
        if self.suppressed:
            return
        if tag == 'title':
            self.in_title = True
        if tag in self.blocks:
            self.parts.append('\n')
        if tag == 'a' and attrs.get('href'):
            self.link = [attrs['href'], []]
        if tag == 'img' and attrs.get('alt'):
            self.parts.append(' ' + attrs['alt'] + ' ')

    def handle_endtag(self, tag):
        if self.suppressed:
            if tag == self.suppressed[-1]:
                self.suppressed.pop()
            return
        if tag == 'title':
            self.in_title = False
        if tag in self.blocks:
            self.parts.append('\n')
        if tag == 'a' and self.link:
            self.links.append((self.link[0], ''.join(self.link[1]).strip()))
            self.link = None

    def handle_data(self, data):
        if self.suppressed:
            return
        if self.in_title:
            self.title_parts.append(data)
        else:
            self.parts.append(data)
        if self.link:
            self.link[1].append(data)

    @property
    def text(self):
        return '\n'.join(line for line in (re.sub(r'\s+', ' ', x).strip()
                         for x in ''.join(self.parts).splitlines()) if line)

    @property
    def title(self):
        return re.sub(r'\s+', ' ', ''.join(self.title_parts)).strip()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Mirror:
    def __init__(self, config, state_dir, output_dir, transport=None, sleep=time.sleep):
        self.config = config
        self.origin = config['origin'].rstrip('/')
        parsed = urlparse.urlsplit(self.origin)
        if parsed.scheme != 'https' or parsed.netloc != 'www.cheyennecity.org' or parsed.path:
            raise ValueError('Only https://www.cheyennecity.org is an allowed crawl origin')
        self.state_dir = Path(state_dir)
        self.output = Path(output_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.state_dir / 'state.json'
        self.state = self._load_state()
        self.records = self.state['records']
        self.archive_bytes = sum(r.get('source_bytes', 0) for r in self.records.values())
        self.transport = transport or self.http
        self.sleep = sleep
        self.last_request = None
        self.deadline = time.monotonic() + config.get('max_run_seconds', 5400)
        self.delay = max(3, config['delay_seconds'])
        self.bytes = 0
        self.robots = None
        self.report = {'started_at': now(), 'status': 'running', 'checked': 0,
                       'updated': 0, 'unchanged': 0, 'blocked': 0, 'errors': [],
                       'excluded': 0, 'bytes_downloaded': 0, 'pending': 0}

    def _load_state(self):
        """Load the persisted snapshot, quarantining it if it fails validation.

        A restored Actions cache can be truncated or otherwise unreadable. Rather
        than failing the whole publish (or silently discarding history), the bad
        file is moved outside the cached directory and rendering proceeds from an
        explicit empty state with a visible recovery note. The previous cache
        entries still exist server-side, so a later crawl can rebuild from them.
        """
        if not self.state_path.exists():
            return fresh_state()
        try:
            state = json.loads(self.state_path.read_text())
            if not isinstance(state, dict) or not isinstance(state.get('records'), dict):
                raise ValueError('snapshot shape invalid: expected {"records": {...}}')
            state.setdefault('changes', [])
            if not isinstance(state['changes'], list):
                raise ValueError('snapshot shape invalid: expected "changes" to be a list')
            return state
        except (ValueError, OSError, UnicodeDecodeError) as error:
            quarantine = self.state_dir.parent / 'city-mirror-quarantine'
            quarantine.mkdir(parents=True, exist_ok=True)
            stamp = now().replace(':', '').replace('+', '')
            salvaged = quarantine / f'state-{stamp}.json'
            try:
                self.state_path.replace(salvaged)
            except OSError:
                salvaged = None
            state = fresh_state()
            state['state_recovery'] = {
                'quarantined_at': now(),
                'reason': f'Previous snapshot failed validation ({error}); rendering an explicit empty mirror.',
                'quarantined_file': salvaged.name if salvaged else None,
            }
            return state

    def canonical(self, raw, base=None):
        try:
            p = urlparse.urlsplit(urlparse.urljoin(base or self.origin + '/', raw))
            if p.scheme not in ('https', 'http') or p.username or p.password:
                return None
            if p.hostname != 'www.cheyennecity.org' or p.port not in (None, 80, 443):
                return None
            path = p.path or '/'
            decoded = urlparse.unquote(path)
            if any(re.search(pattern, decoded, re.I) for pattern in self.config['exclude_path_patterns']):
                return None
            # Drop tracking only; preserve document identifiers and pagination.
            query = [(k, v) for k, v in urlparse.parse_qsl(p.query, keep_blank_values=True)
                     if not k.lower().startswith('utm_') and k.lower() not in ('fbclid', 'gclid')]
            if len(query) > 8 or len(p.query) > 1000:
                return None
            return self.origin + urlparse.quote(path, safe="/%;:@!$&'()*+,=-._~") + ('?' + urlparse.urlencode(sorted(query)) if query else '')
        except (ValueError, TypeError):
            return None

    def http(self, url, headers):
        req = urllib.request.Request(url, headers=headers, method='GET')
        opener = urllib.request.build_opener(NoRedirect())
        try:
            response = opener.open(req, timeout=self.config['timeout_seconds'])
        except urllib.error.HTTPError as error:
            response = error
        with response:
            # Check headers before downloading large files; cap streamed reads too.
            cap = min(self.config['max_file_bytes'], self.config['max_bytes_per_run'] - self.bytes)
            length = response.headers.get('Content-Length')
            if length and int(length) > cap:
                raise ValueError('Response exceeds download budget')
            body = response.read(cap + 1)
            if len(body) > cap:
                self.bytes += len(body)
                raise ValueError('Response exceeds download budget')
            return response.status, {k.lower(): v for k, v in response.headers.items()}, body

    def request(self, url, headers=None, robot_request=False):
        headers = {'User-Agent': self.config['user_agent'], 'Accept-Encoding': 'identity', **(headers or {})}
        for redirect in range(6):
            if self.canonical(url) != url:
                raise ValueError('URL outside allowed scope')
            if not robot_request and (not self.robots or not self.robots.can_fetch(self.config['user_agent'], url)):
                raise PermissionError('Disallowed by robots.txt')
            if self.bytes >= self.config['max_bytes_per_run']:
                raise ValueError('Run download budget exhausted')
            for attempt in range(3):
                if time.monotonic() >= self.deadline:
                    raise TimeoutError('Run time budget exhausted')
                if self.last_request is not None:
                    self.sleep(max(0, self.delay - (time.monotonic() - self.last_request)))
                self.last_request = time.monotonic()
                status, response_headers, body = self.transport(url, headers)
                self.bytes += len(body)
                if status not in (429, 503) or attempt == 2:
                    break
                retry = response_headers.get('retry-after', '')
                self.sleep(min(120, max(self.delay, int(retry) if retry.isdigit() else 15 * (attempt + 1))))
            if status in (301, 302, 303, 307, 308):
                destination = self.canonical(response_headers.get('location', ''), url)
                if not destination or destination == url:
                    raise ValueError('Redirect outside allowed scope or redirect loop')
                url = destination
                headers = {'User-Agent': self.config['user_agent'], 'Accept-Encoding': 'identity'}
                continue
            return status, response_headers, body, url
        raise ValueError('Too many redirects')

    def load_robots(self):
        status, _, body, _ = self.request(self.origin + '/robots.txt', robot_request=True)
        self.robots = urllib.robotparser.RobotFileParser()
        if status == 404:
            self.robots.parse([])
        elif status == 200:
            self.robots.parse(body.decode('utf-8', errors='replace').splitlines())
        else:
            raise RuntimeError(f'robots.txt HTTP {status}; crawl stopped (fail closed)')
        delay = self.robots.crawl_delay(self.config['user_agent'])
        rate = self.robots.request_rate(self.config['user_agent'])
        self.delay = max(self.delay, delay or 0, rate.seconds / rate.requests if rate and rate.requests else 0)
        return self.robots.site_maps() or [self.origin + '/sitemap.xml']

    def sitemap_urls(self, seeds):
        maps = deque(seeds)
        visited = set()
        pages = []
        while maps and len(visited) < self.config['max_sitemaps'] and time.monotonic() < self.deadline:
            url = self.canonical(maps.popleft())
            if not url or url in visited:
                continue
            visited.add(url)
            try:
                status, _, body, _ = self.request(url)
                if status != 200:
                    continue
                tree = ET.fromstring(body)
                is_index = tree.tag.split('}')[-1] == 'sitemapindex'
                for element in tree.iter():
                    if element.tag.split('}')[-1] == 'loc' and element.text:
                        candidate = self.canonical(element.text.strip())
                        if candidate:
                            (maps if is_index else pages).append(candidate)
            except Exception as error:
                self.report['errors'].append({'url': url, 'error': str(error)[:250]})
        return pages

    def crawl_page(self, url):
        old = self.records.get(url, {})
        headers = {}
        if old.get('etag'):
            headers['If-None-Match'] = old['etag']
        if old.get('last_modified'):
            headers['If-Modified-Since'] = old['last_modified']
        status, meta, body, final = self.request(url, headers)
        self.report['checked'] += 1
        if status == 304 and old:
            old['checked_at'] = now()
            old['source_status'] = 304
            self.report['unchanged'] += 1
            return [link[0] for link in old.get('links', [])]
        if status != 200:
            if old:
                old['source_status'] = status
                old['checked_at'] = now()
            raise RuntimeError(f'HTTP {status}; last archived version retained if available')
        kind = meta.get('content-type', '').split(';')[0].strip().lower()
        supported = kind in ('text/html', 'application/xhtml+xml') or kind in self.config['document_types']
        if supported and self.archive_bytes - old.get('source_bytes', 0) + len(body) > self.config.get('max_archive_bytes', 400000000):
            raise ValueError('Total archive budget exhausted; increase deliberately or narrow scope')
        record = {'url': url, 'final_url': final, 'checked_at': now(), 'fetched_at': now(),
                  'source_status': status, 'etag': meta.get('etag'), 'last_modified': meta.get('last-modified'),
                  'sha256': hashlib.sha256(body).hexdigest(), 'content_type': kind, 'source_bytes': len(body)}
        if kind in ('text/html', 'application/xhtml+xml'):
            charset = re.search(r'charset=["\']?([\w-]+)', meta.get('content-type', ''), re.I)
            try:
                text = body.decode(charset.group(1) if charset else 'utf-8', errors='replace')
            except LookupError:
                text = body.decode('utf-8', errors='replace')
            parser = PageParser()
            parser.feed(text)
            links = []
            for href, title in parser.links:
                absolute = urlparse.urljoin(final, href)
                if urlparse.urlsplit(absolute).scheme not in ('https', 'http'):
                    continue
                links.append([absolute, title or absolute])
            record.update(title=parser.title or urlparse.urlsplit(final).path, text=parser.text,
                          links=links, path='pages/' + key(url) + '.html', kind='page')
        elif kind in self.config['document_types']:
            if kind == 'application/pdf' and not body.startswith(b'%PDF-'):
                raise ValueError('PDF content signature mismatch')
            name = key(url) + self.config['document_types'][kind]
            dest = self.state_dir / 'documents' / name
            dest.parent.mkdir(exist_ok=True)
            dest.write_bytes(body)
            record.update(title=urlparse.unquote(urlparse.urlsplit(final).path.rsplit('/', 1)[-1]) or 'Document',
                          path='documents/' + name, kind='document', links=[], text='')
        else:
            self.report['excluded'] += 1
            return []
        if old.get('sha256') == record['sha256']:
            self.report['unchanged'] += 1
        else:
            self.report['updated'] += 1
            self.state['changes'].append({'url': url, 'observed_at': now(),
                                          'before': old.get('sha256'), 'after': record['sha256']})
        self.archive_bytes += len(body) - old.get('source_bytes', 0)
        self.records[url] = record
        return [link[0] for link in record['links']]

    def run(self):
        queue = deque()
        visited = set()
        scheduled = set()
        def enqueue(raw):
            url = self.canonical(raw)
            if url and url not in scheduled:
                scheduled.add(url)
                queue.append(url)
        try:
            sitemaps = self.load_robots()
            # Carry unfinished work ahead of already checked records to avoid
            # permanently starving a site larger than the per-run budget.
            for url in self.state.get('pending', []):
                enqueue(url)
            for seed in self.config['seeds']:
                enqueue(seed)
            for url in self.sitemap_urls(sitemaps):
                enqueue(url)
            for url in sorted(self.records, key=lambda u: self.records[u].get('checked_at', '')):
                enqueue(url)
            while queue and len(visited) < self.config['max_pages_per_run'] and self.bytes < self.config['max_bytes_per_run'] and time.monotonic() < self.deadline:
                url = queue.popleft()
                visited.add(url)
                try:
                    for link in self.crawl_page(url):
                        enqueue(link)
                except PermissionError:
                    self.report['blocked'] += 1
                    if url in self.records:
                        self.records[url]['source_status'] = 'robots-blocked'
                except Exception as error:
                    self.report['errors'].append({'url': url, 'error': str(error)[:250]})
            self.state['pending'] = list(queue)
            self.report['pending'] = len(queue)
            self.report['status'] = 'partial' if queue or self.report['errors'] else 'completed'
            if self.report['checked']:
                self.state['last_successful_fetch_run'] = now()
            if self.report['status'] == 'completed':
                self.state['last_completed_run'] = now()
        except Exception as error:
            self.report['status'] = 'failed'
            self.report['errors'].append({'url': self.origin, 'error': str(error)[:250]})
        self.report['finished_at'] = now()
        self.report['bytes_downloaded'] = self.bytes
        self.state['latest_run'] = self.report
        if self.report.get('checked') and 'state_recovery' in self.state:
            # Sources were actually re-checked, so the snapshot is rebuilt from
            # real fetches rather than empty. Keep the incident as history.
            self.state['last_recovery'] = self.state.pop('state_recovery')
        save_json(self.state_path, self.state)
        self.render()
        return self.report

    def frame(self, title, body, nested=False):
        prefix = '../' if nested else ''
        return f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex">
<title>{html.escape(title)} | Independent Cheyenne Mirror</title>
<link rel="stylesheet" href="{prefix}../city.css"></head><body>
<div class="notice">INDEPENDENT ARCHIVE — NOT THE CITY OF CHEYENNE <span>Archived information may be incomplete or out of date.</span></div>
<header><div><p class="eyebrow">THE REAL WINDY CITY</p><h1>{html.escape(title)}</h1></div><a href="https://www.cheyennecity.org/">Official city website ↗</a></header>
<nav aria-label="Mirror navigation"><a href="{prefix}../">Community records</a><a href="{prefix}index.html">Mirror directory</a><a href="{prefix}status.html">Sync status &amp; changes</a></nav>
<main style="padding:32px 20px">{body}</main><footer>Independent read-only archive. Use official services for transactions, deadlines and current notices.</footer></body></html>'''

    def render(self):
        self.output.mkdir(parents=True, exist_ok=True)
        (self.output / 'pages').mkdir(exist_ok=True)
        (self.output / 'documents').mkdir(exist_ok=True)
        entries = []
        for url, record in sorted(self.records.items()):
            if record['kind'] == 'document':
                source = self.state_dir / record['path']
                if not source.exists():
                    continue
                (self.output / record['path']).write_bytes(source.read_bytes())
            else:
                links = []
                seen = set()
                for href, title in record['links']:
                    target = self.canonical(href)
                    matched = self.records.get(target)
                    local = matched and (matched['kind'] == 'page' or (self.state_dir / matched['path']).exists())
                    resolved = '../' + matched['path'] if local else href
                    if resolved in seen:
                        continue
                    seen.add(resolved)
                    links.append(f'<li><a href="{html.escape(resolved, quote=True)}">{html.escape(title)}</a> <small>{"Archived" if local else "External / official source"}</small></li>')
                body = f'''<section class="note"><p><strong>Archived copy, not an official notice.</strong> Forms, scripts, embedded media and interactive controls have been removed. Links to services open the original site.</p>
<p><a href="{html.escape(url, quote=True)}">View official source ↗</a><br>Retrieved: {record['fetched_at']}<br>Last checked: {record['checked_at']} · Source status: {record['source_status']}</p>
<details><summary>Source fingerprint (SHA-256)</summary><code style="overflow-wrap:anywhere">{record['sha256']}</code></details></section>
<article><pre style="max-height:none">{html.escape(record['text'])}</pre></article><section><h2>Links from this page</h2><ul>{''.join(links)}</ul></section>'''
                (self.output / record['path']).write_text(self.frame(record['title'], body, True))
            entries.append({k: record[k] for k in ('title', 'url', 'path', 'kind', 'fetched_at', 'source_status')})
        save_json(self.output / 'catalog.json', entries)
        save_json(self.output / 'status.json', {k: v for k, v in self.state.items() if k != 'records'})
        run = self.state.get('latest_run', {'status': 'not yet run'})
        body = f'''<section><p class="eyebrow">PUBLIC CITY WEBSITE · READ-ONLY MIRROR</p><h2>Browse the archived city website</h2>
<p>{len(entries)} archived pages and documents. Latest sync: <strong>{html.escape(run['status'])}</strong>. <a href="status.html">Review coverage and errors</a>.</p>
<p>This is a text-and-document mirror, not a replica of transactional systems. A page’s hash detects differences between observed versions; it does not establish why a change occurred. PDF files are unmodified source documents; open downloads with an up-to-date viewer.</p>
<label for="mirror-search">Filter by page title or source URL</label><input id="mirror-search" type="search" placeholder="Search the mirror directory…">
<p id="mirror-count" role="status"></p><div id="mirror-results"></div><button id="mirror-more" class="button" hidden>Show more</button>
<noscript><p>Search requires JavaScript. All archived pages are listed below.</p></noscript>
<details><summary>Complete directory (also works without JavaScript)</summary><ul>'''
        body += ''.join(f'<li><a href="{html.escape(e["path"], quote=True)}">{html.escape(e["title"])}</a> ({e["kind"]})</li>' for e in entries)
        body += '</ul></details></section><script src="../mirror-search.js" defer></script>'
        if not entries:
            body += '<p>No city content has been fetched yet. This is not evidence that the city has no public documents. The first successful sync will populate this directory.</p>'
        (self.output / 'index.html').write_text(self.frame('City website mirror', body))
        status_body = '<h2>Sync report</h2><p>Scope: public HTML, PDF and plain-text files on www.cheyennecity.org. External hosts, forms, logins, robots-disallowed URLs and unsupported files are not mirrored. “Completed” means the discovered queue was processed, not that every city record was found. Content requiring JavaScript may be missing.</p>'
        status_body += '<p>Previous copies are retained when a source fails or disappears, and labeled with their last observed status. Cached state can be evicted by GitHub; this is not permanent or tamper-proof preservation.</p>'
        status_body += '<pre>' + html.escape(json.dumps({k: v for k, v in self.state.items() if k not in ('records', 'changes', 'pending')}, indent=2)) + '</pre>'
        status_body += '<h2>Observed changes (latest 200)</h2><p>Byte hashes of fetched responses, not assertions of substantive edits. Previous document bodies are not versioned by this service.</p><ul>'
        for change in reversed(self.state['changes'][-200:]):
            status_body += f'<li>{change["observed_at"]} — <a href="{html.escape(change["url"], quote=True)}">{html.escape(change["url"])}</a>: {"changed" if change["before"] else "first archived"}</li>'
        status_body += '</ul><a href="status.json">Download full sync status and hash-change log (JSON)</a>'
        (self.output / 'status.html').write_text(self.frame('Sync status & changes', status_body))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default='city/mirror-config.json')
    parser.add_argument('--state-dir', default='.cache/city-mirror')
    parser.add_argument('--output', default='city/mirror')
    parser.add_argument('--render-only', action='store_true', help='Render existing state without network access')
    args = parser.parse_args()
    mirror = Mirror(json.loads(Path(args.config).read_text()), args.state_dir, args.output)
    if args.render_only:
        mirror.render()
    else:
        report = mirror.run()
        print(json.dumps(report, indent=2))
        # Fail CI after writing status. The Pages workflow still publishes the
        # failure report and last known copies, not a misleading success state.
        if report['status'] == 'failed' or (report['errors'] and not report['checked']):
            raise SystemExit(1)


if __name__ == '__main__':
    main()
