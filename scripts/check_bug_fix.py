#!/usr/bin/env python3
"""
检查并修复 srt-whiteboard-animation 的已知 bug
修复 render_stream_whiteboard.py 第405行的参数错误
"""

import os
import re
from pathlib import Path
import shutil

def check_bug(file_path):
    """检查指定文件是否有bug"""
    if not file_path.exists():
        print(f"❌ 文件不存在: {file_path}")
        return False
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 查找错误的代码行
    bug_pattern = r'self\._lay_ink\(writer,\s*ink_frames,\s*\[\],\s*set\(\)(?:,\s*None)?,\s*allowed\)'
    match = re.search(bug_pattern, content)
    
    if match:
        print(f"⚠️  发现bug代码: {match.group()}")
        return True
    else:
        print(f"✅ 未发现bug")
        return False

def fix_bug(file_path):
    """修复bug"""
    if not file_path.exists():
        print(f"❌ 文件不存在: {file_path}")
        return False
    
    # 备份原文件
    backup_path = file_path.with_suffix(file_path.suffix + '.bak')
    shutil.copy2(file_path, backup_path)
    print(f"📁 已备份原文件: {backup_path}")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    fixed = False
    for i, line in enumerate(lines):
        # 查找错误的行
        if 'self._lay_ink(writer, ink_frames, [], set(), None, allowed)' in line:
            # 修复：移除None参数
            fixed_line = line.replace('self._lay_ink(writer, ink_frames, [], set(), None, allowed)', 
                                     'self._lay_ink(writer, ink_frames, [], set(), allowed)')
            lines[i] = fixed_line
            fixed = True
            print(f"🔧 修复第 {i+1} 行: {fixed_line.strip()}")
    
    if fixed:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        print(f"✅ bug已修复")
        return True
    else:
        print(f"✅ 无需修复，bug可能已被修复")
        return False

def verify_fix(file_path):
    """验证修复结果"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 检查是否还有错误形式
    bug_pattern1 = r'self\._lay_ink\([^)]*None[^)]*\)'
    bug_pattern2 = r'self\._lay_ink\(writer,\s*ink_frames,\s*\[\],\s*set\(\)(?:,\s*None)?,\s*allowed\)'
    
    if re.search(bug_pattern1, content) or re.search(bug_pattern2, content):
        print("❌ 修复验证失败，仍有bug存在")
        return False
    else:
        print("✅ 修复验证通过")
        return True

def main():
    """主函数"""
    print("srt-whiteboard-animation bug检查与修复工具")
    print("=" * 60)
    
    # 获取当前目录
    current_dir = Path.cwd()
    
    # 检查是否是项目目录
    script_file = current_dir / "scripts" / "render_stream_whiteboard.py"
    if not script_file.exists():
        # 检查子目录
        script_file = current_dir / "srt-whiteboard-animation" / "scripts" / "render_stream_whiteboard.py"
        if not script_file.exists():
            print("❌ 未找到 render_stream_whiteboard.py 文件")
            print("   请确保在 srt-whiteboard-animation 项目目录或其父目录运行此脚本")
            return 1
    
    print(f"📄 目标文件: {script_file}")
    print()
    
    # 检查bug
    print("=== 检查bug ===")
    has_bug = check_bug(script_file)
    print()
    
    if has_bug:
        # 询问是否修复
        print("是否修复此bug? [Y/n]: ", end="")
        choice = input().strip().lower()
        
        if choice in ['', 'y', 'yes']:
            print()
            print("=== 开始修复 ===")
            if fix_bug(script_file):
                print()
                print("=== 验证修复 ===")
                if verify_fix(script_file):
                    print()
                    print("✅ 修复成功！现在可以正常使用渲染功能。")
                else:
                    print()
                    print("❌ 修复验证失败，可能需要手动修复")
            else:
                print()
                print("❌ 修复失败")
        else:
            print()
            print("ℹ️  跳过修复，但渲染时可能会遇到错误:")
            print("   TypeError: RegionStreamRenderer._lay_ink() takes 6 positional arguments but 7 were given")
    else:
        print("✅ 项目环境正常，可直接使用")
    
    print()
    print("=" * 60)
    print("Bug信息:")
    print("- 问题: _lay_ink() 方法调用时多传递了一个 None 参数")
    print("- 位置: render_stream_whiteboard.py 第405行")
    print("- 影响: 导致渲染失败，抛出 TypeError")
    print("- 修复: 移除多余的 None 参数")
    print("- 修复前: self._lay_ink(writer, ink_frames, [], set(), None, allowed)")
    print("- 修复后: self._lay_ink(writer, ink_frames, [], set(), allowed)")
    
    return 0

if __name__ == "__main__":
    try:
        import shutil
        import re
        main()
    except KeyboardInterrupt:
        print("\n\n操作被用户中断")
    except Exception as e:
        print(f"❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()