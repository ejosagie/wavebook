import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../../../api/api_client.dart';
import '../../../models/models.dart';
import '../../../theme.dart';

class SettingsTab extends StatefulWidget {
  const SettingsTab({super.key});

  @override
  State<SettingsTab> createState() => _SettingsTabState();
}

class _SettingsTabState extends State<SettingsTab> {
  final _api = ApiClient();
  Business? _business;
  bool _loading = true;
  bool _saving = false;
  String? _error;

  final _name = TextEditingController();
  final _tagline = TextEditingController();
  final _about = TextEditingController();
  final _rules = TextEditingController();
  final _phone = TextEditingController();
  final _email = TextEditingController();
  final _address = TextEditingController();
  final _instagram = TextEditingController();
  final _facebook = TextEditingController();
  final _tiktok = TextEditingController();
  final _hours = TextEditingController();
  final _deposit = TextEditingController();
  final _buffer = TextEditingController();

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _name.dispose();
    _tagline.dispose();
    _about.dispose();
    _rules.dispose();
    _phone.dispose();
    _email.dispose();
    _address.dispose();
    _instagram.dispose();
    _facebook.dispose();
    _tiktok.dispose();
    _hours.dispose();
    _deposit.dispose();
    _buffer.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final data = await _api.get('/api/business');
      if (!mounted) return;
      final b = Business.fromJson(data as Map<String, dynamic>);
      setState(() {
        _business = b;
        _name.text = b.name;
        _tagline.text = b.tagline;
        _about.text = b.aboutText;
        _rules.text = b.rules;
        _phone.text = b.contactPhone;
        _email.text = b.contactEmail;
        _address.text = b.address;
        _instagram.text = b.instagram;
        _facebook.text = b.facebook;
        _tiktok.text = b.tiktok;
        _hours.text = b.openingHours;
        _deposit.text = b.depositAmount.toStringAsFixed(2);
        _buffer.text = b.bufferMinutes.toString();
      });
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _save() async {
    setState(() => _saving = true);
    try {
      await _api.patch('/api/business', body: {
        'name': _name.text.trim(),
        'tagline': _tagline.text.trim(),
        'about_text': _about.text.trim(),
        'rules': _rules.text.trim(),
        'contact_phone': _phone.text.trim(),
        'contact_email': _email.text.trim(),
        'address': _address.text.trim(),
        'instagram': _instagram.text.trim(),
        'facebook': _facebook.text.trim(),
        'tiktok': _tiktok.text.trim(),
        'opening_hours': _hours.text.trim(),
        'deposit_amount': double.tryParse(_deposit.text) ?? 20.0,
        'buffer_minutes': int.tryParse(_buffer.text) ?? 30,
      });
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Settings saved')),
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

  Future<void> _uploadLogo() async {
    final picker = ImagePicker();
    final file = await picker.pickImage(source: ImageSource.gallery, maxWidth: 800);
    if (file == null) return;
    try {
      await _api.upload('/api/business/logo', file.path, 'file');
      await _load();
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  Future<void> _uploadAboutImage() async {
    final picker = ImagePicker();
    final file = await picker.pickImage(source: ImageSource.gallery, maxWidth: 800);
    if (file == null) return;
    try {
      await _api.upload('/api/business/about-image', file.path, 'file');
      await _load();
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Settings'),
        actions: [
          if (_business != null)
            TextButton(
              onPressed: _saving ? null : _save,
              child: _saving
                  ? const SizedBox(
                      height: 18,
                      width: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Text('Save', style: TextStyle(fontWeight: FontWeight.w700)),
            ),
        ],
      ),
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
    final b = _business!;
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        const Text('Branding', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
        const SizedBox(height: 12),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              children: [
                Row(
                  children: [
                    if (b.logoPath.isNotEmpty)
                      ClipRRect(
                        borderRadius: BorderRadius.circular(10),
                        child: Image.network(
                          '${kApiBaseUrl}${b.logoPath}',
                          height: 56,
                          errorBuilder: (_, __, ___) => const Icon(Icons.image, size: 56),
                        ),
                      )
                    else
                      const Icon(Icons.image_outlined, size: 56, color: WaveBookColors.muted),
                    const SizedBox(width: 16),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text('Logo', style: TextStyle(fontWeight: FontWeight.w700)),
                          const SizedBox(height: 4),
                          OutlinedButton(
                            style: OutlinedButton.styleFrom(minimumSize: const Size(0, 40)),
                            onPressed: _uploadLogo,
                            child: const Text('Upload Logo'),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
                const Divider(height: 32),
                Row(
                  children: [
                    if (b.aboutImage.isNotEmpty)
                      ClipRRect(
                        borderRadius: BorderRadius.circular(10),
                        child: Image.network(
                          '${kApiBaseUrl}${b.aboutImage}',
                          height: 56,
                          errorBuilder: (_, __, ___) => const Icon(Icons.image, size: 56),
                        ),
                      )
                    else
                      const Icon(Icons.image_outlined, size: 56, color: WaveBookColors.muted),
                    const SizedBox(width: 16),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text('Welcome Image', style: TextStyle(fontWeight: FontWeight.w700)),
                          const SizedBox(height: 4),
                          OutlinedButton(
                            style: OutlinedButton.styleFrom(minimumSize: const Size(0, 40)),
                            onPressed: _uploadAboutImage,
                            child: const Text('Upload Image'),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 24),
        const Text('Business Info', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
        const SizedBox(height: 12),
        TextFormField(controller: _name, decoration: const InputDecoration(labelText: 'Business Name')),
        const SizedBox(height: 12),
        TextFormField(controller: _tagline, decoration: const InputDecoration(labelText: 'Tagline')),
        const SizedBox(height: 12),
        TextFormField(
          controller: _about,
          decoration: const InputDecoration(labelText: 'About Text'),
          maxLines: 4,
        ),
        const SizedBox(height: 12),
        TextFormField(
          controller: _rules,
          decoration: const InputDecoration(labelText: 'House Rules'),
          maxLines: 4,
        ),
        const SizedBox(height: 24),
        const Text('Contact', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
        const SizedBox(height: 12),
        TextFormField(controller: _phone, decoration: const InputDecoration(labelText: 'Phone')),
        const SizedBox(height: 12),
        TextFormField(controller: _email, decoration: const InputDecoration(labelText: 'Email')),
        const SizedBox(height: 12),
        TextFormField(
          controller: _address,
          decoration: const InputDecoration(labelText: 'Address'),
          maxLines: 2,
        ),
        const SizedBox(height: 24),
        const Text('Social Links', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
        const SizedBox(height: 12),
        TextFormField(controller: _instagram, decoration: const InputDecoration(labelText: 'Instagram URL')),
        const SizedBox(height: 12),
        TextFormField(controller: _facebook, decoration: const InputDecoration(labelText: 'Facebook URL')),
        const SizedBox(height: 12),
        TextFormField(controller: _tiktok, decoration: const InputDecoration(labelText: 'TikTok URL')),
        const SizedBox(height: 24),
        const Text('Booking Settings', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
        const SizedBox(height: 12),
        TextFormField(
          controller: _hours,
          decoration: const InputDecoration(labelText: 'Opening Hours'),
          maxLines: 3,
        ),
        const SizedBox(height: 12),
        Row(
          children: [
            Expanded(
              child: TextFormField(
                controller: _deposit,
                keyboardType: const TextInputType.numberWithOptions(decimal: true),
                decoration: const InputDecoration(labelText: 'Deposit (£)'),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: TextFormField(
                controller: _buffer,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(labelText: 'Buffer (min)'),
              ),
            ),
          ],
        ),
        const SizedBox(height: 24),
        ElevatedButton(
          onPressed: _saving ? null : _save,
          child: _saving
              ? const SizedBox(
                  height: 22,
                  width: 22,
                  child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                )
              : const Text('Save Settings'),
        ),
      ],
    );
  }
}
