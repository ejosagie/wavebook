import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../../services/app_update.dart';
import '../../account/change_password_screen.dart';
import '../../../state/auth_state.dart';
import '../../../state/theme_state.dart';
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
    final theme = context.watch<ThemeState>();
    return Scaffold(
      appBar: AppBar(title: const Text('More')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Card(
            margin: const EdgeInsets.only(bottom: 12),
            child: SwitchListTile(
              secondary: const Icon(Icons.light_mode_outlined, color: WaveBookColors.pink),
              title: const Text('Light theme', style: TextStyle(fontWeight: FontWeight.w700)),
              subtitle: const Text('White background with light pink accents'),
              value: theme.isLight,
              onChanged: (v) => context.read<ThemeState>().setLight(v),
            ),
          ),
          _MenuCard(
            icon: Icons.storefront_outlined,
            color: WaveBookColors.pink,
            title: 'Online Shop',
            subtitle: 'Shop settings, products and orders',
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
          _MenuCard(
            icon: Icons.lock_outline,
            color: WaveBookColors.rose,
            title: 'Change password',
            subtitle: 'Update your WaveBook sign-in password',
            onTap: () => _push(context, const ChangePasswordScreen()),
          ),
          _MenuCard(
            icon: Icons.support_agent_outlined,
            color: WaveBookColors.rose,
            title: 'Contact Support',
            subtitle: 'Email support@getwavebook.com',
            onTap: () => launchUrl(Uri.parse('mailto:support@getwavebook.com')),
          ),
          _MenuCard(
            icon: Icons.system_update_alt,
            color: WaveBookColors.pink,
            title: 'Check for updates',
            subtitle: 'You have version $kAppVersion',
            onTap: () => checkForUpdate(context, manual: true),
          ),
          Card(
            child: ListTile(
              leading: const CircleAvatar(
                backgroundColor: Color(0x26F87171),
                child: Icon(Icons.logout, color: WaveBookColors.danger),
              ),
              title: const Text(
                'Log out',
                style: TextStyle(fontWeight: FontWeight.w700, color: WaveBookColors.danger),
              ),
              onTap: () => confirmAndLogout(context),
            ),
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
