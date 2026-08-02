param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9]{2}$')]
    [string]$Ordinal,

    [ValidateSet('always', 'madvise', 'never')]
    [string]$ExpectedDebianThpPolicy = 'never',

    [ValidateSet('ubuntu-first', 'debian-first')]
    [string]$StartOrder = 'ubuntu-first',

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
$SshArgs = @(
    '-i', $KeyPath, '-p', "$SshPort", '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes',
    '-o', 'StrictHostKeyChecking=yes', '-o', "UserKnownHostsFile=$KnownHostsPath"
)

function Invoke-Remote {
    param([string]$HostName, [string]$Command, [switch]$AllowFailure)
    $output = & ssh.exe @SshArgs $HostName $Command
    $exitCode = $LASTEXITCODE
    if (-not $AllowFailure -and $exitCode -ne 0) {
        throw "SSH command failed on $HostName with exit code $exitCode"
    }
    return [pscustomobject]@{ Output = ($output -join "`n"); ExitCode = $exitCode }
}

function ConvertFrom-KeyValueText {
    param([string]$Text)
    $values = @{}
    foreach ($line in ($Text -split "`n")) {
        if ($line -match '^([^=]+)=(.*)$') {
            $values[$Matches[1]] = $Matches[2].Trim()
        }
    }
    return $values
}

function Assert-Summary {
    param([string]$HostLabel, [hashtable]$Values)
    foreach ($key in @(
        'wall_to_target_seconds', 'observed_target_height', 'outgoing_at_target',
        'incoming_at_target', 'stop_rc', 'fatal_pattern_matches'
    )) {
        if (-not $Values.ContainsKey($key)) { throw "$HostLabel summary missing $key" }
    }
    if ([int]$Values.observed_target_height -lt 4500) { throw "$HostLabel did not reach target" }
    if ([int]$Values.outgoing_at_target -le 0) { throw "$HostLabel has no outgoing peers" }
    if ([int]$Values.incoming_at_target -ne 0) { throw "$HostLabel has inbound peers" }
    if ([int]$Values.stop_rc -ne 0) { throw "$HostLabel graceful stop failed" }
    if ([int]$Values.fatal_pattern_matches -ne 0) { throw "$HostLabel fatal pattern detected" }
}

$ubuntuRun = "/opt/discrete-benchmark/results/v.0.9.5/cross-os-512m/cold/crossos-512m-cold-$Ordinal-ubuntu24.04"
$debianRun = "/opt/discrete-benchmark/results/v.0.9.5/cross-os-512m/cold/crossos-512m-cold-$Ordinal-debian12"
$unit = "discrete-crossos-cold-controller-$Ordinal"

$ubuntuStart = "set -eu; test ! -e '$ubuntuRun'; sudo systemd-run --unit='$unit' --collect --property=Type=exec /opt/discrete-benchmark/harness/v.0.9.5/cross-os/run-cold-host.sh '$Ordinal' ubuntu24.04"
$debianStart = "set -eu; test ! -e '$debianRun'; sudo systemd-run --unit='$unit' --collect --property=Type=exec /opt/discrete-benchmark/harness/v.0.9.5/cross-os/run-cold-host.sh '$Ordinal' debian12"
if ($StartOrder -eq 'ubuntu-first') {
    Invoke-Remote -HostName $UbuntuHost -Command $ubuntuStart | Out-Null
    Invoke-Remote -HostName $DebianHost -Command $debianStart | Out-Null
} else {
    Invoke-Remote -HostName $DebianHost -Command $debianStart | Out-Null
    Invoke-Remote -HostName $UbuntuHost -Command $ubuntuStart | Out-Null
}
Write-Output "controllers_started ordinal=$Ordinal order=$StartOrder utc=$([DateTimeOffset]::UtcNow.ToString('O'))"

$ubuntuSummary = "$ubuntuRun/run-summary.txt"
$debianSummary = "$debianRun/run-summary.txt"
$completion = [Diagnostics.Stopwatch]::StartNew()
$ubuntuDone = $false
$debianDone = $false
while ($completion.Elapsed.TotalSeconds -lt 720) {
    $ubuntuDone = (Invoke-Remote -HostName $UbuntuHost -Command "test -r '$ubuntuSummary'" -AllowFailure).ExitCode -eq 0
    $debianDone = (Invoke-Remote -HostName $DebianHost -Command "test -r '$debianSummary'" -AllowFailure).ExitCode -eq 0
    if ($ubuntuDone -and $debianDone) { break }
    Start-Sleep -Seconds 2
}
if (-not $ubuntuDone -or -not $debianDone) {
    throw "Pair $Ordinal did not produce both summaries within 720 wall seconds"
}

$ubuntuSummaryText = (Invoke-Remote -HostName $UbuntuHost -Command "cat '$ubuntuSummary'").Output
$debianSummaryText = (Invoke-Remote -HostName $DebianHost -Command "cat '$debianSummary'").Output
$ubuntuValues = ConvertFrom-KeyValueText -Text $ubuntuSummaryText
$debianValues = ConvertFrom-KeyValueText -Text $debianSummaryText
Assert-Summary -HostLabel 'Ubuntu' -Values $ubuntuValues
Assert-Summary -HostLabel 'Debian' -Values $debianValues

$ubuntuThp = (Invoke-Remote -HostName $UbuntuHost -Command "grep -F '/sys/kernel/mm/transparent_hugepage/enabled=' '$ubuntuRun/host-pre-run.txt'").Output
$debianThp = (Invoke-Remote -HostName $DebianHost -Command "grep -F '/sys/kernel/mm/transparent_hugepage/enabled=' '$debianRun/host-pre-run.txt'").Output
if ($ubuntuThp -notmatch '\[never\]') {
    throw "Pair $Ordinal Ubuntu was not recorded with THP=never"
}
$expectedDebianPattern = switch ($ExpectedDebianThpPolicy) {
    'always' { '\[always\]' }
    'madvise' { '\[madvise\]' }
    'never' { '\[never\]' }
}
if ($debianThp -notmatch $expectedDebianPattern) {
    throw "Pair $Ordinal Debian was not recorded with THP=$ExpectedDebianThpPolicy"
}

Write-Output "thp_condition ordinal=$Ordinal ubuntu=never debian=$ExpectedDebianThpPolicy"
Write-Output "===== Ubuntu cold pair $Ordinal ====="
Write-Output $ubuntuSummaryText
Write-Output "===== Debian cold pair $Ordinal ====="
Write-Output $debianSummaryText
