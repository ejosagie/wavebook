import 'package:flutter/material.dart';

import '../../api/api_client.dart';
import '../../models/models.dart';
import '../../theme.dart';

class OrdersScreen extends StatefulWidget {
  const OrdersScreen({super.key});

  @override
  State<OrdersScreen> createState() => _OrdersScreenState();
}

class _OrdersScreenState extends State<OrdersScreen> {
  final _api = ApiClient();
  List<Order> _orders = [];
  String _currency = 'GBP';
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
      final data = await _api.get('/api/orders');
      String currency = 'GBP';
      try {
        final biz = await _api.get('/api/business') as Map<String, dynamic>;
        currency = biz['currency']?.toString() ?? 'GBP';
      } catch (_) {
        // Currency is a display nicety; fall back to GBP.
      }
      if (!mounted) return;
      setState(() {
        _orders = (data as List).map((o) => Order.fromJson(o as Map<String, dynamic>)).toList();
        _currency = currency;
      });
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _setStatus(Order order, String status) async {
    try {
      await _api.patch('/api/orders/${order.id}', body: {'status': status});
      await _load();
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  Future<void> _cancelOrder(Order order) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Cancel order?'),
        content: Text('Order #${order.id} from ${order.customerName} will be cancelled.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Keep')),
          TextButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Cancel Order', style: TextStyle(color: WaveBookColors.danger)),
          ),
        ],
      ),
    );
    if (ok == true) await _setStatus(order, 'cancelled');
  }

  String _statusLabel(String status) {
    switch (status) {
      case 'pending':
        return 'Awaiting payment';
      case 'paid':
        return 'Paid — needs confirmation';
      case 'confirmed':
        return 'Confirmed — packing';
      case 'shipped':
        return 'Shipped';
      case 'cancelled':
        return 'Cancelled';
      default:
        return status;
    }
  }

  Color _statusColor(String status) {
    switch (status) {
      case 'paid':
        return WaveBookColors.pink;
      case 'confirmed':
        return Colors.orange;
      case 'shipped':
        return Colors.green;
      case 'cancelled':
        return WaveBookColors.danger;
      default:
        return WaveBookColors.muted;
    }
  }

  @override
  Widget build(BuildContext context) {
    return _buildBody();
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
    if (_orders.isEmpty) {
      return const Center(
        child: Text('No orders yet. When customers buy from your store, their orders appear here.'),
      );
    }
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView.builder(
        padding: const EdgeInsets.all(16),
        itemCount: _orders.length,
        itemBuilder: (context, index) {
          final order = _orders[index];
          return Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          'Order #${order.id} · ${order.customerName}',
                          style: const TextStyle(fontWeight: FontWeight.w800),
                        ),
                      ),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                        decoration: BoxDecoration(
                          color: _statusColor(order.status).withValues(alpha: 0.15),
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: Text(
                          _statusLabel(order.status),
                          style: TextStyle(
                            fontSize: 12,
                            fontWeight: FontWeight.w700,
                            color: _statusColor(order.status),
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Text(
                    order.items.map((i) => '${i.quantity} × ${i.name}').join('\n'),
                    style: const TextStyle(color: WaveBookColors.muted, fontSize: 13),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    '${currencySymbol(_currency)}${order.total.toStringAsFixed(2)} · ${order.createdAt}',
                    style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13),
                  ),
                  if (order.customerPhone.isNotEmpty)
                    Text(
                      'Call: ${order.customerPhone}',
                      style: const TextStyle(color: WaveBookColors.muted, fontSize: 13),
                    ),
                  if (order.status == 'paid' || order.status == 'confirmed')
                    const SizedBox(height: 12),
                  if (order.status == 'paid')
                    Row(
                      children: [
                        Expanded(
                          child: ElevatedButton(
                            onPressed: () => _setStatus(order, 'confirmed'),
                            child: const Text('Confirm Order'),
                          ),
                        ),
                        const SizedBox(width: 8),
                        IconButton(
                          icon: const Icon(Icons.close, color: WaveBookColors.danger),
                          tooltip: 'Cancel order',
                          onPressed: () => _cancelOrder(order),
                        ),
                      ],
                    ),
                  if (order.status == 'confirmed')
                    Row(
                      children: [
                        Expanded(
                          child: ElevatedButton(
                            onPressed: () => _setStatus(order, 'shipped'),
                            child: const Text('Mark as Shipped'),
                          ),
                        ),
                        const SizedBox(width: 8),
                        IconButton(
                          icon: const Icon(Icons.close, color: WaveBookColors.danger),
                          tooltip: 'Cancel order',
                          onPressed: () => _cancelOrder(order),
                        ),
                      ],
                    ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }
}
