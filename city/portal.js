'use strict';
(async () => {
  async function fetchWithTimeout(url, ms = 15000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), ms);
    try {
      return await fetch(url, { signal: controller.signal });
    } finally {
      clearTimeout(timer);
    }
  }
  try {
    const response = await fetchWithTimeout('city/freshness.json');
    if (!response.ok) throw new Error('Unavailable');
    const data = await response.json();
    const checked = data.meeting_information_last_checked ? new Date(data.meeting_information_last_checked).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short', timeZone: 'America/Denver' }) : 'Not recorded';
    document.getElementById('portal-checked').textContent = checked;
    document.getElementById('portal-indexed').textContent = data.latest_meeting_indexed ? `${data.latest_meeting_indexed} (catalog maximum)` : 'Not recorded';
    document.getElementById('portal-outcome').textContent = data.latest_verified_outcome || 'None documented as verified';
    document.getElementById('portal-gaps').textContent = `${data.known_gaps?.length || 0} known gaps — ${data.known_gaps?.[0] || 'See coverage page'}`;
  } catch {
    for (const id of ['portal-checked', 'portal-indexed', 'portal-outcome', 'portal-gaps']) document.getElementById(id).textContent = 'Status record unavailable; no build time substituted.';
  }
})();
