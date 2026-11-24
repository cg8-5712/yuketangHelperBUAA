# Changelog

## 2026-11-25 — 适配雨课堂 AI 版新版视频心跳

### 背景
雨课堂 AI 版升级了视频播放心跳机制。旧版脚本发送的 3 条 `loadeddata` 心跳不再被服务端认定为有效播放进度，导致视频进度长期卡住。本项目已按新版心跳结构重写视频进度上报逻辑。

### 修复
- 重构 `videoHelper.one_video_watcher()` 的心跳生成逻辑：
  - 不再发送 3 条重复的 `loadeddata`
  - 改为模拟真实播放器事件序列：
    - `loadstart`
    - `play`
    - `playing`
    - `heartbeat`
  - `sq` 由每轮重置改为跨轮连续递增
  - `ts` 改为每条事件独立毫秒时间戳，`heartbeat` 比播放事件晚约 5 秒
  - `cp` 每轮只推进当前增量，不再一次性加 3 倍进度
  - `tp` 按真实播放器逻辑处理：首次为 0，后续为当前播放位置
  - `sp` 从固定 `2` 改为真实值 `1`
  - `pg` 由每轮随机改为同一视频同一播放会话固定随机后缀
  - 补充新版心跳必需字段：
    - `cards_id`
    - `slide`
    - `v_url`
- 修复 `cc` 字段来源：
  - 旧版错误地使用 `video_id`
  - 现改为通过 `/mooc-api/v1/lms/learn/leaf_info/{classroom_id}/{video_id}/` 获取 `data.content_info.media.ccid`
- 修复 `d` 字段：
  - 旧版固定写死 `4976.5`
  - 现改为：
    - `et=loadstart` 时强制为 `0`
    - 其他事件使用视频真实时长
  - 新增播放直链接口支持：
    - `/api/open/audiovideo/playurl?video_id=<ccid>&provider=cc&file_type=1&is_single=0&domain=<domain>`
  - 新增 MP4 `mvhd` 解析逻辑，通过 Range 请求读取 `moov/mvhd`，解析出真实视频时长（如 `519.403`）
  - 若解析失败，回退使用 `leaf_info.media.duration / video_length`
- 修复进度卡死时的静默失败：
  - 旧逻辑只检查 HTTP 状态码
  - 新逻辑结合进度接口确认服务端是否真正写入进度
- 新增 `VideoTaskError`：
  - 视频 worker 失败时会以更清晰的错误信息终止整个任务
- 新增 `--debug` 启动选项：
  - 打印 `university_id`、`user_id`
  - 打印每个视频的 `leaf_info.media`
  - 打印解析出的 `ccid`、真实时长、`pg`
  - 打印每次心跳 payload
  - 打印心跳响应
  - 打印进度接口返回
  - 用于排查服务端静默拒收、限流或字段异常

### 已知行为
- 服务端可能返回：
  - `"message": "Partial data anomaly"`
  - `"code": 200`
  - `"data": [{"non_field_errors": ["cp 10 seconds longer"]}]`
- 该响应表示单条心跳被拒绝，但整体请求不一定失败。
- 实测使用新格式后，进度可正常推进，例如：
  - `watch_length` 从 `124.0` → `129.9`
  - `rate` 从 `23.89%` → `25.03%`

### 验证
- `python -m pytest -q tests`
- 7 项测试全部通过。
