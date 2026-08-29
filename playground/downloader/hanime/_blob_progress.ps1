# read-only: blob storage segment sizes
Get-ChildItem -Path 'F:\Python\ScrapeAll\browser_session\Default\blob_storage' -Recurse -File -ErrorAction SilentlyContinue |
  Sort-Object Name |
  ForEach-Object { '{0,12:N0}B  {1}  {2}' -f $_.Length, $_.LastWriteTime.ToString('HH:mm:ss'), $_.Name }
