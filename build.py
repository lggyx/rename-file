#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量文件名修改工具 - 打包脚本
使用PyInstaller将应用程序打包成可执行文件
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path


def clean_build_dirs():
    """清理构建目录"""
    build_dirs = ["build", "dist", "__pycache__"]
    
    for dir_name in build_dirs:
        if os.path.exists(dir_name):
            shutil.rmtree(dir_name)
            print(f"已清理目录: {dir_name}")
    
    # 清理spec文件
    spec_files = [f for f in os.listdir('.') if f.endswith('.spec')]
    for spec_file in spec_files:
        os.remove(spec_file)
        print(f"已删除文件: {spec_file}")


def create_installer_script():
    """创建安装脚本"""
    installer_content = """@echo off
chcp 65001 > nul
echo ================================================
echo     批量文件名修改工具 - 安装程序
echo ================================================
echo.

REM 检查是否以管理员权限运行
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo 请以管理员权限运行此安装程序！
    echo 右键点击此文件，选择"以管理员身份运行"
    pause
    exit /b 1
)

REM 创建程序目录
set "PROGRAM_DIR=%ProgramFiles%\\批量文件名修改工具"

if not exist "%PROGRAM_DIR%" (
    mkdir "%PROGRAM_DIR%"
    echo 创建程序目录: %PROGRAM_DIR%
)

REM 复制文件
xcopy /Y /E /I "dist\\*" "%PROGRAM_DIR%"
if %errorLevel% neq 0 (
    echo 文件复制失败！
    pause
    exit /b 1
)

REM 创建桌面快捷方式
set "SHORTCUT_PATH=%USERPROFILE%\\Desktop\\批量文件名修改工具.lnk"

powershell -Command "
$WshShell = New-Object -comObject WScript.Shell;
$Shortcut = $WshShell.CreateShortcut('%SHORTCUT_PATH%');
$Shortcut.TargetPath = '%PROGRAM_DIR%\\main.exe';
$Shortcut.WorkingDirectory = '%PROGRAM_DIR%';
$Shortcut.Save()
"

if %errorLevel% eq 0 (
    echo 创建桌面快捷方式成功！
) else (
    echo 创建桌面快捷方式失败！
)

REM 创建开始菜单快捷方式
set "START_MENU_DIR=%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs"
set "START_MENU_SHORTCUT=%START_MENU_DIR%\\批量文件名修改工具.lnk"

powershell -Command "
$WshShell = New-Object -comObject WScript.Shell;
$Shortcut = $WshShell.CreateShortcut('%START_MENU_SHORTCUT%');
$Shortcut.TargetPath = '%PROGRAM_DIR%\\main.exe';
$Shortcut.WorkingDirectory = '%PROGRAM_DIR%';
$Shortcut.Save()
"

if %errorLevel% eq 0 (
    echo 创建开始菜单快捷方式成功！
) else (
    echo 创建开始菜单快捷方式失败！
)

echo.
echo ================================================
echo     安装完成！
echo ================================================
echo.
echo 程序已安装到: %PROGRAM_DIR%
echo 桌面快捷方式已创建
echo 开始菜单快捷方式已创建
echo.
echo 您现在可以:
echo 1. 双击桌面快捷方式启动程序
echo 2. 在开始菜单中找到程序
echo 3. 直接运行 %PROGRAM_DIR%\\main.exe
echo.
pause
"""
    
    with open("install.bat", "w", encoding="utf-8") as f:
        f.write(installer_content)
    print("已创建安装脚本: install.bat")


def create_portable_script():
    """创建便携版脚本"""
    portable_content = """@echo off
chcp 65001 > nul
title 批量文件名修改工具 - 便携版

REM 检查是否在正确目录
if not exist "main.exe" (
    echo 错误: 未找到 main.exe 文件！
    echo 请确保此批处理文件与 main.exe 在同一目录下。
    pause
    exit /b 1
)

echo ================================================
echo     批量文件名修改工具 - 便携版
echo ================================================
echo.
echo 正在启动程序...
echo.

REM 启动程序
start "" "main.exe"

echo 程序已启动！
echo 您可以关闭此窗口。
pause
"""
    
    with open("启动程序.bat", "w", encoding="utf-8") as f:
        f.write(portable_content)
    print("已创建便携版启动脚本: 启动程序.bat")


