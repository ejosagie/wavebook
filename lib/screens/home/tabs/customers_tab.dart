import 'package:flutter/material.dart';

import '../../../api/api_client.dart';
import '../../../models/models.dart';
import '../../../theme.dart';

class CustomersTab extends StatefulWidget {
  const CustomersTab({super.key});

  @override
  State<CustomersTab> createState() => _CustomersTabState();
}

class _CustomersTabState extends State<CustomersTab> {
  final _api = ApiClient();
  List<Customer> _customers = [];
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
      final data = await _api.get('/api/customers');
      if (!mounted) return;
      setState(() {
        _customers = (data as List)
            .map((c) => Customer.fromJson(c as Map<String, dynamic>))
            .toList();
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
      appBar: AppBar(title: const Text('Customers')),
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
    if (_customers.isEmpty) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(32),
          child: Text(
            'Customers appear here automatically when they book.',
            textAlign: TextAlign.center,
            style: TextStyle(color: WaveBookColors.muted),
          ),
        ),
      );
    }
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView.builder(
        padding: const EdgeInsets.all(16),
        itemCount: _customers.length + 1,
        itemBuilder: (context, i) {
          if (i == 0) {
            final totalBookings = _customers.fold<int>(0, (sum, c) => sum + c.bookingCount);
            return Card(
              margin: const EdgeInsets.only(bottom: 12),
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Row(
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            '${_customers.length}',
                            style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w800, color: WaveBookColors.pink),
                          ),
                          const Text('Total customers', style: TextStyle(color: WaveBookColors.muted, fontSize: 12)),
                        ],
                      ),
                    ),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            '$totalBookings',
                            style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w800, color: WaveBookColors.rose),
                          ),
                          const Text('Total bookings', style: TextStyle(color: WaveBookColors.muted, fontSize: 12)),
                        ],
                      ),
                    ),
                    const Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'Auto',
                            style: TextStyle(fontSize: 24, fontWeight: FontWeight.w800, color: WaveBookColors.success),
                          ),
                          Text('Saved from bookings', style: TextStyle(color: WaveBookColors.muted, fontSize: 12)),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            );
          }
          final c = _customers[i - 1];
          return Card(
            margin: const EdgeInsets.only(bottom: 12),
            child: ListTile(
              leading: CircleAvatar(
                backgroundColor: WaveBookColors.rose.withValues(alpha: 0.15),
                child: const Icon(Icons.person, color: WaveBookColors.rose),
              ),
              title: Text(c.name, style: const TextStyle(fontWeight: FontWeight.w700)),
              subtitle: Text(
                '${c.email}\n${c.phone}',
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
              trailing: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Text(
                    '${c.bookingCount}',
                    style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w800, color: WaveBookColors.pink),
                  ),
                  const Text('bookings', style: TextStyle(fontSize: 11, color: WaveBookColors.muted)),
                ],
              ),
            ),
          );
        },
      ),
    );
  }
}
