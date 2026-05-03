"""
Weather Tools - 天气查询工具

提供根据经纬度查询天气信息的功能，使用Open-Meteo API
"""

import requests
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

# 初始化日志器
logger = logging.getLogger(__name__)

# 导入地理编码库
try:
    from geopy.geocoders import Nominatim

    GEOPY_AVAILABLE = True
    # 创建地理编码器实例
    geolocator = Nominatim(user_agent="FlightTicketMCP_WeatherApp")
except ImportError:
    GEOPY_AVAILABLE = False
    geolocator = None
    logger.warning("geopy库未安装，将仅支持预设城市的天气查询")


def getWeatherByLocation(
    latitude: float, longitude: float, start_date: str = None, end_date: str = None
) -> Dict[str, Any]:
    """
    根据经纬度查询天气信息

    Args:
        latitude: 纬度
        longitude: 经度
        start_date: 开始日期 (YYYY-MM-DD格式)，可选，默认为前一天
        end_date: 结束日期 (YYYY-MM-DD格式)，可选，默认为后一天

    Returns:
        包含天气查询结果的字典
    """
    logger.info(
        f"开始查询天气信息: 纬度={latitude}, 经度={longitude}, 开始日期={start_date}, 结束日期={end_date}"
    )

    try:
        # 验证输入参数
        if latitude is None or longitude is None:
            logger.warning("经纬度参数不能为空")
            return {
                "status": "error",
                "message": "经纬度参数不能为空",
                "error_code": "INVALID_PARAMS",
                "data_source": "open_meteo_api",
            }

        # 验证经纬度范围
        if not (-90 <= latitude <= 90):
            logger.warning(f"纬度超出有效范围: {latitude}")
            return {
                "status": "error",
                "message": f"纬度必须在-90到90之间，当前值: {latitude}",
                "error_code": "INVALID_LATITUDE",
                "data_source": "open_meteo_api",
            }

        if not (-180 <= longitude <= 180):
            logger.warning(f"经度超出有效范围: {longitude}")
            return {
                "status": "error",
                "message": f"经度必须在-180到180之间，当前值: {longitude}",
                "error_code": "INVALID_LONGITUDE",
                "data_source": "open_meteo_api",
            }

        # 设置默认日期（今天和明天，共两天）
        now = datetime.now()
        if start_date is None:
            # 默认从今天开始
            start_date = now.strftime("%Y-%m-%d")

        if end_date is None:
            # 默认到明天结束
            default_end = now + timedelta(days=1)
            end_date = default_end.strftime("%Y-%m-%d")

        # 验证日期格式
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            logger.debug(f"日期解析成功: {start_dt} 到 {end_dt}")
        except ValueError as ve:
            logger.warning(
                f"日期格式错误: start_date={start_date}, end_date={end_date}"
            )
            return {
                "status": "error",
                "message": "日期格式不正确，请使用YYYY-MM-DD格式",
                "error_code": "INVALID_DATE_FORMAT",
                "data_source": "open_meteo_api",
            }

        # 验证日期范围
        if start_dt > end_dt:
            logger.warning(f"开始日期晚于结束日期: {start_date} > {end_date}")
            return {
                "status": "error",
                "message": "开始日期不能晚于结束日期",
                "error_code": "INVALID_DATE_RANGE",
                "data_source": "open_meteo_api",
            }

        # 构建API请求URL
        base_url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": "temperature_2m",
            "models": "cma_grapes_global",
            "timezone": "Asia/Shanghai",
            "start_date": start_date,
            "end_date": end_date,
        }

        logger.info(f"请求Open-Meteo API: {base_url}")
        logger.debug(f"请求参数: {params}")

        try:
            # 发送HTTP请求
            response = requests.get(base_url, params=params, timeout=30)
            response.raise_for_status()

            weather_data = response.json()
            logger.debug(
                f"API响应数据: {json.dumps(weather_data, indent=2, ensure_ascii=False)}"
            )

            # 调试：检查温度数据质量
            if "hourly" in weather_data and "temperature_2m" in weather_data["hourly"]:
                temps = weather_data["hourly"]["temperature_2m"]
                none_count = sum(1 for temp in temps if temp is None)
                valid_count = len(temps) - none_count
                logger.debug(
                    f"温度数据质量检查: 总数据点={len(temps)}, 有效数据点={valid_count}, None值数量={none_count}"
                )

            # 格式化结果
            result = {
                "status": "success",
                "latitude": weather_data.get("latitude"),
                "longitude": weather_data.get("longitude"),
                "timezone": weather_data.get("timezone"),
                "timezone_abbreviation": weather_data.get("timezone_abbreviation"),
                "elevation": weather_data.get("elevation"),
                "start_date": start_date,
                "end_date": end_date,
                "hourly_units": weather_data.get("hourly_units", {}),
                "hourly_data": weather_data.get("hourly", {}),
                "formatted_output": _format_weather_result(
                    weather_data, latitude, longitude, start_date, end_date
                ),
                "query_time": datetime.now().isoformat(),
                "data_source": "open_meteo_api",
            }

            # 添加温度统计信息
            if "hourly" in weather_data and "temperature_2m" in weather_data["hourly"]:
                temperatures = weather_data["hourly"]["temperature_2m"]
                if temperatures:
                    # 过滤掉None值
                    valid_temperatures = [
                        temp for temp in temperatures if temp is not None
                    ]
                    if valid_temperatures:
                        result["temperature_statistics"] = {
                            "min_temperature": min(valid_temperatures),
                            "max_temperature": max(valid_temperatures),
                            "avg_temperature": round(
                                sum(valid_temperatures) / len(valid_temperatures), 1
                            ),
                            "data_points": len(temperatures),
                            "valid_data_points": len(valid_temperatures),
                        }
                    else:
                        logger.warning("所有温度数据都为None值")
                        result["temperature_statistics"] = {
                            "error": "无有效温度数据",
                            "data_points": len(temperatures),
                            "valid_data_points": 0,
                        }

            logger.info(f"天气查询成功: 纬度={latitude}, 经度={longitude}")
            return result

        except requests.exceptions.RequestException as re:
            logger.error(f"API请求失败: {str(re)}", exc_info=True)
            return {
                "status": "error",
                "message": f"天气API请求失败: {str(re)}",
                "error_code": "API_REQUEST_FAILED",
                "data_source": "open_meteo_api",
            }

        except json.JSONDecodeError as je:
            logger.error(f"API响应解析失败: {str(je)}", exc_info=True)
            return {
                "status": "error",
                "message": f"天气API响应格式错误: {str(je)}",
                "error_code": "API_RESPONSE_INVALID",
                "data_source": "open_meteo_api",
            }

    except Exception as e:
        logger.error(f"查询天气信息失败: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "message": f"查询天气信息失败: {str(e)}",
            "error_code": "WEATHER_QUERY_FAILED",
            "data_source": "open_meteo_api",
        }


