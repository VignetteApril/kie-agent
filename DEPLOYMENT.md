# KIE Agent 部署说明

本文档用于把当前项目部署到 Linux 服务器。

## 1. 推荐环境

- Ubuntu 22.04 / 24.04
- Docker
- Docker Compose
- 2 核以上 CPU
- 足够磁盘空间用于上传文件、结果文件和日志

> 注意：本项目依赖外部 LLM 接口。`LLM_BASE_URL` 必须能被 `backend` 和 `worker` 容器访问。

## 2. 部署文件说明

项目里已经补齐了这些部署前材料：

- `.env.example`：生产环境变量模板
- `deploy/nginx/kie-agent.conf.example`：Nginx 反向代理模板
- `deploy/scripts/deploy.sh`：在线构建部署脚本
- `deploy/scripts/check.sh`：部署后检查脚本
- `deploy/scripts/package-images.ps1`：外网 PowerShell 镜像打包脚本
- `deploy/scripts/offline-deploy.sh`：内网 Bash 离线导入部署脚本

## 3. 在线部署（服务器可直接构建）

### 3.1 上传代码

把项目上传到服务器，例如：

```bash
sudo mkdir -p /opt/kie-agent
sudo chown -R $USER:$USER /opt/kie-agent
cd /opt/kie-agent
```

### 3.2 准备环境变量

```bash
cp .env.example .env
nano .env
```

按你当前环境，建议至少配置：

```env
BACKEND_PORT=8001
FRONTEND_PORT=5173
LLM_BASE_URL=http://192.168.137.2:8000/v1
VITE_API_BASE_URL=http://192.168.137.2:8001
CORS_ORIGINS=["*"]
```

### 3.3 启动

```bash
chmod +x deploy/scripts/deploy.sh deploy/scripts/check.sh
./deploy/scripts/deploy.sh
```

### 3.4 访问

- 前端：`http://192.168.137.2:5173`
- 后端：`http://192.168.137.2:8001`
- 健康检查：`http://192.168.137.2:8001/health`

## 4. 离线部署（推荐内网场景）

适合：

- 外网机器可以构建镜像
- 内网服务器不能联网或不方便联网

### 4.1 外网机器：构建并导出镜像（PowerShell）

在项目根目录执行：

```powershell
.\deploy\scripts\package-images.ps1
```

默认会生成：

```text
kie-agent-images.tar
```

如果你要指定文件名：

```powershell
.\deploy\scripts\package-images.ps1 -ArchiveName kie-agent-2026-04-09.tar
```

### 4.2 传输到内网服务器

把这些文件一起传到内网服务器：

- 项目代码目录
- `.env`
- 镜像包 `.tar`

例如传到：

```bash
/opt/kie-agent
```

### 4.3 内网服务器：导入镜像并启动（Bash）

在服务器执行：

```bash
cd /opt/kie-agent
cp .env.example .env
nano .env
chmod +x deploy/scripts/offline-deploy.sh deploy/scripts/check.sh
./deploy/scripts/offline-deploy.sh
```

如果 tar 包文件名不是默认值：

```bash
./deploy/scripts/offline-deploy.sh kie-agent-2026-04-09.tar
```

### 4.4 离线部署原理

当前 `docker-compose.yml` 已固定镜像名：

- `kie-agent-backend:latest`
- `kie-agent-worker:latest`
- `kie-agent-frontend:latest`

因此外网打包、内网导入后，服务器可直接：

```bash
docker compose up -d
```

不会重新构建镜像。

## 5. 使用 Nginx 域名反代

如果你有域名，推荐使用 Nginx；你现在没有域名，这部分可先跳过。

### 5.1 修改 `.env`

```env
VITE_API_BASE_URL=https://your-domain.com
CORS_ORIGINS=["https://your-domain.com"]
```

### 5.2 安装站点配置

```bash
sudo cp deploy/nginx/kie-agent.conf.example /etc/nginx/sites-available/kie-agent.conf
sudo nano /etc/nginx/sites-available/kie-agent.conf
```

把 `your-domain.com` 改成你的域名。

然后启用：

```bash
sudo ln -s /etc/nginx/sites-available/kie-agent.conf /etc/nginx/sites-enabled/kie-agent.conf
sudo nginx -t
sudo systemctl reload nginx
```

### 5.3 配 HTTPS

推荐使用 Certbot：

```bash
sudo apt update
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

## 6. 常用命令

在线构建并启动：

```bash
docker compose up -d --build
```

离线镜像导入后启动：

```bash
docker compose up -d
```

查看状态：

```bash
docker compose ps
```

查看日志：

```bash
docker compose logs -f backend
docker compose logs -f worker
docker compose logs -f frontend
```

快速检查：

```bash
./deploy/scripts/check.sh
```

停止服务：

```bash
docker compose down
```

## 7. 持久化数据

以下目录会保留业务数据：

- `backend/data/tasks.db`
- `backend/data/uploads/`
- `backend/data/outputs/`
- `backend/data/logs/`

升级或重启前不要删除 `backend/data`。

## 8. 常见问题

### 8.1 前端打开后请求失败

通常是 `VITE_API_BASE_URL` 填错了。  
注意它是**前端构建时写死**进去的，改完后要重新构建前端镜像。

### 8.2 容器里访问不到 LLM

检查：

- `LLM_BASE_URL` 是否正确
- 模型服务端口是否开放
- 目标地址是否允许从服务器访问

### 8.3 离线部署后仍然触发构建

请确认你执行的是：

```bash
./deploy/scripts/offline-deploy.sh
```

或：

```bash
docker compose up -d
```

不要使用：

```bash
docker compose up -d --build
```

### 8.4 上传大文件报错

如果你用了 Nginx，请调整：

```nginx
client_max_body_size 100m;
```

## 9. 建议上线前检查项

- [ ] `.env` 已创建并填写正确
- [ ] `LLM_BASE_URL` 可从服务器访问
- [ ] `VITE_API_BASE_URL` 已改为正式访问地址
- [ ] 防火墙已放行对应端口
- [ ] `backend/data` 已保留持久化
- [ ] `docker compose ps` 全部正常
- [ ] `/health` 返回成功
