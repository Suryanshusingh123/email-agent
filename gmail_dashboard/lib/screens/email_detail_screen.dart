import 'package:flutter/material.dart';
import '../models/email_stats.dart';
import '../services/api_service.dart';
import '../services/tone_preference_service.dart';
import '../widgets/priority_badge.dart';

class EmailDetailScreen extends StatefulWidget {
  final EmailRecord email;

  const EmailDetailScreen({super.key, required this.email});

  @override
  State<EmailDetailScreen> createState() => _EmailDetailScreenState();
}

class _EmailDetailScreenState extends State<EmailDetailScreen> {
  bool _generatingDraft = false;
  bool _draftCreated = false;
  String _selectedTone = 'professional';
  // null = no feedback yet, false = sent as-is, true = edited
  bool? _feedbackRecorded;
  bool _recordingFeedback = false;

  EmailRecord get email => widget.email;

  @override
  void initState() {
    super.initState();
    _draftCreated = email.draftGenerated;
    _feedbackRecorded = email.draftEditedBeforeSend;
    _loadTonePreference();
  }

  Future<void> _loadTonePreference() async {
    final tone = await TonePreferenceService().load(email.sender);
    if (mounted) setState(() => _selectedTone = tone);
  }

  Future<void> _generateDraft() async {
    setState(() => _generatingDraft = true);
    try {
      await ApiService().generateDraft(email.gmailMessageId, tone: _selectedTone);
      await TonePreferenceService().save(email.sender, _selectedTone);
      setState(() => _draftCreated = true);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Draft saved to Gmail! Open Gmail Drafts to review.'),
            backgroundColor: Color(0xFF43A047),
            duration: Duration(seconds: 4),
          ),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Failed: $e'), backgroundColor: Colors.red),
        );
      }
    } finally {
      if (mounted) setState(() => _generatingDraft = false);
    }
  }

  Future<void> _showFeedbackDialog() async {
    final result = await showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => AlertDialog(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        title: const Text(
          'How was the draft?',
          style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
        ),
        content: const Text(
          'Did you send the draft as-is, or did you edit it before sending?\n\n'
          'This helps improve future drafts.',
          style: TextStyle(fontSize: 14, height: 1.5),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Sent as-is'),
          ),
          ElevatedButton(
            onPressed: () => Navigator.pop(ctx, true),
            style: ElevatedButton.styleFrom(
              backgroundColor: const Color(0xFF6750A4),
              foregroundColor: Colors.white,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
            ),
            child: const Text('I edited it'),
          ),
        ],
      ),
    );

    if (result == null || !mounted) return;

    setState(() => _recordingFeedback = true);
    try {
      await ApiService().recordDraftFeedback(email.gmailMessageId, edited: result);
      if (mounted) {
        setState(() => _feedbackRecorded = result);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(result
                ? 'Feedback recorded: you edited the draft.'
                : 'Feedback recorded: sent as-is. Great prompt performance!'),
            backgroundColor: const Color(0xFF6750A4),
            duration: const Duration(seconds: 3),
          ),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Could not record feedback: $e'), backgroundColor: Colors.red),
        );
      }
    } finally {
      if (mounted) setState(() => _recordingFeedback = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF8F9FA),
      appBar: AppBar(
        backgroundColor: Colors.white,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back, color: Color(0xFF1A1A2E)),
          onPressed: () => Navigator.pop(context),
        ),
        title: const Text(
          'Email Detail',
          style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: Color(0xFF1A1A2E)),
        ),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Header card
            _Card(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Wrap(
                    spacing: 8,
                    runSpacing: 6,
                    children: [
                      PriorityBadge(email.priority),
                      CategoryChip(email.category),
                      if (email.actionRequired)
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                          decoration: BoxDecoration(
                            color: Colors.blue.shade50,
                            borderRadius: BorderRadius.circular(6),
                            border: Border.all(color: Colors.blue.shade200),
                          ),
                          child: Text(
                            'ACTION NEEDED',
                            style: TextStyle(color: Colors.blue.shade700, fontSize: 10, fontWeight: FontWeight.bold),
                          ),
                        ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  Text(
                    email.subject,
                    style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: Color(0xFF1A1A2E)),
                  ),
                  const SizedBox(height: 8),
                  _MetaRow(icon: Icons.person_outline, text: email.sender),
                  if (email.receivedAt != null)
                    _MetaRow(icon: Icons.schedule, text: email.receivedAt!),
                ],
              ),
            ),

            const SizedBox(height: 12),

            // AI Summary
            if (email.summary != null)
              _Section(
                icon: Icons.auto_awesome,
                iconColor: const Color(0xFF6750A4),
                title: 'AI Summary',
                child: Text(
                  email.summary!,
                  style: const TextStyle(fontSize: 14, height: 1.6, color: Color(0xFF444444)),
                ),
              ),

            // Action required
            if (email.actionRequired && email.actionDescription != null) ...[
              const SizedBox(height: 12),
              _Section(
                icon: Icons.task_alt,
                iconColor: const Color(0xFF1565C0),
                title: 'Action Required',
                child: Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: Colors.blue.shade50,
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Text(
                    email.actionDescription!,
                    style: TextStyle(fontSize: 14, height: 1.5, color: Colors.blue.shade800),
                  ),
                ),
              ),
            ],

            // Key points
            if (email.keyPoints.isNotEmpty) ...[
              const SizedBox(height: 12),
              _Section(
                icon: Icons.format_list_bulleted,
                iconColor: const Color(0xFF43A047),
                title: 'Key Points',
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: email.keyPoints.map((point) => Padding(
                    padding: const EdgeInsets.only(bottom: 8),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text('• ', style: TextStyle(fontSize: 16, color: Color(0xFF43A047))),
                        Expanded(
                          child: Text(point, style: const TextStyle(fontSize: 14, height: 1.5, color: Color(0xFF444444))),
                        ),
                      ],
                    ),
                  )).toList(),
                ),
              ),
            ],

            // Labels applied
            if (email.labelsApplied.isNotEmpty) ...[
              const SizedBox(height: 12),
              _Section(
                icon: Icons.label_outline,
                iconColor: const Color(0xFFFB8C00),
                title: 'Gmail Labels Applied',
                child: Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: email.labelsApplied.map((label) => Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                    decoration: BoxDecoration(
                      color: const Color(0xFFFFF3E0),
                      borderRadius: BorderRadius.circular(20),
                      border: Border.all(color: const Color(0xFFFFCC02)),
                    ),
                    child: Text(
                      label,
                      style: const TextStyle(fontSize: 12, color: Color(0xFFE65100), fontWeight: FontWeight.w500),
                    ),
                  )).toList(),
                ),
              ),
            ],

            // Draft button — available for any email
            ...[
              const SizedBox(height: 12),
              if (_draftCreated) ...[
                // Success card
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    color: const Color(0xFFE8F5E9),
                    borderRadius: BorderRadius.circular(16),
                    border: Border.all(color: const Color(0xFF43A047)),
                  ),
                  child: Column(
                    children: [
                      const Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Icon(Icons.check_circle, color: Color(0xFF43A047), size: 20),
                          SizedBox(width: 8),
                          Text(
                            'Draft saved to Gmail',
                            style: TextStyle(
                              color: Color(0xFF2E7D32),
                              fontWeight: FontWeight.bold,
                              fontSize: 14,
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 4),
                      Text(
                        'Open Gmail Drafts to review and send.',
                        style: TextStyle(color: Colors.green.shade700, fontSize: 12),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 10),
                // Feedback section
                if (_feedbackRecorded != null)
                  _FeedbackConfirmation(edited: _feedbackRecorded!)
                else
                  SizedBox(
                    width: double.infinity,
                    child: OutlinedButton.icon(
                      onPressed: _recordingFeedback ? null : _showFeedbackDialog,
                      icon: _recordingFeedback
                          ? const SizedBox(
                              width: 14,
                              height: 14,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Icon(Icons.rate_review_outlined, size: 16),
                      label: const Text('Rate this draft'),
                      style: OutlinedButton.styleFrom(
                        foregroundColor: const Color(0xFF6750A4),
                        side: const BorderSide(color: Color(0xFF6750A4)),
                        padding: const EdgeInsets.symmetric(vertical: 12),
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                      ),
                    ),
                  ),
              ] else ...[
                _ToneSelector(
                  selected: _selectedTone,
                  onChanged: (t) => setState(() => _selectedTone = t),
                ),
                const SizedBox(height: 10),
                SizedBox(
                  width: double.infinity,
                  child: ElevatedButton.icon(
                    onPressed: _generatingDraft ? null : _generateDraft,
                    icon: _generatingDraft
                        ? const SizedBox(
                            width: 16,
                            height: 16,
                            child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                          )
                        : const Icon(Icons.auto_awesome, size: 18),
                    label: Text(_generatingDraft ? 'Generating Draft...' : 'Generate Reply Draft'),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFF6750A4),
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(vertical: 14),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                    ),
                  ),
                ),
              ],
            ],

            const SizedBox(height: 32),
          ],
        ),
      ),
    );
  }
}

