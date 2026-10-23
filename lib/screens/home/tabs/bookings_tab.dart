import 'dart:async';

import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../../api/api_client.dart';
import '../../../models/models.dart';
import '../../../theme.dart';

const int _pageSize = 20;

class BookingsTab extends StatefulWidget {
  const BookingsTab({super.key});

  @override
  State<BookingsTab> createState() => _BookingsTabState();
}

class _BookingsTabState extends State<BookingsTab> {
  final _api = ApiClient();
  List<Booking> _bookings = [];
  bool _loading = true;
  bool _loadingMore = false;
  String? _error;
  String _filter = 'all';
  int _total = 0;
  String _search = '';
  final _searchCtrl = TextEditingController();
  Timer? _debounce;
  List<StaffMember> _staff = [];
  bool _canAssign = false;
  List<Service> _services = [];
  String _businessSlug = '';

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _searchCtrl.dispose();
    super.dispose();
  }

  Future<void> _fetchBookings({bool append = false}) async {
    if (!append) {
      setState(() {
        _loading = true;
        _error = null;
      });
    } else {
      setState(() => _loadingMore = true);
    }
    try {
      final offset = append ? _bookings.length : 0;
      final params = <String, String>{
        'limit': '$_pageSize',
        'offset': '$offset',
        if (_filter != 'all') 'status': _filter,
        if (_search.isNotEmpty) 'q': _search,
      };
      final uri = Uri(queryParameters: params).query;
      final data = await _api.get('/api/bookings?$uri') as Map<String, dynamic>;
      if (!mounted) return;
      final items = (data['items'] as List)
          .map((b) => Booking.fromJson(b as Map<String, dynamic>))
          .toList();
      setState(() {
        _bookings = append ? [..._bookings, ...items] : items;
        _total = data['total'] as int? ?? items.length;
      });
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } finally {
      if (mounted) {
        setState(() {
          _loading = false;
          _loadingMore = false;
        });
      }
    }
  }

  void _onSearchChanged(String value) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 350), () {
      _search = value.trim();
      _fetchBookings();
    });
  }

  Future<void> _load() async {
    await _fetchBookings();
    if (!mounted) return;
    try {
      try {
        final businessData = await _api.get('/api/business') as Map<String, dynamic>;
        if (mounted) setState(() => _businessSlug = businessData['slug']?.toString() ?? '');
      } on ApiException {
        // Schedule link needs the slug; leave it empty if unavailable.
      }
      try {
        final servicesData = await _api.get('/api/services');
        if (mounted) {
          setState(() {
            _services = (servicesData as List)
                .map((s) => Service.fromJson(s as Map<String, dynamic>))
                .toList();
          });
        }
      } on ApiException {
        // Intake labels are optional; answers still display with their ids.
      }
      try {
        final sub = SubscriptionInfo.fromJson(await _api.get('/api/subscription') as Map<String, dynamic>);
        final canAssign = sub.maxStaff > 0;
        if (canAssign) {
          final staffData = await _api.get('/api/staff');
          if (mounted) {
            setState(() {
              _staff = (staffData as List).map((s) => StaffMember.fromJson(s as Map<String, dynamic>)).toList();
            });
          }
        }
        if (mounted) setState(() => _canAssign = canAssign);
      } on ApiException {
        if (mounted) setState(() => _canAssign = false);
      }
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Map<String, String> _intakeLabels(Booking booking) {
    final service = _services.where((s) => s.id == booking.serviceId).firstOrNull;
    if (service == null) return booking.intakeAnswers;
    final labels = <String, String>{};
    for (final q in service.questions) {
      final qid = q['id']?.toString();
      if (qid != null) labels[qid] = q['label']?.toString() ?? qid;
    }
    return booking.intakeAnswers.map((k, v) => MapEntry(labels[k] ?? k, v));
  }

  Future<void> _setStatus(Booking booking, String status) async {
    try {
      await _api.patch('/api/bookings/${booking.id}/status', body: {'status': status});
      await _load();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Booking ${status == 'confirmed' ? 'confirmed' : status == 'cancelled' ? 'cancelled' : 'updated'}'),
        ),
      );
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  Future<void> _assign(Booking booking) async {
    if (_staff.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Invite a staff member first (WaveBook Premium)')),
      );
      return;
    }
    final choice = await showDialog<({int? staffId})>(
      context: context,
      builder: (ctx) => SimpleDialog(
        title: const Text('Assign to'),
        children: [
          SimpleDialogOption(
            onPressed: () => Navigator.pop(ctx, (staffId: null)),
            child: const Text('Unassigned'),
          ),
          for (final member in _staff)
            SimpleDialogOption(
              onPressed: () => Navigator.pop(ctx, (staffId: member.id)),
              child: Text(member.fullName),
            ),
        ],
      ),
    );
    if (choice == null) return;
    try {
      await _api.patch('/api/bookings/${booking.id}/assign', body: {'staff_id': choice.staffId});
      await _load();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(choice.staffId == null ? 'Booking unassigned' : 'Booking assigned, staff member emailed'),
          ),
        );
      }
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

  Future<void> _openSchedule() async {
    try {
      final data = await _api.post('/api/business/calendar-token') as Map<String, dynamic>;
      final token = data['calendar_token'] as String;
      final url = '$kApiBaseUrl/t/$_businessSlug/calendar.ics?token=$token';
      final launched = await launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication);
      if (!launched && mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Could not open the calendar link')),
        );
      }
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  List<Booking> get _filtered => _bookings;

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
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
            child: TextField(
              controller: _searchCtrl,
              onChanged: _onSearchChanged,
              decoration: InputDecoration(
                hintText: 'Search name, email, phone or booking ID',
                prefixIcon: const Icon(Icons.search),
                suffixIcon: _searchCtrl.text.isEmpty
                    ? null
                    : IconButton(
                        icon: const Icon(Icons.clear),
                        onPressed: () {
                          _searchCtrl.clear();
                          _debounce?.cancel();
                          _search = '';
                          _fetchBookings();
                        },
                      ),
                isDense: true,
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
              ),
            ),
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            child: FittedBox(
              fit: BoxFit.scaleDown,
              child: SegmentedButton<String>(
                segments: const [
                  ButtonSegment(value: 'all', label: Text('All', maxLines: 1)),
                  ButtonSegment(value: 'pending', label: Text('Pending', maxLines: 1)),
                  ButtonSegment(value: 'confirmed', label: Text('Confirmed', maxLines: 1)),
                  ButtonSegment(value: 'cancelled', label: Text('Cancelled', maxLines: 1)),
                ],
                selected: {_filter},
                onSelectionChanged: (s) {
                  setState(() => _filter = s.first);
                  _fetchBookings();
                },
              ),
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
      return Center(
        child: Text(
          _search.isEmpty ? 'No bookings found' : 'No bookings match "$_search"',
          style: const TextStyle(color: WaveBookColors.muted),
        ),
      );
    }
    final hasMore = _bookings.length < _total;
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView.builder(
        padding: const EdgeInsets.all(16),
        itemCount: bookings.length + 2,
        itemBuilder: (context, i) {
          if (i == 0) {
            return Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Text(
                '${bookings.length} of $_total bookings',
                style: const TextStyle(color: WaveBookColors.muted, fontSize: 13),
              ),
            );
          }
          if (i == bookings.length + 1) {
            if (!hasMore) return const SizedBox.shrink();
            return Center(
              child: _loadingMore
                  ? const Padding(
                      padding: EdgeInsets.all(12),
                      child: CircularProgressIndicator(),
                    )
                  : TextButton.icon(
                      onPressed: () => _fetchBookings(append: true),
                      icon: const Icon(Icons.expand_more),
                      label: Text('Load more ($_total - ${_bookings.length} remaining)'),
                    ),
            );
          }
          final index = i - 1;
          final b = bookings[index];
          return _BookingCard(
            booking: b,
            intakeLabels: _intakeLabels(b),
            onConfirm: () => _setStatus(b, 'confirmed'),
            onCancel: () => _setStatus(b, 'cancelled'),
            onDelete: () => _delete(b),
            onAddToCalendar: _openSchedule,
            onAssign: () => _assign(b),
            canAssign: _canAssign,
          );
        },
      ),
    );
  }
}

