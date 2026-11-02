<script lang="ts">
  import { env } from '$env/dynamic/public';
  import { onMount } from 'svelte';

  import {
    createApi,
    statusLabel,
    type Drone,
    type Eligibility,
    type EventRecord,
    type Mission
  } from '$lib/api';

  const apiOrigin = env.PUBLIC_TRETA_API_ORIGIN || 'http://127.0.0.1:8000';
  const api = createApi(apiOrigin);

  let drones: Drone[] = [];
  let missions: Mission[] = [];
  let events: EventRecord[] = [];
  let eligibility: Eligibility | null = null;
  let incidentCount = 0;
  let running = false;
  let elapsedSeconds = 0;
  let replayDeterministic: boolean | null = null;
  let busy = false;
  let error = '';

  async function refresh() {
    const [nextDrones, nextMissions, nextEvents, incidents, simulation] =
      await Promise.all([
        api.request<Drone[]>('/api/v1/drones', 'viewer'),
        api.request<Mission[]>('/api/v1/missions', 'viewer'),
        api.request<EventRecord[]>('/api/v1/events?limit=500', 'viewer'),
        api.request<unknown[]>('/api/v1/incidents', 'viewer'),
        api.request<{ running: boolean; elapsed_seconds: number }>(
          '/api/v1/simulation/status',
          'viewer'
        )
      ]);
    drones = nextDrones;
    missions = nextMissions;
    events = nextEvents;
    incidentCount = incidents.length;
    running = simulation.running;
    elapsedSeconds = simulation.elapsed_seconds;
  }

  async function runVerticalSlice() {
    busy = true;
    error = '';
    replayDeterministic = null;
    try {
      await api.request(
        '/api/v1/simulation/start',
        'simulator_engineer',
        'POST'
      );
      const mission = await api.request<Mission>(
        '/api/v1/missions',
        'mission_planner',
        'POST',
        {
          origin: { latitude_deg: 0.01, longitude_deg: 0.01 },
          destination: { latitude_deg: 0.014, longitude_deg: 0.015 },
          payload_kg: 1.2,
          minimum_landing_reserve_percent: 25
        }
      );
      eligibility = await api.request<Eligibility>(
        `/api/v1/missions/${mission.mission_id}/evaluate`,
        'mission_planner',
        'POST'
      );
      await api.request(
        `/api/v1/missions/${mission.mission_id}/assign`,
        'mission_planner',
        'POST'
      );
      await api.request(
        `/api/v1/missions/${mission.mission_id}/start`,
        'operator',
        'POST'
      );
      if (!eligibility.selected_drone_id)
        throw new Error('No eligible drone was selected.');
      await api.request(
        '/api/v1/simulation/failures',
        'simulator_engineer',
        'POST',
        {
          drone_id: eligibility.selected_drone_id,
          failure_type: 'RAPID_BATTERY_DRAIN',
          severity: 'HIGH',
          multiplier: 25
        }
      );
      await api.request(
        '/api/v1/simulation/step',
        'simulator_engineer',
        'POST',
        { seconds: 8 }
      );
      await api.request(
        '/api/v1/simulation/pause',
        'simulator_engineer',
        'POST'
      );
      const replay = await api.request<{ deterministic: boolean }>(
        `/api/v1/missions/${mission.mission_id}/replay`,
        'viewer'
      );
      replayDeterministic = replay.deterministic;
      await refresh();
    } catch (caught) {
      error =
        caught instanceof Error
          ? caught.message
          : 'Unknown local simulation error';
    } finally {
      busy = false;
    }
  }

  onMount(() => {
    refresh().catch((caught: unknown) => {
      error =
        caught instanceof Error
          ? caught.message
          : 'Unable to load the synthetic fleet';
    });
  });
</script>

<svelte:head>
  <title>Treta · Synthetic fleet operations</title>
</svelte:head>

<header class="truth-banner">
  <strong>LOCAL · SIMULATION ONLY</strong>
  <span
    >Simulator success does not establish airworthiness. Physical control is
    disabled.</span
  >
</header>

