@echo off
rem 一键全量回归：双击即跑，任一节点报红立即终止（退出码非 0）
rem 优先用 python / py，都找不到就报错提示
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel%==0 (
    python "跑全量回归.py"
    exit /b %errorlevel%
)

where py >nul 2>nul
if %errorlevel%==0 (
    py "跑全量回归.py"
    exit /b %errorlevel%
)

echo [ERROR] 找不到 python 解释器，请先安装 Python 3 并加入 PATH。
exit /b 2
