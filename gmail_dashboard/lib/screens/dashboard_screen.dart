import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../models/email_stats.dart';
import '../providers/dashboard_provider.dart';
import '../widgets/stat_card.dart';
import '../widgets/email_list_tile.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  @override
  void initState() {
    super.initState();
    // Load data as soon as the screen mounts
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<DashboardProvider>().loadAll();
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF8F9FA),
      appBar: AppBar(
        backgroundColor: Colors.white,
        elevation: 0,
        title: const Row(
          children: [
            Icon(Icons.auto_awesome, color: Color(0xFF6750A4), size: 22),
            SizedBox(width: 8),
            Text(
              'Gmail AI Agent',
              style: TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.bold,
                color: Color(0xFF1A1A2E),
              ),
            ),
          ],
        ),
        actions: [
          // Poll now button
          Consumer<DashboardProvider>(
            builder: (_, provider, __) => IconButton(
              onPressed: provider.polling ? null : () => provider.triggerPoll(),
              icon: provider.polling
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.refresh, color: Color(0xFF6750A4)),
              tooltip: 'Poll Gmail Now',
            ),
          ),
          const SizedBox(width: 8),
        ],
      ),
      body: Consumer<DashboardProvider>(
        builder: (context, provider, _) {
          // Show snackbar when poll completes
          if (provider.pollMessage != null) {
            WidgetsBinding.instance.addPostFrameCallback((_) {
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(content: Text(provider.pollMessage!), duration: const Duration(seconds: 3)),
              );
              provider.pollMessage = null;
            });
          }

          return RefreshIndicator(
            onRefresh: provider.loadAll,
            child: CustomScrollView(
              slivers: [
                // --- Stats cards ---
                SliverToBoxAdapter(child: _StatsSection()),

                // --- Category chart ---
                SliverToBoxAdapter(child: _CategoryChart()),

                // --- Draft quality ---
                SliverToBoxAdapter(child: _DraftQualitySection()),

                // --- Filter bar ---
                SliverToBoxAdapter(child: _FilterBar()),

                // --- Email list ---
                _EmailList(),
              ],
            ),
          );
        },
      ),
    );
  }
}


class _StatsSection extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Consumer<DashboardProvider>(
      builder: (_, provider, __) {
        final stats = provider.stats;
        final loading = provider.statsState == LoadState.loading;

        return Padding(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'Overview',
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: Color(0xFF1A1A2E)),
              ),
              const SizedBox(height: 12),
              if (loading)
                const Center(child: CircularProgressIndicator())
              else if (stats == null)
                const Text('No data yet. Run a poll first.')
              else
                GridView.count(
                  crossAxisCount: 2,
                  shrinkWrap: true,
                  physics: const NeverScrollableScrollPhysics(),
                  crossAxisSpacing: 10,
                  mainAxisSpacing: 10,
                  childAspectRatio: 1.5,
                  children: [
                    StatCard(
                      label: 'Total Processed',
                      value: '${stats.total}',
                      icon: Icons.mail_outline,
                      color: const Color(0xFF6750A4),
                      onTap: () => context.read<DashboardProvider>().clearFilters(),
                    ),
                    StatCard(
                      label: 'High Priority',
                      value: '${stats.highPriority}',
                      icon: Icons.priority_high,
                      color: const Color(0xFFE53935),
                      onTap: () => context.read<DashboardProvider>().setFilter(priority: 'high'),
                    ),
                    StatCard(
                      label: 'Action Required',
                      value: '${stats.actionRequired}',
                      icon: Icons.task_alt,
                      color: const Color(0xFF1565C0),
                      onTap: () => context.read<DashboardProvider>().setFilter(actionRequired: true),
                    ),
                    StatCard(
                      label: 'Security Alerts',
                      value: '${stats.byCategory['security'] ?? 0}',
                      icon: Icons.security,
                      color: const Color(0xFFE65100),
                      onTap: () => context.read<DashboardProvider>().setFilter(category: 'security'),
                    ),
                  ],
                ),
            ],
          ),
        );
      },
    );
  }
}


class _CategoryChart extends StatelessWidget {
  static const _colors = [
    Color(0xFF6750A4),
    Color(0xFF1565C0),
    Color(0xFFE53935),
    Color(0xFF43A047),
    Color(0xFFFB8C00),
    Color(0xFF00ACC1),
    Color(0xFFE65100),
    Color(0xFF757575),
  ];

