# 发布清单

## 内容与权利

- [ ] 已确认参赛队、学校、赛区和竞赛允许当前公开时点；
- [ ] 未加入题面、官方附件、论文模板、第三方全文或字体；
- [ ] 未加入参赛论文/支撑包，或已单独确认它们的公开与许可安排；
- [ ] `LICENSE` 中的权利人表述符合发布者意愿；
- [ ] `CITATION.cff` 的作者信息已由发布者补充或确认。

## 技术门禁

```bash
python scripts/check_public_boundary.py
python scripts/check_repository_metadata.py
python scripts/smoke_synthetic.py
python -m pytest -q
python -m compileall -q c_grid scripts tests
git diff --check
git status --short
```

- [ ] 全部门禁通过；
- [ ] `git ls-files` 中没有被 `.gitignore` 隐藏但已跟踪的敏感文件；
- [ ] 最大跟踪文件和仓库总大小适合公开托管；
- [ ] 新公开远端为空仓库，没有导入私有历史；
- [ ] 首次推送前再次核对远端 URL、分支和提交 SHA。

创建远端、推送、发布 Release 和修改仓库可见性属于独立操作，应在明确确认后执行。
