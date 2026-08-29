$roots = @('F:\Python\ScrapeAll\browser_session', $env:TEMP,
           "$env:USERPROFILE\Downloads", 'J:\es_scrape')
foreach ($r in $roots) {
  if (Test-Path $r) {
    Get-ChildItem -Path $r -Recurse -Filter '*.crdownload' -ErrorAction SilentlyContinue |
      Select-Object FullName, Length, LastWriteTime | Format-List
  }
}
