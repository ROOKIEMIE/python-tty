# 阶段记录

## 2026/02/02

目标：
1. Milestone A：Kernel 固化 + Job API（不做 RPC）
   - 交付物
      - 完整 RuntimeEvent 流（含 stdout/log，支持 run_id 关联）
      - JobStore + 基础操作（list/get/cancel/events/result）
      - TTY 侧：新增 jobs 命令族（只是前端展示，不改变内核）（暂缓实现）
2. Milestone B：proto + grpc aio server（RPC 独立 submit）
   - 交付物
      - runtime.proto（Invoke + StreamEvents）
      - RPC 侧：构建 ExecutionContext → Invocation → executor.submit（source=rpc）
      - StreamEvents 从 JobStore/EventBus 订阅事件

落地细节：
1. 固化中心链路：Executor + RuntimeEvent + Audit 不依赖 TTY/RPC

事件“采集”与事件“消费”必须分层

1.1.
目前的问题：
stdout/log 目前很多还是走 router（proxy_print）→ UIEvent，这会导致 RPC/Job 无法看到过程输出

引入机制：Run 上下文传播（contextvar 或显式参数）
- 执行某个 invocation 时，executor 在运行 handler 前设置 current_run_id（contextvar）
- proxy_print() 如果发现存在 current_run_id，则发布 RuntimeEvent(kind=STDOUT/LOG, run_id=...) 给 executor/eventhub，同时仍可选渲染到 TTY

1.2. 构建事件消费层（Frontends / Sinks）
- TTY：订阅 RuntimeEvent → to_ui_event → 渲染
- RPC：订阅 RuntimeEvent → proto → streaming
- Audit：订阅 RuntimeEvent + run_state → 落盘
- Web：订阅 RuntimeEvent + meta snapshot → WS push

2. Job 管理：给一个基本组件 + 为 Session 留空间
对外的 JobStore / JobAPI（可被 TTY/RPC 同时使用）。
2.1. 最小 JobStore 接口（建议就这些）：
- list(filters)：按 status/source/principal/command_id 查询
- get(run_id)：返回 RunState + 元信息（Invocation 摘要）
- cancel(run_id)
- events(run_id, since_seq=0)：订阅事件（最好支持 fanout）
- result(run_id)：等结果（可选 timeout）

2.2. 为 Session 留哪些空间
Session 本质是“跨多次 invocation 的上下文容器”，先不实现它，但要预留 2 个钩子就够：
- Invocation.session_id: Optional[str]（或放到 invocation.tags/kwargs）
- lock_key 未来可从 global → session:{session_id}（你说 global 会用很久完全 OK，但先把字段语义预留）

3. ExecutionContext：从 TTY 抽象最小执行上下文，让 RPC 复用

3.1. ExecutionContext 应该是什么
它不是 Console，也不是 Commands。它应该是一个纯运行时载体：
- source（tty/rpc）
- principal（用户/客户端）
- console_path（console_name，可选）
- command_path（command_name / command_id）
- argv/raw_cmd
- run_id（提交后填）
- meta_revision（可选：客户端携带）
- session_id（预留）
- deadline/timeout_ms
- lock_key（默认 global）

它的职责：
- 承载调用意图
- 参与校验（argspec / meta revision / allowlist）
- 构建 Invocation

3.2. “命令执行”需要谁来做
执行永远是 executor handler 做。ExecutionContext 只负责把“调用意图”变成 invocation。

3.3. 增加一个ExecutionBinding（适配器）用以解决“必须通过console才能拿到service”的问题
- ExecutionBinding(service, manager, ctx)
- 让 Commands 在执行时能访问 binding.service
- TTY binding 的 service 来自 main console 注入
- RPC binding 的 service 来自 factory 注入（同一实例）
这比“RPC 必须构造 console”更干净：你把“获取业务核心”的依赖从 console 语义里抽出来了。

4. 先定义 proto，再完善 RPC：proto 要按“运行时协议”来，而不是按“TTY 命令对象”来

4.1. proto 的核心应该只围绕三件事
- InvokeRequest/InvokeReply（返回 run_id）
- StreamEventsRequest（run_id + since_seq）
- RuntimeEvent（state/log/stdout + seq + ts + level + payload）
不要把 UIEvent/Prompt 这类东西放进去。

