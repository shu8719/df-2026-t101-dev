import 'dart:async';

import 'package:flutter/material.dart';
import 'package:web/web.dart' as web;

import '../api.dart';
import '../ui.dart';
import '../viewer.dart';

/// S6 生成中
class GenerateScreen extends StatefulWidget {
  const GenerateScreen({super.key, required this.caseId});
  final String caseId;
  @override
  State<GenerateScreen> createState() => _GenerateScreenState();
}

class _GenerateScreenState extends State<GenerateScreen> {
  static const steps = ['部品を選んでいます', '寸法を決めています', '形を作っています', '画像で確認しています'];
  int _step = 0;
  Timer? _timer;
  Object? _error;

  @override
  void initState() {
    super.initState();
    _timer = Timer.periodic(const Duration(milliseconds: 700), (_) {
      if (_step < steps.length - 1) setState(() => _step++);
    });
    _run();
  }

  Future<void> _run() async {
    setState(() => _error = null);
    try {
      final r = await Api.instance.post(
        '/v1/cases/${widget.caseId}/designs',
        {},
      );
      final d = r['design'];
      if (!mounted) return;
      if (d['status'] == 'failed') {
        throw ApiError(d['error']?['message'] ?? '形を作れませんでした');
      }
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(
          builder: (_) =>
              PreviewScreen(caseId: widget.caseId, designId: d['design_id']),
        ),
      );
    } catch (e) {
      setState(() => _error = e);
    }
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AppPage(
      title: '形を作っています',
      children: [
        for (final (i, s) in steps.indexed)
          ListTile(
            leading: Icon(
              i < _step
                  ? Icons.check_circle
                  : (i == _step ? Icons.autorenew : Icons.circle_outlined),
              color: i <= _step ? AppColors.ok : AppColors.line,
            ),
            title: Text(s),
          ),
        if (_error != null)
          InfoCard(
            color: const Color(0xFFFDECEA),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('$_error'),
                TextButton(onPressed: _run, child: const Text('もう一度作る')),
              ],
            ),
          ),
      ],
    );
  }
}

/// S7 プレビューと微調整（スマホでも使える）
class PreviewScreen extends StatefulWidget {
  const PreviewScreen({
    super.key,
    required this.caseId,
    required this.designId,
  });
  final String caseId;
  final String designId;
  @override
  State<PreviewScreen> createState() => _PreviewScreenState();
}

class _PreviewScreenState extends State<PreviewScreen> {
  Map<String, dynamic>? _case;
  Map<String, dynamic>? _design;
  bool _busy = false;
  final _ctrl = TextEditingController();
  static const colors = {
    '#3A7CA5': 'あお',
    '#2F7D6D': 'みどり',
    '#E07A5F': 'オレンジ',
    '#E8A0BF': 'ピンク',
    '#F2E8CF': 'クリーム',
    '#3D405B': 'こん',
  };

  @override
  void initState() {
    super.initState();
    _load(widget.designId);
  }

  Future<void> _load(String designId) async {
    final c = Map<String, dynamic>.from(
      await Api.instance.get('/v1/cases/${widget.caseId}'),
    );
    setState(() {
      _case = c;
      _design = Map<String, dynamic>.from(
        (c['designs'] as List).firstWhere((d) => d['design_id'] == designId),
      );
    });
  }

