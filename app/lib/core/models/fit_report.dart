import 'package:jijogu_app/core/models/attachments.dart';

// ───────── S10 の「使ってみてどうでしたか」（docs/adr/0015-refit-reorder.md、api.md §3.14） ─────────

/// 答えの選択肢（API の result と、画面の文）
const fitResultJa = {
  'good': 'ちょうどいい',
  'loose': 'ゆるい',
  'tight_pain': 'きつい・痛い',
  'red': '赤くなった',
  'tool_slips': '道具が抜ける',
};

/// 報告できる部品1つ（id は API の part：cover か取り付け具の ID）
class FitPart {
  const FitPart(this.id, this.name, this.printKey);
  final String id;
  final String name;
  final String printKey;
  bool get isCover => id == 'cover';
}

/// 報告できる部品：カバーと、取り付け具ごとのクリップ（名前はダウンロードの行に合わせる）
List<FitPart> fitParts(Map<String, dynamic> design, Map<String, dynamic>? requirements) {
  final atts = viewAttachments(design, requirements);
  return [
    const FitPart('cover', 'カバー', 'cover'),
    for (final a in atts)
      FitPart(
        '${a['id']}',
        atts.length == 1 ? 'C字クリップ' : '${attachmentLabel(a, atts)}のクリップ',
        (a['print_key'] as String?) ?? 'c_clip',
      ),
  ];
}

/// その部品で選べる答え（「道具が抜ける」はクリップだけ）
List<String> fitResultsFor(FitPart part) => [
  for (final k in fitResultJa.keys)
    if (!(part.isCover && k == 'tool_slips')) k,
];

/// 報告の欄を出すか：印刷用データがあって読める（確認済みかデモ）最新の版だけ
bool canReportFit(Map<String, dynamic> design, Map<String, dynamic>? caseDoc, {required bool ready}) =>
    ready &&
    (((design['files'] as Map?)?['print'] as Map?)?.isNotEmpty ?? false) &&
    caseDoc?['current_design_id'] == design['design_id'];

/// 報告した版と比べて、この印刷用のキーの部品を刷り直すか（true＝刷り直す、false＝そのまま使える、null＝報告から作った版ではない）
bool? needsReprint(Map<String, dynamic> design, String printKey) {
  final r = design['reprint'];
  if (r is! Map) return null;
  if ((r['changed'] as List? ?? const []).contains(printKey)) return true;
  if ((r['unchanged'] as List? ?? const []).contains(printKey)) return false;
  return null;
}

/// 返ってきた次にすること（advice）の見せ方
enum FitAdviceKind { stop, none, felt, refine, consult }

FitAdviceKind fitAdviceKind(Map<String, dynamic> advice) => switch (advice['kind']) {
  'stop' => FitAdviceKind.stop,
  'felt' => FitAdviceKind.felt,
  'refine' => FitAdviceKind.refine,
  'consult' => FitAdviceKind.consult,
  _ => FitAdviceKind.none,
};