4.2. 一个必须提前考虑的问题：事件 fanout
一个 run_id 同时被 TTY 显示、RPC client 订阅、Audit 记录，那么 per-run events 不能是单消费者 queue。

现在就把事件模型做成：
- RunEventBus：每个订阅者拿一个独立 queue
- publish 时广播
否则你很快会遇到“RPC 订阅把事件读走了，TTY 就看不到了”的问题。

## 2026/01/27/02

1. rpc侧应该模仿console/core模块中execute和run方法的实现，重新构建invocation并投递至executor，source为rpc。不要复用现有console的submit过程，应该形成一条独立的submit过程。
2. 新增runtime.proto。
3. 新增grpc aio server，协程模式。

## 2026/01/27/01

目标:
1. 把框架的整体结构并发式地跑起来：
一个进程，两类 event loop：
- 主线程：一个 asyncio loop
   - FastAPI（Meta API：HTTP + WS）
   - gRPC aio server（Invoke + StreamEvents）
   - CommandExecutor（作为“唯一运行时入口”，最好也在这个 loop 上）
- TTY 线程：一个独立线程
   - prompt_toolkit 的 PromptSession/应用运行（它内部也会用 asyncio，但你可以在这个线程里创建自己的 loop 或让 prompt_toolkit 管理）
   - TTY 发起命令：通过 submit_threadsafe() 把 invocation 投递到主线程 executor loop
   - 输出：OutputRouter 把事件安全地写回 TTY（run_in_terminal / patch_stdout 等）
2. 原始的V2开发规划：
- Step 0：把 Executor 插进去（让命令可后台执行）
   - 把 BaseConsole.execute 改成 submit invocation
   - TTY 调用也走 executor
   - 先用同步等待结果也行，但建议至少把执行从 console loop 中剥离
- Step 1：定义 Invocation / Run / Event 三个核心数据结构
   - 这是 Web/RPC/TTY 共用的“运行时协议”
   - 有了它，Meta/RPC 都只是“外壳”
- Step 2：Meta Descriptor v1（argv-only）
   - 从 registry 导出 consoles/commands/argspec(min/max)
   - revision hash
- Step 3：RPC proto v1（Invoke + StreamEvents）
   - 先走通 unary invoke + server streaming 事件
- Step 4：Meta HTTP/WS server（只读）
   - /meta + ws snapshot
   - ETag 缓存
- Step 5：把 allowlist + audit + mTLS 完整接入 RPC
   - RPC 默认 deny
   - 命令必须显式 exposure.rpc=true 才可调用
   - audit 强制落盘

下一步规划:
1. RPC proto + aio server：直接复用你现有 Invocation/RunState/RuntimeEvent，把 RuntimeEvent 流映射为 gRPC server streaming。
2. Meta HTTP/WS：GET /meta 返回 export_meta()，ETag = revision（你已算出 revision）。WS snapshot 可先做“连接后推一次 meta+revision”，后续再做增量。
3. Web实现位于frontends/web，RPC实现位于frontends/rpc；根据需要可以进一步增加子包。

## 2026/01/26/02

1. 修改了OutputRouter的emit，使之可以输出STATE。
2. 就目前的实现来说“全量输出审计”仅针对executor生效，对于proxy_print以及ConsoleHandler暂不生效；需要为OutputRouter增加一个attach_audit_sink方法，从而允许在factory中将auditsink注入其中，任何地方只要走 OutputRouter，就会被审计（如果开启）。
3. 为ConsoleRegistry 增加公开读取 API（例如 iter_consoles() / get_root() / get_subs()），meta 不要直接获取私有成员；meta v1 就带上 ConsoleManager 里已经维护了的 tree: {root, children} 或在 console entry 上带 children: []，之后外部系统生成 UI/适配更简单。

## 2026/01/26/01

1. 为UIEvent补充三个字段
   - source: "tty" | "rpc" | "framework" | "service"（输入源：框架tty、rpc、使用者custom调用输出）
   - ts/seq: 时间戳/序号（用于审计与重放顺序稳定）
