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

from fastmcp import FastMCP  # noqa: E402

from .tools import hotel_login_tools, hotel_search_tools  # noqa: E402

mcp = FastMCP("Hotel Ticket Server")


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
        city: str,
        checkin: str,
        checkout: str,
        location: str = None,
        adults: int = 2,
        children: int = 0,
        rooms: int = 1,
        price_min: int = None,
        price_max: int = None,
        star_min: int = None,
        star_max: int = None,
        min_score: float = None,
        room_type: str = None,
        accommodation_type: str = None,
        breakfast: str = None,
        sort: str = "smart",
        limit: int = 20,
    ):
        """携程酒店搜索 - 按城市、入住/退房日期等条件抓取酒店列表。

        ⚠ 风险提示：本工具通过浏览器模拟真人浏览并抓取需要登录态的携程酒店数据，
        存在账号被封禁风险。使用前必须在安装时同意风险条款（HOTEL_MCP_CONSENT=yes）。

        参数：
        city: 城市名（如"武汉"）；checkin/checkout: YYYY-MM-DD；
        location: 地标/商圈（如"武汉站-东出口"）；adults/children/rooms: 人数与房间数；
        price_min/price_max: 价格区间；star_min/star_max: 星级区间；
        min_score: 最低评分（客户端过滤）；room_type: 双床房/大床房等；
        accommodation_type: 酒店/民宿/青年旅馆；breakfast: 无/单早/双早；
        sort: smart(默认智能排序)/price_asc(低价优先)/distance(直线距离)/score_desc(好评优先)；
        limit: 返回数量（默认20，最大50）。
        搜索之间自动等待随机 30s~5min 间隔（防封禁）。
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
    def ctripHotelLogin():
        """携程酒店登录助手 - 打开可见浏览器窗口，等待用户手动完成携程登录，
        然后把登录 cookie 保存到本地文件供后续搜索复用（最多等待 5 分钟）。

        ⚠ 仅在搜索返回 LOGIN_REQUIRED 错误时调用；使用本工具即表示同意风险条款。
        """
        return hotel_login_tools.ctripHotelLogin()

    logging.getLogger(__name__).info(
        "MCP工具注册完成 - 已注册工具: searchHotels, ctripHotelLogin"
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
            mcp.run()
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
        run_server()
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
