param(
    [ValidatePattern('^[0-9]{2}$')]
    [string]$Ordinal = '01',

    [Parameter(Mandatory = $true)]
    [string]$UbuntuHost,

    [Parameter(Mandatory = $true)]
    [string]$DebianHost,

    [Parameter(Mandatory = $true)]
    [string]$KeyPath,

    [Parameter(Mandatory = $true)]
    [string]$KnownHostsPath,

    [ValidateRange(1, 65535)]
    [int]$SshPort = 22822
)

$ErrorActionPreference = 'Stop'
$Hosts = @(
    [pscustomobject]@{ Label = 'ubuntu'; Target = $UbuntuHost; Os = 'ubuntu24.04' },
    [pscustomobject]@{ Label = 'debian'; Target = $DebianHost; Os = 'debian12' }
)
$SshArgs = @(
    '-i', $KeyPath, '-p', "$SshPort", '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes',
    '-o', 'StrictHostKeyChecking=yes', '-o', "UserKnownHostsFile=$KnownHostsPath"
)
$RemoteHarness = '/opt/discrete-benchmark/harness/v.0.9.5/cross-os/reboot-validation-host.sh'
$RemoteArm = '/usr/local/sbin/discrete-benchmark-arm-mem512'
$RemoteDropIn = '/etc/default/grub.d/99-discrete-benchmark-mem512.cfg'
$RemoteRollback = '/usr/local/sbin/discrete-benchmark-rollback-mem512'

function Invoke-Remote {
    param([string]$Target, [string]$Command, [switch]$AllowFailure)
    $output = & ssh.exe @SshArgs $Target $Command
    $exitCode = $LASTEXITCODE
    if (-not $AllowFailure -and $exitCode -ne 0) {
        throw "SSH failed on $Target with exit code $exitCode"
    }
    return [pscustomobject]@{ Output = ($output -join "`n"); ExitCode = $exitCode }
}

function Wait-ForNewBoot {
    param([string]$Target, [string]$OldBootId, [int]$TimeoutSeconds = 300)
    $timer = [Diagnostics.Stopwatch]::StartNew()
    Start-Sleep -Seconds 5
    while ($timer.Elapsed.TotalSeconds -lt $TimeoutSeconds) {
        $probe = Invoke-Remote -Target $Target -Command 'cat /proc/sys/kernel/random/boot_id' -AllowFailure
        if ($probe.ExitCode -eq 0 -and $probe.Output.Trim() -ne $OldBootId) { return }
        Start-Sleep -Seconds 3
    }
    throw "A new boot ID was not observed on $Target within $TimeoutSeconds seconds"
}

$prepared = @{}
try {
    foreach ($hostInfo in $Hosts) {
        $result = Invoke-Remote -Target $hostInfo.Target -Command "sudo '$RemoteHarness' prepare '$($hostInfo.Os)' '$Ordinal'"
        $prepared[$hostInfo.Label] = $true
        Write-Output "$($hostInfo.Label): $($result.Output)"
    }

    for ($cycle = 1; $cycle -le 2; $cycle++) {
        $oldBootIds = @{}
        foreach ($hostInfo in $Hosts) {
            if ($cycle -eq 1) {
                $armCommand = "sudo '$RemoteArm'"
            } else {
                $armCommand = 'set -eu; timeout 330 sudo systemctl stop discrete-crossos-daemon.service; sudo systemctl stop discrete-crossos-monitor.service; ! pgrep -x discreted >/dev/null; sudo /usr/local/sbin/discrete-benchmark-arm-mem512; sudo systemctl start discrete-crossos-daemon.service; sudo systemctl start discrete-crossos-monitor.service; deadline=$((SECONDS + 180)); while (( SECONDS < deadline )); do info=$(curl --silent --show-error --max-time 3 http://127.0.0.1:19331/getinfo 2>/dev/null || true); if [[ -n "$info" ]] && jq -e ''.height > 0 and .outgoing_connections_count > 0'' >/dev/null 2>&1 <<< "$info"; then exit 0; fi; sleep 1; done; exit 1'
            }
            $armResult = Invoke-Remote -Target $hostInfo.Target -Command $armCommand
            Write-Output "===== $($hostInfo.Label) mem512 arm for reboot cycle $cycle ====="
            Write-Output $armResult.Output
            $oldBootIds[$hostInfo.Label] = (Invoke-Remote -Target $hostInfo.Target -Command 'cat /proc/sys/kernel/random/boot_id').Output.Trim()
        }
        foreach ($hostInfo in $Hosts) {
            Invoke-Remote -Target $hostInfo.Target -Command 'sudo systemctl reboot' -AllowFailure | Out-Null
        }
        foreach ($hostInfo in $Hosts) {
            Wait-ForNewBoot -Target $hostInfo.Target -OldBootId $oldBootIds[$hostInfo.Label]
        }
        foreach ($hostInfo in $Hosts) {
            $result = Invoke-Remote -Target $hostInfo.Target -Command "sudo '$RemoteHarness' verify '$($hostInfo.Os)' '$Ordinal' '$cycle'"
            Write-Output "===== $($hostInfo.Label) reboot cycle $cycle ====="
            Write-Output $result.Output
        }
    }
}
finally {
    foreach ($hostInfo in $Hosts) {
        if ($prepared[$hostInfo.Label]) {
            $result = Invoke-Remote -Target $hostInfo.Target -Command "sudo '$RemoteHarness' cleanup '$($hostInfo.Os)' '$Ordinal'" -AllowFailure
            Write-Output "===== $($hostInfo.Label) reboot cleanup (exit $($result.ExitCode)) ====="
            Write-Output $result.Output
        }
        $disarm = Invoke-Remote -Target $hostInfo.Target -Command "if test -e '$RemoteDropIn'; then sudo '$RemoteRollback'; fi" -AllowFailure
        if ($disarm.ExitCode -ne 0) {
            Write-Output "WARNING: $($hostInfo.Label) mem512 drop-in cleanup failed with exit $($disarm.ExitCode)"
            Write-Output $disarm.Output
        }
    }
}