class _BookingCard extends StatelessWidget {
  final Booking booking;
  final Map<String, String> intakeLabels;
  final VoidCallback onConfirm;
  final VoidCallback onCancel;
  final VoidCallback onDelete;
  final VoidCallback onAddToCalendar;
  final VoidCallback onAssign;
  final bool canAssign;

  const _BookingCard({
    required this.booking,
    this.intakeLabels = const {},
    required this.onConfirm,
    required this.onCancel,
    required this.onDelete,
    required this.onAddToCalendar,
    required this.onAssign,
    required this.canAssign,
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
                    maxLines: 1,
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
            if (booking.intakeAnswers.isNotEmpty) ...[
              const SizedBox(height: 4),
              Text(
                'Intake answers',
                style: TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.w700,
                  color: WaveBookColors.muted,
                ),
              ),
              ...intakeLabels.entries.map(
                (e) => _InfoRow(icon: Icons.fact_check_outlined, text: '${e.key}: ${e.value}'),
              ),
            ],
            if (booking.assignedStaffName != null)
              _InfoRow(icon: Icons.badge_outlined, text: 'Assigned to ${booking.assignedStaffName}'),
            const SizedBox(height: 12),
            if (booking.status != 'cancelled') ...[
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
                ],
              ),
              const SizedBox(height: 4),
            ],
            Row(
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                if (canAssign)
                  IconButton(
                    icon: const Icon(Icons.person_add_alt_1_outlined, color: WaveBookColors.pink),
                    onPressed: onAssign,
                    tooltip: 'Assign to staff',
                  ),
                IconButton(
                  icon: const Icon(Icons.calendar_month_outlined, color: WaveBookColors.pink),
                  onPressed: onAddToCalendar,
                  tooltip: 'Open schedule link',
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
