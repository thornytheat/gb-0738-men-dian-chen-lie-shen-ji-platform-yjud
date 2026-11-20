# 门店陈列审计台

连锁酒水巡店员在同一份巡检档件中核对门店时区、当时生效的货架陈列图、原始照片和清点表。面板显示抽样缺口、逐柜处置和罚额。复核员可提交异议材料并留下改判记录。

## 启动与试跑

```bash
docker compose up --build
```

浏览 [工作台](http://localhost:18427/)。选择「十一月 · 巡店原件」，保持目标 18 柜并运行。点击严重度矩阵的数字，按店组和状态查看柜位。点击柜位处置行，查看同柜命中的候选罚则及实际执行额。照片证据页可打开通过校验的原件，结算页可以追到隔离原值和源行。

原件结果为抽中 17 柜，8 合规、3 违规、3 待证、3 隔离，原罚额 295 元。近郊组缺 1 个名册柜，保持缺额。另有「核验副本」，目标 18 柜全数合规。相同档件和抽样目标再次运行会取回同一批次及其异议记录。

可在「异议复核」选 `002:A03`，提交发起事件，再录入复核决定。部分减免 6000 分后，原罚额仍为 295 元、净罚额为 235 元。工具条可下载一份 JSON 证据。

```bash
docker compose exec -T app pytest -q
```

本地可用 Python 3.12 运行。

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m pytest -q
uvicorn app.main:app --port 18427
```

Compose 使用 `audit-data` 命名卷；本地数据库默认为 `data/audits.sqlite3`。可通过 `SHELF_DB_PATH` 指定新数据库。

## 七个业务入口

| 模块 | 入口 | 动作 |
|---|---|---|
| 巡店收件 | `GET /api/intake` | 解码、校验柜位和门店、归一巡检时刻 |
| 货架版本 | `GET /api/plans` | 按有效到访时点匹配规则、登记重叠和 SKU 旧名 |
| 照片证据 | `GET /api/photos` | 读取原件、核验拍摄窗口、发现跨柜复用和清点矛盾 |
| 抽样覆盖 | `GET /api/coverage` | 按店组分配和确定性抽取柜位、保留未填额 |
| 罚则裁决 | `GET /api/penalties` | 区分缺图、缺品及无法裁决，择一执行罚则 |
| 结算勾稽 | `GET /api/settlement`、`POST /api/settlement/runs` | 对账预览或生成可复用的结算批次 |
| 异议复核 | `GET /api/appeals/{run_id}`、`POST /api/appeals/{run_id}/events` | 查看并追加复核事件，核算净额 |

预检接口接受 `dataset=field` 或 `dataset=reference`，以及可选 `sample_size`。运行提交同名 JSON 字段。使用 `GET /api/settlement/runs/{run_id}` 读取批次，使用 `GET /api/appeals/{run_id}/export` 下载证据。接口目录位于 `/docs`。

[字段与规则](docs/DATA-DICTIONARY.md) · [测试证据](docs/DEPTH.md)
