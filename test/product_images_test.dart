import 'package:flutter_test/flutter_test.dart';
import 'package:wavebook_app/models/models.dart';

void main() {
  test('Product.fromJson reads up to four images in order', () {
    final product = Product.fromJson({
      'id': 7,
      'name': 'Candle',
      'description': '',
      'price': 5,
      'image_path': '/uploads/a.png',
      'active': 1,
      'sort_order': 0,
      'images': [
        {'id': 1, 'path': '/uploads/a.png'},
        {'id': 2, 'path': '/uploads/b.png'},
      ],
    });
    expect(product.images.map((i) => i.id).toList(), [1, 2]);
    expect(product.images.first.path, '/uploads/a.png');
  });

  test('Product.fromJson defaults to no images when the field is missing', () {
    final product = Product.fromJson({
      'id': 8,
      'name': 'Soap',
      'price': 3,
      'active': 1,
    });
    expect(product.images, isEmpty);
    expect(product.imagePath, '');
  });
}
