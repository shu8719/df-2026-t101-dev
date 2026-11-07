import 'dart:async';
import 'dart:convert';
import 'dart:js_interop';

import 'package:flutter/material.dart';
import 'package:web/web.dart' as web;

/// web/js/viewer.js が用意する window.jijoguViewer
extension type _Viewer._(JSObject _) implements JSObject {
  external void showStl(
    web.HTMLElement el,
    String url,
    String color,
    String capsulesJson,
    String hand,
  );
  external void setColor(web.HTMLElement el, String color);
  external void showHand(web.HTMLElement el, String handModelJson);
}

@JS('jijoguViewer')
external _Viewer? get _viewer;

Future<_Viewer> _waitViewer() async {
  for (var i = 0; i < 100; i++) {
    final v = _viewer;
    if (v != null) return v;
    await Future<void>.delayed(const Duration(milliseconds: 100));
  }
  throw StateError('3D表示の準備ができませんでした');
}

/// three.js の3D表示を埋め込む。STL（握り）か、手のカプセルモデルのどちらかを出す。
class Viewer3D extends StatefulWidget {
  const Viewer3D.stl({
    super.key,
    required String this.stlUrl,
    required this.color,
    this.capsules,
    this.hand = 'right',
  }) : handModel = null;
  const Viewer3D.hand({super.key, required Map<String, dynamic> this.handModel})
    : stlUrl = null,
      color = '#F2C09E',
      capsules = null,
      hand = 'right';

  final String? stlUrl;
  final String color;
  final List<dynamic>? capsules;
  final String hand;
  final Map<String, dynamic>? handModel;

  @override
  State<Viewer3D> createState() => _Viewer3DState();
}

class _Viewer3DState extends State<Viewer3D> {
  web.HTMLElement? _el;

  Future<void> _render({bool colorOnly = false}) async {
    final el = _el;
    if (el == null) return;
    final v = await _waitViewer();
    if (colorOnly) {
      v.setColor(el, widget.color);
    } else if (widget.handModel != null) {
      v.showHand(el, jsonEncode(widget.handModel));
    } else {
      v.showStl(
        el,
        widget.stlUrl!,
        widget.color,
        jsonEncode(widget.capsules ?? []),
        widget.hand,
      );
    }
  }

  @override
  void didUpdateWidget(Viewer3D old) {
    super.didUpdateWidget(old);
    if (old.stlUrl != widget.stlUrl || old.handModel != widget.handModel) {
      _render();
    } else if (old.color != widget.color) {
      _render(colorOnly: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: '3Dの表示。指でドラッグすると回せます',
      child: ClipRRect(
        borderRadius: BorderRadius.circular(16),
        child: ColoredBox(
          color: const Color(0xFFF4F1EA),
          child: HtmlElementView.fromTagName(
            tagName: 'div',
            onElementCreated: (Object el) {
              final div = el as web.HTMLDivElement;
              div.style.width = '100%';
              div.style.height = '100%';
              _el = div;
              unawaited(_render());
            },
          ),
        ),
      ),
    );
  }
}
