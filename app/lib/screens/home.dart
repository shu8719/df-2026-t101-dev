import 'package:flutter/material.dart';

import '../api.dart';
import '../ui.dart';
import 'design.dart';
import 'questions.dart';

/// S1 ホーム（ケースの一覧）
class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});
  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  late Future<List<dynamic>> _cases = _load();

  Future<List<dynamic>> _load() async =>
      (await Api.instance.get('/v1/cases')) as List<dynamic>;

  Future<void> _new() async {
    try {
      final r = await Api.instance.post('/v1/cases', {'title': '新しい道具'});
      if (!mounted) return;
      await Navigator.of(context).push(
        MaterialPageRoute(
          builder: (_) => QuestionsScreen(caseId: r['case_id']),
        ),
      );
      setState(() => _cases = _load());
    } catch (e) {
      if (mounted) showError(context, e);
    }
  }

  @override
  Widget build(BuildContext context) {
    return AppPage(
      title: '自助具ジェネレーター',
      bottom: FilledButton.icon(
        onPressed: _new,
        icon: const Icon(Icons.add),
        label: const Text('新しく作る'),
      ),
      children: [
        const InfoCard(
          icon: Icons.back_hand_outlined,
          child: Text(
            '指の形に合わせて、筆やペン、スプーンを持ちやすくする握りを作ります。'
            '手の動画は保存しません。角度を測るために、手の部分を数枚だけ送ります（保存しません）。',
          ),
        ),
        const SizedBox(height: 8),
        Text('これまでの道具', style: Theme.of(context).textTheme.titleMedium),
        FutureBuilder<List<dynamic>>(
          future: _cases,
          builder: (context, snap) {
            if (snap.connectionState != ConnectionState.done) {
              return const Padding(
                padding: EdgeInsets.all(24),
                child: Center(child: Text('読み込んでいます…')),
              );
            }
            if (snap.hasError) {
              return InfoCard(
                color: const Color(0xFFFDECEA),
                icon: Icons.cloud_off,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('読み込めませんでした。生成APIが動いているか確かめてください。\n${snap.error}'),
                    TextButton(
                      onPressed: () => setState(() => _cases = _load()),
                      child: const Text('再読み込み'),
                    ),
                  ],
                ),
              );
            }
            final cases = snap.data!;
            if (cases.isEmpty) {
              return const InfoCard(
                child: Text('まだ道具がありません。「新しく作る」から始めてください。'),
              );
            }
            return Column(
              children: [
                for (final c in cases)
                  Card(
                    elevation: 0,
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(16),
                      side: const BorderSide(color: AppColors.line),
                    ),
                    child: ListTile(
                      minVerticalPadding: 14,
                      title: Text(c['title'] ?? ''),
                      subtitle: Text(_statusJa(c['status'])),
                      trailing: const Icon(Icons.chevron_right),
                      onTap: () async {
                        if (c['current_design_id'] != null) {
                          await Navigator.of(context).push(
                            MaterialPageRoute(
                              builder: (_) => PreviewScreen(
                                caseId: c['case_id'],
                                designId: c['current_design_id'],
                              ),
                            ),
                          );
                        } else {
                          await Navigator.of(context).push(
                            MaterialPageRoute(
                              builder: (_) =>
                                  QuestionsScreen(caseId: c['case_id']),
                            ),
                          );
                        }
                        setState(() => _cases = _load());
                      },
                    ),
                  ),
              ],
            );
          },
        ),
      ],
    );
  }
}

String _statusJa(String? s) => switch (s) {
  'interviewing' => '質問に答えている途中',
  'measuring' => '撮影の前',
  'designing' => '形を作る前',
  'previewing' => '形ができました',
  'in_review' => 'OTの確認待ち',
  'approved' => '確認済み',
  _ => s ?? '',
};
