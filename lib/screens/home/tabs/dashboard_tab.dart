import 'dart:async';
import 'dart:io' show Platform;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../../api/api_client.dart';
import '../../../models/models.dart';
import '../../../services/app_update.dart';
import '../../../state/auth_state.dart';
import '../../../theme.dart';
import '../../storefront/shop_screen.dart';
import 'chats_screen.dart';
import 'notifications_screen.dart';

class DashboardTab extends StatefulWidget {
  const DashboardTab({super.key});

  @override
  State<DashboardTab> createState() => _DashboardTabState();
}

class _DashboardTabState extends State<DashboardTab> {
  final _api = ApiClient();
  Business? _business;
  List<Booking> _bookings = [];
  List<Service> _services = [];
  AppMeta? _appMeta;
  bool _loading = true;
  String? _error;
  int _unread = 0;
  int _chatUnread = 0;
  Timer? _unreadTimer;
  int _pendingOrders = 0;

  @override
  void initState() {
    super.initState();
    _load();
    _pollUnread();
    _unreadTimer = Timer.periodic(const Duration(seconds: 30), (_) => _pollUnread());
  }

  @override
  void dispose() {
    _unreadTimer?.cancel();
    super.dispose();
  }

  Future<void> _pollUnread() async {
    try {
      final data = await _api.get('/api/notifications/unread-count');
      if (!mounted) return;
      final count = (data as Map<String, dynamic>)['count'] as int? ?? 0;
      if (count != _unread) setState(() => _unread = count);
    } catch (_) {
      // Silent: badge polling failures shouldn't disturb the user.
    }
    try {
      final data = await _api.get('/api/chats/unread-count');
      if (!mounted) return;
      final count = (data as Map<String, dynamic>)['count'] as int? ?? 0;
      if (count != _chatUnread) setState(() => _chatUnread = count);
    } catch (_) {
      // Silent: badge polling failures shouldn't disturb the user.
    }
  }

  void _openChats() {
    Navigator.of(context)
        .push(MaterialPageRoute(builder: (_) => const ChatsScreen()))
        .then((_) => _pollUnread());
  }

