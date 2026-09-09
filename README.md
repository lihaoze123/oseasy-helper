# oseasy-helper

一个小型 CLI：接收噢易课堂广播视频，提供播放器地址；查询、临时启停本机学生端。Python 3.10+，运行时只使用标准库。

```text
oseasy-helper -h
oseasy-helper video -h
oseasy-helper control -h
```

`video` 去除私有 UDP 分片封装，重组 H.264，再封装为 MPEG-TS。**画面解码由 mpv / VLC 完成**。脚本没有窗口、录制、FFmpeg 调用或校验流程，也不安装驱动或自启项。

## 运行

在仓库目录安装：

```powershell
python -m pip install .
oseasy-helper -h
```

也可以不安装，直接在仓库目录使用 `python -m oseasy_helper`。

Windows 的 `control` 使用系统自带的 Windows PowerShell。`video` 基于标准 socket 编写，当前宿主验证环境是 Windows；其他系统的组播接收需要自行验证。

## 视频

下面都是文档示例地址，必须替换为现场实际参数。`--local` 是连接课堂网络的本机网卡 IPv4；`--group` 是实际视频目的组播地址，不能仅凭教师 IP 推算。

```powershell
oseasy-helper video --teacher 203.0.113.10 --local 192.0.2.20 --group 239.255.0.1
```

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

## 本机控制管理

```powershell
oseasy-helper control status
oseasy-helper control stop
oseasy-helper control start
```

| 命令 | 行为 |
| --- | --- |
| `status` | 只读查询 MMPC 服务及 Student / MultiClient / LissHelper 同名候选进程。服务运行不等于已连接教师。 |
| `stop` | 管理员终端运行。停止 MMPC，结束其安装目录内上述学生端进程；原学生端管理连接会中断。 |
| `start` | 管理员终端运行。启动 MMPC；若学生端没有自动出现，使用原软件入口启动，再检查连接状态。 |

启停不会修改服务启动类型、删除文件、操作驱动或自动提权。`stop` 是临时停止：其他组件或系统重启可能再次启动学生端，也不能保证已经生效的驱动锁定会解除。出错可能已经完成部分操作，应先 `control status`，需要恢复时使用 `control start`。

**本项目没有实现“原学生端保持在线，同时屏蔽全部键鼠强控”。** 独立接收视频与原管理连接分属不同链路；视频能继续到达仍取决于实际网络和教师广播状态。当前没有广播与控制同时发生的现场验收结果。

## 文档和复现文件

- [HANDOFF.md](HANDOFF.md)：研究结论、视频链路复现、控制范围和未验证事项。
- [docs/PROTOCOL.md](docs/PROTOCOL.md)：私有头部、重组及 MPEG-TS 输出细节。
- `oseasy_helper/video.py`：接收、重组、TS 封装和 HTTP 输出。
- `oseasy_helper/control.py`：本机服务管理，命令内容直接可审阅。

运行测试：

```powershell
python -m unittest discover -s tests -v
```

测试使用人工数据和本机 HTTP，覆盖协议处理、输出结构和 CLI 入口，不执行控制启停。封装链路曾用标准解码器验证；此 CLI 尚未在真实广播期间复测，也未实际测试 mpv / VLC 客户端。

此实现来自对 10.9.0.4820 所用视频格式的观察，并非厂商提供的完整协议规范。没有音频、重传、教师指令、身份模拟或心跳保活功能。
