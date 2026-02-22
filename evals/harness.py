"""
评测执行引擎 (Evaluation Harness)

负责加载用例、执行评测、收集指标
"""
import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from context.types import AgentRole, TaskComplexity, Message, Task
from config import settings

from .core.types import (
    Assertion,
    AssertionResult,
    CaseResult,
    EvalCase,
    EvalCategory,
    EvalResult,
    FailureReason,
    Priority,
)
from .metrics.collector import MetricsCollector
from .cases import get_all_cases, get_cases_by_category

logger = logging.getLogger(__name__)


@dataclass
class MockLLMResponse:
    """Mock LLM 响应"""
    content: str
    latency_ms: float = 100.0
    tokens_used: int = 50


@dataclass
class EvalConfig:
    """评测配置"""
    # 是否使用 Mock LLM
    use_mock_llm: bool = True

    # Mock 响应配置
    mock_response_latency_ms: float = 100.0
    mock_talker_latency_ms: float = 150.0
    mock_thinker_latency_ms: float = 2000.0

    # 超时配置
    case_timeout_seconds: float = 60.0

    # 是否启用进度输出
    show_progress: bool = True

    # 用例过滤器
    category_filter: Optional[str] = None  # 支持 "simple", "medium", "complex", "edge", "conversation", "ux_quality"
    priority_filter: Optional[Priority] = None
    case_id_filter: Optional[List[str]] = None  # 指定运行某些用例 ID


