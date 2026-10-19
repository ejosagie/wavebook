import 'package:flutter/material.dart';

import '../../../api/api_client.dart';
import '../../../models/models.dart';
import '../../../theme.dart';

class ServicesTab extends StatefulWidget {
  const ServicesTab({super.key});

  @override
  State<ServicesTab> createState() => _ServicesTabState();
}

class _ServicesTabState extends State<ServicesTab> {
  final _api = ApiClient();
  List<Service> _services = [];
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
      final data = await _api.get('/api/services');
      if (!mounted) return;
      setState(() {
        _services = (data as List).map((s) => Service.fromJson(s as Map<String, dynamic>)).toList();
      });
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _openEditor([Service? service]) async {
    final result = await Navigator.of(context).push<bool>(
      MaterialPageRoute(builder: (_) => ServiceEditorScreen(service: service)),
    );
    if (result == true) _load();
  }

  Future<void> _delete(Service service) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Delete service?'),
        content: Text('Delete "${service.name}"?'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          TextButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Delete', style: TextStyle(color: WaveBookColors.danger)),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    try {
      await _api.delete('/api/services/${service.id}');
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
        title: const Text('Services'),
        actions: [IconButton(icon: const Icon(Icons.refresh), onPressed: _load)],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => _openEditor(),
        icon: const Icon(Icons.add),
        label: const Text('Add Service'),
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
    if (_services.isEmpty) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(32),
          child: Text(
            'No services yet. Tap "Add Service" to create your first one.',
            textAlign: TextAlign.center,
            style: TextStyle(color: WaveBookColors.muted),
          ),
        ),
      );
    }
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView.builder(
        padding: const EdgeInsets.all(16),
        itemCount: _services.length,
        itemBuilder: (context, i) {
          final s = _services[i];
          return Card(
            margin: const EdgeInsets.only(bottom: 12),
            child: ListTile(
              title: Text(s.name, style: const TextStyle(fontWeight: FontWeight.w700)),
              subtitle: Text(
                '${s.description}\n£${s.price.toStringAsFixed(2)} · ${_formatDuration(s.durationMinutes)}',
                maxLines: 3,
                overflow: TextOverflow.ellipsis,
              ),
              isThreeLine: true,
              trailing: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  IconButton(
                    icon: const Icon(Icons.edit_outlined),
                    onPressed: () => _openEditor(s),
                  ),
                  IconButton(
                    icon: const Icon(Icons.delete_outline, color: WaveBookColors.danger),
                    onPressed: () => _delete(s),
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }

  String _formatDuration(int minutes) {
    final h = minutes ~/ 60;
    final m = minutes % 60;
    if (h > 0 && m > 0) return '$h hr $m min';
    if (h > 0) return '$h hr';
    return '$m min';
  }
}

class ServiceEditorScreen extends StatefulWidget {
  final Service? service;

  const ServiceEditorScreen({super.key, this.service});

  @override
  State<ServiceEditorScreen> createState() => _ServiceEditorScreenState();
}

class _ServiceEditorScreenState extends State<ServiceEditorScreen> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _name;
  late final TextEditingController _description;
  late final TextEditingController _price;
  late final TextEditingController _duration;
  late final List<Map<String, dynamic>> _questions;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    _name = TextEditingController(text: widget.service?.name ?? '');
    _description = TextEditingController(text: widget.service?.description ?? '');
    _price = TextEditingController(
      text: widget.service != null ? widget.service!.price.toStringAsFixed(2) : '',
    );
    _duration = TextEditingController(
      text: widget.service?.durationMinutes.toString() ?? '60',
    );
    _questions = widget.service?.questions.map((q) => Map<String, dynamic>.from(q)).toList() ?? [];
  }

  @override
  void dispose() {
    _name.dispose();
    _description.dispose();
    _price.dispose();
    _duration.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _saving = true);
    final body = {
      'name': _name.text.trim(),
      'description': _description.text.trim(),
      'price': double.parse(_price.text),
      'duration_minutes': int.parse(_duration.text),
      'questions': _questions,
    };
    try {
      final api = ApiClient();
      if (widget.service == null) {
        await api.post('/api/services', body: body);
      } else {
        await api.patch('/api/services/${widget.service!.id}', body: body);
      }
      if (mounted) Navigator.of(context).pop(true);
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _editQuestion(int? index) async {
    final result = await showDialog<Map<String, dynamic>>(
      context: context,
      builder: (_) => _IntakeQuestionDialog(question: index == null ? null : _questions[index]),
    );
    if (result == null) return;
    setState(() {
      if (index == null) {
        result['id'] = 'q${DateTime.now().millisecondsSinceEpoch}';
        _questions.add(result);
      } else {
        _questions[index] = result;
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(widget.service == null ? 'Add Service' : 'Edit Service')),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Form(
            key: _formKey,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                TextFormField(
                  controller: _name,
                  decoration: const InputDecoration(labelText: 'Service Name'),
                  validator: (v) => (v == null || v.trim().isEmpty) ? 'Enter a name' : null,
                ),
                const SizedBox(height: 16),
                TextFormField(
                  controller: _description,
                  decoration: const InputDecoration(labelText: 'Description'),
                  maxLines: 3,
                ),
                const SizedBox(height: 16),
                TextFormField(
                  controller: _price,
                  keyboardType: const TextInputType.numberWithOptions(decimal: true),
                  decoration: const InputDecoration(labelText: 'Price (£)', prefixText: '£ '),
                  validator: (v) {
                    final val = double.tryParse(v ?? '');
                    return (val == null || val < 0) ? 'Enter a valid price' : null;
                  },
                ),
                const SizedBox(height: 16),
                TextFormField(
                  controller: _duration,
                  keyboardType: TextInputType.number,
                  decoration: const InputDecoration(labelText: 'Duration (minutes)'),
                  validator: (v) {
                    final val = int.tryParse(v ?? '');
                    return (val == null || val < 5) ? 'Minimum 5 minutes' : null;
                  },
                ),
                const SizedBox(height: 24),
                Text(
                  'Intake questions',
                  style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w800),
                ),
                const SizedBox(height: 4),
                Text(
                  'Questions customers answer before booking this service.',
                  style: TextStyle(fontSize: 13, color: WaveBookColors.muted),
                ),
                const SizedBox(height: 8),
                if (_questions.isEmpty)
                  Text(
                    'No questions yet.',
                    style: TextStyle(fontSize: 13, color: WaveBookColors.muted),
                  )
                else
                  ..._questions.asMap().entries.map(
                        (e) => Card(
                          margin: const EdgeInsets.only(bottom: 8),
                          child: ListTile(
                            dense: true,
                            title: Text(
                              e.value['label']?.toString() ?? 'Question',
                              style: const TextStyle(fontWeight: FontWeight.w700),
                            ),
                            subtitle: Text(
                              '${e.value['type'] == 'choice' ? 'Multiple choice' : 'Text'}'
                              '${e.value['required'] == true ? ' · Required' : ''}',
                            ),
                            trailing: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                IconButton(
                                  icon: const Icon(Icons.edit_outlined, size: 20),
                                  tooltip: 'Edit question',
                                  onPressed: () => _editQuestion(e.key),
                                ),
                                IconButton(
                                  icon: const Icon(Icons.delete_outline, size: 20, color: WaveBookColors.danger),
                                  tooltip: 'Remove question',
                                  onPressed: () => setState(() => _questions.removeAt(e.key)),
                                ),
                              ],
                            ),
                          ),
                        ),
                      ),
                OutlinedButton.icon(
                  onPressed: () => _editQuestion(null),
                  icon: const Icon(Icons.add),
                  label: const Text('Add question'),
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
                      : Text(widget.service == null ? 'Add Service' : 'Save Changes'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _IntakeQuestionDialog extends StatefulWidget {
  final Map<String, dynamic>? question;

  const _IntakeQuestionDialog({this.question});

  @override
  State<_IntakeQuestionDialog> createState() => _IntakeQuestionDialogState();
}

class _IntakeQuestionDialogState extends State<_IntakeQuestionDialog> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _label;
  late final TextEditingController _options;
  late String _type;
  late bool _required;

  @override
  void initState() {
    super.initState();
    final q = widget.question;
    _label = TextEditingController(text: q?['label']?.toString() ?? '');
    _type = q?['type']?.toString() ?? 'text';
    _required = q?['required'] == true;
    _options = TextEditingController(
      text: (q?['options'] as List? ?? []).join(', '),
    );
  }

  @override
  void dispose() {
    _label.dispose();
    _options.dispose();
    super.dispose();
  }

  void _save() {
    if (!_formKey.currentState!.validate()) return;
    final options = _options.text
        .split(',')
        .map((o) => o.trim())
        .where((o) => o.isNotEmpty)
        .toList();
    Navigator.of(context).pop({
      'label': _label.text.trim(),
      'type': _type,
      'required': _required,
      'options': _type == 'choice' ? options : <String>[],
    });
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text(widget.question == null ? 'Add question' : 'Edit question'),
      content: SingleChildScrollView(
        child: Form(
          key: _formKey,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              TextFormField(
                controller: _label,
                decoration: const InputDecoration(labelText: 'Question'),
                validator: (v) => (v == null || v.trim().isEmpty) ? 'Enter the question' : null,
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<String>(
                initialValue: _type,
                decoration: const InputDecoration(labelText: 'Answer type'),
                items: const [
                  DropdownMenuItem(value: 'text', child: Text('Text')),
                  DropdownMenuItem(value: 'choice', child: Text('Multiple choice')),
                ],
                onChanged: (v) => setState(() => _type = v ?? 'text'),
              ),
              if (_type == 'choice') ...[
                const SizedBox(height: 12),
                TextFormField(
                  controller: _options,
                  decoration: const InputDecoration(
                    labelText: 'Options',
                    hintText: 'Comma separated, e.g. Email, Phone, WhatsApp',
                  ),
                  validator: (v) {
                    final opts = (v ?? '').split(',').map((o) => o.trim()).where((o) => o.isNotEmpty);
                    return opts.length >= 2 ? null : 'Enter at least two options';
                  },
                ),
              ],
              const SizedBox(height: 12),
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Required'),
                value: _required,
                onChanged: (v) => setState(() => _required = v),
              ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.of(context).pop(), child: const Text('Cancel')),
        ElevatedButton(onPressed: _save, child: const Text('Save')),
      ],
    );
  }
}
