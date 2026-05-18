import 'package:flutter/foundation.dart';
import '../models/email_stats.dart';
import '../services/api_service.dart';

// Possible states for any async data load
enum LoadState { idle, loading, loaded, error }

class DashboardProvider extends ChangeNotifier {
  final ApiService _api;

  DashboardProvider({ApiService? api}) : _api = api ?? ApiService();

  // --- Stats ---
  EmailStats? stats;
  LoadState statsState = LoadState.idle;
  String? statsError;

  // --- Email feed ---
  List<EmailRecord> emails = [];
  LoadState emailsState = LoadState.idle;
  String? emailsError;
  int emailsTotal = 0;

  // --- Active filters ---
  String? filterPriority;
  String? filterCategory;
  bool? filterActionRequired;

  // --- Poll trigger ---
  bool polling = false;
  String? pollMessage;

  Future<void> loadStats() async {
    statsState = LoadState.loading;
    statsError = null;
    notifyListeners();

    try {
      stats = await _api.fetchStats();
      statsState = LoadState.loaded;
    } catch (e) {
      statsError = e.toString();
      statsState = LoadState.error;
    }
    notifyListeners();
  }

  Future<void> loadEmails({int offset = 0}) async {
    emailsState = LoadState.loading;
    emailsError = null;
    notifyListeners();

    try {
      final result = await _api.fetchEmails(
        limit: 20,
        offset: offset,
        priority: filterPriority,
        category: filterCategory,
        actionRequired: filterActionRequired,
      );
      emails = result.emails;
      emailsTotal = result.total;
      emailsState = LoadState.loaded;
    } catch (e) {
      emailsError = e.toString();
      emailsState = LoadState.error;
    }
    notifyListeners();
  }

  Future<void> loadAll() async {
    await Future.wait([loadStats(), loadEmails()]);
  }

  void setFilter({String? priority, String? category, bool? actionRequired}) {
    filterPriority = priority;
    filterCategory = category;
    filterActionRequired = actionRequired;
    loadEmails();
  }

  void clearFilters() => setFilter();

  Future<void> triggerPoll() async {
    polling = true;
    pollMessage = null;
    notifyListeners();

    try {
      final result = await _api.triggerPollNow();
      pollMessage = 'Poll complete — ${result['total_processed']} emails processed';
      await loadAll(); // Refresh everything after a poll
    } catch (e) {
      pollMessage = 'Poll failed: $e';
    } finally {
      polling = false;
      notifyListeners();
    }
  }
}
