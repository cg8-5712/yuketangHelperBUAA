# yuketangHelperBUU
雨课堂刷课脚本 refactor from [Cat1007/yuketangHelperSCUTLite](https://github.com/Cat1007/yuketangHelperSCUTLite)

20241101更新：更新多线程刷课，更新扫码快速登录

20250307更新：更新AI答题，这个仓库再也不用带Lite后缀了 xD

20250923更新：支持填空题了！

#### 说点什么：

之前也有想到伪造心跳包的方法去快速刷网课，结果上GitHub一搜发现有师兄已经实现了这个思路。

在此十分感谢@[heyblackC](https://github.com/heyblackC)，让我不用再研究包里变量含义了hhhh

以下是原脚本仓库：

https://github.com/heyblackC/yuketangHelper



#### 脚本改进：

- 修改一些域名及对应的参数，适配本科生系统
- 修复一个正则表达式匹配Bug
- 修改了一些文本提示



#### 食用方法：

1. 安装好python环境

2. 安装pip（最好换一下国内的镜像源）[参考](https://blog.csdn.net/yuzaipiaofei/article/details/80891108)

3. 克隆或下载该仓库

4. 安装vscode以及vscode的python插件，并根据提示使用pip安装所需要的包

5. 安装依赖：pip install -r requirements.txt

6. 在项目根目录创建 `config.json`，填写模型接口地址、密钥、模型名和 system prompt。接口地址填写 API 根路径，例如 `https://api.openai.com/v1`；无需修改 `openai_ask.py`。配置示例：
   ```json
   {
     "base_url": "https://api.openai.com/v1",
     "key": "你的 API Key",
     "model": "你的模型名称",
     "system_prompt": "按题型仅返回答案：填空题返回 JSON；选择题返回选项字母；判断题返回 true 或 false。"
   }
   ```
   prompt 示例：
   > 回答下面的问题,如果是填空题则按照下面的json格式返回答案，比如有2个空，则第一个空键为1，值为第一个空的答案，第二个空键为2，值为第二个空的答案。如果是选择题直接返回答案对应选项的字母,不要回复多余内容,如果不知道答案,请直接回答C,多选题回答格式是每个选项之间用一个半角逗号和一个空格分开，判断题只用返回true或false，不用回复标点符号。

7. 右上角绿色三角点击运行，运行之前先将自己的雨课堂账号和微信去进行绑定

8. 运行 `python helper_main.py`，按终端菜单依次填写域名、Cookie 文件名、登录方式、课程和是否答题。已有 Cookie 文件时默认选读取；首次使用默认扫码。二维码直接打印在终端。选择课程时，第 1 项为全部课程。

9. 选择 AI 做作业后，可在主程序中选择 Chat Completions（默认）或 Responses。选择 Responses 时，模型和接口服务需支持 `/responses`；一些兼容服务只支持 `/chat/completions`。使用 Responses 需要 `openai` Python SDK 1.73.0 或更新版本。

10. 选择题和判断题优先查询项目目录中的 `question_bank.sqlite3`，命中时显示保存的解析并跳过 AI。未命中时请求 AI；平台明确判对后才保存答案及平台提供的解析。填空题与讨论题继续每次请求 AI。删除该 SQLite 文件可重建题库，初始题目保存在 `data/question_bank_seed.json`。

答题提交前会随机等待 0.3 到 1 秒；网络超时或连接中断时最多尝试 3 次，并采用带随机抖动的指数退避。判断题可直接返回 `true` 或 `false`，提交时会自动转换为平台使用的答案列表。

视频阶段在支持动态刷新的终端固定显示四个 Worker 行，包含当前视频和进度；平台限制等待会切换为倒计时进度条。普通输出环境回退到逐条进度日志。运行中按 Ctrl+C 可停止视频线程。

代码按职责放在 `yuketang_helper/`：`platform/` 负责平台接口，`workflows/` 负责视频、作业和讨论流程，`answers/` 负责 AI、答案解析和 SQLite 题库，`decryption/` 负责字体解密。根目录的旧模块名是兼容入口。`config.json`、Cookie 文件与 `question_bank.sqlite3` 仍留在项目根目录，不需要迁移。

11. 直接爽到起飞🛫️

### 本地 WebUI 与多账号

安装 Python 依赖后运行 `python helper_main.py --webui`，浏览器访问 `http://127.0.0.1:8765`。不加 `--webui` 仍进入原命令行菜单。WebUI 前端在 `webui/` 目录由 Yarn 管理：首次开发或重新构建时执行 `cd webui`、`yarn install`、`yarn build`；开发预览可执行 `yarn dev`，接口会代理到本地 Flask 服务。构建产物存在时，Flask 优先托管 `webui/dist`；没有构建产物时使用仓库内置的零构建回退页面。

在网页中可以手动添加 Cookie，也可以点击“扫码添加”，填写学校域名后直接在页面展示二维码。扫码成功后会自动调用平台登录接口创建账号，并把该账号 Cookie 保存在项目根目录的 `.accounts/`；页面不会回显 Cookie，可单独更新或删除账号。选中多个账号即可并发启动，每账号有独立请求会话、停止信号和四个视频 worker；最多同时运行 8 个账号。单门课程按课程名称在各账号中匹配，可先点“查看课程”载入列表。WebUI 可选视频后做习题，需配置 `config.json`；讨论题需要人工确认，网页任务会跳过。

UA 池和代理池均为每行一项，按账号固定分配，新启动任务使用最新设置。代理池接受 `http://host:port`、`https://host:port`，可在 URL 中填写代理账号密码。只有真实可用的代理才会改变请求的出口 IP；留空时使用本机网络。UA 只改变请求头，不能伪装出口 IP。网页默认只监听 `127.0.0.1`，请勿将 Cookie 或带密码的代理地址分享给其他人。
