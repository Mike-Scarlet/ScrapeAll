# read-only: files under the automation profile modified in the last 3 minutes
$cut = (Get-Date).AddMinutes(-3)
Get-ChildItem -Path 'F:\Python\ScrapeAll\browser_session' -Recurse -File -ErrorAction SilentlyContinue |
  Where-Object { $_.LastWriteTime -gt $cut } |
  Sort-Object Length -Descending |
  Select-Object -First 15 |
  ForEach-Object { '{0,12:N0}B  {1}  {2}' -f $_.Length, $_.LastWriteTime.ToString('HH:mm:ss'), $_.FullName }
'--- wait 45s, re-check top candidates ---'
Start-Sleep -Seconds 45
Get-ChildItem -Path 'F:\Python\ScrapeAll\browser_session' -Recurse -File -ErrorAction SilentlyContinue |
  Where-Object { $_.LastWriteTime -gt $cut } |
  Sort-Object Length -Descending |
  Select-Object -First 15 |
  ForEach-Object { '{0,12:N0}B  {1}  {2}' -f $_.Length, $_.LastWriteTime.ToString('HH:mm:ss'), $_.FullName }
