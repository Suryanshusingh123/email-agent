// Models that map to your FastAPI /history/stats and /history/ responses.
// fromJson() constructors parse the raw API JSON into typed Dart objects.

class DraftTelemetry {
  final int draftsGenerated;
  final int draftsSentAsIs;
  final int draftsEdited;
  // null when no feedback has been recorded yet
  final double? approvalRate;
  final Map<String, int> byPromptVersion;

  const DraftTelemetry({
    required this.draftsGenerated,
    required this.draftsSentAsIs,
    required this.draftsEdited,
    this.approvalRate,
    required this.byPromptVersion,
  });

  factory DraftTelemetry.fromJson(Map<String, dynamic> json) {
    return DraftTelemetry(
      draftsGenerated: json['drafts_generated'] as int? ?? 0,
      draftsSentAsIs: json['drafts_sent_as_is'] as int? ?? 0,
      draftsEdited: json['drafts_edited'] as int? ?? 0,
      approvalRate: (json['approval_rate'] as num?)?.toDouble(),
      byPromptVersion: Map<String, int>.from(json['by_prompt_version'] as Map? ?? {}),
    );
  }

  // Total drafts that have received feedback
  int get totalWithFeedback => draftsSentAsIs + draftsEdited;

  // "84%" string — null when no data
  String? get approvalRateLabel {
    if (approvalRate == null) return null;
    return '${(approvalRate! * 100).round()}%';
  }
}


class EmailStats {
  final int total;
  final Map<String, int> byPriority;
  final Map<String, int> byCategory;
  final int actionRequired;
  final DraftTelemetry? draftTelemetry;

  const EmailStats({
    required this.total,
    required this.byPriority,
    required this.byCategory,
    required this.actionRequired,
    this.draftTelemetry,
  });

  factory EmailStats.fromJson(Map<String, dynamic> json) {
    final telemetryJson = json['draft_telemetry'] as Map<String, dynamic>?;
    return EmailStats(
      total: json['total'] as int? ?? 0,
      byPriority: Map<String, int>.from(json['by_priority'] as Map? ?? {}),
      byCategory: Map<String, int>.from(json['by_category'] as Map? ?? {}),
      actionRequired: json['action_required'] as int? ?? 0,
      draftTelemetry: telemetryJson != null ? DraftTelemetry.fromJson(telemetryJson) : null,
    );
  }

  // Convenience getters for the dashboard cards
  int get highPriority => byPriority['high'] ?? 0;
  int get mediumPriority => byPriority['medium'] ?? 0;
  int get lowPriority => byPriority['low'] ?? 0;
}


class EmailRecord {
  final int id;
  final String gmailMessageId;
  final String subject;
  final String sender;
  final String? summary;
  final String category;
  final String priority;
  final bool actionRequired;
  final String? actionDescription;
  final List<String> keyPoints;
  final List<String> labelsApplied;
  final String? receivedAt;
  final String? processedAt;
  final bool draftGenerated;
  final String? gmailDraftId;
  // null = not sent yet, false = sent as-is, true = edited before sending
  final bool? draftEditedBeforeSend;

  const EmailRecord({
    required this.id,
    required this.gmailMessageId,
    required this.subject,
    required this.sender,
    this.summary,
    required this.category,
    required this.priority,
    required this.actionRequired,
    this.actionDescription,
    required this.keyPoints,
    required this.labelsApplied,
    this.receivedAt,
    this.processedAt,
    this.draftGenerated = false,
    this.gmailDraftId,
    this.draftEditedBeforeSend,
  });

  factory EmailRecord.fromJson(Map<String, dynamic> json) {
    return EmailRecord(
      id: json['id'] as int,
      gmailMessageId: json['gmail_message_id'] as String,
      subject: json['subject'] as String? ?? 'No Subject',
      sender: json['sender'] as String? ?? 'Unknown',
      summary: json['summary'] as String?,
      category: json['category'] as String? ?? 'other',
      priority: json['priority'] as String? ?? 'medium',
      actionRequired: json['action_required'] as bool? ?? false,
      actionDescription: json['action_description'] as String?,
      keyPoints: List<String>.from(json['key_points'] as List? ?? []),
      labelsApplied: List<String>.from(json['labels_applied'] as List? ?? []),
      receivedAt: json['received_at'] as String?,
      processedAt: json['processed_at'] as String?,
      draftGenerated: json['draft_generated'] as bool? ?? false,
      gmailDraftId: json['gmail_draft_id'] as String?,
      draftEditedBeforeSend: json['draft_edited_before_send'] as bool?,
    );
  }
}


class EmailHistoryResponse {
  final int total;
  final List<EmailRecord> emails;

  const EmailHistoryResponse({required this.total, required this.emails});

  factory EmailHistoryResponse.fromJson(Map<String, dynamic> json) {
    return EmailHistoryResponse(
      total: json['total'] as int? ?? 0,
      emails: (json['emails'] as List? ?? [])
          .map((e) => EmailRecord.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }
}
