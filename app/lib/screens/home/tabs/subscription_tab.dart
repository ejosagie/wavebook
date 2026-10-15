import 'package:flutter/material.dart';

import '../../../api/api_client.dart';
import '../../../models/models.dart';
import '../../../theme.dart';

class SubscriptionTab extends StatefulWidget {
  const SubscriptionTab({super.key});

  @override
  State<SubscriptionTab> createState() => _SubscriptionTabState();
}

class _SubscriptionTabState extends State<SubscriptionTab> {
  final _api = ApiClient();
  SubscriptionInfo? _info;
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
      final data = await _api.get('/api/subscription');
      if (!mounted) return;
      setState(() => _info = SubscriptionInfo.fromJson(data as Map<String, dynamic>));
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _startCheckout() async {
    try {
      final data = await _api.post('/api/subscription/checkout');
      final url = data['checkout_url'] as String?;
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              url != null
                  ? 'Opening checkout in your browser...'
                  : 'Could not start checkout.',
            ),
          ),
        );
      }
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Subscription')),
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
    final info = _info!;
    final active = info.status == 'active';
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Card(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              children: [
                Icon(
                  active ? Icons.workspace_premium : Icons.rocket_launch,
                  size: 56,
                  color: active ? WaveBookColors.pink : WaveBookColors.muted,
                ),
                const SizedBox(height: 12),
                Text(
                  active ? 'Subscription Active' : 'Free Trial',
                  style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w800),
                ),
                const SizedBox(height: 4),
                Text(
                  '£${info.priceGbp.toStringAsFixed(2)}/month · all features included',
                  style: const TextStyle(color: WaveBookColors.muted),
                ),
                const SizedBox(height: 16),
                const Text(
                  'Subscriptions are activated on the WaveBook website (getwavebook.com/subscribe) to comply with App Store policies. Premium features unlock automatically in the app after subscribing.',
                  textAlign: TextAlign.center,
                  style: TextStyle(fontSize: 13, color: WaveBookColors.muted),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 16),
        Card(
          child: ListTile(
            leading: const Icon(Icons.group_outlined, color: WaveBookColors.pink),
            title: const Text('Staff members', style: TextStyle(fontWeight: FontWeight.w700)),
            subtitle: Text('Up to ${info.maxStaff} included'),
          ),
        ),
        const SizedBox(height: 24),
        if (!active)
          ElevatedButton(
            onPressed: _startCheckout,
            child: const Text('Subscribe on Website'),
          ),
      ],
    );
  }
}
