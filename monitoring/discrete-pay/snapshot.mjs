// Root-owned forced command. No journal, database, network or wallet access.
import {openSync, closeSync, fstatSync, readSync, constants} from 'node:fs';
import {issues} from './policy.mjs';
try {
  if (process.env.SSH_ORIGINAL_COMMAND !== 'snapshot') throw new Error('command denied');
  const fd = openSync('/run/discrete-pay-observer/snapshot.json', constants.O_RDONLY | constants.O_NOFOLLOW);
  let value;
  try {
    const info = fstatSync(fd);
    if (!info.isFile() || info.uid !== 0 || (info.mode & 0o022) || info.size > 4096) throw new Error('invalid snapshot file');
    const bytes = Buffer.alloc(4097);
    const count = readSync(fd, bytes, 0, bytes.length, 0);
    if (count > 4096) throw new Error('oversize snapshot');
    value = JSON.parse(bytes.subarray(0, count).toString('utf8'));
    issues(value, Date.now());
  } finally { closeSync(fd); }
  process.stdout.write(JSON.stringify(value) + '\n');
} catch {
  process.stderr.write('snapshot unavailable\n');
  process.exitCode = 1;
}
