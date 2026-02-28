# TXT -> InfluxDB 上传脚本

本仓库提供 `influx_txt_uploader.py`，用于持续读取温控软件生成的 TXT 文件，把**未上传过的新行**转换成 InfluxDB line protocol 后，通过 HTTP 写入 NAS 上的 InfluxDB。

## 适配你的需求
- 数据库：`cavityfermi`
- measurement：`science_cavity`
- 文件 1（`20260228153635.txt`）：
  - `aom_base`（第1通道：设定温度+实际温度）
  - `ipg_shell`（第2通道：设定温度+实际温度）
- 文件 2（`20260228154001.txt`）：
  - `vacuum_cavity`（设定温度+实际温度）
- field 统一用：`temperature`
- tag 区分：`source`、`channel`、`temp_role(setpoint/actual)`

## 首次运行
在 TXT 文件所在目录执行：

```bash
python influx_txt_uploader.py --once
```

首次运行会自动生成 `uploader_config.json`，请修改 InfluxDB 地址等配置后再次运行。

## 持续运行（每分钟轮询）

```bash
python influx_txt_uploader.py
```

轮询间隔默认 60 秒，可在 `uploader_config.json` 里改 `poll_interval_seconds`。

## 状态文件
脚本会写入 `uploader_state.json`，记录每个文件最后上传的行号（索引列），避免重复上传。

## Windows 7 后台运行建议
可以做一个 `.bat`：

```bat
@echo off
cd /d %~dp0
python influx_txt_uploader.py >> uploader.log 2>&1
```

双击后常驻运行并写日志到 `uploader.log`。
