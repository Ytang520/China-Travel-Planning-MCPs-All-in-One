# 与已有方案的差异

下面是本项目和若干已有出行方案之间的差异，以及不采用飞猪 API 的原因。差异写的是对方实际做法和接入中遇到的情况。

## 和其他已有方案之间的差异

| 对比对象 | 差异分析 | link |
| --- | --- | --- |
| [codex-china-travel-suite](https://github.com/DrivingGodJ/codex-china-travel-suite) | 1. 借助飞猪和美团已有的 API 接口处理查询。2. 美团 API 目前无法配置：通过 skillhub 下载时缺少 `.tgz` 文件，恐怕是上游文件传输错误。申请也没有成功，身份信息显示错误。 | https://github.com/DrivingGodJ/codex-china-travel-suite |
| [Go-Home](https://github.com/huanchong-99/Go-Home) | 1. 更接近路径规划：先取得已有机票和火车票价，再据此重新规划行程。2. 支持国际航班。3. 只考虑一层中转。中转时间是固定值；若需要过夜，时间和费用也都按固定值计算。这样得到的结果相对稳健，但不够多样。4. 先最小化总费用，费用相同时才比较耗时。 | https://github.com/huanchong-99/Go-Home |
| [china-travel-assistant](https://github.com/19Chris19/china-travel-assistant) | 1. 借助飞猪和美团已有的 API 接口处理查询，并用 Variflight 和网页端做核验。2. 优先做可视化，给出形象化的路线。 | https://github.com/19Chris19/china-travel-assistant |
| [Dida-hotel-MCP-CN](https://github.com/DIDA-AI/Dida-hotel-MCP-CN) | 官方平台的酒店 MCP，通过调用该平台的酒店接口完成查询。 | https://github.com/DIDA-AI/Dida-hotel-MCP-CN |
| [trvl](https://github.com/MikkoParkkola/trvl) | 面向欧洲出行的 MCP。 | https://github.com/MikkoParkkola/trvl |

## 为什么不选择飞猪 API

### 查询航班和酒店

每次查询只返回 10 条。

- 直接对源码打补丁后，航班最多可以到 20 条，酒店只有 11 家。
- 可以把时间切到最小粒度，多次请求后再把结果聚合起来。

查询航班时，指定时间段内的航班信息不完整：

- 未指定具体航班时，部分航司（如南航、上航等）可能被忽略，多次搜索也没有返回结果。
- 指定具体航班（南航）时，接口返回 5 条，少于浏览器页面实际渲染出的 15 条。

查询酒店时：

- 按距离筛选或排序：有 `--sort distance_asc`，但没有半径筛选。接口返回经纬度，直线距离需要自行计算。
- 按价格排序：只有价格上限 `--max-price`。

### 查询火车

默认 `limit=10`。允许自由调高上限，并拿到全部返回结果。
