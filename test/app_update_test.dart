import 'package:flutter_test/flutter_test.dart';

import 'package:wavebook_app/services/app_update.dart';

void main() {
  group('compareVersions', () {
    test('newer patch, minor and major versions compare greater', () {
      expect(compareVersions('1.1.3', '1.1.2'), greaterThan(0));
      expect(compareVersions('1.2.0', '1.1.9'), greaterThan(0));
      expect(compareVersions('2.0.0', '1.9.9'), greaterThan(0));
    });

    test('equal versions compare as zero', () {
      expect(compareVersions('1.1.2', '1.1.2'), 0);
      expect(compareVersions('1.1', '1.1.0'), 0);
    });

    test('older versions compare less', () {
      expect(compareVersions('1.1.1', '1.1.2'), lessThan(0));
    });
  });
}
