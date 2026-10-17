import 'package:flutter/material.dart';

import '../../api/api_client.dart';
import '../../models/models.dart';
import '../../theme.dart';
import 'orders_screen.dart';
import 'products_screen.dart';

class ShopScreen extends StatefulWidget {
  const ShopScreen({super.key});

  @override
  State<ShopScreen> createState() => _ShopScreenState();
}

class _ShopScreenState extends State<ShopScreen> {
  final _api = ApiClient();
  Business? _business;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final data = await _api.get('/api/business');
      if (!mounted) return;
      setState(() {
        _business = Business.fromJson(data as Map<String, dynamic>);
      });
    } on ApiException {
      // Non-fatal — the shop screens still work without the banner.
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final enabled = _business?.storefrontEnabled ?? false;
    return Scaffold(
      appBar: AppBar(title: const Text('Online Shop')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          if (!_loading)
            Card(
              color: enabled ? null : WaveBookColors.darkSurfaceAlt,
              child: ListTile(
                leading: Icon(
                  enabled ? Icons.storefront : Icons.storefront_outlined,
                  color: enabled ? WaveBookColors.pink : WaveBookColors.muted,
                ),
                title: Text(
                  enabled ? 'Your shop is live' : 'Your shop is hidden',
                  style: const TextStyle(fontWeight: FontWeight.w700),
                ),
                subtitle: Text(
                  enabled
                      ? 'Customers can buy from your booking website.'
                      : 'Turn on the storefront in Settings to start selling.',
                ),
                trailing: const Icon(Icons.chevron_right),
                onTap: () => _openSettings(),
              ),
            ),
          const SizedBox(height: 12),
          _ShopCard(
            icon: Icons.inventory_2_outlined,
            color: WaveBookColors.pink,
            title: 'Inventory',
            subtitle: 'Add, edit and organise the items you sell',
            onTap: () => _push(const ProductsScreen()),
          ),
          const SizedBox(height: 12),
          _ShopCard(
            icon: Icons.receipt_long_outlined,
            color: WaveBookColors.rose,
            title: 'Orders',
            subtitle: 'See new orders, confirm them and mark as shipped',
            onTap: () => _push(const OrdersScreen()),
          ),
          const SizedBox(height: 16),
          const Text(
            'Customers buy without registering — they just add items to the basket and pay by card. You get paid for each sale and arrange delivery or collection.',
            style: TextStyle(color: WaveBookColors.muted, fontSize: 13),
          ),
        ],
      ),
    );
  }

  void _push(Widget screen) {
    Navigator.of(context).push(MaterialPageRoute(builder: (_) => screen));
  }

  void _openSettings() {
    Navigator.of(context).pop();
  }
}

class _ShopCard extends StatelessWidget {
  final IconData icon;
  final Color color;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  const _ShopCard({
    required this.icon,
    required this.color,
    required this.title,
    required this.subtitle,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor: color.withValues(alpha: 0.15),
          child: Icon(icon, color: color),
        ),
        title: Text(title, style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 18)),
        subtitle: Text(subtitle),
        trailing: const Icon(Icons.chevron_right),
        onTap: onTap,
      ),
    );
  }
}
