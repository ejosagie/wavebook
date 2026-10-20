import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:qr_flutter/qr_flutter.dart';
import 'package:share_plus/share_plus.dart';

import '../../api/api_client.dart';
import '../../models/models.dart';
import '../../theme.dart';
import 'orders_screen.dart';
import 'products_screen.dart';

class ShopScreen extends StatefulWidget {
  const ShopScreen({super.key, this.initialTab = 0});

  /// Which tab to open on first: 0 = Shop Settings, 1 = Products, 2 = Orders.
  final int initialTab;

  @override
  State<ShopScreen> createState() => _ShopScreenState();
}

class _ShopScreenState extends State<ShopScreen> {
  final _api = ApiClient();
  final _name = TextEditingController();
  final _slug = TextEditingController();
  final _phone = TextEditingController();
  final _email = TextEditingController();
  bool _storefrontEnabled = false;
  bool _loading = true;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _name.dispose();
    _slug.dispose();
    _phone.dispose();
    _email.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final data = await _api.get('/api/business');
      if (!mounted) return;
      final b = Business.fromJson(data as Map<String, dynamic>);
      setState(() {
        _name.text = b.name;
        _slug.text = b.slug;
        _phone.text = b.contactPhone;
        _email.text = b.contactEmail;
        _storefrontEnabled = b.storefrontEnabled;
      });
    } on ApiException {
      // Non-fatal — the tabs still work without the settings card.
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _save() async {
    setState(() => _saving = true);
    try {
      await _api.patch('/api/business', body: {
        'name': _name.text.trim(),
        'contact_phone': _phone.text.trim(),
        'contact_email': _email.text.trim(),
        'storefront_enabled': _storefrontEnabled,
      });
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Shop settings saved')),
        );
      }
      await _load();
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  void _showStoreQr(String slug) {
    final storeUrl = '$kApiBaseUrl/t/$slug/store';
    showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Your Store QR Code'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(12),
              ),
              child: QrImageView(data: storeUrl, size: 200),
            ),
            const SizedBox(height: 12),
            Text(
              storeUrl,
              textAlign: TextAlign.center,
              style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: 4),
            const Text(
              'Customers scan this to open your online store.',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 12, color: WaveBookColors.muted),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Close'),
          ),
          TextButton.icon(
            icon: const Icon(Icons.copy, size: 18),
            label: const Text('Copy link'),
            onPressed: () {
              Clipboard.setData(ClipboardData(text: storeUrl));
              Navigator.pop(ctx);
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text('Store link copied')),
              );
            },
          ),
          FilledButton.icon(
            icon: const Icon(Icons.share, size: 18),
            label: const Text('Share'),
            onPressed: () {
              Navigator.pop(ctx);
              Share.share(storeUrl);
            },
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 3,
      initialIndex: widget.initialTab,
      child: Scaffold(
        appBar: AppBar(
          title: const Text('Online Shop'),
          bottom: const TabBar(
            tabs: [
              Tab(icon: Icon(Icons.settings_outlined), text: 'Shop Settings'),
              Tab(icon: Icon(Icons.inventory_2_outlined), text: 'Products'),
              Tab(icon: Icon(Icons.receipt_long_outlined), text: 'Orders'),
            ],
          ),
        ),
        body: TabBarView(
          children: [
            _loading
                ? const Center(child: CircularProgressIndicator())
                : ListView(children: [_buildSettingsCard()]),
            const ProductsScreen(),
            const OrdersScreen(),
          ],
        ),
      ),
    );
  }

  Widget _buildSettingsCard() {
    final slug = _slug.text.trim().isEmpty ? 'your-business' : _slug.text.trim();
    return Card(
      margin: const EdgeInsets.fromLTRB(16, 16, 16, 8),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Shop Settings',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _name,
              decoration: const InputDecoration(labelText: 'Business name'),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _slug,
              readOnly: true,
              decoration: const InputDecoration(
                labelText: 'Website address',
                helperText: 'Chosen during set-up and cannot be changed',
              ),
            ),
            const SizedBox(height: 4),
            Text(
              '$slug.wab.is',
              style: const TextStyle(
                fontSize: 14,
                fontWeight: FontWeight.w700,
                color: WaveBookColors.pink,
              ),
            ),
            const SizedBox(height: 8),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              value: _storefrontEnabled,
              onChanged: (v) => setState(() => _storefrontEnabled = v),
              title: const Text('Sell products on your website', style: TextStyle(fontWeight: FontWeight.w700)),
              subtitle: Text(
                _storefrontEnabled
                    ? 'Your shop is live — customers can buy from $slug.wab.is'
                    : 'Your shop is hidden until you turn it on',
              ),
            ),
            if (_storefrontEnabled) ...[
              const SizedBox(height: 4),
              OutlinedButton.icon(
                icon: const Icon(Icons.qr_code_2),
                label: const Text('Show QR code'),
                onPressed: () => _showStoreQr(slug),
              ),
            ],
            const SizedBox(height: 4),
            Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _phone,
                    keyboardType: TextInputType.phone,
                    decoration: const InputDecoration(labelText: 'Phone number'),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: TextField(
                    controller: _email,
                    keyboardType: TextInputType.emailAddress,
                    decoration: const InputDecoration(labelText: 'Contact email'),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Align(
              alignment: Alignment.centerRight,
              child: ElevatedButton(
                onPressed: _saving ? null : _save,
                child: _saving
                    ? const SizedBox(
                        height: 20,
                        width: 20,
                        child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                      )
                    : const Text('Save'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
