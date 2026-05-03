param(
  [Parameter(Mandatory=$true)]
  [string]$RootPath,

  [Parameter(Mandatory=$false)]
  [string]$OutCsv = $null,

  [int]$MaxParallel = 4
)

if (-not $OutCsv) {
  $OutCsv = Join-Path -Path $RootPath -ChildPath "file_inventory_with_hash.csv"
}

function Get-FileHashSafe {
  param([string]$Path)
  try {
    $h = Get-FileHash -Path $Path -Algorithm SHA256 -ErrorAction Stop
    return $h.Hash
  } catch {
    return "ERROR:$($_.Exception.Message)"
  }
}

Write-Host "Scanning files under $RootPath ..."
$files = Get-ChildItem -Path $RootPath -Recurse -File -ErrorAction SilentlyContinue

$results = @()
foreach ($f in $files) {
  $sha = Get-FileHashSafe -Path $f.FullName
  $results += [PSCustomObject]@{
    Path = $f.FullName.Substring($RootPath.Length + 1)
    Size = $f.Length
    LastWriteTime = $f.LastWriteTime.ToString("o")
    SHA256 = $sha
  }
}

$results | Sort-Object @{Expression='Size';Descending=$true} | Export-Csv -Path $OutCsv -NoTypeInformation -Encoding UTF8
Write-Host "Inventory written to $OutCsv"
