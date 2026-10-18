import 'dart:io' show Platform;

import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

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

  Future<void> _openSubscribePage() async {
    final opened = await launchUrl(
      Uri.parse('https://getwavebook.com/subscribe'),
      mode: LaunchMode.externalApplication,
    );
    if (mounted && !opened) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Could not open getwavebook.com/subscribe')),
      );
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
    final trial = info.status == 'trial';
    final expired = info.status == 'expired';
    final ios = Platform.isIOS;
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
                  active ? 'Subscription Active' : (expired ? 'Free Trial Ended' : 'Free Trial'),
                  style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w800),
                ),
                const SizedBox(height: 4),
                Text(
                  'WaveBook Premium · £${info.priceGbp.toStringAsFixed(2)}/month · all features included',
                  style: const TextStyle(color: WaveBookColors.muted),
                ),
                if (trial || expired) ...[
                  const SizedBox(height: 8),
                  Text(
                    info.trialDaysLeft > 0
                        ? '${info.trialDaysLeft} day${info.trialDaysLeft == 1 ? '' : 's'} left in your free trial'
                        : 'Your free trial has ended',
                    style: const TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.w700,
                      color: WaveBookColors.pink,
                    ),
                  ),
                ],
                if (!active) ...[
                  const SizedBox(height: 16),
                  Text(
                    ios
                        ? 'To manage your subscription status, visit getwavebook.com.'
                        : 'Choose a plan at getwavebook.com to keep using WaveBook. Your plan unlocks automatically in the app after you subscribe.',
                    textAlign: TextAlign.center,
                    style: const TextStyle(fontSize: 13, color: WaveBookColors.muted),
                  ),
                ],
              ],
            ),
          ),
        ),
        const SizedBox(height: 16),
        Card(
          child: ListTile(
            leading: const Icon(Icons.group_outlined, color: WaveBookColors.pink),
            title: const Text('Staff members', style: TextStyle(fontWeight: FontWeight.w700)),
            subtitle: Text(info.maxStaff > 0 ? 'Up to ${info.maxStaff} included' : 'Available on WaveBook Premium'),
          ),
        ),
        const SizedBox(height: 24),
        if (!active && !ios)
          ElevatedButton(
            onPressed: _openSubscribePage,
            child: const Text('Subscribe Now'),
          ),
      ],
    );
  }
}
