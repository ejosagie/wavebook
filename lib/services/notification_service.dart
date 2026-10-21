import 'dart:async';

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

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

/// Polls the backend for new booking/chat notifications and shows a popup.
class NotificationService {
  final ApiClient _api = ApiClient();
  Timer? _timer;
  int _lastSeenId = 0;
  bool _running = false;
  bool _initialized = false;

  /// Start polling. [onNewBooking] is called when a new booking notification
  /// arrives, [onNewChat] when a new chat message notification arrives.
  void start({
    required void Function(AppNotification notification) onNewBooking,
    void Function(AppNotification notification)? onNewChat,
  }) {
    if (_running) return;
    _running = true;
    _poll(onNewBooking, onNewChat);
    _timer = Timer.periodic(
      const Duration(seconds: 20),
      (_) => _poll(onNewBooking, onNewChat),
    );
  }

  void stop() {
    _running = false;
    _timer?.cancel();
    _timer = null;
  }

  Future<void> _poll(
    void Function(AppNotification) onNewBooking,
    void Function(AppNotification)? onNewChat,
  ) async {
    try {
      final data = await _api.get('/api/notifications?since=$_lastSeenId');
      final items = (data as List)
          .map((n) => AppNotification.fromJson(n as Map<String, dynamic>))
          .toList();
      if (!_initialized) {
        // Seed the watermark with the newest existing notification so we only
        // alert for notifications that arrive after the app started.
        _initialized = true;
        if (items.isNotEmpty) _lastSeenId = items.first.id;
        return;
      }
      for (final n in items.reversed) {
        if (n.id > _lastSeenId) {
          _lastSeenId = n.id;
          if (n.type == 'booking') {
            onNewBooking(n);
          } else if (n.type == 'chat' && onNewChat != null) {
            onNewChat(n);
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

final AudioPlayer _bookingPlayer = AudioPlayer();
final AudioPlayer _chatPlayer = AudioPlayer();

const _bookingSoundKey = 'wavebook_booking_sound';
const _chatSoundKey = 'wavebook_chat_sound';

Future<bool> isBookingSoundEnabled() async {
  final prefs = await SharedPreferences.getInstance();
  return prefs.getBool(_bookingSoundKey) ?? true;
}

Future<void> setBookingSoundEnabled(bool enabled) async {
  final prefs = await SharedPreferences.getInstance();
  await prefs.setBool(_bookingSoundKey, enabled);
}

Future<bool> isChatSoundEnabled() async {
  final prefs = await SharedPreferences.getInstance();
  return prefs.getBool(_chatSoundKey) ?? true;
}

Future<void> setChatSoundEnabled(bool enabled) async {
  final prefs = await SharedPreferences.getInstance();
  await prefs.setBool(_chatSoundKey, enabled);
}

Future<void> _playBookingChime() async {
  try {
    if (!await isBookingSoundEnabled()) return;
    await _bookingPlayer.play(AssetSource('sounds/new_booking.wav'));
  } catch (_) {}
}

/// Plays the chat notification chime when a new customer chat message arrives.
Future<void> playChatNotificationSound() async {
  try {
    if (!await isChatSoundEnabled()) return;
    await _chatPlayer.play(AssetSource('sounds/new_booking.wav'));
  } catch (_) {}
}

/// Shows the booking popup dialog and plays the booking chime when enabled.
void showBookingNotificationPopup(
  BuildContext context,
  AppNotification notification,
) {
  unawaited(_playBookingChime());
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
