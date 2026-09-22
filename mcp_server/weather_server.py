"""可选的 MCP 天气服务（stdio）。

主流程里天气是用 `services/vehicle_behavior_service.fetch_weather_note()` 直接调的，
这个 MCP 服务是给"把外部能力做成 MCP 工具"这条扩展路线准备的示范：
外部 Agent（Claude Desktop、其它 MCP 客户端）可以把它挂上去查天气。

需要先安装可选依赖：

    pip install -r requirements-mcp.txt
    python -m mcp_server.weather_server

然后在 MCP 客户端配置里指向这个命令即可。
"""

from __future__ import annotations

import os

try:  # 可选依赖，未安装时不影响主项目
    from mcp.server.fastmcp import FastMCP
except ImportError:  # pragma: no cover
    FastMCP = None

WEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"


def fetch_weather(city: str = "Beijing") -> str:
    """查询实时天气；未配置 API Key 时返回提示文本。"""

    api_key = os.getenv("OPENWEATHER_API_KEY")
    if not api_key:
        return "未配置 OPENWEATHER_API_KEY，无法查询实时天气。"

    import requests

    try:
        response = requests.get(
            WEATHER_URL,
            params={"q": city, "appid": api_key, "units": "metric", "lang": "zh_cn"},
            timeout=8,
        )
        if response.status_code != 200:
            return f"查询 {city} 天气失败（HTTP {response.status_code}）。"
        data = response.json()
        description = data.get("weather", [{}])[0].get("description", "")
        main = data.get("main", {})
        return (
            f"{city} 当前天气：{description}，气温 {main.get('temp')}℃，"
            f"体感 {main.get('feels_like')}℃，湿度 {main.get('humidity')}%。"
        )
    except Exception as exc:  # pragma: no cover - 外部服务异常
        return f"查询天气时出错：{exc}"


if FastMCP is not None:
    mcp = FastMCP("smart-auto-service-weather")

    @mcp.tool()
    def get_current_weather(city: str = "Beijing") -> str:
        """查询指定城市的当前天气，用于生成保养提醒与到店提示。"""

        return fetch_weather(city)

    def main() -> None:
        mcp.run()

else:

    def main() -> None:  # pragma: no cover
        raise SystemExit(
            "未安装 MCP 依赖。请先执行：pip install -r requirements-mcp.txt"
        )


if __name__ == "__main__":  # pragma: no cover
    main()