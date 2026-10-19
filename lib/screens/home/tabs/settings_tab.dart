import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../../api/api_client.dart';
import '../../../models/models.dart';
import '../../../theme.dart';
import '../../../services/notification_service.dart';
import '../../../widgets/loading_network_image.dart';
import '../../storefront/products_screen.dart';

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
  final _smsInstructions = TextEditingController();
  final _payoutBankName = TextEditingController();
  final _payoutAccountName = TextEditingController();
  final _payoutAccountNumber = TextEditingController();
  final _payoutSortCode = TextEditingController();
  bool _storefrontEnabled = false;
  SmsBalance? _smsBalance;
  bool _bookingSound = true;

  @override
  void initState() {
    super.initState();
    _load();
    isBookingSoundEnabled().then((v) {
      if (mounted) setState(() => _bookingSound = v);
    });
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
    _smsInstructions.dispose();
    _payoutBankName.dispose();
    _payoutAccountName.dispose();
    _payoutAccountNumber.dispose();
    _payoutSortCode.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final data = await _api.get('/api/business');
      final smsData = await _api.get('/api/notifications/sms-balance');
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
        _smsInstructions.text = b.smsInstructions;
        _storefrontEnabled = b.storefrontEnabled;
        _payoutBankName.text = b.payoutBankName;
        _payoutAccountName.text = b.payoutAccountName;
        _payoutAccountNumber.text = b.payoutAccountNumber;
        _payoutSortCode.text = b.payoutSortCode;
        _smsBalance = SmsBalance.fromJson(smsData as Map<String, dynamic>);
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
        'sms_instructions': _smsInstructions.text.trim(),
        'storefront_enabled': _storefrontEnabled,
        'payout_bank_name': _payoutBankName.text.trim(),
        'payout_account_name': _payoutAccountName.text.trim(),
        'payout_account_number': _payoutAccountNumber.text.trim(),
        'payout_sort_code': _payoutSortCode.text.trim(),
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

  Future<void> _buySmsCredits() async {
    try {
      final data = await _api.post('/api/payments/sms/topup');
      final url = data['payment_link'] as String?;
      if (url != null) {
        final opened = await launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication);
        if (mounted && !opened) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Could not open the payment page.')),
          );
        }
      } else if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Could not start checkout.')),
        );
      }
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  Future<void> _openProducts() async {
    await Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => const ProductsScreen()),
    );
    _load();
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
                        child: LoadingNetworkImage(
                          url: '$kApiBaseUrl${b.logoPath}',
                          height: 56,
                          iconSize: 56,
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
                        child: LoadingNetworkImage(
                          url: '$kApiBaseUrl${b.aboutImage}',
                          height: 56,
                          iconSize: 56,
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
        TextFormField(
          controller: _phone,
          keyboardType: TextInputType.phone,
          decoration: const InputDecoration(
            labelText: 'Phone',
            hintText: 'e.g. 07123 456789',
          ),
          validator: (v) {
            final digits = (v ?? '').replaceAll(RegExp(r'[^0-9+]'), '');
            if (digits.isEmpty) return 'Enter your business phone number';
            final normalized = digits.startsWith('+44')
                ? digits.substring(1)
                : digits.startsWith('44') && digits.length == 12
                    ? digits
                    : digits.startsWith('0') && digits.length == 11
                        ? '44${digits.substring(1)}'
                        : digits;
            return RegExp(r'^44\d{10}$').hasMatch(normalized)
                ? null
                : 'Enter a valid UK mobile number, e.g. 07123 456789';
          },
        ),
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
        const Text('Alerts', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
        const SizedBox(height: 12),
        Card(
          child: SwitchListTile(
            title: const Text('New booking sound', style: TextStyle(fontWeight: FontWeight.w700)),
            subtitle: const Text('Play a chime when a new booking arrives', style: TextStyle(fontSize: 13)),
            value: _bookingSound,
            onChanged: (v) async {
              setState(() => _bookingSound = v);
              await setBookingSoundEnabled(v);
            },
          ),
        ),
        const SizedBox(height: 24),
        const Text('SMS Notifications', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
        const SizedBox(height: 12),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'SMS credit balance',
                  style: TextStyle(fontWeight: FontWeight.w700),
                ),
                const SizedBox(height: 8),
                if (_smsBalance != null)
                  Text(
                    '${_smsBalance!.freeRemaining} of ${_smsBalance!.freeLimit} free texts remaining'
                    '${_smsBalance!.credits > 0 ? ' + ${_smsBalance!.credits} purchased' : ''}',
                    style: const TextStyle(color: WaveBookColors.muted, fontSize: 13),
                  ),
                const SizedBox(height: 8),
                if (_smsBalance != null && _smsBalance!.totalRemaining <= 0)
                  ElevatedButton(
                    onPressed: _buySmsCredits,
                    child: Text(
                      'Buy ${_smsBalance!.topupCredits} more texts for £${_smsBalance!.topupPriceGbp.toStringAsFixed(2)}',
                    ),
                  )
                else if (_smsBalance != null)
                  TextButton(
                    onPressed: _buySmsCredits,
                    child: Text(
                      'Buy ${_smsBalance!.topupCredits} more texts for £${_smsBalance!.topupPriceGbp.toStringAsFixed(2)}',
                    ),
                  ),
                const SizedBox(height: 8),
                const Text(
                  'Add optional details below (address, parking, what to bring).',
                  style: TextStyle(color: WaveBookColors.muted, fontSize: 13),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 12),
        TextFormField(
          controller: _smsInstructions,
          decoration: const InputDecoration(
            labelText: 'Special Instructions (optional)',
            helperText: 'e.g. address, parking details, what to bring — added to the confirmation text',
          ),
          maxLines: 3,
        ),
        const SizedBox(height: 24),
        const Text('Storefront', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
        const SizedBox(height: 12),
        Card(
          child: Column(
            children: [
              SwitchListTile(
                value: _storefrontEnabled,
                onChanged: (v) => setState(() => _storefrontEnabled = v),
                title: const Text('Sell products on your booking website', style: TextStyle(fontWeight: FontWeight.w700)),
                subtitle: const Text(
                  'Adds a Store menu to your customer booking site. Payment processing and transfer fees apply to every sale.',
                ),
              ),
              if (_storefrontEnabled)
                ListTile(
                  leading: const Icon(Icons.inventory_2_outlined, color: WaveBookColors.pink),
                  title: const Text('Manage Products', style: TextStyle(fontWeight: FontWeight.w700)),
                  trailing: const Icon(Icons.chevron_right),
                  onTap: _openProducts,
                ),
            ],
          ),
        ),
        const SizedBox(height: 24),
        const Text('Payout Details', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
        const SizedBox(height: 4),
        const Text(
          'We pay you for deposits and store sales by bank transfer. Add your bank details below.',
          style: TextStyle(color: WaveBookColors.muted, fontSize: 13),
        ),
        const SizedBox(height: 12),
        TextFormField(
          controller: _payoutBankName,
          decoration: const InputDecoration(labelText: 'Bank Name'),
        ),
        const SizedBox(height: 12),
        TextFormField(
          controller: _payoutAccountName,
          decoration: const InputDecoration(labelText: 'Account Holder Name'),
        ),
        const SizedBox(height: 12),
        Row(
          children: [
            Expanded(
              child: TextFormField(
                controller: _payoutSortCode,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(labelText: 'Sort Code'),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: TextFormField(
                controller: _payoutAccountNumber,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(labelText: 'Account Number'),
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
