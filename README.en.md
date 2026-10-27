# Xianwai 弦外

**Hear what's left unsaid.** An open-source, local-first tool that turns everyday conversations into a diary, a to-do list, and gentle heads-ups about what was said between the lines.

- 🔒 **Local-first**: on-device speech recognition with [FunASR](https://github.com/modelscope/FunASR); your data lives in a SQLite file on your disk
- 🧠 **Bring your own LLM**: any OpenAI-compatible API (DeepSeek, Qwen, Kimi, GLM) or fully offline via Ollama
- 🧩 **Analyzers as plugins**: one YAML file per analyzer (anti-fraud, commitments, communication insights...)
- 🔍 **Every conclusion cites its source**: jump to the exact line and replay the audio

Currently optimized for Mandarin Chinese.

## Quick start

```bash
git clone https://github.com/gaohuan319-debug/xianwai.git && cd xianwai
cp .env.example .env   # set XW_LLM_API_KEY
docker compose up -d
```

Open <http://localhost:8000>. Set `XW_ASR_ENGINE=mock` to try a built-in demo conversation without downloading speech models.

See the [Chinese README](README.md) for full docs. License: [AGPL-3.0](LICENSE).
