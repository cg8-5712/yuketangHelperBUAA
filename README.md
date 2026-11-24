# yuketangHelperBUAA

雨课堂刷课脚本，refactor from [Cat1007/yuketangHelperSCUTLite](https://github.com/Cat1007/yuketangHelperSCUTLite)。

## 来源

- 原始思路与脚本来自 [heyblackC/yuketangHelper](https://github.com/heyblackC/yuketangHelper)
- 本仓库基于 [Cat1007/yuketangHelperSCUTLite](https://github.com/Cat1007/yuketangHelperSCUTLite) 重构
- 感谢 [@heyblackC](https://github.com/heyblackC) 的原始实现

## 更新记录

- 2024-11-01：更新多线程刷课，更新扫码快速登录。
- 2025-03-07：更新 AI 答题，本仓库不再需要 Lite 后缀。
- 2025-09-23：支持填空题。
- 2026-11-25：适配雨课堂 AI 版新版视频心跳包，修复视频进度卡住的问题，详见 `CHANGELOG.md`。

## 使用方法

1. 安装 Python 3 与依赖：

   ```bash
   pip install -r requirements.txt
   ```

2. 克隆或下载本仓库。

3. 在项目根目录创建 `config.json`，填写 AI 接口配置。示例：

   ```json
   {
     "base_url": "https://api.openai.com/v1",
     "key": "你的 API Key",
     "model": "你的模型名称",
     "system_prompt": "按题型仅返回答案：填空题返回 JSON；选择题返回选项字母；判断题返回 true 或 false。"
   }
   ```

4. 运行主程序：

   ```bash
   python helper_main.py
   ```

5. 按终端菜单依次填写域名、Cookie 文件名、登录方式、课程和是否答题。

6. 可选 `--debug` 查看心跳包与响应：

   ```bash
   python helper_main.py --debug
   ```

7. 首次使用建议先绑定雨课堂账号和微信，再运行脚本。已有 Cookie 文件时默认读取，否则默认扫码。

## 功能说明

### 视频刷课

- 按新版雨课堂 AI 心跳包模拟真实播放事件流。
- 自动从视频信息接口获取真实 `ccid`。
- 自动从 MP4 `mvhd` 读取真实视频时长。
- 支持多 worker 并发刷课。
- 支持平台限流自动等待。
- 支持进度停滞自动报错，避免无限卡住。

### AI 答题

- 支持 Chat Completions 与 Responses 两种接口。
- 选择题、判断题优先查本地题库 `question_bank.sqlite3`。
- 命中题库时显示已保存解析并跳过 AI。
- 未命中时请求 AI，平台判对后保存答案与解析。
- 填空题与讨论题每次请求 AI，讨论题仍需人工确认。

### 本地 WebUI 与多账号

运行：

```bash
python helper_main.py --webui
```

浏览器访问 `http://127.0.0.1:8765`。

- 支持手动添加 Cookie。
- 支持扫码添加账号。
- Cookie 保存在根目录 `.accounts/`。
- 支持多账号并发，每账号独立请求会话与 4 个视频 worker。
- 最多同时运行 8 个账号。
- UA 池与代理池按账号固定分配。
- 代理支持 `http://host:port`、`https://host:port`，可带账号密码。

## 项目结构

```text
yuketang_helper/
  platform/    平台接口与登录
  workflows/   视频、作业与讨论流程
  answers/     AI 答题与题库
  decryption/  字体解密
  webui/       本地 WebUI
tools/
  legacy/      旧版独立作业脚本
tests/         测试
```

## 相关文件

- `config.json`：AI 接口配置。
- `question_bank.sqlite3`：本地题库。
- `CHANGELOG.md`：详细更新日志。

## 注意

- Cookie 与账号信息不要分享给别人。
- WebUI 默认只监听 `127.0.0.1`。
- AI 配置的 `base_url` 需要填 API 根路径，例如 `https://api.openai.com/v1`。
