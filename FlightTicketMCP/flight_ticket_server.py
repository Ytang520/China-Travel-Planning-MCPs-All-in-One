#!/usr/bin/env python3
"""
Flight Ticket MCP Server 主启动文件

这是整个项目的主入口点，用于启动航空机票MCP服务器。
"""

import sys
import os

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from flight_ticket_mcp_server import main

if __name__ == "__main__":
    main()
