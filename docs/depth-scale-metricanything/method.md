# しくみと方法（MetricAnything）

> **このドキュメントで決めたこと**
> 1. 重み `student_pointmap.pt` を Hugging Face から取ってきて、導入済みの MoGe の `MoGeModel.from_pretrained(重みのパス)` で読み込む（同梱の古い MoGe は使わない）。長さの出し方は MoGe-2 の実験と同じ（点のまわりの点群の中央値、[../depth-scale-moge2/method.md §2](../depth-scale-moge2/method.md#2-出力の扱い)）。
> 2. **時間は、モデルを読み込んだあと、写真1枚ごとに段階別に測る**：①写真を読んで縮める ②MediaPipe で手の21点 ③MetricAnything の推論 ④長さの計算。合計を「画像の処理から計測結果が出るまでの時間」とする。モデルの読み込み（最初の1回だけ）は別に示す。
> 3. 補正の評価は YOLO26 Depth の実験と同じ（[../depth-scale-yolo26/method.md §4](../depth-scale-yolo26/method.md#4-補正の評価)）。

関連：[README.md](README.md)、[experiment.md](experiment.md)

---

## 1. 読み込みと推論（2026-11-08 に確かめた）

```python
from huggingface_hub import hf_hub_download
from moge.model.v2 import MoGeModel
p = hf_hub_download("yjh001/metricanything_student_pointmap", "student_pointmap.pt", cache_dir=checkpoints)
model = MoGeModel.from_pretrained(p)          # 導入済みの MoGe（74fbce0）で、厳密に（strict）読み込めた
out = model.infer(画像（3, H, W）, 0〜1)       # points（m）・depth・mask・intrinsics（正規化）
```

- 同梱の MoGe は古い版で、重みのファイル名（`student_pointmap.pt`）と、多少合わなくても読み込む設定（`strict=False`）が違うだけだった。重みの中身（設定）は MoGe-2 の ViT-L と同じ形で、面の向きの出力（法線）はない
- 焦点距離は推定させる（与えない）。px への直し方は MoGe-2 と同じ（`f_px = fx × 幅`）

## 2. 長さの出し方

MoGe-2 の実験と同じ。写真を長い辺 1280px まで縮め、MediaPipe の手首と付け根の5点のまわり（半径 3px）の点群の、x・y・z それぞれの中央値を3D位置にして、4区間の長さを出す。確かめとして、深度と焦点距離から3Dに直した長さも出す。

## 3. 時間の測り方

| 段階 | 中身 |
|---|---|
| モデルの読み込み | 最初の1回だけ（重みの読み込みと GPU への転送） |
| ① 写真の読み込み | ファイルを読み、撮影情報の向きどおりに回し、長い辺 1280px に縮める |
| ② 手の21点 | MediaPipe（CPU） |
| ③ 推論 | MetricAnything（GPU、RTX 3080 Ti Laptop） |
| ④ 長さの計算 | 点のまわりの点群の中央値と、4区間の長さ |
| **合計** | **①〜④（画像の処理から計測結果が出るまで）** |

- 最初の1枚は GPU の準備の分だけ遅いので、2枚目以降の中央値も示す
- 本番で使う場合は、Cloud Run の L4 での時間を別に測る必要がある（今回は手元の GPU）
