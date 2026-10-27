<div align="center">

<img src="frontend/icon.svg" width="72" alt="弦外">

# 弦外 · Xianwai

**听见弦外之音。开源、本地优先的对话记录与分析。**

录一段对话，或导入手机里的录音 → 自动转写、区分说话人 → 生成日记、待办，并提醒你话里话外值得留意的地方。

[快速开始](#快速开始) · [功能](#功能) · [写一个分析器](#写一个分析器) · [路线图](#路线图) · [English](README.en.md)

</div>

> 📽️ 演示动图待补：`docs/demo.gif`

## 为什么做弦外

每天的对话里藏着大量信息：答应别人的事、聊天背后的情绪表达、沟通中弦外之音、诈骗诱导风险。现在我们摄入的信息日益爆炸，而且作为老实人的我们也很难有心力去详细体会，这些关键信息很容易漏掉。

市面上的录音 AI 工具，大多要把你的录音上传到别人的服务器上。**弦外选择相反的路线：** 我希望能在本地自动化识别关键信息并做好日记留存。当前版本还是一个mvp试运行的版本，我自己也不是程序员，用claude搓一个临时demo，后续想结合app或者硬件把这个事情做闭环。有想法可以联系我邮箱：gaohuan319@gmail.com

- 🔒 **数据不出本地**：转写用本地的 [FunASR](https://github.com/modelscope/FunASR)，数据库是你磁盘上的一个 SQLite 文件
- 🧠 **模型你来选**：DeepSeek、通义、Kimi、智谱，或者完全离线的 Ollama
- 🧩 **分析器即插件**：一个 YAML 文件就是一个分析器，社区可以共建
- 🔍 **每条结论都有出处**：点一下就能跳到原话、回听原声，不做黑箱判断

## 功能

| | |
|---|---|
| 🎙️ **录音 / 导入** | 浏览器直接录音，或导入 m4a、mp3、wav、webm 等格式 |
| 👥 **说话人分离** | 自动区分不同的人，也可以指定人数（讲座选 1 人最准）；标注一次「妈妈」「老板」，人物会跨录音保留 |
| 📔 **日记摘要** | 每段对话生成一段日记和要点 |
| ✅ **待办追踪** | 提取承诺和约定（谁、做什么、什么时候），跨天勾选追踪 |
| 🛡️ **防诈提醒** | 识别冒充客服、安全账户、要求保密等典型电诈话术 |
| 💬 **沟通洞察** | 施压、回避、情绪起伏、字面之外的诉求，即「弦外之音」 |
| 👍 **纠错反馈** | 每条洞察都能标记对错，为后续的个性化打基础 |

## 快速开始

### 方式一：Docker（推荐）

```bash
git clone https://github.com/gaohuan319-debug/xianwai.git
cd xianwai
cp .env.example .env      # 填入 XW_LLM_API_KEY
docker compose up -d
```

打开 <http://localhost:8000>。首次转写会自动从 ModelScope 下载语音模型（约 2GB，保存在 `models/` 目录），之后完全离线。

> 💻 **资源需求**：镜像约 3GB，运行时内存约 3GB。请给 Docker 分配至少 4GB 内存（Docker Desktop 在设置里调整，Colima 用 `colima start --memory 4`）。

国内构建慢的话，可以换用 pip 镜像：

```bash
PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple docker compose build
```

### 方式二：先体验演示模式（不下载模型）

在 `.env` 里设置 `XW_ASR_ENGINE=mock`，再用 `WITH_ASR=false docker compose up -d --build` 构建轻量镜像。随便上传一个音频文件，就会用一段内置的示例对话（里面有待办，也有一段电诈话术）跑完整个流程。

### 方式三：本地开发

需要 Python 3.9+ 和 ffmpeg。

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pip install torch torchaudio && pip install -r requirements-asr.txt   # 演示模式可跳过
export XW_LLM_API_KEY=sk-xxx          # 演示模式可加 XW_ASR_ENGINE=mock
uvicorn app.main:app --reload
```

> 📱 **在手机上录音**：浏览器只允许在 HTTPS 或 localhost 下使用麦克风。局域网访问时可以先用「导入音频」，或者用 Caddy、Tailscale 等工具配置 HTTPS。

### 常见问题

**转写失败，提示「语音模型尚未下载，且从 ModelScope 下载失败」**

容器访问不了外网。先确认一下：

```bash
docker compose exec xianwai python -c "import socket; print(socket.gethostbyname('www.modelscope.cn'))"
```

如果报 `name resolution` 错误，说明是容器的 DNS 有问题，常见于 Colima，以及开了代理软件的电脑。可以在项目根目录新建 `docker-compose.override.yml`，给容器指定 DNS，然后执行 `docker compose up -d`：

```yaml
services:
  xianwai:
    dns: [223.5.5.5, 119.29.29.29]
```

**第一次转写特别慢**

第一次要下载约 2GB 的模型，之后每次启动加载模型只需要十几秒。转写本身大约需要录音时长的三分之一，比如 37 分钟的录音在 4 核 CPU 上需要 12 分钟左右。

**讲座、单人录音被分成了好几个说话人**

上传时把「说话人数」选为 1；已经上传的录音可以在详情页选好人数后点「重新转写」。

## 配置大模型

任何兼容 OpenAI Chat Completions 的接口都可以用：

| 服务 | `XW_LLM_BASE_URL` | `XW_LLM_MODEL` 示例 |
|---|---|---|
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |
| 通义千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus` |
| Kimi | `https://api.moonshot.cn/v1` | `moonshot-v1-8k` |
| 智谱 | `https://open.bigmodel.cn/api/paas/v4` | `glm-4-flash` |
| Ollama（完全离线） | `http://host.docker.internal:11434/v1` | `qwen2.5:7b` |

一小时的对话大约 1 万字，用 DeepSeek 分析一次通常只要几分钱。

## 写一个分析器

分析器放在 [`backend/analyzers/`](backend/analyzers)（内置）或 `data/analyzers/`（你自己的，同 id 会覆盖内置的）。比如：

```yaml
id: workplace_pua
name: 职场 PUA 识别
kind: insight          # summary 日记 | todo 待办 | insight 洞察
version: 1
description: 识别贬低、否定、情绪控制等职场 PUA 话术。
prompt: |
  从录音主人的角度，检查对方是否使用了以下话术：
  - 全盘否定、人身贬低（「你怎么什么都做不好」）
  - 比较打压（「别人都能加班就你不行」）
  - 画饼与情绪绑架
  只描述话术本身，不要评判对方的人品；没有就返回空列表。
```

只需要写 `prompt`。输出格式、证据引用和前端展示都由 `kind` 统一处理。欢迎提交 PR 分享你的分析器。

### 用评测验证你的分析器

[`backend/evals/cases.yaml`](backend/evals/cases.yaml) 里是一组固定的对话用例，每个用例都写明了「应该标出什么、不应该标出什么」，例如朋友互损不应被当成恶意、正常的银行事务不应误报诈骗。改 prompt 之前和之后各跑一遍：

```bash
cd backend
python -m evals.run                    # 全部用例（读取根目录 .env 里的模型配置）
python -m evals.run -a todo -r 3       # 只测待办分析器，每个用例跑 3 次看稳定性
```

提交新分析器时请附上对应的用例，误报用例和漏报用例同样重要。

## 架构

```
浏览器 / PWA ──上传音频──► FastAPI
                             │
                ffmpeg → 16k wav
                             │
          FunASR: Paraformer + VAD + 标点 + CAM++ 说话人
                             │
                     segments（带编号）
                             │
        ┌──────── 分析器（YAML）× N ────────┐
        │  转写 + prompt → 大模型 → JSON    │
        └───────────────────────────────────┘
                             │
          SQLite: 摘要 / 待办 / 洞察（引用片段编号）
```

## 路线图

- [x] 录音 / 导入、本地转写、说话人分离
- [x] 日记摘要、待办追踪、防诈提醒、沟通洞察
- [x] 分析器插件、证据回溯、纠错反馈
- [ ] 声纹注册：标注过的人在新录音里自动识别
- [ ] SenseVoice 情绪识别，补上文字丢失的语气
- [ ] 纠错反馈回灌为个性化示例
- [ ] 跨录音的人物时间线（「我和妈妈最近聊了什么」）
- [ ] 每日 / 每周回顾
- [ ] 移动端 App

## 隐私与合规

- 弦外默认把所有数据保存在你自己的设备上。分析时只会把**转写文字**发送给你配置的大模型服务；想做到完全离线，请使用 Ollama。
- 设置 `XW_KEEP_AUDIO=false` 后，处理完成会删除原始音频，只保留文字。
- **请在合法、并取得对方知情同意的前提下录音**。声纹等生物识别信息属于《个人信息保护法》规定的敏感个人信息。
- 分析结果由 AI 生成，可能有误，仅供参考，不应作为评判他人的依据。

## 许可证

[AGPL-3.0](LICENSE)。可以自由使用、修改和部署；如果修改后对外提供网络服务，需要同样开源。
