"""MoviePilot qBittorrent completed-download organizer plugin."""

from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

import requests
from apscheduler.triggers.interval import IntervalTrigger

from app.chain.transfer import TransferChain
from app.core.config import settings
from app.db.downloadhistory_oper import DownloadHistoryOper
from app.log import logger
from app.plugins import _PluginBase
from app.schemas import FileItem, Response


class QbApiError(RuntimeError):
    """Raised when qBittorrent Web API returns an unusable response."""


class QbAutoOrganizer(_PluginBase):
    """Poll qBittorrent and enqueue newly completed torrents for organizing."""

    plugin_name = "qB自动整理助手"
    plugin_desc = "监控 qBittorrent 下载完成，并立即触发 MoviePilot 媒体整理。"
    plugin_icon = (
        "https://raw.githubusercontent.com/jxxghp/MoviePilot-Plugins/"
        "main/icons/Qbittorrent_A.png"
    )
    plugin_version = "1.0.0"
    plugin_author = "Codex"
    author_url = "https://github.com/jxxghp/MoviePilot"
    plugin_config_prefix = "qbautoorganizer_"
    plugin_order = 25
    auth_level = 1

    _DATA_KEY = "processed_torrents"
    _LOG_LEVELS = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40}
    _DEFAULT_URL = "http://127.0.0.1:8080"
    _DEFAULT_USERNAME = "admin"
    _DEFAULT_INTERVAL = 30
    _DEFAULT_LOG_LEVEL = "INFO"
    _REQUEST_TIMEOUT = (5, 20)

    _enabled: bool = False
    _qb_url: str = _DEFAULT_URL
    _username: str = _DEFAULT_USERNAME
    _password: str = ""
    _interval: int = _DEFAULT_INTERVAL
    _tag_filter_text: str = ""
    _tag_filters: Set[str] = set()
    _log_level: str = _DEFAULT_LOG_LEVEL

    def __init__(self):
        super().__init__()
        self._check_lock = threading.Lock()
        self._stop_event = threading.Event()

    def init_plugin(self, config: dict = None):
        """Load settings. MoviePilot reloads public services after configuration changes."""
        config = config or {}
        self._stop_event.set()

        self._enabled = self._as_bool(config.get("enabled", False))
        self._qb_url = self._normalize_url(config.get("qb_url") or self._DEFAULT_URL)
        self._username = str(config.get("username") or self._DEFAULT_USERNAME).strip()
        self._password = str(config.get("password") or "")
        self._interval = self._normalize_interval(config.get("interval"))
        self._tag_filter_text = str(config.get("tag_filter") or "").strip()
        self._tag_filters = self._parse_tags(self._tag_filter_text)
        configured_level = str(
            config.get("log_level") or self._DEFAULT_LOG_LEVEL
        ).upper()
        self._log_level = (
            configured_level
            if configured_level in self._LOG_LEVELS
            else self._DEFAULT_LOG_LEVEL
        )

        self._stop_event.clear()
        if self._enabled:
            filter_text = ", ".join(sorted(self._tag_filters)) or "全部"
            self._log(
                "INFO",
                f"插件已启用：服务器={self._qb_url}，轮询间隔={self._interval}秒，"
                f"标签过滤={filter_text}",
            )

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return []

    def get_api(self) -> List[Dict[str, Any]]:
        return [
            {
                "path": "/test",
                "endpoint": self.test_connection,
                "methods": ["GET"],
                "auth": "apikey",
                "summary": "测试 qBittorrent 连接",
                "description": "登录 qBittorrent Web API 并返回服务端版本。",
            }
        ]

    def get_service(self) -> List[Dict[str, Any]]:
        if not self._enabled:
            return []
        return [
            {
                "id": "QbAutoOrganizerPoll",
                "name": "qB自动整理助手轮询",
                "trigger": IntervalTrigger(seconds=self._interval),
                "func": self.check_completed_torrents,
                "kwargs": {},
            }
        ]

    def test_connection(self) -> Response:
        """Configuration-page API used by the '立即检测' button."""
        try:
            with self._qb_session() as session:
                version_response = session.get(
                    self._api_url("/api/v2/app/version"),
                    timeout=self._REQUEST_TIMEOUT,
                )
                self._raise_for_status(version_response, "读取 qBittorrent 版本")
                version = version_response.text.strip() or "未知"

                torrent_response = session.get(
                    self._api_url("/api/v2/torrents/info"),
                    params={"filter": "completed"},
                    timeout=self._REQUEST_TIMEOUT,
                )
                self._raise_for_status(torrent_response, "查询已完成任务")
                completed_count = len(self._decode_torrent_list(torrent_response))

            self._log(
                "INFO",
                f"连接测试成功：qBittorrent {version}，已完成任务 {completed_count} 个",
            )
            return Response(
                success=True,
                message=(
                    f"连接成功：qBittorrent {version}，当前已完成任务 "
                    f"{completed_count} 个"
                ),
                data={"version": version, "completed_count": completed_count},
            )
        except Exception as exc:
            message = self._safe_error(exc)
            self._log("ERROR", f"连接测试失败：{message}")
            return Response(success=False, message=f"连接失败：{message}")

    def check_completed_torrents(self) -> Dict[str, Any]:
        """Poll qBittorrent once and enqueue eligible torrents in MoviePilot."""
        if not self._enabled or self._stop_event.is_set():
            return {"checked": 0, "queued": 0, "failed": 0}
        if not self._check_lock.acquire(blocking=False):
            self._log("WARNING", "上一轮检测仍在运行，本轮跳过")
            return {"checked": 0, "queued": 0, "failed": 0, "busy": True}

        checked = queued = failed = 0
        try:
            self._log("DEBUG", "开始查询 qBittorrent 已完成任务")
            torrents = self._get_completed_torrents()
            processed = self._load_processed()
            self._log(
                "DEBUG",
                f"qBittorrent 返回 {len(torrents)} 个已完成任务，"
                f"持久化记录中已有 {len(processed)} 个 hash",
            )

            for torrent in torrents:
                if self._stop_event.is_set():
                    self._log("INFO", "插件正在停止，终止本轮检测")
                    break

                torrent_hash = str(torrent.get("hash") or "").strip().lower()
                if not torrent_hash:
                    self._log("WARNING", "发现缺少 hash 的 qBittorrent 任务，已跳过")
                    continue
                checked += 1

                name = str(torrent.get("name") or torrent_hash)
                if torrent_hash in processed:
                    self._log("DEBUG", f"任务已处理，跳过：{name} ({torrent_hash})")
                    continue
                if not self._is_completed(torrent):
                    self._log("DEBUG", f"任务尚未完整下载，跳过：{name} ({torrent_hash})")
                    continue

                torrent_tags = self._parse_tags(torrent.get("tags"))
                if self._tag_filters and not self._tag_filters.intersection(torrent_tags):
                    self._log(
                        "DEBUG",
                        f"任务标签不匹配，跳过：{name}；任务标签="
                        f"{', '.join(sorted(torrent_tags)) or '无'}",
                    )
                    continue

                source_path = self._torrent_content_path(torrent)
                if not source_path:
                    failed += 1
                    self._log("ERROR", f"无法确定任务内容路径：{name} ({torrent_hash})")
                    continue

                self._log(
                    "INFO",
                    f"发现新的已完成任务：{name} ({torrent_hash})，路径={source_path}",
                )
                try:
                    success, detail = self._enqueue_transfer(
                        torrent=torrent,
                        torrent_hash=torrent_hash,
                        source_path=source_path,
                    )
                except Exception as exc:
                    success, detail = False, self._safe_error(exc)

                if not success:
                    failed += 1
                    self._log(
                        "ERROR",
                        f"触发 MoviePilot 整理失败：{name} ({torrent_hash}) - {detail}",
                    )
                    continue

                processed[torrent_hash] = {
                    "name": name,
                    "path": source_path,
                    "processed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                }
                try:
                    self.save_data(self._DATA_KEY, processed)
                except Exception as exc:
                    failed += 1
                    self._log(
                        "ERROR",
                        f"整理已入队但 hash 持久化失败：{name} ({torrent_hash}) - "
                        f"{self._safe_error(exc)}",
                    )
                    continue

                queued += 1
                self._log(
                    "INFO",
                    f"已加入 MoviePilot 整理队列并记录 hash：{name} ({torrent_hash})",
                )

            self._log(
                "INFO",
                f"本轮检测完成：检查={checked}，新入队={queued}，失败={failed}",
            )
            return {"checked": checked, "queued": queued, "failed": failed}
        except Exception as exc:
            failed += 1
            self._log("ERROR", f"检测 qBittorrent 任务失败：{self._safe_error(exc)}")
            return {"checked": checked, "queued": queued, "failed": failed}
        finally:
            self._check_lock.release()

    def _get_completed_torrents(self) -> List[dict]:
        with self._qb_session() as session:
            response = session.get(
                self._api_url("/api/v2/torrents/info"),
                params={"filter": "completed"},
                timeout=self._REQUEST_TIMEOUT,
            )
            self._raise_for_status(response, "查询已完成任务")
            return self._decode_torrent_list(response)

    def _qb_session(self) -> requests.Session:
        self._validate_url()
        session = requests.Session()
        session.headers.update(
            {
                "Accept": "application/json, text/plain, */*",
                "Referer": f"{self._qb_url}/",
                "User-Agent": f"MoviePilot-{self.__class__.__name__}/{self.plugin_version}",
            }
        )
        try:
            response = session.post(
                self._api_url("/api/v2/auth/login"),
                data={"username": self._username, "password": self._password},
                timeout=self._REQUEST_TIMEOUT,
            )
            self._raise_for_status(response, "登录 qBittorrent")
            if response.text.strip().lower() != "ok.":
                raise QbApiError("qBittorrent 用户名或密码错误")
            return session
        except Exception:
            session.close()
            raise

    def _enqueue_transfer(
        self, torrent: dict, torrent_hash: str, source_path: str
    ) -> Tuple[bool, str]:
        path = Path(source_path)
        if not path.exists():
            return (
                False,
                "下载路径在 MoviePilot 容器中不存在；请检查 qB 与 MoviePilot 的目录映射是否一致："
                f"{source_path}",
            )

        is_file = path.is_file()
        normalized_path = path.as_posix()
        if not is_file and not normalized_path.endswith("/"):
            normalized_path += "/"

        try:
            size = path.stat().st_size if is_file else int(torrent.get("total_size") or 0)
        except OSError:
            size = int(torrent.get("total_size") or 0)

        downloader = self._resolve_downloader_source(torrent_hash)
        fileitem = FileItem(
            storage="local",
            path=normalized_path,
            type="file" if is_file else "dir",
            name=path.name,
            basename=path.stem,
            extension=path.suffix.lstrip(".") if is_file else "",
            size=size,
        )
        state, message = TransferChain().do_transfer(
            fileitem=fileitem,
            downloader=downloader,
            download_hash=torrent_hash,
            background=True,
        )
        return bool(state), str(message or "")

    def _resolve_downloader_source(self, torrent_hash: str) -> str:
        """Keep the original MoviePilot downloader instance when history exists."""
        try:
            history = DownloadHistoryOper().get_by_hash(torrent_hash)
            if history and getattr(history, "downloader", None):
                downloader = str(history.downloader)
                self._log(
                    "DEBUG",
                    f"沿用 MoviePilot 下载历史中的下载器来源：{downloader}",
                )
                return downloader
        except Exception as exc:
            self._log(
                "WARNING",
                f"读取下载历史失败，将使用 qbittorrent 来源标记：{self._safe_error(exc)}",
            )
        return "qbittorrent"

    def _load_processed(self) -> Dict[str, dict]:
        try:
            stored = self.get_data(self._DATA_KEY)
        except Exception as exc:
            self._log("ERROR", f"读取已处理 hash 失败：{self._safe_error(exc)}")
            return {}

        if isinstance(stored, dict):
            return {str(key).lower(): value for key, value in stored.items()}
        if isinstance(stored, list):
            return {str(key).lower(): {} for key in stored}
        return {}

    @staticmethod
    def _decode_torrent_list(response: requests.Response) -> List[dict]:
        try:
            data = response.json()
        except ValueError as exc:
            raise QbApiError("qBittorrent 返回了无效 JSON") from exc
        if not isinstance(data, list):
            raise QbApiError("qBittorrent 种子接口返回格式异常")
        return [item for item in data if isinstance(item, dict)]

    @staticmethod
    def _is_completed(torrent: dict) -> bool:
        try:
            return float(torrent.get("progress") or 0) >= 0.999999
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _torrent_content_path(torrent: dict) -> str:
        content_path = str(torrent.get("content_path") or "").strip()
        if content_path:
            return content_path
        save_path = str(torrent.get("save_path") or "").strip()
        name = str(torrent.get("name") or "").strip()
        if not save_path:
            return ""
        return str(Path(save_path) / name) if name else save_path

    @staticmethod
    def _parse_tags(value: Any) -> Set[str]:
        if value is None:
            return set()
        if isinstance(value, (list, tuple, set)):
            parts = value
        else:
            parts = str(value).replace("，", ",").split(",")
        return {str(part).strip().lower() for part in parts if str(part).strip()}

    @classmethod
    def _normalize_interval(cls, value: Any) -> int:
        try:
            return max(10, int(value or cls._DEFAULT_INTERVAL))
        except (TypeError, ValueError):
            return cls._DEFAULT_INTERVAL

    @staticmethod
    def _as_bool(value: Any) -> bool:
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    @staticmethod
    def _normalize_url(value: Any) -> str:
        return str(value or QbAutoOrganizer._DEFAULT_URL).strip().rstrip("/")

    def _validate_url(self):
        parsed = urlparse(self._qb_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise QbApiError("qBittorrent 服务器地址必须是有效的 http(s) URL")

    def _api_url(self, path: str) -> str:
        return f"{self._qb_url}{path}"

    @staticmethod
    def _raise_for_status(response: requests.Response, action: str):
        try:
            response.raise_for_status()
        except requests.RequestException as exc:
            status = getattr(response, "status_code", "未知")
            raise QbApiError(f"{action}失败，HTTP 状态码 {status}") from exc

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        if isinstance(exc, requests.Timeout):
            return "连接超时"
        if isinstance(exc, requests.ConnectionError):
            return "无法连接服务器"
        return str(exc) or exc.__class__.__name__

    def _log(self, level: str, message: str):
        level = level.upper()
        if self._LOG_LEVELS.get(level, 20) < self._LOG_LEVELS.get(
            self._log_level, 20
        ):
            return
        text = f"[QbAutoOrganizer] {message}"
        if level == "DEBUG":
            logger.debug(text)
        elif level == "WARNING":
            logger.warning(text)
        elif level == "ERROR":
            logger.error(text)
        else:
            logger.info(text)

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """Return MoviePilot's declarative Vuetify configuration schema."""
        return [
            {
                "component": "VForm",
                "content": [
                    {
                        "component": "VCard",
                        "props": {"class": "mt-0", "variant": "tonal"},
                        "content": [
                            {
                                "component": "VCardTitle",
                                "props": {"class": "d-flex align-center"},
                                "content": [
                                    {
                                        "component": "VIcon",
                                        "props": {"color": "primary", "class": "mr-2"},
                                        "text": "mdi-server-network",
                                    },
                                    {"component": "span", "text": "qBittorrent 连接"},
                                ],
                            },
                            {"component": "VDivider"},
                            {
                                "component": "VCardText",
                                "content": [
                                    {
                                        "component": "VRow",
                                        "content": [
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 12, "md": 6},
                                                "content": [
                                                    {
                                                        "component": "VTextField",
                                                        "props": {
                                                            "model": "qb_url",
                                                            "label": "服务器地址",
                                                            "placeholder": self._DEFAULT_URL,
                                                            "prepend-inner-icon": "mdi-web",
                                                            "type": "url",
                                                            "clearable": True,
                                                        },
                                                    }
                                                ],
                                            },
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 12, "md": 3},
                                                "content": [
                                                    {
                                                        "component": "VTextField",
                                                        "props": {
                                                            "model": "username",
                                                            "label": "用户名",
                                                            "placeholder": self._DEFAULT_USERNAME,
                                                            "prepend-inner-icon": "mdi-account",
                                                            "autocomplete": "username",
                                                        },
                                                    }
                                                ],
                                            },
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 12, "md": 3},
                                                "content": [
                                                    {
                                                        "component": "VTextField",
                                                        "props": {
                                                            "model": "password",
                                                            "label": "密码",
                                                            "prepend-inner-icon": "mdi-lock",
                                                            "type": "password",
                                                            "autocomplete": "current-password",
                                                        },
                                                    }
                                                ],
                                            },
                                        ],
                                    }
                                ],
                            },
                            {
                                "component": "VCardActions",
                                "props": {"class": "px-4 pb-4"},
                                "content": [
                                    {
                                        "component": "VBtn",
                                        "props": {
                                            "color": "primary",
                                            "variant": "elevated",
                                            "prepend-icon": "mdi-lan-connect",
                                        },
                                        "text": "立即检测",
                                        "events": {
                                            "click": {
                                                "api": "plugin/QbAutoOrganizer/test",
                                                "method": "get",
                                                "params": {"apikey": settings.API_TOKEN},
                                            }
                                        },
                                    },
                                    {
                                        "component": "span",
                                        "props": {"class": "text-caption text-medium-emphasis ml-3"},
                                        "text": "按钮使用已保存的连接配置，并通过弹窗返回检测结果。",
                                    },
                                ],
                            },
                        ],
                    },
                    {
                        "component": "VCard",
                        "props": {"class": "mt-3", "variant": "tonal"},
                        "content": [
                            {
                                "component": "VCardTitle",
                                "props": {"class": "d-flex align-center"},
                                "content": [
                                    {
                                        "component": "VIcon",
                                        "props": {"color": "success", "class": "mr-2"},
                                        "text": "mdi-tune-variant",
                                    },
                                    {"component": "span", "text": "监控规则"},
                                ],
                            },
                            {"component": "VDivider"},
                            {
                                "component": "VCardText",
                                "content": [
                                    {
                                        "component": "VRow",
                                        "content": [
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 12, "md": 4},
                                                "content": [
                                                    {
                                                        "component": "VTextField",
                                                        "props": {
                                                            "model": "interval",
                                                            "label": "监控间隔（秒）",
                                                            "type": "number",
                                                            "min": 10,
                                                            "step": 1,
                                                            "prepend-inner-icon": "mdi-timer-outline",
                                                            "hint": "最小 10 秒",
                                                            "persistent-hint": True,
                                                        },
                                                    }
                                                ],
                                            },
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 12, "md": 8},
                                                "content": [
                                                    {
                                                        "component": "VTextField",
                                                        "props": {
                                                            "model": "tag_filter",
                                                            "label": "标签过滤",
                                                            "placeholder": "movie,tv",
                                                            "prepend-inner-icon": "mdi-tag-multiple-outline",
                                                            "hint": "逗号分隔；命中任一标签即整理，留空则处理全部任务",
                                                            "persistent-hint": True,
                                                            "clearable": True,
                                                        },
                                                    }
                                                ],
                                            },
                                        ],
                                    }
                                ],
                            },
                        ],
                    },
                    {
                        "component": "VCard",
                        "props": {"class": "mt-3", "variant": "tonal"},
                        "content": [
                            {
                                "component": "VCardTitle",
                                "props": {"class": "d-flex align-center"},
                                "content": [
                                    {
                                        "component": "VIcon",
                                        "props": {"color": "warning", "class": "mr-2"},
                                        "text": "mdi-bug-outline",
                                    },
                                    {"component": "span", "text": "调试设置"},
                                ],
                            },
                            {"component": "VDivider"},
                            {
                                "component": "VCardText",
                                "content": [
                                    {
                                        "component": "VRow",
                                        "content": [
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 12, "md": 4},
                                                "content": [
                                                    {
                                                        "component": "VSelect",
                                                        "props": {
                                                            "model": "log_level",
                                                            "label": "日志级别",
                                                            "prepend-inner-icon": "mdi-text-box-search-outline",
                                                            "items": [
                                                                {"title": level, "value": level}
                                                                for level in ("DEBUG", "INFO", "WARNING", "ERROR")
                                                            ],
                                                        },
                                                    }
                                                ],
                                            },
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 12, "md": 4},
                                                "content": [
                                                    {
                                                        "component": "VSwitch",
                                                        "props": {
                                                            "model": "enabled",
                                                            "label": "启用插件",
                                                            "color": "primary",
                                                            "inset": True,
                                                        },
                                                    }
                                                ],
                                            },
                                        ],
                                    },
                                    {
                                        "component": "VAlert",
                                        "props": {
                                            "type": "info",
                                            "variant": "tonal",
                                            "class": "mt-2",
                                            "text": (
                                                "qBittorrent 返回的内容路径必须在 MoviePilot 容器内可见。"
                                                "插件仅在整理成功入队后记录 hash，不会修改或删除种子。"
                                            ),
                                        },
                                    },
                                ],
                            },
                        ],
                    },
                ],
            }
        ], {
            "qb_url": self._DEFAULT_URL,
            "username": self._DEFAULT_USERNAME,
            "password": "",
            "interval": self._DEFAULT_INTERVAL,
            "tag_filter": "",
            "log_level": self._DEFAULT_LOG_LEVEL,
            "enabled": False,
        }

    @staticmethod
    def get_page() -> Optional[List[dict]]:
        return None

    def stop_service(self):
        """Ask an in-flight polling loop to stop at the next torrent boundary."""
        self._stop_event.set()

