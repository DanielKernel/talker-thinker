"""
天气查询Skill示例
"""
import os
from typing import Any, Dict, Optional

import aiohttp

from skills.base import Skill, SkillResult


class WeatherSkill(Skill):
    """
    天气查询Skill
    """

    @property
    def name(self) -> str:
        return "get_weather"

    @property
    def description(self) -> str:
        return "查询指定地点和日期的天气情况"

    def _get_param_descriptions(self) -> list:
        return [
            ("location", "string", "城市名称，如'北京'、'上海'"),
            ("date", "string", "日期：今天/明天/后天 或 YYYY-MM-DD格式"),
        ]

    async def execute(
        self,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> SkillResult:
        self._start_timer()

        location = params.get("location")
        date = params.get("date", "今天")

        try:
            # 调用天气API（这里使用模拟数据）
            weather_data = await self._get_weather_data(location, date)

            # 格式化输出
            formatted = self._format_weather(weather_data)

            return self._create_success_result(
                data=weather_data,
                formatted=formatted,
                metadata={"location": location, "date": date},
            )

        except Exception as e:
            return self._create_error_result(str(e))

    async def _get_weather_data(
        self,
        location: str,
        date: str,
    ) -> Dict[str, Any]:
        """获取天气数据"""
        # 模拟数据（实际项目中应该调用真实的天气API）
        # weather_api_key = os.getenv("WEATHER_API_KEY")

        # 模拟天气数据
        mock_data = {
            "北京": {
                "今天": {"condition": "晴", "temp_min": 18, "temp_max": 28, "humidity": 45, "wind": "东南风3级"},
                "明天": {"condition": "多云", "temp_min": 16, "temp_max": 25, "humidity": 55, "wind": "东风2级"},
            },
            "上海": {
                "今天": {"condition": "小雨", "temp_min": 20, "temp_max": 26, "humidity": 80, "wind": "南风2级"},
                "明天": {"condition": "阴", "temp_min": 19, "temp_max": 24, "humidity": 75, "wind": "东风3级"},
            },
            "深圳": {
                "今天": {"condition": "晴", "temp_min": 25, "temp_max": 32, "humidity": 70, "wind": "西南风2级"},
                "明天": {"condition": "雷阵雨", "temp_min": 24, "temp_max": 30, "humidity": 85, "wind": "南风3级"},
            },
        }

        # 尝试获取数据
        if location in mock_data and date in mock_data[location]:
            data = mock_data[location][date]
        else:
            # 默认数据
            data = {"condition": "晴", "temp_min": 20, "temp_max": 28, "humidity": 50, "wind": "微风"}

        return {
            "location": location,
            "date": date,
            **data,
        }

    def _format_weather(self, data: Dict[str, Any]) -> str:
        """格式化天气输出"""
        return (
            f"{data['location']}{data['date']}天气：{data['condition']}，"
            f"气温{data['temp_min']}-{data['temp_max']}℃，"
            f"湿度{data['humidity']}%，{data['wind']}"
        )
