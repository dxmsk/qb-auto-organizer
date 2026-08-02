"""MoviePilot qBittorrent completed-download organizer plugin."""

from __future__ import annotations

import json
import math
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

import requests
from apscheduler.triggers.interval import IntervalTrigger

from app.chain.transfer import TransferChain
from app.core.event import Event, eventmanager
from app.db.downloadhistory_oper import DownloadHistoryOper
from app.log import logger
from app.plugins import _PluginBase
from app.schemas import FileItem, Response
from app.schemas.types import EventType


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
    plugin_version = "1.4.0"
    plugin_author = "Codex"
    author_url = "https://github.com/jxxghp/MoviePilot"
    plugin_config_prefix = "qbautoorganizer_"
    plugin_order = 25
    auth_level = 1

    _LEGACY_DATA_KEY = "processed_torrents"
    _BASELINE_FILE = "baseline_hashes.json"
    _PROCESSED_FILE = "processed_hashes.json"
    _RECORDS_FILE = "transfer_records.json"
    _RAPID_FILE = "rapid_uploaded_hashes.json"
    _LEGACY_RECORDS_FILE = "organize_records.json"
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
    _force_organize: bool = False
    _rapid_priority: bool = True
    _rapid_grace_seconds: int = 8
    _log_level: str = _DEFAULT_LOG_LEVEL

    def __init__(self):
        super().__init__()
        self._check_lock = threading.Lock()
        self._data_lock = threading.RLock()
        self._stop_event = threading.Event()
        self._baseline_ready = False
        self._known_hashes: Set[str] = set()
        self._new_hashes: Set[str] = set()
        self._submitted_hashes: Set[str] = set()
        self._pending_sources: Dict[str, str] = {}
        self._processed_hashes: Set[str] = set()
        self._rapid_uploaded_hashes: Set[str] = set()
        self._rapid_deferred_at: Dict[str, float] = {}
        self._baseline_path: Optional[Path] = None
        self._processed_path: Optional[Path] = None
        self._records_path: Optional[Path] = None
        self._rapid_path: Optional[Path] = None

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
        self._force_organize = self._as_bool(config.get("force_organize", False))
        self._rapid_priority = self._as_bool(config.get("rapid_priority", True))
        self._rapid_grace_seconds = self._normalize_rapid_grace(
            config.get("rapid_grace_seconds", 8)
        )
        configured_level = str(
            config.get("log_level") or self._DEFAULT_LOG_LEVEL
        ).upper()
        self._log_level = (
            configured_level
            if configured_level in self._LOG_LEVELS
            else self._DEFAULT_LOG_LEVEL
        )

        self._initialize_storage()
        self._new_hashes.clear()
        self._submitted_hashes.clear()
        self._pending_sources.clear()
        self._rapid_deferred_at.clear()
        self._stop_event.clear()
        if self._enabled:
            filter_text = ", ".join(sorted(self._tag_filters)) or "全部"
            self._log(
                "INFO",
                f"插件已启用：服务器={self._qb_url}，轮询间隔={self._interval}秒，"
                f"标签过滤={filter_text}，强制整理={'开启' if self._force_organize else '关闭'}",
            )
            if self._baseline_ready:
                self._log(
                    "INFO",
                    f"已从 baseline_hashes.json 加载固定基线，共 "
                    f"{len(self._known_hashes)} 个历史种子",
                )
            else:
                try:
                    self._capture_startup_baseline()
                except Exception as exc:
                    self._log(
                        "WARNING",
                        "首次基线建立失败，将在首次连接成功时建立基线且不处理当时已存在的种子："
                        f"{self._safe_error(exc)}",
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
                "auth": "bear",
                "summary": "测试 qBittorrent 连接",
                "description": "登录 qBittorrent Web API 并返回服务端版本。",
            },
            {
                "path": "/records",
                "endpoint": self.get_records,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取整理记录",
                "description": "分页返回 qB 自动整理成功记录。",
            },
            {
                "path": "/baseline/reset",
                "endpoint": self.reset_baseline,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "重置 qB 种子基线",
                "description": "删除持久化基线，并在下次插件启动或重载时重新建立。",
            },
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

    def get_records(self, page: int = 1, page_size: int = 20) -> Response:
        """Return persisted organize records to the Vue status page."""
        page = max(1, int(page or 1))
        page_size = min(100, max(1, int(page_size or 20)))
        records = self._load_records()
        total = len(records)
        pages = max(1, math.ceil(total / page_size))
        page = min(page, pages)
        start = (page - 1) * page_size
        return Response(
            success=True,
            data={
                "records": records[start:start + page_size],
                "total": total,
                "page": page,
                "page_size": page_size,
                "pages": pages,
            },
        )

    def reset_baseline(self) -> Response:
        """Delete the persisted baseline without changing this running instance."""
        try:
            with self._data_lock:
                if self._baseline_path and self._baseline_path.exists():
                    self._baseline_path.unlink()
            self._log(
                "WARNING",
                "固定基线已重置；当前运行期仍沿用内存基线，下次插件启动或配置重载时重新扫描",
            )
            return Response(
                success=True,
                message="基线已重置，下次插件启动或配置重载时将重新扫描现有种子",
            )
        except Exception as exc:
            message = self._safe_error(exc)
            self._log("ERROR", f"重置固定基线失败：{message}")
            return Response(success=False, message=f"重置基线失败：{message}")

    def _rapid_plugin(self):
        """Find the optional rapid-upload plugin without importing its code."""
        try:
            from app.core.plugin import PluginManager

            plugins = getattr(PluginManager(), "running_plugins", {}) or {}
            plugin = plugins.get("Qb115RapidUpload")
            if plugin is not None:
                return plugin
            for plugin_id, candidate in plugins.items():
                if str(plugin_id).lower().startswith("qb115rapidupload"):
                    return candidate
        except Exception:
            return None
        return None

    def _rapid_action(self, torrent_hash: str, name: str) -> str:
        """Return ``proceed``, ``defer`` or ``skip`` for organizer submission."""
        if not self._rapid_priority:
            return "proceed"
        if torrent_hash in self._rapid_uploaded_hashes:
            return "skip"
        plugin = self._rapid_plugin()
        getter = getattr(plugin, "get_coordination_status", None) if plugin else None
        if not callable(getter):
            self._rapid_deferred_at.pop(torrent_hash, None)
            return "proceed"
        try:
            payload = getter(torrent_hash) or {}
            status = str(payload.get("status") or "UNKNOWN").upper()
        except Exception as exc:
            self._log("DEBUG", f"读取秒传联动状态失败，继续整理：{torrent_hash[:12]} - {exc}")
            return "proceed"
        if status in {"WATCHING", "WAITING", "PROCESSING", "RETRY_WAIT"}:
            self._rapid_deferred_at.setdefault(torrent_hash, time.monotonic())
            self._log("INFO", f"秒传优先，暂缓整理：{name} ({torrent_hash[:12]})，状态={status}")
            return "defer"
        if status == "SUCCESS":
            self._rapid_uploaded_hashes.add(torrent_hash)
            self._write_json(self._rapid_path, sorted(self._rapid_uploaded_hashes))
            self._rapid_deferred_at.pop(torrent_hash, None)
            self._log("INFO", f"115 秒传已成功，跳过 MoviePilot 整理：{name} ({torrent_hash[:12]})")
            return "skip"
        if status == "UNKNOWN":
            started = self._rapid_deferred_at.setdefault(torrent_hash, time.monotonic())
            if time.monotonic() - started < self._rapid_grace_seconds:
                self._log("DEBUG", f"等待秒传插件登记任务：{name} ({torrent_hash[:12]})")
                return "defer"
        self._rapid_deferred_at.pop(torrent_hash, None)
        return "proceed"

    def check_completed_torrents(self) -> Dict[str, Any]:
        """Discover torrents absent from the fixed baseline and organize them."""
        if not self._enabled or self._stop_event.is_set():
            return {"checked": 0, "queued": 0, "failed": 0}
        if not self._check_lock.acquire(blocking=False):
            self._log("WARNING", "上一轮检测仍在运行，本轮跳过")
            return {"checked": 0, "queued": 0, "failed": 0, "busy": True}

        checked = queued = failed = 0
        try:
            self._log("DEBUG", "开始查询 qBittorrent 全部任务")
            torrents = self._get_all_torrents()

            if not self._baseline_ready:
                self._set_baseline(torrents)
                self._log(
                    "INFO",
                    f"已建立启动基线，共记录 {len(self._known_hashes)} 个历史种子；"
                    "本轮不触发整理",
                )
                return {"checked": len(torrents), "queued": 0, "failed": 0}

            current_hashes = {
                str(item.get("hash") or "").strip().lower()
                for item in torrents
                if item.get("hash")
            }
            discovered = current_hashes - self._known_hashes
            newly_observed = discovered - self._new_hashes
            self._new_hashes.update(discovered)
            if newly_observed:
                self._log("INFO", f"发现 {len(newly_observed)} 个固定基线外的新种子")

            removed = self._new_hashes - current_hashes
            if removed:
                self._new_hashes.difference_update(removed)
                self._submitted_hashes.difference_update(removed)
                for torrent_hash in removed:
                    self._pending_sources.pop(torrent_hash, None)

            self._log(
                "DEBUG",
                f"qBittorrent 返回 {len(torrents)} 个任务，启动后新增 "
                f"{len(self._new_hashes)} 个，已成功整理 {len(self._processed_hashes)} 个",
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
                if torrent_hash not in self._new_hashes:
                    self._log("DEBUG", f"启动前历史任务，跳过：{name} ({torrent_hash})")
                    continue
                if torrent_hash in self._processed_hashes:
                    self._log("DEBUG", f"任务已处理，跳过：{name} ({torrent_hash})")
                    continue
                if torrent_hash in self._rapid_uploaded_hashes:
                    self._log("DEBUG", f"任务已由 115 秒传处理，跳过整理：{name} ({torrent_hash})")
                    continue
                if torrent_hash in self._submitted_hashes:
                    self._log("DEBUG", f"任务已提交整理，等待结果：{name} ({torrent_hash})")
                    continue
                if not self._is_completed(torrent):
                    self._log("DEBUG", f"新增任务尚未下载完成：{name} ({torrent_hash})")
                    continue

                torrent_tags = self._parse_tags(torrent.get("tags"))
                if self._tag_filters and not self._tag_filters.intersection(torrent_tags):
                    self._log(
                        "DEBUG",
                        f"任务标签不匹配，跳过：{name}；任务标签="
                        f"{', '.join(sorted(torrent_tags)) or '无'}",
                    )
                    continue
                if not self._force_organize and "已整理" in torrent_tags:
                    self._log(
                        "INFO",
                        f"任务带有“已整理”标签，普通模式跳过：{name} ({torrent_hash})",
                    )
                    continue

                source_path = self._torrent_content_path(torrent)
                if not source_path:
                    failed += 1
                    self._log("ERROR", f"无法确定任务内容路径：{name} ({torrent_hash})")
                    continue

                rapid_action = self._rapid_action(torrent_hash, name)
                if rapid_action == "defer":
                    continue
                if rapid_action == "skip":
                    continue

                self._log(
                    "INFO",
                    f"发现新的已完成任务：{name} ({torrent_hash})，路径={source_path}",
                )
                self._submitted_hashes.add(torrent_hash)
                self._pending_sources[torrent_hash] = source_path
                try:
                    success, detail = self._enqueue_transfer(
                        torrent=torrent,
                        torrent_hash=torrent_hash,
                        source_path=source_path,
                    )
                except Exception as exc:
                    success, detail = False, self._safe_error(exc)

                if not success:
                    self._submitted_hashes.discard(torrent_hash)
                    self._pending_sources.pop(torrent_hash, None)
                    failed += 1
                    self._log(
                        "ERROR",
                        f"触发 MoviePilot 整理失败：{name} ({torrent_hash}) - {detail}",
                    )
                    continue

                queued += 1
                self._log(
                    "INFO",
                    f"已加入 MoviePilot 整理队列，等待成功事件：{name} ({torrent_hash})",
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

    def _get_all_torrents(self) -> List[dict]:
        with self._qb_session() as session:
            response = session.get(
                self._api_url("/api/v2/torrents/info"),
                timeout=self._REQUEST_TIMEOUT,
            )
            self._raise_for_status(response, "查询种子任务")
            return self._decode_torrent_list(response)

    def _capture_startup_baseline(self):
        torrents = self._get_all_torrents()
        self._set_baseline(torrents)
        self._log(
            "INFO",
            f"启动基线建立完成：已记录 {len(self._known_hashes)} 个现有种子，"
            "这些种子不会触发整理",
        )

    def _set_baseline(self, torrents: List[dict]):
        self._known_hashes = {
            str(item.get("hash") or "").strip().lower()
            for item in torrents
            if item.get("hash")
        }
        self._new_hashes.clear()
        self._write_json(self._baseline_path, sorted(self._known_hashes))
        self._baseline_ready = True

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
            manual=self._force_organize,
            force=self._force_organize,
            background=True,
        )
        return bool(state), str(message or "")

    @eventmanager.register(EventType.TransferComplete)
    def on_transfer_complete(self, event: Event):
        """Persist a record only after MoviePilot reports a real transfer success."""
        if not self._enabled or not event or not event.event_data:
            return
        event_data = event.event_data
        torrent_hash = str(event_data.get("download_hash") or "").strip().lower()
        if not torrent_hash or torrent_hash not in self._submitted_hashes:
            return

        try:
            record = self._build_organize_record(torrent_hash, event_data)
            with self._data_lock:
                records = self._load_records_unlocked()
                existing_index = next(
                    (
                        index
                        for index, item in enumerate(records)
                        if str(item.get("hash") or "").lower() == torrent_hash
                    ),
                    None,
                )
                if existing_index is None:
                    records.insert(0, record)
                else:
                    records[existing_index] = record
                self._write_json(self._records_path, records)

                self._processed_hashes.add(torrent_hash)
                self._write_json(
                    self._processed_path, sorted(self._processed_hashes)
                )

            self._submitted_hashes.discard(torrent_hash)
            self._new_hashes.discard(torrent_hash)
            self._pending_sources.pop(torrent_hash, None)
            self._log(
                "INFO",
                f"整理成功并写入记录：{record['media_name']} ({torrent_hash}) -> "
                f"{record['target_path']}",
            )
        except Exception as exc:
            self._log(
                "ERROR",
                f"写入整理成功记录失败：{torrent_hash} - {self._safe_error(exc)}",
            )

    @eventmanager.register(EventType.TransferFailed)
    def on_transfer_failed(self, event: Event):
        """Allow a failed submitted torrent to be retried on a later poll."""
        if not event or not event.event_data:
            return
        torrent_hash = str(
            event.event_data.get("download_hash") or ""
        ).strip().lower()
        if torrent_hash not in self._submitted_hashes:
            return
        self._submitted_hashes.discard(torrent_hash)
        self._pending_sources.pop(torrent_hash, None)
        self._log("WARNING", f"整理失败，后续轮询将重试：{torrent_hash}")

    def _build_organize_record(
        self, torrent_hash: str, event_data: dict
    ) -> Dict[str, str]:
        fileitem = event_data.get("fileitem")
        mediainfo = event_data.get("mediainfo")
        meta = event_data.get("meta")
        transferinfo = event_data.get("transferinfo")

        source_path = self._pending_sources.get(torrent_hash) or str(
            getattr(fileitem, "path", "") or ""
        )
        target_path = ""
        if transferinfo:
            target_diritem = getattr(transferinfo, "target_diritem", None)
            target_item = getattr(transferinfo, "target_item", None)
            target_path = str(
                getattr(target_diritem, "path", None)
                or getattr(target_item, "path", None)
                or ""
            )
            if not target_path:
                target_files = getattr(transferinfo, "file_list_new", None) or []
                target_path = str(target_files[0]) if target_files else ""

        media_name = str(
            getattr(mediainfo, "title", None)
            or getattr(meta, "name", None)
            or getattr(fileitem, "name", None)
            or Path(source_path).name
            or torrent_hash
        )
        media_type_value = getattr(mediainfo, "type", None)
        media_type = str(
            getattr(media_type_value, "value", media_type_value) or "未知"
        )
        if media_type not in {"电影", "电视剧"}:
            media_type = "电视剧" if media_type.lower() in {"tv", "show"} else "电影"

        poster_url = ""
        poster_getter = getattr(mediainfo, "get_poster_image", None)
        if callable(poster_getter):
            try:
                poster_url = str(poster_getter() or "")
            except Exception:
                poster_url = ""
        if not poster_url:
            poster_url = str(getattr(mediainfo, "poster_path", None) or "")

        return {
            "hash": torrent_hash,
            "media_name": media_name,
            "poster_url": poster_url,
            "organized_at": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
            "source_path": source_path,
            "target_path": target_path,
            "media_type": media_type,
        }

    def _initialize_storage(self):
        data_path = self.get_data_path()
        data_path.mkdir(parents=True, exist_ok=True)
        self._baseline_path = data_path / self._BASELINE_FILE
        self._processed_path = data_path / self._PROCESSED_FILE
        self._records_path = data_path / self._RECORDS_FILE
        self._rapid_path = data_path / self._RAPID_FILE

        baseline = self._read_json(self._baseline_path, None)
        if isinstance(baseline, (list, dict)):
            self._known_hashes = {
                str(item).strip().lower()
                for item in baseline
                if str(item).strip()
            }
            self._baseline_ready = True
        else:
            if self._baseline_path.exists():
                self._log(
                    "WARNING",
                    "baseline_hashes.json 内容无效，将在连接 qBittorrent 成功后重新建立固定基线",
                )
            self._known_hashes = set()
            self._baseline_ready = False

        stored = self._read_json(self._processed_path, [])
        if isinstance(stored, dict):
            stored = list(stored)
        self._processed_hashes = {
            str(item).strip().lower() for item in stored if str(item).strip()
        }

        rapid_stored = self._read_json(self._rapid_path, [])
        if isinstance(rapid_stored, dict):
            rapid_stored = list(rapid_stored)
        self._rapid_uploaded_hashes = {
            str(item).strip().lower() for item in rapid_stored if str(item).strip()
        }
        if not self._rapid_path.exists():
            self._write_json(self._rapid_path, sorted(self._rapid_uploaded_hashes))

        # Migrate dedup hashes written by v1.0.0 from MoviePilot's plugin DB.
        try:
            legacy = self.get_data(self._LEGACY_DATA_KEY)
            legacy_hashes = list(legacy) if isinstance(legacy, (dict, list)) else []
            before = len(self._processed_hashes)
            self._processed_hashes.update(
                str(item).strip().lower()
                for item in legacy_hashes
                if str(item).strip()
            )
            if len(self._processed_hashes) != before:
                self._write_json(self._processed_path, sorted(self._processed_hashes))
        except Exception as exc:
            self._log("WARNING", f"迁移旧版 hash 数据失败：{self._safe_error(exc)}")

        if not self._processed_path.exists():
            self._write_json(self._processed_path, sorted(self._processed_hashes))
        if not self._records_path.exists():
            legacy_records_path = data_path / self._LEGACY_RECORDS_FILE
            legacy_records = self._read_json(legacy_records_path, [])
            self._write_json(
                self._records_path,
                legacy_records if isinstance(legacy_records, list) else [],
            )

    def _load_records(self) -> List[dict]:
        with self._data_lock:
            return self._load_records_unlocked()

    def _load_records_unlocked(self) -> List[dict]:
        records = self._read_json(self._records_path, [])
        if not isinstance(records, list):
            return []
        return sorted(
            (item for item in records if isinstance(item, dict)),
            key=lambda item: str(item.get("organized_at") or ""),
            reverse=True,
        )

    @staticmethod
    def _read_json(path: Optional[Path], default: Any) -> Any:
        if not path or not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return default

    @staticmethod
    def _write_json(path: Optional[Path], value: Any):
        if not path:
            raise RuntimeError("插件数据路径尚未初始化")
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(f"{path.name}.tmp")
        temp_path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temp_path.replace(path)

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
            progress_complete = float(torrent.get("progress") or 0) >= 0.999999
        except (TypeError, ValueError):
            return False
        if not progress_complete:
            return False

        state = str(torrent.get("state") or "").strip().lower()
        if not state:
            # Older/custom qB-compatible APIs may omit state; progress remains usable.
            return True
        return state == "uploading" or state.endswith("up")

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
    def _normalize_rapid_grace(value: Any) -> int:
        try:
            return min(60, max(1, int(value or 8)))
        except (TypeError, ValueError):
            return 8

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

    @staticmethod
    def get_render_mode() -> Tuple[str, str]:
        """Use MoviePilot's supported Vue module-federation renderer."""
        return "vue", "dist/assets"

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
                                    },
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
                                                "props": {"cols": 12, "md": 4},
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
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 12, "md": 4},
                                                "content": [
                                                    {
                                                        "component": "VSwitch",
                                                        "props": {
                                                            "model": "force_organize",
                                                            "label": "强制整理",
                                                            "color": "warning",
                                                            "inset": True,
                                                            "hint": "开启后传递 manual=True、force=True，忽略“已整理”标签和历史整理记录",
                                                            "persistent-hint": True,
                                                        },
                                                    }
                                                ],
                                            },
                                        ],
                                    },
                                    {
                                        "component": "VRow",
                                        "props": {"class": "mt-2"},
                                        "content": [
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 12, "md": 4},
                                                "content": [
                                                    {
                                                        "component": "VSwitch",
                                                        "props": {
                                                            "model": "rapid_priority",
                                                            "label": "115 秒传优先",
                                                            "color": "success",
                                                            "inset": True,
                                                            "hint": "秒传处理中暂缓整理；秒传成功后跳过整理；失败或超时后恢复整理",
                                                            "persistent-hint": True,
                                                        },
                                                    }
                                                ],
                                            },
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 12, "md": 4},
                                                "content": [
                                                    {
                                                        "component": "VTextField",
                                                        "props": {
                                                            "model": "rapid_grace_seconds",
                                                            "label": "秒传登记等待（秒）",
                                                            "type": "number",
                                                            "min": 1,
                                                            "max": 60,
                                                            "hint": "秒传插件尚未登记 qB 任务时的短暂等待窗口",
                                                            "persistent-hint": True,
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
                                            "color": "error",
                                            "variant": "tonal",
                                            "prepend-icon": "mdi-database-refresh-outline",
                                        },
                                        "text": "重置基线",
                                        "events": {
                                            "click": {
                                                "api": "plugin/QbAutoOrganizer/baseline/reset",
                                                "method": "post",
                                                "confirm": "确认删除固定基线？下次启动或配置重载会把当前全部种子作为历史种子。",
                                            }
                                        },
                                    },
                                    {
                                        "component": "span",
                                        "props": {"class": "text-caption text-medium-emphasis ml-3"},
                                        "text": "删除后不会立即改变当前运行期；下次启动或重载时重新扫描。",
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
                                                "插件启动时忽略全部现有种子，仅在收到整理成功事件后记录 hash，"
                                                "且不会修改或删除种子。强制整理只对启动后新增的种子生效。"
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
            "force_organize": False,
            "rapid_priority": True,
            "rapid_grace_seconds": 8,
            "log_level": self._DEFAULT_LOG_LEVEL,
            "enabled": False,
        }

    @staticmethod
    def get_page() -> List[dict]:
        """The Vue renderer loads the exposed Page single-file component."""
        return []

    def stop_service(self):
        """Ask an in-flight polling loop to stop at the next torrent boundary."""
        self._stop_event.set()