2. 增加一个类AuditSink，用以实现“Invocation + RunState + Events”落盘，audit的完整传递路径为：Executor 发出 state/log/stdout 事件 → OutputRouter 渲染其中 stdout/log → AuditSink 把“Invocation + RunState + Events”落盘。目前utils包中的ui_logger模块似乎并没有使用，我认为是使用增加一个包，叫做audit，然后将这个模块移至audit包下重命名并重构其中的实现，以满足这里对于audit落盘的需要。
3. 把框架的整体结构并发式地跑起来：
一个进程，两类 event loop：
- 主线程：一个 asyncio loop
   - FastAPI（Meta API：HTTP + WS）
   - gRPC aio server（Invoke + StreamEvents）
   - CommandExecutor（作为“唯一运行时入口”，最好也在这个 loop 上）
- TTY 线程：一个独立线程
   - prompt_toolkit 的 PromptSession/应用运行（它内部也会用 asyncio，但你可以在这个线程里创建自己的 loop 或让 prompt_toolkit 管理）
   - TTY 发起命令：通过 submit_threadsafe() 把 invocation 投递到主线程 executor loop
   - 输出：OutputRouter 把事件安全地写回 TTY（run_in_terminal / patch_stdout 等）
4. 给出一个初步的meta实现（目前meta包中的实现还是空的），需要从从 registry 导出 consoles/commands/argspec 的 JSON（或 dict）结构；revision hash：未看到对 meta 做 canonical 序列化并生成 hash/ETag 的实现。

## 2026/01/24/01

目前存在问题及初步解决方案：
1. 事件队列 _event_queues 的 loop 绑定风险

publish_event() 在 loop running 时会 queue = self._event_queues.setdefault(run_id, asyncio.Queue())。

asyncio.Queue() 会绑定创建时所在的 loop（不同 Python 版本细节略有差异）。你现在 publish 可能来自不同线程（虽然你大多数会在 executor loop 线程），但如果未来在别处创建队列/发布事件，可能出现 loop 不一致的问题。

需要将所有事件队列的创建强制安排在 executor loop 线程里（比如在 submit 时创建，或用 loop.call_soon_threadsafe 创建）。

2. inline fallback 里 asyncio.run(result) 的潜在问题

_run_inline() 遇到 awaitable 会 asyncio.run(result)。
如果调用 inline 的线程里已经有事件循环（比如某些嵌入环境），asyncio.run 会报错。你现在默认会启动 executor loop thread，TTY 基本不会走 inline，但 RPC/测试场景可能会触发。

应该用 anyio或者更谨慎的 loop 处理。

3. Invocation.command_id 目前是“命令名 token”，不是稳定的 CommandDef ID

BaseConsole._build_invocation() 用 command_id=token。而 self.commands.get_command_def(invocation.command_id) 也按名字查。这对 TTY 没问题，但对 RPC/Meta 的最终目标来说，最好让 invocation 携带一个稳定 command_id（比如 cmd:{console_name}:{command}），否则：
- 多 console 下同名命令可能冲突（尤其你未来要支持“全局命令”）
- allowlist/audit 粒度会难做

在开始做 Meta Descriptor 时把 command_id 规范化。

## 2026/01/23/02

已有实现中还存在的问题：
1. 目前 TTY 路径“后台执行”并未真正启动
submit_threadsafe() 在 loop 不存在或不 running 时，会回落到 submit()；而 submit() 在拿不到 running loop 时会走 _run_inline() 同步执行。
同时 ConsoleFactory.start() 只是 manager.run()，并不会自动启动一个 asyncio loop 去 executor.start()。

2. 未来一旦“真后台执行”，TTY 输出会遇到线程/会话上下文问题
你的命令实现（例如示例里的 run_use/run_debug）大量直接调用 proxy_print()。
proxy_print 依赖 prompt_toolkit.get_app_session() 输出到当前会话。
如果未来 executor worker 在 另一个线程/另一个 event loop 执行命令，get_app_session() 很可能取不到正确 session 或输出错乱。
这意味着：后台执行要稳定，必须把“输出”从命令线程里剥离出来，改为事件化（UIEvent/RunEvent）→ 由前台 console 线程渲染。

这部分可以保留proxy_print()函数作为输出的顶层接口，重构其内部实现，
在其内部再封装事件化构造，然后统一调用输出渲染。

