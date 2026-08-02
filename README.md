# qB自动整理助手

这是一个 MoviePilot v2 插件。它首次启动时将 qBittorrent 中全部现有种子写入固定历史基线，之后只跟踪并整理基线之外新增且下载完成的任务。插件重启或修改配置时会继续加载原基线，不会把尚未完成的新种子误归为历史任务。

## 功能

- 首次启动时持久化全部现有 hash，历史种子即使之后完成也不会触发整理；后续重启直接加载原基线。
- 以 10 秒以上的自定义间隔轮询 qBittorrent，持续跟踪固定基线外新增但尚未完成的种子。
- 支持逗号分隔的 qB 标签过滤；命中任意一个配置标签即处理，留空处理全部。
- 支持“强制整理”开关。关闭时跳过带“已整理”标签或已有整理记录的任务；开启时向整理链传递 `manual=True, force=True`。
- 使用插件数据目录中的 `processed_hashes.json` 持久化成功整理的 hash。
- 通过 `TransferChain.do_transfer()` 传入下载路径、`download_hash` 与下载器来源。若存在 MoviePilot 下载历史，则沿用其中的具体下载器实例名；否则使用 `qbittorrent`。
- 监听 MoviePilot `TransferComplete` 事件，只有实际整理成功后才写入 `transfer_records.json`。
- 提供 Vue 状态页，展示海报、媒体名称、类型、整理时间和目标路径，每页 20 条。
- 提供受 MoviePilot 鉴权保护的 `/records` 分页 API。
- 日志级别支持 `DEBUG`、`INFO`、`WARNING`、`ERROR`。
- 配置页提供“立即检测”按钮，测试登录、版本读取和已完成任务查询，并由 MoviePilot 弹窗显示结果。
- 配置页提供带二次确认的“重置基线”按钮，对应受鉴权保护的 `/baseline/reset` API。
- 不修改、暂停或删除 qBittorrent 中的种子。

## 目录结构

```text
qb-auto-organizer/
├── package.v2.json
└── plugins.v2/
    └── qbautoorganizer/
        ├── __init__.py
        ├── dist/assets/remoteEntry.js
        └── src/components/
            ├── Config.vue
            └── Page.vue
```

## 安装

可将本目录作为 MoviePilot 自定义插件仓库发布，或把 `plugins.v2/qbautoorganizer` 放入对应的 MoviePilot 插件仓库后安装。插件 ID 为 `QbAutoOrganizer`。

安装后进入插件配置：

1. 填写 qBittorrent Web UI 地址、用户名和密码，保存配置。
2. 点击“立即检测”，确认弹窗显示连接成功。
3. 设置监控间隔、可选标签、强制整理开关和日志级别。
4. 打开“启用插件”并保存。

## 路径映射要求

qBittorrent API 返回的 `content_path` 必须能在 MoviePilot 容器内以同一路径访问。例如 qB 返回 `/downloads/movie/A.mkv`，MoviePilot 容器内也必须存在该路径。若两个容器使用了不同的内部路径，请调整 Docker volume，使两端路径一致。

## 基线与去重

首次成功连接 qBittorrent 时，当前全部种子 hash 会写入 `baseline_hashes.json` 并永久作为历史基线。以后启用、重启或修改配置均直接加载该文件；基线外的新种子即使尚未完成或期间插件重启，也会在后续轮询中继续等待。

配置页的“重置基线”会删除基线文件，但不会改变当前运行实例的内存基线。下次插件启动或配置重载时，当前 qBittorrent 中全部种子会重新成为历史基线。

hash 只有在 MoviePilot 发出 `TransferComplete` 成功事件后才会写入 `processed_hashes.json`。路径暂不可见、识别失败或整理失败时不会记录，后续轮询会再次尝试。

整理明细保存在 MoviePilot 插件数据目录的 `transfer_records.json` 中，记录接口按整理时间倒序返回。旧版 `organize_records.json` 会在首次升级时自动迁移。

标签匹配不区分大小写，并同时兼容英文逗号和中文逗号。
