# SearXNG 搜索引擎实例

为 agent-explore 实验提供 Web 搜索能力的自托管 SearXNG 实例。

## 架构

```
Client → [port 80] nginx (Basic Auth) → [port 8080] SearXNG container
```

- **SearXNG** 只监听 `127.0.0.1:8080`，不对外暴露
- **nginx** 反向代理在端口 80，添加 HTTP Basic Authentication
- 两个容器通过 Docker 网络互联

## EC2 实例规格

| 参数 | 值 |
|---|---|
| AMI | Amazon Linux 2023 (存储在 `~/.aws-resources` 的 `SEARXNG_AMI` 变量) |
| 实例类型 | `t3.small` (2 vCPU, 2GB RAM) |
| 存储 | 20GB gp3 |
| 区域 | us-east-1 |
| SSH Key Pair | `3phandbook` |
| SSH 用户名 | `ec2-user` |

## 安全组规则 (`searxng-sg`)

| 端口 | 协议 | 来源 | 用途 |
|---|---|---|---|
| 22 | TCP | 0.0.0.0/0 | SSH |
| 80 | TCP | 0.0.0.0/0 | SearXNG (nginx 反向代理) |

> **安全提醒**: Basic Auth 在 HTTP 明文下保护不足。如需加强，可收紧安全组来源 IP 或加 HTTPS。

## 从零部署（全新实例）

### 1. 启动 EC2 实例

```bash
source ~/.aws-resources  # 加载 AMI、SG 等变量

aws ec2 run-instances \
  --image-id "$SEARXNG_AMI" \
  --instance-type t3.small \
  --key-name 3phandbook \
  --security-group-ids "$SEARXNG_SG" \
  --subnet-id "$SEARXNG_SUBNET" \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=SearXNG}]' \
  --block-device-mappings '[{"DeviceName":"/dev/xvda","Ebs":{"VolumeSize":20,"VolumeType":"gp3"}}]' \
  --region us-east-1
```

### 2. SSH 进入实例

```bash
# 获取公网 IP
SEARXNG_IP=$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=SearXNG" "Name=instance-state-name,Values=running" \
  --query 'Reservations[0].Instances[0].PublicIpAddress' \
  --output text --region us-east-1)

# 如果没有 3phandbook.pem，用 EC2 Instance Connect
ssh-keygen -t rsa -b 2048 -f /tmp/ec2_temp_key -N "" -q 2>/dev/null
aws ec2-instance-connect send-ssh-public-key \
  --instance-id "$(aws ec2 describe-instances \
    --filters 'Name=tag:Name,Values=SearXNG' 'Name=instance-state-name,Values=running' \
    --query 'Reservations[0].Instances[0].InstanceId' --output text --region us-east-1)" \
  --instance-os-user ec2-user \
  --ssh-public-key file:///tmp/ec2_temp_key.pub \
  --region us-east-1

ssh -i /tmp/ec2_temp_key ec2-user@${SEARXNG_IP}
```

### 3. 安装 Docker

```bash
sudo dnf update -y
sudo dnf install -y docker htop
sudo systemctl enable docker
sudo systemctl start docker
sudo usermod -aG docker ec2-user
# 重新登录以生效 docker 组权限
exit
# 重新 SSH 进入
```

### 4. 安装 Docker Compose

```bash
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" \
  -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

### 5. 部署 SearXNG

```bash
mkdir -p ~/searxng/searxng-config

# 创建 docker-compose.yml
cat > ~/searxng/docker-compose.yml << 'COMPOSE'
version: '3.8'

services:
  searxng:
    image: searxng/searxng:latest
    container_name: searxng
    restart: unless-stopped
    ports:
      - "127.0.0.1:8080:8080"
    volumes:
      - ./searxng-config:/etc/searxng
    environment:
      - SEARXNG_SECRET_KEY=${SEARXNG_SECRET_KEY}

  nginx:
    image: nginx:alpine
    container_name: nginx
    restart: unless-stopped
    ports:
      - "80:80"
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
      - ./htpasswd:/etc/nginx/.htpasswd:ro
    depends_on:
      - searxng
