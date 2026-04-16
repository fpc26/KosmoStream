<script>
  import { onMount, afterUpdate } from 'svelte';
  import bd2026raw from '../../bd_calendar_2026.json';

  // ── Constants ───────────────────────────────────────────────────────────────
  const OWM_KEY = import.meta.env.VITE_OWM_API_KEY || '';
  const REFRESH_INTERVAL_MS = 5 * 60 * 1000;
  const DEFAULT_ZIP = '10001';
  const LS_ZIP_KEY   = 'kosmostream_zip';
  const LS_PREFS_KEY = 'ks_prefs';
  const LS_SCREENS_KEY = 'ks_screens';

  const TRACKS = [
    'music/Daybreak Doppler.mp3',
    'music/Doppler Drizzle.mp3',
    'music/Ice Waltz for Seeds.mp3',
    'music/Kosmophytotrophia-Stroke.mp3',
    'music/Winter Forecast Wonderland.mp3',
  ];

  const KOSMO_TIPS = [
    'Biochar is carbon-negative and its porous, negatively charged structure soaks up minerals and nutrients, then releases them slowly over decades.',
    'Compost teas boost soil biome diversity, turning root zones into microbial parties that unlock nutrients for plants.',
    'Biodynamic preparations provide rhythmic, resonance-based inputs that align soil and plant vitality with cosmic cycles.',
    'Blend compost teas, biodynamic preps, and biochar for a Kosmophytotrophia trio: long-lived fertility, microbial housing, and rhythmic resonance in the root zone.',
  ];

  const SLIDE_META = [
    { id: 'current',    label: 'Current Conditions' },
    { id: 'outlook-3',  label: 'Planting Outlook' },
    { id: 'outlook-7',  label: 'Extended Planting Outlook' },
    { id: 'almanac',    label: 'Enhanced Almanac' },
    { id: 'bd-outlook', label: 'Biodynamic Outlook' },
    { id: 'vinter',     label: "Vinter's Outlook" },
    { id: 'kosmogrow',  label: 'KosmoGrow Advantage' },
  ];

  const bdCalendar = bd2026raw['2026'] || {};

  // ── State ──────────────────────────────────────────────────────────────────
  let zip = (typeof localStorage !== 'undefined' && localStorage.getItem(LS_ZIP_KEY)) || DEFAULT_ZIP;
  let zipInput = zip;
  let locationName = '';

  let forecast = [];   // [{date, display_label, wx, bd, suggestion}]
  let space = null;
  let bdRanges = [];
  let moonPhases = [];
  let loading = true;
  let error = '';
  let lastUpdated = '';

  // Slide management
  let slideIndex = 0;
  let visibleSlideIds = SLIDE_META.map(s => s.id);
  let slideTimer = null;
  let bdPageTimer = null;
  let bdPageIndex = 0;
  let kosmoTipIndex = 0;
  let slidesStarted = false;

  // Settings
  let units = 'metric';
  let scrollSeconds = 12;
  let muted = false;
  let kioskMode = false;

  // UI panels
  let showSettings = false;
  let alertsCollapsed = false;
  let screenPickerSelected = new Set(SLIDE_META.map(s => s.id));

  // Window width for responsive BD pager
  let windowWidth = typeof window !== 'undefined' ? window.innerWidth : 800;

  // Music
  let audioEl = null;
  let audioReady = false;
  let musicStarted = false;
  let playlist = [];
  let trackIndex = 0;

  // Swipe tracking
  let swipeStartX = 0, swipeStartY = 0;

  // ── Reactive declarations ──────────────────────────────────────────────────
  $: visibleSlides = SLIDE_META.filter(s => visibleSlideIds.includes(s.id));
  $: scrollIntervalMs = scrollSeconds * 1000;
  $: bdPageSize = windowWidth >= 768 ? 6 : 3;
  $: bdTotalPages = Math.max(1, Math.ceil(bdRanges.length / bdPageSize));
  $: bdPageRanges = bdRanges.slice(bdPageIndex * bdPageSize, (bdPageIndex + 1) * bdPageSize);
  $: bd = forecast[0]?.bd || null;
  $: wx = forecast[0]?.wx || null;
  $: alerts = buildAlerts(bd, wx, space);
  $: currentSuggestion = buildSuggestion(bd, wx, space);

  // ── Helpers ────────────────────────────────────────────────────────────────
  function todayISO() { return new Date().toISOString().slice(0, 10); }

  function formatDate(v) {
    if (!v) return '';
    try { return new Date(v).toLocaleString(); } catch { return ''; }
  }

  function formatTemp(min, max, u) {
    u = u || units;
    if (min == null || max == null) return '—';
    if (u === 'imperial') return `${Math.round(min * 9/5 + 32)}–${Math.round(max * 9/5 + 32)}°F`;
    return `${Math.round(min)}–${Math.round(max)}°C`;
  }

  function formatPop(pop) { return `${Math.round((Number(pop) || 0) * 100)}%`; }

  function suffix(n) {
    if (n >= 10 && n <= 20) return 'th';
    return { 1: 'st', 2: 'nd', 3: 'rd' }[n % 10] || 'th';
  }

  function dayLabel(dateStr, todayStr) {
    const today = new Date(todayStr + 'T00:00:00');
    const target = new Date(dateStr + 'T00:00:00');
    const delta = Math.round((target - today) / 86400000);
    const day = target.getDate();
    const month = target.toLocaleDateString('en-US', { month: 'long' });
    const prettyDate = `${month} ${day}${suffix(day)}`;
    if (delta === 0) return `Today (${prettyDate})`;
    if (delta === 1) return `Tomorrow (${prettyDate})`;
    const weekday = target.toLocaleDateString('en-US', { weekday: 'long' });
    return `${weekday} ${day}${suffix(day)}`;
  }

  function shuffle(arr) {
    const a = [...arr];
    for (let i = a.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [a[i], a[j]] = [a[j], a[i]];
    }
    return a;
  }

  // ── BD calendar helpers ────────────────────────────────────────────────────
  function lookupBD(isoDate) {
    const e = bdCalendar[isoDate];
    if (!e) return null;
    return {
      type: e.type || '',
      phase: e.phase || '',
      activities: e.activities || '',
      notes: (e.notes && e.notes !== '-') ? e.notes : null,
    };
  }

  function buildBdRanges(todayStr, daysAhead = 30) {
    const rows = [];
    const start = new Date(todayStr + 'T00:00:00');
    for (let i = 0; i < daysAhead; i++) {
      const d = new Date(start); d.setDate(start.getDate() + i);
      const e = bdCalendar[d.toISOString().slice(0, 10)];
      if (e) rows.push(e);
    }
    if (!rows.length) return [];
    const items = [];
    let current = null;
    for (const r of rows) {
      const bdType = (r.type || '').trim();
      if (!bdType) continue;
      const dateD = new Date(r.date + 'T00:00:00');
      if (current && bdType.toLowerCase() === current.type.toLowerCase()) {
        const diff = Math.round((dateD - new Date(current.end + 'T00:00:00')) / 86400000);
        if (diff === 1) { current.end = r.date; continue; }
      }
      if (current) items.push(current);
      current = { type: bdType, phase: r.phase || '', start: r.date, end: r.date, activities: r.activities || '' };
    }
    if (current) items.push(current);
    const todayD = new Date(todayStr + 'T00:00:00');
    const fmt = d => d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    return items.map(it => {
      const s = new Date(it.start + 'T00:00:00'), e = new Date(it.end + 'T00:00:00');
      const deltaS = Math.round((s - todayD) / 86400000);
      const deltaE = Math.round((e - todayD) / 86400000);
      const sl = deltaS === 0 ? 'Today' : deltaS === 1 ? 'Tomorrow' : fmt(s);
      const el = deltaE === 0 ? 'Today' : deltaE === 1 ? 'Tomorrow' : fmt(e);
      return { type: it.type, phase: it.phase, activities: it.activities,
        display_range: it.start === it.end ? sl : `${sl} – ${el}` };
    });
  }

  function buildMoonPhases(todayStr, limit = 12, daysAhead = 90) {
    const wanted = { 'new': 'New Moon', 'first quarter': 'First Quarter', 'full': 'Full Moon', 'last quarter': 'Last Quarter', 'third quarter': 'Last Quarter' };
    const phases = [], seen = new Set();
    const start = new Date(todayStr + 'T00:00:00');
    for (let i = 0; i < daysAhead; i++) {
      const d = new Date(start); d.setDate(start.getDate() + i);
      const e = bdCalendar[d.toISOString().slice(0, 10)];
      if (!e) continue;
      const pl = (e.phase || '').toLowerCase();
      for (const [key, name] of Object.entries(wanted)) {
        if (pl.includes(key) && !seen.has(name)) {
          seen.add(name);
          phases.push({ date: e.date, phase: name });
          if (phases.length >= limit) return phases;
          break;
        }
      }
    }
    return phases;
  }

  // ── OWM ───────────────────────────────────────────────────────────────────
  async function geocodeZip(z) {
    const res = await fetch(`https://api.openweathermap.org/geo/1.0/zip?zip=${encodeURIComponent(z + ',US')}&appid=${OWM_KEY}`);
    if (!res.ok) throw new Error(`Geocode failed: HTTP ${res.status}`);
    return res.json();
  }

  async function fetchForecast(lat, lon) {
    const res = await fetch(`https://api.openweathermap.org/data/2.5/forecast?lat=${lat}&lon=${lon}&appid=${OWM_KEY}&units=metric`);
    if (!res.ok) throw new Error(`Weather failed: HTTP ${res.status}`);
    const data = await res.json();
    return aggregateAllDays(data.list || []);
  }

  function aggregateAllDays(list) {
    const buckets = {};
    for (const item of list) {
      const d = new Date(item.dt * 1000).toISOString().slice(0, 10);
      if (!buckets[d]) buckets[d] = [];
      buckets[d].push(item);
    }
    const rows = [];
    for (const [day, items] of Object.entries(buckets).sort()) {
      const temps = items.map(i => i.main?.temp).filter(t => t != null);
      const pops  = items.map(i => i.pop).filter(p => p != null);
      let precip = 0;
      for (const i of items) precip += (i.rain?.['3h'] || 0) + (i.snow?.['3h'] || 0);
      const descCount = {}; let icon = '';
      for (const i of items) {
        const wx = (i.weather || [{}])[0];
        const d = wx.description || '';
        descCount[d] = (descCount[d] || 0) + 1;
        if (!icon) icon = wx.icon || '';
      }
      const description = Object.entries(descCount).sort((a, b) => b[1] - a[1])[0]?.[0] || '';
      rows.push({ date: day, wx: {
        temp_min: temps.length ? Math.min(...temps) : null,
        temp_max: temps.length ? Math.max(...temps) : null,
        pop: pops.length ? Math.max(...pops) : 0, precipitation: precip, description, icon,
      }});
    }
    return rows.slice(0, 7);
  }

  // ── NOAA Kp ────────────────────────────────────────────────────────────────
  async function fetchKp() {
    const res = await fetch('https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json');
    if (!res.ok) throw new Error(`Kp failed: HTTP ${res.status}`);
    const payload = await res.json();
    let rows = [];
    if (Array.isArray(payload)) {
      const first = payload[0];
      rows = (Array.isArray(first) && String(first[0]).toLowerCase() === 'time_tag') ? payload.slice(1) : payload;
    }
    const vals = rows.slice(-8).map(row => {
      const c = Array.isArray(row) ? row[1] : (row?.kp ?? row?.kp_index ?? row?.Kp ?? null);
      const n = parseFloat(c); return isNaN(n) ? null : n;
    }).filter(v => v != null);
    const kp_now = vals.length ? vals[vals.length - 1] : null;
    const kp_max = vals.length ? Math.max(...vals) : null;
    return { kp_now, kp_max, summary: kp_now != null ? `Kp now ${kp_now}, 24h max ${kp_max}` : 'Kp data unavailable' };
  }

  // ── Business logic ─────────────────────────────────────────────────────────
  function buildSuggestion(bdEntry, wxEntry, spaceEntry) {
    if (!bdEntry) return 'No BD data yet.';
    const bdType = (bdEntry.type || '').toLowerCase();
    const pop = wxEntry?.pop ?? 0, tempMax = wxEntry?.temp_max ?? null, kp = spaceEntry?.kp_now ?? null;
    const base = { fruit: 'Favour fruiting tasks; avoid deep root pruning.',
      root: 'Deep watering and transplant roots; keep foliage handling light.',
      leaf: 'Foliar feed and sow leafy greens; steady moisture helps.',
      flower: 'Support pollinators and light pruning only; good for blooms.',
      rest: 'Rest/maintenance only; skip sowing/planting.',
      barren: 'Rest/maintenance only; skip sowing/planting.' };
    let tip = base[bdType] || 'Balance tasks to match the day.';
    const ov = [];
    if (pop >= 0.5) ov.push('Rain likely; defer watering and protect seedlings.');
    if (tempMax != null && tempMax >= 30) ov.push('Heat ahead; avoid midday transplants.');
    if (kp != null && kp >= 5) ov.push('Space weather active (Kp ≥5); expect energetic conditions.');
    if (ov.length) tip += ' ' + ov.join(' ');
    return tip;
  }

  function buildAlerts(bdEntry, wxEntry, spaceEntry) {
    const result = [];
    const bdType = (bdEntry?.type || '').toLowerCase();
    if (bdType === 'rest' || bdType === 'barren')
      result.push({ level: 'danger', text: 'BD rest/barren period — avoid sowing/planting.' });
    if (wxEntry) {
      const pop = (wxEntry.pop || 0) * 100;
      if (pop >= 60) result.push({ level: 'warning', text: `High rain chance today (${Math.round(pop)}% POP).` });
    }
    if (spaceEntry?.kp_now != null && spaceEntry.kp_now >= 5)
      result.push({ level: 'warning', text: `Space weather alert: Kp ${spaceEntry.kp_now}.` });
    return result;
  }

  function kpSegColor(seg) {
    return ['#2ecc71','#2ecc71','#27ae60','#f1c40f','#f39c12','#e67e22','#e74c3c','#c0392b','#8e0e00'][seg - 1];
  }

  function bdDotColor(type) {
    const t = (type || '').toLowerCase();
    if (t.includes('fruit'))  return '#ffb347';
    if (t.includes('root'))   return '#d48c2f';
    if (t.includes('leaf'))   return '#76c893';
    if (t.includes('flower')) return '#ffd166';
    return '#b0b8c2';
  }

  // ── Inline SVG icons ───────────────────────────────────────────────────────
  function bdIconSvg(type) {
    const t = (type || '').toLowerCase();
    if (t.includes('fruit'))
      return `<svg class="bd-icon" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg"><circle cx="50" cy="64" r="28" fill="none" stroke="#ffb347" stroke-width="7"/><path d="M50 22 C36 8 22 22 32 34" fill="none" stroke="#76c893" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/><path d="M50 22 C64 8 78 22 68 34" fill="none" stroke="#76c893" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/><line x1="50" y1="20" x2="50" y2="40" stroke="#76c893" stroke-width="7" stroke-linecap="round"/></svg>`;
    if (t.includes('root'))
      return `<svg class="bd-icon" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg"><polygon points="50,78 32,36 68,36" fill="none" stroke="#d48c2f" stroke-width="7" stroke-linejoin="round"/><path d="M50 20 C38 10 26 18 34 30" fill="none" stroke="#76c893" stroke-width="7" stroke-linecap="round"/><path d="M50 20 C62 10 74 18 66 30" fill="none" stroke="#76c893" stroke-width="7" stroke-linecap="round"/><line x1="50" y1="20" x2="50" y2="40" stroke="#76c893" stroke-width="7" stroke-linecap="round"/></svg>`;
    if (t.includes('leaf'))
      return `<svg class="bd-icon" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg"><path d="M50 12 Q14 54 44 88 Q86 54 50 12" fill="#1f6f4a" stroke="#76c893" stroke-width="6" stroke-linejoin="round"/><line x1="50" y1="18" x2="50" y2="82" stroke="#b8f2c8" stroke-width="5" stroke-linecap="round"/><path d="M50 42 C40 46 34 56 32 66" fill="none" stroke="#b8f2c8" stroke-width="4" stroke-linecap="round"/><path d="M50 46 C60 50 66 60 68 70" fill="none" stroke="#b8f2c8" stroke-width="4" stroke-linecap="round"/></svg>`;
    if (t.includes('flower'))
      return `<svg class="bd-icon" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg"><circle cx="50" cy="50" r="13" fill="#ffd166" stroke="#ffd166" stroke-width="3"/><ellipse cx="50" cy="26" rx="10" ry="18" fill="none" stroke="#ffd166" stroke-width="5" transform="rotate(0 50 50)"/><ellipse cx="50" cy="26" rx="10" ry="18" fill="none" stroke="#ffd166" stroke-width="5" transform="rotate(60 50 50)"/><ellipse cx="50" cy="26" rx="10" ry="18" fill="none" stroke="#ffd166" stroke-width="5" transform="rotate(120 50 50)"/><ellipse cx="50" cy="26" rx="10" ry="18" fill="none" stroke="#ffd166" stroke-width="5" transform="rotate(180 50 50)"/></svg>`;
    if (t.includes('rest') || t.includes('barren'))
      return `<svg class="bd-icon" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg"><circle cx="50" cy="50" r="36" fill="none" stroke="#b0b8c2" stroke-width="7"/><line x1="30" y1="50" x2="70" y2="50" stroke="#b0b8c2" stroke-width="7" stroke-linecap="round"/></svg>`;
    return `<svg class="bd-icon" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg"><circle cx="50" cy="50" r="36" fill="none" stroke="#9fb3c8" stroke-width="7"/></svg>`;
  }

  function moonIconSvg(phase) {
    const p = (phase || '').toLowerCase(), s = '#c7d3e3';
    if (p.includes('new'))
      return `<svg class="moon-icon" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg"><circle cx="50" cy="50" r="40" fill="none" stroke="${s}" stroke-width="6"/></svg>`;
    if (p.includes('full'))
      return `<svg class="moon-icon" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg"><circle cx="50" cy="50" r="40" fill="${s}" stroke="${s}" stroke-width="6"/></svg>`;
    if (p.includes('first quarter'))
      return `<svg class="moon-icon" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg"><circle cx="50" cy="50" r="40" fill="none" stroke="${s}" stroke-width="6"/><path d="M50 10 A40 40 0 0 1 50 90 L50 10 Z" fill="${s}"/></svg>`;
    if (p.includes('last quarter') || p.includes('third quarter'))
      return `<svg class="moon-icon" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg"><circle cx="50" cy="50" r="40" fill="none" stroke="${s}" stroke-width="6"/><path d="M50 10 A40 40 0 0 0 50 90 L50 10 Z" fill="${s}"/></svg>`;
    if (p.includes('waxing'))
      return `<svg class="moon-icon" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg"><circle cx="50" cy="50" r="40" fill="none" stroke="${s}" stroke-width="6"/><path d="M50 10 A40 40 0 0 1 50 90 A24 40 0 0 0 50 10 Z" fill="${s}"/></svg>`;
    if (p.includes('waning'))
      return `<svg class="moon-icon" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg"><circle cx="50" cy="50" r="40" fill="none" stroke="${s}" stroke-width="6"/><path d="M50 10 A40 40 0 0 0 50 90 A24 40 0 0 1 50 10 Z" fill="${s}"/></svg>`;
    return `<svg class="moon-icon" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg"><circle cx="50" cy="50" r="40" fill="none" stroke="${s}" stroke-width="6"/></svg>`;
  }

  // ── Vinter helpers ─────────────────────────────────────────────────────────
  const CELLAR_MAP = {
    fruit:  { label: 'Fruit Day',   color: '#f39c12', text: 'Ideal for tastings, bottling & blending — expect aromatic lift and expressive fruit character.' },
    flower: { label: 'Flower Day',  color: '#74b9ff', text: 'Wines open expressively. Excellent for aromatic evaluations and careful racking.' },
    root:   { label: 'Root Day',    color: '#a8b6c8', text: 'Wines trend closed and earthy. Defer bottling, tastings, and aromatic work.' },
    leaf:   { label: 'Leaf Day',    color: '#76c893', text: 'Wines may show green notes. Minimal cellar intervention recommended.' },
    rest:   { label: 'Rest Day',    color: '#a8b6c8', text: 'Postpone all critical cellar operations — rack, bottle, or taste another day.' },
    barren: { label: 'Barren Day',  color: '#e74c3c', text: 'Barren period: avoid tastings, bottling, and aromatic evaluations entirely.' },
  };

  function vinterCellar(bdEntry) {
    return CELLAR_MAP[(bdEntry?.type || '').toLowerCase()] || { label: 'Unclassified Day', color: '#9fb3c8', text: 'Observe and record; defer evaluations until BD type clarifies.' };
  }

  function vinterMoon(bdEntry) {
    const p = (bdEntry?.phase || '').toLowerCase();
    if (p.includes('waxing') || p.includes('crescent')) return 'Ascending Moon — wines open and oxygenate well. Suitable for racking.';
    if (p.includes('waning'))          return 'Descending Moon — prefer bottling, capping, and settling. Wines integrate.';
    if (p.includes('full'))            return 'Full Moon — energy peaks; wines can be volatile. Taste carefully and note results.';
    if (p.includes('new'))             return 'New Moon — wines tend stable and closed. Suitable for filtration.';
    if (p.includes('first quarter'))   return 'First Quarter — building energy. Suitable for oxygenation and aromatic lifting.';
    if (p.includes('last quarter') || p.includes('third quarter')) return 'Last Quarter — winding energy. Favours racking for clarity and precision bottling.';
    return bdEntry?.phase ? `Phase: ${bdEntry.phase}.` : 'Moon phase data unavailable.';
  }

  function vinterKp(spaceEntry) {
    const kp = spaceEntry?.kp_now;
    if (kp == null) return 'Geomagnetic data unavailable.';
    if (kp >= 5) return `⚡ Elevated geomagnetic activity (Kp ${kp}) — heightened sensitivity during tastings.`;
    if (kp >= 3) return `Kp ${kp} — mild activity; monitor aromatic consistency.`;
    return `Kp ${kp} — quiet conditions; ideal for precision cellar work.`;
  }

  function vinterTemp(wxEntry) {
    const t = wxEntry?.temp_max;
    if (t == null) return 'Cellar temperatures within expected range.';
    if (t >= 28) return `⚠ High of ${Math.round(t)}°C expected — verify cellar cooling is active.`;
    if (t <= 5)  return `❄ Cold high of ${Math.round(t)}°C — check fermentation temps and heating.`;
    return 'Cellar temperatures within expected range.';
  }

  function vinterNextHint(bdEntry, ranges) {
    const t = (bdEntry?.type || '').toLowerCase();
    const better = ['fruit', 'flower'];
    if (!better.includes(t) && ranges?.length) {
      const next = ranges.find(r => better.includes((r.type || '').toLowerCase()));
      if (next) return `Next tasting window: ${next.type} day — ${next.display_range}.`;
    }
    return '';
  }

  // ── Main refresh ───────────────────────────────────────────────────────────
  async function refresh() {
    if (!OWM_KEY) { error = 'OWM API key not configured (set VITE_OWM_API_KEY).'; loading = false; return; }
    loading = true; error = '';
    try {
      const [geo, spaceData] = await Promise.all([geocodeZip(zip), fetchKp().catch(() => null)]);
      locationName = geo.name || zip;
      const dailyRows = await fetchForecast(geo.lat, geo.lon);
      space = spaceData;
      const today = todayISO();
      forecast = dailyRows.map(row => ({
        ...row, display_label: dayLabel(row.date, today),
        bd: lookupBD(row.date), suggestion: buildSuggestion(lookupBD(row.date), row.wx, spaceData),
      }));
      bdRanges   = buildBdRanges(today, 30);
      moonPhases = buildMoonPhases(today, 12, 90);
      lastUpdated = new Date().toISOString();
    } catch (err) {
      error = `Unable to load data: ${err?.message || 'unknown error'}`;
    } finally {
      loading = false;
    }
  }

  function applyZip() {
    const z = zipInput.trim();
    if (!z) return;
    zip = z;
    if (typeof localStorage !== 'undefined') localStorage.setItem(LS_ZIP_KEY, zip);
    refresh();
  }

  // ── Slide management ───────────────────────────────────────────────────────
  function scheduleNext(delayMs) {
    clearTimeout(slideTimer);
    slideTimer = setTimeout(advanceSlide, delayMs);
  }

  function goToSlide(newIdx) {
    clearTimeout(slideTimer); clearTimeout(bdPageTimer);
    const count = visibleSlides.length;
    if (!count) return;
    slideIndex = ((newIdx % count) + count) % count;
    const slide = visibleSlides[slideIndex];
    if (slide?.id === 'bd-outlook') { bdPageIndex = 0; bdPagerStart(); }
    else if (slide?.id === 'kosmogrow') { kosmoTipIndex = (kosmoTipIndex + 1) % KOSMO_TIPS.length; scheduleNext(scrollIntervalMs); }
    else { scheduleNext(scrollIntervalMs); }
  }

  function advanceSlide() { goToSlide(slideIndex + 1); }
  function prevSlideNav()  { goToSlide(slideIndex - 1); }

  function advanceBdPage() {
    clearTimeout(bdPageTimer);
    if (bdPageIndex + 1 < bdTotalPages) { bdPageIndex++; bdPagerStart(); }
    else advanceSlide();
  }

  function bdPagerStart() {
    if (bdTotalPages <= 1) { scheduleNext(scrollIntervalMs); return; }
    bdPageTimer = setTimeout(() => {
      if (bdPageIndex + 1 < bdTotalPages) { bdPageIndex++; bdPagerStart(); }
      else advanceSlide();
    }, Math.max(scrollIntervalMs, 7000));
  }

  function startSlides() {
    clearTimeout(slideTimer); clearTimeout(bdPageTimer);
    goToSlide(slideIndex);
  }

  // ── Settings ───────────────────────────────────────────────────────────────
  function loadPrefs() {
    if (typeof localStorage === 'undefined') return;
    const p = JSON.parse(localStorage.getItem(LS_PREFS_KEY) || '{}');
    if (p.units)         units = p.units;
    if (p.scrollSeconds) scrollSeconds = p.scrollSeconds;
    if (p.muted != null) muted = p.muted;
    if (p.kiosk)         kioskMode = p.kiosk;
  }

  function savePrefs() {
    const chosen = Array.from(screenPickerSelected);
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem(LS_PREFS_KEY, JSON.stringify({ units, scrollSeconds, muted, kiosk: kioskMode }));
      localStorage.setItem(LS_SCREENS_KEY, JSON.stringify(chosen));
    }
    visibleSlideIds = chosen.length ? chosen : SLIDE_META.map(s => s.id);
    slideIndex = 0;
    if (kioskMode) document.documentElement.requestFullscreen?.().catch(() => {});
    else document.exitFullscreen?.().catch(() => {});
    showSettings = false;
    startSlides();
  }

  // ── Screen picker ──────────────────────────────────────────────────────────
  function loadScreens() {
    if (typeof localStorage === 'undefined') return SLIDE_META.map(s => s.id);
    const stored = JSON.parse(localStorage.getItem(LS_SCREENS_KEY) || '[]');
    if (!Array.isArray(stored) || !stored.length) return SLIDE_META.map(s => s.id);
    return stored.filter(id => SLIDE_META.some(s => s.id === id));
  }

  function toggleScreen(id) {
    const s = new Set(screenPickerSelected);
    if (s.has(id)) s.delete(id); else s.add(id);
    screenPickerSelected = s;
  }

  // ── Music ──────────────────────────────────────────────────────────────────
  function initMusic() {
    if (!audioEl || audioReady) return;
    playlist = shuffle(TRACKS); trackIndex = 0;
    audioEl.src = playlist[trackIndex]; audioEl.muted = muted; audioReady = true;
    audioEl.addEventListener('ended', () => {
      trackIndex = (trackIndex + 1) % playlist.length;
      if (trackIndex === 0) playlist = shuffle(TRACKS);
      audioEl.src = playlist[trackIndex];
      if (!muted) audioEl.play().catch(() => {});
    });
  }

  function toggleMute() {
    muted = !muted;
    if (typeof localStorage !== 'undefined') {
      const p = JSON.parse(localStorage.getItem(LS_PREFS_KEY) || '{}');
      p.muted = muted; localStorage.setItem(LS_PREFS_KEY, JSON.stringify(p));
    }
    if (!audioEl) return;
    initMusic(); audioEl.muted = muted;
    if (!muted) audioEl.play().catch(() => {});
  }

  function handleMusicButton() {
    if (!musicStarted) {
      musicStarted = true;
      muted = false;
      if (audioEl) { audioEl.muted = false; audioEl.play().catch(() => {}); }
      if (typeof localStorage !== 'undefined') {
        const p = JSON.parse(localStorage.getItem(LS_PREFS_KEY) || '{}');
        p.muted = false; localStorage.setItem(LS_PREFS_KEY, JSON.stringify(p));
      }
    } else {
      toggleMute();
    }
  }

  // ── Touch/keyboard ─────────────────────────────────────────────────────────
  function onTouchStart(e) { swipeStartX = e.changedTouches[0].clientX; swipeStartY = e.changedTouches[0].clientY; }
  function onTouchEnd(e) {
    const dx = e.changedTouches[0].clientX - swipeStartX;
    const dy = e.changedTouches[0].clientY - swipeStartY;
    if (Math.abs(dx) > Math.abs(dy) && Math.abs(dx) > 40) { if (dx < 0) advanceSlide(); else prevSlideNav(); }
  }

  function onKeydown(e) {
    if (showSettings) return;
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') { e.preventDefault(); advanceSlide(); }
    if (e.key === 'ArrowLeft'  || e.key === 'ArrowUp')   { e.preventDefault(); prevSlideNav(); }
  }

  // ── Lifecycle ──────────────────────────────────────────────────────────────
  onMount(() => {
    loadPrefs();
    const saved = loadScreens();
    visibleSlideIds = saved; screenPickerSelected = new Set(saved);
    const onResize = () => { windowWidth = window.innerWidth; };
    window.addEventListener('resize', onResize);
    // Pre-load audio to reduce first-play lag; start playback on first user gesture
    initMusic();
    const startOnInteraction = () => {
      if (!musicStarted && !muted && audioEl) { musicStarted = true; audioEl.play().catch(() => {}); }
    };
    document.addEventListener('click', startOnInteraction, { once: true });
    document.addEventListener('touchstart', startOnInteraction, { once: true });
    refresh();
    const timer = setInterval(refresh, REFRESH_INTERVAL_MS);
    return () => {
      clearInterval(timer); clearTimeout(slideTimer); clearTimeout(bdPageTimer);
      window.removeEventListener('resize', onResize);
      document.removeEventListener('click', startOnInteraction);
      document.removeEventListener('touchstart', startOnInteraction);
    };
  });

  afterUpdate(() => {
    if (!loading && !error && !slidesStarted && visibleSlides.length > 0) {
      slidesStarted = true; startSlides();
    }
  });
