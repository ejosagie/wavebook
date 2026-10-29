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
  String _themeStyle = 'rose';
  String _themeFont = 'default';
  bool _loading = true;
  bool _saving = false;

  // Acuity-style website presets: (label, key, accent, dark, font).
  static const _styles = [
    ('Rose', 'rose', '#ec4899', false, 'default'),
    ('Midnight', 'midnight', '#d4a017', true, 'georgia'),
    ('Ocean', 'ocean', '#0ea5e9', false, 'default'),
    ('Forest', 'forest', '#10b981', false, 'default'),
    ('Sunset', 'sunset', '#f97316', false, 'default'),
    ('Violet', 'violet', '#8b5cf6', true, 'default'),
    ('Mono', 'mono', '#111827', false, 'courier'),
  ];

  // Font choices: (key, label).
  static const _fonts = [
    ('default', 'Default (system)'),
    ('georgia', 'Georgia'),
    ('times', 'Times New Roman'),
    ('arial', 'Arial'),
    ('helvetica', 'Helvetica'),
    ('verdana', 'Verdana'),
    ('tahoma', 'Tahoma'),
    ('trebuchet', 'Trebuchet MS'),
    ('courier', 'Courier New'),
    ('palatino', 'Palatino'),
  ];

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
    ('Purple', '#8b5cf6'),
  ];

  // Font key -> Flutter font family (null = system default).
  static String? _fontFamily(String key) {
    switch (key) {
      case 'georgia':
        return 'Georgia';
      case 'times':
        return 'Times New Roman';
      case 'arial':
        return 'Arial';
      case 'helvetica':
        return 'Helvetica';
      case 'verdana':
        return 'Verdana';
      case 'tahoma':
        return 'Tahoma';
      case 'trebuchet':
        return 'Trebuchet MS';
      case 'courier':
        return 'Courier New';
      case 'palatino':
        return 'Palatino';
      default:
        return null;
    }
  }

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
        _themeStyle = b.themeStyle;
        _themeFont = b.themeFont;
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
        'theme_style': _themeStyle,
        'theme_font': _themeFont,
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
                const SizedBox(height: 24),
                const Text(
                  'Website style',
                  style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800),
                ),
                const SizedBox(height: 4),
                const Text(
                  'Pick a ready-made style, or use a custom colour below.',
                  style: TextStyle(color: WaveBookColors.muted, fontSize: 13),
                ),
                const SizedBox(height: 16),
                Wrap(
                  spacing: 12,
                  runSpacing: 12,
                  children: _styles.map((style) {
                    final (label, key, accent, dark, font) = style;
                    final selected = _themeStyle == key;
                    final accentColor = Color(int.parse('FF${accent.substring(1)}', radix: 16));
                    return GestureDetector(
                      onTap: () => setState(() {
                        _themeStyle = key;
                        _themeColor = accent;
                        _darkTheme = dark;
                        _themeFont = font;
                      }),
                      child: Container(
                        width: 118,
                        decoration: BoxDecoration(
                          color: dark ? const Color(0xFF14141D) : Colors.white,
                          borderRadius: BorderRadius.circular(14),
                          border: Border.all(
                            color: selected ? accentColor : const Color(0xFFE5E0E8),
                            width: selected ? 2.5 : 1,
                          ),
                          boxShadow: selected
                              ? [BoxShadow(color: accentColor.withValues(alpha: 0.25), blurRadius: 10)]
                              : null,
                        ),
                        clipBehavior: Clip.antiAlias,
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            Container(
                              height: 46,
                              color: dark ? const Color(0xFF1E1E28) : const Color(0xFFF7F5F9),
                              alignment: Alignment.center,
                              child: Text(
                                'Aa',
                                style: TextStyle(
                                  fontSize: 20,
                                  fontWeight: FontWeight.w700,
                                  color: accentColor,
                                  fontFamily: _fontFamily(font),
                                ),
                              ),
                            ),
                            Padding(
                              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                              child: Row(
                                children: [
                                  Container(
                                    width: 10,
                                    height: 10,
                                    decoration: BoxDecoration(
                                      color: accentColor,
                                      shape: BoxShape.circle,
                                    ),
                                  ),
                                  const SizedBox(width: 6),
                                  Expanded(
                                    child: Text(
                                      label,
                                      style: TextStyle(
                                        fontSize: 12,
                                        fontWeight: FontWeight.w700,
                                        color: dark ? Colors.white : Colors.black87,
                                      ),
                                    ),
                                  ),
                                  if (selected)
                                    Icon(Icons.check_circle, color: accentColor, size: 16),
                                ],
                              ),
                            ),
                          ],
                        ),
                      ),
                    );
                  }).toList(),
                ),
                const SizedBox(height: 24),
                const Text(
                  'Custom colour',
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
                      onTap: () => setState(() {
                        _themeColor = color;
                        _themeStyle = 'custom';
                      }),
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
                const Text(
                  'Font',
                  style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800),
                ),
                const SizedBox(height: 4),
                const Text(
                  'Choose the font used across your booking website and store.',
                  style: TextStyle(color: WaveBookColors.muted, fontSize: 13),
                ),
                const SizedBox(height: 12),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: _fonts.map((font) {
                    final (key, label) = font;
                    final selected = _themeFont == key;
                    return ChoiceChip(
                      label: Text(
                        label,
                        style: TextStyle(fontSize: 12, fontFamily: _fontFamily(key)),
                      ),
                      selected: selected,
                      onSelected: (_) => setState(() {
                        _themeFont = key;
                        _themeStyle = 'custom';
                      }),
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
                  onChanged: (v) => setState(() {
                    _darkTheme = v;
                    _themeStyle = 'custom';
                  }),
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
