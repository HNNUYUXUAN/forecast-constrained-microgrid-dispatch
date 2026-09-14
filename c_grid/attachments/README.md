# 官方输入放置目录

本目录只保留说明文件，官方输入不进入 Git。

请从竞赛官方渠道取得 2026 C 题材料，并保持下列结构：

```text
c_grid/attachments/
├── 附件1.xlsx
├── 附件2.xlsx
├── 附件3.xlsx
├── 附件4.xlsx
└── 附件5/
    ├── result1.xlsx
    ├── result2.xlsx
    ├── result3.xlsx
    ├── result4-2.xlsx
    └── result4-3.xlsx
```

随后在仓库根目录执行 `python scripts/verify_inputs.py`。只有全部 SHA-256 与 `data/INPUTS.sha256` 一致时，才运行数据集成测试和完整年度计算。

