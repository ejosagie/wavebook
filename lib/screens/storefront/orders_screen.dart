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
        _orders = (data as List)
            .map((o) => Order.fromJson(o as Map<String, dynamic>))
            .toList();
        _currency = currency;
      });
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _setStatus(
    Order order,
    String status, {
    String trackingNumber = '',
    String courierName = '',
    String deliveredAt = '',
  }) async {
    try {
      await _api.patch(
        '/api/orders/${order.id}',
        body: {
          'status': status,
          'tracking_number': trackingNumber,
          'courier_name': courierName,
          'delivered_at': deliveredAt,
        },
      );
      await _load();
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(_statusLabel(status))));
      }
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  Future<void> _markShipped(Order order) async {
    final courierCtrl = TextEditingController(text: order.courierName);
    final trackingCtrl = TextEditingController(text: order.trackingNumber);
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Mark as Shipped'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: courierCtrl,
              decoration: const InputDecoration(
                labelText: 'Courier name',
                hintText: 'e.g. Royal Mail, DPD',
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: trackingCtrl,
              decoration: const InputDecoration(labelText: 'Tracking number'),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Mark as Shipped'),
          ),
        ],
      ),
    );
    if (ok != true) return;
    final courier = courierCtrl.text.trim();
    final tracking = trackingCtrl.text.trim();
    if (courier.isEmpty || tracking.isEmpty) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Enter the courier name and tracking number'),
          ),
        );
      }
      return;
    }
    await _setStatus(
      order,
      'shipped',
      courierName: courier,
      trackingNumber: tracking,
    );
  }

  Future<void> _markDelivered(Order order) async {
    final now = DateTime.now();
    final initial = DateTime(now.year, now.month, now.day);
    final picked = await showDatePicker(
      context: context,
      initialDate: initial,
      firstDate: initial.subtract(const Duration(days: 30)),
      lastDate: initial,
      helpText: 'Delivery date',
    );
    if (picked == null) return;
    final date =
        '${picked.year.toString().padLeft(4, '0')}-${picked.month.toString().padLeft(2, '0')}-${picked.day.toString().padLeft(2, '0')}';
    await _setStatus(order, 'delivered', deliveredAt: date);
  }

  Future<void> _cancelOrder(Order order) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Cancel order?'),
        content: Text(
          'Order #${order.id} from ${order.customerName} will be cancelled.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Keep'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text(
              'Cancel Order',
              style: TextStyle(color: WaveBookColors.danger),
            ),
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
      case 'delivered':
        return 'Delivered';
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
      case 'delivered':
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
        child: Text(
          'No orders yet. When customers buy from your store, their orders appear here.',
        ),
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
                        padding: const EdgeInsets.symmetric(
                          horizontal: 8,
                          vertical: 4,
                        ),
                        decoration: BoxDecoration(
                          color: _statusColor(
                            order.status,
                          ).withValues(alpha: 0.15),
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
                    order.items
                        .map((i) => '${i.quantity} × ${i.name}')
                        .join('\n'),
                    style: const TextStyle(
                      color: WaveBookColors.muted,
                      fontSize: 13,
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    '${currencySymbol(_currency)}${order.total.toStringAsFixed(2)} · ${order.createdAt}',
                    style: const TextStyle(
                      fontWeight: FontWeight.w700,
                      fontSize: 13,
                    ),
                  ),
                  if (order.shippingFee > 0)
                    Text(
                      'Shipping: ${currencySymbol(_currency)}${order.shippingFee.toStringAsFixed(2)}',
                      style: const TextStyle(
                        color: WaveBookColors.muted,
                        fontSize: 13,
                      ),
                    ),
                  if (order.customerPhone.isNotEmpty)
                    Text(
                      'Call: ${order.customerPhone}',
                      style: const TextStyle(
                        color: WaveBookColors.muted,
                        fontSize: 13,
                      ),
                    ),
                  if (order.customerAddress.isNotEmpty ||
                      order.customerCity.isNotEmpty ||
                      order.customerPostcode.isNotEmpty ||
                      order.customerCountry.isNotEmpty) ...[
                    const SizedBox(height: 8),
                    const Text(
                      'Ship to:',
                      style: TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.w700,
                        color: WaveBookColors.muted,
                      ),
                    ),
                    Text(
                      [
                        if (order.customerAddress.isNotEmpty)
                          order.customerAddress,
                        if (order.customerCity.isNotEmpty) order.customerCity,
                        if (order.customerPostcode.isNotEmpty)
                          order.customerPostcode,
                        if (order.customerCountry.isNotEmpty)
                          order.customerCountry,
                      ].join(', '),
                      style: const TextStyle(
                        color: WaveBookColors.muted,
                        fontSize: 13,
                      ),
                    ),
                  ],
                  if (order.courierName.isNotEmpty ||
                      order.trackingNumber.isNotEmpty)
                    Text(
                      'Courier: ${order.courierName} · Tracking: ${order.trackingNumber}',
                      style: const TextStyle(
                        color: WaveBookColors.muted,
                        fontSize: 13,
                      ),
                    ),
                  if (order.deliveredAt.isNotEmpty)
                    Text(
                      'Delivered on: ${order.deliveredAt}',
                      style: const TextStyle(
                        color: WaveBookColors.muted,
                        fontSize: 13,
                      ),
                    ),
                  if (order.status == 'paid' ||
                      order.status == 'confirmed' ||
                      order.status == 'shipped')
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
                          icon: const Icon(
                            Icons.close,
                            color: WaveBookColors.danger,
                          ),
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
                            onPressed: () => _markShipped(order),
                            child: const Text('Mark as Shipped'),
                          ),
                        ),
                        const SizedBox(width: 8),
                        IconButton(
                          icon: const Icon(
                            Icons.close,
                            color: WaveBookColors.danger,
                          ),
                          tooltip: 'Cancel order',
                          onPressed: () => _cancelOrder(order),
                        ),
                      ],
                    ),
                  if (order.status == 'shipped')
                    Row(
                      children: [
                        Expanded(
                          child: ElevatedButton(
                            onPressed: () => _markDelivered(order),
                            child: const Text('Mark as Delivered'),
                          ),
                        ),
                        const SizedBox(width: 8),
                        IconButton(
                          icon: const Icon(
                            Icons.close,
                            color: WaveBookColors.danger,
                          ),
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
