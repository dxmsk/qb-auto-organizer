# qB自动整理助手

这是一个 MoviePilot v2 插件。它通过 qBittorrent Web API 定期查询已完成任务，并把新完成任务的内容路径交给 MoviePilot 内置 `TransferChain` 整理链。

## 功能

- 以 10 秒以上的自定义间隔轮询 qBittorrent。
- 支持逗号分隔的 qB 标签过滤；命中任意一个配置标签即处理，留空处理全部。
- 使用 MoviePilot 插件数据存储持久化已处理 hash，MoviePilot 重启后仍可去重。
- 整理时传入 `download_hash` 与下载器来源。若存在 MoviePilot 下载历史，则沿用其中的具体下载器实例名；否则使用 `qbittorrent`。
- 日志级别支持 `DEBUG`、`INFO`、`WARNING`、`ERROR`。
- 配置页提供“立即检测”按钮，测试登录、版本读取和已完成任务查询，并由 MoviePilot 弹窗显示结果。
- 不修改、暂停或删除 qBittorrent 中的种子。

## 目录结构

```text
qb-auto-organizer/
├── package.v2.json
└── plugins.v2/
    └── qbautoorganizer/
        └── __init__.py
```

## 安装

可将本目录作为 MoviePilot 自定义插件仓库发布，或把 `plugins.v2/qbautoorganizer` 放入对应的 MoviePilot 插件仓库后安装。插件 ID 为 `QbAutoOrganizer`。

安装后进入插件配置：

1. 填写 qBittorrent Web UI 地址、用户名和密码，保存配置。
2. 点击“立即检测”，确认弹窗显示连接成功。
3. 设置监控间隔、可选标签和日志级别。
4. 打开“启用插件”并保存。

## 路径映射要求

qBittorrent API 返回的 `content_path` 必须能在 MoviePilot 容器内以同一路径访问。例如 qB 返回 `/downloads/movie/A.mkv`，MoviePilot 容器内也必须存在该路径。若两个容器使用了不同的内部路径，请调整 Docker volume，使两端路径一致。

## 去重说明

hash 只有在 MoviePilot 整理调用成功入队后才会写入插件数据键 `processed_torrents`。路径暂不可见、识别失败或整理调用失败时不会记录，下次轮询会再次尝试。

标签匹配不区分大小写，并同时兼容英文逗号和中文逗号。

