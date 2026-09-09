# oseasy-helper

一个小型 CLI：接收噢易课堂广播视频，提供播放器地址；接收下发文件；查询、挂起或临时启停本机学生端。Python 3.10+；视频和文件接收使用标准库，进程挂起使用 `psutil`。

```text
uv run oseasy-helper -h
uv run oseasy-helper video -h
uv run oseasy-helper files -h
uv run oseasy-helper control -h
```

`video` 去除私有 UDP 分片封装，重组 H.264，再封装为 MPEG-TS。**画面解码由 mpv / VLC 完成**。脚本没有窗口、录制、FFmpeg 调用或校验流程，也不安装驱动或自启项。

## 运行

使用 [uv](https://docs.astral.sh/uv/) 管理项目环境。在仓库目录运行：

```powershell
uv sync --locked
uv run oseasy-helper -h
```

后续命令均在仓库目录执行，无需手动激活虚拟环境。

Windows 的 `control` 使用系统自带的 Windows PowerShell。`video` 基于标准 socket 编写，当前宿主验证环境是 Windows；其他系统的组播接收需要自行验证。

## 视频

将下面示例地址替换为教师 IP 和本机课堂网卡 IPv4。组播地址由程序自动推导，无需填写。

```powershell
uv run oseasy-helper video --teacher 203.0.113.10 --local 192.0.2.20
```

按研究版本的地址约定，教师 IP `A.B.C.D` 对应组播 `229.1.C.D`。例如上述教师地址对应 `229.1.113.10`。这个映射与原先验证的视频环境一致；其他地址约定尚未验证。

启动成功后，标准输出只有一个地址：

```text
http://127.0.0.1:17778/live.ts
```

保持接收器运行，在另一个终端打开播放器：

```powershell
mpv http://127.0.0.1:17778/live.ts
vlc http://127.0.0.1:17778/live.ts
```

也可以在 VLC 的“打开网络串流”中粘贴地址。默认接收 UDP 7778，可用 `--udp-port` 更改；HTTP 端口可用 `--http-port` 更改。HTTP 只监听本机，不向局域网转播。按 Ctrl+C 停止，地址随进程退出失效。

打印地址只表示接收器已启动。标准错误会提示等待关键帧，首次完成重组后提示视频尺寸，退出时给出收包、帧、丢帧和无效包计数。教师未广播、网卡选错、组播未到达或尚未收到完整关键帧时，播放器会等待。单纯启动接收器不会要求教师端开始广播。

## 文件接收（实验功能）

在下次文件下发前，手动打开一个终端运行并保持监听：

```powershell
uv run oseasy-helper files --teacher 203.0.113.10 --local 192.0.2.20
```

默认保存到 `received/<本次运行目录>/transfer-*/`，可用 `--output` 指定其他目录。同一运行目录内的 `events.jsonl` 记录任务和收件结果；终端也会显示主要事件。按 Ctrl+C 停止。可与 `video` 在两个终端同时运行。

接收器监听**本机 TCP 9100**，并主动连接**教师 TCP 8555**获取文件任务；连接失败每 5 秒重试。端口与现场配置不同时，可使用 `--data-port`、`--node-port`。仅接受 `--teacher` 指定地址发起的数据连接。命令不启动原学生端、不更改服务或防火墙。

| 事件 | 含义 |
| --- | --- |
| `listening` | 本地端口已绑定，尚不表示收到任务或文件 |
| `node_connected` / `node_ready` | 文件任务连接成功 / 已登记本机接收端口 |
| `node_retry` | 文件任务连接失败后等待重试 |
| `receive_task` | 收到接收任务；`matches_listener=false` 表示任务地址或端口与当前参数不同 |
| `data_connected` / `file_begin` | 数据连接到达 / 开始接收文件 |
| `file_saved` | 完整写入并核对声明大小，显示路径、字节数及 SHA-256 |
| `transfer_complete` | 收到传输结束报文，本地文件处理完成 |
| `data_error` / `file_partial` | 协议、连接或写入失败；未完成的文件保留为 `.part` |

已通过本机模拟发送测试，以及**原厂组件在回环地址发送 → Python 接收**的兼容性测试，涵盖目录、中文文件名和约 1 MiB 的二进制文件。真实课堂观察确认：教师端只向已登录的学生分配文件；原接收器连接 8555 后先发送节点心跳 6，再发送接收端就绪 7，收到接收任务 3 后，教师机主动连接学生的 9100 发送内容。本命令已经实现 6/7 和内容接收，但不模拟 9003 学生登录；其他学生节点中继、自动切换端口和完成报告也尚未实现。任务中的发送节点地址可能是教师机内部地址，因此只作记录；本地任务地址和端口用于校验监听参数。

下次测试后，先查看 `file_saved` 和实际文件内容。如果没有收到文件，保留本次 `events.jsonl`，它能区分任务未到、数据连接未到和协议处理失败。端口绑定失败时先检查地址和占用；只有 `listening` 时再检查任务日志及本机 TCP 9100 入站是否可达。文件是否在教师界面显示完成，不能从本地保存结果推断。

当前一次数据连接最多接收 8 GiB、10000 个条目；单帧最多 8 MiB，数据连接连续 60 秒没有数据会结束。接收器持续等待后续连接。文件不会自动执行，也不会按教师提供的绝对路径覆盖本机文件；上传命令会忽略。

## 管理登录（实验原型）

现场已确认 `--mock-thumbnail` 回传的固定测试图可在教师界面显示。目录查询应答也已加入：收到命令 87 的查询后，用命令 88 提供 `--receive-dir` 指定的收件目录（默认 `received`），不枚举磁盘或子目录。此目录应答尚待教师界面实测；请另开 `files` 接收进程，并让它的 `--output` 与 `--receive-dir` 一致。实际文件仍保存在 `files` 创建的本次运行子目录内。

退出官方学生端后，在一个终端运行：

```powershell
uv run oseasy-helper client --teacher 203.0.113.10 --local 192.0.2.20
```

程序使用本机名称、当前用户名及课堂网卡的 MAC/IP 发送 9003 登录报文，随后持续读取并记录命令号。真实测试中收到配置报文及周期缩略图请求，但教师界面仍显示未登录/离线，因此目前不能替代官方客户端完成登录或保证文件分配。`login_sent` 只表示报文已发送。

该原型只记录管理命令，不执行截图、键鼠控制、启动程序等操作。可加 `--mock-thumbnail`，在收到 64×64 缩略图请求时回传随程序附带的固定 MOCK 测试图，用于检查教师界面显示；默认不回复缩略图。文件内容由另一个终端的 `files` 命令接收。按 Ctrl+C 退出，断线后也会退出；当前不自动重连。不应同时运行官方学生端和本原型。

## 本机控制管理

```powershell
uv run oseasy-helper control status
uv run oseasy-helper control suspend
uv run oseasy-helper control resume
uv run oseasy-helper control stop
uv run oseasy-helper control start
```

| 命令 | 行为 |
| --- | --- |
| `status` | 只读查询 MMPC 服务，并按安装目录及 MMPC 子进程树发现当前噢易进程。服务运行不等于已连接教师。 |
| `suspend` | 管理员终端运行。挂起安装目录内的 Student / MmcStudent / MultiClient，MMPC 服务保持运行。 |
| `resume` | 管理员终端运行。恢复上述已挂起的进程。 |
| `stop` | 管理员终端运行。停止 MMPC，结束其安装目录内上述学生端进程；原学生端管理连接会中断。 |
| `start` | 管理员终端运行。启动 MMPC；若学生端没有自动出现，使用原软件入口启动，再检查连接状态。 |

`suspend/resume` 参考 OsEasy-ToolBox 的 `psutil.Process.suspend()/resume()` 做法，但增加了安装目录复核；不会挂起 MMPC、DeviceControl 或无关的同名程序。挂起会停止学生端处理心跳、文件任务及其他报文，教师端可能在超时后判定离线，不能把它当作“持续在线但拒绝控制”的保证。

普通终端也能显示受保护的 MMPC 服务进程及其子进程，但 Windows 可能不提供其 `ExecutablePath`；这不等于进程不存在。所有状态变更都不会修改服务启动类型、删除文件、操作驱动或自动提权。`stop` 是临时停止：其他组件或系统重启可能再次启动学生端，也不能保证已经生效的驱动锁定会解除。出错可能已经完成部分操作，应先 `control status`，挂起后使用 `control resume`，停止后使用 `control start`。

**本项目没有实现“原学生端保持在线，同时屏蔽全部键鼠强控”。** 独立接收视频与原管理连接分属不同链路；视频能继续到达仍取决于实际网络和教师广播状态。当前没有广播与控制同时发生的现场验收结果。

## 文档和复现文件

- [HANDOFF.md](HANDOFF.md)：研究结论、视频链路复现、控制范围和未验证事项。
- [docs/PROTOCOL.md](docs/PROTOCOL.md)：私有头部、重组及 MPEG-TS 输出细节。
- `oseasy_helper/video.py`：接收、重组、TS 封装和 HTTP 输出。
- `oseasy_helper/control.py`：本机服务管理，命令内容直接可审阅。
- `oseasy_helper/files.py`：文件任务连接、TCP 内容接收和完成应答。

运行测试：

```powershell
uv run python -m unittest discover -s tests -v
```

测试使用人工数据、本机 TCP 和 HTTP，覆盖协议处理、输出结构和 CLI 入口，不执行控制启停。封装链路曾用标准解码器验证；视频 CLI 尚未在真实广播期间复测，也未实际测试 mpv / VLC 客户端。

此实现来自对 10.9.0.4820 的研究，并非厂商提供的完整协议规范。没有音频、重传、原学生端身份模拟或完整教师指令支持。文件节点使用自身协议的连接消息，与原学生端管理保活无关。

文件下发使用独立的连接和任务协议，`video` 不接收文件。文件协议、复现证据与现场待验证事项见 [HANDOFF.md](HANDOFF.md#五文件接收链路)。
