<script>
  import { onMount } from 'svelte';
  import bd2026raw from '../../bd_calendar_2026.json';

  // ── Constants ───────────────────────────────────────────────────────────────
  const OWM_KEY = import.meta.env.VITE_OWM_API_KEY || '';
  const REFRESH_INTERVAL_MS = 5 * 60 * 1000;
  const DEFAULT_ZIP = '10001';
  const LS_ZIP_KEY = 'kosmostream_zip';
  const LS_MUTE_KEY = 'kosmostream_muted';

  const TRACKS = [
    'music/Daybreak Doppler.mp3',
    'music/Doppler Drizzle.mp3',
    'music/Ice Waltz for Seeds.mp3',
    'music/Kosmophytotrophia-Stroke.mp3',
    'music/Winter Forecast Wonderland.mp3',
  ];

  // ── BD calendar: the JSON has shape { "2026": { "2026-01-01": {...}, ... } }
  const bdCalendar = bd2026raw['2026'] || {};

  // ── State ────────────────────────────────────────────────────────────────────
  let zip = (typeof localStorage !== 'undefined' && localStorage.getItem(LS_ZIP_KEY)) || DEFAULT_ZIP;
  let zipInput = zip;
  let locationName = '';

  let bd = null;
  let weather = null;
  let space = null;
  let suggestion = '';
  let alerts = [];

  let loading = true;
  let error = '';
  let lastUpdated = '';

  // Music player state
  let audioEl = null;
  let muted = (typeof localStorage !== 'undefined' && localStorage.getItem(LS_MUTE_KEY) === 'true');
  let playlist = [];
  let trackIndex = 0;
  let audioReady = false;

  // ── Helpers ──────────────────────────────────────────────────────────────────
  function todayISO() {
    return new Date().toISOString().slice(0, 10);
  }

  function formatDate(value) {
    if (!value) return '';
    try { return new Date(value).toLocaleString(); } catch { return ''; }
  }

  function formatTemp(min, max) {
    if (min == null || max == null) return '—';
    return `${Math.round(min)}°C – ${Math.round(max)}°C`;
  }

  function formatPop(pop) {
    return `${Math.round((Number(pop) || 0) * 100)}%`;
  }

  function shuffle(arr) {
    const a = [...arr];
    for (let i = a.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [a[i], a[j]] = [a[j], a[i]];
    }
    return a;
  }

  // ── BD lookup ────────────────────────────────────────────────────────────────
  function lookupBD(isoDate) {
    const entry = bdCalendar[isoDate];
    if (!entry) return null;
    return {
      type: entry.type || '',
      phase: entry.phase || '',
      activities: entry.activities || '',
      notes: (entry.notes && entry.notes !== '-') ? entry.notes : null,
    };
  }

  // ── OWM: geocode ZIP ─────────────────────────────────────────────────────────
  async function geocodeZip(z) {
    const url = `https://api.openweathermap.org/geo/1.0/zip?zip=${encodeURIComponent(z + ',US')}&appid=${OWM_KEY}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`Geocode failed: HTTP ${res.status}`);
    return res.json(); // { lat, lon, name, ... }
  }

  // ── OWM: 5-day/3h forecast → today's aggregated row ──────────────────────────
  async function fetchWeather(lat, lon) {
    const url = `https://api.openweathermap.org/data/2.5/forecast?lat=${lat}&lon=${lon}&appid=${OWM_KEY}&units=metric`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`Weather fetch failed: HTTP ${res.status}`);
    const data = await res.json();
    return aggregateToday(data.list || []);
  }

  function aggregateToday(list) {
    const today = todayISO();
    const items = list.filter(item => {
      const d = new Date(item.dt * 1000);
      return d.toISOString().slice(0, 10) === today;
    });
    if (!items.length) {
      // Fallback: use first available day
      if (!list.length) return null;
      const firstDay = new Date(list[0].dt * 1000).toISOString().slice(0, 10);
      items.push(...list.filter(item => new Date(item.dt * 1000).toISOString().slice(0, 10) === firstDay));
    }

    const temps = items.map(i => i.main?.temp).filter(t => t != null);
    const pops = items.map(i => i.pop).filter(p => p != null);
    let precip = 0;
    for (const i of items) {
      precip += (i.rain?.['3h'] || 0) + (i.snow?.['3h'] || 0);
    }
    const descCount = {};
    let icon = '';
    for (const i of items) {
      const wx = (i.weather || [{}])[0];
      const d = wx.description || '';
      descCount[d] = (descCount[d] || 0) + 1;
      if (!icon) icon = wx.icon || '';
    }
    const description = Object.entries(descCount).sort((a, b) => b[1] - a[1])[0]?.[0] || '';

    return {
      temp_min: temps.length ? Math.min(...temps) : null,
      temp_max: temps.length ? Math.max(...temps) : null,
      pop: pops.length ? Math.max(...pops) : 0,
      precipitation: precip,
      description,
      icon,
    };
  }

  // ── NOAA Kp ──────────────────────────────────────────────────────────────────
  async function fetchKp() {
    const url = 'https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json';
    const res = await fetch(url);
    if (!res.ok) throw new Error(`Kp fetch failed: HTTP ${res.status}`);
    const payload = await res.json();

    let rows = [];
    if (Array.isArray(payload)) {
      const first = payload[0];
      rows = (Array.isArray(first) && String(first[0]).toLowerCase() === 'time_tag')
        ? payload.slice(1)
        : payload;
    }
    const recent = rows.slice(-8);
    const vals = recent.map(row => {
      const candidate = Array.isArray(row) ? row[1] : (row?.kp ?? row?.kp_index ?? row?.Kp ?? null);
      const n = parseFloat(candidate);
      return isNaN(n) ? null : n;
    }).filter(v => v !== null);

    const kp_now = vals.length ? vals[vals.length - 1] : null;
    const kp_max = vals.length ? Math.max(...vals) : null;
    const summary = kp_now != null
      ? `Kp now ${kp_now}, 24h max ${kp_max}`
      : 'Kp data unavailable';
    return { kp_now, kp_max, summary };
  }

  // ── Business logic (ported from Python) ──────────────────────────────────────
  function buildSuggestion(bdEntry, wxEntry, spaceEntry) {
    if (!bdEntry) return 'No BD data yet.';
    const bdType = (bdEntry.type || '').toLowerCase();
    const pop = wxEntry?.pop ?? 0;
    const tempMax = wxEntry?.temp_max ?? null;
    const kp = spaceEntry?.kp_now ?? null;

    const baseMap = {
      fruit:   'Favour fruiting tasks; avoid deep root pruning.',
      root:    'Deep watering and transplant roots; keep foliage handling light.',
      leaf:    'Foliar feed and sow leafy greens; steady moisture helps.',
      flower:  'Support pollinators and light pruning only; good for blooms.',
      rest:    'Rest/maintenance only; skip sowing/planting.',
      barren:  'Rest/maintenance only; skip sowing/planting.',
    };
    let tip = baseMap[bdType] || 'Balance tasks to match the day.';
    const overlays = [];
    if (pop >= 0.5) overlays.push('Rain likely; defer watering and protect seedlings.');
    if (tempMax != null && tempMax >= 30) overlays.push('Heat ahead; avoid midday transplants.');
    if (kp != null && kp >= 5) overlays.push('Space weather active (Kp ≥5); expect energetic conditions.');
    if (overlays.length) tip += ' ' + overlays.join(' ');
    return tip;
  }

  function buildAlerts(bdEntry, wxEntry, spaceEntry) {
    const result = [];
    const bdType = (bdEntry?.type || '').toLowerCase();
    if (bdType === 'rest' || bdType === 'barren') {
      result.push({ level: 'danger', text: 'BD rest/barren period — avoid sowing/planting.' });
    }
    if (wxEntry) {
      const pop = (wxEntry.pop || 0) * 100;
      if (pop >= 60) result.push({ level: 'warning', text: `High rain chance today (${Math.round(pop)}% POP).` });
    }
    if (spaceEntry?.kp_now != null && spaceEntry.kp_now >= 5) {
      result.push({ level: 'warning', text: `Space weather alert: Kp ${spaceEntry.kp_now}.` });
    }
    return result;
  }

  function describeKp(val) {
    if (val == null) return null;
    if (val < 2) return 'Quiet';
    if (val < 4) return 'Unsettled';
    if (val < 5) return 'Active';
    if (val < 7) return 'Storm';
    return 'Severe Storm';
  }

  // ── Main refresh ──────────────────────────────────────────────────────────────
  async function refresh() {
    if (!OWM_KEY) {
      error = 'OWM API key not configured (set VITE_OWM_API_KEY).';
      loading = false;
      return;
    }
    loading = true;
    error = '';

    try {
      const [geo, spaceData] = await Promise.all([
        geocodeZip(zip),
        fetchKp().catch(() => null),
      ]);
      locationName = geo.name || zip;
      const wxData = await fetchWeather(geo.lat, geo.lon);

      const today = todayISO();
      bd = lookupBD(today);
      weather = wxData;
      space = spaceData;
      suggestion = buildSuggestion(bd, weather, space);
      alerts = buildAlerts(bd, weather, space);
      lastUpdated = new Date().toISOString();
    } catch (err) {
      error = `Unable to load data: ${err?.message || 'unknown error'}`;
    } finally {
      loading = false;
    }
  }

  function applyZip() {
    const trimmed = zipInput.trim();
    if (!trimmed) return;
    zip = trimmed;
    if (typeof localStorage !== 'undefined') localStorage.setItem(LS_ZIP_KEY, zip);
    refresh();
  }

  // ── Music player ──────────────────────────────────────────────────────────────
  function initMusic() {
    if (!audioEl || audioReady) return;
    playlist = shuffle(TRACKS);
    trackIndex = 0;
    audioEl.src = playlist[trackIndex];
    audioEl.muted = muted;
    audioReady = true;
    audioEl.addEventListener('ended', nextTrack);
  }

  function nextTrack() {
    if (!audioEl || !playlist.length) return;
    trackIndex++;
    if (trackIndex >= playlist.length) {
      playlist = shuffle(TRACKS);
      trackIndex = 0;
    }
    audioEl.src = playlist[trackIndex];
    if (!muted) audioEl.play().catch(() => {});
  }

  function toggleMute() {
    muted = !muted;
    if (typeof localStorage !== 'undefined') localStorage.setItem(LS_MUTE_KEY, muted);
    if (!audioEl) return;
    initMusic();
    audioEl.muted = muted;
    if (!muted) audioEl.play().catch(() => {});
  }

  function playMusic() {
    initMusic();
    if (!muted && audioEl) audioEl.play().catch(() => {});
  }

  // ── Lifecycle ─────────────────────────────────────────────────────────────────
  onMount(() => {
    refresh();
    const timer = setInterval(refresh, REFRESH_INTERVAL_MS);
    return () => clearInterval(timer);
  });
