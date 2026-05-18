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
  bool? _feedbackRecorded;
  bool _recordingFeedback = false;
  final _instructionsController = TextEditingController();

  EmailRecord get email => widget.email;

  @override
  void initState() {
    super.initState();
    _draftCreated = email.draftGenerated;
    _feedbackRecorded = email.draftEditedBeforeSend;
    _loadTonePreference();
  }

  @override
  void dispose() {
    _instructionsController.dispose();
    super.dispose();
  }

  Future<void> _loadTonePreference() async {
    final tone = await TonePreferenceService().load(email.sender);
    if (mounted) setState(() => _selectedTone = tone);
  }

  Future<void> _generateDraft() async {
    setState(() => _generatingDraft = true);
    try {
      await ApiService().generateDraft(
        email.gmailMessageId,
        tone: _selectedTone,
        instructions: _instructionsController.text,
      );
      await TonePreferenceService().save(email.sender, _selectedTone);
      setState(() => _draftCreated = true);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: const Text('Draft saved to Gmail! Open Gmail Drafts to review.'),
            backgroundColor: const Color(0xFF43A047),
            duration: const Duration(seconds: 4),
            behavior: SnackBarBehavior.floating,
            shape:
                RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          ),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Failed: $e'),
            backgroundColor: Colors.red,
            behavior: SnackBarBehavior.floating,
            shape:
                RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          ),
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
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
        title: const Text(
          'How was the draft?',
          style: TextStyle(fontSize: 17, fontWeight: FontWeight.bold),
        ),
        content: const Text(
          'Did you send the draft as-is, or did you edit it before sending?\n\n'
          'This helps improve future drafts.',
          style: TextStyle(fontSize: 14, height: 1.6, color: Color(0xFF555555)),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Sent as-is',
                style: TextStyle(color: Color(0xFF6750A4))),
          ),
          ElevatedButton(
            onPressed: () => Navigator.pop(ctx, true),
            style: ElevatedButton.styleFrom(
              backgroundColor: const Color(0xFF6750A4),
              foregroundColor: Colors.white,
              shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(10)),
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
            behavior: SnackBarBehavior.floating,
            shape:
                RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          ),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Could not record feedback: $e'),
            backgroundColor: Colors.red,
            behavior: SnackBarBehavior.floating,
          ),
        );
      }
    } finally {
      if (mounted) setState(() => _recordingFeedback = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF0EFF8),
      appBar: AppBar(
        elevation: 0,
        backgroundColor: Colors.transparent,
        flexibleSpace: Container(
          decoration: const BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: [Color(0xFF4527A0), Color(0xFF7E57C2)],
            ),
          ),
        ),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new, color: Colors.white, size: 18),
          onPressed: () => Navigator.pop(context),
        ),
        title: const Text(
          'Email Detail',
          style: TextStyle(
            fontSize: 17,
            fontWeight: FontWeight.bold,
            color: Colors.white,
          ),
        ),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Header card
            _DetailCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Wrap(
                    spacing: 8,
                    runSpacing: 6,
                    crossAxisAlignment: WrapCrossAlignment.center,
                    children: [
                      PriorityBadge(email.priority),
                      CategoryChip(email.category),
                      if (email.actionRequired)
                        Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 10, vertical: 4),
                          decoration: BoxDecoration(
                            color: const Color(0xFF1565C0),
                            borderRadius: BorderRadius.circular(20),
                          ),
                          child: const Text(
                            'ACTION NEEDED',
                            style: TextStyle(
                              color: Colors.white,
                              fontSize: 10,
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                        ),
                    ],
                  ),
                  const SizedBox(height: 14),
                  Text(
                    email.subject,
                    style: const TextStyle(
                      fontSize: 19,
                      fontWeight: FontWeight.bold,
                      color: Color(0xFF1A1A2E),
                      height: 1.3,
                    ),
                  ),
                  const SizedBox(height: 10),
                  Container(
                    height: 1,
                    color: const Color(0xFFEEEEEE),
                  ),
                  const SizedBox(height: 10),
                  _MetaRow(icon: Icons.person_outline, text: email.sender),
                  if (email.receivedAt != null)
                    _MetaRow(
                        icon: Icons.schedule_outlined,
                        text: email.receivedAt!),
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
                  style: const TextStyle(
                    fontSize: 14,
                    height: 1.7,
                    color: Color(0xFF444444),
                  ),
                ),
              ),

            // Action required
            if (email.actionRequired && email.actionDescription != null) ...[
              const SizedBox(height: 12),
              _Section(
                icon: Icons.task_alt_rounded,
                iconColor: const Color(0xFF1565C0),
                title: 'Action Required',
                child: Container(
                  padding: const EdgeInsets.all(14),
                  decoration: BoxDecoration(
                    color: const Color(0xFFE3F2FD),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: const Color(0xFF90CAF9)),
                  ),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Icon(Icons.arrow_forward_ios,
                          size: 13, color: Color(0xFF1565C0)),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          email.actionDescription!,
                          style: const TextStyle(
                            fontSize: 14,
                            height: 1.5,
                            color: Color(0xFF0D47A1),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],

            // Key points
            if (email.keyPoints.isNotEmpty) ...[
              const SizedBox(height: 12),
              _Section(
                icon: Icons.format_list_bulleted_rounded,
                iconColor: const Color(0xFF43A047),
                title: 'Key Points',
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: email.keyPoints.map((point) => Padding(
                    padding: const EdgeInsets.only(bottom: 10),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Container(
                          margin: const EdgeInsets.only(top: 6),
                          width: 6,
                          height: 6,
                          decoration: const BoxDecoration(
                            color: Color(0xFF43A047),
                            shape: BoxShape.circle,
                          ),
                        ),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Text(
                            point,
                            style: const TextStyle(
                              fontSize: 14,
                              height: 1.5,
                              color: Color(0xFF444444),
                            ),
                          ),
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
                    padding: const EdgeInsets.symmetric(
                        horizontal: 12, vertical: 6),
                    decoration: BoxDecoration(
                      gradient: const LinearGradient(
                        colors: [Color(0xFFFFF8E1), Color(0xFFFFF3CD)],
                      ),
                      borderRadius: BorderRadius.circular(20),
                      border: Border.all(color: const Color(0xFFFFCC02)),
                    ),
                    child: Text(
                      label,
                      style: const TextStyle(
                        fontSize: 12,
                        color: Color(0xFFE65100),
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  )).toList(),
                ),
              ),
            ],

            // Draft section
            ...[
              const SizedBox(height: 12),
              if (_draftCreated) ...[
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(18),
                  decoration: BoxDecoration(
                    gradient: const LinearGradient(
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                      colors: [Color(0xFFE8F5E9), Color(0xFFF1F8E9)],
                    ),
                    borderRadius: BorderRadius.circular(18),
                    border: Border.all(color: const Color(0xFF81C784)),
                    boxShadow: [
                      BoxShadow(
                        color: const Color(0xFF43A047).withValues(alpha: 0.15),
                        blurRadius: 12,
                        offset: const Offset(0, 4),
                      ),
                    ],
                  ),
                  child: Column(
                    children: [
                      const Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Icon(Icons.check_circle_rounded,
                              color: Color(0xFF43A047), size: 22),
                          SizedBox(width: 8),
                          Text(
                            'Draft saved to Gmail',
                            style: TextStyle(
                              color: Color(0xFF2E7D32),
                              fontWeight: FontWeight.bold,
                              fontSize: 15,
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 6),
                      Text(
                        'Open Gmail Drafts to review and send.',
                        style: TextStyle(
                            color: Colors.green.shade600, fontSize: 12),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 10),
                if (_feedbackRecorded != null)
                  _FeedbackConfirmation(edited: _feedbackRecorded!)
                else
                  SizedBox(
                    width: double.infinity,
                    child: OutlinedButton.icon(
                      onPressed:
                          _recordingFeedback ? null : _showFeedbackDialog,
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
                        padding: const EdgeInsets.symmetric(vertical: 13),
                        shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(14)),
                      ),
                    ),
                  ),
              ] else ...[
                _ToneSelector(
                  selected: _selectedTone,
                  onChanged: (t) => setState(() => _selectedTone = t),
                ),
                const SizedBox(height: 12),
                // Optional instructions field
                Container(
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(20),
                    boxShadow: [
                      BoxShadow(
                        color: Colors.black.withValues(alpha: 0.05),
                        blurRadius: 12,
                        offset: const Offset(0, 4),
                      ),
                    ],
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Container(
                            padding: const EdgeInsets.all(6),
                            decoration: BoxDecoration(
                              color: const Color(0xFF6750A4).withValues(alpha: 0.1),
                              borderRadius: BorderRadius.circular(8),
                            ),
                            child: const Icon(Icons.edit_note,
                                size: 14, color: Color(0xFF6750A4)),
                          ),
                          const SizedBox(width: 8),
                          const Text(
                            'What to include  ',
                            style: TextStyle(
                              fontSize: 14,
                              fontWeight: FontWeight.bold,
                              color: Color(0xFF6750A4),
                            ),
                          ),
                          Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 7, vertical: 2),
                            decoration: BoxDecoration(
                              color: Colors.grey.shade100,
                              borderRadius: BorderRadius.circular(8),
                            ),
                            child: const Text(
                              'optional',
                              style: TextStyle(
                                fontSize: 10,
                                color: Color(0xFF999999),
                                fontWeight: FontWeight.w500,
                              ),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 12),
                      TextField(
                        controller: _instructionsController,
                        maxLines: 3,
                        minLines: 2,
                        style: const TextStyle(
                            fontSize: 14, color: Color(0xFF333333)),
                        decoration: InputDecoration(
                          hintText:
                              'e.g. mention I\'ll be out next week, ask for a reschedule, keep it short...',
                          hintStyle: TextStyle(
                              fontSize: 13, color: Colors.grey.shade400),
                          filled: true,
                          fillColor: const Color(0xFFF5F4FF),
                          border: OutlineInputBorder(
                            borderRadius: BorderRadius.circular(12),
                            borderSide: BorderSide.none,
                          ),
                          focusedBorder: OutlineInputBorder(
                            borderRadius: BorderRadius.circular(12),
                            borderSide: const BorderSide(
                                color: Color(0xFF6750A4), width: 1.5),
                          ),
                          contentPadding: const EdgeInsets.all(12),
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 12),
                SizedBox(
                  width: double.infinity,
                  child: ElevatedButton.icon(
                    onPressed: _generatingDraft ? null : _generateDraft,
                    icon: _generatingDraft
                        ? const SizedBox(
                            width: 16,
                            height: 16,
                            child: CircularProgressIndicator(
                                strokeWidth: 2, color: Colors.white),
                          )
                        : const Icon(Icons.auto_awesome, size: 18),
                    label: Text(_generatingDraft
                        ? 'Generating Draft...'
                        : 'Generate Reply Draft'),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFF6750A4),
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(vertical: 15),
                      elevation: 4,
                      shadowColor:
                          const Color(0xFF6750A4).withValues(alpha: 0.4),
                      shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(14)),
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


class _DetailCard extends StatelessWidget {
  final Widget child;
  const _DetailCard({required this.child});

  @override
  Widget build(BuildContext context) => Container(
        width: double.infinity,
        padding: const EdgeInsets.all(18),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(20),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.05),
              blurRadius: 12,
              offset: const Offset(0, 4),
            ),
          ],
        ),
        child: child,
      );
}


class _Section extends StatelessWidget {
  final IconData icon;
  final Color iconColor;
  final String title;
  final Widget child;

  const _Section({
    required this.icon,
    required this.iconColor,
    required this.title,
    required this.child,
  });

  @override
  Widget build(BuildContext context) => Container(
        width: double.infinity,
        padding: const EdgeInsets.all(18),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(20),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.05),
              blurRadius: 12,
              offset: const Offset(0, 4),
            ),
          ],
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  padding: const EdgeInsets.all(6),
                  decoration: BoxDecoration(
                    color: iconColor.withValues(alpha: 0.1),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Icon(icon, size: 14, color: iconColor),
                ),
                const SizedBox(width: 8),
                Text(
                  title,
                  style: TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.bold,
                    color: iconColor,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 14),
            child,
          ],
        ),
      );
}


