"""
JSON 报告生成器

导出评测结果为 JSON 格式
"""
import json
import time
from pathlib import Path
from typing import Dict, Any, Optional

from ..core.types import EvalResult


class JSONReporter:
    """
    JSON 报告生成器

    将评测结果导出为 JSON 格式
    """

    def __init__(self, indent: int = 2):
        """
        初始化报告生成器

        Args:
            indent: JSON 缩进空格数
        """
        self.indent = indent

    def generate(self, eval_result: EvalResult) -> str:
        """
        生成 JSON 报告

        Args:
            eval_result: 评测结果

        Returns:
            str: JSON 格式的报告
        """
        return json.dumps(eval_result.to_dict(), indent=self.indent, ensure_ascii=False)

    def export(
        self,
        eval_result: EvalResult,
        file_path: Optional[str] = None,
    ) -> str:
        """
        导出 JSON 报告到文件

        Args:
            eval_result: 评测结果
            file_path: 输出文件路径，如果为 None 则自动生成

        Returns:
            str: 输出文件路径
        """
        if file_path is None:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            file_path = f"evals/results/eval_result_{timestamp}.json"

        # 确保目录存在
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        # 写入文件
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.generate(eval_result))

        return str(file_path)

    def to_dict(self, eval_result: EvalResult) -> Dict[str, Any]:
        """
        转换为字典

        Args:
            eval_result: 评测结果

        Returns:
            Dict: 字典格式的报告
        """
        return eval_result.to_dict()
