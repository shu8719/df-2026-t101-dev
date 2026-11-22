import 'package:flutter_test/flutter_test.dart';
import 'package:jijogu_app/core/api/api_error.dart';
import 'package:jijogu_app/core/api/mock_backend.dart';
import 'package:jijogu_app/core/models/fit_report.dart';
import 'package:jijogu_app/core/models/requirements.dart';

/// S10「使ってみてどうでしたか」（ADR-0015）。決め方は純粋な関数で、報告から直す流れはモックで確かめる
void main() {
  final mock = MockBackend.instance;
  Map<String, dynamic> m(Object? x) => Map<String, dynamic>.from(x as Map);

  ToolAnswer pen() => ToolAnswer()..activity = 'write'..toolType = 'pen'..toolDmm = 9.0..shaftShape = 'round';
  ToolAnswer spoon() => ToolAnswer()..activity = 'eat'..toolType = 'spoon'..toolDmm = 12.0..shaftShape = 'round';

  /// ケースを作って最初の版を作り、デモの印刷用データを出す（刷って使った版）
  Future<(String, Map<String, dynamic>)> printed(List<ToolAnswer> tools) async {
    final id = (await mock.handle('POST', '/v1/cases', {'title': 't'}))['case_id'] as String;
    final a = Answers()
      ..tools = tools
      ..handSide = 'right'..donningBy = 'self'..fingerState = 'fist'..captureBy = 'helper';
    await mock.handle('PUT', '/v1/cases/$id/requirements', a.toJson());
    await mock.handle('PUT', '/v1/cases/$id/measurement', {
      'capture': {'mesh_id': 'hm_1'},
      'palm': {'hand_width_mcp_mm': 75},
    });
    final d = m((await mock.handle('POST', '/v1/cases/$id/designs', {}))['design']);
    await mock.handle('POST', '/v1/cases/$id/designs/${d['design_id']}/prepare-print', {});
    return (id, d);
  }

  Future<Map<String, dynamic>> report(String cid, String did, Map<String, dynamic> body) async =>
      m(await mock.handle('POST', '/v1/cases/$cid/designs/$did/fit-report', body));

  group('部品と答えの選択肢', () {
    test('取り付け具1つ：カバーと C字クリップ', () {
      final d = {
        'attachments': [
          {'id': 'a1', 'tool_type': 'pen', 'tool_d_mm': 9.0, 'angle_deg': 60, 'primary': true, 'print_key': 'c_clip'},
        ],
      };
      final ps = fitParts(d, null);
      expect([for (final p in ps) p.name], ['カバー', 'C字クリップ']);
      expect([for (final p in ps) p.printKey], ['cover', 'c_clip']);
    });

    test('取り付け具2つ：道具の名前つき', () {
      final d = {
        'attachments': [
          {'id': 'a1', 'tool_type': 'pen', 'tool_d_mm': 9.0, 'angle_deg': 60, 'primary': true, 'print_key': 'c_clip'},
          {'id': 'a2', 'tool_type': 'spoon', 'tool_d_mm': 12.0, 'angle_deg': 60, 'print_key': 'c_clip_a2'},
        ],
      };
      expect([for (final p in fitParts(d, null)) p.name], ['カバー', 'ペンのクリップ', 'スプーンのクリップ']);
    });

    test('「道具が抜ける」はクリップだけ', () {
      expect(fitResultsFor(const FitPart('cover', 'カバー', 'cover')), isNot(contains('tool_slips')));
      expect(fitResultsFor(const FitPart('a1', 'C字クリップ', 'c_clip')), contains('tool_slips'));
      expect(fitResultsFor(const FitPart('a1', 'C字クリップ', 'c_clip')).length, 5);
    });

    test('S12 を開けるのは、印刷用データを読める（確認済みかデモ）最新の版だけ', () {
      final approved = {
        'design_id': 'd1',
        'files': {'print': {'cover': 'x'}},
        'approval': {'status': 'approved'},
      };
      final demoOnly = {...approved, 'approval': {'status': 'none'}};
      expect(canReportFit(approved, {'current_design_id': 'd1'}), isTrue);
      expect(canReportFit(demoOnly, {'current_design_id': 'd1', 'demo': true}), isTrue);
      expect(canReportFit(demoOnly, {'current_design_id': 'd1', 'demo': false}), isFalse); // 確認前
      expect(canReportFit(approved, {'current_design_id': 'd2'}), isFalse); // 最新の版でない
      expect(canReportFit({...approved, 'files': {}}, {'current_design_id': 'd1'}), isFalse); // 印刷用データがない
    });

    test('刷り直す印：reprint がない版は出さない', () {
      final d = {
        'reprint': {'changed': ['cover'], 'unchanged': ['c_clip']},
      };
      expect(needsReprint(d, 'cover'), isTrue);
      expect(needsReprint(d, 'c_clip'), isFalse);
      expect(needsReprint(d, 'c_clip_a2'), isNull);
      expect(needsReprint(<String, dynamic>{}, 'cover'), isNull);
    });
  });

  group('モックで報告から直す', () {
    test('赤くなった：使うのをやめる。直す案は出さない', () async {
      final (cid, d) = await printed([pen()]);
      final r = await report(cid, d['design_id'], {'part': 'cover', 'result': 'red'});
      expect(fitAdviceKind(m(r['advice'])), FitAdviceKind.stop);
      expect(r['advice']['proposal'], isNull);
    });

    test('カバーがゆるい：フェルト → 替えても合わない → すき間を狭めた版。カバーだけ刷り直す', () async {
      final (cid, d) = await printed([pen()]);
      final did = d['design_id'] as String;
      var r = await report(cid, did, {'part': 'cover', 'result': 'loose', 'felt_changed': false});
      expect(fitAdviceKind(m(r['advice'])), FitAdviceKind.felt);
      r = await report(cid, did, {'part': 'cover', 'result': 'loose', 'felt_changed': true});
      expect(fitAdviceKind(m(r['advice'])), FitAdviceKind.refine);
      expect(r['advice']['proposal']['to'], 1.25);
      final n = m((await mock.handle('POST', '/v1/cases/$cid/designs/$did/refine',
          m(r['advice']['proposal']['request'])))['design']);
      expect(n['hand_clearance_mm'], 1.25);
      expect(n['refit_base_design_id'], did);
      expect(n['fit_report_id'], r['report_id']);
      expect(needsReprint(n, 'cover'), isTrue);
      expect(needsReprint(n, 'c_clip'), isFalse);
      // 直した版はまだ刷っていないので報告できない
      expect(
        () => report(cid, n['design_id'], {'part': 'cover', 'result': 'good'}),
        throwsA(isA<ApiError>().having((e) => e.code, 'code', 'CONFLICT')),
      );
    });

    test('2つ目のクリップの道具が抜ける：その取り付け具の太さの値を 0.25mm 小さく。そのクリップだけ刷り直す', () async {
      final (cid, d) = await printed([pen(), spoon()]);
      final did = d['design_id'] as String;
      final r = await report(cid, did, {'part': 'a2', 'result': 'tool_slips'});
      final req = m(r['advice']['proposal']['request']);
      expect(req['tool_d_mm'], 11.75);
      expect(req['attachment_id'], 'a2');
      final n = m((await mock.handle('POST', '/v1/cases/$cid/designs/$did/refine', req))['design']);
      expect(needsReprint(n, 'c_clip_a2'), isTrue);
      expect(needsReprint(n, 'cover'), isFalse);
      expect(needsReprint(n, 'c_clip'), isFalse);
    });

    test('ほかの版の報告では直せない。カバーに「道具が抜ける」は送れない', () async {
      final (cid, d) = await printed([pen()]);
      final did = d['design_id'] as String;
      expect(
        () => mock.handle('POST', '/v1/cases/$cid/designs/$did/refine', {'tool_d_mm': 9.0, 'fit_report_id': 'fr_x'}),
        throwsA(isA<ApiError>().having((e) => e.code, 'code', 'INVALID_ARGUMENT')),
      );
      expect(
        () => report(cid, did, {'part': 'cover', 'result': 'tool_slips'}),
        throwsA(isA<ApiError>().having((e) => e.code, 'code', 'INVALID_ARGUMENT')),
      );
    });
  });
}