</script>

<svelte:window on:keydown={onKeydown} />
<audio bind:this={audioEl} preload="auto" style="display:none"></audio>

<div class="container-fluid py-2" id="app-root">
  <!-- Header -->
  <div class="d-flex align-items-center justify-content-between mb-2 flex-shrink-0 flex-wrap gap-2">
    <div>
      <h1 class="hero-title fw-bold mb-0">KosmoStream</h1>
      <div class="small text-secondary">Cosmic-aligned planting stream</div>
    </div>
    <div class="d-flex gap-2 align-items-center flex-wrap">
      {#if locationName}<span class="badge-soft d-none d-sm-inline">{locationName} · {todayISO()}</span>{/if}
      <!-- ZIP input (desktop only — mobile gets it in the bottom bar) -->
      <div class="d-none d-sm-flex gap-1 align-items-center">
        <input class="zip-input" type="text" inputmode="numeric" maxlength="5" placeholder="ZIP" bind:value={zipInput}
          on:keydown={e => e.key === 'Enter' && applyZip()} aria-label="ZIP code" />
        <button class="btn btn-sm btn-outline-light pill-btn" on:click={applyZip}>Go</button>
      </div>
      <div class="d-none d-sm-flex gap-2 align-items-center">
        <button class="btn btn-sm btn-outline-light pill-btn" on:click={() => showSettings = true}>Settings</button>
        <button class="btn btn-sm btn-outline-light pill-btn" id="muteToggle" on:click|stopPropagation={handleMusicButton}
          title={muted ? 'Unmute' : 'Mute'}>
          {muted ? '🔇' : '🔊'}
        </button>
      </div>
    </div>
  </div>

  <!-- Alerts ticker -->
  {#if !loading && alerts.length && !alertsCollapsed}
    <div class="ticker mb-2 flex-shrink-0 d-flex align-items-center justify-content-between">
      <span>{#each alerts as a, i}{#if i > 0} &nbsp;·&nbsp; {/if}{a.text}{/each}</span>
      <button class="btn-close btn-close-white ms-3 flex-shrink-0" style="font-size:.6rem; opacity:.8;"
        on:click={() => alertsCollapsed = true} aria-label="Dismiss alert"></button>
    </div>
  {/if}

  <!-- Slides area -->
  {#if loading}
    <div class="d-flex align-items-center justify-content-center" style="flex:1;">
      <div class="glass p-4 text-center">
        <div class="spinner-border text-light mb-2" role="status"></div>
        <div>Loading data…</div>
      </div>
    </div>
  {:else if error}
    <div class="d-flex align-items-center justify-content-center" style="flex:1;">
      <div class="glass p-4 text-center" style="max-width:480px; border-color:#e74c3c;">
        <div style="color:#e74c3c; font-weight:600; margin-bottom:.5rem;">Error</div>
        <div class="text-secondary">{error}</div>
      </div>
    </div>
  {:else}
    <div id="slides-wrapper" on:touchstart={onTouchStart} on:touchend={onTouchEnd}>
      <button class="slide-nav slide-nav-prev" on:click={prevSlideNav} aria-label="Previous">&#8249;</button>
      <button class="slide-nav slide-nav-next" on:click={advanceSlide} aria-label="Next">&#8250;</button>

      {#each visibleSlides as slide, i}
        <section class="view-slide" class:active={i === slideIndex}>

          {#if slide.id === 'current'}
          <!-- ── Slide 1: Current Conditions ───────────────────────────────── -->
          <div class="section-title">Current Conditions</div>
          <div class="glass p-4">
            <div class="d-flex justify-content-between align-items-start mb-3 flex-wrap gap-2">
              <div>
                <div class="metric-label">Today</div>
                <div class="metric-value">{bd?.type || 'No BD data'}</div>
                <div class="text-secondary d-flex align-items-center gap-1">
                  {#if bd}{@html bdIconSvg(bd.type)}{@html moonIconSvg(bd.phase)}{bd.phase}{/if}
                </div>
              </div>
              <div class="text-end">
                <div class="metric-label">Suggestion</div>
                <div class="fw-semibold" style="max-width:280px;">{currentSuggestion}</div>
              </div>
            </div>
            <div class="row g-3">
              <div class="col-md-4">
                <div class="card-dark p-3 h-100">
                  <div class="metric-label">Weather</div>
                  {#if wx}
                    <div class="metric-value">{formatTemp(wx.temp_min, wx.temp_max)}</div>
                    <div class="muted">{wx.description}</div>
                    <div class="badge-soft mt-2">POP {formatPop(wx.pop)}</div>
                  {:else}<div class="muted">No weather data yet.</div>{/if}
                </div>
              </div>
              <div class="col-md-4">
                <div class="card-dark p-3 h-100">
                  <div class="metric-label">Geomagnetic Activity</div>
                  {#if space}
                    <div class="metric-value">Kp {space.kp_now ?? 'n/a'}</div>
                    <div class="muted">{space.summary}</div>
                    {#if space.kp_now != null}
                      <div class="kp-bar mt-2">
                        {#each Array.from({length:9},(_,i)=>i+1) as seg}
                          <div class="kp-cell" style={seg <= Math.floor(space.kp_now) ? `background:${kpSegColor(seg)}` : ''}></div>
                        {/each}
                      </div>
                    {/if}
                  {:else}<div class="muted">No space data yet.</div>{/if}
                </div>
              </div>
              <div class="col-md-4">
                <div class="card-dark p-3 h-100">
                  <div class="metric-label">BD Notes</div>
                  {#if bd}
                    <div class="fw-semibold">{bd.activities}</div>
                    {#if bd.notes}<div class="muted">{bd.notes}</div>{/if}
                  {:else}<div class="muted">No BD data yet.</div>{/if}
                </div>
              </div>
            </div>
          </div>

          {:else if slide.id === 'outlook-3'}
          <!-- ── Slide 2: Planting Outlook (3-day) ────────────────────────── -->
          <div class="section-title">Planting Outlook</div>
          <div class="glass p-3">
            <div class="row g-3">
              {#each forecast.slice(0,3) as item}
                <div class="col-md-4">
                  <div class="card-dark p-3 h-100">
                    <div class="fw-bold">{item.display_label}</div>
                    <div class="muted small d-flex align-items-center gap-1">
                      {#if item.bd}{@html moonIconSvg(item.bd.phase)}{item.bd.phase}{/if}
                    </div>
                    <div class="d-flex align-items-center mt-1 gap-1">
                      {#if item.bd}{@html bdIconSvg(item.bd.type)}{/if}
                      <span class="fs-5 fw-semibold">{formatTemp(item.wx.temp_min, item.wx.temp_max)}</span>
                    </div>
                    <div class="badge-soft mt-1">POP {formatPop(item.wx.pop)}</div>
                    <div class="muted small">{item.wx.description}</div>
                    <div class="small text-secondary mt-1">{item.suggestion}</div>
                  </div>
                </div>
              {/each}
            </div>
          </div>

          {:else if slide.id === 'outlook-7'}
          <!-- ── Slide 3: Extended Outlook ────────────────────────────────── -->
          <div class="section-title">Extended Planting Outlook</div>
          <div class="glass p-3">
            <div class="row g-3">
              {#each forecast.slice(3,6) as item}
                <div class="col-12 col-md-4">
                  <div class="card-dark p-3 h-100">
                    <div class="fw-bold d-flex align-items-center gap-1">
                      {#if item.bd}{@html bdIconSvg(item.bd.type)}{/if}
                      <span>{item.display_label}</span>
                    </div>
                    <div class="muted small d-flex align-items-center gap-1">
                      {#if item.bd}{@html moonIconSvg(item.bd.phase)}{item.bd.phase}{/if}
                    </div>
                    <div class="fs-6 fw-semibold">{formatTemp(item.wx.temp_min, item.wx.temp_max)}</div>
                    <div class="badge-soft mt-1">POP {formatPop(item.wx.pop)}</div>
                    {#if item.bd}<div class="small mt-1">BD: {item.bd.type}</div>{/if}
                    <div class="small text-secondary mt-1">{item.suggestion}</div>
                  </div>
                </div>
              {:else}
                <div class="col-12"><div class="muted">Extended forecast not available yet.</div></div>
              {/each}
            </div>
          </div>

          {:else if slide.id === 'almanac'}
          <!-- ── Slide 4: Enhanced Almanac ────────────────────────────────── -->
          <div class="section-title">Enhanced Almanac</div>
          <div class="glass p-3">
            <div class="row g-3">
              <div class="col-12">
                <div class="card-dark p-3">
                  {#if moonPhases.length}
                    <div class="fw-bold mb-2">Moon Phases</div>
                    <div class="d-flex flex-wrap gap-2 mb-3">
                      {#each moonPhases as m}
                        <div class="d-flex align-items-center gap-2 px-2 py-1 rounded" style="background:rgba(255,255,255,0.05); border:1px solid rgba(255,255,255,0.08);">
                          {@html moonIconSvg(m.phase)}
                          <span class="small">{m.phase}</span>
                          <span class="text-secondary small">{m.date}</span>
                        </div>
                      {/each}
                    </div>
                  {/if}
                  <div class="fw-bold mb-2">Sun &amp; Moon Rise/Set</div>
                  <div class="text-secondary small">Rise/set times are not available in the web version — run the local server for astronomical calculations.</div>
                </div>
              </div>
            </div>
          </div>

          {:else if slide.id === 'bd-outlook'}
          <!-- ── Slide 5: Biodynamic Outlook ──────────────────────────────── -->
          <div class="d-flex justify-content-between align-items-center mb-1">
            <div class="section-title mb-0">Biodynamic Outlook</div>
            {#if bdTotalPages > 1}<button class="badge-soft bd-page-btn" on:click={advanceBdPage} title="Tap to advance page">{bdPageIndex+1} / {bdTotalPages}</button>{/if}
          </div>
          <div class="glass p-3">
            {#if bdPageRanges.length}
              <div class="row g-2">
                {#each bdPageRanges as r}
                  <div class="col-12 col-md-4">
                    <div class="p-2 rounded" style="background:rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.06); min-height:80px;">
                      <div class="d-flex align-items-center mb-1 gap-1">
                        {@html bdIconSvg(r.type)}
                        {#if r.phase}{@html moonIconSvg(r.phase)}{/if}
                        <div class="fw-semibold small">{r.display_range}</div>
                      </div>
                      <div class="small text-uppercase">{r.type}</div>
                      <div class="text-secondary" style="font-size:.8rem;">{r.phase}</div>
                      {#if r.activities}<div class="text-secondary" style="font-size:.8rem;">{r.activities}</div>{/if}
                    </div>
                  </div>
                {/each}
              </div>
            {:else}
              <div class="text-secondary">No biodynamic periods available.</div>
            {/if}
          </div>

          {:else if slide.id === 'vinter'}
          <!-- ── Slide 6: Vinter's Outlook ────────────────────────────────── -->
          {#if bd && (wx || space)}
          {@const cellar = vinterCellar(bd)}
          <div class="section-title">Vinter's Outlook</div>
          <div class="glass p-3">
            <div class="row g-3">
              <div class="col-12 col-lg-6">
                <div class="card-dark p-3 h-100">
                  <div class="fw-bold mb-2">Cellar Timing Guidance</div>
                  <div class="mb-2" style="line-height:1.5;">
                    <span class="fw-bold" style="color:{cellar.color}">{cellar.label}</span><br>
                    <span class="text-secondary" style="line-height:1.5;">{cellar.text}</span>
                  </div>
                  <div class="text-secondary small mt-2" style="line-height:1.4;">{vinterMoon(bd)}</div>
                </div>
              </div>
              <div class="col-12 col-lg-6">
                <div class="card-dark p-3 h-100">
                  <div class="fw-bold mb-2">Energy of the Day</div>
                  <div class="d-flex justify-content-between align-items-center mb-2">
                    <span class="metric-label">Moon Phase</span>
                    <span class="fw-semibold text-end small">{bd.phase || '—'}</span>
                  </div>
                  <div class="text-secondary small mb-2">{vinterKp(space)}</div>
                  <div class="text-secondary small">{vinterTemp(wx)}</div>
                  {#if vinterNextHint(bd, bdRanges)}
                    <div class="text-secondary small mt-2" style="font-style:italic;">{vinterNextHint(bd, bdRanges)}</div>
                  {/if}
                </div>
              </div>
            </div>
          </div>
          {:else}
          <div class="section-title">Vinter's Outlook</div>
          <div class="glass p-4"><div class="muted">Loading data…</div></div>
          {/if}

          {:else if slide.id === 'kosmogrow'}
          <!-- ── Slide 7: KosmoGrow Advantage ─────────────────────────────── -->
          <div class="section-title">KosmoGrow Advantage</div>
          <div class="glass p-3">
            <div class="card-dark p-3 mb-3">
              <div class="fw-bold">Rotating Knowledge Nugget</div>
              <div class="text-secondary mt-1" style="line-height:1.5;">{KOSMO_TIPS[kosmoTipIndex]}</div>
            </div>
            <div class="text-secondary small">Premium lane for compost teas, biochar, biodynamic preps, and Kosmophytotrophia synergy. Tips rotate each pass.</div>
          </div>
          {/if}

        </section>
      {/each}
    </div>
  {/if}

  <!-- Slide dots (mobile only) -->
  {#if !loading && !error && visibleSlides.length > 0}
    <div class="slide-dots d-flex d-sm-none">
      {#each visibleSlides as _, i}
        <button class="slide-dot" class:active={i === slideIndex} on:click={() => goToSlide(i)} aria-label="Slide {i+1}"></button>
      {/each}
    </div>
  {/if}

  <!-- Last updated -->
  {#if lastUpdated && !loading}
    <div class="text-secondary" style="font-size:.7rem; text-align:right; flex-shrink:0; padding:.25rem .5rem;">Updated {formatDate(lastUpdated)}</div>
  {/if}
</div>

<!-- ── Mobile bottom bar (portrait only) ────────────────────────────────── -->
<div class="bottom-bar d-flex d-sm-none align-items-center gap-2 px-3">
  <button class="btn btn-sm btn-outline-light pill-btn flex-shrink-0" on:click={() => showSettings = true}>Settings</button>
  <div class="d-flex gap-1 align-items-center flex-grow-1" style="min-width:0;">
    <input class="zip-input" style="min-width:0; flex:1;" type="text" inputmode="numeric" maxlength="5" placeholder="ZIP"
      bind:value={zipInput} on:keydown={e => e.key === 'Enter' && applyZip()} aria-label="ZIP code" />
    <button class="btn btn-sm btn-outline-light pill-btn flex-shrink-0" on:click={applyZip}>Go</button>
  </div>
  {#if alerts.length && alertsCollapsed}
    <button class="btn btn-sm alert-chip pill-btn flex-shrink-0" on:click={() => alertsCollapsed = false}
      title={alerts[0].text}>⚠</button>
  {/if}
  <button class="btn btn-sm btn-outline-light pill-btn flex-shrink-0" on:click|stopPropagation={handleMusicButton}
    title={muted ? 'Unmute' : 'Mute'}>
    {muted ? '🔇' : '🔊'}
  </button>
</div>

<!-- ── Settings overlay ───────────────────────────────────────────────────── -->
{#if showSettings}
  <div class="screen-overlay">
    <div class="screen-picker">
      <h5 class="fw-bold">Settings</h5>
      <!-- Screens -->
      <div class="mb-3">
        <div class="d-flex justify-content-between align-items-center mb-1">
          <label class="form-label small fw-semibold mb-0">Screens</label>
          <button class="btn btn-link btn-sm p-0 text-secondary" style="font-size:.75rem;"
            on:click={() => { screenPickerSelected = new Set(SLIDE_META.map(s=>s.id)); }}>Select all</button>
        </div>
        <div style="max-height:160px; overflow-y:auto;">
          {#each SLIDE_META as s}
            <div class="form-check mb-1">
              <input class="form-check-input" type="checkbox" id="cfg-{s.id}" checked={screenPickerSelected.has(s.id)}
                on:change={() => toggleScreen(s.id)} />
              <label class="form-check-label" for="cfg-{s.id}">{s.label}</label>
            </div>
          {/each}
        </div>
      </div>
      <!-- Units -->
      <div class="mb-2">
        <label class="form-label small">Units</label>
        <select class="form-select form-select-sm" bind:value={units}>
          <option value="metric">Metric (°C)</option>
          <option value="imperial">Imperial (°F)</option>
        </select>
      </div>
      <div class="form-check form-switch mb-2">
        <input class="form-check-input" type="checkbox" id="toggleKiosk" bind:checked={kioskMode} />
        <label class="form-check-label" for="toggleKiosk">Kiosk mode (fullscreen)</label>
      </div>
      <div class="mb-3">
        <label class="form-label small">Scroll speed (seconds per slide)</label>
        <input type="number" min="5" max="60" step="1" class="form-control form-control-sm" bind:value={scrollSeconds} />
      </div>
      <div class="d-flex gap-2">
        <button class="btn btn-primary w-100" on:click={savePrefs}>Save</button>
        <button class="btn btn-outline-light" on:click={() => showSettings = false}>Cancel</button>
      </div>
    </div>
  </div>
{/if}

<style>
  :global(html) { height: 100%; }
  :global(body) {
    background: radial-gradient(circle at 20% 20%, #16213e 0%, #0a0f1f 35%, #050910 100%);
    color: #e9edf5;
    height: 100dvh;
    overflow: hidden;
    overscroll-behavior: none;
    display: flex;
    flex-direction: column;
    margin: 0;
    padding: env(safe-area-inset-top,0) env(safe-area-inset-right,0) env(safe-area-inset-bottom,0) env(safe-area-inset-left,0);
  }
  :global(#app) { flex: 1; display: flex; flex-direction: column; overflow: hidden; }

  #app-root { flex: 1; display: flex; flex-direction: column; overflow: hidden; min-height: 0; }

  #slides-wrapper {
    flex: 1; position: relative; overflow: hidden; min-height: 0;
  }

  .view-slide {
    position: absolute; inset: 0; overflow-y: auto;
    -webkit-overflow-scrolling: touch;
    padding: 1rem 3.5rem;
    display: none; box-sizing: border-box;
  }
  .view-slide.active { display: block; }

  @media (max-width: 576px) {
    .view-slide { padding: .75rem .5rem; }
    .slide-nav  { display: none; }
    #app-root   { padding-bottom: 64px; }
  }

  .slide-nav {
    position: absolute; top: 50%; transform: translateY(-50%); z-index: 100;
    background: rgba(255,255,255,.07); border: 1px solid rgba(255,255,255,.15);
    color: #e9edf5; border-radius: 50%; width: 44px; height: 44px;
    display: flex; align-items: center; justify-content: center;
    cursor: pointer; font-size: 1.6rem; opacity: .2; transition: opacity .25s; padding: 0;
  }
  .slide-nav:hover, .slide-nav:focus { opacity: 1; outline: none; }
  .slide-nav-prev { left: 6px; }
  .slide-nav-next { right: 6px; }

  .glass {
    background: rgba(255,255,255,.08); border: 1px solid rgba(255,255,255,.1);
    box-shadow: 0 10px 30px rgba(0,0,0,.35); backdrop-filter: blur(6px); border-radius: 18px;
  }
  .card-dark {
    background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.08);
    color: #e9edf5; border-radius: 12px;
  }
  .hero-title  { letter-spacing: .04em; }
  .section-title { letter-spacing: .05em; text-transform: uppercase; font-size: .9rem; color: #9fb3c8; margin-bottom: .4rem; }
  .metric-label  { text-transform: uppercase; letter-spacing: .06em; font-size: .75rem; color: #9fb3c8; }
  .metric-value  { font-size: 2rem; font-weight: 700; }
  .badge-soft    { background: rgba(255,255,255,.12); color: #c7d3e3; border-radius: 10px; padding: 4px 8px; font-size: .8rem; }
  .muted         { color: #a8b6c8; }
  .pill-btn      { border-radius: 999px; min-height: 44px; }
  .ticker        { background: linear-gradient(90deg,#d7263d,#f19a3e); color:#fff; border-radius:12px; padding:10px 14px; font-weight:600; box-shadow:0 6px 16px rgba(0,0,0,.35); }

  .kp-bar  { display: grid; grid-template-columns: repeat(9,1fr); gap: 4px; margin-top: 6px; }
  .kp-cell { height: 10px; border-radius: 4px; background: rgba(255,255,255,.1); }

  .zip-input {
    width: 6rem; padding: .3rem .6rem; border-radius: 8px;
    border: 1px solid rgba(255,255,255,.2); background: rgba(255,255,255,.07);
    color: #e9edf5; font-size: .9rem; min-height: 44px;
  }
  .zip-input:focus { outline: none; border-color: rgba(255,255,255,.5); }

  /* Icons from {@html} — must be global */
  :global(.bd-icon)   { width: 28px; height: 28px; display: inline-block; vertical-align: middle; flex-shrink: 0; }
  :global(.moon-icon) { width: 24px; height: 24px; display: inline-block; vertical-align: middle; flex-shrink: 0; }

  /* Overlays */
  .screen-overlay {
    position: fixed; inset: 0; background: rgba(5,9,16,.9); z-index: 2000;
    display: flex; align-items: center; justify-content: center; padding: 1rem;
  }
  .screen-picker {
    max-width: 420px; width: 100%; background: rgba(255,255,255,.06);
    border: 1px solid rgba(255,255,255,.12); border-radius: 16px; padding: 1rem;
    box-shadow: 0 10px 40px rgba(0,0,0,.4); color: #e9edf5;
  }

  :global(.form-control), :global(.form-select) {
    background-color: #0f1625 !important; color: #e9edf5 !important;
    border: 1px solid rgba(255,255,255,.15) !important;
  }
  :global(.form-control:focus), :global(.form-select:focus) {
    background-color: #0f1625 !important; color: #e9edf5 !important;
    box-shadow: 0 0 0 .15rem rgba(255,255,255,.15) !important;
  }
  :global(.form-check-label) { color: #e9edf5; }

  .bottom-bar {
    position: fixed; bottom: 0; left: 0; right: 0; height: 60px;
    background: rgba(5,9,16,.95); border-top: 1px solid rgba(255,255,255,.1);
    z-index: 500;
    padding-bottom: env(safe-area-inset-bottom, 0);
    padding-left: env(safe-area-inset-left, 0);
    padding-right: env(safe-area-inset-right, 0);
  }

  .slide-dots { justify-content: center; gap: 8px; padding: 4px 0; flex-shrink: 0; }
  .slide-dot {
    width: 8px; height: 8px; border-radius: 50%; border: none; padding: 0; cursor: pointer;
    background: rgba(255,255,255,.3); transition: background .2s, transform .2s; flex-shrink: 0;
  }
  .slide-dot.active { background: #e9edf5; transform: scale(1.3); }

  .alert-chip {
    background: linear-gradient(90deg,#d7263d,#f19a3e); color: #fff;
    border: none; font-size: .9rem; padding: 0 8px;
  }
  .bd-page-btn {
    background: rgba(255,255,255,.12); color: #c7d3e3;
    border: none; border-radius: 10px; padding: 4px 8px;
    font-size: .75rem; cursor: pointer; transition: background .2s;
  }
  .bd-page-btn:hover, .bd-page-btn:focus { background: rgba(255,255,255,.22); outline: none; }
</style>
