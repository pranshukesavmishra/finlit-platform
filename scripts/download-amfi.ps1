# Downloads the AMFI half-yearly "Average Market Capitalization" lists (the NSE data folder's amfi/ part) on a PC in India, because AMFI does not answer the AWS server.
# Run in PowerShell:   powershell -ExecutionPolicy Bypass -File scripts\download-amfi.ps1     It writes .\amfi\<period>.xlsx and prints one line per file.
# Generated from finlit_technicals/fetch.py (AMFI list + the portal's naming pattern for newer half-years); re-generate when a new half-year is published.
$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"
New-Item -ItemType Directory -Force -Path .\amfi | Out-Null
$ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
$ref = "https://www.amfiindia.com/otherdata/categorisation-of-stocks"
$files = [ordered]@{
  "2017H2" = @("https://www.amfiindia.com/Themes/Theme1/downloads/Avg.%20Market%20Capitalization%20of%20listed%20companies%20during%20-Jul-Dec%202017.xlsx")
  "2018H1" = @("https://www.amfiindia.com/Themes/Theme1/downloads/Avg.%20Market%20Capitalization%20of%20listed%20companies%20during%20-Jan-June%202018.xlsx")
  "2018H2" = @("https://www.amfiindia.com/Themes/Theme1/downloads/Avg.%20Market%20Capitalization%20of%20listed%20companies%20during%20Jul-Dec%202018.xlsx")
  "2019H1" = @("https://www.amfiindia.com/Themes/Theme1/downloads/Avg.%20Market%20Capitalization%20of%20listed%20companies%20during%20-Jan-June%202019.xlsx")
  "2019H2" = @("https://www.amfiindia.com/Themes/Theme1/downloads/Avg.%20Market%20Capitalization%20of%20listed%20companies%20during%20Jul-Dec%202019.xlsx")
  "2020H1" = @("https://www.amfiindia.com/Themes/Theme1/downloads/Average%20Market%20Capitalization%20of%20Listed%20Companies%20during%20Jan%20-%20Jun%202020_Final.xlsx")
  "2020H2" = @("https://www.amfiindia.com/Themes/Theme1/downloads/Average%20Market%20Capitalization%20of%20Listed%20Companies%20during%20Jul%20-%20Dec%202020_Final.xlsx")
  "2021H1" = @("https://www.amfiindia.com/Themes/Theme1/downloads/Average%20Market%20Capitalization%20of%20List%20Companies%20during%20Jan-June%202021.xlsx")
  "2021H2" = @("https://www.amfiindia.com/Themes/Theme1/downloads/Average%20Market%20Capitalisation%20of%20Listed%20Companies%20during%20Jul%20-%20Dec%202021.xlsx")
  "2022H1" = @("https://www.amfiindia.com/Themes/Theme1/downloads/AverageMarketCapitalizationoflistedcompaniesduringthesixmonthsended30June2022.xlsx")
  "2022H2" = @("https://www.amfiindia.com/Themes/Theme1/downloads/AverageMarketCapitalizationoflistedcompaniesduringthesixmonthsended31Dec2022.xlsx")
  "2023H1" = @("https://www.amfiindia.com/Themes/Theme1/downloads/AverageMarketCapitalizationoflistedcompaniesduringthesixmonthsended30Jun2023.xlsx")
  "2023H2" = @("https://www.amfiindia.com/Themes/Theme1/downloads/AverageMarketCapitalizationoflistedcompaniesduringthesixmonthsended31Dec2023.xlsx")
  "2024H1" = @("https://www.amfiindia.com/uploads/Average_Market_Capitalization_30_Jun2024_2a1ab4c1d8.xlsx")
  "2024H2" = @("https://www.amfiindia.com/Themes/Theme1/downloads/AverageMarketCapitalizationoflistedcompaniesduringthesixmonthsended31Dec2024.xlsx")
  "2025H1" = @("https://www.amfiindia.com/Themes/Theme1/downloads/AverageMarketCapitalization30Jun2025.xlsx")
  "2025H2" = @("https://www.amfiindia.com/Themes/Theme1/downloads/AverageMarketCapitalization31Dec2025.xlsx")
  "2026H1" = @("https://portal.amfiindia.com/spages/AverageMarketCapitalization30Jun2026.xlsx")
}
$ok = 0; $bad = @()
foreach ($p in $files.Keys) {
  $dest = ".\amfi\$p.xlsx"
  if ((Test-Path $dest) -and ((Get-Item $dest).Length -gt 10000)) { Write-Host "$p already here"; $ok++; continue }
  $got = $false
  foreach ($u in $files[$p]) {
    try {
      Invoke-WebRequest -Uri $u -OutFile $dest -UserAgent $ua -Headers @{ Referer = $ref } -TimeoutSec 60
      $b = [System.IO.File]::ReadAllBytes($dest)
      if ($b.Length -gt 10000 -and $b[0] -eq 0x50 -and $b[1] -eq 0x4B) { Write-Host "$p saved ($([int]($b.Length/1024)) KB)"; $got = $true; break }
      Remove-Item $dest -ErrorAction SilentlyContinue
    } catch { Remove-Item $dest -ErrorAction SilentlyContinue }
  }
  if ($got) { $ok++ } else { $bad += $p; Write-Host "$p NOT downloaded" }
}
Write-Host ""
Write-Host "$ok of $($files.Count) files are in .\amfi"
if ($bad.Count) { Write-Host "Missing: $($bad -join ', '). Send this list to Claude." }
