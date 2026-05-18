import 'dart:convert';
import 'package:http/http.dart' as http;
import '../models/email_stats.dart';

// Change this if running on a physical device — use your Mac's local IP
// e.g. http://192.168.1.10:8000
// Android emulator: http://10.0.2.2:8000
const String _baseUrl = 'http://127.0.0.1:8000';

class ApiException implements Exception {
  final String message;
  final int? statusCode;
  const ApiException(this.message, {this.statusCode});

  @override
  String toString() => 'ApiException($statusCode): $message';
}

class ApiService {
  final http.Client _client;

  ApiService({http.Client? client}) : _client = client ?? http.Client();

  Future<EmailStats> fetchStats() async {
    final response = await _client
        .get(Uri.parse('$_baseUrl/history/stats'))
        .timeout(const Duration(seconds: 10));

    _assertOk(response);
    return EmailStats.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  }

  Future<EmailHistoryResponse> fetchEmails({
    int limit = 20,
    int offset = 0,
    String? priority,
    String? category,
    bool? actionRequired,
  }) async {
    final params = <String, String>{
      'limit': '$limit',
      'offset': '$offset',
      if (priority != null) 'priority': priority,
      if (category != null) 'category': category,
      if (actionRequired != null) 'action_required': '$actionRequired',
    };

    final uri = Uri.parse('$_baseUrl/history/').replace(queryParameters: params);
    final response = await _client.get(uri).timeout(const Duration(seconds: 10));

    _assertOk(response);
    return EmailHistoryResponse.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<Map<String, dynamic>> generateDraft(
    String gmailMessageId, {
    String tone = 'professional',
  }) async {
    final uri = Uri.parse('$_baseUrl/emails/$gmailMessageId/draft')
        .replace(queryParameters: {'tone': tone});
    final response = await _client.post(uri).timeout(const Duration(seconds: 30));
    _assertOk(response);
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  Future<void> recordDraftFeedback(String gmailMessageId, {required bool edited}) async {
    final uri = Uri.parse('$_baseUrl/emails/$gmailMessageId/draft/feedback')
        .replace(queryParameters: {'edited': '$edited'});
    final response = await _client.post(uri).timeout(const Duration(seconds: 10));
    _assertOk(response);
  }

  Future<Map<String, dynamic>> triggerPollNow() async {
    final response = await _client
        .post(Uri.parse('$_baseUrl/polling/run-now?max_results=10'))
        .timeout(const Duration(seconds: 60));

    _assertOk(response);
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  void _assertOk(http.Response response) {
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw ApiException(
        'Request failed: ${response.body}',
        statusCode: response.statusCode,
      );
    }
  }
}