3. Run/Future/EventQueue 的生命周期目前没有回收策略
_runs/_run_futures/_event_queues 会持续增长，长跑会内存累积。
建议后面加一个：
- retain_last_n 或 ttl_seconds；
- 或 pop_run(run_id) 在客户端确认收取结果后释放。

## 2026/01/23/01

目前仅保留main分支和V1分支

main分支主力开发原有V2的目标

建立了三个目录：executor、frontends和meta

executor：
其中中主要放置CommandExecutor / InvocationManager实现
CommandExecutor为单例设计，其中
内部主要设计：
queue: asyncio.Queue[Invocation]
workers: N（通常 1 起步，后面加并发组）
locks: dict[str, asyncio.Lock]（全局锁或按 group）
runs: dict[run_id, RunState]
event_bus: run_id → asyncio.Queue[UIEvent] 或 pubsub channel

对外设计：
submit(invocation) -> run_id（立即返回）
await wait_result(run_id)（RPC unary 需要时）
stream_events(run_id)（RPC streaming / WS 用）

Worker loop设计：
inv = await queue.get()
await acquire_lock(inv.lock_key)
try: 执行命令（可能是 sync 或 async）
finally: release_lock, 标记结果, publish events

尽管 CommandExecutor 是 async，但它需要同时支持执行 sync 命令（线程池）和 async 命令。因为目前tty中的命令大多都是sync命令

InvocationManager：
内部的基本单元为Invocation
目前已确定的字段有：
- run_id
- source: "tty" / "rpc"
- principal（rpc 的 caller 身份）
- console_id, command_id
- argv / kwargs
- lock_key（默认 "global"）
- timeout_ms
- audit_policy（rpc 强制，tty 可选）
锁策略 v1 就用全局锁（最安全），后续再按命令/console/agent 分组优化。

frontends：
其中主要实现Web服务器和RPC服务器

meta：
其中主要放置元数据的数据结构，对齐Meta Descriptor v1 + Exporter

插入已有实现：
1. 关于BaseConsole的修改
execute() 是一个很好的“拦截点”
run() 现在是直接解析后调用命令函数
重构目标：run() 不再直接执行命令，只负责解析 → 组装 Invocation → submit。
BaseConsole.execute(cmd)：
- 解析 token/arg_text（你已经统一 split_cmd）
- 找到 CommandDef（已经有 command_defs/command_funcs）
- 调 executor.submit(Invocation(..., source="tty", console_uid=self.uid, ...))
- 对于“需要同步返回结果”的命令：可以阻塞等待（但尽量少，更多走事件流/结果查询）

结果输出怎么做:
- 由 Executor 在执行中 publish UIEvent
- 你的 UIEventSpeaker/Listener 机制可以升级为“run_id 事件流”
- TTY 前台 console 订阅当前 run 的事件并打印

2. 关于ConsoleFactory的修改
- 需要为ConsoleFactory增加一个配置数据类，用以确定它在启动时以什么样的方式启动
默认情况下仅运行tty。
- HTTP/RPC 跑主线程 event loop，TTY 跑独立线程
   - 主线程：asyncio loop + 启动 FastAPI（uvicorn）+ 启动 gRPC server + Executor workers
   - 另一个线程：TTY 交互（同步 prompt），输入后通过 executor.submit 把任务丢给主 loop（线程安全提交）。具体实现便是：TTY 线程用 asyncio.run_coroutine_threadsafe(...) 或 loop.call_soon_threadsafe(...) 把 invocation 放进 queue。

3. 更新后的V2开发规划：
- Step 0：把 Executor 插进去（让命令可后台执行）
   - 把 BaseConsole.execute 改成 submit invocation
   - TTY 调用也走 executor
   - 先用同步等待结果也行，但建议至少把执行从 console loop 中剥离
- Step 1：定义 Invocation / Run / Event 三个核心数据结构
   - 这是 Web/RPC/TTY 共用的“运行时协议”
   - 有了它，Meta/RPC 都只是“外壳”
- Step 2：Meta Descriptor v1（argv-only）
   - 从 registry 导出 consoles/commands/argspec(min/max)
   - revision hash
- Step 3：RPC proto v1（Invoke + StreamEvents）
   - 先走通 unary invoke + server streaming 事件
