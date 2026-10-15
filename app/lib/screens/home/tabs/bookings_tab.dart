import 'package:flutter/material.dart';

import '../../../api/api_client.dart';
import '../../../models/models.dart';
import '../../../theme.dart';

class BookingsTab extends StatefulWidget {
  const BookingsTab({super.key});

  @override
  State<BookingsTab> createState() => _BookingsTabState();
}

class _BookingsTabState extends State<BookingsTab> {
  final _api = ApiClient();
  List<Booking> _bookings = [];
  bool _loading = true;
  String? _error;
  String _filter = 'all';

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
      final data = await _api.get('/api/bookings');
      if (!mounted) return;
      setState(() {
        _bookings = (data as List).map((b) => Booking.fromJson(b as Map<String, dynamic>)).toList();
      });
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _setStatus(Booking booking, String status) async {
    try {
      await _api.patch('/api/bookings/${booking.id}/status', body: {'status': status});
      await _load();
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  Future<void> _delete(Booking booking) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Delete booking?'),
        content: Text('Delete the booking for ${booking.customerName}?'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          TextButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Delete', style: TextStyle(color: WaveBookColors.danger)),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    try {
      await _api.delete('/api/bookings/${booking.id}');
      await _load();
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  Future<void> _sendSms(Booking booking) async {
    final controller = TextEditingController(
      text: 'Hi ${booking.customerName}, your booking with us is '
          '${booking.serviceName} on ${booking.date} at ${booking.time}. '
          'See you soon!',
    );
    final message = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('Text ${booking.customerName}'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: controller,
              maxLines: 4,
              decoration: const InputDecoration(labelText: 'Message'),
            ),
            const SizedBox(height: 8),
            Align(
              alignment: Alignment.centerLeft,
              child: Text(
                'To: ${booking.customerPhone.isEmpty ? 'no phone on file' : booking.customerPhone}',
                style: const TextStyle(color: WaveBookColors.muted, fontSize: 12),
              ),
            ),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
          TextButton(
            onPressed: () => Navigator.pop(ctx, controller.text),
            child: const Text('Send Text'),
          ),
        ],
      ),
    );
    if (message == null || message.trim().isEmpty) return;
    if (booking.customerPhone.isEmpty) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('This customer has no phone number on file')),
        );
      }
      return;
    }
    try {
      await _api.post('/api/notifications/send-text', body: {
        'phone': booking.customerPhone,
        'message': message.trim(),
      });
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Text message sent')),
        );
      }
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  List<Booking> get _filtered {
    if (_filter == 'all') return _bookings;
    return _bookings.where((b) => b.status == _filter).toList();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Bookings'),
        actions: [IconButton(icon: const Icon(Icons.refresh), onPressed: _load)],
      ),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            child: SegmentedButton<String>(
              segments: const [
                ButtonSegment(value: 'all', label: Text('All')),
                ButtonSegment(value: 'pending', label: Text('Pending')),
                ButtonSegment(value: 'confirmed', label: Text('Confirmed')),
                ButtonSegment(value: 'cancelled', label: Text('Cancelled')),
              ],
              selected: {_filter},
              onSelectionChanged: (s) => setState(() => _filter = s.first),
            ),
          ),
          Expanded(child: _buildBody()),
        ],
      ),
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
    final bookings = _filtered;
    if (bookings.isEmpty) {
      return const Center(
        child: Text('No bookings found', style: TextStyle(color: WaveBookColors.muted)),
      );
    }
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView.builder(
        padding: const EdgeInsets.all(16),
        itemCount: bookings.length,
        itemBuilder: (context, i) => _BookingCard(
          booking: bookings[i],
          onConfirm: () => _setStatus(bookings[i], 'confirmed'),
          onCancel: () => _setStatus(bookings[i], 'cancelled'),
          onDelete: () => _delete(bookings[i]),
          onSendSms: () => _sendSms(bookings[i]),
        ),
      ),
    );
  }
}

class _BookingCard extends StatelessWidget {
  final Booking booking;
  final VoidCallback onConfirm;
  final VoidCallback onCancel;
  final VoidCallback onDelete;
  final VoidCallback onSendSms;

  const _BookingCard({
    required this.booking,
    required this.onConfirm,
    required this.onCancel,
    required this.onDelete,
    required this.onSendSms,
  });

  @override
  Widget build(BuildContext context) {
    final color = switch (booking.status) {
      'confirmed' => WaveBookColors.success,
      'cancelled' => WaveBookColors.danger,
      _ => WaveBookColors.warning,
    };
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    booking.customerName,
                    style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w800),
                  ),
                ),
                Container(
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
              ],
            ),
            const SizedBox(height: 8),
            _InfoRow(icon: Icons.content_cut, text: booking.serviceName),
            _InfoRow(icon: Icons.event, text: '${booking.date} at ${booking.time}'),
            if (booking.customerPhone.isNotEmpty)
              _InfoRow(icon: Icons.phone, text: booking.customerPhone),
            if (booking.customerEmail.isNotEmpty)
              _InfoRow(icon: Icons.email, text: booking.customerEmail),
            if (booking.notes.isNotEmpty) _InfoRow(icon: Icons.notes, text: booking.notes),
            if (booking.confirmationFile.isNotEmpty)
              _InfoRow(icon: Icons.receipt, text: 'Payment evidence uploaded'),
            const SizedBox(height: 12),
            Row(
              children: [
                if (booking.status == 'pending') ...[
                  Expanded(
                    child: ElevatedButton(
                      style: ElevatedButton.styleFrom(
                        backgroundColor: WaveBookColors.success,
                        minimumSize: const Size(0, 40),
                      ),
                      onPressed: onConfirm,
                      child: const Text('Confirm'),
                    ),
                  ),
                  const SizedBox(width: 8),
                ],
                if (booking.status != 'cancelled') ...[
                  Expanded(
                    child: OutlinedButton(
                      style: OutlinedButton.styleFrom(
                        foregroundColor: WaveBookColors.warning,
                        side: const BorderSide(color: WaveBookColors.warning),
                        minimumSize: const Size(0, 40),
                      ),
                      onPressed: onCancel,
                      child: const Text('Cancel'),
                    ),
                  ),
                  const SizedBox(width: 8),
                ],
                IconButton(
                  icon: const Icon(Icons.sms_outlined, color: WaveBookColors.pink),
                  onPressed: onSendSms,
                  tooltip: 'Send text message',
                ),
                IconButton(
                  icon: const Icon(Icons.delete_outline, color: WaveBookColors.danger),
                  onPressed: onDelete,
                  tooltip: 'Delete',
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _InfoRow extends StatelessWidget {
  final IconData icon;
  final String text;

  const _InfoRow({required this.icon, required this.text});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        children: [
          Icon(icon, size: 16, color: WaveBookColors.muted),
          const SizedBox(width: 8),
          Expanded(child: Text(text, style: const TextStyle(fontSize: 14))),
        ],
      ),
    );
  }
}
