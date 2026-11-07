# やること（Depth Anything 3）

> **このドキュメントで決めたこと**
> 1. MVP の作業を優先し、この実験は手が空いた人が行う。11/9 21:00（機能の追加を止める時刻）までに結果が出なければ、ピッチで今後の課題として話す。
> 2. まず DA3 の深度の直し方（焦点距離の大きさ合わせ・÷300・単位）をコードで確かめ（D2）、写真1枚で4つの組み合わせを比べる（D4）。動画（D6）は、写真1枚で②が Depth Pro に近いと分かってから行う。
> 3. 担当は毎日21:00の打ち合わせで決める。

関連：[README.md](README.md)、[method.md](method.md)、[scripts.md](scripts.md)

---

## 1. タスクと完了条件

| ID | タスク | 担当 | 期限 | 完了条件 | 状況（2026-11-08） |
|---|---|---|---|---|---|
| D1 | 環境を作る | 未定 | 最初に | 共通の環境（`experiments/depth_scale/.venv`）に Depth Anything 3（コミット固定）が入り、手元のGPUで `DA3METRIC-LARGE` と `DA3-BASE` の重みが読み込める。`data/`・`checkpoints/` が `.gitignore` に入っている | **済み（重みの読み込みは D4 で）**。はじめ別の環境を作ってディスクが満杯になり、PyTorch も 2.15.0 に入れ替わったので、環境を1つにまとめた（[scripts.md §8](scripts.md#8-環境と決まり)） |
| D2 | 深度の直し方を確かめる | 未定 | D1 のあと | 処理の大きさ、「÷300」の焦点距離をどの画像の px で数えるか、出力の単位、焦点距離を渡せるかが、コードを読んで分かり、[scripts.md §3](scripts.md#3-da3_backendpy) に書いてある | **済み**。長い辺 504px・14px の倍数、「÷300」の焦点距離は縮めた画像の px（fx・fy の平均）。カメラの情報を渡さなければ出力は掛ける前の値。内容は `da3_backend.py` の冒頭に書いた |
| D3 | `da3_backend.py`・`focal_sources.py`・`try_image_da3.py` とテスト | 未定 | D2 のあと | 写真1枚で、4つの組み合わせの距離・焦点距離・4区間の長さと、結果の画像が出る。テストが通る | **コードとテストはできた**（テスト11件が通る） |
| D4 | 写真1枚で比べる | 未定 | D3 のあと | [experiment.md §3.1](experiment.md#31-写真1枚) の表が、正解の値と一緒に埋まり、[method.md §3](method.md#結果での判断) の判断が書いてある | **済み（正解の数値はまだ）**。①が外れた（長さが Depth Pro より約25%大きい）。DA3 では焦点距離が長さにほとんど効かないことも分かった。次は予備の候補（MapAnything）か、今後の課題とするかを決める |
| D5 | 動画の ③④⑤ とテスト | 未定 | D4 で②が合ったら | [scripts.md §6](scripts.md#6-動画-depth_da3pymeasure_da3pycompare_all_da3py) のスクリプトが動き、テストが通る | 未着手 |
| D6 | 動画で比べる | 未定 | Depth Pro 側の DS6（撮影とノギス）と MoGe-2 側の ③ のあと | [experiment.md §3.2](experiment.md#32-動画での比較) の表が埋まっている | 未着手 |
| D7 | 使うかを決める | 全員 | 11/9 21:00 の打ち合わせ | 採用・確かめ用・今後の課題のどれにするかが [experiment.md §3.3](experiment.md#33-決めたこと) にある | 未着手 |
| D8 | 片付け | 未定 | 実験のあと（遅くとも2026年12月） | 実験の写真・動画を消した | 未着手 |

## 2. 確かめること（要確認）

| 項目 | 関係するところ |
|---|---|
| DA3 の処理の大きさ、「÷300」の焦点距離の数え方、出力の単位、焦点距離を渡せるか | [method.md §5](method.md#5-確かめること要確認) |
| `DA3-BASE` のモデルのページのライセンス（README の表だけでなく） | [method.md §6](method.md#6-ライセンス) |
| `DA3-BASE` が1枚の写真からカメラの情報を推定できるか | [method.md §3](method.md#3-試す組み合わせ) の④ |
| 入れ方（PyPI か、コミット固定か）、`xformers` の要否、Python 3.12・numpy 2・PyTorch 2.14.1 で動くか | [scripts.md §8](scripts.md#8-環境と決まり) |
| 手元のGPUでの時間とメモリ（見込みは Depth Pro より速い） | [experiment.md §3.1](experiment.md#31-写真1枚) |
| 本番に入れる場合、L4（24GB）に SAM 3D Body と MoGe-2 と DA3 が載るか | [../depth-scale/tasks.md §4](../depth-scale/tasks.md#4-採用することになったら) |

## 3. ライセンスの記録

2026-11-08 に読んだページ。

| 対象 | 内容 | ページ |
|---|---|---|
| コード | Apache-2.0（Copyright 2025 The Depth Anything 3 Team） | https://github.com/ByteDance-Seed/Depth-Anything-3 |
| `DA3METRIC-LARGE` の重み | Hugging Face の表示は `License: apache-2.0` | https://huggingface.co/depth-anything/DA3METRIC-LARGE |
| `DA3-BASE` の重み | README の表では Apache-2.0（モデルのページは未確認） | https://github.com/ByteDance-Seed/Depth-Anything-3 |
| 使わない版 | `DA3-LARGE`・`DA3-GIANT`・`DA3NESTED-GIANT-LARGE`（と `-1.1`）は CC BY-NC 4.0（非営利だけ） | 同上 |
