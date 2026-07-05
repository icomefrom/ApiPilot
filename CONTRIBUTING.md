# Contributing

感谢你愿意参与 Bug Shoot。

## 开发流程

1. Fork 或拉取项目代码。
2. 基于 `main` 创建功能分支。
3. 本地完成开发和测试。
4. 提交 Pull Request，并说明变更动机、实现方式和验证结果。

## 本地启动

```bash
cp .env.example .env
docker compose up --build -d
```

## 提交建议

- 保持 PR 聚焦，一个 PR 解决一个明确问题。
- 涉及接口行为变化时，请同步更新 README 或相关文档。
- 涉及数据模型变化时，请提交 Django migration。
- 修复 bug 时，尽量补充对应测试或复现说明。

## Issue 建议

提交问题时请尽量包含：

- Bug Shoot 版本或提交号
- 部署方式：Docker Compose / 本地开发
- 操作步骤
- 期望结果
- 实际结果
- 相关日志或截图
