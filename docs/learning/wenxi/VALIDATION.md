# 学习材料验证记录

验证日期：2026-10-22（Asia/Shanghai）。本记录仅描述学习材料的生成与检查，不表示问溪应用已完成集成验收。

## 内容与来源

- 4 个章节组，65 节；其中六个实战模块各 8 节，面试与自测 8 题。
- 183 处源码步骤，全部与当前仓库对应行号逐字一致；每段 5–15 行。
- 156 个被引用文件纳入只读源码快照及 SHA-256 manifest。
- 上游 JSON Schema、章节锚点唯一性、概念开场、解释长度、关键要点与本地链接检查通过。

## 实际执行

以下命令从仓库根目录运行，均通过：

```powershell
.\.venv\Scripts\python.exe .artifacts/wenxi-learning/assemble.py
.\.venv\Scripts\python.exe docs/learning/wenxi/build.py
.\.venv\Scripts\python.exe docs/learning/wenxi/build.py --check
.\.venv\Scripts\python.exe -m ruff check docs/learning/wenxi/build.py
.\.venv\Scripts\python.exe -m ruff format --check docs/learning/wenxi/build.py
node .artifacts/wenxi-learning/browser-check.cjs
git diff --check -- docs/learning/wenxi
```

`.artifacts/` 下的组装脚本和浏览器检查报告保留在本地工作区，不属于需要分发的阅读文件。日常复核可以使用本目录 `build.py --check`。

浏览器检查使用临时无头 Microsoft Edge 155.0.4283.62，覆盖：

- HTTP 完整加载；按钮与键盘翻页；搜索结果跳转。
- 学习进度与暗色主题在刷新后恢复。
- 代码展开；源码快照链接与指定行定位；全部本地链接解析。
- 全部 Mermaid 图的解析与渲染；面试答案展开与键盘操作。
- 1440×1000 桌面、390×844 移动布局与菜单；人工查看截图。
- 打印样式显示全部章节；断网环境 `file://` 直接打开并渲染图表。
- 页面 JavaScript 错误为 0；外部资源请求为 0。

## 改动边界与未运行项

本次正式产物位于 `docs/learning/wenxi/`，属于可重建的学习快照；未修改业务实现、领域术语、运行状态或安全规则。开始与结束的 Git status 比较仅新增 `docs/learning/`，原有工作区修改保留。

没有新增或修改业务测试。未运行后端完整 pytest、前端应用完整质量门禁、PostgreSQL/Redis/Milvus 集成、在线模型、live RAG 评测或迁移；本次变更不涉及这些实现，离线网页验证不能替代其证据。

无需同步业务 Contract、数据库迁移或 RAG 评测资产；根 README、CONTEXT、ADR 与 Runbook 的正式定义未变。学习数据使用的上游 schema 单独保存在本目录，未混入业务 Contract。
