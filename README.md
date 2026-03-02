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
- 文件 3（`20260302161726.txt`）：
  - `AOM-1`（设定温度+实际温度）
  - `AOM-2`（设定温度+实际温度）
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

## Grafana 仪表盘 JSON
新增文件：`grafana_dashboard_science_cavity.json`

导入方法：Grafana -> Dashboards -> New -> Import -> 上传该 JSON。

仪表盘内容：
- 4 张时间序列图（2x2）：AOM底座 / IPG外壳 / 真空腔 / AOM双通道（AOM-1 + AOM-2）
- 8 个 Stat 数据块（2x4）：
  - 4 个“当前温度”（AOM底座、IPG外壳、真空腔、AOM-2）
  - 4 个“过去1小时波动”（使用 `stddev(temperature)` 作为方差类指标）

## 常见问题：导入后没有让你选数据库 / 没有数据
如果你导入后没有弹出数据源选择，通常是 Dashboard JSON 没有 `__inputs` 定义，已在当前版本修复。

请这样检查：
1. 导入 `grafana_dashboard_science_cavity.json` 时，选择一个 **InfluxDB 类型**的数据源。
2. 在该数据源中确认 Database 填的是：`cavityfermi`。
3. 到 Explore 里先执行：
   - `SHOW MEASUREMENTS`
   - `SELECT * FROM "science_cavity" ORDER BY time DESC LIMIT 10`
4. 如果有数据但面板空白，把 Dashboard 右上角时间范围改为 `Last 24 hours` 再看。

## 单图版 Dashboard（来自你提供的 panel）
新增：`grafana_dashboard_temperature_cavity_setup.json`

包含 3 个面板：
- 1 个时间序列图：`Temperature Cavity Experiment`
- 1 个 Stat：当前温度（`last(value)`）
- 1 个 Stat：1小时温度方差（`variance(value)`）

查询基于：
- measurement: `supmea`
- tag: `name::tag = Temperature Cavity Setup`
