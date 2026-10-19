import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../../../api/api_client.dart';
import '../../../models/models.dart';
import '../../../theme.dart';
import '../../../widgets/loading_network_image.dart';

class GalleryTab extends StatefulWidget {
  const GalleryTab({super.key});

  @override
  State<GalleryTab> createState() => _GalleryTabState();
}

class _GalleryTabState extends State<GalleryTab> {
  final _api = ApiClient();
  List<GalleryItem> _items = [];
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
      final data = await _api.get('/api/business/gallery');
      if (!mounted) return;
      setState(() {
        _items = (data as List)
            .map((g) => GalleryItem.fromJson(g as Map<String, dynamic>))
            .toList();
      });
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _pickAndUpload(int slot) async {
    final picker = ImagePicker();
    final file = await picker.pickImage(source: ImageSource.gallery, maxWidth: 1200);
    if (file == null) return;
    try {
      await _api.upload('/api/business/gallery/$slot', file.path, 'file');
      await _load();
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  Future<void> _remove(int slot) async {
    try {
      await _api.delete('/api/business/gallery/$slot');
      await _load();
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  Future<void> _editCaption(GalleryItem item) async {
    final controller = TextEditingController(text: item.caption);
    final caption = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Caption'),
        content: TextField(
          controller: controller,
          decoration: const InputDecoration(labelText: 'Caption'),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
          TextButton(onPressed: () => Navigator.pop(ctx, controller.text), child: const Text('Save')),
        ],
      ),
    );
    if (caption == null) return;
    try {
      await _api.patch('/api/business/gallery/${item.slot}?caption=${Uri.encodeQueryComponent(caption)}');
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
      appBar: AppBar(title: const Text('Gallery')),
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
    return GridView.builder(
      padding: const EdgeInsets.all(16),
      gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: 2,
        mainAxisSpacing: 12,
        crossAxisSpacing: 12,
        childAspectRatio: 1,
      ),
      itemCount: 8,
      itemBuilder: (context, i) {
        final item = _items.firstWhere(
          (g) => g.slot == i,
          orElse: () => GalleryItem(slot: i, path: '', caption: ''),
        );
        return Card(
          clipBehavior: Clip.antiAlias,
          child: Stack(
            fit: StackFit.expand,
            children: [
              if (item.path.isNotEmpty)
                LoadingNetworkImage(
                  url: '$kApiBaseUrl${item.path}',
                  fit: BoxFit.cover,
                )
              else
                const _EmptySlot(),
              Positioned(
                top: 6,
                right: 6,
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    if (item.path.isNotEmpty) ...[
                      IconButton.filledTonal(
                        icon: const Icon(Icons.edit_outlined, size: 18),
                        onPressed: () => _editCaption(item),
                        tooltip: 'Edit caption',
                      ),
                      IconButton.filledTonal(
                        icon: const Icon(Icons.delete_outline, size: 18, color: WaveBookColors.danger),
                        onPressed: () => _remove(item.slot),
                        tooltip: 'Remove',
                      ),
                    ],
                  ],
                ),
              ),
              if (item.path.isEmpty)
                Positioned.fill(
                  child: Material(
                    color: Colors.transparent,
                    child: InkWell(
                      onTap: () => _pickAndUpload(item.slot),
                      child: const Center(
                        child: Icon(Icons.add_a_photo_outlined, size: 32, color: WaveBookColors.muted),
                      ),
                    ),
                  ),
                ),
              if (item.caption.isNotEmpty)
                Positioned(
                  left: 0,
                  right: 0,
                  bottom: 0,
                  child: Container(
                    color: Colors.black54,
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                    child: Text(
                      item.caption,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(color: Colors.white, fontSize: 12),
                    ),
                  ),
                ),
            ],
          ),
        );
      },
    );
  }
}

class _EmptySlot extends StatelessWidget {
  const _EmptySlot();

  @override
  Widget build(BuildContext context) {
    return Container(
      color: Theme.of(context).colorScheme.surfaceContainerHighest.withValues(alpha: 0.4),
      child: const Center(
        child: Icon(Icons.image_outlined, size: 32, color: WaveBookColors.muted),
      ),
    );
  }
}
