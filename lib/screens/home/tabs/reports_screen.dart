import 'package:flutter/material.dart';

import '../../../api/api_client.dart';
import '../../../theme.dart';

class ReportsScreen extends StatefulWidget {
  const ReportsScreen({super.key});

  @override
  State<ReportsScreen> createState() => _ReportsScreenState();
}

class _ReportsScreenState extends State<ReportsScreen> {
  final _api = ApiClient();
  String _period = 'today';
  Map<String, dynamic>? _data;
  bool _loading = true;
  String? _error;

  static const _periods = [
    ('today', 'Today'),
    ('week', 'This Week'),
    ('month', 'This Month'),
    ('year', 'This Year'),
  ];

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
      final data = await _api.get('/api/reports/financials?period=$_period');
      if (!mounted) return;
      setState(() => _data = data as Map<String, dynamic>);
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Report and Analytics')),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
            child: Row(
              children: _periods.map((p) {
                final (value, label) = p;
                final selected = _period == value;
                return Padding(
                  padding: const EdgeInsets.only(right: 8),
                  child: ChoiceChip(
                    label: Text(label),
                    selected: selected,
                    onSelected: (_) {
                      setState(() => _period = value);
                      _load();
                    },
                  ),
                );
              }).toList(),
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
    final d = _data!;
    final currency = d['currency']?.toString() ?? 'GBP';
    final symbol = currencySymbol(currency);
    final bookingsAmount = (d['bookings_amount'] as num).toDouble();
    final depositsAmount = (d['deposits_amount'] as num).toDouble();
    final ordersAmount = (d['orders_amount'] as num).toDouble();
    final total = bookingsAmount + depositsAmount + ordersAmount;
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Card(
            color: Theme.of(context).colorScheme.surfaceContainerHighest,
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('Total income', style: TextStyle(color: WaveBookColors.muted, fontSize: 13)),
                  const SizedBox(height: 4),
                  Text(
                    '$symbol${total.toStringAsFixed(2)}',
                    style: const TextStyle(fontSize: 32, fontWeight: FontWeight.w800, color: WaveBookColors.pink),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 12),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Row(
                children: [
                  CircleAvatar(
                    backgroundColor: WaveBookColors.pink.withValues(alpha: 0.15),
                    child: const Icon(Icons.event_available, color: WaveBookColors.pink),
                  ),
                  const SizedBox(width: 16),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text('Bookings', style: TextStyle(fontWeight: FontWeight.w700)),
                        const SizedBox(height: 2),
                        Text(
                          '${d['bookings_count'] as int} ${d['bookings_count'] == 1 ? 'booking' : 'bookings'}',
                          style: const TextStyle(color: WaveBookColors.muted, fontSize: 13),
                        ),
                      ],
                    ),
                  ),
                  Text(
                    '$symbol${bookingsAmount.toStringAsFixed(2)}',
                    style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w800, color: WaveBookColors.pink),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 12),
          _ReportCard(
            icon: Icons.payments_outlined,
            color: WaveBookColors.success,
            title: 'Deposits received',
            count: d['deposits_count'] as int,
            amount: depositsAmount,
            symbol: symbol,
          ),
          const SizedBox(height: 12),
          _ReportCard(
            icon: Icons.receipt_long_outlined,
            color: WaveBookColors.rose,
            title: 'Online orders',
            count: d['orders_count'] as int,
            amount: ordersAmount,
            symbol: symbol,
          ),
        ],
      ),
    );
  }
}

class _ReportCard extends StatelessWidget {
  final IconData icon;
  final Color color;
  final String title;
  final int count;
  final double amount;
  final String symbol;

  const _ReportCard({
    required this.icon,
    required this.color,
    required this.title,
    required this.count,
    required this.amount,
    required this.symbol,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          children: [
            CircleAvatar(
              backgroundColor: color.withValues(alpha: 0.15),
              child: Icon(icon, color: color),
            ),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title, style: const TextStyle(fontWeight: FontWeight.w700)),
                  const SizedBox(height: 2),
                  Text(
                    '$count ${count == 1 ? 'item' : 'items'}',
                    style: const TextStyle(color: WaveBookColors.muted, fontSize: 13),
                  ),
                ],
              ),
            ),
            Text(
              '$symbol${amount.toStringAsFixed(2)}',
              style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w800, color: WaveBookColors.pink),
            ),
          ],
        ),
      ),
    );
  }
}
