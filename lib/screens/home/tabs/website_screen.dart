import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../../api/api_client.dart';
import '../../../models/models.dart';
import '../../../theme.dart';

class WebsiteScreen extends StatefulWidget {
  const WebsiteScreen({super.key});

  @override
  State<WebsiteScreen> createState() => _WebsiteScreenState();
}

class _WebsiteScreenState extends State<WebsiteScreen> {
  final _api = ApiClient();
  Business? _business;
  String _themeColor = '#ec4899';
  bool _darkTheme = false;
  bool _loading = true;
  bool _saving = false;

  static const _themes = [
    ('Pink', '#ec4899'),
    ('Rose', '#be185d'),
    ('Red', '#ef4444'),
    ('Orange', '#f97316'),
    ('Amber', '#f59e0b'),
    ('Green', '#22c55e'),
    ('Teal', '#14b8a6'),
    ('Blue', '#3b82f6'),
    ('Indigo', '#6366f1'),
    ('Purple', '#a855f7'),
  ];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final data = await _api.get('/api/business');
      if (!mounted) return;
      final b = Business.fromJson(data as Map<String, dynamic>);
      setState(() {
        _business = b;
        _themeColor = b.themeColor;
        _darkTheme = b.darkTheme;
      });
    } on ApiException {
      // Non-fatal — the screen still renders.
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _save() async {
    setState(() => _saving = true);
    try {
      await _api.patch('/api/business', body: {
        'theme_color': _themeColor,
        'dark_theme': _darkTheme,
      });
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Website theme updated')),
        );
      }
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final slug = _business?.slug ?? 'your-business';
    return Scaffold(
      appBar: AppBar(title: const Text('Website')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                Card(
                  child: ListTile(
                    leading: const Icon(Icons.public, color: WaveBookColors.pink),
                    title: const Text('Your website', style: TextStyle(fontWeight: FontWeight.w700)),
                    subtitle: Text('$slug.wab.ad'),
                    trailing: const Icon(Icons.open_in_new),
                    onTap: () => _openWebsite(slug),
                  ),
                ),
                const SizedBox(height: 16),
                const Text(
                  'Theme colour',
                  style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800),
                ),
                const SizedBox(height: 4),
                const Text(
                  'This changes the look of your booking website, store and booking pages.',
                  style: TextStyle(color: WaveBookColors.muted, fontSize: 13),
                ),
                const SizedBox(height: 16),
                Wrap(
                  spacing: 16,
                  runSpacing: 16,
                  children: _themes.map((theme) {
                    final (label, color) = theme;
                    final selected = _themeColor.toLowerCase() == color;
                    return GestureDetector(
                      onTap: () => setState(() => _themeColor = color),
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Container(
                            width: 52,
                            height: 52,
                            decoration: BoxDecoration(
                              color: Color(int.parse('FF${color.substring(1)}', radix: 16)),
                              shape: BoxShape.circle,
                              border: selected
                                  ? Border.all(color: Colors.white, width: 3)
                                  : null,
                              boxShadow: selected
                                  ? [BoxShadow(color: Color(int.parse('FF${color.substring(1)}', radix: 16)).withValues(alpha: 0.5), blurRadius: 8)]
                                  : null,
                            ),
                            child: selected
                                ? const Icon(Icons.check, color: Colors.white)
                                : null,
                          ),
                          const SizedBox(height: 6),
                          Text(label, style: const TextStyle(fontSize: 12)),
                        ],
                      ),
                    );
                  }).toList(),
                ),
                const SizedBox(height: 24),
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('Dark theme', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
                  subtitle: const Text(
                    'Use a dark background on your booking website.',
                    style: TextStyle(color: WaveBookColors.muted, fontSize: 13),
                  ),
                  value: _darkTheme,
                  onChanged: (v) => setState(() => _darkTheme = v),
                ),
                const SizedBox(height: 16),
                ElevatedButton(
                  onPressed: _saving ? null : _save,
                  child: _saving
                      ? const SizedBox(
                          height: 20,
                          width: 20,
                          child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                        )
                      : const Text('Save Theme'),
                ),
              ],
            ),
    );
  }

  void _openWebsite(String slug) {
    launchUrl(
      Uri.parse('https://$slug.wab.ad'),
      mode: LaunchMode.externalApplication,
    );
  }
}
