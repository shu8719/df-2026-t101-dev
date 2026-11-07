# 実験：Depth Anything 3 で手を実寸にする（1円玉がないとき）

仕様は [docs/depth-scale-da3/scripts.md](../../docs/depth-scale-da3/scripts.md)、組み合わせと判断は [docs/depth-scale-da3/method.md](../../docs/depth-scale-da3/method.md) を正とする。ここには動かし方だけを書く。

- 使うのは `DA3METRIC-LARGE` と `DA3-BASE`（どちらも Apache-2.0）だけ。非営利（CC BY-NC）の版はコードで読み込めないようにしてある
- Depth Pro・MoGe-2 の実験とは、重み・出力を分ける。**仮想環境は Depth Pro 側の `../depth_scale/.venv` を共通で使う**（PyTorch を実験ごとに入れるとディスクを圧迫するため）。焦点距離と比べる数値は、それぞれの `try_image` が保存した JSON を読む
- **本番のコード（`app/`・`api/`・`hand_mesh/`）は変えない。** 写真・重み・結果はコミットしない（`data/`・`checkpoints/` は `.gitignore` 済み）

## 準備（Windows、PowerShell）

Depth Anything 3 は依存ライブラリが多く（open3d・xformers など）、`numpy<2` も指定している。PyTorch の版が変わったり、OpenCV 5・MediaPipe（numpy 2 が要る）とぶつかったりしないよう、**本体は依存を入れずに入れ、推論に要るものだけを、版の固定（`..\constraints.txt`）を付けて入れる**。固定を付けずに入れたら、PyTorch が 2.15.0 に入れ替わったことがある（2026-11-08）。

```powershell
cd experiments\depth_scale_da3
$P = "..\depth_scale\.venv\Scripts\python"   # 共通の環境（先に ../depth_scale/README.md の準備を済ませる）
& $P -m pip install --no-cache-dir --no-deps "git+https://github.com/ByteDance-Seed/Depth-Anything-3.git@3d835ec1a5802d64a8b8b15f817a1ab54809bfe4"
& $P -m pip install --no-cache-dir -c ..\constraints.txt -r requirements.txt
```

以下のコマンドの `.venv\Scripts\python` は、`..\depth_scale\.venv\Scripts\python` と読み替える。

- xformers は入れない（あれば使う作りで、なくても動く）。open3d は性能評価（`bench`）でしか使わないので入れない
- 重みは、初めて動かすときに Hugging Face から `checkpoints/` に取ってくる
- 写真から手の21点を出すのに、Depth Pro 側の MediaPipe のモデル（`../depth_scale/checkpoints/hand_landmarker.task`）を使う

## 写真1枚で試す

先に、同じ写真で Depth Pro と MoGe-2 を動かしておく（焦点距離と、比べる数値の JSON ができる）。

```powershell
# Depth Pro（experiments\depth_scale で）
.venv\Scripts\python try_image.py <写真>
# MoGe-2（experiments\depth_scale_moge2 で）
.venv\Scripts\python try_image_moge.py <写真> --model vitl
.venv\Scripts\python try_image_moge.py <写真> --model vits
# Depth Anything 3（experiments\depth_scale_da3 で）
.venv\Scripts\python try_image_da3.py <写真> --truth 75.0,72.0,69.0,62.0
```

- `--truth`：定規・ノギスで測った正解（mm）を「0→5、0→9、0→17、5→17」の順に渡すと、ずれ（%）も出す
- `--combos`：試す組み合わせ（既定は5つ全部）。名前は [method.md §3](../../docs/depth-scale-da3/method.md) を参照
- 結果の画像（組み合わせごとの重ね描きと深度、全部を並べた画像）と数値は `data/vis/` に保存する（`--no-save` で止める）
- `--constant`：重みなしで流れだけを確かめる偽物。**結果を実験に使ってはいけない**

## テスト

```powershell
.venv\Scripts\python -m pytest -q tests
```