def build_with_pyinstaller():
    """使用PyInstaller打包应用程序"""
    
    # PyInstaller命令参数
    pyinstaller_args = [
        "pyinstaller",
        "--name=批量文件名修改工具",
        "--onefile",  # 打包成单个可执行文件
        "--windowed",  # 窗口模式，不显示控制台
        "--icon=NONE",  # 不使用图标
        "--add-data=README.md;.",  # 包含README文件
        "--hidden-import=wx.lib.scrolledpanel",
        "--hidden-import=pathlib",
        "--hidden-import=logging",
        "--clean",  # 清理临时文件
        "--noconfirm",  # 不确认覆盖
        "main.py"
    ]
    
    try:
        print("开始打包应用程序...")
        result = subprocess.run(pyinstaller_args, check=True, capture_output=True, text=True)
        print("打包成功！")
        print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"打包失败: {e}")
        print(f"错误输出: {e.stderr}")
        return False
    except FileNotFoundError:
        print("错误: 未找到PyInstaller，请先安装: pip install pyinstaller")
        return False


def create_distribution_package():
    """创建分发包"""
    
    # 创建分发目录
    dist_dir = Path("distribution")
    if dist_dir.exists():
        shutil.rmtree(dist_dir)
    dist_dir.mkdir()
    
    # 复制可执行文件
    exe_source = Path("dist") / "批量文件名修改工具.exe"
    if exe_source.exists():
        shutil.copy2(exe_source, dist_dir / "main.exe")
        print("已复制可执行文件")
    
    # 复制README
    readme_source = Path("README.md")
    if readme_source.exists():
        shutil.copy2(readme_source, dist_dir / "README.md")
        print("已复制README文件")
    
    # 创建便携版脚本
    create_portable_script()
    shutil.copy2("启动程序.bat", dist_dir / "启动程序.bat")
    
    # 创建安装版脚本
    create_installer_script()
    shutil.copy2("install.bat", dist_dir / "install.bat")
    
    # 创建版本信息文件
    version_info = """批量文件名修改工具
版本: 1.0.0
构建时间: {}
功能:
- 正则表达式匹配文件名
- 支持前缀、后缀、字符串替换、正则替换
- 安全预览机制
- 跨平台支持
""".format(__import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    
    with open(dist_dir / "版本信息.txt", "w", encoding="utf-8") as f:
        f.write(version_info)
    
    print("分发包创建完成！")
    print(f"分发目录: {dist_dir.absolute()}")


def main():
    """主函数"""
    print("=" * 60)
    print("批量文件名修改工具 - 打包程序")
    print("=" * 60)
    
    # 检查当前目录
    if not Path("main.py").exists():
        print("错误: 请在项目根目录运行此脚本！")
        sys.exit(1)
    
    # 清理构建目录
    print("\n1. 清理构建目录...")
    clean_build_dirs()
    
    # 打包应用程序
    print("\n2. 使用PyInstaller打包...")
    if not build_with_pyinstaller():
        print("打包失败，请检查错误信息！")
        sys.exit(1)
    
    # 创建分发包
    print("\n3. 创建分发包...")
    create_distribution_package()
    
    print("\n" + "=" * 60)
    print("打包完成！")
    print("\n生成的文件:")
    print("- distribution/main.exe (主程序)")
    print("- distribution/启动程序.bat (便携版启动脚本)")
    print("- distribution/install.bat (安装程序)")
    print("- distribution/README.md (说明文档)")
    print("- distribution/版本信息.txt (版本信息)")
    print("\n使用方法:")
    print("1. 便携版: 直接运行 distribution/启动程序.bat")
    print("2. 安装版: 以管理员身份运行 distribution/install.bat")
    print("=" * 60)


if __name__ == "__main__":
    main()