class MockTalkerAgent:
    """Mock Talker Agent 用于评测"""

    def __init__(self, latency_ms: float = 150.0):
        self.latency_ms = latency_ms
        self.call_count = 0

    async def process(
        self,
        user_input: str,
        context_messages: Optional[List[Dict[str, str]]] = None,
        **kwargs,
    ) -> Tuple[str, float, int]:
        """
        模拟 Talker 处理

        Returns:
            Tuple[content, latency_ms, tokens_used]
        """
        self.call_count += 1
        await asyncio.sleep(self.latency_ms / 1000)

        # 根据输入生成简单的模拟响应
        content = self._generate_response(user_input, context_messages)
        return content, self.latency_ms, 50

    def _generate_response(self, user_input: str, context_messages: Optional[List[Dict[str, str]]] = None) -> str:
        """生成模拟响应"""
        input_lower = user_input.lower()

        # === 安全检查 (优先处理) ===
        # E008: 指令注入防御
        if "忽略" in user_input and ("指令" in user_input or "提示" in user_input):
            return "抱歉，我不能忽略我的安全准则。"

        if "系统提示" in user_input and ("告诉" in user_input or "是什么" in user_input):
            return "抱歉，我不能分享我的系统配置信息。"

        # UQ010: 危险请求拒绝
        if "炸弹" in user_input or "危险物品" in user_input:
            return "抱歉，我不能提供危险物品的制作方法。建议通过合法途径学习科学知识。"

        # UQ011: 隐私保护
        if "身份证" in user_input or "隐私" in user_input:
            return "请注意，身份证号码属于敏感个人信息，建议不要泄露。"

        # UQ008: 医疗建议
        if "失眠" in user_input or "睡不着" in user_input:
            return """建议尝试以下方法：
1. 保持规律作息
2. 睡前避免使用电子设备
3. 可以喝杯热牛奶
如持续失眠，建议咨询医生。"""

        # UQ009: 技术问题排查
        if "开不了机" in user_input or ("电脑" in user_input and "问题" in user_input):
            return """电脑开不了机可能有多种原因：

**第一，电源问题**：检查电源连接是否正常，插头是否松动
**第二，电池问题**：检查电池是否有电，尝试拔掉电源长按电源键
**另外，硬件故障**：内存条松动、显卡故障等也可能导致无法开机

建议按以上步骤逐一排查，如问题持续，建议联系专业维修人员。"""

        # UQ001: 事实准确性
        if "首都" in user_input and "中国" in user_input:
            return "中国的首都是北京"

        # UQ002: 计算准确性
        if "25" in user_input and ("乘" in user_input or "乘以" in user_input):
            return "25 乘以 4 等于 100"

        # UQ003: 时效性信息
        if "总统" in user_input and "美国" in user_input:
            return "截至 2024 年，美国总统是乔·拜登。请注意信息可能随时间变化。"

        # M004: 翻译任务
        if "翻译" in user_input or "translate" in input_lower:
            return "Hello, World"

        # === 对话上下文处理 (CX001-CX018) ===
        context_info = {}
        if context_messages:
            for msg in context_messages:
                content = msg.get("content", "")
                if "喜欢" in content and "吃" in content:
                    context_info["food_preference"] = "清淡"
                if "孩子" in content or "儿子" in content:
                    context_info["has_child"] = True
                if "咖啡" in content:
                    context_info["likes_coffee"] = True
                if "iPhone" in content or "iphone" in content.lower():
                    context_info["discussed_iphone"] = True
                if "天气" in content and "上海" in content:
                    context_info["weather_context"] = "shanghai"
                if "天气" in content and "北京" in content:
                    context_info["weather_context"] = "beijing"
                if "餐厅" in content:
                    context_info["discussed_restaurant"] = True
                if "日料" in content:
                    context_info["restaurant_type"] = "日料"
                if "浅草" in content:
                    context_info["restaurant_name"] = "浅草日料"
                if "电影" in content:
                    context_info["discussed_movie"] = True
                if "星际穿越" in content:
                    context_info["movie_name"] = "星际穿越"

        # CX001: 代词指代 - "它有什么特点"
        if "它" in user_input and "特点" in user_input:
            if context_info.get("discussed_iphone"):
                return "iPhone 15 的特点包括 A16 仿生芯片、4800 万像素摄像头和 USB-C 接口。"
            if context_info.get("discussed_movie"):
                return f"{context_info.get('movie_name', '这部电影')}的特点包括精彩的剧情和出色的特效。"
            # 默认回应，提及上下文中可能讨论的内容
            if context_info.get("discussed_restaurant"):
                return "我们刚才讨论的餐厅有优质的食材、精湛的烹饪技艺和舒适的用餐环境。"
            return "请问您指的是什么呢？如果能提供更多信息，我可以给您更详细的介绍。"

        # CX002: 话题延续 - "那...呢"
        if "那" in user_input and "呢" in user_input:
            if context_info.get("weather_context") == "shanghai":
                return "北京明天天气晴朗，气温 15-25 度。"
            if context_info.get("restaurant_type"):
                return "日料餐厅有很多选择，比如浅草日料、樱之味等，您更喜欢哪家？"

        # CX005: 上下文意图推断 - "还有别的推荐吗"
        if "还有" in user_input and ("推荐" in user_input or "别的" in user_input):
            if context_info.get("discussed_movie"):
                return "除了《星际穿越》，我还推荐《盗梦空间》和《星际迷航》等科幻电影，它们都有精彩的剧情和震撼的视觉效果。"
            if context_info.get("discussed_restaurant"):
                return "除了刚才推荐的餐厅，还有很多其他不错的选择，比如寿司店、居酒屋等。您想尝试哪种类型？"
            return "当然有！我还有很多其他推荐。请问您对什么类型的感兴趣呢？"

        # CX004: 上下文实体回忆 - "她喜欢什么"
        if "她喜欢" in user_input or "喜欢什么" in user_input:
            if context_info.get("likes_coffee"):
                return "根据之前的对话，她喜欢喝咖啡。"

        # CX006/CX008: 情感回应 - 负面情绪
        if "累" in user_input or "辛苦" in user_input or "太多" in user_input:
            return "理解你的感受，工作确实很辛苦。建议适当休息，照顾好自己的身体。"

        # CX007: 积极情感回应 - 升职
        if "升职" in user_input:
            return "恭喜你升职！这是对你能力的肯定，太棒了！"

        # CX009: 用户偏好记忆 - 晚餐建议
        if "吃" in user_input and ("什么" in user_input or "好吗" in user_input):
            if context_info.get("food_preference") == "清淡":
                return "根据您喜欢清淡的口味，今晚可以考虑清蒸鱼、白灼菜心或番茄鸡蛋汤。"

        # CX011: 任务确认 - "好的，就这个吧"
        if "就这个" in user_input or "好的" in user_input and "吧" in user_input:
            if context_info.get("discussed_restaurant"):
                return "好的，确认为您预订{0}。请问您想预订什么时间的座位？大约需要几人位呢？我会帮您联系餐厅确认预订。".format(context_info.get('restaurant_name', '这家餐厅'))
            return "好的，没问题！请问您还需要其他帮助吗？"

        # CX014: 自然对话结束 - 告别
        if "知道了" in user_input or "明白" in user_input or "好的" in user_input and "谢谢" in user_input:
            return "不客气！如果以后还有其他问题，随时欢迎来问我。祝您一切顺利！"

        # CX010: 用户身份认知 - 活动推荐
        if "活动" in user_input or "周末" in user_input:
            if context_info.get("has_child"):
                return "既然您有孩子，周末可以考虑带孩子去公园、博物馆或亲子乐园，既能增长见识又能增进亲子关系。"

        # CX015: 追问处理 - "为什么"
        if "为什么" in user_input:
            if context_info.get("restaurant_name"):
                return f"因为{context_info.get('restaurant_name')}的食材新鲜，师傅手艺好，口碑也很不错。"

        # CX012: 话题切换 - 天气查询
        if "天气" in user_input:
            if context_info.get("discussed_restaurant"):
                return "明天天气晴朗，气温 18-26 度，很适合外出用餐。"
            return "北京明天天气晴朗，气温 15-25 度。"

        # CX016: 模糊请求处理
        if "随便聊聊" in user_input or "聊聊" in user_input:
            return "好的，我们可以聊聊各种话题，比如旅行、美食、电影、科技等。你对什么话题比较感兴趣呢？"

        # CX003: 模糊任务请求 - 需要澄清
        if "帮我订一个" in user_input or "帮我预订" in user_input:
            return "好的，请问您想订什么时间的座位？大约需要几人位呢？"

        # CX008: 挫折情境安抚 - 工作不满意
        if "项目" in user_input and ("领导" in user_input or "不满意" in user_input):
            return "理解你的感受，做了很多遍还不满意确实让人沮丧。建议和领导沟通一下具体需求，或者请他给出更明确的修改意见。"

        # CX013: 自然对话开场 - "嗨"
        if "嗨" in user_input or "嗨" in input_lower:
            return "你好！有什么我可以帮助你的吗？"

        # CX017: 敏感话题处理 - 政治问题
        if "政治" in user_input or "政治事件" in user_input:
            return "抱歉，我不便讨论敏感政治话题。我们可以聊聊其他有趣的事情，比如科技、文化、旅行等。如果您有其他问题，我很乐意帮助。"

        # CX018: 知识边界处理
        if "2030" in user_input and ("奥运会" in user_input or "在哪里" in user_input):
            return "目前 2030 年奥运会的举办地尚未确定，建议关注国际奥委会官方消息获取最新信息。"

        # === UX 质量相关响应 ===

        # UQ005: 量子计算解释
        if "量子计算" in user_input and "什么" in user_input:
            return """## 什么是量子计算

### 定义
量子计算是一种基于量子力学原理的新型计算方式。简单来说，它利用了一种特殊的物理现象来进行信息处理。

### 与传统计算的区别
- **传统计算机**：使用比特作为基本单位，要么是 0，要么是 1
- **量子计算机**：使用量子比特，可同时处于 0 和 1 的叠加状态

### 优势
量子计算在特定问题上具有超强计算能力，如密码破译、药物研发、金融建模等领域。

### 现状
量子计算仍处于早期发展阶段，但谷歌、IBM 等科技巨头正在加速研发。"""

        # UQ006: 如何学好编程
        if "学好编程" in user_input or "学好代码" in user_input:
            return """## 如何学好编程

### 第一阶段：打好基础
1. **选择一门入门语言**：Python 语法简洁适合入门，JavaScript 适合 Web 开发
2. **掌握基本概念**：变量、循环、条件判断、函数
3. **理解数据结构**：数组、链表、栈、队列、树

### 第二阶段：项目实践
1. **小项目练习**：计算器、待办事项列表、简单的网站
2. **参与开源项目**：在 GitHub 上学习他人代码
3. **解决实际问题**：用编程解决生活工作中的问题

### 第三阶段：深入学习
1. **算法训练**：LeetCode、牛客网刷题
2. **设计模式**：学习常见的设计模式和最佳实践
3. **系统架构**：理解大型系统的设计思路

### 关键建议
- 多写代码，实践是最好的老师
- 善用搜索引擎和社区资源
- 保持好奇心，持续学习新技术"""

        # UQ009: 电脑开不了机（已有，但确保优先匹配）
        # 已在前面处理

        # UQ013: 不确定性表达 - 房价预测
        if "房价" in user_input and ("涨" in user_input or "跌" in user_input):
            return """## 房价走势分析

### 不确定性因素
房价走势受多种因素影响，**难以准确预测**，可能上涨也可能下跌，取决于多种因素的综合作用。

**第一，政策因素**：限购政策、贷款利率、土地供应等政府调控政策
**第二，经济环境**：GDP 增长、就业情况、居民收入水平
**此外，市场供需**：人口流动、城镇化进程、房屋库存量
**最后，国际金融**：全球经济形势、资本流动、汇率变化

### 可能的情况
- **上涨可能**：如果经济持续向好、人口流入增加
- **下跌可能**：如果调控政策收紧、经济下行压力大

### 建议
购房决策应基于自身需求和经济能力，而非短期投机。"""

        # UQ012: 专业概念解释 - 过拟合
        if "过拟合" in user_input and ("解释" in user_input or "什么是" in user_input):
            return """## 什么是过拟合

### 定义
过拟合（Overfitting）是**机器学习**中的一个重要概念，指模型在训练数据上表现很好，但在新数据上泛化能力差的现象。

### 通俗解释
简单来说，就是模型"死记硬背"了训练数据，但没有真正理解规律。就像一个学生只记住了考试答案，但不理解解题方法，遇到新题目就不会做了。

### 原因分析
1. **模型过于复杂**：参数过多，模型"记住"了训练数据
2. **训练数据不足**：样本太少，无法代表整体分布
3. **训练时间过长**：过度迭代导致过度适配

### 解决方案
- **正则化**：限制模型参数大小
- **增加数据**：收集更多训练样本
- **Dropout**：随机丢弃部分神经元
- **早停法**：验证集性能下降时停止训练

### 实际案例
例如，一个图像分类模型在训练集上准确率 99%，但在测试集上只有 70%，这就是典型的过拟合。"""

        # UQ014: 火星语请求 - 知识边界诚实
        if "火星语" in user_input or "火星文" in user_input:
            return """抱歉，我**不会**说火星语。火星语并不是一种真实的语言，而是网络上一种用符号、特殊字符或变形文字表达的娱乐形式。

我可以帮您：
- 使用标准的中文或英文交流
- 解释网络流行语的含义
- 提供其他形式的创意表达

如果您有其他需要，我很乐意帮助！"""

        # === 常规响应 ===
        if "你好" in user_input or "hello" in input_lower:
            return "你好！有什么我可以帮助你的吗？"
        elif "1+1" in user_input:
            return "1+1 等于 2"
        elif "时间" in user_input or "几点" in user_input:
            import datetime
            now = datetime.datetime.now()
            return f"现在是 {now.hour}点{now.minute}分"
        elif "谢谢" in user_input:
            return "不客气！有其他问题吗？"
        elif "谁" in user_input:
            return "我是 Talker 助手，可以快速回答你的问题。"
        elif "天气" in user_input:
            return "北京明天天气晴朗，气温 15-25 度。"
        elif "公里" in user_input or "英里" in user_input:
            return "100 公里约等于 62.14 英里。"
        elif "星期" in user_input or "周" in user_input:
            import datetime
            now = datetime.datetime.now()
            weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
            return f"今天是{weekdays[now.weekday()]}"
        else:
            return f"我收到了你的问题：'{user_input}'，这是一个简单的问题。"