</script>

<!-- Hidden audio element for background music -->
<audio bind:this={audioEl} preload="auto" style="display:none"></audio>

<main>
  <header>
    <h1>KosmoStream</h1>
    <p>Cosmic-aligned planting dashboard</p>
    <small>{todayISO()}{locationName ? ` · ${locationName}` : ''}</small>
  </header>

  <!-- ZIP input -->
  <section class="card zip-bar">
    <label for="zip-input">Location (US ZIP)</label>
    <div class="zip-row">
      <input
        id="zip-input"
        type="text"
        inputmode="numeric"
        maxlength="5"
        pattern="[0-9]{5}"
        placeholder="ZIP code"
        bind:value={zipInput}
        on:keydown={e => e.key === 'Enter' && applyZip()}
      />
      <button type="button" on:click={applyZip}>Go</button>
      <button type="button" class="music-btn" on:click={playMusic} title="Enable music" aria-label="Enable background music">♪</button>
      <button type="button" class="mute-btn" on:click={toggleMute} title={muted ? 'Unmute music' : 'Mute music'} aria-label={muted ? 'Unmute music' : 'Mute music'}>
        {muted ? '🔇' : '🔊'}
      </button>
    </div>
  </section>

  {#if loading}
    <section class="card">Loading…</section>
  {:else if error}
    <section class="card error">{error}</section>
  {:else}
    <!-- Alerts banner -->
    {#if alerts.length}
      <section class="card alerts-card">
        <h2>Alerts</h2>
        <ul>
          {#each alerts as alert}
            <li class="alert-{alert.level}">{alert.text}</li>
          {/each}
        </ul>
      </section>
    {/if}

    <section class="grid">
      <!-- Biodynamic -->
      <article class="card">
        <h2>Biodynamic</h2>
        {#if bd}
          <p class="value">{bd.type}</p>
          <p>{bd.phase}</p>
          <p class="muted">{bd.activities}</p>
          {#if bd.notes}<p class="muted">{bd.notes}</p>{/if}
        {:else}
          <p class="muted">No BD data for today.</p>
        {/if}
      </article>

      <!-- Weather -->
      <article class="card">
        <h2>Weather</h2>
        {#if weather}
          <p class="value">{formatTemp(weather.temp_min, weather.temp_max)}</p>
          <p>{weather.description}</p>
          <p class="muted">POP: {formatPop(weather.pop)}</p>
        {:else}
          <p class="muted">No weather data.</p>
        {/if}
      </article>

      <!-- Space Weather -->
      <article class="card">
        <h2>Space Weather</h2>
        {#if space}
          <p class="value">Kp {space.kp_now ?? 'n/a'}</p>
          {#if space.kp_now != null}
            <p>{describeKp(space.kp_now)}</p>
            <div class="kp-bar">
              {#each Array.from({length: 9}, (_, i) => i + 1) as seg}
                <div class="kp-cell" class:active={seg <= Math.floor(space.kp_now)} data-seg={seg}></div>
              {/each}
            </div>
          {/if}
          <p class="muted">{space.summary}</p>
        {:else}
          <p class="muted">No space data.</p>
        {/if}
      </article>
    </section>

    <!-- Suggestion -->
    <section class="card">
      <h2>Today's Suggestion</h2>
      <p>{suggestion}</p>
    </section>
  {/if}

  <footer>
    <button type="button" on:click={refresh}>Refresh</button>
    {#if lastUpdated}
      <small>Updated: {formatDate(lastUpdated)}</small>
    {/if}
  </footer>
</main>

<style>
  .zip-bar label {
    display: block;
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #9fb3c8;
    margin-bottom: 0.4rem;
  }

  .zip-row {
    display: flex;
    gap: 0.5rem;
    align-items: center;
    flex-wrap: wrap;
  }

  .zip-row input {
    width: 7rem;
    padding: 0.4rem 0.7rem;
    border-radius: 8px;
    border: 1px solid rgba(255, 255, 255, 0.2);
    background: rgba(255, 255, 255, 0.07);
    color: #e9edf5;
    font-size: 1rem;
    min-height: 44px;
  }

  .zip-row input:focus {
    outline: none;
    border-color: rgba(255, 255, 255, 0.5);
  }

  .music-btn, .mute-btn {
    font-size: 1.1rem;
    padding: 0.3rem 0.7rem;
    min-height: 44px;
  }

  .muted {
    color: #9fb3c8;
    font-size: 0.9rem;
  }

  .alerts-card ul {
    margin: 0;
    padding: 0 0 0 1.2rem;
  }

  .alert-danger {
    color: #f87171;
  }

  .alert-warning {
    color: #fbbf24;
  }

  .kp-bar {
    display: grid;
    grid-template-columns: repeat(9, 1fr);
    gap: 3px;
    margin: 0.5rem 0;
  }

  .kp-cell {
    height: 8px;
    border-radius: 3px;
    background: rgba(255, 255, 255, 0.1);
  }

  .kp-cell.active[data-seg="1"],
  .kp-cell.active[data-seg="2"] { background: #2ecc71; }
  .kp-cell.active[data-seg="3"] { background: #27ae60; }
  .kp-cell.active[data-seg="4"] { background: #f1c40f; }
  .kp-cell.active[data-seg="5"] { background: #f39c12; }
  .kp-cell.active[data-seg="6"] { background: #e67e22; }
  .kp-cell.active[data-seg="7"] { background: #e74c3c; }
  .kp-cell.active[data-seg="8"] { background: #c0392b; }
  .kp-cell.active[data-seg="9"] { background: #8e0e00; }
</style>
