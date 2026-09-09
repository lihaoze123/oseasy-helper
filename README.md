# oseasy-helper

用于噢易多媒体网络教室的 Python CLI，基于 10.9.0.4820 版本研究：

- `client`：模拟学生端登录、响应目录查询、被动接收下发文件，可回传固定测试缩略图。
- `video`：接收课堂广播，输出供 mpv / VLC 播放的视频流地址。
- `control`：查询、挂起、恢复或临时启停本机官方学生端。

当前验证环境为 Windows，要求 Python 3.10+。使用 [uv](https://docs.astral.sh/uv/) 管理环境；不安装驱动或自启项。

## 安装与帮助

在仓库目录运行：

```powershell
uv sync --locked
uv run oseasy-helper -h
```

各子命令可通过 `-h` 查看参数：

```powershell
uv run oseasy-helper client -h
uv run oseasy-helper video -h
uv run oseasy-helper control -h
```

以下示例中的 `--teacher` 替换为教师机 IPv4，`--local` 替换为本机课堂网卡 IPv4。

## 客户端

退出官方学生端后运行：

```powershell
uv run oseasy-helper client --teacher 203.0.113.10 --local 192.0.2.20 --mock-thumbnail
```

一个进程同时处理管理连接、目录查询、文件任务和文件接收，无需单独启动文件监听器。程序使用本机名称、当前用户名及指定网卡的 MAC/IP 发送登录报文。它不执行远程键鼠控制、截图、启动程序或上传文件的指令，也不会自动停止官方学生端。

`--mock-thumbnail` 在教师请求缩略图时回传一张标有 MOCK/TEST 的固定 64×64 图片，不读取桌面。现场已确认教师界面可以显示该图。不加此参数时不会回传缩略图；此前测试中教师界面仍显示未登录/离线。

### 收件目录

默认保存到 `received/<本次运行目录>/transfer-*/`。更改收件目录：

```powershell
uv run oseasy-helper client --teacher 203.0.113.10 --local 192.0.2.20 --mock-thumbnail --receive-dir D:\Classroom\Received
```

目录查询只向教师端提供指定的收件目录，不枚举磁盘或子目录。实际文件仍放入本次运行的子目录，不按教师指定的任意绝对路径写入。目录查询应答及合并后的真实课堂收件仍待验证。

每次运行的 `events.jsonl` 保存管理和收件事件，终端也会显示主要事件：

| 事件 | 含义 |
| --- | --- |
| `listening` | 本地文件接收端口已绑定 |
| `login_sent` | 登录报文已发出，不代表教师端已认可在线 |
| `mock_thumbnail_sent` | 固定缩略图已发出 |
| `receive_directory_sent` | 收件目录应答已发出 |
| `node_connected` / `node_ready` | 文件节点已连接 / 就绪消息已发出 |
| `node_retry` | 文件节点连接失败，5 秒后重试 |
| `receive_task` | 收到文件任务；`matches_listener=false` 表示本机地址或端口不匹配 |
| `data_connected` / `file_begin` | 数据连接到达 / 开始接收文件 |
| `file_saved` / `transfer_complete` | 文件写入完成 / 已处理整次传输结束报文 |
| `data_error` / `file_partial` | 接收失败；未完成文件保留为 `.part` |

文件接收只接受指定教师 IP 的连接，不覆盖已有文件，不自动执行文件。每条数据连接最多接收 8 GiB、10000 个条目，连续 60 秒没有数据会结束；客户端继续等待后续传输。暂不支持断点续传、其他学生节点中继或教师端完成报告。

默认使用教师 TCP 9003 管理连接、教师 TCP 8555 文件任务连接及本机 TCP 9100 数据监听，分别可用 `--port`、`--node-port`、`--data-port` 修改。

按 Ctrl+C 或管理连接断开时，客户端一并停止文件任务连接和数据监听。管理连接暂不自动重连。不要同时运行官方学生端和本客户端，以免重复登录或占用接收端口。

## 视频

```powershell
uv run oseasy-helper video --teacher 203.0.113.10 --local 192.0.2.20
```

组播地址由教师 IP 自动推导，无需填写。启动后输出：

```text
http://127.0.0.1:17778/live.ts
```

保持进程运行，在 mpv 或 VLC 中打开该地址：

```powershell
mpv http://127.0.0.1:17778/live.ts
```

`video` 重组私有 UDP 分片中的 H.264，再封装为 MPEG-TS；画面解码由播放器完成。没有窗口或 FFmpeg 依赖。默认 UDP 端口为 7778、HTTP 端口为 17778，可用 `--udp-port`、`--http-port` 修改。HTTP 只监听本机。

可以与 `client` 同时运行。教师未广播或尚未收到完整关键帧时，播放器会等待；输出地址本身不代表已收到视频。按 Ctrl+C 停止。目前不支持音频或丢包重传。

## 官方学生端管理

```powershell
uv run oseasy-helper control status
uv run oseasy-helper control suspend
uv run oseasy-helper control resume
uv run oseasy-helper control stop
uv run oseasy-helper control start
```

| 操作 | 行为 |
| --- | --- |
| `status` | 只读查询 MMPC 服务和相关进程 |
| `suspend` / `resume` | 挂起 / 恢复安装目录内的 Student、MmcStudent、MultiClient |
| `stop` | 停止 MMPC 并结束上述学生端进程 |
| `start` | 启动 MMPC；学生端未自动出现时需通过官方入口启动 |

除 `status` 外需在管理员终端执行。挂起不会停止 MMPC 或 DeviceControl；它会同时暂停学生端的心跳和任务处理，可能导致教师端判定离线。此做法不保证官方客户端持续在线或解除已经生效的控制。

这些操作不修改服务启动类型、不删除文件、不操作驱动，也不会自动提权。停止是临时的，其他组件或系统重启可能再次启动官方学生端。

## 验证与研究文档

已完成本机文件协议互通测试，以及合并客户端的登录、收件和断线清理测试；固定测试缩略图已在教师界面显示。真实课堂文件接收、目录选择及长期在线仍需实测，不能从 TCP 连接或消息发送成功推断这些功能已完成。

```powershell
uv run python -m unittest discover -s tests -v
```

测试使用人工数据和本机连接，不执行官方客户端控制启停。协议与研究证据见：

- [HANDOFF.md](HANDOFF.md)：登录、缩略图、文件链路、控制范围和待验证事项。
- [docs/PROTOCOL.md](docs/PROTOCOL.md)：视频分片、H.264 重组与 MPEG-TS 输出细节。

本项目实现的是所研究版本的部分协议，不是完整的官方客户端替代品。
