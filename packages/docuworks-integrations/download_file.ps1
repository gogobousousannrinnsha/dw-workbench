param([Parameter(Mandatory=$true)][string]$Uri, [Parameter(Mandatory=$true)][string]$Destination)
$ErrorActionPreference = 'Stop'
Invoke-WebRequest -UseBasicParsing -Uri $Uri -OutFile $Destination
