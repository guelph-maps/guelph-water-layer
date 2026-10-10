$taskName   = "kk-GuelphWaterLayer"
$projectDir = $PSScriptRoot
$logFile    = "$projectDir\logs\scheduler.log"

if (-not (Test-Path "$projectDir\logs")) {
    New-Item -ItemType Directory -Path "$projectDir\logs" | Out-Null
}

$action = New-ScheduledTaskAction `
    -Execute "cmd.exe" `
    -Argument "/c cd /d `"$projectDir`" && python run.py update >> `"$logFile`" 2>&1"

# Weekly is enough: the City adds about one basin a year, and its service
# carries no edit date to poll anyway. The gap page is what actually moves week
# to week -- it diffs against live OSM. The 16:30 band is full (one sibling
# layer a day, Monday to Sunday), so this opens the second band: Monday 19:30,
# three hours clear of the 16:30 run so the two never drive tippecanoe in the
# same WSL instance at once.
$trigger  = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At "19:30"
# Restart on failure. 'update' exits 75 as soon as it sees no usable link
# instead of blocking on one (the ExecutionTimeLimit would kill a long wait
# anyway), so three tries half an hour apart turn a dead link at 19:30 into a
# run by 21:00 rather than a seven-day gap -- which is what a dead resolver
# cost the Toronto sibling on 2026-07-27. Still clear of the 23:00 quiet window.
#
# It also exits 70 when no Overpass mirror answered and the gap page had to fall
# back to cached OSM. That publishes first, so the retry costs a rebuild and not
# the tiles; without it, two 504s in Aug 2026 left the page a fortnight stale
# with the task reporting success both times.
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 2) -StartWhenAvailable `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 30)

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Force

Write-Host "Scheduled '$taskName' to run weekly on Monday at 19:30."
Write-Host "Log: $logFile"
