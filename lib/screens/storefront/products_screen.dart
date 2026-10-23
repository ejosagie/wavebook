import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../../api/api_client.dart';
import '../../models/models.dart';
import '../../theme.dart';
import '../../widgets/loading_network_image.dart';

const _maxProductImages = 4;

String _photoUrl(String path) => path.startsWith('http') ? path : '$kApiBaseUrl$path';

class ProductsScreen extends StatefulWidget {
  const ProductsScreen({super.key});

  @override
  State<ProductsScreen> createState() => _ProductsScreenState();
}

class _ProductsScreenState extends State<ProductsScreen> {
  final _api = ApiClient();
  List<Product> _products = [];
  String _currency = 'GBP';
  bool _loading = true;
  String? _error;
  final Map<int, double> _uploading = {};

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
      final data = await _api.get('/api/products');
      String currency = 'GBP';
      try {
        final biz = await _api.get('/api/business') as Map<String, dynamic>;
        currency = biz['currency']?.toString() ?? 'GBP';
      } catch (_) {
        // Currency is a display nicety; fall back to GBP.
      }
      if (!mounted) return;
      setState(() {
        _products = (data as List).map((p) => Product.fromJson(p as Map<String, dynamic>)).toList();
        _currency = currency;
      });
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _addProduct() async {
    final result = await _showProductDialog();
    if (result == null) return;
    try {
      await _api.post('/api/products', body: result);
      await _load();
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  Future<void> _editProduct(Product product) async {
    final result = await _showProductDialog(product: product);
    if (result == null) return;
    try {
      await _api.patch('/api/products/${product.id}', body: result);
      await _load();
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  Future<void> _toggleActive(Product product) async {
    try {
      await _api.patch('/api/products/${product.id}', body: {'active': !product.active});
      await _load();
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  Future<void> _deleteProduct(Product product) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Delete product?'),
        content: Text('"${product.name}" will be removed from your store.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          TextButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Delete', style: TextStyle(color: WaveBookColors.danger)),
          ),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await _api.delete('/api/products/${product.id}');
      await _load();
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  Future<void> _uploadImage(Product product) async {
    if (product.images.length >= _maxProductImages) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('You can add up to 4 photos per product. Remove one first.')),
      );
      return;
    }
    final picker = ImagePicker();
    final file = await picker.pickImage(source: ImageSource.gallery, maxWidth: 1200);
    if (file == null) return;
    setState(() => _uploading[product.id] = 0);
    try {
      await _api.upload(
        '/api/products/${product.id}/images',
        file.path,
        'file',
        onProgress: (p) {
          if (mounted) setState(() => _uploading[product.id] = p);
        },
      );
      await _load();
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      }
    } finally {
      if (mounted) setState(() => _uploading.remove(product.id));
    }
  }

  Future<void> _deleteImage(Product product, ProductImage image) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Remove photo?'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          TextButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Remove', style: TextStyle(color: WaveBookColors.danger)),
          ),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await _api.delete('/api/products/${product.id}/images/${image.id}');
      await _load();
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  void _openViewer(List<ProductImage> images, int index) {
    Navigator.of(context).push(
      MaterialPageRoute(
        fullscreenDialog: true,
        builder: (_) => _ImageViewer(urls: images.map((i) => i.path).toList(), initialIndex: index),
      ),
    );
  }

  Future<Map<String, dynamic>?> _showProductDialog({Product? product}) {
    return Navigator.of(context).push<Map<String, dynamic>>(
      MaterialPageRoute(builder: (_) => _ProductFormPage(product: product, currency: _currency)),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _addProduct,
        icon: const Icon(Icons.add),
        label: const Text('Add Product'),
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
    if (_products.isEmpty) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.inventory_2_outlined, size: 56, color: WaveBookColors.muted),
            const SizedBox(height: 12),
            const Text('No products yet. Tap Add Product to start selling.'),
          ],
        ),
      );
    }
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView.builder(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 88),
        itemCount: _products.length,
        itemBuilder: (context, index) {
          final p = _products[index];
          return Card(
            clipBehavior: Clip.antiAlias,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                _ProductPhotos(
                  images: p.images,
                  uploadProgress: _uploading[p.id],
                  onOpen: (i) => _openViewer(p.images, i),
                  onRemove: (i) => _deleteImage(p, p.images[i]),
                  onAdd: () => _uploadImage(p),
                ),
                ListTile(
                  title: Text(p.name, style: const TextStyle(fontWeight: FontWeight.w700)),
                  subtitle: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('${currencySymbol(_currency)}${p.price.toStringAsFixed(2)}${p.active ? '' : ' · hidden'}'),
                      if (p.stock != null)
                        Padding(
                          padding: const EdgeInsets.only(top: 2),
                          child: Text(
                            p.stock! <= 0
                                ? 'Out of stock'
                                : p.stock! < 5
                                    ? 'Only ${p.stock} left in stock'
                                    : '${p.stock} in stock',
                            style: TextStyle(
                              fontSize: 12,
                              fontWeight: FontWeight.w700,
                              color: p.stock! < 5 ? WaveBookColors.danger : WaveBookColors.success,
                            ),
                          ),
                        ),
                    ],
                  ),
                  trailing: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      IconButton(
                        icon: Icon(p.active ? Icons.visibility : Icons.visibility_off),
                        tooltip: p.active ? 'Hide product' : 'Show product',
                        onPressed: () => _toggleActive(p),
                      ),
                      IconButton(
                        icon: const Icon(Icons.edit_outlined),
                        tooltip: 'Edit',
                        onPressed: () => _editProduct(p),
                      ),
                      IconButton(
                        icon: const Icon(Icons.delete_outline, color: WaveBookColors.danger),
                        tooltip: 'Delete',
                        onPressed: () => _deleteProduct(p),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          );
        },
      ),
    );
  }
}

