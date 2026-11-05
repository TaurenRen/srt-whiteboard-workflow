#!/usr/bin/env python3
"""
srt-whiteboard-workflow 快速测试脚本
用于验证项目环境和基本功能是否正常工作
"""

import os
import sys
import subprocess
from pathlib import Path

def test_environment():
    """测试项目环境准备"""
    print("=== 测试 srt-whiteboard-animation 环境 ===")
    
    # 检查项目目录
    project_path = Path.cwd() / "srt-whiteboard-animation"
    if not project_path.exists():
        print("❌ 项目目录不存在，请先克隆:")
        print("   git clone https://github.com/geeklee/srt-whiteboard-animation.git")
        return False
    
    print(f"✅ 项目目录: {project_path}")
    
    # 检查 venv
    venv_path = project_path / ".venv"
    if not venv_path.exists():
        print("❌ 虚拟环境不存在，请运行:")
        print(f"   cd {project_path} && python scripts/prepare_env.py")
        return False
    
    print(f"✅ 虚拟环境: {venv_path}")
    
    # 检查 Python 可执行文件
    python_exe = venv_path / "Scripts" / "python.exe" if os.name == 'nt' else venv_path / "bin" / "python"
    if not python_exe.exists():
        print("❌ Python 可执行文件不存在")
        return False
    
    print(f"✅ Python: {python_exe}")
    
    # 测试依赖
    test_script = project_path / "scripts" / "parse_srt.py"
    if not test_script.exists():
        print("❌ 脚本文件不存在")
        return False
    
    try:
        result = subprocess.run(
            [str(python_exe), str(test_script), "--help"],
            capture_output=True,
            text=True,
            cwd=project_path
        )
        if result.returncode == 0:
            print("✅ SRT 解析脚本: 正常")
        else:
            print(f"❌ SRT 解析脚本: 失败\n{result.stderr}")
            return False
    except Exception as e:
        print(f"❌ 测试异常: {e}")
        return False
    
    return True

def create_test_srt():
    """创建测试用 SRT 文件"""
    srt_content = """1
00:00:00,000 --> 00:00:05,000
这是一个快速测试字幕文件

2
00:00:05,000 --> 00:00:10,000
用于验证 srt-whiteboard-animation 功能

3
00:00:10,000 --> 00:00:15,000
测试完成，环境准备就绪
"""
    
    test_dir = Path.cwd() / "test_output"
    test_dir.mkdir(exist_ok=True)
    
    srt_path = test_dir / "test_quick.srt"
    srt_path.write_text(srt_content, encoding="utf-8")
    
    print(f"✅ 测试 SRT 文件已创建: {srt_path}")
    return srt_path, test_dir

def main():
    """主函数"""
    print("srt-whiteboard-workflow 快速测试工具")
    print("=" * 50)
    
    # 测试环境
    if not test_environment():
        print("\n❌ 环境测试失败，请检查环境准备")
        return 1
    
    # 创建测试文件
    print("\n=== 创建测试文件 ===")
    srt_path, test_dir = create_test_srt()
    
    # 测试解析
    print("\n=== 测试 SRT 解析 ===")
    project_path = Path.cwd() / "srt-whiteboard-animation"
    python_exe = project_path / ".venv" / "Scripts" / "python.exe" if os.name == 'nt' else project_path / ".venv" / "bin" / "python"
    parse_script = project_path / "scripts" / "parse_srt.py"
    
    try:
        result = subprocess.run(
            [str(python_exe), str(parse_script), str(srt_path)],
            capture_output=True,
            text=True,
            cwd=project_path
        )
        
        if result.returncode == 0:
            print("✅ SRT 解析成功")
            # 保存解析结果
            json_path = test_dir / "test_parsed.json"
            with open(json_path, "w", encoding="utf-8") as f:
                f.write(result.stdout)
            print(f"   解析结果: {json_path}")
        else:
            print(f"❌ SRT 解析失败: {result.stderr}")
            return 1
    except Exception as e:
        print(f"❌ 解析异常: {e}")
        return 1
    
    print("\n" + "=" * 50)
    print("✅ 所有测试通过！环境准备就绪。")
    print(f"   测试文件保存在: {test_dir}")
    print("\n下一步: ")
    print("1. 准备手绘图像 (PNG, 背景 #F5EBD7)")
    print("2. 编写对应的 annotation.json 标注文件")
    print("3. 运行渲染: python scripts/render_stream_whiteboard.py ...")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())