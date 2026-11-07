import 'dart:convert';

import 'package:http/http.dart' as http;

/// 生成APIの呼び出し（docs/api.md）。プロトタイプでは認証の代わりに X-User を送る。
class Api {
  Api._();
  static final Api instance = Api._();

  static const base = String.fromEnvironment(
    'API_BASE',
    defaultValue: 'http://localhost:8080',
  );
  String user = 'demo-user';

  Map<String, String> get _headers => {
    'Content-Type': 'application/json; charset=utf-8',
    'X-User': user,
  };

  Future<dynamic> get(String path) async =>
      _handle(await http.get(Uri.parse('$base$path'), headers: _headers));

  Future<dynamic> post(String path, [Object? body]) async => _handle(
    await http.post(
      Uri.parse('$base$path'),
      headers: _headers,
      body: jsonEncode(body ?? {}),
    ),
  );

  Future<dynamic> put(String path, Object body) async => _handle(
    await http.put(
      Uri.parse('$base$path'),
      headers: _headers,
      body: jsonEncode(body),
    ),
  );

  String fileUrl(String rel) => '$base/files/$rel';

  dynamic _handle(http.Response r) {
    final body = r.body.isEmpty ? null : jsonDecode(utf8.decode(r.bodyBytes));
    if (r.statusCode >= 400) {
      final e = (body is Map && body['detail'] is Map)
          ? body['detail']['error']
          : null;
      throw ApiError(
        e?['message'] ?? 'エラーが起きました（${r.statusCode}）',
        retryable: e?['retryable'] == true,
      );
    }
    return body;
  }
}

class ApiError implements Exception {
  ApiError(this.message, {this.retryable = false});
  final String message;
  final bool retryable;
  @override
  String toString() => message;
}
