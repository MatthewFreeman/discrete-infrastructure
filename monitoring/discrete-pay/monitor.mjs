import {execFile} from 'node:child_process';
import {open, rename} from 'node:fs/promises';
import {promisify} from 'node:util';
import {tick, validateState} from './policy.mjs';

const run = promisify(execFile);
const stateFile = '/var/lib/discrete-pay-monitor/state.json';
const configFile = '/etc/discrete-pay-monitor/telegram.json';
let stop = false;
let wake;
for (const signal of ['SIGTERM', 'SIGINT']) process.once(signal, () => { stop = true; wake?.(); });

async function boundedJson(path, limit) {
  const file = await open(path, 'r');
  try {
    const info = await file.stat();
    if (!info.isFile() || info.size > limit) throw new Error('invalid file');
    const buffer = Buffer.alloc(limit + 1);
    const {bytesRead} = await file.read(buffer, 0, buffer.length, 0);
    if (bytesRead > limit) throw new Error('oversize file');
    return JSON.parse(buffer.subarray(0, bytesRead).toString('utf8'));
  } finally { await file.close(); }
}

async function persist(state) {
  const file = await open(`${stateFile}.tmp`, 'w', 0o600);
  try { await file.writeFile(JSON.stringify(state)); await file.sync(); } finally { await file.close(); }
  await rename(`${stateFile}.tmp`, stateFile);
}

async function notify(config, pending) {
  const response = await fetch(`https://api.telegram.org/bot${config.token}/sendMessage`, {
    method: 'POST', redirect: 'error', signal: AbortSignal.timeout(10_000),
    headers: {'content-type': 'application/json'},
    body: JSON.stringify({chat_id: config.chatId, disable_notification: false,
      text: `[Discrete Pay] ${pending.issues.length ? 'ALERT: ' + pending.issues.join(', ') : 'RECOVERED'}\n${pending.id}`}),
  });
  // Bound response parsing; never log API bodies or the credential-bearing URL.
  const reader = response.body?.getReader();
  if (!reader) throw new Error('no response');
  let length = 0; const chunks = [];
  try {
    for (;;) {
      const {done, value} = await reader.read();
      if (done) break;
      length += value.length;
      if (length > 16_384) throw new Error('oversize response');
      chunks.push(Buffer.from(value));
    }
  } finally { await reader.cancel(); }
  if (!response.ok || JSON.parse(Buffer.concat(chunks).toString('utf8')).ok !== true) throw new Error('delivery rejected');
}

try {
  const config = await boundedJson(configFile, 4096);
  if (!config || Object.keys(config).sort().join(',') !== 'chatId,token'
      || typeof config.token !== 'string' || !/^\d+:[A-Za-z0-9_-]{30,}$/.test(config.token)
      || typeof config.chatId !== 'string' || !/^-?\d+$/.test(config.chatId)) throw new Error('invalid destination');
  let state;
  try { state = await boundedJson(stateFile, 16_384); }
  catch (error) { if (error.code !== 'ENOENT') throw error; state = {}; }
  // Invalid persisted data stops the observer rather than hiding an incident.
  validateState(state, Date.now());
  while (!stop) {
    await tick(state, {now: Date.now, save: persist, send: pending => notify(config, pending), snapshot: async () => {
      const {stdout} = await run('/usr/bin/ssh', ['-F', '/etc/discrete-pay-monitor/ssh_config',
        '-oBatchMode=yes', '-oStrictHostKeyChecking=yes', '-oClearAllForwardings=yes',
        '-oConnectTimeout=5', 'pay-observer', 'snapshot'],
      {timeout: 15_000, killSignal: 'SIGKILL', maxBuffer: 16_384});
      return JSON.parse(stdout);
    }});
    await new Promise(resolve => { const timer = setTimeout(resolve, 10_000);
      wake = () => { clearTimeout(timer); resolve(); }; if (stop) wake(); });
  }
} catch {
  process.stderr.write('monitor stopped: configuration, state or local I/O failure\n');
  process.exitCode = 1;
}
