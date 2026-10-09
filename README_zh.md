# 小说引擎 Story Dashboard

## 项目管理

在“项目历史”区域点击“新建项目”，填写项目名称与小说设定，再点击“创建项目”。每个新项目使用唯一 ID，在 `backend/data/<project_id>/` 下独立保存 `state.json`、章节正文、快照和角色、物品、地图、设定、大纲导出文件。同名项目也不会覆盖彼此。设置 `NOVEL_DATA_DIR` 时，该目录作为项目库根目录。

历史列表展示项目名称、设定摘要、已批准章节数、草稿数和最近保存时间。点击“加载项目”即可继续创作；切换不会丢弃已保存的草稿或路线规划。重启后默认恢复最后加载的项目。已打开的页面在请求中携带项目 ID，避免其他标签页切换项目后误操作数据。

数据根目录下已有的、包含 `state.json` 的直接子目录会自动出现在历史列表中。旧版直接存放在根目录中的项目显示为“旧版项目（data 根目录）”，可继续加载，不搬移或覆盖原文件。无法读取的项目会标为不可加载。

新增与调整的接口：

- `GET /api/projects`：返回历史项目列表及最后选择的项目 ID。
- `POST /api/project/init`：接收 `{ "name": "项目名称", "prompt": "小说设定" }`，创建独立项目并返回 `project_id`。兼容旧客户端省略名称，此时使用设定摘要。重复调用会新建项目。
- `POST /api/project/load`：接收 `{ "project_id": "..." }`，加载已有项目。
- 现有章节、规划、回档、状态、Dashboard 和导出接口支持 `X-Project-ID` 请求头（中文 ID 需 URL 编码），也可用 `project_id` 查询参数指定项目；省略时使用最后选择的项目。Dashboard 额外返回 `project_id` 和 `projects`。

## 正文导出与章节流程

点击顶部“下载到txt”，可将 `chapters` 中已保存的每章 `text` 按章节号排序导出，每三章一个 TXT，最后不足三章也会导出。只有一组时直接下载 TXT，多组时下载包含各个 TXT 的 ZIP。正文包含已批准章节和已保存草稿，并标注状态；文件使用 UTF-8 BOM 编码，便于 Windows 记事本显示中文。没有正文时按钮不可用。接口为 `GET /api/project/export/txt`，导出不修改项目数据。

基于 Flask + Vue 的小说状态闭环、Story Dashboard 与 Phase 3 Narrative Planning，默认使用无需 API Key 的 MockLLMProvider。

已实现：初始化 → 生成三种策略候选 → 人工选择路线 → 生成草稿 → 机审与有限重写 → 人工批准 → 状态提交与快照 → 回档。

Dashboard 提供项目概览、章节导航、正文与机审工作区、只读角色/物品/地图/设定、最近状态变化、快照历史。草稿与正式状态明确分开。

每章先点击 Generate Story Options，选择 Progression / Escalation / Revelation 后才能 Generate Chapter。已有草稿时，先 Discard Draft 才能更换或重新生成路线。未提交规划不改变正式世界。

先安装 Miniconda 或 Anaconda，前端另需 Node.js 和 npm。在 `novel_engine` 项目根目录运行（Windows PowerShell），安装依赖前先创建并激活独立的 Python 3.13 环境：

```powershell
conda create -n novel_engine python=3.13 pip -y
conda activate novel_engine
```

环境只需创建一次；每次打开新终端运行后端命令前，执行 `conda activate novel_engine`。

安装依赖并启动后端：

```powershell
python -m pip install -r backend/requirements.lock.txt
python -m backend.app
```

另开一个终端：

```powershell
cd frontend
npm ci
npm run dev
```

打开 http://127.0.0.1:5173 。后端监听 http://127.0.0.1:5000 。

测试与构建：

```powershell
conda activate novel_engine
python -m pytest -q
cd frontend
npm test
npm run build
```

完整的数据模型、API、模型配置、验证结果和限制见 [Phase 1 实现报告](docs/baseline_report.md)。

Phase 2 的增量 API、数据兼容性、测试结果及浏览器验收限制见 [Story Dashboard 报告](docs/phase2_story_dashboard_report.md)。

Phase 3 的 schema、生命周期、API 与验证结果见 [Narrative Planning 报告](docs/phase3_narrative_planning_report.md)。旧版未批准草稿没有路线绑定，升级后须丢弃并重新规划；已有批准历史仍可读取。

Mock 使用固定的“旅人收集路标石”故事，保留用户设定用于 lore 和大纲 premise；它用于验证流程，不代表真实小说解析与生成能力。真实模型需配置 OpenAI-compatible Provider。
## 视频教程
以下视频讲述从小说到视频的全流程教程

[▶ 观看视频](https://youtu.be/Cjfw1-kFnxc)

