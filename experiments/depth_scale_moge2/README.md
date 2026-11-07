# 実験：MoGe-2 で手を実寸にする（1円玉がないとき）

仕様は [docs/depth-scale-moge2/scripts.md](../../docs/depth-scale-moge2/scripts.md)、手順は [docs/depth-scale-moge2/experiment.md](../../docs/depth-scale-moge2/experiment.md) を正とする。ここには動かし方だけを書く。

- MoGe-2（Microsoft）は、コードも重みも MIT（中の DINOv2 は Apache-2.0）。本番の候補にできる
- Depth Pro の実験（`../depth_scale/`）とは、重み・出力を分ける。**仮想環境は Depth Pro 側の `../depth_scale/.venv` を共通で使う**（PyTorch を実験ごとに入れるとディスクを圧迫するため）。フレーム・手の21点・ノギスの正解・1円玉の採寸は Depth Pro 側の `data/` を読み、計算は Depth Pro 側の `common.py` を使う（同じ条件で比べるため）
- **本番のコード（`app/`・`api/`・`hand_mesh/`）は変えない。** 写真・動画・重み・結果はコミットしない（`data/`・`checkpoints/` は `.gitignore` 済み）

## 準備（Windows、PowerShell）

先に `../depth_scale/README.md` の準備を済ませ、その共通の環境に MoGe を入れる（版の固定は `..\constraints.txt`）。

```powershell
cd experiments\depth_scale_moge2
..\depth_scale\.venv\Scripts\python -m pip install --no-cache-dir -c ..\constraints.txt -r requirements.txt
```

以下のコマンドの `.venv\Scripts\python` は、`..\depth_scale\.venv\Scripts\python` と読み替える。

- 重みは、初めて動かすときに Hugging Face から `checkpoints/` に取ってくる
- 写真から手の21点を出すのに、Depth Pro 側の MediaPipe のモデル（`../depth_scale/checkpoints/hand_landmarker.task`）を使う

## 写真1枚で試す

```powershell
.venv\Scripts\python try_image_moge.py <写真のパス> --model vitl --compare-depth-pro
```

- カメラから手までの距離、焦点距離、手の甲の4区間の長さ（点群から／確かめ：深度から）を表示する
- `--compare-depth-pro`：同じ写真で Depth Pro 側の `try_image.py` を先に動かしておくと、数値を並べる
- 結果の画像と数値は `data/vis/` に保存する（`--no-save` で止める）
- 「点群と深度の長さの差」が 0.5% を超えたら、焦点距離の直し方か単位の読み方を疑う

## 動画で比べる

先に Depth Pro 側で ①（`extract_frames.py`）と ②（`landmarks.py`）を動かしておく。

```powershell
.venv\Scripts\python depth_moge.py --all --model vitl --cond A,B,C       # ③ 点群・深度（vits も同じように）
.venv\Scripts\python measure_moge.py --all --model vitl,vits --cond A,B,C --radius 1,3,5   # ④ 長さ
.venv\Scripts\python compare_all.py --radius 3 --skin-offset-mm 0        # ⑤ ノギス・1円玉・Depth Pro・MoGe-2 を並べる
```

- `depth_moge.py --model constant` は、重みなしで流れだけを確かめるための偽物。**結果を実験に使ってはいけない**
- ⑤ の `data/results/summary_all.md` は [experiment.md §4.2](../../docs/depth-scale-moge2/experiment.md) にそのまま貼れる

## テスト

```powershell
.venv\Scripts\python -m pytest -q tests
```
