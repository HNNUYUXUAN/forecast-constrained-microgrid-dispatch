# 贡献指南

感谢参与。为了让数值结果仍可追溯，请把模型变更、数据边界和结果变化一起说明。

## 开发流程

1. 创建独立分支。
2. 安装 `.[test,reproduce]` 依赖。
3. 修改代码并补充最小回归测试。
4. 运行以下门禁：

```bash
python scripts/check_public_boundary.py
python scripts/check_repository_metadata.py
python scripts/smoke_synthetic.py
python -m pytest -q
```

5. 在 Pull Request 中写明假设、输入范围、随机性、计算资源和结果差异。

不要提交官方附件、题面/模板、第三方全文、字体、账号凭据、大体积运行数组或个人机器路径。若变更依赖官方数据，请同时给出输入 SHA-256，并保证无输入时的单元测试仍可运行。
