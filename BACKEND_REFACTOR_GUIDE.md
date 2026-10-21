# Python 代码整理记录

## 当前定位

这是一个命令行程序，不是需要提供 HTTP 服务的后端。建议保留 `python helper_main.py` 的启动方式，将登录、平台请求、视频、作业、AI 和题库按职责拆开。不建议仅为了整理目录引入 Web 框架、任务队列或 ORM。

以下清单是基于 2026-10-07 工作区代码提出的原始建议。当前实现已按下方目录迁移；保留此清单供后续维护时对照。

## 先修运行问题

| 优先级 | 位置 | 当前问题 | 建议及完成标准 |
| --- | --- | --- | --- |
| P0 | `helper_main.py`、`get_info.py`、`homeworkHelper.py`、`decrypt_problem.py` | 多处 `requests.get/post` 未设置超时。网络挂起时，主流程可能长期停住。 | 所有平台和字体请求统一设置连接与读取超时；区分可重试的读取请求和可能已经提交成功的写请求。Ctrl+C 后不再发起新请求。 |
| P0 | `get_info.py` | 登录验证 Cookie 写死 `university_id=3325`，但程序已经获取实际学校 ID。 | 使用本次获取的 `university_id` 构造所有登录参数；在非该 ID 的学校上也能完成登录。 |
| P0 | `homeworkHelper.py` | 提交失败、达到重试上限后仍可能打印“习题已经完成”；响应缺少 `data` 或 `my_score` 时可能再抛异常。 | 提交结果分为成功、答错、限流、失败；仅确认成功后记录完成。达到上限时输出题目 ID 与失败原因。 |
| P0 | `homeworkHelper.py`、`helper_main.py` | 多处裸 `except:` 把解析失败、接口变化甚至 `KeyboardInterrupt` 当作普通情况吞掉。 | 只捕获预期异常；无法解析的响应保留上下文并停止当前任务或明确跳过。中断信号必须向上传播。 |
| P1 | `homeworkHelper.py` | 作业页面和讨论页面的 GET 请求没有统一超时；提交 POST 的超时重试可能重复提交。 | 提交前确认接口是否支持幂等键或提交状态查询；无法确认时，超时后先查询状态，再决定是否重发。 |
| P1 | `videoHelper.py` | 进度读取一处用正则从 JSON 文本提取 `completed`，其余地方用 JSON；反复限流可能让同一心跳无限等待。 | 统一解析 JSON；对单个视频设置可观测的限流/重试上限，超限后记录失败并结束该视频。 |
| P1 | `get_info.py`、`get_websockets.py` | 登录失败返回 `None`，随后 `json.loads(None)` 才暴露错误；Cookie 用逗号拆分，文件句柄未关闭。 | 登录接口返回明确的成功结果或抛有上下文的异常；用适合 `Set-Cookie` 的解析方式处理 Cookie，读写文件使用上下文管理器。 |
| P1 | `question_bank.py` | 初始化时每次读入种子文件并执行插入；失效的种子记录在重建数据库后会再次出现。 | 给种子数据标版本；明确种子与平台验证记录的优先级。不要让一次判错后的失效记录在下次启动时被种子重新启用。 |
| P2 | `openai_ask.py` | 每道未命中题都重新读取配置并创建 SDK client；答案仅按逗号拆分。 | 启动时加载并校验配置，复用 client；按题型解析和校验输出，判断题、多选题和填空题分别处理。 |

## 目标目录

建议采用小型包结构，先移动代码并维持现有命令行入口；模块名只是建议，关键是职责边界。

```text
helper_main.py                 # 兼容入口：只调用 yuketang_helper.cli.main()
requirements.txt
README.md
yuketang_helper/
  __init__.py
  cli.py                      # 参数、交互提示、启动与退出码
  config.py                   # 读取并校验运行配置
  models.py                   # Course、Question、Answer、SubmitResult 等数据结构
  platform/
    __init__.py
    client.py                 # requests.Session、认证头、超时、响应错误
    auth.py                   # Cookie 和扫码登录
    websocket_login.py        # WebSocket 生命周期、终端二维码
    courses.py                # 课程、章节、视频与作业列表
    video.py                  # 视频进度和心跳接口
    exercise.py               # 取题、提交、解析平台返回结果
    discussion.py             # 讨论题相关平台接口
  workflows/
    __init__.py
    video.py                  # worker 分配、停止信号、进度流程
    homework.py               # 取题 -> 查题库/问 AI -> 提交 -> 保存结果
    discussion.py             # 生成、确认、提交讨论回复
  answers/
    __init__.py
    parser.py                 # 按题型校验 AI/题库答案
    ai.py                     # Chat Completions / Responses 适配
    bank.py                   # SQLite 查询、验证写入、失效
  decryption/
    __init__.py
    font.py                   # 字体映射和题目解密
  logging.py                  # 统一终端日志与倒计时
data/
  mapping_file.json
  question_bank_seed.json
tools/
  create_mapping_file.py     # 离线生成映射文件
tests/                        # 纯本地测试；迁移时逐步补
```

