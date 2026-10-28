# Windows 项目目录更名为 Wenxi

本流程适用于已有原生 Windows `.venv`、前端 Vite 和本地 Compose 基础设施的开发目录。
先完成正在运行的对话、索引和评估；脚本发现活动任务时拒绝操作。

## 执行

1. 退出占用旧目录的 Codex 项目、编辑器和终端。不要强行结束不明进程。
2. 重新打开一个 PowerShell，工作目录放在项目的父目录。下例按当前目录名 `SuperMew` 展示：

```powershell
cd F:\project\rag

# 只检查：不停止服务、不移动目录
powershell -NoProfile -File .\SuperMew\scripts\rename-project.ps1 -TargetName Wenxi -CheckOnly

# 执行更名；会暂停并恢复本项目服务
powershell -NoProfile -File .\SuperMew\scripts\rename-project.ps1 -TargetName Wenxi
```

如果 Windows 仍返回错误 32，说明还有进程把旧目录作为工作目录或持有不允许更名的句柄。
关闭相应窗口后再执行；脚本不会终止 Codex、编辑器或普通用户终端，也不会复制文件到第二个仓库冒充更名。

脚本需要一个带 pip 内置 distlib 的工具 Python 来按安装元数据重新生成 `.venv` 的 Windows 启动器。
默认使用 Codex 已安装的工具运行时；其它环境可传 `-ToolPythonPath <python.exe>`，不会将 pip 加为应用依赖。
原 `.venv` 中的包、版本和项目 Git 修改保留。脚本不会重新下载模型或重建业务数据库。

## 保持的数据边界

- 源目录和目标均解析为同一父目录下的绝对路径；目标已存在时直接拒绝。
- 仅终止命令行明确属于旧目录的 backend launcher / Vite 进程；未知进程保留。
- 默认校验现有 PostgreSQL 容器的 Compose 项目为 `supermew`；不匹配时通过 `-ComposeProject` 显式指定。
- `docker compose down` 不带 `-v`，保留 RustFS 命名卷和所有磁盘数据；更名后从新路径重建容器挂载。
- 将原 Compose 项目身份保存在本地 `.env` 的 `COMPOSE_PROJECT_NAME`，避免文件夹名改变后出现第二套空数据卷。
- 只修正 `.env` 的目录/path 配置，不改 credential 或历史 Run/Document/Model Snapshot。
- 使用标准 distlib 按原 `.venv` 已安装的 entry points 重新生成 console/gui 启动器，修正激活路径和环境提示名。
- 移动失败时从旧目录恢复 Docker、API 和前端；移动成功但后续启动失败时保留新目录，并从新目录尝试恢复。

## 更名后检查

```powershell
cd F:\project\rag\Wenxi
.\.venv\Scripts\Activate.ps1
python -m pytest --version
docker compose ps
Invoke-RestMethod http://127.0.0.1:8000/health/ready
```

重新在 Codex/编辑器中打开 `F:\project\rag\Wenxi`。旧终端需要重新激活 `.venv`。
浏览器地址继续为 `http://localhost:3000/`；模型配置、用户、对话和知识库应保持原状。

## 对象存储卷身份核验

开发 Compose 使用 `RUSTFS_DATA_VOLUME_NAME` 指定 RustFS 的持久卷名，默认 `supermew_rustfs-data`。
目录或 Compose 项目改名时必须保留实际使用的旧卷名；已有其它卷名的部署需要在 `.env` 中显式填写该值。
使用 `docker inspect milvus-rustfs --format '{{range .Mounts}}{{.Name}}{{end}}'` 核验实际挂载。

若 PostgreSQL/etcd/Milvus 的 bind mount 保留旧数据，而 RustFS 挂载新空卷，容器可能仍显示 healthy，
但查询和索引会报 `channel not subscribed`；Milvus 日志同时出现 `GetObjectSize` 的 404。
应先确认旧对象卷仍在，恢复正确卷挂载，再重启 RustFS 和 Milvus。不要删除卷、清空元数据或绕过索引核验。