import 'package:flutter/material.dart';

import '../../../api/api_client.dart';
import '../../../models/models.dart';
import '../../../theme.dart';

class FeedbackTab extends StatefulWidget {
  const FeedbackTab({super.key});

  @override
  State<FeedbackTab> createState() => _FeedbackTabState();
}

class _FeedbackTabState extends State<FeedbackTab> {
  final _api = ApiClient();
  List<FeedbackItem> _feedback = [];
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
      final data = await _api.get('/api/feedback');
      if (!mounted) return;
      setState(() {
        _feedback = (data as List)
            .map((f) => FeedbackItem.fromJson(f as Map<String, dynamic>))
            .toList();
      });
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _delete(FeedbackItem item) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Delete review?'),
        content: Text('Remove the review from ${item.customerName}?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text('Delete', style: TextStyle(color: WaveBookColors.danger)),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    try {
      await _api.delete('/api/feedback/${item.id}');
      if (!mounted) return;
      setState(() => _feedback.removeWhere((f) => f.id == item.id));
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Feedback')),
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
    if (_feedback.isEmpty) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(32),
          child: Text(
            'No feedback yet. Customers can leave reviews on your booking page.',
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
        itemCount: _feedback.length,
        itemBuilder: (context, i) {
          final f = _feedback[i];
          final bookingInfo = f.bookingDate.isNotEmpty
              ? '${f.serviceName} · ${f.bookingDate} ${f.bookingTime}'
              : '';
          return Card(
            margin: const EdgeInsets.only(bottom: 12),
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          f.customerName,
                          style: const TextStyle(fontWeight: FontWeight.w700),
                        ),
                      ),
                      IconButton(
                        icon: const Icon(Icons.delete_outline, size: 20),
                        color: WaveBookColors.muted,
                        tooltip: 'Delete review',
                        onPressed: () => _delete(f),
                      ),
                    ],
                  ),
                  Row(
                    children: List.generate(5, (s) {
                      return Icon(
                        s < f.rating ? Icons.star : Icons.star_border,
                        size: 18,
                        color: const Color(0xFFF59E0B),
                      );
                    }),
                  ),
                  if (f.comment.isNotEmpty)
                    Padding(
                      padding: const EdgeInsets.only(top: 8),
                      child: Text(f.comment),
                    ),
                  if (bookingInfo.isNotEmpty)
                    Padding(
                      padding: const EdgeInsets.only(top: 8),
                      child: Text(
                        bookingInfo,
                        style: const TextStyle(fontSize: 12, color: WaveBookColors.muted),
                      ),
                    ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }
}
