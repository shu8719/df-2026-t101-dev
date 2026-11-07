# 実験：AIの距離推定で手を実寸にする（1円玉がないとき）

仕様は [docs/depth-scale/scripts.md](../../docs/depth-scale/scripts.md)、実験の手順は [docs/depth-scale/experiment.md](../../docs/depth-scale/experiment.md) を正とする。ここには動かし方だけを書く。

**本番のコード（`app/`・`api/`・`hand_mesh/`）は変えない。** 動画・フレーム・深度は `data/` にだけ置き、コミットしない。

## 準備（Windows、PowerShell）

**この `.venv` は、3つの実験（Depth Pro・MoGe-2・Depth Anything 3）で共通に使う。** PyTorch（約3GB）を実験ごとに入れるとディスクを圧迫するため（2026-11-08 にディスクが満杯になった）。追加のライブラリは、必ず `..\constraints.txt` を `-c` で渡して入れ、PyTorch・numpy の版が勝手に変わらないようにする。

```powershell
cd experiments\depth_scale
python -m venv .venv
.venv\Scripts\python -m pip install --no-cache-dir -c ..\constraints.txt -r requirements.txt
```

MoGe-2・Depth Anything 3 の分は、それぞれのフォルダの README を見て、この `.venv` に入れる。

- ② で使う MediaPipe のモデルは、本番と同じ `app/web/mediapipe/models/hand_landmarker.task`。なければリポジトリの直下で `bash scripts/fetch_mediapipe.sh` を実行するか、`--model` で場所を指定する
- ③ で Depth Pro を使うときは `requirements-depth.txt` を見て入れる。重み（1.9GB）は `checkpoints/` に置く（コミットしない）
- **Depth Pro の重みは研究目的だけのライセンス**（Apple Machine Learning Research Model License）。この実験（精度を測る）だけに使い、アプリには組み込まない
- iPhone の動画（HEVC）を読めないときは ffmpeg が要る

## 写真1枚で手軽に試す

```powershell
.venv\Scripts\python try_image.py <写真のパス>
```

手の甲を上にして机に置き、30cmほど上から撮った写真を渡すと、カメラから手までの距離と、手の甲の4区間の長さ（mm）を表示する。定規やノギスで測った値と比べる。写真はどこにも保存しない。

## データを置く

`data/` に次のものを置く（形は [scripts.md §2](../../docs/depth-scale/scripts.md#2-データの置き場所と形)）。

| もの | 書く人 |
|---|---|
| `data/recordings.csv`（撮影の記録） | 人 |
| `data/truth.csv`（ノギスの正解） | 人 |
| `data/raw/{rec_id}.mp4`（動画） | 人 |
| `data/coin/{rec_id}.json`（同じ動画をアプリに読み込ませた採寸） | 人（`.localstore/db/cases/{case_id}.json` の `measurement` を写す） |

撮影ID `rec_id` は `p1_t1` の形。人は番号で表し、名前は書かない。

## 動かす

```powershell
.venv\Scripts\python extract_frames.py --all          # ① 動画 → フレーム
.venv\Scripts\python landmarks.py --all               # ② 手の21点
.venv\Scripts\python depth.py --all --cond A,B,C      # ③ 深度と焦点距離（Depth Pro）
.venv\Scripts\python measure.py --all --cond A,B,C --radius 1,3,5 --skin-offset-mm 0,10   # ④ 長さ
.venv\Scripts\python compare.py --radius 3 --skin-offset-mm 0                             # ⑤ 比べる
```

- 出力があれば飛ばす。作り直すときは `--force`（①〜③）
- `depth.py --model constant` は、重みなしで流れだけを確かめるための偽物（深度300mm一定）。**結果を実験に使ってはいけない**
- ⑤ の `data/results/summary.md` は、[experiment.md §6](../../docs/depth-scale/experiment.md#6-結果) にそのまま貼れる

## テスト

```powershell
.venv\Scripts\python -m pytest -q tests
```

本物の動画やモデルを使わずに、計算（3Dに直す式・焦点距離の換算・集計・ずれ）と、偽物の深度での ③〜⑤ の流れを確かめる。

## 片付け

実験が終わったら `data/raw/`・`data/frames/`・`data/depth/`・`data/tmp/` を消す（`data/results/` の数値は残してよい）。