class _Card extends StatelessWidget {
  final Widget child;
  const _Card({required this.child});

  @override
  Widget build(BuildContext context) => Container(
    width: double.infinity,
    padding: const EdgeInsets.all(16),
    decoration: BoxDecoration(
      color: Colors.white,
      borderRadius: BorderRadius.circular(16),
      border: Border.all(color: Colors.grey.shade200),
    ),
    child: child,
  );
}

class _Section extends StatelessWidget {
  final IconData icon;
  final Color iconColor;
  final String title;
  final Widget child;

  const _Section({required this.icon, required this.iconColor, required this.title, required this.child});

  @override
  Widget build(BuildContext context) => Container(
    width: double.infinity,
    padding: const EdgeInsets.all(16),
    decoration: BoxDecoration(
      color: Colors.white,
      borderRadius: BorderRadius.circular(16),
      border: Border.all(color: Colors.grey.shade200),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(children: [
          Icon(icon, size: 16, color: iconColor),
          const SizedBox(width: 6),
          Text(title, style: TextStyle(fontSize: 13, fontWeight: FontWeight.bold, color: iconColor)),
        ]),
        const SizedBox(height: 12),
        child,
      ],
    ),
  );
}

class _ToneSelector extends StatelessWidget {
  static const _tones = [
    ('professional', Icons.business_center_outlined),
    ('friendly',     Icons.emoji_emotions_outlined),
    ('concise',      Icons.compress),
    ('detailed',     Icons.format_align_left_outlined),
  ];