class _ProductPhotos extends StatefulWidget {
  final List<ProductImage> images;
  final double? uploadProgress;
  final void Function(int index) onOpen;
  final void Function(int index) onRemove;
  final VoidCallback onAdd;

  const _ProductPhotos({
    required this.images,
    required this.uploadProgress,
    required this.onOpen,
    required this.onRemove,
    required this.onAdd,
  });

  @override
  State<_ProductPhotos> createState() => _ProductPhotosState();
}

class _ProductPhotosState extends State<_ProductPhotos> {
  final _controller = PageController();
  int _index = 0;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final images = widget.images;
    final progress = widget.uploadProgress;
    if (images.isEmpty && progress == null) {
      return Container(
        height: 140,
        color: WaveBookColors.muted.withValues(alpha: 0.08),
        alignment: Alignment.center,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.image_outlined, size: 40, color: WaveBookColors.muted),
            TextButton.icon(
              onPressed: widget.onAdd,
              icon: const Icon(Icons.add_a_photo_outlined),
              label: const Text('Add photo'),
            ),
          ],
        ),
      );
    }
    final current = images.isEmpty ? 0 : _index.clamp(0, images.length - 1).toInt();
    return SizedBox(
      height: 200,
      child: Stack(
        fit: StackFit.expand,
        children: [
          if (images.isNotEmpty)
            PageView.builder(
              controller: _controller,
              itemCount: images.length,
              onPageChanged: (i) => setState(() => _index = i),
              itemBuilder: (_, i) => GestureDetector(
                onTap: () => widget.onOpen(i),
                child: LoadingNetworkImage(url: _photoUrl(images[i].path), fit: BoxFit.cover),
              ),
            ),
          if (images.isNotEmpty)
            Positioned(
              top: 8,
              left: 8,
              child: _Chip(text: '${current + 1} / ${images.length}'),
            ),
          if (images.isNotEmpty)
            Positioned(
              top: 4,
              right: 4,
              child: _CircleAction(
                icon: Icons.delete_outline,
                tooltip: 'Remove photo',
                onPressed: () => widget.onRemove(current),
              ),
            ),
          if (images.isNotEmpty && images.length < _maxProductImages)
            Positioned(
              bottom: 4,
              right: 4,
              child: _CircleAction(
                icon: Icons.add_a_photo_outlined,
                tooltip: 'Add photo',
                onPressed: widget.onAdd,
              ),
            ),
          if (images.length > 1)
            Positioned(
              bottom: 10,
              left: 0,
              right: 0,
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: List.generate(
                  images.length,
                  (i) => Container(
                    width: 7,
                    height: 7,
                    margin: const EdgeInsets.symmetric(horizontal: 3),
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: i == current ? Colors.white : Colors.white54,
                    ),
                  ),
                ),
              ),
            ),
          if (progress != null)
            Container(
              color: Colors.black54,
              padding: const EdgeInsets.symmetric(horizontal: 32),
              alignment: Alignment.center,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  LinearProgressIndicator(value: progress >= 1 ? null : progress),
                  const SizedBox(height: 10),
                  Text(
                    progress >= 1
                        ? 'Processing photo, please wait...'
                        : 'Uploading photo... ${(progress * 100).round()}%',
                    style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w600),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

class _Chip extends StatelessWidget {
  final String text;

  const _Chip({required this.text});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(color: Colors.black54, borderRadius: BorderRadius.circular(12)),
      child: Text(text, style: const TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.w700)),
    );
  }
}

