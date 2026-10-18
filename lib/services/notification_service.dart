import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../api/api_client.dart';

class AppNotification {
  final int id;
  final String type;
  final String title;
  final String message;
  final int? bookingId;
  final bool read;
  final String createdAt;

  AppNotification({
    required this.id,
    required this.type,
    required this.title,
    required this.message,
    this.bookingId,
    required this.read,
    required this.createdAt,
  });

  factory AppNotification.fromJson(Map<String, dynamic> json) => AppNotification(
        id: json['id'] as int,
        type: json['type'] as String? ?? 'booking',
        title: json['title'] as String? ?? '',
        message: json['message'] as String? ?? '',
        bookingId: json['booking_id'] as int?,
        read: (json['read'] as int? ?? 0) == 1,
        createdAt: json['created_at'] as String? ?? '',
      );
}

/// Polls the backend for new booking notifications and shows a popup.
class NotificationService {
  final ApiClient _api = ApiClient();
  Timer? _timer;
  int _lastSeenId = 0;
  bool _running = false;

  /// Start polling. [onNewBooking] is called when a new booking notification arrives.
  void start({required void Function(AppNotification notification) onNewBooking}) {
    if (_running) return;
    _running = true;
    _poll(onNewBooking);
    _timer = Timer.periodic(const Duration(seconds: 20), (_) => _poll(onNewBooking));
  }

  void stop() {
    _running = false;
    _timer?.cancel();
    _timer = null;
  }

  Future<void> _poll(void Function(AppNotification) onNewBooking) async {
    try {
      final data = await _api.get('/api/notifications?since=$_lastSeenId');
      final items = (data as List)
          .map((n) => AppNotification.fromJson(n as Map<String, dynamic>))
          .toList();
      for (final n in items.reversed) {
        if (n.id > _lastSeenId) {
          _lastSeenId = n.id;
          if (n.type == 'booking') {
            onNewBooking(n);
          }
        }
      }
    } catch (_) {
      // Silent: polling failures shouldn't disturb the user.
    }
  }

  Future<void> markRead(int id) async {
    try {
      await _api.post('/api/notifications/$id/read');
    } catch (_) {}
  }

  Future<void> markAllRead() async {
    try {
      await _api.post('/api/notifications/read-all');
    } catch (_) {}
  }
}

/// Shows the booking popup dialog.
void showBookingNotificationPopup(
  BuildContext context,
  AppNotification notification,
) {
  SystemSound.play(SystemSoundType.alert);
  showDialog(
    context: context,
    barrierDismissible: true,
    builder: (ctx) => AlertDialog(
      icon: const Icon(Icons.notifications_active, color: Color(0xFFEC4899), size: 40),
      title: const Text('New Booking!'),
      content: Text(
        notification.message,
        textAlign: TextAlign.center,
        style: const TextStyle(fontSize: 15),
      ),
      actionsAlignment: MainAxisAlignment.center,
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(ctx),
          child: const Text('OK'),
        ),
      ],
    ),
  );
}
