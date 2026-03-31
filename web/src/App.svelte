<script>
  import { onMount } from 'svelte';

  const DEFAULT_API_URL = 'http://localhost:5000/api/status';
  const configuredApiUrl = (import.meta.env.VITE_API_URL || '').trim();
  const apiUrl = configuredApiUrl || DEFAULT_API_URL;

  let data = null;
  let loading = true;
  let error = '';
  let lastUpdated = '';

  function formatDate(value) {
    if (!value) return '';
    try {
      return new Date(value).toLocaleString();
    } catch {
      return '';
    }
  }

  function formatTemp(min, max) {
    if (min == null || max == null) return '—';
    return `${Math.round(min)}°C – ${Math.round(max)}°C`;
  }

  function formatPop(pop) {
    const pct = Math.round((Number(pop) || 0) * 100);
    return `${pct}%`;
  }

  async function refreshStatus() {
    try {
      const res = await fetch(apiUrl, { cache: 'no-store' });
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
      data = await res.json();
      error = '';
      lastUpdated = new Date().toISOString();
    } catch (err) {
      error = `Unable to load status from ${apiUrl} (${err?.message || 'unknown error'})`;
    } finally {
      loading = false;
    }
  }

  onMount(() => {
    refreshStatus();
    const timer = setInterval(refreshStatus, 5 * 60 * 1000);
    return () => clearInterval(timer);
  });
</script>

<main>
  <header>
    <h1>KosmoStream</h1>
    <p>Cosmic-aligned planting dashboard (Svelte)</p>
    <small>API: {apiUrl}</small>
  </header>

  {#if loading}
    <section class="card">Loading status…</section>
  {:else if error}
    <section class="card error">{error}</section>
  {:else if data}
    <section class="grid">
      <article class="card">
        <h2>Biodynamic</h2>
        <p class="value">{data.bd?.type || 'No data'}</p>
        <p>{data.bd?.phase || ''}</p>
        <p>{data.bd?.activities || ''}</p>
      </article>

      <article class="card">
        <h2>Weather</h2>
        <p class="value">{formatTemp(data.weather?.temp_min, data.weather?.temp_max)}</p>
        <p>{data.weather?.description || 'No data'}</p>
        <p>POP: {formatPop(data.weather?.pop)}</p>
      </article>

      <article class="card">
        <h2>Space Weather</h2>
        <p class="value">Kp {data.space?.kp_now ?? 'n/a'}</p>
        <p>{data.space?.summary || 'No data'}</p>
      </article>
    </section>

    <section class="card">
      <h2>Suggestion</h2>
      <p>{data.suggestion || 'No suggestion available.'}</p>
    </section>

    <section class="card">
      <h2>Alerts</h2>
      {#if data.alerts?.length}
        <ul>
          {#each data.alerts as alert}
            <li>{alert.text}</li>
          {/each}
        </ul>
      {:else}
        <p>No active alerts.</p>
      {/if}
    </section>
  {/if}

  <footer>
    <button type="button" on:click={refreshStatus}>Refresh now</button>
    {#if lastUpdated}
      <small>Last updated: {formatDate(lastUpdated)}</small>
    {/if}
  </footer>
</main>
