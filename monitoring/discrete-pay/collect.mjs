// Local privileged oneshot with fixed read-only commands; never remotely invoked.
// Only the redacted result is made readable by the SSH observer account.
import {execFileSync} from 'node:child_process';
import {openSync, writeFileSync, fsyncSync, closeSync, renameSync} from 'node:fs';
import {randomUUID} from 'node:crypto';
import {fromJournal, issues, workerUnit} from './policy.mjs';

try {
  const unit = workerUnit(process.env.PAY_OBSERVER_WORKER_UNIT);
  const info = execFileSync('/usr/bin/systemctl', ['show', unit, '--property=ActiveState,InvocationID,LoadState'],
    {encoding: 'utf8', timeout: 5_000, maxBuffer: 4096, stdio: ['ignore', 'pipe', 'ignore']});
  const values = Object.fromEntries(info.trim().split('\n').map(line => line.split('=')));
  if (!['active', 'inactive', 'failed', 'activating', 'deactivating'].includes(values.ActiveState)) throw new Error('unknown unit');
  const invocation = /^[a-f0-9]{32}$/.test(values.InvocationID ?? '') ? values.InvocationID : '';
  const lines = invocation ? execFileSync('/usr/bin/journalctl', ['--quiet', '--no-pager', '--output=json',
    '--unit', unit, '--since=-5min', '--lines=256'],
  {encoding: 'utf8', timeout: 5_000, maxBuffer: 1_048_576, stdio: ['ignore', 'pipe', 'ignore']}) : '';
  const at = Date.now();
  const value = {version: 1, at, active: values.ActiveState === 'active', samples: fromJournal(lines, invocation, at)};
  issues(value, at);
  const path = `/run/discrete-pay-observer/.snapshot-${randomUUID()}`;
  const fd = openSync(path, 'wx', 0o644);
  try { writeFileSync(fd, JSON.stringify(value) + '\n'); fsyncSync(fd); } finally { closeSync(fd); }
  renameSync(path, '/run/discrete-pay-observer/snapshot.json');
} catch {
  process.stderr.write('collector unavailable\n');
  process.exitCode = 1;
}