def _format_weather_result(
    weather_data: Dict[str, Any],
    latitude: float,
    longitude: float,
    start_date: str,
    end_date: str,
) -> str:
    """
    格式化天气查询结果

    Args:
        weather_data: API返回的天气数据
        latitude: 纬度
        longitude: 经度
        start_date: 开始日期
        end_date: 结束日期

    Returns:
        格式化后的字符串
    """
    try:
        output = []
        output.append("🌤️ 天气查询结果")
        output.append(
            f"📍 位置: 纬度 {weather_data.get('latitude', latitude)}, 经度 {weather_data.get('longitude', longitude)}"
        )
        output.append(f"📅 查询时间段: {start_date} 到 {end_date}")
        output.append(
            f"🌍 时区: {weather_data.get('timezone', 'N/A')} ({weather_data.get('timezone_abbreviation', 'N/A')})"
        )

        if "elevation" in weather_data:
            output.append(f"⛰️ 海拔: {weather_data['elevation']}米")

        output.append("")

        # 处理小时温度数据
        if "hourly" in weather_data and "temperature_2m" in weather_data["hourly"]:
            times = weather_data["hourly"].get("time", [])
            temperatures = weather_data["hourly"].get("temperature_2m", [])

            if times and temperatures:
                # 按日期分组显示
                daily_data = {}
                for time_str, temp in zip(times, temperatures):
                    try:
                        dt = datetime.fromisoformat(time_str.replace("T", " "))
                        date_key = dt.strftime("%Y-%m-%d")
                        hour = dt.strftime("%H:%M")

                        if date_key not in daily_data:
                            daily_data[date_key] = []
                        daily_data[date_key].append((hour, temp))
                    except:
                        continue

                # 显示每日数据
                for date, hourly_temps in daily_data.items():
                    output.append(f"📆 {date}")

                    # 计算当日统计
                    day_temps = [temp for _, temp in hourly_temps if temp is not None]
                    if day_temps:
                        min_temp = min(day_temps)
                        max_temp = max(day_temps)
                        avg_temp = sum(day_temps) / len(day_temps)
                        output.append(
                            f"    🌡️ 温度范围: {min_temp:.1f}°C ~ {max_temp:.1f}°C (平均: {avg_temp:.1f}°C)"
                        )
                    else:
                        output.append(f"    ❌ 当日无有效温度数据")

                    # 显示部分小时数据（每4小时一次）
                    sample_data = hourly_temps[::4]  # 每4小时取一个样本
                    for hour, temp in sample_data[:6]:  # 最多显示6个时间点
                        if temp is not None:
                            output.append(f"    {hour}: {temp}°C")
                        else:
                            output.append(f"    {hour}: 无数据")

                    output.append("")

                # 整体统计
                all_temps = [temp for temp in temperatures if temp is not None]
                if all_temps:
                    output.append("📊 整体统计:")
                    output.append(f"    最低温度: {min(all_temps):.1f}°C")
                    output.append(f"    最高温度: {max(all_temps):.1f}°C")
                    output.append(
                        f"    平均温度: {sum(all_temps) / len(all_temps):.1f}°C"
                    )
                    output.append(f"    数据点数: {len(times)}个")
        else:
            output.append("❌ 未获取到温度数据")

        return "\n".join(output)

    except Exception as e:
        logger.error(f"格式化天气结果失败: {str(e)}", exc_info=True)
        return f"天气数据格式化失败: {str(e)}"


