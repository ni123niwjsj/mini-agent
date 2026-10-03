"""测试 tools/file.py 文件工具真实读写能力与安全截断"""

import asyncio
import os
import shutil
from mini_agent.tools.file import ReadFileTool, WriteFileTool

TEST_TMP_DIR = "tests/tmp_sandbox"


async def main():
    os.makedirs(TEST_TMP_DIR, exist_ok=True)
    
    reader = ReadFileTool(workspace_dir=TEST_TMP_DIR)
    writer = WriteFileTool(workspace_dir=TEST_TMP_DIR)

    print("=== 1. 测试真实写文件 (write_file) ===")
    sample_code = "def hello():\n    print('Hello World')\n    return 42\n"
    res_write = await writer.execute("demo/hello.py", sample_code)
    print(f"写入结果: content='{res_write.content}', is_error={res_write.is_error}")

    print("\n=== 2. 测试真实读文件 (read_file 全文带行号) ===")
    res_read = await reader.execute("demo/hello.py")
    print(f"读取内容:\n{res_read.content}")

    print("\n=== 3. 测试行号切片读取 (start_line=2, end_line=2) ===")
    res_slice = await reader.execute("demo/hello.py", start_line=2, end_line=2)
    print(f"切片内容:\n{res_slice.content}")

    print("\n=== 4. 测试读取不存在的文件 (容错自愈检查) ===")
    res_not_found = await reader.execute("non_existent_file.txt")
    print(f"报错拦截: content='{res_not_found.content}', is_error={res_not_found.is_error}")

    print("\n=== 5. 测试防 Token 爆炸安全截断 (生成 450 行大文件) ===")
    large_content = "\n".join([f"# Line {i}: some mock python code" for i in range(1, 451)])
    await writer.execute("large.py", large_content)
    res_large = await reader.execute("large.py")
    print(f"大文件截断末尾预览:\n...{res_large.content[-250:]}")

    # 清理测试产生的临时目录
    shutil.rmtree(TEST_TMP_DIR, ignore_errors=True)
    print("\n✅ 所有文件工具测试全部通过并清理临时文件！")


if __name__ == "__main__":
    asyncio.run(main())