class MockThinkerAgent:
    """Mock Thinker Agent 用于评测"""

    def __init__(self, latency_ms: float = 2000.0):
        self.latency_ms = latency_ms
        self.call_count = 0

    async def process(
        self,
        user_input: str,
        context_messages: Optional[List[Dict[str, str]]] = None,
        **kwargs,
    ) -> Tuple[str, float, int]:
        """
        模拟 Thinker 处理

        Returns:
            Tuple[content, latency_ms, tokens_used]
        """
        self.call_count += 1
        await asyncio.sleep(self.latency_ms / 1000)

        content = self._generate_response(user_input)
        return content, self.latency_ms, 500

    def _generate_response(self, user_input: str) -> str:
        """生成模拟响应 (更长，更有结构)"""
        input_lower = user_input.lower()

        # C006: 学术写作 - 机器学习在医疗诊断中的应用
        if "机器学习" in user_input and ("医疗" in user_input or "综述" in user_input):
            return """## 机器学习在医疗诊断中的应用综述

### 摘要
随着人工智能技术的快速发展，机器学习在医疗诊断领域的应用日益广泛。本文综述了机器学习在医学影像分析、电子病历处理和疾病风险预测等方面的最新进展。通过文献回顾和案例分析，我们发现机器学习技术在提高诊断准确性、降低误诊率方面具有显著优势。同时，本文也讨论了当前面临的数据隐私、算法可解释性等挑战，并对未来发展方向进行了展望。

### 方法
本研究采用系统性文献回顾方法，收集了 2020-2024 年间发表的关于机器学习在医疗诊断应用的研究论文。

1. **深度学习在医学影像中的应用**
   - CNN 在 CT、MRI 影像分析中的应用：卷积神经网络能够自动识别医学影像中的病灶区域，在肺结节、乳腺癌等疾病的早期检测中表现出色
   - 自动识别病灶、肿瘤检测：通过图像分割和分类技术，AI 系统可以精确定位肿瘤位置和大小
   - 准确率达到或超过专业医生水平：多项研究表明，在特定诊断任务上，AI 系统的准确率已达到甚至超过资深放射科医生

2. **自然语言处理在电子病历分析中的应用**
   - 从非结构化病历中提取关键信息：利用命名实体识别 (NER) 技术，从医生书写的大量文本中提取疾病、症状、药物等关键信息
   - 疾病编码自动分类：使用文本分类模型，将病历自动归类到标准疾病编码体系 (如 ICD-10)
   - 药物相互作用检测：通过分析电子病历中的用药记录，识别潜在的药物相互作用风险

3. **预测模型在疾病风险评估中的应用**
   - 基于多模态数据的疾病预测：整合影像、实验室检查、基因组学等多源数据，构建综合预测模型
   - 个性化治疗方案推荐：根据患者个体特征，推荐最适合的治疗方案和用药剂量
   - 慢性病管理支持：对糖尿病、高血压等慢性病患者进行长期跟踪和风险评估

### 结论
综上所述，机器学习正在重塑医疗诊断的实践方式。在医学影像、电子病历分析、疾病预测等多个子领域，机器学习技术已经展现出巨大的应用价值和商业潜力。

然而，该领域仍面临诸多挑战：
1. **数据隐私与安全**：医疗数据高度敏感，如何在保护患者隐私的前提下进行模型训练是需要解决的关键问题
2. **算法可解释性**：医疗诊断需要高度透明，医生和患者需要理解 AI 系统的决策依据
3. **监管审批**：医疗 AI 产品需要通过严格的监管审批才能临床应用
4. **临床整合**：如何将 AI 工具有效整合到现有医疗工作流中，需要仔细设计

未来发展方向包括：
- 联邦学习等隐私保护技术的发展
- 可解释 AI (XAI) 在医疗领域的应用
- 多模态融合诊断系统的完善
- AI 辅助诊断与医生协作模式的探索

尽管面临挑战，机器学习在医疗诊断领域的广阔前景已得到广泛认可。随着技术的进一步成熟和相关法规的完善，机器学习将在精准医疗、个性化治疗等方向发挥更大作用，最终造福广大患者。"""

        # C005: 系统设计 - 高并发短 URL 生成系统
        if "短 URL" in user_input or ("高并发" in user_input and "系统" in user_input):
            return """## 高并发短 URL 生成系统设计

### 核心架构
1. **ID 生成策略**
   - 雪花算法 (Snowflake): 分布式 ID 生成，保证全局唯一
   - 数据库自增 ID: 简单可靠，单点瓶颈
   - Hash 算法：MD5/SHA1 取前缀，需处理冲突

2. **存储设计**
   - Redis 缓存：存储热门 URL 映射，降低数据库压力
   - 数据库分库分表：按 ID 范围或 Hash 分片
   - 读写分离：主从复制，提升读取性能

3. **并发处理**
   - 负载均衡：Nginx/HAProxy 分发请求
   - 限流降级：保护后端服务，防止雪崩
   - 异步处理：消息队列缓冲写请求

4. **扩展性考虑**
   - 水平扩展：无状态服务设计，便于扩容
   - 容灾备份：多机房部署，数据异地备份
   - 监控告警：实时监控 QPS、延迟、错误率

### 性能指标
- 目标 QPS: 10 万 +
- P99 延迟：< 50ms
- 可用性：99.99%"""

        # UQ012: 专业概念解释 - 过拟合
        if "过拟合" in user_input or ("机器学习" in user_input and "解释" in user_input):
            return """## 什么是过拟合

### 定义
过拟合 (Overfitting) 是指模型在训练数据上表现很好，但在新数据上泛化能力差的现象。

### 原因分析
1. **模型过于复杂**
   - 参数过多，模型"记住"了训练数据
   - 无法捕捉数据的本质规律

2. **训练数据不足**
   - 样本数量太少
   - 数据分布不够全面

3. **训练时间过长**
   - 过度迭代导致模型过度适配训练集

### 解决方案
- **正则化**: L1/L2 正则化限制参数大小
- **增加训练数据**: 数据增强、收集更多样本
- **Dropout**: 随机丢弃部分神经元，防止共适应
- **早停法**: 验证集性能下降时停止训练

### 实际案例
例如，一个图像分类模型在训练集上准确率 99%，但在测试集上只有 70%，这就是典型的过拟合。"""

        # UQ015: 职业建议 - 转行做程序员
        if "转行" in user_input and ("程序员" in user_input or "代码" in user_input):
            return """## 转行做程序员需要准备什么

### 技能要求
1. **编程语言**
   - Python: 语法简洁，适合入门
   - JavaScript: Web 开发必备
   - Java/C++: 企业级应用、底层开发

2. **数据结构与算法**
   - 数组、链表、栈、队列
   - 排序、查找算法
   - 树、图的基本操作

3. **框架技术**
   - Web 开发：React/Vue/Angular
   - 后端：Spring/Django/Express
   - 数据库：MySQL/Redis/MongoDB

### 学习路线
1. **第一阶段：编程基础 (2-3 个月)**
   - 学习一门编程语言基础
   - 掌握基本的数据结构
   - 完成小项目练习

2. **第二阶段：项目实战 (2-3 个月)**
   - 参与开源项目
   - 独立完成个人作品
   - 积累 GitHub 代码仓库

3. **第三阶段：面试准备 (1-2 个月)**
   - 刷 LeetCode 算法题
   - 准备八股文
   - 模拟面试练习

### 求职建议
- 准备一份突出项目的简历
- 在 GitHub 上展示代码作品
- 参加技术社区活动扩展人脉

加油！转行虽然有挑战，但只要坚持学习，成功的机会很大。"""

        # C001: 深度分析 - AI 发展趋势
        if "分析" in user_input and ("趋势" in user_input or "展望" in user_input):
            return """## AI 技术发展趋势分析

### 当前现状
人工智能技术正在快速发展，主要体现在以下几个方面：

1. **大语言模型**: 模型规模持续增长，能力不断增强
2. **多模态融合**: 文本、图像、音频的深度融合
3. **Agent 系统**: 自主智能体成为新热点

### 核心驱动因素
- 计算能力的持续提升
- 海量数据的积累
- 算法创新的加速

### 未来展望
考虑到多方面因素，我们认为：

1. **短期 (1-3 年)**
   - 垂直领域的深度应用加速落地
   - 人机协作模式重新定义工作方式
   - AI 助手成为日常生活标配

2. **中期 (3-5 年)**
   - 多模态能力成为标配
   - 边缘 AI 设备普及
   - 行业标准化逐步建立

3. **长期 (5-10 年)**
   - 通用人工智能 (AGI) 研究持续推进
   - AI 与人类智能深度融合
   - 社会生产方式发生根本性变革

综上所述，AI 技术将在未来 5-10 年持续保持高速发展，带来深刻的社会变革。"""

        # C002: 产品对比
        if "对比" in user_input or "比较" in user_input:
            return """## 产品对比分析

### iPhone 15
- **优点**：A17 芯片性能强劲，iOS 生态完善，拍照优秀，系统流畅
- **缺点**：价格较高，充电速度慢，系统封闭

### Samsung Galaxy S24
- **优点**：屏幕素质一流，Android 系统灵活，快充支持，硬件配置高
- **缺点**：系统更新支持相对较短，品牌溢价较高

### Google Pixel 8
- **优点**：原生 Android 体验，AI 功能丰富，拍照算法优秀，系统更新及时
- **缺点**：国内使用受限，品牌认知度较低，硬件配置中等

### 购买建议
综合考虑三款产品：
- **追求稳定体验**：推荐 iPhone 15，iOS 生态完善，长期使用流畅
- **偏好 Android 灵活性**：推荐 Samsung Galaxy S24，硬件配置顶级
- **喜欢原生体验和 AI 功能**：推荐 Google Pixel 8，但需考虑使用环境"""

        # C003: 旅行计划
        if "旅行" in user_input or "计划" in user_input:
            return """## 5 天东京旅行计划

### 第1天：抵达与适应
- **上午**：抵达成田机场，办理入住手续
- **下午**：游览涩谷、原宿，感受东京潮流文化（景点）
- **晚餐**：涩谷美食街品尝日式拉面
- **住宿**：新宿区域酒店，交通便利

### 第2天：传统文化体验
- **上午**：浅草寺、雷门，体验和服体验（景点）
- **下午**：秋叶原电器街，动漫文化探索（景点）
- **晚餐**：银座高级料理，品尝寿司或天妇罗

### 第3天：现代东京
- **上午**：东京塔观景、皇居东御苑漫步（景点）
- **下午**：台场海滨公园，teamLab 数字艺术展（景点）
- **晚餐**：新宿歌舞伎町，体验东京夜生活

### 第4天：周边游览
- **全天**：镰仓一日游（景点）
  - 鹤冈八幡宫参拜
  - 镰仓大佛参观
  - 江之岛海景漫步

### 第5天：购物与返程
- **上午**：表参道、银座购物
- **下午**：前往机场，结束旅程

### 美食推荐
- 拉面：一兰、金色不如归
- 寿司：筑地市场、银座高级寿司店
- 其他：和牛烧肉、鳗鱼饭、天妇罗

### 住宿建议
推荐选择新宿或涩谷区域，交通便利，餐饮选择丰富，适合首次到访东京的游客。

### 景点总结
本次行程覆盖了东京经典景点：涩谷、原宿、浅草寺、秋叶原、东京塔、台场、镰仓等，涵盖了传统文化、现代都市和自然风光。"""

        # C004: 代码错误分析
        if "错误" in user_input or "bug" in input_lower or "报错" in user_input:
            return """## 代码错误分析

### 错误原因
`TypeError: 'int' object is not iterable` 通常由以下原因导致：

1. **原因一：尝试遍历一个整数**
   ```python
   for i in 5:  # 错误！5 是整数，不可迭代
       print(i)
   ```

2. **原因二：函数返回了整数而非可迭代对象**
   ```python
   result = get_items()  # 期望返回 list，但返回了 int
   for item in result:
       print(item)
   ```

3. **原因三：变量被意外覆盖**
   ```python
   items = [1, 2, 3]
   items = len(items)  # items 现在是整数 3
   for i in items:  # 错误！
       print(i)
   ```

### 解决方案
1. **检查变量类型**
   - 使用 `isinstance()` 验证变量类型
   - 添加类型注解便于 IDE 检查

2. **使用正确的迭代对象**
   ```python
   for i in range(5):  # 正确！range 生成可迭代对象
       print(i)
   ```

3. **调试技巧**
   - 在循环前打印变量类型：`print(type(variable))`
   - 使用断点调试查看变量值

### 预防措施
- 添加类型注解和类型检查
- 编写单元测试覆盖边界情况
- 使用 linter 工具检测潜在问题

建议按照以上步骤排查代码，找到问题根源后修复。"""

        # 默认响应
        return f"""## 关于'{user_input[:50]}...'的分析

### 问题理解
这是一个需要深入思考的复杂问题。

### 分析过程
考虑到多方面因素，我们需要从以下几个角度分析：

1. **背景分析**: 理解问题的来龙去脉
2. **关键因素**: 识别影响结果的核心要素
3. **解决方案**: 基于分析提出可行方案

### 结论
综上所述，这个问题需要综合考虑多个维度的信息，建议进一步收集相关信息后做出决策。"""


