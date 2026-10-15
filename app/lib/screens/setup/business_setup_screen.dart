import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../api/api_client.dart';
import '../../models/models.dart';
import '../../state/auth_state.dart';
import '../../theme.dart';

class BusinessSetupScreen extends StatefulWidget {
  const BusinessSetupScreen({super.key});

  @override
  State<BusinessSetupScreen> createState() => _BusinessSetupScreenState();
}

class _BusinessSetupScreenState extends State<BusinessSetupScreen> {
  final _formKey = GlobalKey<FormState>();
  final _name = TextEditingController();
  final _slug = TextEditingController();
  bool _loading = false;
  String? _error;

  @override
  void dispose() {
    _name.dispose();
    _slug.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final api = ApiClient();
      final data = await api.post('/api/business', body: {
        'name': _name.text.trim(),
        'slug': _slug.text.trim().toLowerCase(),
      });
      final business = Business.fromJson(data as Map<String, dynamic>);
      final auth = context.read<AuthState>();
      auth.refreshUser(User(
        id: auth.user!.id,
        email: auth.user!.email,
        fullName: auth.user!.fullName,
        phone: auth.user!.phone,
        role: 'owner',
        businessId: business.id,
      ));
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 480),
              child: Form(
                key: _formKey,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const Icon(Icons.waves, size: 56, color: WaveBookColors.pink),
                    const SizedBox(height: 8),
                    const Text(
                      'Set up your business',
                      textAlign: TextAlign.center,
                      style: TextStyle(fontSize: 22, fontWeight: FontWeight.w800, color: WaveBookColors.white),
                    ),
                    const SizedBox(height: 4),
                    const Text(
                      'This creates your booking website and dashboard.',
                      textAlign: TextAlign.center,
                      style: TextStyle(color: WaveBookColors.muted),
                    ),
                    const SizedBox(height: 28),
                    TextFormField(
                      controller: _name,
                      decoration: const InputDecoration(
                        labelText: 'Business Name',
                        hintText: 'e.g. SlayInstalls UK',
                        prefixIcon: Icon(Icons.storefront_outlined),
                      ),
                      validator: (v) => (v == null || v.trim().isEmpty) ? 'Enter your business name' : null,
                    ),
                    const SizedBox(height: 16),
                    TextFormField(
                      controller: _slug,
                      decoration: const InputDecoration(
                        labelText: 'Website Address',
                        hintText: 'slayinstalls',
                        prefixIcon: Icon(Icons.link),
                        suffixText: '.wavebook.com',
                      ),
                      validator: (v) {
                        if (v == null || v.trim().isEmpty) return 'Choose a website address';
                        if (!RegExp(r'^[a-z0-9-]{2,63}$').hasMatch(v.trim().toLowerCase())) {
                          return 'Use lowercase letters, numbers and hyphens only';
                        }
                        return null;
                      },
                    ),
                    if (_error != null) ...[
                      const SizedBox(height: 12),
                      Text(
                        _error!,
                        style: const TextStyle(color: WaveBookColors.danger),
                        textAlign: TextAlign.center,
                      ),
                    ],
                    const SizedBox(height: 24),
                    ElevatedButton(
                      onPressed: _loading ? null : _submit,
                      child: _loading
                          ? const SizedBox(
                              height: 22,
                              width: 22,
                              child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                            )
                          : const Text('Create My Booking Website'),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
