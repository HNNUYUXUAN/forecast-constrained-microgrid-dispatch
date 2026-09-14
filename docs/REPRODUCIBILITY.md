# 复现说明

## 层级 1：无官方数据的快速校验

```bash
python scripts/check_public_boundary.py
python scripts/smoke_synthetic.py
python -m pytest -q
```

这一层验证安装、核心优化器、结算器和信息截止测试，不验证官方数据结果。

## 层级 2：官方输入校验与集成测试

按 `c_grid/attachments/README.md` 放置文件后：

```bash
python scripts/verify_inputs.py
python -m pytest -q
```

`verify_inputs.py` 对九个文件逐一计算 SHA-256；缺失或不匹配时失败关闭。

## 层级 3：完整参考计算

```bash
python scripts/run_online_dispatch.py \
  --workers 4 \
  --output outputs/reproduction \
  --resume
python scripts/validate_online_results.py --run outputs/reproduction
python scripts/online_report.py --run outputs/reproduction --export
```

首次执行请使用新的输出目录。进程数只是并行策略数量，每个策略仍按日顺序推进。不要在未知退出状态后把不同输入或配置的断点混入同一目录；指纹门禁会拒绝明显不一致的恢复。

图形导出还要求用户在许可范围内安装 Times New Roman 与宋体，或设置 `MICROGRID_FONT_DIR` 指向字体目录。字体不随仓库分发。

## 结果口径

公开仓库只保留六个主场景的 `summary.json` 和派生图，不保留逐时段数组、Excel 结果和参赛提交件。完整复算后，应以当前输出目录中的 `manifest.json`、`completion.json` 和 `validation.json` 为准。

