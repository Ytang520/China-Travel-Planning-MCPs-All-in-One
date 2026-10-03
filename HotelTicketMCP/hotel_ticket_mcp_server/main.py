"""
Main entry point for the Hotel Ticket MCP Server.

Mirrors the FlightTicketMCP structure: transport selection, logging,
.env loading, and tool registration, but registers the hotel search and
login tools (both gated by the HOTEL_MCP_CONSENT risk-consent switch).
"""

import logging
import logging.handlers
import os
import sys
from functools import partial
print = partial(print, file=sys.stderr)

# FastMCP 2.8.1+ requires this env to be set
os.environ.setdefault("FASTMCP_LOG_LEVEL", "INFO")


def load_env_file(env_file_path=None):
    """Load environment variables from .env (cwd or package root) if present."""
    candidate_paths = []
    if env_file_path:
        candidate_paths.append(env_file_path)

    package_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidate_paths.extend(
        [
            os.path.join(os.getcwd(), ".env"),
            os.path.join(package_root, ".env"),
        ]
    )

    for candidate in candidate_paths:
        if not candidate or not os.path.exists(candidate):
            continue
        with open(candidate, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key, value = key.strip(), value.strip()
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                elif value.startswith("'") and value.endswith("'"):
                    value = value[1:-1]
                if key not in os.environ:
                    os.environ[key] = value
        return

    print("No .env file found, using system environment variables")


load_env_file()

from .utils.browser_runtime import browser_lifespan, install_shutdown_handlers, shutdown_browsers
from fastmcp import FastMCP, Context  # noqa: E402
from typing import Literal, Annotated
from pydantic import Field

from .tools import hotel_login_tools, hotel_search_tools  # noqa: E402

mcp = FastMCP("Hotel Ticket Server", lifespan=browser_lifespan)


def get_transport_config():
    config = {"transport": "stdio"}
    transport = os.getenv("MCP_TRANSPORT", "stdio").lower()
    valid = ["stdio", "sse", "http", "streamable-http"]
    if transport not in valid:
        print(f"Warning: Invalid transport '{transport}'. Falling back to 'stdio'.")
        transport = "stdio"
    config["transport"] = transport
    return config


def setup_logging():
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_file_path = os.getenv("LOG_FILE_PATH", "logs/hotel_server.log")

    log_dir = os.path.dirname(log_file_path)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir)

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level, logging.INFO))
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    root_logger.addHandler(console)

    if log_dir:
        file_handler = logging.handlers.RotatingFileHandler(
            log_file_path,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )
        root_logger.addHandler(file_handler)


def register_tools():
    @mcp.tool()
    def searchHotels(
        city: Annotated[str, Field(min_length=1, description="城市名称，例如武汉；不填写地标")],
        checkin: Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$", description="入住日期 YYYY-MM-DD，不早于今天")],
        checkout: Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$", description="退房日期 YYYY-MM-DD，晚于入住")],
        location: Annotated[str | None, Field(description="城市内的地标全名；同名时附加线路或出口，例如梨园地铁站")] = None,
        adults: Annotated[int, Field(ge=1, description="成人人数")] = 2,
        children: Annotated[int, Field(ge=0, description="儿童人数")] = 0,
        rooms: Annotated[int, Field(ge=1, description="房间数")] = 1,
        price_min: Annotated[int | None, Field(ge=0, description="每晚人民币最低价")] = None,
        price_max: Annotated[int | None, Field(ge=0, description="每晚人民币最高价")] = None,
        star_min: Annotated[int | None, Field(ge=1, le=5, description="最低星级")] = None,
        star_max: Annotated[int | None, Field(ge=1, le=5, description="最高星级")] = None,
        min_score: Annotated[float | None, Field(ge=0, le=5, description="最低评分，采集后过滤；评分未知的酒店保留并返回空评分")] = None,
        room_type: Annotated[
            Literal["大床房", "双床房", "单人床房", "三床房", "特大床房"] | None,
            Field(description="房型筛选，单选；省略或 null 表示不限"),
        ] = None,
        accommodation_type: Annotated[
            Literal["酒店", "民宿", "青年旅馆", "酒店公寓", "公寓"] | None,
            Field(description="住宿类型筛选，单选；省略或 null 表示不限"),
        ] = None,
        breakfast: Annotated[str | None, Field(description="暂不支持早餐筛选，传值会返回未应用警告")] = None,
        sort: Literal["smart", "price_asc", "distance", "score_desc"] = "smart",
        limit: Annotated[int, Field(ge=1, le=50, description="最多返回的酒店数")] = 20,
    ):
        """按城市和日期搜索携程酒店，返回实际地点与排序应用状态。
        需要登录及 HOTEL_MCP_CONSENT=yes；查询间自动等待随机 15 秒至 3 分钟。
        location 使用城市内的地点全名，distance 排序必须有 location。
        调用 get_tool_details({tool_name: "hotel_ctrip_searchHotels"}) 查看参数、示例及错误处理。
        """
        return hotel_search_tools.searchHotels(
            city=city,
            checkin=checkin,
            checkout=checkout,
            location=location,
            adults=adults,
            children=children,
            rooms=rooms,
            price_min=price_min,
            price_max=price_max,
            star_min=star_min,
            star_max=star_max,
            min_score=min_score,
            room_type=room_type,
            accommodation_type=accommodation_type,
            breakfast=breakfast,
            sort=sort,
            limit=limit,
        )

    # 下游工具名固定为 login，使网关注册名为 hotel_ctrip_login
    # （网关命名规则为 {domain}_{provider}_{toolName}）
    @mcp.tool(name="login")
    async def ctripHotelLogin(ctx: Context, user_action: Literal["open_login", "cancel"] | None = None,
                              return_url: str | None = None):
        """携程酒店登录助手 - 打开可见浏览器窗口，等待用户手动完成携程登录，
        然后把登录 cookie 保存到本地文件供后续搜索复用（默认最多等待 14 分钟，
        可用 HOTEL_MCP_LOGIN_TIMEOUT 调整；登录窗口保持打开直至登录完成或超时）。

        搜索返回 LOGIN_REQUIRED 后调用。网关将先弹出登录问题；若收到
        USER_INTERACTION_REQUIRED，必须用 AskUserQuestion 或宿主原生提问工具
        等待用户选择后传 user_action=open_login/cancel。不要在聊天中索要密码或验证码。
        return_url 使用搜索返回的官方酒店页地址；成功后以原参数重试搜索一次。
        """
        return await hotel_login_tools.login_with_progress(user_action, return_url, ctx)

    logging.getLogger(__name__).info(
        "MCP工具注册完成 - 已注册工具: searchHotels, login"
    )


def run_server():
    try:
        config = get_transport_config()
        setup_logging()
        print("Hotel Ticket MCP Server starting...")
        print(f"Transport: {config['transport']}")
        register_tools()
        print("All tools registered successfully")
        if config["transport"] == "stdio":
            mcp.run(show_banner=False)
        else:
            host = os.getenv("MCP_HOST", "127.0.0.1")
            port = int(os.getenv("MCP_PORT", "8080"))
            mcp.run(transport="http", host=host, port=port)
    except KeyboardInterrupt:
        print("\nShutting down Hotel Ticket MCP Server...")
    except Exception as e:
        print(f"Error starting server: {e}")
        sys.exit(1)


def main():
    try:
        install_shutdown_handlers()
        run_server()
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)

    finally:
        shutdown_browsers()


if __name__ == "__main__":
    main()
