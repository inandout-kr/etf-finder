# ETF 파인더 일일 갱신: 수집 -> 빌드 -> Cloudflare Pages 배포
# 사용: .\update.ps1  (또는 작업 스케줄러에 등록)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "[1/3] 데이터 수집..."
python collector.py
if ($LASTEXITCODE -ne 0) { Write-Host "수집 실패 - 중단"; exit 1 }

Write-Host "[2/3] 정적 빌드..."
python build_static.py
if ($LASTEXITCODE -ne 0) { Write-Host "빌드 실패 - 중단"; exit 1 }

Write-Host "[3/3] GitHub Pages 배포..."
& (Join-Path $PSScriptRoot "deploy_github.ps1")
if ($LASTEXITCODE -ne 0) { Write-Host "배포 실패"; exit 1 }

# Cloudflare Pages로 전환 시 위 두 줄 대신:
# npx wrangler pages deploy dist --project-name etf-finder --commit-dirty=true

Write-Host "완료: $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
