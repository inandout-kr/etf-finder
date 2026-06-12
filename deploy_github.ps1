# dist/ 를 gh-pages 브랜치에 단일 커밋으로 강제 푸시 (히스토리 누적 방지)
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "dist")

if (Test-Path .git) { Remove-Item -Recurse -Force .git -Confirm:$false }
git init -b gh-pages -q
git add -A
git commit -q -m "deploy $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
git push -f -q https://github.com/inandout-kr/etf-finder.git gh-pages
Remove-Item -Recurse -Force .git -Confirm:$false

Write-Host "gh-pages 배포 완료: https://inandout-kr.github.io/etf-finder/"