  @override
  Widget build(BuildContext context) {
    return Consumer<DashboardProvider>(
      builder: (_, provider, __) {
        final stats = provider.stats;
        if (stats == null || stats.byCategory.isEmpty) return const SizedBox.shrink();

        final entries = stats.byCategory.entries.toList();

        return Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
          child: Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: Colors.grey.shade200),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'By Category',
                  style: TextStyle(fontSize: 14, fontWeight: FontWeight.bold, color: Color(0xFF1A1A2E)),
                ),
                const SizedBox(height: 16),
                Row(
                  children: [
                    // Pie chart
                    SizedBox(
                      height: 120,
                      width: 120,
                      child: PieChart(
                        PieChartData(
                          sections: entries.asMap().entries.map((e) {
                            final color = _colors[e.key % _colors.length];
                            return PieChartSectionData(
                              value: e.value.value.toDouble(),
                              color: color,
                              radius: 40,
                              title: '${e.value.value}',
                              titleStyle: const TextStyle(
                                fontSize: 11,
                                fontWeight: FontWeight.bold,
                                color: Colors.white,
                              ),
                            );
                          }).toList(),
                          sectionsSpace: 2,
                          centerSpaceRadius: 24,
                        ),
                      ),
                    ),
                    const SizedBox(width: 20),
                    // Legend
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: entries.asMap().entries.map((e) {
                          final color = _colors[e.key % _colors.length];
                          return Padding(
                            padding: const EdgeInsets.symmetric(vertical: 3),
                            child: Row(
                              children: [
                                Container(
                                  width: 10,
                                  height: 10,
                                  decoration: BoxDecoration(color: color, shape: BoxShape.circle),
                                ),
                                const SizedBox(width: 8),
                                Text(
                                  '${e.value.key} (${e.value.value})',
                                  style: TextStyle(fontSize: 12, color: Colors.grey[700]),
                                ),
                              ],
                            ),
                          );
                        }).toList(),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}


class _DraftQualitySection extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Consumer<DashboardProvider>(
      builder: (_, provider, __) {
        final telemetry = provider.stats?.draftTelemetry;

        // Hide section entirely if no drafts have been generated yet
        if (telemetry == null || telemetry.draftsGenerated == 0) {
          return const SizedBox.shrink();
        }

        return Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
          child: Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: Colors.grey.shade200),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Section header
                const Row(
                  children: [
                    Icon(Icons.auto_awesome, size: 15, color: Color(0xFF6750A4)),
                    SizedBox(width: 6),
                    Text(
                      'Draft Quality',
                      style: TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.bold,
                        color: Color(0xFF1A1A2E),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 16),

                // Top row: approval rate (big) + counts (small)
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    // Approval rate block
                    Expanded(
                      child: _ApprovalRateBlock(telemetry: telemetry),
                    ),
                    const SizedBox(width: 12),
                    // Sent vs edited breakdown
                    Expanded(
                      child: _DraftCountBreakdown(telemetry: telemetry),
                    ),
                  ],
                ),

                // Prompt version table — only if more than one version exists
                if (telemetry.byPromptVersion.isNotEmpty) ...[
                  const SizedBox(height: 16),
                  const Divider(height: 1),
                  const SizedBox(height: 12),
                  _PromptVersionTable(byVersion: telemetry.byPromptVersion),
                ],
              ],
            ),
          ),
        );
      },
    );
  }
}


class _ApprovalRateBlock extends StatelessWidget {
  final DraftTelemetry telemetry;
  const _ApprovalRateBlock({required this.telemetry});

  @override
  Widget build(BuildContext context) {
    final label = telemetry.approvalRateLabel;
    final hasFeedback = telemetry.totalWithFeedback > 0;

    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFF6750A4).withValues(alpha: 0.07),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            hasFeedback ? (label ?? '—') : '—',
            style: TextStyle(
              fontSize: 32,
              fontWeight: FontWeight.bold,
              color: hasFeedback ? const Color(0xFF6750A4) : Colors.grey,
            ),
          ),
          const SizedBox(height: 2),
          Text(
            'Approval rate',
            style: TextStyle(fontSize: 11, color: Colors.grey[600]),
          ),
          const SizedBox(height: 4),
          Text(
            hasFeedback
                ? '${telemetry.totalWithFeedback} rated'
                : 'No feedback yet',
            style: TextStyle(fontSize: 10, color: Colors.grey[500]),
          ),
        ],
      ),
    );
  }
}


class _DraftCountBreakdown extends StatelessWidget {
  final DraftTelemetry telemetry;
  const _DraftCountBreakdown({required this.telemetry});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _CountRow(
          icon: Icons.send_outlined,
          iconColor: const Color(0xFF43A047),
          label: 'Generated',
          value: telemetry.draftsGenerated,
        ),
        const SizedBox(height: 8),
        _CountRow(
          icon: Icons.thumb_up_outlined,
          iconColor: const Color(0xFF6750A4),
          label: 'Sent as-is',
          value: telemetry.draftsSentAsIs,
        ),
        const SizedBox(height: 8),
        _CountRow(
          icon: Icons.edit_note,
          iconColor: Colors.orange.shade700,
          label: 'Edited first',
          value: telemetry.draftsEdited,
        ),
      ],
    );
  }
}


