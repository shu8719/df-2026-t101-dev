# 実験：MapAnything で手を実寸にする（1円玉がないとき）

仕様は [docs/depth-scale-mapanything/](../../docs/depth-scale-mapanything/README.md) を正とする。ここには動かし方だけを書く。

- 使う重みは `facebook/map-anything-apache`（Apache-2.0）だけ。非営利の `facebook/map-anything`（CC BY-NC 4.0）はコードで読み込めないようにしてある
- **結果（2026-11-08）：不合格**。写真1で +424%、写真2で +370%（モデルが手を 1.2m 先の大きな手と見積もる）
- 仮想環境は共通の `../depth_scale/.venv` を使う。写真・重み・結果はコミットしない（`data/`・`checkpoints/` は `.gitignore` 済み）

## 準備（Windows、PowerShell）

```powershell
cd experiments\depth_scale_mapanything
$P = "..\depth_scale\.venv\Scripts\python"   # 共通の環境（先に ../depth_scale/README.md の準備を済ませる）
& $P -m pip install --no-cache-dir --no-deps "git+https://github.com/facebookresearch/map-anything.git@3d10cf7a3016fc0f9bb13a071ee66c47b10be0d9"
& $P -m pip install --no-cache-dir -c ..\constraints.txt -r requirements.txt
```

- 重み（約4.6GB）は、初めて動かすときに Hugging Face から `checkpoints/` に取ってくる
- 写真から手の21点を出すのに、Depth Pro 側の MediaPipe のモデル（`../depth_scale/checkpoints/hand_landmarker.task`）を使う

## 写真1枚で試す

```powershell
& $P try_image_mapanything.py <写真> --compare-depth-pro
```

- 正解は既定で写真1の Depth Pro の値（0→5 75.5、0→9 72.3、0→17 69.3、5→17 61.8mm）。`--truth` で変えられる
- `--compare-depth-pro`：同じ写真で Depth Pro 側の `try_image.py` を先に動かしておくと、数値を並べる
- 途中経過の画像（モデルが見た画像と手の点・深度・信頼度・使える画素・点群を横から見た図・最終結果・まとめ）と数値を `data/vis/` に保存する（`--no-save` で止める）
- `--constant`：重みなしで流れだけを確かめる偽物。**結果を実験に使ってはいけない**

## テスト

```powershell
& $P -m pytest -q tests
```
