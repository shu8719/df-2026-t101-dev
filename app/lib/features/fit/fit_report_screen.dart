import 'package:flutter/material.dart';

import 'package:jijogu_app/app/router.dart';
import 'package:jijogu_app/core/api/api.dart';
import 'package:jijogu_app/core/models/fit_report.dart';
import 'package:jijogu_app/core/ui/ui.dart';

/// S12 使ってみてどうでしたか（docs/screens.md S12、ADR-0015）。
/// S2 と同じく1問ずつ進む：問い1「どの部品ですか」→ 問い2「どうでしたか」→ 送ると次にすることを出す。
/// 直す案を押すと新しい版を作り、できたら形の画面（S7）を開く
class FitReportScreen extends StatefulWidget {
  const FitReportScreen({
    super.key,
    required this.caseId,
    required this.designId,
  });
  final String caseId;
  final String designId;

  @override
  State<FitReportScreen> createState() => _FitReportScreenState();
}

class _FitReportScreenState extends State<FitReportScreen> {
  static const _total = 2; // 問いの数（結果の画面は数えない）

  Map<String, dynamic>? _case;
  Map<String, dynamic>? _design;
  String? _loadError;

  int _step = 0; // 0：部品、1：答え、2：次にすること
  FitPart? _part;
  String? _result;
  Map<String, dynamic>? _advice;
  String? _busy;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loadError = null);
    try {
      final c = await Api.instance.get('/v1/cases/${widget.caseId}');
      final r = await Api.instance.get(
        '/v1/cases/${widget.caseId}/designs/${widget.designId}',
      );
      setState(() {
        _case = Map<String, dynamic>.from(c);
        _design = Map<String, dynamic>.from(r['design'] ?? r);
      });
    } on ApiError catch (e) {
      setState(() => _loadError = e.message);
    } catch (e) {
      setState(() => _loadError = '$e');
    }
  }

  Future<void> _send({bool feltChanged = false}) async {
    final part = _part, result = _result;
    if (part == null || result == null) return;
    setState(() {
      _busy = '送っています';
      _error = null;
    });
    try {
      final r = await Api.instance.post(
        '/v1/cases/${widget.caseId}/designs/${widget.designId}/fit-report',
        {'part': part.id, 'result': result, 'felt_changed': feltChanged},
      );
      setState(() {
        _advice = Map<String, dynamic>.from(r['advice'] as Map);
        _step = 2;
      });
    } on ApiError catch (e) {
      setState(() => _error = e.message);
    } catch (e) {
      setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _busy = null);
    }
  }

  Future<void> _refine(Map<String, dynamic> request) async {
    setState(() {
      _busy = '形を作り直しています（20〜60秒）';
      _error = null;
    });
    try {
      final r = await Api.instance.post(
        '/v1/cases/${widget.caseId}/designs/${widget.designId}/refine',
        request,
      );
      final id = (r['design'] as Map?)?['design_id'] as String?;
      if (!mounted) return;
      if (id == null) {
        setState(
          () => _error = '${r['clarify_ja'] ?? '作り直せませんでした。もう一度試してください。'}',
        );
        return;
      }
      Navigator.of(context)
          .pushReplacementNamed(AppRouter.design(widget.caseId, id));
    } on ApiError catch (e) {
      setState(() => _error = e.message);
    } catch (e) {
      setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _busy = null);
    }
  }

  void _back() {
    if (_busy != null) return;
    if (_step == 0) {
      Navigator.of(context).pop();
    } else {
      setState(() {
        _step -= 1;
        _error = null;
        if (_step < 2) _advice = null;
      });
    }
  }

  void _restart() => setState(() {
    _step = 0;
    _part = null;
    _result = null;
    _advice = null;
    _error = null;
  });

  @override
  Widget build(BuildContext context) {
    final d = _design;
    final idle = _busy == null;
    if (d == null || _loadError != null) {
      return AppPage(
        title: '使ってみてどうでしたか',
        onBack: () => Navigator.of(context).pop(),
        children: [
          if (_loadError != null)
            ErrorCard(message: _loadError!, onRetry: _load)
          else
            const BusyCard(text: '読み込んでいます'),
        ],
      );
    }
    if (!canReportFit(d, _case)) {
      return AppPage(
        title: '使ってみてどうでしたか',
        onBack: () => Navigator.of(context).pop(),
        bottom: OutlinedButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('戻る'),
        ),
        children: const [
          InfoCard(
            icon: Icons.lock_outline_rounded,
            child: Text('印刷用のデータを出した最新の版だけ報告できます。'),
          ),
        ],
      );
    }
    final parts = fitParts(
      d,
      (_case?['requirements'] as Map?)?.cast<String, dynamic>(),
    );
    final (Widget? bottom, List<Widget> body) = switch (_step) {
      0 => (
        _part == null
            ? null
            : FilledButton(
                onPressed: () => setState(() => _step = 1),
                child: const Text('次へ'),
              ),
        _question('どの部品ですか', [
          for (final p in parts)
            ChoiceButton(
              label: p.name,
              selected: _part?.id == p.id,
              onTap: () => setState(() {
                _part = p;
                if (_result != null && !fitResultsFor(p).contains(_result)) {
                  _result = null;
                }
              }),
            ),
        ]),
      ),
      1 => (
        _result == null
            ? null
            : FilledButton(
                onPressed: idle ? () => _send() : null,
                child: const Text('送る'),
              ),
        _question('どうでしたか', [
          Text(_part?.name ?? '', style: AppText.supporting),
          for (final k in fitResultsFor(_part!))
            ChoiceButton(
              label: fitResultJa[k]!,
              selected: _result == k,
              onTap: () => setState(() => _result = k),
            ),
        ]),
      ),
      _ => _adviceView(_advice ?? const {}, idle),
    };
    return AppPage(
      title: '使ってみてどうでしたか',
      onBack: _back,
      bottom: bottom,
      children: [
        ...body,
        if (_busy != null) BusyCard(text: _busy!),
        if (_error != null) ErrorCard(message: _error!),
      ],
    );
  }

  /// 1つの問い（S2 と同じ見た目：「質問 1 / 2」＋進み具合の棒＋見出し＋選択肢）
  List<Widget> _question(String title, List<Widget> choices) => [
    Text(
      '質問 ${_step + 1} / $_total',
      style: AppText.labelLarge.copyWith(color: AppColors.onSurfaceVariant),
    ),
    const SizedBox(height: 8),
    LinearProgressIndicator(value: (_step + 1) / _total),
    const SizedBox(height: 12),
    Semantics(
      header: true,
      child: Text(
        title,
        style: AppText.headlineSmall.copyWith(color: AppColors.onSurface),
      ),
    ),
    const SizedBox(height: 6),
    if (_step == 0) Text('刷って使ってみた部品を選んでください。', style: AppText.supporting),
    ...choices,
  ];

  (Widget?, List<Widget>) _adviceView(Map<String, dynamic> advice, bool idle) {
    final kind = fitAdviceKind(advice);
    final msg = Text('${advice['message_ja'] ?? ''}');
    final proposal = advice['proposal'] as Map?;
    final canRefine = kind == FitAdviceKind.refine && proposal != null;
    final Widget bottom = canRefine
        ? FilledButton(
            onPressed: idle
                ? () => _refine(
                    Map<String, dynamic>.from(proposal['request'] as Map),
                  )
                : null,
            child: const Text('この内容で作り直す'),
          )
        : OutlinedButton(
            onPressed: idle
                ? () => Navigator.of(context).pushReplacementNamed(
                    AppRouter.print(widget.caseId, widget.designId),
                  )
                : null,
            child: const Text('ダウンロードの画面へ'),
          );
    return (
      bottom,
      [
        Semantics(
          header: true,
          child: Text(
            '次にすること',
            style: AppText.headlineSmall.copyWith(color: AppColors.onSurface),
          ),
        ),
        const SizedBox(height: 6),
        Text(
          '${_part?.name}：${fitResultJa[_result] ?? ''}',
          style: AppText.supporting,
        ),
        const SizedBox(height: 6),
        switch (kind) {
          FitAdviceKind.stop => InfoCard(tone: NoticeTone.error, child: msg),
          FitAdviceKind.none => InfoCard(tone: NoticeTone.success, child: msg),
          FitAdviceKind.consult => InfoCard(
            tone: NoticeTone.warning,
            child: msg,
          ),
          FitAdviceKind.felt ||
          FitAdviceKind.refine => InfoCard(tone: NoticeTone.info, child: msg),
        },
        // フェルトを替えても合わないときは、替えたことを添えて報告し直し、直す案を受け取る
        if (kind == FitAdviceKind.felt)
          OutlinedButton(
            onPressed: idle ? () => _send(feltChanged: true) : null,
            child: const Text('フェルトを替えても合わない'),
          ),
        if (canRefine)
          InfoCard(
            icon: Icons.build_rounded,
            child: Text('${proposal['summary_ja']}'),
          ),
        const SizedBox(height: 8),
        OutlinedButton(
          onPressed: idle ? _restart : null,
          child: const Text('別の部品を報告する'),
        ),
        TextButton(
          onPressed: idle
              ? () =>
                    Navigator.of(context)
                        .pushNamedAndRemoveUntil('/', (r) => false)
              : null,
          child: const Text('ホームへ戻る'),
        ),
      ],
    );
  }
}
