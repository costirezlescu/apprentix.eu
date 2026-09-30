<#
    Apprentix — pull data out of Word documents.

    A .docx file is a zip containing XML. This reads it directly: no Word,
    no COM automation, no installation.

    -In accepts a single .docx OR a folder of them.

    Typical workflow:

      1. See what is in there
         pwsh -File scripts/docx-extract.ps1 -In data/raw/fiches

      2a. If the data is in TABLES — pull them out as CSV
         pwsh -File scripts/docx-extract.ps1 -In data/raw/fiches -Mode tables -Out data/raw/tables
         pwsh -File scripts/csv-to-json.ps1  -In data/raw/tables/table-1.csv -Out data/published/mine/records.json

      2b. If each document IS a record (heading = field, text beneath = value)
         pwsh -File scripts/docx-extract.ps1 -In data/raw/fiches -Mode qa -Out data/published/mine/records.json

    Modes:
      inspect  (default)  report tables, headings and structure — always start here
      tables              every table to its own CSV
      text                headings and paragraphs to JSON, outline preserved
      qa                  one record per document: heading becomes the field name,
                          the text beneath it becomes the value
#>

param(
  [Parameter(Mandatory)][string]$In,
  [ValidateSet('inspect','tables','text','qa')][string]$Mode = 'inspect',
  [string]$Out,
  [int]$MinRows = 2
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem

if (-not (Test-Path $In)) { Write-Host "Not found: $In" -ForegroundColor Red; exit 1 }

# ---------- which files ----------

$files = if (Test-Path $In -PathType Container) {
  @(Get-ChildItem -Path $In -Filter '*.docx' -File | Where-Object { $_.Name -notlike '~$*' } | Sort-Object Name)
} else {
  @(Get-Item $In)
}
if (-not $files) { Write-Host "No .docx files found in $In" -ForegroundColor Red; exit 1 }

# ---------- read one document ----------

function Read-Docx([string]$path) {
  $zip = [System.IO.Compression.ZipFile]::OpenRead($path)
  try {
    $entry = $zip.Entries | Where-Object { $_.FullName -eq 'word/document.xml' }
    if (-not $entry) { return $null }
    $reader = New-Object System.IO.StreamReader($entry.Open(), [System.Text.Encoding]::UTF8)
    $text = $reader.ReadToEnd(); $reader.Close()
  } finally { $zip.Dispose() }

  $xml = [xml]$text
  $ns = New-Object System.Xml.XmlNamespaceManager($xml.NameTable)
  $ns.AddNamespace('w', 'http://schemas.openxmlformats.org/wordprocessingml/2006/main')
  [pscustomobject]@{
    xml    = $xml
    ns     = $ns
    body   = $xml.SelectSingleNode('//w:body', $ns)
    tables = @($xml.SelectNodes('//w:tbl', $ns))
  }
}

function Get-Text($node, $ns) {
  $sb = New-Object System.Text.StringBuilder
  foreach ($n in $node.SelectNodes('.//w:t | .//w:tab | .//w:br', $ns)) {
    if ($n.LocalName -eq 't') { [void]$sb.Append($n.InnerText) } else { [void]$sb.Append(' ') }
  }
  ($sb.ToString() -replace '\s+', ' ').Trim()
}

function Get-HeadingLevel($p, $ns) {
  $s = $p.SelectSingleNode('.//w:pStyle/@w:val', $ns)
  if (-not $s) { return $null }
  $v = $s.Value
  if ($v -match '^(?:Heading|Titre|berschrift)(\d)$') { return [int]$Matches[1] }
  if ($v -eq 'Title') { return 0 }
  return $null
}

function Read-Table($tbl, $ns) {
  $rows = @()
  foreach ($tr in $tbl.SelectNodes('./w:tr', $ns)) {
    $cells = @()
    foreach ($tc in $tr.SelectNodes('./w:tc', $ns)) { $cells += (Get-Text $tc $ns) }
    if (($cells -join '') -ne '') { $rows += ,$cells }
  }
  ,$rows
}

function Get-Blocks($doc) {
  $out = @()
  foreach ($node in $doc.body.ChildNodes) {
    if ($node.LocalName -eq 'p') {
      $t = Get-Text $node $doc.ns
      if (-not $t) { continue }
      $lvl = Get-HeadingLevel $node $doc.ns
      $out += [pscustomobject]@{ kind = $(if ($null -ne $lvl) { 'heading' } else { 'para' }); level = $lvl; text = $t }
    } elseif ($node.LocalName -eq 'tbl') {
      $out += [pscustomobject]@{ kind = 'table'; level = $null; text = '[table]' }
    }
  }
  $out
}

function New-Key([string]$s) { ($s.ToLower() -replace '[^a-z0-9]+', '_').Trim('_') }

Write-Host "`n$($files.Count) document$(if ($files.Count -ne 1) {'s'})" -ForegroundColor Green

# ---------- inspect ----------

if ($Mode -eq 'inspect') {
  foreach ($f in $files) {
    $doc = Read-Docx $f.FullName
    if (-not $doc) { Write-Host "`n$($f.Name) — not a readable .docx" -ForegroundColor Yellow; continue }

    $paras = @($doc.body.SelectNodes('.//w:p', $doc.ns))
    Write-Host "`n$($f.Name)" -ForegroundColor Cyan
    Write-Host ("  paragraphs {0}   tables {1}" -f $paras.Count, $doc.tables.Count)

    for ($i = 0; $i -lt $doc.tables.Count; $i++) {
      $rows = Read-Table $doc.tables[$i] $doc.ns
      $cols = ($rows | ForEach-Object { $_.Count } | Measure-Object -Maximum).Maximum
      Write-Host ("  table [{0}] {1} rows x {2} cols" -f ($i + 1), $rows.Count, $cols) -ForegroundColor DarkGray
      if ($rows.Count) { Write-Host ("      " + (($rows[0] | Select-Object -First 6) -join ' | ')) -ForegroundColor DarkGray }
    }

    $heads = @(foreach ($p in $paras) {
      $lvl = Get-HeadingLevel $p $doc.ns
      if ($null -ne $lvl) { $t = Get-Text $p $doc.ns; if ($t) { "H$lvl  $t" } }
    })
    if ($heads) {
      Write-Host "  headings ($($heads.Count)):"
      $heads | Select-Object -First 12 | ForEach-Object { Write-Host "      $_" -ForegroundColor DarkGray }
      if ($heads.Count -gt 12) { Write-Host "      … and $($heads.Count - 12) more" -ForegroundColor DarkGray }
    } else {
      Write-Host "  no styled headings (document may use plain bold text)" -ForegroundColor Yellow
    }
  }

  Write-Host "`nNext:" -ForegroundColor Cyan
  Write-Host "  -Mode tables -Out data/raw/tables              tables -> CSV"
  Write-Host "  -Mode qa     -Out data/published/X/records.json  one record per document"
  Write-Host "  -Mode text   -Out data/raw/text.json           full outline`n"
  exit 0
}

if (-not $Out) { Write-Host "This mode needs -Out." -ForegroundColor Red; exit 1 }

# ---------- tables -> CSV ----------

if ($Mode -eq 'tables') {
  if (-not (Test-Path $Out)) { New-Item -ItemType Directory -Force -Path $Out | Out-Null }
  $n = 0
  foreach ($f in $files) {
    $doc = Read-Docx $f.FullName
    if (-not $doc) { continue }
    $stem = if ($files.Count -gt 1) { (New-Key $f.BaseName) + '-' } else { '' }
    $t = 0
    foreach ($tbl in $doc.tables) {
      $rows = Read-Table $tbl $doc.ns
      if ($rows.Count -lt $MinRows) { continue }
      $t++; $n++

      $seen = @{}
      $header = @($rows[0] | ForEach-Object {
        $h = if ($_ -and $_.Trim()) { $_.Trim() } else { 'column' }
        if ($seen.ContainsKey($h)) { $seen[$h]++; "$h $($seen[$h])" } else { $seen[$h] = 1; $h }
      })

      $objs = foreach ($r in $rows[1..($rows.Count - 1)]) {
        $o = [ordered]@{}
        for ($c = 0; $c -lt $header.Count; $c++) { $o[$header[$c]] = if ($c -lt $r.Count) { $r[$c] } else { '' } }
        [pscustomobject]$o
      }

      $path = Join-Path $Out ("{0}table-{1}.csv" -f $stem, $t)
      $objs | Export-Csv -Path $path -NoTypeInformation -Encoding UTF8
      Write-Host ("  {0}  ({1} rows, {2} cols)" -f $path, $objs.Count, $header.Count) -ForegroundColor Green
      Write-Host ("     " + ($header -join ', ')) -ForegroundColor DarkGray
    }
  }
  if ($n -eq 0) { Write-Host "No tables with at least $MinRows rows." -ForegroundColor Yellow }
  Write-Host ""
  exit 0
}

# ---------- text ----------

if ($Mode -eq 'text') {
  $all = foreach ($f in $files) {
    $doc = Read-Docx $f.FullName
    if (-not $doc) { continue }
    [pscustomobject]@{ file = $f.Name; blocks = @(Get-Blocks $doc) }
  }
  $dir = Split-Path -Parent $Out
  if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
  $all | ConvertTo-Json -Depth 6 | Set-Content -Path $Out -Encoding UTF8
  Write-Host "Wrote $($all.Count) document(s) to $Out`n" -ForegroundColor Green
  exit 0
}

# ---------- qa: one record per document ----------

if ($Mode -eq 'qa') {
  $seenIds = @{}
  $records = foreach ($f in $files) {
    $doc = Read-Docx $f.FullName
    if (-not $doc) { Write-Host "  skipped $($f.Name)" -ForegroundColor Yellow; continue }

    $id = New-Key $f.BaseName
    if ($seenIds.ContainsKey($id)) { $seenIds[$id]++; $id = "$id-$($seenIds[$id])" } else { $seenIds[$id] = 1 }

    $rec = [ordered]@{ id = $id; source_file = $f.Name }
    $current = $null; $buffer = @()
    foreach ($b in Get-Blocks $doc) {
      if ($b.kind -eq 'heading') {
        if ($current) { $rec[$current] = ($buffer -join ' ').Trim() }
        $k = New-Key $b.text
        if (-not $k) { $k = "section_$($rec.Count)" }
        if ($rec.Contains($k)) { $k = "${k}_$($rec.Count)" }
        $current = $k; $buffer = @()
      } elseif ($b.kind -eq 'para' -and $current) {
        $buffer += $b.text
      }
    }
    if ($current) { $rec[$current] = ($buffer -join ' ').Trim() }
    Write-Host ("  {0,-45} {1} fields" -f $f.Name, $rec.Count) -ForegroundColor DarkGray
    [pscustomobject]$rec
  }

  $dir = Split-Path -Parent $Out
  if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
  @($records) | ConvertTo-Json -Depth 5 | Set-Content -Path $Out -Encoding UTF8

  Write-Host "`nWrote $(@($records).Count) records to $Out" -ForegroundColor Green

  # union of keys, so you know what meta.json must cover
  $keys = [ordered]@{}
  foreach ($r in $records) { foreach ($k in $r.PSObject.Properties.Name) { $keys[$k] = 1 } }
  Write-Host "`nField keys across all documents ($($keys.Count)):" -ForegroundColor Cyan
  $keys.Keys | ForEach-Object { Write-Host "  { `"key`": `"$_`", `"label`": `"$_`", `"type`": `"text`" }," }
  Write-Host "`nHeadings differ between documents? Any key missing from a record is simply`nleft out of that record — the site handles that.`n"
  exit 0
}
