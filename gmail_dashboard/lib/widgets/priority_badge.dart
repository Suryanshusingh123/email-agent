import 'package:flutter/material.dart';

class PriorityBadge extends StatelessWidget {
  final String priority;

  const PriorityBadge(this.priority, {super.key});

  Color get _color => switch (priority.toLowerCase()) {
        'high' => const Color(0xFFE53935),
        'medium' => const Color(0xFFFB8C00),
        _ => const Color(0xFF43A047),
      };

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: _color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: _color.withValues(alpha: 0.4)),
      ),
      child: Text(
        priority.toUpperCase(),
        style: TextStyle(
          color: _color,
          fontSize: 10,
          fontWeight: FontWeight.bold,
          letterSpacing: 0.5,
        ),
      ),
    );
  }
}


class CategoryChip extends StatelessWidget {
  final String category;

  const CategoryChip(this.category, {super.key});

  IconData get _icon => switch (category.toLowerCase()) {
        'security' => Icons.security,
        'work' => Icons.work,
        'finance' => Icons.attach_money,
        'newsletter' => Icons.newspaper,
        'promotional' => Icons.local_offer,
        'social' => Icons.people,
        'personal' => Icons.person,
        _ => Icons.mail,
      };

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(_icon, size: 12, color: Colors.grey[500]),
        const SizedBox(width: 4),
        Text(
          category,
          style: TextStyle(fontSize: 12, color: Colors.grey[500]),
        ),
      ],
    );
  }
}
