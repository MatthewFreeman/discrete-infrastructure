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

function Read-RemoteJson {
    param([string]$HostName, [string]$Path)
    $result = Invoke-Remote -HostName $HostName -Command "if test -r '$Path'; then cat '$Path'; else exit 3; fi" -AllowFailure
    if ($result.ExitCode -ne 0) { return $null }
    try { return $result.Output | ConvertFrom-Json } catch { return $null }
}

function Read-RemoteRpc {
    param([string]$HostName)
    $result = Invoke-Remote -HostName $HostName -Command 'curl --silent --show-error --max-time 3 http://127.0.0.1:19331/getinfo' -AllowFailure
    if ($result.ExitCode -ne 0) { return $null }
    try { return $result.Output | ConvertFrom-Json } catch { return $null }
}

$ubuntuRun = "/opt/discrete-benchmark/results/v.0.9.5/cross-os-512m/warm/crossos-512m-warm-$Ordinal-ubuntu24.04"
$debianRun = "/opt/discrete-benchmark/results/v.0.9.5/cross-os-512m/warm/crossos-512m-warm-$Ordinal-debian12"
$goFile = "/opt/discrete-benchmark/state/v.0.9.5/cross-os/warm-$Ordinal.go"
$unit = "discrete-crossos-warm-controller-$Ordinal"

$ubuntuStart = "set -eu; test ! -e '$ubuntuRun'; test ! -e '$goFile'; sudo systemd-run --unit='$unit' --collect --property=Type=exec /opt/discrete-benchmark/harness/v.0.9.5/cross-os/run-warm-host.sh '$Ordinal' ubuntu24.04"
$debianStart = "set -eu; test ! -e '$debianRun'; test ! -e '$goFile'; sudo systemd-run --unit='$unit' --collect --property=Type=exec /opt/discrete-benchmark/harness/v.0.9.5/cross-os/run-warm-host.sh '$Ordinal' debian12"
if ($StartOrder -eq 'ubuntu-first') {
    Invoke-Remote -HostName $UbuntuHost -Command $ubuntuStart | Out-Null
    Invoke-Remote -HostName $DebianHost -Command $debianStart | Out-Null
} else {
    Invoke-Remote -HostName $DebianHost -Command $debianStart | Out-Null
    Invoke-Remote -HostName $UbuntuHost -Command $ubuntuStart | Out-Null
}
Write-Output "controllers_started ordinal=$Ordinal order=$StartOrder utc=$([DateTimeOffset]::UtcNow.ToString('O'))"

$stopwatch = [Diagnostics.Stopwatch]::StartNew()
$lastKey = ''
$stable = 0
$ubuntuReady = "$ubuntuRun/sync-ready-getinfo.json"
$debianReady = "$debianRun/sync-ready-getinfo.json"
$matchedUbuntu = $null
$matchedDebian = $null
while ($stopwatch.Elapsed.TotalSeconds -lt 480) {
    $ubuntuIsReady = (Invoke-Remote -HostName $UbuntuHost -Command "test -r '$ubuntuReady'" -AllowFailure).ExitCode -eq 0
    $debianIsReady = (Invoke-Remote -HostName $DebianHost -Command "test -r '$debianReady'" -AllowFailure).ExitCode -eq 0
    if ($ubuntuIsReady -and $debianIsReady) {
        $ubuntu = Read-RemoteRpc -HostName $UbuntuHost
        $debian = Read-RemoteRpc -HostName $DebianHost
    } else {
        $ubuntu = $null
        $debian = $null
    }
    if ($null -ne $ubuntu -and $null -ne $debian) {
        $key = "$($ubuntu.height)|$($ubuntu.top_block_hash)"
        $equal = (
            $ubuntu.height -eq $debian.height -and
            $ubuntu.top_block_hash -eq $debian.top_block_hash -and
            $ubuntu.outgoing_connections_count -gt 0 -and
            $debian.outgoing_connections_count -gt 0 -and
            $ubuntu.incoming_connections_count -eq 0 -and
            $debian.incoming_connections_count -eq 0
        )
        if ($equal) {
            if ($key -eq $lastKey) { $stable++ } else { $lastKey = $key; $stable = 1 }
            if ($stable -ge 2) {
                $matchedUbuntu = $ubuntu
                $matchedDebian = $debian
                break
            }
        } else {
            $lastKey = ''
            $stable = 0
        }
    }
    Start-Sleep -Seconds 1
}
if ($null -eq $matchedUbuntu -or $null -eq $matchedDebian) {
    throw "No stable equal live-RPC barrier within 480 wall seconds for pair $Ordinal"
}

$remoteEpoch = Invoke-Remote -HostName $UbuntuHost -Command 'date +%s%N'
$goEpoch = [Int64]$remoteEpoch.Output.Trim() + 5000000000
$writeGo = "printf '%s\n' '$goEpoch' | sudo tee '$goFile' >/dev/null"
Invoke-Remote -HostName $UbuntuHost -Command $writeGo | Out-Null
Invoke-Remote -HostName $DebianHost -Command $writeGo | Out-Null
Write-Output "barrier_opened ordinal=$Ordinal height=$($matchedUbuntu.height) hash=$($matchedUbuntu.top_block_hash) ubuntu_out=$($matchedUbuntu.outgoing_connections_count) debian_out=$($matchedDebian.outgoing_connections_count) epoch_ns=$goEpoch"

$ubuntuSummary = "$ubuntuRun/run-summary.txt"
$debianSummary = "$debianRun/run-summary.txt"
$completion = [Diagnostics.Stopwatch]::StartNew()
while ($completion.Elapsed.TotalSeconds -lt 420) {
    $ubuntuDone = (Invoke-Remote -HostName $UbuntuHost -Command "test -r '$ubuntuSummary'" -AllowFailure).ExitCode -eq 0
    $debianDone = (Invoke-Remote -HostName $DebianHost -Command "test -r '$debianSummary'" -AllowFailure).ExitCode -eq 0
    if ($ubuntuDone -and $debianDone) { break }
    Start-Sleep -Seconds 2
}
if (-not $ubuntuDone -or -not $debianDone) {
    throw "Pair $Ordinal did not produce both summaries within 420 wall seconds"
}

$ubuntuStartInfo = Read-RemoteJson -HostName $UbuntuHost -Path "$ubuntuRun/idle-start-getinfo.json"
$debianStartInfo = Read-RemoteJson -HostName $DebianHost -Path "$debianRun/idle-start-getinfo.json"
if ($null -eq $ubuntuStartInfo -or $null -eq $debianStartInfo) {
    throw "Pair $Ordinal is missing idle-start getinfo"
}
if ($ubuntuStartInfo.height -ne $debianStartInfo.height -or $ubuntuStartInfo.top_block_hash -ne $debianStartInfo.top_block_hash) {
    throw "Pair $Ordinal idle-start height/top hash mismatch"
}

$ubuntuSummaryText = (Invoke-Remote -HostName $UbuntuHost -Command "cat '$ubuntuSummary'").Output
$debianSummaryText = (Invoke-Remote -HostName $DebianHost -Command "cat '$debianSummary'").Output
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
Write-Output "===== Ubuntu pair $Ordinal ====="
Write-Output $ubuntuSummaryText
Write-Output "===== Debian pair $Ordinal ====="
Write-Output $debianSummaryText
