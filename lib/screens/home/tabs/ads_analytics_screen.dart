import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../api/api_client.dart';
import '../../../theme.dart';

/// Ads & Analytics: tracking links to paste into ad campaigns plus visit and
/// booking stats, mirroring the browser portal's Ads & Analytics tab.
class AdsAnalyticsScreen extends StatefulWidget {
  const AdsAnalyticsScreen({super.key});

  @override
  State<AdsAnalyticsScreen> createState() => _AdsAnalyticsScreenState();
}

class _AdsAnalyticsScreenState extends State<AdsAnalyticsScreen> {
  final _api = ApiClient();
  String _range = '7d';
  List<Map<String, dynamic>> _links = [];
  Map<String, dynamic>? _data;
  bool _loading = true;
  String? _error;

  static const _ranges = [
    ('7d', '7 days'),
    ('14d', '14 days'),
    ('30d', '30 days'),
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
      final links = await _api.get('/api/ads/links') as List;
      final data = await _api.get('/api/ads/analytics?range=$_range');
      if (!mounted) return;
      setState(() {
        _links = links.map((l) => (l as Map).cast<String, dynamic>()).toList();
        _data = data as Map<String, dynamic>;
      });
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _copy(String text, String label) async {
    await Clipboard.setData(ClipboardData(text: text));
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('$label link copied')),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Ads & Analytics')),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
            child: Row(
              children: _ranges.map((r) {
                final (value, label) = r;
                return Padding(
                  padding: const EdgeInsets.only(right: 8),
                  child: ChoiceChip(
                    label: Text(label),
                    selected: _range == value,
                    onSelected: (_) {
                      setState(() => _range = value);
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
    final visits = d['ad_visits'] as int? ?? 0;
    final bookings = d['ad_bookings'] as int? ?? 0;
    final conversion = (d['conversion'] as num?)?.toDouble() ?? 0;
    final bySource = (d['by_source'] as List? ?? []).cast<Map<String, dynamic>>();
    final recent = (d['recent'] as List? ?? []).cast<Map<String, dynamic>>();
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          const Text('Tracking links', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
          const SizedBox(height: 4),
          const Text(
            'Copy a link for each platform you advertise on and paste it into your ad campaign\'s URL field.',
            style: TextStyle(color: WaveBookColors.muted),
          ),
          const SizedBox(height: 12),
          ..._links.map((l) => Card(
                margin: const EdgeInsets.only(bottom: 8),
                child: ListTile(
                  leading: CircleAvatar(
                    backgroundColor: WaveBookColors.pink.withValues(alpha: 0.15),
                    child: const Icon(Icons.link, color: WaveBookColors.pink),
                  ),
                  title: Text(l['label'] ?? l['key'] ?? '', style: const TextStyle(fontWeight: FontWeight.w700)),
                  subtitle: Text(l['url'] ?? '', maxLines: 1, overflow: TextOverflow.ellipsis),
                  trailing: IconButton(
                    icon: const Icon(Icons.copy, color: WaveBookColors.pink),
                    tooltip: 'Copy link',
                    onPressed: () => _copy(l['url'] ?? '', l['label'] ?? l['key'] ?? ''),
                  ),
                ),
              )),
          const SizedBox(height: 16),
          const Text('Performance', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: _StatCard(label: 'Visits', value: '$visits', color: WaveBookColors.pink),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: _StatCard(label: 'Bookings', value: '$bookings', color: WaveBookColors.rose),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: _StatCard(label: 'Conversion', value: '${conversion.toStringAsFixed(1)}%', color: WaveBookColors.success),
              ),
            ],
          ),
          const SizedBox(height: 16),
          const Text('Visits by platform', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
          const SizedBox(height: 8),
          if (bySource.isEmpty)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 8),
              child: Text('No ad visits in this period yet.', style: TextStyle(color: WaveBookColors.muted)),
            )
          else
            Card(
              child: Column(
                children: bySource.map((s) {
                  final key = s['source']?.toString() ?? '';
                  final label = _platformLabel(key);
                  return ListTile(
                    dense: true,
                    title: Text(label),
                    trailing: Text(
                      '${s['c']}',
                      style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w800, color: WaveBookColors.pink),
                    ),
                  );
                }).toList(),
              ),
            ),
          const SizedBox(height: 16),
          const Text('Recent visits', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
          const SizedBox(height: 8),
          if (recent.isEmpty)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 8),
              child: Text('No visits recorded yet.', style: TextStyle(color: WaveBookColors.muted)),
            )
          else
            Card(
              child: Column(
                children: recent.map((v) {
                  final key = v['source']?.toString() ?? '';
                  return ListTile(
                    dense: true,
                    leading: const Icon(Icons.ads_click, size: 20, color: WaveBookColors.rose),
                    title: Text(_platformLabel(key)),
                    subtitle: Text('${v['visited_at']} · ${v['page']}'),
                  );
                }).toList(),
              ),
            ),
        ],
      ),
    );
  }

  String _platformLabel(String key) {
    for (final l in _links) {
      if (l['key'] == key) return l['label'] as String;
    }
    return key.isEmpty ? 'Direct' : key;
  }
}

class _StatCard extends StatelessWidget {
  final String label;
  final String value;
  final Color color;

  const _StatCard({required this.label, required this.value, required this.color});

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: EdgeInsets.zero,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 8),
        child: Column(
          children: [
            Text(value, style: TextStyle(fontSize: 20, fontWeight: FontWeight.w800, color: color)),
            const SizedBox(height: 2),
            Text(label, style: const TextStyle(fontSize: 12, color: WaveBookColors.muted)),
          ],
        ),
      ),
    );
  }
}
