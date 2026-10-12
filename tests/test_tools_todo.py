import asyncio
import unittest
from mini_agent.tools.todo import TodoTool


class TestTodoTool(unittest.TestCase):
    def setUp(self):
        self.todo_tool = TodoTool()

    def test_schema(self):
        schema = self.todo_tool.get_schema()
        self.assertEqual(schema["type"], "function")
        self.assertEqual(schema["function"]["name"], "todo")
        self.assertIn("action", schema["function"]["parameters"]["properties"])

    def test_add_and_list_todos(self):
        # 初始列表为空
        res = asyncio.run(self.todo_tool.execute(action="list"))
        self.assertFalse(res.is_error)
        self.assertIn("暂无任务待办项", res.content)

        # 添加任务 1
        res1 = asyncio.run(self.todo_tool.execute(action="add", task="设计数据库表结构"))
        self.assertFalse(res1.is_error)
        self.assertIn("已添加任务 #1", res1.content)
        self.assertIn("[ ] #1: 设计数据库表结构 (pending)", res1.content)

        # 添加任务 2
        res2 = asyncio.run(self.todo_tool.execute(action="add", task="编写 API 接口", status="in_progress"))
        self.assertFalse(res2.is_error)
        self.assertIn("已添加任务 #2", res2.content)
        self.assertIn("[▶] #2: 编写 API 接口 (in_progress)", res2.content)

        # 验证 list 输出统计
        res_list = asyncio.run(self.todo_tool.execute(action="list"))
        self.assertIn("共 2 项, 0 已完成, 1 进行中, 1 待处理", res_list.content)

    def test_update_todo(self):
        asyncio.run(self.todo_tool.execute(action="add", task="任务 A"))
        asyncio.run(self.todo_tool.execute(action="add", task="任务 B"))

        # 更新状态为 completed
        res = asyncio.run(self.todo_tool.execute(action="update", task_id=1, status="completed"))
        self.assertFalse(res.is_error)
        self.assertIn("[✔] #1: 任务 A (completed)", res.content)

        # 更新任务描述和状态
        res2 = asyncio.run(self.todo_tool.execute(action="update", task_id=2, task="任务 B (已取消)", status="cancelled"))
        self.assertFalse(res2.is_error)
        self.assertIn("[✖] #2: 任务 B (已取消) (cancelled)", res2.content)

    def test_clear_todos(self):
        asyncio.run(self.todo_tool.execute(action="add", task="临时任务"))
        res = asyncio.run(self.todo_tool.execute(action="clear"))
        self.assertFalse(res.is_error)
        self.assertIn("已清空任务清单 (共清除 1 项)", res.content)

        res_list = asyncio.run(self.todo_tool.execute(action="list"))
        self.assertIn("暂无任务待办项", res_list.content)

    def test_error_handling(self):
        # add 缺少 task
        res_add_err = asyncio.run(self.todo_tool.execute(action="add"))
        self.assertTrue(res_add_err.is_error)
        self.assertIn("必须提供 'task'", res_add_err.content)

        # update 缺少 task_id
        res_upd_err1 = asyncio.run(self.todo_tool.execute(action="update", status="completed"))
        self.assertTrue(res_upd_err1.is_error)
        self.assertIn("必须提供 'task_id'", res_upd_err1.content)

        # update 不存在的 task_id
        res_upd_err2 = asyncio.run(self.todo_tool.execute(action="update", task_id=999, status="completed"))
        self.assertTrue(res_upd_err2.is_error)
        self.assertIn("未找到编号为 #999", res_upd_err2.content)

        # update 非法 status
        asyncio.run(self.todo_tool.execute(action="add", task="测试"))
        res_upd_err3 = asyncio.run(self.todo_tool.execute(action="update", task_id=1, status="unknown_status"))
        self.assertTrue(res_upd_err3.is_error)
        self.assertIn("非法状态", res_upd_err3.content)

        # 未知 action
        res_unknown = asyncio.run(self.todo_tool.execute(action="delete"))
        self.assertTrue(res_unknown.is_error)
        self.assertIn("未知动作", res_unknown.content)

    def test_persistence_and_reload(self):
        import tempfile
        import shutil

        temp_dir = tempfile.mkdtemp()
        storage_file = f"{temp_dir}/session1.todo.json"

        try:
            # 1. 实例 1 添加任务
            tool1 = TodoTool(storage_file=storage_file)
            asyncio.run(tool1.execute(action="add", task="持久化任务 1"))
            asyncio.run(tool1.execute(action="add", task="持久化任务 2", status="in_progress"))

            # 2. 模拟进程重启或恢复会话: 实例化工具 2
            tool2 = TodoTool(storage_file=storage_file)
            res_list = asyncio.run(tool2.execute(action="list"))
            self.assertIn("#1: 持久化任务 1", res_list.content)
            self.assertIn("#2: 持久化任务 2", res_list.content)

            # 3. 动态重定向会话
            storage_file2 = f"{temp_dir}/session2.todo.json"
            tool2.set_storage_file(storage_file2)
            res_empty = asyncio.run(tool2.execute(action="list"))
            self.assertIn("暂无任务待办项", res_empty.content)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

