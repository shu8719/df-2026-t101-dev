import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../api.dart';
import '../measure.dart';
import '../ui.dart';
import '../viewer.dart';
import 'design.dart';
import 'live_capture.dart';

Uint8List _dataUrlBytes(String dataUrl) =>
    base64Decode(dataUrl.substring(dataUrl.indexOf(',') + 1));

/// S3 撮影（同意 → 撮り方 → 動画か写真2枚を選ぶ）
class CaptureScreen extends StatefulWidget {
  const CaptureScreen({super.key, required this.caseId});
  final String caseId;
  @override
  State<CaptureScreen> createState() => _CaptureScreenState();
}

class _CaptureScreenState extends State<CaptureScreen> {
  bool _consented = false;
  bool _busy = false;
  String? _status;
  String _hand = 'right';

  @override
  void initState() {
    super.initState();
    Api.instance.get('/v1/cases/${widget.caseId}').then((c) {
      if (mounted) {
        setState(() => _hand = c['requirements']?['hand_side'] ?? 'right');
      }
    });
  }

  Future<void> _consent() async {
    setState(() => _busy = true);
    try {
      await Api.instance.post('/v1/cases/${widget.caseId}/consent');
      setState(() => _consented = true);
      unawaited(MeasureEngine.instance.init()); // 裏でMediaPipeを読み込んでおく
    } catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _pick({required bool video}) async {
    setState(() {
      _busy = true;
      _status = '手を調べる準備をしています（初回だけ時間がかかります）';
    });
    try {
      final eng = MeasureEngine.instance;
      await eng.init();
      setState(
        () => _status = video ? '動画を選んでください' : '写真を2枚選んでください（上から・親指側の横から）',
      );
      final r = video
          ? await eng.pickVideo(
              (stage, i, n) => setState(() => _status = '$stage（$i/$n）'),
            )
          : await eng.pickPhotos();
      if (r['cancelled'] == true) {
        if (r['message'] != null && mounted) showError(context, r['message']);
        return;
      }
      if (!mounted) return;
      Navigator.of(context).push(
        MaterialPageRoute(
          builder: (_) => CoinScreen(
            caseId: widget.caseId,
            hand: _hand,
            first: r,
            video: video,
          ),
        ),
      );
    } catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) {
        setState(() {
          _busy = false;
          _status = null;
        });
      }
    }
  }

  Future<void> _useSample() async {
    setState(() => _busy = true);
    try {
      final m = Map<String, dynamic>.from(
        await Api.instance.get('/v1/sample-measurement'),
      );
      m['hand_side'] = _hand;
      final r = await Api.instance.put(
        '/v1/cases/${widget.caseId}/measurement?dry_run=true',
        m,
      );
      if (!mounted) return;
      Navigator.of(context).push(
        MaterialPageRoute(
          builder: (_) => MeasureConfirmScreen(
            caseId: widget.caseId,
            measurement: m,
            handModel: Map<String, dynamic>.from(r['hand_model']),
          ),
        ),
      );
    } catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!_consented) {
      return AppPage(
        title: '撮影の前に',
        bottom: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            FilledButton(
              onPressed: _busy ? null : _consent,
              child: const Text('同意して進む'),
            ),
            const SizedBox(height: 8),
            OutlinedButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('やめる'),
            ),
          ],
        ),
        children: const [
          InfoCard(
            icon: Icons.privacy_tip_outlined,
            child: Text(
              '指の角度を正確に測るため、手の部分を切り抜いた画像を最大8枚、'
              '計算のためだけに角度の計算サーバーに送ります。保存はしません。\n\n'
              '動画そのものは、この端末から外に出しません。同意しない場合は、採寸に進めません。',
            ),
          ),
        ],
      );
    }
    return AppPage(
      title: '手を撮る',
      bottom: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          FilledButton.icon(
            onPressed: _busy
                ? null
                : () => Navigator.of(context).push(
                    MaterialPageRoute(
                      builder: (_) =>
                          LiveCaptureScreen(caseId: widget.caseId, hand: _hand),
                    ),
                  ),
            icon: const Icon(Icons.videocam_outlined),
            label: const Text('カメラで撮る'),
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              Expanded(
                child: OutlinedButton(
                  onPressed: _busy ? null : () => _pick(video: true),
                  child: const Text('動画を選ぶ'),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: OutlinedButton(
                  onPressed: _busy ? null : () => _pick(video: false),
                  child: const Text('写真2枚'),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: OutlinedButton(
                  onPressed: _busy ? null : _useSample,
                  child: const Text('サンプル'),
                ),
              ),
            ],
          ),
        ],
      ),
      children: [
        if (_status != null)
          InfoCard(icon: Icons.hourglass_top, child: Text(_status!)),
        const InfoCard(
          icon: Icons.people_outline,
          child: Text('家族や支援者に撮ってもらうのがおすすめです。'),
        ),
        for (final (i, s) in const [
          '暗い色の布か紙を机に敷き、その上に、いつもの曲がり方のまま手を置きます（手の甲が上）。',
          '1円玉を、指先の前に3〜5cm離して平らに置きます。',
          'スマホを手から40〜50cm離します。できれば2倍ズームにします。',
          '親指側の低い所から、手の上を通って小指側まで、5〜10秒かけてゆっくり半周します。手と1円玉がずっと画面に入るようにします。',
        ].indexed)
          InfoCard(child: Text('${i + 1}. $s')),
      ],
    );
  }
}

