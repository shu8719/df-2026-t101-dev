import 'package:flutter/material.dart';

import 'package:jijogu_app/app/router.dart';
import 'package:jijogu_app/core/api/api.dart';
import 'package:jijogu_app/core/models/fit_report.dart';
import 'package:jijogu_app/core/ui/ui.dart';

/// S10「使ってみてどうでしたか」（docs/screens.md S10、ADR-0015）。
/// 部品と答えを選んで送ると、次にすること（使うのをやめる・フェルト・直す案・OTに相談）を出す。
/// 直す案を押すと新しい版を作り、できたら形の画面（S7）を開く
class FitReportPanel extends StatefulWidget {
  const FitReportPanel({
    super.key,
    required this.caseId,
    required this.design,
    required this.requirements,
  });
  final String caseId;
  final Map<String, dynamic> design;
  final Map<String, dynamic>? requirements;

  @override
  State<FitReportPanel> createState() => _FitReportPanelState();
}

class _FitReportPanelState extends State<FitReportPanel> {
  FitPart? _part;
  String? _result;
  Map<String, dynamic>? _advice;
  String? _busy;
  String? _error;

  String get _did => '${widget.design['design_id']}';

  void _reset() => setState(() {
    _part = null;
    _result = null;
    _advice = null;
    _error = null;
  });

  Future<void> _send({bool feltChanged = false}) async {
    final part = _part, result = _result;
    if (part == null || result == null) return;
    setState(() {
      _busy = '送っています';
      _error = null;
    });
    try {
      final r = await Api.instance.post(
        '/v1/cases/${widget.caseId}/designs/$_did/fit-report',
        {'part': part.id, 'result': result, 'felt_changed': feltChanged},
      );
      setState(() => _advice = Map<String, dynamic>.from(r['advice'] as Map));
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
      final r = await Api.instance.post('/v1/cases/${widget.caseId}/designs/$_did/refine', request);
      final id = (r['design'] as Map?)?['design_id'] as String?;
      if (!mounted) return;
      if (id == null) {
        setState(() => _error = '${r['clarify_ja'] ?? '作り直せませんでした。もう一度試してください。'}');
        return;
      }
      Navigator.of(context).pushReplacementNamed(AppRouter.design(widget.caseId, id));
    } on ApiError catch (e) {
      setState(() => _error = e.message);
    } catch (e) {
      setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _busy = null);
    }
  }

  @override
  Widget build(BuildContext context) {
    final parts = fitParts(widget.design, widget.requirements);
    final advice = _advice;
    final idle = _busy == null;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const Padding(
          padding: EdgeInsets.only(top: 22, bottom: 6),
          child: SectionLabel('使ってみてどうでしたか'),
        ),
        Text('刷って使ってみたら、部品ごとに教えてください。合わないときは、直し方をお知らせします。',
            style: AppText.supporting),
        if (advice == null) ...[
          const SizedBox(height: 8),
          Text('どの部品ですか', style: AppText.titleSmall),
          for (final p in parts)
            ChoiceButton(
              label: p.name,
              selected: _part?.id == p.id,
              onTap: () => setState(() {
                _part = p;
                if (_result != null && !fitResultsFor(p).contains(_result)) _result = null;
              }),
            ),
          if (_part != null) ...[
            const SizedBox(height: 8),
            Text('どうでしたか', style: AppText.titleSmall),
            for (final k in fitResultsFor(_part!))
              ChoiceButton(
                label: fitResultJa[k]!,
                selected: _result == k,
                onTap: () => setState(() => _result = k),
              ),
          ],
          const SizedBox(height: 8),
          FilledButton(
            onPressed: idle && _part != null && _result != null ? () => _send() : null,
            child: const Text('送る'),
          ),
        ] else
          ..._adviceView(advice, idle),
        if (_busy != null) BusyCard(text: _busy!),
        if (_error != null) ErrorCard(message: _error!),
      ],
    );
  }

  List<Widget> _adviceView(Map<String, dynamic> advice, bool idle) {
    final kind = fitAdviceKind(advice);
    final msg = Text('${advice['message_ja'] ?? ''}');
    final proposal = advice['proposal'] as Map?;
    return [
      const SizedBox(height: 8),
      Text('${_part?.name}：${fitResultJa[_result] ?? ''}', style: AppText.titleSmall),
      switch (kind) {
        FitAdviceKind.stop => InfoCard(tone: NoticeTone.error, child: msg),
        FitAdviceKind.none => InfoCard(tone: NoticeTone.success, child: msg),
        FitAdviceKind.consult => InfoCard(tone: NoticeTone.warning, child: msg),
        FitAdviceKind.felt || FitAdviceKind.refine => InfoCard(tone: NoticeTone.info, child: msg),
      },
      // フェルトを替えても合わないときは、替えたことを報告し直して直す案を受け取る
      if (kind == FitAdviceKind.felt)
        OutlinedButton(
          onPressed: idle ? () => _send(feltChanged: true) : null,
          child: const Text('フェルトを替えても合わない'),
        ),
      if (kind == FitAdviceKind.refine && proposal != null) ...[
        InfoCard(
          icon: Icons.build_rounded,
          child: Text('${proposal['summary_ja']}'),
        ),
        FilledButton(
          onPressed: idle ? () => _refine(Map<String, dynamic>.from(proposal['request'] as Map)) : null,
          child: const Text('この内容で作り直す'),
        ),
      ],
      const SizedBox(height: 8),
      OutlinedButton(
        onPressed: idle ? _reset : null,
        child: const Text('別の部品を報告する'),
      ),
    ];
  }
}
