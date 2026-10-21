'use strict';
(async () => {
  const search = document.getElementById('mirror-search');
  const results = document.getElementById('mirror-results');
  const count = document.getElementById('mirror-count');
  const more = document.getElementById('mirror-more');
  let limit = 40;
  try {
    const response = await fetch('catalog.json');
    if (!response.ok) throw new Error('Catalog unavailable');
    const entries = await response.json();
    function render() {
      const query = search.value.trim().toLowerCase();
      const matches = entries.filter(entry => `${entry.title} ${entry.url}`.toLowerCase().includes(query));
      results.replaceChildren();
      count.textContent = `${matches.length} matches · showing ${Math.min(limit, matches.length)}`;
      for (const entry of matches.slice(0, limit)) {
        const article = document.createElement('article'); article.className = 'meeting';
        const content = document.createElement('div');
        const heading = document.createElement('h3');
        const link = document.createElement('a'); link.href = entry.path; link.textContent = entry.title;
        heading.append(link);
        const detail = document.createElement('p'); detail.className = 'small';
        detail.textContent = `${entry.kind === 'document' ? 'Source document download' : 'Archived page'} · Retrieved ${entry.fetched_at} · Last source status: ${entry.source_status}`;
        content.append(heading, detail); article.append(content); results.append(article);
      }
      more.hidden = matches.length <= limit;
    }
    search.addEventListener('input', () => { limit = 40; render(); });
    more.addEventListener('click', () => { limit += 40; render(); });
    render();
  } catch {
    count.textContent = 'Search is unavailable. Use the complete directory below.';
  }
})();