COMPOSE

# 创建 nginx.conf
cat > ~/searxng/nginx.conf << 'NGINX'
server {
    listen 80;

    auth_basic "MiroFlow Search";
    auth_basic_user_file /etc/nginx/.htpasswd;

    location / {
        proxy_pass http://searxng:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
NGINX

# 生成 htpasswd（需要设置用户名和密码）
docker pull httpd:alpine
echo "YOUR_PASSWORD" | docker run --rm -i httpd:alpine htpasswd -niB miroflow > ~/searxng/htpasswd

# 生成 secret key 并写入 .env
echo "SEARXNG_SECRET_KEY=$(openssl rand -hex 32)" > ~/searxng/.env
```

### 6. 配置 SearXNG settings.yml

SearXNG 首次启动会自动生成完整的默认 `settings.yml`。关键的自定义项：

```yaml
# ~/searxng/searxng-config/settings.yml 中需要确认的设置：

search:
  # 启用 JSON 格式输出（供 API 调用）
  formats:
    - html
    - json

server:
  limiter: false        # 私有实例不需要限流
  public_instance: false
```

如果需要从头创建，可以复制本目录下的 `settings.yml` 模板到实例：
```bash
scp settings.yml ec2-user@${SEARXNG_IP}:~/searxng/searxng-config/
```

### 7. 启动服务

```bash
cd ~/searxng
docker compose up -d
# 或者旧版
docker-compose up -d
```

### 8. 验证

```bash
# 容器状态
docker ps

# 本地测试（绕过 nginx auth）
curl -s http://127.0.0.1:8080/search?q=test&format=json | head -c 200

# 通过 nginx 测试（需要认证）
curl -s -u miroflow:YOUR_PASSWORD http://localhost/search?q=test&format=json | head -c 200
```

## 日常运维

### 重启服务

```bash
cd ~/searxng
docker compose restart
```

### 更新镜像

```bash
cd ~/searxng
docker compose pull
docker compose up -d
```

### 查看日志

```bash
docker logs searxng --tail 50
docker logs nginx --tail 50
```

### 修改 Basic Auth 密码

```bash
echo "NEW_PASSWORD" | docker run --rm -i httpd:alpine htpasswd -niB miroflow > ~/searxng/htpasswd
docker restart nginx
```

## API 调用方式

SearXNG JSON API 供 agent tools 使用：

```bash
# 搜索
curl -u miroflow:PASSWORD "http://INSTANCE_IP/search?q=query&format=json"

# 带参数搜索
curl -u miroflow:PASSWORD "http://INSTANCE_IP/search?q=query&format=json&language=zh-CN&categories=general"
```

Python 调用示例：

```python
import requests

response = requests.get(
    "http://INSTANCE_IP/search",
    params={"q": "query", "format": "json"},
    auth=("miroflow", "PASSWORD"),
)
results = response.json()
```

## 文件结构

```
~/searxng/
├── .env                    # SEARXNG_SECRET_KEY（自动生成）
├── docker-compose.yml      # 服务编排
├── nginx.conf              # nginx 反向代理 + Basic Auth
├── htpasswd                # Basic Auth 凭据（htpasswd 格式）
└── searxng-config/
    └── settings.yml        # SearXNG 配置（首次启动自动生成）
```

## 故障排查

| 症状 | 排查 |
|---|---|
| 无法访问端口 80 | 检查安全组是否开放 80，`docker ps` 确认 nginx 运行 |
| 401 Unauthorized | htpasswd 文件格式错误，重新生成 |
| SearXNG 无搜索结果 | `docker logs searxng` 查看引擎报错，可能被上游封 IP |
| 容器未启动 | `docker compose logs` 查看启动错误 |
| settings.yml 未生效 | 修改后需 `docker restart searxng`，确认文件权限 |
