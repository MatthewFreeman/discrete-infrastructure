// Read-only observations. A completed webhook cycle is NOT a delivery receipt.
export const components = ['scanner', 'webhook'];
// Root-controlled collector environment; never accept a remote unit argument.
export function workerUnit(value = 'discrete-pay-worker.service') {
  if (!['discrete-pay-worker.service', 'discrete-pay-app-worker.service'].includes(value)) {
    throw new Error('unsupported worker unit');
  }
  return value;
}
const codes = new Set(['success', 'catching_up', 'deep_reorg', 'scanner_behind',
  'chain_invalid', 'rpc_unavailable', 'cycle_failed']);
const issueKeys = new Set(['worker_inactive', 'snapshot_unavailable',
  ...components.flatMap(component => [`${component}_stale`,
    ...[...codes].filter(code => code !== 'success').map(code => `${component}_${code}`)])]);

export function validateState(state, now) {
  const fields = new Set(['candidate', 'count', 'confirmed', 'initialized', 'queue', 'failures', 'nextAttemptAt']);
  const validIssues = value => Array.isArray(value) && value.length <= 3
    && new Set(value).size === value.length && value.every(key => issueKeys.has(key));
  if (!state || typeof state !== 'object' || Array.isArray(state)
      || Object.keys(state).some(key => !fields.has(key))) throw new Error('invalid state');
  for (const key of ['candidate', 'confirmed']) {
    if (state[key] !== undefined && (typeof state[key] !== 'string'
        || !validIssues(state[key] === '' ? [] : state[key].split(',')))) throw new Error('invalid issue state');
  }
  for (const [key, max] of [['count', 3], ['failures', 5], ['nextAttemptAt', now + 360_000]]) {
    if (state[key] !== undefined && (!Number.isSafeInteger(state[key]) || state[key] < 0 || state[key] > max)) throw new Error('invalid counter');
  }
  if (state.initialized !== undefined && typeof state.initialized !== 'boolean') throw new Error('invalid initial state');
  if (state.queue !== undefined && (!Array.isArray(state.queue) || state.queue.length > 32
      || state.queue.some(entry => !entry || Object.keys(entry).sort().join(',') !== 'at,id,issues'
        || !Number.isSafeInteger(entry.at) || entry.at < 0 || entry.at > now + 5_000
        || entry.id !== `pay-${entry.at}` || !validIssues(entry.issues)))) throw new Error('invalid queue');
  return state;
}

export function cycle(value) {
  if (!value || value.event !== 'worker_cycle' || !components.includes(value.component)
      || !codes.has(value.code) || typeof value.ok !== 'boolean'
      || value.ok !== (value.code === 'success')
      || !Number.isSafeInteger(value.timestamp_ms) || value.timestamp_ms < 0) return null;
  return {component: value.component, ok: value.ok, code: value.code, at: value.timestamp_ms};
}

// Read only the selected unit's current invocation; never export raw journal text.
export function fromJournal(lines, invocation, now) {
  const samples = {scanner: null, webhook: null};
  for (const line of lines.split('\n')) {
    try {
      const entry = JSON.parse(line);
      if (!invocation || entry._SYSTEMD_INVOCATION_ID !== invocation || typeof entry.MESSAGE !== 'string') continue;
      const value = cycle(JSON.parse(entry.MESSAGE));
      if (value && value.at <= now + 5_000 && value.at > (samples[value.component]?.at ?? -1)) {
        samples[value.component] = value;
      }
    } catch { /* unrelated/invalid lines do not become observations */ }
  }
  return samples;
}

export function issues(snapshot, now) {
  if (!snapshot || snapshot.version !== 1 || !Number.isSafeInteger(snapshot.at)
      || snapshot.at > now + 5_000 || now - snapshot.at > 30_000
      || typeof snapshot.active !== 'boolean' || !snapshot.samples) throw new Error('invalid snapshot');
  const result = [];
  if (!snapshot.active) result.push('worker_inactive');
  for (const component of components) {
    const value = snapshot.samples[component];
    if (value === null) { result.push(`${component}_stale`); continue; }
    if (!value || value.component !== component || !codes.has(value.code)
        || typeof value.ok !== 'boolean' || value.ok !== (value.code === 'success')
        || !Number.isSafeInteger(value.at) || value.at < 0 || value.at > now + 5_000) throw new Error('invalid sample');
    if (now - value.at > 180_000) result.push(`${component}_stale`);
    else if (!value.ok) result.push(`${component}_${value.code}`);
  }
  return result.sort();
}

// Repeated observations open after three polls and resolve after two. One bounded
// pending queue survives delivery failure/restart; notifications have a stable id.
export function observe(state, current, now) {
  const key = [...current].sort().join(',');
  if (state.candidate !== key) { state.candidate = key; state.count = 0; }
  state.count = Math.min((state.count ?? 0) + 1, 3);
  if (state.count >= (key ? 3 : 2) && state.confirmed !== key) {
    // Do not send a spurious recovery on an initially good baseline.
    if (state.initialized || key) {
      state.queue ??= [];
      if (state.queue.length >= 32) throw new Error('notification queue full');
      state.queue.push({id: `pay-${now}`, issues: [...current].sort(), at: now});
    }
    state.confirmed = key;
    state.initialized = true;
  }
  return state;
}

export async function tick(state, ports) {
  let current;
  try { current = issues(await ports.snapshot(), ports.now()); }
  catch { current = ['snapshot_unavailable']; }
  observe(state, current, ports.now());
  await ports.save(state); // persist BEFORE contacting the external receiver
  if (state.queue?.length && ports.now() >= (state.nextAttemptAt ?? 0)) {
    try {
      await ports.send(state.queue[0]);
      state.queue.shift(); state.failures = 0; state.nextAttemptAt = 0;
    } catch {
      state.failures = Math.min((state.failures ?? 0) + 1, 5);
      state.nextAttemptAt = ports.now() + Math.min(300_000, 10_000 * 2 ** state.failures);
    }
    await ports.save(state);
  }
}