  Future<void> _refine(Map<String, dynamic> body) async {
    setState(() => _busy = true);
    try {
      final r = await Api.instance.post(
        '/v1/cases/${widget.caseId}/designs/${_design!['design_id']}/refine',
        body,
      );
      if (r['clarify_ja'] != null) {
        if (mounted) showError(context, r['clarify_ja']);
        return;
      }
      await _load(r['design']['design_id']);
    } catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _preparePrint() async {
    setState(() => _busy = true);
    try {
      await Api.instance.post(
        '/v1/cases/${widget.caseId}/designs/${_design!['design_id']}/prepare-print',
      );
      await _load(_design!['design_id']);
      if (!mounted) return;
      Navigator.of(context).push(
        MaterialPageRoute(builder: (_) => DownloadScreen(design: _design!)),
      );
    } catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final d = _design;
    if (d == null || _case == null) {
      return const AppPage(
        title: 'プレビュー',
        children: [Center(child: Text('読み込んでいます…'))],
      );
    }
    final g = Map<String, dynamic>.from(d['params']['grip_body']);
    final hand = _case!['requirements']['hand_side'] ?? 'right';
    final issues = List<dynamic>.from(d['review']?['unresolved_issues'] ?? []);
    final color = d['style']['color'] as String;
    return AppPage(
      title: '形ができました（${d['revision']}版）',
      bottom: FilledButton.icon(
        onPressed: _busy ? null : _preparePrint,
        icon: const Icon(Icons.print_outlined),
        label: const Text('印刷用のデータを作る'),
      ),
      children: [
        if (_case!['demo'] == true) const DemoBanner(),
        if (d['status'] == 'needs_attention')
          InfoCard(
            color: const Color(0xFFFFF4E0),
            icon: Icons.warning_amber_rounded,
            child: Text(
              '確認で解決しなかった点があります：\n${issues.map((i) => '・${i['description_ja']}').join('\n')}',
            ),
          ),
        SizedBox(
          height: 380,
          child: Viewer3D.stl(
            key: ValueKey(d['design_id']),
            stlUrl: Api.instance.fileUrl(d['files']['preview_stl']),
            color: color,
            capsules: d['variant'] == 'fitted' ? g['capsules'] as List : null,
            hand: hand,
          ),
        ),
        const SizedBox(height: 8),
        InfoCard(child: Text(d['summary_ja'] ?? '')),
        Text('見た目', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 6),
        Wrap(
          spacing: 10,
          runSpacing: 10,
          children: [
            for (final e in colors.entries)
              Semantics(
                label: '色：${e.value}',
                selected: e.key == color,
                button: true,
                child: InkWell(
                  onTap: _busy
                      ? null
                      : () => _refine({
                          'style': {'color': e.key, 'pattern': 'none'},
                        }),
                  borderRadius: BorderRadius.circular(28),
                  child: Container(
                    width: 52,
                    height: 52,
                    decoration: BoxDecoration(
                      color: Color(
                        int.parse('FF${e.key.substring(1)}', radix: 16),
                      ),
                      shape: BoxShape.circle,
                      border: Border.all(
                        color: e.key == color ? AppColors.ink : AppColors.line,
                        width: e.key == color ? 3 : 1,
                      ),
                    ),
                    child: e.key == color
                        ? const Icon(Icons.check, color: Colors.white)
                        : null,
                  ),
                ),
              ),
          ],
        ),
        const SizedBox(height: 16),
        Text('言葉で直す', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 6),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            for (final s in ['もう少し太く', 'もう少し細く', 'くぼみを浅く', 'ナットを回しやすく'])
              SuggestButton(
                label: s,
                onPressed: _busy ? null : () => _refine({'instruction': s}),
              ),
          ],
        ),
        const SizedBox(height: 8),
        Row(
          children: [
            Expanded(
              child: TextField(
                controller: _ctrl,
                maxLength: 500,
                decoration: const InputDecoration(
                  hintText: '例：もう少し短く',
                  border: OutlineInputBorder(),
                  counterText: '',
                ),
              ),
            ),
            const SizedBox(width: 8),
            IconButton.filled(
              onPressed: _busy
                  ? null
                  : () => _refine({'instruction': _ctrl.text}),
              icon: const Icon(Icons.send),
            ),
          ],
        ),
        if (_busy)
          const Padding(
            padding: EdgeInsets.all(12),
            child: LinearProgressIndicator(),
          ),
        ExpansionTile(
          title: const Text('詳しく見る（寸法と理由）'),
          children: [
            for (final row in (d['param_rows'] as List))
              ListTile(
                dense: true,
                title: Text(
                  '${row['label_ja']}：${row['value']} ${row['unit']}',
                ),
                subtitle: Text(
                  '${_sourceJa(row['source'])}・${row['reason_ja'] ?? ''}',
                ),
              ),
            ListTile(
              dense: true,
              title: Text(
                'くり抜きの深さ（最大）：${d['validation']?['carve']?['max_depth_mm'] ?? '—'} mm',
              ),
              subtitle: Text(
                '穴まわりの壁（最小）：${d['validation']?['carve']?['min_wall_mm'] ?? '—'} mm',
              ),
            ),
          ],
        ),
      ],
    );
  }
}

String _sourceJa(String? s) => switch (s) {
  'measured' => '採寸から',
  'rule' => '決まった式',
  'interview' => '質問の答えから',
  'ai' => 'AIが調整',
  'user' => 'あなたが変更',
  _ => '既定の値',
};

/// S10 ダウンロードと印刷ガイド
class DownloadScreen extends StatelessWidget {
  const DownloadScreen({super.key, required this.design});
  final Map<String, dynamic> design;

  @override
  Widget build(BuildContext context) {
    final url = Api.instance.fileUrl(design['files']['print_stl']);
    return AppPage(
      title: '印刷する',
      bottom: FilledButton.icon(
        onPressed: () => web.window.open(url, '_blank'),
        icon: const Icon(Icons.download),
        label: const Text('STLをダウンロード'),
      ),
      children: const [
        DemoBanner(),
        InfoCard(
          icon: Icons.settings_outlined,
          child: Text(
            'おすすめの設定（PLA）：積層0.2mm、外壁4本、充填25%（ジャイロイド）、サポートなし、握りにはブリム5mm。'
            '握りはコレットを上にして立てて、ナットは平らに置いて刷ります。',
          ),
        ),
        InfoCard(
          icon: Icons.build_outlined,
          child: Text('組み立て：ナットをねじ込む → 道具の柄を差す → ナットを締める → 強く引いて抜けないか確かめる。'),
        ),
        InfoCard(
          icon: Icons.health_and_safety_outlined,
          color: Color(0xFFFFF4E0),
          child: Text(
            '注意：口に入れないでください。痛みが出たら使うのをやめて、作業療法士に相談してください。'
            'PLAは熱に弱いので、熱いお湯につけないでください。',
          ),
        ),
      ],
    );
  }
}
