import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

/// Base URL for the WaveBook backend.
///
/// - Production: https://getwavebook.com (API lives at /api/*)
/// - Android emulator (local dev): http://10.0.2.2:8000
/// - iOS simulator / desktop (local dev): http://localhost:8000
/// - Physical device (local dev): your machine's LAN IP, e.g. http://192.168.1.10:8000
const String kApiBaseUrl = String.fromEnvironment(
  'API_BASE_URL',
  defaultValue: 'https://getwavebook.com',
);

class ApiException implements Exception {
  final int statusCode;
  final String message;

  ApiException(this.statusCode, this.message);

  @override
  String toString() => message;
}

class ApiClient {
  static const _tokenKey = 'wavebook_token';

  /// Called when the server rejects the stored token (expired session).
  /// AuthState uses this to return the user to the login screen.
  void Function()? onUnauthorized;

  Future<String?> getToken() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_tokenKey);
  }

  Future<void> saveToken(String token) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_tokenKey, token);
  }

  Future<void> clearToken() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_tokenKey);
  }

  Future<Map<String, String>> _headers({bool auth = true}) async {
    final headers = {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    };
    if (auth) {
      final token = await getToken();
      if (token != null) headers['Authorization'] = 'Bearer $token';
    }
    return headers;
  }

  Future<dynamic> get(String path, {bool auth = true}) async {
    final res = await http.get(
      Uri.parse('$kApiBaseUrl$path'),
      headers: await _headers(auth: auth),
    );
    return _handle(res);
  }

  /// Fetch a response as raw text (e.g. .ics calendar files).
  Future<String> getRaw(String path, {bool auth = true}) async {
    final res = await http.get(
      Uri.parse('$kApiBaseUrl$path'),
      headers: await _headers(auth: auth),
    );
    if (res.statusCode >= 200 && res.statusCode < 300) {
      return res.body;
    }
    throw ApiException(res.statusCode, 'Request failed (${res.statusCode})');
  }

  Future<dynamic> post(String path, {Object? body, bool auth = true}) async {
    final res = await http.post(
      Uri.parse('$kApiBaseUrl$path'),
      headers: await _headers(auth: auth),
      body: body == null ? null : jsonEncode(body),
    );
    return _handle(res);
  }

  Future<dynamic> patch(String path, {Object? body, bool auth = true}) async {
    final res = await http.patch(
      Uri.parse('$kApiBaseUrl$path'),
      headers: await _headers(auth: auth),
      body: body == null ? null : jsonEncode(body),
    );
    return _handle(res);
  }

  Future<dynamic> put(String path, {Object? body, bool auth = true}) async {
    final res = await http.put(
      Uri.parse('$kApiBaseUrl$path'),
      headers: await _headers(auth: auth),
      body: body == null ? null : jsonEncode(body),
    );
    return _handle(res);
  }

  Future<dynamic> delete(String path, {bool auth = true}) async {
    final res = await http.delete(
      Uri.parse('$kApiBaseUrl$path'),
      headers: await _headers(auth: auth),
    );
    return _handle(res);
  }

  /// Uploads a file as multipart form data. [onProgress] receives a value from 0 to 1
  /// as the request body is sent.
  Future<dynamic> upload(
    String path,
    String filePath,
    String fieldName, {
    void Function(double progress)? onProgress,
  }) async {
    final token = await getToken();
    final request = http.MultipartRequest('POST', Uri.parse('$kApiBaseUrl$path'));
    if (token != null) request.headers['Authorization'] = 'Bearer $token';
    request.files.add(await http.MultipartFile.fromPath(fieldName, filePath));
    final total = request.contentLength;
    final body = request.finalize();
    var sent = 0;
    final tracked = body.map((chunk) {
      sent += chunk.length;
      if (onProgress != null && total > 0) onProgress(sent / total);
      return chunk;
    });
    final streamedRequest = http.StreamedRequest('POST', request.url)
      ..headers.addAll(request.headers)
      ..contentLength = total;
    final client = http.Client();
    try {
      final responseFuture = client.send(streamedRequest);
      await streamedRequest.sink.addStream(tracked);
      await streamedRequest.sink.close();
      final res = await http.Response.fromStream(await responseFuture);
      return _handle(res);
    } finally {
      client.close();
    }
  }

  dynamic _handle(http.Response res) {
    dynamic data;
    try {
      data = res.body.isEmpty ? null : jsonDecode(res.body);
    } catch (_) {
      data = null;
    }
    if (res.statusCode >= 200 && res.statusCode < 300) {
      return data;
    }
    if (res.statusCode == 401) {
      unawaited(_expireSession());
    }
    final message = (data is Map && data['detail'] != null)
        ? data['detail'].toString()
        : 'Request failed (${res.statusCode})';
    throw ApiException(res.statusCode, message);
  }

  /// Called on a 401: if a token was stored, the session has expired, so clear
  /// it and let AuthState return the user to the login screen.
  Future<void> _expireSession() async {
    final token = await getToken();
    if (token == null) return;
    await clearToken();
    onUnauthorized?.call();
  }
}
