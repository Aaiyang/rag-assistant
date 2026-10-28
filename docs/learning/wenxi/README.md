# 问溪 Wenxi 项目学习手册

本目录是使用 [xWebt/project-learning-skill](https://github.com/xWebt/project-learning-skill) 生成的中文学习快照：全部模块、标准深度，附面试与自测。内容对应生成时的工作区，包含未提交改动；源码变动后需要重新核对。

## 打开阅读

直接用浏览器打开本目录的 `index.html` 即可离线阅读。需要保持整个目录及 `vendor/` 文件完整。

也可以从**仓库根目录**启动仅供本机使用的静态服务器：

```powershell
.\.venv\Scripts\python.exe -m http.server 8420 --bind 127.0.0.1 --directory docs/learning/wenxi
```

然后打开 <http://127.0.0.1:8420/>，在终端按 `Ctrl+C` 停止。

网页支持全文搜索、左右方向键翻页、代码展开、明暗主题、章节直达链接、打印和本机学习进度恢复。移动端可以从左上角展开目录。进度仅表示已浏览章节。

## 内容与来源

按“前置准备 → 架构设计 → 实战演练 → 面试与自测”阅读。实战包括认证、持久运行与 Agent、知识入库与 RAG、模型与评测、Skill/Tool 与安全、Vue 前端六个模块。

- `project-learning.json`：按原 skill schema 组织的学习内容。
- `index.html`：内嵌同一份学习数据的阅读网页；双击打开不需要请求 JSON。
- `source.html` / `source-data.js`：被引用文件的只读快照，支持点击源码位置和行号。
- `source-manifest.json`：生成时间、Git HEAD、源码与本地资源的 SHA-256。Git HEAD 不代表未提交修改，文件哈希才是本次快照的依据。
- `project-learning-schema.json`：原 skill 的数据结构。
- `build.py`：重新组装网页或校验来源的脚本；只读源码，不导入应用或访问 Provider。
- `vendor/`：本地网页依赖、原版 HTML 模板与第三方许可证。

指南解释设计，正式事实仍按 [CONTEXT](../../../CONTEXT.md)、[Contract](../../../contracts/run_event_v1.json)、[ADR](../../adr/0023-single-canonical-implementation.md)、[Runbook](../../runbooks/repository-quality-gates.md)、[README](../../../README.md) 和代码测试核对。源码查看器呈现生成时的文件内容，不代表正在运行的服务。

## 校验与重新组装

从**仓库根目录**运行，使用项目已安装的 `jsonschema`：

```powershell
# 只读检查：schema、概念开场、锚点、讲解长度、逐字源码摘录、快照与生成物
.\.venv\Scripts\python.exe docs/learning/wenxi/build.py --check

# 修改学习 JSON 后重新生成 HTML、源码快照和 manifest
.\.venv\Scripts\python.exe docs/learning/wenxi/build.py
```

源码已变化时，`--check` 会明确失败；应重新分析并更新相关讲解和摘录，再执行组装。不能仅改哈希来掩盖过时内容。

文档中的安装、迁移、测试和真实服务调用是供学习者执行的练习。本次生成过程的实际校验记录见 [VALIDATION.md](VALIDATION.md)；离线网页检查不代表问溪应用、数据库、模型或 live RAG 已通过集成验证。

## 模板与第三方资源

页面结构、搜索、分页与调用链展示源自 [project-learning-skill 的 template.html](https://github.com/xWebt/project-learning-skill/blob/main/assets/template.html)。本地适配加入了内嵌数据、Markdown 清洗、源码快照、独立进度键和离线资源。

本地资源包括 Highlight.js 11.9.0、Marked 9.1.6、DOMPurify 3.4.14 和 Mermaid 11.17.2。对应许可证位于 `vendor/`；资源哈希见 manifest。它们仅用于学习页面，未改动应用依赖清单或锁文件。
