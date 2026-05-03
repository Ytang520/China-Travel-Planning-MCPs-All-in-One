"""
API Client - API客户端工具

提供HTTP请求、响应处理、错误处理等功能
"""

import requests
import json
from typing import Dict, Any, Optional
import logging


class APIClient:
    """通用API客户端类"""

    def __init__(
        self,
        base_url: str = "",
        timeout: int = 30,
        headers: Optional[Dict[str, str]] = None,
    ):
        """
        初始化API客户端

        Args:
            base_url: API基础URL
            timeout: 请求超时时间（秒）
            headers: 默认请求头
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

        # 设置默认请求头
        default_headers = {
            "Content-Type": "application/json",
            "User-Agent": "FlightTicketMCP/1.0.0",
        }
        if headers:
            default_headers.update(headers)
        self.session.headers.update(default_headers)

        # 设置日志
        self.logger = logging.getLogger(__name__)

    def _build_url(self, endpoint: str) -> str:
        """构建完整URL"""
        endpoint = endpoint.lstrip("/")
        return f"{self.base_url}/{endpoint}" if self.base_url else endpoint

    def _handle_response(self, response: requests.Response) -> Dict[str, Any]:
        """处理响应"""
        try:
            response.raise_for_status()
            return {
                "success": True,
                "data": response.json() if response.content else {},
                "status_code": response.status_code,
                "headers": dict(response.headers),
            }
        except requests.exceptions.HTTPError as e:
            self.logger.error(f"HTTP错误: {e}")
            return {
                "success": False,
                "error": str(e),
                "status_code": response.status_code,
                "data": response.text,
            }
        except requests.exceptions.JSONDecodeError as e:
            self.logger.error(f"JSON解析错误: {e}")
            return {
                "success": False,
                "error": f"JSON解析错误: {str(e)}",
                "status_code": response.status_code,
                "data": response.text,
            }

    def get(
        self, endpoint: str, params: Optional[Dict[str, Any]] = None, **kwargs
    ) -> Dict[str, Any]:
        """发送GET请求"""
        url = self._build_url(endpoint)
        try:
            response = self.session.get(
                url, params=params, timeout=self.timeout, **kwargs
            )
            return self._handle_response(response)
        except requests.exceptions.RequestException as e:
            self.logger.error(f"GET请求失败: {e}")
            return {
                "success": False,
                "error": f"请求失败: {str(e)}",
                "status_code": None,
            }

    def post(
        self, endpoint: str, data: Optional[Dict[str, Any]] = None, **kwargs
    ) -> Dict[str, Any]:
        """发送POST请求"""
        url = self._build_url(endpoint)
        try:
            json_data = json.dumps(data) if data else None
            response = self.session.post(
                url, data=json_data, timeout=self.timeout, **kwargs
            )
            return self._handle_response(response)
        except requests.exceptions.RequestException as e:
            self.logger.error(f"POST请求失败: {e}")
            return {
                "success": False,
                "error": f"请求失败: {str(e)}",
                "status_code": None,
            }

    def put(
        self, endpoint: str, data: Optional[Dict[str, Any]] = None, **kwargs
    ) -> Dict[str, Any]:
        """发送PUT请求"""
        url = self._build_url(endpoint)
        try:
            json_data = json.dumps(data) if data else None
            response = self.session.put(
                url, data=json_data, timeout=self.timeout, **kwargs
            )
            return self._handle_response(response)
        except requests.exceptions.RequestException as e:
            self.logger.error(f"PUT请求失败: {e}")
            return {
                "success": False,
                "error": f"请求失败: {str(e)}",
                "status_code": None,
            }

    def delete(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        """发送DELETE请求"""
        url = self._build_url(endpoint)
        try:
            response = self.session.delete(url, timeout=self.timeout, **kwargs)
            return self._handle_response(response)
        except requests.exceptions.RequestException as e:
            self.logger.error(f"DELETE请求失败: {e}")
            return {
                "success": False,
                "error": f"请求失败: {str(e)}",
                "status_code": None,
            }


def format_api_error(error_response: Dict[str, Any]) -> str:
    """
    格式化API错误信息

    Args:
        error_response: 错误响应

    Returns:
        str: 格式化的错误信息
    """
    if error_response.get("success", False):
        return "操作成功"

    error_msg = error_response.get("error", "未知错误")
    status_code = error_response.get("status_code")

    if status_code:
        return f"API错误 ({status_code}): {error_msg}"
    else:
        return f"请求错误: {error_msg}"
