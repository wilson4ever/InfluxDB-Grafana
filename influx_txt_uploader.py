#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将温控软件持续写入的 TXT 数据上传到 InfluxDB（1.x HTTP API）。
兼容 Python 3.8（Windows 7 可用）。
"""

import argparse
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from urllib import parse, request


DEFAULT_CONFIG = {
    "influx": {
        "host": "192.168.1.100",
        "port": 8086,
        "database": "cavityfermi",
        "username": "",
        "password": "",
        "ssl": False,
        "timeout_seconds": 8,
    },
    "measurement": "science_cavity",
    "poll_interval_seconds": 60,
    "files": [
        {
            "path": "20260302161726.txt",
            "source": "vacuum_aom2",
            "channels": [
                {"name": "vacuum_cavity", "set_idx": 0, "actual_idx": 1},
                {"name": "AOM-2", "set_idx": 2, "actual_idx": 3},
            ],
        },
        {
            "path": "20260228153635.txt",
            "source": "aom1_ipg",
            "channels": [
                {"name": "AOM-1", "set_idx": 0, "actual_idx": 1},
                {"name": "ipg_shell", "set_idx": 2, "actual_idx": 3},
            ],
        },
    ],
}


def ensure_config(config_path: Path) -> Dict:
    if not config_path.exists():
        config_path.write_text(
            json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print("已创建配置文件:", config_path)
        print("请先检查 NAS InfluxDB 地址/账号，再重新运行。")
        raise SystemExit(0)
    return json.loads(config_path.read_text(encoding="utf-8"))


def load_state(state_path: Path) -> Dict[str, int]:
    if not state_path.exists():
        return {}
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state_path: Path, state: Dict[str, int]) -> None:
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_timestamp(date_s: str, time_s: str) -> int:
    dt = datetime.strptime("%s %s" % (date_s, time_s), "%Y/%m/%d %H:%M:%S")
    return int(dt.timestamp() * 1_000_000_000)


def escape_tag(value: str) -> str:
    return value.replace("\\", "\\\\").replace(" ", "\\ ").replace(",", "\\,").replace("=", "\\=")


def parse_line_to_points(
    raw_line: str,
    file_cfg: Dict,
    measurement: str,
) -> Tuple[Optional[int], List[str]]:
    line = raw_line.strip()
    if not line:
        return None, []

    # 兼容两种格式：
    # 1) 正常空格分隔："3158 2026/3/2 16:18:02 25.01 20.63 20.02 26.2"
    # 2) 时间戳和第一列黏连："3158 2026/3/2 16:18:0225.01 20.63 20.02 26.2"
    m = re.match(r"^\s*(\d+)\s+(\d{4}/\d{1,2}/\d{1,2})\s+(\d{1,2}:\d{2}:\d{2})(.*)$", line)
    if not m:
        return None, []

    try:
        row_index = int(m.group(1))
        timestamp_ns = parse_timestamp(m.group(2), m.group(3))
    except Exception:
        return None, []

    tail = m.group(4)
    value_tokens = re.findall(r"[-+]?\d+(?:\.\d+)?", tail)
    if len(value_tokens) < 2:
        return None, []

    points: List[str] = []
    source = escape_tag(file_cfg["source"])

    for ch in file_cfg.get("channels", []):
        channel = escape_tag(ch["name"])
        for role, idx_key, old_col_key in (("setpoint", "set_idx", "set_col"), ("actual", "actual_idx", "actual_col")):
            idx = ch.get(idx_key)
            if idx is None and ch.get(old_col_key) is not None:
                # 兼容旧配置：整行 split 列号 -> 数值区 index
                idx = int(ch[old_col_key]) - 3
            if idx is None or idx < 0 or idx >= len(value_tokens):
                continue
            try:
                temp = float(value_tokens[idx])
            except ValueError:
                continue
            role_escaped = escape_tag(role)
            lp = "%s,source=%s,channel=%s,temp_role=%s temperature=%s %d" % (
                measurement,
                source,
                channel,
                role_escaped,
                temp,
                timestamp_ns,
            )
            points.append(lp)

    return row_index, points


def extract_new_points(
    txt_path: Path,
    file_cfg: Dict,
    measurement: str,
    last_row: int,
) -> Tuple[int, List[str]]:
    if not txt_path.exists():
        print("文件不存在，跳过:", txt_path)
        return last_row, []

    new_last = last_row
    payload_lines: List[str] = []

    with txt_path.open("r", encoding="utf-8", errors="ignore") as f:
        for raw_line in f:
            row_index, points = parse_line_to_points(raw_line, file_cfg, measurement)
            if row_index is None:
                continue
            if row_index <= last_row:
                continue
            payload_lines.extend(points)
            if row_index > new_last:
                new_last = row_index

    return new_last, payload_lines


def post_to_influx(influx_cfg: Dict, payload_lines: Iterable[str]) -> None:
    lines = [x for x in payload_lines if x]
    if not lines:
        return

    scheme = "https" if influx_cfg.get("ssl") else "http"
    params = {"db": influx_cfg["database"]}
    if influx_cfg.get("username"):
        params["u"] = influx_cfg["username"]
    if influx_cfg.get("password"):
        params["p"] = influx_cfg["password"]
    query = parse.urlencode(params)
    url = "%s://%s:%s/write?%s" % (
        scheme,
        influx_cfg["host"],
        influx_cfg["port"],
        query,
    )

    body = "\n".join(lines).encode("utf-8")
    req = request.Request(url=url, data=body, method="POST")
    req.add_header("Content-Type", "text/plain; charset=utf-8")

    timeout = float(influx_cfg.get("timeout_seconds", 8))
    with request.urlopen(req, timeout=timeout) as resp:
        status = getattr(resp, "status", resp.getcode())
        if status >= 300:
            raise RuntimeError("InfluxDB 写入失败，HTTP %s" % status)


def run_once(config: Dict, state: Dict[str, int], state_path: Path) -> None:
    measurement = config.get("measurement", "science_cavity")
    all_lines: List[str] = []
    next_state = dict(state)

    for file_cfg in config.get("files", []):
        path = Path(file_cfg["path"]).resolve()
        key = str(path)
        last_row = int(state.get(key, -1))
        new_last, points = extract_new_points(path, file_cfg, measurement, last_row)
        if points:
            all_lines.extend(points)
        next_state[key] = new_last

    if all_lines:
        post_to_influx(config["influx"], all_lines)
        save_state(state_path, next_state)
        state.clear()
        state.update(next_state)
        print("上传成功，新增点数:", len(all_lines))
    else:
        print("没有新数据")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="将温控 TXT 增量上传到 InfluxDB")
    p.add_argument("--config", default="uploader_config.json", help="配置文件路径")
    p.add_argument("--state", default="uploader_state.json", help="状态文件路径")
    p.add_argument("--once", action="store_true", help="仅执行一次")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    config_path = Path(args.config).resolve()
    state_path = Path(args.state).resolve()

    config = ensure_config(config_path)
    state = load_state(state_path)

    interval = int(config.get("poll_interval_seconds", 60))

    while True:
        try:
            run_once(config, state, state_path)
        except Exception as e:
            print("上传失败:", e)

        if args.once:
            break
        time.sleep(max(interval, 1))


if __name__ == "__main__":
    main()
