@echo off
chcp 65001 >nul
echo =====================================================
echo   网页邮箱提取器 — 打包脚本
echo =====================================================
echo.

:: 激活 conda 环境（如果需要）
call conda activate email_extractor 2>nul

:: 安装/更新 PyInstaller
echo [1/3] 检查 PyInstaller...
pip install pyinstaller --quiet
if errorlevel 1 (
    echo 安装 PyInstaller 失败，请检查网络
    pause
    exit /b 1
)

:: 清理旧的构建产物
echo [2/3] 清理旧构建文件...
if exist dist\邮箱提取器 rmdir /s /q "dist\邮箱提取器"
if exist build rmdir /s /q build

:: 执行打包
echo [3/3] 开始打包（约 1-3 分钟）...
pyinstaller email_extractor.spec --noconfirm
if errorlevel 1 (
    echo.
    echo 打包失败！请查看上方错误信息
    pause
    exit /b 1
)

:: 打包完成 — 创建 zip
echo.
echo 打包成功！正在压缩为 zip...
cd dist
powershell -Command "Compress-Archive -Path '邮箱提取器' -DestinationPath '邮箱提取器.zip' -Force"
cd ..

echo.
echo =====================================================
echo   完成！
echo   可执行文件夹: dist\邮箱提取器\
echo   压缩包:       dist\邮箱提取器.zip
echo   使用方式: 解压 zip，双击 "邮箱提取器.exe"
echo =====================================================
pause
