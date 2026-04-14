# KIE Agent

基于本地 Qwen 模型的 Word→Excel 关键信息抽取系统。

## 功能

- 上传多个 `.docx` 和一个 `.xlsx` 模板
- 自动识别 Excel 第一行表头
- 为每个表头自动生成默认抽取说明，并允许前端逐项修改
- 异步创建任务并轮询进度
- 从多个 Word 中抽取信息并回填 Excel
- 前端可查看结果值对应的来源片段
- 对每个字段抽取记录结构化日志
- 模型返回空值、非 JSON、超时或 HTTP 错误时自动重试
- 不再使用固定字段 fallback，完全按当前表头和模型结果执行
- Docker Compose 一键部署前后端与 worker

## Excel 模板格式

Excel 第一张工作表的第一行就是目标表头，例如：

| 姓名 | 联系电话 | 合同编号 | 签署日期 | 金额 | 单位名称 |
| --- | --- | --- | --- | --- | --- |

系统会自动生成类似“从文档中提取姓名”“从文档中提取联系电话”的默认抽取说明，用户可在前端修改后再执行任务。

## API 概览

- `POST /api/mappings/preview`：上传 Word + Excel，识别表头并返回默认映射
- `POST /api/tasks`：提交确认后的映射，创建任务
- `GET /api/tasks/{task_id}`：查看任务状态、结果预览、字段状态与错误信息
- `GET /api/tasks/{task_id}/download`：下载结果 Excel

## 本地运行

### Backend

```bash
cd backend
python -m venv .venv
. .venv/bin/activate  # Windows 请改为 .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8001
```

另开一个终端启动 worker：

```bash
cd backend
python -m app.worker
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Docker 部署

```bash
docker compose up --build
```

更完整的服务器部署说明见：[DEPLOYMENT.md](./DEPLOYMENT.md)

## 日志与排查

日志会同时输出到：

- `docker logs kie-agent-backend`
- `docker logs kie-agent-worker`
- `backend/data/logs/kie-agent.log`

字段级日志会记录：

- 文档名、字段名、任务 ID
- 第几次尝试
- 使用了哪种 prompt
- 模型原始返回摘要
- 解析出的 value/evidence
- 最终成功/失败状态
- 失败原因（空值、非 JSON、HTTP 错误、超时等）

默认重试策略：

- 首次调用失败或返回空值后，再自动重试 2 次
- 如果仍失败，则该字段直接记为失败，不做固定字段 fallback

## 测试样例

`samples/` 目录下已提供：

- `sample-contract-1.docx`
- `sample-contract-2.docx`
- `sample-contract-3.docx`
- `sample-template.xlsx`

## 注意事项

- 当前仅支持 `.docx` 和 `.xlsx`
- Word 仅解析正文段落
- Excel 第一行必须包含至少一个非空表头
- 模型接口按 OpenAI 兼容 `/chat/completions` 调用