`config.json`、Cookie 文件和运行生成的 `question_bank.sqlite3` 属于本地数据，应继续忽略，不随代码移动或提交。`homework_Helpers.py` 看起来是旧的独立实现：先确认是否还有人直接运行，再删除或移入 `tools/legacy/`；不要与当前作业流程同时维护两套逻辑。

## 模块边界

1. **CLI 只负责选择和调度。** `helper_main.py` 目前在模块导入阶段就调用 `input()` 和登录。将交互放入 `main()`，把“全部课程”和“单门课程”统一为一个课程列表后遍历，避免两份相同流程。
2. **平台客户端只负责 HTTP/WebSocket。** 统一域名、学校 ID、认证头、超时和错误转换；它返回解析后的数据，不打印日志、不调用 AI，也不决定是否刷课。避免把可重试的 GET 与可能产生副作用的 POST 放进完全相同的重试逻辑。
3. **工作流负责步骤和状态。** 视频工作流持有停止事件与 worker；作业工作流决定题库命中、AI 回答、提交与验证；讨论工作流管理人工确认。网络、题库和 AI 依赖通过构造参数传入，避免全局状态。
4. **答案模型必须有稳定格式。** 区分单选、多选、判断和填空；提交前统一验证答案是否属于选项，判断题规范为平台接受的值，填空题验证 JSON 结构。题库保存的是规范化答案，不依赖某次模型输出的字符串形态。
5. **题库只接收有证据的记录。** 保留原始题型、题干、选项、答案、解析、来源和有效状态。仅在平台明确判对时写入；对题库命中但判错的记录标记失效。题干规范化规则要稳定，修改规则时考虑旧键迁移。
6. **日志只报告状态。** 统一 `Main/WorkerN`、级别、课程或题目 ID；不要打印认证 Cookie、API key 或完整登录响应。失败日志要能定位步骤，但不能把失败写成完成。

## 推荐迁移顺序

1. **建立行为基线。** 记录现有 CLI 输入、接口响应样例和典型成功/限流/失败场景；保留当前 SQLite 数据和 Cookie 文件。先明确提交 API 在超时后的重复提交语义。
2. **修 P0 问题。** 给所有外部请求加超时，修复学校 ID，替换裸 `except:`，让作业提交返回明确结果。此阶段暂不搬文件，便于定位回归。
3. **抽出平台客户端。** 先迁移登录和课程读取，再迁移视频与作业接口；旧入口仍可运行。每次只迁移一条调用链，避免同时改请求形态和业务规则。
4. **抽出模型、AI 和题库。** 固定答案格式与题库键生成规则；让作业工作流使用这些接口。迁移时保留现有 `question_bank.sqlite3`，先验证新代码能读取旧表。
5. **拆分工作流与 CLI。** 将 `do_homework()` 中的取题、答题、提交、讨论分开；统一课程循环和退出处理。最后清理旧文件、死代码与过时 README 内容。

## 每阶段验收

- 导入任意模块不会提示输入、登录或发网络请求；运行 `python helper_main.py` 仍能进入原有交互。
- 网络无响应时会在配置的超时时间内报错；Ctrl+C 能停止视频 worker 和限流倒计时。
- 同一课程的单课程/全部课程路径结果一致；失败、答错和成功日志可区分。
- 题库命中不请求 AI；无答案的文字题仍请求 AI；平台判错的答案不会再被缓存使用。
- 登录在不同学校 ID 下构造正确请求；Cookie 和 API key 不出现在日志中。

## 当前实施状态

- `helper_main.py` 只保留兼容入口；交互与调度在 `yuketang_helper/cli.py`。根目录旧模块名继续转发到包内实现。
- 平台 HTTP 请求集中在 `platform/`，设置连接和读取超时；作业提交超时后先读取作答次数，状态不明时停止重试。
- 题库保留根目录原 SQLite 数据，种子和字体映射移入 `data/`。种子版本记录在数据库中，失效记录不会被重复导入启用。
- 作业日志按正确、答错、限流、失败区分；只有每题得到确认结果后才报告该习题完成。
- `homework_Helpers.py` 的旧实现已移到 `tools/legacy/`；根目录同名文件仅作为直接运行的兼容入口，导入不触发登录。主入口不使用它。
- 尚未用真实平台账号执行端到端验证；不同学校的响应差异仍需在实际运行中确认。