class _CircleAction extends StatelessWidget {
  final IconData icon;
  final String tooltip;
  final VoidCallback onPressed;

  const _CircleAction({required this.icon, required this.tooltip, required this.onPressed});

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.black54,
      shape: const CircleBorder(),
      child: IconButton(
        icon: Icon(icon, color: Colors.white, size: 20),
        tooltip: tooltip,
        onPressed: onPressed,
      ),
    );
  }
}

class _ImageViewer extends StatefulWidget {
  final List<String> urls;
  final int initialIndex;

  const _ImageViewer({required this.urls, required this.initialIndex});

  @override
  State<_ImageViewer> createState() => _ImageViewerState();
}

class _ImageViewerState extends State<_ImageViewer> {
  late final PageController _controller = PageController(initialPage: widget.initialIndex);
  late int _index = widget.initialIndex;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.black,
        foregroundColor: Colors.white,
        title: Text('${_index + 1} / ${widget.urls.length}'),
      ),
      body: PageView.builder(
        controller: _controller,
        itemCount: widget.urls.length,
        onPageChanged: (i) => setState(() => _index = i),
        itemBuilder: (_, i) => InteractiveViewer(
          minScale: 1,
          maxScale: 4,
          child: Center(
            child: LoadingNetworkImage(
              url: _photoUrl(widget.urls[i]),
              fit: BoxFit.contain,
              iconSize: 64,
            ),
          ),
        ),
      ),
    );
  }
}

class _ProductFormPage extends StatefulWidget {
  final Product? product;
  final String currency;

  const _ProductFormPage({this.product, this.currency = 'GBP'});

  @override
  State<_ProductFormPage> createState() => _ProductFormPageState();
}

class _ProductFormPageState extends State<_ProductFormPage> {
  late final TextEditingController _name;
  late final TextEditingController _description;
  late final TextEditingController _price;
  late final TextEditingController _stock;

  @override
  void initState() {
    super.initState();
    _name = TextEditingController(text: widget.product?.name ?? '');
    _description = TextEditingController(text: widget.product?.description ?? '');
    _price = TextEditingController(
      text: widget.product != null ? widget.product!.price.toStringAsFixed(2) : '',
    );
    _stock = TextEditingController(
      text: widget.product?.stock != null ? widget.product!.stock.toString() : '',
    );
  }

  @override
  void dispose() {
    _name.dispose();
    _description.dispose();
    _price.dispose();
    _stock.dispose();
    super.dispose();
  }

  void _save() {
    final p = double.tryParse(_price.text) ?? 0;
    if (_name.text.trim().isEmpty || p <= 0) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Enter a product name and a price above 0')),
      );
      return;
    }
    final stockText = _stock.text.trim();
    final stock = stockText.isEmpty ? null : int.tryParse(stockText);
    if (stockText.isNotEmpty && stock == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Stock must be a whole number')),
      );
      return;
    }
    Navigator.pop(context, {
      'name': _name.text.trim(),
      'description': _description.text.trim(),
      'price': p,
      'stock': stock,
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        leading: const BackButton(),
        title: Text(widget.product == null ? 'Add Product' : 'Edit Product'),
        actions: [
          TextButton(
            onPressed: _save,
            child: const Text('Save', style: TextStyle(fontWeight: FontWeight.w700)),
          ),
        ],
      ),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 24, 16, 24),
          children: [
            TextField(
              controller: _name,
              textCapitalization: TextCapitalization.sentences,
              decoration: const InputDecoration(labelText: 'Product name'),
            ),
            const SizedBox(height: 16),
            TextField(
              controller: _description,
              decoration: const InputDecoration(labelText: 'Description'),
              minLines: 3,
              maxLines: 6,
            ),
            const SizedBox(height: 16),
            TextField(
              controller: _price,
              keyboardType: const TextInputType.numberWithOptions(decimal: true),
              decoration: InputDecoration(labelText: 'Price (${currencySymbol(widget.currency)})'),
            ),
            const SizedBox(height: 16),
            TextField(
              controller: _stock,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(
                labelText: 'Stock (optional)',
                helperText: 'Leave empty for unlimited. Warns in red when under 5.',
              ),
            ),
            const SizedBox(height: 24),
            ElevatedButton(onPressed: _save, child: const Text('Save product')),
            const SizedBox(height: 8),
            OutlinedButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Cancel'),
            ),
          ],
        ),
      ),
    );
  }
}
