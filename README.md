# aivideo-test — 爆量情绪短视频实验

与主项目 [`../aivideo`](../aivideo) 不同：本仓库**不用 AI 生图**，而是从网上搜索免费视频片段（Pexels），**先抽帧理解画面再写口播**，配合 TTS 混剪成竖屏短视频，主攻情绪价值与刷流量向内容。

## 五种 Demo 类型

| ID | 类型 | 风格 |
|----|------|------|
| `landscape_heal` | 风景治愈 | 慢节奏、解压 |
| `cute_animals` | 动物萌宠 | 可爱反差 |
| `curiosity_wonder` | 猎奇奇观 | 震撼冷知识 |
| `anxiety_hot` | 焦虑热点 | 追热点、紧迫感（Exa 辅助） |
| `urban_lonely` | 城市孤独 | 雨夜霓虹共鸣 |

## 环境

- macOS / Linux，`ffmpeg`、`ffprobe`、`python3`
- 从 `../aivideo/.env` 复制 API Key（已支持）：`AIHUBMIX`、`EXA`、`VOLCENGINE_TTS`
- **推荐**：`PEXELS_API_KEY`（你已有；`STOCK_PROVIDER=pexels` 默认）
- Pixabay：国内官网常 **403 无法注册**，可跳过；有 Key 再设 `STOCK_PROVIDER=pixabay`
- 无外链：`STOCK_PROVIDER=local`，把 mp4 放进 `assets/stock/`（见该目录 README）

## 一键生成全部 Demo

```bash
./make-demos.sh
```

只跑一种：

```bash
./make-demos.sh --only landscape_heal
```

成片在 `output/demo_<类型>_<时间>.mp4`，脚本与日志在 `logs/<时间>_<类型>/`。

## 目录

```
src/
  make_demos.py      # 入口：素材 → 视觉理解 → 口播 → 合成
  vision_client.py   # 抽帧 + 多模态描述画面
  script_generator.py
  pixabay_client.py / stock_client.py
  clip_compose.py
  tts_client.py / text_client.py / exa_client.py
demos/types.json     # 五类配置
output/              # 成片
```

## 下一步

- 换口播音色、调 `AIVIDEO_BGM_VOLUME`
- 在 `demos/types.json` 加新类型或改 `clip_queries`
- 用 Pexels 重跑 `./make-demos.sh`，或本地素材模式见 `assets/stock/README.md`
- 手动上传新号，对比五类完播与转化