  void _openNotifications() {
    Navigator.of(context)
        .push(MaterialPageRoute(builder: (_) => const NotificationsScreen()))
        .then((_) => _pollUnread());
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final businessData = await _api.get('/api/business');
      final bookingsData = await _api.get('/api/bookings');
      final ordersData = await _api.get('/api/orders');
      final servicesData = await _api.get('/api/services');
      AppMeta? appMeta;
      try {
        final metaData = await _api.get('/api/app/meta');
        appMeta = AppMeta.fromJson(metaData as Map<String, dynamic>);
      } on ApiException {
        appMeta = null;
      }
      if (!mounted) return;
      setState(() {
        _business = Business.fromJson(businessData as Map<String, dynamic>);
        _bookings = (bookingsData as List).map((b) => Booking.fromJson(b as Map<String, dynamic>)).toList();
        final orders = (ordersData as List)
          .map((o) => Order.fromJson(o as Map<String, dynamic>))
          .toList();
        _pendingOrders = orders.where((o) => o.status == 'paid').length;
        _services = (servicesData as List).map((s) => Service.fromJson(s as Map<String, dynamic>)).toList();
        _appMeta = appMeta;
      });
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthState>();
    return Scaffold(
      appBar: AppBar(
        title: Text(_business?.name ?? 'Dashboard'),
        actions: [
          Stack(
            clipBehavior: Clip.none,
            children: [
              IconButton(
                icon: const Icon(Icons.chat_bubble_outline),
                onPressed: _openChats,
                tooltip: 'Customer chats',
              ),
              if (_chatUnread > 0)
                Positioned(
                  right: 6,
                  top: 6,
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
                    decoration: BoxDecoration(
                      color: WaveBookColors.pink,
                      borderRadius: BorderRadius.circular(10),
                    ),
                    constraints: const BoxConstraints(minWidth: 16),
                    child: Text(
                      '$_chatUnread',
                      textAlign: TextAlign.center,
                      style: const TextStyle(color: Colors.white, fontSize: 10, fontWeight: FontWeight.w800),
                    ),
                  ),
                ),
            ],
          ),
          Stack(
            clipBehavior: Clip.none,
            children: [
              IconButton(
                icon: const Icon(Icons.notifications_outlined),
                onPressed: _openNotifications,
                tooltip: 'Notifications',
              ),
              if (_unread > 0)
                Positioned(
                  right: 6,
                  top: 6,
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
                    decoration: BoxDecoration(
                      color: WaveBookColors.pink,
                      borderRadius: BorderRadius.circular(10),
                    ),
                    constraints: const BoxConstraints(minWidth: 16),
                    child: Text(
                      '$_unread',
                      textAlign: TextAlign.center,
                      style: const TextStyle(color: Colors.white, fontSize: 10, fontWeight: FontWeight.w800),
                    ),
                  ),
                ),
            ],
          ),
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _load,
            tooltip: 'Refresh',
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _load,
        child: _buildBody(auth),
      ),
    );
  }

  Widget _buildBody(AuthState auth) {
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_error != null) {
      return ListView(
        children: [
          const SizedBox(height: 80),
          Icon(Icons.cloud_off, size: 48, color: WaveBookColors.muted),
          const SizedBox(height: 12),
          Text(_error!, textAlign: TextAlign.center),
          const SizedBox(height: 16),
          Center(child: ElevatedButton(onPressed: _load, child: const Text('Retry'))),
        ],
      );
    }
    final business = _business!;
    final pending = _bookings.where((b) => b.status == 'pending').length;
    final confirmed = _bookings.where((b) => b.status == 'confirmed').length;
    final today = _bookings.where((b) => b.date == _today()).length;

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        if (_hasUpdate())
          Card(
            color: Theme.of(context).colorScheme.surfaceContainerHighest,
            child: ListTile(
              leading: const Icon(Icons.system_update_alt, color: WaveBookColors.pink),
              title: const Text('Update available', style: TextStyle(fontWeight: FontWeight.w700)),
              subtitle: Text(
                _appMeta!.updateMessage.isNotEmpty
                    ? _appMeta!.updateMessage
                    : 'A new version of the WaveBook app is available.',
              ),
              trailing: _appMeta!.updateUrl.isNotEmpty
                  ? TextButton(
                      onPressed: () => _openUrl(_appMeta!.updateUrl),
                      child: const Text('Update'),
                    )
                  : null,
            ),
          ),
        if (_hasUpdate()) const SizedBox(height: 8),
        if (business.subscriptionStatus == 'trial' || business.subscriptionStatus == 'expired')
          Card(
            color: Theme.of(context).colorScheme.surfaceContainerHighest,
            child: ListTile(
              leading: const Icon(Icons.rocket_launch, color: WaveBookColors.pink),
              title: Text(
                business.subscriptionStatus == 'expired' ? 'Free trial ended' : 'Free trial active',
                style: const TextStyle(fontWeight: FontWeight.w700),
              ),
              subtitle: Text(_trialNotice(business)),
              trailing: Platform.isIOS
                  ? null
                  : TextButton(
                      onPressed: () => _openUrl('https://getwavebook.com/subscribe'),
                      child: const Text('Subscribe'),
                    ),
            ),
          ),
        const SizedBox(height: 8),
        Row(
          children: [
            Expanded(
              child: _StatCard(
                label: 'Total Bookings',
                value: _bookings.length.toString(),
                icon: Icons.event,
                color: WaveBookColors.pink,
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: _StatCard(
                label: 'Pending',
                value: pending.toString(),
                icon: Icons.hourglass_top,
                color: WaveBookColors.warning,
              ),
            ),
          ],
        ),
        const SizedBox(height: 12),
        Row(
          children: [
            Expanded(
              child: _StatCard(
                label: 'Confirmed',
                value: confirmed.toString(),
                icon: Icons.check_circle,
                color: WaveBookColors.success,
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: _StatCard(
                label: 'Today',
                value: today.toString(),
                icon: Icons.today,
                color: WaveBookColors.pink,
              ),
            ),
          ],
        ),
        const SizedBox(height: 24),
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            const Text('Recent Bookings', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
            Text('${_services.length} services', style: const TextStyle(color: WaveBookColors.muted)),
          ],
        ),
        const SizedBox(height: 12),
        if (_bookings.isEmpty)
          const Card(
            child: Padding(
              padding: EdgeInsets.all(24),
              child: Text(
                'No bookings yet. Share your booking website to start receiving appointments.',
                textAlign: TextAlign.center,
                style: TextStyle(color: WaveBookColors.muted),
              ),
            ),
          )
        else
          ..._bookings.take(5).map((b) => _BookingTile(booking: b)),
        const SizedBox(height: 24),
        Card(
          child: ListTile(
            leading: const Icon(Icons.public, color: WaveBookColors.pink),
            title: const Text('Your booking website', style: TextStyle(fontWeight: FontWeight.w700)),
            subtitle: Text('${business.slug}.wab.is'),
            trailing: const Icon(Icons.open_in_new),
            onTap: () => _openWebsite(context, business.slug),
          ),
        ),
        if (_pendingOrders > 0) ...[
          const SizedBox(height: 8),
          Card(
            color: Theme.of(context).colorScheme.surfaceContainerHighest,
            child: ListTile(
              leading: const Icon(Icons.receipt_long_outlined, color: WaveBookColors.pink),
              title: Text(
                '$_pendingOrders pending order${_pendingOrders == 1 ? '' : 's'}',
                style: const TextStyle(fontWeight: FontWeight.w700),
              ),
              subtitle: const Text('Paid — confirm them in Online Shop'),
              trailing: const Icon(Icons.chevron_right),
              onTap: () => Navigator.of(context).push(
                MaterialPageRoute(builder: (_) => const ShopScreen(initialTab: 2)),
              ),
            ),
          ),
        ],
        const SizedBox(height: 8),
        Card(
          child: ListTile(
            leading: const Icon(Icons.logout, color: WaveBookColors.danger),
            title: const Text('Sign out', style: TextStyle(color: WaveBookColors.danger)),
            onTap: () => confirmAndLogout(context),
          ),
        ),
      ],
    );
  }

  bool _hasUpdate() {
    final meta = _appMeta;
    if (meta == null || meta.latestVersion.isEmpty) return false;
    return compareVersions(meta.latestVersion, kAppVersion) > 0;
  }

  String _trialNotice(Business business) {
    final ios = Platform.isIOS;
    final cta = ios
        ? 'Visit getwavebook.com to manage your subscription status.'
        : 'Choose a plan at getwavebook.com to unlock everything.';
    if (business.subscriptionStatus == 'expired') {
      return ios ? cta : 'Your free trial has ended. $cta';
    }
    if (business.trialEndsAt.isEmpty) return cta;
    final parts = business.trialEndsAt.split('-');
    if (parts.length != 3) return cta;
    final end = DateTime(int.parse(parts[0]), int.parse(parts[1]), int.parse(parts[2]));
    final days = end.difference(DateTime.now()).inDays;
    final date = '${parts[2]}/${parts[1]}/${parts[0]}';
    if (days <= 0) return ios ? cta : 'Your free trial ended on $date. $cta';
    if (days == 1) return 'Your free trial ends tomorrow ($date). $cta';
    return '$days days left in your free trial (ends $date). $cta';
  }

  void _openUrl(String url) {
    launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication);
  }

  String _today() {
    final now = DateTime.now();
    return '${now.year.toString().padLeft(4, '0')}-${now.month.toString().padLeft(2, '0')}-${now.day.toString().padLeft(2, '0')}';
  }

  void _openWebsite(BuildContext context, String slug) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('Open $slug.wab.is in your browser to view your booking site.')),
    );
  }
}

