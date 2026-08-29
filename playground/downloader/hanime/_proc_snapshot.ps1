'=== python 进程 ==='
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | ForEach-Object {
  $cmd = $_.CommandLine
  if (-not $cmd) { $cmd = '' }
  if ($cmd.Length -gt 160) { $cmd = $cmd.Substring(0, 160) }
  "pid=$($_.ProcessId) start=$($_.CreationDate) cmd=$cmd"
}
'=== chrome 进程 ==='
$chrome = @(Get-CimInstance Win32_Process -Filter "Name='chrome.exe'")
"chrome 总数: $($chrome.Count)"
$chrome | Select-Object -First 6 | ForEach-Object {
  $cmd = $_.CommandLine
  if (-not $cmd) { $cmd = '' }
  if ($cmd.Length -gt 150) { $cmd = $cmd.Substring(0, 150) }
  "pid=$($_.ProcessId) cmd=$cmd"
}