class _ToneSelector extends StatelessWidget {
  static const _tones = [
    ('professional', Icons.business_center_outlined),
    ('friendly', Icons.emoji_emotions_outlined),
    ('concise', Icons.compress),
    ('detailed', Icons.format_align_left_outlined),
  ];

  final String selected;
  final ValueChanged<String> onChanged;

  const _ToneSelector({required this.selected, required this.onChanged});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(20),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.05),
            blurRadius: 12,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(6),
                decoration: BoxDecoration(
                  color: const Color(0xFF6750A4).withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: const Icon(Icons.tune,
                    size: 14, color: Color(0xFF6750A4)),
              ),
              const SizedBox(width: 8),
              const Text(
                'Reply Tone',
                style: TextStyle(
                  fontSize: 14,
                  fontWeight: FontWeight.bold,
                  color: Color(0xFF6750A4),
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
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
                      duration: const Duration(milliseconds: 180),
                      curve: Curves.easeInOut,
                      padding: const EdgeInsets.symmetric(vertical: 10),
                      decoration: BoxDecoration(
                        color: isSelected
                            ? const Color(0xFF6750A4)
                            : const Color(0xFFF5F4FF),
                        borderRadius: BorderRadius.circular(12),
                        boxShadow: isSelected
                            ? [
                                BoxShadow(
                                  color: const Color(0xFF6750A4)
                                      .withValues(alpha: 0.35),
                                  blurRadius: 8,
                                  offset: const Offset(0, 3),
                                ),
                              ]
                            : null,
                      ),
                      child: Column(
                        children: [
                          Icon(
                            icon,
                            size: 18,
                            color: isSelected
                                ? Colors.white
                                : const Color(0xFF9E9E9E),
                          ),
                          const SizedBox(height: 5),
                          Text(
                            tone,
                            style: TextStyle(
                              fontSize: 10,
                              fontWeight: FontWeight.w600,
                              color: isSelected
                                  ? Colors.white
                                  : const Color(0xFF9E9E9E),
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
      ),
    );
  }
}


class _FeedbackConfirmation extends StatelessWidget {
  final bool edited;
  const _FeedbackConfirmation({required this.edited});

  @override
  Widget build(BuildContext context) {
    final label =
        edited ? 'You edited this draft' : 'Sent as-is — great prompt match!';
    final icon = edited ? Icons.edit_note : Icons.thumb_up_rounded;
    final color = edited ? Colors.orange.shade700 : const Color(0xFF6750A4);
    final bg = edited ? Colors.orange.shade50 : Colors.purple.shade50;

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: color.withValues(alpha: 0.25)),
      ),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(6),
            decoration: BoxDecoration(
              color: color.withValues(alpha: 0.12),
              shape: BoxShape.circle,
            ),
            child: Icon(icon, size: 15, color: color),
          ),
          const SizedBox(width: 10),
          Text(
            label,
            style: TextStyle(
              fontSize: 13,
              color: color,
              fontWeight: FontWeight.w600,
            ),
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
        padding: const EdgeInsets.only(top: 8),
        child: Row(
          children: [
            Icon(icon, size: 14, color: const Color(0xFFAAAAAA)),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                text,
                style: const TextStyle(
                  fontSize: 13,
                  color: Color(0xFF777777),
                ),
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ],
        ),
      );
}