  final String selected;
  final ValueChanged<String> onChanged;

  const _ToneSelector({required this.selected, required this.onChanged});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'REPLY TONE',
          style: TextStyle(fontSize: 10, fontWeight: FontWeight.bold, color: Colors.grey[500], letterSpacing: 0.8),
        ),
        const SizedBox(height: 8),
        Row(
          children: _tones.map((t) {
            final (tone, icon) = t;
            final isSelected = selected == tone;
            return Expanded(
              child: Padding(
                padding: const EdgeInsets.only(right: 6),
                child: GestureDetector(
                  onTap: () => onChanged(tone),
                  child: AnimatedContainer(
                    duration: const Duration(milliseconds: 150),
                    padding: const EdgeInsets.symmetric(vertical: 8),
                    decoration: BoxDecoration(
                      color: isSelected
                          ? const Color(0xFF6750A4)
                          : Colors.grey.shade100,
                      borderRadius: BorderRadius.circular(10),
                      border: Border.all(
                        color: isSelected ? const Color(0xFF6750A4) : Colors.grey.shade300,
                      ),
                    ),
                    child: Column(
                      children: [
                        Icon(icon, size: 16, color: isSelected ? Colors.white : Colors.grey[600]),
                        const SizedBox(height: 4),
                        Text(
                          tone,
                          style: TextStyle(
                            fontSize: 10,
                            fontWeight: FontWeight.w600,
                            color: isSelected ? Colors.white : Colors.grey[600],
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            );
          }).toList(),
        ),
      ],
    );
  }
}


class _FeedbackConfirmation extends StatelessWidget {
  final bool edited;
  const _FeedbackConfirmation({required this.edited});

  @override
  Widget build(BuildContext context) {
    final label = edited ? 'You edited this draft' : 'Sent as-is — great prompt match!';
    final icon = edited ? Icons.edit_note : Icons.thumb_up_outlined;
    final color = edited ? Colors.orange.shade700 : const Color(0xFF6750A4);
    final bg = edited ? Colors.orange.shade50 : Colors.purple.shade50;

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withValues(alpha: 0.3)),
      ),
      child: Row(
        children: [
          Icon(icon, size: 16, color: color),
          const SizedBox(width: 8),
          Text(
            label,
            style: TextStyle(fontSize: 12, color: color, fontWeight: FontWeight.w500),
          ),
        ],
      ),
    );
  }
}

class _MetaRow extends StatelessWidget {
  final IconData icon;
  final String text;
  const _MetaRow({required this.icon, required this.text});

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(top: 6),
    child: Row(children: [
      Icon(icon, size: 14, color: Colors.grey[500]),
      const SizedBox(width: 6),
      Expanded(
        child: Text(text,
          style: TextStyle(fontSize: 12, color: Colors.grey[600]),
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
        ),
      ),
    ]),
  );
}
