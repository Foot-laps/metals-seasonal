$ErrorActionPreference = "Stop"
$dir = $PSScriptRoot
Set-Location $dir
$python = "c:\VS CODE\project\.venv\Scripts\python.exe"

Write-Host "Step 1/4  清洗数据..." -ForegroundColor Cyan
& $python clean_data_策略对日度数据.py

Write-Host "Step 2/4  生成HTML..." -ForegroundColor Cyan
& $python seasonal_all.py

Write-Host "Step 3/4  复制为 index.html..." -ForegroundColor Cyan
Copy-Item "全品种季节性分析.html" "index.html" -Force

Write-Host "Step 4/4  推送到 GitHub..." -ForegroundColor Cyan
git add index.html
$msg = "update $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
git diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
    git commit -m $msg
    git push
    Write-Host "`n发布完成！" -ForegroundColor Green
} else {
    Write-Host "`n内容无变化，跳过提交。" -ForegroundColor Yellow
}
