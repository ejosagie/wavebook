import 'package:flutter/material.dart';

import '../../../theme.dart';
import '../../storefront/shop_screen.dart';
import 'customers_tab.dart';
import 'feedback_tab.dart';
import 'gallery_tab.dart';
import 'reports_screen.dart';
import 'settings_tab.dart';
import 'staff_tab.dart';
import 'subscription_tab.dart';
import 'website_screen.dart';

class MoreTab extends StatelessWidget {
  const MoreTab({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('More')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          _MenuCard(
            icon: Icons.storefront_outlined,
            color: WaveBookColors.pink,
            title: 'Online Shop',
            subtitle: 'Inventory, orders and shipping',
            onTap: () => _push(context, const ShopScreen()),
          ),
          _MenuCard(
            icon: Icons.public,
            color: WaveBookColors.pink,
            title: 'Website',
            subtitle: 'Your site address and theme colour',
            onTap: () => _push(context, const WebsiteScreen()),
          ),
          _MenuCard(
            icon: Icons.photo_library_outlined,
            color: WaveBookColors.pink,
            title: 'Gallery',
            subtitle: 'Manage your website gallery (up to 8 photos)',
            onTap: () => _push(context, const GalleryTab()),
          ),
          _MenuCard(
            icon: Icons.bar_chart,
            color: WaveBookColors.rose,
            title: 'Report',
            subtitle: 'Bookings, deposits and order income',
            onTap: () => _push(context, const ReportsScreen()),
          ),
          _MenuCard(
            icon: Icons.group_outlined,
            color: WaveBookColors.rose,
            title: 'Staff',
            subtitle: 'Invite up to 5 staff members',
            onTap: () => _push(context, const StaffTab()),
          ),
          _MenuCard(
            icon: Icons.people_outline,
            color: WaveBookColors.pink,
            title: 'Customers',
            subtitle: 'Customer profiles and booking history',
            onTap: () => _push(context, const CustomersTab()),
          ),
          _MenuCard(
            icon: Icons.rate_review_outlined,
            color: WaveBookColors.rose,
            title: 'Feedback',
            subtitle: 'Reviews left by your customers',
            onTap: () => _push(context, const FeedbackTab()),
          ),
          _MenuCard(
            icon: Icons.settings_outlined,
            color: WaveBookColors.rose,
            title: 'Settings',
            subtitle: 'Business info, contact details and rules',
            onTap: () => _push(context, const SettingsTab()),
          ),
          _MenuCard(
            icon: Icons.workspace_premium_outlined,
            color: WaveBookColors.pink,
            title: 'Subscription',
            subtitle: 'Manage your £9.99/month plan',
            onTap: () => _push(context, const SubscriptionTab()),
          ),
        ],
      ),
    );
  }

  void _push(BuildContext context, Widget screen) {
    Navigator.of(context).push(MaterialPageRoute(builder: (_) => screen));
  }
}

class _MenuCard extends StatelessWidget {
  final IconData icon;
  final Color color;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  const _MenuCard({
    required this.icon,
    required this.color,
    required this.title,
    required this.subtitle,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor: color.withValues(alpha: 0.15),
          child: Icon(icon, color: color),
        ),
        title: Text(title, style: const TextStyle(fontWeight: FontWeight.w700)),
        subtitle: Text(subtitle),
        trailing: const Icon(Icons.chevron_right),
        onTap: onTap,
      ),
    );
  }
}