# 主要城市经纬度数据
CITY_COORDINATES = {
    "北京": {"latitude": 39.9042, "longitude": 116.4074, "name": "北京"},
    "上海": {"latitude": 31.2304, "longitude": 121.4737, "name": "上海"},
    "广州": {"latitude": 23.1291, "longitude": 113.2644, "name": "广州"},
    "深圳": {"latitude": 22.5431, "longitude": 114.0579, "name": "深圳"},
    "成都": {"latitude": 30.5728, "longitude": 104.0668, "name": "成都"},
    "武汉": {"latitude": 30.5928, "longitude": 114.3055, "name": "武汉"},
    "西安": {"latitude": 34.3416, "longitude": 108.9398, "name": "西安"},
    "杭州": {"latitude": 30.2741, "longitude": 120.1551, "name": "杭州"},
    "重庆": {"latitude": 29.5647, "longitude": 106.5507, "name": "重庆"},
    "天津": {"latitude": 39.3434, "longitude": 117.3616, "name": "天津"},
    "南京": {"latitude": 32.0603, "longitude": 118.7969, "name": "南京"},
    "青岛": {"latitude": 36.0986, "longitude": 120.3719, "name": "青岛"},
    "大连": {"latitude": 38.9140, "longitude": 121.6147, "name": "大连"},
    "宁波": {"latitude": 29.8683, "longitude": 121.5440, "name": "宁波"},
    "厦门": {"latitude": 24.4798, "longitude": 118.0819, "name": "厦门"},
    "福州": {"latitude": 26.0745, "longitude": 119.2965, "name": "福州"},
    "无锡": {"latitude": 31.4912, "longitude": 120.3124, "name": "无锡"},
    "合肥": {"latitude": 31.8206, "longitude": 117.2272, "name": "合肥"},
    "昆明": {"latitude": 25.0389, "longitude": 102.7183, "name": "昆明"},
    "哈尔滨": {"latitude": 45.8038, "longitude": 126.5349, "name": "哈尔滨"},
    "沈阳": {"latitude": 41.8057, "longitude": 123.4315, "name": "沈阳"},
    "长春": {"latitude": 43.8171, "longitude": 125.3235, "name": "长春"},
    "石家庄": {"latitude": 38.0428, "longitude": 114.5149, "name": "石家庄"},
    "长沙": {"latitude": 28.2282, "longitude": 112.9388, "name": "长沙"},
    "郑州": {"latitude": 34.7466, "longitude": 113.6254, "name": "郑州"},
    "南昌": {"latitude": 28.6820, "longitude": 115.8581, "name": "南昌"},
    "贵阳": {"latitude": 26.6470, "longitude": 106.6302, "name": "贵阳"},
    "兰州": {"latitude": 36.0611, "longitude": 103.8343, "name": "兰州"},
    "海口": {"latitude": 20.0458, "longitude": 110.3417, "name": "海口"},
    "三亚": {"latitude": 18.2528, "longitude": 109.5122, "name": "三亚"},
    "银川": {"latitude": 38.4872, "longitude": 106.2309, "name": "银川"},
    "西宁": {"latitude": 36.6171, "longitude": 101.7782, "name": "西宁"},
    "呼和浩特": {"latitude": 40.8414, "longitude": 111.7519, "name": "呼和浩特"},
    "乌鲁木齐": {"latitude": 43.8256, "longitude": 87.6168, "name": "乌鲁木齐"},
    "拉萨": {"latitude": 29.6625, "longitude": 91.1112, "name": "拉萨"},
    "南宁": {"latitude": 22.8170, "longitude": 108.3669, "name": "南宁"},
    # 港澳台
    "香港": {"latitude": 22.3193, "longitude": 114.1694, "name": "香港"},
    "澳门": {"latitude": 22.1987, "longitude": 113.5439, "name": "澳门"},
    "台北": {"latitude": 25.0330, "longitude": 121.5654, "name": "台北"},
}


