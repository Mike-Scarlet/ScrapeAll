# read-only: sample automation chrome renderer memory/cpu twice, 30s apart
Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" | ForEach-Object {
  $p = Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue
  if ($p) {
    $t = 'browser'
    if ($_.CommandLine -match '--type=renderer') { $t = 'renderer' }
    elseif ($_.CommandLine -match '--type=') { $t = 'other' }
    'pid={0,-7} {1,-9} WS={2,9:N1}MB CPU={3,9:N1}' -f $p.Id, $t, ($p.WorkingSet64 / 1MB), $p.CPU
  }
}
Start-Sleep -Seconds 30
'--- 30s later ---'
Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" | ForEach-Object {
  $p = Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue
  if ($p) {
    $t = 'browser'
    if ($_.CommandLine -match '--type=renderer') { $t = 'renderer' }
    elseif ($_.CommandLine -match '--type=') { $t = 'other' }
    'pid={0,-7} {1,-9} WS={2,9:N1}MB CPU={3,9:N1}' -f $p.Id, $t, ($p.WorkingSet64 / 1MB), $p.CPU
  }
}