/// S4 1円玉の指定（最初のフレームで1回タップ）
class CoinScreen extends StatefulWidget {
  const CoinScreen({
    super.key,
    required this.caseId,
    required this.hand,
    required this.first,
    required this.video,
  });
  final String caseId;
  final String hand;
  final Map<String, dynamic> first;
  final bool video;
  @override
  State<CoinScreen> createState() => _CoinScreenState();
}

class _CoinScreenState extends State<CoinScreen> {
  late String _image = widget.first['first'];
  late double _w = (widget.first['width'] as num).toDouble();
  late double _h = (widget.first['height'] as num).toDouble();
  late final int _count = widget.video
      ? 1
      : (widget.first['frames'] as num).toInt();
  int _index = 0; // 写真モードでは、写真ごとに1円玉を指定する
  bool? _ok;
  bool _tooSmall = false; // 1円玉が小さく写りすぎている
  bool _busy = false;
  bool _auto = true; // いま出ている結果が自動で見つけたものか（タップしたら false）

  @override
  void initState() {
    super.initState();
    _autoFind();
  }

  /// タップしなくても、写真の中の1円玉を自動で探す（OpenCV）
  Future<void> _autoFind() async {
    setState(() => _busy = true);
    try {
      final r = await MeasureEngine.instance.autoCoin(_index);
      if (!mounted) return;
      setState(() {
        _image = r['image'];
        _ok = r['ok'] == true;
        _tooSmall = r['too_small'] == true;
        _auto = true;
      });
    } catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _nextPhoto() async {
    setState(() => _busy = true);
    try {
      final r = await MeasureEngine.instance.frameImage(_index + 1);
      setState(() {
        _index++;
        _image = r['first'];
        _w = (r['width'] as num).toDouble();
        _h = (r['height'] as num).toDouble();
        _ok = null;
        _tooSmall = false;
      });
    } catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
    if (mounted) await _autoFind();
  }

  Future<void> _tap(TapUpDetails d, Size size) async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      final r = await MeasureEngine.instance.setCoin(
        d.localPosition.dx / size.width,
        d.localPosition.dy / size.height,
        _index,
      );
      setState(() {
        _image = r['image'];
        _ok = r['ok'] == true;
        _tooSmall = r['too_small'] == true;
        _auto = false;
      });
    } catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final last = _index >= _count - 1;
    return AppPage(
      title: _count > 1 ? '1円玉の確認（${_index + 1}/$_count枚目）' : '1円玉の確認',
      bottom: FilledButton(
        onPressed: _ok == true && !_busy
            ? (last
                  ? () => Navigator.of(context).pushReplacement(
                      MaterialPageRoute(
                        builder: (_) => AnalyzeScreen(
                          caseId: widget.caseId,
                          hand: widget.hand,
                          video: widget.video,
                        ),
                      ),
                    )
                  : _nextPhoto)
            : null,
        child: Text(
          !last ? '次の写真へ' : (widget.video ? 'この1円玉で解析する' : 'この1円玉で測る'),
        ),
      ),
      children: [
        Text(
          _busy
              ? '1円玉を探しています…'
              : _ok == null
              ? '写真の中の1円玉をタップ（PCはクリック）してください。'
              : _ok! && _auto
              ? '1円玉を自動で見つけました。黄色い輪が1円玉に重なっていれば、下のボタンで進みます。違う所に輪があるときは、1円玉をタップしてください。'
              : _ok!
              ? '黄色い輪が1円玉に重なっていれば、下のボタンで進みます。ずれていたら、もう一度タップします。'
              : _tooSmall
              ? '1円玉が小さく写りすぎています。カメラを手と1円玉に近づけて（またはズームして）撮り直してください。'
              : _auto
              ? '1円玉を自動では見つけられませんでした。写真の中の1円玉をタップ（PCはクリック）してください。'
              : 'うまく見つかりませんでした（赤い十字がタップした所です）。1円玉の上をもう一度タップしてください。',
        ),
        const SizedBox(height: 8),
        AspectRatio(
          aspectRatio: _w / _h,
          child: LayoutBuilder(
            builder: (context, c) => Semantics(
              label: '写真。黄色い輪が1円玉でなければ、1円玉をタップしてください',
              image: true,
              child: GestureDetector(
                excludeFromSemantics: true,
                onTapUp: (d) => _tap(d, Size(c.maxWidth, c.maxHeight)),
                child: MouseRegion(
                  cursor: _busy
                      ? SystemMouseCursors.wait
                      : SystemMouseCursors.click,
                  child: Stack(
                    fit: StackFit.expand,
                    children: [
                      ClipRRect(
                        borderRadius: BorderRadius.circular(12),
                        child: Image.memory(
                          _dataUrlBytes(_image),
                          fit: BoxFit.fill,
                          gaplessPlayback: true,
                        ),
                      ),
                      if (_busy)
                        const Center(child: CircularProgressIndicator()),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }
}

/// 解析 → 角度の計算（hand-mesh）→ 手のモデル
class AnalyzeScreen extends StatefulWidget {
  const AnalyzeScreen({
    super.key,
    required this.caseId,
    required this.hand,
    required this.video,
  });
  final String caseId;
  final String hand;
  final bool video;
  @override
  State<AnalyzeScreen> createState() => _AnalyzeScreenState();
}

class _AnalyzeScreenState extends State<AnalyzeScreen> {
  String _stage = '始めています';
  double? _value;
  String? _error;
  bool _retake = false;

  @override
  void initState() {
    super.initState();
    _run();
  }

  Future<void> _run() async {
    setState(() {
      _error = null;
      _retake = false;
    });
    final eng = MeasureEngine.instance;
    try {
      final a = await eng.analyze(
        (stage, i, n) => setState(() {
          _stage = '$stage（$i/$n）';
          _value = n == 0 ? null : i / n;
        }),
      );
      setState(() {
        _stage = '角度を計算しています';
        _value = null;
      });
      Map<String, dynamic>? mesh;
      for (var attempt = 1; attempt <= 3; attempt++) {
        try {
          mesh = await eng.callHandMesh(
            widget.caseId,
            Api.instance.user,
            widget.hand,
          );
          break;
        } on EngineError catch (e) {
          if (!e.retryable || attempt == 3) rethrow;
          setState(() => _stage = '角度を計算する準備をしています（1〜3分。$attempt/3回目）');
          await Future<void>.delayed(Duration(seconds: 5 * attempt));
        }
      }
      final m = Map<String, dynamic>.from(mesh!['measurement']);
      final r = await Api.instance.put(
        '/v1/cases/${widget.caseId}/measurement?dry_run=true',
        m,
      );
      if (!mounted) return;
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(
          builder: (_) => MeasureConfirmScreen(
            caseId: widget.caseId,
            measurement: m,
            handModel: Map<String, dynamic>.from(r['hand_model']),
            repFrames: List<dynamic>.from(a['rep_frames']),
            stats: Map<String, dynamic>.from(a['stats']),
            meshModel: mesh!['mesh_model'],
          ),
        ),
      );
    } on EngineError catch (e) {
      setState(() {
        _error = e.code == 'ENGINE_ERROR'
            ? e.message
            : '角度を計算できませんでした。もう一度撮影が必要です（約1分）。\n（${e.message}）';
        _retake = !e.retryable;
      });
    } catch (e) {
      setState(() => _error = '$e');
    }
  }

  @override
  Widget build(BuildContext context) {
    return AppPage(
      title: '手を調べています',
      bottom: _error == null
          ? null
          : Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                if (!_retake)
                  FilledButton(onPressed: _run, child: const Text('もう一度試す')),
                if (!_retake) const SizedBox(height: 8),
                OutlinedButton(
                  onPressed: () => Navigator.of(context).pop(),
                  child: const Text('撮り直す'),
                ),
              ],
            ),
      children: [
        InfoCard(
          icon: _error == null ? Icons.hourglass_top : Icons.error_outline,
          color: _error == null ? AppColors.card : const Color(0xFFFDECEA),
          child: Text(_error ?? _stage),
        ),
        if (_error == null)
          Padding(
            padding: const EdgeInsets.all(8),
            child: LinearProgressIndicator(value: _value),
          ),
        const InfoCard(
          child: Text(
            '動画はこの端末の中だけで調べています。外に送るのは、角度を計算するための手の部分の画像（最大8枚）だけで、保存しません。',
          ),
        ),
      ],
    );
  }
}

/// S5 採寸結果の確認（本人向けは「合っている／ずれている／撮り直す」だけ。数値は「詳しく見る」）
class MeasureConfirmScreen extends StatefulWidget {
  const MeasureConfirmScreen({
    super.key,
    required this.caseId,
    required this.measurement,
    required this.handModel,
    this.repFrames = const [],
    this.stats,
    this.meshModel,
  });
  final String caseId;
  final Map<String, dynamic> measurement;
  final Map<String, dynamic> handModel;
  final List<dynamic> repFrames;
  final Map<String, dynamic>? stats;
  final String? meshModel;
  @override
  State<MeasureConfirmScreen> createState() => _MeasureConfirmScreenState();
}

class _MeasureConfirmScreenState extends State<MeasureConfirmScreen> {
  bool _busy = false;

  Future<void> _save() async {
    setState(() => _busy = true);
    try {
      await Api.instance.put(
        '/v1/cases/${widget.caseId}/measurement',
        widget.measurement,
      );
      unawaited(MeasureEngine.instance.reset()); // 動画とフレームを捨てる
      if (!mounted) return;
      Navigator.of(context).pushAndRemoveUntil(
        MaterialPageRoute(
          builder: (_) => GenerateScreen(caseId: widget.caseId),
        ),
        (r) => r.isFirst,
      );
    } catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final cav = Map<String, dynamic>.from(widget.handModel['cavities']);
    final fingers = Map<String, dynamic>.from(widget.measurement['fingers']);
    const names = {
      'index': '人差し指',
      'middle': '中指',
      'ring': '薬指',
      'pinky': '小指',
    };
    const viewNames = {'top': '上から', 'thumb_side': '親指側', 'pinky_side': '小指側'};
    final warnings = {
      ...List<String>.from(widget.handModel['warnings'] ?? []),
      ...List<String>.from(widget.measurement['quality']?['warnings'] ?? []),
    };
    return AppPage(
      title: '手の形を確かめる',
      bottom: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          FilledButton(
            onPressed: _busy ? null : _save,
            child: const Text('合っている'),
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              Expanded(
                child: OutlinedButton(
                  onPressed: () => ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(
                      content: Text('プロトタイプでは、値の修正はまだできません。撮り直してください。'),
                    ),
                  ),
                  child: const Text('ずれている'),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: OutlinedButton(
                  onPressed: () => Navigator.of(context).pop(),
                  child: const Text('撮り直す'),
                ),
              ),
            ],
          ),
        ],
      ),
      children: [
        const Text('測った手を、指をカプセルで表して3Dにしました。緑の輪は、握りを置くすき間です。'),
        const SizedBox(height: 8),
        SizedBox(
          height: 320,
          child: Viewer3D.hand(handModel: widget.handModel),
        ),
        if (widget.repFrames.isNotEmpty) ...[
          const SizedBox(height: 8),
          SizedBox(
            height: 150,
            child: ListView(
              scrollDirection: Axis.horizontal,
              children: [
                for (final f in widget.repFrames)
                  Padding(
                    padding: const EdgeInsets.only(right: 8),
                    child: Column(
                      children: [
                        Expanded(
                          child: ClipRRect(
                            borderRadius: BorderRadius.circular(10),
                            child: Image.memory(
                              _dataUrlBytes(f['image']),
                              fit: BoxFit.contain,
                            ),
                          ),
                        ),
                        Text(
                          viewNames[f['view']] ?? '${f['view']}',
                          style: const TextStyle(
                            fontSize: 14,
                            color: AppColors.sub,
                          ),
                        ),
                      ],
                    ),
                  ),
              ],
            ),
          ),
        ],
        if (warnings.contains('CAVITY_PARTIAL'))
          const InfoCard(
            icon: Icons.info_outline,
            child: Text('指先と手のひらの間が少し開いています。握りは、指が回り込みきらない所が少し出る形になります。'),
          ),
        if (warnings.contains('ANGLE_DISAGREE'))
          const InfoCard(
            icon: Icons.info_outline,
            child: Text('角度の計算と、画像からの見積もりが15度以上違う関節があります。作業療法士に確かめてもらいます。'),
          ),
        if (warnings.contains('FEW_FRAMES') || warnings.contains('VIEW_BIASED'))
          const InfoCard(
            icon: Icons.info_outline,
            child: Text('使えたフレームが少ないか、見えた向きが片寄っています。ずれていたら撮り直してください。'),
          ),
        ExpansionTile(
          title: const Text('詳しく見る'),
          children: [
            if (widget.stats != null)
              ListTile(
                dense: true,
                title: Text(
                  'フレーム：候補 ${widget.stats!['candidates']} → 残した ${widget.stats!['kept']} → 使えた ${widget.stats!['used']}',
                ),
                subtitle: Text(
                  '使わなかった理由：${widget.stats!['rejected']}　角度の計算：${widget.meshModel ?? '—'}',
                ),
              ),
            ListTile(
              dense: true,
              title: Text(
                '縮尺：${widget.measurement['scale']?['px_per_mm_median']} px/mm　手の幅：${widget.measurement['palm']?['hand_width_mcp_mm']} mm',
              ),
              subtitle: Text(
                '警告：${warnings.isEmpty ? 'なし' : warnings.join('、')}',
              ),
            ),
            for (final f in names.keys)
              ListTile(
                dense: true,
                title: Text(names[f]!),
                subtitle: Text(
                  'すき間 ${cav[f]['diameter_mm'] ?? '—'} mm ／ 曲がり '
                  '${fingers[f]['flexion_deg']['mcp']}°・${fingers[f]['flexion_deg']['pip']}°・${fingers[f]['flexion_deg']['dip']}°'
                  '${fingers[f]['angles_alt_deg'] != null ? '（画像からの見積もり ${fingers[f]['angles_alt_deg']['mcp']}°・${fingers[f]['angles_alt_deg']['pip']}°・${fingers[f]['angles_alt_deg']['dip']}°）' : ''} ／ '
                  '長さ ${(fingers[f]['lengths_mm'] as List).join('・')} mm ／ 太さ（半径）${(fingers[f]['radii_mm'] as List).join('・')} mm',
                ),
              ),
          ],
        ),
      ],
    );
  }
}
