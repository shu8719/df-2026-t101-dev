import 'package:flutter/material.dart';

import '../api.dart';
import '../ui.dart';
import 'capture.dart';

/// S2a 選択式の質問（docs/screens.md S2）
class Question {
  const Question(this.field, this.text, this.options, {this.hint});
  final String field;
  final String text;
  final List<(String value, String label, String? sub)> options;
  final String? hint;
}

const questions = <Question>[
  Question('activity', '何をしたいですか', [
    ('draw', '絵を描く', '筆'),
    ('write', '字を書く', 'ペン'),
    ('eat', '食べる', 'スプーン'),
    ('other', 'その他', '次の画面で教えてください'),
  ]),
  Question('hand_side', 'どちらの手で持ちますか', [
    ('right', '右手', null),
    ('left', '左手', null),
  ]),
  Question('tool_shaft_size', '道具の柄の太さは', [
    ('thin', '細い', '7mmまで'),
    ('medium', 'ふつう', '7〜10mm'),
    ('thick', '太い', '10〜13mm'),
    ('unknown', 'わからない', 'よくある太さで作ります'),
  ], hint: '1円玉の直径は20mmです。並べて比べると分かりやすいです。'),
  Question('tool_shaft_shape', '柄の形は', [
    ('round', '丸い', null),
    ('flat', '平たい', null),
  ]),
  Question('nut_operator', 'ねじ（ナット）を回すのは', [
    ('self', '自分で回せる', null),
    ('self_weak', '指先でつまむのは難しい', '手のひらで回せる羽根付きにします'),
    ('helper', '家族や支援者が回す', null),
  ]),
  Question('grip_strength', '握る力は', [
    ('firm', 'しっかり握れる', null),
    ('light', '軽くなら握れる', null),
    ('weak', 'ほとんど握れない', null),
  ]),
  Question('capture_by', '撮影するのは', [
    ('self', '自分（片手）', null),
    ('helper', '家族や支援者', 'おすすめです'),
  ]),
];

const toolForActivity = {
  'draw': 'brush',
  'write': 'pen',
  'eat': 'spoon',
  'other': 'other',
};

class QuestionsScreen extends StatefulWidget {
  const QuestionsScreen({super.key, required this.caseId});
  final String caseId;
  @override
  State<QuestionsScreen> createState() => _QuestionsScreenState();
}

class _QuestionsScreenState extends State<QuestionsScreen> {
  int _i = 0;
  final Map<String, String> _answers = {};
  bool _saving = false;

  Future<void> _pick(String value) async {
    final q = questions[_i];
    setState(() => _answers[q.field] = value);
    await Future<void>.delayed(const Duration(milliseconds: 180));
    if (_i < questions.length - 1) {
      setState(() => _i++);
      return;
    }
    setState(() => _saving = true);
    try {
      final body = {
        ..._answers,
        'tool_type': toolForActivity[_answers['activity']],
      };
      final r = await Api.instance.put(
        '/v1/cases/${widget.caseId}/requirements',
        body,
      );
      if (!mounted) return;
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(
          builder: (_) => ChatScreen(
            caseId: widget.caseId,
            requirements: Map<String, dynamic>.from(r['requirements']),
          ),
        ),
      );
    } catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final q = questions[_i];
    return AppPage(
      title: '${_i + 1} / ${questions.length}',
      onBack: _i == 0
          ? () => Navigator.of(context).pop()
          : () => setState(() => _i--),
      children: [
        LinearProgressIndicator(
          value: (_i + 1) / questions.length,
          minHeight: 6,
          borderRadius: BorderRadius.circular(3),
        ),
        const SizedBox(height: 20),
        Text(
          q.text,
          style: Theme.of(context).textTheme.headlineSmall
              ?.copyWith(fontWeight: FontWeight.w700),
        ),
        if (q.hint != null)
          Padding(
            padding: const EdgeInsets.only(top: 6),
            child: Text(q.hint!, style: const TextStyle(color: AppColors.sub)),
          ),
        const SizedBox(height: 12),
        for (final o in q.options)
          ChoiceButton(
            label: o.$2,
            sub: o.$3,
            selected: _answers[q.field] == o.$1,
            onTap: _saving ? () {} : () => _pick(o.$1),
          ),
        if (_saving)
          const Padding(
            padding: EdgeInsets.all(16),
            child: Center(child: Text('保存しています…')),
          ),
      ],
    );
  }
}

