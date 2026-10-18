import 'package:flutter/material.dart';

import '../../api/api_client.dart';
import '../../models/models.dart';
import '../../theme.dart';

class StaffBookingsTab extends StatefulWidget {
  const StaffBookingsTab({super.key});

  @override
  State<StaffBookingsTab> createState() => _StaffBookingsTabState();
}

class _StaffBookingsTabState extends State<StaffBookingsTab> {
  final _api = ApiClient();
  List<Booking> _bookings = [];
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
      final data = await _api.get('/api/bookings/mine');
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

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('My Bookings'),
        actions: [IconButton(icon: const Icon(Icons.refresh), onPressed: _load)],
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
            Text(_error!, textAlign: TextAlign.center),
            const SizedBox(height: 12),
            ElevatedButton(onPressed: _load, child: const Text('Retry')),
          ],
        ),
      );
    }
    if (_bookings.isEmpty) {
      return const Center(
        child: Text('No bookings assigned to you', style: TextStyle(color: WaveBookColors.muted)),
      );
    }
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView.builder(
        padding: const EdgeInsets.all(16),
        itemCount: _bookings.length,
        itemBuilder: (context, i) => _StaffBookingCard(booking: _bookings[i]),
      ),
    );
  }
}

class _StaffBookingCard extends StatelessWidget {
  final Booking booking;

  const _StaffBookingCard({required this.booking});

  @override
  Widget build(BuildContext context) {
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
                if (booking.reference.isNotEmpty)
                  Text(booking.reference, style: const TextStyle(color: WaveBookColors.muted, fontSize: 12)),
              ],
            ),
            const SizedBox(height: 8),
            _InfoRow(icon: Icons.content_cut, text: booking.serviceName),
            _InfoRow(icon: Icons.event, text: '${booking.date} at ${booking.time}'),
            if (booking.customerPhone.isNotEmpty)
              _InfoRow(icon: Icons.phone, text: booking.customerPhone),
            if (booking.notes.isNotEmpty) _InfoRow(icon: Icons.notes, text: booking.notes),
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
