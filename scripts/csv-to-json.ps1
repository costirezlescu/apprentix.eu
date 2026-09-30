<#
    Apprentix — turn a CSV into records.json

    Usage:
      pwsh -File scripts/csv-to-json.ps1 -In data/raw/mydata.csv -Out data/published/mine/records.json

    Options:
      -IdColumn   which column holds the unique id (default: first column)
      -Split      comma-separated list of columns holding MULTIPLE values,
                  e.g. -Split "compensation,level"   (values separated by ";" or "|")
      -Delimiter  CSV delimiter (default ",")

    For Excel: open the sheet and Save As > CSV UTF-8, then run this on the .csv.
#>

param(
  [Parameter(Mandatory)][string]$In,
  [Parameter(Mandatory)][string]$Out,
  [string]$IdColumn,
  [string]$Split = '',
  [string]$Delimiter = ','
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path $In)) { Write-Host "Input not found: $In" -ForegroundColor Red; exit 1 }

$rows = Import-Csv -Path $In -Delimiter $Delimiter -Encoding UTF8
if (-not $rows) { Write-Host "No rows found in $In" -ForegroundColor Red; exit 1 }

$columns = $rows[0].PSObject.Properties.Name
Write-Host "`nColumns found ($($columns.Count)):" -ForegroundColor Cyan
$columns | ForEach-Object { Write-Host "  $_" }

if (-not $IdColumn) { $IdColumn = $columns[0] }
if ($IdColumn -notin $columns) {
  Write-Host "`nId column '$IdColumn' is not one of the columns." -ForegroundColor Red; exit 1
}
Write-Host "`nUsing '$IdColumn' as the record id." -ForegroundColor Cyan

$multi = @($Split -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })
if ($multi) { Write-Host "Treating as multi-value: $($multi -join ', ')" -ForegroundColor Cyan }

$seen = @{}
$records = foreach ($row in $rows) {
  $o = [ordered]@{}
  $rawId = "$($row.$IdColumn)".Trim()
  if (-not $rawId) { continue }

  # slug the id, and make sure it is unique
  $id = ($rawId.ToLower() -replace '[^a-z0-9]+', '-').Trim('-')
  if ($seen.ContainsKey($id)) { $seen[$id]++; $id = "$id-$($seen[$id])" } else { $seen[$id] = 1 }
  $o['id'] = $id

  foreach ($c in $columns) {
    $v = "$($row.$c)".Trim()
    if ($v -eq '') { continue }
    $key = ($c.ToLower() -replace '[^a-z0-9]+', '_').Trim('_')
    if ($key -eq 'id') { continue }
    $o[$key] = if ($c -in $multi) {
      @($v -split '[;|]' | ForEach-Object { $_.Trim() } | Where-Object { $_ })
    } else { $v }
  }
  [pscustomobject]$o
}

$dir = Split-Path -Parent $Out
if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }

$records | ConvertTo-Json -Depth 6 | Set-Content -Path $Out -Encoding UTF8

Write-Host "`nWrote $($records.Count) records to $Out" -ForegroundColor Green
Write-Host "`nField keys for your meta.json:" -ForegroundColor Cyan
$records[0].PSObject.Properties.Name | ForEach-Object { Write-Host "  { `"key`": `"$_`", `"label`": `"$_`", `"type`": `"text`" }," }
Write-Host "`nNow write meta.json in the same folder, then add the dataset to data/datasets.json.`n"