- Step 4：Meta HTTP/WS server（只读）
   - /meta + ws snapshot
   - ETag 缓存
- Step 5：把 allowlist + audit + mTLS 完整接入 RPC
   - RPC 默认 deny
   - 命令必须显式 exposure.rpc=true 才可调用
   - audit 强制落盘

## 2026/01/22

### V1:

创建V1、V2分支，归档现有代码。

之后V1将作为纯TTY框架进行维护；V2作为完成Web + PRC的最终目标

补全V1作为纯TTY框架的README.md和README_zh.md

给出V2的基础README.md和README_zh.md

### V2:

开发里程碑
- M1：Meta Descriptor v1 + Exporter
   - 从现有 ConsoleRegistry/CommandRegistry 导出 meta
   - 完成 ArgSpec -> args(mode=argv) 的映射
   - 生成 revision（建议对 canonical JSON 做 sha256）
- M2：RPC proto v1 +（本地）序列化/反序列化
   - 定义 proto 并生成 stub（先不跑 server）
   - 定义 InvokeRequest.argv 与当前 CLI tokenize 语义一致
   - 定义 RunEvent 与 UIEvent 的映射
- M3：Meta Web Server（HTTP + WS）
   - HTTP：/meta + ETag
   - WS：先 snapshot-only
   - 安全：默认 localhost + 可选 token
- M4：RPC Server（mTLS + allowlist + audit）
   - 只实现 Invoke + StreamRunEvents
   - allowlist 默认 deny（命令需要显式声明 exposure.rpc=true 才可调用）
   - audit 先写日志/文件，后续可接 SIEM/DB
- M5：统一执行系统（解决 RPC/TTY 冲突）
   - TTY 命令执行改走 CommandExecutor（即便是本地调用）
   - 先全局锁，保证正确性
   - 后续再做并发分组优化


## 2026/01/20

如果粗略分下优先级和复杂度：

1. **第一阶段（现在就能动手）：重做骨架 & main/sub console 抽象**
   - 拿现有代码清理出：
     - BaseConsole / MainConsole / SubConsole；
     - ConsoleManager/Registry（管理前台、切换、parent 关系）；
     - 把 quit/help/use 这些命令抽成基础 mixin。
   - 难度：⭐️⭐️⭐️（中等）
      收益：你的“多 console 模型”会非常清晰，为后面的命令重构打基础。
2. **第二阶段：CommandRegistry + 双通道命令注册 + ArgSpec 雏形**
   - 建立全局 CommandRegistry；
   - 统一 `@register_command` 和 `register_command(func, console_cls=...)` 的元数据收集；
   - 简单版 ArgSpec：至少能表达参数个数、必选/可选；
   - CLI 端先用 ArgSpec 做更合理的参数计数校验 + 限制补全次数。
   - 难度：⭐️⭐️⭐️⭐️（中等偏上）
      收益：你原来的“命令分层 + 扩展性”会真正脱胎换骨，一切命令相关逻辑都围绕 CommandDef/ArgSpec 转。
3. **第三阶段（中长期）：结构化参数 → 对外 REST/RPC 层**
   - 完善 ArgSpec 成为一个可以导出 JSON Schema / FastAPI 模型的结构；
   - 设计一个“命令声明 → Web/RPC 接口”的映射层；
   - 把“命令实现”换成 RPC client stub 时保持 TTY 端 API 不变。
   - 难度：⭐️⭐️⭐️⭐️（看你想做多自动）
      收益：你从“一个 TTY 框架作者”升级成“一个 CLI+API 双栈控制平面作者”。


## 2024/03/29

Demo中的File Manager正在开发中......


## 2024/03/27
为BaseCommand中的校验器CommandValidator添加了一个变量``` enable_undefined_command ```，
用于控制Console级别的校验器是否在用户输入一些非命令时的拦截行为，该变量在BaseCommand构造时将传入Console校验器CommandValidator中，
通过重载BaseCommand的enable_undefined_command方法，修改其返回值为True，即可实现在Console中放行非命令的输入，
以此来拓展Console的可使用范围，现在有此功能之后，就可以实现一些例如Telnet控制台之类的功能了，可以在Console中方便地决定，
当配置命令都不匹配时，是否应该使用系统命令。

