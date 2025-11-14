#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量文件名修改工具 - 测试脚本
用于测试应用程序的基本功能
"""

import os
import tempfile
import shutil
from pathlib import Path


def create_test_files():
    """创建测试文件"""
    test_dir = Path(tempfile.mkdtemp(prefix="rename_test_"))
    
    # 创建测试文件
    test_files = [
        "test1.txt",
        "test2.txt", 
        "image1.jpg",
        "image2.jpg",
        "document1.pdf",
        "document2.pdf",
        "file_with_spaces.txt",
        "FileWithCaps.TXT",
        "123_numbered_file.txt"
    ]
    
    for filename in test_files:
        file_path = test_dir / filename
        file_path.write_text(f"Test content for {filename}")
    
    # 创建子目录和文件
    subdir = test_dir / "subdir"
    subdir.mkdir()
    (subdir / "subfile.txt").write_text("Subdirectory file")
    
    print(f"测试文件已创建在: {test_dir}")
    return test_dir


def test_rename_rules():
    """测试重命名规则"""
    
    # 模拟重命名规则应用
    test_cases = [
        ("前缀添加", "prefix_", "test.txt", "prefix_test.txt"),
        ("后缀添加", "_suffix", "test.txt", "test_suffix.txt"),
        ("字符串替换", "test->demo", "test.txt", "demo.txt"),
        ("正则替换", r"\d+", "number", "file123.txt", "filenumber.txt"),
    ]
    
    print("重命名规则测试:")
    print("-" * 50)
    
    for rule_type, param, original, expected in test_cases:
        result = apply_rename_rule_sim(original, rule_type, param)
        status = "✓" if result == expected else "✗"
        print(f"{status} {rule_type}: '{original}' -> '{result}' (期望: '{expected}')")
    
    print("-" * 50)


def apply_rename_rule_sim(filename, rule_type, param):
    """模拟应用重命名规则"""
    if rule_type == "前缀添加":
        return param + filename
    elif rule_type == "后缀添加":
        name, ext = os.path.splitext(filename)
        return name + param + ext
    elif rule_type == "字符串替换":
        find, replace = param.split("->")
        return filename.replace(find, replace)
    elif rule_type == "正则替换":
        import re
        pattern, replacement = param.split(",")
        return re.sub(pattern, replacement, filename)
    return filename


def test_filename_validation():
    """测试文件名验证"""
    
    test_cases = [
        ("valid_file.txt", True),
        ("file with spaces.txt", True),
        ("FileWithCaps.txt", True),
        ("", False),
        ("con.txt", False),  # Windows保留名称
        ("file<>.txt", False),  # 非法字符
        ("file/".txt", False),  # 非法字符
    ]
    
    print("\n文件名验证测试:")
    print("-" * 50)
    
    for filename, expected in test_cases:
        result = is_filename_valid_sim(filename)
        status = "✓" if result == expected else "✗"
        print(f"{status} '{filename}' -> {'有效' if result else '无效'} (期望: {'有效' if expected else '无效'})")
    
    print("-" * 50)


def is_filename_valid_sim(filename):
    """模拟文件名验证"""
    if not filename or filename.strip() == "":
        return False
    
    # 检查非法字符（Windows）
    invalid_chars = '<>:"/\\|?*'
    if any(char in filename for char in invalid_chars):
        return False
    
    # 检查保留名称
    reserved_names = {
        'CON', 'PRN', 'AUX', 'NUL',
        'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
        'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
    }
    
    name_without_ext = os.path.splitext(filename)[0].upper()
    if name_without_ext in reserved_names:
        return False
    
    return True


def main():
    """主测试函数"""
    print("=" * 60)
    print("批量文件名修改工具 - 功能测试")
    print("=" * 60)
    
    # 创建测试文件
    test_dir = None
    try:
        test_dir = create_test_files()
        
        # 测试重命名规则
        test_rename_rules()
        
        # 测试文件名验证
        test_filename_validation()
        
        print("\n" + "=" * 60)
        print("测试完成！")
        print(f"测试文件目录: {test_dir}")
        print("您可以手动检查测试文件来验证功能。")
        print("=" * 60)
        
        # 询问是否清理测试文件
        response = input("\n是否清理测试文件？(y/n): ").strip().lower()
        if response == 'y':
            if test_dir and test_dir.exists():
                shutil.rmtree(test_dir)
                print("测试文件已清理。")
        else:
            print(f"测试文件保留在: {test_dir}")
            
    except Exception as e:
        print(f"测试过程中出错: {e}")
        if test_dir and test_dir.exists():
            print(f"测试文件保留在: {test_dir}")


if __name__ == "__main__":
    main()