class _StatCard extends StatelessWidget {
  final String label;
  final String value;
  final IconData icon;
  final Color color;

  const _StatCard({
    required this.label,
    required this.value,
    required this.icon,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icon, color: color, size: 22),
            const SizedBox(height: 8),
            Text(value, style: const TextStyle(fontSize: 26, fontWeight: FontWeight.w800)),
            Text(label, style: const TextStyle(color: WaveBookColors.muted, fontSize: 13)),
          ],
        ),
      ),
    );
  }
}

class _BookingTile extends StatelessWidget {
  final Booking booking;

  const _BookingTile({required this.booking});

  @override
  Widget build(BuildContext context) {
    final color = switch (booking.status) {
      'confirmed' => WaveBookColors.success,
      'cancelled' => WaveBookColors.danger,
      _ => WaveBookColors.warning,
    };
    return Card(
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor: color.withValues(alpha: 0.12),
          child: Icon(Icons.person, color: color),
        ),
        title: Text(booking.customerName, style: const TextStyle(fontWeight: FontWeight.w700)),
        subtitle: Text('${booking.serviceName} · ${booking.date} at ${booking.time}'),
        trailing: Container(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
          decoration: BoxDecoration(
            color: color.withValues(alpha: 0.12),
            borderRadius: BorderRadius.circular(20),
          ),
          child: Text(
            booking.status.toUpperCase(),
            style: TextStyle(color: color, fontSize: 11, fontWeight: FontWeight.w700),
          ),
        ),
      ),
    );
  }
}