def getWeatherByCity(
    city_name: str, start_date: str = None, end_date: str = None
) -> Dict[str, Any]:
    """
    根据城市名查询天气信息

    Args:
        city_name: 城市名（如：武汉、北京、上海等，支持全球任意城市）
        start_date: 开始日期 (YYYY-MM-DD格式)，可选，默认为今天
        end_date: 结束日期 (YYYY-MM-DD格式)，可选，默认为明天

    Returns:
        包含天气查询结果的字典
    """
    logger.info(f"根据城市名查询天气: {city_name}")

    try:
        # 清理输入的城市名
        city_name = city_name.strip()
        city_coord = None
        city_display_name = city_name
        coordinate_source = "unknown"

        # 方法1：首先尝试从预设字典查找（更快更准确）
        search_keys = [
            city_name,
            city_name.replace("市", ""),  # 去掉"市"后缀
            city_name.replace("省", ""),  # 去掉"省"后缀
        ]

        for key in search_keys:
            if key in CITY_COORDINATES:
                city_coord = CITY_COORDINATES[key]
                city_display_name = city_coord["name"]
                coordinate_source = "preset_dict"
                logger.info(
                    f"从预设字典找到城市 '{city_name}' 的坐标: 纬度={city_coord['latitude']}, 经度={city_coord['longitude']}"
                )
                break

        # 如果预设字典中没有，尝试使用geopy进行地理编码
        if not city_coord and GEOPY_AVAILABLE and geolocator:
            try:
                logger.info(f"使用geopy查找城市 '{city_name}' 的坐标...")
                location = geolocator.geocode(city_name, timeout=10)

                if location:
                    city_coord = {
                        "latitude": location.latitude,
                        "longitude": location.longitude,
                        "name": city_name,
                    }
                    city_display_name = (
                        location.address if location.address else city_name
                    )
                    coordinate_source = "geopy"
                    logger.info(
                        f"通过geopy找到城市 '{city_name}' 的坐标: 纬度={city_coord['latitude']}, 经度={city_coord['longitude']}"
                    )
                    logger.debug(f"geopy返回的完整地址: {location.address}")
                else:
                    logger.warning(f"geopy无法找到城市 '{city_name}' 的坐标")

            except Exception as geo_e:
                logger.warning(f"geopy查询失败: {str(geo_e)}")

        # 如果两种方法都没有找到坐标
        if not city_coord:
            error_message = f"无法找到城市 '{city_name}' 的坐标信息。"
            if GEOPY_AVAILABLE:
                error_message += "请检查城市名称是否正确。"
            else:
                error_message += f"当前仅支持预设城市：不支持"

            logger.warning(error_message)
            return {
                "status": "error",
                "message": error_message,
                "error_code": "CITY_NOT_FOUND",
                "coordinate_source": coordinate_source,
                "geopy_available": GEOPY_AVAILABLE,
                "data_source": "open_meteo_api",
            }

        # 调用原有的经纬度查询函数
        result = getWeatherByLocation(
            latitude=city_coord["latitude"],
            longitude=city_coord["longitude"],
            start_date=start_date,
            end_date=end_date,
        )

        # 在结果中添加城市信息
        if result.get("status") == "success":
            result["city_name"] = city_display_name
            result["city_input"] = city_name
            result["coordinate_source"] = coordinate_source

            # 更新格式化输出，添加城市名称
            if "formatted_output" in result:
                formatted_lines = result["formatted_output"].split("\n")
                if formatted_lines:
                    # 替换第一行，添加城市名称
                    formatted_lines[0] = f"🌤️ {city_display_name}天气查询结果"
                    result["formatted_output"] = "\n".join(formatted_lines)

        return result

    except Exception as e:
        logger.error(f"根据城市名查询天气失败: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "message": f"查询城市 '{city_name}' 天气失败: {str(e)}",
            "error_code": "CITY_WEATHER_QUERY_FAILED",
            "data_source": "open_meteo_api",
        }