/// S2b ほかに伝えたいこと（任意のチャット）
class ChatScreen extends StatefulWidget {
  const ChatScreen({
    super.key,
    required this.caseId,
    required this.requirements,
  });
  final String caseId;
  final Map<String, dynamic> requirements;
  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final _ctrl = TextEditingController();
  final List<(bool me, String text)> _msgs = [
    (false, 'ほかに伝えたいことはありますか？（なければ「とばす」）'),
  ];
  bool _sending = false;
  late final bool _required = widget.requirements['activity'] == 'other';

  Future<void> _send([String? preset]) async {
    final text = (preset ?? _ctrl.text).trim();
    if (text.isEmpty) return;
    setState(() {
      _msgs.add((true, text));
      _sending = true;
      _ctrl.clear();
    });
    try {
      final r = await Api.instance.post(
        '/v1/cases/${widget.caseId}/interview',
        {'message': text},
      );
      final turn = r['turn'];
      if (turn['status'] == 'out_of_scope' && mounted) {
        await showDialog<void>(
          context: context,
          builder: (_) => AlertDialog(
            title: const Text('このアプリでは作れません'),
            content: Text(turn['message_ja']),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(context),
                child: const Text('閉じる'),
              ),
            ],
          ),
        );
      }
      setState(() => _msgs.add((false, turn['message_ja'])));
    } catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  void _next() => Navigator.of(context).pushReplacement(
    MaterialPageRoute(
      builder: (_) => SummaryScreen(
        caseId: widget.caseId,
        requirements: widget.requirements,
      ),
    ),
  );

  @override
  Widget build(BuildContext context) {
    return AppPage(
      title: 'ほかに伝えたいこと',
      bottom: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _ctrl,
                  maxLength: 500,
                  decoration: const InputDecoration(
                    hintText: '例：人差し指の付け根が痛い',
                    border: OutlineInputBorder(),
                    counterText: '',
                  ),
                  onSubmitted: (_) => _send(),
                ),
              ),
              const SizedBox(width: 8),
              IconButton.filled(
                onPressed: _sending ? null : _send,
                icon: const Icon(Icons.send),
                iconSize: 28,
              ),
            ],
          ),
          const SizedBox(height: 8),
          OutlinedButton(
            onPressed: _required && _msgs.length < 3 ? null : _next,
            child: Text(_required ? '次へ' : 'とばす・次へ'),
          ),
        ],
      ),
      children: [
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            for (final s in ['痛い所がある', '長い時間使いたい', '目立たない見た目がいい'])
              SuggestButton(
                label: s,
                onPressed: _sending ? null : () => _send(s),
              ),
          ],
        ),
        const SizedBox(height: 12),
        for (final m in _msgs)
          Align(
            alignment: m.$1 ? Alignment.centerRight : Alignment.centerLeft,
            child: Container(
              margin: const EdgeInsets.symmetric(vertical: 4),
              padding: const EdgeInsets.all(12),
              constraints: const BoxConstraints(maxWidth: 520),
              decoration: BoxDecoration(
                color: m.$1 ? const Color(0xFFE3EEF3) : AppColors.card,
                borderRadius: BorderRadius.circular(14),
                border: Border.all(color: AppColors.line),
              ),
              child: Text(m.$2),
            ),
          ),
        if (_sending)
          const Padding(
            padding: EdgeInsets.all(8),
            child: Text('考えています…', style: TextStyle(color: AppColors.sub)),
          ),
      ],
    );
  }
}

/// S2c まとめ
class SummaryScreen extends StatelessWidget {
  const SummaryScreen({
    super.key,
    required this.caseId,
    required this.requirements,
  });
  final String caseId;
  final Map<String, dynamic> requirements;

  String _label(String field) {
    final q = questions.firstWhere((q) => q.field == field);
    final v = requirements[field];
    final o = q.options.where((o) => o.$1 == v);
    return o.isEmpty
        ? '$v'
        : o.first.$2 +
              (o.first.$3 != null && field == 'tool_shaft_size'
                  ? '（${o.first.$3}）'
                  : '');
  }

  @override
  Widget build(BuildContext context) {
    return AppPage(
      title: 'まとめ',
      bottom: FilledButton(
        onPressed: () => Navigator.of(context).pushReplacement(
          MaterialPageRoute(builder: (_) => CaptureScreen(caseId: caseId)),
        ),
        child: const Text('この内容で撮影に進む'),
      ),
      children: [
        for (final q in questions)
          InfoCard(
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    q.text,
                    style: const TextStyle(color: AppColors.sub),
                  ),
                ),
                Text(
                  _label(q.field),
                  style: const TextStyle(fontWeight: FontWeight.w600),
                ),
              ],
            ),
          ),
      ],
    );
  }
}
