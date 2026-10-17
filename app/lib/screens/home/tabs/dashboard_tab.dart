import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../api/api_client.dart';
import '../../../models/models.dart';
import '../../../state/auth_state.dart';
import '../../../theme.dart';

/// Current app version — the dashboard compares this against the admin-managed
/// `latest_version` from /api/app/meta to show an update banner.
const String kAppVersion = '1.0.0';

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

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final businessData = await _api.get('/api/business');
      final bookingsData = await _api.get('/api/bookings');
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
            color: WaveBookColors.darkSurfaceAlt,
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
        if (business.subscriptionStatus == 'trial')
          Card(
            color: WaveBookColors.darkSurfaceAlt,
            child: ListTile(
              leading: const Icon(Icons.rocket_launch, color: WaveBookColors.pink),
              title: const Text('Free trial active', style: TextStyle(fontWeight: FontWeight.w700)),
              subtitle: Text(_trialNotice(business)),
              trailing: TextButton(
                onPressed: () => _openSubscription(context),
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
        const SizedBox(height: 8),
        Card(
          child: ListTile(
            leading: const Icon(Icons.logout, color: WaveBookColors.danger),
            title: const Text('Sign out', style: TextStyle(color: WaveBookColors.danger)),
            onTap: () => context.read<AuthState>().logout(),
          ),
        ),
      ],
    );
  }

  bool _hasUpdate() {
    final meta = _appMeta;
    if (meta == null || meta.latestVersion.isEmpty) return false;
    return _versionCompare(meta.latestVersion, kAppVersion) > 0;
  }

  int _versionCompare(String a, String b) {
    final pa = a.split('.').map((s) => int.tryParse(s) ?? 0).toList();
    final pb = b.split('.').map((s) => int.tryParse(s) ?? 0).toList();
    final len = pa.length > pb.length ? pa.length : pb.length;
    for (var i = 0; i < len; i++) {
      final va = i < pa.length ? pa[i] : 0;
      final vb = i < pb.length ? pb[i] : 0;
      if (va != vb) return va - vb;
    }
    return 0;
  }

  String _trialNotice(Business business) {
    if (business.trialEndsAt.isEmpty) return 'Subscribe for £9.99/month to unlock everything.';
    final parts = business.trialEndsAt.split('-');
    if (parts.length != 3) return 'Subscribe for £9.99/month to unlock everything.';
    final end = DateTime(int.parse(parts[0]), int.parse(parts[1]), int.parse(parts[2]));
    final days = end.difference(DateTime.now()).inDays;
    if (days <= 0) return 'Your free trial has ended. Subscribe for £9.99/month to keep using WaveBook.';
    if (days == 1) return 'Your free trial ends tomorrow. Subscribe for £9.99/month to keep everything.';
    return '$days days left in your free trial. Subscribe for £9.99/month to unlock everything.';
  }

  void _openUrl(String url) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('Open $url in your browser to update the app.')),
    );
  }

  String _today() {
    final now = DateTime.now();
    return '${now.year.toString().padLeft(4, '0')}-${now.month.toString().padLeft(2, '0')}-${now.day.toString().padLeft(2, '0')}';
  }

  void _openSubscription(BuildContext context) {
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('Subscriptions are activated on the WaveBook website: getwavebook.com/subscribe'),
      ),
    );
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