class _CountRow extends StatelessWidget {
  final IconData icon;
  final Color iconColor;
  final String label;
  final int value;
  const _CountRow({required this.icon, required this.iconColor, required this.label, required this.value});

  @override
  Widget build(BuildContext context) => Row(
    children: [
      Icon(icon, size: 14, color: iconColor),
      const SizedBox(width: 6),
      Expanded(
        child: Text(label, style: TextStyle(fontSize: 12, color: Colors.grey[700])),
      ),
      Text(
        '$value',
        style: const TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: Color(0xFF1A1A2E)),
      ),
    ],
  );
}


class _PromptVersionTable extends StatelessWidget {
  final Map<String, int> byVersion;
  const _PromptVersionTable({required this.byVersion});

  @override
  Widget build(BuildContext context) {
    final entries = byVersion.entries.toList()
      ..sort((a, b) => a.key.compareTo(b.key));

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'BY PROMPT VERSION',
          style: TextStyle(fontSize: 10, fontWeight: FontWeight.bold, color: Colors.grey[500], letterSpacing: 0.8),
        ),
        const SizedBox(height: 8),
        ...entries.map((e) => Padding(
          padding: const EdgeInsets.only(bottom: 6),
          child: Row(
            children: [
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  color: const Color(0xFF6750A4).withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(6),
                ),
                child: Text(
                  'v${e.key}',
                  style: const TextStyle(fontSize: 11, color: Color(0xFF6750A4), fontWeight: FontWeight.w600),
                ),
              ),
              const SizedBox(width: 10),
              Text(
                '${e.value} draft${e.value == 1 ? '' : 's'}',
                style: TextStyle(fontSize: 12, color: Colors.grey[700]),
              ),
            ],
          ),
        )),
      ],
    );
  }
}


class _FilterBar extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Consumer<DashboardProvider>(
      builder: (_, provider, __) {
        final hasFilter = provider.filterPriority != null ||
            provider.filterCategory != null ||
            provider.filterActionRequired != null;

        return Padding(
          padding: const EdgeInsets.fromLTRB(16, 4, 16, 4),
          child: Row(
            children: [
              const Text(
                'Emails',
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: Color(0xFF1A1A2E)),
              ),
              if (hasFilter) ...[
                const SizedBox(width: 8),
                GestureDetector(
                  onTap: provider.clearFilters,
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                    decoration: BoxDecoration(
                      color: const Color(0xFF6750A4).withValues(alpha: 0.1),
                      borderRadius: BorderRadius.circular(6),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(
                          _filterLabel(provider),
                          style: const TextStyle(fontSize: 11, color: Color(0xFF6750A4)),
                        ),
                        const SizedBox(width: 4),
                        const Icon(Icons.close, size: 12, color: Color(0xFF6750A4)),
                      ],
                    ),
                  ),
                ),
              ],
              const Spacer(),
              Text(
                '${provider.emailsTotal} total',
                style: TextStyle(fontSize: 12, color: Colors.grey[500]),
              ),
            ],
          ),
        );
      },
    );
  }

  String _filterLabel(DashboardProvider p) {
    if (p.filterPriority != null) return p.filterPriority!;
    if (p.filterCategory != null) return p.filterCategory!;
    if (p.filterActionRequired == true) return 'action required';
    return '';
  }
}


class _EmailList extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Consumer<DashboardProvider>(
      builder: (_, provider, __) {
        if (provider.emailsState == LoadState.loading) {
          return const SliverToBoxAdapter(
            child: Padding(
              padding: EdgeInsets.all(32),
              child: Center(child: CircularProgressIndicator()),
            ),
          );
        }

        if (provider.emailsState == LoadState.error) {
          return SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.all(32),
              child: Center(
                child: Column(
                  children: [
                    const Icon(Icons.error_outline, size: 48, color: Colors.red),
                    const SizedBox(height: 8),
                    Text(provider.emailsError ?? 'Unknown error',
                        textAlign: TextAlign.center,
                        style: const TextStyle(color: Colors.red)),
                  ],
                ),
              ),
            ),
          );
        }

        if (provider.emails.isEmpty) {
          return const SliverToBoxAdapter(
            child: Padding(
              padding: EdgeInsets.all(48),
              child: Center(
                child: Column(
                  children: [
                    Icon(Icons.inbox, size: 48, color: Colors.grey),
                    SizedBox(height: 12),
                    Text('No emails yet.\nTap ↻ to poll Gmail.',
                        textAlign: TextAlign.center,
                        style: TextStyle(color: Colors.grey)),
                  ],
                ),
              ),
            ),
          );
        }

        return SliverList(
          delegate: SliverChildBuilderDelegate(
            (context, index) {
              if (index >= provider.emails.length) return const SizedBox(height: 16);
              return EmailListTile(email: provider.emails[index]);
            },
            childCount: provider.emails.length + 1,
          ),
        );
      },
    );
  }
}
