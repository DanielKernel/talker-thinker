"""
计算Skill示例
"""
import ast
import operator
from typing import Any, Dict, Optional

from skills.base import Skill, SkillResult


class CalculatorSkill(Skill):
    """
    计算器Skill
    支持基本数学运算
    """

    @property
    def name(self) -> str:
        return "calculate"

    @property
    def description(self) -> str:
        return "执行数学计算"

    def _get_param_descriptions(self) -> list:
        return [
            ("expression", "string", "数学表达式，如'2+3*4'"),
        ]

    # 支持的运算符
    OPERATORS = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Pow: operator.pow,
        ast.Mod: operator.mod,
        ast.USub: operator.neg,
    }

    async def execute(
        self,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> SkillResult:
        self._start_timer()

        expression = params.get("expression", "").strip()

        try:
            # 安全地计算表达式
            result = self._safe_eval(expression)

            return self._create_success_result(
                data={"expression": expression, "result": result},
                formatted=f"{expression} = {result}",
                metadata={"expression": expression},
            )

        except Exception as e:
            return self._create_error_result(f"计算错误: {str(e)}")

    def _safe_eval(self, expression: str) -> float:
        """安全地计算表达式"""
        try:
            tree = ast.parse(expression, mode="eval")
            return self._eval_node(tree.body)
        except Exception as e:
            raise ValueError(f"无法解析表达式: {expression}")

    def _eval_node(self, node) -> float:
        """递归计算AST节点"""
        if isinstance(node, ast.Constant):
            return float(node.value)

        elif isinstance(node, ast.BinOp):
            left = self._eval_node(node.left)
            right = self._eval_node(node.right)
            op_type = type(node.op)

            if op_type in self.OPERATORS:
                return self.OPERATORS[op_type](left, right)
            else:
                raise ValueError(f"不支持的运算符: {op_type}")

        elif isinstance(node, ast.UnaryOp):
            operand = self._eval_node(node.operand)
            op_type = type(node.op)

            if op_type in self.OPERATORS:
                return self.OPERATORS[op_type](operand)
            else:
                raise ValueError(f"不支持的一元运算符: {op_type}")

        else:
            raise ValueError(f"不支持的表达式类型: {type(node)}")


class UnitConverterSkill(Skill):
    """
    单位转换Skill
    """

    @property
    def name(self) -> str:
        return "convert_unit"

    @property
    def description(self) -> str:
        return "转换单位"

    def _get_param_descriptions(self) -> list:
        return [
            ("value", "number", "要转换的值"),
            ("from_unit", "string", "原单位"),
            ("to_unit", "string", "目标单位"),
        ]

    # 转换因子（到基本单位）
    LENGTH_UNITS = {
        "米": 1, "m": 1,
        "千米": 1000, "km": 1000,
        "厘米": 0.01, "cm": 0.01,
        "毫米": 0.001, "mm": 0.001,
        "英里": 1609.344, "mile": 1609.344,
        "英尺": 0.3048, "ft": 0.3048,
        "英寸": 0.0254, "in": 0.0254,
    }

    WEIGHT_UNITS = {
        "千克": 1, "kg": 1,
        "克": 0.001, "g": 0.001,
        "毫克": 0.000001, "mg": 0.000001,
        "磅": 0.453592, "lb": 0.453592,
        "盎司": 0.0283495, "oz": 0.0283495,
    }

    TEMPERATURE_OFFSETS = {
        "摄氏度": 0, "°C": 0,
        "华氏度": 32, "°F": 32,
    }

    async def execute(
        self,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> SkillResult:
        self._start_timer()

        value = params.get("value")
        from_unit = params.get("from_unit", "")
        to_unit = params.get("to_unit", "")

        try:
            result = self._convert(value, from_unit, to_unit)

            return self._create_success_result(
                data={
                    "original_value": value,
                    "original_unit": from_unit,
                    "converted_value": result,
                    "converted_unit": to_unit,
                },
                formatted=f"{value} {from_unit} = {result:.4f} {to_unit}",
                metadata={"from_unit": from_unit, "to_unit": to_unit},
            )

        except Exception as e:
            return self._create_error_result(str(e))

    def _convert(self, value: float, from_unit: str, to_unit: str) -> float:
        """执行转换"""
        from_unit = from_unit.strip()
        to_unit = to_unit.strip()

        # 温度转换（特殊处理）
        if from_unit in self.TEMPERATURE_OFFSETS and to_unit in self.TEMPERATURE_OFFSETS:
            if from_unit == to_unit:
                return value
            # 摄氏转华氏
            if from_unit in ("摄氏度", "°C") and to_unit in ("华氏度", "°F"):
                return value * 9 / 5 + 32
            # 华氏转摄氏
            if from_unit in ("华氏度", "°F") and to_unit in ("摄氏度", "°C"):
                return (value - 32) * 5 / 9

        # 长度转换
        if from_unit in self.LENGTH_UNITS and to_unit in self.LENGTH_UNITS:
            base_value = value * self.LENGTH_UNITS[from_unit]
            return base_value / self.LENGTH_UNITS[to_unit]

        # 重量转换
        if from_unit in self.WEIGHT_UNITS and to_unit in self.WEIGHT_UNITS:
            base_value = value * self.WEIGHT_UNITS[from_unit]
            return base_value / self.WEIGHT_UNITS[to_unit]

        raise ValueError(f"不支持的单位转换: {from_unit} -> {to_unit}")
