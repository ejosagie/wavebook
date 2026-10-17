import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../../api/api_client.dart';
import '../../models/models.dart';
import '../../theme.dart';

class ProductsScreen extends StatefulWidget {
  const ProductsScreen({super.key});

  @override
  State<ProductsScreen> createState() => _ProductsScreenState();
}

class _ProductsScreenState extends State<ProductsScreen> {
  final _api = ApiClient();
  List<Product> _products = [];
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
      final data = await _api.get('/api/products');
      if (!mounted) return;
      setState(() {
        _products = (data as List).map((p) => Product.fromJson(p as Map<String, dynamic>)).toList();
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
    final picker = ImagePicker();
    final file = await picker.pickImage(source: ImageSource.gallery, maxWidth: 1200);
    if (file == null) return;
    try {
      await _api.upload('/api/products/${product.id}/image', file.path, 'file');
      await _load();
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  Future<Map<String, dynamic>?> _showProductDialog({Product? product}) async {
    final name = TextEditingController(text: product?.name ?? '');
    final description = TextEditingController(text: product?.description ?? '');
    final price = TextEditingController(
      text: product != null ? product.price.toStringAsFixed(2) : '',
    );
    final result = await showDialog<Map<String, dynamic>>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(product == null ? 'Add Product' : 'Edit Product'),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: name,
                decoration: const InputDecoration(labelText: 'Product name'),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: description,
                decoration: const InputDecoration(labelText: 'Description'),
                maxLines: 3,
              ),
              const SizedBox(height: 12),
              TextField(
                controller: price,
                keyboardType: const TextInputType.numberWithOptions(decimal: true),
                decoration: const InputDecoration(labelText: 'Price (£)'),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
          TextButton(
            onPressed: () {
              final p = double.tryParse(price.text) ?? 0;
              if (name.text.trim().isEmpty || p <= 0) return;
              Navigator.pop(ctx, {
                'name': name.text.trim(),
                'description': description.text.trim(),
                'price': p,
              });
            },
            child: const Text('Save'),
          ),
        ],
      ),
    );
    name.dispose();
    description.dispose();
    price.dispose();
    return result;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Products'),
        actions: [
          IconButton(
            icon: const Icon(Icons.add),
            tooltip: 'Add product',
            onPressed: _addProduct,
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
    if (_products.isEmpty) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.inventory_2_outlined, size: 56, color: WaveBookColors.muted),
            const SizedBox(height: 12),
            const Text('No products yet. Add your first product to start selling.'),
            const SizedBox(height: 16),
            ElevatedButton(onPressed: _addProduct, child: const Text('Add Product')),
          ],
        ),
      );
    }
    return ListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: _products.length,
      itemBuilder: (context, index) {
        final p = _products[index];
        return Card(
          child: ListTile(
            leading: p.imagePath.isNotEmpty
                ? ClipRRect(
                    borderRadius: BorderRadius.circular(8),
                    child: Image.network(
                      '$kApiBaseUrl${p.imagePath}',
                      width: 48,
                      height: 48,
                      fit: BoxFit.cover,
                      errorBuilder: (_, _, _) => const Icon(Icons.image, size: 48),
                    ),
                  )
                : const Icon(Icons.image_outlined, size: 48, color: WaveBookColors.muted),
            title: Text(p.name, style: const TextStyle(fontWeight: FontWeight.w700)),
            subtitle: Text('£${p.price.toStringAsFixed(2)}${p.active ? '' : ' · hidden'}'),
            trailing: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                IconButton(
                  icon: const Icon(Icons.photo_outlined),
                  tooltip: 'Upload image',
                  onPressed: () => _uploadImage(p),
                ),
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
        );
      },
    );
  }
}
