#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量文件名修改工具
支持正则表达式匹配和多种修改规则
"""

import wx
import wx.lib.scrolledpanel as scrolled
import os
import re
import sys
from pathlib import Path
from typing import List, Tuple, Optional
import logging
from datetime import datetime


class FileRenamerApp(wx.Frame):
    """批量文件名修改工具主窗口"""
    
    def __init__(self):
        super().__init__(None, title="批量文件名修改工具", size=(800, 600))
        
        # 设置日志
        self.setup_logging()
        
        # 初始化变量
        self.selected_files = []
        self.preview_data = []
        
        # 创建界面
        self.create_ui()
        
        # 绑定事件
        self.bind_events()
        
        # 居中显示
        self.Centre()
        
        self.logger.info("应用程序启动成功")
    
    def setup_logging(self):
        """设置日志系统"""
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        log_file = log_dir / f"rename_tool_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def create_ui(self):
        """创建用户界面"""
        panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # 文件选择区域
        file_section = self.create_file_section(panel)
        main_sizer.Add(file_section, 0, wx.EXPAND | wx.ALL, 10)
        
        # 修改规则区域
        rule_section = self.create_rule_section(panel)
        main_sizer.Add(rule_section, 0, wx.EXPAND | wx.ALL, 10)
        
        # 预览区域
        preview_section = self.create_preview_section(panel)
        main_sizer.Add(preview_section, 1, wx.EXPAND | wx.ALL, 10)
        
        # 操作按钮区域
        button_section = self.create_button_section(panel)
        main_sizer.Add(button_section, 0, wx.EXPAND | wx.ALL, 10)
        
        panel.SetSizer(main_sizer)
    
    def create_file_section(self, parent):
        """创建文件选择区域"""
        box = wx.StaticBox(parent, label="文件选择")
        sizer = wx.StaticBoxSizer(box, wx.VERTICAL)
        
        # 目录选择
        dir_sizer = wx.BoxSizer(wx.HORIZONTAL)
        dir_sizer.Add(wx.StaticText(parent, label="目标目录:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        
        self.dir_picker = wx.DirPickerCtrl(parent, path=os.getcwd(), 
                                          message="选择要处理的目录")
        dir_sizer.Add(self.dir_picker, 1, wx.EXPAND)
        
        self.recursive_cb = wx.CheckBox(parent, label="递归搜索子目录")
        dir_sizer.Add(self.recursive_cb, 0, wx.LEFT, 10)
        
        sizer.Add(dir_sizer, 0, wx.EXPAND | wx.ALL, 5)
        
        # 文件过滤
        filter_sizer = wx.BoxSizer(wx.HORIZONTAL)
        filter_sizer.Add(wx.StaticText(parent, label="文件过滤:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        
        self.filter_pattern = wx.TextCtrl(parent, value="*", 
                                         style=wx.TE_PROCESS_ENTER)
        filter_sizer.Add(self.filter_pattern, 1, wx.EXPAND)
        
        filter_sizer.Add(wx.StaticText(parent, label="正则模式:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT | wx.RIGHT, 5)
        
        self.regex_pattern = wx.TextCtrl(parent, value=".*", 
                                        style=wx.TE_PROCESS_ENTER)
        filter_sizer.Add(self.regex_pattern, 1, wx.EXPAND)
        
        sizer.Add(filter_sizer, 0, wx.EXPAND | wx.ALL, 5)
        
        # 文件列表
        file_list_sizer = wx.BoxSizer(wx.HORIZONTAL)
        file_list_sizer.Add(wx.StaticText(parent, label="匹配文件:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        
        self.file_count_label = wx.StaticText(parent, label="0 个文件")
        file_list_sizer.Add(self.file_count_label, 1, wx.EXPAND)
        
        self.scan_btn = wx.Button(parent, label="扫描文件")
        file_list_sizer.Add(self.scan_btn, 0, wx.LEFT, 10)
        
        sizer.Add(file_list_sizer, 0, wx.EXPAND | wx.ALL, 5)
        
        return sizer
    
    def create_rule_section(self, parent):
        """创建修改规则区域"""
        box = wx.StaticBox(parent, label="修改规则")
        sizer = wx.StaticBoxSizer(box, wx.VERTICAL)
        
        # 规则类型选择
        rule_type_sizer = wx.BoxSizer(wx.HORIZONTAL)
        rule_type_sizer.Add(wx.StaticText(parent, label="规则类型:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        
        self.rule_types = ["前缀添加", "后缀添加", "字符串替换", "正则替换"]
        self.rule_choice = wx.Choice(parent, choices=self.rule_types)
        self.rule_choice.SetSelection(0)
        rule_type_sizer.Add(self.rule_choice, 1, wx.EXPAND)
        
        sizer.Add(rule_type_sizer, 0, wx.EXPAND | wx.ALL, 5)
        
        # 规则参数容器面板
        self.rule_params_container = wx.Panel(parent)
        self.container_sizer = wx.BoxSizer(wx.VERTICAL)
        self.rule_params_container.SetSizer(self.container_sizer)
        
        # 创建独立的参数面板，每个规则类型一个面板
        self.rule_params_panels = {}
        
        # 前缀添加参数面板
        prefix_panel = wx.Panel(self.rule_params_container)
        prefix_sizer = wx.BoxSizer(wx.HORIZONTAL)
        prefix_sizer.Add(wx.StaticText(prefix_panel, label="前缀内容:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.prefix_text = wx.TextCtrl(prefix_panel, size=(200, -1))
        prefix_sizer.Add(self.prefix_text, 1, wx.EXPAND)
        prefix_panel.SetSizer(prefix_sizer)
        self.rule_params_panels["前缀添加"] = prefix_panel
        
        # 后缀添加参数面板
        suffix_panel = wx.Panel(self.rule_params_container)
        suffix_sizer = wx.BoxSizer(wx.HORIZONTAL)
        suffix_sizer.Add(wx.StaticText(suffix_panel, label="后缀内容:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.suffix_text = wx.TextCtrl(suffix_panel, size=(200, -1))
        suffix_sizer.Add(self.suffix_text, 1, wx.EXPAND)
        suffix_panel.SetSizer(suffix_sizer)
        self.rule_params_panels["后缀添加"] = suffix_panel
        
        # 字符串替换参数面板
        string_replace_panel = wx.Panel(self.rule_params_container)
        string_sizer = wx.BoxSizer(wx.HORIZONTAL)
        string_sizer.Add(wx.StaticText(string_replace_panel, label="查找内容:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.find_text = wx.TextCtrl(string_replace_panel, size=(150, -1))
        string_sizer.Add(self.find_text, 1, wx.EXPAND)
        string_sizer.Add(wx.StaticText(string_replace_panel, label="替换为:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT | wx.RIGHT, 5)
        self.replace_text = wx.TextCtrl(string_replace_panel, size=(150, -1))
        string_sizer.Add(self.replace_text, 1, wx.EXPAND)
        string_replace_panel.SetSizer(string_sizer)
        self.rule_params_panels["字符串替换"] = string_replace_panel
        
        # 正则替换参数面板
        regex_replace_panel = wx.Panel(self.rule_params_container)
        regex_sizer = wx.BoxSizer(wx.HORIZONTAL)
        regex_sizer.Add(wx.StaticText(regex_replace_panel, label="正则模式:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.regex_find = wx.TextCtrl(regex_replace_panel, size=(150, -1))
        regex_sizer.Add(self.regex_find, 1, wx.EXPAND)
        regex_sizer.Add(wx.StaticText(regex_replace_panel, label="替换为:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT | wx.RIGHT, 5)
        self.regex_replace = wx.TextCtrl(regex_replace_panel, size=(150, -1))
        regex_sizer.Add(self.regex_replace, 1, wx.EXPAND)
        regex_replace_panel.SetSizer(regex_sizer)
        self.rule_params_panels["正则替换"] = regex_replace_panel
        
        # 将所有面板添加到sizer中
        for panel in self.rule_params_panels.values():
            self.container_sizer.Add(panel, 0, wx.EXPAND)
        
        # 默认显示前缀添加面板，隐藏其他面板
        self.current_rule_panel = prefix_panel
        for rule_type, panel in self.rule_params_panels.items():
            if rule_type != "前缀添加":
                panel.Hide()
        
        sizer.Add(self.rule_params_container, 0, wx.EXPAND | wx.ALL, 5)
        
        # 大小写敏感选项（仅对字符串替换和正则替换有效）
        self.case_sensitive_cb = wx.CheckBox(parent, label="大小写敏感")
        sizer.Add(self.case_sensitive_cb, 0, wx.ALL, 5)
        
        # 预览按钮
        preview_sizer = wx.BoxSizer(wx.HORIZONTAL)
        preview_sizer.AddStretchSpacer(1)
        self.preview_btn = wx.Button(parent, label="预览修改")
        preview_sizer.Add(self.preview_btn, 0)
        sizer.Add(preview_sizer, 0, wx.EXPAND | wx.ALL, 5)
        
        return sizer
    
    def create_preview_section(self, parent):
        """创建预览区域"""
        box = wx.StaticBox(parent, label="预览")
        sizer = wx.StaticBoxSizer(box, wx.VERTICAL)
        
        # 预览列表
        self.preview_list = wx.ListCtrl(parent, style=wx.LC_REPORT | wx.BORDER_SUNKEN)
        self.preview_list.InsertColumn(0, "原文件名", width=300)
        self.preview_list.InsertColumn(1, "新文件名", width=300)
        self.preview_list.InsertColumn(2, "状态", width=100)
        
        sizer.Add(self.preview_list, 1, wx.EXPAND | wx.ALL, 5)
        
        return sizer
    
    def create_button_section(self, parent):
        """创建操作按钮区域"""
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        self.execute_btn = wx.Button(parent, label="执行修改")
        self.execute_btn.Disable()
        sizer.Add(self.execute_btn, 0, wx.RIGHT, 10)
        
        self.export_btn = wx.Button(parent, label="导出列表")
        self.export_btn.Disable()
        sizer.Add(self.export_btn, 0, wx.RIGHT, 10)
        
        self.clear_btn = wx.Button(parent, label="清空预览")
        sizer.Add(self.clear_btn, 0, wx.RIGHT, 10)
        
        self.help_btn = wx.Button(parent, label="帮助")
        sizer.Add(self.help_btn, 0)
        
        return sizer
    
    def bind_events(self):
        """绑定事件处理"""
        # 文件选择事件
        self.dir_picker.Bind(wx.EVT_DIRPICKER_CHANGED, self.on_directory_changed)
        self.scan_btn.Bind(wx.EVT_BUTTON, self.on_scan_files)
        self.filter_pattern.Bind(wx.EVT_TEXT_ENTER, self.on_scan_files)
        self.regex_pattern.Bind(wx.EVT_TEXT_ENTER, self.on_scan_files)
        
        # 规则事件
        self.rule_choice.Bind(wx.EVT_CHOICE, self.on_rule_type_changed)
        self.preview_btn.Bind(wx.EVT_BUTTON, self.on_preview)
        
        # 按钮事件
        self.execute_btn.Bind(wx.EVT_BUTTON, self.on_execute)
        self.export_btn.Bind(wx.EVT_BUTTON, self.on_export)
        self.clear_btn.Bind(wx.EVT_BUTTON, self.on_clear)
        self.help_btn.Bind(wx.EVT_BUTTON, self.on_help)
    
    def on_directory_changed(self, event):
        """目录改变事件"""
        self.logger.info(f"目录更改为: {self.dir_picker.GetPath()}")
    
    def on_scan_files(self, event):
        """扫描文件"""
        try:
            directory = self.dir_picker.GetPath()
            if not directory or not os.path.exists(directory):
                wx.MessageBox("请选择有效的目录", "错误", wx.OK | wx.ICON_ERROR)
                return
            
            pattern = self.filter_pattern.GetValue().strip()
            regex_pattern = self.regex_pattern.GetValue().strip()
            recursive = self.recursive_cb.GetValue()
            
            self.selected_files = self.find_files(directory, pattern, regex_pattern, recursive)
            self.file_count_label.SetLabel(f"{len(self.selected_files)} 个文件")
            
            if self.selected_files:
                self.logger.info(f"找到 {len(self.selected_files)} 个匹配文件")
                wx.MessageBox(f"找到 {len(self.selected_files)} 个匹配文件", "扫描完成", wx.OK | wx.ICON_INFORMATION)
            else:
                wx.MessageBox("没有找到匹配的文件", "提示", wx.OK | wx.ICON_WARNING)
                
        except Exception as e:
            self.logger.error(f"扫描文件时出错: {str(e)}")
            wx.MessageBox(f"扫描文件时出错: {str(e)}", "错误", wx.OK | wx.ICON_ERROR)
    
    def find_files(self, directory: str, pattern: str, regex_pattern: str, recursive: bool) -> List[Path]:
        """查找匹配的文件"""
        files = []
        dir_path = Path(directory)
        
        # 构建搜索模式
        search_pattern = pattern if pattern != "*" else "*"
        
        # 搜索文件
        if recursive:
            search_path = dir_path.rglob(search_pattern)
        else:
            search_path = dir_path.glob(search_pattern)
        
        # 过滤文件（只保留文件，排除目录）
        for path in search_path:
            if path.is_file():
                # 正则表达式过滤
                if regex_pattern and regex_pattern != ".*":
                    try:
                        if re.match(regex_pattern, path.name):
                            files.append(path)
                    except re.error:
                        # 正则表达式错误，跳过这个过滤条件
                        files.append(path)
                else:
                    files.append(path)
        
        return files
    
    def on_rule_type_changed(self, event):
        """规则类型改变事件"""
        rule_type = self.rule_choice.GetStringSelection()
        
        # 隐藏所有面板
        for panel in self.rule_params_panels.values():
            panel.Hide()
        
        # 显示选中的面板
        new_panel = self.rule_params_panels.get(rule_type)
        if new_panel:
            new_panel.Show()
            self.current_rule_panel = new_panel
            
            # 强制刷新布局
            self.rule_params_container.Layout()
            self.rule_params_container.GetParent().Layout()
            
            # 根据规则类型显示/隐藏大小写敏感选项
            if rule_type in ["字符串替换", "正则替换"]:
                self.case_sensitive_cb.Show()
            else:
                self.case_sensitive_cb.Hide()
        
        self.logger.info(f"规则类型更改为: {rule_type}")
    
    def on_preview(self, event):
        """预览修改"""
        if not self.selected_files:
            wx.MessageBox("请先扫描文件", "提示", wx.OK | wx.ICON_WARNING)
            return
        
        try:
            rule_type = self.rule_choice.GetStringSelection()
            case_sensitive = self.case_sensitive_cb.GetValue()
            
            self.preview_data = []
            self.preview_list.DeleteAllItems()
            
            for file_path in self.selected_files:
                old_name = file_path.name
                new_name = self.apply_rename_rule(old_name, rule_type, case_sensitive)
                
                # 检查新文件名是否有效
                status = "有效"
                if not new_name or new_name == old_name:
                    status = "无变化"
                elif self.is_filename_valid(new_name):
                    # 检查是否会产生冲突
                    new_path = file_path.parent / new_name
                    if new_path.exists() and new_path != file_path:
                        status = "冲突"
                else:
                    status = "无效"
                
                self.preview_data.append((file_path, new_name, status))
                
                # 添加到列表
                index = self.preview_list.InsertItem(self.preview_list.GetItemCount(), old_name)
                self.preview_list.SetItem(index, 1, new_name)
                self.preview_list.SetItem(index, 2, status)
            
            # 启用执行按钮
            valid_changes = any(status == "有效" for _, _, status in self.preview_data)
            self.execute_btn.Enable(valid_changes)
            self.export_btn.Enable(len(self.preview_data) > 0)
            
            self.logger.info(f"预览完成，共 {len(self.preview_data)} 个文件")
            
        except Exception as e:
            self.logger.error(f"预览时出错: {str(e)}")
            wx.MessageBox(f"预览时出错: {str(e)}", "错误", wx.OK | wx.ICON_ERROR)
    
    def apply_rename_rule(self, filename: str, rule_type: str, case_sensitive: bool) -> str:
        """应用重命名规则"""
        if rule_type == "前缀添加":
            prefix = self.prefix_text.GetValue()
            return prefix + filename
        
        elif rule_type == "后缀添加":
            suffix = self.suffix_text.GetValue()
            name, ext = os.path.splitext(filename)
            return name + suffix + ext
        
        elif rule_type == "字符串替换":
            find_text = self.find_text.GetValue()
            replace_text = self.replace_text.GetValue()
            
            if not find_text:
                return filename
            
            if case_sensitive:
                return filename.replace(find_text, replace_text)
            else:
                # 不区分大小写替换
                pattern = re.compile(re.escape(find_text), re.IGNORECASE)
                return pattern.sub(replace_text, filename)
        
        elif rule_type == "正则替换":
            regex_find = self.regex_find.GetValue()
            regex_replace = self.regex_replace.GetValue()
            
            if not regex_find:
                return filename
            
            try:
                flags = 0 if case_sensitive else re.IGNORECASE
                pattern = re.compile(regex_find, flags)
                return pattern.sub(regex_replace, filename)
            except re.error:
                # 正则表达式错误，返回原文件名
                return filename
        
        return filename
    
    def is_filename_valid(self, filename: str) -> bool:
        """检查文件名是否有效"""
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
    
    def on_execute(self, event):
        """执行修改"""
        if not self.preview_data:
            wx.MessageBox("请先预览修改", "提示", wx.OK | wx.ICON_WARNING)
            return
        
        # 确认对话框
        confirm_msg = f"确定要重命名 {len(self.preview_data)} 个文件吗？\n\n此操作不可撤销！"
        dialog = wx.MessageDialog(self, confirm_msg, "确认操作", 
                                wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING)
        
        if dialog.ShowModal() != wx.ID_YES:
            return
        
        try:
            success_count = 0
            error_count = 0
            
            for file_path, new_name, status in self.preview_data:
                if status == "有效":
                    try:
                        new_path = file_path.parent / new_name
                        file_path.rename(new_path)
                        success_count += 1
                        self.logger.info(f"重命名成功: {file_path.name} -> {new_name}")
                    except Exception as e:
                        error_count += 1
                        self.logger.error(f"重命名失败 {file_path.name}: {str(e)}")
            
            # 显示结果
            result_msg = f"操作完成！\n成功: {success_count} 个文件\n失败: {error_count} 个文件"
            wx.MessageBox(result_msg, "操作完成", wx.OK | wx.ICON_INFORMATION)
            
            # 清空预览
            self.on_clear(None)
            
        except Exception as e:
            self.logger.error(f"执行修改时出错: {str(e)}")
            wx.MessageBox(f"执行修改时出错: {str(e)}", "错误", wx.OK | wx.ICON_ERROR)
    
    def on_export(self, event):
        """导出列表"""
        if not self.preview_data:
            wx.MessageBox("没有可导出的数据", "提示", wx.OK | wx.ICON_WARNING)
            return
        
        try:
            with wx.FileDialog(self, "导出列表", wildcard="文本文件 (*.txt)|*.txt", 
                             style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as dialog:
                
                if dialog.ShowModal() == wx.ID_OK:
                    file_path = dialog.GetPath()
                    
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write("批量文件名修改工具 - 导出列表\n")
                        f.write(f"导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                        f.write("=" * 50 + "\n\n")
                        
                        for file_path, new_name, status in self.preview_data:
                            f.write(f"原文件名: {file_path.name}\n")
                            f.write(f"新文件名: {new_name}\n")
                            f.write(f"状态: {status}\n")
                            f.write("-" * 30 + "\n")
                    
                    wx.MessageBox(f"列表已导出到: {file_path}", "导出成功", wx.OK | wx.ICON_INFORMATION)
                    self.logger.info(f"列表导出到: {file_path}")
                    
        except Exception as e:
            self.logger.error(f"导出列表时出错: {str(e)}")
            wx.MessageBox(f"导出列表时出错: {str(e)}", "错误", wx.OK | wx.ICON_ERROR)
    
    def on_clear(self, event):
        """清空预览"""
        self.preview_list.DeleteAllItems()
        self.preview_data.clear()
        self.execute_btn.Disable()
        self.export_btn.Disable()
        self.logger.info("预览已清空")
    
    def on_help(self, event):
        """显示帮助信息"""
        help_text = """批量文件名修改工具 - 使用说明

功能特性：
• 正则表达式匹配文件名
• 支持前缀、后缀、字符串替换、正则替换
• 安全预览机制，避免误操作
• 跨平台支持，自动处理路径格式
• 详细日志记录

使用步骤：
1. 选择目标目录
2. 设置文件过滤条件
3. 点击"扫描文件"查找匹配文件
4. 选择修改规则并设置参数
5. 点击"预览修改"查看效果
6. 确认无误后点击"执行修改"

注意事项：
• 操作前请务必备份重要文件
• 预览时请仔细检查"状态"列
• "冲突"状态表示新文件名已存在
• "无效"状态表示新文件名不合法
"""
        
        wx.MessageBox(help_text, "帮助", wx.OK | wx.ICON_INFORMATION)


def main():
    """主函数"""
    app = wx.App(False)
    frame = FileRenamerApp()
    frame.Show()
    app.MainLoop()


if __name__ == "__main__":
    main()
