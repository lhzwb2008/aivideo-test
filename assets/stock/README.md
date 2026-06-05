# 本地视频素材（无需翻墙）

当 Pixabay 无法注册、外网不稳时，可把 mp4 放到这里：

```
assets/stock/
  common/          # 所有类型共用
  landscape_heal/  # 按 demo id 分子目录
  cute_animals/
  ...
```

然后设置 `.env`：`STOCK_PROVIDER=local`，再运行 `./make-demos.sh`。

素材来源建议：爱给网、新CG儿等国内站手动下载（注意授权说明）。
