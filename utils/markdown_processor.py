"""
Markdown 格式处理工具
支持各种 Markdown 格式的解析、清理和转换
"""

import re
from typing import Optional, Dict, List
from markdown import Markdown
from markdown.extensions import (
    fenced_code, tables, toc, codehilite, 
    nl2br, extra, sane_lists
)
from markdown.extensions.codehilite import CodeHiliteExtension
import html


class MarkdownProcessor:
    """Markdown 处理器，支持各种格式"""
    
    def __init__(self):
        """初始化 Markdown 处理器"""
        # 基础扩展列表
        extensions = [
            'fenced_code',           # 代码块
            'tables',                # 表格
            'toc',                   # 目录
            'nl2br',                 # 换行转 <br>
            'extra',                 # 额外功能
            'sane_lists',            # 智能列表
        ]
        
        # 尝试添加代码高亮扩展
        try:
            extensions.append('codehilite')
            extension_configs = {
                'codehilite': {
                    'css_class': 'highlight',
                    'use_pygments': True,
                    'noclasses': False,
                },
                'toc': {
                    'permalink': True,
                }
            }
        except Exception:
            extension_configs = {
                'toc': {
                    'permalink': True,
                }
            }
        
        # 尝试添加增强代码块扩展（可选）
        try:
            import pymdownx.superfences
            extensions.append('pymdownx.superfences')
        except ImportError:
            pass  # 如果未安装 pymdown-extensions，跳过
        
        # 配置 Markdown 扩展
        self.md = Markdown(
            extensions=extensions,
            extension_configs=extension_configs
        )
    
    def process(self, text: str, mode: str = 'html') -> str:
        """
        处理 Markdown 文本
        
        Args:
            text: 原始 Markdown 文本
            mode: 处理模式 ('html', 'clean', 'validate')
                - 'html': 转换为 HTML
                - 'clean': 清理并规范化
                - 'validate': 验证格式
        
        Returns:
            处理后的文本
        """
        if not text:
            return text
        
        if mode == 'html':
            return self.to_html(text)
        elif mode == 'clean':
            return self.clean(text)
        elif mode == 'validate':
            return self.validate(text)
        else:
            return text
    
    def to_html(self, text: str) -> str:
        """
        将 Markdown 转换为 HTML
        
        Args:
            text: Markdown 文本
        
        Returns:
            HTML 字符串
        """
        try:
            # 重置 Markdown 实例（避免状态累积）
            self.md.reset()
            # 转换
            html_content = self.md.convert(text)
            return html_content
        except Exception as e:
            # 如果转换失败，返回转义的原始文本
            return f'<pre>{html.escape(text)}</pre>'
    
    def clean(self, text: str) -> str:
        """
        清理和规范化 Markdown 文本
        
        Args:
            text: 原始 Markdown 文本
        
        Returns:
            清理后的 Markdown 文本
        """
        # 移除多余的空白行（保留最多两个连续换行）
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        # 规范化列表格式
        text = self._normalize_lists(text)
        
        # 规范化代码块
        text = self._normalize_code_blocks(text)
        
        # 规范化表格
        text = self._normalize_tables(text)
        
        # 移除行尾空格
        text = re.sub(r' +$', '', text, flags=re.MULTILINE)
        
        return text.strip()
    
    def validate(self, text: str) -> Dict:
        """
        验证 Markdown 格式
        
        Args:
            text: Markdown 文本
        
        Returns:
            验证结果字典
        """
        issues = []
        warnings = []
        
        # 检查未闭合的代码块
        code_block_count = text.count('```')
        if code_block_count % 2 != 0:
            issues.append('未闭合的代码块')
        
        # 检查未闭合的表格
        if '|' in text:
            lines = text.split('\n')
            in_table = False
            for i, line in enumerate(lines):
                if '|' in line and not in_table:
                    in_table = True
                elif in_table and '|' not in line and line.strip():
                    warnings.append(f'第 {i+1} 行：表格可能未正确闭合')
                    in_table = False
        
        # 检查标题格式
        title_pattern = r'^#{1,6}\s+'
        titles = re.findall(title_pattern, text, re.MULTILINE)
        if len(titles) > 0:
            for title in titles:
                if len(title.strip()) > 7:  # 超过 6 个 #
                    warnings.append(f'标题层级过深: {title}')
        
        return {
            'valid': len(issues) == 0,
            'issues': issues,
            'warnings': warnings
        }
    
    def _normalize_lists(self, text: str) -> str:
        """规范化列表格式"""
        lines = text.split('\n')
        normalized = []
        
        for line in lines:
            # 统一无序列表为 -
            if re.match(r'^\s*[+\*]\s+', line):
                line = re.sub(r'^(\s*)[+\*](\s+)', r'\1-\2', line)
            normalized.append(line)
        
        return '\n'.join(normalized)
    
    def _normalize_code_blocks(self, text: str) -> str:
        """规范化代码块格式"""
        # 确保代码块前后有空行
        text = re.sub(r'([^\n])\n```', r'\1\n\n```', text)
        text = re.sub(r'```\n([^\n])', r'```\n\n\1', text)
        return text
    
    def _normalize_tables(self, text: str) -> str:
        """规范化表格格式"""
        lines = text.split('\n')
        normalized = []
        in_table = False
        
        for line in lines:
            if '|' in line:
                if not in_table:
                    in_table = True
                    # 确保表格前有空行
                    if normalized and normalized[-1].strip():
                        normalized.append('')
                # 清理表格中的多余空格
                cells = [cell.strip() for cell in line.split('|')]
                normalized.append('|'.join(cells))
            else:
                if in_table:
                    in_table = False
                    # 确保表格后有空行
                    if line.strip():
                        normalized.append('')
                normalized.append(line)
        
        return '\n'.join(normalized)
    
    def extract_code_blocks(self, text: str) -> List[Dict]:
        """
        提取代码块
        
        Args:
            text: Markdown 文本
        
        Returns:
            代码块列表，每个包含 {'language': str, 'code': str}
        """
        pattern = r'```(\w+)?\n(.*?)```'
        matches = re.findall(pattern, text, re.DOTALL)
        
        code_blocks = []
        for match in matches:
            language = match[0] if match[0] else 'text'
            code = match[1].strip()
            code_blocks.append({
                'language': language,
                'code': code
            })
        
        return code_blocks
    
    def extract_tables(self, text: str) -> List[List[List[str]]]:
        """
        提取表格数据
        
        Args:
            text: Markdown 文本
        
        Returns:
            表格列表，每个表格是二维数组
        """
        tables = []
        lines = text.split('\n')
        current_table = []
        in_table = False
        
        for line in lines:
            if '|' in line:
                if not in_table:
                    in_table = True
                    current_table = []
                # 解析表格行
                cells = [cell.strip() for cell in line.split('|')[1:-1]]
                current_table.append(cells)
            else:
                if in_table and len(current_table) > 1:
                    # 跳过分隔行（包含 --- 的行）
                    if not all('-' in cell or cell == '' for cell in current_table[-1]):
                        tables.append(current_table)
                in_table = False
                current_table = []
        
        # 处理最后一个表格
        if in_table and len(current_table) > 1:
            tables.append(current_table)
        
        return tables
    
    def strip_markdown(self, text: str) -> str:
        """
        移除 Markdown 格式，保留纯文本
        
        Args:
            text: Markdown 文本
        
        Returns:
            纯文本
        """
        # 移除代码块
        text = re.sub(r'```[\s\S]*?```', '', text)
        # 移除行内代码
        text = re.sub(r'`([^`]+)`', r'\1', text)
        # 移除链接，保留文本
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
        # 移除图片
        text = re.sub(r'!\[([^\]]*)\]\([^\)]+\)', r'\1', text)
        # 移除标题标记
        text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
        # 移除粗体和斜体
        text = re.sub(r'\*\*([^\*]+)\*\*', r'\1', text)
        text = re.sub(r'\*([^\*]+)\*', r'\1', text)
        text = re.sub(r'__([^_]+)__', r'\1', text)
        text = re.sub(r'_([^_]+)_', r'\1', text)
        # 移除删除线
        text = re.sub(r'~~([^~]+)~~', r'\1', text)
        # 移除引用标记
        text = re.sub(r'^>\s+', '', text, flags=re.MULTILINE)
        # 移除列表标记
        text = re.sub(r'^[\s]*[-*+]\s+', '', text, flags=re.MULTILINE)
        text = re.sub(r'^[\s]*\d+\.\s+', '', text, flags=re.MULTILINE)
        
        return text.strip()


# 全局实例
_markdown_processor = None

def get_markdown_processor() -> MarkdownProcessor:
    """获取全局 Markdown 处理器实例"""
    global _markdown_processor
    if _markdown_processor is None:
        _markdown_processor = MarkdownProcessor()
    return _markdown_processor


# 便捷函数
def markdown_to_html(text: str) -> str:
    """将 Markdown 转换为 HTML"""
    return get_markdown_processor().to_html(text)


def clean_markdown(text: str) -> str:
    """清理 Markdown 文本"""
    return get_markdown_processor().clean(text)


def validate_markdown(text: str) -> Dict:
    """验证 Markdown 格式"""
    return get_markdown_processor().validate(text)