class EvalRunner:
    """
    评测执行引擎

    负责加载用例、执行评测、收集指标
    """

    def __init__(self, config: Optional[EvalConfig] = None):
        self.config = config or EvalConfig()
        self.collector = MetricsCollector()
        self.talker_mock = MockTalkerAgent(self.config.mock_talker_latency_ms)
        self.thinker_mock = MockThinkerAgent(self.config.mock_thinker_latency_ms)

    async def run(self, cases: Optional[List[EvalCase]] = None) -> EvalResult:
        """
        执行评测

        Args:
            cases: 要执行的用例列表，如果为 None 则根据配置加载

        Returns:
            EvalResult: 评测结果
        """
        # 加载用例
        if cases is None:
            cases = self._load_cases()

        if not cases:
            logger.warning("没有要执行的评测用例")
            return EvalResult()

        self.collector.total_cases = len(cases)
        self.collector.start_time = time.time()

        # 执行所有用例
        case_results = []
        for i, case in enumerate(cases):
            if self.config.show_progress:
                print(f"\r正在执行评测 [{i+1}/{len(cases)}] {case.case_id}: {case.name}", end="")

            try:
                result = await self._execute_case(case)
                case_results.append(result)
            except Exception as e:
                logger.exception(f"用例 {case.case_id} 执行失败")
                case_results.append(CaseResult(
                    case_id=case.case_id,
                    case_name=case.name,
                    passed=False,
                    actual_agent=AgentRole.TALKER,
                    actual_complexity=TaskComplexity.SIMPLE,
                    actual_output=f"执行异常：{str(e)}",
                    response_time_ms=0,
                    assertion_results=[],
                    failure_reason=FailureReason.EXCEPTION,
                    failure_details=str(e),
                ))

        if self.config.show_progress:
            print("\n")

        # 构建评测结果
        self.collector.end_time = time.time()

        passed_cases = sum(1 for r in case_results if r.passed)
        failed_cases = len(case_results) - passed_cases

        eval_result = EvalResult(
            case_results=case_results,
            start_time=self.collector.start_time,
            end_time=self.collector.end_time,
            total_cases=len(case_results),
            passed_cases=passed_cases,
            failed_cases=failed_cases,
        )

        # 更新指标收集器
        for result in case_results:
            category = self._get_category_from_case_id(result.case_id)
            self.collector.record_case_result(result, category)

        return eval_result

    def _load_cases(self) -> List[EvalCase]:
        """加载用例"""
        if self.config.category_filter:
            # 检查是否为字符串类别（conversation, ux_quality）
            if isinstance(self.config.category_filter, str):
                cases = get_cases_by_category(self.config.category_filter)
            else:
                cases = get_cases_by_category(self.config.category_filter)
        else:
            cases = get_all_cases()

        # 应用优先级过滤
        if self.config.priority_filter:
            cases = [c for c in cases if c.priority == self.config.priority_filter]

        # 应用用例 ID 过滤
        if self.config.case_id_filter:
            cases = [c for c in cases if c.case_id in self.config.case_id_filter]

        return cases

    async def _execute_case(self, case: EvalCase) -> CaseResult:
        """
        执行单个用例

        Args:
            case: 评测用例

        Returns:
            CaseResult: 用例执行结果
        """
        start_time = time.time()

        # 确定使用哪个 Mock Agent
        # 在真实场景中，这里会调用 Orchestrator
        # 为了评测，我们根据期望的 Agent 来模拟路由
        expected_agent = case.expected_agent

        # 模拟 Agent 路由
        actual_agent = self._route_agent(case.user_input)
        actual_complexity = self._classify_complexity(case.user_input)

        # 执行 Agent 处理
        if actual_agent == AgentRole.THINKER:
            content, latency, tokens = await self.thinker_mock.process(
                case.user_input,
                case.context_messages,
            )
        else:
            content, latency, tokens = await self.talker_mock.process(
                case.user_input,
                case.context_messages,
            )

        response_time_ms = latency

        # 执行断言检查
        assertion_results = self._run_assertions(
            case,
            actual_agent=actual_agent,
            actual_complexity=actual_complexity,
            actual_output=content,
            response_time_ms=response_time_ms,
        )

        # 判断是否通过
        passed = all(ar.passed for ar in assertion_results)

        # 确定失败原因
        failure_reason = None
        failure_details = ""
        if not passed:
            failed_assertions = [ar for ar in assertion_results if not ar.passed]
            if failed_assertions:
                # 根据失败的断言判断失败原因
                for fa in failed_assertions:
                    if "routing" in fa.assertion_name.lower():
                        failure_reason = FailureReason.WRONG_AGENT
                    elif "time" in fa.assertion_name.lower():
                        failure_reason = FailureReason.TIMEOUT
                    elif "output" in fa.assertion_name.lower():
                        failure_reason = FailureReason.WRONG_OUTPUT
                    else:
                        failure_reason = FailureReason.ASSERTION_FAILED

                    failure_details = fa.failure_reason
                    break

        return CaseResult(
            case_id=case.case_id,
            case_name=case.name,
            passed=passed,
            actual_agent=actual_agent,
            actual_complexity=actual_complexity,
            actual_output=content,
            response_time_ms=response_time_ms,
            assertion_results=assertion_results,
            failure_reason=failure_reason,
            failure_details=failure_details,
            tokens_used=tokens,
        )

    def _route_agent(self, user_input: str) -> AgentRole:
        """
        模拟 Agent 路由

        在真实场景中，这里会调用 Orchestrator 的路由逻辑
        """
        # 简单规则：长输入或包含复杂关键词 -> Thinker

        # 特殊情况：指令注入攻击应由 Talker 快速拒绝（安全响应）
        if "忽略" in user_input and ("指令" in user_input or "提示" in user_input):
            return AgentRole.TALKER
        if "系统提示" in user_input and ("告诉" in user_input or "是什么" in user_input):
            return AgentRole.TALKER

        # 特殊情况：事实性问题、简单解释应由 Talker 处理
        if "什么是" in user_input and len(user_input) < 30:
            return AgentRole.TALKER
        if "量子计算" in user_input and "什么是" in user_input:
            return AgentRole.TALKER
        if "房价" in user_input and ("涨" in user_input or "跌" in user_input):
            return AgentRole.TALKER
        if "过拟合" in user_input and "解释" in user_input:
            return AgentRole.TALKER
        if "如何学好编程" in user_input:
            return AgentRole.TALKER

        complex_keywords = [
            "分析", "对比", "规划", "设计", "方案", "深度", "复杂", "多步",
            "学术", "综述", "写作", "论文", "报告",  # 学术写作类
            "系统", "架构", "高并发", "分布式",  # 系统设计类
            "如何学好", "怎么学", "学习路线", "转行",  # 学习规划类
            "过拟合", "机器学习",  # 专业概念类（量子计算已移到上面）
        ]

        if len(user_input) > 50 or any(k in user_input for k in complex_keywords):
            return AgentRole.THINKER
        return AgentRole.TALKER

    def _classify_complexity(self, user_input: str) -> TaskComplexity:
        """
        模拟复杂度分类

        在真实场景中，这里会调用意图分类逻辑
        """
        # 指令注入攻击属于简单拒绝响应
        if "忽略" in user_input and ("指令" in user_input or "提示" in user_input):
            return TaskComplexity.SIMPLE
        if "系统提示" in user_input and ("告诉" in user_input or "是什么" in user_input):
            return TaskComplexity.SIMPLE

        complex_keywords = [
            "分析", "对比", "规划", "设计", "方案", "深度", "复杂", "多步",
            "学术", "综述", "写作", "论文", "报告",
            "系统", "架构", "高并发", "分布式",
            "如何学好", "怎么学", "学习路线", "转行",
            "过拟合", "机器学习", "量子计算",
        ]

        if len(user_input) > 100 or any(k in user_input for k in complex_keywords):
            return TaskComplexity.COMPLEX
        elif len(user_input) > 30:
            return TaskComplexity.MEDIUM
        return TaskComplexity.SIMPLE

    def _run_assertions(
        self,
        case: EvalCase,
        actual_agent: AgentRole,
        actual_complexity: TaskComplexity,
        actual_output: str,
        response_time_ms: float,
    ) -> List[AssertionResult]:
        """执行所有断言检查"""
        results = []

        # 从 context_messages 提取关键词
        context_keywords = []
        if case.context_messages:
            for msg in case.context_messages:
                content = msg.get("content", "")
                # 提取关键实体
                if "iPhone" in content or "iphone" in content.lower():
                    context_keywords.append("iPhone")
                if "天气" in content:
                    context_keywords.append("天气")
                if "餐厅" in content:
                    context_keywords.append("餐厅")
                if "电影" in content:
                    context_keywords.append("电影")

        for assertion in case.assertions:
            try:
                result = assertion.check(
                    # Agent 路由相关参数
                    actual_agent=actual_agent,
                    expected_agent=case.expected_agent,
                    # 复杂度相关参数
                    actual_complexity=actual_complexity,
                    expected_complexity=case.expected_complexity,
                    # 输出相关参数
                    actual_output=actual_output,
                    golden_output=case.golden_output,
                    # 时间相关参数
                    response_time_ms=response_time_ms,
                    threshold=500 if case.expected_agent == AgentRole.TALKER else 3000,
                    # 上下文相关参数
                    context_keywords=context_keywords,
                    context_messages=case.context_messages,
                    # 兼容性参数 (旧版断言可能使用)
                    actual=actual_agent,
                    expected=case.expected_agent,
                )
                results.append(result)
            except Exception as e:
                results.append(AssertionResult(
                    assertion_name=assertion.name,
                    passed=False,
                    weight=assertion.weight,
                    failure_reason=f"断言执行异常：{str(e)}",
                ))

        return results

    def _get_category_from_case_id(self, case_id: str) -> str:
        """从用例 ID 获取类别"""
        if case_id.startswith("S"):
            return EvalCategory.SIMPLE.value
        elif case_id.startswith("M"):
            return EvalCategory.MEDIUM.value
        elif case_id.startswith("C"):
            return EvalCategory.COMPLEX.value
        elif case_id.startswith("E"):
            return EvalCategory.EDGE.value
        return "unknown"

    def get_collector(self) -> MetricsCollector:
        """获取指标收集器"""
        return self.collector