同时，为BaseConsole中run方法添加了命令执行状态变量，用以检测输入的命令是否匹配配置的命令，若输入的命令不匹配任何配置的命令，
则会调用cmd_invoke_miss方法，可以通过重载该方法实现在输入的命令不匹配任何配置的命令时的自定义操作，
该方法为普通方法，入参为该不匹配的命令字符串以及其参数，不要求在继承的自定义Console中一定实现，默认的行为是对不匹配的命令不做任何处理和操作。

将clean_console方法改为普通方法，不要求自定义Console一定要实现该方法。

## 2024/03/26
基本上造完了绘制表格的轮子，目前实现的表格可以做到以下几点：
1. 跨平台，支持在Linux/Windows中可以正常使用(未在Windows环境中测试，但理论上是可以运行的，因为没有依赖一些Linux特有的库，只使用了copy标准库)
2. 只能绘制无边框的表格，纵向暂时没有设置分隔线，水平方向只有标题和数据项之间存在分隔线且该线的符号可以自定义
3. 表格整体可以设置缩进
4. 表格可以设置标题，标题也可以设置缩进
5. 目前只实现了左对齐，无论是表头亦或是数据项都是左对齐
6. 创建表格时输入数据，暂时不支持后续添加数据
7. 初始化表格数据时根据表头项数会对输入的数据项数做判断，数据项数小于表头项数时自动补上空项；反之会截去多余的数据项避免报错
由于该表格最初的目的就是做一个静态表格，因此其不具备一些动态表格的能力，目前来看其所实现的能力基本复合使用需求。

通过``` NoneArgumentValidator ```给出了一个无参方法校验器的例子，该例子中，先通过inspect库提供的方法取得了命令执行函数的参数
再通过传入的命令行输入进行判断

## 2024/03/25
为项目添加了第三方库``` tqdm ```用以实现进度条的展示
除此之外，还希望添加对静态表格的功能，尝试了几款用于绘制ASCII表格的第三方库，发现都无法满足现有的要求
现有的对表格的要求：
1. 跨平台，支持在Linux/Windows中可以正常使用
2. 支持无外边框表格，存在内边框，可以自定义内边框符号
3. 表格整体带缩进
4. 支持配置单元格对齐方式

FIXME:
1. 给出校验器校验命令执行函数的实例

## 2024/03/21
如何通过ConsoleFactory将业务核心注入到每个console中？

FIXME:
1. 校验器应与实际应该执行的命令执行函数绑定，这样才能校验出应该输入多少个参数

## 2024/03/19
现阶段发现并需要做出改进的地方：
1. 重新考虑应该通过什么样的方式来实现Console的命令
   - 在现阶段上进行修改，最终需要达到的目的是——将Console注入到Completer以及Validate中。
   - 将单个命令改成使用类来实现，在其中分别注入Console实例。
2. Console的执行逻辑
   - 先初始化Console的属性
   - 将Console传入Commands，将Commands的Completer和Validate初始化
   - Console整合Commands中所有的命令的Completer和Validate完成Console的构造
3. 了解反射调用方法的方式

## 2024/03/12
对于一个Console所需的组件已经确定了下来，一个Console由一个PromptSession和该Console所拥有的Commands组成
对于PromptSession需要配置Message、Style、Completer和Validator
Message指的是该会话开头所展示的HostName
Style指的是HostName中所各部分以及用户输入时的命令行颜色风格
Completer指的是该命令行会话所带有的补全器，该补全器将分为两层，第一层为该命令会话对各命令的智能补全，第二层为各命令中根据命令的功能所定义的补全器
Validator指的是该命令行会话所带有的校验器，用以校验输入是否合法

整体的UI框架目前初步的设想是由一个主Console以及若干个子Console组成，主Console为所有子Console的最底层，子Console之间没有明确的层次结构
对于主Console，其没有Back命令；在子Console中执行Back命令将回退至上一层Console中
在任意Console中执行Quit或者Exit命令都将退出整个UI
上述两个功能由两个异常来实现：
Back命令由异常``` SubConsoleExit ```定义，当Console捕获该异常时将退出当前Console
Quit或Exit命令由异常``` ConsoleExit ```定义，当Console捕获该异常时将检查当前Console是否为主Console，若不是则将该异常向外抛出；若是则退出Console
