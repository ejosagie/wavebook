import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../../api/api_client.dart';
import '../../../models/models.dart';
import '../../../theme.dart';

class AvailabilityTab extends StatefulWidget {
  const AvailabilityTab({super.key});

  @override
  State<AvailabilityTab> createState() => _AvailabilityTabState();
}

class _AvailabilityTabState extends State<AvailabilityTab> {
  final _api = ApiClient();
  Availability? _availability;
  bool _loading = true;
  bool _saving = false;
  String? _error;

  static const _dayNames = {
    'mon': 'Monday',
    'tue': 'Tuesday',
    'wed': 'Wednesday',
    'thu': 'Thursday',
    'fri': 'Friday',
    'sat': 'Saturday',
    'sun': 'Sunday',
  };

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
      final data = await _api.get('/api/availability');
      if (!mounted) return;
      setState(() => _availability = Availability.fromJson(data as Map<String, dynamic>));
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _save() async {
    if (_availability == null) return;
    setState(() => _saving = true);
    try {
      await _api.put('/api/availability', body: _availability!.toJson());
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Availability saved')),
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

  Future<void> _pickTime(String dayKey, bool isStart) async {
    final current = _availability!.workingDays[dayKey]!;
    final initial = isStart ? current.start : current.end;
    final picked = await showTimePicker(
      context: context,
      initialTime: _parseTime(initial),
    );
    if (picked == null) return;
    final formatted = DateFormat('HH:mm').format(DateTime(2000, 1, 1, picked.hour, picked.minute));
    setState(() {
      final day = _availability!.workingDays[dayKey]!;
      if (isStart) {
        _availability!.workingDays[dayKey] = DayConfig(enabled: day.enabled, start: formatted, end: day.end);
      } else {
        _availability!.workingDays[dayKey] = DayConfig(enabled: day.enabled, start: day.start, end: formatted);
      }
    });
  }

  TimeOfDay _parseTime(String t) {
    final parts = t.split(':');
    return TimeOfDay(hour: int.parse(parts[0]), minute: int.parse(parts[1]));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Availability'),
        actions: [
          if (_availability != null)
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
    final avail = _availability!;
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        const Text('Working Hours', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
        const SizedBox(height: 4),
        const Text(
          'Toggle days on/off and set opening and closing times.',
          style: TextStyle(color: WaveBookColors.muted),
        ),
        const SizedBox(height: 16),
        ..._dayNames.entries.map((entry) {
          final day = avail.workingDays[entry.key];
          if (day == null) return const SizedBox.shrink();
          return Card(
            margin: const EdgeInsets.only(bottom: 8),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
              child: Row(
                children: [
                  Switch(
                    value: day.enabled,
                    onChanged: (v) => setState(() {
                      avail.workingDays[entry.key] =
                          DayConfig(enabled: v, start: day.start, end: day.end);
                    }),
                  ),
                  SizedBox(
                    width: 90,
                    child: Text(entry.value, style: const TextStyle(fontWeight: FontWeight.w600)),
                  ),
                  if (day.enabled) ...[
                    TextButton(
                      onPressed: () => _pickTime(entry.key, true),
                      child: Text(day.start),
                    ),
                    const Text('—'),
                    TextButton(
                      onPressed: () => _pickTime(entry.key, false),
                      child: Text(day.end),
                    ),
                  ] else
                    const Text('Closed', style: TextStyle(color: WaveBookColors.muted)),
                ],
              ),
            ),
          );
        }),
        const SizedBox(height: 16),
        const Text('Slot Interval', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
        const SizedBox(height: 8),
        Card(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12),
            child: DropdownButtonFormField<int>(
              initialValue: avail.slotInterval,
              decoration: const InputDecoration(labelText: 'Minutes between slots'),
              items: [15, 30, 45, 60, 90, 120]
                  .map((v) => DropdownMenuItem(value: v, child: Text('$v minutes')))
                  .toList(),
              onChanged: (v) {
                if (v != null) setState(() => avail.slotInterval = v);
              },
            ),
          ),
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
              : const Text('Save Availability'),
        ),
      ],
    );
  }
}
