# やること（MoGe-2）

> **このドキュメントで決めたこと**
> 1. MVP の作業を優先し、この実験は手が空いた人が行う。11/9 21:00（機能の追加を止める時刻）までに結果が出なければ、ピッチで今後の課題として話す。
> 2. まず写真1枚で、MoGe-2 の単位とカメラの情報の扱いを確かめ（M2）、Depth Pro と並べる（M4）。動画での比較（M6）は、撮影とノギスの値がそろってから行う。
> 3. 担当は毎日21:00の打ち合わせで決める。

関連：[README.md](README.md)、[method.md](method.md)、[scripts.md](scripts.md)、Depth Pro 側の [tasks.md](../depth-scale/tasks.md)

---

## 1. タスクと完了条件

| ID | タスク | 担当 | 期限 | 完了条件 | 状況（2026-11-08） |
|---|---|---|---|---|---|
| M1 | 環境を作る | 未定 | 最初に | `experiments/depth_scale_moge2/` に別の仮想環境があり、MoGe（コミット固定）と PyTorch が入り、手元のGPUで `vitl`・`vits` の重みが読み込める。`data/`・`.venv/`・`checkpoints/` が `.gitignore` に入っている | **済み**。MoGe はコミット `74fbce0`。numpy 2.5.4 のままで動き、Depth Pro 側とぶつからない。重みは vitl と vits で合わせて 1.4GB |
| M2 | 単位とカメラの情報を確かめる | 未定 | M1 のあと | `points`・`depth` の単位と、正規化された `intrinsics` を px に直す式が、コードを読んで分かり、[scripts.md §3](scripts.md#3-moge_backendpy) に書いてある。写真1枚で、点群からの長さと深度からの長さの差が 0.5% 以内 | **済み**。`f_px = fx × 幅 = fy × 高さ`（`moge_backend.py` に書いた）。差は 0.15〜0.20%。単位は明記がなくメートルと見込んだ |
| M3 | `moge_backend.py` と `try_image_moge.py` | 未定 | M2 のあと | 写真1枚から、カメラから手までの距離・焦点距離・4区間の長さと、結果の画像が出る | **済み**。マスク・面の向きの画像と、4枚まとめた画像も出す |
| M4 | Depth Pro と並べる | 未定 | M3 のあと | Depth Pro で試したのと同じ写真の結果が、[experiment.md §4.1](experiment.md#41-写真1枚の確かめtry_imagepy) にある（ノギスの値があれば一緒に） | **済み（ノギスの値はまだ）**。MoGe-2 の長さは Depth Pro の約1.8倍で、大きさの推定が外れている見込み |
| M5 | ③④⑤ とテスト | 未定 | M3 のあと | [scripts.md](scripts.md) の `depth_moge.py`・`measure_moge.py`・`compare_all.py` が動き、テストが通る | コードとテスト（12件）はできて、すべて通る。動画ではまだ動かしていない |
| M6 | 動画で比べる | 未定 | Depth Pro 側の DS6（撮影とノギス）のあと | [experiment.md §4.2](experiment.md#42-動画での比較-の出力を貼る) の表が埋まっている | 未着手 |
| M7 | 使うかを決める | 全員 | 11/9 21:00 の打ち合わせ | 採用・確かめ用・今後の課題のどれにするかが [experiment.md §4.3](experiment.md#43-決めたこと) にある | 未着手 |
| M8 | 片付け | 未定 | 実験のあと（遅くとも2026年12月） | 実験の写真・動画を消した | 未着手 |

## 2. 確かめること（要確認）

| 項目 | 関係するところ |
|---|---|
| `points`・`depth` の単位、`intrinsics` の正規化の定義 | [method.md §5](method.md#5-確かめること要確認) |
| `vitl`・`vits` の重みの大きさと、手元のGPUでの時間・メモリ | [method.md §4](method.md#4-使うモデル) |
| Python 3.12・numpy 2・PyTorch 2.14.1 で動くか | [scripts.md §8](scripts.md#8-環境と決まり) |
| 条件B（切り抜き）での、点群の x・y の扱い | [scripts.md §4](scripts.md#4--depth_mogepy) |
| 30cmほどの近さの手で、大きさがどれだけ当たるか | [experiment.md](experiment.md) |
| MoGe-3 のライセンスと、MoGe-2 より良いか | [method.md §3](method.md#3-ほかの候補と比べた結果) |

## 3. ライセンスの記録

2026-11-08 に読んだページ。

| 対象 | 内容 | ページ |
|---|---|---|
| コード | MIT（Copyright (c) Microsoft Corporation）。DINOv2 の部分は Meta AI の Apache-2.0 | https://github.com/microsoft/MoGe |
| 重み（大きい版） | Hugging Face の表示は `License: mit`。説明文は空 | https://huggingface.co/Ruicheng/moge-2-vitl-normal |
| 重み（小さい版） | 同上 | https://huggingface.co/Ruicheng/moge-2-vits-normal |