<main>
  <section class="hero" aria-labelledby="page-title">
    <div>
      <p class="eyebrow">Deterministic autonomy control plane</p>
      <h1 id="page-title">Synthetic fleet operations</h1>
      <p>
        Evaluate, dispatch, fail safely, investigate, and replay one complete
        delivery mission.
      </p>
    </div>
    <button class="primary" onclick={runVerticalSlice} disabled={busy}>
      {busy ? 'Running verified flow…' : 'Run battery-reserve scenario'}
    </button>
  </section>

  {#if error}
    <div class="alert critical" role="alert">
      <strong>Operator action required:</strong>
      {error}
    </div>
  {/if}

  <section class="metrics" aria-label="Simulation summary">
    <article><span>Environment</span><strong>Local</strong></article>
    <article>
      <span>Simulation</span><strong>{running ? 'Running' : 'Stopped'}</strong>
    </article>
    <article>
      <span>Simulated time</span><strong>{elapsedSeconds} s</strong>
    </article>
    <article><span>Incidents</span><strong>{incidentCount}</strong></article>
    <article>
      <span>Replay</span>
      <strong
        >{replayDeterministic === null
          ? 'Not run'
          : replayDeterministic
            ? 'Deterministic'
            : 'Mismatch'}</strong
      >
    </article>
  </section>

  <section class="panel" aria-labelledby="fleet-heading">
    <div class="panel-heading">
      <div>
        <p class="eyebrow">Live projection</p>
        <h2 id="fleet-heading">Three-vehicle fleet</h2>
      </div>
      <button class="secondary" onclick={refresh}>Refresh telemetry</button>
    </div>
    <div class="table-wrap">
      <table>
        <caption>Current synthetic drone state and data freshness</caption>
        <thead
          ><tr
            ><th>Vehicle</th><th>Profile</th><th>Status</th><th>Battery</th><th
              >GPS / link</th
            ><th>Freshness</th></tr
          ></thead
        >
        <tbody>
          {#each drones as drone (drone.drone_id)}
            <tr>
              <td
                ><strong>{drone.name}</strong><small
                  >{drone.drone_id} · simulated</small
                ></td
              >
              <td>{drone.profile.name}</td>
              <td
                ><span class:warning={drone.health === 'WARNING'} class="status"
                  >{statusLabel(drone.state)}</span
                ></td
              >
              <td><strong>{drone.battery_percent.toFixed(1)}%</strong></td>
              <td
                >{statusLabel(drone.gps_quality)} / {drone.link_quality_percent.toFixed(
                  0
                )}%</td
              >
              <td
                ><time datetime={drone.last_observed_at}
                  >{drone.last_observed_at}</time
                ></td
              >
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </section>

  <div class="two-column">
    <section class="panel" aria-labelledby="eligibility-heading">
      <p class="eyebrow">Explainable policy</p>
      <h2 id="eligibility-heading">Mission eligibility</h2>
      {#if eligibility}
        <p>
          Safest selected vehicle: <strong
            >{eligibility.selected_drone_id}</strong
          >
        </p>
        <ul class="decision-list">
          {#each eligibility.drones as result (result.drone_id)}
            <li class:accepted={result.eligible}>
              <strong
                >{result.drone_id} · {result.eligible
                  ? 'Eligible'
                  : 'Rejected'}</strong
              >
              <span
                >{result.reasons
                  .map((reason) => `${reason.rule_id}: ${reason.reason}`)
                  .join(' ')}</span
              >
            </li>
          {/each}
        </ul>
      {:else}
        <p class="empty">
          Run the scenario to see eligible and rejected drones with rule
          reasons.
        </p>
      {/if}
    </section>

    <section class="panel" aria-labelledby="mission-heading">
      <p class="eyebrow">Command truth</p>
      <h2 id="mission-heading">Mission state</h2>
      {#if missions.length}
        {#each missions as mission (mission.mission_id)}
          <article class="mission-card">
            <strong>{mission.mission_id}</strong>
            <span class="status critical">{statusLabel(mission.state)}</span>
            <p>Assigned: {mission.assigned_drone_id ?? 'Not assigned'}</p>
            <p>Landing reserve: {mission.minimum_landing_reserve_percent}%</p>
          </article>
        {/each}
      {:else}
        <p class="empty">No mission has been created.</p>
      {/if}
    </section>
  </div>

  <section class="panel" aria-labelledby="timeline-heading">
    <p class="eyebrow">Append-only audit view</p>
    <h2 id="timeline-heading">Incident and decision timeline</h2>
    {#if events.length}
      <ol class="timeline">
        {#each [...events].reverse().slice(0, 30) as event (event.event_id)}
          <li>
            <span class="event-dot" aria-hidden="true"></span>
            <div>
              <strong>{event.event_type}</strong><small
                >{event.event_id} · {event.producer}</small
              >
            </div>
            <time datetime={event.occurred_at}>{event.occurred_at}</time>
          </li>
        {/each}
      </ol>
    {:else}
      <p class="empty">No audit events are available.</p>
    {/if}
  </section>
</main>

<footer>
  Free-tier infrastructure has no acceptable mission-critical SLA.
  Software-in-the-loop testing does not replace hardware-in-the-loop testing.
  Near-zero latency cannot be guaranteed over the public internet.
</footer>
