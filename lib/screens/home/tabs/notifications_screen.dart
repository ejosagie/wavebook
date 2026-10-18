import 'package:flutter/material.dart';

import '../../../api/api_client.dart';
import '../../../services/notification_service.dart';
import '../../../theme.dart';

class NotificationsScreen extends StatefulWidget {
  const NotificationsScreen({super.key});

  @override
  State<NotificationsScreen> createState() => _NotificationsScreenState();
}

class _NotificationsScreenState extends State<NotificationsScreen> {
  final _api = ApiClient();
  final _service = NotificationService();
  List<AppNotification> _items = [];
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
      final data = await _api.get('/api/notifications');
      if (!mounted) return;
      setState(() {
        _items = (data as List)
            .map((n) => AppNotification.fromJson(n as Map<String, dynamic>))
            .toList();
      });
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _markRead(AppNotification n) async {
    if (n.read) return;
    await _service.markRead(n.id);
    setState(() {
      _items = _items.map((x) => x.id == n.id ? AppNotification.fromJson({..._toJson(x), 'read': 1}) : x).toList();
    });
  }

  Map<String, dynamic> _toJson(AppNotification n) => {
        'id': n.id,
        'type': n.type,
        'title': n.title,
        'message': n.message,
        'booking_id': n.bookingId,
        'read': n.read ? 1 : 0,
        'created_at': n.createdAt,
      };

  Future<void> _markAllRead() async {
    await _service.markAllRead();
    setState(() {
      _items = _items.map((x) => AppNotification.fromJson({..._toJson(x), 'read': 1})).toList();
    });
  }

  IconData _iconFor(String type) {
    switch (type) {
      case 'payment':
        return Icons.payments_outlined;
      case 'feedback':
        return Icons.rate_review_outlined;
      default:
        return Icons.event_outlined;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Notifications'),
        actions: [
          if (_items.any((n) => !n.read))
            TextButton(onPressed: _markAllRead, child: const Text('Mark all read')),
        ],
      ),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_error != null) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text(_error!),
            const SizedBox(height: 12),
            ElevatedButton(onPressed: _load, child: const Text('Retry')),
          ],
        ),
      );
    }
    if (_items.isEmpty) {
      return const Center(
        child: Text('No notifications yet. New bookings and payments will appear here.'),
      );
    }
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView.builder(
        padding: const EdgeInsets.all(16),
        itemCount: _items.length,
        itemBuilder: (context, index) {
          final n = _items[index];
          return Card(
            color: n.read ? null : Theme.of(context).colorScheme.surfaceContainerHighest,
            child: ListTile(
              leading: CircleAvatar(
                backgroundColor: WaveBookColors.pink.withValues(alpha: 0.15),
                child: Icon(_iconFor(n.type), color: WaveBookColors.pink),
              ),
              title: Text(
                n.title,
                style: TextStyle(
                  fontWeight: n.read ? FontWeight.w500 : FontWeight.w800,
                ),
              ),
              subtitle: Text(
                '${n.message}\n${n.createdAt}',
                style: const TextStyle(fontSize: 13),
              ),
              isThreeLine: true,
              trailing: n.read ? null : const Icon(Icons.circle, size: 10, color: WaveBookColors.pink),
              onTap: () => _markRead(n),
            ),
          );
        },
      ),
    );
  }
}
