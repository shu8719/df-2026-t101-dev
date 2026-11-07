import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';

import 'screens/home.dart';
import 'ui.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  // Flutter Web は読み上げ用の情報が既定で無効なので、起動時に有効にする（docs/screens.md §2）
  SemanticsBinding.instance.ensureSemantics();
  runApp(const JijoguApp());
}

class JijoguApp extends StatelessWidget {
  const JijoguApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: '自助具ジェネレーター',
      debugShowCheckedModeBanner: false,
      theme: appTheme(),
      home: const HomeScreen(),
    );
  }
}
