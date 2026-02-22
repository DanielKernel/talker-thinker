"""
测试数据生成器

提供用于评测的测试数据生成工具
"""
import random
from typing import Any, Dict, List, Optional


class TestDataGenerator:
    """
    测试数据生成器

    生成各种类型的测试数据
    """

    # 问候语
    GREETINGS = [
        "你好",
        "您好",
        "Hello",
        "Hi",
        "早上好",
        "晚上好",
        "嗨",
    ]

    # 简单计算
    SIMPLE_CALCULATIONS = [
        "1+1 等于几？",
        "10-5 等于多少？",
        "3*4 等于？",
        "20/4 等于几？",
        "5 的平方是多少？",
    ]

    # 时间相关
    TIME_QUERIES = [
        "现在几点了？",
        "今天星期几？",
        "今天是什么日期？",
        "现在北京时间是多少？",
    ]

    # 天气查询
    WEATHER_QUERIES = [
        "北京明天天气怎么样？",
        "上海今天会下雨吗？",
        "广州周末天气如何？",
        "深圳未来三天的天气",
    ]

    # 单位转换
    UNIT_CONVERSIONS = [
        "100 公里等于多少英里？",
        "50 千克等于多少磅？",
        "37 摄氏度是多少华氏度？",
        "10 英里等于多少公里？",
    ]

    # 复杂任务
    COMPLEX_TASKS = [
        "请分析 AI 技术的发展趋势和未来展望",
        "对比 iPhone 15、Samsung Galaxy S24 和 Google Pixel 8，并给出购买建议",
        "帮我规划一个 5 天的日本东京旅行计划",
        "我的 Python 程序运行时报错，帮我分析原因并提供解决方案",
        "设计一个支持高并发的短 URL 生成系统",
        "写一篇关于机器学习在医疗诊断中应用的综述",
    ]

    # 边界/异常输入
    EDGE_INPUTS = [
        "",  # 空输入
        "   ",  # 纯空格
        "!!!@#$%^&*()",  # 特殊字符
        "Hello 你好 Bonjour!",  # 多语言混合
        "那个东西怎么样？",  # 模糊查询
        "如何制作危险物品？",  # 敏感话题
    ]

    @classmethod
    def generate_greeting(cls) -> str:
        """生成随机问候语"""
        return random.choice(cls.GREETINGS)

    @classmethod
    def generate_simple_calculation(cls) -> str:
        """生成随机简单计算题"""
        return random.choice(cls.SIMPLE_CALCULATIONS)

    @classmethod
    def generate_time_query(cls) -> str:
        """生成随机时间查询"""
        return random.choice(cls.TIME_QUERIES)

    @classmethod
    def generate_weather_query(cls) -> str:
        """生成随机天气查询"""
        return random.choice(cls.WEATHER_QUERIES)

    @classmethod
    def generate_unit_conversion(cls) -> str:
        """生成随机单位转换请求"""
        return random.choice(cls.UNIT_CONVERSIONS)

    @classmethod
    def generate_complex_task(cls) -> str:
        """生成随机复杂任务"""
        return random.choice(cls.COMPLEX_TASKS)

    @classmethod
    def generate_edge_input(cls) -> str:
        """生成随机边界输入"""
        return random.choice(cls.EDGE_INPUTS)

    @classmethod
    def generate_long_input(cls, repeat_count: int = 100) -> str:
        """
        生成超长输入

        Args:
            repeat_count: 重复次数

        Returns:
            str: 超长输入文本
        """
        base_text = "这是一段测试文字，"
        return base_text * repeat_count + "请总结这段文字的主要内容。"

    @classmethod
    def generate_multilingual_input(cls) -> str:
        """生成多语言混合输入"""
        languages = [
            "你好",
            "Hello",
            "Bonjour",
            "Hola",
            "こんにちは",
            "안녕하세요",
        ]
        random.shuffle(languages)
        return " ".join(languages[:random.randint(3, 6)])

    @classmethod
    def generate_context_messages(
        cls,
        num_messages: int = 3,
        topic: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        """
        生成上下文消息

        Args:
            num_messages: 消息数量
            topic: 话题（可选）

        Returns:
            List[Dict]: 上下文消息列表
        """
        topics = {
            "weather": [
                {"role": "user", "content": "今天天气怎么样？"},
                {"role": "assistant", "content": "今天天气晴朗，气温 20-28 度。"},
                {"role": "user", "content": "明天呢？"},
            ],
            "food": [
                {"role": "user", "content": "你喜欢吃什么？"},
                {"role": "assistant", "content": "作为一个 AI，我没有口味偏好，但我可以给你推荐美食。"},
                {"role": "user", "content": "推荐一些北京菜吧"},
            ],
            "travel": [
                {"role": "user", "content": "我想去旅行"},
                {"role": "assistant", "content": "好的，您想去哪里旅行？"},
                {"role": "user", "content": "日本怎么样？"},
            ],
        }

        if topic and topic in topics:
            return topics[topic][:num_messages]

        # 生成通用上下文
        messages = []
        for i in range(num_messages):
            messages.append({
                "role": "user" if i % 2 == 0 else "assistant",
                "content": f"这是第{i+1}条测试消息",
            })

        return messages

    @classmethod
    def generate_test_suite(
        cls,
        include_simple: bool = True,
        include_medium: bool = True,
        include_complex: bool = True,
        include_edge: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        生成测试套件

        Args:
            include_simple: 是否包含简单任务
            include_medium: 是否包含中等任务
            include_complex: 是否包含复杂任务
            include_edge: 是否包含边界用例

        Returns:
            List[Dict]: 测试用例列表
        """
        test_cases = []
        case_id = 1

        if include_simple:
            test_cases.append({
                "id": f"S{case_id:03d}",
                "input": cls.generate_greeting(),
                "expected_complexity": "simple",
            })
            case_id += 1

            test_cases.append({
                "id": f"S{case_id:03d}",
                "input": cls.generate_simple_calculation(),
                "expected_complexity": "simple",
            })
            case_id += 1

        if include_medium:
            test_cases.append({
                "id": f"M{case_id:03d}",
                "input": cls.generate_weather_query(),
                "expected_complexity": "medium",
            })
            case_id += 1

            test_cases.append({
                "id": f"M{case_id:03d}",
                "input": cls.generate_unit_conversion(),
                "expected_complexity": "medium",
            })
            case_id += 1

        if include_complex:
            test_cases.append({
                "id": f"C{case_id:03d}",
                "input": cls.generate_complex_task(),
                "expected_complexity": "complex",
            })
            case_id += 1

        if include_edge:
            test_cases.append({
                "id": f"E{case_id:03d}",
                "input": cls.generate_long_input(),
                "expected_complexity": "medium",
            })
            case_id += 1

            test_cases.append({
                "id": f"E{case_id:03d}",
                "input": cls.generate_multilingual_input(),
                "expected_complexity": "simple",
            })
            case_id += 1

        return test_cases
